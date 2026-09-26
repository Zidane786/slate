---
name: upgrade
description: Upgrade this project's Slate board to the installed plugin's version - show "What's new" for every version in between, replace kanban/index.html, board.py and README.md, migrate tickets.json additively, run each version's upgrade steps (merge driver, .gitignore, SLATE.md sections, board server, custom states and workflow rules recommended from how the team really works), record the upgrade in SLATE.md, run doctor until healthy, show the diff.
disable-model-invocation: true
allowed-tools: Bash(python3 kanban/board.py *), Bash(python kanban/board.py *), Bash(py -3 kanban/board.py *)
---

# /slate:upgrade — bring the copied board up to the plugin's version

Only run when the user typed `/slate:upgrade` (other skills offer it, never run it). Never
hand-edit or read `kanban/tickets.json` directly; `board.py` migrates it. Board commands are
`python3 kanban/board.py …`, or the Python command `SLATE.md` names ("Python: `…`"); every
command is in `<ROOT>/reference/commands.md`. Ask one question at a time and keep every value
the project already set.

```
 versions ─▶ What's new (every version in between) ─▶ ask ─▶ upgrade + migrate
    ─▶ upgrades/<v>.md steps, in order ─▶ SLATE.md (version line, sections, Slate updates)
    ─▶ doctor until healthy (tickets problems → /slate:sync) ─▶ summary + diff ─▶ STOP
```

## Step 0: versions

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code). If it still reads literally,
   use this skill's base directory (printed when the skill loads) + `/../..`, made absolute.
2. If `kanban/board.py` is missing: "This repo isn't set up for Slate yet — run `/slate:init`."
   Stop.
3. `python3 kanban/board.py version --against "<ROOT>" --json` → note the project's board
   version (**OLD**) and the plugin version (**NEW**):
   - `same` → "Already on Slate <version>." Still run `python3 kanban/board.py doctor --against
     "<ROOT>"`; if it lists `setup` problems, offer to fix them (step 4). Otherwise stop.
   - `ahead` → the board is newer than the plugin (<board> vs <plugin>) — never downgrade;
     offer to update it for them: "Your Slate plugin is older than this board (a teammate upgraded). Update it now? I'll run `claude plugin marketplace update slate` and `claude plugin update slate@slate`." On yes, run both, then ask the user to run `/reload-plugins` (or restart Claude Code) and invoke this command again. On no, stop.
   - `behind` → continue.
4. `git status --short kanban/ SLATE.md`: if those files have uncommitted changes, say so and
   ask whether to continue (the upgrade replaces the Slate-owned files).

## Step 1: What's new — before changing anything

- List `<ROOT>/upgrades/` and pick every `<version>.md` with **OLD < version ≤ NEW**, compared
  as numbers (0.10.0 > 0.9.0), in ascending order (see `<ROOT>/upgrades/README.md`).
- Show the user each file's **"What's new"** section in plain words (what they can now do, one
  example command each). Keep it short; group by version when there are several.
- Say what the upgrade changes: `kanban/index.html`, `kanban/board.py`, `kanban/README.md`
  replaced (Slate-owned; local edits to them are not kept); `kanban/tickets.json` migrated by
  additive steps only (new fields with defaults, new statuses inserted; nothing deleted or
  renamed); `SLATE.md` gets its version line, any new sections and one "Slate updates" line —
  every value the project set is kept; git settings (`.gitattributes`, `.gitignore`, this
  clone's git config) as the steps say, each asked first.
- The full CHANGELOG ships with the plugin (`<ROOT>/CHANGELOG.md`); if it is somehow missing,
  point to https://github.com/Zidane786/slate/blob/main/plugins/slate/CHANGELOG.md.
- Ask: "Upgrade from <OLD> to <NEW> now?" Continue only on yes.

## Step 2: replace and migrate

```bash
python3 kanban/board.py upgrade --from "<ROOT>/assets/board"
python3 kanban/board.py version --against "<ROOT>"      # expect: same
python3 kanban/board.py check
```

`upgrade` copies the three files and runs the new `board.py migrate` (which also runs `check`).
If anything fails, show the output, and restore with `git checkout -- kanban/` only if the
user agrees. Never hand-edit `tickets.json` to make it pass: use the `fix:` lines `check` prints
(board.py accepts writes that remove errors and add none: "repair: N errors left"). If a hand
edit is still needed, explain why, then run exactly
`python3 kanban/board.py unlock --reason "<why>" --minutes 5` (no `cd … &&`, no pipes). In
Manual, Accept edits and Auto mode Claude Code shows its approval card and the user's Yes
activates it; in Plan, Bypass permissions and Don't-ask mode the guard refuses it, and the user
runs `unlock` in their own terminal (or tmux pane) and types the code it shows. One unlock =
one edit. If the user declines, stop. Copilot CLI support: planned.

## Step 2b: team settings (always)

Run `python3 kanban/board.py doctor --json`. If it reports `team-settings-missing`, add Slate to
the **project's** `.claude/settings.json` (in the repo — never the user's `~/.claude/settings.json`)
exactly as `/slate:init` does (read
`ROOT/skills/init/SKILL.md`, "Team settings"): merge the `extraKnownMarketplaces.slate` entry
(with `"autoUpdate": true`) and `"enabledPlugins": {"slate@slate": true}`, keep every other key,
and tell the user what you added. If doctor's notes include `team-settings-ignored`, don't touch
`.gitignore`; just tell the user people who clone the repo won't get Slate automatically until
`.claude/settings.json` is committed.

