# Changelog

All notable changes to Slate. Versions follow the plugin's `plugin.json`; the board's schema
version is noted when it changes.

## 0.2.0 — 2026-09-26

Board schema version 2. Older boards keep working; `/slate:upgrade` (or `board.py migrate`)
upgrades them by adding only. Every item below came from using Slate on a real project with
about 60 tickets, stacked PRs, parallel agents and git worktrees.

**Planning and editing tickets**

1. `edit-phase` changes a phase's name, goal, demo or unscheduled flag.
2. `rename-phase OLD NEW` changes a phase id and moves its tickets with it.
3. `remove-phase` removes a phase; it refuses while tickets use it unless you say where they go
   (`--move-to`).
4. `reorder-phases` sets the order phases are shown in.
5. **Unscheduled phases** hold someday ideas (for example `BACKLOG`): `next`, `list` and
   `/slate:work` skip them, the board shows them last and folded with an `unscheduled` tag,
   and a ticket there can't move forward until it's moved to a real phase.
6. Repeating a flag adds to it (`--acceptance`, `--test`, `--user-test-json`, `--labels`,
   `--areas`, `--depends`); the last three also take comma lists.
7. `edit ID description+="…"` adds text to the end of a text field instead of replacing it.
8. **Bug tickets:** `new --bug --fixes ACME-004` labels the ticket `bug` and `fixes-ACME-004`,
   ranks it just before the ticket it fixes and makes that ticket wait for it. A fixed ticket
   that is already done is only reopened when you agree (`--reopen`).
9. `edit … --rerank` moves a ticket after its dependencies when you change them, and the rank
   error now suggests it.
10. `set ID in_progress --ignore-deps "why"` starts a ticket before its dependencies are done
    (for stacked work); the reason is kept in the note. Waiting for merge and Done stay strict.
11. **Several tickets at once:** `set ID1,ID2 …` and `link ID1,ID2 --pr URL`. All or nothing:
    if one is refused, none is changed.
12. `export --json` gives full tickets, filtered by phase, status, label or area, so agents
    don't read `tickets.json` directly.
13. `list` and `status` take the same filters.
14. `check --quiet-optional` (or `meta.check_quiet_optional`) hides warnings about optional
    fields and says how many it hid.

**Branches, worktrees and merges**

15. `diff OTHER` shows how this board differs from another one: a file, a folder or a git
    branch. Rank-only changes are hidden unless asked for.
16. `sync --from OTHER` brings another board's changes in: new tickets are added, notes,
    commits and ticks are combined, and the status that is further along wins.
17. **Merge driver:** `install-merge-driver` makes git merge `tickets.json` ticket by ticket
    instead of leaving conflict markers in the JSON; only real conflicts are reported.
18. **Board of record:** board.py warns when you write in a secondary worktree, outside the
    board named by `SLATE_BOARD_OF_RECORD`, or on a board missing tickets the default branch
    has, and tells you the `diff` / `sync` command to run. `/slate:work` stops and asks.
19. `copy-to PATH` writes a checked copy of the board somewhere else, refusing to overwrite
    newer changes unless `--force`.

**The guard and hand edits**

20. The guard no longer blocks reading `tickets.json` from Python (`json.load(open(…))`):
    `open(…)` counts as a write only with a `w`, `a`, `x` or `+` mode. Git operations on the
    file (checkout, restore, merge, rebase, stash) are allowed; the next board.py call checks
    the file anyway.
21. **Unlock:** when a hand edit is truly needed, Claude explains why and runs
    `board.py unlock --reason "…"`. The guard makes Claude Code show its own permission card
    for that command in Manual, Accept edits and Auto mode, and your Yes is the approval (it
    works over SSH too, in any terminal). In Plan, Bypass permissions and Don't-ask mode the
    command is refused, and you run `unlock` in your own terminal and type the 4-letter code it
    shows. One unlock allows exactly one direct edit, then it's used up; unlocks expire (at
    most 30 minutes), are logged in `meta.unlock_log`, and the unlock files can't be edited
    directly. `lock` cancels one early. Copilot CLI support: planned.

**The board page**

22. **Live refresh:** the served board re-reads `tickets.json` and `preview.json` every few
    seconds while the tab is visible (backing off when nothing changes) and redraws in place, keeping your view, filters, scroll
    and open ticket, with a small "Board updated" note. (Not when loaded with the file picker.)
23. In Implementation order, phases fold and unfold; empty phases show as one folded line;
    unscheduled phases come last, folded.
24. Cards show chips: the PR (click to open it), `bug` / `fixes …`, and "blocked by <ID>" for
    each unfinished dependency (click to jump there).
25. `SLATE.md` gains sections on the board of record and worktrees, bugs, unscheduled phases,
    item ticks, merges and unlocks.
26. **Ticks with evidence:** `check-item ID acceptance|test N --evidence "…"` (and
    `uncheck-item`) ticks a Done-when or test item on the board. `show` prints `[x]` with the
    evidence; the board shows it ticked and locked with its evidence, and you can still tick
    other items in your browser. `/slate:work` ticks items as each one is proven.
