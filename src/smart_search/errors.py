"""Central ErrorType / error_code / exit-code contract for CLI and JSON consumers."""

from __future__ import annotations

from enum import Enum
from typing import Any


EXIT_OK = 0
EXIT_PARAMETER_ERROR = 2
EXIT_CONFIG_ERROR = 3
EXIT_NETWORK_ERROR = 4
EXIT_RUNTIME_ERROR = 5


class ErrorType(str, Enum):
    """Stable machine-facing error categories (JSON `error_type`)."""

    CONFIG = "config_error"
    PARAMETER = "parameter_error"
    NETWORK = "network_error"
    EVIDENCE = "evidence_error"
    AUTH = "auth_error"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    PARSE = "parse_error"
    QUALITY = "quality_error"
    RUNTIME = "runtime_error"


# Stable SCREAMING_SNAKE codes for Agent/JSON consumers (JSON `error_code`).
ERROR_CODE_BY_TYPE: dict[ErrorType, str] = {
    ErrorType.CONFIG: "CONFIG_ERROR",
    ErrorType.PARAMETER: "PARAMETER_ERROR",
    ErrorType.NETWORK: "NETWORK_ERROR",
    ErrorType.EVIDENCE: "EVIDENCE_ERROR",
    ErrorType.AUTH: "AUTH_ERROR",
    ErrorType.RATE_LIMITED: "RATE_LIMITED",
    ErrorType.TIMEOUT: "TIMEOUT",
    ErrorType.PARSE: "PARSE_ERROR",
    ErrorType.QUALITY: "QUALITY_ERROR",
    ErrorType.RUNTIME: "RUNTIME_ERROR",
}

EXIT_CODE_BY_TYPE: dict[ErrorType, int] = {
    ErrorType.CONFIG: EXIT_CONFIG_ERROR,
    ErrorType.PARAMETER: EXIT_PARAMETER_ERROR,
    ErrorType.NETWORK: EXIT_NETWORK_ERROR,
    ErrorType.EVIDENCE: EXIT_NETWORK_ERROR,  # keep historical exit 4
    ErrorType.AUTH: EXIT_RUNTIME_ERROR,
    ErrorType.RATE_LIMITED: EXIT_RUNTIME_ERROR,
    ErrorType.TIMEOUT: EXIT_RUNTIME_ERROR,
    ErrorType.PARSE: EXIT_RUNTIME_ERROR,
    ErrorType.QUALITY: EXIT_RUNTIME_ERROR,
    ErrorType.RUNTIME: EXIT_RUNTIME_ERROR,
}

# Specific codes for common failure shapes (optional overrides of type default).
MISSING_API_KEY = "MISSING_API_KEY"
MINIMUM_PROFILE = "MINIMUM_PROFILE"
SEARCH_EMPTY = "SEARCH_EMPTY"
SEARCH_FAILED = "SEARCH_FAILED"
EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
FETCH_FAILED = "FETCH_FAILED"
MAP_TIMEOUT = "MAP_TIMEOUT"
MAP_HTTP_ERROR = "MAP_HTTP_ERROR"
MAP_ERROR = "MAP_ERROR"
PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
PROVIDER_NETWORK = "PROVIDER_NETWORK"
PROVIDER_RUNTIME = "PROVIDER_RUNTIME"
PROVIDER_EMPTY = "PROVIDER_EMPTY"
PARSE_FAILED = "PARSE_FAILED"

