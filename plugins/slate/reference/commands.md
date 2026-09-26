# Slate board commands — reference for agents

Every command is run from the repo root as `<python> kanban/board.py <command> …`, where
`<python>` is the command in `SLATE.md` ("Python: `…`": `python3`, `python` or `py -3`),
`python3` when it says nothing. Below it is written `python3`. Skills link here instead of
repeating the list.

Rules that hold for every command:

- `kanban/tickets.json` changes **only** through these commands. Never edit it by hand, never
  write it with a script; a hook blocks that. Don't read it directly either: use `show --json`,
  `export --json`, `list --json`, `status --json` (they add labels, claims and derived state).
- Every write validates the whole board and writes atomically; if anything is wrong nothing is
  written. A refusal prints `error: <ID> <field>: …` followed by `fix: <command>` (run it, or
  adapt it) or `ask the user: …` (stop and ask, never guess the answer).
- **Speak in roles, not names.** Every status has a role (`draft backlog ready in_progress
  review user_testing merge_ready done`); a project may rename statuses or add its own
  ("qa" with the review role). Before moving tickets, run `export --json --statuses` once and use
  the status **name** whose role you mean. Show the user the **label** (column title).
- Exit codes: `0` ok, `1` refused / validation errors / problems found (`doctor`) / merge
  conflicts (`merge-driver`), `2` wrong usage.
- A warning that this is not the board of record (secondary worktree, `SLATE_BOARD_OF_RECORD`
  elsewhere, default branch has newer tickets) means **stop and ask the user** before writing
  more (see `/slate:sync`).
- Writes take turns through `kanban/.slate-write.lock` (up to ~10 s). "board is busy" → wait a
  few seconds and retry; `unlock-write` only when the error says the lock is stale.
- `<cmd> --help` is the final word on flags. A command marked **(pending)** is specified but not
  in `board.py --help` yet. A project whose board is older than the plugin may lack newer
  commands (`serve`, `flow`, `workflow`): check `--help`, use the fallback the entry gives, and
  offer `/slate:upgrade`.

## Read (never changes anything)

#### `next`
What to work on: open tickets to resume (in_progress / review / user_testing roles) first, then
"Waiting for merge" (a question for the user, not work to resume), then the lowest-rank ready
ticket. Tickets claimed by someone else are shown as "on: <name>" and never offered.
Flags: `--brief` (one line, used by the session hook), `--json`, `--against PLUGIN_ROOT`,
`--as NAME` (who you are for claims; default the git branch).
Use it when: picking or resuming work, or starting a session.

#### `list`
Next N ready tickets in build order; unscheduled phases and others' claims are skipped.
Flags: `[N]`, `--json`, `--as NAME`, filters `--phase --status --label --area` (comma lists).
Use it when: showing the user what comes after the next ticket.

#### `show`
One ticket in full, plain text: fields, `[x]` ticks with evidence, user-test results, commits,
PR, claim, history. Flags: `ID`, `--json`.
Use it when: reading a ticket before working, reviewing or answering about it.

#### `status`
Progress per phase, counts per status (with labels and the workflow mode), claims, tickets
waiting for the user and for merge, drafts, unscheduled count, archived count.
Flags: `--json`, filters `--phase --status --label --area`.
Use it when: the user asks "where are we", or for `/slate:status`.

#### `export`
Full tickets as JSON, filtered; drafts left out unless `--drafts`; `status_label` added when
labels are set. `--removed` lists archived tickets instead; `--statuses` prints the status
setup instead: `{workflow, statuses: [{name, role, label, from}]}`.
Flags: `--json`, `--drafts`, `--removed`, `--statuses`, `--phase --status --label --area`.
Use it when: you need many tickets' details at once (instead of reading tickets.json), or the
status names for each role (`--statuses`).

#### `check`
Validate the whole board; exit 1 on errors. Every error line comes with a `fix:` line.
Flags: `--json`, `--quiet-optional` (hide missing visual/technical warnings; also
`meta.check_quiet_optional`).
Use it when: before and after a batch of writes, at step 0 of a skill, and after any merge.

#### `version`
Board, schema and tickets.json versions; with `--against` compares with the plugin
(`same` / `behind` / `ahead`).
Flags: `--against PLUGIN_ROOT`, `--json`.
Use it when: step 0 of every skill.

