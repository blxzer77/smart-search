import time

import pytest

from smart_search import service


@pytest.mark.parametrize(
    ("query", "expect_docs"),
    [
        ("How do I use the Prisma Client API?", True),
        ("Compare OpenAI and Anthropic pricing models", False),
        ("How does the market react to rate cuts?", False),
        ("公司内部配置管理流程是什么", False),
        ("python list comprehension syntax", True),
        ("Summarize https://docs.python.org/3/library/asyncio.html event loop", False),
        ("LangChain Python SDK 快速开始教程", True),
        ("Tavily vs Exa which is better for RAG", False),
        ("对比 Context7 和 Exa 做文档检索的架构取舍", False),
    ],
)
def test_docs_intent_precision_cases(query, expect_docs):
    assert service._is_docs_intent(query) is expect_docs


@pytest.mark.parametrize(
    "query",
    [
        "Tavily vs Exa which is better for RAG",
        "对比 Context7 和 Exa 做文档检索的架构取舍",
        "Compare Tavily vs Firecrawl best practices for agent tooling 2026",
    ],
)
def test_broad_intent_provider_comparisons(query):
    assert service._is_broad_research_intent(query) is True
    assert service._is_docs_intent(query) is False


def test_cross_validation_triggers_on_vs():
    plan = service.build_deep_research_plan(
        "Tavily vs Exa which is better for RAG",
        evidence_dir="C:/evidence/vs",
    )
    assert plan["intent_signals"]["cross_validation_need"] == "high"
    assert plan["intent_signals"]["docs_api_intent"] is False


@pytest.mark.asyncio
async def test_docs_empty_fail_open_runs_web_discovery(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test")
    monkeypatch.setenv("CONTEXT7_API_KEY", "ctx")
    monkeypatch.setenv("EXA_API_KEY", "exa")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily")
    monkeypatch.setenv("JINA_API_KEY", "jina")

    async def fake_context7_library(*args, **kwargs):
        return {"ok": True, "results": [{"id": "/org/lib"}]}

    async def fake_context7_docs(*args, **kwargs):
        return {"ok": True, "content": "docs snippet only"}

    async def fake_bilingual(*args, **kwargs):
        return (
            [{"url": "https://candidate.example.com", "title": "Candidate", "provider": "tavily"}],
            [service._attempt("web_search", "tavily", "ok", time.time(), result_count=1)],
        )

    async def fake_fetch(*args, **kwargs):
        return {
            "url": "https://candidate.example.com",
            "provider": "jina",
            "content": "fetched body " * 20,
        }, [service._attempt("web_fetch", "jina", "ok", time.time())]

    monkeypatch.setattr(service, "context7_library", fake_context7_library)
    monkeypatch.setattr(service, "context7_docs", fake_context7_docs)
    monkeypatch.setattr(service, "_run_bilingual_web_search", fake_bilingual)
    monkeypatch.setattr(service, "_run_web_fetch_fallback", fake_fetch)

    query = "Prisma Client API reference"
    assert service._is_docs_intent(query) is True

    result = await service.research(query, evidence_dir=str(tmp_path), fallback="auto", budget="standard")

    stages = [entry.get("stage") for entry in result.get("stage_results") or []]
    assert "fail_open_web_after_docs" in stages
    assert "web_discovery" in stages
    assert result["route_policy_version"] == service.RESEARCH_ROUTE_POLICY_VERSION
