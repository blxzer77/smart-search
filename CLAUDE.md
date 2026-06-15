# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`@konbakuyomu/smart-search` is a CLI-first multi-source web research tool. It is an **npm package that wraps a Python CLI**: the npm `bin` launcher (`npm/bin/smart-search.js`) spawns a dedicated Python venv and runs `python -m smart_search.cli`. All real logic is Python (`src/smart_search/`, importable as the `smart_search` module). Node only bootstraps the runtime and forwards args/stdio.

This is a **private deep-customization workspace** derived from upstream `konbakuyomu/smartsearch`. See `AGENTS.md` for project boundaries (do not push upstream, publish, or treat `origin` as a push target unless asked). Distribution stays MIT-licensed; preserve `LICENSE`.

## Commands

Two Python venvs are referenced in this repo and **neither is committed** — create one before running anything:
- `.venv/` — manual dev venv used by the README's Development section.
- `.smart-search-python/` — auto-created by `npm install` (postinstall), used by the npm wrapper and `npm test`.

Tests put `src/` on `sys.path` via `tests/conftest.py`, so pytest only needs the runtime deps installed (`httpx[socks]`, `InquirerPy`, `pyfiglet`, `rich`, `tenacity`), not necessarily an editable install. The autouse fixture isolates config to a tmp dir and sets `SMART_SEARCH_MINIMUM_PROFILE=off`.

```bash
# Set up a dev venv (example; pick your interpreter)
python -m venv .venv && .venv/Scripts/python.exe -m pip install -e ".[dev]"

# Tests / checks (run with the venv's python)
python -m pytest tests -q                          # full suite
python -m pytest tests/test_service.py -q           # one file
python -m pytest tests/test_cli.py::test_name -q    # one test
python -m compileall -q src tests                   # syntax/byte-compile check
python -m smart_search.cli regression               # offline CLI regression
python -m smart_search.cli smoke --mock --format json  # offline provider-routing smoke

# Full release-shaped check (requires .smart-search-python from `npm install`)
npm test     # pip install -e .[dev] -> pytest -> wrapper-repair -> --help -> UTF-8 deep check -> npm pack --dry-run
npm pack --dry-run
```

`npm test` (`npm/scripts/test.js`) is the authoritative pre-release gate and asserts the npm wrapper preserves non-ASCII CLI args / UTF-8 JSON. Version is kept in sync between `package.json` and `pyproject.toml` by `npm run set-version` / the `version` script (`sync-python-version.js`).

## Architecture

The dependency direction is **`cli.py` → `service.py` → `providers/` + `config.py` + `sources.py`**. Read `service.py` first — it is the orchestration core and the largest file.

### Request flow
1. `cli.py:build_parser()` defines every subcommand (argparse). `main()` dispatches: sync commands (`regression`, `setup`, `skills`, `config`, `model`) run inline; everything else runs through `asyncio.run(_run_async(args))`.
2. `_run_async` maps each command to one `service.*` async function (e.g. `search`, `research`, `fetch`, `exa_search`, `doctor`). Service functions **always return a result dict** (never raise to the CLI); errors are encoded as `{"ok": false, "error_type": ...}`.
3. `cli.py` rendering layer (`_render` / `_format_markdown` / `_format_content` / `_print_result`) turns that dict into `json` / `markdown` / `content` output, and `_exit_code` maps `error_type` to process exit codes: `0` ok, `2` parameter, `3` config, `4` network, `5` runtime.

### Capability-based provider routing (the core mental model)
`service.py` defines `PROVIDER_PROFILES` (each provider declares a `capability`/`capabilities`) and `RESEARCH_PROFILE_ORDER` (per-capability provider order). **Fallback is same-capability only** — a provider never substitutes across capability boundaries.

| Capability | Providers (in fallback order) | Notes |
| --- | --- | --- |
| `main_search` | `xai-responses` → `openai-compatible` | `MAIN_SEARCH_FALLBACK_CHAIN` |
| `docs_search` | `context7`, `exa` | library/API docs vs official-domain/paper discovery |
| `web_search` | `zhipu` → `zhipu-mcp` → `tavily` → `firecrawl` | Chinese/current/domain-filtered discovery |
| `web_fetch` | `tavily` → `jina` → `zhipu-mcp-reader` → `firecrawl` | exact-URL content extraction |
| `vertical_search` | `anysearch` | experimental; **not** in any fallback chain |
| `site_map` | `tavily` | |
| `synthesis` | `main-search` | evidence-only final synthesis used by `research` |

