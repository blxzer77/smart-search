import re

from .research_keywords import (
    DOCS_INTENT_ASCII_KEYWORDS,
    DOCS_INTENT_TEXT_KEYWORDS,
    FETCH_INTENT_KEYWORDS,
    RESEARCH_BROAD_TOPIC_KEYWORDS,
    RESEARCH_PROVIDER_MENTION_KEYWORDS,
    ZH_CURRENT_KEYWORDS,
)


def contains_any(query: str, keywords: set[str]) -> bool:
    q = query.lower()
    return any(keyword.lower() in q for keyword in keywords)


def is_broad_research_intent(query: str) -> bool:
    q = query.lower()
    mentions_provider = any(keyword in q for keyword in RESEARCH_PROVIDER_MENTION_KEYWORDS)
    broad_topic = any(keyword in q for keyword in RESEARCH_BROAD_TOPIC_KEYWORDS)
    return mentions_provider and broad_topic


def is_docs_intent(query: str) -> bool:
    if is_broad_research_intent(query):
        return False
    q = query.lower()
    if any(keyword in q for keyword in DOCS_INTENT_TEXT_KEYWORDS):
        return True
    for keyword in DOCS_INTENT_ASCII_KEYWORDS:
        pattern = re.escape(keyword).replace(r"\ ", r"\s+")
        if re.search(rf"(?<![a-z0-9_]){pattern}(?![a-z0-9_])", q):
            return True
    return False


def is_zh_current_intent(query: str) -> bool:
    q = query.lower()
    return any(keyword in q for keyword in ZH_CURRENT_KEYWORDS)


def is_fetch_intent(query: str) -> bool:
    return contains_any(query, FETCH_INTENT_KEYWORDS)
