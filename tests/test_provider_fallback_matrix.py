import time

import pytest

from smart_search import service


def _configure_fetch_providers(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tavily")
    monkeypatch.setenv("JINA_API_KEY", "jina")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "firecrawl")


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
