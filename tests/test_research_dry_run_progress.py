import io
import sys
import time
from contextlib import redirect_stderr

import pytest

from smart_search import service
from smart_search.research_synthesis import citation_items


def test_citation_items_include_structured_fields():
    items = [
        {
            "id": "eabc123",
            "url": "https://example.com/a",
            "title": "A",
            "provider": "jina",
            "source_type": "fetched_page",
            "subquestion_id": "sq1",
            "verified": True,
            "content_len": 120,
        }
    ]
    citations = citation_items(items)
    assert len(citations) == 1
    assert citations[0]["id"] == "eabc123"
    assert citations[0]["source_type"] == "fetched_page"
    assert citations[0]["subquestion_id"] == "sq1"
    assert citations[0]["verified"] is True
    assert citations[0]["content_len"] == 120


@pytest.mark.asyncio
async def test_research_dry_run_returns_plan_without_live_providers(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test")
    monkeypatch.setenv("CONTEXT7_API_KEY", "ctx")
    monkeypatch.setenv("EXA_API_KEY", "exa")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily")
    monkeypatch.setenv("JINA_API_KEY", "jina")

    async def fail_live(*args, **kwargs):
        raise AssertionError("dry-run must not call live providers")

    monkeypatch.setattr(service, "_run_bilingual_web_search", fail_live)
    monkeypatch.setattr(service, "_run_web_fetch_fallback", fail_live)
    monkeypatch.setattr(service, "context7_library", fail_live)

    result = await service.research(
        "OpenAI Responses API web_search vs Chat Completions",
        evidence_dir=str(tmp_path),
        budget="deep",
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["mode"] == "deep_research"
    assert result["research_plan"]["mode"] == "deep_research"
    assert len(result["research_plan"]["steps"]) >= 1
    assert "routing_decision" in result
    assert result["candidate_fetch_limit"] == 6
    assert not (tmp_path / "summary.json").exists()


@pytest.mark.asyncio
async def test_research_progress_writes_stderr(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test")
    monkeypatch.setenv("CONTEXT7_API_KEY", "ctx")
    monkeypatch.setenv("EXA_API_KEY", "exa")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily")
    monkeypatch.setenv("JINA_API_KEY", "jina")

    async def fake_bilingual(*args, **kwargs):
        return (
            [
                {"url": "https://evidence.example.com/source-a", "title": "Source A", "provider": "tavily"},
                {"url": "https://evidence.example.com/source-b", "title": "Source B", "provider": "tavily"},
            ],
            [service._attempt("web_search", "tavily", "ok", time.time(), result_count=2)],
        )

    async def fake_fetch(*args, **kwargs):
        url = args[0] if args else kwargs.get("url", "")
        return (
            {"ok": True, "url": url, "provider": "jina", "content": "# Evidence"},
            [service._attempt("web_fetch", "jina", "ok", time.time(), result_count=1)],
        )

    monkeypatch.setattr(service, "_run_bilingual_web_search", fake_bilingual)
    monkeypatch.setattr(service, "_run_web_fetch_fallback", fake_fetch)

    stderr = io.StringIO()
    with redirect_stderr(stderr):
        result = await service.research("今天国内 AI 新闻", evidence_dir=str(tmp_path), progress=True)

    lines = stderr.getvalue()
    assert result["ok"] is True
    assert "[research]" in lines
    assert "plan ready" in lines
    assert "web_discovery" in lines
    assert "gap_check" in lines
    assert result.get("output_schema_version") == 1
    assert result["citations"][0].get("id")


@pytest.mark.asyncio
async def test_research_dry_run_skips_progress_stderr(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily")

    stderr = io.StringIO()
    with redirect_stderr(stderr):
        result = await service.research("test question", evidence_dir=str(tmp_path), dry_run=True, progress=True)

    assert result["dry_run"] is True
    assert stderr.getvalue() == ""
