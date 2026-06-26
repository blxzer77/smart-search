import time

import pytest

from smart_search import service
from smart_search.research_discovery import run_bilingual_web_search


@pytest.mark.parametrize(
    "locale_scope,expected_locales",
    [
        ("cn", {"zh"}),
        ("en", {"en"}),
        ("both", {"zh", "en"}),
        ("CN", {"zh"}),
        ("EN", {"en"}),
        ("BOTH", {"zh", "en"}),
    ],
)
@pytest.mark.asyncio
async def test_run_bilingual_web_search_respects_locale_scope(monkeypatch, locale_scope, expected_locales):
    calls: list[str] = []

    async def fake_web_search_fallback(query, count=5, providers="auto", fallback="auto"):
        calls.append(query)
        return (
            [{"url": f"https://example.com/{len(calls)}", "title": "hit", "provider": "tavily"}],
            [service._attempt("web_search", "tavily", "ok", time.time(), result_count=1)],
        )

    monkeypatch.setattr(service, "_run_web_search_fallback", fake_web_search_fallback)

    sources, _ = await run_bilingual_web_search("test question", locale_scope=locale_scope)

    assert len(calls) == len(expected_locales)
    locales = {item.get("query_locale") for item in sources}
    assert locales == expected_locales


@pytest.mark.asyncio
async def test_research_executor_passes_locale_scope_to_bilingual(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test")
    monkeypatch.setenv("CONTEXT7_API_KEY", "ctx")
    monkeypatch.setenv("EXA_API_KEY", "exa")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily")
    monkeypatch.setenv("JINA_API_KEY", "jina")

    captured: dict[str, str] = {}

    async def fake_bilingual(*args, **kwargs):
        captured["locale_scope"] = kwargs.get("locale_scope", "")
        return (
            [{"url": "https://evidence.example.com/source-a", "title": "Source A", "provider": "tavily"}],
            [service._attempt("web_search", "tavily", "ok", time.time(), result_count=1)],
        )

    async def fake_fetch(*args, **kwargs):
        return (
            {"ok": True, "url": "https://evidence.example.com/source-a", "provider": "jina", "content": "# Evidence"},
            [service._attempt("web_fetch", "jina", "ok", time.time(), result_count=1)],
        )

    monkeypatch.setattr(service, "_run_bilingual_web_search", fake_bilingual)
    monkeypatch.setattr(service, "_run_web_fetch_fallback", fake_fetch)

    await service.research("今天国内 AI 新闻", evidence_dir=str(tmp_path), locale_scope="cn")

    assert captured.get("locale_scope") == "cn"


@pytest.mark.asyncio
async def test_research_rejects_invalid_locale_scope():
    result = await service.research("test question", locale_scope="fr")
    assert result["ok"] is False
    assert result["error_type"] == "parameter_error"
    assert "locale scope" in result["error"].lower()