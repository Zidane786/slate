---
name: status
description: Report Slate board progress, read-only - phase progress, in-flight tickets with their last handoff line, tickets waiting for the user to test (with steps), drafts, blocked tickets, uncommitted work and the next ticket. Use when asked "where are we", "status", "what's next", or at session start.
allowed-tools: Bash(python3 kanban/board.py *), Bash(git status *), Bash(git log *)
---

# /slate:status — where are we?

**Read-only.** Change nothing: no status changes, no edits, no upgrade.

## Step 0: version check

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code). If it still reads literally,
   use this skill's base directory (printed when the skill loads) + `/../..`, made absolute.
2. If `kanban/board.py` is missing: say "This repo isn't set up for Slate yet — run
   `/slate:init`." and stop.
3. `python3 kanban/board.py version --against "<ROOT>"` → keep the result for the report's
   version line (`behind` → suggest `/slate:upgrade`; `ahead` → update the plugin).
4. Skim `SLATE.md` for the project name (fall back to `meta.project`).

## Gather

```bash
python3 kanban/board.py status
python3 kanban/board.py next
python3 kanban/board.py list 5
python3 kanban/board.py check
git status --short 2>/dev/null; git log --oneline -5 2>/dev/null
```

Then `python3 kanban/board.py show <ID>` for every ticket in `in_progress`, `review` or
`user_testing` (last handoff line; the user tests and their recorded results).
Count tickets with status `draft` from `status` (or `status --json`).

## Report (under 200 words)

1. **Phases:** a small table, phase · done/total.
2. **In flight:** each `in_progress` / `review` ticket with its last handoff line.
3. **Waiting for you to test:** each `user_testing` ticket with its user tests as short
   numbered steps + what you should see, and which already passed. Say how to record a
   result: tell Claude "pass" / "fail: …", or run `/slate:work <ID>`.
4. **Drafts:** how many, and "finish one with `/slate:plan <ID>`".
5. **Blocked:** tickets waiting on unfinished dependencies or open questions, and why.
6. **Uncommitted work** from `git status`, and any `check` errors.
7. **Next:** the ticket `next` recommends.
8. **Version line** only when the board is behind or ahead of the plugin.
