# Per-release upgrade steps

One file per plugin version that needs more than "replace the board files and migrate":
`<version>.md`, e.g. `0.2.0.md`. `/slate:upgrade` executes them; people can read them too.

## How `/slate:upgrade` uses them

1. Before changing anything it notes the project's board version (**OLD**, from
   `board.py version`) and picks every file here whose version is **greater than OLD and at most
   the plugin's version**, in ascending version order (compare as numbers: 0.10.0 > 0.9.0). A
   project going from 0.1.0 to 0.4.0 uses `0.2.0.md`, `0.3.0.md`, `0.4.0.md` if they exist.
2. It shows the user each file's **"What's new"** section and asks before upgrading.
3. The general upgrade runs: `board.py upgrade --from "<ROOT>/assets/board"` replaces
   `kanban/board.py`, `index.html`, `README.md` and migrates `tickets.json`.
4. Then it runs each file's steps, file by file, in their numbered order. Each step is skipped
   when its **check** says it isn't needed, so re-running an upgrade is safe.
5. It records one dated line in `SLATE.md`'s `## Slate updates`, runs `doctor` until there are
   no setup problems, and repeats a short "What's new" summary at the end.

Agents learn the new commands without any of this: skills, `reference/commands.md` and the
templates ship inside the plugin, so a plugin update changes their instructions at once. These
files are for the **project's** files and settings.

## Format of a file

```markdown
# Upgrade to X.Y.Z

## What's new

Plain words for the user: what they can now do, one example command each.

## Steps

One paragraph: when these steps run.

### 1. Short title
**Check:** how to tell it's needed — a `board.py doctor` problem code, a command and the output
that means "needed", or a file that lacks a line.
**Do:** exact commands, and the exact questions to ask the user (one at a time, with the
default). Say what to write where.
```

Rules for writing steps:

- Commands are `python3 kanban/board.py …` (the executor swaps in the project's Python command
  from `SLATE.md`). Never hand-edit or read `kanban/tickets.json`; if a step needs ticket data,
  it uses a board.py command (`export --json`, `set-meta`, …).
- Ask before anything that changes meaning or touches files the project owns (`.gitignore`,
  `.gitattributes`, `SLATE.md`, git config). Keep every value the project already set.
  Recommendations (states, workflow rules) are applied only on a yes; the default is "keep".
- Never commit, push or delete data. The upgrade skill shows the diff and the user commits.
- Every step must be idempotent: its check must come back "not needed" once done.
