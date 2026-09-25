---
name: work
description: Build ONE Slate ticket end to end, with the user in charge - the ticket the user names, or the next ready one after the user confirms it, implement with tests first, lint + full tests + live test, review agent, fix, ask the user to try it when it changes something visible, commit and draft PR when a remote exists (both recorded on the ticket), then write the handoff, close it and stop. Never continues to another ticket unless the user explicitly says so. Use when asked to "work the next ticket", "start ACME-014", or "keep building".
argument-hint: "[ticket ID]"
allowed-tools: Bash(python3 kanban/board.py *)
---

# /slate:work [ID] — the build loop

Follow these steps in order. Do not skip or reorder them. Announce each step in one line.

**The user is always in charge.** This skill works on exactly one ticket per request:

- The user named a ticket → that is the go-ahead: start it without asking again, and work
  that ticket only.
- No ticket named → show the next ticket (id, title, summary) and ask "Start <ID>?" Begin only
  on a yes.
- When the ticket is closed (or stopped), report and **stop**. Do not start the next ticket,
  even if one is ready, unless the user explicitly asked for more ("keep going", "do the next
  3", "work through phase P1"). Then do exactly that much and stop again.
- Never run through the whole board on your own initiative.
Every board read and write is a `python3 kanban/board.py …` call from the repo root; **never
edit `kanban/tickets.json` directly** (a hook blocks it).

```
 pick ─▶ in_progress ─▶ implement (tests first) ─▶ lint + full tests + live test
   ▲                                                         │
   │                                                         ▼
 next ◀── done ◀── user says pass ◀── user_testing ◀── review agent, fix findings
                    (only if the ticket has required user tests; else review ─▶ done)
```

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
     (`claude plugin marketplace update slate`, `claude plugin update slate@slate`, restart)."
     Stop: this skill writes to the board, and writes wait until the plugin is updated.
4. Read `SLATE.md`: commands (lint/test/types), Live test, Extra review checks, Stop and ask
   before, Docs map, Rules (branch pattern). If it is missing, fall back to `CLAUDE.md` /
   `AGENTS.md` / docs for the same things and suggest re-running `/slate:init`.
5. `python3 kanban/board.py check`. If it fails, show the errors and stop: nothing can be
   written until the board is valid.

## Step 1: pick

- [ ] `$ARGUMENTS` names a ticket → use it and go on (no confirmation needed). Otherwise run `python3 kanban/board.py next`
      (it lists `in_progress` / `review` / `user_testing` tickets to resume before new work),
      show the user what it suggests, and ask "Start <ID>?" (or "Resume <ID>?"). Wait for a yes.
- [ ] **Drafts are never picked.** If the named ticket's status is `draft`, say: "<ID> is a
      draft — not finished enough to build. Finish it first with `/slate:plan <ID>`?" and stop.
- [ ] `python3 kanban/board.py show <ID>`. If any dependency isn't `done`, stop and say which
      ones block it (and offer the next ready ticket instead; start it only if the user says so).
- [ ] Resuming? Read the ticket's history (handoff log) and pick up where it says. A ticket in
      `user_testing` goes straight to step 5; one in `review` to step 4.
- [ ] New ticket → `python3 kanban/board.py set <ID> in_progress`.
- [ ] Read the ticket fully, its `plan_doc`, the docs-map entries it touches, and the code it
      touches. If the ticket conflicts with the docs, the docs win; note the fix in the handoff.
      If it is still unclear, or it hits a "Stop and ask before" rule, ask the user before coding.

## Step 2: implement

- [ ] If git exists: create the branch from the default branch using the pattern in `SLATE.md`
      (default `slate/<id-lowercase>-<short-slug>`, e.g. `slate/acme-014-password-reset`).
      Reuse it when resuming.
- [ ] Write the tests from `test_scenarios` **first** (one test per "When …, then …"), watch
      them fail, then write the code.
- [ ] Stay inside the ticket's scope. Adjacent work you notice goes in the handoff as a
      follow-up (or `/slate:plan` a new ticket, with the user's OK) — never done silently.

## Step 3: test

- [ ] Run the lint, type-check and test commands from `SLATE.md` — the **full** suite, not only
      the new tests. Fix failures.
- [ ] **Live test whenever possible**, as `SLATE.md` "Live test" says: start the app and use the
      feature (curl the endpoint, run the CLI, load the page and click through). Stop anything
      you started afterwards.
- [ ] Record exactly what you ran and saw. If a live test is impossible here, say so and why.

## Step 4: review

- [ ] `python3 kanban/board.py set <ID> review --handoff "Built <what>; tests <result>; live test <result>."`
- [ ] Dispatch a review subagent (the `code-review` skill if available, else an Agent such as
      `feature-dev:code-reviewer` or a general-purpose agent) on the diff
      (`git diff <default-branch>...HEAD` plus uncommitted changes). Paste the ticket's
      acceptance and test_scenarios verbatim and this brief:
  1. **Bugs and logic errors:** error handling, edge cases, async misuse, resource leaks.
  2. **Security basics:** secrets in code, logs or commits; injection into shell/SQL/HTML;
     path escapes; missing auth or input validation.
  3. **Scope:** every acceptance bullet met; every test scenario has a test; nothing outside
     the ticket changed without a note.
  4. **Blast radius:** callers of changed functions, data/migrations against existing rows,
     config and build still valid, full suite still passes.
  5. **Project checks:** every item under "Extra review checks" in `SLATE.md`.
- [ ] Fix every confirmed finding; re-run step 3; re-review if a fix was non-trivial. List
      dismissed findings and why.

## Step 5: user testing (only if the ticket has a `required` user test)

Skip to step 6 if the ticket has no user test marked `required`.

- [ ] `python3 kanban/board.py set <ID> user_testing --handoff "Ready for you to try. Start the app: <exact command>, then open <url>."`
- [ ] Start the app for the user if you can (per `SLATE.md` Live test) and tell them it's running.
- [ ] Print each user test in plain words, numbered, exactly like this:

  ```
  Please try this yourself (ACME-014, test 1 of 2): Reset with a known email
  Setup:  <setup>
    1. <step>
    2. <step>
  You should see: <expect>
  Did it work? (pass / fail + what you saw)
  ```

- [ ] Record each answer as it comes: `python3 kanban/board.py usertest <ID> <index> pass`
      or `… fail --note "<what the user saw>"` (index = position in `user_tests`, from 0).
- [ ] **Fail** → board.py moves the ticket back to `in_progress` with the note. Go back to
      step 2 with the user's note as the bug report, then through steps 3–5 again.
- [ ] **Then wait.** Don't start other tickets while the user is testing. If the user would
      rather test later, leave the ticket in `user_testing` (its handoff says how to start the
      app) and stop; `/slate:status` and the board show it as "needs you".
- [ ] Continue to step 6 only when every required user test has a `pass`.

## Step 6: update SLATE.md, commit, push, draft PR — and record them on the ticket

- [ ] **Update `SLATE.md`** if this ticket taught something the next ticket needs: a
      project-wide decision → one line under "Decisions"; a gotcha, setup quirk or new command →
      one line under "Learned along the way" (or fix the Commands / Live test line if it was
      wrong). Keep lines short and dated; don't copy what CLAUDE.md or the docs already say.
- [ ] If git exists: commit on the ticket branch (code, tests, `SLATE.md`, and the board
      files changed so far), message `<ID>: <what changed>` with a body listing the
      verification (tests, live test, user tests).
- [ ] **Record the commit on the ticket:** `python3 kanban/board.py link <ID> --commit HEAD`
      right after each **code** commit (e.g. again after review fixes). Link only commits that
      contain the ticket's work — never the board-bookkeeping commit. Leave the resulting
      `kanban/tickets.json` change uncommitted for now; it goes in with the close-out commit
      in step 7.
- [ ] Only if `git remote -v` shows a remote: push the branch and open a **draft** PR/MR titled
      `<ID> <title>` whose body has: summary, ticket id, acceptance checklist, verification,
      blast-radius notes, follow-ups. **Never merge.**
- [ ] **Record the PR on the ticket:** `python3 kanban/board.py link <ID> --pr <url> --pr-state draft`.
      When you later learn it was merged or closed, update it with `--pr-state merged|closed`.
- [ ] No remote: commit locally, record the commit, and say so in the handoff. board.py only
      asks for a PR when the repo has a remote, so **don't pass `--no-pr`** here. No git: skip
      and say so.

## Step 7: close

- [ ] `python3 kanban/board.py set <ID> done --handoff "<built>; <decisions/deviations>; <verified: tests, live test, user tests>; <follow-ups>"`
      board.py refuses `done` when a required user test has no `pass` (go back to step 5), when
      no commit is linked, or when the repo has a remote and no PR is linked (go back to step 6).
      When it refuses, fix what it names: link the missing commit/PR (the error prints the exact
      `link` command) and run `set … done` again. Only for a ticket that truly changed no code
      (or where a PR isn't wanted) use `--no-code "<why>"` / `--no-pr "<why>"` — and **only after
      the user agrees**; ask "NOTE-014 changed no code because <why>. Close it without a
      commit?" first.
- [ ] `python3 kanban/board.py check`
- [ ] Commit the board update (linked commits, status, handoff) as one bookkeeping commit on
      the ticket branch: `git add kanban/tickets.json && git commit -m "<ID>: close on board"`
      (don't link this one), and push it if the branch is pushed.
- [ ] Report: what was built, what was verified, commits and PR link, and what the next ready
      ticket would be (`python3 kanban/board.py next`) — **as a suggestion only**. Then stop.
      Go back to step 1 only if the user explicitly asked for more work in this request.

## Rules that always hold

- Never leave a ticket `in_progress` at the end of a session without a handoff note:
  `python3 kanban/board.py set <ID> in_progress --handoff "Stopped at <where>; next <what>."`
  (if board.py refuses, tell the user exactly where you stopped).
- Obey "Stop and ask before" in `SLATE.md`: when blocked, do everything that doesn't depend on
  the answer, write the question into the handoff, and stop to ask. Don't switch to another
  ticket unless the user says so.
- One ticket per request unless the user explicitly asks for more. Human in the loop, always.
- Draft PRs only, never merge, never force-push.
