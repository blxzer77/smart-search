<!-- CSTL:START -->
# Cursor-Trellis (cstl) Instructions

These instructions are for AI assistants working in this project.

**Thin-connect to the harness root instance (2026-08-16 决策落地)**: this repo has **no independent `.cstl/`**. The cstl runtime and all working knowledge live in the **harness root instance** `D:\MyHarness\.cstl`:

- `D:\MyHarness\.cstl/workflow.md` — development phases, when to create tasks, skill routing
- `D:\MyHarness\.cstl/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `D:\MyHarness\.cstl/workspace/` — per-developer journals and session traces
- `D:\MyHarness\.cstl/tasks/` — active and archived tasks (PRDs, research, jsonl context)

When a cstl command is available on Cursor (e.g. `cstl-finish-work`, `cstl-continue`), prefer it over manual steps. CLI/hook scripts run from this directory resolve to the root instance automatically (nearest-`.cstl` upward lookup). Tasks for this repo live under `D:\MyHarness\.cstl/tasks/`; mark them with `--package smart-search` when creating.

## Web research routing (smart-search first)

For **any external / current / web fact**, run **`python ./.cstl/scripts/run_smart_search.py "<question>" --intent deep-research --json`** first (from the harness root, or via `d:\MyHarness\.cstl\scripts\...` absolute path). That script is the **only** cstl web-research evidence entrypoint (it shells out to the `smart-search` CLI — this repo's package). Platform built-in web tools (Cursor `WebSearch` / `WebFetch`) are **downgrade-only fallbacks**. On Cursor, `smart-search-cli` is an **internal workflow skill name** only; follow `.cstl/framework/retrieval-daily-guide.md` and `.cursor/rules/retrieval-routing.mdc` for the executable contract.

**External-knowledge gate:** If the answer would be wrong because the **world or a third-party API moved** and that matters → use smart-search (cheap `docs` / `broad-search` when enough; `deep-research` when multi-source). If truth lives only in this workspace → do not default to web.

Managed by cursor-trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `cstl update`.

<!-- CSTL:END -->

# AGENTS.md

## Purpose

This is the project-local instruction file for `D:\MyHarness\smart-search`, a private deep-customization workspace derived from `konbakuyomu/smartsearch`.

This is not a fork/PR contribution workspace. Optimize for the user's private workflow and long-term maintainability, while preserving upstream license obligations.

## Language

- User-facing replies must be in Simplified Chinese unless the user explicitly requests another language.
- Tool prompts, search queries, command descriptions, model handoffs, and technical operating language should be in English when practical.
- Preserve exact identifiers, paths, commands, config keys, package names, provider names, and citations when translation would reduce precision.

## Project Boundaries

- Preserve `LICENSE` and upstream copyright notices.
- Do not push to upstream, publish npm packages, install dependencies, start services, or change credentials unless the user explicitly asks.
- Treat provider keys and local configuration as secrets; never copy them into tracked files or replies.
- Prefer small, reversible edits and validate with the smallest relevant tests or checks.
- Read local evidence before editing: `README.md`, `README.zh-CN.md`, `package.json`, `pyproject.toml`, `src/`, `npm/`, `skills/`, and `tests/`.

## SmartSearch Private Workspace

The current repository may still have `origin` pointing at `https://github.com/konbakuyomu/smartsearch.git` until the user configures a private remote. Do not treat that remote as a push target.

## D:\MyHarness workspace (harness)

**Purpose path:** `D:\MyHarness\smart-search` (this git repo). The harness root `D:\MyHarness` is a **local-only git repository** (git-ified 2026-08-14). Open Cursor at `D:\MyHarness` for workspace-level cstl (`.cstl`) tasks, spec, and journals; opening at this repo works too — the `.cursor/hooks` here thin-connect to the harness root instance.

This package is one of **four independent git repositories** under the harness (there is **no** `.cstl/` directory inside this package; cstl runtime resolves upward to the harness root):

| Path | Role |
| --- | --- |
| `D:\MyHarness\.cstl\` | cursor-trellis workflow, tasks, spec, workspace journals (harness root instance) |
| `D:\MyHarness\smart-search\` | **This repo** — smart-search Python package + npm wrapper |
| `D:\MyHarness\cursor-trellis\` | cursor-trellis CLI source; published as `@blxzer/cursor-trellis` |
| `D:\MyHarness\blaze-skills\` | Reusable agent skill directories |
| `D:\MyHarness\cursor-byok\` | BYOK fork workspace (upstream leookun/cursor-byok) |

**cursor-trellis CLI (contributors):** `npm install -g @blxzer/cursor-trellis`. Do not confuse this with smart-search npm install docs (e.g. `@konbakuyomu/smart-search@next` in `README.md`).

Run **git** and **package tests** from **this directory**:

- `.\.venv\Scripts\python.exe -m pytest tests -q`
- `npm test`

**Branch policy (mandatory):** **`main` is integration/release only — never develop on `main`.** Before any durable edit, create or checkout a short-lived branch (`feat/…`, `fix/…`). Harness-wide rule: `D:\MyHarness\.cursor\rules\feature-branch-policy.mdc`.

See `D:\MyHarness\AGENTS.md` for harness-wide structure and per-repo commands.

