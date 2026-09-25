# Slate board

The project's kanban and build-order board. One file, no build step, no dependencies:
`index.html` is plain HTML, CSS and JavaScript and reads `tickets.json` from the same folder.
It was put here by `/slate:init` and is kept current by `/slate:upgrade`. Don't edit
`index.html`, `board.py` or this README by hand: `/slate:upgrade` replaces them.

## Open it

```bash
cd kanban
python3 -m http.server 8088
```

Then open http://localhost:8088.

The page loads `./tickets.json` (and `./preview.json` if there is one), so it needs a
static server. If you open `index.html` straight from disk (`file://`), the browser blocks
that. The page then shows a file picker: choose `tickets.json`, and `preview.json` as well
if you want to see the preview. After that everything works the same.

The footer shows the board's Slate version (`Slate v0.1.0`) and the version recorded in
`tickets.json`. The page also has `<meta name="slate-version">` for scripts.

## Views

**Board.** One column per status, in the order of `meta.statuses`. A status that a ticket
uses but `meta.statuses` leaves out still gets a column, so nothing disappears. Each card
shows the id, rank, priority, title, the summary in one line, phase, areas, estimate, the
number of dependencies, a small `PR` tag when a pull request is linked, and one state tag:

| Tag | Meaning |
|---|---|
| `ready` | Status is Backlog or Ready and everything it needs is Done. |
| `blocked` | Something it needs isn't Done yet (red left edge). |
| `needs you` | It's in **User testing**: try it yourself and tell Claude how it went. |
| `not ready` | It's a **Draft**: saved, but not finished, so no one works on it yet. |
| `preview` | Not saved at all; see "Preview" below (dashed border). |

Drag a card to another column to change its status in your browser, or use the status
dropdown in the ticket drawer. Sort by rank (default), priority or id. The header shows
totals, and a "waiting for you to test" pill when tickets are in User testing. Click it to
show only those tickets.

**Implementation order.** Tickets grouped by phase, with each phase's goal, demo and a
done/total bar, in rank order. Each row has the summary, dependency chips, a state tag and a
status dropdown. Blocked tickets and drafts are dimmed.

### Draft and User testing columns

- **Draft** holds tickets that are written down but not finished. `board.py next` and
  `list` never pick them. A draft needs only a title, a summary and a phase. Its drawer
  lists what is still missing. `board.py promote ID` moves it to Backlog once it's complete.
- **User testing** holds tickets that change something you can see or click. They wait
  here until you've tried them. Each one has **Try it yourself** steps in its drawer.

## The ticket drawer

Click a card or row. Prev / Next (or the ← → keys) walk the tickets in rank order. The
drawer reads top to bottom:

1. **Summary**: what you get, in one or two sentences.
2. **Story**: a short example of someone using it.
3. **Picture**: a diagram or screen sketch. Wide pictures scroll sideways instead of
   wrapping, so the drawing stays intact.
4. **Done when**: the checks that say it's finished (tick boxes).
5. **Try it yourself**: the steps you follow by hand: before you start, numbered steps,
   what you should see, and whether the test is required. **Pass / Fail** buttons record
   your answer *in this browser only*. A result Claude has saved (from `board.py usertest`)
   shows as a "Recorded: passed/failed" badge with its date and note.
6. **Automated tests**: what the tests check, as "When …, then …" (tick boxes).
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

The page never changes `tickets.json`. Status changes, ticks and Pass/Fail clicks go
to an **overlay** in `localStorage`. The key includes the project's prefix, so two boards
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
in an exported file, the next `board.py` command checks it and refuses to write until it's
valid.

