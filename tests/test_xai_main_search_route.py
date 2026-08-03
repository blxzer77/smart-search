import pytest

from smart_search import cli, service
from smart_search.config import config
from smart_search.providers.openai_compatible import OpenAICompatibleSearchProvider
from smart_search.providers.xai_responses import XAIResponsesSearchProvider


def _set_openai_env(monkeypatch):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_URL", "https://relay.example.com/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "relay-key")


def _set_xai_env(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-key")


def test_effective_chain_defaults_to_fallback_order():
    assert service._effective_main_search_chain() == ["xai-responses", "openai-compatible"]


def test_effective_chain_single_openai(monkeypatch):
    monkeypatch.setenv("SMART_SEARCH_MAIN_SEARCH_ROUTE", "openai-compatible")
    assert service._effective_main_search_chain() == ["openai-compatible"]


def test_effective_chain_csv_order_and_alias(monkeypatch):
    monkeypatch.setenv("SMART_SEARCH_MAIN_SEARCH_ROUTE", "openai,grok")
    assert service._effective_main_search_chain() == ["openai-compatible", "xai-responses"]


def test_effective_chain_dedupes(monkeypatch):
    monkeypatch.setenv("SMART_SEARCH_MAIN_SEARCH_ROUTE", "xai,xai-responses")
    assert service._effective_main_search_chain() == ["xai-responses"]


def test_effective_chain_invalid_raises(monkeypatch):
    monkeypatch.setenv("SMART_SEARCH_MAIN_SEARCH_ROUTE", "bogus")
    with pytest.raises(ValueError, match="SMART_SEARCH_MAIN_SEARCH_ROUTE"):
        service._effective_main_search_chain()


def test_configs_xai_only(monkeypatch):
    _set_xai_env(monkeypatch)
    configs = service._main_search_provider_configs()
    assert [item["provider"] for item in configs] == ["xai-responses"]
    assert configs[0]["mode"] == "xai-responses"
    assert configs[0]["tools"] == ["web_search", "x_search"]
    assert configs[0]["api_url"] == "https://api.x.ai/v1"


def test_configs_openai_only_keeps_current_behavior(monkeypatch):
    _set_openai_env(monkeypatch)
    configs = service._main_search_provider_configs()
    assert [item["provider"] for item in configs] == ["openai-compatible"]


def test_configs_both_default_xai_first(monkeypatch):
    _set_xai_env(monkeypatch)
    _set_openai_env(monkeypatch)
    assert [item["provider"] for item in service._main_search_provider_configs()] == ["xai-responses", "openai-compatible"]


def test_configs_both_route_openai_first(monkeypatch):
    _set_xai_env(monkeypatch)
    _set_openai_env(monkeypatch)
    monkeypatch.setenv("SMART_SEARCH_MAIN_SEARCH_ROUTE", "openai-compatible,xai-responses")
    assert [item["provider"] for item in service._main_search_provider_configs()] == ["openai-compatible", "xai-responses"]


def test_configs_both_route_single_no_cross(monkeypatch):
    _set_xai_env(monkeypatch)
    _set_openai_env(monkeypatch)
    monkeypatch.setenv("SMART_SEARCH_MAIN_SEARCH_ROUTE", "openai-compatible")
    assert [item["provider"] for item in service._main_search_provider_configs()] == ["openai-compatible"]


def test_configs_route_points_to_unconfigured_provider(monkeypatch):
    _set_openai_env(monkeypatch)
    monkeypatch.setenv("SMART_SEARCH_MAIN_SEARCH_ROUTE", "xai-responses")
    assert service._main_search_provider_configs() == []


def test_factory_instantiates_xai_provider(monkeypatch):
    _set_xai_env(monkeypatch)
    providers = service._main_search_providers(service._main_search_provider_configs(), "auto")
    assert isinstance(providers[0], XAIResponsesSearchProvider)


def test_factory_mixed_chain_order(monkeypatch):
    _set_xai_env(monkeypatch)
    _set_openai_env(monkeypatch)
    providers = service._main_search_providers(service._main_search_provider_configs(), "auto")
    assert isinstance(providers[0], XAIResponsesSearchProvider)
    assert isinstance(providers[1], OpenAICompatibleSearchProvider)


def test_factory_fallback_off_takes_first_only(monkeypatch):
    _set_xai_env(monkeypatch)
    _set_openai_env(monkeypatch)
    providers = service._main_search_providers(service._main_search_provider_configs(), "off")
    assert len(providers) == 1
    assert isinstance(providers[0], XAIResponsesSearchProvider)


def test_main_search_capability_ok_with_xai_only(monkeypatch):
    _set_xai_env(monkeypatch)
    status = service.get_capability_status()
    assert status["main_search"]["ok"] is True
    assert status["main_search"]["configured"] == ["xai-responses"]


def test_main_search_capability_reports_effective_chain(monkeypatch):
    _set_xai_env(monkeypatch)
    _set_openai_env(monkeypatch)
    monkeypatch.setenv("SMART_SEARCH_MAIN_SEARCH_ROUTE", "openai-compatible")
    status = service.get_capability_status()
    assert status["main_search"]["fallback_chain"] == ["openai-compatible"]
    assert status["main_search"]["configured"] == ["openai-compatible"]


def test_parse_xai_tools_default():
    assert config.parse_xai_tools() == ["web_search", "x_search"]


def test_parse_xai_tools_dedup_and_order():
    assert config.parse_xai_tools("x_search,web_search,x_search") == ["x_search", "web_search"]


def test_parse_xai_tools_invalid_raises():
    with pytest.raises(ValueError, match="XAI_TOOLS"):
        config.parse_xai_tools("web_search,bogus")


def test_setup_non_interactive_saves_xai_values(monkeypatch, capsys):
    saved = {}

    def fake_config_set(key, value):
        saved[key] = value
        return {"ok": True, "key": key, "value": "***", "config_file": "C:/tmp/config.json"}

    monkeypatch.setattr(cli.service, "config_set", fake_config_set)
    monkeypatch.setattr(cli.service, "config_path", lambda: {"ok": True, "config_file": "C:/tmp/config.json"})

    code = cli.main([
        "setup",
        "--non-interactive",
        "--xai-api-url",
        "https://api.x.ai/v1",
        "--xai-api-key",
        "xai-test-secret",
        "--xai-model",
        "grok-4-fast",
        "--xai-tools",
        "web_search,x_search",
        "--main-search-route",
        "xai-responses,openai-compatible",
    ])

    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert saved["XAI_API_URL"] == "https://api.x.ai/v1"
    assert saved["XAI_API_KEY"] == "xai-test-secret"
    assert saved["XAI_MODEL"] == "grok-4-fast"
    assert saved["XAI_TOOLS"] == "web_search,x_search"
    assert saved["SMART_SEARCH_MAIN_SEARCH_ROUTE"] == "xai-responses,openai-compatible"
    assert "xai-test-secret" not in out
