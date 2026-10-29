"""Claim Receipts.

Finds factual and promotional claims in a draft and checks each one against
the approved-facts library. Every claim ends in one of three states:

  Supported     an approved, unexpired fact backs it
  Contradicted  an approved fact says something different
  Unbacked      no approved fact covers it (or the fact has expired)

Numbers are always compared by code. The AI may *extract* claims, but it
never decides whether 24 hours equals 10 hours.
"""
import re
from datetime import date

from .exact import finding
from .text_utils import sentence_at

UNITS = {
    "hour": ["hours", "hour", "hrs", "hr", "h"],
    "minute": ["minutes", "minute", "mins", "min"],
    "day": ["days", "day"],
    "year": ["years", "year", "yrs", "yr"],
    "month": ["months", "month"],
    "percent": ["%", "percent", "per cent"],
    "mAh": ["mah"],
    "mm": ["mm"],
    "GB": ["gb"],
    "dB": ["db"],
    "W": ["watts", "watt", "w"],
    "kg": ["kg"],
    "g": ["grams", "gram", "g"],
}
UNIT_LOOKUP = {alias: canon for canon, aliases in UNITS.items() for alias in aliases}
_unit_alt = "|".join(sorted((re.escape(a) for a in UNIT_LOOKUP), key=len, reverse=True))