| Command | What it does |
|---|---|
| `python3 kanban/board.py next [--brief]` | What to work on: open tickets first (In progress, Review, User testing), else the lowest-rank ready one |
| `list [N]` | Next N ready tickets |
| `show ID` | A ticket in drawer order, with history and user test results |
| `status` | Progress per phase, count per status, tickets waiting for you, drafts |
| `check` | Check the whole board. Prints errors, then warnings |
| `version [--against PLUGIN_ROOT]` | Board, schema and file versions, and whether the plugin is newer |
| `new --title … --summary … --phase … [--draft] …` | Add one ticket (`--draft` for an unfinished one) |
| `add --file BATCH [--dry-run] [--as-draft] [--after ID]` | Add many tickets from a batch file. `--dry-run` writes `preview.json` |
| `batch-check --file BATCH` | Check a batch file before adding it |
| `discard-preview` | Delete `preview.json` |
| `set ID STATUS [--handoff "…"] [--no-code "why" \| --no-pr "why"]` | Change status. A note is required for review, user_testing and done. Done also needs code linked (see below) |
| `edit ID key=value … [--file PATCH.json]` | Change fields (not id, rank, status, handoff, user_checks, unlocks, commits, pr or done_without) |
| `rerank ID --after OTHER` / `--first` | Move a ticket in the build order |
| `promote ID` | Move a draft to Backlog after full checks |
| `add-phase --id P3 --name … --goal … --demo …` | Add a phase |
| `usertest ID INDEX pass\|fail [--note "…"]` | Save a user test result. A fail sends a User testing ticket back to In progress |
| `link ID [--commit SHA_OR_REF …] [--message "…"] [--pr URL] [--pr-state S] [--pr-title "…"]` | Record the commits and pull request that built a ticket (any status, done included) |
| `set-meta key=value … / key:=JSON` | Change `project`, `repo_url`, `areas` or `user_test_areas` (nothing else) |
| `upgrade --from ASSETS_DIR` / `migrate` | Used by `/slate:upgrade` |

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

### Done needs code

`set ID done` checks, in a git repository:

1. The ticket has at least one commit linked, and every linked sha is a commit in this
   repository (`git cat-file -e`).
2. If the repository has a remote (`git remote`), a pull request is linked too.

Ways out, for when that is really so: `--no-code "why"` (nothing was coded; skips both
checks) and `--no-pr "why"` (skips only the PR check). The reason goes on the end of the
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

Only `project`, `repo_url`, `areas` and `user_test_areas` can change (lists as `key:=JSON`).
The prefix and statuses are fixed once tickets exist. `init --repo-url URL` sets `repo_url`
at the start. A trailing `/` or `.git` is dropped.

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
    "slate_version": "0.1.0", "schema_version": 1,
    "generated": "2026-09-26",
    "statuses": ["draft", "backlog", "ready", "in_progress", "review", "user_testing", "done"],
    "areas": ["backend", "frontend", "infra"],
    "priorities": ["P0", "P1", "P2", "P3"],
    "user_test_areas": ["frontend", "ui"]
  },
  "phases": [{ "id": "P1", "name": "Link arrives", "goal": "…", "demo": "…" }],
  "tickets": [{
    "id": "ACME-001", "title": "…", "summary": "…", "story": "…", "visual": "markdown, optional",
    "description": "markdown", "acceptance": ["…"], "test_scenarios": ["When …, then …"],
    "user_tests": [{ "title": "…", "setup": "…", "steps": ["…"], "expect": "…", "required": true }],
    "technical": "markdown, optional", "plan_doc": "docs/plans/…md, optional",
    "phase": "P1", "areas": ["frontend"], "priority": "P1", "rank": 1, "status": "backlog",
    "depends_on": [], "unlocks": [], "estimate": "1d", "labels": [],
    "handoff": [{ "date": "2026-09-26", "status": "review", "note": "…" }],
    "user_checks": { "0": { "result": "pass", "date": "2026-09-26", "note": "" } },
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
  **Ready**: `backlog` or `ready` with every dependency `done`.

What the page relies on:

- `meta.statuses` sets the columns and every status dropdown, in that order. Without it the
  page uses the default list above.
- `meta.project` is the page title and brand (fallback "Slate board"). `meta.prefix` names
  the overlay key.
- A `phase` that's missing from `phases` still gets its own group, named after its id.
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
