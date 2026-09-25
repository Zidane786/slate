---
name: upgrade
description: Upgrade this project's Slate board to the installed plugin's version - show what changes, replace kanban/index.html, board.py and README.md, migrate tickets.json additively, refresh SLATE.md's version line, show the diff.
disable-model-invocation: true
allowed-tools: Bash(python3 kanban/board.py *)
---

# /slate:upgrade — bring the copied board up to the plugin's version

Only run when the user typed `/slate:upgrade` (other skills offer it, never run it). Never
hand-edit `kanban/tickets.json`; `board.py` migrates it.

## Step 0: versions

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code). If it still reads literally,
   use this skill's base directory (printed when the skill loads) + `/../..`, made absolute.
2. If `kanban/board.py` is missing: "This repo isn't set up for Slate yet — run `/slate:init`."
   Stop.
3. `python3 kanban/board.py version --against "<ROOT>" --json` →
   - `same` → "Already on Slate <version>. Nothing to upgrade." Stop.
   - `ahead` → "This board is newer than your plugin (<board> vs <plugin>). Update the plugin
     instead: `claude plugin marketplace update slate`, `claude plugin update slate@slate`,
     restart." Stop — never downgrade.
   - `behind` → continue.
4. `git status --short kanban/ SLATE.md`: if those files have uncommitted changes, say so and
   ask whether to continue (the upgrade replaces the Slate-owned files).

## Step 1: show what changes, then ask

- Files replaced: `kanban/index.html`, `kanban/board.py`, `kanban/README.md` (Slate-owned;
  local edits to them are not kept). `kanban/tickets.json` migrated by additive steps only
  (new fields with defaults, new statuses appended; nothing deleted or renamed).
  `SLATE.md`: version line and any new sections; every value you set is kept.
- The CHANGELOG entries between the two versions: read `ROOT/CHANGELOG.md` (it ships with the
  plugin); if it is somehow missing, point to
  https://github.com/Zidane786/slate/blob/main/plugins/slate/CHANGELOG.md.
- Ask: "Upgrade from <board> to <plugin> now?" Continue only on yes.

## Step 2: replace and migrate

```bash
python3 kanban/board.py upgrade --from "<ROOT>/assets/board"
python3 kanban/board.py version --against "<ROOT>"      # expect: same
python3 kanban/board.py check
```

`upgrade` copies the three files and runs the new `board.py migrate` (which also runs `check`).
If anything fails, show the output, and restore with `git checkout -- kanban/` only if the
user agrees.

## Step 3: refresh SLATE.md

- Replace the first line with `<!-- slate v<plugin version> · written by /slate:init, safe to edit values -->`.
- Compare with `ROOT/templates/SLATE.md`: add any section the template has that `SLATE.md`
  lacks (fill it the way `/slate:init` would, asking the user for anything unknown). Change no
  existing value.
- `SLATE.md` missing → offer to recreate it with `/slate:init`.

## Step 4: show the result

- `git diff --stat` and a one-line summary per changed file.
- Tell the user to commit it (e.g. `Slate: upgrade board to v<version>`); `/slate:work` will
  also commit it on its branch if they prefer. Do not commit yourself unless asked.
