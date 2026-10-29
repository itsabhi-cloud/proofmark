"""JSON API. Every write checks the caller's role on the server."""
import json
from functools import wraps

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash

from . import services as S
from .db import get_db, init_schema, log_event, now_iso, one, rows
from .engine import ai
from .engine.compiler import compile_guidelines
from .engine.parse import ParseError, extract_text
from .engine.scan import apply_fixes, rewrite_draft
from .seed import SAMPLE_DRAFTS, SAMPLE_GUIDE_UPDATE

bp = Blueprint("api", __name__, url_prefix="/api")

CONTENT_TYPES = ["Social post", "Ad", "Email", "Blog post", "Product page", "Press release"]
DISMISS_REASONS = ["False alarm", "Rule unclear", "Approved exception"]
EDITABLE = ("draft", "changes_requested")


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


@bp.errorhandler(ApiError)
def _api_error(e):
    return jsonify({"error": e.message}), e.status


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return one(get_db(), "SELECT id, name, email, role, team FROM users WHERE id=?", (uid,))


def login_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                raise ApiError("Sign in to continue.", 401)
            if roles and user["role"] not in roles:
                raise ApiError("Your role cannot do this.", 403)
            return fn(user, *args, **kwargs)
        return wrapper
    return deco


def body():
    return request.get_json(silent=True) or {}


def text_field(data, key, required=True, max_len=20000):
    value = (data.get(key) or "").strip() if isinstance(data.get(key, ""), str) else ""
    if required and not value:
        raise ApiError(f"{key.replace('_', ' ').capitalize()} is required.")
    if len(value) > max_len:
        raise ApiError(f"{key.replace('_', ' ').capitalize()} is too long (max {max_len} characters).")
    return value


def get_draft_or_404(conn, draft_id):
    draft = one(conn, "SELECT * FROM drafts WHERE id=?", (draft_id,))
    if not draft:
        raise ApiError("Draft not found.", 404)
    return draft


def can_edit(user, draft):
    return (user["role"] == "owner" or draft["creator_id"] == user["id"]) and draft["status"] in EDITABLE


# ------------------------------------------------------------------ auth

@bp.post("/auth/login")
def login():
    data = body()
    conn = get_db()
    if data.get("demo_email"):
        user = one(conn, "SELECT * FROM users WHERE email=?", (data["demo_email"],))
    else:
        user = one(conn, "SELECT * FROM users WHERE email=?", ((data.get("email") or "").strip().lower(),))
        if not user or not check_password_hash(user["pw_hash"], data.get("password") or ""):
            raise ApiError("Email or password is incorrect.", 401)
    if not user:
        raise ApiError("Unknown demo account.", 404)
    session.clear()
    session["uid"] = user["id"]
    return jsonify({"user": {k: user[k] for k in ("id", "name", "email", "role", "team")}})


