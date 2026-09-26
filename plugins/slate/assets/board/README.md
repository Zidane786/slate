# Slate board

The project's kanban and build-order board. One file, no build step, no dependencies:
`index.html` is plain HTML, CSS and JavaScript and reads `tickets.json` from the same folder.
It was put here by `/slate:init` and is kept current by `/slate:upgrade`. Don't edit
`index.html`, `board.py` or this README by hand: `/slate:upgrade` replaces them.

## Open it

```bash
python3 kanban/board.py serve --ensure        # from the repo root; prints the URL
```

Then open the URL it prints (http://localhost:8088 unless that port was taken). Slate's
commands run this for you unless `SLATE.md` says `Board server: off`; `--ensure` reuses a
server that is already running for this board, so there is never a second one.

**Live mode** (served by `board.py serve`). The header says "Live: changes save to the board".
Every click is a real board change made through the same code as the commands, with the same
checks: dragging a card or picking a status (`set`; a note is asked for when the move needs
one), ticking a Done-when or test item (`check-item` / `uncheck-item`), Pass / Fail on a user
test (`usertest`) and "Clear result" (`usertest … reset`), "Add note" in the drawer (`note`),
"Promote" on a draft (`promote`), "Take" / "Release" (`claim` / `release`; asks your name once and
remembers it in this browser). Moves that aren't allowed right now are greyed out; a refused
move shows the reason and the fix. History entries record `via: "board page"`. Editing ticket
text, creating or removing tickets, phases and states stay with the commands (or Claude).

**View-only mode** (any other static server, such as `cd kanban && python3 -m http.server
8088`, or `index.html` opened from disk with the file picker). The header says "View only:
changes stay in this browser". Ticks, Pass/Fail and status drags are kept in your browser only,
marked "local only" with a count in the header, and **Copy as board.py commands** turns them
into `check-item` / `usertest` / `set` commands to run. Local marks clear once the file holds
them.

`serve` flags: `--port N` (default 8088, or `Board port:` in `SLATE.md`; a taken port moves to
the next free one unless `--strict-port`), `--host` (default 127.0.0.1; anything else warns,
because the page can change tickets), `--open` (open a browser), `--ensure`, `--status`,
`--stop`, `--idle-exit HOURS` (default 8). While running it writes `kanban/.slate-serve.json`
(and logs background runs to `kanban/.slate-serve.log`); keep both out of git. Writes need a
random per-run token that only the served page has, so other pages can't change your board.

**Over SSH / in tmux.** The server runs where the repo is. From your own machine forward the
port — `ssh -L 8088:localhost:8088 you@host` — and open http://localhost:8088 there.

Opened straight from disk (`file://`), the browser blocks loading `./tickets.json`: the page
shows a file picker; choose `tickets.json` (and `preview.json` to see a preview).

The footer shows the board's Slate version (`Slate v0.2.0`) and the version recorded in
`tickets.json`. The page also has `<meta name="slate-version">` for scripts.

**Live refresh.** When the page is served (not opened with the file picker), it re-reads
`tickets.json` and `preview.json` every few seconds while the tab is visible (less often when
nothing changes). When either
changed, the board redraws in place: your view, filters, search, scroll position and open
ticket drawer stay as they were, and a small "Board updated" note shows for a moment. A
half-written file is skipped until the next round. Files loaded with the file picker can't be
re-read, so they don't refresh; reload and pick them again.

## Views

**Board.** One column per status, in the order of `meta.statuses`. A status that a ticket
uses but `meta.statuses` leaves out still gets a column, so nothing disappears. Each card
shows the id, rank, priority, title, the summary in one line, phase, areas, estimate, the
number of dependencies, and one state tag. Below the areas, small chips show:

- **PR #42 · open**: the linked pull request and its state. Click it to open the PR.
- **bug** and **fixes ACME-004**: a bug ticket and the ticket it fixes (click to jump there).
- **blocked by ACME-011**: each dependency that isn't Done yet (up to three, then "+N more").
  Click one to open it.

| Tag | Meaning |
|---|---|
| `ready` | Status is Backlog or Ready, everything it needs is Done, and its phase is scheduled. |
| `blocked` | Something it needs isn't Done yet (red left edge). |
| `needs you` | It's in **User testing**: try it yourself and tell Claude how it went. |
| `waiting for merge` | Built, reviewed and tested; its PR is waiting to be merged. |
| `unscheduled` | It sits in an unscheduled (someday) phase; nobody picks it until it's moved. |
| `not ready` | It's a **Draft**: saved, but not finished, so no one works on it yet. |
| `preview` | Not saved at all; see "Preview" below (dashed border). |

Drag a card to another column, or use the status dropdown in the ticket drawer, to change its
status (saved to the board in live mode, kept in your browser in view-only mode). Column titles
are the status labels (`meta.status_labels`); a card someone is working on shows an "on:
<name>" chip. Sort by rank (default), priority or id. The header shows
totals, plus pills for "waiting for you to test", "waiting for merge" and "unscheduled" when
there are any. Click a pill to show only those tickets.

**Implementation order.** Tickets grouped by phase, in the order of the `phases` list, with
each phase's goal, demo and a done/total bar, in rank order. Each row has the summary,
dependency chips, a state tag, PR and bug chips, and a status dropdown. Blocked tickets and
drafts are dimmed. Click a phase header to fold or unfold it.

- A phase with no tickets yet shows as a single folded line ("no tickets yet").
- **Unscheduled phases** (`"unscheduled": true`, e.g. a `BACKLOG` of someday ideas) come
  last, folded, with an `unscheduled` tag. Unfold one to see its tickets.
- While a filter or search is active, phases with nothing matching are left out.

### Draft, User testing and Waiting for merge columns

- **Draft** holds tickets that are written down but not finished. `board.py next` and
  `list` never pick them. A draft needs only a title, a summary and a phase. Its drawer
  lists what is still missing. `board.py promote ID` moves it to Backlog once it's complete.
- **User testing** holds tickets that change something you can see or click. They wait
  here until you've tried them. Each one has **Try it yourself** steps in its drawer.
- **Waiting for merge** (status `merge_ready`) holds tickets that are built, reviewed, tested
  and have their commit and PR linked. The card shows the PR; the drawer opens with a note
  and the PR link. A ticket moves on to **Done** only once you tell Claude the PR is merged.

## The ticket drawer

Click a card or row. Prev / Next (or the ← → keys) walk the tickets in rank order. The
drawer reads top to bottom:

1. **Summary**: what you get, in one or two sentences.
2. **Story**: a short example of someone using it.
3. **Picture**: a diagram or screen sketch. Wide pictures scroll sideways instead of
   wrapping, so the drawing stays intact.
4. **Done when**: the checks that say it's finished (tick boxes). Items ticked on the board
   (`board.py check-item`) show ticked and locked, with a green "Checked <date>: <evidence>"
   line under them. Items of a Done ticket all show ticked. Other items you can still tick
   in your browser.
5. **Try it yourself**: the steps you follow by hand: before you start, numbered steps,
   what you should see, and whether the test is required. **Pass / Fail** buttons record
   your answer *in this browser only*. A result Claude has saved (from `board.py usertest`)
   shows as a "Recorded: passed/failed" badge with its date and note.
6. **Automated tests**: what the tests check, as "When …, then …" (tick boxes, same rules
   as Done when).
7. **Details**: the full description.
8. **Technical notes**: for developers, closed until you open it.
9. **Needs / Unlocks**: which tickets must be done first, and which ones wait for this
   one. Click a chip to jump to it.
10. **Plan doc**: the `docs/plans/…` file the ticket came from.
11. **Code changes**: the pull request (a link with its state: draft, open, merged or
    closed) and the commits that built the ticket, each with its short sha, subject and
    date. When `meta.repo_url` is set, each sha links to the commit on GitHub
    (`<repo_url>/commit/<sha>`) or GitLab (`<repo_url>/-/commit/<sha>`, used when the host
    name contains "gitlab"). A ticket closed with `--no-code` or `--no-pr` shows the reason
    ("Closed without code: …").
12. **History**: the handoff notes, oldest first.

Older tickets that have no summary or story (for example ones brought over from an earlier
board) still show. Their details come first, then Done when, tests, needs/unlocks, code
changes and history.

Descriptions and notes support a small set of markdown: headings (`#` to `###`),
paragraphs, bullet and numbered lists, **bold**, *italic*, `inline code`, links, fenced
code blocks, tables (`| a | b |` with a `|---|---|` row) and `>` blockquotes.

## Preview

When Claude plans new tickets it runs `board.py add --dry-run`, which writes
`kanban/preview.json`:

```json
{ "preview": true, "phases": [ … new phases … ], "tickets": [ … new tickets with ids and ranks … ] }
```

The board shows those tickets in their columns and rank positions, with a dashed border
and a `preview` tag. A banner at the top reads "Preview: N tickets not yet saved". Preview
tickets are for looking at only. You can't change their status or tick them, Export leaves
them out, and they're not counted in the header totals or local changes. They become real
tickets only when Claude runs `board.py add` (which deletes `preview.json`).
`board.py discard-preview` throws them away.

## Search, filters, keyboard

- Search matches id, title, summary, story, description and labels, as you type.
- Filters: phase, area, priority and status (multi-select), "Ready to start only" (Backlog
  or Ready with everything it needs Done) and "Hide done". They apply to both views.
- `/` focuses search. `Esc` closes the drawer. `←` / `→` go to the previous or next ticket
  while the drawer is open.
- The Theme button cycles auto, light and dark. Auto follows your system setting.

## What the page stores in your browser

In view-only mode the page never changes `tickets.json`: status changes, ticks and Pass/Fail
clicks go to an **overlay** in `localStorage`. (In live mode they go to the board instead; the
page remembers only your theme and the name you use for Take.) A tick saved in the file (`item_checks`) always wins over
the overlay, and isn't counted as a local change. The key includes the project's prefix, so two boards
on the same address don't mix:

| Key | Holds |
|---|---|
| `slate.<prefix>.overlay.v1` (e.g. `slate.ACME.overlay.v1`; `slate.board.overlay.v1` when `meta.prefix` is missing) | per-ticket local changes |
| `slate.theme` | `auto`, `light` or `dark` |

```json
{
  "ACME-004": {
    "status": "review",
    "checks": { "acceptance:0": true, "test:1": true, "usertest:0": "pass" }
  }
}
```

A status that matches the file is dropped, so "n local changes" counts only real
differences. The overlay belongs to one browser and isn't shared with anyone.

**Export tickets.json** downloads the original file with your overlay *statuses* applied,
in the same layout. Ticks and Pass/Fail clicks are not written. `user_checks` in the file
is the only record of user tests, and only `board.py usertest` writes it. Preview tickets
are never exported. **Reset local changes** clears the overlay after asking.

## Change tickets only through `board.py`

`tickets.json` is changed only by `kanban/board.py`. It checks the whole board before every
write and writes atomically. Claude's plugin blocks direct edits to the file. If you swap
in an exported file, the next `board.py` command checks it; while it has errors, a write is
accepted only when it **repairs** the board: it adds no new error and leaves fewer errors than
before (board.py then prints `repair: N errors left`). So the `fix:` lines `check` prints can be
run one by one on a broken board; any other write is refused until it's valid.

Several `board.py` commands at once (parallel agents, two terminals) are safe: every command
that changes the board holds `kanban/.slate-write.lock` while it reads, changes and writes, and
the others wait up to 10 s for their turn. A lock left behind by a crashed command is removed
with `unlock-write` (only when it is older than 60 s or its process is gone).

| Command | What it does |
|---|---|
| `python3 kanban/board.py next [--brief] [--json] [--as NAME]` | What to work on: open tickets first (In progress, Review, User testing), then "Waiting for merge" (a question for you, not work to resume), else the lowest-rank ready one. Tickets claimed by someone else are listed as "being worked on elsewhere" and never offered |
| `list [N] [filters] [--as NAME]` | Next N ready tickets (unscheduled phases and tickets claimed by someone else are skipped) |
| `show ID [--json]` | A ticket in drawer order, with `[x]` ticks and their evidence, history and user test results |
| `status [filters] [--json]` | Progress per phase, count per status, tickets waiting for you, waiting for merge, drafts, unscheduled ones last |
| `export --json [filters] [--drafts] [--removed] [--statuses]` | Full tickets as JSON (drafts left out unless `--drafts`; `status_label` added when labels are set). `--removed`: archived tickets. `--statuses`: the status setup (roles, labels, path rules, workflow). Use this instead of reading `tickets.json` |
| `check [--quiet-optional] [--json]` | Check the whole board. Prints errors, then warnings. `--quiet-optional` (or `meta.check_quiet_optional: true`) hides warnings about optional fields and prints how many it hid |
| `version [--against PLUGIN_ROOT]` | Board, schema and file versions, and whether the plugin is newer |
| `new --title … --summary … --phase … [--draft] …` | Add one ticket (`--draft` for an unfinished one). `--acceptance`, `--test`, `--user-test-json`, `--labels`, `--areas`, `--depends` can be repeated; the last three also take comma lists |
| `new --bug --fixes ID[,ID] [--reopen] …` | Add a bug ticket for problems found in other tickets (see "Bugs") |
| `add --file BATCH [--dry-run] [--as-draft] [--after ID]` | Add many tickets from a batch file. `--dry-run` writes `preview.json` |
| `batch-check --file BATCH` | Check a batch file before adding it |
| `discard-preview` | Delete `preview.json` |
| `set ID[,ID…] STATUS [--handoff "…"] [--ignore-deps "why"] [--no-code "why" \| --no-pr "why"] [--as NAME] [--take-over "why"]` | Change status. A note is required for review, user_testing, merge_ready and done. merge_ready and done need code linked (see below). Claims: see "Who is on what". Several ids: all or nothing |
| `edit ID[,ID…] key=value … [--file PATCH.json] [--rerank]` | Change fields (not id, rank, status, handoff, user_checks, item_checks, unlocks, commits, pr, done_without or claimed_by). `key+="text"` appends to `description`, `technical`, `story`, `summary` or `visual`. `--rerank` moves the ticket after its latest dependency when needed |
| `rerank ID --after OTHER` / `--first` | Move a ticket in the build order |
| `promote ID` | Move a draft to Backlog after full checks |
| `add-phase --id P3 --name … --goal … --demo … [--unscheduled]` | Add a phase (at the end). Ids: a letter, then letters, digits, `-` or `_` (e.g. `P3`, `BACKLOG`) |
| `edit-phase ID [name=…] [goal=…] [demo=…] [unscheduled:=true\|false]` | Change a phase |
| `rename-phase OLD NEW` | Change a phase id; every ticket in it moves along |
| `remove-phase ID [--move-to OTHER]` | Remove a phase; refuses while tickets use it unless `--move-to` |
| `reorder-phases ID ID …` | Set the display order; list every phase exactly once |
| `check-item ID acceptance\|test INDEX [--evidence "…"]` | Tick one Done-when or automated-test item on the board (index from 0) |
| `uncheck-item ID acceptance\|test INDEX` | Untick it |
| `usertest ID INDEX pass\|fail\|reset [--note "…"]` | Save a user test result (`reset` clears one, noted in the history). A fail sends a User testing ticket back to In progress |
| `link ID[,ID…] [--commit SHA_OR_REF …] [--message "…"] [--pr URL] [--pr-state S] [--pr-title "…"]` | Record the commits and pull request that built a ticket (any status, done included). Several ids share one PR; all or nothing |
| `set-meta key=value … / key:=JSON` | Change `project`, `repo_url`, `areas`, `user_test_areas`, `check_quiet_optional`, `priorities` (refused while a ticket uses a dropped one) or `workflow` |
| `diff OTHER [--json] [--include-rank]` | What differs from another board: a tickets.json path, a folder, or a git ref (see "Branches and worktrees") |
| `sync --from OTHER [--dry-run] [--only ID,…] [--prefer ours\|theirs]` | Bring another board's changes into this one |
| `copy-to PATH [--force]` (alias `export-file`) | Write a checked copy of this board to PATH |
| `install-merge-driver [--python CMD]` | Set up git to merge `tickets.json` ticket by ticket |
| `merge-driver BASE OURS THEIRS` | Used by git during merges; you don't run it yourself |
| `claim ID [--as NAME] [--take-over "why"]` / `release ID [--as NAME] [--take-over "why"]` | Mark a ticket as yours / remove the claim (see "Who is on what") |
| `unlock --reason "…" [--minutes 5]` / `lock` | Ask for one hand edit of `tickets.json` (see "Unlock") / cancel an active unlock or a pending request |
| `unlock-write` | Remove a stale write lock (older than 60 s, or its process is gone) |
| `add-status NAME --after STATUS\|--first --like ROLE_OR_STATUS [--label "…"] [--note required\|optional]` | Add a status (column) that follows a role's rules (see "Statuses"); `--note` defaults to the `--like` state's setting |
| `rename-status OLD NEW` / `edit-status NAME [label=…] [role=…] [from=a,b] [note=required\|optional]` | Rename a status (its tickets move with it) / change its label, role, path rule, or whether moving into it needs a note for the ticket's history |
| `reorder-statuses S S …` / `remove-status NAME [--move-to OTHER]` | Column order (every status once) / remove a status |
| `set-meta workflow=strict\|free` | Path rules preset: forward moves follow backlog → in progress → review → user testing → waiting for merge → done / no rules |
| `remove ID[,ID…] --reason "…" [--detach] [--force-done "why"]` / `restore ID` | Archive tickets in `meta.removed` (not deleted; ids are never reused) / bring one back |
| `unlink ID[,ID…] --commit SHA_OR_PREFIX … \| --pr [--reason "…"]` | Remove a wrongly linked commit or PR (noted in the history) |
| `note ID[,ID…] "text"` | Add a history note without changing the status |
| `doctor [--json] [--brief] [--against PLUGIN_ROOT]` | Project health, each problem with a code, a kind and a `fix:` line (see "Doctor"). Exit 1 when there are problems |
| `upgrade --from ASSETS_DIR` / `migrate` | Used by `/slate:upgrade`. `migrate` takes a schema 1 board to schema 2 |
| `serve [--ensure] [--port N] [--strict-port] [--host H] [--open] [--status] [--stop] [--idle-exit HOURS]` | Run the live board page (see "Open it"). |
| `flow [--json]` | The status moves tickets really made, with counts, from their history; used to recommend workflow rules. |
| `workflow --markdown` | Print the `## Workflow` section for `SLATE.md` from the board (states, labels, roles, rules). |

Filters for `list`, `status` and `export`: `--phase P[,P]`, `--status S[,S]`, `--label L[,L]`,
`--area A[,A]`.

### Linking code: `link`

```bash
python3 kanban/board.py link ACME-014 --commit HEAD                 # the commit you just made
python3 kanban/board.py link ACME-014 --commit 3f9c2a7 --commit a41e07d
python3 kanban/board.py link ACME-014 --pr https://github.com/acme/app/pull/42
python3 kanban/board.py link ACME-014 --pr-state merged             # update the PR you linked
```

- `--commit` takes a sha or any git ref (`HEAD`, a branch, a tag) and can be repeated.
  board.py asks git (run from the repository that holds `kanban/`, or the current folder)
  for the full sha, the commit's subject line and date, and the current branch. If git
  isn't there or can't find the ref, a plain 7 to 40 character hex sha is still accepted:
  its message comes from `--message` (or stays empty) and its date is today. Anything else
  is refused. Linking a sha that is already there does nothing.
- `--pr URL` sets the pull request. The number is read from GitHub `/pull/N` and GitLab
  `/-/merge_requests/N` links. The state starts as `draft` unless you pass `--pr-state`.
  Linking the same URL again keeps its state and title; a different URL replaces it.
- `--pr-state draft|open|merged|closed` or `--pr-title "…"` on their own update the PR that
  is already linked.

### Waiting for merge, then done

`set ID merge_ready` (shown as **Waiting for merge**) checks, in a git repository:

1. Every required user test has a `pass`.
2. The ticket has at least one commit linked, and every linked sha is a commit in this
   repository (`git cat-file -e`).
3. If the repository has a remote (`git remote`), a pull request is linked too.

`set ID done` checks the same things, and also: when a PR is linked, its state must be
`merged`. If it isn't, board.py refuses and prints both ways out:
`link ID --pr-state merged` (once the PR really is merged) or `--no-pr "why"` (ask the user).

Ways out, for when that is really so: `--no-code "why"` (nothing was coded; skips the commit
and PR checks) and `--no-pr "why"` (skips only the PR checks). The reason goes on the end of the
handoff note (`(no code: …)` / `(no PR: …)`) and into `done_without` on the ticket.
Without git (no `git` command, or `kanban/` isn't inside a repository) the checks are
skipped with a warning. These rules apply only when a ticket moves to done: tickets that
were done before are still valid, and `check` never asks for commits.

### Project settings: `set-meta`

```bash
python3 kanban/board.py set-meta repo_url=https://github.com/acme/app project="Acme app"
python3 kanban/board.py set-meta 'areas:=["backend", "frontend", "infra", "ui"]'
python3 kanban/board.py set-meta repo_url:=null       # remove it
```

Keys: `project`, `repo_url`, `areas`, `user_test_areas`, `check_quiet_optional`, `priorities`
(refused while a ticket uses a priority you drop) and `workflow` (`strict` or `free`); lists as
`key:=JSON`. The prefix can't change; statuses change with the status commands (see
"Statuses"). `init --repo-url URL` sets `repo_url`
at the start. A trailing `/` or `.git` is dropped.

### Starting before dependencies are done

`set ID in_progress|review|user_testing --ignore-deps "reason"` lets a ticket move on while
something it needs is still open (for example stacked PRs). The note gets
`(deps open: <IDs> — <reason>)` added. merge_ready and done always need every dependency done.

### Several tickets at once

`set ACME-004,ACME-005 review --handoff "…"` and `link ACME-004,ACME-005 --pr URL` check every
ticket first; if any one is refused, nothing is written.

## Bugs

```bash
python3 kanban/board.py new --bug --fixes ACME-004 --title "Opening a reset link twice shows an error page" \
  --summary "…" --phase P2 --story "…" --description "…" --acceptance "…" \
  --test "When a used link is opened again, then …" --priority P1 --areas backend --estimate 0.5d
```

The new ticket gets the labels `bug` and `fixes-ACME-004`, ACME-004 gets it in `depends_on`
(so it waits for the fix), and it is ranked just before ACME-004. `--fixes` takes several
ids. If a fixed ticket is already `done` or `merge_ready`, board.py refuses with
`ask the user:`; with their OK, `--reopen` moves those tickets back to `in_progress` with a
handoff note.

## Unscheduled phases

A phase with `"unscheduled": true` holds someday ideas (`add-phase --id BACKLOG … --unscheduled`,
or `edit-phase BACKLOG unscheduled:=true`). `next` and `list` never offer its tickets, `status`
and `show` list them last, and moving one of its tickets to in_progress, review,
user_testing, merge_ready or done is refused with `fix: … edit ID phase=<scheduled phase>`.
`promote` still works there and reminds you to move the ticket.

## Ticking items: `check-item`

```bash
python3 kanban/board.py check-item ACME-004 test 0 --evidence "tests/test_reset.py::test_fresh_link_shows_email"
python3 kanban/board.py check-item ACME-004 acceptance 2 --evidence "tried it: mismatched passwords show a message"
python3 kanban/board.py uncheck-item ACME-004 test 0
```

`acceptance` is the Done-when list, `test` the automated tests; the index starts at 0. The tick
is stored in `item_checks` with the date and evidence. `show` prints `[x]` and the evidence per
item (every item of a done ticket shows `[x]`), and the board shows the item ticked and locked.

## Branches and worktrees

Each branch and git worktree has its own copy of `tickets.json`, so boards drift apart when
several agents work at once. The **board of record** is the one on the default branch in the
main checkout.

- **Warnings.** Every write warns (on stderr, not fatal) when you're in a secondary worktree
  (naming the main worktree's board), when the environment variable `SLATE_BOARD_OF_RECORD`
  points at a different tickets.json, or when the default branch's board (`origin/HEAD`, else
  `main` / `master`; no fetch) has tickets or handoff notes this board lacks. The warning
  prints `fix:` lines with the `diff` and `sync` commands.
- **`diff OTHER`** shows added, removed and changed tickets and fields. OTHER is a path to a
  tickets.json, a folder with `kanban/tickets.json` or `tickets.json`, or a git ref (`main`,
  `origin/main`). Rank-only changes are hidden unless `--include-rank`; handoff notes are
  compared by status and note, ignoring dates.
- **`sync --from OTHER`** brings OTHER's changes in: new tickets and phases are added, record
  lists (`handoff`, `commits`, `user_checks`, `item_checks`) are combined, `status` takes the
  one further along, other fields take theirs (`--prefer ours` to keep yours). Try it with
  `--dry-run` first; `--only ID,…` limits it.
- **`copy-to PATH`** writes a checked copy (to a file, or `PATH/kanban/tickets.json` for a
  folder). It refuses when the target has changes this board lacks, unless `--force`.
- **Merge driver.** Run once per clone:

  ```bash
  python3 kanban/board.py install-merge-driver
  ```

  It adds `kanban/tickets.json merge=slate` to `.gitattributes` (commit that) and sets
  `merge.slate.driver` = `python3 kanban/board.py merge-driver %O %A %B` and
  `merge.slate.name` = `Slate board merge` in the clone's git config. During a merge git then
  merges the board ticket by ticket: a change on one side is taken, record lists (`handoff`,
  `commits`, `user_checks`, `item_checks`) are combined, `status` takes the one further along,
  ranks are made unique again with every ticket after the tickets it needs. Anything else
  changed differently on both sides (or a ticket id added on both sides as two different
  tickets) is a conflict: yours is kept, it's reported, and git stops so you can look. If the
  merged board breaks a rule neither side broke, that is reported the same way.
  `install-merge-driver` writes the Python command it finds (`python3`, `python`, `py -3`) into
  the driver line; `--python CMD` picks another.

## Statuses

The columns are `meta.statuses`, in order. Every status has a **role** — `draft`, `backlog`,
`ready`, `in_progress`, `review`, `user_testing`, `merge_ready` or `done` — and board.py's rules
follow the role, not the name: which tickets are ready, what `next` resumes, draft checks,
claims, the user test and merge gates, what `done` means for dependents. A built-in status's
role is its own name; `meta.status_roles` maps any other name (`add-status qa --after review
--like review`), and `meta.status_labels` gives display titles (`edit-status in_progress
label="Doing"`). Boards without these fields work exactly as before; a status with no role
has no special rules.

**Notes for the ticket's history.** Each status says whether moving a ticket into it needs a note
(`set … --handoff "…"`): by default `review`, `user_testing`, `merge_ready` and `done` do, the
others don't. `add-status … --note required|optional` (default: as the `--like` state) and
`edit-status NAME note=required|optional` (built-in statuses too) change it. While path rules
exist, moving back always needs a note.

board.py refuses a status change that would leave no status with the `done` role, or none with
`backlog`/`ready`. Without a `draft` status, `new --draft` refuses (with the `add-status` fix).
Without `merge_ready`, `done` simply doesn't pass through it; without `user_testing`, `usertest`
still records results. `rename-status` moves tickets along (history notes keep the old name);
`remove-status` refuses while tickets are in it unless `--move-to`; `edit-status … role=…` refuses
when tickets in it would become invalid, and names them.

**Path rules** (optional, `meta.status_from`: `{status: [statuses it may be reached from]}`)
restrict forward moves (later in `meta.statuses`) made with `set`: a move that isn't allowed is
refused as `error: ID status: can't move <from> → <to>`, with the allowed previous statuses and a
`fix:` for the next allowed step. While rules exist, moving back is allowed but needs
`--handoff "why"`. `set-meta workflow=strict` writes the usual path (skipping statuses the board
doesn't have), `workflow=free` removes every rule, `edit-status NAME from=a,b` (or `from=`) sets
one. `promote`, a failed user test, `new --bug --reopen`, `sync` and the merge driver aren't path
moves (they still run every other check). `show` and `status` name the active workflow.
`flow` shows the moves your tickets actually made, so rules can follow how the team really
works, and `workflow --markdown` prints the matching `## Workflow` section for `SLATE.md`
(`doctor` reports `slate-md-workflow-stale` when the two drift apart).

## Who is on what (claims)

`set ID in_progress` records who is working on the ticket in `claimed_by`
(`{"by": "<branch>", "since": "YYYY-MM-DD HH:MM"}`): the current git branch, or `host-user`
when there is none; `--as NAME` overrides it. `review`, `user_testing` and `merge_ready` keep
the claim; `done`, `backlog`, `ready` and `draft` clear it. `next` and `list` skip tickets
claimed by someone else and show `on: <name>`; `status` lists every claim. Moving a ticket
someone else claimed is refused with an `ask the user:` line; with their OK add
`--take-over "why"` (the reason goes into the handoff note). `done` is not blocked by a claim
(it needs the merged PR anyway). `claim ID` / `release ID` set or clear a claim by hand.

## Doctor

`python3 kanban/board.py doctor` checks the project, locally (no network): board errors
(`board-errors`, `board-unreadable`), schema and board files behind the plugin
(`schema-outdated`, `board-files-outdated`; `--against PLUGIN_ROOT`), board newer than the plugin
(`plugin-outdated`), SLATE.md missing or lacking a section of the plugin's template
(`slate-md-missing`, `slate-md-sections`), its `## Workflow` section out of step with the board's
states and rules (`slate-md-workflow-stale`), its `Python:` line (`python-cmd-missing`), a plugin
folder it can't read (`plugin-unreadable`), the merge
driver (`merge-driver-missing`), `.gitignore` lines (`gitignore-missing`), `meta.repo_url` when
there is a git remote (`repo-url-missing`), a stale write lock (`write-lock-stale`), an active
unlock or request (`unlock-active`), and whether the default branch's board has tickets or notes
this one lacks (`board-behind`). `--json` gives each problem a `code`, a `kind` (`tickets` for
`board-behind`, `board-errors` and `board-unreadable`, which `/slate:sync` sorts out; `setup` for
the rest) and `fix` lines. `--brief` prints one line, e.g.
`Slate: 2 setup issues — run /slate:upgrade · board behind main — run /slate:sync`; the
session-start line (`next --brief --against …`) adds it when there is something to fix.

## Unlock (one hand edit)

Direct edits to `kanban/tickets.json` are blocked for Claude. Most repairs don't need one: run
the `fix:` lines `check` prints (see "repair" above). When a hand edit is truly needed (for
example git conflict markers from a merge without the merge driver), Claude explains why and
runs exactly this, with nothing wrapped around it:

```bash
python3 kanban/board.py unlock --reason "fix the merge by hand" --minutes 5
```

- **Run by Claude** (not a terminal), `unlock` only writes a request
  (`kanban/.slate-unlock-request.json`) and says how to approve it. It never unlocks by itself.
- **Approval is Claude Code's own permission card.** The plugin's guard answers "ask" for every
  `board.py unlock` command, so Claude Code shows its approval card in **Manual, Accept edits and
  Auto** mode (over SSH too). After you click Yes and the command has run, the guard turns the
  fresh request (under 2 minutes old) into the active unlock `kanban/.slate-unlock.json`
  (`approved: "permission prompt"`, with the permission mode). Only the plain command
  `python3|python|py -3 kanban/board.py unlock …` can activate it: anything with `&&`, `;`, `|`,
  `&`, backticks or `$(` never does.
- **Plan, Bypass and Don't-ask mode:** the guard refuses the command (in Plan mode: leave plan
  mode first; in the others nobody is there to approve). There, and in any agent tool without
  the guard, **you run `unlock` in your own terminal** (a second SSH session is fine): it shows
  a random 4-letter code and you type it; a match writes the active unlock
  (`approved: "terminal code"`).
- **One unlock = one edit:** the guard lets the next direct edit of that tickets.json through and
  uses the unlock up (it is renamed to `kanban/.slate-unlock.used.json`); after that, edits are
  blocked again. An unused unlock expires after `--minutes` (1 to 30).
- `lock` cancels an active unlock and a pending request. `check`, `status` and `doctor` warn
  while either exists.
- Everything is logged in `meta.unlock_log`: requested, activated (how, and the permission
  mode), used (by which tool), expired, refused (wrong code) and locked. The guard never writes
  `tickets.json`, so activations and uses are folded into the log by the next board.py write; if
  the board can't be written (e.g. it isn't valid JSON), entries wait in
  `kanban/.slate-unlock-log.json`.