27. **Waiting for merge:** a new `merge_ready` status and board column between User testing
    and Done. `/slate:work` moves a ticket there once user tests pass and the commit (and PR,
    when there's a remote) are linked, then stops. `done` needs the linked PR to be `merged`
    (`link ID --pr-state merged`) or your OK to close without it (`--no-pr "why"`). `next`
    lists these tickets under "Waiting for merge".

**Also new in 0.2.0**

- **Live board page:** `board.py serve` serves the board with a small local API, so clicks
  become real board changes through the same checks as the commands: status moves, ticks,
  Pass/Fail and "Clear result", notes, Promote, Take/Release. `serve --ensure` starts it once
  in the background and reuses it after that (`--port`, `--strict-port`, `--host`, `--open`,
  `--status`, `--stop`, `--idle-exit`); it listens on 127.0.0.1 and needs a per-run token for
  writes. Slate's skills start it for you unless `SLATE.md` says `Board server: off`. Opened
  any other way the board is view-only, marks your clicks "local only" and can copy them as
  board.py commands. Over SSH: `ssh -L 8088:localhost:8088 you@host`.
- **Custom columns with roles:** `add-status`, `rename-status`, `edit-status` (`label=`,
  `role=`, `from=`), `reorder-statuses`, `remove-status`. Every status follows one of the eight
  built-in roles, so renamed or added columns (a "QA" column like Review) keep every rule.
  Labels show on the board and in `status`, `show`, `next`, `list`; `export --json --statuses`
  prints the setup.
- **Which moves need a note for the ticket's history** is set per state: `add-status … --note
  required|optional` (default as the state it is like) and `edit-status NAME note=…` (built-in
  states too). Defaults unchanged: Review, User testing, Waiting for merge and Done need one;
  moving back under workflow rules always does.
- **Workflow rules (optional):** `set-meta workflow=strict|free` and per-status `from=` rules
  stop forward moves that skip a step; a refusal names the next allowed step. Moving back needs
  a note. `board.py flow` shows the moves your tickets really made, so `/slate:upgrade` can
  recommend rules from evidence; `board.py workflow --markdown` writes the matching
  `## Workflow` section of `SLATE.md`.
- **No board action needs a hand edit:** `remove` / `restore` (archive in `meta.removed`, ids
  never reused, `export --json --removed`), `unlink` (a wrongly linked commit or PR),
  `usertest … reset`, `note` (a history note without a status change), bulk `edit ID1,ID2 …`,
  and `set-meta priorities:=[…]`.
- **Claims:** `set ID in_progress` records who is on the ticket (the current branch; `--as`);
  `next` and `list` skip others' tickets and show "on: <name>"; moving one needs
  `--take-over "why"` with the user's OK; `claim` / `release`; `status` lists claims; merges
  keep the later claim.
- **Write lock:** board writes take turns through `kanban/.slate-write.lock`, so parallel agents
  never lose a write; `unlock-write` removes a stale lock.
- **`doctor`:** one health report (versions, SLATE.md, Python command, merge driver,
  `.gitignore`, repo address, locks, board errors, board behind the default branch), each problem
  with a code, a kind (`setup` → `/slate:upgrade`, `tickets` → `/slate:sync`) and a fix.
  `--brief` feeds the session-start line.
- **Repair writes:** a board that already has errors accepts writes that fix some and add none
  ("repair: N errors left"), so `check`'s fix lines can be run one by one.
- **New `/slate:sync` skill** to sort boards out across branches and worktrees: differences in
  plain words, sync only with your yes, merge conflicts one at a time, repairs, claims.
- **Upgrades explain themselves:** `plugins/slate/upgrades/<version>.md` starts with "What's new"
  in plain words; `/slate:upgrade` shows it before changing anything, runs each version's steps
  in order (merge driver, `.gitignore`, board server, SLATE.md sections, BACKLOG, repo address,
  Python command, columns and workflow rules — each asked first), records a dated line in
  `SLATE.md`'s new `## Slate updates`, and runs `doctor` until healthy.
- **`/slate:init` asks more:** parallel work and the board of record, the repo address from the
  git remote, a `BACKLOG` phase, who merges PRs, the Python command, board server and port,
  columns and workflow rules (recommended from how the team works, shown as a picture first);
  it installs the merge driver, adds the `.gitignore` lines (`kanban/.slate-unlock*.json`,
  `.slate-write.lock`, `.slate-serve.json`, `.slate-serve.log`) and explains unlock once.
- **`SLATE.md`** gains `Python:`, `Board server:` and `Board port:` lines, a `## Workflow` section
  (columns, roles, rules, who merges, board of record, unlock rule) and `## Slate updates`.
- **Command reference for agents:** `plugins/slate/reference/commands.md` lists every board.py
  command with "use it when…"; every skill links it, and a test keeps docs and board.py in step.
- **Skills speak in roles** (renamed or custom columns still work), never read `tickets.json`
  directly (`show` / `export` / `list` / `status --json`), create the ticket branch before
  claiming, respect claims and path rules, and allow `python3`, `python` and `py -3`.
- **Works on Windows, macOS and Linux:** hooks run through `hooks/run.sh` (tries `python3`,
  `python`, `py -3`), UTF-8 everywhere, Windows paths in the guard, the merge driver uses the
  detected Python command, CI runs the tests on all three.
- `/slate:status` lists waiting-for-merge tickets, claims, unscheduled and archived counts, the
  workflow mode, doctor's summary and the live board link; `/slate:review` and `/slate:status`
  use `export --json` instead of reading the file.

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
