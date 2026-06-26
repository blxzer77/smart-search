import asyncio

import pytest

from smart_search.research_fetch_batch import fetch_research_candidates_concurrent


@pytest.mark.asyncio
async def test_fetch_research_candidates_concurrent_limits_parallelism():
    active = 0
    peak = 0
    lock = asyncio.Lock()

    async def fake_fetch(url, fallback="auto", preferred_order=None):
        nonlocal active, peak
        async with lock:
            active += 1
            peak = max(peak, active)
        await asyncio.sleep(0.05)
        async with lock:
            active -= 1
        return (
            {"ok": True, "url": url, "provider": "test", "content": "body"},
            [],
        )

    candidates = [{"url": f"https://example.com/{i}", "title": f"T{i}"} for i in range(6)]

    await fetch_research_candidates_concurrent(
        candidates,
        question="q",
        fallback_mode="auto",
        fetched_urls=set(),
        run_web_fetch_fallback=fake_fetch,
        research_fetch_order=lambda question, url: ["jina"],
        concurrency=2,
    )

    assert peak <= 2
    assert peak >= 2


@pytest.mark.asyncio
async def test_fetch_research_candidates_skips_already_fetched_urls():
    calls: list[str] = []

    async def fake_fetch(url, fallback="auto", preferred_order=None):
        calls.append(url)
        return ({"ok": True, "url": url, "provider": "test", "content": "x"}, [])

    candidates = [
        {"url": "https://a.example", "title": "A"},
        {"url": "https://b.example", "title": "B"},
    ]

    results = await fetch_research_candidates_concurrent(
        candidates,
        question="q",
        fallback_mode="auto",
        fetched_urls={"https://a.example"},
        run_web_fetch_fallback=fake_fetch,
        research_fetch_order=lambda question, url: ["jina"],
        concurrency=3,
    )

    assert calls == ["https://b.example"]
    assert len(results) == 1
    assert results[0]["url"] == "https://b.example"