#### `flow`
Reads every ticket's handoff history and prints the status transitions actually used, with
counts (`review → user_testing 31`, `in_progress → done 2`). Flags: `--json` (also
`suggested_from`: a rule set built from what was seen).
Use it when: recommending workflow rules from how the team really works (`/slate:upgrade`, or
`/slate:plan` when asked). Turn it into a plain recommendation; apply rules only on a yes.

#### `workflow`
`workflow --markdown` prints the `## Workflow` section for `SLATE.md` from the board: each
state (name, column title, role, allowed "from" states, whether a move into it needs a note
for the ticket's history), the workflow mode, and the project
settings board.py knows. Flags: `--markdown`.
Use it when: after `/slate:init`, `/slate:upgrade`, or any change to states, rules or phases —
regenerate SLATE.md's `## Workflow` section from it (with the user's OK), never hand-write it.
On an older board without it, write the section by hand from `export --json --statuses`.

## Board page server

#### `serve`
Serves the `kanban/` folder **plus** a small JSON API, so clicks on the board page become real
board changes through the same code paths as the CLI (checks, gates, path rules, write lock;
refusals come back with their fix text; history notes carry `via: "board page"`). Binds
127.0.0.1; a per-run token is required on writes. Writes `kanban/.slate-serve.json`
{pid, host, port, url, …} while running and logs background runs to `kanban/.slate-serve.log`.
Flags:
- `--port N` (default 8088, or `Board port:` in SLATE.md); a taken port → the next free one,
  unless `--strict-port` (then it refuses, naming the port). Every message prints the real URL.
- `--host HOST` (default `127.0.0.1`; anything else warns loudly — the page can change tickets).
- `--open` open the page in a browser.
- `--ensure` reuse a running Slate server for this board (print its URL, exit 0) or start one
  in the background; cleans up a stale runtime file. If the port answers but isn't Slate (e.g.
  `python3 -m http.server`), it says the board is view-only there and gives the live URL.
- `--status` report only (read-only). `--stop` stop the recorded server and remove its file.
  (`--ensure`, `--status` and `--stop` exclude each other.)
- `--idle-exit HOURS` (default 8; 0 = never) stop by itself after that long without a request.
Use it when: step 0 of `plan`, `work`, `status`, `sync` —
`python3 kanban/board.py serve --ensure --port <Board port>` unless SLATE.md says
`Board server: off`; show the link once. Over SSH the user forwards the port:
`ssh -L <port>:localhost:<port> <host>`. Plain `python3 -m http.server` / opening the file gives
a **view-only** board (clicks stay in that browser; "Copy as board.py commands" turns them into
commands).

## Plan tickets

#### `new`
Create one ticket from flags (or a draft with `--draft`).
Flags: `--title --summary --phase` (required), `--story --description --visual --technical
--plan-doc --priority --estimate --after ID`, repeatable `--acceptance TEXT --test TEXT
--user-test-json JSON`, repeatable or comma lists `--areas --depends --labels`; bugs:
`--bug --fixes ID,… [--reopen]`; `--dry-run`.
Use it when: one quick ticket, or a bug found while working another ticket (`--bug --fixes`).
`--reopen` only after the user agreed to reopen a done / merge_ready ticket. No draft-role status
on the board → `--draft` refuses with an `add-status` fix.

#### `add`
Add many tickets (and phases) from a batch file with short keys instead of ids.
Flags: `--file BATCH`, `--after ID`, `--as-draft`, `--dry-run` (writes `kanban/preview.json`).
Use it when: saving the cards from `/slate:plan`; always `--dry-run` first so the user sees
the preview.

#### `batch-check`
Validate a batch file on its own. Flags: `--file BATCH`, `--as-draft`, `--json`.
Use it when: before `add --dry-run`, to fix the batch without touching the board.

#### `discard-preview`
Remove `kanban/preview.json`. Use it when: the user rejects a preview.

#### `edit`
Change ticket fields: `key=value`, `key+=text` (append a paragraph to description, technical,
story, summary, visual), `key:=JSON` (lists, objects, booleans). `ID1,ID2` edits several at
once, all or nothing.
Flags: `ID[,ID…]`, assignments, `--file PATCH.json`, `--rerank` (move after its latest
dependency). Can't change id, rank, status, handoff, checks, commits, pr or claims.
Use it when: correcting or extending a ticket, moving tickets to another phase
(`edit ACME-004,ACME-005 phase=P3`), changing priority or `depends_on` (add `--rerank` if the
rank error says so).

