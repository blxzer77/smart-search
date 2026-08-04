"""Interactive / guided setup wizard for Smart Search CLI."""
from __future__ import annotations

import argparse
import contextlib
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .cli_format import _print_result, _stream_safe, _write_stderr


def _cli():
    """Lazy facade for monkeypatch points on smart_search.cli (tests patch cli.*)."""
    from . import cli as cli_mod

    return cli_mod


TAVILY_DEFAULT_API_URL = "https://api.tavily.com"
FIRECRAWL_DEFAULT_API_URL = "https://api.firecrawl.dev/v2"

_STATIC_SMART_SEARCH_BANNER = r"""
 ____                       _     ____                      _
/ ___| _ __ ___   __ _ _ __| |_  / ___|  ___  __ _ _ __ ___| |__
\___ \| '_ ` _ \ / _` | '__| __| \___ \ / _ \/ _` | '__/ __| '_ \
 ___) | | | | | | (_| | |  | |_   ___) |  __/ (_| | | | (__| | | |
|____/|_| |_| |_|\__,_|_|   \__| |____/ \___|\__,_|_|  \___|_| |_|
""".strip("\n")


def _smart_search_banner_text() -> str:
    try:
        import pyfiglet

        banner = pyfiglet.figlet_format("Smart Search", font="slant")
        return banner.rstrip()
    except Exception:
        return _STATIC_SMART_SEARCH_BANNER


def _write_setup_banner(lang: str) -> None:
    banner = _smart_search_banner_text()
    tagline = _t(lang, "CLI-first multi-source search for AI agents", "CLI-first multi-source search for AI agents")
    _write_stderr(f"\n{banner}\n\n   Smart Search\n   {tagline}\n")


def _write_panel(text: str, lang: str) -> None:
    if not _is_interactive_setup_stream():
        _write_stderr(text)
        return
    try:
        from rich.console import Console
        from rich.panel import Panel
    except Exception:
        _write_stderr(text)
        return
    console = Console(file=_cli().sys.stderr, force_terminal=True)
    title = _t(lang, "Smart Search 配置", "Smart Search Setup")
    console.print(Panel(text.strip(), title=title, expand=False, safe_box=True))


def _is_secret_key(key: str) -> bool:
    upper_key = key.upper()
    return "KEY" in upper_key or "TOKEN" in upper_key or "SECRET" in upper_key


def _is_private_display_key(key: str) -> bool:
    return key.upper().endswith("_URL") or key.upper().endswith("_BASE_URL")


def _t(lang: str, zh: str, en: str) -> str:
    return zh if lang == "zh" else en


def _display_provider(provider: str, lang: str) -> str:
    names = {
        "openai-compatible": "OpenAI-compatible",
        "exa": "Exa",
        "context7": "Context7",
        "jina": "Jina Reader",
        "tavily": "Tavily",
        "firecrawl": "Firecrawl",
    }
    return names.get(provider, provider)


def _with_scheme(url: str) -> str:
    value = url.strip()
    if not value:
        return ""
    if "://" not in value:
        return f"https://{value}"
    return value


def _normalize_custom_base_url(url: str) -> str:
    value = _with_scheme(url).strip()
    return value.rstrip("/") if value else ""


def _normalize_tavily_api_url(url: str, *, hikari: bool = True) -> str:
    value = _normalize_custom_base_url(url)
    if not value:
        return ""
    parsed = urlsplit(value)
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    if host == "api.tavily.com":
        return urlunsplit((parsed.scheme, parsed.netloc, path or "", "", ""))
    if hikari and path in {"", "/mcp"}:
        return urlunsplit((parsed.scheme, parsed.netloc, "/api/tavily", "", ""))
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _normalize_tavily_flag_api_url(url: str, api_key: str = "") -> str:
    value = _normalize_custom_base_url(url)
    if not value:
        return ""
    parsed = urlsplit(value)
    path = parsed.path.rstrip("/")
    if path == "/mcp" or _is_tavily_hikari_key(api_key):
        return _normalize_tavily_api_url(value)
    return _normalize_tavily_api_url(value, hikari=False)


def _normalize_firecrawl_api_url(url: str) -> str:
    return _normalize_custom_base_url(url)


def _normalize_jina_reader_api_url(url: str) -> str:
    return _normalize_custom_base_url(url)


def _is_tavily_hikari_key(api_key: str) -> bool:
    return api_key.strip().lower().startswith("th-")


def _is_interactive_setup_stream() -> bool:
    return bool(getattr(_cli().sys.stdin, "isatty", lambda: False)() and getattr(_cli().sys.stderr, "isatty", lambda: False)())


