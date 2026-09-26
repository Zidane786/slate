# Testing Slate on this machine

Hand this file to any coding agent (Claude Code, Codex, Copilot, …) on a fresh clone of the
Slate repo, on **Windows, macOS or Linux**, and say: *"Follow TEST.md and report the results."*

It covers four levels. Do them in order; stop and report at the first level that fails.

| Level | What it proves | Needs |
|---|---|---|
| 1. Automated tests | Every command, rule, hook and the board server work here | Python 3.9+, git, `pytest` |
| 2. Plugin check | Claude Code accepts the plugin | Claude Code CLI |
| 3. Hands-on board | A real board works end to end on this OS | Python, git, a browser |
| 4. Claude Code live | The `/slate:*` skills and hooks work in a real session | Claude Code, optionally tmux |

**Rules for the agent running this:** don't edit Slate's source to make a check pass. Report
failures with the exact command and output. Work only inside a scratch folder for levels 3–4 (never
in a real project). Clean up servers you start.

---

## 0. Record the machine

Run and report:

```
python3 --version || python --version || py -3 --version
git --version
uname -a            # macOS / Linux
ver                 # Windows (cmd) — or: [System.Environment]::OSVersion (PowerShell)
claude --version    # if installed
tmux -V             # if installed
```

Use whichever Python command worked (`python3`, `python` or `py -3`) as `PY` below.

---

## 1. Automated tests

From the repo root:

```
PY -m pip install --user pytest        # or: uv run --with pytest pytest -q
PY -m pytest -q
```

**Expected:** all tests pass (≈800). Report the last line (`N passed …`).

If you have more than one Python, also run the oldest supported one (3.9) if available.

**Windows notes:** run from Git Bash or PowerShell; tests that need `sh` skip themselves when it's
missing. Line endings: the repo must not be converted to CRLF for `tickets.json` fixtures — if many
JSON tests fail, check `git config core.autocrlf` (should be `false` or `input`).

---

## 2. Plugin check (needs Claude Code)

```
claude plugin validate --strict .
claude plugin validate --strict plugins/slate
```

**Expected:** `✔ Validation passed` twice.

---

## 3. Hands-on board (no Claude needed)

Create a scratch project **outside the repo** and copy the board in (this is what `/slate:init`
does):

```
mkdir slate-scratch && cd slate-scratch && git init -q
mkdir kanban
cp <repo>/plugins/slate/assets/board/index.html <repo>/plugins/slate/assets/board/board.py <repo>/plugins/slate/assets/board/README.md kanban/
PY kanban/board.py init --project "Scratch" --prefix SCR
PY kanban/board.py add-phase --id P1 --name "First" --goal "try it" --demo "see a card"
PY kanban/board.py new --title "People can say hello" --summary "A hello page." \
   --story "Sam opens the app and sees hello." --description "Show hello." --phase P1 \
   --areas frontend --acceptance "The page says hello" --test "When I open /, then I see hello" \
   --user-test-json '{"title":"See hello","steps":["Open the app"],"expect":"It says hello","required":true}'
PY kanban/board.py check
PY kanban/board.py show SCR-001
```

**Expected:** `check` reports no errors; `show` prints the ticket in plain sections.

**Board server (live mode):**

```
PY kanban/board.py serve --ensure --port 8088
PY kanban/board.py serve --ensure            # must say it's already running (reused)
PY kanban/board.py serve --status
```

Open the printed URL in a browser. Check and report:

- [ ] Header says **"Live: changes save to the board"**.
- [ ] Drag SCR-001 to *In progress* → it saves (`PY kanban/board.py show SCR-001` shows the new status).
- [ ] Drag it to *Review* → a box asks for a note for the ticket's history; saving it works.
- [ ] Tick "The page says hello" in the drawer → `show` prints it as `[x]`.
- [ ] Run `PY kanban/board.py note SCR-001 "hello from the terminal"` → within ~5 s the page shows it
      in History without reloading ("Board updated").

Then stop it: `PY kanban/board.py serve --stop` (the runtime file `kanban/.slate-serve.json` must be gone).

**View-only mode:** `PY -m http.server 8090` inside `kanban/`, open it, confirm the header says
**"View only"**, drag a card, and check the **"Copy as board.py commands"** button produces a
`set …` command. Stop the server.

**Guard, merge helper, doctor:**

```
PY kanban/board.py install-merge-driver
PY kanban/board.py doctor
```

**Expected:** doctor lists only expected setup items (e.g. missing SLATE.md in a scratch folder)
with a `fix:` line each — no crash.

**Merge helper, for real:**

```
git add -A && git commit -qm base
git checkout -qb a && PY kanban/board.py edit SCR-001 title="Hello from branch A" && git commit -qam a
git checkout -q - && git checkout -qb b && PY kanban/board.py edit SCR-001 summary="Summary from B" && git commit -qam b
git checkout -q a && git merge b -m merge
PY kanban/board.py check && PY kanban/board.py show SCR-001
```

**Expected:** the merge finishes **without conflicts**; the ticket has branch A's title and branch
B's summary; `check` passes.

---

## 4. Claude Code live (the real thing)

Install the plugin from your clone (no marketplace needed):

```
cd slate-scratch
claude --plugin-dir <repo>/plugins/slate
```

In the session, try and report what happens:

- [ ] `/slate:status` → a short report; mentions the board link.
- [ ] `/slate:plan add a goodbye page` → story, flow picture, cards, then a **preview** on the board
      page (dashed cards); answer "save as drafts" → they appear in the Draft column.
- [ ] Ask Claude to edit `kanban/tickets.json` directly → **blocked** with "Change tickets through
      kanban/board.py…".
- [ ] Ask Claude to run `PY kanban/board.py unlock --reason "test"`:
  - in the default / Accept edits / Auto mode → Claude Code shows an **approval card**; answer No →
    nothing unlocks;
  - in Plan mode or with `--permission-mode bypassPermissions` → **refused** with the "run it in your
    own terminal" message.
- [ ] In a **second terminal** (or a second **tmux** pane) run
      `PY kanban/board.py unlock --reason "test" --minutes 5` → it asks you to **type a code**; type it
      → unlocked for **one** edit. Ask Claude for one direct edit (allowed), then a second (blocked).
- [ ] `/slate:work SCR-001` → Claude works on only that ticket and stops at user testing, asking you
      to try it.

**tmux / SSH:** repeat the unlock card and the typed code inside tmux, and over SSH if you can. The
card appears in the same pane; the code prompt works in any interactive pane. Over SSH, open the
board with `ssh -L 8088:localhost:8088 <host>`.

---

## Report format

```
Machine: <OS + version>, Python <ver> (<command>), git <ver>, Claude Code <ver|none>, tmux <ver|none>
Level 1: <N passed / failures with names>
Level 2: <pass/fail>
Level 3: <each checkbox: pass/fail + notes>
Level 4: <each checkbox: pass/fail + notes>
Problems: <exact command + output for every failure>
```

## Cleanup

`PY kanban/board.py serve --stop` in the scratch project, then delete the `slate-scratch` folder.

---

*Maintainers: keep this file in step with the features — see "Keeping docs in step" in CLAUDE.md.*
