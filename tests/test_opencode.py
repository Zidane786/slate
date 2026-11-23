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
OPENCODE_SRC = SLATE_PLUGIN / "opencode"
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

ASSEMBLED_FILES = (
    "index.js", "package.json", "hooks/guard_tickets.py", "reference/commands.md",
    "CHANGELOG.md", ".claude-plugin/plugin.json", "assets/board/board.py",
    "assets/board/index.html", "assets/board/README.md", "templates/SLATE.md",
    "upgrades/0.5.0.md", "skills/init/SKILL.md", "skills/plan/SKILL.md",
    "skills/work/SKILL.md", "skills/review/SKILL.md", "skills/status/SKILL.md",
    "skills/sync/SKILL.md", "skills/upgrade/SKILL.md",
)


def test_opencode_files_live_inside_the_installed_plugin() -> None:
    assert not (REPO / "plugins" / "opencode").exists()
    assert (OPENCODE_SRC / "index.js").is_file()
    assert (OPENCODE_SRC / "package.json").is_file()
    assert (OPENCODE_SRC / "commands" / "slate-init.md").is_file()


def test_opencode_plugin_has_no_runtime_dependencies() -> None:
    manifest = json.loads((OPENCODE_SRC / "package.json").read_text(encoding="utf-8"))
    assert manifest["type"] == "module" and manifest["main"] == "index.js"
    assert "dependencies" not in manifest and "devDependencies" not in manifest
    for file in OPENCODE_SRC.rglob("*.js"):
        source = file.read_text(encoding="utf-8")
        assert "require(" not in source, file
        imports = re.findall(r'from\s+["\']([^"\']+)["\']', source)
        assert all(name.startswith("node:") for name in imports), (file, imports)


def test_plugin_registers_the_hooks_it_needs() -> None:
    source = (OPENCODE_SRC / "index.js").read_text(encoding="utf-8")
    for hook in ('session.hook("context"', 'permission.hook("evaluate"', 'tool.hook("execute.after"',
                 'skill.transform'):
        assert hook in source, hook
    assert "--opencode" in source


