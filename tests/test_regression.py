from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PUBLIC_SKILL_DIR = ROOT / "skills" / "smart-search-cli"
PACKAGED_SKILL_DIR = ROOT / "src" / "smart_search" / "assets" / "skills" / "smart-search-cli"


def test_regression_does_not_create_repo_log_file():
    log_dir = ROOT / "logs"
    if not log_dir.exists():
        return
    assert not list(log_dir.glob("smart_search_*.log"))


def test_smart_search_skill_contract_enforces_cli_first():
    skill_dir = Path.home() / ".codex" / "skills" / "smart-search-cli"
    if not skill_dir.exists():
        return
    skill_files = [
        p
        for p in skill_dir.rglob("*")
        if p.is_file() and p.suffix in {".md", ".yaml", ".yml"}
    ]
    if not skill_files:
        return

    text = "\n".join(
        p.read_text(encoding="utf-8")
        for p in skill_files
    )

    forbidden_text = [
        "mcp__smart-search__",
        "get_sources",
        "get_config_info",
        "toggle_builtin_tools",
        "native web search fallback",
        "silently fallback",
    ]
    for phrase in forbidden_text:
        assert phrase not in text

    assert "native `web_search` is disabled" in text or "native web search is disabled" in text
    assert "do not silently fall back" in text


def _read_skill_tree(path: Path) -> str:
    return "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted(path.rglob("*"))
        if p.is_file() and p.suffix in {".md", ".yaml", ".yml"}
    )


def test_deep_research_skill_contract_public_and_packaged_assets_match():
    public_text = _read_skill_tree(PUBLIC_SKILL_DIR)
    packaged_text = _read_skill_tree(PACKAGED_SKILL_DIR)
    required_markers = [
        "Deep Research Mode",
        "深度搜索",
        "深度调研",
        "deep search",
        "deep research",
        "research_plan",
        "capability-based orchestration",
        "intent_signals",
        "capability_plan",
        "gap_check",
        "fetch_before_claim",
        "Do not treat Exa as the universal second hop",
        "Prefer Context7 before Exa",
        "decomposition",
        "usage_boundary",
        "search`, `exa-search`, `exa-similar`, `context7-library`, `context7-docs`, `fetch`, and `map`",
        "doctor` is preflight",
        "fixed topic recipe",
        "深度搜索一下最近的比特币行情",
        "resolved_evidence_dir",
        "SMART_SEARCH_EVIDENCE_DIR",
        "bilingual search steps",
        "does not depend on an MCP session",
        "SMART_SEARCH_RESEARCH_PREFERRED_PROVIDERS",
        "provider advantage routing",
        "`search --validation strict` uses the same bilingual web_search policy as balanced mode",
        "`search` runs bilingual web_search source discovery through Tavily / Firecrawl when configured",
        "Zhipu is deprecated from default routing",
        "Docs/API/library routing stays explicit keyword intent-based",
    ]
    for marker in required_markers:
        assert marker in public_text
        assert marker in packaged_text


def test_deep_research_cli_contract_documents_plan_and_smoke_matrix():
    public_contract = (PUBLIC_SKILL_DIR / "references" / "cli-contract.md").read_text(encoding="utf-8")
    packaged_contract = (PACKAGED_SKILL_DIR / "references" / "cli-contract.md").read_text(encoding="utf-8")
    required_markers = [
        "Deep Research Skill Contract",
        "`smart-search research` is the public live executor command",
        "must not change default `smart-search search` behavior",
        "`mode`: always `deep_research`",
        "`query_mode`: always `research`",
        "`question`: the user's research question",
        "`trigger_source`: usually `explicit_cli`",
        "`difficulty`: `standard` or `high`",
        "`intent_signals`: dimensional signals",
        "`decomposition`: subquestions for complex research",
        "`capability_plan`: the selected capability needs",
        "`evidence_policy`: default `fetch_before_claim`",
        "`preflight`: `doctor` guidance",
        "`steps`: ordered CLI command steps",
        "`gap_check`: how the executor verifies",
        "`final_answer_policy`: how to cite fetched evidence",
        "Allowed `tool` values are `search`, `exa-search`, `exa-similar`, `context7-library`, `context7-docs`, `fetch`, and `map`",
        "`doctor` is a `preflight` action, not a `steps[]` item",
        "must not require fixed topic recipe ids",
        "fixed topic recipe ids are not required schema",
        "research provider advantage routing",
        "`research --fallback auto` permits same-capability fallback",
        "Budget limits must not break evidence policy",
        "Even `--budget quick` plans must retain at least one `fetch` step",
        "`steps[].command` and `steps[].output_path` are one contract",
        "resolved_evidence_dir",
        "Prefer PowerShell-safe quoted commands",
    ]
    for marker in required_markers:
        assert marker in public_contract
        assert marker in packaged_contract


