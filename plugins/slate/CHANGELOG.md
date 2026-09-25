# Changelog

All notable changes to Slate. Versions follow the plugin's `plugin.json`; the board's schema
version is noted when it changes.

## 0.1.0 — 2026-09-26

First release. Board schema version 1.

- **Plugin and marketplace:** install with `/plugin marketplace add Zidane786/slate` and
  `/plugin install slate@slate`.
- **Six commands:** `/slate:init`, `/slate:plan`, `/slate:work`, `/slate:review`,
  `/slate:status`, `/slate:upgrade`.
- **Board** (`kanban/index.html`): project-neutral kanban with board and implementation-order
  views, plain-language ticket drawer (summary, story, picture, done when, try it yourself,
  automated tests, details, collapsed technical notes, history), Draft and User testing
  columns, "needs you" badge, and a preview of unsaved tickets from `kanban/preview.json`.
- **`kanban/board.py`:** the only writer of `tickets.json` — `init`, `next`, `list`, `show`,
  `status`, `check`, `version`, `new`, `add` (batch files, `--dry-run` preview, `--as-draft`),
  `batch-check`, `discard-preview`, `set`, `edit`, `rerank`, `promote`, `add-phase`,
  `usertest`, `link`, `set-meta`, `upgrade`, `migrate`. Validates every write and writes atomically.
- **Tickets for non-developers:** plain title and summary, story, visual, "When …, then …"
  test scenarios, and required user tests for anything visible.
- **Drafts:** saved-but-unfinished tickets that `/slate:work` never picks.
- **Human in the loop:** `/slate:work` builds one ticket per request (the one you name, or
  the suggested next one after you say yes), waits while you test, and stops when it's done.
- **Code on the ticket:** `board.py link` records commits and the PR on a ticket; the board
  shows them under "Code changes". `set … done` refuses without a linked commit (and without
  a PR when the repo has a remote); `--no-code` / `--no-pr` record why, only with your OK.
- **Actionable errors:** every refusal prints `fix:` lines with the exact command to run, or
  `ask the user:` when a person must decide.
- **`set-meta`** for project name, `repo_url` (links commits on the board), areas.
- **`SLATE.md`:** living per-project context (what the project is, decisions, lessons learned), commands, live test, review checks, stop-and-ask rules, plan
  style and docs map, written by `/slate:init`.
- **Hooks:** a one-line board summary at session start, and a guard that blocks direct edits
  to `kanban/tickets.json`.
- **Versioning:** every copied file carries its version; skills offer `/slate:upgrade` when the
  project's board is behind the plugin.