def test_no_generated_files_are_shipped() -> None:
    for path in OPENCODE_SRC.rglob("*"):
        assert "__pycache__" not in path.parts, path
        assert ".ruff_cache" not in path.parts, path
        assert path.suffix != ".pyc", path


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_plugin_is_valid_javascript() -> None:
    for file in OPENCODE_SRC.rglob("*.js"):
        r = subprocess.run(["node", "--check", str(file)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=10)
        assert r.returncode == 0, r.stderr


def test_command_stubs_point_at_the_registered_skills() -> None:
    commands = OPENCODE_SRC / "commands"
    for name in ("init", "plan", "work", "review", "status", "sync", "upgrade"):
        stub = commands / f"slate-{name}.md"
        assert stub.is_file()
        text = stub.read_text(encoding="utf-8")
        assert "description:" in text
        assert f"slate-{name}" in text


def _copy_block(skill: str, kind: str) -> str:
    text = (SLATE_PLUGIN / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(rf"<!-- opencode-copy:{kind} -->\s*```(?:bash|powershell)\n(.*?)\n[ \t]*```",
                      text, re.S)
    assert match, (skill, kind)
    return match.group(1)


def _install_shaped_root(tmp_path: Path) -> Path:
    root = tmp_path / "cache" / "slate" / "slate" / VERSION
    shutil.copytree(SLATE_PLUGIN, root, ignore=shutil.ignore_patterns("__pycache__", ".ruff_cache"))
    return root


def _run_copy(root: Path, project: Path, skill: str = "init") -> subprocess.CompletedProcess:
    script = _copy_block(skill, "bash").replace("<ROOT>", str(root))
    return subprocess.run(["bash", "-c", script], cwd=str(project), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=30)


@pytest.mark.parametrize("skill", ["init", "upgrade"])
def test_install_shaped_copy_assembles_everything_index_needs(tmp_path: Path, skill: str) -> None:
    root = _install_shaped_root(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    r = _run_copy(root, project, skill)
    assert r.returncode == 0, r.stdout + r.stderr

    target = project / ".opencode" / "plugins" / "slate"
    for rel in ASSEMBLED_FILES:
        assert (target / rel).is_file(), rel
    assert (target / "hooks" / "guard_tickets.py").read_bytes() == GUARD.read_bytes()
    assert json.loads((target / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"] \
        == VERSION
    for name in ("init", "plan", "work", "review", "status", "sync", "upgrade"):
        assert (project / ".opencode" / "commands" / f"slate-{name}.md").is_file()


def test_install_shaped_copy_fails_actionably_without_index_js(tmp_path: Path) -> None:
    root = _install_shaped_root(tmp_path)
    (root / "opencode" / "index.js").unlink()
    project = tmp_path / "project"
    project.mkdir()
    r = _run_copy(root, project)
    assert r.returncode != 0
    assert "opencode/index.js" in (r.stdout + r.stderr)
    assert "fix:" in (r.stdout + r.stderr)
    assert not (project / ".opencode" / "plugins" / "slate").exists()


def test_windows_copy_steps_are_documented() -> None:
    for skill in ("init", "upgrade"):
        text = (SLATE_PLUGIN / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        assert "opencode-copy:powershell" in text, skill
        block = _copy_block(skill, "powershell")
        assert "Remove-Item" in block and "Copy-Item" in block and "Test-Path" in block


def test_repo_docs_no_longer_promise_a_duplicated_tree() -> None:
    for name in ("AGENTS.md", "CLAUDE.md"):
        text = (REPO / name).read_text(encoding="utf-8")
        assert "byte-for-byte" not in text, name
        assert "plugins/opencode/" not in text, name


def test_readme_has_an_opencode_only_install_path() -> None:
    root = (REPO / "README.md").read_text(encoding="utf-8")
    assert "`/slate:init` (or `/slate-init` inside OpenCode)" in root
    assert "no Claude Code" in root and "no Copilot" in root and "no npm" in root
    assert "~/.config/opencode/plugins/slate/" in root
    assert "$XDG_CONFIG_HOME/opencode/plugins/slate/" in root
    assert "~/.config/opencode/commands/" in root
    assert "Commit" in root and ".opencode/plugins/slate/" in root
    assert "restart OpenCode" in root


ASSEMBLE = REPO / "scripts" / "assemble_opencode.py"


def _run_assemble(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ASSEMBLE), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=30, **kwargs)


def test_standalone_assembly_builds_a_project_plugin(tmp_path: Path) -> None:
    root = _install_shaped_root(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    r = _run_assemble("--root", str(root), "--project", str(project))
    assert r.returncode == 0, r.stdout + r.stderr
    target = project / ".opencode" / "plugins" / "slate"
    for rel in ASSEMBLED_FILES:
        assert (target / rel).is_file(), rel
    for name in ("init", "plan", "work", "review", "status", "sync", "upgrade"):
        assert (project / ".opencode" / "commands" / f"slate-{name}.md").is_file()
    assert "restart opencode" in r.stdout.lower()


def test_standalone_assembly_supports_the_global_path(tmp_path: Path) -> None:
    root = _install_shaped_root(tmp_path)
    xdg = tmp_path / "xdg"
    env = {**os.environ, "XDG_CONFIG_HOME": str(xdg)}
    r = _run_assemble("--root", str(root), "--global", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    base = xdg / "opencode"
    assert (base / "plugins" / "slate" / "index.js").is_file()
    assert (base / "commands" / "slate-init.md").is_file()
    assert str(base / "plugins" / "slate") in r.stdout


def test_standalone_assembly_replaces_stale_files(tmp_path: Path) -> None:
    root = _install_shaped_root(tmp_path)
    (root / "opencode" / "index.js").write_text("// changed\n", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    target = project / ".opencode" / "plugins" / "slate"
    target.mkdir(parents=True)
    (target / "stale.js").write_text("old", encoding="utf-8")
    assert _run_assemble("--root", str(root), "--project", str(project)).returncode == 0
    assert not (target / "stale.js").exists()
    assert (target / "index.js").read_text(encoding="utf-8") == "// changed\n"


def test_standalone_assembly_fails_actionably_without_index_js(tmp_path: Path) -> None:
    root = _install_shaped_root(tmp_path)
    (root / "opencode" / "index.js").unlink()
    project = tmp_path / "project"
    project.mkdir()
    r = _run_assemble("--root", str(root), "--project", str(project))
    assert r.returncode != 0
    assert "opencode/index.js" in (r.stdout + r.stderr)
    assert "fix:" in (r.stdout + r.stderr)
    assert not (project / ".opencode" / "plugins" / "slate").exists()


def test_all_opencode_docs_mention_the_restart_after_upgrade() -> None:
    for rel in ("plugins/slate/README.md", "plugins/slate/assets/board/README.md",
                "plugins/slate/reference/commands.md", "plugins/slate/templates/SLATE.md",
                "docs/specs/2026-09-26-slate-design.md",
                "docs/plans/2026-11-23-opencode-v2-build-plan.md"):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "restart OpenCode" in text.lower() or "restart opencode" in text.lower(), rel