def test_search_timeout_retry_policy_is_distributable():
    public_text = _read_skill_tree(PUBLIC_SKILL_DIR)
    packaged_text = _read_skill_tree(PACKAGED_SKILL_DIR)
    public_contract = (PUBLIC_SKILL_DIR / "references" / "cli-contract.md").read_text(encoding="utf-8")
    packaged_contract = (PACKAGED_SKILL_DIR / "references" / "cli-contract.md").read_text(encoding="utf-8")

    skill_markers = [
        "Timeout Retry Policy",
        "error_type: \"network_error\"",
        "Retry up to 3 total attempts with `--timeout 180`",
        "`--extra-sources 1` during retry attempts",
        "Always use the CLI's `--timeout` option",
        "Do not wrap `smart-search` in a shell-level `timeout` command",
        "Do not rely on `SMART_SEARCH_RETRY_*` settings",
        "fall back to source-first evidence",
        "Run `exa-search` with the original query",
        "`fetch` the top 1-2 relevant URLs",
        "source_mode: \"fallback\"",
    ]
    contract_markers = [
        "Agent timeout handling contract",
        "`smart-search search ... --timeout 180 --extra-sources 1 --format json --output PATH`",
        "not a shell-level `timeout` wrapper",
        "`SMART_SEARCH_RETRY_*` settings are not the contract",
        "switch to source-first fallback",
        "`exa-search --include-domains`",
        "`source_mode: \"fallback\"`",
    ]

    for marker in skill_markers:
        assert marker in public_text
        assert marker in packaged_text
    for marker in contract_markers:
        assert marker in public_contract
        assert marker in packaged_contract


def test_deep_research_readme_documents_capability_orchestration():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    english_markers = [
        "Deep Research is not a fixed topic recipe system",
        "smart-search research",
        "`route_policy_version`",
        "provider-advantage",
        "`intent_signals`",
        "`decomposition`",
        "`capability_plan`",
        "`gap_check`",
        "`exa-similar`",
        "`context7-library`",
        "`doctor` is preflight, not a research step",
        "Unsupported key claims must be fetched or downgraded to unverified candidates",
    ]
    chinese_markers = [
        "Deep Research 不是固定题材配方",
        "smart-search research",
        "`route_policy_version`",
        "provider 优势",
        "`intent_signals`",
        "`decomposition`",
        "`capability_plan`",
        "`gap_check`",
        "`exa-similar`",
        "`context7-library`",
        "`doctor` 是 preflight 配置预检",
        "没有 fetch 的来源标为未验证候选",
    ]
    for marker in english_markers:
        assert marker in readme
    for marker in chinese_markers:
        assert marker in readme_zh


def test_readme_language_split_and_provider_links_are_documented():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    package_json = (ROOT / "package.json").read_text(encoding="utf-8")

    assert "[简体中文](README.zh-CN.md) | English" in readme
    assert "简体中文 | [English](README.md)" in readme_zh
    assert "## 中文" not in readme
    assert "## English" not in readme
    assert "README.zh-CN.md" in package_json

    provider_markers = [
        "https://platform.openai.com/docs",
        "https://platform.openai.com/api-keys",
        "https://docs.exa.ai/",
        "https://dashboard.exa.ai/api-keys",
        "https://context7.com/docs",
        "https://docs.bigmodel.cn/cn/guide/tools/web-search",
        "https://open.bigmodel.cn/usercenter/apikeys",
        "https://docs.tavily.com/",
        "https://app.tavily.com/home",
        "https://docs.firecrawl.dev/",
        "https://www.firecrawl.dev/app/api-keys",
    ]
    for marker in provider_markers:
        assert marker in readme
        assert marker in readme_zh


