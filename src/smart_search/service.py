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
from .logger import log_info
from .providers.context7 import Context7Provider
from .providers.exa import ExaSearchProvider
from .providers.jina import JinaReaderProvider
from .providers.openai_compatible import OpenAICompatibleSearchProvider, get_local_time_info
from .providers.zhipu import ZhipuWebSearchProvider
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
    OPENAI_COMPATIBLE_DIAGNOSE_COMMAND,
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
    call_jina_reader as _call_jina_reader_impl,
    call_tavily_extract as _call_tavily_extract_impl,
    jina_fetch as _jina_fetch_impl,
    run_web_fetch_fallback as _run_web_fetch_fallback_impl,
)
from .research_discovery import (
    run_bilingual_web_search as _run_bilingual_web_search_impl,
    run_docs_search_fallback as _run_docs_search_fallback_impl,
    run_web_search_fallback as _run_web_search_fallback_impl,
)
from .sources import merge_sources, new_session_id, split_answer_and_sources
from .utils import search_prompt


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
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "ok": False,
        "error_type": error_type,
        "error": error,
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
) -> dict[str, Any]:
    return {
        "capability": capability,
        "provider": provider,
        "status": status,
        "error_type": error_type,
        "error": error,
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
    status = {
        "main_search": {
            "configured": main_configured,
            "fallback_chain": MAIN_SEARCH_FALLBACK_CHAIN,
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
            "deprecated_configured": ["zhipu"] if config.zhipu_api_key else [],
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
    return {
        "ok": not missing,
        "error_type": "config_error" if missing else "",
        "error": f"{MINIMUM_PROFILE_ERROR} 缺失能力: {', '.join(missing)}" if missing else "",
        "profile": profile,
        "required": required,
        "missing": missing,
        "capability_status": capability_status,
    }


def validate_minimum_profile() -> dict[str, Any]:
    try:
        profile = config.minimum_profile
    except ValueError as e:
        return {"ok": False, "error_type": "parameter_error", "error": str(e), "missing": []}
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


def _configured_main_search_provider_ids() -> list[str]:
    configured: set[str] = set()

    if config.openai_compatible_api_url and config.openai_compatible_api_key:
        configured.add("openai-compatible")

    return [provider for provider in MAIN_SEARCH_FALLBACK_CHAIN if provider in configured]


def _main_search_provider_configs(model_override: str = "", providers: str = "auto") -> list[dict[str, Any]]:
    provider_filter = _parse_provider_filter(providers)
    by_provider: dict[str, dict[str, Any]] = {}

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
        for provider in MAIN_SEARCH_FALLBACK_CHAIN
        if provider in by_provider and _provider_allowed(provider, provider_filter)
    ]


def _main_search_providers(provider_configs: list[dict[str, Any]], fallback: str) -> list[Any]:
    selected = provider_configs if fallback != "off" else provider_configs[:1]
    providers: list[Any] = []
    for provider_config in selected:
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
    api_key = config.tavily_api_key
    if not api_key:
        return None
    endpoint = f"{config.tavily_api_url.rstrip('/')}/search"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",
        "include_raw_content": False,
        "include_answer": False,
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(endpoint, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                    "score": r.get("score", 0),
                }
                for r in results
            ] if results else None
    except Exception:
        return None


async def call_firecrawl_search(query: str, limit: int = 14) -> list[dict] | None:
    api_key = config.firecrawl_api_key
    if not api_key:
        return None
    endpoint = f"{config.firecrawl_api_url.rstrip('/')}/search"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"query": query, "limit": limit}
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(endpoint, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
            results = data.get("data", {}).get("web", [])
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "description": r.get("description", ""),
                }
                for r in results
            ] if results else None
    except Exception:
        return None


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
    api_key = config.tavily_api_key
    if not api_key:
        return {
            "ok": False,
            "error_type": "config_error",
            "error": "TAVILY_API_KEY 未配置。请运行 `smart-search setup`，或使用 `smart-search config set TAVILY_API_KEY <key>`。",
        }

    endpoint = f"{config.tavily_api_url.rstrip('/')}/map"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"url": url, "max_depth": max_depth, "max_breadth": max_breadth, "limit": limit, "timeout": timeout}
    if instructions:
        body["instructions"] = instructions
    try:
        async with httpx.AsyncClient(timeout=float(timeout + 10)) as client:
            response = await client.post(endpoint, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
            return {
                "ok": True,
                "base_url": data.get("base_url", ""),
                "results": data.get("results", []),
                "response_time": data.get("response_time", 0),
            }
    except httpx.TimeoutException:
        return {"ok": False, "error_type": "network_error", "error": f"映射超时: 请求超过{timeout}秒"}
    except httpx.HTTPStatusError as e:
        return {"ok": False, "error_type": "network_error", "error": f"HTTP错误: {e.response.status_code} - {e.response.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error_type": "network_error", "error": f"映射错误: {str(e)}"}


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
        return _empty_search_result(start, session_id, query, "parameter_error", str(e))

    minimum = validate_minimum_profile()
    if not minimum.get("ok"):
        return _empty_search_result(
            start,
            session_id,
            query,
            minimum.get("error_type", "config_error"),
            minimum.get("error", MINIMUM_PROFILE_ERROR),
            extra={
                "capability_status": minimum.get("capability_status", {}),
                "minimum_profile_ok": False,
                "validation_level": validation_level,
            },
        )

    try:
        main_provider_configs = _main_search_provider_configs(model_override=model, providers=providers)
    except ValueError as e:
        return _empty_search_result(start, session_id, query, "parameter_error", str(e), extra={"validation_level": validation_level})

    if not main_provider_configs:
        return _empty_search_result(
            start,
            session_id,
            query,
            "config_error",
            "No configured main_search provider matches --providers.",
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
                "network_error",
                f"{search_provider.get_provider_name()} 返回空结果",
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
        result = last_primary_error or _primary_search_error_result(start, session_id, query, primary_api_mode, "network_error", "搜索失败或无结果")
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
    return {
        "ok": ok,
        "error_type": "" if ok else ("evidence_error" if validation_level == "strict" else "network_error"),
        "error": "" if ok else ("strict 模式证据不足" if validation_level == "strict" else "搜索失败或无结果"),
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
            "network_error",
            f"{provider_name} 请求超时: {str(exc)}",
        )
    if isinstance(exc, httpx.HTTPStatusError):
        body = exc.response.text[:300] if exc.response is not None else str(exc)
        status = exc.response.status_code if exc.response is not None else "unknown"
        return _primary_search_error_result(
            start,
            session_id,
            query,
            primary_api_mode,
            "network_error",
            f"{provider_name} HTTP {status}: {body}",
        )
    if isinstance(exc, httpx.RequestError):
        return _primary_search_error_result(
            start,
            session_id,
            query,
            primary_api_mode,
            "network_error",
            f"{provider_name} 网络错误: {str(exc)}",
        )
    return _primary_search_error_result(
        start,
        session_id,
        query,
        primary_api_mode,
        "runtime_error",
        f"{provider_name} 运行错误: {str(exc)}",
    )


def _primary_search_error_result(
    start: float,
    session_id: str,
    query: str,
    primary_api_mode: str,
    error_type: str,
    error: str,
) -> dict[str, Any]:
    return {
        "ok": False,
        "error_type": error_type,
        "error": error,
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
        error = "TAVILY_API_KEY、JINA_API_KEY 和 FIRECRAWL_API_KEY 均未配置"
        error_type = "config_error"
    else:
        error = "所有提取服务均未能获取内容"
        error_type = "network_error"
    return {
        "ok": False,
        "url": url,
        "provider": "",
        "content": "",
        "error_type": error_type,
        "error": error,
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
            "error_type": "config_error",
            "error": "EXA_API_KEY 未配置。请运行 `smart-search setup`，或使用 `smart-search config set EXA_API_KEY <key>`。",
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
        return {"ok": False, "error_type": "parse_error", "error": raw}
    if not data.get("ok", False):
        data.setdefault("error_type", "network_error")
    return data


async def _decode_provider_json(raw: str, provider: str = "jina") -> dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "provider": provider, "error_type": "parse_error", "error": raw}


async def jina_fetch(url: str) -> dict[str, Any]:
    return await _jina_fetch_impl(url)




async def exa_find_similar(url: str, num_results: int = 5) -> dict[str, Any]:
    api_key = config.exa_api_key
    if not api_key:
        return {
            "ok": False,
            "error_type": "config_error",
            "error": "EXA_API_KEY 未配置。请运行 `smart-search setup`，或使用 `smart-search config set EXA_API_KEY <key>`。",
        }

    provider = ExaSearchProvider(config.exa_base_url, api_key, config.exa_timeout)
    raw = await provider.find_similar(url=url, num_results=num_results)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error_type": "parse_error", "error": raw}
    if not data.get("ok", False):
        data.setdefault("error_type", "network_error")
    return data


async def zhipu_search(
    query: str,
    count: int = 10,
    search_engine: str = "",
    search_recency_filter: str = "noLimit",
    search_domain_filter: str = "",
    content_size: str = "medium",
) -> dict[str, Any]:
    api_key = config.zhipu_api_key
    if not api_key:
        return {
            "ok": False,
            "error_type": "config_error",
            "error": "ZHIPU_API_KEY 未配置。请运行 `smart-search setup`，或使用 `smart-search config set ZHIPU_API_KEY <key>`。",
        }
    provider = ZhipuWebSearchProvider(
        config.zhipu_api_url,
        api_key,
        search_engine or config.zhipu_search_engine,
        config.zhipu_timeout,
    )
    raw = await provider.search(
        query=query,
        count=count,
        search_engine=search_engine or None,
        search_recency_filter=search_recency_filter,
        search_domain_filter=search_domain_filter,
        content_size=content_size,
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error_type": "parse_error", "error": raw}
    if not data.get("ok", False):
        data.setdefault("error_type", "network_error")
    return data


async def context7_library(name: str, query: str = "") -> dict[str, Any]:
    api_key = config.context7_api_key
    if not api_key:
        return {
            "ok": False,
            "error_type": "config_error",
            "error": "CONTEXT7_API_KEY 未配置。请运行 `smart-search setup`，或使用 `smart-search config set CONTEXT7_API_KEY <key>`。",
        }
    provider = Context7Provider(config.context7_base_url, api_key, config.context7_timeout)
    raw = await provider.library(name, query)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error_type": "parse_error", "error": raw}
    if not data.get("ok", False):
        data.setdefault("error_type", "network_error")
    return data


async def context7_docs(library_id: str, query: str) -> dict[str, Any]:
    api_key = config.context7_api_key
    if not api_key:
        return {
            "ok": False,
            "error_type": "config_error",
            "error": "CONTEXT7_API_KEY 未配置。请运行 `smart-search setup`，或使用 `smart-search config set CONTEXT7_API_KEY <key>`。",
        }
    provider = Context7Provider(config.context7_base_url, api_key, config.context7_timeout)
    raw = await provider.docs(library_id, query)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error_type": "parse_error", "error": raw}
    if not data.get("ok", False):
        data.setdefault("error_type", "network_error")
    return data


async def _test_primary_chat_completion(api_url: str, api_key: str, model: str) -> dict[str, Any]:
    chat_url = f"{api_url.rstrip('/')}/chat/completions"
    start = time.time()
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            chat_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
                "stream": False,
                "max_tokens": 8,
            },
        )
        response_time = _elapsed_ms(start)
        content_type = response.headers.get("content-type", "")
        if response.status_code != 200:
            return {
                "status": "warning",
                "message": f"HTTP {response.status_code}: {response.text[:100]}",
                "response_time_ms": response_time,
                "http_status": response.status_code,
                "content_type": content_type,
                "has_content": bool(response.text.strip()),
            }
        return {
            "status": "ok",
            "message": f"聊天接口可用 (HTTP {response.status_code})",
            "response_time_ms": response_time,
            "http_status": response.status_code,
            "content_type": content_type,
            "has_content": bool(response.text.strip()),
        }


def _diagnose_check_result(
    *,
    name: str,
    status: str,
    message: str,
    start: float,
    http_status: int | None = None,
    content_type: str = "",
    has_content: bool = False,
    stream: bool | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "status": status,
        "message": message,
        "response_time_ms": _elapsed_ms(start),
        "has_content": has_content,
    }
    if http_status is not None:
        result["http_status"] = http_status
    if content_type:
        result["content_type"] = content_type
    if stream is not None:
        result["stream"] = stream
    return result


def _openai_compatible_diagnosis(quick: dict[str, Any], no_stream: dict[str, Any], stream: dict[str, Any]) -> tuple[bool, str, str]:
    quick_ok = quick.get("status") == "ok"
    no_stream_ok = no_stream.get("status") == "ok"
    stream_ok = stream.get("status") == "ok"
    search_timeout = no_stream.get("status") == "timeout" or stream.get("status") == "timeout"

    if no_stream_ok and stream_ok:
        return (
            True,
            "OpenAI-compatible 主链路正常。",
            "真实 search 形态的 stream=false 和 stream=true 都能返回。若用户仍卡住，更可能是调用方、PATH、超时设置或上游偶发波动。",
        )
    if stream_ok and not no_stream_ok:
        return (
            False,
            "非流式请求不稳定，流式请求可用。",
            "建议设置 `OPENAI_COMPATIBLE_STREAM=true`，或临时使用 `smart-search search ... --stream`。",
        )
    if no_stream_ok and not stream_ok:
        return (
            False,
            "流式请求不稳定，非流式请求可用。",
            "建议设置 `OPENAI_COMPATIBLE_STREAM=false`，或临时使用 `smart-search search ... --no-stream`。",
        )
    if quick_ok and search_timeout:
        return (
            False,
            "小请求能通，但真实 search 形态超时。",
            "这通常是上游模型或中转站在处理 smart-search 的完整 prompt 时卡住；建议换模型/中转，或把本诊断报告贴给维护者。",
        )
    if quick_ok:
        return (
            False,
            "小请求能通，但真实 search 形态失败。",
            "这更像上游模型/中转站对 smart-search 请求形态不兼容；建议换模型/中转，或把本诊断报告贴给维护者。",
        )
    return (
        False,
        "OpenAI-compatible 基础请求不可用。",
        "请先检查 API URL、API key、模型名和网络；修好后再运行本诊断命令。",
    )


async def _probe_openai_compatible_search_shape(
    api_url: str,
    api_key: str,
    model: str,
    *,
    stream: bool,
    timeout_seconds: float,
) -> dict[str, Any]:
    name = "真实 search 请求 (stream=true)" if stream else "真实 search 请求 (stream=false)"
    start = time.time()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": search_prompt},
            {"role": "user", "content": get_local_time_info() + "\nping"},
        ],
        "stream": stream,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "smart-search/diagnose",
    }
    timeout = httpx.Timeout(connect=6.0, read=timeout_seconds, write=10.0, pool=None)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=config.ssl_verify_enabled) as client:
            if stream:
                async with client.stream(
                    "POST",
                    f"{api_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    content_type = response.headers.get("content-type", "")
                    response.raise_for_status()
                    has_content = False
                    async for line in response.aiter_lines():
                        stripped = line.strip()
                        if not stripped:
                            continue
                        if not stripped.startswith("data:"):
                            continue
                        if stripped in ("data: [DONE]", "data:[DONE]"):
                            continue
                        try:
                            data = json.loads(stripped[5:].lstrip())
                        except json.JSONDecodeError:
                            continue
                        choices = data.get("choices", []) if isinstance(data, dict) else []
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        if isinstance(delta, dict) and str(delta.get("content") or "").strip():
                            has_content = True
                            break
                        message = choices[0].get("message", {})
                        if isinstance(message, dict) and str(message.get("content") or "").strip():
                            has_content = True
                            break
                    status = "ok" if has_content else "empty"
                    message = f"HTTP {response.status_code}; {'收到流式内容' if has_content else '未收到内容'}"
                    return _diagnose_check_result(
                        name=name,
                        status=status,
                        message=message,
                        start=start,
                        http_status=response.status_code,
                        content_type=content_type,
                        has_content=has_content,
                        stream=stream,
                    )

            response = await client.post(
                f"{api_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            content_type = response.headers.get("content-type", "")
            response.raise_for_status()
            content = await OpenAICompatibleSearchProvider(api_url, api_key, model, stream=False)._parse_completion_response(response)
            has_content = bool(content.strip())
            status = "ok" if has_content else "empty"
            message = f"HTTP {response.status_code}; {'收到内容' if has_content else '返回为空'}"
            return _diagnose_check_result(
                name=name,
                status=status,
                message=message,
                start=start,
                http_status=response.status_code,
                content_type=content_type,
                has_content=has_content,
                stream=stream,
            )
    except httpx.TimeoutException as e:
        return _diagnose_check_result(name=name, status="timeout", message=f"请求超时: {e}", start=start, stream=stream)
    except httpx.HTTPStatusError as e:
        body = e.response.text[:200] if e.response is not None else str(e)
        status_code = e.response.status_code if e.response is not None else None
        content_type = e.response.headers.get("content-type", "") if e.response is not None else ""
        return _diagnose_check_result(
            name=name,
            status="warning",
            message=f"HTTP {status_code}: {body}",
            start=start,
            http_status=status_code,
            content_type=content_type,
            stream=stream,
        )
    except httpx.RequestError as e:
        return _diagnose_check_result(name=name, status="error", message=f"网络错误: {e}", start=start, stream=stream)
    except Exception as e:
        return _diagnose_check_result(name=name, status="error", message=f"运行错误: {e}", start=start, stream=stream)


async def diagnose_openai_compatible(timeout_seconds: float = 30.0) -> dict[str, Any]:
    start = time.time()
    api_url = config.openai_compatible_api_url
    api_key = config.openai_compatible_api_key
    model = config.openai_compatible_model
    info = config.config_path_info()
    result: dict[str, Any] = {
        "ok": False,
        "provider": "openai-compatible",
        "api_url": api_url or "未配置",
        "api_key": config._mask_api_key(api_key) if api_key else "未配置",
        "model": model,
        "configured_stream": config.openai_compatible_stream,
        "timeout_seconds": timeout_seconds,
        "config_file": info.get("config_file", ""),
        "config_dir_source": info.get("config_dir_source", ""),
        "checks": [],
        "next_command": OPENAI_COMPATIBLE_DIAGNOSE_COMMAND,
    }
    missing = []
    if not api_url:
        missing.append("OPENAI_COMPATIBLE_API_URL")
    if not api_key:
        missing.append("OPENAI_COMPATIBLE_API_KEY")
    if missing:
        result.update(
            {
                "error_type": "config_error",
                "error": "缺少 OpenAI-compatible 配置: " + ", ".join(missing),
                "summary": "OpenAI-compatible 配置不完整。",
                "recommendation": "请先运行 `smart-search setup`，或用 `smart-search config set` 填好缺失项。",
                "missing": missing,
                "elapsed_ms": _elapsed_ms(start),
            }
        )
        return result

    try:
        quick = await _test_primary_chat_completion(api_url, api_key, model)
    except httpx.TimeoutException as e:
        quick = {"status": "timeout", "message": f"轻量 chat 请求超时: {e}"}
    except httpx.RequestError as e:
        quick = {"status": "error", "message": f"轻量 chat 网络错误: {e}"}
    except Exception as e:
        quick = {"status": "error", "message": f"轻量 chat 运行错误: {e}"}
    quick_check = {
        "name": "轻量 chat 请求",
        "status": quick.get("status", "error"),
        "message": quick.get("message", ""),
        "response_time_ms": quick.get("response_time_ms"),
        "http_status": quick.get("http_status"),
        "content_type": quick.get("content_type", ""),
        "has_content": bool(quick.get("has_content", quick.get("status") == "ok")),
    }
    result["checks"].append(quick_check)
    no_stream = await _probe_openai_compatible_search_shape(api_url, api_key, model, stream=False, timeout_seconds=timeout_seconds)
    result["checks"].append(no_stream)
    stream = await _probe_openai_compatible_search_shape(api_url, api_key, model, stream=True, timeout_seconds=timeout_seconds)
    result["checks"].append(stream)

    ok, summary, recommendation = _openai_compatible_diagnosis(quick_check, no_stream, stream)
    result.update(
        {
            "ok": ok,
            "error_type": "" if ok else "network_error",
            "error": "" if ok else summary,
            "summary": summary,
            "recommendation": recommendation,
            "elapsed_ms": _elapsed_ms(start),
        }
    )
    return result


async def _test_primary_connection(api_url: str, api_key: str, model: str) -> dict[str, Any]:
    chat_test = await _test_primary_chat_completion(api_url, api_key, model)

    models_url = f"{api_url.rstrip('/')}/models"
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                models_url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            response_time = _elapsed_ms(start)
            if response.status_code != 200:
                models_test = {"status": "warning", "message": f"HTTP {response.status_code}: {response.text[:100]}", "response_time_ms": response_time}
            else:
                models_test = {"status": "ok", "message": f"成功获取模型列表 (HTTP {response.status_code})", "response_time_ms": response_time}
                try:
                    models_data = response.json()
                    model_names = [m["id"] for m in models_data.get("data", []) if isinstance(m, dict) and "id" in m]
                    models_test["message"] += f"，共 {len(model_names)} 个模型"
                    if model_names:
                        models_test["available_models"] = model_names
                except Exception:
                    pass
    except httpx.HTTPError as e:
        models_test = {"status": "warning", "message": f"模型列表接口请求失败: {e}", "response_time_ms": _elapsed_ms(start)}

    if chat_test.get("status") != "ok":
        models_state = "可用" if models_test.get("status") == "ok" else "不可用"
        return {
            "status": "warning",
            "message": f"聊天接口不可用: {chat_test.get('message', '')}；模型列表接口{models_state}: {models_test['message']}",
            "response_time_ms": chat_test.get("response_time_ms", models_test.get("response_time_ms")),
            "models_endpoint_test": models_test,
            "chat_completion_test": chat_test,
        }

    if models_test.get("status") != "ok":
        return {
            "status": "ok",
            "message": f"{chat_test['message']}；模型列表接口不可用: {models_test['message']}",
            "response_time_ms": chat_test.get("response_time_ms"),
            "models_endpoint_test": models_test,
            "chat_completion_test": chat_test,
        }

    result: dict[str, Any] = {
        "status": "ok",
        "message": f"{chat_test['message']}；{models_test['message']}",
        "response_time_ms": chat_test.get("response_time_ms"),
        "models_endpoint_test": models_test,
        "chat_completion_test": chat_test,
    }
    if "available_models" in models_test:
        result["available_models"] = models_test["available_models"]
    return result


async def _test_main_provider_connection(provider_config: dict[str, Any]) -> dict[str, Any]:
    return await _test_primary_connection(provider_config["api_url"], provider_config["api_key"], provider_config["model"])


async def _safe_test_main_provider_connection(provider_config: dict[str, Any]) -> dict[str, Any]:
    try:
        return await _test_main_provider_connection(provider_config)
    except httpx.TimeoutException:
        return {"status": "timeout", "message": f"{provider_config['provider']} 请求超时，请检查网络连接或 API URL"}
    except httpx.RequestError as e:
        return {"status": "error", "message": f"{provider_config['provider']} 网络错误: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": f"{provider_config['provider']} 未知错误: {str(e)}"}


async def _test_exa_connection() -> dict[str, Any]:
    exa_key = config.exa_api_key
    if not exa_key:
        return {"status": "not_configured", "message": "EXA_API_KEY 未设置，Exa 搜索功能不可用"}
    start = time.time()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{config.exa_base_url.rstrip('/')}/search",
            headers={"x-api-key": exa_key, "content-type": "application/json"},
            json={"query": "test", "numResults": 1, "type": "keyword"},
        )
        response_time = _elapsed_ms(start)
        if resp.status_code == 200:
            return {"status": "ok", "message": "Exa API 可用 (HTTP 200)", "response_time_ms": response_time}
        return {"status": "warning", "message": f"HTTP {resp.status_code}: {resp.text[:100]}", "response_time_ms": response_time}


async def _test_tavily_connection() -> dict[str, Any]:
    tavily_key = config.tavily_api_key
    if not tavily_key:
        return {"status": "not_configured", "message": "TAVILY_API_KEY 未设置，Tavily 功能不可用"}
    start = time.time()
    timeout = httpx.Timeout(connect=6.0, read=config.tavily_timeout, write=10.0, pool=None)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=config.ssl_verify_enabled) as client:
        resp = await client.post(
            f"{config.tavily_api_url.rstrip('/')}/search",
            headers={"Authorization": f"Bearer {tavily_key}", "Content-Type": "application/json"},
            json={"query": "test", "max_results": 1, "search_depth": "basic"},
        )
        response_time = _elapsed_ms(start)
        if resp.status_code == 200:
            return {"status": "ok", "message": "Tavily API 可用 (HTTP 200)", "response_time_ms": response_time}
        return {"status": "warning", "message": f"HTTP {resp.status_code}: {resp.text[:100]}", "response_time_ms": response_time}