def _setup_status_from_values(values: dict[str, str]) -> dict[str, Any]:
    def has(key: str) -> bool:
        return bool(values.get(key))

    main_configured: set[str] = set()
    if has("XAI_API_KEY"):
        main_configured.add("xai-responses")
    if has("OPENAI_COMPATIBLE_API_URL") and has("OPENAI_COMPATIBLE_API_KEY"):
        main_configured.add("openai-compatible")

    status = {
        "main_search": {
            "configured": [provider for provider in ("xai-responses", "openai-compatible") if provider in main_configured],
            "fallback_chain": ["xai-responses", "openai-compatible"],
        },
        "web_search": {
            "configured": [
                provider
                for provider, configured in [
                    ("tavily", has("TAVILY_API_KEY")),
                    ("firecrawl", has("FIRECRAWL_API_KEY")),
                ]
                if configured
            ],
            "fallback_chain": ["tavily", "firecrawl"],
        },
        "docs_search": {
            "configured": [
                provider
                for provider, configured in [
                    ("context7", has("CONTEXT7_API_KEY")),
                    ("exa", has("EXA_API_KEY")),
                ]
                if configured
            ],
            "fallback_chain": ["context7", "exa"],
        },
        "web_fetch": {
            "configured": [
                provider
                for provider, configured in [
                    ("tavily", has("TAVILY_API_KEY")),
                    ("jina", has("JINA_API_KEY")),
                    ("firecrawl", has("FIRECRAWL_API_KEY")),
                ]
                if configured
            ],
            "fallback_chain": ["tavily", "jina", "firecrawl"],
        },
    }
    for item in status.values():
        item["ok"] = bool(item["configured"])
    return status


def _merge_setup_values(current: dict[str, str], values: dict[str, str]) -> dict[str, str]:
    merged = dict(current)
    merged.update({key: value for key, value in values.items() if value})
    return merged


def _write_setup_status(status: dict[str, Any], lang: str, *, final: bool = False) -> None:
    title = _t(lang, "最低配置检查", "Minimum profile check") if final else _t(lang, "当前状态", "Current status")
    _write_stderr(f"\n{title}:\n")
    required = {"main_search", "docs_search", "web_fetch"}
    labels = {
        "main_search": _t(lang, "main_search 主搜索", "main_search primary search"),
        "docs_search": _t(lang, "docs_search 文档搜索", "docs_search documentation search"),
        "web_fetch": _t(lang, "web_fetch 网页抓取", "web_fetch page fetch"),
        "web_search": _t(lang, "web_search 网页补强", "web_search web reinforcement"),
    }
    for capability in ("main_search", "docs_search", "web_fetch", "web_search"):
        item = status.get(capability, {})
        configured = item.get("configured") or []
        configured_text = ", ".join(_display_provider(provider, lang) for provider in configured)
        if item.get("ok"):
            marker = "OK"
            value = configured_text
        elif capability in required:
            marker = "MISSING"
            value = _t(lang, "需要至少配置一个 provider", "at least one provider is required")
        else:
            marker = "OPTIONAL"
            value = _t(lang, "未配置", "not configured")
        _write_stderr(f"  [{marker}] {labels[capability]}: {value}\n")


def _prompt_choice(prompt: str, default: str = "") -> str:
    _write_stderr(prompt)
    value = input("").strip()
    return value or default


def _prompt_yes_no(prompt: str, default: bool = False) -> bool:
    default_text = "Y/n" if default else "y/N"
    answer = _prompt_choice(f"{prompt} [{default_text}]: ", "y" if default else "n").strip().lower()
    return answer in {"y", "yes", "是", "好", "1", "true"}


def _prompt_value(key: str, label: str, current: str = "", optional: bool = False, lang: str = "en") -> str:
    suffix = _t(lang, " 可选", " optional") if optional else _t(lang, " 必填", " required")
    current_display = (
        _t(lang, "已配置，回车保留", "configured, press Enter to keep")
        if current and (_is_secret_key(key) or _is_private_display_key(key))
        else current
    )
    if current:
        prompt = f"{label}{suffix} [{current_display}]: "
    else:
        prompt = f"{label}{suffix}: "
    if _is_secret_key(key):
        value = _cli().getpass.getpass(_stream_safe(_cli().sys.stderr, prompt)).strip()
    else:
        _write_stderr(prompt)
        value = input("").strip()
    return value or current


def _ascii_choice_values(choices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {**choice, "name": _stream_safe(_cli().sys.stderr, str(choice.get("name", "")))}
        for choice in choices
    ]


