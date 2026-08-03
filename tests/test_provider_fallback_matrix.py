import time

import pytest

from smart_search import service


def _configure_fetch_providers(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tavily")
    monkeypatch.setenv("JINA_API_KEY", "jina")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "firecrawl")


def _configure_web_search_providers(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tavily")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "firecrawl")


def _configure_docs_providers(monkeypatch):
    monkeypatch.setenv("CONTEXT7_API_KEY", "context7")
    monkeypatch.setenv("EXA_API_KEY", "exa")


@pytest.mark.asyncio
async def test_web_fetch_fallback_off_uses_first_provider_only(monkeypatch):
    _configure_fetch_providers(monkeypatch)
    calls: list[str] = []

    async def fake_tavily(url):
        calls.append("tavily")
        return None

    async def fake_jina(url):
        calls.append("jina")
        return {"ok": True, "content": "body", "url": url}

    monkeypatch.setattr(service, "call_tavily_extract", fake_tavily)
    monkeypatch.setattr(service, "jina_fetch", fake_jina)

    result, attempts = await service._run_web_fetch_fallback(
        "https://example.com/a",
        fallback="off",
        preferred_order=["tavily", "jina", "firecrawl"],
    )

    assert result is None
    assert calls == ["tavily"]
    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_web_fetch_fallback_auto_tries_next_provider(monkeypatch):
    _configure_fetch_providers(monkeypatch)

    async def fake_tavily(url):
        return None

    async def fake_jina(url):
        return {"ok": True, "content": "fetched", "url": url}

    monkeypatch.setattr(service, "call_tavily_extract", fake_tavily)
    monkeypatch.setattr(service, "jina_fetch", fake_jina)

    result, attempts = await service._run_web_fetch_fallback(
        "https://example.com/b",
        fallback="auto",
        preferred_order=["tavily", "jina"],
    )

    assert result is not None
    assert result["provider"] == "jina"
    assert service._fallback_used(attempts) is True


@pytest.mark.asyncio
async def test_web_search_fallback_off_uses_first_provider_only(monkeypatch):
    _configure_web_search_providers(monkeypatch)
    calls: list[str] = []

    async def fake_tavily(query, count=5):
        calls.append("tavily")
        return []

    async def fake_firecrawl(query, count=5):
        calls.append("firecrawl")
        return [{"url": "https://example.com", "title": "x"}]

    monkeypatch.setattr(service, "call_tavily_search", fake_tavily)
    monkeypatch.setattr(service, "call_firecrawl_search", fake_firecrawl)

    sources, attempts = await service._run_web_search_fallback(
        "query",
        count=3,
        fallback="off",
    )

    assert sources == []
    assert calls == ["tavily"]
    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_web_search_fallback_auto_tries_next_provider(monkeypatch):
    _configure_web_search_providers(monkeypatch)
    calls: list[str] = []

    async def fake_tavily(query, count=5):
        calls.append("tavily")
        return []

    async def fake_firecrawl(query, count=5):
        calls.append("firecrawl")
        return [{"url": "https://example.com", "title": "x", "content": "body"}]

    monkeypatch.setattr(service, "call_tavily_search", fake_tavily)
    monkeypatch.setattr(service, "call_firecrawl_search", fake_firecrawl)

    sources, attempts = await service._run_web_search_fallback(
        "query",
        count=3,
        fallback="auto",
    )

    assert calls == ["tavily", "firecrawl"]
    assert len(sources) == 1
    assert sources[0]["provider"] == "firecrawl"
    assert service._fallback_used(attempts) is True


@pytest.mark.asyncio
async def test_docs_search_fallback_off_uses_first_provider_only(monkeypatch):
    _configure_docs_providers(monkeypatch)
    calls: list[str] = []

    async def fake_context7(library_query, query):
        calls.append("context7")
        return {"ok": False, "error_type": "", "error": "", "results": []}

    async def fake_exa(query, num_results=5, include_highlights=True):
        calls.append("exa")
        return {"ok": True, "results": [{"url": "https://docs.example.com", "title": "Docs"}]}

    monkeypatch.setattr(service, "context7_library", fake_context7)
    monkeypatch.setattr(service, "exa_search", fake_exa)

    sources, attempts = await service._run_docs_search_fallback("React hooks", fallback="off")

    assert sources == []
    assert calls == ["context7"]
    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_docs_search_fallback_auto_tries_next_provider(monkeypatch):
    _configure_docs_providers(monkeypatch)
    calls: list[str] = []

    async def fake_context7(library_query, query):
        calls.append("context7")
        return {"ok": False, "error_type": "", "error": "", "results": []}

    async def fake_exa(query, num_results=5, include_highlights=True):
        calls.append("exa")
        return {
            "ok": True,
            "results": [{"url": "https://docs.example.com", "title": "Docs", "text": "body"}],
        }

    monkeypatch.setattr(service, "context7_library", fake_context7)
    monkeypatch.setattr(service, "exa_search", fake_exa)

    sources, attempts = await service._run_docs_search_fallback("React hooks", fallback="auto")

    assert calls == ["context7", "exa"]
    assert len(sources) == 1
    assert sources[0]["provider"] == "exa"
    assert service._fallback_used(attempts) is True


def test_main_search_fallback_off_takes_first_only(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk")
    configs = service._main_search_provider_configs()
    assert len(configs) >= 2
    providers_off = service._main_search_providers(configs, "off")
    providers_auto = service._main_search_providers(configs, "auto")
    assert len(providers_off) == 1
    assert len(providers_auto) == len(configs)