DEFAULT_MESSAGES: dict[str, str] = {
    ERROR_CODE_BY_TYPE[ErrorType.CONFIG]: "Configuration error.",
    ERROR_CODE_BY_TYPE[ErrorType.PARAMETER]: "Invalid parameter.",
    ERROR_CODE_BY_TYPE[ErrorType.NETWORK]: "Network error.",
    ERROR_CODE_BY_TYPE[ErrorType.EVIDENCE]: "Insufficient evidence.",
    ERROR_CODE_BY_TYPE[ErrorType.AUTH]: "Authentication error.",
    ERROR_CODE_BY_TYPE[ErrorType.RATE_LIMITED]: "Rate limited.",
    ERROR_CODE_BY_TYPE[ErrorType.TIMEOUT]: "Request timed out.",
    ERROR_CODE_BY_TYPE[ErrorType.PARSE]: "Failed to parse provider response.",
    ERROR_CODE_BY_TYPE[ErrorType.QUALITY]: "Provider quality gate failed.",
    ERROR_CODE_BY_TYPE[ErrorType.RUNTIME]: "Runtime error.",
    MISSING_API_KEY: "Required API key is not configured. Run `smart-search setup` or `smart-search config set <KEY> <value>`.",
    MINIMUM_PROFILE: (
        "Minimum profile not satisfied: configure at least one provider each for "
        "main_search, docs_search, and web_fetch."
    ),
    SEARCH_EMPTY: "Search returned no results.",
    SEARCH_FAILED: "Search failed or returned no results.",
    EVIDENCE_INSUFFICIENT: "Strict validation requires citable evidence sources.",
    FETCH_FAILED: "All extract providers failed to fetch content.",
    MAP_TIMEOUT: "Map request timed out.",
    MAP_HTTP_ERROR: "Map HTTP error.",
    MAP_ERROR: "Map request failed.",
    PROVIDER_TIMEOUT: "Provider request timed out.",
    PROVIDER_NETWORK: "Provider network error.",
    PROVIDER_RUNTIME: "Provider runtime error.",
    PROVIDER_EMPTY: "Provider returned empty results.",
    PARSE_FAILED: "Failed to parse provider response.",
}


def coerce_error_type(value: ErrorType | str | None) -> ErrorType | None:
    if value is None or value == "":
        return None
    if isinstance(value, ErrorType):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return ErrorType(text)
    except ValueError:
        return None


def error_code_for(error_type: ErrorType | str | None, *, error_code: str | None = None) -> str:
    if error_code:
        return error_code
    et = coerce_error_type(error_type)
    if et is None:
        return ""
    return ERROR_CODE_BY_TYPE[et]


def default_message(error_code: str, *, error_type: ErrorType | str | None = None) -> str:
    if error_code and error_code in DEFAULT_MESSAGES:
        return DEFAULT_MESSAGES[error_code]
    et = coerce_error_type(error_type)
    if et is not None:
        return DEFAULT_MESSAGES[ERROR_CODE_BY_TYPE[et]]
    return "Request failed."


def exit_code_for(error_type: ErrorType | str | None) -> int:
    et = coerce_error_type(error_type)
    if et is None:
        return EXIT_RUNTIME_ERROR
    return EXIT_CODE_BY_TYPE[et]


def exit_code_from_result(data: dict[str, Any]) -> int:
    if data.get("ok", False):
        return EXIT_OK
    return exit_code_for(data.get("error_type"))


def missing_api_key_message(key_name: str) -> str:
    return (
        f"{key_name} is not configured. "
        f"Run `smart-search setup`, or use `smart-search config set {key_name} <key>`."
    )


def error_fields(
    error_type: ErrorType | str | None,
    *,
    error: str = "",
    error_code: str | None = None,
) -> dict[str, str]:
    """Build the stable triple used on failed JSON payloads."""
    et = coerce_error_type(error_type)
    if et is None:
        return {"error_type": "", "error_code": "", "error": error or ""}
    code = error_code_for(et, error_code=error_code)
    message = error if error else default_message(code, error_type=et)
    return {"error_type": et.value, "error_code": code, "error": message}


def attach_error_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure `error_code` exists when `error_type` is set (idempotent)."""
    error_type = data.get("error_type") or ""
    if not error_type:
        data.setdefault("error_code", "")
        return data
    if not data.get("error_code"):
        data["error_code"] = error_code_for(error_type)
    return data