def _select_with_tui(message: str, choices: list[dict[str, Any]], default: Any = None) -> Any:
    if not _is_interactive_setup_stream():
        return None
    try:
        from InquirerPy import inquirer
    except Exception:
        return None
    try:
        with contextlib.redirect_stdout(_cli().sys.stderr):
            return inquirer.select(
                message=_stream_safe(_cli().sys.stderr, message),
                choices=_ascii_choice_values(choices),
                default=default,
                qmark="",
                pointer=">",
                marker=">",
            ).execute()
    except (KeyboardInterrupt, EOFError):
        raise
    except Exception:
        return None


def _checkbox_with_tui(message: str, choices: list[dict[str, Any]]) -> list[str] | None:
    if not _is_interactive_setup_stream():
        return None
    try:
        from InquirerPy import inquirer
    except Exception:
        return None
    try:
        with contextlib.redirect_stdout(_cli().sys.stderr):
            result = inquirer.checkbox(
                message=_stream_safe(_cli().sys.stderr, message),
                choices=_ascii_choice_values(choices),
                instruction="(Up/Down move, Space select, Enter confirm)",
                qmark="",
                pointer=">",
                enabled_symbol="[x]",
                disabled_symbol="[ ]",
            ).execute()
        return [str(item) for item in result]
    except (KeyboardInterrupt, EOFError):
        raise
    except Exception:
        return None


def _provider_choices(providers: list[str], selected: list[str], lang: str) -> list[dict[str, Any]]:
    selected_set = set(selected)
    return [
        {"name": _display_provider(provider, lang), "value": provider, "enabled": provider in selected_set}
        for provider in providers
    ]


def _prompt_provider_multi_select(
    message: str,
    providers: list[str],
    default_selected: list[str],
    lang: str,
) -> list[str]:
    tui_value = _cli()._checkbox_with_tui(message, _provider_choices(providers, default_selected, lang))
    if tui_value is not None:
        return [provider for provider in providers if provider in set(tui_value)]

    default_text = ",".join(default_selected) if default_selected else "skip"
    _write_stderr(f"{message} [{'/'.join(providers)}/skip] ({default_text}): ")
    raw = input("").strip().lower()
    if not raw:
        return [provider for provider in providers if provider in set(default_selected)]
    aliases = {
        "跳过": "skip",
        "无": "skip",
        "n": "skip",
        "no": "skip",
        "否": "skip",
        "都配": "all",
        "全部": "all",
        "两个": "all",
        "both": "all",
        "all": "all",
        "openai": "openai-compatible",
        "ctx7": "context7",
        "context": "context7",
    }
    tokens = [aliases.get(part.strip(), part.strip()) for part in raw.replace("+", ",").replace(";", ",").split(",")]
    if len(tokens) == 1 and " " in tokens[0]:
        tokens = [aliases.get(part.strip(), part.strip()) for part in tokens[0].split()]
    if "skip" in tokens or "none" in tokens:
        return []
    if "all" in tokens:
        return providers
    selected = [provider for provider in providers if provider in tokens]
    return selected if selected else [provider for provider in providers if provider in set(default_selected)]


def _prompt_select(message: str, choices: list[dict[str, Any]], default: str) -> str:
    tui_value = _cli()._select_with_tui(message, choices, default)
    if tui_value is not None:
        return str(tui_value)
    choice_values = [str(choice["value"]) for choice in choices]
    _write_stderr(f"{message} [{'/'.join(choice_values)}] ({default}): ")
    value = input("").strip().lower()
    return value if value in set(choice_values) else default


def _select_setup_language(lang: str = "") -> str:
    if lang in {"zh", "en"}:
        return lang
    choices = [
        {"name": "中文", "value": "zh"},
        {"name": "English", "value": "en"},
    ]
    answer = _cli()._prompt_select("Language / 语言", choices, "zh").strip().lower()
    if answer in {"en", "english"}:
        return "en"
    return "zh"


def _setup_choice(prompt: str, choices: set[str], default: str) -> str:
    value = _prompt_choice(prompt, default).strip().lower()
    aliases = {
        "保持": "keep",
        "跳过": "skip",
        "都配": "both",
        "两个": "both",
        "是": "yes",
        "否": "no",
    }
    value = aliases.get(value, value)
    return value if value in choices else default


