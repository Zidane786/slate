# Slate

Slate is a Claude Code plugin that gives any project two things:

1. **A way to plan.** You talk an idea through with Claude in plain words, with examples and
   pictures, and it becomes clear, readable tickets on a kanban board that lives in your repo.
2. **A way to build.** You tell Claude which ticket to build (or say yes to the one it
   suggests). It builds it with tests, ticks each check on the ticket as it's proven, gets it
   reviewed, asks you to try it yourself when there's something to see, commits it, opens a
   draft PR, records both on the ticket, moves it to **Waiting for merge**, and **stops**. It
   closes the ticket only after you say the PR is merged, and only moves to another ticket when
   you say so.

Everything is plain files in your repository: no account, no hosted service, no database, no
Jira. Anyone on the team can open the board in a browser, even without the plugin.

## Install

In Claude Code:

```
/plugin marketplace add Zidane786/slate
/plugin install slate@slate
```

Then, inside any repo:

```
/slate:init
```

## The seven commands

| Command | What it does |
|---|---|
| `/slate:init` | Sets Slate up in this repo: copies the board into `kanban/`, asks how your team works (parallel agents, who merges, QA, board server), writes `SLATE.md` with this project's commands, rules and workflow. Re-run it to upgrade and refresh. |
| `/slate:plan [idea]` | Brainstorms an idea into tickets: story → flow picture → phases → plain cards → board preview → save as ready tickets or drafts. Also "add a ticket for X", "log a bug in ACME-004", "park this idea for someday", notes, priorities, removing or restoring tickets, phases, **custom columns** ("add a QA column") and **workflow rules**, or `/slate:plan ACME-012` to finish a draft. |
| `/slate:work [ID]` | Builds the ticket you name (or suggests the next one and asks first) end to end: tests, review, your check, commit + draft PR recorded on the ticket, handoff note, then Waiting for merge. Then stops. Tell it "the PR is merged" to close the ticket. Say "keep going" or "do the next 3" if you want more. |
| `/slate:review [ID]` | Runs just the review step on the current changes, for a re-check. |
| `/slate:status` | Where are we: progress per phase, who is on what, what's waiting for you to test or for a merge, board health, the live board link, what's next. |
| `/slate:sync [branch]` | Sorts the board out across branches and worktrees: shows what differs in plain words, brings changes across only with your yes, walks you through board merge conflicts one by one, repairs a broken board. |
| `/slate:upgrade` | Brings this project's copy of the board up to the plugin's version: shows what's new first, then sets up anything new (asking each time) and runs a health check. |

## How it flows

```
  you have an idea
        │
        ▼
 /slate:plan ── ① story ─ ② flow picture ─ ③ phases ─ ④ plain cards ─ ⑤ board preview
        │                                                                   │
        │            "save as ready / save as drafts / discard?"  ◀────────┘
        ▼
 kanban/tickets.json  ◀── every change goes through kanban/board.py
        │
        ▼
 /slate:work ── pick ─▶ build (tests first) ─▶ lint + tests + live test ─▶ review ─▶ fix
        ▲                                                                            │
        │                                                                            ▼
     stop ◀── waiting for merge ◀── commit + PR on ticket ◀── you say "pass" ◀── user testing ◀─┘
                    │                                        (only for tickets you can see)
                    ▼  you: "the PR is merged"
                  done ──▶ stop   (next ticket only when you say so)
```

**You stay in charge.** Slate never works through the board on its own. One ticket per
request; it asks before starting when you didn't name one; it waits for you while you test.

Tickets are written for someone who doesn't write code: a plain title, a one-line summary, a
short story of someone using it, a picture when it helps, "done when" checks, automated tests
phrased "When …, then …", and step-by-step "try it yourself" instructions. Technical notes sit
in their own collapsed section.

**Drafts** are tickets saved on the board but not finished yet. `/slate:work` never picks them;
finish one with `/slate:plan <ID>` or `python3 kanban/board.py promote <ID>`.

**Waiting for merge** is the column between User testing and Done. A ticket lands there when
it's built, reviewed, tested by you (when there's something to see), and its commit and PR are
recorded. It moves to Done only when you tell Claude the PR is merged (or agree to close it
without one), so the board never claims work is finished while the PR is still open.

**Bugs.** When something built earlier turns out broken, ask `/slate:plan` to log it. It
becomes its own ticket tagged `bug` and `fixes-ACME-004`, ranked just before the ticket it
fixes, and that ticket waits for it (`board.py new --bug --fixes ACME-004 …`). If the broken
ticket was already done, Slate asks before reopening it.

**Someday ideas** go in an *unscheduled* phase (for example `BACKLOG`). The board shows it last
and folded, and `/slate:work` never picks from it until a ticket is moved to a real phase.

**Ticks with evidence.** Each "Done when" and automated-test item is ticked on the board as it's
proven (`board.py check-item`), with a note of how: a test name or what was seen. The board
shows those ticks and their evidence, and refreshes by itself every few seconds while it's open.

