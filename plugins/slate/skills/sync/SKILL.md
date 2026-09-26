---
name: sync
description: Sort out the Slate board across branches and git worktrees, with the user deciding every change - find what differs (doctor, diff), explain it in plain words, bring changes across (sync --dry-run, then sync), walk through board conflicts left by a git merge one by one, repair a broken tickets.json with the fixes check prints, or copy the board to another worktree. Never hand-edits tickets.json. Use when asked to "sync the board", "sort out the board", "boards differ", "board conflict", "merge conflict in tickets.json", "the board is broken", or when board.py warns this is not the board of record.
argument-hint: "[branch | path]"
allowed-tools: Bash(python3 kanban/board.py *), Bash(python kanban/board.py *), Bash(py -3 kanban/board.py *), Bash(git status *), Bash(git log *), Bash(git worktree list *), Bash(git rev-parse *), Bash(git branch *)
---

# /slate:sync [branch | path] — sort out the board

Several branches, worktrees or agents each have their own copy of `kanban/tickets.json`, so
boards drift apart and git merges of the file can conflict. This skill finds the differences,
explains them in plain words and applies only what the user chooses.

**The user decides every change.** Look first (read-only), explain, ask, then write. Never run
`sync` (without `--dry-run`), `copy-to`, a conflict resolution or `unlock` without a yes for
that exact step. Every board read and write is a `python3 kanban/board.py …` call (use the
Python command from `SLATE.md` if it names another one); **never edit `kanban/tickets.json`
directly** and never write it with a script or `git checkout --theirs/--ours` on your own. The
full command list is in `<ROOT>/reference/commands.md`. Board server, doctor and every
refusal follow the same `error:` / `fix:` / `ask the user:` shape.

```
 doctor ─▶ what's wrong?  ─┬─ board won't load / check fails ─▶ Repair (step 4)
                           ├─ git merge left conflicts       ─▶ Conflicts (step 3)
                           └─ boards differ                  ─▶ diff ─▶ explain ─▶ ask
                                                                 ─▶ sync --dry-run ─▶ ask ─▶ sync
 afterwards: check ─▶ (copy-to another worktree only if the user asks) ─▶ report ─▶ STOP
```

## Step 0: version check, board server and where we are

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code). If it still reads literally,
   use this skill's base directory (printed when the skill loads) + `/../..`, made absolute.
2. If `kanban/board.py` is missing: say "This repo isn't set up for Slate yet — run
   `/slate:init` first." and stop.
3. Read `SLATE.md` (Python command, Board server / Board port, `## Workflow` incl. the board of
   record, "Stop and ask before").
4. `python3 kanban/board.py version --against "<ROOT>"`
   - `same` → say nothing.
   - `behind` → "This project's board is Slate <board>, the plugin is <plugin>. Upgrade now
     with `/slate:upgrade`?" Ask once. The branch/merge commands below need board 0.2.0 or
     newer: if the board is older, stop here and suggest the upgrade.
   - `ahead` → a teammate upgraded this board: offer to update it for them: "Your Slate plugin is older than this board (a teammate upgraded). Update it now? I'll run `claude plugin marketplace update slate` and `claude plugin update slate@slate`." On yes, run both, then ask the user to run `/reload-plugins` (or restart Claude Code) and invoke this command again. On no, stop.
5. **Board server.** Unless `SLATE.md` says `Board server: off`:
   `python3 kanban/board.py serve --ensure --port <Board port, default 8088>`; show the URL once
   (over SSH: `ssh -L <port>:localhost:<port> <host>`). If `serve` isn't in `--help` (an older board), skip.
   If the board can't be read at all, skip this until step 4 has repaired it.
6. Work out where you are, read-only:
   - `git rev-parse --git-dir` vs `git rev-parse --git-common-dir`: different → this is a
     **secondary worktree**. `git worktree list` shows the main one.
   - `SLATE_BOARD_OF_RECORD` set (an environment variable naming the board of record's
     tickets.json) → that file is the board of record.
   - Otherwise the board of record is `kanban/tickets.json` on the default branch in the main
     checkout (or what `SLATE.md` `## Workflow` says).
   - `git status --short kanban/`: uncommitted board changes? Mention them.

**Board of record rule.** If this checkout is not the board of record, or any board.py command
prints a board-of-record warning, **stop and ask** before writing anything: show the warning and
its `fix:` lines and ask which board should win. Typical answers: sync this board from the board
of record (step 2), or finish here and later sync the board of record from this one (the user
runs `/slate:sync <this branch or path>` from the main checkout).

## Step 1: what is wrong? (read-only)

