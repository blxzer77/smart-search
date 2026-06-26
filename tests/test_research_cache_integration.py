import time

import pytest

from smart_search import research_cache, service
from smart_search.research_cache import _TTLCache, reset_cache_disabled_flag


def _setup_min_profile(monkeypatch):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test")
    monkeypatch.setenv("CONTEXT7_API_KEY", "ctx")
    monkeypatch.setenv("EXA_API_KEY", "exa")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily")
    monkeypatch.setenv("JINA_API_KEY", "jina")


@pytest.mark.asyncio
async def test_research_web_discovery_cached_on_repeat(monkeypatch, tmp_path):
    _setup_min_profile(monkeypatch)
    monkeypatch.delenv("SMART_SEARCH_CACHE", raising=False)
    reset_cache_disabled_flag()
    research_cache._REGISTRY = _TTLCache()

    calls: list[str] = []

    async def fake_bilingual(*args, **kwargs):
        calls.append(args[0] if args else kwargs.get("query", ""))
        return (
            [{"url": "https://evidence.example.com/source-a", "title": "A", "provider": "tavily"}],
            [service._attempt("web_search", "tavily", "ok", time.time(), result_count=1)],
        )

    async def fake_fetch(*args, **kwargs):
        url = args[0] if args else kwargs.get("url", "")
        return (
            {"ok": True, "url": url, "provider": "jina", "content": "# Evidence"},
            [service._attempt("web_fetch", "jina", "ok", time.time(), result_count=1)],
        )

    monkeypatch.setattr(service, "_run_bilingual_web_search", fake_bilingual)
    monkeypatch.setattr(service, "_run_web_fetch_fallback", fake_fetch)

    await service.research("React server components architecture", evidence_dir=str(tmp_path), budget="quick")
    await service.research("React server components architecture", evidence_dir=str(tmp_path), budget="quick")

    assert len(calls) == 1
    reset_cache_disabled_flag()


@pytest.mark.asyncio
async def test_research_time_sensitive_query_not_cached(monkeypatch, tmp_path):
    _setup_min_profile(monkeypatch)
    monkeypatch.delenv("SMART_SEARCH_CACHE", raising=False)
    reset_cache_disabled_flag()
    research_cache._REGISTRY = _TTLCache()

    calls: list[str] = []

    async def fake_bilingual(*args, **kwargs):
        calls.append(args[0] if args else kwargs.get("query", ""))
        return (
            [{"url": "https://evidence.example.com/news-a", "title": "News A", "provider": "tavily"}],
            [service._attempt("web_search", "tavily", "ok", time.time(), result_count=1)],
        )

    async def fake_fetch(*args, **kwargs):
        url = args[0] if args else kwargs.get("url", "")
        return (
            {"ok": True, "url": url, "provider": "jina", "content": "# News"},
            [service._attempt("web_fetch", "jina", "ok", time.time(), result_count=1)],
        )

    monkeypatch.setattr(service, "_run_bilingual_web_search", fake_bilingual)
    monkeypatch.setattr(service, "_run_web_fetch_fallback", fake_fetch)

    await service.research("今天国内 AI 新闻最新动态", evidence_dir=str(tmp_path), budget="quick")
    await service.research("今天国内 AI 新闻最新动态", evidence_dir=str(tmp_path), budget="quick")

    assert len(calls) == 2
    reset_cache_disabled_flag()


@pytest.mark.asyncio
async def test_research_provider_attempts_record_cache_hit(monkeypatch, tmp_path):
    _setup_min_profile(monkeypatch)
    monkeypatch.delenv("SMART_SEARCH_CACHE", raising=False)
    reset_cache_disabled_flag()
    research_cache._REGISTRY = _TTLCache()

    async def fake_bilingual(*args, **kwargs):
        return (
            [{"url": "https://evidence.example.com/source-a", "title": "A", "provider": "tavily"}],
            [service._attempt("web_search", "tavily", "ok", time.time(), result_count=1)],
        )

    async def fake_fetch(*args, **kwargs):
        url = args[0] if args else kwargs.get("url", "")
        return (
            {"ok": True, "url": url, "provider": "jina", "content": "# Evidence"},
            [service._attempt("web_fetch", "jina", "ok", time.time(), result_count=1)],
        )

    monkeypatch.setattr(service, "_run_bilingual_web_search", fake_bilingual)
    monkeypatch.setattr(service, "_run_web_fetch_fallback", fake_fetch)

    await service.research("React hooks patterns", evidence_dir=str(tmp_path), budget="quick")
    result2 = await service.research("React hooks patterns", evidence_dir=str(tmp_path), budget="quick")

    cache_hits = [a.get("cache_hit") for a in result2["provider_attempts"] if a.get("capability") == "web_search"]
    assert any(cache_hits)
    stage_hits = [s.get("cache_hit") for s in result2["stage_results"] if s.get("stage") == "web_discovery"]
    assert any(stage_hits)
    reset_cache_disabled_flag()
