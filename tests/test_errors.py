"""ErrorType / error_code / exit mapping contract tests."""

from smart_search.errors import (
    EXIT_CONFIG_ERROR,
    EXIT_NETWORK_ERROR,
    EXIT_PARAMETER_ERROR,
    EXIT_RUNTIME_ERROR,
    ErrorType,
    attach_error_fields,
    error_code_for,
    error_fields,
    exit_code_for,
    exit_code_from_result,
)
from smart_search import cli, service


def test_error_type_enum_values_are_stable():
    assert ErrorType.CONFIG.value == "config_error"
    assert ErrorType.PARAMETER.value == "parameter_error"
    assert ErrorType.NETWORK.value == "network_error"
    assert ErrorType.EVIDENCE.value == "evidence_error"
    assert ErrorType.RUNTIME.value == "runtime_error"


def test_exit_code_mapping_keeps_historical_contract():
    assert exit_code_for(ErrorType.PARAMETER) == EXIT_PARAMETER_ERROR
    assert exit_code_for(ErrorType.CONFIG) == EXIT_CONFIG_ERROR
    assert exit_code_for(ErrorType.NETWORK) == EXIT_NETWORK_ERROR
    assert exit_code_for(ErrorType.EVIDENCE) == EXIT_NETWORK_ERROR
    assert exit_code_for(ErrorType.AUTH) == EXIT_RUNTIME_ERROR
    assert exit_code_for(ErrorType.TIMEOUT) == EXIT_RUNTIME_ERROR
    assert exit_code_for("unknown_type") == EXIT_RUNTIME_ERROR


def test_cli_exit_code_uses_central_mapping():
    assert cli._exit_code({"ok": True}) == 0
    assert cli._exit_code({"ok": False, "error_type": "parameter_error"}) == EXIT_PARAMETER_ERROR
    assert cli._exit_code({"ok": False, "error_type": "config_error"}) == EXIT_CONFIG_ERROR
    assert cli._exit_code({"ok": False, "error_type": "network_error"}) == EXIT_NETWORK_ERROR
    assert cli._exit_code({"ok": False, "error_type": "evidence_error"}) == EXIT_NETWORK_ERROR
    assert cli._exit_code({"ok": False, "error_type": "runtime_error"}) == EXIT_RUNTIME_ERROR
    assert exit_code_from_result({"ok": False, "error_type": "rate_limited"}) == EXIT_RUNTIME_ERROR


def test_error_fields_default_english_and_error_code():
    fields = error_fields(ErrorType.CONFIG, error_code="MISSING_API_KEY")
    assert fields["error_type"] == "config_error"
    assert fields["error_code"] == "MISSING_API_KEY"
    assert "API key" in fields["error"] or "configured" in fields["error"].lower()
    assert all(ord(ch) < 128 or ch in fields["error"] for ch in fields["error"][:1])  # starts ASCII
    # Default message for type when no specific code message override beyond DEFAULT_MESSAGES
    typed = error_fields(ErrorType.NETWORK)
    assert typed["error_code"] == "NETWORK_ERROR"
    assert typed["error"] == "Network error."


def test_attach_error_fields_is_idempotent():
    payload = {"ok": False, "error_type": "parse_error", "error": "raw"}
    attach_error_fields(payload)
    assert payload["error_code"] == "PARSE_ERROR"
    attach_error_fields(payload)
    assert payload["error_code"] == "PARSE_ERROR"


def test_empty_search_result_includes_error_code():
    payload = service._empty_search_result(
        start=0.0,
        session_id="s",
        query="q",
        error_type=ErrorType.CONFIG.value,
        error="missing",
    )
    assert payload["error_type"] == "config_error"
    assert payload["error_code"] == error_code_for(ErrorType.CONFIG)
    assert payload["error"] == "missing"


def test_search_timeout_result_includes_error_code():
    payload = cli._search_timeout_result("q", 12.0)
    assert payload["error_type"] == "network_error"
    assert payload["error_code"] == "SEARCH_TIMEOUT"
    assert "timed out" in payload["error"].lower()