**Notes, mistakes and tidying up.** `board.py note ACME-014 "waiting on legal"` adds a history
note without moving the ticket. Mistakes are fixed with commands, never by hand: `unlink` (a
wrongly linked commit or PR), `usertest … reset` (a wrongly recorded result), `edit ID1,ID2 …`
(several tickets at once). `remove ACME-011 --reason "duplicate"` archives a ticket (Slate asks
first) and `restore ACME-011` brings it back; ids are never reused.

## The board page: live or view-only

```bash
python3 kanban/board.py serve --ensure      # prints the URL, e.g. http://localhost:8088
```

Slate commands run this for you (unless `SLATE.md` says `Board server: off`) and never start a
second one. It serves the board **live**: ticking an item, Pass/Fail on a user test, dragging a
card to another column, adding a note, "Promote" on a draft, "Take"/"Release" on a ticket all
save to `tickets.json` through board.py, with the same checks and rules as the commands (a
refused move shows why and what to do). It listens on your machine only (127.0.0.1), picks the
next free port if 8088 is taken (`--port N`, `Board port:` in `SLATE.md`), and stops itself after
8 idle hours (`serve --status`, `serve --stop`).

Open the board any other way (`cd kanban && python3 -m http.server 8088`, or `index.html` from
disk) and it is **view-only**: your clicks stay in that browser, marked "local only", and
**Copy as board.py commands** turns them into commands you (or Claude) can run.

**Over SSH or in tmux:** the server runs on the remote machine; forward the port from your own
machine with `ssh -L 8088:localhost:8088 you@host`, then open http://localhost:8088. Everything
else (permission cards, typed unlock codes) works in the terminal you're in.

## Columns, roles and workflow rules

The default columns are Draft, Backlog, Ready, In progress, Review, User testing, Waiting for
merge, Done. You can shape them: add one (`add-status qa --after review --like review --label
"QA"`), rename or relabel one (`edit-status in_progress label="Doing"`), reorder or remove one.
Every column has a **role** (one of the eight built-in ones), and Slate's rules follow the role,
so a "QA" column that works like Review is treated as review by `/slate:work`, the gates and
the board. Each column also says whether moving a ticket into it needs a **note for the ticket's
history** (what was done, what to check): by default Review, User testing, Waiting for merge and
Done do and the others don't; change it with `edit-status review note=optional` or
`add-status … --note required`.

**Workflow rules** are optional. By default any move is allowed. `set-meta workflow=strict`
makes tickets move forward only along the usual path (Backlog → In progress → Review → User
testing → Waiting for merge → Done); `edit-status qa from=review` sets a single rule; moving
back always works with a note. A refused move says which step comes next. `/slate:init` asks how
your team works and recommends columns and rules (or none); `/slate:upgrade` can recommend them
from how your tickets actually moved (`board.py flow`). `SLATE.md`'s `## Workflow` section always
describes the current setup, so every agent knows it.

## Branches, worktrees and several agents

Every branch and git worktree carries its own copy of `kanban/tickets.json`, so with parallel
agents or stacked PRs the copies drift. Slate keeps it manageable:

- **Claims: who is on what.** `/slate:work` creates the ticket branch, then moves the ticket to
  In progress, which claims it for that branch. Other agents' `next` and `list` skip it (shown
  as "on: <branch>"), and nobody moves it without your OK (`--take-over "why"`). `claim` /
  `release` do it by hand; the board page has Take / Release buttons.
- **Write lock.** Several board.py commands at once (parallel agents, two terminals, the board
  page) take turns through `kanban/.slate-write.lock`, so no write is lost. A lock left by a
  crashed command is cleared with `board.py unlock-write`.
- **Board of record.** `board.py` warns whenever you write somewhere that isn't the board of
  record (the default branch in the main checkout): a secondary worktree, a board other than the
  one `SLATE_BOARD_OF_RECORD` names, or a board missing tickets or notes the default branch has.
  `/slate:work` stops and asks when it sees that.
- **`/slate:sync`** shows what differs (`board.py diff main`), brings it across with your yes
  (`sync --from main`, dry run first), and walks through merge conflicts one at a time.
  `copy-to PATH` writes a checked copy to another checkout.
- **Merge driver.** `python3 kanban/board.py install-merge-driver` (once per clone; `/slate:init`
  and `/slate:upgrade` offer it) lets git merge `tickets.json` ticket by ticket instead of
  leaving conflict markers in the JSON.
- One PR covering several tickets: `board.py link ACME-004,ACME-005 --pr URL`.

## Health check

`python3 kanban/board.py doctor` checks the project in one go: board and plugin versions, the
`SLATE.md` sections and settings, the Python command, the merge driver, `.gitignore`, the repo
address, a stale write lock or active unlock, board errors, and whether the default branch's
board has tickets this one lacks. Each problem comes with the command that fixes it. Setup
problems are fixed by `/slate:upgrade`; board problems by `/slate:sync`. The session-start line
mentions it when something needs attention.

## What lives where in your project

