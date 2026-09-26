---
name: work
description: Build ONE Slate ticket end to end, with the user in charge - the ticket the user names, or the next ready one after the user confirms it, implement with tests first (ticking each check on the board as it passes), lint + full tests + live test, review agent, fix, ask the user to try it when it changes something visible, commit and draft PR when a remote exists (both recorded on the ticket), move it to Waiting for merge and stop; close it as done only after the user says the PR is merged. Never continues to another ticket unless the user explicitly says so. Use when asked to "work the next ticket", "start ACME-014", or "keep building".
argument-hint: "[ticket ID]"
allowed-tools: Bash(python3 kanban/board.py *), Bash(python kanban/board.py *), Bash(py -3 kanban/board.py *)
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

Every board read and write is a `python3 kanban/board.py …` call from the repo root (use the
command from `SLATE.md` "Python: `…`" instead of `python3` when it names another, e.g.
`py -3`). **Never edit `kanban/tickets.json` directly** (a hook blocks it) and never read it
directly either: use `show`, `export --json`, `list --json`, `status --json`. Every command,
flag and "use it when" is in `<ROOT>/reference/commands.md`; read it when a command below
isn't enough.

**Speak in roles, not names.** The steps below name statuses by their **role**:
`in_progress`, `review`, `user_testing`, `merge_ready`, `done`. A project may have renamed a
status ("Doing") or added its own (a "qa" column with the review role). In step 0 you look up
the status name for each role and use that name in every `set` command, and the label (column
title) when you talk to the user.

```
 pick ─▶ branch ─▶ in_progress (claims it) ─▶ implement (tests first, tick items)
                                                      │
                                                      ▼
 user_testing (only with required user tests) ◀── lint + full tests + live test ◀── review + fixes
      │ user says pass
      ▼
 commit + PR linked ─▶ merge_ready ("Waiting for merge") ─▶ STOP
                                   │ later: user says "the PR is merged"
                                   ▼
                     link --pr-state merged ─▶ done ─▶ STOP
```

## Step 0: version check, board server and context

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code). If it still reads literally,
   use this skill's base directory (printed when the skill loads) + `/../..`, made absolute.
2. If `kanban/board.py` is missing: say "This repo isn't set up for Slate yet — run
   `/slate:init` first." and stop.
3. Read `SLATE.md`: Python command, Board server / Board port, `## Workflow` (states, rules,
   who merges, board of record), commands (lint/test/types), Live test, Extra review checks,
   Stop and ask before, Docs map, Rules (branch pattern). If it is missing, fall back to
   `CLAUDE.md` / `AGENTS.md` / docs for the same things and suggest re-running `/slate:init`.
4. `python3 kanban/board.py version --against "<ROOT>"`
   - `same` → say nothing.
   - `behind` → "This project's board is Slate <board>, the plugin is <plugin>. Upgrade now
     with `/slate:upgrade`?" Ask once, then continue either way (never run it yourself).
   - `ahead` → a teammate upgraded this board: offer to update it for them: "Your Slate plugin is older than this board (a teammate upgraded). Update it now? I'll run `claude plugin marketplace update slate` and `claude plugin update slate@slate`." On yes, run both, then ask the user to run `/reload-plugins` (or restart Claude Code) and invoke this command again. On no, stop.
5. **Board server.** Unless `SLATE.md` says `Board server: off`:
   `python3 kanban/board.py serve --ensure --port <Board port from SLATE.md, default 8088>`.
   It reuses a running server or starts one in the background, never two. Show the URL it
   prints **once** in this conversation: "Live board: <url> (clicks there save to the board)."
   Working over SSH? Add: "From your machine: `ssh -L <port>:localhost:<port> <host>`, then open
   the URL." If `serve` isn't in `python3 kanban/board.py --help` (an older board), skip this.
6. `python3 kanban/board.py check`. If it fails, show the errors and stop: nothing can be
   written until the board is valid (`/slate:sync` repairs boards).
7. `python3 kanban/board.py export --json --statuses` → the status **name** and **label** for
   each role, and the workflow (`free`, `strict` or custom path rules). No status with the
   `merge_ready` role → step 7 goes straight to `done`; none with `user_testing` → step 5 records
   user tests without moving the ticket.