@bp.post("/auth/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.get("/auth/me")
def me():
    return jsonify({"user": current_user()})


@bp.get("/demo-accounts")
def demo_accounts():
    return jsonify({"accounts": rows(get_db(), "SELECT name, email, role, team FROM users ORDER BY id")})


@bp.get("/system")
def system():
    conn = get_db()
    return jsonify({
        "ai": ai.public_config(),
        "brand": one(conn, "SELECT * FROM brand LIMIT 1"),
        "content_types": CONTENT_TYPES,
        "dismiss_reasons": DISMISS_REASONS,
        "confidential_facts": one(conn, "SELECT COUNT(*) AS n FROM facts WHERE confidential=1")["n"],
    })


@bp.post("/demo/reset")
@login_required("owner")
def demo_reset(user):
    from .seed import seed
    conn = get_db()
    for table in ("findings", "scans", "comments", "events", "versions", "drafts", "facts", "rules", "users", "brand"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    seed(conn)
    session.clear()
    return jsonify({"ok": True})


# ------------------------------------------------------------------ rules

@bp.get("/rules")
@login_required()
def list_rules(user):
    return jsonify({"rules": S.all_rules(get_db())})


def _rule_from(data):
    category = data.get("category")
    method = data.get("method")
    kind = data.get("kind")
    if category not in S.PREFIX:
        raise ApiError("Pick a valid category.")
    if method not in ("exact", "ai", "human"):
        raise ApiError("Pick how the rule is checked.")
    allowed = {"exact": {"banned", "term_case", "required", "pattern", "link_text", "alt_text", "readability",
                         "all_caps", "numeric_claims", "unbacked_claims"},
               "ai": {"tone", "messaging"}, "human": {"human"}}
    if kind not in allowed[method]:
        raise ApiError("That rule type does not match the check method.")
    params = data.get("params") if isinstance(data.get("params"), dict) else {}
    if kind == "banned" and not params.get("terms"):
        raise ApiError("List at least one banned word.")
    if kind == "term_case" and not params.get("canonical"):
        raise ApiError("Give the exact spelling to enforce.")
    if kind == "required" and not params.get("phrase"):
        raise ApiError("Give the phrase that must be included.")
    severity = data.get("severity") if data.get("severity") in ("high", "medium", "low") else "medium"
    return {"category": category, "method": method, "kind": kind, "params": params, "severity": severity,
            "text": text_field(data, "text", max_len=400), "ambiguous": 0}


@bp.post("/rules")
@login_required("owner")
def create_rule(user):
    conn = get_db()
    code = S.insert_rule(conn, _rule_from(body()), status="approved", source=f"Added by {user['name']}")
    log_event(conn, "added rule", user["id"], None, code)
    conn.commit()
    return jsonify({"code": code})


@bp.patch("/rules/<int:rule_id>")
@login_required("owner")
def update_rule(user, rule_id):
    conn = get_db()
    rule = one(conn, "SELECT * FROM rules WHERE id=?", (rule_id,))
    if not rule:
        raise ApiError("Rule not found.", 404)
    data = body()
    if "status" in data:
        if data["status"] not in ("approved", "rejected", "disabled"):
            raise ApiError("Invalid status.")
        conn.execute("UPDATE rules SET status=? WHERE id=?", (data["status"], rule_id))
        log_event(conn, f"rule {data['status']}", user["id"], None, rule["code"])
    if "text" in data:
        conn.execute("UPDATE rules SET text=?, ambiguous=0, ambiguity_reason=NULL WHERE id=?",
                     (text_field(data, "text", max_len=400), rule_id))
        log_event(conn, "rule reworded", user["id"], None, rule["code"])
    if "severity" in data and data["severity"] in ("high", "medium", "low"):
        conn.execute("UPDATE rules SET severity=? WHERE id=?", (data["severity"], rule_id))
    conn.commit()
    return jsonify({"rule": one(conn, "SELECT * FROM rules WHERE id=?", (rule_id,))})


@bp.get("/rules/sample-guide")
@login_required()
def sample_guide(user):
    return jsonify({"text": SAMPLE_GUIDE_UPDATE})


@bp.post("/rules/compile")
@login_required("owner")
def compile_rules(user):
    text = text_field(body(), "text", max_len=12000)
    compiled, mode = compile_guidelines(text)
    conn = get_db()
    codes = []
    for r in compiled:
        codes.append(S.insert_rule(conn, r, status="proposed", source=f"Compiler ({mode})"))
    log_event(conn, "compiled guidelines", user["id"], None,
              f"{len(codes)} proposed rules, {sum(r['ambiguous'] for r in compiled)} ambiguous ({mode})")
    conn.commit()
    return jsonify({"mode": mode, "codes": codes, "count": len(codes),
                    "ambiguous": sum(r["ambiguous"] for r in compiled)})


# ------------------------------------------------------------------ facts

@bp.get("/facts")
@login_required()
def list_facts(user):
    facts = S.all_facts(get_db())
    if user["role"] not in ("owner",):
        for f in facts:
            if f["confidential"]:
                f["statement"] = "Confidential: visible to brand owners only."
                f["source"] = None
    return jsonify({"facts": facts})


@bp.post("/facts")
@login_required("owner")
def create_fact(user):
    data = body()
    conn = get_db()
    statement = text_field(data, "statement", max_len=400)
    keywords = [k.strip() for k in (data.get("keywords") or []) if isinstance(k, str) and k.strip()]
    if not keywords:
        raise ApiError("Add at least one keyword so Proofmark can find claims about this fact.")
    value = data.get("value")
    if value in ("", None):
        value = None
    else:
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ApiError("Value must be a number.")
    unit = (data.get("unit") or "").strip() or None
    if value is not None and not unit:
        raise ApiError("Give a unit for the number (for example hour, percent, INR).")
    comparison = data.get("comparison") if data.get("comparison") in ("max", "exact") else "max"
    code = S.next_code(conn, "facts", "FACT")
    conn.execute("""INSERT INTO facts (code, statement, keywords, value, unit, comparison, source, valid_until,
                    confidential, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                 (code, statement, json.dumps(keywords), value, unit, comparison,
                  (data.get("source") or "").strip() or None, (data.get("valid_until") or "").strip() or None,
                  1 if data.get("confidential") else 0, now_iso()))
    log_event(conn, "added fact", user["id"], None, code)
    conn.commit()
    return jsonify({"code": code})


@bp.delete("/facts/<int:fact_id>")
@login_required("owner")
def delete_fact(user, fact_id):
    conn = get_db()
    fact = one(conn, "SELECT code FROM facts WHERE id=?", (fact_id,))
    if not fact:
        raise ApiError("Fact not found.", 404)
    conn.execute("DELETE FROM facts WHERE id=?", (fact_id,))
    log_event(conn, "removed fact", user["id"], None, fact["code"])
    conn.commit()
    return jsonify({"ok": True})


# ------------------------------------------------------------------ drafts

@bp.get("/drafts")
@login_required()
def list_drafts(user):
    conn = get_db()
    sql = """SELECT d.*, u.name AS creator_name, u.team AS creator_team,
             (SELECT MAX(number) FROM versions WHERE draft_id=d.id) AS version,
             (SELECT COUNT(*) FROM findings f WHERE f.severity!='info' AND f.status='open' AND f.scan_id =
                (SELECT MAX(s.id) FROM scans s JOIN versions v ON v.id=s.version_id
                 WHERE v.draft_id=d.id AND v.number=(SELECT MAX(number) FROM versions WHERE draft_id=d.id))) AS open_issues,
             (SELECT COUNT(*) FROM findings f WHERE f.severity='high' AND f.status='open' AND f.scan_id =
                (SELECT MAX(s.id) FROM scans s JOIN versions v ON v.id=s.version_id
                 WHERE v.draft_id=d.id AND v.number=(SELECT MAX(number) FROM versions WHERE draft_id=d.id))) AS high_issues
             FROM drafts d JOIN users u ON u.id=d.creator_id"""
    args = ()
    if user["role"] == "creator":
        sql += " WHERE d.creator_id=?"
        args = (user["id"],)
    sql += " ORDER BY d.updated_at DESC, d.id DESC"
    return jsonify({"drafts": rows(conn, sql, args)})


@bp.get("/drafts/samples")
@login_required()
def draft_samples(user):
    return jsonify({"samples": SAMPLE_DRAFTS})


@bp.post("/drafts")
@login_required("creator", "owner")
def create_draft(user):
    data = body()
    content_type = data.get("content_type")
    if content_type not in CONTENT_TYPES:
        raise ApiError("Pick a content type.")
    conn = get_db()
    draft_id = S.create_draft(conn, user["id"], text_field(data, "title", max_len=120), content_type,
                              text_field(data, "goal", required=False, max_len=200),
                              text_field(data, "body", max_len=12000))
    S.run_scan(conn, draft_id, user["id"])
    conn.commit()
    return jsonify({"id": draft_id})


@bp.get("/drafts/<int:draft_id>")
@login_required()
def get_draft(user, draft_id):
    conn = get_db()
    draft = get_draft_or_404(conn, draft_id)
    if user["role"] == "creator" and draft["creator_id"] != user["id"]:
        raise ApiError("You can only open your own drafts.", 403)
    detail = S.draft_detail(conn, draft_id)
    detail["permissions"] = {
        "edit": can_edit(user, draft),
        "review": user["role"] in ("reviewer", "owner") and draft["status"] == "in_review"
                  and draft["creator_id"] != user["id"],
        "dismiss": user["role"] in ("reviewer", "owner") and draft["status"] != "approved",
        "comment": user["role"] != "viewer",
        "submit": can_edit(user, draft),
    }
    return jsonify(detail)


@bp.get("/drafts/<int:draft_id>/diff")
@login_required()
def diff(user, draft_id):
    conn = get_db()
    get_draft_or_404(conn, draft_id)
    a = request.args.get("from", type=int)
    b = request.args.get("to", type=int)
    va = one(conn, "SELECT body FROM versions WHERE draft_id=? AND number=?", (draft_id, a))
    vb = one(conn, "SELECT body FROM versions WHERE draft_id=? AND number=?", (draft_id, b))
    if not va or not vb:
        raise ApiError("Version not found.", 404)
    return jsonify({"segments": S.word_diff(va["body"], vb["body"])})


def _require_editable(conn, user, draft_id):
    draft = get_draft_or_404(conn, draft_id)
    if not can_edit(user, draft):
        if draft["status"] not in EDITABLE:
            raise ApiError("This draft is locked while it is in review or approved.", 409)
        raise ApiError("Only the draft's creator can change it.", 403)
    return draft


@bp.post("/drafts/<int:draft_id>/versions")
@login_required("creator", "owner")
def save_version(user, draft_id):
    conn = get_db()
    _require_editable(conn, user, draft_id)
    data = body()
    new_body = text_field(data, "body", max_len=12000)
    current = S.latest_version(conn, draft_id)
    if new_body == current["body"]:
        raise ApiError("No changes to save.")
    number = S.add_version(conn, draft_id, new_body, user["id"],
                           text_field(data, "note", required=False, max_len=120) or "Edited")
    log_event(conn, "saved version", user["id"], draft_id, f"v{number}")
    S.run_scan(conn, draft_id, user["id"])
    conn.commit()
    return jsonify({"version": number})


@bp.post("/drafts/<int:draft_id>/scan")
@login_required("creator", "reviewer", "owner")
def rescan(user, draft_id):
    conn = get_db()
    draft = get_draft_or_404(conn, draft_id)
    if user["role"] == "creator" and draft["creator_id"] != user["id"]:
        raise ApiError("You can only scan your own drafts.", 403)
    S.run_scan(conn, draft_id, user["id"])
    conn.commit()
    return jsonify({"ok": True})


@bp.post("/drafts/<int:draft_id>/apply-fixes")
@login_required("creator", "owner")
def apply_selected(user, draft_id):
    conn = get_db()
    _require_editable(conn, user, draft_id)
    data = body()
    accept_ids = [int(i) for i in data.get("accept", []) if str(i).isdigit()]
    reject_ids = [int(i) for i in data.get("reject", []) if str(i).isdigit()]
    if not accept_ids and not reject_ids:
        raise ApiError("Choose at least one suggestion to accept or reject.")
    version = S.latest_version(conn, draft_id)
    scan = S.latest_scan(conn, version["id"])
    scan_findings = {f["id"]: f for f in rows(conn, "SELECT * FROM findings WHERE scan_id=?", (scan["id"],))}
    if any(i not in scan_findings for i in accept_ids + reject_ids):
        raise ApiError("These suggestions are from an older scan. Refresh and try again.", 409)
    for i in reject_ids:
        conn.execute("UPDATE findings SET status='rejected', decided_by=? WHERE id=?", (user["id"], i))
    accepted = [scan_findings[i] for i in accept_ids if scan_findings[i]["suggestion"] is not None]
    result = {"applied": 0, "version": version["number"]}
    if accepted:
        new_body, applied = apply_fixes(version["body"], accepted)
        for f in accepted:
            conn.execute("UPDATE findings SET status='accepted', decided_by=? WHERE id=?", (user["id"], f["id"]))
        number = S.add_version(conn, draft_id, new_body, user["id"], f"Applied {applied} suggested fix(es)")
        log_event(conn, "applied fixes", user["id"], draft_id, f"{applied} fixes -> v{number}")
        S.run_scan(conn, draft_id, user["id"])
        result = {"applied": applied, "version": number}
    if reject_ids:
        log_event(conn, "rejected suggestions", user["id"], draft_id, f"{len(reject_ids)} kept as written")
    conn.commit()
    return jsonify(result)


@bp.post("/drafts/<int:draft_id>/rewrite")
@login_required("creator", "owner")
def propose_rewrite(user, draft_id):
    conn = get_db()
    draft = _require_editable(conn, user, draft_id)
    version = S.latest_version(conn, draft_id)
    scan = S.latest_scan(conn, version["id"])
    findings = rows(conn, "SELECT * FROM findings WHERE scan_id=? AND status='open'", (scan["id"],)) if scan else []
    proposal = rewrite_draft(version["body"], S.all_rules(conn, "approved"), S.all_facts(conn),
                             draft["content_type"], draft["goal"] or "", findings)
    log_event(conn, "asked for rewrite", user["id"], draft_id,
              f'{proposal["mode"]}, {len(proposal["remaining"])} issues left after re-scan')
    conn.commit()
    proposal["diff"] = S.word_diff(version["body"], proposal["text"])
    proposal["remaining"] = [{k: f.get(k) for k in ("rule_code", "severity", "quote", "explanation")}
                             for f in proposal["remaining"]]
    proposal.pop("summary", None)
    return jsonify(proposal)


@bp.post("/drafts/<int:draft_id>/submit")
@login_required("creator", "owner")
def submit(user, draft_id):
    conn = get_db()
    _require_editable(conn, user, draft_id)
    conn.execute("UPDATE drafts SET status='in_review', updated_at=? WHERE id=?", (now_iso(), draft_id))
    log_event(conn, "submitted for review", user["id"], draft_id, text_field(body(), "note", False, 300) or None)
    conn.commit()
    return jsonify({"ok": True})


@bp.post("/drafts/<int:draft_id>/review")
@login_required("reviewer", "owner")
def review(user, draft_id):
    conn = get_db()
    draft = get_draft_or_404(conn, draft_id)
    if draft["status"] != "in_review":
        raise ApiError("Only drafts in review can be approved or sent back.", 409)
    if draft["creator_id"] == user["id"]:
        raise ApiError("You cannot review your own draft.", 403)
    data = body()
    decision = data.get("decision")
    comment = text_field(data, "comment", required=decision == "request_changes", max_len=1000)
    checks = data.get("checks") or {}
    version = S.latest_version(conn, draft_id)
    if decision == "approve":
        human = [r["code"] for r in rows(conn, "SELECT code FROM rules WHERE status='approved' AND method='human'")]
        missing = [c for c in human if not checks.get(c)]
        if missing:
            raise ApiError(f"Confirm the human checks first: {', '.join(missing)}.")
        conn.execute("UPDATE drafts SET status='approved', updated_at=? WHERE id=?", (now_iso(), draft_id))
        conn.execute("UPDATE versions SET locked=1 WHERE id=?", (version["id"],))
        log_event(conn, "approved", user["id"], draft_id, f'v{version["number"]} locked' + (f": {comment}" if comment else ""))
    elif decision == "request_changes":
        conn.execute("UPDATE drafts SET status='changes_requested', updated_at=? WHERE id=?", (now_iso(), draft_id))
        log_event(conn, "requested changes", user["id"], draft_id, comment)
    else:
        raise ApiError("Choose approve or request changes.")
    if comment:
        conn.execute("INSERT INTO comments (draft_id, version_number, user_id, body, created_at) VALUES (?,?,?,?,?)",
                     (draft_id, version["number"], user["id"], comment, now_iso()))
    conn.commit()
    return jsonify({"ok": True})


@bp.post("/findings/<int:finding_id>/dismiss")
@login_required("reviewer", "owner")
def dismiss(user, finding_id):
    conn = get_db()
    f = one(conn, """SELECT f.*, v.draft_id FROM findings f JOIN scans s ON s.id=f.scan_id
                     JOIN versions v ON v.id=s.version_id WHERE f.id=?""", (finding_id,))
    if not f:
        raise ApiError("Finding not found.", 404)
    data = body()
    reason = data.get("reason")
    if reason not in DISMISS_REASONS:
        raise ApiError("Pick a reason for overriding this finding.")
    note = text_field(data, "note", required=False, max_len=300)
    conn.execute("UPDATE findings SET status='dismissed', dismiss_reason=?, dismiss_note=?, decided_by=? WHERE id=?",
                 (reason, note or None, user["id"], finding_id))
    log_event(conn, "dismissed finding", user["id"], f["draft_id"], f'{f["rule_code"] or "AI"}: {reason}')
    conn.commit()
    return jsonify({"ok": True})


@bp.post("/drafts/<int:draft_id>/comments")
@login_required("creator", "reviewer", "owner")
def add_comment(user, draft_id):
    conn = get_db()
    draft = get_draft_or_404(conn, draft_id)
    if user["role"] == "creator" and draft["creator_id"] != user["id"]:
        raise ApiError("You can only comment on your own drafts.", 403)
    version = S.latest_version(conn, draft_id)
    conn.execute("INSERT INTO comments (draft_id, version_number, user_id, body, created_at) VALUES (?,?,?,?,?)",
                 (draft_id, version["number"], user["id"], text_field(body(), "body", max_len=1000), now_iso()))
    log_event(conn, "commented", user["id"], draft_id)
    conn.commit()
    return jsonify({"ok": True})


@bp.post("/upload")
@login_required("creator", "owner")
def upload(user):
    file = request.files.get("file")
    if not file:
        raise ApiError("Choose a file to upload.")
    try:
        text = extract_text(file.filename, file.read())
    except ParseError as e:
        raise ApiError(str(e))
    if not text:
        raise ApiError("The file has no text.")
    return jsonify({"text": text[:12000], "truncated": len(text) > 12000, "filename": file.filename})


# ------------------------------------------------------------------ insights + audit

@bp.get("/insights")
@login_required("reviewer", "owner", "viewer")
def get_insights(user):
    return jsonify(S.insights(get_db()))


@bp.get("/activity")
@login_required()
def activity(user):
    conn = get_db()
    sql = """SELECT e.*, u.name AS user_name, u.role AS user_role, d.title AS draft_title FROM events e
             LEFT JOIN users u ON u.id=e.user_id LEFT JOIN drafts d ON d.id=e.draft_id"""
    args = ()
    if user["role"] == "creator":
        sql += " WHERE d.creator_id=? OR e.user_id=?"
        args = (user["id"], user["id"])
    sql += " ORDER BY e.id DESC LIMIT 200"
    return jsonify({"events": rows(conn, sql, args)})