```
my-app/
  SLATE.md              Slate's settings for this project: commands, live test, review checks,
                        stop-and-ask rules, plan style, docs map, Python command, board server,
                        the Workflow (columns, roles, rules, who merges) and a log of Slate
                        updates. Written by /slate:init; edit freely.
  CLAUDE.md, AGENTS.md  Yours. Slate reads them, creates them only if missing, never edits them
                        (it may offer to add one pointer line).
  kanban/
    index.html          The board. Open it live: python3 kanban/board.py serve --ensure
                        (Slate commands start it for you; prints the URL)
    board.py            The only thing that changes tickets.json (validates every write).
    tickets.json        Project info, phases and tickets. Don't hand-edit it.
    README.md           How to use the board and board.py by hand.
  .gitattributes        One line so git merges tickets.json with Slate's merge driver.
  .gitignore            Keeps local files out of git: kanban/.slate-unlock*.json (one-time
                        unlocks), .slate-write.lock, .slate-serve.json / .slate-serve.log.
  docs/plans/           One file per brainstorm, linked from its tickets.
  .claude/settings.json Optional: offers the Slate plugin to teammates.
```

Commit all of it. Teammates without the plugin can still open the board and run
`python3 kanban/board.py status`, `next`, `show ID`.

### Sharing with your team

`/slate:init` can add this to `.claude/settings.json` so teammates are offered the plugin
when they trust the repo:

```json
{
  "extraKnownMarketplaces": {
    "slate": { "source": { "source": "github", "repo": "Zidane786/slate" } }
  },
  "enabledPlugins": { "slate@slate": true }
}
```

## Upgrading

The board is copied into each project, so each copy carries its version (`board.py version`,
the board footer, `SLATE.md`'s first line, `tickets.json` meta). Every Slate command compares
it with the plugin:

- **Board older than plugin:** Slate offers `/slate:upgrade`. It first shows **what's new** in
  plain words for every version in between, then replaces `kanban/index.html`, `board.py` and
  `README.md`, migrates `tickets.json` by adding only (never deletes or renames your data), runs
  that version's setup steps (asking before each: merge driver, `.gitignore`, board server,
  columns and workflow rules), adds a dated line to `SLATE.md`'s "Slate updates", runs `doctor`
  until healthy, and shows the diff for you to commit.
- **Board newer than plugin** (a teammate upgraded): update your plugin —
  `claude plugin marketplace update slate`, then `claude plugin update slate@slate`, and restart.
  Until then Slate only reads the board.

Agents pick up new commands as soon as the plugin updates: the skills and the command reference
(`plugins/slate/reference/commands.md`) ship inside the plugin.

## FAQ

**Can I edit `tickets.json` by hand?** Please don't; use `python3 kanban/board.py` (`new`,
`add`, `edit`, `set`, `note`, `remove`, `unlink`, …) or the live board page. It checks every
change so the board can't break. The plugin blocks Claude from editing the file directly. If a
hand edit is truly needed (say, repairing a messy merge), Claude explains why and runs
`board.py unlock --reason "…"`:

- In **Manual**, **Accept edits** and **Auto** permission mode, Claude Code shows its own
  approval card (the same kind as for any command); your Yes allows exactly one edit.
- In **Plan**, **Bypass permissions** and **Don't-ask** mode nobody is there to click, so the
  unlock is refused; you run `python3 kanban/board.py unlock --reason "…"` in your own terminal
  (a tmux pane or second SSH session is fine) and type the 4-letter code it shows.

One unlock = one edit, expiring after a few minutes if unused, all logged. Git operations on the
file (checkout, restore, merge, rebase, stash) are never blocked.

**Does Slate work with other agent tools?** The board and `board.py` work anywhere Python runs
(macOS, Linux, Windows; `python3`, `python` or `py -3`). The skills and hooks are for Claude
Code. GitHub Copilot CLI support: planned.

**Do I need the plugin to see the board?** No. The board is a single HTML file plus a Python
script (standard library only) in your repo: `python3 kanban/board.py serve` gives the live
board to anyone.

**Does Slate push or merge code?** It commits on a `slate/<id>-<slug>` branch and, only when
the repo has a remote, pushes and opens a *draft* pull request. It never merges. You merge,
then tell Claude, and the ticket moves from Waiting for merge to Done.

**What if my project already has a `kanban/` folder?** `/slate:init` stops and asks; it won't
overwrite a board it didn't create.

**Where do project-specific rules go?** In `SLATE.md` (extra review checks, stop-and-ask
rules, commands). Coding conventions stay in your `CLAUDE.md`/docs; `SLATE.md` points to them.

**Why did Claude ask me to try something?** Tickets that change something you can see or
click have "try it yourself" steps. They close only after you say they work.

## Developing Slate

```
plugins/slate/     the plugin: skills/, assets/board/, templates/, hooks/, reference/ (all
                   commands for agents), upgrades/ (per-version upgrade steps)
tests/             pytest for board.py and the hooks
docs/specs/        the design spec
```

Run the tests with `python3 -m pytest -q` (or `uv run --with pytest python -m pytest -q`).
Try the plugin locally with `claude --plugin-dir plugins/slate`, and check the manifests with
`claude plugin validate .`.

See [plugins/slate/CHANGELOG.md](plugins/slate/CHANGELOG.md) and the design spec in
[docs/specs/2026-09-26-slate-design.md](docs/specs/2026-09-26-slate-design.md).
