---
name: review
description: Run only the Slate review gate on the current diff against a ticket's scope - bugs, security basics, scope vs acceptance and test scenarios, blast radius, plus the project's extra checks from SLATE.md - then fix confirmed findings. Does not change ticket status. Use for re-checks or when asked to "review ACME-014" or "review my changes".
argument-hint: "[ticket ID]"
allowed-tools: Bash(python3 kanban/board.py *)
---

# /slate:review [ID] — the review gate on its own

This is step 4 of `/slate:work` without the status change. **Do not change any ticket status**
and never edit `kanban/tickets.json`; `/slate:work` moves tickets.

## Step 0: version check and context

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code). If it still reads literally,
   use this skill's base directory (printed when the skill loads) + `/../..`, made absolute.
2. If `kanban/board.py` is missing: say "This repo isn't set up for Slate yet — run
   `/slate:init` first." You can still review the diff without a ticket; say so.
3. `python3 kanban/board.py version --against "<ROOT>"`: `same` → silent; `behind` → offer
   `/slate:upgrade` once and continue; `ahead` → tell the user to update the plugin
   (`claude plugin marketplace update slate`, `claude plugin update slate@slate`, restart);
   reviewing is read-only, so continue.
4. Read `SLATE.md` (commands, Extra review checks, Docs map). If it is missing, fall back to
   `CLAUDE.md` / `AGENTS.md` / docs and suggest re-running `/slate:init`.

## Steps

1. **Ticket:** `$ARGUMENTS`, else the open ticket from `python3 kanban/board.py next`
   (an `in_progress` / `review` / `user_testing` one). `python3 kanban/board.py show <ID>` for
   its acceptance and test_scenarios. No ticket at all → review against what the user describes.
2. **Diff:** `git diff <default-branch>...HEAD` plus `git diff` and `git diff --cached`.
   No git → list the changed files from the conversation.
3. **Tests first:** run the lint, type-check and full test commands from `SLATE.md`. Report
   failures before reviewing.
4. **Dispatch a reviewer** (the `code-review` skill if available, else an Agent such as
   `feature-dev:code-reviewer` or a general-purpose agent) with the diff, the ticket's
   acceptance and test_scenarios verbatim, and this brief:
   1. **Bugs and logic errors:** error handling, edge cases, async misuse, resource leaks.
   2. **Security basics:** secrets in code, logs or commits; injection into shell/SQL/HTML;
      path escapes; missing auth or input validation.
   3. **Scope:** every acceptance bullet met; every test scenario has a test; nothing outside
      the ticket changed without a note.
   4. **Blast radius:** callers of changed functions, data/migrations against existing rows,
      config and build still valid, full suite still passes.
   5. **Project checks:** every item under "Extra review checks" in `SLATE.md`.
5. **Verify and fix:** check each finding against the code yourself; fix the confirmed ones,
   re-run step 3, and re-review if a fix was non-trivial.
6. **Report:** findings fixed · findings dismissed and why · acceptance bullets or test
   scenarios still not covered · blast-radius notes. Suggest `/slate:work <ID>` to continue.
