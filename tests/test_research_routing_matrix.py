import pytest

from smart_search import service


def _min_caps():
    return {
        "main_search": {"configured": ["openai-compatible"], "ok": True},
        "docs_search": {"configured": ["context7", "exa"], "ok": True},
        "web_search": {"configured": ["tavily", "firecrawl"], "ok": True},
        "web_fetch": {"configured": ["jina", "tavily", "firecrawl"], "ok": True},
    }


@pytest.mark.parametrize(
    ("query", "expect_docs", "expect_broad"),
    [
        ("React useEffect API docs", True, False),
        ("Compare Tavily vs Firecrawl best practices 2026", False, True),
        ("今天国内 AI 政策最新公告", False, False),
        ("https://example.com/page summarize", False, False),
    ],
)
def test_routing_signals_matrix(monkeypatch, query, expect_docs, expect_broad):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk")
    monkeypatch.setenv("CONTEXT7_API_KEY", "c7")
    monkeypatch.setenv("EXA_API_KEY", "exa")
    monkeypatch.setenv("TAVILY_API_KEY", "tv")
    monkeypatch.setenv("JINA_API_KEY", "jina")
    plan = service.build_deep_research_plan(query, evidence_dir="C:/evidence/matrix")
    routes = service._research_capability_routes(
        query, plan, "auto", capability_status=_min_caps()
    )
    assert routes["signals"]["docs_api_intent"] is expect_docs
    assert routes["signals"]["broad_research_intent"] is expect_broad
    assert routes["capabilities"]["docs_search"]["providers"]
    assert routes["capabilities"]["web_search"]["providers"]
    assert routes["capabilities"]["web_fetch"]["providers"]


def test_routing_preferred_override_orders_docs(monkeypatch):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk")
    monkeypatch.setenv("CONTEXT7_API_KEY", "c7")
    monkeypatch.setenv("EXA_API_KEY", "exa")
    monkeypatch.setenv("TAVILY_API_KEY", "tv")
    monkeypatch.setenv("JINA_API_KEY", "jina")
    monkeypatch.setenv("SMART_SEARCH_RESEARCH_PREFERRED_PROVIDERS", "exa,context7")
    plan = service.build_deep_research_plan("OpenAI API documentation", evidence_dir="C:/evidence/ovr")
    routes = service._research_capability_routes(
        "OpenAI API documentation", plan, "auto", capability_status=_min_caps()
    )
    docs = routes["capabilities"]["docs_search"]["providers"]
    assert docs[0] == "exa"