def _prompt_main_search(values: dict[str, str], current: dict[str, str], lang: str) -> None:
    status = _setup_status_from_values(_merge_setup_values(current, values))
    configured = status["main_search"]["configured"]
    default_selected = configured or ["xai-responses"]
    _write_stderr(
        _t(
            lang,
            "\n[1/3 必选] main_search 主搜索\n用途: 负责综合搜索回答和最终合成。\n推荐: 二选一——xAI Responses（Grok，自带 server-side 联网）或 OpenAI-compatible 中转服务。\n",
            "\n[1/3 Required] main_search primary search\nPurpose: broad search answers and final synthesis.\nRecommended: pick one — xAI Responses (Grok with server-side web search) or an OpenAI-compatible relay.\n",
        )
    )
    selected = _prompt_provider_multi_select(
        _t(
            lang,
            "选择 main_search provider",
            "Choose main_search providers",
        ),
        ["xai-responses", "openai-compatible"],
        default_selected,
        lang,
    )
    if "xai-responses" in selected:
        values["XAI_API_KEY"] = _cli()._prompt_value(
            "XAI_API_KEY",
            _t(
                lang,
                "xAI API key（console.x.ai）",
                "xAI API key (console.x.ai)",
            ),
            current.get("XAI_API_KEY", ""),
            lang=lang,
        )
        values["XAI_MODEL"] = _cli()._prompt_value(
            "XAI_MODEL",
            _t(lang, "xAI 模型（默认 grok-4.5）", "xAI model (default grok-4.5)"),
            current.get("XAI_MODEL", ""),
            optional=True,
            lang=lang,
        )
        values["XAI_TOOLS"] = _cli()._prompt_value(
            "XAI_TOOLS",
            _t(lang, "xAI server-side 工具（web_search,x_search）", "xAI server-side tools (web_search,x_search)"),
            current.get("XAI_TOOLS", ""),
            optional=True,
            lang=lang,
        )
    if "openai-compatible" in selected:
        values["OPENAI_COMPATIBLE_API_URL"] = _cli()._prompt_value(
            "OPENAI_COMPATIBLE_API_URL",
            _t(
                lang,
                "OpenAI-compatible API 地址（示例: https://api.openai.com/v1）",
                "OpenAI-compatible API URL (example: https://api.openai.com/v1)",
            ),
            current.get("OPENAI_COMPATIBLE_API_URL", ""),
            lang=lang,
        )
        values["OPENAI_COMPATIBLE_API_KEY"] = _cli()._prompt_value(
            "OPENAI_COMPATIBLE_API_KEY",
            "OpenAI-compatible API key",
            current.get("OPENAI_COMPATIBLE_API_KEY", ""),
            lang=lang,
        )
        values["OPENAI_COMPATIBLE_MODEL"] = _cli()._prompt_value(
            "OPENAI_COMPATIBLE_MODEL",
            _t(lang, "OpenAI-compatible 模型", "OpenAI-compatible model"),
            current.get("OPENAI_COMPATIBLE_MODEL", ""),
            optional=True,
            lang=lang,
        )
        stream_default = current.get("OPENAI_COMPATIBLE_STREAM", "")
        if _prompt_yes_no(
            _t(
                lang,
                f"是否启用 OpenAI-compatible stream=true？用于部分中转长请求兼容 [{stream_default or 'false'}]: ",
                f"Enable OpenAI-compatible stream=true for relay long-request compatibility [{stream_default or 'false'}]: ",
            ),
            default=(str(stream_default).lower() in {"true", "1", "yes"}),
        ):
            values["OPENAI_COMPATIBLE_STREAM"] = "true"
        elif stream_default:
            values["OPENAI_COMPATIBLE_STREAM"] = "false"

    merged_status = _setup_status_from_values(_merge_setup_values(current, values))
    main_configured = [provider for provider in ("xai-responses", "openai-compatible") if provider in merged_status["main_search"]["configured"]]
    if len(main_configured) < 2:
        return
    current_route = current.get("SMART_SEARCH_MAIN_SEARCH_ROUTE", "")
    route_choices = [
        {"name": "xAI Responses 优先（xai-responses,openai-compatible）", "value": "xai-responses,openai-compatible"},
        {"name": "OpenAI-compatible 优先（openai-compatible,xai-responses）", "value": "openai-compatible,xai-responses"},
        {"name": _t(lang, "仅用 xAI Responses（不跨路由）", "xAI Responses only (no cross-route fallback)"), "value": "xai-responses"},
        {"name": _t(lang, "仅用 OpenAI-compatible（不跨路由）", "OpenAI-compatible only (no cross-route fallback)"), "value": "openai-compatible"},
    ]
    default_route = current_route if current_route in {choice["value"] for choice in route_choices} else "xai-responses,openai-compatible"
    values["SMART_SEARCH_MAIN_SEARCH_ROUTE"] = _cli()._prompt_select(
        _t(
            lang,
            "两个 main_search 均已配置，选择优先路由",
            "Both main_search providers are configured; choose the priority route",
        ),
        route_choices,
        default_route,
    )


