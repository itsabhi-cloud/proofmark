"""The scan pipeline: exact rules -> claim receipts -> AI -> verifier.

    scan_text(text, rules, facts, content_type, goal) -> (findings, summary)

Only approved rules are used. Confidential facts are never sent to the AI.
"""
from datetime import date

from . import ai
from .claims import run_claims
from .exact import check_tone_heuristic, run_exact
from .text_utils import mask_pii, top_relevant

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


def _overlaps(a, b):
    if a.get("start") is None or b.get("start") is None:
        return False
    return a["start"] < b["end"] and b["start"] < a["end"]


def _dedupe(findings):
    """Exact findings win over AI/heuristic findings on the same words."""
    exact = [f for f in findings if f["method"] == "exact"]
    others = [f for f in findings if f["method"] != "exact"]
    kept = list(exact)
    for f in others:
        if f.get("start") is not None and any(_overlaps(f, e) and e.get("claim_state") != "Supported" for e in exact):
            continue
        if any(_overlaps(f, k) and k["method"] == f["method"] and k.get("rule_code") == f.get("rule_code") for k in kept):
            continue
        kept.append(f)
    # identical span + rule from two checks
    seen, unique = set(), []
    for f in kept:
        key = (f.get("rule_code"), f.get("fact_code"), f.get("start"), f.get("end"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    return unique


def sort_findings(findings):
    return sorted(findings, key=lambda f: (SEVERITY_ORDER.get(f["severity"], 4),
                                           f["start"] if f.get("start") is not None else 10**9))


def scan_text(text, rules, facts, content_type, goal="", use_ai=True, today=None, _post=None):
    approved = [r for r in rules if r.get("status") == "approved"]
    findings = run_exact(text, approved, facts, content_type)
    findings += run_claims(text, approved, facts, today or date.today())

    ai_rules = [r for r in approved if r["method"] == "ai"]
    human_rules = [r for r in approved if r["method"] == "human"]
    summary = {"mode": "exact+heuristic", "ai": ai.public_config(), "verifier": None,
               "masked_items": 0, "confidential_withheld": sum(1 for f in facts if f.get("confidential")),
               "ai_error": None, "rules_checked": len(approved), "human_checks": [r["code"] for r in human_rules]}

    used_ai = False
    if use_ai and ai_rules and ai.config()["enabled"]:
        masked, count = mask_pii(text)
        summary["masked_items"] = count
        public_facts = top_relevant(text, [f for f in facts if not f.get("confidential")],
                                    key=lambda f: f["statement"] + " " + " ".join(f.get("keywords", [])), limit=8)
        try:
            raw = ai.analyze(masked, ai_rules, public_facts, goal, content_type, _post=_post)
            verified, stats = ai.verify_findings(raw, masked, ai_rules)
            for f in verified:  # restore original words (masking keeps offsets)
                f["quote"] = text[f["start"]:f["end"]]
            findings += verified
            summary["verifier"] = stats
            summary["mode"] = "exact+ai"
            used_ai = True
        except ai.AIUnavailable as exc:
            summary["ai_error"] = str(exc)

    if not used_ai:
        for rule in ai_rules:
            findings += check_tone_heuristic(text, rule)

    findings = sort_findings(_dedupe(findings))
    issues = [f for f in findings if f["severity"] != "info"]
    summary["counts"] = {
        "high": sum(1 for f in issues if f["severity"] == "high"),
        "medium": sum(1 for f in issues if f["severity"] == "medium"),
        "low": sum(1 for f in issues if f["severity"] == "low"),
        "supported_claims": sum(1 for f in findings if f.get("claim_state") == "Supported"),
        "claims": sum(1 for f in findings if f.get("claim_state")),
    }
    return findings, summary


def apply_fixes(text, findings):
    """Apply suggestions for the given findings, right to left, skipping overlaps."""
    fixes = [f for f in findings if f.get("suggestion") is not None and f.get("start") is not None]
    fixes.sort(key=lambda f: f["start"], reverse=True)
    out = text
    last_start = None
    applied = 0
    for f in fixes:
        if last_start is not None and f["end"] > last_start:
            continue
        if f["start"] == f["end"]:  # insertion (e.g. required phrase at end)
            out = out[:f["start"]] + f["suggestion"] + out[f["start"]:]
        else:
            out = out[:f["start"]] + f["suggestion"] + out[f["end"]:]
        last_start = f["start"]
        applied += 1
    return _tidy(out), applied


def _tidy(text):
    import re
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +([,.!?])", r"\1", text)
    text = re.sub(r"^\s*[,.!?]\s*", "", text)
    return text


def rewrite_draft(text, rules, facts, content_type, goal, findings, _post=None):
    """Purpose-preserving rewrite. Every proposal is re-scanned before it is shown.

    AI mode: up to 2 attempts; a second attempt gets the issues the first one left.
    Offline mode: applies every safe suggested fix deterministically.
    """
    approved = [r for r in rules if r.get("status") == "approved"]
    issues = [f for f in findings if f["severity"] != "info"]
    public_facts = [f for f in facts if not f.get("confidential")]
    attempts = 0
    if ai.config()["enabled"]:
        masked, _ = mask_pii(text)
        current_issues = issues
        best = None
        for _ in range(2):
            attempts += 1
            try:
                proposal = ai.rewrite(masked, goal, content_type, current_issues, approved, public_facts, _post=_post)
            except ai.AIUnavailable as exc:
                if best:
                    break
                return _offline_rewrite(text, approved, facts, content_type, goal, issues, error=str(exc))
            new_findings, summary = scan_text(proposal["text"], rules, facts, content_type, goal, _post=_post)
            remaining = [f for f in new_findings if f["severity"] in ("high", "medium")]
            best = {"text": proposal["text"], "goal_preserved": proposal["goal_preserved"],
                    "goal_reason": proposal["goal_reason"], "remaining": remaining,
                    "summary": summary, "attempts": attempts, "mode": "ai"}
            if not remaining:
                break
            current_issues = remaining
        return best
    return _offline_rewrite(text, approved, facts, content_type, goal, issues)


def _offline_rewrite(text, rules, facts, content_type, goal, issues, error=None):
    new_text, applied = apply_fixes(text, issues)
    new_findings, summary = scan_text(new_text, rules, facts, content_type, goal, use_ai=False)
    remaining = [f for f in new_findings if f["severity"] in ("high", "medium")]
    return {"text": new_text, "goal_preserved": True,
            "goal_reason": "Only the flagged words were replaced, so the rest of the message is unchanged.",
            "remaining": remaining, "summary": summary, "attempts": 1, "mode": "offline",
            "applied": applied, "ai_error": error}
