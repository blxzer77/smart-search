import pytest

from smart_search.research_cache import (
    CACHE_TTL_BY_CAPABILITY,
    DEFAULT_CACHE_MAX_ENTRIES,
    _TTLCache,
    cached_call,
    is_time_sensitive,
    make_key,
    make_keyed,
    reset_cache_disabled_flag,
    reset_cache_max_entries_flag,
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
async def test_make_keyed_changes_when_model_changes(monkeypatch):
    monkeypatch.setattr("smart_search.research_cache.cache_identity", lambda: "id-a")
    key_a = make_keyed("bilingual", "q", 5, "tavily", "auto", "both")
    monkeypatch.setattr("smart_search.research_cache.cache_identity", lambda: "id-b")
    key_b = make_keyed("bilingual", "q", 5, "tavily", "auto", "both")
    assert key_a != key_b


@pytest.mark.asyncio
async def test_cached_call_misses_after_model_identity_change(monkeypatch):
    monkeypatch.delenv("SMART_SEARCH_CACHE", raising=False)
    reset_cache_disabled_flag()
    research_cache._REGISTRY = _TTLCache()

    calls: list[str] = []

    async def fake_search(*args, **kwargs):
        calls.append("x")
        return ([{"url": "https://e.com"}], [])

    monkeypatch.setattr("smart_search.research_cache.cache_identity", lambda: "m1")
    key1 = make_keyed("bilingual", "q", 5, "tavily", "auto", "both")
    await cached_call("web_search", key1, CACHE_TTL_BY_CAPABILITY["web_search"], fake_search)
    await cached_call("web_search", key1, CACHE_TTL_BY_CAPABILITY["web_search"], fake_search)
    assert len(calls) == 1

    monkeypatch.setattr("smart_search.research_cache.cache_identity", lambda: "m2")
    key2 = make_keyed("bilingual", "q", 5, "tavily", "auto", "both")
    await cached_call("web_search", key2, CACHE_TTL_BY_CAPABILITY["web_search"], fake_search)
    assert len(calls) == 2
    assert key1 != key2


def test_ttl_cache_lru_evicts_oldest_when_over_capacity():
    cache = _TTLCache(max_entries=2)
    cache.set(("a",), "1", ttl=3600)
    cache.set(("b",), "2", ttl=3600)
    assert len(cache) == 2
    cache.set(("c",), "3", ttl=3600)
    assert len(cache) == 2
    assert cache.get(("a",)) is None
    assert cache.get(("b",)) == "2"
    assert cache.get(("c",)) == "3"


def test_ttl_cache_lru_promotes_on_get():
    cache = _TTLCache(max_entries=2)
    cache.set(("a",), "1", ttl=3600)
    cache.set(("b",), "2", ttl=3600)
    assert cache.get(("a",)) == "1"
    cache.set(("c",), "3", ttl=3600)
    assert cache.get(("b",)) is None
    assert cache.get(("a",)) == "1"
    assert cache.get(("c",)) == "3"


def test_cache_max_entries_env(monkeypatch):
    monkeypatch.setenv("SMART_SEARCH_CACHE_MAX_ENTRIES", "3")
    reset_cache_max_entries_flag()
    assert research_cache._cache_max_entries() == 3
    monkeypatch.delenv("SMART_SEARCH_CACHE_MAX_ENTRIES", raising=False)
    reset_cache_max_entries_flag()
    assert research_cache._cache_max_entries() == DEFAULT_CACHE_MAX_ENTRIES


@pytest.mark.parametrize(
    "locale_a,locale_b,budget_a,budget_b,should_differ",
    [
        ("cn", "en", "standard", "standard", True),
        ("both", "both", "standard", "deep", True),
        ("cn", "cn", "standard", "standard", False),
        ("en", "en", "deep", "deep", False),
    ],
)
def test_make_keyed_locale_budget_collision_matrix(
    monkeypatch, locale_a, locale_b, budget_a, budget_b, should_differ
):
    monkeypatch.setattr("smart_search.research_cache.cache_identity", lambda: "id-fixed")
    key_a = make_keyed("bilingual", "same-question", 5, "tavily", "auto", locale_a, budget_a)
    key_b = make_keyed("bilingual", "same-question", 5, "tavily", "auto", locale_b, budget_b)
    if should_differ:
        assert key_a != key_b
    else:
        assert key_a == key_b
