# Slate: design spec

Date: 2026-09-26 · Status: draft for review · Origin: generalised from the Forge build kit
(`forge/kanban/` + `forge/.claude/skills/forge-*`).

## 1. What Slate is

Slate is a Claude Code plugin that gives any project two things:

1. **A way to plan.** You brainstorm an idea with Claude in plain language, with examples and
   pictures, and it turns into well-written tickets on a local kanban board.
2. **A way to build.** Claude picks the next ready ticket, builds it, tests it, gets it
   reviewed, asks you to try it yourself when there is something to see, and writes a
   handoff note, then moves on.

The board is the Forge kanban (`index.html` + `tickets.json`), made project-neutral. It is
installed once as a plugin and set up per project with `/slate:init`. It never rebuilds the
board per project and never stores project knowledge inside the plugin.

**Not Slate:** a Jira client or sync, a hosted service, a database. Everything is files in the
project's repo.

### Success looks like

- In a brand-new repo: install plugin → `/slate:init` → `/slate:plan "password reset"` →
  tickets on the board a non-developer can read and understand → `/slate:work` builds them in
  order, and asks the user to try UI tickets before closing them.
- The same board UI, the same commands and the same rules in every project; only the project
  name, prefix, commands and review checks differ, and those live in the project's own files.
- Forge could switch to Slate later with no ticket loss (separate step, out of scope here).

