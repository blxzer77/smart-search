import re

from .research_keywords import (
    DOCS_INTENT_ASCII_STRONG,
    DOCS_INTENT_TERSE_PAIRS,
    DOCS_INTENT_TEXT_STRONG,
    FETCH_INTENT_KEYWORDS,
    RESEARCH_BROAD_TOPIC_KEYWORDS,
    RESEARCH_PROVIDER_MENTION_KEYWORDS,
    ZH_CURRENT_KEYWORDS,
)

_URL_RE = re.compile(r"https?://[^\s<>\]\)\"']+", re.IGNORECASE)


def contains_any(query: str, keywords: set[str]) -> bool:
    q = query.lower()
    return any(keyword.lower() in q for keyword in keywords)


def _strip_urls(query: str) -> str:
    return _URL_RE.sub(" ", query or "")


def _ascii_keyword_hit(text: str, keyword: str) -> bool:
    pattern = re.escape(keyword).replace(r"\ ", r"\s+")
    return bool(re.search(rf"(?<![a-z0-9_]){pattern}(?![a-z0-9_])", text))


def _any_ascii_hit(text: str, keywords: set[str]) -> bool:
    return any(_ascii_keyword_hit(text, keyword) for keyword in keywords)


def is_broad_research_intent(query: str) -> bool:
    q = query.lower()
    mentions_provider = any(keyword in q for keyword in RESEARCH_PROVIDER_MENTION_KEYWORDS)
    broad_topic = any(keyword in q for keyword in RESEARCH_BROAD_TOPIC_KEYWORDS)
    return mentions_provider and broad_topic


def is_docs_intent(query: str) -> bool:
    """Precision-first docs/API detector (no embeddings / LLM).

    Strong cues alone count. Weak product/language tokens need a strong cue or a
    terse allowlist pair. Queries that only contain a URL (or URL + non-docs residue)
    do not count as docs intent — fetch-first handles known URLs.
    """
    if is_broad_research_intent(query):
        return False
    remainder = _strip_urls(query).lower().strip()
    has_url = bool(_URL_RE.search(query or ""))
    if has_url and not remainder:
        return False

    if any(keyword in remainder for keyword in DOCS_INTENT_TEXT_STRONG):
        return True
    if _any_ascii_hit(remainder, DOCS_INTENT_ASCII_STRONG):
        return True

    for weak, companions in DOCS_INTENT_TERSE_PAIRS:
        if _ascii_keyword_hit(remainder, weak) and any(_ascii_keyword_hit(remainder, c) for c in companions):
            return True

    return False


def is_zh_current_intent(query: str) -> bool:
    q = query.lower()
    return any(keyword in q for keyword in ZH_CURRENT_KEYWORDS)


def is_fetch_intent(query: str) -> bool:
    return contains_any(query, FETCH_INTENT_KEYWORDS)
