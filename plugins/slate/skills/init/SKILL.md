---
name: init
description: Set up Slate in this repo - copy the kanban board into kanban/, create tickets.json, write SLATE.md with this project's commands and rules, and create CLAUDE.md/AGENTS.md only if missing. Re-running it upgrades the board and refreshes SLATE.md.
argument-hint: "[project name]"
disable-model-invocation: true
allowed-tools: Bash(python3 kanban/board.py *)
---

# /slate:init — set up Slate in this project

You are setting up Slate in the current repo (the working directory; call it the repo root).
Work from the repo root. Announce each step in one line. Never touch any ticket data.

**Plugin root (`ROOT`):** `${CLAUDE_PLUGIN_ROOT}` (Claude Code fills this in for plugin skills).
If it still reads literally as `${CLAUDE_PLUGIN_ROOT}`, use this skill's base directory
(printed when the skill loads, `<root>/skills/init`) + `/../..`, resolved to an absolute path.
Assets are in `ROOT/assets/board/`, templates in `ROOT/templates/`, the plugin version in
`ROOT/.claude-plugin/plugin.json` (`version`).

## Step 0: what state is this repo in?

Check, in this order, and take the first branch that matches:

1. **`kanban/tickets.json` exists but has no Slate meta** (no `meta.slate_version`, or no
   `kanban/board.py`; for example a Forge board with `kanban/next.py`): **stop and ask.**
   Say: "This repo already has a kanban board that Slate didn't create. Moving it onto Slate
   is a separate migration step. I won't change it." Ask what they want to do and stop. Do not
   copy files, run `board.py init`, or write `SLATE.md` in this run.
2. **Already set up** (`kanban/board.py` and `kanban/tickets.json` with `meta.slate_version`):
   this run is an **upgrade plus refresh**. Run
   `python3 kanban/board.py version --against "<ROOT>"`:
   - `behind` → follow the `/slate:upgrade` procedure (read `ROOT/skills/upgrade/SKILL.md` and
     do its steps 1–5), then continue at step 1 below in *refresh mode*.
   - `ahead` → tell the user a teammate upgraded the board and they should update the plugin
     (`claude plugin marketplace update slate` then `claude plugin update slate@slate`, and
     restart Claude Code). Stop.
   - `same` → continue at step 1 in *refresh mode*.
   In refresh mode you re-detect values and compare them to `SLATE.md`; for every value that
   differs, show old vs new and ask before changing it. Never run `board.py init` again and
   never change tickets.
3. **Not set up** → continue at step 1.

## Step 1: look through the repo (read-only)

Read what exists, skipping what doesn't:

- [ ] `README*`, `CLAUDE.md`, `AGENTS.md`, `docs/` (list it; read the top-level files)
- [ ] Manifests: `pyproject.toml`, `setup.cfg`, `package.json` (+ lockfile to know npm/pnpm/yarn/bun),
      `go.mod`, `Cargo.toml`, `Gemfile`, `pom.xml`/`build.gradle`, `Makefile`, `justfile`, `Taskfile.yml`
- [ ] CI config: `.github/workflows/*`, `.gitlab-ci.yml`, others — these show the real lint/test commands
- [ ] Git: `git remote -v`, default branch (`git symbolic-ref refs/remotes/origin/HEAD` or
      `git branch --show-current`), whether the tree is clean
- [ ] Existing app entry points / dev server scripts (e.g. `npm run dev`, `uvicorn …`, `docker compose up`)

## Step 2: work out the values

| Value | How to infer | Example |
|---|---|---|
| project name | `$ARGUMENTS`, else manifest name, else README title, else folder name | Acme |
| prefix | 2–6 capital letters from the name, must match `^[A-Z][A-Z0-9]{1,9}$` | ACME |
| lint / test / typecheck | CI steps first, then manifest scripts | `npm run lint` · `npm test` · `npx tsc --noEmit` |
| live test | dev-server script + the URL/port it serves; or a CLI command to run | `npm run dev`, then open http://localhost:3000 |
| areas | top-level structure (e.g. `web/` → frontend, `api/` → backend, `infra/`) | backend, frontend, infra |
| docs map | files that explain conventions and architecture | coding conventions → CLAUDE.md |
| branch pattern | default `slate/<id>-<slug>` | |

If a command doesn't exist (e.g. no type checker), write `none`.

## Step 3: ask only what you couldn't work out

One question per message, multiple choice where possible, with your best guess as option (a).
Skip any question whose answer you already know. In this order:

1. Prefix for ticket ids (propose one; e.g. "(a) ACME (b) AC (c) something else").
2. Areas (propose the list you inferred).
3. Commands you couldn't find (lint / test / typecheck / how to start the app).
4. Extra review checks for this project, beyond the generic ones (bugs, security basics, scope,
   blast radius). Examples: "no secrets in logs or prompts", "every schema change is an
   additive migration", "accessibility on every UI change". (a) none (b) the user lists them.
