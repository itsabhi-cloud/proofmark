"""Rulebook Compiler: guideline prose -> proposed, testable rules.

Proposed rules are never used until a brand owner approves them.
Vague guidelines are marked ambiguous instead of guessed.
"""
import re

from . import ai
from .text_utils import sentences

CATEGORIES = {"terminology", "claims", "tone", "messaging", "accessibility", "legal", "visual"}
KINDS_BY_METHOD = {
    "exact": {"banned", "term_case", "required"},
    "ai": {"tone", "messaging"},
    "human": {"human"},
}
VAGUE = ["where appropriate", "when appropriate", "if possible", "where possible", "as needed",
         "generally", "usually", "sometimes", "nice", "good", "cool", "on-brand", "feel premium",
         "be careful", "try to", "reasonable", "appropriately", "modern"]

CONTENT_WORDS = [("emails?", "Email"), ("ads?", "Ad"), ("adverts?", "Ad"), ("social posts?", "Social post"),
                 ("captions?", "Social post"), ("blogs?", "Blog post"), ("product pages?", "Product page"),
                 ("press releases?", "Press release")]

Q = r"[\"“'‘]([^\"”'’]+)[\"”'’]"


def _vague(s):
    low = s.lower()
    hits = [v for v in VAGUE if re.search(r"\b" + re.escape(v) + r"\b", low)]
    if hits:
        return f'Uses vague wording ("{hits[0]}"): a writer cannot tell exactly what passes.'
    return ""


def heuristic_compile(text):
    rules = []
    for _, _, s in sentences(text):
        s = s.strip(" -•*\t")
        if len(s) < 8:
            continue
        # headings: short line without sentence punctuation, or a document title
        if (not re.search(r"[.!?]$", s) and len(s.split()) <= 8) or re.search(r"\bguidelines?\b.*\bv?\d", s, re.I):
            continue
        low = s.lower()
        reason = _vague(s)
        rule = None

        m = re.search(r"\b(?:never|do not|don't|avoid|no)\s+(?:use|say|write|call\w*|using|saying)?\s*(?:the\s+words?\s+|terms?\s+)?" + Q, s, re.I)
        if m:
            terms = re.findall(Q, s[m.start():])
            repl = re.search(r"(?:use|say|write)\s+" + Q + r"\s+instead|instead,?\s+(?:use|say|write)\s+" + Q, s, re.I)
            replacement = (repl.group(1) or repl.group(2)) if repl else None
            if replacement and replacement in terms:
                terms.remove(replacement)
            rule = {"category": "terminology", "method": "exact", "kind": "banned",
                    "params": {"terms": terms, **({"replacement": replacement} if replacement else {})},
                    "severity": "medium"}
        if rule is None:
            m = re.search(r"\b(?:always\s+)?(?:write|spell|style)\s+(?:our\s+\w+\s+name\s+as\s+|it\s+as\s+)?" + Q, s, re.I)
            if m and ("always" in low or "spell" in low or " as " in low):
                rule = {"category": "terminology", "method": "exact", "kind": "term_case",
                        "params": {"canonical": m.group(1)}, "severity": "medium"}
        if rule is None:
            m = re.search(r"\b(?:must|should always|always)\s+(?:include|end with|contain|carry|add)\s+" + Q, s, re.I)
            if m:
                types = [label for word, label in CONTENT_WORDS if re.search(r"\b" + word + r"\b", low)]
                rule = {"category": "legal", "method": "exact", "kind": "required",
                        "params": {"phrase": m.group(1), "content_types": sorted(set(types)), "when_any": []},
                        "severity": "high"}
        if rule is None and re.search(r"\b(logo|image|photo|imagery|colour|color|font|layout|visual)s?\b", low):
            rule = {"category": "visual", "method": "human", "kind": "human", "params": {}, "severity": "medium"}
        if rule is None and re.search(r"\b(message|mention|highlight|emphasi[sz]e|focus on|tagline)\b", low):
            rule = {"category": "messaging", "method": "ai", "kind": "messaging", "params": {}, "severity": "low"}
        if rule is None and re.search(r"\b(tone|voice|sound|feel|friendly|formal|casual)\b", low):
            rule = {"category": "tone", "method": "ai", "kind": "tone", "params": {}, "severity": "medium"}
        if rule is None:
            rule = {"category": "messaging", "method": "human", "kind": "human", "params": {}, "severity": "low"}
            reason = reason or "Could not be turned into an automatic test; a reviewer must judge it."

        rule.update({"text": s, "ambiguous": 1 if reason else 0, "ambiguity_reason": reason})
        rules.append(rule)
    return rules


def _clean(item):
    """Validate one AI-proposed rule. Returns a safe rule dict or None."""
    if not isinstance(item, dict) or not str(item.get("text", "")).strip():
        return None
    method = item.get("method") if item.get("method") in KINDS_BY_METHOD else "human"
    kind = item.get("kind") if item.get("kind") in KINDS_BY_METHOD[method] else next(iter(KINDS_BY_METHOD[method]))
    params = item.get("params") if isinstance(item.get("params"), dict) else {}
    if kind == "banned" and not (isinstance(params.get("terms"), list) and params["terms"]):
        method, kind, params = "human", "human", {}
    if kind == "term_case" and not params.get("canonical"):
        method, kind, params = "human", "human", {}
    if kind == "required" and not params.get("phrase"):
        method, kind, params = "human", "human", {}
    category = item.get("category") if item.get("category") in CATEGORIES else "messaging"
    severity = item.get("severity") if item.get("severity") in ("high", "medium", "low") else "medium"
    text = str(item["text"]).strip()[:400]
    reason = str(item.get("ambiguity_reason") or "").strip()[:300]
    ambiguous = bool(item.get("ambiguous")) or bool(_vague(text))
    if ambiguous and not reason:
        reason = _vague(text) or "Marked vague by the compiler."
    return {"text": text, "category": category, "method": method, "kind": kind, "params": params,
            "severity": severity, "ambiguous": 1 if ambiguous else 0, "ambiguity_reason": reason if ambiguous else ""}


def compile_guidelines(text):
    """Returns (rules, mode). mode is 'ai' or 'heuristic'."""
    try:
        raw = ai.compile_rules(text)
        cleaned = [r for r in (_clean(x) for x in raw) if r]
        if cleaned:
            return cleaned, "ai"
    except ai.AIUnavailable:
        pass
    return heuristic_compile(text), "heuristic"