#### `rerank`
Move a ticket in the build order; renumbers only what must move, keeps ranks after deps.
Flags: `ID`, `--after OTHER` or `--first`.
Use it when: the user wants a different order.

#### `promote`
Turn a draft into a backlog ticket; full checks run and list what is still missing.
Flags: `ID`, `--handoff NOTE`. Use it when: a draft is finished (`/slate:plan <ID>`).

#### `remove` / `restore`
`remove` archives tickets into `meta.removed` (not deleted; ids are never reused); `restore`
brings one back. Refuses while other tickets depend on it unless `--detach` (drops it from their
`depends_on`); a done ticket needs `--force-done "why"`.
Flags: `remove ID[,ID…] --reason "…" [--detach] [--force-done REASON]`, `restore ID`.
Use it when: the user wants a ticket gone (duplicate, dropped idea). **Ask first**, naming the
tickets; list archived ones with `export --json --removed`.

#### `note`
Add a history note without changing the status. Flags: `ID[,ID…] "text"`.
Use it when: recording "waiting on …", a decision, or a hand-off while the status stays.

## Work tickets

#### `set`

> Agents: always pass `--handoff "…"` on every status move you make, even when the target state's note is optional (project rule in SLATE.md).

Change status. A note for the ticket's history (`--handoff`, the handoff note) is required when
the target state asks for one — by default the review, user_testing, merge_ready and done states;
any state can be changed with `edit-status NAME note=required|optional` — and for any backward
move while path rules exist. `ID1,ID2` changes several, all or nothing.
Flags: `ID[,ID…] STATUS`, `--handoff NOTE`, `--ignore-deps REASON` (in_progress / review /
user_testing roles only, the user's reason), `--no-code REASON` or `--no-pr REASON` (only after
the user agreed), `--as NAME` (who claims it; default the git branch), `--take-over REASON`
(move a ticket someone else claimed — only with the user's OK).
Use it when: moving a ticket through the build loop.
- in_progress **claims** the ticket for the current branch (create the ticket branch first);
  review / user_testing / merge_ready keep the claim; every other status clears it.
- merge_ready needs passed required user tests, a linked commit and (with a remote) a linked
  PR; done needs the linked PR `merged`.
- **Path rules** (`meta.status_from`, `workflow=strict`): a forward move that isn't allowed is
  refused as `can't move A → B` with the allowed previous statuses and a `fix:` for the next
  allowed step. Follow that step; change the rule only if the user says so.

#### `claim` / `release`
Mark a ticket as yours / remove the claim, without changing status.
Flags: `ID`, `--as NAME`, `--take-over REASON`.
Use it when: you work on a ticket without moving it (e.g. review help), or you stop working on
one you claimed. Never take over someone else's claim without the user's OK.

#### `usertest`
Record a user test result; a fail moves a user_testing ticket back to in_progress with the
note; `reset` clears a wrongly recorded result (noted in the history).
Flags: `ID INDEX pass|fail|reset`, `--note NOTE`.
Use it when: the user answers a "try it yourself" (or says a recorded answer was wrong).

#### `check-item` / `uncheck-item`
Tick (or untick) one "Done when" / "Automated tests" item, with evidence.
Flags: `ID acceptance|test INDEX` (0 is the first), `--evidence TEXT` (check-item only).
Use it when: an item is proven (test passes, behaviour seen), not all at the end.

#### `link`
Record commits (sha, subject, branch, date from git) and the PR on a ticket; idempotent.
`ID1,ID2` for one PR covering several tickets.
Flags: `ID[,ID…]`, repeatable `--commit SHA_OR_REF`, `--message`, `--pr URL`,
`--pr-state draft|open|merged|closed`, `--pr-title`.
Use it when: right after each code commit (`--commit HEAD`), after opening the PR, and when the
user says the PR is merged (`--pr-state merged`).

#### `unlink`
Remove a wrongly linked commit or PR (noted in the history).
Flags: `ID[,ID…]`, repeatable `--commit SHA_OR_PREFIX`, `--pr`, `--reason TEXT`.
Use it when: you linked the wrong commit (e.g. the bookkeeping commit) or the wrong PR.

## Phases

#### `add-phase`
Append a phase. Flags: `--id ID --name --goal --demo`, `--unscheduled` (someday phase, skipped
by `next` / `list`). Use it when: a plan needs a new phase, or a `BACKLOG` for someday ideas.

#### `edit-phase`
Change a phase: `name=`, `goal=`, `demo=`, `unscheduled:=true|false`. Flags: `ID`, assignments.

#### `rename-phase`
Change a phase id; every ticket in it moves along, atomically. Flags: `OLD NEW`.

#### `remove-phase`
Remove a phase; refuses while tickets use it unless `--move-to OTHER`. Flags: `ID`,
`--move-to OTHER`. Use it when: the user wants to drop or merge phases.

#### `reorder-phases`
Set the phase display order; list every phase exactly once. Flags: `ID ID …`.

## States (columns) and workflow rules

Every status has a role; board.py's rules follow the role, not the name. A done-role status and
a backlog- or ready-role status must always remain. Ask the user before adding, renaming or
removing a state, and regenerate SLATE.md's `## Workflow` afterwards (`workflow --markdown`).

#### `add-status`
Add a column that follows a role's rules. Flags: `NAME`, `--after STATUS` or `--first`,
`--like ROLE_OR_STATUS` (required), `--label TEXT` (column title), `--note required|optional`
(must a move into it carry a note for the ticket's history? default: inherited from the `--like`
state or role).
Use it when: "add a QA column" → `add-status qa --after review --like review --label "QA"
--note required`. Ask the user whether a note is required for the new state.

#### `rename-status`
Rename a status; its tickets move with it (history keeps the old name). Flags: `OLD NEW`.

#### `edit-status`
Change a status: `label="…"` (column title), `role=…`, `from=a,b` (the path rule: which
statuses may come right before it; `from=` clears it), `note=required|optional` (whether a move
into it needs a note for the ticket's history; built-in states too — defaults: required for
review, user_testing, merge_ready, done; optional otherwise). Flags: `NAME`, assignments.
Use it when: "call In progress 'Doing'" → `edit-status in_progress label="Doing"`; "QA only
after review" → `edit-status qa from=review`; "no note needed for Review" →
`edit-status review note=optional`.

#### `reorder-statuses`
Set the column order; list every status once. Flags: `STATUS STATUS …`.

#### `remove-status`
Remove a status; refuses while tickets are in it unless `--move-to OTHER`. Flags: `NAME`,
`--move-to OTHER`.

#### `set-meta` (workflow and priorities)
`set-meta workflow=strict` writes the usual path (backlog/ready → in progress → review → user
testing → waiting for merge → done, skipping statuses the board lacks); `workflow=free` removes
every rule. `set-meta priorities:='["P0","P1","P2"]'` sets the priority list (refused while a
ticket uses a dropped one). See also "Setup and health".

## Branches, worktrees and merges

#### `diff`
Compare this board with another: a git ref (`main`, `origin/main`), a tickets.json path, or a
folder holding `kanban/tickets.json`. Per ticket: added, removed, changed fields; ignores
rank-only changes and handoff dates.
Flags: `OTHER`, `--json`, `--include-rank`.
Use it when: a board-of-record warning appears, before `sync`, or the user asks how two boards
differ. Explain the result in plain words; changes nothing.

#### `sync`
Bring another board's differences into this one: new tickets and phases added, record lists
(handoff, commits, user_checks, item_checks) unioned, status takes the further-along one, other
changed fields take theirs (or ours). Claims come along with the tickets.
Flags: `--from OTHER`, `--dry-run`, `--only ID,…`, `--prefer ours|theirs`.
Use it when: the user agreed to bring changes across after `diff`. Always `--dry-run` first and
show the plan; run for real only on a yes.

#### `merge-driver`
Git's three-way merge driver for tickets.json (`%O %A %B`): merges ticket by ticket and field by
field (later claim wins), writes the result to OURS, reports real conflicts on stderr (kept as
ours), exit 1 when there are conflicts. Flags: `BASE OURS THEIRS`.
Use it when: never by hand; git runs it. Its conflict list is what `/slate:sync` walks through.

#### `install-merge-driver`
Add `kanban/tickets.json merge=slate` to `.gitattributes` and set `merge.slate.driver` /
`merge.slate.name` in this clone's git config (with the detected Python command). Safe to
re-run. Flags: `--python CMD` (how git should start Python).
Use it when: `/slate:init`, `/slate:upgrade`, or `doctor` says `merge-driver-missing` (each
clone needs it once).

#### `copy-to` / `export-file`
Write a validated copy of this board to PATH (a file, or `PATH/kanban/tickets.json` for a
folder). Refuses when the target has changes this board lacks, unless `--force`.
Flags: `PATH`, `--force`.
Use it when: the user confirmed this board should replace the one in another worktree or
checkout. `--force` only after the user saw what would be lost (`diff PATH`).

## Locks and unlock

#### `unlock-write`
Remove a stale write lock (`kanban/.slate-write.lock` older than 60 s, or its process gone);
refuses on a live lock.
Use it when: a write refused with "board is busy" **and** says the lock is stale, or `doctor`
reports `write-lock-stale`. A live lock means another command is writing: wait and retry.

#### `unlock`
The supervised escape hatch for ONE direct edit of tickets.json that no command covers.
Flags: `--reason "…"` (required), `--minutes N` (default 5, max 30).
- Run it exactly as `python3 kanban/board.py unlock --reason "…" --minutes 5` (no `cd … &&`, no
  pipes). Run by an agent it only writes a **request**; Claude Code then shows its own permission
  card, and the Yes activates it. The card appears in **Manual, Accept edits and Auto** permission
  modes. **Plan** mode refuses ("leave plan mode first"); **Bypass permissions**, **Don't-ask** and
  `-p` refuse ("nobody to approve"): then the user runs
  `python3 kanban/board.py unlock --reason "…"` in their own terminal (or tmux pane / second SSH
  session) and types the 4-letter code it shows.
- One unlock = one edit, expiring after `--minutes` if unused. Everything is logged in
  `meta.unlock_log`. Copilot CLI support: planned.
Use it when: last resort only — after explaining to the user why no command (`edit`, `sync`,
`unlink`, repair fixes from `check`) can do it. If the user declines, stop.

#### `lock`
Remove any active unlock and pending request; logged. Use it when: an unlock is no longer
needed, or the user asks to cancel one.

## Setup and health

#### `init`
Create tickets.json for a project; refuses if one exists.
Flags: `--project --prefix` (required), `--areas a,b,c`, `--repo-url URL`.
Use it when: `/slate:init` only.

#### `set-meta`
Change allowed meta keys: `project`, `repo_url`, `areas`, `user_test_areas`,
`check_quiet_optional`, `priorities`, `workflow` (`strict|free`). Flags: `key=value …`,
`key:=JSON` for lists and booleans.
Use it when: init / upgrade questions (e.g. `repo_url` from `git remote get-url origin`), or the
user changes priorities or the workflow.

#### `doctor`
One health report for the project's Slate setup and board, each problem with a `code`, a `kind`
and `fix:` lines. Exit 0 healthy, 1 problems.
Flags: `--json`, `--brief` (one line), `--against PLUGIN_ROOT` (also compare with the plugin:
versions, SLATE.md sections).
- kind **`tickets`** (→ `/slate:sync`): `board-behind` (default branch has tickets or notes this
  board lacks; fixes `diff <ref>`, `sync --from <ref> --dry-run`), `board-errors`,
  `board-unreadable`.
- kind **`setup`** (→ `/slate:upgrade`, or run the fix): `schema-outdated`,
  `board-files-outdated`, `plugin-outdated` (update the plugin instead), `plugin-unreadable`,
  `python-cmd-missing`, `slate-md-missing`, `slate-md-sections`, `slate-md-workflow-stale`, `team-settings-missing` (plus the note `team-settings-ignored`, not counted as a problem)
  (SLATE.md's `## Workflow` doesn't match the board; regenerate with
  `workflow --markdown`, with the user's OK), `merge-driver-missing`, `gitignore-missing`,
  `repo-url-missing`, `write-lock-stale` (fix: `unlock-write`), `unlock-active` (fix: `lock`).
Use it when: after an upgrade (run until healthy), when something feels off, in `/slate:status`
(`--brief`), and at the start of `/slate:sync`.

#### `migrate`
Apply additive schema migrations in order (1 → 2 adds `merge_ready` before `done`), then check.
Use it when: `doctor` or `version` says the schema is behind; `upgrade` runs it for you.

#### `upgrade`
Copy new `board.py`, `index.html`, `README.md` from the plugin, then migrate.
Flags: `--from ASSETS_DIR` (`<plugin root>/assets/board`).
Use it when: `/slate:upgrade` only, after the user said yes.