def _prompt_docs_search(values: dict[str, str], current: dict[str, str], lang: str) -> None:
    status = _setup_status_from_values(_merge_setup_values(current, values))
    default_selected = status["docs_search"]["configured"] or ["context7"]
    _write_stderr(
        _t(
            lang,
            "\n[2/3 必选] docs_search 文档搜索\n用途: 查官方文档、SDK、API、框架和库说明。\n推荐: 文档/API/库优先 Context7；官方域名、论文和低噪声发现再配 Exa。\n",
            "\n[2/3 Required] docs_search documentation search\nPurpose: official docs, SDKs, APIs, frameworks, and library references.\nRecommended: Context7 for docs/API/library intent; Exa for official domains, papers, and low-noise discovery.\n",
        )
    )
    selected = _prompt_provider_multi_select(
        _t(
            lang,
            "选择 docs_search provider",
            "Choose docs_search providers",
        ),
        ["exa", "context7"],
        default_selected,
        lang,
    )
    if "exa" in selected:
        values["EXA_API_KEY"] = _cli()._prompt_value("EXA_API_KEY", "Exa API key", current.get("EXA_API_KEY", ""), lang=lang)
    if "context7" in selected:
        values["CONTEXT7_API_KEY"] = _cli()._prompt_value(
            "CONTEXT7_API_KEY",
            "Context7 API key",
            current.get("CONTEXT7_API_KEY", ""),
            lang=lang,
        )


def _prompt_tavily_api_url(values: dict[str, str], current: dict[str, str], lang: str) -> None:
    current_url = current.get("TAVILY_API_URL", "")
    tavily_key = values.get("TAVILY_API_KEY") or current.get("TAVILY_API_KEY", "")
    if current_url:
        default_choice = "current"
    elif _is_tavily_hikari_key(tavily_key):
        default_choice = "hikari"
    else:
        default_choice = "official"
    choices = []
    if current_url:
        choices.append({"name": _t(lang, "保留当前地址（已配置）", "Keep current URL (configured)"), "value": "current"})
    choices.extend([
        {"name": _t(lang, "官方 Tavily (https://api.tavily.com)", "Official Tavily (https://api.tavily.com)"), "value": "official"},
        {"name": _t(lang, "Tavily Hikari / 号池", "Tavily Hikari / pooled endpoint"), "value": "hikari"},
        {"name": _t(lang, "自定义 Tavily REST base", "Custom Tavily REST base"), "value": "custom"},
    ])
    choice = _cli()._prompt_select(_t(lang, "选择 Tavily endpoint", "Choose Tavily endpoint"), choices, default_choice)
    if choice == "current":
        return
    if choice == "official":
        values["TAVILY_API_URL"] = TAVILY_DEFAULT_API_URL
        return
    if choice == "hikari":
        _write_stderr(
            _t(
                lang,
                "号池地址填服务商给你的域名或 URL，例如 https://pool.example.com 或 https://pool.example.com/mcp；setup 会保存为 https://pool.example.com/api/tavily。\n",
                "For pooled endpoints, paste the provider domain or URL, for example https://pool.example.com or https://pool.example.com/mcp; setup saves it as https://pool.example.com/api/tavily.\n",
            )
        )
    label = _t(
        lang,
        "Tavily REST 地址",
        "Tavily REST URL",
    )
    raw = _cli()._prompt_value("TAVILY_API_URL", label, current_url, optional=False, lang=lang)
    normalized = _normalize_tavily_api_url(raw) if choice == "hikari" else _normalize_tavily_api_url(raw, hikari=False)
    if normalized:
        values["TAVILY_API_URL"] = normalized
        if normalized != raw.rstrip("/"):
            _write_stderr(_t(lang, f"已规范化 Tavily REST base: {normalized}\n", f"Normalized Tavily REST base: {normalized}\n"))


def _prompt_firecrawl_api_url(values: dict[str, str], current: dict[str, str], lang: str) -> None:
    current_url = current.get("FIRECRAWL_API_URL", "")
    choices = []
    if current_url:
        choices.append({"name": _t(lang, "保留当前地址（已配置）", "Keep current URL (configured)"), "value": "current"})
    choices.extend([
        {
            "name": _t(
                lang,
                "官方 Firecrawl (https://api.firecrawl.dev/v2)",
                "Official Firecrawl (https://api.firecrawl.dev/v2)",
            ),
            "value": "official",
        },
        {"name": _t(lang, "自定义 Firecrawl REST base", "Custom Firecrawl REST base"), "value": "custom"},
    ])
    default_choice = "current" if current_url else "official"
    choice = _cli()._prompt_select(_t(lang, "选择 Firecrawl endpoint", "Choose Firecrawl endpoint"), choices, default_choice)
    if choice == "current":
        return
    if choice == "official":
        values["FIRECRAWL_API_URL"] = FIRECRAWL_DEFAULT_API_URL
        return
    raw = _cli()._prompt_value(
        "FIRECRAWL_API_URL",
        _t(lang, "Firecrawl 自定义 REST base", "Firecrawl custom REST base"),
        current_url,
        optional=False,
        lang=lang,
    )
    normalized = _normalize_firecrawl_api_url(raw)
    if normalized:
        values["FIRECRAWL_API_URL"] = normalized