- The unlock files and the write lock can't be edited directly. Keep them out of git:

```
kanban/.slate-unlock*.json
kanban/.slate-write.lock
kanban/.slate-serve.json
kanban/.slate-serve.log
```

Copilot CLI support: planned.

## Reading errors

Every error board.py prints says what is wrong and what to do next, in this shape:

```text
error: ACME-014 commits: has no commits linked, so it can't be done
  fix: python3 kanban/board.py link ACME-014 --commit HEAD   (then: python3 kanban/board.py set ACME-014 done --handoff '…')
  ask the user: was anything coded for ACME-014? If not, with their OK: … --no-code "why"
```

- `error: <ID> <field>: …` names the ticket (or `meta`, a phase, a batch entry) and field.
- Each `fix:` line is a command you can run as it is, with the real ids filled in. When
  there are several ways out, each has its own line; words in capitals (`OTHER_ID`, `URL`,
  `SHA`) are the parts you pick.
- `ask the user: …` means a person has to decide (did a user test pass, should a
  dependency go, was the file edited by hand). Ask before running anything.
- When one change breaks several rules, the error lists each one with its own fixes.
- `check --json` and `batch-check --json` give each error and warning a `"fix"` list with
  the same lines. Exit codes stay the same: `0` ok, `1` refused or invalid, `2` usage error.

