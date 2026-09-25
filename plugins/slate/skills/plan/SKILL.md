---
name: plan
description: Brainstorm an idea into plain-language tickets on the Slate kanban board - story, flow picture, phases, plain cards, a board preview, then save as ready tickets or drafts. Also adds a single quick ticket, or finishes a draft ticket. Use when asked to plan a feature, "add a ticket for X", break an idea into tickets, or finish a draft.
argument-hint: "[idea | ticket ID]"
allowed-tools: Bash(python3 kanban/board.py *)
---

# /slate:plan [idea | ID] — brainstorm into tickets

Turn an idea into tickets that someone who doesn't write code can read and understand, and
show every one before it is saved. Every board read and write is a `python3 kanban/board.py …`
call from the repo root. **Never edit `kanban/tickets.json` directly** (a hook blocks it); the
only JSON you write by hand is the batch file.

## Step 0: version check and context

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code). If it still reads literally,
   use this skill's base directory (printed when the skill loads) + `/../..`, made absolute.
2. If `kanban/board.py` is missing: say "This repo isn't set up for Slate yet — run
   `/slate:init` first." and stop.
3. `python3 kanban/board.py version --against "<ROOT>"`
   - `same` → say nothing.
   - `behind` → "This project's board is Slate <board>, the plugin is <plugin>. Upgrade now
     with `/slate:upgrade`?" Ask once, then continue either way (never run it yourself).
   - `ahead` → "A teammate upgraded this board; update your Slate plugin
     (`claude plugin marketplace update slate`, `claude plugin update slate@slate`, restart)." You may read and discuss, but do not write
     anything to the board until the plugin is updated.
4. Read `SLATE.md` (prefix, **Plan style**, docs map). If it is missing, fall back to
   `CLAUDE.md` / `AGENTS.md` / docs and suggest re-running `/slate:init`.
5. `python3 kanban/board.py status` so you know the phases and tickets that already exist.

## Which mode?

| `$ARGUMENTS` / request | Mode |
|---|---|
| an existing ticket id whose status is `draft` | **Finish a draft** (below) |
| a small, already-clear ask ("add a ticket for X") | **Quick ticket** (below) |
| an idea, or empty (ask "What would you like to plan?") | **Full plan**: stages ①–⑥ |

## Conversation rules (all modes)

1. **Plain words first.** Play every idea back as an example of a real person using it.
2. **Show, don't list.** Each stage has a picture: ASCII in a fenced block in the terminal. For
   a big idea, offer a visual HTML page too.