def _prompt_web_fetch(values: dict[str, str], current: dict[str, str], lang: str) -> None:
    status = _setup_status_from_values(_merge_setup_values(current, values))
    default_selected = status["web_fetch"]["configured"] or ["tavily"]
    _write_stderr(
        _t(
            lang,
            "\n[3/3 必选] web_fetch 网页抓取\n用途: 已知 URL 抓正文；高风险事实核验必须用。\n推荐: Tavily 优先；Jina 需要 key 才算标准配置；Firecrawl 可作为抓取兜底。\n",
            "\n[3/3 Required] web_fetch page fetch\nPurpose: extract known URLs; required for high-risk fact checks.\nRecommended: Tavily first; Jina requires a key to satisfy standard config; Firecrawl as fetch fallback.\n",
        )
    )
    selected = _prompt_provider_multi_select(
        _t(
            lang,
            "选择 web_fetch provider",
            "Choose web_fetch providers",
        ),
        ["tavily", "jina", "firecrawl"],
        default_selected,
        lang,
    )
    if "tavily" in selected:
        values["TAVILY_API_KEY"] = _cli()._prompt_value("TAVILY_API_KEY", "Tavily API key", current.get("TAVILY_API_KEY", ""), lang=lang)
        _prompt_tavily_api_url(values, current, lang)
    if "jina" in selected:
        values["JINA_API_KEY"] = _cli()._prompt_value("JINA_API_KEY", "Jina API key", current.get("JINA_API_KEY", ""), lang=lang)
        raw_url = _cli()._prompt_value(
            "JINA_READER_API_URL",
            "Jina Reader API URL",
            current.get("JINA_READER_API_URL", "https://r.jina.ai"),
            optional=True,
            lang=lang,
        )
        values["JINA_READER_API_URL"] = _normalize_jina_reader_api_url(raw_url)
    if "firecrawl" in selected:
        values["FIRECRAWL_API_KEY"] = _cli()._prompt_value(
            "FIRECRAWL_API_KEY",
            "Firecrawl API key",
            current.get("FIRECRAWL_API_KEY", ""),
            lang=lang,
        )
        _prompt_firecrawl_api_url(values, current, lang)


def _prompt_optional_enhancements(values: dict[str, str], current: dict[str, str], lang: str) -> None:
    _write_stderr(
        _t(
            lang,
            "\n[可选增强] web_search 网页补强\n用途: 通过 Tavily / Firecrawl 做中英双语来源检索。\n",
            "\n[Optional] web_search web reinforcement\nPurpose: bilingual Chinese/English source discovery through Tavily / Firecrawl.\n",
        )
    )
    if _prompt_yes_no(_t(lang, "是否调整验证/兜底默认值?", "Adjust validation/fallback defaults?"), default=False):
        values["SMART_SEARCH_VALIDATION_LEVEL"] = _cli()._prompt_value(
            "SMART_SEARCH_VALIDATION_LEVEL",
            _t(lang, "验证强度 (fast/balanced/strict)", "Validation level (fast/balanced/strict)"),
            current.get("SMART_SEARCH_VALIDATION_LEVEL", ""),
            optional=True,
            lang=lang,
        )
        values["SMART_SEARCH_FALLBACK_MODE"] = _cli()._prompt_value(
            "SMART_SEARCH_FALLBACK_MODE",
            _t(lang, "兜底模式 (auto/off)", "Fallback mode (auto/off)"),
            current.get("SMART_SEARCH_FALLBACK_MODE", ""),
            optional=True,
            lang=lang,
        )
        values["SMART_SEARCH_MINIMUM_PROFILE"] = _cli()._prompt_value(
            "SMART_SEARCH_MINIMUM_PROFILE",
            _t(lang, "最低配置门槛 (standard/off)", "Minimum profile (standard/off)"),
            current.get("SMART_SEARCH_MINIMUM_PROFILE", ""),
            optional=True,
            lang=lang,
        )