QUALIFIER = r"(?P<qual>up\s*to|upto|over|more\s+than|at\s+least|nearly|almost|around|about|under|less\s+than)?\s*"
NUMBER_UNIT_RE = re.compile(
    QUALIFIER + r"(?P<num>\d+(?:[.,]\d+)?)\s*-?\s*(?P<unit>" + _unit_alt + r")(?![A-Za-z])",
    re.IGNORECASE,
)
CURRENCY_RE = re.compile(
    QUALIFIER + r"(?:₹|rs\.?\s*|inr\s*)(?P<num>\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)

SUPERLATIVES = {
    "best": "great",
    "fastest": "fast",
    "cheapest": "affordable",
    "lowest price": "great price",
    "#1": "popular",
    "number one": "popular",
    "no. 1": "popular",
    "guaranteed": "designed",
    "guarantee": "aim",
    "100% safe": "designed for safety",
    "unbeatable": "great",
    "world's first": "new",
    "world’s first": "new",
    "clinically proven": "tested",
    "most loved": "loved",
    "never fails": "reliable",
}
SUPERLATIVE_RE = re.compile(
    r"(?:the\s+)?(?P<word>" + "|".join(re.escape(k) for k in sorted(SUPERLATIVES, key=len, reverse=True))
    + r")(?P<tail>(?:\s+in\s+(?:india|the\s+world|the\s+market|town|class))?)(?!\w)",
    re.IGNORECASE,
)


def _num(s):
    return float(s.replace(",", ""))


def _expired(fact, today):
    vu = fact.get("valid_until")
    if not vu:
        return False
    try:
        return date.fromisoformat(vu[:10]) < today
    except ValueError:
        return False


def _fact_line(f):
    src = f" ({f['source']})" if f.get("source") else ""
    return f'{f["code"]}: {f["statement"]}{src}'


def _clause(sentence, offset):
    """The comma/semicolon-separated part of the sentence that holds the claim."""
    parts = re.split(r"(?<=[,;:])\s+|\s+(?:and|but|while)\s+", sentence)
    pos = 0
    for part in parts:
        idx = sentence.find(part, pos)
        if idx <= offset < idx + len(part) + 1:
            return part
        pos = idx + len(part)
    return sentence


def _best_fact(sentence, offset, unit, facts):
    """Fact with the same unit whose keywords best match the claim's clause, then sentence."""
    candidates = [f for f in facts if (f.get("unit") or "").lower() == unit.lower() and f.get("value") is not None]
    for scope in (_clause(sentence, offset), sentence):
        s = scope.lower()
        best, best_score = None, 0
        for f in candidates:
            score = sum(1 for kw in f.get("keywords", []) if kw.lower() in s)
            if score > best_score:
                best, best_score = f, score
        if best:
            return best
    if len(candidates) == 1:  # e.g. the only approved price
        return candidates[0]
    return None


def numeric_claims(text, rule, facts, today=None):
    today = today or date.today()
    public = [f for f in facts if not f.get("confidential")]
    out = []
    matches = []
    for m in NUMBER_UNIT_RE.finditer(text):
        matches.append((m, UNIT_LOOKUP[m.group("unit").lower()]))
    for m in CURRENCY_RE.finditer(text):
        matches.append((m, "INR"))

    for m, unit in matches:
        value = _num(m.group("num"))
        qual = (m.group("qual") or "").lower().replace(" ", "")
        s_start, s_end, sentence = sentence_at(text, m.start())
        fact = _best_fact(sentence, m.start() - s_start, unit, public)
        start, end = m.start(), m.end()
        claim = text[start:end].strip()
        start = start + (len(text[start:end]) - len(text[start:end].lstrip()))

        if fact is None:
            out.append(finding(
                rule, start, start + len(claim), text,
                f'"{claim}" is a measurable claim, but no approved fact backs it. '
                "Add the fact to the library or remove the number.",
                category="claims", claim_state="Unbacked", severity="medium",
            ))
            continue

        unit_word = m.group("unit") if unit != "INR" else ""
        if _expired(fact, today):
            out.append(finding(
                rule, start, start + len(claim), text,
                f'The approved fact for this claim expired on {fact["valid_until"]}. '
                "Confirm it is still true before publishing.",
                category="claims", claim_state="Unbacked", severity="high",
                fact_code=fact["code"], evidence=_fact_line(fact),
            ))
            continue

        approved = fact["value"]
        too_high = value > approved + 1e-9
        mismatch = abs(value - approved) > 1e-9
        contradicted = mismatch if fact.get("comparison") == "exact" else too_high
        if qual in ("over", "morethan", "atleast") and value >= approved - 1e-9 and fact.get("comparison") != "exact":
            contradicted = True

        approved_txt = f"{approved:g}"
        if unit == "INR":
            fixed = f"₹{int(approved):,}" if approved == int(approved) else f"₹{approved:,}"
        else:
            sep = "" if unit_word == "%" else " "
            fixed = f"{approved_txt}{sep}{unit_word}"
            if qual:
                fixed = "up to " + fixed

        if contradicted:
            out.append(finding(
                rule, start, start + len(claim), text,
                f'"{claim}" conflicts with the approved figure in {fact["code"]} '
                f'({fixed.replace("up to ", "")}{", at most" if fact.get("comparison") != "exact" else ", exactly"}).',
                suggestion=fixed,
                category="claims", claim_state="Contradicted", severity="high",
                fact_code=fact["code"], evidence=_fact_line(fact),
            ))
        else:
            note = "Matches the approved fact."
            if mismatch:
                note = "Lower than the approved figure, so it is not misleading; you may use the exact figure."
            out.append(finding(
                rule, start, start + len(claim), text, note,
                category="claims", claim_state="Supported", severity="info",
                fact_code=fact["code"], evidence=_fact_line(fact),
            ))
    return out


def superlative_claims(text, rule, facts):
    public = [f for f in facts if not f.get("confidential")]
    out = []
    for m in SUPERLATIVE_RE.finditer(text):
        word = m.group("word").lower()
        phrase = m.group(0)
        start = m.start()
        backing = None
        for f in public:
            if word in f["statement"].lower():
                backing = f
                break
        if backing:
            out.append(finding(
                rule, start, m.end(), text, "Backed by an approved fact.",
                category="claims", claim_state="Supported", severity="info",
                fact_code=backing["code"], evidence=_fact_line(backing),
            ))
            continue
        soft = SUPERLATIVES.get(word, "")
        has_the = phrase.lower().startswith("the ")
        suggestion = None
        if soft and not has_the and not m.group("tail"):
            suggestion = soft[:1].upper() + soft[1:] if phrase[:1].isupper() else soft
        out.append(finding(
            rule, start, m.end(), text,
            f'"{phrase.strip()}" is an absolute claim with no approved evidence. '
            "Add proof to the facts library or soften the wording.",
            suggestion=suggestion, category="claims", claim_state="Unbacked",
        ))
    return out


def run_claims(text, rules, facts, today=None):
    out = []
    for rule in rules:
        if rule["method"] != "exact":
            continue
        if rule["kind"] == "numeric_claims":
            out.extend(numeric_claims(text, rule, facts, today))
        elif rule["kind"] == "unbacked_claims":
            out.extend(superlative_claims(text, rule, facts))
    return out
