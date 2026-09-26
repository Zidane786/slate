---
name: plan
description: Brainstorm an idea into plain-language tickets on the Slate kanban board - story, flow picture, phases, plain cards, a board preview, then save as ready tickets or drafts. Also adds a single quick ticket, a bug ticket for a problem found in other work, a someday idea in an unscheduled phase, finishes a draft, or tidies phases (rename, reorder, remove). Use when asked to plan a feature, "add a ticket for X", "log a bug", break an idea into tickets, or finish a draft.
argument-hint: "[idea | ticket ID]"
allowed-tools: Bash(python3 kanban/board.py *), Bash(python kanban/board.py *), Bash(py -3 kanban/board.py *)
---

# /slate:plan [idea | ID] — brainstorm into tickets

Turn an idea into tickets that someone who doesn't write code can read and understand, and
show every one before it is saved. Every board read and write is a `python3 kanban/board.py …`
call from the repo root (use the command from `SLATE.md` "Python: `…`" instead of `python3`
when it names another, e.g. `py -3`). **Never edit `kanban/tickets.json` directly** (a hook
blocks it) and don't read it directly either: use `status`, `show`, `export --json`. The only
JSON you write by hand is the batch file. Every command, flag and "use it when" is in
`<ROOT>/reference/commands.md`.

This skill also looks after the board's **shape**: phases, states (columns), workflow rules,
priorities, and removing or restoring tickets. Always ask before removing tickets or states,
and show the change as a picture first. A hand edit of `tickets.json` is never part of
planning: if one ever seems needed, stop and use `/slate:sync` (it explains the supervised
`unlock`: Claude Code's approval card in Manual / Accept edits / Auto mode, or the user types a
code in their own terminal in Plan / Bypass / Don't-ask mode; one unlock = one edit).

## Step 0: version check, board server and context

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code). If it still reads literally,
   use this skill's base directory (printed when the skill loads) + `/../..`, made absolute.
2. If `kanban/board.py` is missing: say "This repo isn't set up for Slate yet — run
   `/slate:init` first." and stop.
3. Read `SLATE.md` (prefix, **Plan style**, Python command, Board server / Board port,
   `## Workflow`, docs map). If it is missing, fall back to `CLAUDE.md` / `AGENTS.md` / docs and
   suggest re-running `/slate:init`.
4. `python3 kanban/board.py version --against "<ROOT>"`
   - `same` → say nothing.
   - `behind` → "This project's board is Slate <board>, the plugin is <plugin>. Upgrade now
     with `/slate:upgrade`?" Ask once, then continue either way (never run it yourself).
   - `ahead` → a teammate upgraded this board: offer to update it for them: "Your Slate plugin is older than this board (a teammate upgraded). Update it now? I'll run `claude plugin marketplace update slate` and `claude plugin update slate@slate`." On yes, run both, then ask the user to run `/reload-plugins` (or restart Claude Code) and invoke this command again. On no, stop.
5. **Board server.** Unless `SLATE.md` says `Board server: off`:
   `python3 kanban/board.py serve --ensure --port <Board port from SLATE.md, default 8088>`.
   It reuses a running server or starts one, never two. Show the URL it prints **once** in this
   conversation ("Live board: <url>"); over SSH add "From your machine:
   `ssh -L <port>:localhost:<port> <host>`, then open the URL." If `serve` isn't in
   `python3 kanban/board.py --help` (an older board), skip this and use `cd kanban && python3 -m http.server
   8088` in ⑤ (a view-only board).
6. `python3 kanban/board.py status` (phases, tickets, workflow mode) and
   `python3 kanban/board.py export --json --statuses` (state names, labels, roles, rules), so
   you know what exists. Talk about states by their **label** (column title).
7. If any board.py command prints a board-of-record warning, stop and ask before writing
   (see `/slate:sync`).

## Which mode?