8. **Board of record.** If any board.py command prints a warning that this is not the board of
   record (a secondary git worktree, `SLATE_BOARD_OF_RECORD` points elsewhere, or the default
   branch's board has tickets or notes this one lacks), **stop and ask the user** before writing
   anything more. Show the warning and its `fix:` lines (`diff <ref>` to look, `sync --from
   <ref>` to bring changes across) and let the user choose, or suggest `/slate:sync`. Never sync
   on your own.

## Step 1: pick

- [ ] `$ARGUMENTS` names a ticket → use it and go on (no confirmation needed). Otherwise run
      `python3 kanban/board.py next` (it lists tickets to resume before new work, and
      merge_ready ones under "Waiting for merge"; those are not work to resume, only a question
      for the user), show the user what it suggests, and ask "Start <ID>?" (or "Resume <ID>?").
      Wait for a yes.
- [ ] **Drafts are never picked.** If the named ticket has the draft role, say: "<ID> is a
      draft — not finished enough to build. Finish it first with `/slate:plan <ID>`?" and stop.
- [ ] **Unscheduled tickets are never picked.** If the ticket's phase is unscheduled (`show`
      says so), say "<ID> is in an unscheduled phase. Move it to <phase> first?" and, on a yes,
      `python3 kanban/board.py edit <ID> phase=<scheduled phase>`.
- [ ] **Claims.** `show <ID>` names who holds it ("on: <name>"). Claimed by another branch or
      agent → **don't touch it**: say "<ID> is being worked on by <name> since <time>." and offer
      the next ticket. Only if the user explicitly says to take it over, pass
      `--take-over "<the user's reason>"` on the `set` / `claim` below. Claimed by you (your
      branch) → resume it.
- [ ] `python3 kanban/board.py show <ID>`. If any dependency isn't done, stop and say which
      ones block it (and offer the next ready ticket instead; start it only if the user says so).
      Only if the user explicitly says to start anyway, add
      `--ignore-deps "<the user's reason>"` to the `set` below.
- [ ] Resuming? Read the ticket's history (handoff log and notes) and pick up where it says. A
      ticket with the user_testing role goes straight to step 5; review → step 4; merge_ready →
      step 8 (ask whether the PR is merged). Check out its branch (the claim and linked commits
      name it).
- [ ] **New ticket: branch first, then claim.** If git exists, create the ticket branch from the
      default branch using the pattern in `SLATE.md` (default `slate/<id-lowercase>-<short-slug>`,
      e.g. `slate/acme-014-password-reset`) and switch to it **before** moving the ticket, because
      `set … in_progress` records the current branch as the claim. Then
      `python3 kanban/board.py set <ID> <in_progress name>`.
- [ ] Read the ticket fully, its `plan_doc`, the docs-map entries it touches, and the code it
      touches. If the ticket conflicts with the docs, the docs win; note the fix in the handoff.
      If it is still unclear, or it hits a "Stop and ask before" rule, ask the user before coding.

## Step 2: implement

- [ ] Write the tests from `test_scenarios` **first** (one test per "When …, then …"), watch
      them fail, then write the code.
- [ ] **Tick items on the board as they are proven**, not all at the end. When the test for
      scenario N passes: `python3 kanban/board.py check-item <ID> test <N> --evidence "<test name>"`.
      When a "Done when" bullet is met and you've seen it (test, live test, output):
      `python3 kanban/board.py check-item <ID> acceptance <N> --evidence "<how you know>"`.
      Indexes start at 0. If a later change breaks one, `uncheck-item <ID> test <N>`.
- [ ] Waiting on something (an answer, a teammate, a service)? Record it without changing the
      status: `python3 kanban/board.py note <ID> "Waiting on <what> since <when>."`