## `tickets.json` schema

```json
{
  "meta": {
    "project": "Acme", "prefix": "ACME", "repo_url": "https://github.com/acme/app (optional)",
    "slate_version": "0.2.0", "schema_version": 2,
    "generated": "2026-09-26",
    "statuses": ["draft", "backlog", "ready", "in_progress", "review", "user_testing", "merge_ready", "done"],
    "areas": ["backend", "frontend", "infra"],
    "priorities": ["P0", "P1", "P2", "P3"],
    "user_test_areas": ["frontend", "ui"],
    "check_quiet_optional": false,
    "unlock_log": [{ "date": "2026-09-26 14:05", "event": "activated", "reason": "…", "minutes": 5,
                     "until": "2026-09-26T14:10:00Z", "approved": "permission prompt", "permission_mode": "default" }]
  },
  "phases": [
    { "id": "P1", "name": "Link arrives", "goal": "…", "demo": "…" },
    { "id": "BACKLOG", "name": "Someday", "goal": "…", "demo": "…", "unscheduled": true }
  ],
  "tickets": [{
    "id": "ACME-001", "title": "…", "summary": "…", "story": "…", "visual": "markdown, optional",
    "description": "markdown", "acceptance": ["…"], "test_scenarios": ["When …, then …"],
    "user_tests": [{ "title": "…", "setup": "…", "steps": ["…"], "expect": "…", "required": true }],
    "technical": "markdown, optional", "plan_doc": "docs/plans/…md, optional",
    "phase": "P1", "areas": ["frontend"], "priority": "P1", "rank": 1, "status": "in_progress",
    "claimed_by": { "by": "slate/ACME-001-reset", "since": "2026-09-26 14:05" },
    "depends_on": [], "unlocks": [], "estimate": "1d", "labels": [],
    "handoff": [{ "date": "2026-09-26", "status": "review", "note": "…" }],
    "user_checks": { "0": { "result": "pass", "date": "2026-09-26", "note": "" } },
    "item_checks": { "acceptance:0": { "date": "2026-09-26", "evidence": "…" }, "test:2": { "date": "2026-09-26", "evidence": "…" } },
    "commits": [{ "sha": "3f9c2a71b0d8…(7-40 hex)", "date": "2026-09-26", "message": "subject line", "branch": "optional" }],
    "pr": { "url": "https://github.com/acme/app/pull/42", "number": 42, "title": "optional", "state": "draft" },
    "done_without": { "code": "reason" }
  }]
}
```

