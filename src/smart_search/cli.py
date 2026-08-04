"""Smart Search CLI entrypoint (thin glue over setup / format / dispatch)."""
from __future__ import annotations

import asyncio
import getpass
import sys

from . import service
from .cli_dispatch import (
    COMMAND_ALIASES,
    CONFIG_COMMAND_ALIASES,
    SmartSearchArgumentParser,
    _add_format_args,
    _get_version,
    _research_timeout_result,
    _run_async,
    _run_config,
    _search_timeout_result,
    build_parser,
)
from .cli_format import (
    _configured_text,
    _error_lines,
    _error_summary,
    _escape_unencodable_json_char,
    _exit_code,
    _format_config_markdown,
    _format_content,
    _format_diagnose_markdown,
    _format_doctor_markdown,
    _format_markdown,
    _format_result_markdown,
    _format_seconds,
    _format_setup_markdown,
    _json,
    _json_stdout_safe,
    _latency_text,
    _markdown_code_block,
    _markdown_table,
    _md_cell,
    _one_line,
    _plain_result_lines,
    _print_result,
    _provider_detail_lines,
    _render,
    _result_rows,
    _result_summary,
    _result_target,
    _result_title,
    _status_label,
    _stdout_safe,
    _stream_safe,
    _write_stderr,
    _write_stdout,
    _yes_no,
)
from .cli_setup import (
    FIRECRAWL_DEFAULT_API_URL,
    TAVILY_DEFAULT_API_URL,
    _STATIC_SMART_SEARCH_BANNER,
    _ascii_choice_values,
    _checkbox_with_tui,
    _display_provider,
    _is_interactive_setup_stream,
    _is_private_display_key,
    _is_secret_key,
    _is_tavily_hikari_key,
    _merge_setup_values,
    _normalize_custom_base_url,
    _normalize_firecrawl_api_url,
    _normalize_jina_reader_api_url,
    _normalize_tavily_api_url,
    _normalize_tavily_flag_api_url,
    _prompt_choice,
    _prompt_docs_search,
    _prompt_firecrawl_api_url,
    _prompt_main_search,
    _prompt_optional_enhancements,
    _prompt_provider_multi_select,
    _prompt_select,
    _prompt_tavily_api_url,
    _prompt_value,
    _prompt_web_fetch,
    _prompt_yes_no,
    _provider_choices,
    _run_advanced_setup_prompts,
    _run_guided_setup_prompts,
    _run_setup,
    _select_setup_language,
    _select_with_tui,
    _setup_choice,
    _setup_status_from_values,
    _smart_search_banner_text,
    _t,
    _with_scheme,
    _write_panel,
    _write_setup_banner,
    _write_setup_examples,
    _write_setup_keep_note,
    _write_setup_status,
)
from .errors import (
    EXIT_CONFIG_ERROR,
    EXIT_NETWORK_ERROR,
    EXIT_OK,
    EXIT_PARAMETER_ERROR,
    EXIT_RUNTIME_ERROR,
    ErrorType,
    attach_error_fields,
    error_fields,
    exit_code_from_result,
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "setup":
            return _run_setup(args)
        if args.command == "config":
            return _run_config(args)
        return asyncio.run(_run_async(args))
    except KeyboardInterrupt:
        return EXIT_RUNTIME_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
