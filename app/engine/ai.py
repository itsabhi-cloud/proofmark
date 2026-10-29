"""AI layer.

The AI suggests; code verifies. Every AI response must be strict JSON, and
every AI finding passes `verify_findings` before anyone sees it:

  * the quoted text must exist in the draft (string match), and
  * the cited rule code must be an approved AI rule.

A finding that fails the quote check is dropped. A finding with an unknown
rule is kept only as "needs human judgement". Counts are returned so the UI
can show exactly what the verifier did.

Providers: Google Gemini (default) or any OpenAI-compatible endpoint such as
Groq. With no API key the app runs fully offline in "exact + heuristic" mode.
"""
import json
import os
import re
import time

import requests

from .text_utils import find_span

# Per attempt. Each call may try twice (12 + 2 + 12 s), and a rewrite makes up to 4 calls:
# 4 x 26 s stays under Gunicorn's 120 s request limit.
TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "12"))
RETRY_STATUS = (429, 503)  # free-tier "too many requests" / "model busy": worth one more try
RETRY_WAIT = 2.0


class AIUnavailable(Exception):
    pass


def config():
    key = os.environ.get("LLM_API_KEY", "").strip()
    provider = os.environ.get("LLM_PROVIDER", "gemini").strip().lower()
    default_model = "gemini-3.5-flash-lite" if provider == "gemini" else "llama-3.3-70b-versatile"
    return {
        "enabled": bool(key) and os.environ.get("AI_DISABLED", "") != "1",
        "provider": provider,
        "model": os.environ.get("LLM_MODEL", default_model),
        "base_url": os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/"),
        "key": key,
    }


def public_config():
    c = config()
    return {"enabled": c["enabled"], "provider": c["provider"] if c["enabled"] else None,
            "model": c["model"] if c["enabled"] else None}


def _extract_json(raw):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        return json.loads(raw)
    except ValueError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


def _post_with_retry(post, url, body, headers):
    """POST once; if the provider is rate-limited, busy or too slow, wait briefly and try once more."""
    try:
        r = post(url, json=body, headers=headers, timeout=TIMEOUT)
    except requests.Timeout:  # slow answers are usually one-off spikes; a fresh request is often quick
        r = None
    if r is None or getattr(r, "status_code", 200) in RETRY_STATUS:
        time.sleep(RETRY_WAIT)
        r = post(url, json=body, headers=headers, timeout=TIMEOUT)
    return r


def call_json(system, user, _post=None):
    """Send one prompt and return parsed JSON. Raises AIUnavailable on any failure."""
    c = config()
    if not c["enabled"]:
        raise AIUnavailable("No API key configured")
    post = _post or requests.post
    try:
        if c["provider"] == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{c['model']}:generateContent"
            body = {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
            }
            r = _post_with_retry(post, url, body, {"x-goog-api-key": c["key"]})
            r.raise_for_status()
            data = r.json()
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        else:
            url = f"{c['base_url']}/chat/completions"
            body = {
                "model": c["model"],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            }
            r = _post_with_retry(post, url, body, {"Authorization": f"Bearer {c['key']}"})
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
        return _extract_json(text)
    except AIUnavailable:
        raise
    except Exception as exc:  # network, quota, bad JSON: all fall back to offline mode
        raise AIUnavailable(f"{type(exc).__name__}: {str(exc)[:160]}")


# ---------------------------------------------------------------- analysis

ANALYZE_SYSTEM = """You are Proofmark's brand reviewer. You check marketing drafts against the
brand rules you are given and nothing else. Return ONLY JSON with this shape:
{"findings":[{"quote":"exact words copied from the draft","rule_code":"TONE-01",
"explanation":"one sentence: what is wrong and why, citing the rule",
"severity":"high|medium|low","confidence":"High|Medium|Low",
"suggestion":"replacement text for the quoted words that keeps the writer's goal, or empty"}],
"claims":[{"quote":"exact words of a factual or promotional claim","value":null,"unit":null,
"topic":"short topic such as battery life"}]}
Rules:
- quote must be copied character for character from the draft, as short as possible (2-12 words).
- rule_code must be one of the rule codes provided. Never invent a rule.
- Only report real problems. If the draft follows a rule, report nothing for it.
- Text like [EMAIL1] or [PHONE2] is masked personal data; ignore it.
- claims: list every number-based or absolute claim (best, guaranteed, waterproof, etc.)."""


def analyze(masked_text, ai_rules, facts, goal, content_type, _post=None):
    rule_lines = "\n".join(f'{r["code"]} [{r["category"]}]: {r["text"]}' for r in ai_rules)
    fact_lines = "\n".join(f'{f["code"]}: {f["statement"]}' for f in facts) or "(none)"
    user = (
        f"Content type: {content_type}\nWriter's goal: {goal or 'not stated'}\n\n"
        f"BRAND RULES TO CHECK:\n{rule_lines}\n\nAPPROVED FACTS (for context):\n{fact_lines}\n\n"
        f"DRAFT:\n<<<\n{masked_text}\n>>>"
    )
    return call_json(ANALYZE_SYSTEM, user, _post=_post)