def test_deep_research_shared_skill_files_are_synchronized():
    shared_files = [
        "SKILL.md",
        "examples/batch-search.md",
        "examples/evidence-gathering.md",
        "references/cli-contract.md",
    ]
    for relative in shared_files:
        assert (PUBLIC_SKILL_DIR / relative).read_text(encoding="utf-8") == (
            PACKAGED_SKILL_DIR / relative
        ).read_text(encoding="utf-8")


def test_smart_search_skill_documents_personal_workflows_and_examples():
    public_text = _read_skill_tree(PUBLIC_SKILL_DIR)
    packaged_text = _read_skill_tree(PACKAGED_SKILL_DIR)
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    required_markers = [
        "## Workflows",
        "### Lightweight Evidence Gathering",
        "### Deep Research With Citations",
        "### Batch Search And Fetch",
        "### Evidence Archiving",
        "See `examples/evidence-gathering.md`",
        "See `examples/batch-search.md`",
        "# Evidence Gathering Workflow",
        "# Batch Search Workflow",
        "Use a PowerShell loop when several independent queries need the same source-discovery treatment.",
        "Confirm every claim maps to a fetched file or fetched URL.",
    ]
    for marker in required_markers:
        assert marker in public_text
        assert marker in packaged_text
    assert "assets/skills/smart-search-cli/examples/*.md" in pyproject


def test_search_routing_contract_documents_bilingual_web_search_policy():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    public_text = _read_skill_tree(PUBLIC_SKILL_DIR)
    packaged_text = _read_skill_tree(PACKAGED_SKILL_DIR)
    public_contract = (PUBLIC_SKILL_DIR / "references" / "cli-contract.md").read_text(encoding="utf-8")
    packaged_contract = (PACKAGED_SKILL_DIR / "references" / "cli-contract.md").read_text(encoding="utf-8")

    english_markers = [
        "Default `balanced` and `strict` `search` run bilingual `web_search` source discovery through Tavily / Firecrawl when configured",
        "`--validation fast` skips supplemental discovery",
        "Strict queries without primary, docs, fetch, or explicit source evidence",
        "source-first commands such as `exa-search`",
        "Docs supplemental routing stays keyword-based for explicit docs/API/library/framework intent",
        "Zhipu is retained only as a deprecated manual compatibility command",
        "`extra_sources` are explicit discovery candidates from `--extra-sources N`, which defaults to `0`",
    ]
    for marker in english_markers:
        assert marker in readme

    zh_markers = [
        "`balanced` 和 `strict` 的 `search` 默认通过 Tavily / Firecrawl 执行中英双语 `web_search` 来源发现",
        "`--validation fast` 跳过补强",
        "strict 查询仍可能返回 `evidence_error`",
        "`--extra-sources N`",
        "docs 补强继续保持显式 docs/API/库/框架关键词触发",
        "智谱只保留为 deprecated 手动兼容命令",
        "默认是 `0`",
    ]
    for marker in zh_markers:
        assert marker in readme_zh

    shipped_markers = [
        "`search --validation strict` uses the same bilingual web_search policy as balanced mode",
        "`search` runs bilingual web_search source discovery through Tavily / Firecrawl when configured",
        "Zhipu is deprecated from default routing",
        "explicit keyword-based docs/API/library/framework intent",
        "default `extra_sources` is `0`",
    ]
    for marker in shipped_markers:
        assert marker in public_text
        assert marker in packaged_text
        assert marker in public_contract
        assert marker in packaged_contract


