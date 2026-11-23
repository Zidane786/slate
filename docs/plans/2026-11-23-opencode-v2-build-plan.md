# Slate v0.5 build plan

Version **0.5.0**, board schema **3** (unchanged), planned for release 2026-11-23.

*Working plan for the `feat/0.5.0` branch. It records the contracts 0.5.0 holds to; the design is
spec decision 26 and §8.3. Existing contracts in the v0.1–v0.4 build plans still hold, and the
Claude Code and Copilot CLI payloads are unchanged.*

## Goal

**OpenCode V2 support with full parity, in a local plugin folder.** OpenCode 2.x has no
`hooks.json` and no Claude-style hook payload, so Slate ships a small dependency-free `index.js`
that translates V2 hook events into the same Python guard the other hosts use. `/slate:init` and
`/slate:upgrade` copy the folder into the project; there is no npm package, no global install and
no `plugins` config entry. One board and one unlock contract are shared by all three hosts.

**Not in scope:** OpenCode V1 (its function-returning hooks and dual npm entry can come later),
VS Code Copilot Chat, and any hosted board.

## What OpenCode V2 does differently (measured in 2.3.2) and the contract for each

| OpenCode V2 does | Contract |
|---|---|
| Discovers a local plugin from `.opencode/plugins/<name>/`; `package.json` with `"type": "module"` and `"main": "index.js"` marks it as ESM | `plugins/slate/opencode/` holds only the JS plugin, manifest and stubs; init/upgrade assemble them with the installed plugin's shared files into `.opencode/plugins/slate/`. No npm install and no `plugins` entry in `opencode.jsonc`. |
| Loads a default-export plugin object `{ id, setup }`; project root is `ctx.location.directory` | `index.js` resolves the guard and skills relative to its own file, and uses the project root for board commands. |
| `session.hook("context")` receives an event with a `system` array | Compose the same `next --brief --against <ROOT>` line into ONE system text part; title calls use the separate `session.hook("title")` and are not touched. |
| `permission.hook("evaluate")` gets `{ action, resources, effect, message }`; actions are `edit`, `write`, `shell`, … | Call `guard_tickets.py --opencode`, which answers `allow` / `deny` / `ask`; set `event.effect` and `event.message`, so the refusal reason is visible in the TUI. |
| `tool.hook("execute.after")` gets `input.command` for shell tools | Run `--post` so an approved `board.py unlock` creates exactly one edit unlock; send the note via `ctx.session.synthetic` when a session ID is available. |
| `skill.transform` editors expose `add`, and command stubs say “Use the slate-init skill” | Register all seven `SKILL.md` files as `slate-<name>` so names match the `/slate-*` stubs; rewrite `${CLAUDE_PLUGIN_ROOT}` to the copied folder. |
| Sets `OPENCODE=1` in the agent shell; a non-interactive `opencode run` has no approval card | `board.py unlock` names OpenCode’s “Allow once” card and the second-pane typed-code fallback. |
| A stale background service can hide plugin changes; `opencode run` has no card | Hands-on tests use `opencode --standalone` in tmux; users restart OpenCode (or its background service) after init/upgrade; the guard fails open if the JS/Python bridge breaks, so unrelated tools keep working. |
| OpenCode-only users have no Claude Code or Copilot install to run init from | `scripts/assemble_opencode.py --root <release>/plugins/slate` (`--project` or `--global`) builds the same folder from a download/clone; tested with OpenCode 2.3.2. |

`--opencode` is one more dialect inside the same Python guard: JSON in, one JSON decision on
stdout, exit 0. Claude Code (exit 2 + stderr) and Copilot CLI (`permissionDecision`,
`COPILOT_CLI`) are untouched. One unlock = one edit and “change tickets through board.py” are
shared by all three hosts.

## Files

- **New `plugins/slate/opencode/`:** `index.js`, dependency-free `package.json` and seven command
  stubs. init/upgrade assemble the project plugin from these plus ROOT's skills, guard, board
  assets, templates, reference, upgrades, CHANGELOG and `plugin.json`, with bash and PowerShell
  copy steps and an actionable error if `index.js` is missing.
- `hooks/guard_tickets.py`: `--opencode` decision dialect and `--opencode --post` activation.
- `assets/board/board.py`: OpenCode wording for `unlock`; version 0.5.0.
- `assets/board/index.html`, `templates/SLATE.md`, plugin manifest: version 0.5.0.
- Skills: init/upgrade copy or refresh the whole OpenCode folder, add command stubs and add
  `"SLATE.md"` to `instructions` in `opencode.jsonc`; the shared reference and all skills name
  the three hosts and OpenCode’s no-colon commands.
- Docs: both READMEs, board README, `reference/commands.md`, `TEST.md` level 6, spec decision 26
  and §8.3, `AGENTS.md` / `CLAUDE.md`, CHANGELOG 0.5.0, `upgrades/0.5.0.md`,
  `scripts/release_notes.py`.
- CI already watches `plugins/**`, so the new folder needs no workflow change.

## Tests

`tests/test_opencode.py` pins every row of the table above: the JSON decision dialect (edit,
shell, unlock requests, chained commands, malformed input, one-edit consumption), the shipped
folder (no runtime dependencies, all seven skills and stubs, no generated caches), an
install-shaped copy of `plugins/slate` at `cache/slate/slate/0.5.0/` that assembles every file
`index.js` needs, the missing-`index.js` refusal, Windows copy steps, Node syntax, and the
OpenCode-specific unlock wording. `tests/conftest.py` clears `OPENCODE` so the existing Claude/Copilot tests remain
explicit. Docs consistency and release-notes tests cover the new command names and CHANGELOG
section.

## Verification

- Full suite on Python 3.13 and 3.9: **987 passed, 4 skipped** on both.
- `claude plugin validate --strict .` and `claude plugin validate --strict plugins/slate`: passed.
- Live in OpenCode 2.3.2 in tmux (`--standalone`): plugin discovered, context line reached the
  model, `/slate-status` registered, a direct edit of `tickets.json` was denied with the
  `fix:` reason, and **Allow once** activated one edit followed by a block on the second.
- Live in the user’s project: `opencode plugin list` reports `slate  local` at
  `.opencode/plugins/slate`, the session ID resolves in that project, and the guard denial is
  visible in the TUI.
- Claude Code and Copilot CLI behaviour unchanged (existing host suites remain green).

## Still open

- Finish `TEST.md` level 6’s typed-code fallback and board-server checks with the user in the
  live session before merge.
- OpenCode V1 support and VS Code Copilot Chat remain out of scope.