| `$ARGUMENTS` / request | Mode |
|---|---|
| an existing ticket id whose status has the draft role | **Finish a draft** (below) |
| a small, already-clear ask ("add a ticket for X") | **Quick ticket** (below) |
| a bug found in existing work ("ACME-004 crashes when …") | **Bug ticket** (below) |
| "someday", "later", "park this idea" | **Someday idea** (below) |
| change several tickets at once, add a note, change priorities | **Edit tickets** (below) |
| drop / delete / bring back a ticket | **Remove or restore** (below) |
| rename / reorder / remove / change a phase | **Phases** (below) |
| "add a QA column", rename or remove a column | **States** (below) |
| "tickets must go through review", "make the workflow strict", "why can't I move X" | **Workflow rules** (below) |
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
4. Tell the user how to see it: "Open the board at <the URL from step 0> (it refreshes by
   itself). The new tickets have a dashed border and a *preview* tag; nothing is saved yet."
   With `Board server: off`: `python3 kanban/board.py serve --port <Board port>` in a terminal,
   or `cd kanban && python3 -m http.server 8088` for a view-only board. Show the ids/ranks table
   too.
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

Repeat a flag to add more (`--acceptance`, `--test`, `--user-test-json`, `--labels`, `--areas`,
`--depends` all add up). `--labels`, `--areas` and `--depends` also take comma lists;
acceptance and test sentences never split on commas.

A quick ticket that grows (several screens, several tickets, open questions) → switch to the
full plan.

## Bug ticket

A bug found while building or testing another ticket gets its own ticket, so the fix is
visible and the broken ticket waits for it.

1. Play the bug back in plain words: what the person did, what they expected, what happened.
   Show it as a plain card (④) like any other ticket: the summary says what goes wrong for the
   user; acceptance says what "fixed" looks like; one "When …, then …" test that fails today.
2. Ask before writing, then:

   ```bash
   python3 kanban/board.py new --bug --fixes ACME-004 --dry-run --title "…" --summary "…" \
     --phase P2 --story "…" --description "…" --acceptance "…" --test "When …, then …" \
     --priority P1 --areas backend --estimate 0.5d
   # then the same without --dry-run
   ```

   board.py adds the labels `bug` and `fixes-ACME-004`, makes ACME-004 wait for the new ticket,
   and ranks it just before ACME-004. Several tickets: `--fixes ACME-004,ACME-006`.
3. If a fixed ticket is already `done` or `merge_ready`, board.py refuses with `ask the user:`.
   Ask: "ACME-004 is already <status>. Reopen it (back to in progress) so it waits for the
   fix?" Only on a yes, run the command again with `--reopen`. On a no, drop `--fixes` for
   that ticket and mention it in the description instead.
4. `python3 kanban/board.py check`.

## Someday idea

An idea worth keeping that nobody should build yet goes in an **unscheduled** phase (the
board shows it last and folded; `next`, `list` and `/slate:work` skip it).

