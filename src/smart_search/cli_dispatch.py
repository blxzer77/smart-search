"""CLI argument parsing and command dispatch."""
from __future__ import annotations

import argparse
import asyncio
import json
from importlib import metadata
from pathlib import Path
from typing import Any

from .cli_format import _format_seconds, _print_result
from .errors import (
    EXIT_PARAMETER_ERROR,
    ErrorType,
    error_fields,
)


def _cli():
    """Lazy facade for monkeypatch points on smart_search.cli (tests patch cli.*)."""
    from . import cli as cli_mod

    return cli_mod


COMMAND_ALIASES = {
    "search": ["s"],
    "fetch": ["f"],
    "map": ["m"],
    "exa-search": ["exa", "x"],
    "exa-similar": ["xs"],
    "context7-library": ["c7", "ctx7"],
    "context7-docs": ["c7d", "c7docs", "ctx7-docs"],
    "research": ["rs"],
    "doctor": ["d"],
    "diagnose": ["diag"],
    "setup": ["init"],
    "config": ["cfg"],
}

CONFIG_COMMAND_ALIASES = {
    "path": ["p"],
    "list": ["ls", "l"],
    "set": ["s"],
    "unset": ["rm", "u"],
}


class SmartSearchArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)
def _get_version() -> str:
    root = Path(__file__).resolve().parents[2]
    package_json = root / "package.json"
    try:
        version = json.loads(package_json.read_text(encoding="utf-8")).get("version", "")
        if version:
            return str(version)
    except (OSError, json.JSONDecodeError):
        pass

    pyproject = root / "pyproject.toml"
    try:
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            if line.startswith("version = "):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass

    try:
        return metadata.version("smart-search")
    except metadata.PackageNotFoundError:
        pass

    return "unknown"
def _search_timeout_result(query: str, timeout: float, search_kwargs: dict[str, Any] | None = None) -> dict[str, Any]:
    seconds = _format_seconds(timeout)
    search_kwargs = search_kwargs or {}
    stream = search_kwargs.get("stream")
    if stream is None:
        stream = _cli().service.config.openai_compatible_stream
    model = search_kwargs.get("model") or _cli().service.config.openai_compatible_model
    return {
        "ok": False,
        **error_fields(ErrorType.NETWORK, error=f"Search timed out after {seconds} seconds", error_code="SEARCH_TIMEOUT"),
        "query": query,
        "content": "",
        "sources": [],
        "sources_count": 0,
        "primary_sources": [],
        "primary_sources_count": 0,
        "extra_sources": [],
        "extra_sources_count": 0,
        "source_warning": "",
        "routing_decision": {},
        "providers_used": [],
        "provider_attempts": [],
        "fallback_used": False,
        "validation_level": "",
        "timeout_seconds": timeout,
        "provider": search_kwargs.get("providers", "auto"),
        "model": model,
        "stream": stream,
        "diagnose_command": "smart-search diagnose openai-compatible --format markdown",
        "recommendation": "Run `smart-search diagnose openai-compatible --format markdown` to check whether OpenAI-compatible stream/no-stream search requests are hanging upstream.",
    }


def _research_timeout_result(query: str, timeout: float) -> dict[str, Any]:
    seconds = _format_seconds(timeout)
    return {
        "ok": False,
        **error_fields(ErrorType.NETWORK, error=f"Research timed out after {seconds} seconds", error_code="RESEARCH_TIMEOUT"),
        "question": query,
        "query": query,
        "final_answer": "",
        "content": "",
        "citations": [],
        "evidence_items": [],
        "gap_check": {"status": "failed", "gaps": [{"reason": "cli research timeout"}], "stop_reason": "timeout"},
        "provider_attempts": [],
        "fallback_used": False,
        "degraded": True,
        "timeout_seconds": timeout,
        "mode": "deep_research_execution",
    }


def _add_format_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=["json", "markdown", "content"], default="json")
    parser.add_argument("--output", default="", help="Write rendered output to a file.")


