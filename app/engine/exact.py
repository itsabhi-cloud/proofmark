"""Deterministic checks. Same input, same output, every time.

Each check receives the draft text and one approved rule, and returns a list
of findings (plain dicts). Findings always carry a character span, so the UI
can highlight them and the fix can be applied safely.
"""
import re

from .text_utils import flesch_reading_ease, sentences, WORD_RE


def finding(rule, start, end, text, explanation, suggestion=None, severity=None,
            category=None, method="exact", confidence="High", evidence=None,
            fact_code=None, claim_state=None):
    return {
        "rule_code": rule["code"] if rule else None,
        "fact_code": fact_code,
        "category": category or (rule["category"] if rule else "general"),
        "method": method,
        "severity": severity or (rule["severity"] if rule else "medium"),
        "confidence": confidence,
        "quote": text[start:end] if start is not None else "",
        "start": start,
        "end": end,
        "explanation": explanation,
        "evidence": evidence or (f'{rule["code"]}: {rule["text"]}' if rule else ""),
        "suggestion": suggestion,
        "claim_state": claim_state,
    }


def _flex_pattern(phrase):
    """'Volta Audio' -> regex that also matches 'volta-audio', 'VoltaAudio'."""
    parts = [re.escape(p) for p in phrase.split()]
    return r"\b" + r"[\s\-]*".join(parts) + r"\b"


def match_case(original, replacement):
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def check_banned(text, rule):
    p = rule["params"]
    out = []
    replacement = p.get("replacement")
    for term in p.get("terms", []):
        for m in re.finditer(_flex_pattern(term), text, re.IGNORECASE):
            sugg = match_case(m.group(0), replacement) if replacement else None
            note = p.get("reason") or f'"{term}" is not allowed in brand copy.'
            if replacement:
                note += f' Use "{replacement}" instead.'
            out.append(finding(rule, m.start(), m.end(), text, note, suggestion=sugg))
    return out


def check_term_case(text, rule):
    p = rule["params"]
    canonical = p.get("canonical", "")
    out = []
    patterns = [_flex_pattern(canonical)] + [_flex_pattern(v) for v in p.get("variants", [])]
    seen = set()
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            if m.start() in seen:
                continue
            seen.add(m.start())
            if m.group(0) != canonical:
                out.append(finding(
                    rule, m.start(), m.end(), text,
                    f'Write the name exactly as "{canonical}".', suggestion=canonical,
                ))
    return out


def check_required(text, rule, content_type):
    p = rule["params"]
    types = p.get("content_types") or []
    if types and content_type not in types:
        return []
    triggers = p.get("when_any") or []
    lower = text.lower()
    if triggers and not any(re.search(r"\b" + re.escape(t.lower()) + r"\b", lower) for t in triggers):
        return []
    phrase = p.get("phrase", "")
    if phrase and phrase.lower() not in lower:
        end = len(text.rstrip())
        return [finding(
            rule, end, end, text,
            f'This {content_type.lower()} must include "{phrase}".',
            suggestion=f" {phrase}",
        )]
    return []


def check_pattern(text, rule):
    p = rule["params"]
    out = []
    try:
        rx = re.compile(p["regex"], re.IGNORECASE if p.get("ignore_case", True) else 0)
    except (KeyError, re.error):
        return out
    for m in rx.finditer(text):
        sugg = p.get("replacement")
        out.append(finding(rule, m.start(), m.end(), text, p.get("message") or rule["text"], suggestion=sugg))
    return out


def check_link_text(text, rule):
    out = []
    for m in re.finditer(r"\b(click here|read more here|link here|tap here)\b", text, re.IGNORECASE):
        out.append(finding(
            rule, m.start(), m.end(), text,
            "Link text should say where it goes, so screen-reader users understand it out of context.",
            suggestion=match_case(m.group(0), "see the full details"),
        ))
    return out


def check_alt_text(text, rule):
    out = []
    for m in re.finditer(r"!\[\s*\]\(([^)]+)\)", text):
        out.append(finding(rule, m.start(), m.end(), text,
                           "This image has no alt text. Describe what it shows.",
                           suggestion=f"![Describe the image]({m.group(1)})"))
    for m in re.finditer(r"<img\b(?![^>]*\balt\s*=\s*\"[^\"]+\")[^>]*>", text, re.IGNORECASE):
        out.append(finding(rule, m.start(), m.end(), text,
                           "This image tag has no alt text. Add alt=\"…\" describing the image."))
    return out


def check_all_caps(text, rule):
    out = []
    for m in re.finditer(r"\b[A-Z]{2,}(?:[!?,.]*\s+[A-Z]{2,}){2,}\b", text):
        words = m.group(0)
        out.append(finding(rule, m.start(), m.end(), text,
                           "Long runs of capitals read as shouting and may be spelled out by screen readers.",
                           suggestion=words.lower().capitalize()))
    return out


def check_readability(text, rule):
    p = rule["params"]
    out = []
    max_words = int(p.get("max_sentence_words", 25))
    for start, end, s in sentences(text):
        n = len(WORD_RE.findall(s))
        if n > max_words:
            out.append(finding(rule, start, end, text,
                               f"This sentence has {n} words; keep sentences under {max_words} words.",
                               severity="low"))
    score = flesch_reading_ease(text)
    min_score = float(p.get("min_flesch", 50))
    if len(WORD_RE.findall(text)) >= 30 and score < min_score:
        out.append(finding(rule, None, None, text,
                           f"Reading-ease score is {score}; the brand target is {min_score:g} or higher. "
                           "Use shorter sentences and simpler words.", severity="low"))
    return out


def check_tone_heuristic(text, rule):
    """Offline fallback for AI tone rules: flags listed words only."""
    p = rule["params"]
    out = []
    for word in p.get("pressure_words", []) + p.get("slang_words", []):
        for m in re.finditer(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text, re.IGNORECASE):
            out.append(finding(
                rule, m.start(), m.end(), text,
                f'"{m.group(0)}" does not fit the brand voice: {rule["text"]}',
                suggestion=match_case(m.group(0), p.get("replacements", {}).get(word.lower(), "")),
                method="heuristic", confidence="Medium",
            ))
    return out


def check_confidential(text, facts):
    """Flags any mention of a confidential fact's keywords: a leak risk."""
    out = []
    for f in facts:
        if not f.get("confidential"):
            continue
        for kw in f.get("keywords", []):
            for m in re.finditer(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", text, re.IGNORECASE):
                out.append(finding(
                    None, m.start(), m.end(), text,
                    "This mentions information marked confidential. It must not be published yet.",
                    severity="high", category="confidentiality", fact_code=f["code"],
                    evidence=f'{f["code"]} (confidential): details hidden from creators and AI',
                ))
    return out


CHECKS = {
    "banned": check_banned,
    "term_case": check_term_case,
    "pattern": check_pattern,
    "link_text": check_link_text,
    "alt_text": check_alt_text,
    "all_caps": check_all_caps,
    "readability": check_readability,
}


def run_exact(text, rules, facts, content_type):
    out = []
    for rule in rules:
        if rule["method"] != "exact":
            continue
        if rule["kind"] == "required":
            out.extend(check_required(text, rule, content_type))
        elif rule["kind"] in CHECKS:
            out.extend(CHECKS[rule["kind"]](text, rule))
    out.extend(check_confidential(text, facts))
    return out
