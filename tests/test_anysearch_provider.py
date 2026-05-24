import json

import httpx
import pytest

from smart_search.providers.anysearch import AnySearchProvider


class FakeAnySearchClient:
    calls = []
    response: httpx.Response | None = None
    exception: Exception | None = None

    def __init__(self, timeout, follow_redirects=True):
        self.timeout = timeout
        self.follow_redirects = follow_redirects

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url, headers, json):
        self.__class__.calls.append({"url": url, "headers": headers, "json": json, "timeout": self.timeout})
        if self.__class__.exception:
            raise self.__class__.exception
        return self.__class__.response


@pytest.fixture(autouse=True)
def reset_fake_client():
    FakeAnySearchClient.calls = []
    FakeAnySearchClient.response = None
    FakeAnySearchClient.exception = None


@pytest.mark.asyncio
async def test_anysearch_jsonrpc_success_parses_markdown_and_auth_header(monkeypatch):
    FakeAnySearchClient.response = httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "### 1. React hooks\n- **URL**: https://react.dev/reference/react\nReact Hooks API reference.",
                    }
                ]
            },
        },
        request=httpx.Request("POST", "https://api.anysearch.com/mcp"),
    )
    monkeypatch.setattr("smart_search.providers.anysearch.httpx.AsyncClient", FakeAnySearchClient)

    provider = AnySearchProvider("https://api.anysearch.com/mcp", "as-test-secret", timeout=12)
    data = json.loads(await provider.vertical_search("React hooks", domain="code.doc", max_results=2))

    assert data["ok"] is True
    assert data["provider"] == "anysearch"
    assert data["tool"] == "search"
    assert data["query"] == "React hooks"
    assert data["domain"] == "code"
    assert data["sub_domain"] == "doc"
    assert data["raw_content"].startswith("### 1. React hooks")
    assert data["results"][0]["url"] == "https://react.dev/reference/react"
    assert data["results"][0]["title"] == "React hooks"
    call = FakeAnySearchClient.calls[0]
    assert call["headers"]["Authorization"] == "Bearer as-test-secret"
    assert call["json"]["method"] == "tools/call"
    assert call["json"]["params"]["name"] == "search"
    assert call["json"]["params"]["arguments"]["max_results"] == 2
    assert call["json"]["params"]["arguments"]["domain"] == "code"
    assert call["json"]["params"]["arguments"]["sub_domain"] == "doc"
    assert call["timeout"].read == 12.0


@pytest.mark.asyncio
async def test_anysearch_anonymous_request_omits_authorization(monkeypatch):
    FakeAnySearchClient.response = httpx.Response(
        200,
        json={"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "No domains"}]}},
        request=httpx.Request("POST", "https://api.anysearch.com/mcp"),
    )
    monkeypatch.setattr("smart_search.providers.anysearch.httpx.AsyncClient", FakeAnySearchClient)

    provider = AnySearchProvider("https://api.anysearch.com/mcp", None)
    data = json.loads(await provider.list_domains())

    assert data["ok"] is True
    assert "Authorization" not in FakeAnySearchClient.calls[0]["headers"]


@pytest.mark.asyncio
async def test_anysearch_result_is_error_is_provider_error_without_sources(monkeypatch):
    FakeAnySearchClient.response = httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "isError": True,
                "content": [{"type": "text", "text": "invalid domain https://example.com/should-not-be-source"}],
            },
        },
        request=httpx.Request("POST", "https://api.anysearch.com/mcp"),
    )
    monkeypatch.setattr("smart_search.providers.anysearch.httpx.AsyncClient", FakeAnySearchClient)

    provider = AnySearchProvider("https://api.anysearch.com/mcp", "as-test-secret")
    data = json.loads(await provider.vertical_search("query", domain="bad.domain"))

    assert data["ok"] is False
    assert data["error_type"] == "provider_error"
    assert "invalid domain" in data["error"]
    assert data["results"] == []
    assert data["raw_content"].startswith("invalid domain")