def _write_setup_keep_note(lang: str) -> None:
    _write_stderr(
        _t(
            lang,
            "\n提示: setup 不会删除旧配置；删除请运行 `smart-search config unset KEY`。\n",
            "\nNote: setup does not delete saved values; use `smart-search config unset KEY` to remove one.\n",
        )
    )


def _write_setup_examples(lang: str) -> None:
    _write_stderr(
        _t(
            lang,
            "\n不知道怎么填: 先配齐 main_search + docs_search + web_fetch。\n"
            "  main_search: 二选一即可——xAI Responses（填 XAI_API_KEY）或 OpenAI-compatible（示例: https://api.openai.com/v1）；都配则需选优先路由。\n"
            "  docs_search: 文档/API 优先 Context7；官方域名、论文和低噪声发现再配 Exa。\n"
            "  web_fetch: Tavily 官方地址是 https://api.tavily.com；号池填 https://<host>/api/tavily。\n"
            "  key 都填你自己控制台里的；Firecrawl 可之后再补。\n",
            "\nIf unsure: first configure main_search + docs_search + web_fetch.\n"
            "  main_search: pick ONE — xAI Responses (set XAI_API_KEY) or OpenAI-compatible (example: https://api.openai.com/v1); if both are set you must choose a priority route.\n"
            "  docs_search: Context7 for docs/API first; add Exa for official domains, papers, and low-noise discovery.\n"
            "  web_fetch: official Tavily endpoint is https://api.tavily.com; pooled endpoints use https://<host>/api/tavily.\n"
            "  Use keys from your own provider consoles. Firecrawl can be added later.\n",
        )
    )


def _run_guided_setup_prompts(
    values: dict[str, str],
    current: dict[str, str],
    lang: str,
    *,
    show_banner: bool = True,
) -> None:
    config_file = _cli().service.config_path()["config_file"]
    if show_banner:
        _write_setup_banner(lang)
    _write_panel(
        _t(
            lang,
            f"\nSmart Search 配置向导\n配置文件: {config_file}\n\n目标: standard 最低可用配置\n操作: 方向键移动，空格勾选，回车确认；API key 输入不显示。\n最低要求: main_search + docs_search + web_fetch 各至少一个 provider。\n",
            f"\nSmart Search setup wizard\nConfig file: {config_file}\n\nGoal: standard minimum profile\nKeys: move with arrow keys, select with Space, confirm with Enter; API key input is hidden.\nMinimum: at least one provider in each of main_search + docs_search + web_fetch.\n",
        ),
        lang,
    )
    _write_setup_keep_note(lang)
    _write_setup_examples(lang)
    _write_setup_status(_setup_status_from_values(_merge_setup_values(current, values)), lang)
    _prompt_main_search(values, current, lang)
    _prompt_docs_search(values, current, lang)
    _prompt_web_fetch(values, current, lang)
    _prompt_optional_enhancements(values, current, lang)


def _run_advanced_setup_prompts(values: dict[str, str], current: dict[str, str], lang: str) -> None:
    _write_stderr(
        _t(
            lang,
            "\n高级模式: 逐项配置底层键。一般用户建议直接使用默认分组向导。\n",
            "\nAdvanced mode: configure low-level keys one by one. Most users should use the grouped wizard.\n",
        )
    )
    prompts = [
        ("XAI_API_URL", "xAI Responses API URL", True),
        ("XAI_API_KEY", "xAI API key", True),
        ("XAI_MODEL", "xAI model", True),
        ("XAI_TOOLS", "xAI server-side tools (web_search,x_search)", True),
        ("OPENAI_COMPATIBLE_API_URL", "OpenAI-compatible API URL", True),
        ("OPENAI_COMPATIBLE_API_KEY", "OpenAI-compatible API key", True),
        ("OPENAI_COMPATIBLE_MODEL", "OpenAI-compatible model", True),
        ("OPENAI_COMPATIBLE_STREAM", "OpenAI-compatible stream mode (true/false)", True),
        ("SMART_SEARCH_MAIN_SEARCH_ROUTE", "Main search route CSV (xai-responses,openai-compatible)", True),
        ("SMART_SEARCH_VALIDATION_LEVEL", "Validation level (fast/balanced/strict)", True),
        ("SMART_SEARCH_FALLBACK_MODE", "Fallback mode (auto/off)", True),
        ("SMART_SEARCH_MINIMUM_PROFILE", "Minimum profile (standard/off)", True),
        ("EXA_API_KEY", "Exa API key", True),
        ("CONTEXT7_API_KEY", "Context7 API key", True),
        ("JINA_API_KEY", "Jina API key", True),
        ("JINA_READER_API_URL", "Jina Reader API URL", True),
        ("JINA_RESPOND_WITH", "Jina respond-with mode (optional, e.g. readerlm-v2)", True),
        ("JINA_TIMEOUT_SECONDS", "Jina timeout seconds", True),
        ("TAVILY_API_URL", "Tavily API URL", True),
        ("TAVILY_API_KEY", "Tavily API key", True),
        ("FIRECRAWL_API_URL", "Firecrawl API URL", True),
        ("FIRECRAWL_API_KEY", "Firecrawl API key", True),
    ]
    for key, label, optional in prompts:
        if values[key]:
            continue
        value = _cli()._prompt_value(key, label, current.get(key, ""), optional=optional, lang=lang)
        if key == "TAVILY_API_URL":
            value = _normalize_tavily_api_url(value)
        elif key == "FIRECRAWL_API_URL":
            value = _normalize_firecrawl_api_url(value)
        elif key == "JINA_READER_API_URL":
            value = _normalize_jina_reader_api_url(value)
        values[key] = value