## 2. Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Name **Slate**; plugin, marketplace and repo all `slate` (`github.com/Zidane786/slate`). Commands `/slate:init`, `/slate:plan`, `/slate:work`, `/slate:review`, `/slate:status`, `/slate:upgrade`. | Short, neutral, "a clean slate of tickets". |
| 2 | Own board only (`tickets.json` + `index.html`). No Jira. | Full control over fields and flow; no account needed. |
| 3 | Delivered as a Claude Code plugin; the repo is its own marketplace (the Plannotator pattern). | One install, versioned updates. |
| 4 | Installed once at user level; `/slate:init` per project **copies** the board and script into `kanban/`. | Teammates without the plugin can still open the board and run the script. |
| 5 | Skills only, no `.claude/commands/`. Skills are slash commands and can bundle files. | Current Claude Code format. |
| 6 | Slate's project context lives in **`SLATE.md`** at the repo root, written by `/slate:init`, never in the plugin. `CLAUDE.md` / `AGENTS.md` belong to the agent harness: Slate reads them for anything `SLATE.md` doesn't say, creates them only if missing, and never edits existing ones. | Slate's settings stay in one file Slate owns; the harness files stay yours. |
| 7 | Every ticket change (create, edit, rerank, status, user test) goes through `kanban/board.py`. Nobody hand-edits `tickets.json`; a plugin hook blocks Claude's Edit/Write on it. | Validation on every write; the board can't be broken. |
| 12 | Every Slate-owned file carries its version (`board.py`, `index.html`, `SLATE.md`, `tickets.json` meta). Each skill compares it with the plugin's version first and offers `/slate:upgrade` when the project is behind. | Copied files can't silently fall out of date. |
| 8 | Folder name is always `kanban/` at the repo root. | One fixed place for skills; Forge already uses it. |
| 9 | Tickets are written for a non-technical reader first; technical detail is kept in its own collapsed section. | The user must be able to read and understand every card. |
| 10 | Tickets that change something a person can see or click must be tried by the user before they close. | Tests pass is not the same as "it works for me". |
| 11 | No project-level skills by default. `init` creates one only for a real extra command the project needs (Forge's seeded-bug E2E is the example). | YAGNI; the generic procedure is in the plugin. |

## 3. The pieces at a glance

```
            ┌──────────────── Slate plugin (installed once, same for everyone) ───────────────┐
            │  skills: init · plan · work · review · status · upgrade                         │
            │  assets/board: index.html · board.py · README.md   templates: SLATE.md …      │
            └───────────────┬─────────────────────────────────────────────────────────────────┘
                            │ /slate:init copies board files, writes SLATE.md
                            ▼
 ┌──────────────────────── your project (all committed to git) ────────────────────────┐
 │  SLATE.md                ← Slate's context: commands, checks, rules, docs map        │
 │  CLAUDE.md / AGENTS.md   ← yours; Slate reads them, creates them only if missing     │
 │  kanban/index.html       ← the board you open in a browser                           │
 │  kanban/board.py         ← the only thing that changes tickets.json                  │
 │  kanban/tickets.json     ← meta + phases + tickets                                   │
 │  docs/plans/*.md         ← one file per brainstorm, linked from its tickets          │
 └──────────────────────────────────────────────────────────────────────────────────────┘
        ▲ you: open the board, run board.py        ▲ Claude: /slate:plan, /slate:work
```

### 3.1 Plugin repo layout

```
slate/
  .claude-plugin/
    marketplace.json      { "name": "slate", "owner": {...},
                            "plugins": [{ "name": "slate", "source": "./plugins/slate" }] }
  plugins/slate/
    .claude-plugin/plugin.json   { name, version, description, repository, keywords }
    skills/
      init/SKILL.md
      plan/SKILL.md
      work/SKILL.md
      review/SKILL.md
      status/SKILL.md
      upgrade/SKILL.md
    assets/board/
      index.html
      board.py
      README.md
    templates/
      SLATE.md             (skeleton init fills in)
      CLAUDE.md            (minimal, only used when the project has none)
      AGENTS.md            (minimal, only used when the project has none)
      plan-doc.md          (skeleton for docs/plans/<date>-<topic>.md)
    hooks/hooks.json       (SessionStart hint + tickets.json write guard, §8)
  tests/                   pytest for board.py; fixture projects for init
  docs/specs/              this file
  README.md  CHANGELOG.md  LICENSE
```

The plugin lives in `plugins/slate/` rather than the repo root so the marketplace can hold
more plugins later, as Plannotator does with `apps/hook`.

**Install:**

```
/plugin marketplace add Zidane786/slate
/plugin install slate@slate
```

Then `/slate:init` inside any repo. Skills find bundled files from the base directory Claude
Code reports when the skill loads (`<base>/../../assets/board/`).

### 3.2 A project after `/slate:init`

```
my-app/
  SLATE.md                  Slate's context for this project (written by init, §7.1)
  CLAUDE.md                 untouched if it existed; else a minimal one pointing to SLATE.md
  AGENTS.md                 untouched if it existed; else a minimal one pointing to SLATE.md
  kanban/
    index.html              same board, shows "Acme" and ACME- ids, version in the footer
    board.py                SLATE_VERSION at the top; `board.py version`
    tickets.json            meta { project, prefix, slate_version, schema_version, … } + phases + tickets
    README.md
  docs/plans/               created by /slate:plan
  .claude/settings.json     optional: enables the slate plugin for teammates
```

## 4. Tickets: what a card contains and how it reads

Every ticket must make sense to someone who doesn't write code. Plain language first, a
picture where it helps, then the checks, then technical notes out of the way.

### 4.1 Fields

| Field | Required | Who reads it | What goes in it |
|---|---|---|---|
| `id` | yes | all | `<PREFIX>-NNN`, assigned by `board.py`, never renumbered |
| `title` | yes | all | Plain outcome, e.g. "People can reset a forgotten password" |
| `summary` | yes | all | 1–2 sentences: what changes for the user and why it matters |
| `story` | yes | all | A short example of someone using it ("Priya forgets her password…") |
| `visual` | when useful | all | Markdown with an ASCII flow, screen sketch or before/after, in a fenced block |
| `description` | yes | all | Full detail in plain language: what's in, what's out, edge cases, open questions |
| `acceptance` | yes | all | "Done when…" bullets, each checkable, no jargon |
| `test_scenarios` | yes | all / dev | Automated tests, phrased as situation → expected result |
| `user_tests` | yes if the ticket changes something visible | user | Steps the user follows by hand, see 4.3 |
| `technical` | optional | dev | Files likely touched, API/schema notes, risks. Collapsed on the board |
| `plan_doc` | when from a plan | all | Path to the `docs/plans/` file this ticket came from |
| `phase`, `areas`, `priority`, `rank`, `status`, `depends_on`, `unlocks`, `estimate`, `labels` | as today | all | Same meaning as the Forge board |
| `handoff` | written by board.py | all | `[{date, status, note}]` log, shown on the board as a timeline |
| `user_checks` | written by board.py | all | Results of user tests: `{ "<index>": {result, date, note} }` |

Older Forge-style tickets without the new fields still load and render; `check` reports them
as warnings, not errors.

### 4.2 Writing rules (enforced by the plan skill, partly by `board.py check`)

- Title and summary say what the **user** gets, not what the code does.
- No unexplained jargon outside `technical`. If a term is needed, explain it in the same
  sentence.
- Each acceptance bullet can be answered yes/no by looking at the product or the tests.
- Every test scenario reads "When …, then …".
- Anything with an `areas` value listed in `meta.user_test_areas` (default `["frontend",
  "ui"]`) must have at least one `user_tests` entry marked `required`. `check` errors otherwise.

### 4.3 User tests

```json
"user_tests": [
  {
    "title": "Reset with a known email",
    "setup": "Open the app at http://localhost:3000 (the ticket's handoff says how to start it).",
    "steps": ["Click 'Forgot password'", "Type priya@example.com", "Click 'Send link'"],
    "expect": "You see 'Check your email' and a reset email appears in the dev inbox.",
    "required": true
  }
]
```

### 4.4 How a ticket looks on the board (drawer order)

```
┌ ACME-014 · People can reset a forgotten password ───────── Phase 1 · P1 · 1d ┐
│ Summary      One or two plain sentences.                                     │
│ Story        Priya forgets her password…                                     │
│ Picture      [ASCII flow / screen sketch, monospace, scrolls sideways]       │
│ Done when    ☐ …  ☐ …                                                        │
│ Try it yourself   ▸ Reset with a known email    [Pass] [Fail] note…          │
│ Automated tests   ☐ When …, then …                                           │
│ Details      full description                                                │
│ ▸ Technical notes (collapsed)                                                │
│ Needs ACME-013 · Unlocks ACME-015 · Plan: docs/plans/2026-09-26-reset.md     │
│ History      26 Sep review: built X, verified Y …  (handoff timeline)        │
└──────────────────────────────────────────────────────────────────────────────┘
```

Pass/Fail clicks in the browser go to the local overlay like status changes do today; the
source of truth is `board.py usertest` (the work skill asks the user and records the answer).

## 5. The board (`index.html`) changes

Keep the Forge board as is (single file, no dependencies, board + implementation-order views,
filters, drawer, overlay, export). Change only:

1. Title, brand and fallback name from `meta.project`; nothing says "Forge".
2. `localStorage` keys from `meta.prefix` (`slate.<prefix>.overlay.v1`), so projects on the
   same origin don't share local state.
3. No id-format assumption; any `<PREFIX>-NNN`.
4. Drawer renders the new fields in the order of 4.4; `technical` collapsed; `handoff` shown
   as a timeline; `user_tests` with pass/fail.
5. Markdown renderer also handles tables, blockquotes and `###` headings; fenced blocks stay
   monospace and scroll sideways so ASCII pictures never wrap.
6. New default status column **User testing** (see 7.3). Columns still come from
   `meta.statuses`.
7. **Draft preview:** if `kanban/draft.json` exists, its tickets show with a dashed border and
   a "draft" tag in the right columns and rank positions. Drafts are never exported or saved.
8. Card badge "needs you" when a ticket is in User testing.

## 6. The script (`kanban/board.py`)

Python 3 standard library only. Run from the repo root or `kanban/`. Every write validates
first and writes atomically (temp file + rename) with stable formatting (2-space JSON, key
order kept), so git diffs stay small. If validation fails, nothing is written and the errors
are printed.

### 6.1 Commands

| Command | Does |
|---|---|
| `init --project "Acme" --prefix ACME [--areas …]` | Create `tickets.json` with meta (default statuses `backlog ready in_progress review user_testing done`). Refuses if it exists. |
| `next` / `next --brief` | Resume `in_progress` / `review` / `user_testing` first, else the lowest-rank ready ticket. |
| `list [N]` | Next N ready tickets in rank order. |
| `show ID` | Full ticket, plain layout, including handoff and user-check results. |
| `status` | Progress per phase, counts per status, tickets waiting on the user. |
| `check` | Validate everything (6.2). Exit 1 on errors. |
| `version` | Print the board's Slate version, schema version and whether `tickets.json` matches. |
| `new --title "…" --summary "…" --phase P1 [--after ID] [--depends ID,…] …` | Create one ticket from flags; opens nothing, writes nothing invalid. Good for quick asks. |
| `add --file draft.json [--dry-run] [--after ID]` | Add many tickets from a draft (6.3). `--dry-run` writes `kanban/draft.json` for the board preview and prints the result. |
| `draft-check --file draft.json` | Validate a draft on its own (fields, writing rules, keys) before previewing. |
| `set ID STATUS [--handoff "…"]` | Change status; handoff note required for `review`, `user_testing`, `done`. |
| `edit ID field=value …` / `edit ID --file patch.json` | Change fields. Cannot change `id`. |
| `rerank ID --after OTHER` | Move a ticket; renumbers only what must move; keeps ranks above deps. |
| `add-phase --id P3 --name "…" --goal "…" --demo "…"` | Add a phase. |
| `usertest ID INDEX pass\|fail [--note "…"]` | Record a user test result. |
| `discard-draft` | Delete `kanban/draft.json`. |
| `upgrade --from <plugin assets dir>` | See 6.4. Replaces `index.html`, `board.py`, `README.md`; migrates `tickets.json` only by additive schema steps; updates versions. |

**The draft file is the only JSON Claude writes by hand**, and it lives outside `tickets.json`
(in the scratch area or `kanban/draft.json`). It never becomes ticket data except through
`board.py add`, which validates it.

### 6.2 Validation (runs on every write and in `check`)

Errors (block the write):

- JSON parses; `meta` has `project`, `prefix`, `statuses`.
- Ids unique and match `^<prefix>-\d{3,}$`.
- Every `depends_on` id exists; no dependency cycles.
- Ranks unique; every ticket ranks after all its dependencies.
- Every `phase` exists in `phases`; every `status` is in `meta.statuses`.
- Required fields present (4.1), with Forge-style legacy tickets exempted as warnings.
- No ticket `done` while any dependency is not `done`.
- No ticket `done` while a `required` user test has no `pass` result.
- Tickets in `meta.user_test_areas` have a required user test.

Warnings: missing `visual` on a multi-step flow, missing `technical`, legacy fields, very long
titles.

### 6.3 Draft format for `add`

Claude writes drafts with short keys instead of ids, so it never has to guess numbers:

```json
{
  "phases": [{ "id": "P1", "name": "Link arrives", "goal": "…", "demo": "…" }],
  "tickets": [
    { "key": "reset-request", "title": "…", "phase": "P1", "depends_on": [], … },
    { "key": "set-password",  "title": "…", "phase": "P2", "depends_on": ["reset-request", "ACME-009"], … }
  ]
}
```

`board.py` assigns the next free ids, resolves keys (and existing ids) in `depends_on`, places
ranks after dependencies (or after `--after`), fills `unlocks`, validates the whole board, and
writes. `--dry-run` shows the resulting ids and ranks and writes `draft.json` for the preview.

### 6.4 Versions and upgrading copied files

Because the board is copied into each project, every copy says which version it is:

| File | Where the version is | Example |
|---|---|---|
| `kanban/board.py` | first lines: `# Slate board v0.2.0 — do not edit, run /slate:upgrade` and `SLATE_VERSION = "0.2.0"` | `board.py version` prints it |
| `kanban/index.html` | `<meta name="slate-version" content="0.2.0">` + board footer "Slate v0.2.0" | visible to the user |
| `kanban/tickets.json` | `meta.slate_version`, `meta.schema_version` | written by board.py |
| `SLATE.md` | first line `<!-- slate v0.2.0 -->` | refreshed by upgrade |
| plugin | `plugins/slate/.claude-plugin/plugin.json` → `version` | the source of truth |

**Version check, step 0 of every skill:** read the plugin version and run `board.py version`.

```
 plugin 0.3.0 · project 0.2.0  →  "This project's board is Slate 0.2.0, the plugin is 0.3.0.
                                   Upgrade now? (/slate:upgrade)"  — ask, then continue either way
 plugin 0.2.0 · project 0.3.0  →  "A teammate upgraded this board; update your Slate plugin."
                                   Read-only commands still work; writes wait until updated
 same                          →  silent
```

**What `/slate:upgrade` does** (also offered by re-running `/slate:init`):

1. Show what changes: file list and the CHANGELOG entries between the two versions.
2. Replace `kanban/index.html`, `kanban/board.py`, `kanban/README.md` from the plugin. These
   are Slate-owned; local edits to them are not supported (the header says so).
3. Run `board.py upgrade`: apply schema migrations in order (additive only: new fields with
   defaults, new statuses appended; never deletes or renames data), bump versions, run
   `check`.
4. Refresh the version line and any new keys in `SLATE.md`, keeping every value the project
   set.
5. Show the git diff summary; the user commits it (or `/slate:work` commits it on its branch).

## 7. The skills

Every skill starts with the version check (6.4), then reads **`SLATE.md`** for project
specifics and falls back to `CLAUDE.md` / `AGENTS.md` and the docs for anything `SLATE.md`
doesn't cover (coding conventions, architecture). Every board read and write is a
`python3 kanban/board.py …` call.

### 7.1 `/slate:init` (only when typed: `disable-model-invocation: true`)

1. Look through the repo: README, CLAUDE.md, AGENTS.md, docs, manifest files
   (`pyproject.toml`, `package.json`, `go.mod`, …), CI config, git remote and default branch.
2. Work out: project name, suggested prefix, lint/test/typecheck commands, how to start the
   app for a live test, docs map.
3. Ask only what it couldn't work out, one question at a time: prefix, areas, extra review
   checks (e.g. Forge's security list), stop-and-ask rules, plan style (`plain` or
   `technical` default view), whether to enable the plugin in `.claude/settings.json`,
   whether a project-level skill is needed for an extra command.
4. Copy `assets/board/*` to `kanban/`; `board.py init`; write `SLATE.md`.
5. `CLAUDE.md` / `AGENTS.md`:
   - **missing** → create a minimal one from the template: project one-liner, where the docs
     are, and "Planning and build loop: see SLATE.md".
   - **present** → leave it untouched. Offer once (yes/no) to add a single line
     "Planning and build loop: see SLATE.md", so agents that only read `CLAUDE.md` still find it.
6. Show what it wrote. Suggest `/slate:plan` next.

**Re-running init** in a set-up project becomes an upgrade (6.4) plus a refresh of detected
values in `SLATE.md` (asks before changing any value you set). It never touches tickets.

**`SLATE.md`** (template), for example:

```markdown
<!-- slate v0.1.0 · written by /slate:init, safe to edit values -->
# Slate: how we plan and build in Acme

Board: `kanban/` · prefix `ACME` · open with `cd kanban && python3 -m http.server 8088`

## Commands
lint `npm run lint` · test `npm test` · types `npx tsc --noEmit`

## Live test
`npm run dev`, then open http://localhost:3000

## Extra review checks
- …

## Stop and ask before
- …

## Plan style
plain

## Docs map
| need | read |
|---|---|
| coding conventions | CLAUDE.md |
| architecture | docs/architecture.md |

## Rules
Work tickets with /slate:work · change tickets only through kanban/board.py ·
branch `slate/<id>-<slug>` · draft PRs only, never merge.
```

`SLATE.md` points to `CLAUDE.md` / `AGENTS.md` / docs instead of copying them, so nothing is
said twice.

### 7.2 `/slate:plan [idea]` — brainstorm into tickets

**Conversation rules:**

1. Plain words first. Every idea is played back as an example of someone using it.
2. Show, don't list: each stage has a picture (ASCII in the terminal by default; offer a
   visual HTML page for big ideas).
