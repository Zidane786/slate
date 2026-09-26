# Slate

Plan ideas into plain-language tickets on a kanban board in your repo, then build them one at
a time with tests, review, your own check and the commit/PR recorded on the ticket. You stay
in charge: Claude builds one ticket per request, parks it in **Waiting for merge**, and stops;
it moves to Done only after you say the PR is merged.

## Install and update

Install, in a terminal:

```
claude plugin marketplace add Zidane786/slate
claude plugin install slate@slate
```

Update: turn on auto-update once (`/plugin` → **Marketplaces** → **slate** → **Enable
auto-update**), or by hand:

```
claude plugin marketplace update slate
claude plugin update slate@slate
```

Then `/reload-plugins` (or restart), and `/slate:init` in a new project or `/slate:upgrade` in
an existing one.
What changed: https://github.com/Zidane786/slate/releases

| Command | What it does |
|---|---|
| `/slate:init` | Set Slate up in this repo: `kanban/` board + `SLATE.md` (project context, workflow, Python command, board server) |
| `/slate:plan [idea]` | Brainstorm into tickets: story → flow picture → phases → cards → board preview → save as ready or draft. Also bug tickets (`fixes-<ID>`), someday ideas, notes, priorities, remove/restore, phases, custom columns and workflow rules |
| `/slate:work [ID]` | Build one ticket end to end (claimed for its branch), then stop |
| `/slate:review [ID]` | Re-run the review step on the current changes |
| `/slate:status` | Progress, who is on what, waiting for you to test, waiting for merge, drafts, health, next |
| `/slate:sync [branch]` | Sort the board out across branches and worktrees: differences, merge conflicts, repairs |
| `/slate:upgrade` | Update this project's board to the plugin's version, showing what's new first |

**Open the board:** `python3 kanban/board.py serve --ensure` (Slate commands start it for you,
never twice) prints the URL, e.g. http://localhost:8088. That board is **live**: ticks,
Pass/Fail, dragging cards, notes, Promote and Take/Release save to the board through board.py.
Opened any other way (`python3 -m http.server`, the file itself) it is **view-only**, and "Copy
as board.py commands" turns your clicks into commands. Over SSH: `ssh -L 8088:localhost:8088
you@host`.

**Columns and rules:** add, rename, relabel, reorder or remove columns (`add-status qa --after
review --like review --label "QA"`); each follows a built-in role and says whether moving into
it needs a note for the ticket's history (`--note required|optional`, `edit-status NAME note=…`). Optional workflow rules
(`set-meta workflow=strict`, `edit-status qa from=review`) stop tickets skipping steps.
**Parallel work:** `set ID in_progress` claims a ticket for your branch (others skip it); board
writes take turns through a write lock; `/slate:sync`, `board.py diff` / `sync --from` /
`copy-to` and the git merge driver (`install-merge-driver`) keep copies of the board in step.
**Health:** `board.py doctor` lists setup problems (→ `/slate:upgrade`) and board problems
(→ `/slate:sync`). **Hand edits** are blocked; the rare exception is `board.py unlock`, approved
on Claude Code's own permission card (Manual / Accept edits / Auto mode) or by typing a code in
your own terminal (Plan / Bypass / Don't-ask mode). One unlock = one edit.

Every board command for agents: [reference/commands.md](reference/commands.md). Works on macOS,
Linux and Windows (`python3`, `python` or `py -3`). Copilot CLI support: planned.

Full docs, design and source: https://github.com/Zidane786/slate · Changes: [CHANGELOG.md](CHANGELOG.md)
