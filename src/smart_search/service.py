import asyncio
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from .config import config
from .errors import (
    ErrorType,
    EVIDENCE_INSUFFICIENT,
    FETCH_FAILED,
    MINIMUM_PROFILE,
    MISSING_API_KEY,
    PARSE_FAILED,
    PROVIDER_EMPTY,
    PROVIDER_NETWORK,
    PROVIDER_RUNTIME,
    PROVIDER_TIMEOUT,
    SEARCH_FAILED,
    attach_error_fields,
    error_fields,
    missing_api_key_message,
)
from .logger import log_info
from .providers.context7 import Context7Provider
from .providers.exa import ExaSearchProvider
from .providers.jina import JinaReaderProvider
from .providers.openai_compatible import OpenAICompatibleSearchProvider
from .providers.xai_responses import XAIResponsesSearchProvider
from .research_keywords import (
    DEEP_ALLOWED_TOOLS,
    DEEP_CHINA_KEYWORDS,
    DEEP_CURRENT_KEYWORDS,
    DEEP_EXA_DISCOVERY_KEYWORDS,
    DEEP_HIGH_COMPLEXITY_KEYWORDS,
    DEEP_RECENT_KEYWORDS,
    DEEP_TRIGGER_KEYWORDS,
    DOCS_INTENT_ASCII_KEYWORDS,
    DOCS_INTENT_KEYWORDS,
    DOCS_INTENT_TEXT_KEYWORDS,
    FETCH_INTENT_KEYWORDS,
    MAIN_SEARCH_FALLBACK_CHAIN,
    MAIN_SEARCH_PROVIDER_ALIASES,
    MINIMUM_PROFILE_ERROR,
    PROVIDER_PROFILES,
    RESEARCH_BROAD_TOPIC_KEYWORDS,
    RESEARCH_JS_HEAVY_KEYWORDS,
    RESEARCH_PDF_KEYWORDS,
    RESEARCH_PROFILE_ORDER,
    RESEARCH_PROVIDER_MENTION_KEYWORDS,
    RESEARCH_ROUTE_POLICY_VERSION,
    SOURCE_PROVENANCE_WARNING,
    ZH_CURRENT_KEYWORDS,
)
from .research_gap import (
    http_fetched_evidence_items as _http_fetched_evidence_items_impl,
    is_http_evidence_url as _is_http_evidence_url_impl,
    research_gap_status as _research_gap_status_impl,
)
from .research_intent import (
    contains_any as _contains_any_impl,
    is_broad_research_intent as _is_broad_research_intent_impl,
    is_docs_intent as _is_docs_intent_impl,
    is_fetch_intent as _is_fetch_intent_impl,
    is_zh_current_intent as _is_zh_current_intent_impl,
)
from .research_plan import (
    _bilingual_search_queries as _bilingual_search_queries_impl,
    _deep_budget as _deep_budget_impl,
    _deep_capability as _deep_capability_impl,
    _deep_step as _deep_step_impl,
    _deep_subquestion as _deep_subquestion_impl,
    _default_evidence_dir as _default_evidence_dir_impl,
    _extract_urls as _extract_urls_impl,
    _is_deep_complex as _is_deep_complex_impl,
    _path_join as _path_join_impl,
    _quote_arg as _quote_arg_impl,
    _slugify_query as _slugify_query_impl,
    build_deep_research_plan as _build_deep_research_plan_impl,
)
from .research_routing import (
    _apply_research_overrides as _apply_research_overrides_impl,
    _configured_for_capability as _configured_for_capability_impl,
    _provider_configured as _provider_configured_impl,
    _provider_supports_capability as _provider_supports_capability_impl,
    _research_capability_routes as _research_capability_routes_impl,
    _research_fetch_order as _research_fetch_order_impl,
    _research_route_signals as _research_route_signals_impl,
    _safe_provider_overrides as _safe_provider_overrides_impl,
    provider_profiles as _provider_profiles_impl,
)
from .research_artifacts import (
    artifact_path as _artifact_path_impl,
    write_research_artifact as _write_research_artifact_impl,
)
from .research_synthesis import (
    citation_items as _citation_items_impl,
    evidence_only_synthesis as _evidence_only_synthesis_impl,
    research_evidence_item as _research_evidence_item_impl,
    select_candidate_urls as _select_candidate_urls_impl,
)
from .research_fetch import (
    call_firecrawl_scrape as _call_firecrawl_scrape_impl,
    call_firecrawl_search as _call_firecrawl_search_impl,
    call_jina_reader as _call_jina_reader_impl,
    call_tavily_extract as _call_tavily_extract_impl,
    call_tavily_map as _call_tavily_map_impl,
    call_tavily_search as _call_tavily_search_impl,
    decode_provider_json as _decode_provider_json_impl,
    jina_fetch as _jina_fetch_impl,
    run_web_fetch_fallback as _run_web_fetch_fallback_impl,
)
from .diagnostics import (
    _probe_openai_compatible_search_shape as _probe_openai_compatible_search_shape_impl,
    _probe_xai_search_shape as _probe_xai_search_shape_impl,
    _safe_test_main_provider_connection as _safe_test_main_provider_connection_impl,
    _test_context7_connection as _test_context7_connection_impl,
    _test_exa_connection as _test_exa_connection_impl,
    _test_jina_connection as _test_jina_connection_impl,
    _test_main_provider_connection as _test_main_provider_connection_impl,
    _test_primary_chat_completion as _test_primary_chat_completion_impl,
    _test_primary_connection as _test_primary_connection_impl,
    _test_primary_responses as _test_primary_responses_impl,
    _test_tavily_connection as _test_tavily_connection_impl,
    diagnose_openai_compatible as _diagnose_openai_compatible_impl,
    diagnose_xai as _diagnose_xai_impl,
    doctor as _doctor_impl,
)
from .research_discovery import (
    run_bilingual_web_search as _run_bilingual_web_search_impl,
    run_docs_search_fallback as _run_docs_search_fallback_impl,
    run_web_search_fallback as _run_web_search_fallback_impl,
)
from .sources import merge_sources, new_session_id, split_answer_and_sources


