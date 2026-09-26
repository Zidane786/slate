---
name: init
description: Set up Slate in this repo - copy the kanban board into kanban/, create tickets.json, write SLATE.md with this project's commands and rules, and create CLAUDE.md/AGENTS.md only if missing. Re-running it upgrades the board and refreshes SLATE.md.
argument-hint: "[project name]"
disable-model-invocation: true
allowed-tools: Bash(python3 kanban/board.py *), Bash(python kanban/board.py *), Bash(py -3 kanban/board.py *)
---

# /slate:init — set up Slate in this project

You are setting up Slate in the current repo (the working directory; call it the repo root).
Work from the repo root. Announce each step in one line. Never touch any ticket data, and
never edit or read `kanban/tickets.json` directly: board.py writes it. Every board command,
flag and "use it when" is in `<ROOT>/reference/commands.md`.

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
     do all its steps, including the "What's new" and upgrades/ steps), then continue at step 1 below in *refresh mode*.
   - `ahead` → a teammate upgraded the board: offer to update it for them: "Your Slate plugin is older than this board (a teammate upgraded). Update it now? I'll run `claude plugin marketplace update slate` and `claude plugin update slate@slate`." On yes, run both, then ask the user to run `/reload-plugins` (or restart Claude Code) and invoke this command again. On no, stop.
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
- [ ] Git: `git remote -v` (and `git remote get-url origin`), default branch
      (`git symbolic-ref refs/remotes/origin/HEAD` or `git branch --show-current`), whether the
      tree is clean, `git worktree list` (several worktrees → parallel work)
- [ ] **Python command:** try, in order, `python3`, `python`, `py -3` with
      `<cmd> -c "import sys; print(sys.version_info >= (3, 9))"`; the first that prints `True`
      is the project's Python command. Use it in place of `python3` in every command below.
      None works → tell the user Slate needs Python 3.9+ and stop.
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
| Python command | first of `python3` / `python` / `py -3` that runs 3.9+ | `python3` |
| repo_url | `git remote get-url origin`; SSH `git@host:group/repo.git` → `https://host/group/repo` (drop `.git`) | https://github.com/acme/app |
| parallel work | several `git worktree list` entries, CI with many branches, or the user says so | worktrees |
| board port | 8088 unless it is taken or the app uses it | 8088 |

If a command doesn't exist (e.g. no type checker), write `none`.

## Step 3: ask only what you couldn't work out

One question per message, multiple choice where possible, with your best guess (your
recommendation) as option (a). Skip any question whose answer you already know. In this order:

1. Prefix for ticket ids (propose one; e.g. "(a) ACME (b) AC (c) something else").
2. Areas (propose the list you inferred).
3. Commands you couldn't find (lint / test / typecheck / how to start the app).
4. **Python command** — only if more than one works or the one found isn't `python3`:
   "Slate will run the board with `<cmd>`. (a) OK (b) use another command".
5. Extra review checks for this project, beyond the generic ones (bugs, security basics, scope,
   blast radius). Examples: "no secrets in logs or prompts", "every schema change is an
   additive migration", "accessibility on every UI change". (a) none (b) the user lists them.
6. Stop-and-ask rules: things Claude must ask about before doing. Offer defaults:
   "changing scope · destructive or irreversible actions · new external dependencies ·
   anything needing a credential you don't have · spending real money".
7. Plan style: (a) `plain` — pictures and plain words first, technical view on request
   (b) `technical` — technical view shown by default.