3. Two views: plain by default, technical on request ("show me the technical view"), default
   set by `Plan style` in `SLATE.md`.
4. One question at a time, multiple choice where possible.
5. Nothing reaches the board unseen: phase picture → plain cards → board preview → write.

**Stages (the skill's checklist):**

```
 ① Story      what it is, who it's for, what success is, what's out   (questions, one at a time)
 ② Flow       how it works, as a picture; technical view on request
 ③ Phases     what you can demo after each phase (vertical slices)
 ④ Cards      plain ticket cards: summary, done-when, tests, try-it-yourself
 ⑤ Preview    board.py add --dry-run → draft.json → you look at the board
 ⑥ Write      on "looks good": board.py add → check; save docs/plans/<date>-<topic>.md
```

Example of ② and ③ as the user sees them:

```
 User                    App                     Email
  │  Forgot password ──▶  │                         │
  │                       │── send reset link ────▶ │
  │  ◀──────── email with link (valid 30 min) ──────│
  │  click link, new pw ─▶│  check link, save pw    │
  │  ◀── logged in ───────│                         │

 Phase 1  "Link arrives"     → type email, reset email shows up in the dev inbox
 Phase 2  "Password changes" → click link, set password, log in with it
 Phase 3  "Safe"             → expired and reused links rejected, rate limit, audit log
```

Also handles small asks ("add a ticket for X"): skips ① to ③ when the idea is already clear,
still shows the card and the preview before writing.

Changes during preview ("move 016 before 015", "split 014") go through `rerank` / `edit` on
the draft, then refresh the preview.

### 7.3 `/slate:work [ID]` — the build loop

Same order as Forge's §4, generic:

```
 pick ─▶ in_progress ─▶ implement (tests first) ─▶ lint + full tests + live test
   ▲                                                         │
   │                                                         ▼
 next ◀── done ◀── user says pass ◀── user_testing ◀── review agent, fix findings
                    (only if the ticket has required user tests; else review ─▶ done)
```

1. **Pick:** `$ARGUMENTS` or `board.py next`; stop and explain if dependencies aren't done.
   `set ID in_progress`. Read the ticket, its plan doc, the docs map entries and the code.
2. **Implement** on branch `slate/<id>-<slug>` (pattern overridable in `SLATE.md`).
   Tests from `test_scenarios` first. Stay in scope; note adjacent work in the handoff.
3. **Test:** the lint and test commands from `SLATE.md`, full suite, then a live test
   when possible. Record what was run and seen.
4. **Review:** `set ID review`; dispatch a review agent with the generic brief (bugs, security
   basics, scope vs acceptance and test scenarios, blast radius) plus the project's extra
   checks from `SLATE.md`. Fix confirmed findings; re-test.
5. **User testing** (only when the ticket has required user tests): `set ID user_testing
   --handoff "…how to start the app…"`, then print each user test in plain steps and ask the
   user to try it. Record answers with `usertest`. A fail goes back to step 2 with the user's
   note. While waiting, Claude may pick other ready tickets that don't depend on this one.
6. **Commit, push, draft PR** when a remote exists; commit locally otherwise. Never merge.
7. **Close:** `set ID done --handoff "built; decisions; verified; follow-ups"`, `check`,
   report, and go to the next ticket if asked to keep going.

### 7.4 `/slate:review [ID]`

Step 4 of work on its own, for re-checks. Doesn't change status.

### 7.5 `/slate:status`

Read-only: phase progress, in-flight tickets with the last handoff line, **tickets waiting for
the user to test** (with their steps), blocked tickets and why, uncommitted work, next ticket.
Under 200 words. Includes the version line when the board is behind or ahead of the plugin.

### 7.6 `/slate:upgrade`

Runs 6.4: shows what changes, replaces the Slate-owned files, migrates `tickets.json`,
refreshes `SLATE.md`'s version line, shows the diff. Only when typed
(`disable-model-invocation: true`); other skills offer it, never run it silently.

## 8. Plugin hooks (`hooks/hooks.json`)

1. **SessionStart hint:** `[ -f kanban/board.py ] && python3 kanban/board.py next --brief ||
   true`, so each session starts with one line like "Slate 0.2.0: ACME-014 in review · 2
   waiting for you to test · next ready ACME-016 · board behind plugin, run /slate:upgrade".
   Silent in projects without `kanban/`.
2. **Write guard:** a `PreToolUse` hook on `Edit|Write|MultiEdit` that blocks any change to
   `kanban/tickets.json` with the message "Change tickets through kanban/board.py (new, add,
   edit, set, rerank)". This is what makes "only board.py writes tickets" true for Claude,
   not just a rule in a file.

