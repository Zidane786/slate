# Slate

Slate is a Claude Code plugin that gives any project two things:

1. **A way to plan.** You talk an idea through with Claude in plain words, with examples and
   pictures, and it becomes clear, readable tickets on a kanban board that lives in your repo.
2. **A way to build.** You tell Claude which ticket to build (or say yes to the one it
   suggests). It builds it with tests, gets it reviewed, asks you to try it yourself when
   there's something to see, commits it, opens a draft PR, records both on the ticket, writes a
   note about what it did, and **stops**. It only moves to another ticket when you say so.

Everything is plain files in your repository: no account, no server, no database, no Jira.
Anyone on the team can open the board in a browser, even without the plugin.

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

## The six commands

| Command | What it does |
|---|---|
| `/slate:init` | Sets Slate up in this repo: copies the board into `kanban/`, writes `SLATE.md` with this project's commands and rules. Re-run it to upgrade and refresh. |
| `/slate:plan [idea]` | Brainstorms an idea into tickets: story → flow picture → phases → plain cards → board preview → save as ready tickets or drafts. Also "add a ticket for X", or `/slate:plan ACME-012` to finish a draft. |
| `/slate:work [ID]` | Builds the ticket you name (or suggests the next one and asks first) end to end: tests, review, your check, commit + draft PR recorded on the ticket, handoff note. Then stops. Say "keep going" or "do the next 3" if you want more. |
| `/slate:review [ID]` | Runs just the review step on the current changes, for a re-check. |
| `/slate:status` | Where are we: progress per phase, what's in flight, what's waiting for you to test, what's next. |
| `/slate:upgrade` | Brings this project's copy of the board up to the plugin's version. |

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
     stop ◀── done + commit/PR on ticket ◀── you try it and say "pass" ◀── user testing ◀─┘
      (next ticket only when you say so)    (user testing only for tickets you can see)
```

**You stay in charge.** Slate never works through the board on its own. One ticket per
request; it asks before starting when you didn't name one; it waits for you while you test.

Tickets are written for someone who doesn't write code: a plain title, a one-line summary, a
short story of someone using it, a picture when it helps, "done when" checks, automated tests
phrased "When …, then …", and step-by-step "try it yourself" instructions. Technical notes sit
in their own collapsed section.

**Drafts** are tickets saved on the board but not finished yet. `/slate:work` never picks them;
finish one with `/slate:plan <ID>` or `python3 kanban/board.py promote <ID>`.

## What lives where in your project

```
my-app/
  SLATE.md              Slate's settings for this project: commands, live test, review checks,
                        stop-and-ask rules, plan style, docs map. Written by /slate:init; edit freely.
  CLAUDE.md, AGENTS.md  Yours. Slate reads them, creates them only if missing, never edits them
                        (it may offer to add one pointer line).
  kanban/
    index.html          The board. Open it: cd kanban && python3 -m http.server 8088
                        then http://localhost:8088
    board.py            The only thing that changes tickets.json (validates every write).
    tickets.json        Project info, phases and tickets. Don't hand-edit it.
    README.md           How to use the board and board.py by hand.
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

- **Board older than plugin:** Slate offers `/slate:upgrade`. It shows what changes, replaces
  `kanban/index.html`, `board.py` and `README.md`, migrates `tickets.json` by adding only
  (never deletes or renames your data), refreshes `SLATE.md`'s version line, and shows the diff
  for you to commit.
- **Board newer than plugin** (a teammate upgraded): update your plugin —
  `claude plugin marketplace update slate`, then `claude plugin update slate@slate`, and restart.
  Until then Slate only reads the board.

## FAQ

**Can I edit `tickets.json` by hand?** Please don't; use `python3 kanban/board.py` (`new`,
`add`, `edit`, `set`, `rerank`, `usertest`). It checks every change so the board can't break.
The plugin blocks Claude from editing the file directly.

**Do I need the plugin to see the board?** No. The board is a single HTML file plus a Python
script (standard library only) in your repo.

**Does Slate push or merge code?** It commits on a `slate/<id>-<slug>` branch and, only when
the repo has a remote, pushes and opens a *draft* pull request. It never merges.

**What if my project already has a `kanban/` folder?** `/slate:init` stops and asks; it won't
overwrite a board it didn't create.

**Where do project-specific rules go?** In `SLATE.md` (extra review checks, stop-and-ask
rules, commands). Coding conventions stay in your `CLAUDE.md`/docs; `SLATE.md` points to them.

**Why did Claude ask me to try something?** Tickets that change something you can see or
click have "try it yourself" steps. They close only after you say they work.

## Developing Slate

```
plugins/slate/     the plugin: skills/, assets/board/, templates/, hooks/
tests/             pytest for board.py and the hooks
docs/specs/        the design spec
```

Run the tests with `python3 -m pytest -q` (or `uv run --with pytest python -m pytest -q`).
Try the plugin locally with `claude --plugin-dir plugins/slate`, and check the manifests with
`claude plugin validate .`.

See [CHANGELOG.md](CHANGELOG.md) and the design spec in
[docs/specs/2026-09-26-slate-design.md](docs/specs/2026-09-26-slate-design.md).