async def _test_jina_connection() -> dict[str, Any]:
    if config.jina_respond_with and not config.jina_api_key:
        return {"status": "config_error", "message": "JINA_RESPOND_WITH requires JINA_API_KEY"}
    if not config.jina_api_key:
        return {"status": "not_configured", "message": "JINA_API_KEY 未设置，Jina 不满足 standard web_fetch；匿名 Reader 只能作为显式实验使用"}
    start = time.time()
    data = await jina_fetch("https://example.com")
    response_time = _elapsed_ms(start)
    if data.get("ok"):
        return {"status": "ok", "message": "Jina Reader 可用", "response_time_ms": response_time}
    error_type = data.get("error_type", "")
    status = error_type if error_type in {"auth_error", "config_error", "parameter_error", "rate_limited", "timeout"} else "warning"
    return {"status": status, "message": data.get("error", "Jina Reader 不可用"), "response_time_ms": response_time}


async def _test_zhipu_connection() -> dict[str, Any]:
    if not config.zhipu_api_key:
        return {"status": "not_configured", "message": "ZHIPU_API_KEY 未设置，智谱搜索功能不可用"}
    result = await zhipu_search("test", count=1)
    if result.get("ok"):
        return {"status": "ok", "message": "智谱 Web Search 可用", "response_time_ms": result.get("elapsed_ms", 0)}
    return {"status": "warning", "message": result.get("error", "智谱 Web Search 不可用"), "response_time_ms": result.get("elapsed_ms", 0)}