## 9. Error handling

- `board.py` never writes a board that fails validation; errors say which ticket and field.
- `tickets.json` edited by hand or replaced by a board export: the next `board.py` call runs
  `check` and refuses writes until it's fixed, printing what's wrong.
- `init` in a repo that already has `kanban/tickets.json` without Slate meta (for example
  Forge): stop and ask; migration is a separate step.
- Skills run outside a Slate project: say so and suggest `/slate:init`.
- Board older than plugin: offer `/slate:upgrade`, keep working. Board newer than plugin:
  read-only until the plugin is updated, so an old `board.py` never writes a newer schema.
- `SLATE.md` missing but `kanban/` present: skills fall back to `CLAUDE.md` / `AGENTS.md` and
  suggest re-running `/slate:init` to recreate it.

## 10. Testing Slate itself

- `pytest` for `board.py`: every command, every validation rule, draft key resolution, rank
  placement, atomic write, stable formatting, legacy ticket loading.
- Board: a fixture `tickets.json` covering every field, opened in a browser (Playwright) to
  check the drawer order, collapsed technical notes, user-test buttons, draft preview, and
  per-prefix storage keys.
- Skills: run `/slate:init` and `/slate:plan` on two fixture repos (a Python one and a Node
  one) and check the files produced.
- Dogfood: Slate's own build is tracked on a Slate board in this repo.

## 11. Out of scope for v1

- Moving Forge onto Slate (later; needs a small migration of its `tickets.json` meta and
  CLAUDE.md §4 into `SLATE.md`).
- Codex / other agents (later, a folder per agent as Plannotator does; AGENTS.md already
  can point to `SLATE.md`).
- Jira or any external tracker sync; a hosted board; multi-user live editing.