`commits`, `pr` and `done_without` are optional and written only by board.py (`link`, and
`set ID done --no-code/--no-pr`). `pr.state` is one of `draft`, `open`, `merged`,
`closed`; `pr.number` is optional. `done_without` holds `code` and/or `pr` reasons.
`meta.repo_url` is optional; the board uses it to link commits.

**Schema 2** (Slate 0.2.0) only adds optional things, so schema 1 boards stay valid and
`migrate` upgrades them: the `merge_ready` status (inserted right before `done`),
`meta.check_quiet_optional`, `meta.unlock_log`, `phases[].unscheduled`, and
`tickets[].item_checks` (keys `acceptance:N` / `test:N`, written only by `check-item`). The
order of `phases` is the display order. Also optional in schema 2: `meta.status_roles`,
`meta.status_labels`, `meta.status_from` (see "Statuses"), `meta.removed` (archived tickets:
`{"ticket": {…}, "removed": "YYYY-MM-DD", "reason": "…"}`), `tickets[].claimed_by`
(written by `set`, `claim`, `release`) and the `meta.unlock_log` entries' `event` (`requested`,
`activated`, `used`, `expired`, `refused`, `locked`). The unlock files (`kanban/.slate-unlock.json`
`{"until": "<ISO UTC>", "reason": "…", "approved": "…"}`, the request, the used record, the
pending log) and `kanban/.slate-write.lock` are not board data.