## Step 3: run each version's upgrade steps

For every file picked in step 1, in ascending version order: read it and run its numbered
steps in order. Each step has a **Check** (skip the step when it says "not needed", so re-runs
are safe) and a **Do** (exact commands and the exact questions to ask). Use the project's
Python command in every command. Ask before anything that touches files the project owns.

Steps that recommend **workflow rules** use `python3 kanban/board.py flow` (the status moves
tickets really made, with counts): turn it into a plain recommendation with a picture of the
path, and apply rules only on a yes. If `flow` isn't in `python3 kanban/board.py --help` (an older board),
ask the questions in the step instead (does everything get reviewed? is there QA? do users test
by hand?) — or keep the defaults.

## Step 4: SLATE.md, then doctor until healthy

- [ ] Replace the first line with `<!-- slate v<NEW> · written by /slate:init, safe to edit values -->`.
- [ ] Compare with `<ROOT>/templates/SLATE.md`: add any section or setting line the template has
      that `SLATE.md` lacks (fill it the way `/slate:init` would, asking for anything unknown;
      the `upgrades/<v>.md` steps say how for their version). Change no existing value.
- [ ] `## Workflow`: if it is missing or `doctor` says `slate-md-workflow-stale`, ask, then
      replace (or add) the whole section with the output of
      `python3 kanban/board.py workflow --markdown` (it includes the heading; add nothing inside
      it — doctor compares it word for word). Lines the project had written there (who merges,
      notes) move to "Rules" or "Decisions" first.
- [ ] `## Slate updates`: add one dated line for this upgrade, naming the main new things
      from "What's new", e.g.
      `2026-09-26 · Slate 0.1.0 → 0.2.0: live board (serve), custom states, workflow rules, claims, remove/restore, notes, doctor, sync + merge driver, waiting-for-merge column, bug tickets`.
- [ ] `SLATE.md` missing → offer to recreate it with `/slate:init`.
- [ ] `python3 kanban/board.py doctor --against "<ROOT>"` and repeat until it reports no
      `setup` problems: for each, tell the user what its `fix:` line does and run it (ask first
      when it touches files the project owns). `write-lock-stale` → `unlock-write`;
      `unlock-active` → ask, then `lock`; `ask the user:` lines are questions.
- [ ] Problems of kind **`tickets`** (`board-behind`, `board-errors`, `board-unreadable`) are not
      part of the upgrade: list them and say "Run `/slate:sync` to sort the board out."

## Step 5: show the result, then stop

- Short summary: "Now on Slate <NEW>. New for you: …" (two or three lines from "What's new"),
  what was set up (merge driver, `.gitignore`, board server, states/rules if the user chose
  them), `doctor` result.
- Board server: unless `SLATE.md` says `Board server: off`, run
  `python3 kanban/board.py serve --ensure --port <Board port>` and give the URL once (over SSH:
  `ssh -L <port>:localhost:<port> <host>`).
- `git diff --stat` and a one-line summary per changed file.
- Tell the user to commit it (e.g. `Slate: upgrade board to v<NEW>`) and that each teammate's
  clone needs the merge driver once (`/slate:upgrade` or `/slate:init` in their clone). Do not
  commit yourself unless asked.
