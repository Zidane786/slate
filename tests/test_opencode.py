"""OpenCode V2 support: a local plugin in .opencode/plugins/slate talks to Slate's Python guard.

OpenCode has no hooks.json and no Claude-style hook payload. The JS plugin converts the V2 hook
events into the small JSON dialect pinned here and calls guard_tickets.py --opencode. Every
refusal is a decision on stdout (exit 0), because OpenCode's tool/permission hooks surface an
exception as an opaque error and cannot read a Claude-style exit-2 stderr reason.

The Claude Code and Copilot CLI dialects must stay unchanged: tests without --opencode still
cover those (test_guard.py, test_copilot.py).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from conftest import VERSION, Board, base_doc

REPO = Path(__file__).resolve().parents[1]
SLATE_PLUGIN = REPO / "plugins" / "slate"
OPENCODE_PLUGIN = REPO / "plugins" / "opencode"
GUARD = SLATE_PLUGIN / "hooks" / "guard_tickets.py"
MESSAGE = "Change tickets through kanban/board.py (new, add, edit, set, rerank, usertest)."
CWD = "/work/acme"


def run_guard(body: Any, *args: str) -> subprocess.CompletedProcess:
    stdin = body if isinstance(body, str) else json.dumps(body)
    env = {k: v for k, v in os.environ.items() if k != "COPILOT_CLI"}
    return subprocess.run([sys.executable, str(GUARD), "--opencode", *args], input=stdin,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=env, timeout=10)


def pre_edit(*paths: str, cwd: str = CWD) -> Dict[str, Any]:
    return {"tool": "edit", "cwd": cwd, "resources": list(paths)}


def pre_shell(command: str, cwd: str = CWD) -> Dict[str, Any]:
    return {"tool": "shell", "cwd": cwd, "command": command}


def post_shell(command: str, cwd: str = CWD) -> Dict[str, Any]:
    return {"tool": "shell", "cwd": cwd, "command": command}


def decision(r: subprocess.CompletedProcess) -> Dict[str, Any]:
    """Every OpenCode decision is JSON on stdout with exit 0 — never a bare stderr refusal."""
    assert r.returncode == 0, f"exit {r.returncode}: {r.stderr}\n{r.stdout}"
    assert r.stderr == "", r.stderr
    out = json.loads(r.stdout)
    assert out["action"] in ("allow", "deny", "ask")
    if out["action"] != "allow":
        assert isinstance(out.get("reason"), str) and out["reason"]
    return out


# --------------------------------------------------------------------------- the edit permission

def test_edit_tickets_json_is_denied() -> None:
    out = decision(run_guard(pre_edit("kanban/tickets.json")))
    assert out == {"action": "deny", "reason": MESSAGE}


def test_edit_tickets_json_with_absolute_path_is_denied() -> None:
    out = decision(run_guard(pre_edit("/work/acme/kanban/tickets.json")))
    assert out["action"] == "deny"


def test_edit_tickets_json_with_windows_path_is_denied() -> None:
    out = decision(run_guard(pre_edit(r"C:\work\acme\kanban\tickets.json", cwd=r"C:\work\acme")))
    assert out["action"] == "deny"


def test_edit_unlock_or_lock_file_is_denied() -> None:
    for path in ("kanban/.slate-unlock.json", "kanban/.slate-unlock-request.json",
                 "kanban/.slate-write.lock"):
        out = decision(run_guard(pre_edit(path)))
        assert out["action"] == "deny" and "board.py unlock" in out["reason"]


def test_edit_one_of_many_resources_is_denied() -> None:
    out = decision(run_guard(pre_edit("README.md", "src/app.py", "kanban/tickets.json")))
    assert out["action"] == "deny"


def test_edit_unrelated_files_are_allowed() -> None:
    for path in ("README.md", "kanban/board.py", "kanban/index.html", "src/tickets.json"):
        out = decision(run_guard(pre_edit(path)))
        assert out == {"action": "allow"}


def test_edit_is_allowed_after_an_unlock(tmp_path: Path) -> None:
    board = Board(tmp_path)
    board.write(base_doc())
    board.ok("unlock", "--reason", "opencode test", "--minutes", "5")
    decision(run_guard(post_shell("python3 kanban/board.py unlock --reason opencode test", cwd=str(tmp_path)),
                       "--post"))
    out = decision(run_guard(pre_edit("kanban/tickets.json", cwd=str(tmp_path))))
    assert out == {"action": "allow"}
    # one unlock = one edit: the next edit is blocked again
    out = decision(run_guard(pre_edit("kanban/tickets.json", cwd=str(tmp_path))))
    assert out["action"] == "deny" and out["reason"] == MESSAGE


# --------------------------------------------------------------------------- the shell permission

def test_shell_write_to_tickets_json_is_denied() -> None:
    out = decision(run_guard(pre_shell('printf "x" > kanban/tickets.json')))
    assert out["action"] == "deny" and out["reason"].startswith(MESSAGE)


def test_shell_write_to_unlock_file_is_denied() -> None:
    out = decision(run_guard(pre_shell("rm kanban/.slate-unlock.json")))
    assert out["action"] == "deny" and "board.py unlock" in out["reason"]


def test_shell_reads_and_board_commands_are_allowed() -> None:
    for command in ("cat kanban/tickets.json", "python3 kanban/board.py next --brief",
                    "git diff -- kanban/tickets.json", "grep -n tickets.json README.md"):
        out = decision(run_guard(pre_shell(command)))
        assert out == {"action": "allow"}, command


def test_unlock_request_asks_and_names_the_reason() -> None:
    out = decision(run_guard(pre_shell('python3 kanban/board.py unlock --reason "fix it" --minutes 7')))
    assert out["action"] == "ask"
    assert "fix it" in out["reason"] and "7 minutes" in out["reason"]


def test_unlock_chained_with_another_command_is_refused() -> None:
    out = decision(run_guard(pre_shell("python3 kanban/board.py unlock --reason x && echo done")))
    assert out["action"] == "deny"


# --------------------------------------------------------------------------- unlock activation

def test_post_activates_only_an_exact_unlock_command(tmp_path: Path) -> None:
    board = Board(tmp_path)
    board.write(base_doc())
    board.ok("unlock", "--reason", "tmux test", "--minutes", "5")
    out = decision(run_guard(post_shell("echo nope", cwd=str(tmp_path)), "--post"))
    assert out == {"action": "allow"}
    assert not (tmp_path / "kanban" / ".slate-unlock.json").exists()

    out = decision(run_guard(post_shell("python3 kanban/board.py unlock --reason tmux test", cwd=str(tmp_path)),
                             "--post"))
    assert out["action"] == "allow"
    assert (tmp_path / "kanban" / ".slate-unlock.json").is_file()
    assert "ONE direct edit" in out["note"]
    # the approved unlock then allows exactly one edit
    assert decision(run_guard(pre_edit("kanban/tickets.json", cwd=str(tmp_path))))["action"] == "allow"
    assert decision(run_guard(pre_edit("kanban/tickets.json", cwd=str(tmp_path))))["action"] == "deny"


def test_unlock_request_names_opencode_instead_of_the_other_hosts(tmp_path: Path) -> None:
    board = Board(tmp_path)
    board.write(base_doc())
    r = subprocess.run([sys.executable, str(board.script), "unlock", "--reason", "tmux test", "--minutes", "5"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=str(tmp_path), env={**os.environ, "OPENCODE": "1", "COPILOT_CLI": ""}, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "Approve it in OpenCode's permission card" in r.stdout
    assert "Claude Code" not in r.stdout and "Copilot CLI" not in r.stdout
    assert "second tmux pane" in r.stdout


def test_post_without_a_request_does_nothing(tmp_path: Path) -> None:
    out = decision(run_guard(post_shell("python3 kanban/board.py unlock --reason x", cwd=str(tmp_path)), "--post"))
    assert out == {"action": "allow"}
    assert not (tmp_path / "kanban" / ".slate-unlock.json").exists()


def test_post_rejects_a_wrapped_unlock_command(tmp_path: Path) -> None:
    board = Board(tmp_path)
    board.write(base_doc())
    board.ok("unlock", "--reason", "x", "--minutes", "5")
    decision(run_guard(post_shell("bash -c 'python3 kanban/board.py unlock --reason x'", cwd=str(tmp_path)), "--post"))
    assert not (tmp_path / "kanban" / ".slate-unlock.json").exists()


# --------------------------------------------------------------------------- fails open

@pytest.mark.parametrize("body", ["", "not json", "[]", "{}", '{"tool": "unknown"}',
                                   '{"tool": "edit", "resources": 42}'])
def test_malformed_or_unrelated_input_is_allowed(body: str) -> None:
    assert decision(run_guard(body)) == {"action": "allow"}


def test_no_copilot_env_leaks_into_the_dialect() -> None:
    r = subprocess.run([sys.executable, str(GUARD)], input=json.dumps({"tool_input": {"file_path": "README.md"}}),
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "COPILOT_CLI": "1"}, timeout=10)
    assert r.returncode == 0


# --------------------------------------------------------------------------- the shipped plugin folder

def test_opencode_plugin_has_no_runtime_dependencies() -> None:
    assert (OPENCODE_PLUGIN / "index.js").is_file()
    # package.json only marks the local folder as ESM so OpenCode discovers it; no npm install.
    manifest = json.loads((OPENCODE_PLUGIN / "package.json").read_text(encoding="utf-8"))
    assert manifest["type"] == "module" and manifest["main"] == "index.js"
    assert "dependencies" not in manifest and "devDependencies" not in manifest
    source = (OPENCODE_PLUGIN / "index.js").read_text(encoding="utf-8")
    assert "require(" not in source
    # Only Node/Bun built-ins: no npm package is installed for this plugin.
    imports = re.findall(r'from\s+["\']([^"\']+)["\']', source)
    assert all(name.startswith("node:") for name in imports), imports


def test_plugin_registers_the_hooks_it_needs() -> None:
    source = (OPENCODE_PLUGIN / "index.js").read_text(encoding="utf-8")
    for hook in ('session.hook("context"', 'permission.hook("evaluate"', 'tool.hook("execute.after"',
                 'skill.transform'):
        assert hook in source, hook
    assert "--opencode" in source


def test_plugin_ships_the_guard_and_all_skills(tmp_path: Path) -> None:
    assert (OPENCODE_PLUGIN / "hooks" / "guard_tickets.py").read_bytes() == GUARD.read_bytes()
    assert (OPENCODE_PLUGIN / ".claude-plugin" / "plugin.json").is_file()
    source_skills = sorted(p.name for p in (SLATE_PLUGIN / "skills").iterdir() if p.is_dir())
    shipped = sorted(p.name for p in (OPENCODE_PLUGIN / "skills").iterdir() if p.is_dir())
    assert shipped == source_skills
    for name in source_skills:
        src = (SLATE_PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        dst = (OPENCODE_PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert dst == src
    assert (OPENCODE_PLUGIN / "reference" / "commands.md").read_bytes() == \
        (SLATE_PLUGIN / "reference" / "commands.md").read_bytes()


def _relative_files(root: Path) -> set:
    return {str(p.relative_to(root)) for p in root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and ".ruff_cache" not in p.parts
            and p.suffix != ".pyc"}


def _assert_same_tree(source: Path, shipped: Path) -> None:
    assert _relative_files(source) == _relative_files(shipped)
    for rel in _relative_files(source):
        assert (source / rel).read_bytes() == (shipped / rel).read_bytes(), rel


def test_every_copied_file_matches_the_source_plugin() -> None:
    """init/upgrade copy one folder; a stale copy would give OpenCode a different plugin."""
    for folder in ("skills", "assets", "templates", "upgrades"):
        _assert_same_tree(SLATE_PLUGIN / folder, OPENCODE_PLUGIN / folder)
    for rel in ("hooks/guard_tickets.py", "reference/commands.md", "CHANGELOG.md",
                ".claude-plugin/plugin.json"):
        assert (SLATE_PLUGIN / rel).read_bytes() == (OPENCODE_PLUGIN / rel).read_bytes(), rel


def test_no_generated_files_are_shipped() -> None:
    for path in OPENCODE_PLUGIN.rglob("*"):
        assert "__pycache__" not in path.parts, path
        assert ".ruff_cache" not in path.parts, path
        assert path.suffix != ".pyc", path


def test_init_and_upgrade_replace_the_whole_opencode_folder() -> None:
    for name in ("init", "upgrade"):
        text = (SLATE_PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert "rm -rf .opencode/plugins/slate" in text, name
        assert "rm -f .opencode/commands/slate-*.md" in text, name


def test_opencode_plugin_version_matches_the_plugin() -> None:
    manifest = json.loads((OPENCODE_PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["version"] == VERSION


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_plugin_is_valid_javascript() -> None:
    r = subprocess.run(["node", "--check", str(OPENCODE_PLUGIN / "index.js")], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=10)
    assert r.returncode == 0, r.stderr


def test_command_stubs_point_at_the_registered_skills() -> None:
    commands = OPENCODE_PLUGIN / "commands"
    for name in ("init", "plan", "work", "review", "status", "sync", "upgrade"):
        stub = commands / f"slate-{name}.md"
        assert stub.is_file()
        text = stub.read_text(encoding="utf-8")
        assert "description:" in text
        assert f"slate-{name}" in text
