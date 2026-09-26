# Changelog

All notable changes to Slate. Versions follow the plugin's `plugin.json`; the board's schema
version is noted when it changes. Each release lists **Highlights**, then **Added**, **Changed**,
**Fixed**, **Security**, **Removed** and **Upgrade notes** (a section is left out when it has
nothing). Merging a version bump into `main` publishes a GitHub Release with that version's
section.

## 0.2.0 — 2026-09-26

Board schema **2**. Older boards keep working; `/slate:upgrade` (or `board.py migrate`) upgrades
them by adding only. Most of this release came from using Slate on a real project with about 60
tickets, stacked PRs, parallel agents and git worktrees.

### Highlights

- **Live board page:** `board.py serve` — drag cards, tick items, pass user tests, add notes in
  the browser and they save to the board, through the same checks as the commands.
- **Branches and merges that just work:** a git merge driver merges `tickets.json` ticket by
  ticket; `diff`, `sync`, `copy-to` and board-of-record warnings keep worktrees in step.
- **Your own columns and workflow:** custom states with roles, optional "can only come from"
  rules, per-state note rules.
- **Safe parallel work:** claims ("who's on it") and a write lock so agents never collide.
- **A new "Waiting for merge" column**, ticks with evidence, bug tickets, and a supervised
  one-edit unlock for rare hand fixes.
- **Runs on Windows, macOS and Linux**, tested on all three.

### Added

**Planning and editing tickets**