async def _test_context7_connection() -> dict[str, Any]:
    if not config.context7_api_key:
        return {"status": "not_configured", "message": "CONTEXT7_API_KEY 未设置，Context7 功能不可用"}
    result = await context7_library("react", "hooks")
    if result.get("ok"):
        return {"status": "ok", "message": "Context7 API 可用", "response_time_ms": result.get("elapsed_ms", 0)}
    return {"status": "warning", "message": result.get("error", "Context7 API 不可用"), "response_time_ms": result.get("elapsed_ms", 0)}


async def doctor() -> dict[str, Any]:
    info = config.get_config_info()

    main_provider_configs: list[dict[str, Any]] = []
    try:
        main_provider_configs = _main_search_provider_configs()
        info["main_search_connection_tests"] = {}
        for provider_config in main_provider_configs:
            info["main_search_connection_tests"][provider_config["provider"]] = await _safe_test_main_provider_connection(provider_config)
        if main_provider_configs:
            first_provider = main_provider_configs[0]
            info["primary_api_mode"] = first_provider["mode"]
            info["primary_connection_test"] = info["main_search_connection_tests"][first_provider["provider"]]
        else:
            info["primary_connection_test"] = {"status": "config_error", "message": MINIMUM_PROFILE_ERROR}
    except ValueError as e:
        info["main_search_connection_tests"] = {}
        info["primary_connection_test"] = {"status": "config_error", "message": str(e)}
    except Exception as e:
        info["main_search_connection_tests"] = {}
        info["primary_connection_test"] = {"status": "error", "message": f"未知错误: {str(e)}"}

    try:
        info["exa_connection_test"] = await _test_exa_connection()
    except httpx.TimeoutException:
        info["exa_connection_test"] = {"status": "timeout", "message": "Exa API 请求超时"}
    except Exception as e:
        info["exa_connection_test"] = {"status": "error", "message": str(e)}

    try:
        info["tavily_connection_test"] = await _test_tavily_connection()
    except httpx.TimeoutException:
        info["tavily_connection_test"] = {"status": "timeout", "message": "Tavily API 请求超时"}
    except Exception as e:
        info["tavily_connection_test"] = {"status": "error", "message": str(e)}

    try:
        info["jina_connection_test"] = await _test_jina_connection()
    except httpx.TimeoutException:
        info["jina_connection_test"] = {"status": "timeout", "message": "Jina Reader 请求超时"}
    except Exception as e:
        info["jina_connection_test"] = {"status": "error", "message": str(e)}

    if config.firecrawl_api_key:
        info["firecrawl_connection_test"] = {"status": "configured", "message": "FIRECRAWL_API_KEY 已设置"}
    else:
        info["firecrawl_connection_test"] = {"status": "not_configured", "message": "FIRECRAWL_API_KEY 未设置，Firecrawl 功能不可用"}

    try:
        info["zhipu_connection_test"] = await _test_zhipu_connection()
    except httpx.TimeoutException:
        info["zhipu_connection_test"] = {"status": "timeout", "message": "智谱 API 请求超时"}
    except Exception as e:
        info["zhipu_connection_test"] = {"status": "error", "message": str(e)}

    try:
        info["context7_connection_test"] = await _test_context7_connection()
    except httpx.TimeoutException:
        info["context7_connection_test"] = {"status": "timeout", "message": "Context7 API 请求超时"}
    except Exception as e:
        info["context7_connection_test"] = {"status": "error", "message": str(e)}

    minimum = validate_minimum_profile()
    info["capability_status"] = minimum.get("capability_status", get_capability_status())
    info["minimum_profile_ok"] = minimum.get("ok", False)
    info["minimum_profile_missing"] = minimum.get("missing", [])
    main_connection_tests = info.get("main_search_connection_tests") or {}
    main_search_statuses = [item.get("status") for item in main_connection_tests.values() if isinstance(item, dict)]
    primary_test = info.get("primary_connection_test", {})
    primary_status = primary_test.get("status")
    main_search_ok = any(status == "ok" for status in main_search_statuses) if main_connection_tests else primary_status == "ok"
    info["ok"] = main_search_ok and minimum.get("ok", False)
    if info["ok"]:
        info["error_type"] = ""
        info["error"] = ""
    elif info.get("config_parameter_errors"):
        info["error"] = "; ".join(info["config_parameter_errors"])
        info["error_type"] = "parameter_error"
    elif not minimum.get("ok", False):
        info["error"] = minimum.get("error", MINIMUM_PROFILE_ERROR)
        info["error_type"] = minimum.get("error_type", "config_error")
    else:
        info["error"] = primary_test.get("message", "Primary connection check failed")
        if primary_status == "config_error":
            info["error_type"] = "config_error"
        elif primary_status in {"timeout", "error", "warning"}:
            info["error_type"] = "network_error"
        else:
            info["error_type"] = "runtime_error"
    return info


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
        return {"ok": False, "error_type": "parameter_error", "error": str(e), "config_file": str(config.config_file)}
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
        return {"ok": False, "error_type": "parameter_error", "error": str(e), "config_file": str(config.config_file), "key": key.strip().upper()}
    return {"ok": True, "config_file": str(config.config_file), "key": key.strip().upper()}


def write_output(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
