<!-- slate v0.1.0 · written by /slate:init, safe to edit values -->
# Slate: how we plan and build in {{PROJECT}}

> This is the project's living context for Slate. Every Slate command reads it first, and
> `/slate:plan` and `/slate:work` add to it as they learn. CLAUDE.md, AGENTS.md and the docs
> are still read for anything not written here. Edit it freely; keep it short and true.

## What this project is
{{PROJECT_CONTEXT}}

Board: `kanban/` · prefix `{{PREFIX}}` · open with `cd kanban && python3 -m http.server 8088`, then http://localhost:8088

## Commands
lint `{{LINT_CMD}}` · test `{{TEST_CMD}}` · types `{{TYPECHECK_CMD}}`

## Live test
{{LIVE_TEST}}

## Extra review checks
{{EXTRA_REVIEW_CHECKS}}

## Stop and ask before
{{STOP_AND_ASK}}

## Plan style
{{PLAN_STYLE}}

## Docs map
| need | read |
|---|---|
{{DOCS_MAP_ROWS}}

## Decisions
<!-- Project-wide choices that later tickets must respect. One line each: date · decision · why. -->

## Learned along the way
<!-- Gotchas, setup quirks, commands that turned out to matter. One line each: date · what · where it applies. -->

## Rules
Work tickets with /slate:work · change tickets only through kanban/board.py ·
branch `{{BRANCH_PATTERN}}` · draft PRs only, never merge.