- `edit-phase ID name=… goal=… demo=…` changes a phase after it was created.
- `rename-phase OLD NEW` changes a phase id and moves its tickets with it.
- `remove-phase ID [--move-to OTHER]` removes a phase (refused while tickets use it, unless
  they're moved).
- `reorder-phases` sets the order phases are shown in.
- **Unscheduled phases** (`add-phase … --unscheduled`, e.g. `BACKLOG`) for someday ideas:
  `next`, `list` and `/slate:work` skip them; they show last and folded; phase ids don't need
  a P-number.
- `edit ID description+="…"` appends to a text field (also `summary`, `story`, `technical`,
  `visual`) instead of replacing it.
- **Bug tickets:** `new --bug --fixes ACME-004` labels it `bug` and `fixes-ACME-004`, ranks it
  before the ticket it fixes and makes that ticket wait for it; `--reopen` (with your OK) for a
  fixed ticket that was already done.
- `edit … --rerank` moves a ticket after its dependencies automatically.
- `set ID STATUS --ignore-deps "why"` for stacked work (up to Review / User testing; Waiting for
  merge and Done stay strict); the reason is kept in the ticket's history.
- **Bulk changes:** `set ID1,ID2 …`, `link ID1,ID2 --pr URL`, `edit ID1,ID2 …`, `note ID1,ID2 …`
  — all or nothing.
- `export --json` with `--phase`, `--status`, `--label`, `--area`, `--drafts`, `--removed`,
  `--statuses`, so agents never read `tickets.json` directly; the same filters on `list` and
  `status`.
- `check --quiet-optional` (or `set-meta check_quiet_optional:=true`) hides optional-field
  warnings and says how many.
- **Ticks with evidence:** `check-item ID acceptance|test N --evidence "…"` / `uncheck-item`;
  `show` and the board show each ticked item with its evidence.
- **Waiting for merge:** new `merge_ready` status and column. Reached only after user tests pass
  and the commit (and PR, when there's a remote) are linked; `done` then needs the PR marked
  merged (`link ID --pr-state merged`) or your OK to close without one (`--no-pr "why"`).
- `remove` / `restore` (archive in `meta.removed`; ids never reused), `unlink` (a wrong commit or
  PR link), `usertest ID N reset`, `note ID "…"` (history note without a status change),
  `set-meta priorities:=[…]`.

**Columns and workflow**

- **Custom states with roles:** `add-status NAME --after X --like ROLE [--label … --note …]`,
  `rename-status`, `edit-status NAME label=… role=… from=… note=…`, `reorder-statuses`,
  `remove-status [--move-to]`. Rules follow roles, so renamed or added columns keep working.
- **Optional workflow rules:** per-state `from=` lists or `set-meta workflow=strict|free`; a
  refused move names the next allowed step; moving back needs a note.
- **Per-state note rule:** whether moving into a state needs a note for the ticket's history
  (`--note required|optional`); defaults: Review, User testing, Waiting for merge, Done.
- `flow` shows the moves your tickets really made and suggests rules; `workflow --markdown`
  generates the `## Workflow` section of `SLATE.md`.

**Branches, worktrees and merges**

- `diff OTHER` compares with a file, folder, git ref or worktree (rank-only changes and history
  dates ignored).
- `sync --from OTHER [--dry-run --only --prefer]` brings another board's changes in through the
  normal checks.
- **Merge driver:** `merge-driver` + `install-merge-driver` (`.gitattributes`:
  `kanban/tickets.json merge=slate text eol=lf`) — field-level merges, only real conflicts
  reported.
- **Board-of-record warnings** when writing from a secondary worktree, outside
  `SLATE_BOARD_OF_RECORD`, or behind the default branch's board.
- `copy-to PATH` / `export-file` writes a checked copy, refusing to overwrite newer changes
  unless `--force`.
- **Repair writes:** a broken board accepts writes that fix errors and add none.

**Parallel work and health**

- **Claims:** starting a ticket records who's on it (branch or `--as`); `next`/`list` skip
  others' tickets; `claim`, `release`, `--take-over "why"` (with your OK).
- **Write lock** (`kanban/.slate-write.lock`) so simultaneous writes never lose data;
  `unlock-write` clears a stale lock.
- `doctor [--json --brief --against]`: one health report, each problem with a code, a kind
  (`setup` → `/slate:upgrade`, `tickets` → `/slate:sync`) and a fix.

**Board server and board page**

- `board.py serve [--ensure --status --stop --port --strict-port --host --open --idle-exit]`:
  serves the board plus a token-protected local API; `--ensure` starts it once and reuses it
  (even one you started yourself), picks a free port, stops after 8 idle hours. Skills start it
  automatically unless `SLATE.md` says `Board server: off`.
- **Live mode:** every board-page action saves — drag / status, ticks, user test Pass / Fail /
  Clear, notes, Promote, Take / Release; disallowed moves are greyed with the reason.
- **View-only mode** (opened any other way): changes marked "local only", plus "Copy as
  board.py commands" (grouped, safe order).
- **Auto-refresh:** polls every 5 s while visible (30 s when idle, conditional requests), keeps
  your place and open ticket, shows "Board updated".
- Folding phases (empty ones folded, unscheduled last); card chips for PR, `bug`, `fixes …`,
  "blocked by …", "on: …"; custom column titles; panels for removed tickets and unlock history;
  compact banners for doctor, unlock and preview.

**Skills, setup and docs**

- **New `/slate:sync` skill:** differences in plain words, sync with your yes, merge conflicts
  one at a time, repairs, claims across branches.
- **`/slate:init` asks more:** parallel work and board of record, repo address, `BACKLOG`
  phase, who merges PRs, Python command, board server and port, columns and workflow rules
  (recommended, shown as a picture first).
- **Upgrades explain themselves:** `upgrades/<version>.md` ("What's new" + steps);
  `/slate:upgrade` shows it first, runs each step with your OK, records a dated `## Slate
  updates` line in `SLATE.md`, and runs `doctor` until healthy.
- **Shared command reference** (`reference/commands.md`) linked by every skill; a test keeps
  docs and board.py in step.
- `SLATE.md` gains `Python:`, `Board server:`, `Board port:`, `## Workflow` and
  `## Slate updates`.
- Agents always add a note for the ticket's history on their own status moves.

**Unlock (supervised escape hatch)**

- `board.py unlock --reason "…"` / `lock`: approval is Claude Code's own permission card in
  Manual, Accept edits and Auto mode, or a code you type in your own terminal (works over SSH
  and in tmux). Refused in Plan, Bypass permissions and Don't-ask mode. **One unlock = one
  direct edit**, expiring after at most 30 minutes; every step logged in `meta.unlock_log`.

### Changed

- Hooks run through `hooks/run.sh`, which finds `python3`, `python` or `py -3`; fix lines print
  the Python command that ran board.py.
- Skills speak in roles (not column names), create the ticket branch before claiming, respect
  claims and workflow rules, and allow the `python3`, `python` and `py -3` forms.
- `/slate:work` stops at Waiting for merge and closes only after you confirm the merge.
- `/slate:status` shows waiting-for-merge tickets, claims, unscheduled and archived counts,
  the workflow mode, doctor's summary and the board link; `/slate:review` and `/slate:status`
  read tickets via `export --json`.
- `install-merge-driver`'s `.gitattributes` line now includes `text eol=lf` (older lines are
  updated).
- `board.py check` calls older tickets "older-format ticket (no summary/story)".

### Fixed

- Repeating `--labels a --labels b` on `new` kept only the last value; all values are kept now.
- The guard treated any `open(` in a Bash command as a write, blocking read-only commands like
  `python3 -c "json.load(open('kanban/tickets.json'))"`.
- Changing `depends_on` to a later-ranked ticket failed with no way forward; the error now
  offers `--rerank`.
- Done tickets showed their checklists as 0/N ticked on the board page.
- **Windows:** `serve --ensure` thought free ports were taken (a refused connect is slow there);
  ports are now checked by binding first.
- **Windows:** hook messages reached Claude Code garbled; hooks and board.py now read and write
  UTF-8.
- **Windows:** `tickets.json` showed as changed after every write (CRLF checkouts); files are
  written with LF and `.gitattributes` keeps them that way.
- A slow-to-answer web server on the board port was reported as "port taken" instead of "not a
  Slate server".
- The board page no longer logs a "not found" error every 5 s when there is no preview.

### Security

- The guard now also blocks direct writes via `curl -o`, `wget -O`, `rsync`, `sponge`,
  `shutil.copy`/`move`, `os.replace`/`rename` and `Path.replace`/`rename`, and matches file names
  case-insensitively (macOS and Windows file systems).
- The unlock files and the write lock can't be written directly; an agent alone can only request
  an unlock.
- The board server listens on 127.0.0.1 by default (loud warning otherwise), checks Host/Origin,
  requires a per-run token for writes, and serves only files inside `kanban/`.

### Removed

- Nothing removed. The desktop pop-up approval that was considered for the unlock was not
  shipped (it can't work over SSH); its design is archived in the repo under `docs/archive/`.

### Upgrade notes

- Run `/plugin marketplace update slate`, restart Claude Code, then `/slate:upgrade` in each
  project. It migrates the board to schema 2 (adds the `merge_ready` status), installs the merge
  driver, adds `.gitignore` lines, adds new `SLATE.md` sections, and asks before anything else.
- Every clone runs `install-merge-driver` once (git config isn't committed; `.gitattributes`
  is). `/slate:init` and `/slate:upgrade` do it for you.
- Open the board with `python3 kanban/board.py serve` (live mode). The old
  `python3 -m http.server` still works as view-only.
- Copilot CLI support is planned, not included.

## 0.1.0 — 2026-09-26

First release. Board schema **1**.

### Highlights

- Plan ideas into plain-language tickets on a kanban board inside your repo, then build them one
  ticket at a time with tests, review, your own check, and the commit/PR recorded on the ticket
  — always with a human in the loop.

### Added

- **Plugin and marketplace:** `/plugin marketplace add Zidane786/slate`,
  `/plugin install slate@slate`.
- **Six commands:** `/slate:init`, `/slate:plan`, `/slate:work`, `/slate:review`,
  `/slate:status`, `/slate:upgrade`.
- **Board page** (`kanban/index.html`): board and implementation-order views, plain-language
  ticket drawer (summary, story, picture, done when, try it yourself, automated tests, details,
  collapsed technical notes, history), Draft and User testing columns, "needs you" badge, and a
  preview of unsaved tickets from `kanban/preview.json`.
- **`kanban/board.py`**, the only writer of `tickets.json`: `init`, `next`, `list`, `show`,
  `status`, `check`, `version`, `new`, `add` (batch files, `--dry-run` preview, `--as-draft`),
  `batch-check`, `discard-preview`, `set`, `edit`, `rerank`, `promote`, `add-phase`,
  `usertest`, `link`, `set-meta`, `upgrade`, `migrate`. Every write is validated and atomic.
- **Tickets for non-developers:** plain title and summary, story, visual, "When …, then …" test
  scenarios, required user tests for anything visible.
- **Drafts:** saved-but-unfinished tickets that `/slate:work` never picks.
- **Human in the loop:** `/slate:work` builds one ticket per request and stops.
- **Code on the ticket:** `link` records commits and the PR; `done` needs a linked commit (and a
  PR when there's a remote), or `--no-code` / `--no-pr` with your OK.
- **Actionable errors:** every refusal prints `fix:` lines or `ask the user:`.
- **`SLATE.md`:** living per-project context written by `/slate:init`.
- **Hooks:** a session-start board summary, and a guard blocking direct edits to
  `kanban/tickets.json`.
- **Versioning:** every copied file carries its version; skills offer `/slate:upgrade` when the
  board is behind the plugin.

### Upgrade notes

- New install: `/plugin marketplace add Zidane786/slate`, `/plugin install slate@slate`, then
  `/slate:init` in a project.
