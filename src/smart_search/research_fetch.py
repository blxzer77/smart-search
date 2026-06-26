import time
from typing import Any

import httpx

from .config import config
from .logger import log_info
def _service():
    from . import service as svc

    return svc


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


async def call_tavily_extract(url: str) -> str | None:
    api_key = config.tavily_api_key
    if not api_key:
        return None
    endpoint = f"{config.tavily_api_url.rstrip('/')}/extract"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"urls": [url], "format": "markdown"}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
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
    raw = await _service().JinaReaderProvider(
        config.jina_reader_api_url,
        config.jina_api_key,
        config.jina_respond_with,
        config.jina_timeout,
    ).fetch(url)
    return await _service()._decode_provider_json(raw, provider="jina")


async def jina_fetch(url: str) -> dict[str, Any]:
    return await call_jina_reader(url)