`research` uses a capability-first + provider-advantage router (`_research_capability_routes`, intent/keyword signals) overridable via `SMART_SEARCH_RESEARCH_PREFERRED_PROVIDERS` / `SMART_SEARCH_RESEARCH_DISABLED_PROVIDERS` (reorder/disable within a capability only).

### Providers (`src/smart_search/providers/`)
Each provider subclasses `BaseSearchProvider` (`base.py`: abstract `async search()` + `get_provider_name()`) and returns `SearchResult` objects. `xai_responses.py` (Responses API `/responses`) and `openai_compatible.py` (Chat Completions `/chat/completions`) are the two `main_search` backends; the rest are source/fetch providers.

### Config (`config.py`)
`Config` is a singleton exported as `config`. Resolution order per key: **environment variable first, then the JSON config file**. Only keys in `Config._CONFIG_KEYS` are valid (`set_config_value` rejects others). Secrets are masked in any display path. Config dir resolution: `SMART_SEARCH_CONFIG_DIR` override → on Windows `%LOCALAPPDATA%\smart-search` (with a `~/.config/smart-search` legacy-home fallback) → `~/.config/smart-search`.

`validate_minimum_profile()` enforces the `standard` minimum profile and **fails closed**: at least one configured provider each for `main_search`, `docs_search`, and `web_fetch`. `search` and `research` both gate on it.

### Output post-processing (`sources.py`)
`split_answer_and_sources()` separates the model's prose from a sources/citations block (tries function-call payloads, headings, `<details>` blocks, trailing link lists, and inline `[[n]](url)` citations). `sanitize_answer_text()` strips `<think>` blocks and leading policy-refusal paragraphs (gated by `SMART_SEARCH_OUTPUT_CLEANUP`).

### Skills installer (`skill_installer.py`)
Bundles the `smart-search-cli` skill (`src/smart_search/assets/skills/...` and `skills/`) and installs/refreshes it into per-tool skill roots (`SKILL_TARGETS`: codex, claude, cursor, …). Powers `smart-search skills status|update` and the skill step of `setup`.

## Invariants that are easy to break

- **Keep the two main-search routes separate.** xAI live search = Responses API via `XAI_*`. OpenAI-compatible = Chat Completions via `OPENAI_COMPATIBLE_*`. Never send xAI `web_search`/`x_search` tools or legacy `search_parameters` into the OpenAI-compatible route.
- **Legacy `SMART_SEARCH_API_*` keys are not supported** — use `XAI_*` or `OPENAI_COMPATIBLE_*`.
- **`search` is live, `deep` is offline planning, `research` is live staged execution.** `deep`/`build_deep_research_plan` must not call providers.
- **`extra_sources` are discovery candidates, not verified evidence.** For high-risk claims, `fetch` key URLs and cite fetched text (see `SOURCE_PROVENANCE_WARNING`).
- AnySearch is experimental and deliberately excluded from fallback chains and the minimum profile.
- The npm wrapper must preserve non-ASCII args and UTF-8 JSON (it sets `PYTHONIOENCODING`/`PYTHONUTF8`); `npm test` asserts this.

## Workflow & conventions

Development for this package is coordinated from the **D:\MyHarness** harness. Trellis state lives at **`D:\MyHarness\.trellis\`** (not under `smartsearch-private/`). Use `D:\MyHarness\.trellis\workflow.md` as the workflow source of truth (Plan → Execute → Finish, with a personal No-Task / Micro-Grill / Lite / Full mode ladder); layer guidelines are under `D:\MyHarness\.trellis\spec\`; tasks live under `D:\MyHarness\.trellis\tasks\`. From the harness root, context scripts run as `python ./.trellis/scripts/get_context.py` (and `--mode phase` when needed). Install the CLI with `npm install -g @blxzer/trellis`. Prefer `/trellis:*` commands when available.

**Language policy** (from `AGENTS.md` and the harness `workflow.md`): user-facing replies in Simplified Chinese unless asked otherwise; tool prompts, search queries, command descriptions, and technical delegation in English. Preserve exact identifiers, paths, config keys, and provider names verbatim.
