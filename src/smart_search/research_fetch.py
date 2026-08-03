"""HTTP fetch / extract / map helpers for web content providers.

Monkeypatch points (tests typically patch ``smart_search.service``):
- ``service.call_tavily_extract`` / ``call_firecrawl_scrape`` / ``jina_fetch``
- ``service.call_tavily_search`` / ``call_firecrawl_search`` / ``call_tavily_map``
- ``service._run_web_fetch_fallback`` (facade used by research_runtime)
- ``service.httpx.AsyncClient`` (shared ``httpx`` module attribute)

Implementations live here; ``service`` re-exports thin shims so patches on
``service.<name>`` remain effective when callers go through ``_service()``.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from .config import config
from .errors import (
    ErrorType,
    MAP_ERROR,
    MAP_HTTP_ERROR,
    MAP_TIMEOUT,
    MISSING_API_KEY,
    PARSE_FAILED,
    error_fields,
    missing_api_key_message,
)
from .logger import log_info


def _service():
    from . import service as svc

    return svc


def decode_provider_json(raw: str, provider: str = "jina") -> dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "provider": provider,
            **error_fields(ErrorType.PARSE, error=raw, error_code=PARSE_FAILED),
        }


async def run_web_fetch_fallback(
    url: str,
    fallback: str = "auto",
    preferred_order: list[str] | None = None,
) -> tuple[dict[str, Any] | None, list[dict]]:
    attempts: list[dict] = []
    providers = []
    if config.tavily_api_key:
        providers.append("tavily")
    if config.jina_api_key:
        providers.append("jina")
    if config.firecrawl_api_key:
        providers.append("firecrawl")
    if preferred_order:
        allowed = {provider for provider in providers}
        ordered = [provider for provider in preferred_order if provider in allowed]
        ordered.extend(provider for provider in providers if provider not in ordered)
        providers = ordered
    if fallback == "off":
        providers = providers[:1]

    for provider in providers:
        start = time.time()
        try:
            if provider == "tavily":
                content = await _service().call_tavily_extract(url)
            elif provider == "jina":
                data = await _service().jina_fetch(url)
                content = data.get("content") if data.get("ok") else None
                if not data.get("ok"):
                    status = (
                        "error"
                        if data.get("error_type")
                        in {
                            "auth_error",
                            "config_error",
                            "parameter_error",
                            "quality_error",
                            "rate_limited",
                            "timeout",
                            "network_error",
                            "runtime_error",
                        }
                        else "empty"
                    )
                    attempts.append(
                        _service()._attempt(
                            "web_fetch",
                            provider,
                            status,
                            start,
                            error_type=data.get("error_type", ""),
                            error=data.get("error", ""),
                        )
                    )
                    continue
            else:
                content = await _service().call_firecrawl_scrape(url)
            if content and content.strip():
                attempts.append(_service()._attempt("web_fetch", provider, "ok", start, result_count=1))
                return {
                    "ok": True,
                    "url": url,
                    "provider": provider,
                    "content": content,
                }, attempts
            attempts.append(_service()._attempt("web_fetch", provider, "empty", start))
        except Exception as e:
            attempts.append(
                _service()._attempt(
                    "web_fetch",
                    provider,
                    "error",
                    start,
                    error_type="runtime_error",
                    error=str(e),
                )
            )
    return None, attempts


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
        async with httpx.AsyncClient(timeout=config.tavily_timeout) as client:
            response = await client.post(endpoint, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            return (
                [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "content": r.get("content", ""),
                        "score": r.get("score", 0),
                    }
                    for r in results
                ]
                if results
                else None
            )
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
            return (
                [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "description": r.get("description", ""),
                    }
                    for r in results
                ]
                if results
                else None
            )
    except Exception:
        return None


async def call_tavily_extract(url: str) -> str | None:
    api_key = config.tavily_api_key
    if not api_key:
        return None
    endpoint = f"{config.tavily_api_url.rstrip('/')}/extract"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"urls": [url], "format": "markdown"}
    try:
        async with httpx.AsyncClient(timeout=config.tavily_timeout) as client:
            response = await client.post(endpoint, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
            if data.get("results") and len(data["results"]) > 0:
                content = data["results"][0].get("raw_content", "")
                return content if content and content.strip() else None
            return None
    except Exception:
        return None


async def call_firecrawl_scrape(url: str, ctx=None) -> str | None:
    api_key = config.firecrawl_api_key
    if not api_key:
        return None
    endpoint = f"{config.firecrawl_api_url.rstrip('/')}/scrape"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    for attempt in range(config.retry_max_attempts):
        body = {
            "url": url,
            "formats": ["markdown"],
            "timeout": 60000,
            "waitFor": (attempt + 1) * 1500,
        }
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(endpoint, headers=headers, json=body)
                response.raise_for_status()
                data = response.json()
                markdown = data.get("data", {}).get("markdown", "")
                if markdown and markdown.strip():
                    return markdown
                await log_info(
                    ctx,
                    f"Firecrawl: markdown为空, 重试 {attempt + 1}/{config.retry_max_attempts}",
                    config.debug_enabled,
                )
        except Exception as e:
            await log_info(ctx, f"Firecrawl error: {e}", config.debug_enabled)
            return None
    return None


async def call_jina_reader(url: str) -> dict[str, Any]:
    # Resolve provider via service so tests can monkeypatch service.JinaReaderProvider.
    raw = await _service().JinaReaderProvider(
        config.jina_reader_api_url,
        config.jina_api_key,
        config.jina_respond_with,
        config.jina_timeout,
    ).fetch(url)
    return await _service()._decode_provider_json(raw, provider="jina")


async def jina_fetch(url: str) -> dict[str, Any]:
    return await call_jina_reader(url)


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
            **error_fields(ErrorType.CONFIG, error=missing_api_key_message("TAVILY_API_KEY"), error_code=MISSING_API_KEY),
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
        return {
            "ok": False,
            **error_fields(
                ErrorType.NETWORK,
                error=f"Map request timed out after {timeout} seconds",
                error_code=MAP_TIMEOUT,
            ),
        }
    except httpx.HTTPStatusError as e:
        return {
            "ok": False,
            **error_fields(
                ErrorType.NETWORK,
                error=f"Map HTTP error: {e.response.status_code} - {e.response.text[:200]}",
                error_code=MAP_HTTP_ERROR,
            ),
        }
    except Exception as e:
        return {
            "ok": False,
            **error_fields(ErrorType.NETWORK, error=f"Map request failed: {str(e)}", error_code=MAP_ERROR),
        }