- If there's no unscheduled phase yet, ask first, then:
  `python3 kanban/board.py add-phase --id BACKLOG --name "Someday" --goal "Ideas we may build later" --demo "Nothing yet" --unscheduled`
  (then refresh `SLATE.md`'s Workflow section, below).
- Save the idea there as a draft (it can be thin):
  `python3 kanban/board.py new --draft --phase BACKLOG --title "…" --summary "…"`
- When the user wants to build it: finish it (below) and move it,
  `python3 kanban/board.py edit <ID> phase=P3`, then `promote` if it was a draft.

## Phases

Change phases only through board.py, and only after the user agrees:

```bash
python3 kanban/board.py edit-phase P2 name="Password changes" goal="…" demo="…"
python3 kanban/board.py edit-phase BACKLOG unscheduled:=true      # or false to schedule it
python3 kanban/board.py rename-phase P2 P2a                      # tickets move with it
python3 kanban/board.py remove-phase P4 --move-to P3             # refuses while tickets use it, unless --move-to
python3 kanban/board.py reorder-phases P1 P3 P2 BACKLOG          # list every phase once; this is display order
```

Show the phase picture (③) before and after, and ask before removing one. After any phase
change, refresh `SLATE.md` (see **Keep SLATE.md's Workflow in step** below).

## Edit tickets (several at once, notes, priorities)

- **Several tickets, one change** (all or nothing: if one is refused, none changes). Show the
  list of tickets and the change, ask, then:

  ```bash
  python3 kanban/board.py edit ACME-004,ACME-005,ACME-006 phase=P3
  python3 kanban/board.py edit ACME-007,ACME-008 priority=P1 --rerank
  ```

- **A note on the ticket's history** without changing anything else ("waiting on legal",
  "decided to keep SMS out"): `python3 kanban/board.py note ACME-004 "…"` (`ID1,ID2` for several).
- **Priorities.** The list lives in `meta.priorities` (default `P0 P1 P2 P3`). To change it,
  show old → new, ask, then
  `python3 kanban/board.py set-meta priorities:='["Must","Should","Could"]'`. board.py refuses
  while a ticket still uses a dropped priority and prints the `edit` that moves those tickets
  first: show that list to the user before running it.

## Remove or restore

Tickets are never deleted: `remove` archives them in `meta.removed` (ids are never reused) and
`restore` brings them back.

1. `python3 kanban/board.py show <ID>` for each; tell the user in plain words what goes and what
   depends on it ("ACME-012 waits for it").
2. **Ask first:** "Remove ACME-011 and ACME-012 (archived, can be restored)? Why?" Only on a yes:

   ```bash
   python3 kanban/board.py remove ACME-011,ACME-012 --reason "<the user's reason>"
   python3 kanban/board.py remove ACME-011 --reason "…" --detach          # also drop it from other tickets' depends_on
   python3 kanban/board.py remove ACME-003 --reason "…" --force-done "…"  # a done ticket: only when the user insists
   ```

   Refused because other tickets depend on it → show them and ask: `--detach` (they stop
   waiting for it), or remove them too, or keep it.
3. See archived tickets: `python3 kanban/board.py export --json --removed`. Bring one back:
   `python3 kanban/board.py restore ACME-011` (with the user's OK).

## States (columns)

Every state has a **role** (`draft backlog ready in_progress review user_testing merge_ready
done`); Slate's rules follow the role, so a renamed or added state behaves like its role. A
done-role and a backlog- or ready-role state must always remain. Show the columns before and
after as a picture, and ask before every change (removing a state needs an explicit yes):

```
 now:   Draft │ Backlog │ Ready │ In progress │ Review │ User testing │ Waiting for merge │ Done
 after: Draft │ Backlog │ Ready │ In progress │ Review │ QA │ User testing │ Waiting for merge │ Done
                                                         ▲ new, works like Review
```

```bash
python3 kanban/board.py add-status qa --after review --like review --label "QA" --note required   # --first to put it first
python3 kanban/board.py edit-status in_progress label="Doing"                     # column title only
python3 kanban/board.py edit-status qa role=user_testing                          # change what it behaves like
python3 kanban/board.py edit-status review note=optional                          # moving here no longer needs a note
python3 kanban/board.py rename-status qa quality_check                            # tickets move with it
python3 kanban/board.py reorder-statuses draft backlog ready in_progress review qa user_testing merge_ready done
python3 kanban/board.py remove-status qa --move-to review                         # refuses while tickets are in it, unless --move-to
```

`--like` takes a role or an existing state. When adding a state, also ask: **"Should moving a
ticket into <label> need a note for the ticket's history (what was done, what to check)?
(a) yes (b) no"** — recommend the `--like` state's setting (by default Review, User testing,
Waiting for merge and Done need one; the others don't) and pass `--note required|optional`.
The same question changes an existing state: `edit-status <name> note=required|optional`.
Moving back while workflow rules exist always needs a note. Then refresh `SLATE.md` (below).

## Workflow rules

By default any move is allowed (workflow `free`). Rules say which states may come right before
a state (`from`); board.py then refuses a forward move that skips a step and prints the next
allowed step. Moving back always works (with a note).

1. Show the current path as a picture from `export --json --statuses`, then the proposed one:

   ```
   strict:  Backlog/Ready ─▶ In progress ─▶ Review ─▶ User testing ─▶ Waiting for merge ─▶ Done
                                              └───────────────────────▶┘ (no user test needed)
   ```

2. Recommend from how the team works, one question at a time (does every change get
   reviewed? is there a QA step? do users test by hand? who merges?). Asked "what do we actually
   do?": `python3 kanban/board.py flow` shows the moves tickets really made, with counts — turn
   that into a plain recommendation ("your tickets nearly always go Review → User testing →
   Waiting for merge → Done; lock that in? 2 skipped Review — keep that possible?").
3. Apply only on a yes:

   ```bash
   python3 kanban/board.py set-meta workflow=strict            # the usual path (skips states the board lacks)
   python3 kanban/board.py edit-status qa from=review          # one rule: QA only right after Review
   python3 kanban/board.py edit-status merge_ready from=qa,user_testing
   python3 kanban/board.py edit-status qa from=                # clear one rule
   python3 kanban/board.py set-meta workflow=free              # remove every rule
   ```

4. "Why can't I move X?" → run the move with `set` and read the refusal: it names the allowed
   previous states and the next allowed step. Explain it in plain words; change the rule only if
   the user wants to.

## Keep SLATE.md's Workflow in step

After any change to states, rules or phases (and after adding a `BACKLOG` phase), `SLATE.md`'s
`## Workflow` section must match the board, because every agent reads it. Ask "Update SLATE.md's
Workflow section to match?" and on a yes run:

```bash
python3 kanban/board.py workflow --markdown
```

and replace the **whole** `## Workflow` section (from its heading to the next `##` heading) with
that output; it includes the heading. Add nothing inside it: `doctor` compares it with the board
word for word and reports `slate-md-workflow-stale` otherwise. Project notes (who merges PRs, why
a rule exists) go under "Rules" or "Decisions". If `workflow` isn't in
`python3 kanban/board.py --help` (an older board), write the section by hand from
`export --json --statuses`.

## Finish a draft (`/slate:plan <ID>` on a draft)

1. `python3 kanban/board.py show <ID>`; tell the user in plain words what's missing (anything
   not title/summary/phase: story, description, done-when, tests, try-it-yourself, …).
2. Fill the gaps with the user using the same rules, one question at a time; show the full
   plain card.
3. Write the fields: `python3 kanban/board.py edit <ID> story="…" description="…"
   acceptance:='["…","…"]' test_scenarios:='["When …, then …"]' user_tests:='[{…}]'`
   (`key=value` for text, `key:=JSON` for lists and objects; or `--file patch.json` for long ones).
   To add to a text field instead of replacing it, use `+=`:
   `python3 kanban/board.py edit <ID> description+="Also: …"` (works for `description`,
   `technical`, `story`, `summary`, `visual`; a blank line goes between). After changing
   `depends_on`, add `--rerank` so the ticket moves after its dependencies if needed.
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
| `priority` | yes | one of `meta.priorities` (default `P0`–`P3`) |
| `depends_on` | yes (may be `[]`) | batch keys or existing ids (`"ACME-009"`) |
| `estimate` | yes | `0.5d`, `1d`, `2d` |
| `labels` | optional | list of short tags (`bug` and `fixes-<ID>` come from `new --bug --fixes`) |

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

- [ ] Every status move you made (`set`, `promote`, bulk `set`) carried a short note for the ticket's history (`--handoff "…"`), even where the state doesn't require one.

- [ ] The user saw the phase picture, every card, and the board preview before anything was saved
- [ ] Every write went through `board.py`; `check` passes
- [ ] Plan doc saved and linked from each ticket's `plan_doc` (full plans)
- [ ] No `kanban/.batch.json` or stale `kanban/preview.json` left behind
- [ ] Nothing removed (tickets or states) without the user's explicit yes
- [ ] States, rules or phases changed → `SLATE.md` `## Workflow` updated (with the user's OK)