def test_zhipu_setup_contract_public_and_packaged_assets_match():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    public_text = _read_skill_tree(PUBLIC_SKILL_DIR)
    packaged_text = _read_skill_tree(PACKAGED_SKILL_DIR)
    public_contract = (PUBLIC_SKILL_DIR / "references" / "cli-contract.md").read_text(encoding="utf-8")
    packaged_contract = (PACKAGED_SKILL_DIR / "references" / "cli-contract.md").read_text(encoding="utf-8")
    required_markers = [
        "--zhipu-api-url",
        "--zhipu-search-engine",
        "ZHIPU_API_URL",
        "ZHIPU_SEARCH_ENGINE",
        "search_std",
        "search_pro",
        "search_pro_sogou",
        "search_pro_quark",
        "Web Search API",
        "TAVILY_API_URL",
        "does not proxy Zhipu",
        "not Zhipu Chat Completions",
        "not the MCP Server",
        "deprecated manual compatibility",
        "not used by default routing",
    ]
    for marker in required_markers:
        assert marker in readme
        assert marker in public_text
        assert marker in packaged_text
    zh_required_markers = [
        "--zhipu-api-url",
        "--zhipu-search-engine",
        "ZHIPU_API_URL",
        "ZHIPU_SEARCH_ENGINE",
        "search_std",
        "search_pro",
        "search_pro_sogou",
        "search_pro_quark",
        "Web Search API",
        "TAVILY_API_URL",
        "不会代理智谱",
        "不是 Chat Completions",
        "不是 MCP Server",
    ]
    for marker in zh_required_markers:
        assert marker in readme_zh
    for marker in ["--zhipu-api-url", "--zhipu-search-engine"]:
        assert marker in public_contract
        assert marker in packaged_contract


def test_jina_contract_public_and_packaged_assets_match():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    public_text = _read_skill_tree(PUBLIC_SKILL_DIR)
    packaged_text = _read_skill_tree(PACKAGED_SKILL_DIR)
    public_contract = (PUBLIC_SKILL_DIR / "references" / "cli-contract.md").read_text(encoding="utf-8")
    packaged_contract = (PACKAGED_SKILL_DIR / "references" / "cli-contract.md").read_text(encoding="utf-8")

    required_markers = [
        "JINA_API_KEY",
        "JINA_READER_API_URL",
        "JINA_RESPOND_WITH",
        "Jina Reader is `web_fetch` only",
        "Anonymous Jina Reader calls",
    ]
    for marker in required_markers:
        assert marker in public_text
        assert marker in packaged_text
        assert marker in public_contract
        assert marker in packaged_contract

    readme_markers = [
        "JINA_API_KEY",
        "Jina Reader is not a general search provider",
    ]
    for marker in readme_markers:
        assert marker in readme

    zh_markers = [
        "JINA_API_KEY",
        "Jina Reader 不是通用搜索 provider",
    ]
    for marker in zh_markers:
        assert marker in readme_zh


def test_streaming_contract_public_and_packaged_assets_match():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    public_text = _read_skill_tree(PUBLIC_SKILL_DIR)
    packaged_text = _read_skill_tree(PACKAGED_SKILL_DIR)
    public_contract = (PUBLIC_SKILL_DIR / "references" / "cli-contract.md").read_text(encoding="utf-8")
    packaged_contract = (PACKAGED_SKILL_DIR / "references" / "cli-contract.md").read_text(encoding="utf-8")

    required_markers = [
        "OPENAI_COMPATIBLE_STREAM",
        "--stream",
        "--no-stream",
    ]
    for marker in required_markers:
        assert marker in readme
        assert marker in public_text
        assert marker in packaged_text
        assert marker in public_contract
        assert marker in packaged_contract

    zh_required_markers = [
        "OPENAI_COMPATIBLE_STREAM",
    ]
    for marker in zh_required_markers:
        assert marker in readme_zh


def test_deleted_features_absent_from_shipped_assets():
    """Guard: trimmed providers/commands/keys must not reappear in shipped docs/assets."""
    public_text = _read_skill_tree(PUBLIC_SKILL_DIR)
    packaged_text = _read_skill_tree(PACKAGED_SKILL_DIR)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    corpus = "\n".join([public_text, packaged_text, readme, readme_zh])

    forbidden = [
        "xai-responses",
        "XAI_",
        "anysearch",
        "ANYSEARCH",
        "zhipu-mcp",
        "ZHIPU_MCP",
        "smart-search smoke",
        "smart-search regression",
        "smart-search model",
        "smart-search skills",
        "smart-search deep ",
        "executed_by_deep_command",
    ]
    for token in forbidden:
        assert token not in corpus, f"deleted-feature reference leaked into shipped docs/assets: {token}"
