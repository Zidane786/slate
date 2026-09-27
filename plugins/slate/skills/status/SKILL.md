---
name: status
description: Report Slate board progress, read-only - phase progress, in-flight tickets with their last handoff line and who is on them, tickets waiting for the user to test (with steps), tickets waiting for their PR to be merged, drafts, unscheduled ideas, archived count, blocked tickets, workflow mode, board health (doctor), uncommitted work, the live board link and the next ticket. Use when asked "where are we", "status", "what's next", or at session start.
allowed-tools: Bash(python3 kanban/board.py *), Bash(python kanban/board.py *), Bash(py -3 kanban/board.py *), Bash(git status *), Bash(git log *)
---

# /slate:status — where are we?

**Read-only.** Change no tickets: no status changes, no edits, no upgrade, no sync. (Starting
the board server in step 0 is the only thing this skill may start.) Every command is in
`<ROOT>/reference/commands.md`.

## Step 0: version check and board server

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code). If it still reads literally,
   use this skill's base directory (printed when the skill loads) + `/../..`, made absolute.
2. If `kanban/board.py` is missing: say "This repo isn't set up for Slate yet — run
   `/slate:init`." and stop.
3. Skim `SLATE.md` for the project name (fall back to the `status` header), the Python command
   (use it instead of `python3` when it names another, e.g. `py -3`), `Board server` and
   `Board port`.
4. `python3 kanban/board.py version --against "<ROOT>"` → keep the result for the report's
   version line (`behind` → suggest `/slate:upgrade`; `ahead` → update the plugin).
5. **Board server.** Unless `SLATE.md` says `Board server: off`:
   `python3 kanban/board.py serve --ensure --port <Board port, default 8088>` → keep the URL for
   the report (show it once per conversation). If `serve` isn't in `--help` (an older board), skip it.

## Gather

```bash
python3 kanban/board.py status
python3 kanban/board.py next
python3 kanban/board.py list 5
python3 kanban/board.py check --quiet-optional
python3 kanban/board.py doctor --against "<ROOT>" --json
python3 kanban/board.py export --json --statuses
python3 kanban/board.py export --json --status <names of the in_progress, review, user_testing, merge_ready roles>
python3 kanban/board.py export --json --removed
git status --short 2>/dev/null; git log --oneline -5 2>/dev/null
```

Get ticket details from `export --json` (filters: `--phase`, `--status`, `--label`, `--area`,
`--drafts`) or `show <ID>` / `show <ID> --json`, **never** by reading `kanban/tickets.json`
directly. `status` and `list` take the same filters (e.g. `status --label bug`).

- `export --json --statuses` gives each state's name, **label** (column title) and **role**,
  and the workflow mode (`free`, `strict` or custom). Always report states by their label, and
  pick "in flight", "waiting for you" and "waiting for merge" by role, so renamed or custom
  states (e.g. a "QA" column with the review role) are counted where they belong.
- From the ticket export: the last handoff note of each in-flight ticket, its `claimed_by`
  (who is on it), the user tests and their recorded results, and the PR of each merge_ready
  ticket. Drafts and unscheduled tickets from `status` (or `status --json`); archived tickets =
  the length of `export --json --removed`.
- From `doctor --json`: problems of kind `setup` and of kind `tickets`.
- If board.py prints a board-of-record warning (another worktree or branch has newer tickets),
  include it in the report with its `fix:` lines.

## Report (under 220 words)

1. **Phases:** a small table, phase · done/total, plus what was left out of the total when there
   is any: "3/15 done · 1 cancelled" (from `status --json`: `total` already leaves out cancelled
   and other excluded states; `excluded_by` gives the count per state — name them by label).
   Cancelled tickets are finished, not done, and never "blocked".
2. **In flight:** each ticket in an in_progress- or review-role state: id, title, state label,
   **on: <claim>** (branch or agent), last handoff line.
3. **Waiting for you to test:** each user_testing-role ticket with its user tests as short
   numbered steps + what you should see, and which already passed. Say how to record a result:
   tell Claude "pass" / "fail: …", click Pass / Fail on the live board, or run
   `/slate:work <ID>`.
4. **Waiting for merge:** each merge_ready-role ticket with its PR link and state. Say: "Tell
   me when a PR is merged and I'll close the ticket (`/slate:work <ID>`)."
5. **Drafts:** how many, and "finish one with `/slate:plan <ID>`". **Unscheduled:** how many
   someday tickets (not offered by `next`). **Archived:** how many removed tickets (restorable
   with `/slate:plan`), only when there are any.
6. **Blocked:** tickets waiting on unfinished dependencies (a cancelled dependency no longer
   blocks; `dep_exceptions` on a ticket are dependencies the user agreed it may stay past), open questions, or claimed by
   someone else, and why (bug tickets, labelled `bug` / `fixes-<ID>`, show which ticket waits
   for them).
7. **Workflow:** one line only when it isn't `free`: "Workflow: strict — Backlog → In progress →
   Review → User testing → Waiting for merge → Done" (or the custom path, with labels).
8. **Health:** from `doctor`: `setup` problems → "N setup issues — run `/slate:upgrade`";
   `tickets` problems (board behind the default branch, board errors, unreadable board) →
   "board needs sorting — run `/slate:sync`"; a stale write lock or an active unlock → name it
   with its `fix:` line. Plus any `check` errors, uncommitted work from `git status`, and any
   board-of-record warning. Say "healthy" in one word when there is nothing.
9. **Next:** the ticket `next` recommends.
10. **Board:** "Live board: <url>" when the server runs (and the SSH hint
    `ssh -L <port>:localhost:<port> <host>` if the user is on a remote machine), once.
11. **Version line** only when the board is behind or ahead of the plugin.