@pytest.mark.asyncio
async def test_anysearch_jsonrpc_error_is_provider_error(monkeypatch):
    FakeAnySearchClient.response = httpx.Response(
        200,
        json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32602, "message": "invalid params"}},
        request=httpx.Request("POST", "https://api.anysearch.com/mcp"),
    )
    monkeypatch.setattr("smart_search.providers.anysearch.httpx.AsyncClient", FakeAnySearchClient)

    provider = AnySearchProvider("https://api.anysearch.com/mcp", "as-test-secret")
    data = json.loads(await provider.extract("https://example.com"))

    assert data["ok"] is False
    assert data["error_type"] == "provider_error"
    assert data["error"] == "invalid params"


@pytest.mark.asyncio
async def test_anysearch_http_forbidden_maps_to_auth_error(monkeypatch):
    FakeAnySearchClient.response = httpx.Response(
        403,
        text="forbidden",
        request=httpx.Request("POST", "https://api.anysearch.com/mcp"),
    )
    monkeypatch.setattr("smart_search.providers.anysearch.httpx.AsyncClient", FakeAnySearchClient)

    provider = AnySearchProvider("https://api.anysearch.com/mcp", "as-test-secret")
    data = json.loads(await provider.extract("https://example.com"))

    assert data["ok"] is False
    assert data["error_type"] == "auth_error"
    assert "HTTP 403" in data["error"]


@pytest.mark.asyncio
async def test_anysearch_timeout_maps_to_timeout(monkeypatch):
    FakeAnySearchClient.exception = httpx.ReadTimeout("too slow", request=httpx.Request("POST", "https://api.anysearch.com/mcp"))
    monkeypatch.setattr("smart_search.providers.anysearch.httpx.AsyncClient", FakeAnySearchClient)

    provider = AnySearchProvider("https://api.anysearch.com/mcp", "as-test-secret")
    data = json.loads(await provider.extract("https://example.com"))

    assert data["ok"] is False
    assert data["error_type"] == "timeout"


@pytest.mark.asyncio
async def test_anysearch_structured_result_without_url_is_preserved(monkeypatch):
    FakeAnySearchClient.response = httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": "CVE-2024-3094 severity: critical\nAffected: xz utils"}]},
        },
        request=httpx.Request("POST", "https://api.anysearch.com/mcp"),
    )
    monkeypatch.setattr("smart_search.providers.anysearch.httpx.AsyncClient", FakeAnySearchClient)

    provider = AnySearchProvider("https://api.anysearch.com/mcp", "as-test-secret")
    data = json.loads(await provider.vertical_search("CVE-2024-3094", domain="security.cve"))

    assert data["ok"] is True
    assert data["total"] == 1
    assert data["results"][0]["evidence_type"] == "structured"
    assert data["results"][0]["url"] == ""
    assert "CVE-2024-3094" in data["results"][0]["raw_content"]


@pytest.mark.asyncio
async def test_anysearch_batch_limit_returns_parameter_error_without_request(monkeypatch):
    monkeypatch.setattr("smart_search.providers.anysearch.httpx.AsyncClient", FakeAnySearchClient)

    provider = AnySearchProvider("https://api.anysearch.com/mcp", "as-test-secret")
    data = json.loads(await provider.batch_search(["a", "b", "c", "d", "e", "f"]))

    assert data["ok"] is False
    assert data["error_type"] == "parameter_error"
    assert "max 5" in data["error"]
    assert FakeAnySearchClient.calls == []


@pytest.mark.asyncio
async def test_anysearch_batch_sends_live_compatible_query_objects(monkeypatch):
    FakeAnySearchClient.response = httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "## Query 1: React hooks\n\n### 1. Built-in React Hooks\n- **URL**: https://react.dev/reference/react/hooks",
                    }
                ]
            },
        },
        request=httpx.Request("POST", "https://api.anysearch.com/mcp"),
    )
    monkeypatch.setattr("smart_search.providers.anysearch.httpx.AsyncClient", FakeAnySearchClient)

    provider = AnySearchProvider("https://api.anysearch.com/mcp", "as-test-secret")
    data = json.loads(await provider.batch_search(["React hooks", "CVE-2024-3094"], max_results=1))

    assert data["ok"] is True
    call = FakeAnySearchClient.calls[0]
    assert call["json"]["params"]["name"] == "batch_search"
    assert call["json"]["params"]["arguments"]["queries"] == [
        {"query": "React hooks", "max_results": 1},
        {"query": "CVE-2024-3094", "max_results": 1},
    ]
    assert set(call["json"]["params"]["arguments"]) == {"queries"}
