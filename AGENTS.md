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

**Purpose path:** `D:\MyHarness\smart-search` (this git repo). The harness root `D:\MyHarness` is **not** a git repository. Open Cursor at `D:\MyHarness` when you need workspace-level cursor-trellis (`.cstl`) tasks, spec, and journals.

This package is one of **three independent git repositories** under the harness (there is **no** `.trellis/` or `.cstl/` directory inside this package):

| Path | Role |
| --- | --- |
| `D:\MyHarness\.cstl\` | cursor-trellis workflow, tasks, spec, workspace journals (harness only) |
| `D:\MyHarness\smart-search\` | **This repo** — smart-search Python package + npm wrapper |
| `D:\MyHarness\cursor-trellis\` | cursor-trellis CLI source; published as `@blxzer/cursor-trellis` |
| `D:\MyHarness\riverfjs-skills\` | Reusable agent skill directories |

**cursor-trellis CLI (contributors):** `npm install -g @blxzer/cursor-trellis`. Do not confuse this with smart-search npm install docs (e.g. `@konbakuyomu/smart-search@next` in `README.md`).

Run **git** and **package tests** from **this directory**:

- `.\.venv\Scripts\python.exe -m pytest tests -q`
- `npm test`

**Branch policy (mandatory):** **`main` is integration/release only — never develop on `main`.** Before any durable edit, create or checkout a short-lived branch (`feat/…`, `fix/…`). Harness-wide rule: `D:\MyHarness\.cursor\rules\feature-branch-policy.mdc`.

See `D:\MyHarness\AGENTS.md` for harness-wide structure and per-repo commands.