def verify_findings(raw, text, ai_rules):
    """Turn raw AI output into trusted findings. Returns (findings, stats)."""
    valid = {r["code"]: r for r in ai_rules}
    stats = {"ai_suggested": 0, "kept": 0, "dropped_quote_not_found": 0, "needs_human": 0}
    out = []
    items = raw.get("findings", []) if isinstance(raw, dict) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        stats["ai_suggested"] += 1
        span = find_span(text, str(item.get("quote", "")))
        if span is None:
            stats["dropped_quote_not_found"] += 1
            continue
        code = str(item.get("rule_code", "")).strip().upper()
        rule = valid.get(code)
        sev = item.get("severity") if item.get("severity") in ("high", "medium", "low") else "medium"
        conf = item.get("confidence") if item.get("confidence") in ("High", "Medium", "Low") else "Medium"
        suggestion = item.get("suggestion") or None
        if isinstance(suggestion, str) and not suggestion.strip():
            suggestion = None
        start, end = span
        base = {
            "fact_code": None, "method": "ai", "quote": text[start:end], "start": start, "end": end,
            "explanation": str(item.get("explanation", ""))[:400], "suggestion": suggestion,
            "claim_state": None,
        }
        if rule is None:
            stats["needs_human"] += 1
            out.append({**base, "rule_code": None, "category": "needs human judgement",
                        "severity": "low", "confidence": "Low",
                        "evidence": "AI cited a rule that is not in the approved rulebook, so this is not a confirmed issue."})
            continue
        stats["kept"] += 1
        out.append({**base, "rule_code": rule["code"], "category": rule["category"], "severity": sev,
                    "confidence": conf, "evidence": f'{rule["code"]}: {rule["text"]}'})
    return out, stats


# ---------------------------------------------------------------- rewrite

REWRITE_SYSTEM = """You rewrite marketing drafts so they follow the brand rules while keeping the
writer's goal, key information and length roughly the same. Fix every listed issue. Do not add new
facts, numbers or claims that are not in the approved facts. Return ONLY JSON:
{"rewrite":"the full rewritten draft","goal_preserved":true,"goal_reason":"one short sentence"}"""


def rewrite(masked_text, goal, content_type, issues, rules, facts, _post=None):
    issue_lines = "\n".join(
        f'- "{f.get("quote") or "(whole draft)"}": {f["explanation"]}' + (f' Suggested: {f["suggestion"]}' if f.get("suggestion") else "")
        for f in issues
    ) or "- none"
    rule_lines = "\n".join(f'{r["code"]}: {r["text"]}' for r in rules)
    fact_lines = "\n".join(f'{f["code"]}: {f["statement"]}' for f in facts) or "(none)"
    user = (
        f"Content type: {content_type}\nWriter's goal: {goal or 'not stated'}\n\nISSUES TO FIX:\n{issue_lines}\n\n"
        f"BRAND RULES:\n{rule_lines}\n\nAPPROVED FACTS:\n{fact_lines}\n\nDRAFT:\n<<<\n{masked_text}\n>>>"
    )
    data = call_json(REWRITE_SYSTEM, user, _post=_post)
    text = data.get("rewrite") if isinstance(data, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise AIUnavailable("AI returned no rewrite")
    return {
        "text": text.strip(),
        "goal_preserved": bool(data.get("goal_preserved", True)),
        "goal_reason": str(data.get("goal_reason", ""))[:240],
    }


# ---------------------------------------------------------------- rule compiler

COMPILE_SYSTEM = """You turn brand-guideline prose into individual, testable rules. Return ONLY JSON:
{"rules":[{"text":"the rule in one clear sentence","category":"terminology|claims|tone|messaging|accessibility|legal|visual",
"method":"exact|ai|human","kind":"banned|term_case|required|tone|messaging|human",
"params":{},"severity":"high|medium|low","ambiguous":false,"ambiguity_reason":""}]}
Param shapes: banned {"terms":["word"],"replacement":"better word"}; term_case {"canonical":"Exact Name"};
required {"phrase":"text","content_types":[],"when_any":[]}; tone/messaging/human {}.
Use method exact only for banned, term_case and required. Use ai for tone and messaging judgements.
Use human for anything about images, logos, layout or legal approval.
Mark ambiguous true when the guideline is vague (e.g. "where appropriate", "sound nice") and explain
in ambiguity_reason what a writer could not know. Cover every guideline sentence."""


def compile_rules(guideline_text, _post=None):
    data = call_json(COMPILE_SYSTEM, f"GUIDELINES:\n<<<\n{guideline_text}\n>>>", _post=_post)
    rules = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(rules, list):
        raise AIUnavailable("AI returned no rules")
    return rules