def _run_setup(args: argparse.Namespace) -> int:
    values = {
        "XAI_API_URL": args.xai_api_url,
        "XAI_API_KEY": args.xai_api_key,
        "XAI_MODEL": args.xai_model,
        "XAI_TOOLS": args.xai_tools,
        "OPENAI_COMPATIBLE_API_URL": args.openai_compatible_api_url,
        "OPENAI_COMPATIBLE_API_KEY": args.openai_compatible_api_key,
        "OPENAI_COMPATIBLE_MODEL": args.openai_compatible_model,
        "OPENAI_COMPATIBLE_STREAM": args.openai_compatible_stream,
        "SMART_SEARCH_MAIN_SEARCH_ROUTE": args.main_search_route,
        "SMART_SEARCH_VALIDATION_LEVEL": args.validation_level,
        "SMART_SEARCH_FALLBACK_MODE": args.fallback_mode,
        "SMART_SEARCH_MINIMUM_PROFILE": args.minimum_profile,
        "EXA_API_KEY": args.exa_key,
        "CONTEXT7_API_KEY": args.context7_key,
        "JINA_API_KEY": args.jina_key,
        "JINA_READER_API_URL": _normalize_jina_reader_api_url(args.jina_reader_api_url),
        "JINA_RESPOND_WITH": args.jina_respond_with,
        "JINA_TIMEOUT_SECONDS": args.jina_timeout,
        "TAVILY_API_URL": _normalize_tavily_flag_api_url(args.tavily_api_url, args.tavily_key),
        "TAVILY_API_KEY": args.tavily_key,
        "FIRECRAWL_API_URL": _normalize_firecrawl_api_url(args.firecrawl_api_url),
        "FIRECRAWL_API_KEY": args.firecrawl_key,
    }

    lang = args.lang if args.lang in {"zh", "en"} else "zh"

    if not args.non_interactive:
        current = _cli().service.config_list(show_secrets=True)["values"]
        _write_setup_banner(args.lang if args.lang in {"zh", "en"} else "zh")
        lang = _select_setup_language(args.lang)
        if args.advanced:
            _run_advanced_setup_prompts(values, current, lang)
        else:
            _run_guided_setup_prompts(values, current, lang, show_banner=False)

    saved: dict[str, str] = {}
    for key, value in values.items():
        if value:
            result = _cli().service.config_set(key, value)
            saved[key] = result.get("value", "")

    data = {"ok": True, "config_file": _cli().service.config_path()["config_file"], "saved": saved}
    if not args.non_interactive:
        current_after = _cli().service.config_list(show_secrets=True)["values"]
        final_values = _merge_setup_values(current_after, values)
        final_status = _setup_status_from_values(final_values)
        _write_stderr(_t(lang, "\n保存完成。\n", "\nSaved.\n"))
        _write_setup_status(final_status, lang, final=True)
        missing = [capability for capability in ("main_search", "docs_search", "web_fetch") if not final_status[capability]["ok"]]
        if missing:
            _write_stderr(
                _t(
                    lang,
                    "\n当前配置尚未满足 standard 最低配置。\nsearch / doctor 会 fail closed，不会假装可用。\n",
                    "\nThe current config does not satisfy the standard minimum profile.\nsearch / doctor will fail closed instead of pretending to work.\n",
                )
            )
        else:
            _write_stderr(
                _t(
                    lang,
                    "\n下一步建议:\n  smart-search doctor --format json\n",
                    "\nNext steps:\n  smart-search doctor --format json\n",
                )
            )
        data["minimum_profile_ok"] = not missing
        data["minimum_profile_missing"] = missing
        data["capability_status"] = final_status
    return _print_result("setup", data, args.format, args.output)
