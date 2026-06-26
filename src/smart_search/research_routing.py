from typing import Any

from .config import config
from .research_intent import (
    contains_any as _contains_any,
    is_broad_research_intent as _is_broad_research_intent,
    is_docs_intent as _is_docs_intent,
    is_zh_current_intent as _is_zh_current_intent,
)
from .research_keywords import (
    DEEP_EXA_DISCOVERY_KEYWORDS,
    PROVIDER_PROFILES,
    RESEARCH_JS_HEAVY_KEYWORDS,
    RESEARCH_PDF_KEYWORDS,
    RESEARCH_PROFILE_ORDER,
    RESEARCH_ROUTE_POLICY_VERSION,
)
from .research_plan import _extract_urls


def provider_profiles() -> dict[str, dict[str, Any]]:
    return {provider: dict(profile) for provider, profile in PROVIDER_PROFILES.items()}


def _provider_supports_capability(provider: str, capability: str) -> bool:
    profile = PROVIDER_PROFILES.get(provider, {})
    capabilities = set(profile.get("capabilities") or [profile.get("capability", "")])
    return capability in capabilities


def _provider_configured(provider: str) -> bool:
    if provider == "openai-compatible":
        return bool(config.openai_compatible_api_url and config.openai_compatible_api_key)
    if provider == "context7":
        return bool(config.context7_api_key)
    if provider == "exa":
        return bool(config.exa_api_key)
    if provider == "zhipu":
        return bool(config.zhipu_api_key)
    if provider == "tavily":
        return bool(config.tavily_api_key)
    if provider == "jina":
        return bool(config.jina_api_key)
    if provider == "firecrawl":
        return bool(config.firecrawl_api_key)
    if provider == "main-search":
        return bool(config.openai_compatible_api_url and config.openai_compatible_api_key)
    return False


def _configured_for_capability(capability: str, capability_status: dict[str, Any] | None = None) -> list[str]:
    if capability_status is not None:
        configured = set(capability_status.get(capability, {}).get("configured") or [])
        return [
            provider
            for provider in RESEARCH_PROFILE_ORDER.get(capability, [])
            if provider in configured and _provider_supports_capability(provider, capability)
        ]
    return [provider for provider in RESEARCH_PROFILE_ORDER.get(capability, []) if _provider_configured(provider)]

def _safe_provider_overrides() -> tuple[list[str], list[str], list[str]]:
    known = set(PROVIDER_PROFILES)
    preferred = [provider for provider in config.research_preferred_providers if provider in known]
    disabled = [provider for provider in config.research_disabled_providers if provider in known]
    invalid = [
        provider
        for provider in config.research_preferred_providers + config.research_disabled_providers
        if provider not in known
    ]
    return preferred, disabled, invalid


def _apply_research_overrides(capability: str, providers: list[str]) -> list[str]:
    preferred, disabled, _ = _safe_provider_overrides()
    allowed = [
        provider
        for provider in providers
        if provider not in disabled and _provider_supports_capability(provider, capability)
    ]
    ordered = [
        provider
        for provider in preferred
        if provider in allowed and _provider_supports_capability(provider, capability)
    ]
    ordered.extend(provider for provider in allowed if provider not in ordered)
    return ordered


def _research_fetch_order(query: str, url: str = "", capability_status: dict[str, Any] | None = None) -> list[str]:
    providers = _configured_for_capability("web_fetch", capability_status)
    target = f"{query} {url}".lower()
    if _contains_any(target, RESEARCH_JS_HEAVY_KEYWORDS):
        preferred = ["firecrawl", "tavily", "jina"]
    elif _contains_any(target, RESEARCH_PDF_KEYWORDS) or url.lower().endswith(".pdf"):
        preferred = ["jina", "tavily", "firecrawl"]
    elif url or _extract_urls(query):
        preferred = ["jina", "tavily", "firecrawl"]
    else:
        preferred = providers
    ordered = [provider for provider in preferred if provider in providers]
    ordered.extend(provider for provider in providers if provider not in ordered)
    return _apply_research_overrides("web_fetch", ordered)


def _research_route_signals(question: str, plan: dict[str, Any]) -> dict[str, Any]:
    intent = plan.get("intent_signals") or {}
    text = question.lower()
    return {
        "docs_api_intent": bool(intent.get("docs_api_intent")) or _is_docs_intent(question),
        "broad_research_intent": _is_broad_research_intent(question),
        "official_low_noise_intent": _contains_any(question, DEEP_EXA_DISCOVERY_KEYWORDS),
        "current_or_locale_intent": intent.get("recency_requirement") in {"recent", "current"}
        or intent.get("locale_domain_scope") == "china"
        or _is_zh_current_intent(question),
        "known_url": bool(intent.get("known_url")) or bool(_extract_urls(question)),
        "pdf_or_arxiv_intent": _contains_any(question, RESEARCH_PDF_KEYWORDS),
        "js_heavy_intent": _contains_any(question, RESEARCH_JS_HEAVY_KEYWORDS),
        "claim_risk": intent.get("claim_risk", "medium"),
        "cross_validation_need": intent.get("cross_validation_need", "normal"),
        "raw_query": text,
    }


def _research_capability_routes(
    question: str,
    plan: dict[str, Any],
    fallback: str,
    capability_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    signals = _research_route_signals(question, plan)
    _, _, invalid_overrides = _safe_provider_overrides()
    routes: dict[str, Any] = {
        "signals": signals,
        "fallback_mode": fallback,
        "route_policy_version": RESEARCH_ROUTE_POLICY_VERSION,
        "invalid_provider_overrides": invalid_overrides,
        "capabilities": {},
    }

    web_search = _configured_for_capability("web_search", capability_status)
    ordered = [provider for provider in ["tavily", "firecrawl"] if provider in web_search]
    routes["capabilities"]["web_search"] = {
        "providers": _apply_research_overrides("web_search", ordered),
        "reason": (
            "bilingual current/locale evidence"
            if signals["current_or_locale_intent"]
            else "bilingual broad source discovery"
        ),
    }

    docs = _configured_for_capability("docs_search", capability_status)
    docs_order = [provider for provider in ["context7", "exa"] if provider in docs]
    if signals["official_low_noise_intent"] and not signals["docs_api_intent"]:
        docs_order = [provider for provider in ["exa", "context7"] if provider in docs]
    routes["capabilities"]["docs_search"] = {
        "providers": _apply_research_overrides("docs_search", docs_order),
        "reason": "docs/API evidence" if signals["docs_api_intent"] else "official low-noise discovery",
    }

    fetch_order = _research_fetch_order(question, capability_status=capability_status)
    routes["capabilities"]["web_fetch"] = {
        "providers": fetch_order,
        "reason": "JS-heavy fetch" if signals["js_heavy_intent"] else ("known URL/PDF extraction" if signals["known_url"] or signals["pdf_or_arxiv_intent"] else "evidence extraction"),
    }

    return routes
