"""Business logic shared by the API routes and the demo seed."""
import difflib
import json
import re

from .db import log_event, now_iso, one, rows
from .engine.scan import scan_text

FINDING_FIELDS = ["rule_code", "fact_code", "category", "method", "severity", "confidence", "quote",
                  "start", "end", "explanation", "evidence", "suggestion", "claim_state"]


def all_rules(conn, status=None):
    if status:
        return rows(conn, "SELECT * FROM rules WHERE status=? ORDER BY code", (status,))
    return rows(conn, "SELECT * FROM rules ORDER BY status, code")


def all_facts(conn):
    return rows(conn, "SELECT * FROM facts ORDER BY code")


def next_code(conn, table, prefix):
    existing = [r["code"] for r in rows(conn, f"SELECT code FROM {table} WHERE code LIKE ?", (prefix + "-%",))]
    nums = [int(m.group(1)) for c in existing if (m := re.search(r"-(\d+)$", c))]
    return f"{prefix}-{(max(nums) + 1) if nums else 1:02d}"


PREFIX = {"terminology": "TERM", "claims": "CLM", "tone": "TONE", "messaging": "MSG",
          "accessibility": "A11Y", "legal": "LEGAL", "visual": "VIS"}


def insert_rule(conn, rule, status="approved", source="manual"):
    code = rule.get("code") or next_code(conn, "rules", PREFIX.get(rule["category"], "GEN"))
    conn.execute(
        """INSERT INTO rules (code, category, method, kind, text, params, severity, status, ambiguous,
           ambiguity_reason, source, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (code, rule["category"], rule["method"], rule["kind"], rule["text"], json.dumps(rule.get("params", {})),
         rule["severity"], status, int(rule.get("ambiguous", 0)), rule.get("ambiguity_reason") or None,
         source, now_iso()),
    )
    return code


def latest_version(conn, draft_id):
    return one(conn, "SELECT * FROM versions WHERE draft_id=? ORDER BY number DESC LIMIT 1", (draft_id,))


def add_version(conn, draft_id, body, user_id, note=None):
    last = latest_version(conn, draft_id)
    number = (last["number"] + 1) if last else 1
    conn.execute(
        "INSERT INTO versions (draft_id, number, body, note, created_by, created_at) VALUES (?,?,?,?,?,?)",
        (draft_id, number, body, note, user_id, now_iso()),
    )
    conn.execute("UPDATE drafts SET updated_at=? WHERE id=?", (now_iso(), draft_id))
    return number


def create_draft(conn, user_id, title, content_type, goal, body):
    cur = conn.execute(
        "INSERT INTO drafts (title, content_type, goal, creator_id, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (title, content_type, goal, user_id, "draft", now_iso(), now_iso()),
    )
    draft_id = cur.lastrowid
    add_version(conn, draft_id, body, user_id, "First draft")
    log_event(conn, "created draft", user_id, draft_id, title)
    return draft_id


def run_scan(conn, draft_id, user_id=None, use_ai=True):
    draft = one(conn, "SELECT * FROM drafts WHERE id=?", (draft_id,))
    version = latest_version(conn, draft_id)
    findings, summary = scan_text(version["body"], all_rules(conn, "approved"), all_facts(conn),
                                  draft["content_type"], draft["goal"] or "", use_ai=use_ai)
    cur = conn.execute("INSERT INTO scans (version_id, created_at, mode, summary) VALUES (?,?,?,?)",
                       (version["id"], now_iso(), summary["mode"], json.dumps(summary)))
    scan_id = cur.lastrowid
    for f in findings:
        conn.execute(
            f"INSERT INTO findings (scan_id, {', '.join(FINDING_FIELDS)}) VALUES (?{', ?' * len(FINDING_FIELDS)})",
            (scan_id, *[f.get(k) for k in FINDING_FIELDS]),
        )
    c = summary["counts"]
    log_event(conn, "scanned", user_id, draft_id,
              f'v{version["number"]}: {c["high"]} high, {c["medium"]} medium, {c["low"]} low ({summary["mode"]})')
    return scan_id


def latest_scan(conn, version_id):
    return one(conn, "SELECT * FROM scans WHERE version_id=? ORDER BY id DESC LIMIT 1", (version_id,))


def word_diff(a, b):
    ta = re.findall(r"\s+|[^\s]+", a)
    tb = re.findall(r"\s+|[^\s]+", b)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if op == "equal":
            out.append({"op": "equal", "text": "".join(ta[i1:i2])})
        else:
            if i2 > i1:
                out.append({"op": "delete", "text": "".join(ta[i1:i2])})
            if j2 > j1:
                out.append({"op": "insert", "text": "".join(tb[j1:j2])})
    return out


def draft_detail(conn, draft_id):
    draft = one(conn, """SELECT d.*, u.name AS creator_name, u.team AS creator_team FROM drafts d
                         JOIN users u ON u.id=d.creator_id WHERE d.id=?""", (draft_id,))
    if not draft:
        return None
    versions = rows(conn, """SELECT v.*, u.name AS author FROM versions v LEFT JOIN users u ON u.id=v.created_by
                             WHERE draft_id=? ORDER BY number""", (draft_id,))
    current = versions[-1]
    scan = latest_scan(conn, current["id"])
    findings = []
    if scan:
        findings = rows(conn, """SELECT f.*, u.name AS decided_by_name FROM findings f
                                 LEFT JOIN users u ON u.id=f.decided_by WHERE scan_id=? ORDER BY f.id""", (scan["id"],))
    comments = rows(conn, """SELECT c.*, u.name AS author, u.role AS author_role FROM comments c
                             JOIN users u ON u.id=c.user_id WHERE draft_id=? ORDER BY c.id""", (draft_id,))
    events = rows(conn, """SELECT e.*, u.name AS user_name FROM events e LEFT JOIN users u ON u.id=e.user_id
                           WHERE draft_id=? ORDER BY e.id DESC""", (draft_id,))
    human_rules = rows(conn, "SELECT code, text FROM rules WHERE status='approved' AND method='human' ORDER BY code")
    return {"draft": draft, "versions": versions, "current": current, "scan": scan,
            "findings": findings, "comments": comments, "events": events, "human_checks": human_rules}


def insights(conn):
    total_drafts = one(conn, "SELECT COUNT(*) AS n FROM drafts")["n"]
    scanned = one(conn, """SELECT COUNT(DISTINCT v.draft_id) AS n FROM scans s JOIN versions v ON v.id=s.version_id""")["n"]
    approved = one(conn, "SELECT COUNT(*) AS n FROM drafts WHERE status='approved'")["n"]
    # first scan of each draft = what creators submit before Proofmark helps
    first_scans = rows(conn, """SELECT s.id FROM scans s JOIN versions v ON v.id=s.version_id
                                WHERE s.id IN (SELECT MIN(s2.id) FROM scans s2 JOIN versions v2 ON v2.id=s2.version_id
                                               GROUP BY v2.draft_id)""")
    ids = [r["id"] for r in first_scans] or [0]
    marks = ",".join("?" * len(ids))
    issues_first = one(conn, f"SELECT COUNT(*) AS n FROM findings WHERE scan_id IN ({marks}) AND severity!='info'", ids)["n"]

    broken = rows(conn, """SELECT f.rule_code AS code, r.text, r.category, COUNT(*) AS n FROM findings f
                           JOIN rules r ON r.code=f.rule_code WHERE f.severity!='info'
                           AND f.scan_id IN (SELECT MAX(s.id) FROM scans s JOIN versions v ON v.id=s.version_id GROUP BY v.id)
                           GROUP BY f.rule_code ORDER BY n DESC LIMIT 8""")
    overridden = rows(conn, """SELECT f.rule_code AS code, r.text, COUNT(*) AS n,
                               SUM(CASE WHEN f.dismiss_reason='Rule unclear' THEN 1 ELSE 0 END) AS unclear,
                               SUM(CASE WHEN f.dismiss_reason='False alarm' THEN 1 ELSE 0 END) AS false_alarm,
                               SUM(CASE WHEN f.dismiss_reason='Approved exception' THEN 1 ELSE 0 END) AS exception
                               FROM findings f JOIN rules r ON r.code=f.rule_code
                               WHERE f.status='dismissed' GROUP BY f.rule_code ORDER BY n DESC LIMIT 8""")
    for o in overridden:
        o["likely_unclear"] = o["unclear"] >= 1 and o["n"] >= 2
    by_category = rows(conn, """SELECT category, COUNT(*) AS n FROM findings WHERE severity!='info'
                                GROUP BY category ORDER BY n DESC""")
    by_method = rows(conn, """SELECT method, COUNT(*) AS n FROM findings WHERE severity!='info'
                              GROUP BY method ORDER BY n DESC""")
    claims = rows(conn, """SELECT claim_state AS state, COUNT(*) AS n FROM findings WHERE claim_state IS NOT NULL
                           GROUP BY claim_state""")
    ambiguous = rows(conn, """SELECT code, text, ambiguity_reason, status FROM rules
                              WHERE ambiguous=1 AND status!='rejected' ORDER BY code""")
    by_team = rows(conn, """SELECT COALESCE(u.team,'Unassigned') AS team, COUNT(*) AS n FROM findings f
                            JOIN scans s ON s.id=f.scan_id JOIN versions v ON v.id=s.version_id
                            JOIN drafts d ON d.id=v.draft_id JOIN users u ON u.id=d.creator_id
                            WHERE f.severity!='info' AND f.scan_id IN ({}) GROUP BY team ORDER BY n DESC""".format(marks), ids)
    return {
        "totals": {"drafts": total_drafts, "scanned": scanned, "approved": approved,
                   "issues_at_first_scan": issues_first,
                   "avg_issues_first_scan": round(issues_first / max(1, len(first_scans)), 1)},
        "most_broken": broken, "most_overridden": overridden, "by_category": by_category,
        "by_method": by_method, "claims": claims, "ambiguous_rules": ambiguous, "by_team": by_team,
    }
