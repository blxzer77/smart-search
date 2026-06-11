import pytest

from smart_search import service


def test_minimum_profile_reports_missing_categories(monkeypatch):
    monkeypatch.setenv("SMART_SEARCH_MINIMUM_PROFILE", "standard")

    result = service.validate_minimum_profile()

    assert result["ok"] is False
    assert set(result["missing"]) == {"main_search", "docs_search", "web_fetch"}
    assert "capability_status" in result


@pytest.mark.asyncio
async def test_fetch_attempts_show_fallback(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-secret")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "firecrawl-secret")

    async def no_tavily(url):
        return None

    async def yes_firecrawl(url, ctx=None):
        return "# Page"

    monkeypatch.setattr(service, "call_tavily_extract", no_tavily)
    monkeypatch.setattr(service, "call_firecrawl_scrape", yes_firecrawl)

    result = await service.fetch("https://example.com")

    assert result["ok"] is True
    assert result["provider"] == "firecrawl"
    assert result["fallback_used"] is True
    assert [a["provider"] for a in result["provider_attempts"]] == ["tavily", "firecrawl"]


@pytest.mark.asyncio
async def test_search_docs_intent_uses_docs_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test-secret")
    monkeypatch.setenv("EXA_API_KEY", "exa-secret")
    monkeypatch.setenv("CONTEXT7_API_KEY", "ctx-secret")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-secret")

    async def fake_search(self, query, platform="", ctx=None):
        return "Answer."

    async def fake_context7(name, query=""):
        return {"ok": True, "results": [{"id": "/facebook/react", "title": "React", "description": "UI"}], "total": 1}

    async def fake_bilingual_web_search(query, count=5, providers="auto", fallback="auto"):
        return [], []

    monkeypatch.setattr(service.OpenAICompatibleSearchProvider, "search", fake_search)
    monkeypatch.setattr(service, "context7_library", fake_context7)
    monkeypatch.setattr(service, "_run_bilingual_web_search", fake_bilingual_web_search)

    result = await service.search("React useEffect API docs", validation="balanced")

    assert result["ok"] is True
    assert result["routing_decision"]["docs_intent"] is True
    assert "web_search" in result["routing_decision"]["supplemental_paths"]
    assert result["fallback_used"] is False
    assert "context7" in result["providers_used"]
    assert "exa" not in result["providers_used"]


@pytest.mark.asyncio
async def test_search_docs_intent_falls_back_to_exa_after_context7_empty(monkeypatch):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test-secret")
    monkeypatch.setenv("EXA_API_KEY", "exa-secret")
    monkeypatch.setenv("CONTEXT7_API_KEY", "ctx-secret")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-secret")

    async def fake_search(self, query, platform="", ctx=None):
        return "Answer."

    async def fake_context7(name, query=""):
        return {"ok": True, "results": [], "total": 0}

    async def fake_exa(*args, **kwargs):
        return {"ok": True, "results": [{"url": "https://docs.example.com", "title": "Docs"}]}

    async def fake_bilingual_web_search(query, count=5, providers="auto", fallback="auto"):
        return [], []

    monkeypatch.setattr(service.OpenAICompatibleSearchProvider, "search", fake_search)
    monkeypatch.setattr(service, "context7_library", fake_context7)
    monkeypatch.setattr(service, "exa_search", fake_exa)
    monkeypatch.setattr(service, "_run_bilingual_web_search", fake_bilingual_web_search)

    result = await service.search("React useEffect API docs", validation="balanced")

    assert result["ok"] is True
    assert result["fallback_used"] is True
    providers = [attempt["provider"] for attempt in result["provider_attempts"] if attempt["capability"] == "docs_search"]
    assert providers == ["context7", "exa"]
    assert "exa" in result["providers_used"]


@pytest.mark.asyncio
async def test_search_zh_current_uses_bilingual_tavily_reinforcement(monkeypatch):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test-secret")
    monkeypatch.setenv("EXA_API_KEY", "exa-secret")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-secret")
    monkeypatch.setenv("ZHIPU_API_KEY", "zhipu-secret")

    async def fake_search(self, query, platform="", ctx=None):
        return "Answer."

    web_queries = []

    async def fake_web_search(query, count=5, providers="auto", fallback="auto"):
        web_queries.append(query)
        locale = "zh" if query.startswith("中文搜索") else "en"
        return (
            [{"url": f"https://{locale}.example.com/news", "title": "News", "provider": "tavily"}],
            [service._attempt("web_search", "tavily", "ok", 0, result_count=1)],
        )

    async def fail_zhipu(*args, **kwargs):
        raise AssertionError("zhipu-search must not be used by default routing")

    monkeypatch.setattr(service.OpenAICompatibleSearchProvider, "search", fake_search)
    monkeypatch.setattr(service, "_run_web_search_fallback", fake_web_search)
    monkeypatch.setattr(service, "zhipu_search", fail_zhipu)

    result = await service.search("今天国内 AI 新闻", validation="balanced")

    assert result["ok"] is True
    assert result["routing_decision"]["zh_current_intent"] is True
    assert result["routing_decision"]["bilingual_query_locales"] == ["zh", "en"]
    assert len(web_queries) == 2
    assert "tavily" in result["providers_used"]
    assert "zhipu" not in result["providers_used"]