async def _run_async(args: argparse.Namespace) -> int:
    if args.command == "search":
        search_kwargs = {
            "platform": args.platform,
            "model": args.model,
            "extra_sources": args.extra_sources,
            "validation": args.validation,
            "fallback": args.fallback,
            "providers": args.providers,
        }
        if args.stream is not None:
            search_kwargs["stream"] = args.stream
        try:
            data = await asyncio.wait_for(
                _cli().service.search(args.query, **search_kwargs),
                timeout=args.timeout,
            )
        except asyncio.TimeoutError:
            data = _search_timeout_result(args.query, args.timeout, search_kwargs)
            return _print_result("search", data, args.format, args.output)
        return _print_result("search", data, args.format, args.output)
    if args.command == "fetch":
        data = await _cli().service.fetch(args.url)
        return _print_result("fetch", data, args.format, args.output)
    if args.command == "map":
        data = await _cli().service.map_site(
            args.url,
            instructions=args.instructions,
            max_depth=args.max_depth,
            max_breadth=args.max_breadth,
            limit=args.limit,
            timeout=args.timeout,
        )
        return _print_result("map", data, args.format, args.output)
    if args.command == "exa-search":
        data = await _cli().service.exa_search(
            args.query,
            num_results=args.num_results,
            search_type=args.search_type,
            include_text=args.include_text,
            include_highlights=args.include_highlights,
            start_published_date=args.start_published_date,
            include_domains=args.include_domains,
            exclude_domains=args.exclude_domains,
            category=args.category,
        )
        return _print_result("exa-search", data, args.format, args.output)
    if args.command == "exa-similar":
        data = await _cli().service.exa_find_similar(args.url, num_results=args.num_results)
        return _print_result("exa-similar", data, args.format, args.output)
    if args.command == "context7-library":
        data = await _cli().service.context7_library(args.name, args.query)
        return _print_result("context7-library", data, args.format, args.output)
    if args.command == "context7-docs":
        data = await _cli().service.context7_docs(args.library_id, args.query)
        return _print_result("context7-docs", data, args.format, args.output)
    if args.command == "research":
        try:
            data = await asyncio.wait_for(
                _cli().service.research(
                    args.query,
                    budget=args.budget,
                    evidence_dir=args.evidence_dir,
                    fallback=args.fallback,
                    locale_scope=args.locale_scope,
                    dry_run=args.dry_run,
                    progress=args.progress,
                ),
                timeout=args.timeout,
            )
        except asyncio.TimeoutError:
            data = _research_timeout_result(args.query, args.timeout)
            return _print_result("research", data, args.format, args.output)
        return _print_result("research", data, args.format, args.output)
    if args.command == "doctor":
        data = await _cli().service.doctor()
        return _print_result("doctor", data, args.format, args.output)
    if args.command == "diagnose":
        if args.diagnose_target == "openai-compatible":
            data = await _cli().service.diagnose_openai_compatible(timeout_seconds=args.timeout)
            return _print_result("diagnose", data, args.format, args.output)
        if args.diagnose_target == "xai":
            data = await _cli().service.diagnose_xai(timeout_seconds=args.timeout)
            return _print_result("diagnose", data, args.format, args.output)
        return _print_result(
            "diagnose",
            {
                "ok": False,
                **error_fields(ErrorType.PARAMETER, error=f"Unknown diagnose target: {args.diagnose_target}"),
            },
            args.format,
            args.output,
        )
    return EXIT_PARAMETER_ERROR


def _run_config(args: argparse.Namespace) -> int:
    if args.config_command == "path":
        data = _cli().service.config_path()
    elif args.config_command == "list":
        data = _cli().service.config_list(show_secrets=False)
    elif args.config_command == "set":
        data = _cli().service.config_set(args.key, args.value)
    elif args.config_command == "unset":
        data = _cli().service.config_unset(args.key)
    else:
        data = {"ok": False, **error_fields(ErrorType.PARAMETER, error="Unknown config command")}
    return _print_result("config", data, args.format, args.output)


