import pytest

from smart_search.research_cache import (
    CACHE_TTL_BY_CAPABILITY,
    _TTLCache,
    cached_call,
    is_time_sensitive,
    make_key,
    reset_cache_disabled_flag,
)
from smart_search import research_cache


def test_cache_ttl_by_capability_matches_prd():
    assert CACHE_TTL_BY_CAPABILITY["web_fetch"] == 7 * 24 * 3600
    assert CACHE_TTL_BY_CAPABILITY["docs_search"] == 3600
    assert CACHE_TTL_BY_CAPABILITY["web_search"] == 600
    assert "main_search" not in CACHE_TTL_BY_CAPABILITY


def test_is_time_sensitive_detects_current_and_recent_keywords():
    assert is_time_sensitive("今天国内 AI 新闻") is True
    assert is_time_sensitive("latest Bitcoin price") is True
    assert is_time_sensitive("React hooks tutorial") is False
    assert is_time_sensitive("") is False


def test_make_key_is_deterministic():
    k1 = make_key("web_fetch", "https://a.com", "auto", "jina")
    k2 = make_key("web_fetch", "https://a.com", "auto", "jina")
    assert k1 == k2
    assert make_key("web_fetch", "https://a.com") != make_key("web_fetch", "https://b.com")


@pytest.mark.asyncio
async def test_cached_call_hits_on_second_call(monkeypatch):
    monkeypatch.delenv("SMART_SEARCH_CACHE", raising=False)
    reset_cache_disabled_flag()
    research_cache._REGISTRY = _TTLCache()

    calls: list[str] = []

    async def fake_fetch(url, fallback="auto", preferred_order=None):
        calls.append(url)
        return ({"ok": True, "url": url, "provider": "jina", "content": "x"}, [])

    key = make_key("web_fetch", "https://e.com", "auto", "jina")
    r1, hit1 = await cached_call("web_fetch", key, CACHE_TTL_BY_CAPABILITY["web_fetch"], fake_fetch, "https://e.com", fallback="auto", preferred_order=["jina"])
    r2, hit2 = await cached_call("web_fetch", key, CACHE_TTL_BY_CAPABILITY["web_fetch"], fake_fetch, "https://e.com", fallback="auto", preferred_order=["jina"])

    assert len(calls) == 1
    assert hit1 is False
    assert hit2 is True
    assert r1 == r2


@pytest.mark.asyncio
async def test_cached_call_disabled_via_env(monkeypatch):
    monkeypatch.setenv("SMART_SEARCH_CACHE", "off")
    reset_cache_disabled_flag()
    research_cache._REGISTRY = _TTLCache()

    calls: list[str] = []

    async def fake_fetch(url, fallback="auto", preferred_order=None):
        calls.append(url)
        return ({"ok": True, "url": url, "provider": "jina", "content": "x"}, [])

    key = make_key("web_fetch", "https://e.com", "auto", "jina")
    await cached_call("web_fetch", key, CACHE_TTL_BY_CAPABILITY["web_fetch"], fake_fetch, "https://e.com", fallback="auto", preferred_order=["jina"])
    await cached_call("web_fetch", key, CACHE_TTL_BY_CAPABILITY["web_fetch"], fake_fetch, "https://e.com", fallback="auto", preferred_order=["jina"])

    assert len(calls) == 2
    monkeypatch.delenv("SMART_SEARCH_CACHE", raising=False)
    reset_cache_disabled_flag()


@pytest.mark.asyncio
async def test_cached_call_skips_when_ttl_none(monkeypatch):
    monkeypatch.delenv("SMART_SEARCH_CACHE", raising=False)
    reset_cache_disabled_flag()
    research_cache._REGISTRY = _TTLCache()

    calls: list[str] = []

    async def fake_search(query, count=5, providers="auto", fallback="auto", locale_scope="both"):
        calls.append(query)
        return ([{"url": "https://e.com", "provider": "tavily"}], [])

    key = make_key("bilingual", "今天新闻", 5, "tavily", "auto", "both")
    await cached_call("web_search", key, None, fake_search, "今天新闻", count=5, providers="tavily", fallback="auto", locale_scope="both")
    await cached_call("web_search", key, None, fake_search, "今天新闻", count=5, providers="tavily", fallback="auto", locale_scope="both")

    assert len(calls) == 2
