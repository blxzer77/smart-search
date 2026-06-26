import json
import asyncio
from pathlib import Path
from smart_search import cli


class GbkStdout:
    encoding = "gbk"
    errors = "strict"

    def __init__(self):
        self.parts = []

    def write(self, text):
        text.encode(self.encoding, errors=self.errors)
        self.parts.append(text)
        return len(text)

    def getvalue(self):
        return "".join(self.parts)


def test_help_contains_commands(capsys):
    try:
        cli.main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0

    out = capsys.readouterr().out
    assert "search" in out
    assert "doctor" in out


def test_version_flags_exit_successfully(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_get_version", lambda: "9.9.9-test")

    for flag in ["--version", "--v", "-v"]:
        try:
            cli.main([flag])
        except SystemExit as exc:
            assert exc.code == 0

        assert capsys.readouterr().out.strip() == "smart-search 9.9.9-test"


def test_each_subcommand_help_exits_successfully(capsys):
    commands = [
        ["search", "--help"],
        ["fetch", "--help"],
        ["map", "--help"],
        ["exa-search", "--help"],
        ["exa-similar", "--help"],
        ["zhipu-search", "--help"],
        ["context7-library", "--help"],
        ["context7-docs", "--help"],
        ["doctor", "--help"],
        ["diagnose", "--help"],
        ["diagnose", "openai-compatible", "--help"],
        ["setup", "--help"],
        ["config", "--help"],
        ["config", "path", "--help"],
        ["config", "list", "--help"],
        ["config", "set", "--help"],
        ["config", "unset", "--help"],
    ]

    for command in commands:
        try:
            cli.main(command)
        except SystemExit as exc:
            assert exc.code == 0

    out = capsys.readouterr().out
    assert "usage: smart-search search" in out


def test_command_aliases_parse_to_canonical_commands():
    parser = cli.build_parser()

    command_cases = [
        (["s", "query"], "search"),
        (["f", "https://example.com"], "fetch"),
        (["m", "https://example.com"], "map"),
        (["exa", "query"], "exa-search"),
        (["x", "query"], "exa-search"),
        (["xs", "https://example.com"], "exa-similar"),
        (["z", "query"], "zhipu-search"),
        (["zp", "query"], "zhipu-search"),
        (["c7", "react"], "context7-library"),
        (["ctx7", "react"], "context7-library"),
        (["c7d", "/facebook/react", "hooks"], "context7-docs"),
        (["c7docs", "/facebook/react", "hooks"], "context7-docs"),
        (["ctx7-docs", "/facebook/react", "hooks"], "context7-docs"),
        (["d"], "doctor"),
        (["diag", "openai-compatible"], "diagnose"),
        (["init", "--non-interactive"], "setup"),
        (["cfg", "ls"], "config"),
    ]

    for argv, command in command_cases:
        assert parser.parse_args(argv).command == command

    config_cases = [
        (["cfg", "p"], "path"),
        (["cfg", "ls"], "list"),
        (["cfg", "l"], "list"),
        (["cfg", "s", "OPENAI_COMPATIBLE_MODEL", "grok"], "set"),
        (["cfg", "rm", "OPENAI_COMPATIBLE_MODEL"], "unset"),
        (["cfg", "u", "OPENAI_COMPATIBLE_MODEL"], "unset"),
    ]
    for argv, config_command in config_cases:
        assert parser.parse_args(argv).config_command == config_command


def test_search_help_exposes_timeout(capsys):
    try:
        cli.main(["search", "--help"])
    except SystemExit as exc:
        assert exc.code == 0

    out = capsys.readouterr().out
    assert "--timeout SECONDS" in out
    assert "--stream" in out
    assert "--no-stream" in out


def test_diagnose_openai_compatible_defaults_to_markdown(monkeypatch, capsys):
    async def fake_diagnose(timeout_seconds=30.0):
        return {
            "ok": False,
            "provider": "openai-compatible",
            "summary": "小请求能通，但真实 search 形态超时。",
            "recommendation": "建议换模型/中转，或把本诊断报告贴给维护者。",
            "api_url": "https://relay.example.com/v1",
            "api_key": "sk-T********cret",
            "model": "relay-model",
            "configured_stream": True,
            "timeout_seconds": timeout_seconds,
            "config_file": "C:/tmp/config.json",
            "config_dir_source": "environment",
            "checks": [
                {"name": "轻量 chat 请求", "status": "ok", "response_time_ms": 10.0, "has_content": True, "message": "chat ok"},
                {
                    "name": "真实 search 请求 (stream=false)",
                    "status": "timeout",
                    "response_time_ms": 30000.0,
                    "has_content": False,
                    "message": "请求超时",
                },
            ],
            "next_command": "smart-search diagnose openai-compatible --format markdown",
            "error_type": "network_error",
            "error": "小请求能通，但真实 search 形态超时。",
        }

    monkeypatch.setattr(cli.service, "diagnose_openai_compatible", fake_diagnose)

    code = cli.main(["diagnose", "openai-compatible"])

    out = capsys.readouterr().out
    assert code == cli.EXIT_NETWORK_ERROR
    assert out.startswith("# Smart Search Diagnose")
    assert "小请求能通" in out
    assert "真实 search 请求" in out
    assert "smart-search diagnose openai-compatible --format markdown" in out


def test_diagnose_openai_compatible_json(monkeypatch, capsys):
    async def fake_diagnose(timeout_seconds=30.0):
        return {"ok": True, "provider": "openai-compatible", "summary": "ok", "timeout_seconds": timeout_seconds}

    monkeypatch.setattr(cli.service, "diagnose_openai_compatible", fake_diagnose)

    code = cli.main(["diagnose", "openai-compatible", "--timeout", "5", "--format", "json"])

    data = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    assert data["provider"] == "openai-compatible"
    assert data["timeout_seconds"] == 5


def test_search_outputs_json_and_file(monkeypatch, capsys):
    async def fake_search(query, platform="", model="", extra_sources=0, validation="", fallback="", providers="auto"):
        return {
            "ok": True,
            "query": query,
            "content": "Answer",
            "sources": [{"url": "https://example.com", "title": "Example"}],
            "sources_count": 1,
        }

    monkeypatch.setattr(cli.service, "search", fake_search)
    written = {}

    def fake_write_output(path, content):
        written["path"] = path
        written["content"] = content

    monkeypatch.setattr(cli.service, "write_output", fake_write_output)
    output = "C:/tmp/smart-search-cli-test-result.json"

    code = cli.main(["search", "query", "--output", output])

    assert code == cli.EXIT_OK
    stdout_data = json.loads(capsys.readouterr().out)
    file_data = json.loads(written["content"])
    assert written["path"] == output
    assert stdout_data["sources_count"] == 1
    assert file_data["content"] == "Answer"


def test_search_stream_flags_override_only_when_present(monkeypatch, capsys):
    captured = []

    async def fake_search(query, **kwargs):
        captured.append(kwargs)
        return {"ok": True, "content": "Answer", "sources": [], "sources_count": 0}

    monkeypatch.setattr(cli.service, "search", fake_search)

    assert cli.main(["search", "query"]) == cli.EXIT_OK
    json.loads(capsys.readouterr().out)
    assert cli.main(["search", "query", "--stream"]) == cli.EXIT_OK
    json.loads(capsys.readouterr().out)
    assert cli.main(["search", "query", "--no-stream"]) == cli.EXIT_OK
    json.loads(capsys.readouterr().out)

    assert "stream" not in captured[0]
    assert captured[1]["stream"] is True
    assert captured[2]["stream"] is False


def test_search_json_outputs_readable_chinese(monkeypatch, capsys):
    async def fake_search(query, platform="", model="", extra_sources=0, validation="", fallback="", providers="auto"):
        return {"ok": True, "content": "中文NBA战报", "sources": [], "sources_count": 0}

    monkeypatch.setattr(cli.service, "search", fake_search)

    code = cli.main(["search", "nba战报", "--format", "json"])

    assert code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "中文NBA战报" in out
    assert "\\u4e2d\\u6587" not in out
    assert json.loads(out)["content"] == "中文NBA战报"


def test_search_content_format_outputs_content_only(monkeypatch, capsys):
    async def fake_search(query, platform="", model="", extra_sources=0, validation="", fallback="", providers="auto"):
        return {"ok": True, "content": "中文NBA战报", "sources": [{"url": "https://example.com"}], "sources_count": 1}

    monkeypatch.setattr(cli.service, "search", fake_search)

    code = cli.main(["search", "nba战报", "--format", "content"])

    assert code == cli.EXIT_OK
    assert capsys.readouterr().out == "中文NBA战报\n"


def test_fetch_content_format_matches_markdown_body(monkeypatch, capsys):
    async def fake_fetch(url):
        return {"ok": True, "url": url, "content": "# 中文页面"}

    monkeypatch.setattr(cli.service, "fetch", fake_fetch)

    content_code = cli.main(["fetch", "https://example.com", "--format", "content"])
    content_out = capsys.readouterr().out
    markdown_code = cli.main(["fetch", "https://example.com", "--format", "markdown"])
    markdown_out = capsys.readouterr().out

    assert content_code == cli.EXIT_OK
    assert markdown_code == cli.EXIT_OK
    assert content_out == "# 中文页面\n"
    assert markdown_out == content_out


def test_context7_docs_content_format_outputs_content(monkeypatch, capsys):
    async def fake_context7_docs(library_id, query):
        return {"ok": True, "provider": "context7-docs", "library_id": library_id, "query": query, "content": "中文文档内容"}

    monkeypatch.setattr(cli.service, "context7_docs", fake_context7_docs)

    code = cli.main(["context7-docs", "/facebook/react", "hooks", "--format", "content"])

    assert code == cli.EXIT_OK
    assert capsys.readouterr().out == "中文文档内容\n"


def test_doctor_markdown_outputs_human_health_report(monkeypatch, capsys):
    long_message = "provider detail " + ("x" * 220)

    async def fake_doctor():
        return {
            "ok": True,
            "config_file": "C:/tmp/config.json",
            "config_dir": "C:/tmp",
            "config_dir_source": "environment",
            "default_config_file": "C:/Users/example/AppData/Local/smart-search/config.json",
            "legacy_windows_config_file": "C:/Users/example/.config/smart-search/config.json",
            "legacy_windows_config_exists": True,
            "config_dir_override_value": "C:/Users/example/AppData/Local/smart-search",
            "config_dir_override_matches_default": True,
            "log_dir_config_value": "logs",
            "resolved_log_dir": "C:/tmp/logs",
            "evidence_dir_config_value": "evidence",
            "resolved_evidence_dir": "C:/tmp/evidence",
            "file_logging_enabled": False,
            "config_status": "ok: complete",
            "OPENAI_COMPATIBLE_API_KEY": "未配置",
            "SMART_SEARCH_LOG_DIR": "logs",
            "SMART_SEARCH_EVIDENCE_DIR": "evidence",
            "config_sources": {
                "OPENAI_COMPATIBLE_API_KEY": "default",
                "SMART_SEARCH_LOG_DIR": "default",
                "SMART_SEARCH_EVIDENCE_DIR": "default",
            },
            "minimum_profile_ok": True,
            "minimum_profile_missing": [],
            "capability_status": {
                "main_search": {"ok": True, "configured": ["openai-compatible"], "fallback_chain": ["openai-compatible"]},
                "docs_search": {"ok": True, "configured": ["context7"], "fallback_chain": ["context7", "exa"]},
                "web_fetch": {"ok": True, "configured": ["tavily", "jina"], "fallback_chain": ["tavily", "jina", "firecrawl"]},
            },
            "main_search_connection_tests": {
                "openai-compatible": {
                    "status": "ok",
                    "message": long_message,
                    "response_time_ms": 123.45,
                    "available_models": ["relay-model"],
                    "chat_completion_test": {"status": "ok", "message": "chat ok", "response_time_ms": 100.0},
                    "models_endpoint_test": {"status": "ok", "message": "models ok", "response_time_ms": 23.45},
                }
            },
            "exa_connection_test": {"status": "ok", "message": "Exa ok", "response_time_ms": 11.1},
            "tavily_connection_test": {"status": "ok", "message": "Tavily ok", "response_time_ms": 22.2},
            "jina_connection_test": {"status": "ok", "message": "Jina ok", "response_time_ms": 10.0},
            "firecrawl_connection_test": {"status": "configured", "message": "key configured"},
            "zhipu_connection_test": {"status": "warning", "message": "HTTP 429"},
            "context7_connection_test": {"status": "not_configured", "message": "missing"},
        }

    monkeypatch.setattr(cli.service, "doctor", fake_doctor)

    code = cli.main(["doctor", "--format", "markdown"])

    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert not out.lstrip().startswith("{")
    assert "# Smart Search Doctor" in out
    assert "Overall: OK" in out
    assert "Config dir source: `environment`" in out
    assert "Default config file: `C:/Users/example/AppData/Local/smart-search/config.json`" in out
    assert "Legacy Windows config file: `C:/Users/example/.config/smart-search/config.json`" in out
    assert "Legacy Windows config exists: OK" in out
    assert "SMART_SEARCH_CONFIG_DIR: `C:/Users/example/AppData/Local/smart-search`" in out
    assert "Override matches default: YES" in out
    assert "override matches the current Windows default path" in out
    assert "Log dir config value: `logs`" in out
    assert "Resolved log dir: `C:/tmp/logs`" in out
    assert "Evidence dir config value: `evidence`" in out
    assert "Resolved evidence dir: `C:/tmp/evidence`" in out
    assert "File logging enabled: NO" in out
    assert "## Configuration Values" in out
    assert "| OPENAI_COMPATIBLE_API_KEY | default | 未配置 |" in out
    assert "## Capabilities" in out
    assert "## Main Search Providers" in out
    assert "openai-compatible" in out
    assert "## Provider Details" in out
    assert long_message in out
    assert "relay-model" in out
    assert "Tavily ok" in out


def test_doctor_content_outputs_non_empty_summary(monkeypatch, capsys):
    async def fake_doctor():
        return {
            "ok": False,
            "config_status": "missing config",
            "minimum_profile_ok": False,
            "capability_status": {
                "main_search": {"ok": False, "configured": [], "fallback_chain": ["openai-compatible"]}
            },
            "error": "Missing required capability: main_search",
            "error_type": "config_error",
        }

    monkeypatch.setattr(cli.service, "doctor", fake_doctor)

    code = cli.main(["doctor", "--format", "content"])

    out = capsys.readouterr().out
    assert code == cli.EXIT_CONFIG_ERROR
    assert out.strip()
    assert "Doctor FAIL" in out
    assert "Minimum profile: FAIL" in out
    assert "Missing required capability" in out


def test_search_alias_uses_canonical_command(monkeypatch, capsys):
    captured = {}

    async def fake_search(query, platform="", model="", extra_sources=0, validation="", fallback="", providers="auto"):
        captured["query"] = query
        return {"ok": True, "content": "Answer", "sources": [], "sources_count": 0}

    monkeypatch.setattr(cli.service, "search", fake_search)

    code = cli.main(["s", "alias query"])

    assert code == cli.EXIT_OK
    assert captured["query"] == "alias query"
    assert json.loads(capsys.readouterr().out)["content"] == "Answer"


def test_fetch_alias_uses_canonical_command(monkeypatch, capsys):
    async def fake_fetch(url):
        return {"ok": True, "url": url, "content": "Page"}

    monkeypatch.setattr(cli.service, "fetch", fake_fetch)

    code = cli.main(["f", "https://example.com"])

    assert code == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["url"] == "https://example.com"


def test_research_command_uses_service_and_outputs_json(monkeypatch, capsys, tmp_path):
    captured = {}

    async def fake_research(query, budget="deep", evidence_dir="", fallback="auto", **_kwargs):
        captured.update({"query": query, "budget": budget, "evidence_dir": evidence_dir, "fallback": fallback})
        return {
            "ok": True,
            "mode": "deep_research_execution",
            "query_mode": "research",
            "question": query,
            "final_answer": "Evidence answer",
            "content": "Evidence answer",
            "citations": [{"url": "https://example.com", "title": "Example", "provider": "jina"}],
            "evidence_items": [{"url": "https://example.com", "provider": "jina", "content": "Evidence"}],
            "gap_check": {"status": "closed", "gaps": []},
            "provider_attempts": [],
            "fallback_used": False,
            "degraded": False,
            "route_policy_version": "research-router-v1",
            "evidence_dir": evidence_dir,
        }

    monkeypatch.setattr(cli.service, "research", fake_research)

    code = cli.main([
        "research",
        "React docs",
        "--budget",
        "standard",
        "--evidence-dir",
        str(tmp_path),
        "--fallback",
        "off",
        "--format",
        "json",
    ])

    assert code == cli.EXIT_OK
    data = json.loads(capsys.readouterr().out)
    assert captured == {"query": "React docs", "budget": "standard", "evidence_dir": str(tmp_path), "fallback": "off"}
    assert data["query_mode"] == "research"
    assert data["final_answer"] == "Evidence answer"


def test_research_markdown_and_content_output(monkeypatch, capsys):
    async def fake_research(query, budget="deep", evidence_dir="", fallback="auto", **_kwargs):
        return {
            "ok": True,
            "question": query,
            "final_answer": "Evidence answer",
            "content": "Evidence answer",
            "citations": [{"url": "https://example.com", "title": "Example", "provider": "jina"}],
            "gap_check": {"gaps": []},
            "fallback_used": True,
            "degraded": False,
            "route_policy_version": "research-router-v1",
            "evidence_dir": "C:/tmp/evidence",
        }

    monkeypatch.setattr(cli.service, "research", fake_research)

    assert cli.main(["rs", "React docs", "--format", "markdown"]) == cli.EXIT_OK
    markdown = capsys.readouterr().out
    assert "# Research Report" in markdown
    assert "Evidence answer" in markdown
    assert "https://example.com" in markdown

    assert cli.main(["research", "React docs", "--format", "content"]) == cli.EXIT_OK
    assert capsys.readouterr().out == "Evidence answer\n"


def test_exa_search_passes_powershell_split_domains(monkeypatch, capsys):
    captured = {}

    async def fake_exa_search(
        query,
        num_results=5,
        search_type="neural",
        include_text=False,
        include_highlights=False,
        start_published_date="",
        include_domains="",
        exclude_domains="",
        category="",
    ):
        captured["query"] = query
        captured["include_domains"] = include_domains
        return {"ok": True, "query": query, "results": []}

    monkeypatch.setattr(cli.service, "exa_search", fake_exa_search)

    code = cli.main(["exa-search", "query", "--include-domains", "github.com", "freertos.org"])

    assert code == cli.EXIT_OK
    assert captured["include_domains"] == ["github.com", "freertos.org"]
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_doctor_alias_uses_canonical_command(monkeypatch, capsys):
    async def fake_doctor():
        return {"ok": True, "config_status": "ok"}

    monkeypatch.setattr(cli.service, "doctor", fake_doctor)

    code = cli.main(["d"])

    assert code == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["config_status"] == "ok"


def test_search_timeout_respects_requested_format_and_exit_4(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "relay-timeout-model")
    monkeypatch.setenv("OPENAI_COMPATIBLE_STREAM", "true")

    async def slow_search(query, **kwargs):
        await asyncio.sleep(1)
        return {
            "ok": True,
            "query": query,
            "content": "late answer",
            "sources": [{"url": "https://example.com"}],
            "sources_count": 1,
        }

    monkeypatch.setattr(cli.service, "search", slow_search)

    code = cli.main(["search", "slow query", "--timeout", "0.01", "--format", "markdown"])

    assert code == cli.EXIT_NETWORK_ERROR
    out = capsys.readouterr()
    assert out.err == ""
    assert out.out.startswith("\n## Errors") or "## Errors" in out.out
    assert "network_error" in out.out
    assert "0.01" in out.out
    assert "seconds" in out.out
    assert "relay-timeout-model" in out.out
    assert "Stream: YES" in out.out
    assert "smart-search diagnose openai-compatible --format markdown" in out.out

    code = cli.main(["search", "slow query", "--timeout", "0.01", "--format", "content"])
    assert code == cli.EXIT_NETWORK_ERROR
    content_out = capsys.readouterr().out
    assert "network_error" in content_out
    assert "Search timed out after 0.01 seconds" in content_out

    code = cli.main(["search", "slow query", "--timeout", "0.01", "--format", "json"])
    assert code == cli.EXIT_NETWORK_ERROR
    data = json.loads(capsys.readouterr().out)
    assert data["sources_count"] == 0
    assert data["primary_sources"] == []
    assert data["primary_sources_count"] == 0
    assert data["extra_sources"] == []
    assert data["extra_sources_count"] == 0
    assert data["source_warning"] == ""
    assert data["diagnose_command"] == "smart-search diagnose openai-compatible --format markdown"
    assert data["model"] == "relay-timeout-model"
    assert data["stream"] is True
    assert data["recommendation"]


def test_markdown_search_includes_sources(monkeypatch, capsys):
    async def fake_search(query, platform="", model="", extra_sources=0, validation="", fallback="", providers="auto"):
        return {
            "ok": True,
            "content": "Answer",
            "sources": [{"url": "https://example.com", "title": "Example"}],
            "sources_count": 1,
        }

    monkeypatch.setattr(cli.service, "search", fake_search)

    code = cli.main(["search", "query", "--format", "markdown"])

    assert code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Answer" in out
    assert "[Example](https://example.com)" in out


def test_markdown_search_labels_primary_and_extra_sources(monkeypatch, capsys):
    async def fake_search(query, platform="", model="", extra_sources=0, validation="", fallback="", providers="auto"):
        return {
            "ok": True,
            "content": "Answer",
            "primary_sources": [{"url": "https://primary.example.com", "title": "Primary"}],
            "primary_sources_count": 1,
            "extra_sources": [{"url": "https://extra.example.com", "title": "Extra"}],
            "extra_sources_count": 1,
            "sources": [
                {"url": "https://primary.example.com", "title": "Primary"},
                {"url": "https://extra.example.com", "title": "Extra"},
            ],
            "sources_count": 2,
            "source_warning": "extra_sources are retrieved in parallel",
        }

    monkeypatch.setattr(cli.service, "search", fake_search)

    code = cli.main(["search", "query", "--format", "markdown"])

    assert code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "## Primary Sources" in out
    assert "[Primary](https://primary.example.com)" in out
    assert "## Extra Sources" in out
    assert "[Extra](https://extra.example.com)" in out
    assert "extra_sources are retrieved in parallel" in out


def test_config_error_exit_code(monkeypatch, capsys):
    async def fake_doctor():
        return {"ok": False, "error_type": "config_error", "OPENAI_COMPATIBLE_API_KEY": "未配置"}

    monkeypatch.setattr(cli.service, "doctor", fake_doctor)

    code = cli.main(["doctor"])

    assert code == cli.EXIT_CONFIG_ERROR
    assert json.loads(capsys.readouterr().out)["OPENAI_COMPATIBLE_API_KEY"] == "未配置"


def test_network_error_exit_code(monkeypatch, capsys):
    async def fake_fetch(url):
        return {"ok": False, "error_type": "network_error", "error": "upstream timeout", "url": url}

    monkeypatch.setattr(cli.service, "fetch", fake_fetch)

    code = cli.main(["fetch", "https://example.com"])

    assert code == cli.EXIT_NETWORK_ERROR
    assert json.loads(capsys.readouterr().out)["error"] == "upstream timeout"


def test_stdout_falls_back_for_gbk_unencodable_unicode(monkeypatch):
    fake_stdout = GbkStdout()
    monkeypatch.setattr(cli.sys, "stdout", fake_stdout)

    code = cli._print_result("exa-search", {"ok": True, "content": "A\u2060B"}, "json")

    assert code == cli.EXIT_OK
    out = fake_stdout.getvalue()
    assert "\\u2060" in out
    assert json.loads(out)["content"] == "A\u2060B"


def test_gbk_stdout_keeps_json_parseable_with_chinese_and_unencodable_unicode(monkeypatch):
    fake_stdout = GbkStdout()
    monkeypatch.setattr(cli.sys, "stdout", fake_stdout)

    code = cli._print_result("search", {"ok": True, "content": "中文A\u2060B📅"}, "json")

    assert code == cli.EXIT_OK
    out = fake_stdout.getvalue()
    assert "中文" in out
    assert "\\u2060" in out
    assert "\\ud83d\\udcc5" in out
    assert json.loads(out)["content"] == "中文A\u2060B📅"


def test_real_doctor_ignores_legacy_primary_env_and_returns_config_exit(monkeypatch, capsys):
    secret = "placeholder-test-secret"
    monkeypatch.setenv("SMART_SEARCH_API_URL", "https://api.example.com/v1")
    monkeypatch.setenv("SMART_SEARCH_API_KEY", secret)
    monkeypatch.delenv("OPENAI_COMPATIBLE_API_URL", raising=False)
    monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

    code = cli.main(["doctor"])

    out = capsys.readouterr().out
    data = json.loads(out)
    assert code == cli.EXIT_CONFIG_ERROR
    assert data["ok"] is False
    assert data["error_type"] == "config_error"
    assert "SMART_SEARCH_API_URL" not in data
    assert "SMART_SEARCH_API_KEY" not in data
    assert data["capability_status"]["main_search"]["configured"] == []
    assert secret not in out


def test_config_set_masks_value(monkeypatch, capsys):
    def fake_config_set(key, value):
        return {"ok": True, "key": key, "value": "relay-********cret", "config_file": "C:/tmp/config.json"}

    monkeypatch.setattr(cli.service, "config_set", fake_config_set)

    code = cli.main(["config", "set", "OPENAI_COMPATIBLE_API_KEY", "relay-test-secret"])

    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert "relay-test-secret" not in out
    assert json.loads(out)["value"] == "relay-********cret"


def test_config_list_does_not_request_secrets(monkeypatch, capsys):
    captured = {}

    def fake_config_list(show_secrets=False):
        captured["show_secrets"] = show_secrets
        return {"ok": True, "values": {"OPENAI_COMPATIBLE_API_KEY": "relay-********cret"}}

    monkeypatch.setattr(cli.service, "config_list", fake_config_list)

    code = cli.main(["config", "list"])

    assert code == cli.EXIT_OK
    assert captured["show_secrets"] is False
    assert json.loads(capsys.readouterr().out)["values"]["OPENAI_COMPATIBLE_API_KEY"].endswith("cret")


def test_config_aliases_use_canonical_commands(monkeypatch, capsys):
    captured = {}

    def fake_config_list(show_secrets=False):
        captured["show_secrets"] = show_secrets
        return {"ok": True, "values": {"OPENAI_COMPATIBLE_MODEL": "grok"}}

    def fake_config_set(key, value):
        captured["set"] = (key, value)
        return {"ok": True, "key": key, "value": value}

    def fake_config_unset(key):
        captured["unset"] = key
        return {"ok": True, "key": key}

    monkeypatch.setattr(cli.service, "config_list", fake_config_list)
    monkeypatch.setattr(cli.service, "config_set", fake_config_set)
    monkeypatch.setattr(cli.service, "config_unset", fake_config_unset)

    assert cli.main(["cfg", "ls"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["values"]["OPENAI_COMPATIBLE_MODEL"] == "grok"
    assert captured["show_secrets"] is False

    assert cli.main(["cfg", "s", "OPENAI_COMPATIBLE_MODEL", "grok-4-fast"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["value"] == "grok-4-fast"
    assert captured["set"] == ("OPENAI_COMPATIBLE_MODEL", "grok-4-fast")

    assert cli.main(["cfg", "rm", "OPENAI_COMPATIBLE_MODEL"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["key"] == "OPENAI_COMPATIBLE_MODEL"
    assert captured["unset"] == "OPENAI_COMPATIBLE_MODEL"


def test_config_set_legacy_main_search_key_returns_parameter_error(monkeypatch, capsys):
    def fake_config_set(key, value):
        return {
            "ok": False,
            "error_type": "parameter_error",
            "error": f"Unsupported config key: {key}",
        }

    monkeypatch.setattr(cli.service, "config_set", fake_config_set)

    code = cli.main(["config", "set", "SMART_SEARCH_API_KEY", "sk-test-secret"])
    data = json.loads(capsys.readouterr().out)

    assert code == cli.EXIT_PARAMETER_ERROR
    assert data["error_type"] == "parameter_error"
    assert "Unsupported config key: SMART_SEARCH_API_KEY" in data["error"]


def test_config_markdown_and_content_are_masked_and_non_json(monkeypatch, capsys):
    def fake_config_path():
        return {
            "ok": True,
            "config_file": "C:/tmp/config.json",
            "config_dir": "C:/tmp",
            "config_dir_source": "environment",
            "default_config_file": "C:/Users/example/AppData/Local/smart-search/config.json",
            "legacy_windows_config_file": "C:/Users/example/.config/smart-search/config.json",
            "legacy_windows_config_exists": False,
            "config_dir_override_value": "C:/tmp",
            "config_dir_override_matches_default": False,
            "evidence_dir_config_value": "evidence",
            "resolved_evidence_dir": "C:/tmp/evidence",
            "exists": True,
        }

    def fake_config_list(show_secrets=False):
        return {"ok": True, "config_file": "C:/tmp/config.json", "values": {"OPENAI_COMPATIBLE_API_KEY": "relay-********cret", "OPENAI_COMPATIBLE_MODEL": "grok"}}

    def fake_config_set(key, value):
        return {"ok": True, "config_file": "C:/tmp/config.json", "key": key, "value": "relay-********cret"}

    def fake_config_unset(key):
        return {"ok": True, "config_file": "C:/tmp/config.json", "key": key}

    monkeypatch.setattr(cli.service, "config_path", fake_config_path)
    monkeypatch.setattr(cli.service, "config_list", fake_config_list)
    monkeypatch.setattr(cli.service, "config_set", fake_config_set)
    monkeypatch.setattr(cli.service, "config_unset", fake_config_unset)

    assert cli.main(["config", "path", "--format", "markdown"]) == cli.EXIT_OK
    path_out = capsys.readouterr().out
    assert "# Smart Search Config" in path_out
    assert "C:/tmp/config.json" in path_out
    assert "Config dir source: `environment`" in path_out
    assert "SMART_SEARCH_CONFIG_DIR: `C:/tmp`" in path_out
    assert "Evidence dir config value: `evidence`" in path_out
    assert "Resolved evidence dir: `C:/tmp/evidence`" in path_out

    assert cli.main(["config", "list", "--format", "markdown"]) == cli.EXIT_OK
    list_out = capsys.readouterr().out
    assert "relay-test-secret" not in list_out
    assert "relay-********cret" in list_out
    assert not list_out.lstrip().startswith("{")

    assert cli.main(["config", "set", "OPENAI_COMPATIBLE_API_KEY", "relay-test-secret", "--format", "markdown"]) == cli.EXIT_OK
    set_out = capsys.readouterr().out
    assert "relay-test-secret" not in set_out
    assert "OPENAI_COMPATIBLE_API_KEY" in set_out

    assert cli.main(["config", "unset", "OPENAI_COMPATIBLE_API_KEY", "--format", "content"]) == cli.EXIT_OK
    unset_out = capsys.readouterr().out
    assert "Config OK" in unset_out
    assert "key=OPENAI_COMPATIBLE_API_KEY" in unset_out


def test_provider_markdown_outputs_result_lists(monkeypatch, capsys):
    async def fake_exa_search(*args, **kwargs):
        return {"ok": True, "query": "query", "provider": "exa", "results": [{"title": "Example", "url": "https://example.com", "text": "body"}]}

    async def fake_exa_similar(*args, **kwargs):
        return {"ok": True, "url": "https://source.example.com", "results": [{"title": "Similar", "url": "https://similar.example.com"}]}

    async def fake_zhipu_search(*args, **kwargs):
        return {"ok": True, "query": "news", "provider": "zhipu", "results": [{"title": "News", "url": "https://news.example.com", "description": "desc"}]}

    async def fake_context7_library(*args, **kwargs):
        return {"ok": True, "query": "react", "provider": "context7", "results": [{"id": "/facebook/react", "title": "React", "description": "docs"}]}

    async def fake_map_site(*args, **kwargs):
        return {"ok": True, "url": "https://docs.example.com", "base_url": "https://docs.example.com", "results": ["https://docs.example.com/api"]}

    monkeypatch.setattr(cli.service, "exa_search", fake_exa_search)
    monkeypatch.setattr(cli.service, "exa_find_similar", fake_exa_similar)
    monkeypatch.setattr(cli.service, "zhipu_search", fake_zhipu_search)
    monkeypatch.setattr(cli.service, "context7_library", fake_context7_library)
    monkeypatch.setattr(cli.service, "map_site", fake_map_site)

    cases = [
        (["exa-search", "query", "--format", "markdown"], "Example", "https://example.com"),
        (["exa-similar", "https://source.example.com", "--format", "markdown"], "Similar", "https://similar.example.com"),
        (["zhipu-search", "news", "--format", "markdown"], "News", "https://news.example.com"),
        (["context7-library", "react", "--format", "markdown"], "React", "/facebook/react"),
        (["map", "https://docs.example.com", "--format", "markdown"], "https://docs.example.com/api", "Site Map"),
    ]
    for argv, first, second in cases:
        assert cli.main(argv) == cli.EXIT_OK
        out = capsys.readouterr().out
        assert not out.lstrip().startswith("{")
        assert first in out
        assert second in out


def test_provider_content_outputs_plain_result_list(monkeypatch, capsys):
    async def fake_exa_search(*args, **kwargs):
        return {"ok": True, "query": "query", "results": [{"title": "Example", "url": "https://example.com", "text": "body"}]}

    monkeypatch.setattr(cli.service, "exa_search", fake_exa_search)

    code = cli.main(["exa-search", "query", "--format", "content"])

    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert out.startswith("1. Example - https://example.com")
    assert not out.lstrip().startswith("{")


def test_provider_markdown_empty_results_are_clear(monkeypatch, capsys):
    async def fake_exa_search(*args, **kwargs):
        return {"ok": True, "query": "query", "results": []}

    monkeypatch.setattr(cli.service, "exa_search", fake_exa_search)

    code = cli.main(["exa-search", "query", "--format", "markdown"])

    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert "No results." in out


def test_all_formatted_commands_have_non_json_markdown(monkeypatch):
    async def fake_search(*args, **kwargs):
        return {"ok": True, "content": "Answer", "sources": []}

    async def fake_fetch(*args, **kwargs):
        return {"ok": True, "content": "Page"}

    async def fake_map(*args, **kwargs):
        return {"ok": True, "results": ["https://example.com/api"]}

    async def fake_exa(*args, **kwargs):
        return {"ok": True, "results": [{"title": "Example", "url": "https://example.com"}]}

    async def fake_zhipu(*args, **kwargs):
        return {"ok": True, "results": [{"title": "News", "url": "https://news.example.com"}]}

    async def fake_c7_library(*args, **kwargs):
        return {"ok": True, "results": [{"id": "/lib", "title": "Library"}]}

    async def fake_c7_docs(*args, **kwargs):
        return {"ok": True, "library_id": "/lib", "query": "hooks", "content": "Docs"}

    async def fake_doctor():
        return {"ok": True, "config_status": "ok", "minimum_profile_ok": True}

    async def fake_research(query, budget="deep", evidence_dir="", fallback="auto", **_kwargs):
        return {"ok": True, "question": query, "content": "Research", "final_answer": "Research", "citations": [], "gap_check": {"gaps": []}}

    def fake_config_path():
        return {"ok": True, "config_file": "C:/tmp/config.json"}

    def fake_config_list(show_secrets=False):
        return {"ok": True, "values": {"OPENAI_COMPATIBLE_MODEL": "grok"}}

    def fake_config_set(key, value):
        return {"ok": True, "key": key, "value": "***"}

    def fake_config_unset(key):
        return {"ok": True, "key": key}

    monkeypatch.setattr(cli.service, "search", fake_search)
    monkeypatch.setattr(cli.service, "fetch", fake_fetch)
    monkeypatch.setattr(cli.service, "map_site", fake_map)
    monkeypatch.setattr(cli.service, "exa_search", fake_exa)
    monkeypatch.setattr(cli.service, "exa_find_similar", fake_exa)
    monkeypatch.setattr(cli.service, "zhipu_search", fake_zhipu)
    monkeypatch.setattr(cli.service, "context7_library", fake_c7_library)
    monkeypatch.setattr(cli.service, "context7_docs", fake_c7_docs)
    monkeypatch.setattr(cli.service, "doctor", fake_doctor)
    monkeypatch.setattr(cli.service, "research", fake_research)
    monkeypatch.setattr(cli.service, "config_path", fake_config_path)
    monkeypatch.setattr(cli.service, "config_list", fake_config_list)
    monkeypatch.setattr(cli.service, "config_set", fake_config_set)
    monkeypatch.setattr(cli.service, "config_unset", fake_config_unset)

    command_cases = [
        ("search", ["search", "query", "--format", "markdown"]),
        ("fetch", ["fetch", "https://example.com", "--format", "markdown"]),
        ("map", ["map", "https://example.com", "--format", "markdown"]),
        ("exa-search", ["exa-search", "query", "--format", "markdown"]),
        ("exa-similar", ["exa-similar", "https://example.com", "--format", "markdown"]),
        ("zhipu-search", ["zhipu-search", "query", "--format", "markdown"]),
        ("context7-library", ["context7-library", "react", "--format", "markdown"]),
        ("context7-docs", ["context7-docs", "/lib", "hooks", "--format", "markdown"]),
        ("research", ["research", "query", "--format", "markdown"]),
        ("doctor", ["doctor", "--format", "markdown"]),
        ("diagnose", ["diagnose", "openai-compatible", "--format", "markdown"]),
        ("config-path", ["config", "path", "--format", "markdown"]),
        ("config-list", ["config", "list", "--format", "markdown"]),
        ("config-set", ["config", "set", "OPENAI_COMPATIBLE_MODEL", "grok", "--format", "markdown"]),
        ("config-unset", ["config", "unset", "OPENAI_COMPATIBLE_MODEL", "--format", "markdown"]),
    ]

    for name, argv in command_cases:
        command = cli.build_parser().parse_args(argv).command
        data = {
            "search": {"ok": True, "content": "Answer", "sources": []},
            "fetch": {"ok": True, "content": "Page"},
            "map": {"ok": True, "results": ["https://example.com/api"]},
            "exa-search": {"ok": True, "results": [{"title": "Example", "url": "https://example.com"}]},
            "exa-similar": {"ok": True, "results": [{"title": "Example", "url": "https://example.com"}]},
            "zhipu-search": {"ok": True, "results": [{"title": "News", "url": "https://news.example.com"}]},
            "context7-library": {"ok": True, "results": [{"id": "/lib", "title": "Library"}]},
            "context7-docs": {"ok": True, "library_id": "/lib", "query": "hooks", "content": "Docs"},
            "research": {"ok": True, "question": "q", "content": "Research", "final_answer": "Research", "citations": [], "gap_check": {"gaps": []}},
            "doctor": {"ok": True, "config_status": "ok", "minimum_profile_ok": True},
            "diagnose": {"ok": True, "provider": "openai-compatible", "summary": "ok", "recommendation": "none"},
            "config": {"ok": True, "config_file": "C:/tmp/config.json", "values": {"OPENAI_COMPATIBLE_MODEL": "grok"}},
        }[command]
        rendered = cli._render(command, data, "markdown")
        assert rendered.strip(), name
        assert not rendered.lstrip().startswith("{"), name


def test_non_content_commands_have_non_empty_content_fallback():
    cases = {
        "doctor": {"ok": True, "config_status": "ok", "minimum_profile_ok": True},
        "diagnose": {"ok": True, "provider": "openai-compatible", "summary": "ok", "recommendation": "none"},
        "config": {"ok": True, "config_file": "C:/tmp/config.json"},
        "exa-search": {"ok": True, "results": [{"title": "Example", "url": "https://example.com"}]},
    }
    for command, data in cases.items():
        rendered = cli._render(command, data, "content")
        assert rendered.strip(), command
        assert not rendered.lstrip().startswith("{"), command


def test_setup_non_interactive_saves_values(monkeypatch, capsys):
    saved = {}

    def fake_config_set(key, value):
        saved[key] = value
        return {"ok": True, "key": key, "value": "***", "config_file": "C:/tmp/config.json"}

    monkeypatch.setattr(cli.service, "config_set", fake_config_set)
    monkeypatch.setattr(cli.service, "config_path", lambda: {"ok": True, "config_file": "C:/tmp/config.json"})

    code = cli.main([
        "setup",
        "--non-interactive",
        "--openai-compatible-api-url",
        "https://relay.example.com/v1",
        "--openai-compatible-api-key",
        "relay-test-secret",
        "--openai-compatible-model",
        "relay-model",
        "--openai-compatible-stream",
        "true",
        "--validation-level",
        "balanced",
        "--fallback-mode",
        "auto",
        "--minimum-profile",
        "standard",
        "--zhipu-key",
        "zhipu-secret",
        "--zhipu-api-url",
        "zhipu.example.com/api",
        "--zhipu-search-engine",
        "search_pro",
        "--jina-key",
        "jina-secret",
        "--jina-reader-api-url",
        "r.jina.ai",
        "--jina-respond-with",
        "readerlm-v2",
        "--jina-timeout",
        "10",
        "--context7-key",
        "ctx-secret",
        "--tavily-api-url",
        "pool.example.com",
        "--tavily-key",
        "th-test-secret",
        "--firecrawl-api-url",
        "firecrawl.example.com/v2",
        "--firecrawl-key",
        "firecrawl-secret",
    ])

    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert saved["OPENAI_COMPATIBLE_API_URL"] == "https://relay.example.com/v1"
    assert saved["OPENAI_COMPATIBLE_API_KEY"] == "relay-test-secret"
    assert saved["OPENAI_COMPATIBLE_MODEL"] == "relay-model"
    assert saved["OPENAI_COMPATIBLE_STREAM"] == "true"
    assert saved["SMART_SEARCH_VALIDATION_LEVEL"] == "balanced"
    assert saved["SMART_SEARCH_FALLBACK_MODE"] == "auto"
    assert saved["SMART_SEARCH_MINIMUM_PROFILE"] == "standard"
    assert saved["ZHIPU_API_KEY"] == "zhipu-secret"
    assert saved["ZHIPU_API_URL"] == "https://zhipu.example.com/api"
    assert saved["ZHIPU_SEARCH_ENGINE"] == "search_pro"
    assert saved["JINA_API_KEY"] == "jina-secret"
    assert saved["JINA_READER_API_URL"] == "https://r.jina.ai"
    assert saved["JINA_RESPOND_WITH"] == "readerlm-v2"
    assert saved["JINA_TIMEOUT_SECONDS"] == "10"
    assert saved["CONTEXT7_API_KEY"] == "ctx-secret"
    assert saved["TAVILY_API_URL"] == "https://pool.example.com/api/tavily"
    assert saved["TAVILY_API_KEY"] == "th-test-secret"
    assert saved["FIRECRAWL_API_URL"] == "https://firecrawl.example.com/v2"
    assert saved["FIRECRAWL_API_KEY"] == "firecrawl-secret"
    assert "relay-test-secret" not in out
    assert "th-test-secret" not in out
    assert "jina-secret" not in out


def test_setup_non_interactive_rejects_legacy_flags(capsys):
    for flag, value in [
        ("--api-url", "https://api.example.com/v1"),
        ("--api-key", "sk-test-secret"),
        ("--api-mode", "chat-completions"),
        ("--model", "test-model"),
    ]:
        try:
            cli.main(["setup", "--non-interactive", flag, value])
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError(f"{flag} should be rejected by argparse")
        capsys.readouterr()


def test_setup_banner_falls_back_when_pyfiglet_unavailable(monkeypatch, capsys):
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "pyfiglet":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    cli._write_setup_banner("en")
    captured = capsys.readouterr()

    assert "Smart Search" in captured.err
    assert "CLI-first multi-source search" in captured.err


def test_tavily_url_normalization_cases():
    cases = {
        "pool.example.com": "https://pool.example.com/api/tavily",
        "https://pool.example.com": "https://pool.example.com/api/tavily",
        "https://pool.example.com/mcp": "https://pool.example.com/api/tavily",
        "https://pool.example.com/api/tavily": "https://pool.example.com/api/tavily",
        "https://api.tavily.com": "https://api.tavily.com",
    }

    for raw, expected in cases.items():
        assert cli._normalize_tavily_api_url(raw) == expected
    assert cli._normalize_tavily_api_url("https://custom.example.com", hikari=False) == "https://custom.example.com"
    assert cli._normalize_tavily_flag_api_url("https://custom.example.com", "tvly-key") == "https://custom.example.com"
    assert cli._normalize_tavily_flag_api_url("https://custom.example.com/mcp", "tvly-key") == "https://custom.example.com/api/tavily"
    assert cli._normalize_tavily_flag_api_url("https://custom.example.com", "th-key") == "https://custom.example.com/api/tavily"


def test_tavily_hikari_key_recommends_hikari_endpoint(monkeypatch):
    values = {"TAVILY_API_KEY": "th-test-secret"}
    seen = {}

    def fake_prompt_select(message, choices, default):
        seen["default"] = default
        return "hikari"

    monkeypatch.setattr(cli, "_prompt_select", fake_prompt_select)
    monkeypatch.setattr(cli, "_prompt_value", lambda *args, **kwargs: "https://pool.example.com/mcp")

    cli._prompt_tavily_api_url(values, {}, "en")

    assert seen["default"] == "hikari"
    assert values["TAVILY_API_URL"] == "https://pool.example.com/api/tavily"


def test_tavily_hikari_prompt_shows_beginner_url_example(monkeypatch, capsys):
    values = {"TAVILY_API_KEY": "th-test-secret"}

    monkeypatch.setattr(cli, "_prompt_select", lambda message, choices, default: "hikari")
    monkeypatch.setattr(cli, "_prompt_value", lambda *args, **kwargs: "https://pool.example.com")

    cli._prompt_tavily_api_url(values, {}, "zh")
    captured = capsys.readouterr()

    assert values["TAVILY_API_URL"] == "https://pool.example.com/api/tavily"
    assert "例如 https://pool.example.com" in captured.err
    assert "api/tavily" in captured.err


def test_zhipu_prompt_saves_official_api_url_and_search_engine(monkeypatch):
    values = {}
    selections = iter(["official", "search_pro_sogou"])

    monkeypatch.setattr(cli, "_prompt_select", lambda message, choices, default: next(selections))

    cli._prompt_zhipu_api_url(values, {}, "zh")
    cli._prompt_zhipu_search_engine(values, {}, "zh")

    assert values["ZHIPU_API_URL"] == "https://open.bigmodel.cn/api"
    assert values["ZHIPU_SEARCH_ENGINE"] == "search_pro_sogou"


def test_zhipu_prompt_allows_custom_search_engine(monkeypatch):
    values = {}
    selections = iter(["custom"])

    monkeypatch.setattr(cli, "_prompt_select", lambda message, choices, default: next(selections))
    monkeypatch.setattr(cli, "_prompt_value", lambda *args, **kwargs: "search_future")

    cli._prompt_zhipu_search_engine(values, {}, "en")

    assert values["ZHIPU_SEARCH_ENGINE"] == "search_future"


def test_setup_guided_zh_groups_minimum_capabilities(monkeypatch, capsys):
    saved = {}
    answers = iter(["openai", "https://relay.example.com/v1", "", "n", "context7", "tavily", "official", "skip", "n"])
    secrets = iter(["relay-test-secret", "context7-test-secret", "tavily-test-secret"])

    def fake_config_set(key, value):
        saved[key] = value
        return {"ok": True, "key": key, "value": "***", "config_file": "C:/tmp/config.json"}

    monkeypatch.setattr(cli.service, "config_set", fake_config_set)
    monkeypatch.setattr(cli.service, "config_path", lambda: {"ok": True, "config_file": "C:/tmp/config.json"})
    monkeypatch.setattr(cli.service, "config_list", lambda show_secrets=False: {"ok": True, "values": saved.copy()})
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: next(secrets))

    code = cli.main(["setup", "--lang", "zh"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert code == cli.EXIT_OK
    assert saved == {
        "OPENAI_COMPATIBLE_API_URL": "https://relay.example.com/v1",
        "OPENAI_COMPATIBLE_API_KEY": "relay-test-secret",
        "CONTEXT7_API_KEY": "context7-test-secret",
        "TAVILY_API_URL": "https://api.tavily.com",
        "TAVILY_API_KEY": "tavily-test-secret",
    }
    assert data["minimum_profile_ok"] is True
    assert data["minimum_profile_missing"] == []
    assert captured.out.lstrip().startswith("{")
    assert "Smart Search" in captured.err
    assert "不知道怎么填" in captured.err
    assert "main_search + docs_search + web_fetch" in captured.err
    assert "[1/3" in captured.err
    assert "main_search" in captured.err
    assert "pool.example.com" not in captured.out
    assert "relay-test-secret" not in captured.err
    assert "relay-test-secret" not in captured.out


def test_setup_guided_does_not_prompt_zhipu_by_default(monkeypatch, capsys):
    saved = {}
    answers = iter(["skip", "skip", "skip", "n"])

    def fake_config_set(key, value):
        saved[key] = value
        return {"ok": True, "key": key, "value": "***", "config_file": "C:/tmp/config.json"}

    def fail_getpass(prompt):
        raise AssertionError("guided setup must not prompt for Zhipu by default")

    monkeypatch.setattr(cli.service, "config_set", fake_config_set)
    monkeypatch.setattr(cli.service, "config_path", lambda: {"ok": True, "config_file": "C:/tmp/config.json"})
    monkeypatch.setattr(cli.service, "config_list", lambda show_secrets=False: {"ok": True, "values": saved.copy()})
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(cli.getpass, "getpass", fail_getpass)

    code = cli.main(["setup", "--lang", "zh"])
    captured = capsys.readouterr()

    assert code == cli.EXIT_OK
    assert "ZHIPU_API_KEY" not in saved
    assert "ZHIPU_API_URL" not in saved
    assert "ZHIPU_SEARCH_ENGINE" not in saved
    assert "Zhipu 已弃用为默认路径" in captured.err
    assert "智谱搜索服务" not in captured.err


def test_setup_guided_uses_tui_defaults_for_configured_providers(monkeypatch, capsys):
    current = {
        "OPENAI_COMPATIBLE_API_URL": "https://relay.example.com/v1",
        "OPENAI_COMPATIBLE_API_KEY": "relay-old-secret",
        "CONTEXT7_API_KEY": "ctx-old-secret",
        "FIRECRAWL_API_KEY": "firecrawl-old-secret",
        "FIRECRAWL_API_URL": "https://firecrawl.example.com/v2",
    }
    saved = {}
    checkbox_calls = []

    def fake_checkbox(message, choices):
        selected = [choice["value"] for choice in choices if choice.get("enabled")]
        checkbox_calls.append((message, selected))
        return selected

    monkeypatch.setattr(cli, "_checkbox_with_tui", fake_checkbox)
    monkeypatch.setattr(cli, "_select_with_tui", lambda message, choices, default=None: default)
    monkeypatch.setattr(cli.service, "config_set", lambda key, value: {"ok": True, "key": key, "value": "***"})
    monkeypatch.setattr(cli.service, "config_path", lambda: {"ok": True, "config_file": "C:/tmp/config.json"})
    monkeypatch.setattr(cli.service, "config_list", lambda show_secrets=False: {"ok": True, "values": {**current, **saved}})
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "")

    code = cli.main(["setup", "--lang", "en"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert code == cli.EXIT_OK
    assert data["minimum_profile_ok"] is True
    assert saved == {}
    assert "https://relay.example.com/v1" not in captured.err
    assert "https://firecrawl.example.com/v2" not in captured.err
    assert "configured" in captured.err
    assert checkbox_calls[:3] == [
        ("Choose main_search providers", ["openai-compatible"]),
        ("Choose docs_search providers", ["context7"]),
        ("Choose web_fetch providers", ["firecrawl"]),
    ]


def test_setup_guided_en_reports_missing_minimum(monkeypatch, capsys):
    saved = {}
    answers = iter(["skip", "skip", "skip", "n", "n"])

    def fake_config_set(key, value):
        saved[key] = value
        return {"ok": True, "key": key, "value": "***", "config_file": "C:/tmp/config.json"}

    monkeypatch.setattr(cli.service, "config_set", fake_config_set)
    monkeypatch.setattr(cli.service, "config_path", lambda: {"ok": True, "config_file": "C:/tmp/config.json"})
    monkeypatch.setattr(cli.service, "config_list", lambda show_secrets=False: {"ok": True, "values": saved.copy()})
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    code = cli.main(["setup", "--lang", "en"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert code == cli.EXIT_OK
    assert saved == {}
    assert data["minimum_profile_ok"] is False
    assert data["minimum_profile_missing"] == ["main_search", "docs_search", "web_fetch"]
    assert "Smart Search setup wizard" in captured.err
    assert "If unsure" in captured.err
    assert "main_search + docs_search + web_fetch" in captured.err
    assert "[MISSING] main_search primary search" in captured.err
    assert "will fail closed" in captured.err
    assert "your-relay.example.com" not in captured.out


def test_setup_guided_masks_configured_url_defaults(monkeypatch, capsys):
    current = {
        "OPENAI_COMPATIBLE_API_URL": "https://private-relay.example.com/v1",
        "OPENAI_COMPATIBLE_API_KEY": "relay-old-secret",
    }
    answers = iter(["openai", "", "", "", "skip", "skip", "n", "n"])
    secrets = iter([""])

    monkeypatch.setattr(cli.service, "config_set", lambda key, value: {"ok": True, "key": key, "value": "***"})
    monkeypatch.setattr(cli.service, "config_path", lambda: {"ok": True, "config_file": "C:/tmp/config.json"})
    monkeypatch.setattr(cli.service, "config_list", lambda show_secrets=False: {"ok": True, "values": current.copy()})
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: next(secrets))

    code = cli.main(["setup", "--lang", "en"])
    captured = capsys.readouterr()

    assert code == cli.EXIT_OK
    assert "https://private-relay.example.com/v1" not in captured.err
    assert "configured, press Enter to keep" in captured.err


def test_setup_guided_main_search_can_save_openai_compatible_peer(monkeypatch, capsys):
    saved = {}
    answers = iter(["openai", "https://relay.example.com/v1", "", "", "skip", "skip", "n", "n"])
    secrets = iter(["relay-test-secret"])

    def fake_config_set(key, value):
        saved[key] = value
        return {"ok": True, "key": key, "value": "***", "config_file": "C:/tmp/config.json"}

    monkeypatch.setattr(cli.service, "config_set", fake_config_set)
    monkeypatch.setattr(cli.service, "config_path", lambda: {"ok": True, "config_file": "C:/tmp/config.json"})
    monkeypatch.setattr(cli.service, "config_list", lambda show_secrets=False: {"ok": True, "values": saved.copy()})
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: next(secrets))

    code = cli.main(["setup", "--lang", "en"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert code == cli.EXIT_OK
    assert saved == {
        "OPENAI_COMPATIBLE_API_URL": "https://relay.example.com/v1",
        "OPENAI_COMPATIBLE_API_KEY": "relay-test-secret",
    }
    assert data["capability_status"]["main_search"]["configured"] == ["openai-compatible"]
    assert data["minimum_profile_missing"] == ["docs_search", "web_fetch"]
    assert "relay-test-secret" not in captured.out
    assert "relay-test-secret" not in captured.err


def test_setup_interactive_language_prompt(monkeypatch, capsys):
    saved = {}
    answers = iter(["en", "skip", "skip", "skip", "n", "n"])

    monkeypatch.setattr(cli.service, "config_set", lambda key, value: {"ok": True, "value": "***"})
    monkeypatch.setattr(cli.service, "config_path", lambda: {"ok": True, "config_file": "C:/tmp/config.json"})
    monkeypatch.setattr(cli.service, "config_list", lambda show_secrets=False: {"ok": True, "values": saved.copy()})
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    code = cli.main(["setup"])
    captured = capsys.readouterr()

    assert code == cli.EXIT_OK
    assert "Smart Search setup wizard" in captured.err


def test_search_passes_routing_options(monkeypatch, capsys):
    captured = {}

    async def fake_search(query, platform="", model="", extra_sources=0, validation="", fallback="", providers="auto"):
        captured.update({"validation": validation, "fallback": fallback, "providers": providers})
        return {"ok": True, "content": "Answer", "sources": [], "sources_count": 0}

    monkeypatch.setattr(cli.service, "search", fake_search)

    code = cli.main([
        "search",
        "query",
        "--validation",
        "strict",
        "--fallback",
        "off",
        "--providers",
        "grok,zhipu",
    ])

    assert code == cli.EXIT_OK
    assert captured == {"validation": "strict", "fallback": "off", "providers": "grok,zhipu"}
    assert json.loads(capsys.readouterr().out)["content"] == "Answer"


def test_provider_aliases_use_canonical_commands(monkeypatch, capsys):
    async def fake_exa_search(*args, **kwargs):
        return {"ok": True, "provider": "exa"}

    async def fake_zhipu_search(*args, **kwargs):
        return {"ok": True, "provider": "zhipu"}

    async def fake_context7_library(*args, **kwargs):
        return {"ok": True, "provider": "context7-library"}

    async def fake_context7_docs(*args, **kwargs):
        return {"ok": True, "provider": "context7-docs"}

    async def fake_research(*args, **kwargs):
        return {"ok": True, "query_mode": "research", "content": "Research"}

    monkeypatch.setattr(cli.service, "exa_search", fake_exa_search)
    monkeypatch.setattr(cli.service, "zhipu_search", fake_zhipu_search)
    monkeypatch.setattr(cli.service, "context7_library", fake_context7_library)
    monkeypatch.setattr(cli.service, "context7_docs", fake_context7_docs)
    monkeypatch.setattr(cli.service, "research", fake_research)

    assert cli.main(["exa", "query"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["provider"] == "exa"
    assert cli.main(["z", "query"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["provider"] == "zhipu"
    assert cli.main(["c7", "react"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["provider"] == "context7-library"
    assert cli.main(["c7docs", "/facebook/react", "hooks"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["provider"] == "context7-docs"
    assert cli.main(["rs", "query"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["query_mode"] == "research"


def test_setup_interactive_does_not_print_current_secret(monkeypatch, capsys):
    prompts = []

    def fake_config_set(key, value):
        return {"ok": True, "key": key, "value": "***", "config_file": "C:/tmp/config.json"}

    def fake_input(prompt):
        prompts.append(prompt)
        return ""

    def fake_getpass(prompt):
        prompts.append(prompt)
        return ""

    monkeypatch.setattr(cli.service, "config_path", lambda: {"ok": True, "config_file": "C:/tmp/config.json"})
    monkeypatch.setattr(
        cli.service,
        "config_list",
        lambda show_secrets=False: {
            "ok": True,
            "values": {
                "OPENAI_COMPATIBLE_API_KEY": "relay-test-secret",
                "OPENAI_COMPATIBLE_MODEL": "relay-model",
                "EXA_API_KEY": "exa-test-secret",
            },
        },
    )
    monkeypatch.setattr(cli.service, "config_set", fake_config_set)
    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(cli.getpass, "getpass", fake_getpass)

    code = cli.main(["setup", "--advanced", "--lang", "en"])
    captured = capsys.readouterr()
    prompt_text = "\n".join(prompts)

    assert code == cli.EXIT_OK
    assert "relay-test-secret" not in captured.out
    assert "relay-test-secret" not in captured.err
    assert "relay-test-secret" not in prompt_text
    assert "exa-test-secret" not in prompt_text
    assert "Exa API key optional [configured, press Enter to keep]" in prompt_text


def test_setup_advanced_mode_keeps_low_level_prompts(monkeypatch, capsys):
    prompts = []
    saved = {}

    def fake_config_set(key, value):
        saved[key] = value
        return {"ok": True, "key": key, "value": "***", "config_file": "C:/tmp/config.json"}

    def fake_input(prompt):
        prompts.append(prompt)
        return ""

    def fake_getpass(prompt):
        prompts.append(prompt)
        return ""

    monkeypatch.setattr(cli.service, "config_path", lambda: {"ok": True, "config_file": "C:/tmp/config.json"})
    monkeypatch.setattr(
        cli.service,
        "config_list",
        lambda show_secrets=False: {"ok": True, "values": {"OPENAI_COMPATIBLE_API_URL": "https://relay.example.com/v1"}},
    )
    monkeypatch.setattr(cli.service, "config_set", fake_config_set)
    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(cli.getpass, "getpass", fake_getpass)

    code = cli.main(["setup", "--advanced", "--lang", "en"])

    assert code == cli.EXIT_OK
    captured = capsys.readouterr()
    assert "Legacy primary API URL optional" not in captured.err
    assert "OpenAI-compatible API URL optional" in captured.err
    assert "Zhipu Web Search API URL optional" in captured.err
    assert "Zhipu search service" in captured.err
    assert "Advanced mode" in captured.err

