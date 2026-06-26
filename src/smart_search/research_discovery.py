import time

from .config import config
from .research_plan import _bilingual_search_queries
from .sources import merge_sources

LOCALE_SCOPE_CHOICES = frozenset({"cn", "en", "both"})


def normalize_locale_scope(locale_scope: str = "both") -> str:
    scope = (locale_scope or "both").strip().lower()
    if scope not in LOCALE_SCOPE_CHOICES:
        raise ValueError(f"Invalid locale scope: {locale_scope}")
    return scope


def _variant_matches_locale_scope(variant_locale: str, locale_scope: str) -> bool:
    scope = normalize_locale_scope(locale_scope)
    if scope == "both":
        return True
    locale = (variant_locale or "").strip().lower()
    if scope == "cn":
        return locale in {"zh", "cn"}
    return locale == "en"


def _service():
    from . import service as svc

    return svc


async def run_web_search_fallback(
    query: str,
    count: int = 5,
    providers: str = "auto",
    fallback: str = "auto",
) -> tuple[list[dict], list[dict]]:
    provider_filter = _service()._parse_provider_filter(providers)
    attempts: list[dict] = []
    configured: list[str] = []
    if config.tavily_api_key:
        configured.append("tavily")
    if config.firecrawl_api_key:
        configured.append("firecrawl")
    if provider_filter is not None and "zhipu" in provider_filter and config.zhipu_api_key:
        configured.append("zhipu")
    if provider_filter is not None:
        configured = [p for p in configured if p in provider_filter]
    if fallback == "off":
        configured = configured[:1]

    for provider in configured:
        start = time.time()
        try:
            if provider == "zhipu":
                data = await _service().zhipu_search(query, count=count)
                if data.get("ok"):
                    sources = _service()._normalize_source_results(data.get("results"), "zhipu")
                    if sources:
                        attempts.append(
                            _service()._attempt("web_search", provider, "ok", start, result_count=len(sources))
                        )
                        return sources, attempts
                status = (
                    "error"
                    if data.get("error_type")
                    in {"rate_limited", "auth_error", "timeout", "network_error", "runtime_error"}
                    else "empty"
                )
                attempts.append(
                    _service()._attempt(
                        "web_search",
                        provider,
                        status,
                        start,
                        error_type=data.get("error_type", ""),
                        error=data.get("error", ""),
                    )
                )
            elif provider == "tavily":
                results = await _service().call_tavily_search(query, count)
                sources = _service()._normalize_source_results(results, "tavily")
                if sources:
                    attempts.append(
                        _service()._attempt("web_search", provider, "ok", start, result_count=len(sources))
                    )
                    return sources, attempts
                attempts.append(_service()._attempt("web_search", provider, "empty", start))
            elif provider == "firecrawl":
                results = await _service().call_firecrawl_search(query, count)
                sources = _service()._normalize_source_results(results, "firecrawl")
                if sources:
                    attempts.append(
                        _service()._attempt("web_search", provider, "ok", start, result_count=len(sources))
                    )
                    return sources, attempts
                attempts.append(_service()._attempt("web_search", provider, "empty", start))
        except Exception as e:
            attempts.append(
                _service()._attempt("web_search", provider, "error", start, error_type="runtime_error", error=str(e))
            )
    return [], attempts


async def run_bilingual_web_search(
    query: str,
    count: int = 5,
    providers: str = "auto",
    fallback: str = "auto",
    locale_scope: str = "both",
) -> tuple[list[dict], list[dict]]:
    all_sources: list[dict] = []
    all_attempts: list[dict] = []
    scope = normalize_locale_scope(locale_scope)
    for variant in _bilingual_search_queries(query):
        if not _variant_matches_locale_scope(variant.get("locale", ""), scope):
            continue
        sources, attempts = await _service()._run_web_search_fallback(
            variant["query"],
            count=count,
            providers=providers,
            fallback=fallback,
        )
        for source in sources:
            source.setdefault("query_locale", variant["locale"])
        all_sources = merge_sources(all_sources, sources)
        all_attempts.extend(attempts)
    return all_sources, all_attempts


async def run_docs_search_fallback(
    query: str,
    providers: str = "auto",
    fallback: str = "auto",
) -> tuple[list[dict], list[dict]]:
    provider_filter = _service()._parse_provider_filter(providers)
    attempts: list[dict] = []
    configured: list[str] = []
    if config.context7_api_key:
        configured.append("context7")
    if config.exa_api_key:
        configured.append("exa")
    if provider_filter is not None:
        configured = [p for p in configured if p in provider_filter]
    if fallback == "off":
        configured = configured[:1]

    for provider in configured:
        start = time.time()
        try:
            if provider == "exa":
                data = await _service().exa_search(query, num_results=5, include_highlights=True)
                if data.get("ok"):
                    sources = _service()._normalize_source_results(data.get("results"), "exa")
                    if sources:
                        attempts.append(
                            _service()._attempt("docs_search", provider, "ok", start, result_count=len(sources))
                        )
                        return sources, attempts
                status = (
                    "error"
                    if data.get("error_type")
                    in {"auth_error", "parameter_error", "rate_limited", "timeout", "network_error", "runtime_error"}
                    else "empty"
                )
                attempts.append(
                    _service()._attempt(
                        "docs_search",
                        provider,
                        status,
                        start,
                        error_type=data.get("error_type", ""),
                        error=data.get("error", ""),
                    )
                )
            elif provider == "context7":
                data = await _service().context7_library(query, query)
                if data.get("ok"):
                    sources = [
                        {
                            "url": f"context7:{item.get('id')}",
                            "title": item.get("title") or item.get("id") or "Context7",
                            "description": item.get("description") or "",
                            "provider": "context7",
                        }
                        for item in data.get("results", [])
                        if item.get("id")
                    ]
                    if sources:
                        attempts.append(
                            _service()._attempt("docs_search", provider, "ok", start, result_count=len(sources))
                        )
                        return sources, attempts
                status = (
                    "error"
                    if data.get("error_type") in {"auth_error", "timeout", "network_error", "runtime_error"}
                    else "empty"
                )
                attempts.append(
                    _service()._attempt(
                        "docs_search",
                        provider,
                        status,
                        start,
                        error_type=data.get("error_type", ""),
                        error=data.get("error", ""),
                    )
                )
        except Exception as e:
            attempts.append(
                _service()._attempt("docs_search", provider, "error", start, error_type="runtime_error", error=str(e))
            )
    return [], attempts