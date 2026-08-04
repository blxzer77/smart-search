"""Provider-layer retry/stream contract tests (T5) — no live network."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from smart_search.providers.openai_compatible import (
    OpenAICompatibleSearchProvider,
    _WaitWithRetryAfter,
    _is_retryable_exception,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "openai_compatible"
COMPLETION_OK = json.loads((FIXTURES / "completion_ok.json").read_text(encoding="utf-8"))
STREAM_OK_LINES = (FIXTURES / "stream_ok.sse").read_text(encoding="utf-8").splitlines()


class InstantWait:
    """Zero-delay wait so retry contracts stay fast."""

    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, retry_state):
        return 0


class FakeStreamResponse:
    def __init__(self, status_code: int, lines: list[str], request: httpx.Request):
        self.status_code = status_code
        self._lines = lines
        self.request = request
        self.headers = httpx.Headers({})

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _StreamContext:
    def __init__(self, response_or_exc):
        self._payload = response_or_exc

    async def __aenter__(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    async def __aexit__(self, exc_type, exc, tb):
        return None


class FakeAsyncClient:
    """Queue-driven httpx.AsyncClient stub for completion + stream paths."""

    queue: list = []
    calls: list = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def _next(self):
        if not self.__class__.queue:
            raise AssertionError("FakeAsyncClient queue exhausted")
        return self.__class__.queue.pop(0)

    async def post(self, url, headers=None, json=None):
        self.__class__.calls.append({"kind": "post", "url": url, "headers": headers, "json": json})
        item = self._next()
        if isinstance(item, Exception):
            raise item
        return item

    def stream(self, method, url, headers=None, json=None):
        self.__class__.calls.append(
            {"kind": "stream", "method": method, "url": url, "headers": headers, "json": json}
        )
        return _StreamContext(self._next())


@pytest.fixture
def instant_retry(monkeypatch):
    monkeypatch.setenv("SMART_SEARCH_RETRY_MAX_ATTEMPTS", "2")
    monkeypatch.setattr(
        "smart_search.providers.openai_compatible._WaitWithRetryAfter",
        InstantWait,
    )


@pytest.fixture(autouse=True)
def reset_fake_client():
    FakeAsyncClient.queue = []
    FakeAsyncClient.calls = []


def _request(path: str = "/chat/completions") -> httpx.Request:
    return httpx.Request("POST", f"https://api.example.com/v1{path}")


def test_is_retryable_exception_contract():
    req = _request()
    assert _is_retryable_exception(httpx.TimeoutException("t")) is True
    assert _is_retryable_exception(httpx.ConnectError("c")) is True
    assert _is_retryable_exception(httpx.NetworkError("n")) is True
    assert _is_retryable_exception(httpx.RemoteProtocolError("p")) is True

    for code in (408, 429, 500, 502, 503, 504):
        resp = httpx.Response(code, request=req)
        assert _is_retryable_exception(httpx.HTTPStatusError("e", request=req, response=resp)) is True

    bad = httpx.Response(400, request=req)
    assert _is_retryable_exception(httpx.HTTPStatusError("e", request=req, response=bad)) is False
    assert _is_retryable_exception(ValueError("nope")) is False


def test_wait_with_retry_after_honors_seconds_header():
    req = _request()
    resp = httpx.Response(429, headers={"Retry-After": "7"}, request=req)
    exc = httpx.HTTPStatusError("limited", request=req, response=resp)
    state = SimpleNamespace(outcome=SimpleNamespace(failed=True, exception=lambda: exc))
    wait = _WaitWithRetryAfter(multiplier=1, max_wait=60)
    assert wait(state) == 7.0


def test_wait_with_retry_after_honors_http_date_header():
    req = _request()
    when = datetime.now(timezone.utc) + timedelta(seconds=12)
    resp = httpx.Response(
        429,
        headers={"Retry-After": format_datetime(when)},
        request=req,
    )
    exc = httpx.HTTPStatusError("limited", request=req, response=resp)
    state = SimpleNamespace(outcome=SimpleNamespace(failed=True, exception=lambda: exc))
    wait = _WaitWithRetryAfter(multiplier=1, max_wait=60)
    delay = wait(state)
    assert 0.0 <= delay <= 15.0


@pytest.mark.asyncio
async def test_completion_retries_on_503_then_uses_recorded_fixture(monkeypatch, instant_retry):
    monkeypatch.setattr(
        "smart_search.providers.openai_compatible.httpx.AsyncClient",
        FakeAsyncClient,
    )
    req = _request()
    FakeAsyncClient.queue = [
        httpx.Response(503, text="busy", request=req),
        httpx.Response(200, json=COMPLETION_OK, request=req),
    ]
    provider = OpenAICompatibleSearchProvider("https://api.example.com/v1", "k", "m")
    result = await provider._execute_completion_with_retry(
        provider._build_api_headers(),
        {"model": "m", "messages": [], "stream": False},
    )

    assert result == "recorded completion fixture"
    assert [c["kind"] for c in FakeAsyncClient.calls] == ["post", "post"]
    assert FakeAsyncClient.calls[0]["url"].endswith("/chat/completions")


@pytest.mark.asyncio
async def test_completion_does_not_retry_non_retryable_400(monkeypatch, instant_retry):
    monkeypatch.setattr(
        "smart_search.providers.openai_compatible.httpx.AsyncClient",
        FakeAsyncClient,
    )
    req = _request()
    FakeAsyncClient.queue = [httpx.Response(400, text="bad", request=req)]
    provider = OpenAICompatibleSearchProvider("https://api.example.com/v1", "k", "m")

    with pytest.raises(httpx.HTTPStatusError) as caught:
        await provider._execute_completion_with_retry(
            provider._build_api_headers(),
            {"model": "m", "messages": [], "stream": False},
        )

    assert caught.value.response.status_code == 400
    assert len(FakeAsyncClient.calls) == 1


@pytest.mark.asyncio
async def test_stream_retries_then_parses_recorded_sse_fixture(monkeypatch, instant_retry):
    monkeypatch.setattr(
        "smart_search.providers.openai_compatible.httpx.AsyncClient",
        FakeAsyncClient,
    )
    req = _request()
    FakeAsyncClient.queue = [
        FakeStreamResponse(503, [], req),
        FakeStreamResponse(200, STREAM_OK_LINES, req),
    ]
    provider = OpenAICompatibleSearchProvider(
        "https://api.example.com/v1", "k", "m", stream=True
    )
    result = await provider._execute_stream_with_retry(
        provider._build_api_headers(),
        {"model": "m", "messages": [], "stream": True},
    )

    assert result == "recorded stream"
    assert [c["kind"] for c in FakeAsyncClient.calls] == ["stream", "stream"]
    assert FakeAsyncClient.calls[-1]["json"]["stream"] is True


@pytest.mark.asyncio
async def test_search_stream_true_hits_stream_executor_with_http_stub(monkeypatch, instant_retry):
    monkeypatch.setattr(
        "smart_search.providers.openai_compatible.httpx.AsyncClient",
        FakeAsyncClient,
    )
    req = _request()
    FakeAsyncClient.queue = [FakeStreamResponse(200, STREAM_OK_LINES, req)]
    provider = OpenAICompatibleSearchProvider(
        "https://api.example.com/v1", "k", "m", stream=True
    )

    result = await provider.search("query")

    assert result == "recorded stream"
    assert FakeAsyncClient.calls[0]["kind"] == "stream"
    assert FakeAsyncClient.calls[0]["json"]["stream"] is True