- [ ] `python3 kanban/board.py doctor --against "<ROOT>" --json` — one report; each problem
      has a `code`, a `kind` and `fix` lines.
      - kind **`tickets`** — what this skill sorts out: `board-behind` (the default branch's
        board has tickets or notes this one lacks; its fixes are `diff <ref>` and
        `sync --from <ref> --dry-run` → step 2), `board-errors` (validation errors → step 4),
        `board-unreadable` (won't load: conflict markers or broken JSON → step 3 or 4).
      - kind **`setup`** — belongs to `/slate:upgrade` (or `/slate:init`): `schema-outdated`,
        `board-files-outdated`, `plugin-outdated` (update the plugin instead),
        `plugin-unreadable`, `python-cmd-missing`, `slate-md-missing`, `slate-md-sections`,
        `slate-md-workflow-stale`, `team-settings-missing`, `merge-driver-missing`, `gitignore-missing`,
        `repo-url-missing`. List them and offer `/slate:upgrade`; don't fix them here unless the
        user asks (the `fix` line says how). Two setup codes are handled right here:
        `write-lock-stale` → `python3 kanban/board.py unlock-write` (after saying so; only a
        stale lock), and `unlock-active` → ask whether the unlock is still needed, else
        `python3 kanban/board.py lock`.
- [ ] `python3 kanban/board.py check`. If it fails because the file doesn't parse or was left
      with git conflict markers (`<<<<<<<`), go to step 3 (merge) or step 4 (repair) first; diff
      and sync need a board that loads.
- [ ] Decide what to compare with (`OTHER`):
      `$ARGUMENTS` names a branch, ref or path → use it. Otherwise: the board of record
      (default branch, e.g. `main` or `origin/main` — no fetch unless the user asks), or the
      path from `SLATE_BOARD_OF_RECORD`, or the ref named in a warning's `fix:` line. Unsure →
      ask, multiple choice (the default branch, each worktree from `git worktree list`, other).

## Step 2: compare, explain, bring changes across

- [ ] `python3 kanban/board.py diff <OTHER>` (add `--json` if you need exact values).
- [ ] Explain it in plain words, grouped, each line with the ticket id and title. Say which
      side has what ("on `main`" / "here"). Leave out empty groups:

  ```
  Board here vs main:
  New tickets     on main only: ACME-031 "Export as CSV" (backlog)
                  here only:    ACME-032 "Dark mode" (draft)
  Status          ACME-014 "Password reset": here review · on main in_progress
  Notes           ACME-012: 2 handoff notes on main that aren't here (1 Oct review, 2 Oct done)
  Commits / PRs   ACME-012: commit a1b2c3d and PR !42 linked on main only
  Ticks / tests   ACME-014: user test 1 passed here only
  Field edits     ACME-020 summary: here "…" · on main "…"
  Phases          BACKLOG exists on main only
  ```

  Then say what `sync` would do by default: new tickets and phases added, notes, commits, ticks
  and test results combined from both, status takes whichever is further along, other field
  edits take theirs (`--prefer ours` keeps this board's). Point out anything that looks like
  real disagreement (the same field edited differently on both sides).
- [ ] Ask: "Bring main's changes into this board? (all / only some tickets / keep ours on
      field edits / no)". No → stop and report.
- [ ] `python3 kanban/board.py sync --from <OTHER> --dry-run` (with `--only ID,…` and
      `--prefer ours|theirs` as the user chose). Show the plan it prints in plain words. If it
      reports an id clash (the same id used for different tickets on each side), stop and ask
      how to resolve it: usually keep one side's ticket and re-add the other as a new ticket
      with `new` (a new id), never renumber by hand.
- [ ] Ask "Apply this?" Only on a yes: `python3 kanban/board.py sync --from <OTHER>` with the
      same flags.
- [ ] `python3 kanban/board.py check` and show the summary (`status`).
- [ ] If the sync or merge brought in phase or state changes (new phase, `BACKLOG`, a renamed
      or added state, path rules), ask "Update SLATE.md's Workflow section to match?" and on a
      yes replace the whole section (heading to the next `##` heading) with the output of
      `python3 kanban/board.py workflow --markdown`, adding nothing inside it. `doctor` reports `slate-md-workflow-stale` while they differ.
- [ ] Syncing the other way (this board's changes into the board of record) happens from that
      checkout: tell the user to run `/slate:sync <this branch or path>` there, or offer
      `copy-to` (step 5) when the target has nothing this board lacks.

## Claims across branches

Each branch's board records who is on which ticket (`claimed_by`, set by `set … in_progress` for
the current branch). Boards on different branches can disagree:

- `diff` shows a changed claim like any field; `sync` and the merge driver keep the **later**
  claim. Explain it: "ACME-014 is claimed by `slate/acme-014-reset` here and by
  `agent-b` on main (later)."
- Two branches working the same ticket is a real problem: stop and ask which one continues.
  The other gives it up with `python3 kanban/board.py release <ID>` on its own branch, or the
  user agrees to `claim <ID> --take-over "<reason>"` on the continuing one. Never take over a
  claim without the user's OK.
- A claim left by a finished or deleted branch: ask, then
  `python3 kanban/board.py release <ID> --take-over "branch <name> is gone"`.

## Step 3: after a git merge — walk through board conflicts

Git ran the Slate merge driver on `kanban/tickets.json` and it reported conflicts (exit 1, a
conflict list on stderr naming ticket, field, ours and theirs; ours is kept in the file).
If the merge driver isn't installed, git instead leaves conflict markers and board.py can't load
the file: then either abort the merge (`git merge --abort`, only if the user agrees) and run
`python3 kanban/board.py install-merge-driver` before merging again, or go to step 4.

- [ ] Get the list: the merge output the user pasted or you saw, or re-run the comparison with
      `python3 kanban/board.py diff <the merged branch>` (the other parent, e.g. `MERGE_HEAD`).
- [ ] `python3 kanban/board.py check` — the file must load; if not, step 4 first.
- [ ] For **each** conflict, one at a time, ask in plain words:

  ```
  Conflict 2 of 5 — ACME-014 "Password reset", field: summary
    kept now (ours, <this branch>):   "People can reset a forgotten password by email."
    other side (theirs, <branch>):    "People reset a forgotten password with a link."
  Keep ours, take theirs, or write a new value?
  ```

- [ ] Apply the answer only through board.py:
      - ours → nothing to do (already in the file); note it.
      - theirs or a new value → `python3 kanban/board.py edit <ID> <field>=<value>` (lists,
        numbers, booleans: `<field>:=<JSON>`; long text: `--file patch.json` written to the
        scratch area, never into `kanban/`).
      - status → `python3 kanban/board.py set <ID> <status> --handoff "Merge: kept <status> from <branch>, user's choice."`
      - phase definitions → `edit-phase` / `rename-phase`; rank → `rerank <ID> --after <OTHER>`.
- [ ] After the last one: `python3 kanban/board.py check`; fix what it reports with its `fix:`
      lines (ask before anything that changes meaning). Then tell the user the file is ready to
      `git add kanban/tickets.json` and finish the merge. Do not commit unless asked.

## Step 4: repair a broken board

When `check` fails or the file won't load (bad hand edit, a board export pasted over it, a
merge without the driver):

