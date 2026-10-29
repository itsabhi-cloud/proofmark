"""Small, dependency-free text helpers used by every check."""
import re

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’-]*")
SENTENCE_RE = re.compile(r"[^.!?\n]+(?:[.!?]+|\n|$)")

STOPWORDS = set(
    """a an the and or but if then of to in on for with at by from as is are was were be been it this that
    these those our your you we they he she i me my us them his her its not no do does did can will just so
    than too very into over under about up down out off more most such only own same other all any each""".split()
)


def sentences(text):
    """Return a list of (start, end, sentence_text) spans, skipping blanks."""
    out = []
    for m in SENTENCE_RE.finditer(text):
        chunk = m.group(0)
        if chunk.strip():
            lead = len(chunk) - len(chunk.lstrip())
            start = m.start() + lead
            end = m.start() + len(chunk.rstrip())
            out.append((start, end, text[start:end]))
    return out


def sentence_at(text, index):
    for start, end, s in sentences(text):
        if start <= index <= end:
            return start, end, s
    return 0, len(text), text


def syllables(word):
    word = word.lower().strip("'’-")
    if not word:
        return 0
    if len(word) <= 3:
        return 1
    word = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", word)
    word = re.sub(r"^y", "", word)
    groups = re.findall(r"[aeiouy]{1,2}", word)
    return max(1, len(groups))


def flesch_reading_ease(text):
    words = WORD_RE.findall(text)
    sents = [s for s in sentences(text) if WORD_RE.search(s[2])]
    if not words or not sents:
        return 100.0
    syl = sum(syllables(w) for w in words)
    return round(206.835 - 1.015 * (len(words) / len(sents)) - 84.6 * (syl / len(words)), 1)


def tokens(text):
    return [w.lower() for w in WORD_RE.findall(text) if w.lower() not in STOPWORDS and len(w) > 2]


def relevance(query_tokens, doc_text):
    doc = set(tokens(doc_text))
    return sum(1 for t in set(query_tokens) if t in doc)


def top_relevant(text, items, key, limit):
    """Rank items by token overlap with text. Keeps order stable for ties."""
    q = tokens(text)
    scored = [(relevance(q, key(it)), i, it) for i, it in enumerate(items)]
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [it for score, _, it in scored[:limit]]


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?91[\s-]?)?\b[6-9]\d{4}[\s-]?\d{5}\b")


def mask_pii(text):
    """Replace emails and phone numbers with placeholders before any AI call.

    Placeholders have the same length as the original value so character
    offsets reported by the AI still line up with the original text.
    Returns (masked_text, count).
    """
    count = 0

    def repl(kind):
        def _r(m):
            nonlocal count
            count += 1
            token = f"[{kind}{count}]"
            value = m.group(0)
            if len(token) <= len(value):
                return token + "_" * (len(value) - len(token))
            return ("#" * len(value))
        return _r

    masked = EMAIL_RE.sub(repl("EMAIL"), text)
    masked = PHONE_RE.sub(repl("PHONE"), masked)
    return masked, count


def find_span(text, quote, hint=None):
    """Locate quote in text. Exact match first, then case-insensitive.

    hint: preferred start index when the quote appears more than once.
    Returns (start, end) or None.
    """
    if not quote or not quote.strip():
        return None
    quote = quote.strip()
    candidates = [m.start() for m in re.finditer(re.escape(quote), text)]
    if not candidates:
        candidates = [m.start() for m in re.finditer(re.escape(quote), text, re.IGNORECASE)]
    if not candidates:
        return None
    if hint is not None:
        best = min(candidates, key=lambda c: abs(c - hint))
    else:
        best = candidates[0]
    return best, best + len(quote)
