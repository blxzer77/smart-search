import time

import pytest

from smart_search import service

BROAD_QUERY = (
    "AI agent web research CLI tools best practices 2025 2026 "
    "Tavily Exa Context7 architecture patterns"
)


def test_broad_research_query_not_docs_intent():
    assert service._is_broad_research_intent(BROAD_QUERY) is True
    assert service._is_docs_intent(BROAD_QUERY) is False


def test_research_gap_status_rejects_docs_only_evidence():
    gaps: list[dict] = []
    status, reason = service._research_gap_status(
        [
            service._research_evidence_item(
                url="context7:/packtpublishing/react-design-patterns",
                provider="context7",
                title="noise",
                content="snippet only",
                source_type="docs",
            )
        ],
        gaps,
    )
    assert status == "failed"
    assert reason == "docs_only_without_fetch"
    assert gaps


def test_research_route_signals_mark_broad_research():
    plan = service.build_deep_research_plan(BROAD_QUERY, evidence_dir="C:/evidence/test")
    signals = service._research_route_signals(BROAD_QUERY, plan)
    assert signals["broad_research_intent"] is True
    assert signals["docs_api_intent"] is False


@pytest.mark.asyncio
async def test_research_broad_query_without_http_fetch_does_not_close_gap(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test")
    monkeypatch.setenv("CONTEXT7_API_KEY", "ctx")
    monkeypatch.setenv("EXA_API_KEY", "exa")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily")
    monkeypatch.setenv("JINA_API_KEY", "jina")

    async def fake_bilingual(*args, **kwargs):
        return (
            [{"url": "https://candidate.example.com", "title": "Candidate", "provider": "tavily"}],
            [service._attempt("web_search", "tavily", "ok", time.time(), result_count=1)],
        )

    async def fake_fetch(*args, **kwargs):
        return None, [service._attempt("web_fetch", "jina", "empty", time.time())]

    monkeypatch.setattr(service, "_run_bilingual_web_search", fake_bilingual)
    monkeypatch.setattr(service, "_run_web_fetch_fallback", fake_fetch)

    result = await service.research(BROAD_QUERY, evidence_dir=str(tmp_path), fallback="auto")

    assert result["ok"] is False
    assert result["gap_check"]["status"] == "failed"
    assert result["gap_check"]["stop_reason"] == "provider_exhausted"
    assert result["route_policy_version"] == service.RESEARCH_ROUTE_POLICY_VERSION
    assert result["routing_decision"]["signals"]["broad_research_intent"] is True
    assert result["routing_decision"]["signals"]["docs_api_intent"] is False