- [ ] `python3 kanban/board.py check` and read every `error:` line with its `fix:` /
      `ask the user:` line.
- [ ] Show the user the list in plain words and the fixes, grouped. Ask before running any fix
      that changes meaning (status, dependencies, removing or re-pointing things); purely
      mechanical fixes (e.g. `edit <ID> --rerank`) can be run once the user says "go ahead".
- [ ] Run the fixes one by one, re-running `check` after each group. A board that already has
      errors still accepts a write that **adds no new error and leaves fewer** ("repair: N errors
      left"); any other write is refused until the board is valid, so fix, don't add. `sync`
      only needs "no new errors". `ask the user:` lines are questions: ask them, never guess.
- [ ] Conflict markers or broken JSON that no command can load: prefer git — show the user
      `git diff kanban/tickets.json` and offer `git checkout <ref> -- kanban/tickets.json`
      followed by `sync --from <the other side>` (only with a yes; it replaces the file). Only
      if that can't work either, use the last resort below.

## Step 5: copy the board to another worktree (only after confirming)

- [ ] Only when the user asks for it, or agreed to it in step 2.
- [ ] `python3 kanban/board.py diff <PATH>` first: show what the target has that this board
      lacks. Ask "Replace the board in <PATH> with this one?"
- [ ] Yes → `python3 kanban/board.py copy-to <PATH>`. It refuses when the target has changes
      this board lacks: then offer `sync --from <PATH>` here first. `--force` only after the
      user saw exactly what would be lost and said to overwrite it.

## Last resort: unlock for one direct edit

Only when no command can do it (`edit`, `set`, `sync`, the `check` fixes, git) — explain that to
the user first and name the exact change.

- `python3 kanban/board.py unlock --reason "<why>" --minutes 5`. Run by you, it only writes a
  request; Claude Code then shows its permission card and the user's Yes activates it.
- The card only appears in **Manual**, **Accept edits** and **Auto** permission modes.
  - **Plan** mode refuses: ask the user to leave plan mode first.
  - **Bypass permissions**, **Don't-ask** or a `-p` script refuse (nobody there to approve):
    ask the user to run `python3 kanban/board.py unlock --reason "<why>"` in their own terminal
    and type the code it shows. Wait for them to say it's done.
- One unlock = one edit, expiring after the minutes given. Make exactly that edit, then
  `python3 kanban/board.py check`. If the user declines, stop. Never try to get around the
  guard any other way; `lock` cancels an unlock that is no longer needed.

## Report, then stop

- [ ] Every status move you made (`set`, `promote`, bulk `set`) carried a short note for the ticket's history (`--handoff "…"`), even where the state doesn't require one.

- What differed, what was applied (and what was left out on the user's choice), conflicts and
  how each was decided, repairs made, `check` result, and any `setup` problems from `doctor`
  still open (suggest `/slate:upgrade` or the `fix:` line).
- Anything the user must still do: finish the merge, commit, run `/slate:sync` from the other
  checkout. Do not commit, push or merge on your own. Then stop.