3. **Two views.** Plain by default; technical when the user asks ("show me the technical
   view"). `Plan style: technical` in `SLATE.md` flips the default.
4. **One question at a time**, multiple choice where possible, your recommendation first.
5. **Nothing reaches the board unseen:** phase picture → plain cards → board preview → save.

## Full plan: the six stages (checklist)

Track these as a checklist and do not skip a stage. Move on only when the user agrees.

### ① Story — what, who, success, what's out

Ask, one at a time: who is it for? what can they do afterwards that they can't now? how do we
know it worked? what is deliberately left out? Then play it back as a story:

> **Priya forgets her password.** She clicks "Forgot password", types her email, and a reset
> link arrives within a minute. The link works once, for 30 minutes. She sets a new password
> and is logged straight in. *Out for now:* SMS reset, security questions.

### ② Flow — how it works, as a picture

```
 User                    App                     Email
  │  Forgot password ──▶  │                         │
  │                       │── send reset link ────▶ │
  │  ◀──────── email with link (valid 30 min) ──────│
  │  click link, new pw ─▶│  check link, save pw    │
  │  ◀── logged in ───────│                         │
```

Technical view only on request (or when Plan style is `technical`): components, data, APIs,
risks — still as a picture where possible. Settle open questions here, one at a time.

### ③ Phases — what you can demo after each (vertical slices)

Each phase ends with something a person can see or try, not a layer of code.

```
 Phase 1  "Link arrives"     → type email, reset email shows up in the dev inbox
 Phase 2  "Password changes" → click link, set password, log in with it
 Phase 3  "Safe"             → expired and reused links rejected, rate limit, audit log
```

Reuse an existing phase id from `status` when the work belongs there; new phases need `id`,
`name`, `goal`, `demo`.

### ④ Cards — plain ticket cards

Show every ticket as a plain card before any file is written:

```
┌ reset-request · People can ask for a password reset link ──── Phase 1 · P1 · 1d ┐
│ Summary    Someone who forgot their password can ask for a reset link by email. │
│ Story      Priya clicks "Forgot password", types her email, and gets a link.    │
│ Done when  ☐ The login page has a "Forgot password" link                        │
│            ☐ A reset email arrives for a known email address                    │
│            ☐ An unknown email shows the same message (nobody learns who has one) │
│ Tests      When a known email asks for a reset, then one email is sent          │
│            When an unknown email asks, then no email is sent and the reply matches│
│ Try it     Reset with a known email: open the app → Forgot password → type       │
│            priya@example.com → Send link → you see "Check your email" (required)│
│ Needs      —            Unlocks  set-password                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

Apply the **ticket writing rules** and **field guide** below. Ask the user to change, split,
merge or reorder until they're happy.

### ⑤ Preview — the board shows it before anything is saved

1. Write the batch file (format below) to the session scratchpad directory if one is listed in
   your environment, else to `kanban/.batch.json`.
2. `python3 kanban/board.py batch-check --file <batch>` — fix every error and read every
   warning; re-run until clean.
3. `python3 kanban/board.py add --dry-run --file <batch>` (add `--after <ID>` to place the new
   tickets after an existing one). This prints the ids and ranks they will get and writes
   `kanban/preview.json`.
4. Tell the user how to see it: "Open the board — `cd kanban && python3 -m http.server 8088`,
   then http://localhost:8088 (reload if it's already open). The new tickets have a dashed
   border and a *preview* tag; nothing is saved yet." Show the ids/ranks table too.
5. **Iterate.** Changes ("move the audit log before the rate limit", "split the email ticket",
   "make it P2") are edits to the batch file — ticket order in the file is rank order. Then
   repeat 2–3 so the preview refreshes.

### ⑥ Save — ask, then write

Ask exactly: **"Save as ready tickets, save as drafts (on the board but not ready to work —
finish them later with /slate:plan <ID> or promote), or discard?"**

1. Save the plan doc first (unless discarding): copy `ROOT/templates/plan-doc.md` to
   `docs/plans/<YYYY-MM-DD>-<topic-slug>.md` (today's date; slug from the topic) and fill Story,
   Flow (the picture from ②), Phases (with the demo per phase), Out of scope, Decisions. Make
   sure every ticket in the batch has `"plan_doc": "docs/plans/<same file>.md"`.
2. Then run one of:
   - ready → `python3 kanban/board.py add --file <batch>` (status `backlog`, strict checks)
   - drafts → `python3 kanban/board.py add --as-draft --file <batch>` (status `draft`)
   - discard → `python3 kanban/board.py discard-preview` (and don't keep the plan doc unless the
     user wants it)
3. If `add` refuses, show the errors in plain words, fix the batch, and go back to ⑤ step 2.
4. `python3 kanban/board.py check`. If the brainstorm settled anything project-wide (who
   the users are, a rule every later ticket must follow), add one dated line under
   "Decisions" in `SLATE.md`, and fill "What this project is" if it's still thin. Fill the plan doc's Tickets table with the real ids.
5. Delete the batch file if it is `kanban/.batch.json`. `preview.json` is removed by `add`.
6. Report: tickets saved (id · title · phase · status), the plan doc path, and the next step —
   `/slate:work` for ready tickets, or `/slate:plan <ID>` / `board.py promote <ID>` for drafts.
   Drafts are never picked by `/slate:work`.

## Quick ticket

For a small, clear ask ("add a ticket for dark mode"): skip ①–③, but still show the plain
card (④) and ask before writing. If the user says it isn't ready yet, save it as a draft.

```bash
python3 kanban/board.py new --dry-run --title "…" --summary "…" --phase P1 \
  --story "…" --description "…" --acceptance "…" --acceptance "…" \
  --test "When …, then …" --priority P2 --areas frontend --estimate 1d \
  --user-test-json '{"title":"…","setup":"…","steps":["…"],"expect":"…","required":true}' \
  [--depends ID,…] [--after ID] [--visual "…"] [--technical "…"]
# then the same command without --dry-run
python3 kanban/board.py new --draft --title "…" --summary "…" --phase P1   # not ready yet
python3 kanban/board.py check
```

A quick ticket that grows (several screens, several tickets, open questions) → switch to the
full plan.

## Finish a draft (`/slate:plan <ID>` on a draft)

1. `python3 kanban/board.py show <ID>`; tell the user in plain words what's missing (anything
   not title/summary/phase: story, description, done-when, tests, try-it-yourself, …).
2. Fill the gaps with the user using the same rules, one question at a time; show the full
   plain card.
3. Write the fields: `python3 kanban/board.py edit <ID> story="…" description="…"
   acceptance:='["…","…"]' test_scenarios:='["When …, then …"]' user_tests:='[{…}]'`
   (`key=value` for text, `key:=JSON` for lists and objects; or `--file patch.json` for long ones).
4. Ask: "Mark it ready to work, or keep it as a draft?" → `python3 kanban/board.py promote <ID>`
   on ready. If promote refuses, it lists what's still missing: fill it and retry.
5. `python3 kanban/board.py check`.

## Ticket writing rules (check each card against these)

- [ ] Title and summary say what the **user** gets, not what the code does.
      ("People can reset a forgotten password", not "Add POST /reset endpoint".) Title ≤ 80 chars.
- [ ] No unexplained jargon outside `technical`; if a term is needed, explain it in the same sentence.
- [ ] Every acceptance bullet can be answered yes/no by looking at the product or the tests.
- [ ] Every test scenario reads **"When …, then …"**.
- [ ] Anything a person can see or click (any `areas` value in `meta.user_test_areas`, default
      `frontend`, `ui`) has at least one `user_tests` entry with `"required": true`.
- [ ] Multi-step flows get a `visual`. Technical detail goes in `technical`, which the board collapses.
- [ ] One ticket = one demoable outcome, about a day or two of work; split anything bigger.
- [ ] `depends_on` lists only what truly must come first; order the batch so deps come earlier.

## Field guide (what goes in each field)

| Field | Required | What goes in it |
|---|---|---|
| `key` | batch only | short slug, unique in the batch (`reset-request`); board.py turns it into an id |
| `title` | yes | plain outcome, "People can reset a forgotten password" |
| `summary` | yes | 1–2 sentences: what changes for the user and why it matters |
| `story` | yes | a short example of someone using it ("Priya forgets her password…") |
| `visual` | when useful | markdown with an ASCII flow / screen sketch / before-after in a fenced block |
| `description` | yes | full detail in plain language: what's in, what's out, edge cases, open questions |
| `acceptance` | yes | list of "done when" bullets, each checkable, no jargon |
| `test_scenarios` | yes | list of automated tests, each "When …, then …" |
| `user_tests` | yes if visible | list of `{title, setup, steps[], expect, required}` the user follows by hand |
| `technical` | optional | files likely touched, API/schema notes, risks (collapsed on the board) |
| `plan_doc` | from a plan | `docs/plans/<date>-<topic>.md` |
| `phase` | yes | an existing phase id or one defined in the batch's `phases` |
| `areas` | yes | list from `meta.areas`, e.g. `["frontend"]` |
| `priority` | yes | `P0`–`P3` |
| `depends_on` | yes (may be `[]`) | batch keys or existing ids (`"ACME-009"`) |
| `estimate` | yes | `0.5d`, `1d`, `2d` |
| `labels` | optional | list of short tags |

Never put `id`, `rank`, `status`, `unlocks`, `handoff` or `user_checks` in a batch: board.py
assigns them.

A good user test:

```json
{
  "title": "Reset with a known email",
  "setup": "Start the app (see SLATE.md, Live test) and open http://localhost:3000.",
  "steps": ["Click 'Forgot password'", "Type priya@example.com", "Click 'Send link'"],
  "expect": "You see 'Check your email' and a reset email appears in the dev inbox.",
  "required": true
}
```

## Batch file format

```json
{
  "phases": [
    { "id": "P1", "name": "Link arrives", "goal": "People can ask for a reset link",
      "demo": "Type your email; the reset email shows up in the dev inbox" }
  ],
  "tickets": [
    { "key": "reset-request", "title": "People can ask for a password reset link",
      "summary": "…", "story": "…", "visual": "```\n…\n```", "description": "…",
      "acceptance": ["…"], "test_scenarios": ["When …, then …"],
      "user_tests": [{ "title": "…", "setup": "…", "steps": ["…"], "expect": "…", "required": true }],
      "technical": "…", "plan_doc": "docs/plans/2026-09-26-password-reset.md",
      "phase": "P1", "areas": ["frontend", "backend"], "priority": "P1",
      "depends_on": [], "estimate": "1d", "labels": [] },
    { "key": "set-password", "title": "People can set a new password from the link",
      "phase": "P2", "depends_on": ["reset-request"], "…": "…" }
  ]
}
```

`phases` holds only **new** phases; leave it out (or `[]`) when all tickets use existing ones.

## Before you finish

- [ ] The user saw the phase picture, every card, and the board preview before anything was saved
- [ ] Every write went through `board.py`; `check` passes
- [ ] Plan doc saved and linked from each ticket's `plan_doc` (full plans)
- [ ] No `kanban/.batch.json` or stale `kanban/preview.json` left behind
