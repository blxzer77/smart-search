import time

import pytest

from smart_search import service
from smart_search.research_plan import candidate_fetch_limit_for_budget


@pytest.mark.parametrize(
    "budget,expected",
    [
        ("quick", 3),
        ("standard", 5),
        ("deep", 6),
        ("QUICK", 3),
        ("", 5),
        ("unknown", 5),
    ],
)
def test_candidate_fetch_limit_for_budget(budget, expected):
    assert candidate_fetch_limit_for_budget(budget) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("budget,expected_limit", [("quick", 3), ("deep", 6)])
async def test_research_executor_caps_candidate_fetch_by_budget(monkeypatch, tmp_path, budget, expected_limit):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test")
    monkeypatch.setenv("CONTEXT7_API_KEY", "ctx")
    monkeypatch.setenv("EXA_API_KEY", "exa")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily")
    monkeypatch.setenv("JINA_API_KEY", "jina")

    from smart_search import research_executor

    discovery = [
        {"url": f"https://evidence.example.com/source-{i}", "title": f"Source {i}", "provider": "tavily"}
        for i in range(8)
    ]

    async def fake_bilingual(*args, **kwargs):
        return (
            discovery,
            [service._attempt("web_search", "tavily", "ok", time.time(), result_count=len(discovery))],
        )

    captured: dict[str, list] = {"candidates": []}

    async def fake_batch(candidates, **kwargs):
        captured["candidates"] = list(candidates)
        return []

    monkeypatch.setattr(service, "_run_bilingual_web_search", fake_bilingual)
    monkeypatch.setattr(research_executor, "fetch_research_candidates_concurrent", fake_batch)

    await service.research("broad AI agent research tools 2026", evidence_dir=str(tmp_path), budget=budget)

    assert len(captured["candidates"]) == expected_limit
