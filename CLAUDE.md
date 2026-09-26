# CLAUDE.md — working on the Slate repo

This repo is **Slate**, a Claude Code plugin: plan ideas into plain-language tickets on a kanban
board inside a project, then build them one ticket at a time with tests, review, the user's own
check, and the commit/PR recorded on the ticket — always with a human in the loop.

`AGENTS.md` is an exact copy of this file for other agent tools. **Edit both together.**

## 1. Read first

| Need | Read |
|---|---|
| What Slate is, every decision | `docs/specs/2026-09-26-slate-design.md` |
| How a release was built (contracts) | `docs/plans/*-build-plan.md` (newest last) |
| User-facing overview | `README.md`, `plugins/slate/README.md` |
| Every `board.py` command, "use it when…" | `plugins/slate/reference/commands.md` |
| What changed per version | `plugins/slate/CHANGELOG.md` |
| How to test on a machine by hand | `TEST.md` |
| Rejected designs kept for reference | `docs/archive/` |

## 2. Layout

```
.claude-plugin/marketplace.json      marketplace "slate" → plugins/slate
plugins/slate/                        the installed plugin (only this folder ships)
  .claude-plugin/plugin.json          name + VERSION (source of truth for the plugin version)
  skills/<name>/SKILL.md              /slate:init plan work review status sync upgrade
  assets/board/                       copied into each project's kanban/ by init/upgrade
    board.py                          the ONLY writer of tickets.json (CLI + serve API)
    index.html                        the board page (one file, no deps)
    README.md                         board docs copied into projects
  hooks/                              hooks.json, run.sh (python launcher), guard_tickets.py, session_start.py
  templates/                          SLATE.md, CLAUDE.md, AGENTS.md, plan-doc.md for projects
  reference/commands.md               shared command reference all skills link
  upgrades/<version>.md               per-release "What's new" + upgrade steps
  CHANGELOG.md  README.md
tests/                                pytest suite (+ fixtures/board-demo for the UI)
.github/workflows/test.yml            CI: Windows/macOS/Linux × Python 3.9/3.13
.github/workflows/release.yml         publishes vX.Y.Z releases from the CHANGELOG on merge
scripts/release_notes.py              prints a version's release notes from the CHANGELOG
TEST.md                               hands-on test guide for any machine
docs/                                 specs, build plans, archive
```

## 3. Rules that must hold in every change

- **Standard library only**, Python **3.9+**, in everything that ships (board.py, hooks). No
  pip dependencies. `index.html` loads nothing from the internet.
- **Works on Windows, macOS, Linux, over SSH and in tmux.** UTF-8 + `\n` for every file write,
  pathlib, no `shell=True`, no POSIX-only calls without a Windows path. Hooks go through
  `hooks/run.sh` (finds python3 / python / py -3).
- **`board.py` is the only thing that changes `tickets.json`.** Every write validates the whole
  board, takes the write lock, writes atomically. The guard hook blocks direct edits; don't
  weaken it.
- **Every error/refusal is actionable:** `error: <ID> <field>: …` then `fix: <exact command>` or
  `ask the user: …`. A test asserts this for every refusal path.
- **Backwards compatible.** Existing boards must keep loading. Schema changes are additive and go
  through `migrate` (bump `SCHEMA_VERSION` only when needed).
- **Human in the loop, always.** Skills do one ticket per request, ask before choices, never
  merge, never force-push. The unlock needs the user's approval (Claude Code's card in Manual /
  Accept edits / Auto; typed code in a terminal otherwise); one unlock = one edit.
