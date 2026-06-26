"""CLI JSON contract shape tests (lightweight schema)."""
import pytest

from smart_search import service


def _assert_keys(payload: dict, required: list[str]) -> None:
    missing = [key for key in required if key not in payload]
    assert not missing, f"missing keys: {missing}"


def test_search_result_contract_keys():
    payload = service._empty_search_result(
        start=0.0,
        session_id="test-session",
        query="q",
        error_type="config_error",
        error="x",
    )
    _assert_keys(
        payload,
        [
            "ok",
            "error_type",
            "error",
            "query",
            "routing_decision",
            "provider_attempts",
            "providers_used",
            "fallback_used",
            "primary_sources",
            "extra_sources",
            "source_warning",
            "validation_level",
        ],
    )


@pytest.mark.asyncio
async def test_research_minimum_profile_failure_contract(monkeypatch):
    monkeypatch.setattr(service, "validate_minimum_profile", lambda: {"ok": False, "error_type": "config_error", "error": "x", "capability_status": {}})
    result = await service.research("test")
    _assert_keys(
        result,
        [
            "ok",
            "gap_check",
            "citations",
            "evidence_items",
            "degraded",
            "route_policy_version",
            "evidence_dir",
            "provider_attempts",
        ],
    )
    assert result["gap_check"]["status"] == "failed"


@pytest.mark.asyncio
async def test_doctor_contract_keys(monkeypatch, tmp_path):
    from smart_search.config import Config

    cfg = Config()
    monkeypatch.setattr(cfg, "_config_file", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "_config_dir_source", "override")
    result = await service.doctor()
    _assert_keys(
        result,
        [
            "ok",
            "config_status",
            "minimum_profile_ok",
            "capability_status",
            "error_type",
        ],
    )