- [ ] Stay inside the ticket's scope. Adjacent work you notice goes in the handoff as a
      follow-up (or `/slate:plan` a new ticket or bug ticket, with the user's OK) — never done
      silently.

## Step 3: test

- [ ] Run the lint, type-check and test commands from `SLATE.md` — the **full** suite, not only
      the new tests. Fix failures.
- [ ] **Live test whenever possible**, as `SLATE.md` "Live test" says: start the app and use the
      feature (curl the endpoint, run the CLI, load the page and click through). Stop anything
      you started afterwards.
- [ ] Record exactly what you ran and saw. If a live test is impossible here, say so and why.
- [ ] `python3 kanban/board.py show <ID>`: every item you proved shows `[x]` with its evidence.

## Step 4: review

- [ ] `python3 kanban/board.py set <ID> <review name> --handoff "Built <what>; tests <result>; live test <result>."`
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
- [ ] The project has more review-role states (e.g. "QA")? Move through them in column order
      as `SLATE.md` `## Workflow` describes. Always pass `--handoff "…"` (a note for the ticket's
      history); board.py requires one for every state marked "note required".

## Step 5: user testing (only if the ticket has a `required` user test)

Skip to step 6 if the ticket has no user test marked `required`.

- [ ] `python3 kanban/board.py set <ID> <user_testing name> --handoff "Ready for you to try. Start the app: <exact command>, then open <url>."`
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

  With the live board running they can also click Pass / Fail in the ticket drawer; that saves
  to the board just like your command (check with `show <ID>`).
- [ ] Record each answer as it comes: `python3 kanban/board.py usertest <ID> <index> pass`
      or `… fail --note "<what the user saw>"` (index = position in `user_tests`, from 0).
      Recorded the wrong result? `python3 kanban/board.py usertest <ID> <index> reset`, then
      record the right one.
- [ ] **Fail** → board.py moves the ticket back to in progress with the note. Go back to
      step 2 with the user's note as the bug report, then through steps 3–5 again.
- [ ] **Then wait.** Don't start other tickets while the user is testing. If the user would
      rather test later, leave the ticket in user testing (its handoff says how to start the
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
      contain the ticket's work — never the board-bookkeeping commit. Linked the wrong one?
      `python3 kanban/board.py unlink <ID> --commit <sha prefix> --reason "<why>"`. Leave the
      resulting `kanban/tickets.json` change uncommitted for now; it goes in with the
      bookkeeping commit in step 7.
- [ ] Only if `git remote -v` shows a remote: push the branch and open a **draft** PR/MR titled
      `<ID> <title>` whose body has: summary, ticket id, acceptance checklist, verification,
      blast-radius notes, follow-ups. **Never merge.**
- [ ] **Record the PR on the ticket:** `python3 kanban/board.py link <ID> --pr <url> --pr-state draft`.
      One PR covers several tickets (stacked or combined work)? Link them all at once:
      `python3 kanban/board.py link <ID1>,<ID2> --pr <url> --pr-state draft` (all or nothing).
      Wrong PR? `python3 kanban/board.py unlink <ID> --pr --reason "<why>"`.
- [ ] No remote: commit locally, record the commit, and say so in the handoff. board.py only
      asks for a PR when the repo has a remote, so **don't pass `--no-pr`** here. No git: skip
      and say so.

## Step 7: waiting for merge — then stop

- [ ] `python3 kanban/board.py set <ID> <merge_ready name> --handoff "<built>; <decisions/deviations>; <verified: tests, live test, user tests>; PR <url or 'local branch <name>'>; <follow-ups>"`
      board.py refuses when a required user test has no `pass` (go back to step 5), when no
      commit is linked, or when the repo has a remote and no PR is linked (go back to step 6).
      Fix what it names (the error prints the exact `link` command) and run it again. A PR
      that truly isn't wanted: `--no-pr "<why>"`, **only after the user agrees**. A ticket
      that truly changed no code: ask "<ID> changed no code because <why>. Close it without a
      commit?" and only on a yes use `--no-code "<why>"`.
- [ ] `python3 kanban/board.py check`
- [ ] Commit the board update (linked commits, status, handoff, ticks) as one bookkeeping commit
      on the ticket branch: `git add kanban/tickets.json && git commit -m "<ID>: waiting for merge on board"`
      (don't link this one), and push it if the branch is pushed.
- [ ] Report: what was built, what was verified, commits and the PR link, and "Tell me when the
      PR is merged and I'll close <ID>." (If `SLATE.md` says who merges PRs, name them.) Mention
      the next ready ticket (`python3 kanban/board.py next`) **as a suggestion only**. Then
      **stop**.

## Step 8: close — only after the user says the PR is merged

Run this step only when the user says the PR (or local branch) for `<ID>` is merged, or agrees
to close it without one. Never guess, never merge it yourself.

- [ ] PR merged → `python3 kanban/board.py link <ID> --pr-state merged` (several tickets in one
      PR: `link <ID1>,<ID2> --pr-state merged`).
- [ ] `python3 kanban/board.py set <ID> <done name> --handoff "PR merged by the user on <date>."`
      (several: `set <ID1>,<ID2> <done name> --handoff "…"`, all or nothing).
      board.py refuses done while a linked PR isn't `merged`; the fixes it prints are
      `link <ID> --pr-state merged` or `--no-pr "why"`. Use `--no-pr` only when the user said
      so ("close it without the PR, because …"). Done clears the claim.
- [ ] `python3 kanban/board.py check`, commit the board change
      (`git add kanban/tickets.json && git commit -m "<ID>: close on board"`) on whatever
      branch the user is on, and report. Then stop.

## When board.py refuses

- **Path rule** (`error: <ID> status: can't move A → B`): the project allows B only after the
  statuses it lists. Run the `fix:` line's **next allowed step** (e.g. review before user
  testing), with a real handoff note. Never change the rule yourself (`edit-status … from=…`,
  `set-meta workflow=free`): that is the user's call, so ask. Moving **back** (e.g. review →
  in progress after a finding) is allowed while rules exist but needs `--handoff "why"`.
- **Dependencies** (`error: <ID> depends_on: can't move to <State> until these are …`): each
  state says where dependencies must be first (default: Done; Waiting for merge also accepts
  dependencies that are Waiting for merge, so tickets in one PR can wait for the merge together).
  Say which ones block it and finish those first. `--ignore-deps` only with the user's reason and
  only for In progress / Review / User testing; never change the rule (`edit-status … deps=…`)
  yourself.
- **Claimed by someone else** (`ask the user:` … `--take-over`): stop and ask; add
  `--take-over "<reason>"` only with the user's OK.
- **Board is busy** (write lock held): another command or agent is writing. Wait a few seconds
  and retry, up to about a minute. Only when the error or `doctor` says the lock is **stale**
  (older than 60 s, or its process is gone): `python3 kanban/board.py unlock-write`, then retry.
  Never delete `kanban/.slate-write.lock` yourself.
- **Board-of-record warning** → stop and ask (step 0.8).
- Any other `ask the user:` line is a question: ask it, never guess.

## Rules that always hold

- **Always write a note on your own status moves**, even into states where it's optional (e.g. In progress): pass `--handoff "<what was done, or why it moves>"` on every `set` you run, e.g. `set ACME-014 in_progress --handoff "Started on slate/acme-014-reset; plan: form first, then email"`. The board keeps optional notes optional for people; this rule is for agents.

- Never leave a ticket in progress at the end of a session without a note:
  `python3 kanban/board.py note <ID> "Stopped at <where>; next <what>."`
- Obey "Stop and ask before" in `SLATE.md`: when blocked, do everything that doesn't depend on
  the answer, write the question into a `note`, and stop to ask. Don't switch to another
  ticket unless the user says so.
- One ticket per request unless the user explicitly asks for more. Human in the loop, always.
- Never touch a ticket another branch or agent has claimed without the user's OK.
- Draft PRs only, never merge, never force-push. done only after the user says it's merged.
- Mistakes are fixed with commands, not hand edits: `unlink` (wrong commit/PR),
  `usertest … reset` (wrong result), `uncheck-item` (wrong tick), `set` back with a handoff
  (wrong status), `edit` (wrong field).
- Never edit `kanban/tickets.json` by hand. If a hand edit is truly needed (for example fixing a
  broken merge no command can load), explain why to the user first, then run exactly
  `python3 kanban/board.py unlock --reason "<why>" --minutes 5` (no `cd … &&`, no pipes).
  - In **Manual**, **Accept edits** and **Auto** permission mode Claude Code shows its own
    approval card; the user's Yes activates the unlock.
  - In **Plan**, **Bypass permissions** and **Don't-ask** mode the guard refuses it: ask the
    user to run `python3 kanban/board.py unlock --reason "<why>"` in their own terminal (or tmux
    pane / second SSH session) and type the 4-letter code it shows, then tell you it's done.
  - One unlock = one edit, expiring after the minutes given. If the user declines, stop. Don't
    try to get around the guard any other way; `lock` cancels an unlock no longer needed.