- **Tickets are for non-technical readers** (summary, story, picture, "done when", "try it
  yourself"); technical notes stay collapsed.
- **Product text never mentions other internal projects** (e.g. "Forge"). Slate is generic.
- **Claude Code only for now.** Copilot CLI support is planned; don't add half-support.

## 4. Develop and test

```
uv run --with pytest pytest -q                  # full suite (≈800 tests)
uv run --python 3.9 --with pytest pytest -q     # oldest supported Python
claude plugin validate --strict .
claude plugin validate --strict plugins/slate
```

- Write tests first for every change: happy path + every refusal. UI changes: static checks in
  `tests/test_index_static.py` plus a real-browser check (Playwright) against
  `tests/fixtures/board-demo`, in live (`board.py serve`) and view-only mode.
- Live-test skills in a throwaway repo: `claude --plugin-dir plugins/slate`.
- **CI (`.github/workflows/test.yml`)** runs on every PR and push to `main`, but the full suite
  runs only when one of these changed: `plugins/**`, `tests/**`, `scripts/**`,
  `.github/workflows/**`, `.claude-plugin/**`, `.gitattributes`. Docs-only changes (README, TEST.md,
  CLAUDE.md, AGENTS.md, SECURITY.md, `docs/**`) pass in seconds with "no code changed". A manual
  run always runs everything. Keep this list and the workflow's list in step.
- `tests/test_docs_consistency.py` fails if a skill/doc mentions a command that doesn't exist,
  or a skill doesn't link the reference — keep it green.

## 5. Keeping docs in step (do this in the SAME change as the feature)

Every feature, fix or behaviour change updates **all** that apply, before it's considered done:

- [ ] **`plugins/slate/reference/commands.md`** — new/changed commands and flags, "use it when…".
- [ ] **Skills** (`plugins/slate/skills/*/SKILL.md`) that should use or mention it.
- [ ] **`plugins/slate/templates/SLATE.md`** if projects need to know or configure it.
- [ ] **`plugins/slate/assets/board/README.md`** (copied into projects) for board/CLI changes.
- [ ] **`README.md`** and **`plugins/slate/README.md`** for anything user-visible.
- [ ] **`plugins/slate/CHANGELOG.md`** — plain-words entry under the next version.
- [ ] **`plugins/slate/upgrades/<next-version>.md`** — "What's new" line + upgrade step if
      existing projects need anything (settings, .gitignore, SLATE.md, migrate, questions).
- [ ] **`TEST.md`** — add or adjust the hands-on check for the feature (and the expected result).
- [ ] **Spec** (`docs/specs/…`) for new decisions or commands.
- [ ] **Tests** — unit tests, docs-consistency, and UI static checks as relevant.
- [ ] **This file and `AGENTS.md`** if the rules, layout or workflow changed.

## 6. Releasing a version

1. Bump the version in **all** of: `plugins/slate/.claude-plugin/plugin.json`,
   `board.py` (`SLATE_VERSION`, header line), `index.html` (`slate-version` meta),
   `templates/SLATE.md` (first line), and `SCHEMA_VERSION` + `migrate` if the schema changed.
2. Finish `CHANGELOG.md` and `upgrades/<version>.md` (What's new first, then steps). The
   CHANGELOG section for the version is `## X.Y.Z — YYYY-MM-DD` with the headings **Highlights**,
   **Added**, **Changed**, **Fixed**, **Security**, **Removed**, **Upgrade notes** (leave out
   empty ones). `tests/test_release_notes.py` enforces this; preview the notes with
   `python3 scripts/release_notes.py`.
3. Full suite on 3.13 and 3.9, `claude plugin validate --strict`, `TEST.md` levels 3–4 on at
   least one machine, CI green on all three OSes.
4. Branch `feat/<version>`, draft PR with summary, verification and follow-ups; merge only when
   the user says so. Default branch is `main`, protected by a ruleset: no direct pushes (PR
   required), all 6 CI checks must pass, no force-push or deletion, no bypass. Merged branches are
   deleted automatically.
5. **Releases are automatic:** when a merge to `main` carries a new version in `plugin.json`,
   `.github/workflows/release.yml` tags `vX.Y.Z` and publishes a GitHub Release with that
   CHANGELOG section. Don't create release tags by hand (tags `v*` are protected).

## 7. Commits

Small, focused commits: `<area>: <what changed>` with a short body listing verification. Never
commit generated files (`__pycache__`, `.pytest_cache`, `.DS_Store` — see `.gitignore`).