_AVAILABLE_MODELS_CACHE: dict[tuple[str, str], list[str]] = {}
_AVAILABLE_MODELS_LOCK = asyncio.Lock()
def _elapsed_ms(start: float) -> float:
    return round((time.time() - start) * 1000, 2)


def _normalize_domain_filter(value: str | list[str] | tuple[str, ...] | None) -> list[str] | None:
    if not value:
        return None

    raw_parts = [value] if isinstance(value, str) else [str(item) for item in value if item]
    domains: list[str] = []
    for part in raw_parts:
        domains.extend(item.strip() for item in re.split(r"[\s,]+", part) if item.strip())
    return domains or None


def _empty_search_result(
    start: float,
    session_id: str,
    query: str,
    error_type: str,
    error: str,
    primary_api_mode: str = "",
    extra: dict[str, Any] | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "ok": False,
        **error_fields(error_type, error=error, error_code=error_code),
        "session_id": session_id,
        "query": query,
        "primary_api_mode": primary_api_mode,
        "content": "",
        "sources": [],
        "sources_count": 0,
        "primary_sources": [],
        "primary_sources_count": 0,
        "extra_sources": [],
        "extra_sources_count": 0,
        "source_warning": "",
        "routing_decision": {},
        "providers_used": [],
        "provider_attempts": [],
        "fallback_used": False,
        "validation_level": "",
        "elapsed_ms": _elapsed_ms(start),
    }
    if extra:
        data.update(extra)
        attach_error_fields(data)
    return data


def _attempt(
    capability: str,
    provider: str,
    status: str,
    start: float,
    result_count: int = 0,
    error_type: str = "",
    error: str = "",
    cache_hit: bool = False,
    error_code: str | None = None,
) -> dict[str, Any]:
    fields = error_fields(error_type, error=error, error_code=error_code) if error_type else {"error_type": "", "error_code": "", "error": error}
    return {
        "capability": capability,
        "provider": provider,
        "status": status,
        **fields,
        "elapsed_ms": _elapsed_ms(start),
        "result_count": result_count,
        "cache_hit": cache_hit,
    }


def _normalize_source_results(results: list[dict] | None, provider: str) -> list[dict]:
    normalized: list[dict] = []
    for item in results or []:
        url = (item.get("url") or item.get("link") or "").strip()
        if not url:
            continue
        out = {"url": url, "provider": item.get("provider") or provider}
        title = (item.get("title") or "").strip()
        if title:
            out["title"] = title
        desc = (item.get("description") or item.get("content") or item.get("snippet") or "").strip()
        if desc:
            out["description"] = desc
        published = item.get("published_date") or item.get("publishedDate") or item.get("publish_date")
        if published:
            out["published_date"] = published
        source = item.get("source") or item.get("media")
        if source:
            out["source"] = source
        normalized.append(out)
    return normalized


def _provider_names_from_attempts(attempts: list[dict]) -> list[str]:
    names: list[str] = []
    for attempt in attempts:
        provider = attempt.get("provider")
        if attempt.get("status") == "ok" and provider and provider not in names:
            names.append(provider)
    return names


def _fallback_used(attempts: list[dict]) -> bool:
    by_capability: dict[str, list[dict]] = {}
    for attempt in attempts:
        capability = attempt.get("capability", "")
        if attempt.get("status") in {"ok", "empty", "error"}:
            by_capability.setdefault(capability, []).append(attempt)
    for capability_attempts in by_capability.values():
        previous_failed = False
        previous_provider = ""
        for attempt in capability_attempts:
            provider = attempt.get("provider", "")
            status = attempt.get("status")
            if previous_failed:
                return True
            if previous_provider and provider and provider != previous_provider:
                return True
            previous_failed = status in {"empty", "error"}
            previous_provider = provider or previous_provider
    return False


def provider_profiles() -> dict[str, dict[str, Any]]:
    return _provider_profiles_impl()


def _provider_supports_capability(provider: str, capability: str) -> bool:
    return _provider_supports_capability_impl(provider, capability)


def _provider_configured(provider: str) -> bool:
    return _provider_configured_impl(provider)


def _configured_for_capability(capability: str, capability_status: dict[str, Any] | None = None) -> list[str]:
    return _configured_for_capability_impl(capability, capability_status)


def _bilingual_search_queries(query: str) -> list[dict[str, str]]:
    return _bilingual_search_queries_impl(query)


def _safe_provider_overrides() -> tuple[list[str], list[str], list[str]]:
    return _safe_provider_overrides_impl()


def _apply_research_overrides(capability: str, providers: list[str]) -> list[str]:
    return _apply_research_overrides_impl(capability, providers)


def _research_fetch_order(query: str, url: str = "", capability_status: dict[str, Any] | None = None) -> list[str]:
    return _research_fetch_order_impl(query, url=url, capability_status=capability_status)


def _research_route_signals(question: str, plan: dict[str, Any]) -> dict[str, Any]:
    return _research_route_signals_impl(question, plan)