8. **Parallel work:** "Do several people or agents work on this repo at the same time?
   (a) no, one at a time (b) yes, in separate branches (c) yes, in separate git worktrees".
   (b)/(c) → "Which board is the board of record? (a) `kanban/tickets.json` on
   `<default branch>` in the main checkout (b) another path". A path → tell them that setting
   `SLATE_BOARD_OF_RECORD=<absolute path to that tickets.json>` in each worktree's shell makes
   board.py warn when writing elsewhere (Slate doesn't set environment variables for them).
   Explain once: several agents can run board.py at the same time safely (they take turns via a
   write lock), each agent's ticket is **claimed** by its branch so others skip it, and
   `/slate:sync` brings boards together.
9. **Repository address** (only with a remote): "Link commits on the board to `<repo_url>`?
   (a) yes (b) another address (c) no".
10. **Someday ideas:** "Add an unscheduled `BACKLOG` phase for ideas that aren't planned yet?
    `next` and `/slate:work` skip it. (a) yes (b) no".
11. **Who merges pull requests?** "(a) you (b) a reviewer or maintainer (c) CI after approval".
    Slate never merges, whatever the answer; a ticket goes to Done only after that person's
    merge is reported.
12. **How the team works → states and rules.** Ask one at a time, then recommend:
    does every change get a code review? is there a separate QA / test step? do users try
    visible changes by hand? Recommend states and rules from the answers — or keep the
    defaults and no rules (the default: any move allowed). For example a QA step → add a "QA"
    column that behaves like Review; "every change goes through review and testing" → strict
    workflow. **Show the resulting path as a picture before applying**, then ask
    "(a) apply this (b) keep the defaults (c) change something":

    ```
    Backlog/Ready ─▶ In progress ─▶ Review ─▶ QA ─▶ User testing ─▶ Waiting for merge ─▶ Done
                                  (strict: no skipping forward; moving back needs a note)
    notes for the ticket's history required when moving into: Review, QA, User testing,
    Waiting for merge, Done
    ```

    For each state you add, ask "Should moving a ticket into <label> need a note for the
    ticket's history? (a) yes (b) no" (recommend what the state it is like does; default:
    required for Review, User testing, Waiting for merge and Done, optional otherwise), and
    offer to change a built-in state's setting if the team wants (`edit-status NAME
    note=required|optional`).

13. **Board server:** "Slate can keep the board page running for you, so clicks on it (ticks,
    Pass/Fail, moving cards) save to the board. (a) auto — start it when Slate commands run
    (b) off — I'll open it myself". Then the port: "(a) 8088 (b) another port" (propose another
    if the app uses 8088). Over SSH it is reached with `ssh -L <port>:localhost:<port> <host>`.
14. Does this project need its own extra command (a project-level skill), for example an
    end-to-end test that needs special setup? (a) no (default) (b) yes, describe it.

In refresh mode ask 8–13 only when `SLATE.md` doesn't answer them yet.

## Step 4: copy the board and create tickets.json (skip in refresh mode)

```bash
mkdir -p kanban
cp "<ROOT>/assets/board/index.html" "<ROOT>/assets/board/board.py" "<ROOT>/assets/board/README.md" kanban/
python3 kanban/board.py init --project "<name>" --prefix <PREFIX> --areas <a,b,c> [--repo-url <url>]
python3 kanban/board.py version --against "<ROOT>"      # expect: same
python3 kanban/board.py check
```

If `board.py init` refuses, show its message and stop. Never write `tickets.json` yourself.

Then apply the answers from step 3 (in refresh mode too, for anything newly agreed):

```bash
python3 kanban/board.py set-meta repo_url=<url>                 # if not given to init
python3 kanban/board.py add-phase --id BACKLOG --name "Someday" --goal "Ideas worth keeping, not planned yet" --demo "Nothing to demo; move a ticket to a real phase to build it" --unscheduled
python3 kanban/board.py add-status qa --after review --like review --label "QA" --note required   # only the states agreed
python3 kanban/board.py edit-status review note=optional        # only if the team chose it
python3 kanban/board.py set-meta workflow=strict                # or edit-status <state> from=a,b per agreed rule
python3 kanban/board.py export --json --statuses                # show the result, as a picture
```

## Step 4b: git settings and the board server (also in refresh mode)

- [ ] **Merge driver** (only if git exists): `python3 kanban/board.py install-merge-driver`
      (add `--python "<cmd>"` when the Python command isn't `python3`; it detects it otherwise).
      It adds `kanban/tickets.json merge=slate` to `.gitattributes` and sets
      `merge.slate.driver` in this clone's git config, so git merges the board ticket by
      ticket instead of leaving conflict markers in JSON. Tell the user each teammate runs it
      once per clone (the `.gitattributes` line is committed; the git config is not;
      `/slate:init` or `/slate:upgrade` does it for them).
- [ ] **`.gitignore`**: make sure it has these lines (add only what's missing, under a
      `# Slate: local files (never commit)` comment; create the file if there is none; an older
      `kanban/.slate-unlock.json` / `kanban/.slate-unlock.used.json` pair can stay):

      ```
      kanban/.slate-unlock*.json
      kanban/.slate-write.lock
      kanban/.slate-serve.json
      kanban/.slate-serve.log
      ```

      They hold one-time unlocks for hand edits (request, active, used, pending log), the lock
      board.py holds while it writes, and the running board server's address and log; none of
      them belong in git.
