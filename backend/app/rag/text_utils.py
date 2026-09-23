"""Tokenising, number extraction and sentence helpers shared by retrieval and validation."""
import re
from typing import List, Set, Iterable

STOPWORDS: Set[str] = {
    "a", "an", "the", "and", "or", "but", "if", "then", "so", "of", "to", "in", "on", "at", "by", "for", "with",
    "from", "as", "into", "about", "over", "under", "between", "is", "are", "was", "were", "be", "been", "being",
    "it", "its", "this", "that", "these", "those", "our", "we", "you", "your", "their", "they", "them", "he", "she",
    "his", "her", "i", "me", "my", "do", "does", "did", "have", "has", "had", "will", "would", "can", "could",
    "should", "may", "might", "must", "not", "no", "yes", "all", "any", "each", "more", "most", "some", "such",
    "than", "too", "very", "also", "what", "which", "who", "how", "why", "when", "where", "there", "here",
}

# Words that describe the deck itself rather than its subject ("Create a 10-slide presentation explaining ...")
REQUEST_WORDS: Set[str] = {
    "create", "make", "build", "generate", "prepare", "produce", "write", "draft", "give", "need", "want",
    "please", "presentation", "presentations", "deck", "slides", "slide", "ppt", "pptx", "powerpoint",
    "explaining", "explain", "covering", "cover", "about", "summarising", "summarizing", "summarise", "summarize",
    "including", "include", "overview", "brief", "short", "detailed", "comprehensive",
}

_TOKEN = re.compile(r"[a-z0-9]+(?:[.'][a-z0-9]+)*")


def tokenize(text: str, drop_stopwords: bool = True) -> List[str]:
    tokens = _TOKEN.findall(str(text).lower())
    if drop_stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 1]
    return tokens


def token_set(text: str) -> Set[str]:
    return set(tokenize(text))


# A figure: optional currency, digits with thousands separators/decimals, optional %/scale suffix.
# Digits glued to letters (Q3, FY2024, H1, 10-K) are identifiers, not figures, so they are skipped.
_NUMBER = re.compile(
    r"(?<![A-Za-z0-9.])[$€£₹]?\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?"
    r"(?:\s?(%|percent\b|pp\b|x\b|[kmb]n?\b|thousand\b|million\b|billion\b))?",
    re.IGNORECASE,
)


_SCALES = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9}


def _values(m: "re.Match") -> Set[str]:
    """Canonical value of a match, plus its expanded form when it has a scale ('4.2M' → {'4.2', '4200000'})."""
    value = float(m.group(1).replace(",", "") + ("." + m.group(2) if m.group(2) else ""))
    out = {f"{value:g}"}
    scale = _SCALES.get((m.group(3) or "").lower())
    if scale:
        out.add(f"{round(value * scale, 6):g}")
    return out


def _glued_to_word(text: str, m: "re.Match") -> bool:
    end = m.end()
    return end < len(text) and text[end:end + 1].isalpha() and not m.group(3)


def extract_numbers(text: str) -> Set[str]:
    """Canonical values of the figures in a text ('$4,200.50' → '4200.5', '12%' → '12', '4.2M' → '4.2', '4200000')."""
    text = str(text)
    out: Set[str] = set()
    for m in _NUMBER.finditer(text):
        if not _glued_to_word(text, m):
            out |= _values(m)
    return out


def unsupported_numbers(text: str, supported: Set[str]) -> List[str]:
    """The figures of `text` (as written) none of whose equivalent values are in `supported`."""
    text = str(text)
    missing = []
    for m in _NUMBER.finditer(text):
        if _glued_to_word(text, m):
            continue
        raw = m.group(0).strip()
        has_unit = bool(m.group(3)) or any(sym in raw for sym in "$€£₹")
        if not has_unit and not m.group(2) and "," not in m.group(1) and float(m.group(1)) <= 10:
            continue
        if not (_values(m) & supported):
            missing.append(raw)
    return missing


_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


def split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE.split(str(text)) if s.strip()]


def best_matching_sentence(source: str, claim: str, max_len: int = 220) -> str:
    """The sentence of `source` that best supports `claim` (numbers weigh most), for use as a citation excerpt."""
    claim_tokens = token_set(claim)
    claim_nums = extract_numbers(claim)
    best, best_score = "", -1.0
    for sentence in split_sentences(source):
        score = 3 * len(claim_nums & extract_numbers(sentence)) + len(claim_tokens & token_set(sentence))
        if score > best_score:
            best, best_score = sentence, score
    best = best or str(source)
    return best if len(best) <= max_len else best[:max_len].rsplit(" ", 1)[0] + "…"


def normalise_for_match(text: str) -> str:
    """Lowercase, straight quotes, collapsed whitespace: for verbatim-quote checks."""
    text = str(text).lower().translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"}))
    text = re.sub(r"[\"']", "", text)
    return re.sub(r"\s+", " ", text).strip()


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    a, b = set(a), set(b)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