5. Stop-and-ask rules: things Claude must ask about before doing. Offer defaults:
   "changing scope · destructive or irreversible actions · new external dependencies ·
   anything needing a credential you don't have · spending real money".
6. Plan style: (a) `plain` — pictures and plain words first, technical view on request
   (b) `technical` — technical view shown by default.
7. Enable the plugin for teammates in `.claude/settings.json`? (a) yes (b) no. See step 6.
8. Does this project need its own extra command (a project-level skill), for example an
   end-to-end test that needs special setup? (a) no (default) (b) yes, describe it.

## Step 4: copy the board and create tickets.json (skip in refresh mode)

```bash
mkdir -p kanban
cp "<ROOT>/assets/board/index.html" "<ROOT>/assets/board/board.py" "<ROOT>/assets/board/README.md" kanban/
python3 kanban/board.py init --project "<name>" --prefix <PREFIX> --areas <a,b,c>
python3 kanban/board.py version --against "<ROOT>"      # expect: same
python3 kanban/board.py check
```

If `board.py init` refuses, show its message and stop. Never write `tickets.json` yourself.

## Step 5: write SLATE.md

Copy `ROOT/templates/SLATE.md` to `SLATE.md` and replace every `{{…}}` placeholder:

- `{{PROJECT_CONTEXT}}`: 2–4 plain sentences — what the product is, who uses it, the key words a newcomer must know (from README/docs; point to them rather than copying)
- `{{PROJECT}}`, `{{PREFIX}}`, `{{LINT_CMD}}`, `{{TEST_CMD}}`, `{{TYPECHECK_CMD}}` (use `none` if absent)
- `{{LIVE_TEST}}`: how to start the app and what to open, or "not possible: <why>"
- `{{EXTRA_REVIEW_CHECKS}}`, `{{STOP_AND_ASK}}`: bullet lists (`- …`); `- none` if empty
- `{{PLAN_STYLE}}`: `plain` or `technical`
- `{{DOCS_MAP_ROWS}}`: one `| need | file |` row per doc; point to files, never copy their content
- `{{BRANCH_PATTERN}}`: `slate/<id>-<slug>` unless the user chose another

Keep the first line exactly `<!-- slate v<plugin version> · written by /slate:init, safe to edit values -->`.
In refresh mode, edit only the values the user agreed to change and any sections the template
has that `SLATE.md` lacks; keep everything else as the project wrote it.

## Step 6: CLAUDE.md, AGENTS.md, settings, project skill

- [ ] **CLAUDE.md missing** → create it from `ROOT/templates/CLAUDE.md` (`{{PROJECT}}`,
      `{{ONE_LINER}}` = one sentence on what the project is, `{{DOCS_POINTER}}` = where the docs are).
- [ ] **CLAUDE.md present** → do not edit it. Ask once: "Add one line to CLAUDE.md —
      'Planning, tickets and more project context: read SLATE.md (kept up to date as work goes on)' — so agents that only read CLAUDE.md find it?
      (yes/no)". Append only that line, only on yes. Skip the question if the line is already there.
- [ ] Same two rules for **AGENTS.md** with `ROOT/templates/AGENTS.md`.
- [ ] **Settings (only if the user said yes in step 3.7).** Create or merge into
      `.claude/settings.json` (keep every existing key; merge objects, don't replace them):

  ```json
  {
    "extraKnownMarketplaces": {
      "slate": {
        "source": { "source": "github", "repo": "Zidane786/slate" }
      }
    },
    "enabledPlugins": {
      "slate@slate": true
    }
  }
  ```

  Teammates who trust the repo are then offered the Slate marketplace and plugin.
- [ ] **Project skill (only if the user said yes in step 3.8).** Create
      `.claude/skills/<name>/SKILL.md` with frontmatter `name` and `description` and the exact
      steps of that one extra command, and add it to `SLATE.md` under "Commands". Nothing else.

## Step 7: show what you did

- List every file created or changed (`git status --short`), and show `SLATE.md`.
- Tell the user how to open the board: `cd kanban && python3 -m http.server 8088`, then
  http://localhost:8088 (or open `kanban/index.html` and pick `tickets.json` with the file picker).
- Suggest committing these files, then `/slate:plan "<an idea>"` as the next step.

## Checklist before you finish

- [ ] No existing `CLAUDE.md` / `AGENTS.md` changed except the one agreed line
- [ ] `python3 kanban/board.py check` passes and `version --against` says `same`
- [ ] `SLATE.md` has no `{{` left and starts with the version line
- [ ] No ticket was created, edited or deleted