- [ ] **Board server** (unless the user chose off):
      `python3 kanban/board.py serve --ensure --port <port>` and show the URL it prints. If
      `serve` isn't in `python3 kanban/board.py --help` (an older board), skip it.
- [ ] **Check:** `python3 kanban/board.py doctor --against "<ROOT>"` should report no `setup`
      problems once SLATE.md is written (run it again after step 5).

## Step 5: write SLATE.md

Copy `ROOT/templates/SLATE.md` to `SLATE.md` and replace every `{{…}}` placeholder:

- `{{PROJECT_CONTEXT}}`: 2–4 plain sentences — what the product is, who uses it, the key words a newcomer must know (from README/docs; point to them rather than copying)
- `{{PROJECT}}`, `{{PREFIX}}`, `{{LINT_CMD}}`, `{{TEST_CMD}}`, `{{TYPECHECK_CMD}}` (use `none` if absent)
- `{{LIVE_TEST}}`: how to start the app and what to open, or "not possible: <why>"
- `{{EXTRA_REVIEW_CHECKS}}`, `{{STOP_AND_ASK}}`: bullet lists (`- …`); `- none` if empty
- `{{PLAN_STYLE}}`: `plain` or `technical`
- `{{DOCS_MAP_ROWS}}`: one `| need | file |` row per doc; point to files, never copy their content
- `{{BRANCH_PATTERN}}`: `slate/<id>-<slug>` unless the user chose another
- `{{PYTHON_CMD}}`: the Python command (`python3`, `python` or `py -3`)
- `{{BOARD_SERVER}}`: `auto` or `off`; `{{BOARD_PORT}}`: the port (default `8088`)
- `{{WORKFLOW}}`: fill everything else first and save `SLATE.md` (the generator reads its
  `Python:` line), then run `python3 kanban/board.py workflow --markdown` and replace the
  **whole** `## Workflow` section — from its heading to the next `##` heading — with that output
  (it includes the heading). It describes every state (column title, role, meaning, allowed
  "from" states, whether moving into it needs a note for the ticket's history), the workflow mode, user tests, bugs, unscheduled phases, the board of record,
  the merge driver, the Python command and the unlock rule, all read from the board and this
  repo. **Add nothing inside it:** `doctor` compares it with the board word for word and reports
  `slate-md-workflow-stale` otherwise. Project notes go under "Rules" (next placeholder) or
  "Decisions". If `workflow` isn't in `--help` (an older board), write the section by hand from
  `export --json --statuses`.
- `{{RULES_NOTES}}`: one line each, from the interview: who merges PRs ("PRs are merged by
  <who>; Slate marks a ticket done only after they say it's merged"), how the team works in
  parallel (branches / worktrees; the board of record if not the default). `- none` lines are
  not needed: drop the placeholder line if there is nothing to say.
- `{{SLATE_UPDATES}}`: one line `<today> · Slate <plugin version> set up by /slate:init`

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
- [ ] **Team settings (always; no question).** So everyone who clones the repo gets Slate, make
      sure the **project's** `.claude/settings.json` (in the repo, committed) contains the entry
      below. **Always the project settings file — never the user's `~/.claude/settings.json`**
      (Slate never edits user settings). Create the file if
      missing; if it exists, merge (keep every existing key; merge objects, never replace them;
      leave it alone if the entry is already there). Tell the user what you added.

  ```json
  {
    "extraKnownMarketplaces": {
      "slate": {
        "source": { "source": "github", "repo": "Zidane786/slate" },
        "autoUpdate": true
      }
    },
    "enabledPlugins": {
      "slate@slate": true
    }
  }
  ```

  When someone clones the repo and accepts Claude Code's folder-trust prompt, Claude Code adds
  the Slate marketplace in the background and loads the plugin (Slate's marketplace entry is a
  relative path, so no install command is needed); the first time they see "Plugins changed.
  Run /reload-plugins to activate." `autoUpdate` keeps Slate updated. (`claude -p` and cloud
  sessions never show the trust prompt; there, install with `claude plugin install slate@slate`.)

  **If `.claude/settings.json` is ignored by git** (`git check-ignore -q .claude/settings.json`
  succeeds): still write the entry, but **don't edit `.gitignore`**. Tell the user: "Your
  `.gitignore` excludes `.claude/settings.json`, so people who clone this repo won't get Slate
  automatically. If you want them to, commit that file (remove it from `.gitignore`)."
- [ ] **Project skill (only if the user said yes in step 3.14).** Create
      `.claude/skills/<name>/SKILL.md` with frontmatter `name` and `description` and the exact
      steps of that one extra command, and add it to `SLATE.md` under "Commands". Nothing else.

## Step 7: show what you did

- List every file created or changed (`git status --short`, including `.gitattributes` and
  `.gitignore`), and show `SLATE.md`.
- Tell the user how to open the board: the live URL from step 4b (`Board server: auto`), or
  `python3 kanban/board.py serve --port <port>` in a terminal. Live mode saves clicks (ticks,
  Pass/Fail, moving cards, notes) to the board through board.py; a plain
  `cd kanban && python3 -m http.server 8088` or opening `kanban/index.html` gives a **view-only**
  board whose clicks stay in that browser (its "Copy as board.py commands" button turns them into
  commands). Over SSH: `ssh -L <port>:localhost:<port> <host>`, then open the URL on your machine.
- **Explain unlock once**, in plain words: "Slate blocks direct edits to `tickets.json`. If one
  is ever truly needed, Claude asks for a one-time unlock: in Manual, Accept edits or Auto mode
  Claude Code shows its approval card and your Yes allows exactly one edit; in Plan, Bypass
  permissions or Don't-ask mode you run `python3 kanban/board.py unlock --reason "…"` in your own
  terminal (or a tmux pane) and type the code it shows." Copilot CLI support: planned.
- Suggest committing these files, then `/slate:plan "<an idea>"` as the next step.

## If a hand edit of tickets.json is ever needed

Never write `kanban/tickets.json` yourself. First try the `fix:` lines `check` prints: board.py
accepts a write on a broken board when it removes errors and adds none ("repair: N errors left").
If a hand edit is still needed (for example git conflict markers from a merge without the Slate
merge driver), explain why to the user, then run exactly
`python3 kanban/board.py unlock --reason "<why>" --minutes 5` (no `cd … &&`, no pipes: only the
plain command can activate an unlock). Claude Code shows its approval card in Manual, Accept edits and Auto mode; in Plan, Bypass and Don't-ask mode the guard refuses it, and the user runs `unlock` in their own terminal and types the code it shows. One unlock = one edit. If the user declines, stop.
Copilot CLI support: planned.

## Checklist before you finish

- [ ] No existing `CLAUDE.md` / `AGENTS.md` changed except the one agreed line
- [ ] `python3 kanban/board.py check` passes and `version --against` says `same`
- [ ] `SLATE.md` has no `{{` left and starts with the version line
- [ ] No ticket was created, edited or deleted
- [ ] Merge driver installed (git repos) and `.gitignore` has `kanban/.slate-unlock*.json`,
      `kanban/.slate-write.lock`, `kanban/.slate-serve.json`, `kanban/.slate-serve.log`
- [ ] `SLATE.md` has `Python:`, `Board server:`, `Board port:`, a filled `## Workflow` and a
      `## Slate updates` line; `python3 kanban/board.py doctor --against "<ROOT>"` shows no
      `setup` problems
- [ ] States and rules changed only as the user agreed, after seeing the picture