Rules `board.py check` enforces:

- Every ticket needs `id title phase priority rank status depends_on areas estimate` plus
  `summary story description acceptance test_scenarios`.
- A **legacy ticket** (no `summary` and no `story`) only gets warnings for the missing new
  fields. Any other ticket gets errors.
- If any of a ticket's `areas` is in `meta.user_test_areas`, the ticket needs at least one
  `user_tests` entry with `"required": true`.
- A **draft** (status `draft`) needs only `title`, `summary` and `phase`. Leaving draft runs
  the full checks first. Only other drafts may depend on a draft.
- A ticket can't be `done` while something it needs isn't done, or while a required user
  test has no `pass` in `user_checks`.
- `commits` entries have a 7-40 character hex `sha` (each only once) and a `YYYY-MM-DD`
  `date`; `pr.url` and `meta.repo_url` are `http(s)://` links; `pr.state` is one of the four
  states.
- Ids are unique and look like `<prefix>-NNN`. Ranks are unique and every ticket ranks after
  the tickets it needs. Every `phase` and `status` exists.
- **Open** statuses (picked up first): `in_progress`, `review`, `user_testing`.
  **Waiting for merge**: `merge_ready` (listed by `next`, not resumed).
  **Ready**: `backlog` or `ready` with every dependency `done`, in a scheduled phase.

What the page relies on:

- `meta.statuses` sets the columns and every status dropdown, in that order. Without it the
  page uses the default list above.
- `meta.project` is the page title and brand (fallback "Slate board"). `meta.prefix` names
  the overlay key.
- A `phase` that's missing from `phases` still gets its own group, named after its id.
- A ticket using `merge_ready` on an older board without it in `meta.statuses` still gets
  the Waiting for merge column, right before Done.
- When `unlocks` is missing, the page works it out from `depends_on`.
- Missing lists (`areas`, `labels`, `depends_on`, `acceptance`, `test_scenarios`,
  `user_tests`) count as empty. A missing `rank` falls back to file order.

## Rank and priority

**Rank** is the build order: one sequence across every phase. Each run of tickets should
give you something working end to end that you can demo. Read Implementation order from top
to bottom and you have the build sequence.

**Priority** is how much it hurts to skip a ticket: `P0` can't ship without it, `P1` needed
for a real first version, `P2` more coverage, `P3` polish. Rank says *when*, priority says
*how important*.
