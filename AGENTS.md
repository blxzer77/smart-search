# AGENTS.md

## Purpose

This is the project-local instruction file for `D:\MyHarness\smartsearch-private`, a private deep-customization workspace derived from `konbakuyomu/smartsearch`.

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
- Read local evidence before editing: `README.md`, `README.zh-CN.md`, `package.json`, `pyproject.toml`, `src/`, `npm/`, `skills/`, `tests/`, `.trellis/workflow.md`, and relevant `.trellis/spec/` files.

## SmartSearch Private Workspace

The current repository may still have `origin` pointing at `https://github.com/konbakuyomu/smartsearch.git` until the user configures a private remote. Do not treat that remote as a push target.

## D:\MyHarness workspace (harness)

**Purpose path:** `D:\MyHarness\smartsearch-private` (this git repo). The harness root `D:\MyHarness` is **not** a git repository. Open Cursor at `D:\MyHarness` when you need workspace-level Trellis tasks, spec, and journals.

This package is one of **three independent git repositories** under the harness (there is **no** `.trellis/` directory inside this package):

| Path | Role |
| --- | --- |
| `D:\MyHarness\.trellis\` | Trellis workflow, tasks, spec, workspace journals (harness only) |
| `D:\MyHarness\smartsearch-private\` | **This repo** — smart-search Python package + npm wrapper |
| `D:\MyHarness\Trellis\` | Trellis CLI source; published as `@blxzer/trellis` |
| `D:\MyHarness\riverfjs-skills\` | Reusable agent skill directories |

**Trellis CLI (contributors):** `npm install -g @blxzer/trellis`. Do not confuse this with smart-search npm install docs (e.g. `@konbakuyomu/smart-search@next` in `README.md`).

Run **git** and **package tests** from **this directory**:

- `.\.venv\Scripts\python.exe -m pytest tests -q`
- `npm test`

See `D:\MyHarness\AGENTS.md` for harness-wide structure and per-repo commands.

<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->