def _research_capability_routes(
    question: str,
    plan: dict[str, Any],
    fallback: str,
    capability_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _research_capability_routes_impl(question, plan, fallback, capability_status=capability_status)


def _research_evidence_item(
    *,
    url: str,
    provider: str,
    title: str = "",
    content: str = "",
    source_type: str = "fetched_page",
    subquestion_id: str = "",
) -> dict[str, Any]:
    return _research_evidence_item_impl(
        url=url,
        provider=provider,
        title=title,
        content=content,
        source_type=source_type,
        subquestion_id=subquestion_id,
    )


def _citation_items(evidence_items: list[dict[str, Any]]) -> list[dict[str, str]]:
    return _citation_items_impl(evidence_items)


def _evidence_only_synthesis(question: str, evidence_items: list[dict[str, Any]], gaps: list[dict[str, Any]]) -> str:
    return _evidence_only_synthesis_impl(question, evidence_items, gaps)


def _select_candidate_urls(sources: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    return _select_candidate_urls_impl(sources, limit=limit)


def _artifact_path(evidence_root: str, name: str) -> Path:
    return _artifact_path_impl(evidence_root, name)


def _write_research_artifact(evidence_root: str, name: str, data: Any) -> None:
    return _write_research_artifact_impl(evidence_root, name, data)




def _is_docs_intent(query: str) -> bool:
    return _is_docs_intent_impl(query)


def _is_zh_current_intent(query: str) -> bool:
    return _is_zh_current_intent_impl(query)


def _is_fetch_intent(query: str) -> bool:
    return _is_fetch_intent_impl(query)


def _is_broad_research_intent(query: str) -> bool:
    return _is_broad_research_intent_impl(query)


def _is_http_evidence_url(url: str) -> bool:
    return _is_http_evidence_url_impl(url)


def _http_fetched_evidence_items(evidence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _http_fetched_evidence_items_impl(evidence_items)


def _research_gap_status(
    evidence_items: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    *,
    signals: dict[str, Any] | None = None,
) -> tuple[str, str]:
    return _research_gap_status_impl(evidence_items, gaps, signals=signals)


def _contains_any(query: str, keywords: set[str]) -> bool:
    return _contains_any_impl(query, keywords)


def _extract_urls(query: str) -> list[str]:
    return _extract_urls_impl(query)


def _slugify_query(query: str) -> str:
    return _slugify_query_impl(query)


def _default_evidence_dir(query: str) -> str:
    return _default_evidence_dir_impl(query)


def _quote_arg(value: str) -> str:
    return _quote_arg_impl(value)


def _path_join(base: str, filename: str) -> str:
    return _path_join_impl(base, filename)


def _deep_step(
    step_id: str,
    subquestion_id: str,
    tool: str,
    purpose: str,
    command: str,
    output_path: str,
) -> dict[str, str]:
    return _deep_step_impl(step_id, subquestion_id, tool, purpose, command, output_path)


def _deep_capability(capability: str, tools: list[str], reason: str) -> dict[str, Any]:
    return _deep_capability_impl(capability, tools, reason)


def _deep_subquestion(sub_id: str, question: str, reason: str, required_capabilities: list[str]) -> dict[str, Any]:
    return _deep_subquestion_impl(sub_id, question, reason, required_capabilities)


def _deep_budget(value: str) -> str:
    return _deep_budget_impl(value)


def _is_deep_complex(query: str, budget: str) -> bool:
    return _is_deep_complex_impl(query, budget)


def build_deep_research_plan(query: str, budget: str = "standard", evidence_dir: str = "") -> dict[str, Any]:
    return _build_deep_research_plan_impl(query, budget=budget, evidence_dir=evidence_dir)


async def research(
    query: str,
    budget: str = "deep",
    evidence_dir: str = "",
    fallback: str = "auto",
    locale_scope: str = "both",
    dry_run: bool = False,
    progress: bool = False,
) -> dict[str, Any]:
    from .research_executor import research as _research_executor

    return await _research_executor(
        query,
        budget=budget,
        evidence_dir=evidence_dir,
        fallback=fallback,
        locale_scope=locale_scope,
        dry_run=dry_run,
        progress=progress,
    )


def get_capability_status() -> dict[str, Any]:
    main_configured = _configured_main_search_provider_ids()
    try:
        main_chain = _effective_main_search_chain()
    except ValueError:
        main_chain = list(MAIN_SEARCH_FALLBACK_CHAIN)
    status = {
        "main_search": {
            "configured": main_configured,
            "fallback_chain": main_chain,
            "ok": bool(main_configured),
        },
        "web_search": {
            "configured": [
                name
                for name, enabled in [
                    ("tavily", bool(config.tavily_api_key)),
                    ("firecrawl", bool(config.firecrawl_api_key)),
                ]
                if enabled
            ],
            "fallback_chain": ["tavily", "firecrawl"],
        },
        "docs_search": {
            "configured": [
                name
                for name, enabled in [
                    ("context7", bool(config.context7_api_key)),
                    ("exa", bool(config.exa_api_key)),
                ]
                if enabled
            ],
            "fallback_chain": ["context7", "exa"],
        },
        "web_fetch": {
            "configured": [
                name
                for name, enabled in [
                    ("tavily", bool(config.tavily_api_key)),
                    ("jina", bool(config.jina_api_key)),
                    ("firecrawl", bool(config.firecrawl_api_key)),
                ]
                if enabled
            ],
            "fallback_chain": ["tavily", "jina", "firecrawl"],
        },
    }
    for capability in ("web_search", "docs_search", "web_fetch"):
        status[capability]["ok"] = bool(status[capability]["configured"])
    return status


def _minimum_profile_result(profile: str, capability_status: dict[str, Any]) -> dict[str, Any]:
    required = [] if profile == "off" else ["main_search", "docs_search", "web_fetch"]
    missing = [capability for capability in required if not capability_status.get(capability, {}).get("ok")]
    error_message = ""
    if missing:
        error_message = f"{MINIMUM_PROFILE_ERROR} Missing capabilities: {', '.join(missing)}"
    return {
        "ok": not missing,
        **error_fields(
            ErrorType.CONFIG if missing else None,
            error=error_message,
            error_code=MINIMUM_PROFILE if missing else None,
        ),
        "profile": profile,
        "required": required,
        "missing": missing,
        "capability_status": capability_status,
    }


def validate_minimum_profile() -> dict[str, Any]:
    try:
        profile = config.minimum_profile
    except ValueError as e:
        return {"ok": False, **error_fields(ErrorType.PARAMETER, error=str(e)), "missing": []}
    return _minimum_profile_result(profile, get_capability_status())


def _parse_provider_filter(providers: str = "auto") -> set[str] | None:
    if not providers or providers.strip().lower() == "auto":
        return None
    return {item.strip().lower() for item in providers.split(",") if item.strip()}


def _provider_allowed(provider_id: str, provider_filter: set[str] | None) -> bool:
    if provider_filter is None:
        return True
    aliases = MAIN_SEARCH_PROVIDER_ALIASES.get(provider_id, {provider_id})
    return bool(provider_filter.intersection(aliases))


def _effective_main_search_chain() -> list[str]:
    raw = config.main_search_route_raw
    if not raw.strip():
        return list(MAIN_SEARCH_FALLBACK_CHAIN)
    resolved: list[str] = []
    invalid: list[str] = []
    for item in raw.split(","):
        token = item.strip().lower()
        if not token:
            continue
        match = next(
            (
                provider
                for provider in MAIN_SEARCH_FALLBACK_CHAIN
                if token == provider or token in MAIN_SEARCH_PROVIDER_ALIASES.get(provider, set())
            ),
            None,
        )
        if match is None:
            invalid.append(token)
        elif match not in resolved:
            resolved.append(match)
    if invalid:
        allowed = ", ".join(MAIN_SEARCH_FALLBACK_CHAIN)
        invalid_text = ", ".join(invalid)
        raise ValueError(f"Invalid SMART_SEARCH_MAIN_SEARCH_ROUTE: {invalid_text}. Supported values: {allowed}")
    return resolved or list(MAIN_SEARCH_FALLBACK_CHAIN)


def _configured_main_search_provider_ids() -> list[str]:
    configured: set[str] = set()

    if config.xai_api_key:
        configured.add("xai-responses")
    if config.openai_compatible_api_url and config.openai_compatible_api_key:
        configured.add("openai-compatible")

    try:
        chain = _effective_main_search_chain()
    except ValueError:
        chain = list(MAIN_SEARCH_FALLBACK_CHAIN)
    return [provider for provider in chain if provider in configured]


def _main_search_provider_configs(model_override: str = "", providers: str = "auto") -> list[dict[str, Any]]:
    provider_filter = _parse_provider_filter(providers)
    by_provider: dict[str, dict[str, Any]] = {}

    if config.xai_api_key:
        by_provider["xai-responses"] = {
            "provider": "xai-responses",
            "mode": "xai-responses",
            "api_url": config.xai_api_url,
            "api_key": config.xai_api_key,
            "model": model_override or config.xai_model,
            "tools": config.parse_xai_tools(),
            "source": "XAI_*",
        }

    if config.openai_compatible_api_url and config.openai_compatible_api_key:
        by_provider["openai-compatible"] = {
            "provider": "openai-compatible",
            "mode": "chat-completions",
            "api_url": config.openai_compatible_api_url,
            "api_key": config.openai_compatible_api_key,
            "model": model_override or config.openai_compatible_model,
            "stream": config.openai_compatible_stream,
            "tools": [],
            "source": "OPENAI_COMPATIBLE_*",
        }

    return [
        by_provider[provider]
        for provider in _effective_main_search_chain()
        if provider in by_provider and _provider_allowed(provider, provider_filter)
    ]


def _main_search_providers(provider_configs: list[dict[str, Any]], fallback: str) -> list[Any]:
    selected = provider_configs if fallback != "off" else provider_configs[:1]
    providers: list[Any] = []
    for provider_config in selected:
        if provider_config["provider"] == "xai-responses":
            providers.append(
                XAIResponsesSearchProvider(
                    provider_config["api_url"],
                    provider_config["api_key"],
                    provider_config["model"],
                    provider_config.get("tools", []),
                )
            )
        else:
            providers.append(
                OpenAICompatibleSearchProvider(
                    provider_config["api_url"],
                    provider_config["api_key"],
                    provider_config["model"],
                    provider_config.get("stream", False),
                )
            )
    return providers


async def fetch_available_models(api_url: str, api_key: str) -> list[str]:
    models_url = f"{api_url.rstrip('/')}/models"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            models_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()

    models: list[str] = []
    for item in (data or {}).get("data", []) or []:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            models.append(item["id"])
    return models


async def get_available_models_cached(api_url: str, api_key: str) -> list[str]:
    key = (api_url, api_key)
    async with _AVAILABLE_MODELS_LOCK:
        if key in _AVAILABLE_MODELS_CACHE:
            return _AVAILABLE_MODELS_CACHE[key]

    try:
        models = await fetch_available_models(api_url, api_key)
    except Exception:
        models = []

    async with _AVAILABLE_MODELS_LOCK:
        _AVAILABLE_MODELS_CACHE[key] = models
    return models


def extra_results_to_sources(
    tavily_results: list[dict] | None,
    firecrawl_results: list[dict] | None,
) -> list[dict]:
    sources: list[dict] = []
    seen: set[str] = set()

    if firecrawl_results:
        for r in firecrawl_results:
            url = (r.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            item: dict = {"url": url, "provider": "firecrawl"}
            title = (r.get("title") or "").strip()
            if title:
                item["title"] = title
            desc = (r.get("description") or "").strip()
            if desc:
                item["description"] = desc
            sources.append(item)

    if tavily_results:
        for r in tavily_results:
            url = (r.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            item = {"url": url, "provider": "tavily"}
            title = (r.get("title") or "").strip()
            if title:
                item["title"] = title
            content = (r.get("content") or "").strip()
            if content:
                item["description"] = content
            sources.append(item)

    return sources


async def _run_web_fetch_fallback(
    url: str,
    fallback: str = "auto",
    preferred_order: list[str] | None = None,
) -> tuple[dict[str, Any] | None, list[dict]]:
    return await _run_web_fetch_fallback_impl(url, fallback=fallback, preferred_order=preferred_order)




async def _run_web_search_fallback(
    query: str,
    count: int = 5,
    providers: str = "auto",
    fallback: str = "auto",
) -> tuple[list[dict], list[dict]]:
    return await _run_web_search_fallback_impl(query, count=count, providers=providers, fallback=fallback)


async def _run_bilingual_web_search(
    query: str,
    count: int = 5,
    providers: str = "auto",
    fallback: str = "auto",
    locale_scope: str = "both",
) -> tuple[list[dict], list[dict]]:
    return await _run_bilingual_web_search_impl(
        query,
        count=count,
        providers=providers,
        fallback=fallback,
        locale_scope=locale_scope,
    )


async def _run_docs_search_fallback(
    query: str,
    providers: str = "auto",
    fallback: str = "auto",
) -> tuple[list[dict], list[dict]]:
    return await _run_docs_search_fallback_impl(query, providers=providers, fallback=fallback)


async def call_tavily_search(query: str, max_results: int = 6) -> list[dict] | None:
    return await _call_tavily_search_impl(query, max_results=max_results)


async def call_firecrawl_search(query: str, limit: int = 14) -> list[dict] | None:
    return await _call_firecrawl_search_impl(query, limit=limit)


async def call_tavily_extract(url: str) -> str | None:
    return await _call_tavily_extract_impl(url)


async def call_firecrawl_scrape(url: str, ctx=None) -> str | None:
    return await _call_firecrawl_scrape_impl(url, ctx=ctx)


async def call_jina_reader(url: str) -> dict[str, Any]:
    return await _call_jina_reader_impl(url)


async def call_tavily_map(
    url: str,
    instructions: str = "",
    max_depth: int = 1,
    max_breadth: int = 20,
    limit: int = 50,
    timeout: int = 150,
) -> dict[str, Any]:
    return await _call_tavily_map_impl(
        url,
        instructions=instructions,
        max_depth=max_depth,
        max_breadth=max_breadth,
        limit=limit,
        timeout=timeout,
    )


async def search(
    query: str,
    platform: str = "",
    model: str = "",
    extra_sources: int = 0,
    validation: str = "",
    fallback: str = "",
    providers: str = "auto",
    stream: bool | None = None,
) -> dict[str, Any]:
    start = time.time()
    session_id = new_session_id()
    try:
        validation_level = (validation or config.validation_level).strip().lower()
        fallback_mode = (fallback or config.fallback_mode).strip().lower()
        if validation_level not in config._ALLOWED_VALIDATION_LEVELS:
            raise ValueError(f"Invalid validation level: {validation_level}")
        if fallback_mode not in config._ALLOWED_FALLBACK_MODES:
            raise ValueError(f"Invalid fallback mode: {fallback_mode}")
    except ValueError as e:
        return _empty_search_result(start, session_id, query, ErrorType.PARAMETER.value, str(e))

    minimum = validate_minimum_profile()
    if not minimum.get("ok"):
        return _empty_search_result(
            start,
            session_id,
            query,
            minimum.get("error_type", ErrorType.CONFIG.value),
            minimum.get("error", MINIMUM_PROFILE_ERROR),
            error_code=minimum.get("error_code") or MINIMUM_PROFILE,
            extra={
                "capability_status": minimum.get("capability_status", {}),
                "minimum_profile_ok": False,
                "validation_level": validation_level,
            },
        )

    try:
        main_provider_configs = _main_search_provider_configs(model_override=model, providers=providers)
    except ValueError as e:
        return _empty_search_result(start, session_id, query, ErrorType.PARAMETER.value, str(e), extra={"validation_level": validation_level})

    if not main_provider_configs:
        return _empty_search_result(
            start,
            session_id,
            query,
            ErrorType.CONFIG.value,
            "No configured main_search provider matches --providers.",
            error_code=MISSING_API_KEY,
            extra={
                "validation_level": validation_level,
                "capability_status": minimum.get("capability_status", {}),
                "minimum_profile_ok": minimum.get("ok", False),
            },
        )

    primary_api_mode = main_provider_configs[0]["mode"]
    if stream is not None:
        for provider_config in main_provider_configs:
            if provider_config["provider"] == "openai-compatible":
                provider_config["stream"] = stream

    has_tavily = bool(config.tavily_api_key)
    has_firecrawl = bool(config.firecrawl_api_key)
    tavily_count = 0
    firecrawl_count = 0
    if extra_sources > 0:
        if has_tavily and has_firecrawl:
            tavily_count = max(1, round(extra_sources * 0.6))
            firecrawl_count = extra_sources - tavily_count
        elif has_tavily:
            tavily_count = extra_sources
        elif has_firecrawl:
            firecrawl_count = extra_sources

    docs_intent = _is_docs_intent(query)
    zh_current_intent = _is_zh_current_intent(query)
    bilingual_web_search = True
    web_current_intent = zh_current_intent
    fetch_urls = _extract_urls(query)
    fetch_intent = bool(fetch_urls) or _is_fetch_intent(query)
    supplemental_paths: list[str] = []
    if docs_intent:
        supplemental_paths.append("docs_search")
    if bilingual_web_search:
        supplemental_paths.append("web_search")
    if fetch_intent:
        supplemental_paths.append("web_fetch")
    selected_main_provider_configs = main_provider_configs if fallback_mode != "off" else main_provider_configs[:1]
    routing_decision = {
        "docs_intent": docs_intent,
        "zh_current_intent": zh_current_intent,
        "web_current_intent": web_current_intent,
        "bilingual_web_search": bilingual_web_search,
        "bilingual_query_locales": [item["locale"] for item in _bilingual_search_queries(query)],
        "fetch_intent": fetch_intent,
        "supplemental_paths": supplemental_paths,
        "validation_level": validation_level,
        "fallback_mode": fallback_mode,
        "providers": providers,
        "main_search_chain": [item["provider"] for item in selected_main_provider_configs],
        "openai_compatible_stream": next((bool(item.get("stream")) for item in selected_main_provider_configs if item["provider"] == "openai-compatible"), False),
    }

    provider_attempts: list[dict] = []
    main_providers = _main_search_providers(main_provider_configs, fallback_mode)
    primary_start = time.time()
    primary_result = None
    successful_main_config: dict[str, Any] | None = None
    last_primary_error: dict[str, Any] | None = None
    for provider_config, search_provider in zip(selected_main_provider_configs, main_providers):
        primary_start = time.time()
        try:
            candidate_result = await search_provider.search(query, platform)
            if candidate_result:
                primary_result = candidate_result
                successful_main_config = provider_config
                provider_attempts.append(_attempt("main_search", search_provider.get_provider_name(), "ok", primary_start, result_count=1))
                break
            last_primary_error = _primary_search_error_result(
                start,
                session_id,
                query,
                provider_config["mode"],
                ErrorType.NETWORK.value,
                f"{search_provider.get_provider_name()} returned empty results",
                error_code=PROVIDER_EMPTY,
            )
            provider_attempts.append(_attempt("main_search", search_provider.get_provider_name(), "empty", primary_start))
        except Exception as e:
            error_result = _primary_search_exception_result(start, session_id, query, provider_config["mode"], search_provider.get_provider_name(), e)
            last_primary_error = error_result
            provider_attempts.append(
                _attempt(
                    "main_search",
                    search_provider.get_provider_name(),
                    "error",
                    primary_start,
                    error_type=error_result["error_type"],
                    error=error_result["error"],
                )
            )
    if primary_result is None:
        result = last_primary_error or _primary_search_error_result(
            start,
            session_id,
            query,
            primary_api_mode,
            ErrorType.NETWORK.value,
            "Search failed or returned no results",
            error_code=SEARCH_FAILED,
        )
        result["provider_attempts"] = provider_attempts
        result["providers_used"] = _provider_names_from_attempts(provider_attempts)
        result["fallback_used"] = _fallback_used(provider_attempts)
        result["routing_decision"] = routing_decision
        result["validation_level"] = validation_level
        result["minimum_profile_ok"] = minimum.get("ok", False)
        result["capability_status"] = minimum.get("capability_status", {})
        return result

    successful_main_config = successful_main_config or selected_main_provider_configs[0]
    primary_api_mode = successful_main_config["mode"]
    effective_model = successful_main_config["model"]

    coros: list[Any] = []
    if tavily_count:
        coros.append(call_tavily_search(query, tavily_count))
    if firecrawl_count:
        coros.append(call_firecrawl_search(query, firecrawl_count))

    gathered = await asyncio.gather(*coros, return_exceptions=True)
    primary_result = primary_result or ""
    tavily_results: list[dict] | None = None
    firecrawl_results: list[dict] | None = None
    idx = 0
    if tavily_count:
        tavily_results = None if isinstance(gathered[idx], BaseException) else gathered[idx]
        idx += 1
    if firecrawl_count:
        firecrawl_results = None if isinstance(gathered[idx], BaseException) else gathered[idx]

    answer, primary_sources = split_answer_and_sources(primary_result)
    extra_source_items = extra_results_to_sources(tavily_results, firecrawl_results)
    for item_provider, results in (("tavily", tavily_results), ("firecrawl", firecrawl_results)):
        if results:
            provider_attempts.append(_attempt("web_search", item_provider, "ok", start, result_count=len(results)))

    supplemental_sources: list[dict] = []
    if validation_level in {"balanced", "strict"}:
        if docs_intent:
            docs_sources, docs_attempts = await _run_docs_search_fallback(query, providers=providers, fallback=fallback_mode)
            provider_attempts.extend(docs_attempts)
            supplemental_sources.extend(docs_sources)
        if bilingual_web_search:
            web_sources, web_attempts = await _run_bilingual_web_search(query, count=max(1, extra_sources or 3), providers=providers, fallback=fallback_mode)
            provider_attempts.extend(web_attempts)
            supplemental_sources.extend(web_sources)
        if fetch_intent:
            fetch_url = fetch_urls[0] if fetch_urls else query.strip()
            fetch_result, fetch_attempts = await _run_web_fetch_fallback(fetch_url, fallback=fallback_mode)
            provider_attempts.extend(fetch_attempts)
            if fetch_result:
                supplemental_sources.append({"url": fetch_result["url"], "provider": fetch_result["provider"], "description": fetch_result["content"][:300]})

    extra_source_items = merge_sources(extra_source_items, supplemental_sources)
    sources = merge_sources(primary_sources, extra_source_items)
    ok = bool(answer or sources)
    if validation_level == "strict" and not sources:
        ok = False
    if ok:
        error_payload = {"error_type": "", "error_code": "", "error": ""}
    elif validation_level == "strict":
        error_payload = error_fields(
            ErrorType.EVIDENCE,
            error="Strict validation requires citable evidence sources",
            error_code=EVIDENCE_INSUFFICIENT,
        )
    else:
        error_payload = error_fields(
            ErrorType.NETWORK,
            error="Search failed or returned no results",
            error_code=SEARCH_FAILED,
        )
    return {
        "ok": ok,
        **error_payload,
        "session_id": session_id,
        "query": query,
        "platform": platform,
        "model": effective_model,
        "primary_api_mode": primary_api_mode,
        "content": answer,
        "sources": sources,
        "sources_count": len(sources),
        "primary_sources": primary_sources,
        "primary_sources_count": len(primary_sources),
        "extra_sources": extra_source_items,
        "extra_sources_count": len(extra_source_items),
        "source_warning": SOURCE_PROVENANCE_WARNING if extra_source_items else "",
        "routing_decision": routing_decision,
        "providers_used": _provider_names_from_attempts(provider_attempts),
        "provider_attempts": provider_attempts,
        "fallback_used": _fallback_used(provider_attempts),
        "validation_level": validation_level,
        "minimum_profile_ok": minimum.get("ok", False),
        "capability_status": minimum.get("capability_status", {}),
        "elapsed_ms": _elapsed_ms(start),
    }


def _primary_search_exception_result(
    start: float,
    session_id: str,
    query: str,
    primary_api_mode: str,
    provider_name: str,
    exc: BaseException,
) -> dict[str, Any]:
    if isinstance(exc, httpx.TimeoutException):
        return _primary_search_error_result(
            start,
            session_id,
            query,
            primary_api_mode,
            ErrorType.NETWORK.value,
            f"{provider_name} request timed out: {str(exc)}",
            error_code=PROVIDER_TIMEOUT,
        )
    if isinstance(exc, httpx.HTTPStatusError):
        body = exc.response.text[:300] if exc.response is not None else str(exc)
        status = exc.response.status_code if exc.response is not None else "unknown"
        return _primary_search_error_result(
            start,
            session_id,
            query,
            primary_api_mode,
            ErrorType.NETWORK.value,
            f"{provider_name} HTTP {status}: {body}",
            error_code=PROVIDER_NETWORK,
        )
    if isinstance(exc, httpx.RequestError):
        return _primary_search_error_result(
            start,
            session_id,
            query,
            primary_api_mode,
            ErrorType.NETWORK.value,
            f"{provider_name} network error: {str(exc)}",
            error_code=PROVIDER_NETWORK,
        )
    return _primary_search_error_result(
        start,
        session_id,
        query,
        primary_api_mode,
        ErrorType.RUNTIME.value,
        f"{provider_name} runtime error: {str(exc)}",
        error_code=PROVIDER_RUNTIME,
    )


def _primary_search_error_result(
    start: float,
    session_id: str,
    query: str,
    primary_api_mode: str,
    error_type: str,
    error: str,
    error_code: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        **error_fields(error_type, error=error, error_code=error_code),
        "session_id": session_id,
        "query": query,
        "primary_api_mode": primary_api_mode,
        "content": "",
        "sources": [],
        "sources_count": 0,
        "primary_sources": [],
        "primary_sources_count": 0,
        "extra_sources": [],
        "extra_sources_count": 0,
        "source_warning": "",
        "elapsed_ms": _elapsed_ms(start),
    }


async def fetch(url: str) -> dict[str, Any]:
    start = time.time()
    fetch_result, attempts = await _run_web_fetch_fallback(url)
    if fetch_result:
        return {
            **fetch_result,
            "provider_attempts": attempts,
            "fallback_used": _fallback_used(attempts),
            "elapsed_ms": _elapsed_ms(start),
        }

    if not (config.tavily_api_key or config.jina_api_key or config.firecrawl_api_key):
        fields = error_fields(
            ErrorType.CONFIG,
            error="TAVILY_API_KEY, JINA_API_KEY, and FIRECRAWL_API_KEY are not configured",
            error_code=MISSING_API_KEY,
        )
    else:
        fields = error_fields(
            ErrorType.NETWORK,
            error="All extract providers failed to fetch content",
            error_code=FETCH_FAILED,
        )
    return {
        "ok": False,
        "url": url,
        "provider": "",
        "content": "",
        **fields,
        "provider_attempts": attempts,
        "fallback_used": _fallback_used(attempts),
        "elapsed_ms": _elapsed_ms(start),
    }


async def map_site(
    url: str,
    instructions: str = "",
    max_depth: int = 1,
    max_breadth: int = 20,
    limit: int = 50,
    timeout: int = 150,
) -> dict[str, Any]:
    start = time.time()
    result = await call_tavily_map(url, instructions, max_depth, max_breadth, limit, timeout)
    result.setdefault("url", url)
    result.setdefault("elapsed_ms", _elapsed_ms(start))
    return result


async def exa_search(
    query: str,
    num_results: int = 5,
    search_type: str = "neural",
    include_text: bool = False,
    include_highlights: bool = False,
    start_published_date: str = "",
    include_domains: str | list[str] | tuple[str, ...] = "",
    exclude_domains: str | list[str] | tuple[str, ...] = "",
    category: str = "",
) -> dict[str, Any]:
    api_key = config.exa_api_key
    if not api_key:
        return {
            "ok": False,
            **error_fields(ErrorType.CONFIG, error=missing_api_key_message("EXA_API_KEY"), error_code=MISSING_API_KEY),
        }

    provider = ExaSearchProvider(config.exa_base_url, api_key, config.exa_timeout)
    include_domain_list = _normalize_domain_filter(include_domains)
    exclude_domain_list = _normalize_domain_filter(exclude_domains)

    raw = await provider.search(
        query=query,
        num_results=num_results,
        search_type=search_type,
        include_text=include_text,
        include_highlights=include_highlights,
        start_published_date=start_published_date or None,
        include_domains=include_domain_list,
        exclude_domains=exclude_domain_list,
        category=category or None,
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, **error_fields(ErrorType.PARSE, error=raw, error_code=PARSE_FAILED)}
    if not data.get("ok", False):
        data.setdefault("error_type", ErrorType.NETWORK.value)
        attach_error_fields(data)
    return data


async def _decode_provider_json(raw: str, provider: str = "jina") -> dict[str, Any]:
    return _decode_provider_json_impl(raw, provider=provider)


async def jina_fetch(url: str) -> dict[str, Any]:
    return await _jina_fetch_impl(url)




async def exa_find_similar(url: str, num_results: int = 5) -> dict[str, Any]:
    api_key = config.exa_api_key
    if not api_key:
        return {
            "ok": False,
            **error_fields(ErrorType.CONFIG, error=missing_api_key_message("EXA_API_KEY"), error_code=MISSING_API_KEY),
        }

    provider = ExaSearchProvider(config.exa_base_url, api_key, config.exa_timeout)
    raw = await provider.find_similar(url=url, num_results=num_results)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, **error_fields(ErrorType.PARSE, error=raw, error_code=PARSE_FAILED)}
    if not data.get("ok", False):
        data.setdefault("error_type", ErrorType.NETWORK.value)
        attach_error_fields(data)
    return data


async def context7_library(name: str, query: str = "") -> dict[str, Any]:
    api_key = config.context7_api_key
    if not api_key:
        return {
            "ok": False,
            **error_fields(ErrorType.CONFIG, error=missing_api_key_message("CONTEXT7_API_KEY"), error_code=MISSING_API_KEY),
        }
    provider = Context7Provider(config.context7_base_url, api_key, config.context7_timeout)
    raw = await provider.library(name, query)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, **error_fields(ErrorType.PARSE, error=raw, error_code=PARSE_FAILED)}
    if not data.get("ok", False):
        data.setdefault("error_type", ErrorType.NETWORK.value)
        attach_error_fields(data)
    return data


async def context7_docs(library_id: str, query: str) -> dict[str, Any]:
    api_key = config.context7_api_key
    if not api_key:
        return {
            "ok": False,
            **error_fields(ErrorType.CONFIG, error=missing_api_key_message("CONTEXT7_API_KEY"), error_code=MISSING_API_KEY),
        }
    provider = Context7Provider(config.context7_base_url, api_key, config.context7_timeout)
    raw = await provider.docs(library_id, query)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, **error_fields(ErrorType.PARSE, error=raw, error_code=PARSE_FAILED)}
    if not data.get("ok", False):
        data.setdefault("error_type", ErrorType.NETWORK.value)
        attach_error_fields(data)
    return data


async def _test_primary_chat_completion(api_url: str, api_key: str, model: str) -> dict[str, Any]:
    return await _test_primary_chat_completion_impl(api_url, api_key, model)


async def diagnose_openai_compatible(timeout_seconds: float = 30.0) -> dict[str, Any]:
    return await _diagnose_openai_compatible_impl(timeout_seconds=timeout_seconds)


async def _probe_openai_compatible_search_shape(
    api_url: str,
    api_key: str,
    model: str,
    *,
    stream: bool,
    timeout_seconds: float,
) -> dict[str, Any]:
    return await _probe_openai_compatible_search_shape_impl(
        api_url, api_key, model, stream=stream, timeout_seconds=timeout_seconds
    )


async def diagnose_xai(timeout_seconds: float = 30.0) -> dict[str, Any]:
    return await _diagnose_xai_impl(timeout_seconds=timeout_seconds)


async def _probe_xai_search_shape(api_url: str, api_key: str, model: str, tools: list[str], timeout_seconds: float) -> dict[str, Any]:
    return await _probe_xai_search_shape_impl(api_url, api_key, model, tools, timeout_seconds)


async def _test_primary_connection(api_url: str, api_key: str, model: str) -> dict[str, Any]:
    return await _test_primary_connection_impl(api_url, api_key, model)


async def _test_primary_responses(api_url: str, api_key: str, model: str) -> dict[str, Any]:
    return await _test_primary_responses_impl(api_url, api_key, model)


async def _test_main_provider_connection(provider_config: dict[str, Any]) -> dict[str, Any]:
    return await _test_main_provider_connection_impl(provider_config)


async def _safe_test_main_provider_connection(provider_config: dict[str, Any]) -> dict[str, Any]:
    return await _safe_test_main_provider_connection_impl(provider_config)


async def _test_exa_connection() -> dict[str, Any]:
    return await _test_exa_connection_impl()


async def _test_tavily_connection() -> dict[str, Any]:
    return await _test_tavily_connection_impl()


async def _test_jina_connection() -> dict[str, Any]:
    return await _test_jina_connection_impl()


async def _test_context7_connection() -> dict[str, Any]:
    return await _test_context7_connection_impl()


async def doctor() -> dict[str, Any]:
    return await _doctor_impl()


def config_path() -> dict[str, Any]:
    return config.config_path_info()


def config_list(show_secrets: bool = False) -> dict[str, Any]:
    return {
        "ok": True,
        "config_file": str(config.config_file),
        "values": config.get_saved_config(masked=not show_secrets),
    }


def config_set(key: str, value: str) -> dict[str, Any]:
    try:
        config.set_config_value(key, value)
    except ValueError as e:
        return {"ok": False, **error_fields(ErrorType.PARAMETER, error=str(e)), "config_file": str(config.config_file)}
    saved = config.get_saved_config(masked=True)
    return {
        "ok": True,
        "config_file": str(config.config_file),
        "key": key.strip().upper(),
        "value": saved.get(key.strip().upper(), ""),
    }


def config_unset(key: str) -> dict[str, Any]:
    try:
        config.unset_config_value(key)
    except ValueError as e:
        return {"ok": False, **error_fields(ErrorType.PARAMETER, error=str(e)), "config_file": str(config.config_file), "key": key.strip().upper()}
    return {"ok": True, "config_file": str(config.config_file), "key": key.strip().upper()}


def write_output(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
