"""Diagnostics: doctor / diagnose probes for provider health.

Monkeypatch points (prefer ``smart_search.service`` so existing tests keep working):
- ``service.diagnose_openai_compatible`` / ``service.diagnose_xai`` / ``service.doctor``
- ``service._test_primary_chat_completion`` / ``service._probe_openai_compatible_search_shape``
- ``service._test_primary_responses`` / ``service._probe_xai_search_shape``
- ``service.httpx.AsyncClient`` (shared ``httpx`` module)

Implementations live here; ``service`` re-exports thin shims. Cross-calls that tests
patch on ``service`` go through ``_service()``.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from .config import config
from .errors import (
    ErrorType,
    MINIMUM_PROFILE,
    MISSING_API_KEY,
    error_fields,
)
from .providers.openai_compatible import OpenAICompatibleSearchProvider, get_local_time_info
from .research_keywords import (
    MINIMUM_PROFILE_ERROR,
    OPENAI_COMPATIBLE_DIAGNOSE_COMMAND,
    XAI_DIAGNOSE_COMMAND,
)
from .utils import search_prompt


def _service():
    from . import service as svc

    return svc


def _elapsed_ms(start: float) -> float:
    return round((time.time() - start) * 1000, 2)


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
            "message": f"Chat endpoint available (HTTP {response.status_code})",
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
            "OpenAI-compatible primary path is healthy.",
            "Both stream=false and stream=true search-shape requests returned content. If the user still hangs, prefer caller/PATH/timeout or intermittent upstream issues.",
        )
    if stream_ok and not no_stream_ok:
        return (
            False,
            "Non-stream requests are unstable; stream requests work.",
            "Set `OPENAI_COMPATIBLE_STREAM=true`, or temporarily use `smart-search search ... --stream`.",
        )
    if no_stream_ok and not stream_ok:
        return (
            False,
            "Stream requests are unstable; non-stream requests work.",
            "Set `OPENAI_COMPATIBLE_STREAM=false`, or temporarily use `smart-search search ... --no-stream`.",
        )
    if quick_ok and search_timeout:
        return (
            False,
            "Lightweight chat works, but real search-shape requests timed out.",
            "Upstream model/relay often hangs on the full smart-search prompt; switch model/relay or share this diagnose report with maintainers.",
        )
    if quick_ok:
        return (
            False,
            "Lightweight chat works, but real search-shape requests failed.",
            "Upstream model/relay likely rejects the smart-search request shape; switch model/relay or share this diagnose report with maintainers.",
        )
    return (
        False,
        "OpenAI-compatible base requests are unavailable.",
        "Check API URL, API key, model name, and network; then re-run this diagnose command.",
    )


async def _probe_openai_compatible_search_shape(
    api_url: str,
    api_key: str,
    model: str,
    *,
    stream: bool,
    timeout_seconds: float,
) -> dict[str, Any]:
    name = "real search-shape request (stream=true)" if stream else "real search-shape request (stream=false)"
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
                    message = f"HTTP {response.status_code}; {'received stream content' if has_content else 'no content received'}"
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
            message = f"HTTP {response.status_code}; {'received content' if has_content else 'empty response'}"
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
        return _diagnose_check_result(name=name, status="timeout", message=f"Request timed out: {e}", start=start, stream=stream)
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
            has_content=False,
            stream=stream,
        )
    except httpx.RequestError as e:
        return _diagnose_check_result(name=name, status="error", message=f"Network error: {e}", start=start, stream=stream)
    except Exception as e:
        return _diagnose_check_result(name=name, status="error", message=f"Runtime error: {e}", start=start, stream=stream)


async def diagnose_openai_compatible(timeout_seconds: float = 30.0) -> dict[str, Any]:
    start = time.time()
    api_url = config.openai_compatible_api_url
    api_key = config.openai_compatible_api_key
    model = config.openai_compatible_model
    info = config.config_path_info()
    result: dict[str, Any] = {
        "ok": False,
        "provider": "openai-compatible",
        "api_url": api_url or "not configured",
        "api_key": config._mask_api_key(api_key) if api_key else "not configured",
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
                **error_fields(
                    ErrorType.CONFIG,
                    error="Missing OpenAI-compatible config: " + ", ".join(missing),
                    error_code=MISSING_API_KEY,
                ),
                "summary": "OpenAI-compatible configuration is incomplete.",
                "recommendation": "Run `smart-search setup`, or use `smart-search config set` to fill missing keys.",
                "missing": missing,
                "elapsed_ms": _elapsed_ms(start),
            }
        )
        return result

    try:
        quick = await _service()._test_primary_chat_completion(api_url, api_key, model)
    except httpx.TimeoutException as e:
        quick = {"status": "timeout", "message": f"Lightweight chat request timed out: {e}"}
    except httpx.RequestError as e:
        quick = {"status": "error", "message": f"Lightweight chat network error: {e}"}
    except Exception as e:
        quick = {"status": "error", "message": f"Lightweight chat runtime error: {e}"}
    quick_check = {
        "name": "Lightweight chat request",
        "status": quick.get("status", "error"),
        "message": quick.get("message", ""),
        "response_time_ms": quick.get("response_time_ms"),
        "http_status": quick.get("http_status"),
        "content_type": quick.get("content_type", ""),
        "has_content": bool(quick.get("has_content", quick.get("status") == "ok")),
    }
    result["checks"].append(quick_check)
    no_stream = await _service()._probe_openai_compatible_search_shape(api_url, api_key, model, stream=False, timeout_seconds=timeout_seconds)
    result["checks"].append(no_stream)
    stream = await _service()._probe_openai_compatible_search_shape(api_url, api_key, model, stream=True, timeout_seconds=timeout_seconds)
    result["checks"].append(stream)

    ok, summary, recommendation = _openai_compatible_diagnosis(quick_check, no_stream, stream)
    err = error_fields(None) if ok else error_fields(ErrorType.NETWORK, error=summary)
    result.update(
        {
            "ok": ok,
            **err,
            "summary": summary,
            "recommendation": recommendation,
            "elapsed_ms": _elapsed_ms(start),
        }
    )
    return result


async def _probe_xai_search_shape(api_url: str, api_key: str, model: str, tools: list[str], timeout_seconds: float) -> dict[str, Any]:
    start = time.time()
    payload = {
        "model": model,
        "instructions": search_prompt,
        "input": [{"role": "user", "content": get_local_time_info() + "\nReply with exactly: ok"}],
        "stream": False,
        "tools": [{"type": tool} for tool in tools],
    }
    check_name = "search-shape responses request (server-side tools)"
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                f"{api_url.rstrip('/')}/responses",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "application/json"},
                json=payload,
            )
        has_content = bool(response.text.strip())
        if response.status_code == 200:
            return _diagnose_check_result(
                name=check_name,
                status="ok" if has_content else "warning",
                message=f"HTTP {response.status_code}; {'received content' if has_content else 'empty response'}",
                start=start,
                http_status=response.status_code,
                content_type=response.headers.get("content-type", ""),
                has_content=has_content,
            )
        return _diagnose_check_result(
            name=check_name,
            status="error",
            message=f"HTTP {response.status_code}: {response.text[:100]}",
            start=start,
            http_status=response.status_code,
            content_type=response.headers.get("content-type", ""),
            has_content=has_content,
        )
    except httpx.TimeoutException as e:
        return _diagnose_check_result(name=check_name, status="timeout", message=f"Request timed out: {e}", start=start)
    except httpx.RequestError as e:
        return _diagnose_check_result(name=check_name, status="error", message=f"Network error: {e}", start=start)


def _xai_diagnosis(light_check: dict[str, Any], shape_check: dict[str, Any]) -> tuple[bool, str, str]:
    light_ok = light_check.get("status") == "ok"
    shape_ok = shape_check.get("status") == "ok"
    if light_ok and shape_ok:
        return True, "xAI Responses API config and server-side search tools are available.", ""
    if light_ok:
        return (
            False,
            "Lightweight responses works, but search-shape requests with web_search/x_search tools failed.",
            "Confirm XAI_MODEL supports server-side tools (web_search/x_search) and the account has access; set `smart-search config set XAI_MODEL <model>` then re-check.",
        )
    return (
        False,
        "xAI Responses API connection failed.",
        "Check XAI_API_URL and XAI_API_KEY plus network reachability; then re-run `smart-search diagnose xai --format markdown`.",
    )


async def diagnose_xai(timeout_seconds: float = 30.0) -> dict[str, Any]:
    start = time.time()
    api_url = config.xai_api_url
    api_key = config.xai_api_key
    model = config.xai_model
    info = config.config_path_info()
    result: dict[str, Any] = {
        "ok": False,
        "provider": "xai-responses",
        "api_url": api_url,
        "api_key": config._mask_api_key(api_key) if api_key else "not configured",
        "model": model,
        "timeout_seconds": timeout_seconds,
        "config_file": info.get("config_file", ""),
        "config_dir_source": info.get("config_dir_source", ""),
        "checks": [],
        "next_command": XAI_DIAGNOSE_COMMAND,
    }
    if not api_key:
        result.update(
            {
                **error_fields(
                    ErrorType.CONFIG,
                    error="Missing xAI config: XAI_API_KEY",
                    error_code=MISSING_API_KEY,
                ),
                "summary": "xAI configuration is incomplete.",
                "recommendation": "Run `smart-search setup`, or use `smart-search config set XAI_API_KEY <key>`.",
                "missing": ["XAI_API_KEY"],
                "elapsed_ms": _elapsed_ms(start),
            }
        )
        return result
    try:
        tools = config.parse_xai_tools()
    except ValueError as e:
        result.update(
            {
                **error_fields(ErrorType.CONFIG, error=str(e)),
                "summary": "Invalid XAI_TOOLS configuration.",
                "recommendation": "Restore defaults with `smart-search config set XAI_TOOLS web_search,x_search`, or use whitelist values.",
                "elapsed_ms": _elapsed_ms(start),
            }
        )
        return result
    result["tools"] = tools

    try:
        light = await _service()._test_primary_responses(api_url, api_key, model)
    except httpx.TimeoutException as e:
        light = {"status": "timeout", "message": f"Lightweight responses request timed out: {e}"}
    except httpx.RequestError as e:
        light = {"status": "error", "message": f"Lightweight responses network error: {e}"}
    except Exception as e:
        light = {"status": "error", "message": f"Lightweight responses runtime error: {e}"}
    light_check = {
        "name": "Lightweight responses request",
        "status": light.get("status", "error"),
        "message": light.get("message", ""),
        "response_time_ms": light.get("response_time_ms"),
        "has_content": bool(light.get("status") == "ok"),
    }
    result["checks"].append(light_check)

    shape_check = await _service()._probe_xai_search_shape(api_url, api_key, model, tools, timeout_seconds)
    result["checks"].append(shape_check)

    ok, summary, recommendation = _xai_diagnosis(light_check, shape_check)
    err = error_fields(None) if ok else error_fields(ErrorType.NETWORK, error=summary)
    result.update(
        {
            "ok": ok,
            **err,
            "summary": summary,
            "recommendation": recommendation,
            "elapsed_ms": _elapsed_ms(start),
        }
    )
    return result


async def _test_primary_connection(api_url: str, api_key: str, model: str) -> dict[str, Any]:
    chat_test = await _service()._test_primary_chat_completion(api_url, api_key, model)

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
                models_test = {"status": "ok", "message": f"Models list available (HTTP {response.status_code})", "response_time_ms": response_time}
                try:
                    models_data = response.json()
                    model_names = [m["id"] for m in models_data.get("data", []) if isinstance(m, dict) and "id" in m]
                    models_test["message"] += f", {len(model_names)} models"
                    if model_names:
                        models_test["available_models"] = model_names
                except Exception:
                    pass
    except httpx.HTTPError as e:
        models_test = {"status": "warning", "message": f"Models list request failed: {e}", "response_time_ms": _elapsed_ms(start)}

    if chat_test.get("status") != "ok":
        models_state = "available" if models_test.get("status") == "ok" else "unavailable"
        return {
            "status": "warning",
            "message": f"Chat endpoint unavailable: {chat_test.get('message', '')}; models list {models_state}: {models_test['message']}",
            "response_time_ms": chat_test.get("response_time_ms", models_test.get("response_time_ms")),
            "models_endpoint_test": models_test,
            "chat_completion_test": chat_test,
        }

    if models_test.get("status") != "ok":
        return {
            "status": "ok",
            "message": f"{chat_test['message']}; models list unavailable: {models_test['message']}",
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


async def _test_primary_responses(api_url: str, api_key: str, model: str) -> dict[str, Any]:
    responses_url = f"{api_url.rstrip('/')}/responses"
    start = time.time()
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            responses_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "input": [{"role": "user", "content": "Reply with exactly: ok"}],
                "stream": False,
            },
        )
        response_time = _elapsed_ms(start)
        if response.status_code != 200:
            return {"status": "warning", "message": f"HTTP {response.status_code}: {response.text[:100]}", "response_time_ms": response_time}
        return {"status": "ok", "message": f"xAI Responses API available (HTTP {response.status_code})", "response_time_ms": response_time}


async def _test_main_provider_connection(provider_config: dict[str, Any]) -> dict[str, Any]:
    if provider_config["mode"] == "xai-responses":
        return await _service()._test_primary_responses(provider_config["api_url"], provider_config["api_key"], provider_config["model"])
    return await _service()._test_primary_connection(provider_config["api_url"], provider_config["api_key"], provider_config["model"])


async def _safe_test_main_provider_connection(provider_config: dict[str, Any]) -> dict[str, Any]:
    try:
        return await _service()._test_main_provider_connection(provider_config)
    except httpx.TimeoutException:
        return {"status": "timeout", "message": f"{provider_config['provider']} request timed out; check network or API URL"}
    except httpx.RequestError as e:
        return {"status": "error", "message": f"{provider_config['provider']} network error: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": f"{provider_config['provider']} unknown error: {str(e)}"}


async def _test_exa_connection() -> dict[str, Any]:
    exa_key = config.exa_api_key
    if not exa_key:
        return {"status": "not_configured", "message": "EXA_API_KEY is not set; Exa search unavailable"}
    start = time.time()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{config.exa_base_url.rstrip('/')}/search",
            headers={"x-api-key": exa_key, "content-type": "application/json"},
            json={"query": "test", "numResults": 1, "type": "keyword"},
        )
        response_time = _elapsed_ms(start)
        if resp.status_code == 200:
            return {"status": "ok", "message": "Exa API available (HTTP 200)", "response_time_ms": response_time}
        return {"status": "warning", "message": f"HTTP {resp.status_code}: {resp.text[:100]}", "response_time_ms": response_time}


async def _test_tavily_connection() -> dict[str, Any]:
    tavily_key = config.tavily_api_key
    if not tavily_key:
        return {"status": "not_configured", "message": "TAVILY_API_KEY is not set; Tavily unavailable"}
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
            return {"status": "ok", "message": "Tavily API available (HTTP 200)", "response_time_ms": response_time}
        return {"status": "warning", "message": f"HTTP {resp.status_code}: {resp.text[:100]}", "response_time_ms": response_time}


async def _test_jina_connection() -> dict[str, Any]:
    if config.jina_respond_with and not config.jina_api_key:
        return {"status": "config_error", "message": "JINA_RESPOND_WITH requires JINA_API_KEY"}
    if not config.jina_api_key:
        return {"status": "not_configured", "message": "JINA_API_KEY is not set; Jina does not satisfy standard web_fetch (anonymous Reader is experimental only)"}
    start = time.time()
    data = await _service().jina_fetch("https://example.com")
    response_time = _elapsed_ms(start)
    if data.get("ok"):
        return {"status": "ok", "message": "Jina Reader available", "response_time_ms": response_time}
    error_type = data.get("error_type", "")
    status = error_type if error_type in {"auth_error", "config_error", "parameter_error", "rate_limited", "timeout"} else "warning"
    return {"status": status, "message": data.get("error", "Jina Reader unavailable"), "response_time_ms": response_time}


async def _test_context7_connection() -> dict[str, Any]:
    if not config.context7_api_key:
        return {"status": "not_configured", "message": "CONTEXT7_API_KEY is not set; Context7 unavailable"}
    result = await _service().context7_library("react", "hooks")
    if result.get("ok"):
        return {"status": "ok", "message": "Context7 API available", "response_time_ms": result.get("elapsed_ms", 0)}
    return {"status": "warning", "message": result.get("error", "Context7 API unavailable"), "response_time_ms": result.get("elapsed_ms", 0)}


async def doctor() -> dict[str, Any]:
    info = config.get_config_info()

    main_provider_configs: list[dict[str, Any]] = []
    try:
        main_provider_configs = _service()._main_search_provider_configs()
        info["main_search_connection_tests"] = {}
        for provider_config in main_provider_configs:
            info["main_search_connection_tests"][provider_config["provider"]] = await _service()._safe_test_main_provider_connection(provider_config)
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
        info["primary_connection_test"] = {"status": "error", "message": f"Unknown error: {str(e)}"}

    try:
        info["exa_connection_test"] = await _service()._test_exa_connection()
    except httpx.TimeoutException:
        info["exa_connection_test"] = {"status": "timeout", "message": "Exa API request timed out"}
    except Exception as e:
        info["exa_connection_test"] = {"status": "error", "message": str(e)}

    try:
        info["tavily_connection_test"] = await _service()._test_tavily_connection()
    except httpx.TimeoutException:
        info["tavily_connection_test"] = {"status": "timeout", "message": "Tavily API request timed out"}
    except Exception as e:
        info["tavily_connection_test"] = {"status": "error", "message": str(e)}

    try:
        info["jina_connection_test"] = await _service()._test_jina_connection()
    except httpx.TimeoutException:
        info["jina_connection_test"] = {"status": "timeout", "message": "Jina Reader request timed out"}
    except Exception as e:
        info["jina_connection_test"] = {"status": "error", "message": str(e)}

    if config.firecrawl_api_key:
        info["firecrawl_connection_test"] = {"status": "configured", "message": "FIRECRAWL_API_KEY is set"}
    else:
        info["firecrawl_connection_test"] = {"status": "not_configured", "message": "FIRECRAWL_API_KEY is not set; Firecrawl unavailable"}

    try:
        info["context7_connection_test"] = await _service()._test_context7_connection()
    except httpx.TimeoutException:
        info["context7_connection_test"] = {"status": "timeout", "message": "Context7 API request timed out"}
    except Exception as e:
        info["context7_connection_test"] = {"status": "error", "message": str(e)}

    minimum = _service().validate_minimum_profile()
    info["capability_status"] = minimum.get("capability_status", _service().get_capability_status())
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
        info["error_code"] = ""
        info["error"] = ""
    elif info.get("config_parameter_errors"):
        info.update(error_fields(ErrorType.PARAMETER, error="; ".join(info["config_parameter_errors"])))
    elif not minimum.get("ok", False):
        info.update(
            error_fields(
                minimum.get("error_type", ErrorType.CONFIG.value),
                error=minimum.get("error", MINIMUM_PROFILE_ERROR),
                error_code=minimum.get("error_code") or MINIMUM_PROFILE,
            )
        )
    else:
        info["error"] = primary_test.get("message", "Primary connection check failed")
        if primary_status == "config_error":
            info.update(error_fields(ErrorType.CONFIG, error=info["error"]))
        elif primary_status in {"timeout", "error", "warning"}:
            info.update(error_fields(ErrorType.NETWORK, error=info["error"]))
        else:
            info.update(error_fields(ErrorType.RUNTIME, error=info["error"]))
    return info