def build_parser() -> argparse.ArgumentParser:
    parser = SmartSearchArgumentParser(
        prog="smart-search",
        description="Smart Search CLI for AI-agent web research.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Quick start:\n"
            "  1. smart-search setup\n"
            "  2. smart-search doctor --format json\n"
            "  3. smart-search research \"your question\" --format json\n"
            "\n"
            "If setup fails or configuration looks wrong, run:\n"
            "  smart-search doctor --format markdown\n"
            "On Windows, prefer one config location (%LOCALAPPDATA%\\smart-search or "
            "~\\.config\\smart-search); doctor warns when both exist."
        ),
    )
    parser.add_argument("-v", "--v", "--version", action="version", version=f"%(prog)s {_cli()._get_version()}")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=SmartSearchArgumentParser)

    search_parser = sub.add_parser(
        "search", aliases=COMMAND_ALIASES["search"], help="Run live web search via the configured main_search route (xAI Responses or OpenAI-compatible)."
    )
    search_parser.set_defaults(command="search")
    search_parser.add_argument("query")
    search_parser.add_argument("--platform", default="")
    search_parser.add_argument("--model", default="")
    search_parser.add_argument("--extra-sources", type=int, default=0)
    search_parser.add_argument("--validation", choices=["fast", "balanced", "strict"], default="")
    search_parser.add_argument("--fallback", choices=["auto", "off"], default="")
    search_parser.add_argument("--providers", default="auto")
    stream_group = search_parser.add_mutually_exclusive_group()
    stream_group.add_argument("--stream", dest="stream", action="store_true", default=None, help="Use stream=true for OpenAI-compatible main search.")
    stream_group.add_argument("--no-stream", dest="stream", action="store_false", help="Force stream=false for OpenAI-compatible main search.")
    search_parser.add_argument("--timeout", type=float, default=120, metavar="SECONDS", help="Hard timeout in seconds.")
    _add_format_args(search_parser)

    fetch_parser = sub.add_parser("fetch", aliases=COMMAND_ALIASES["fetch"], help="Fetch a URL as markdown.")
    fetch_parser.set_defaults(command="fetch")
    fetch_parser.add_argument("url")
    _add_format_args(fetch_parser)

    map_parser = sub.add_parser("map", aliases=COMMAND_ALIASES["map"], help="Map a website structure.")
    map_parser.set_defaults(command="map")
    map_parser.add_argument("url")
    map_parser.add_argument("--instructions", default="")
    map_parser.add_argument("--max-depth", type=int, default=1)
    map_parser.add_argument("--max-breadth", type=int, default=20)
    map_parser.add_argument("--limit", type=int, default=50)
    map_parser.add_argument("--timeout", type=int, default=150)
    _add_format_args(map_parser)

    exa_parser = sub.add_parser(
        "exa-search", aliases=COMMAND_ALIASES["exa-search"], help="Run Exa source-first search."
    )
    exa_parser.set_defaults(command="exa-search")
    exa_parser.add_argument("query")
    exa_parser.add_argument("--num-results", type=int, default=5)
    exa_parser.add_argument("--search-type", choices=["neural", "keyword", "auto"], default="neural")
    exa_parser.add_argument("--include-text", action="store_true")
    exa_parser.add_argument("--include-highlights", action="store_true")
    exa_parser.add_argument("--start-published-date", default="")
    exa_parser.add_argument("--include-domains", nargs="+", default="")
    exa_parser.add_argument("--exclude-domains", nargs="+", default="")
    exa_parser.add_argument("--category", default="")
    _add_format_args(exa_parser)

    similar_parser = sub.add_parser(
        "exa-similar", aliases=COMMAND_ALIASES["exa-similar"], help="Find pages similar to a URL with Exa."
    )
    similar_parser.set_defaults(command="exa-similar")
    similar_parser.add_argument("url")
    similar_parser.add_argument("--num-results", type=int, default=5)
    _add_format_args(similar_parser)

    context7_library_parser = sub.add_parser(
        "context7-library",
        aliases=COMMAND_ALIASES["context7-library"],
        help="Resolve Context7 library candidates.",
    )
    context7_library_parser.set_defaults(command="context7-library")
    context7_library_parser.add_argument("name")
    context7_library_parser.add_argument("query", nargs="?", default="")
    _add_format_args(context7_library_parser)

    context7_docs_parser = sub.add_parser(
        "context7-docs",
        aliases=COMMAND_ALIASES["context7-docs"],
        help="Fetch Context7 docs for a library.",
    )
    context7_docs_parser.set_defaults(command="context7-docs")
    context7_docs_parser.add_argument("library_id")
    context7_docs_parser.add_argument("query")
    _add_format_args(context7_docs_parser)

    research_parser = sub.add_parser(
        "research",
        aliases=COMMAND_ALIASES["research"],
        help="Run live Deep Research with provider-advantage routing and evidence-only synthesis.",
    )
    research_parser.set_defaults(command="research")
    research_parser.add_argument("query")
    research_parser.add_argument("--budget", choices=["quick", "standard", "deep"], default="deep")
    research_parser.add_argument("--evidence-dir", default="")
    research_parser.add_argument("--fallback", choices=["auto", "off"], default="auto")
    research_parser.add_argument(
        "--locale-scope",
        choices=["cn", "en", "both"],
        default="both",
        help="Bilingual web discovery: cn (Chinese), en (English), or both (default).",
    )
    research_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and print the research plan and routing preview without calling live providers.",
    )
    research_parser.add_argument(
        "--progress",
        action="store_true",
        help="Write staged execution progress lines to stderr.",
    )
    research_parser.add_argument(
        "--timeout",
        type=float,
        default=600,
        metavar="SECONDS",
        help="Hard timeout in seconds for the full research run (default: 600).",
    )
    _add_format_args(research_parser)

    doctor_parser = sub.add_parser(
        "doctor", aliases=COMMAND_ALIASES["doctor"], help="Show masked configuration and connection checks."
    )
    doctor_parser.set_defaults(command="doctor")
    _add_format_args(doctor_parser)

    diagnose_parser = sub.add_parser(
        "diagnose",
        aliases=COMMAND_ALIASES["diagnose"],
        help="Run focused troubleshooting checks for a provider.",
    )
    diagnose_parser.set_defaults(command="diagnose")
    diagnose_parser.add_argument("diagnose_target", choices=["openai-compatible", "xai"])
    diagnose_parser.add_argument("--timeout", type=float, default=30, metavar="SECONDS", help="Per search-shape probe timeout in seconds.")
    diagnose_parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    diagnose_parser.add_argument("--output", default="", help="Write rendered output to a file.")

    setup_parser = sub.add_parser(
        "setup", aliases=COMMAND_ALIASES["setup"], help="Interactively save local provider configuration."
    )
    setup_parser.set_defaults(command="setup")
    setup_parser.add_argument("--non-interactive", action="store_true", help="Only save values passed as flags.")
    setup_parser.add_argument("--lang", choices=["zh", "en"], default="", help="Interactive setup language.")
    setup_parser.add_argument("--advanced", action="store_true", help="Show every low-level config key in interactive setup.")
    setup_parser.add_argument("--xai-api-url", default="", help="Save XAI_API_URL.")
    setup_parser.add_argument("--xai-api-key", default="", help="Save XAI_API_KEY.")
    setup_parser.add_argument("--xai-model", default="", help="Save XAI_MODEL.")
    setup_parser.add_argument("--xai-tools", default="", help="Save XAI_TOOLS (web_search,x_search).")
    setup_parser.add_argument("--main-search-route", default="", help="Save SMART_SEARCH_MAIN_SEARCH_ROUTE (ordered CSV of xai-responses,openai-compatible).")
    setup_parser.add_argument("--openai-compatible-api-url", default="", help="Save OPENAI_COMPATIBLE_API_URL.")
    setup_parser.add_argument("--openai-compatible-api-key", default="", help="Save OPENAI_COMPATIBLE_API_KEY.")
    setup_parser.add_argument("--openai-compatible-model", default="", help="Save OPENAI_COMPATIBLE_MODEL.")
    setup_parser.add_argument("--openai-compatible-stream", default="", help="Save OPENAI_COMPATIBLE_STREAM.")
    setup_parser.add_argument("--validation-level", default="", help="Save SMART_SEARCH_VALIDATION_LEVEL.")
    setup_parser.add_argument("--fallback-mode", default="", help="Save SMART_SEARCH_FALLBACK_MODE.")
    setup_parser.add_argument("--minimum-profile", default="", help="Save SMART_SEARCH_MINIMUM_PROFILE.")
    setup_parser.add_argument("--exa-key", default="", help="Save EXA_API_KEY.")
    setup_parser.add_argument("--context7-key", default="", help="Save CONTEXT7_API_KEY.")
    setup_parser.add_argument("--jina-key", default="", help="Save JINA_API_KEY.")
    setup_parser.add_argument("--jina-reader-api-url", default="", help="Save JINA_READER_API_URL.")
    setup_parser.add_argument("--jina-respond-with", default="", help="Save JINA_RESPOND_WITH, e.g. readerlm-v2.")
    setup_parser.add_argument("--jina-timeout", default="", help="Save JINA_TIMEOUT_SECONDS.")
    setup_parser.add_argument("--tavily-api-url", default="", help="Save TAVILY_API_URL.")
    setup_parser.add_argument("--tavily-key", default="", help="Save TAVILY_API_KEY.")
    setup_parser.add_argument("--firecrawl-api-url", default="", help="Save FIRECRAWL_API_URL.")
    setup_parser.add_argument("--firecrawl-key", default="", help="Save FIRECRAWL_API_KEY.")
    _add_format_args(setup_parser)

    config_parser = sub.add_parser(
        "config", aliases=COMMAND_ALIASES["config"], help="Read or edit the local Smart Search config file."
    )
    config_parser.set_defaults(command="config")
    config_sub = config_parser.add_subparsers(dest="config_command", required=True, parser_class=SmartSearchArgumentParser)
    config_path = config_sub.add_parser("path", aliases=CONFIG_COMMAND_ALIASES["path"])
    config_path.set_defaults(config_command="path")
    _add_format_args(config_path)
    config_list = config_sub.add_parser("list", aliases=CONFIG_COMMAND_ALIASES["list"])
    config_list.set_defaults(config_command="list")
    _add_format_args(config_list)
    config_set = config_sub.add_parser("set", aliases=CONFIG_COMMAND_ALIASES["set"])
    config_set.set_defaults(config_command="set")
    config_set.add_argument("key")
    config_set.add_argument("value")
    _add_format_args(config_set)
    config_unset = config_sub.add_parser("unset", aliases=CONFIG_COMMAND_ALIASES["unset"])
    config_unset.set_defaults(config_command="unset")
    config_unset.add_argument("key")
    _add_format_args(config_unset)

    return parser
