"""Tests for plugins/slate/hooks/run.sh, the POSIX sh launcher for the hook scripts.

The launcher picks the first of python3, python, "py -3" that is Python 3.9+, runs the script
relative to the hooks folder with stdin and args passed through, and exits 0 quietly (one
stderr line) when no Python is found. Fake interpreters are small sh scripts, so those tests
run only where a POSIX sh can execute them (not native Windows).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

import pytest

from conftest import VERSION

REPO = Path(__file__).resolve().parents[1]
RUN_SH = REPO / "plugins" / "slate" / "hooks" / "run.sh"
SH = shutil.which("sh")

pytestmark = pytest.mark.skipif(SH is None, reason="no POSIX sh on this machine")
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="fake sh interpreters need a POSIX system")


def _hooks_dir(tmp_path: Path) -> Path:
    hooks = tmp_path / "plugin" / "hooks"
    hooks.mkdir(parents=True)
    shutil.copy(RUN_SH, hooks / "run.sh")
    return hooks


def _run(hooks: Path, args: List[str], env_path: str, stdin: str = "") -> subprocess.CompletedProcess:
    env: Dict[str, str] = {k: v for k, v in os.environ.items() if k not in ("PATH",)}
    env["PATH"] = env_path
    return subprocess.run(
        [str(SH), str(hooks / "run.sh"), *args],
        input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(hooks.parent.parent), timeout=60,
    )


def _fake(bin_dir: Path, name: str, body: str) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    p = bin_dir / name
    p.write_bytes(("#!/bin/sh\n" + body).encode("utf-8"))  # LF endings on every OS (3.9: no newline=)
    p.chmod(0o755)


def test_runs_script_with_real_python_passing_args_and_stdin(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    (hooks / "echo_hook.py").write_text(
        "import sys\n"
        "data = sys.stdin.read()\n"
        "print('ok', sys.version_info >= (3, 9), sys.argv[1:], data.strip())\n",
        encoding="utf-8",
    )
    r = _run(hooks, ["echo_hook.py", "--post", "two words"], os.environ.get("PATH", ""), stdin='{"tool": "Bash"}\n')
    if "no Python 3.9+" in r.stderr:
        pytest.skip("no python3/python/py -3 on PATH for sh")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "ok True ['--post', 'two words'] {\"tool\": \"Bash\"}"


def test_exit_code_of_script_passes_through(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    (hooks / "block.py").write_text("import sys\nprint('blocked', file=sys.stderr)\nsys.exit(2)\n", encoding="utf-8")
    r = _run(hooks, ["block.py"], os.environ.get("PATH", ""))
    if "no Python 3.9+" in r.stderr:
        pytest.skip("no python3/python/py -3 on PATH for sh")
    assert r.returncode == 2
    assert "blocked" in r.stderr


@posix_only
def test_no_python_prints_one_stderr_line_and_exits_0(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    r = _run(hooks, ["guard_tickets.py"], str(empty), stdin="{}")
    assert r.returncode == 0
    assert r.stdout == ""
    lines = [ln for ln in r.stderr.splitlines() if ln.strip()]
    assert len(lines) == 1 and "no Python 3.9+" in lines[0]


@posix_only
def test_missing_script_argument_is_quiet_exit_0(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    r = _run(hooks, [], str(tmp_path))
    assert r.returncode == 0
    assert r.stdout == ""


@posix_only
def test_skips_too_old_python3_and_uses_python(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    fake_bin = tmp_path / "bin"
    _fake(fake_bin, "python3", 'if [ "$1" = "-c" ]; then exit 1; fi\necho "python3 $*"\n')
    _fake(fake_bin, "python", 'if [ "$1" = "-c" ]; then exit 0; fi\necho "python $*"\n')
    r = _run(hooks, ["guard_tickets.py", "--post"], str(fake_bin))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f"python {hooks}/guard_tickets.py --post"


@posix_only
def test_prefers_python3_when_it_is_new_enough(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    fake_bin = tmp_path / "bin"
    _fake(fake_bin, "python3", 'if [ "$1" = "-c" ]; then exit 0; fi\necho "python3 $*"\n')
    _fake(fake_bin, "python", 'if [ "$1" = "-c" ]; then exit 0; fi\necho "python $*"\n')
    r = _run(hooks, ["guard_tickets.py"], str(fake_bin))
    assert r.stdout.strip() == f"python3 {hooks}/guard_tickets.py"


@posix_only
def test_falls_back_to_py_launcher(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    fake_bin = tmp_path / "bin"
    _fake(fake_bin, "py", 'if [ "$1" = "-3" ] && [ "$2" = "-c" ]; then exit 0; fi\necho "py $*"\n')
    r = _run(hooks, ["guard_tickets.py", "a b"], str(fake_bin))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f"py -3 {hooks}/guard_tickets.py a b"


@posix_only
def test_absolute_script_path_is_kept(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    fake_bin = tmp_path / "bin"
    _fake(fake_bin, "python3", 'if [ "$1" = "-c" ]; then exit 0; fi\necho "python3 $*"\n')
    target = tmp_path / "elsewhere" / "x.py"
    r = _run(hooks, [str(target)], str(fake_bin))
    assert r.stdout.strip() == f"python3 {target}"


@posix_only
def test_version_probe_does_not_eat_hook_stdin(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    fake_bin = tmp_path / "bin"
    # The probe would swallow stdin if it were not redirected from /dev/null.
    _fake(fake_bin, "python3", 'if [ "$1" = "-c" ]; then while IFS= read -r x; do :; done; exit 0; fi\nIFS= read -r l; echo "got: $l"\n')
    r = _run(hooks, ["guard_tickets.py"], str(fake_bin), stdin="HOOK-JSON")
    assert r.stdout.strip() == "got: HOOK-JSON"


# --------------------------------------------------------------------------- the real hooks through run.sh

PLUGIN = REPO / "plugins" / "slate"
BOARD_SRC = PLUGIN / "assets" / "board" / "board.py"


def test_hooks_json_runs_every_hook_through_run_sh() -> None:
    import json as _json
    hooks = _json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    cmds = {event: [h["command"] for entry in entries for h in entry["hooks"]] for event, entries in hooks.items()}
    prefix = 'sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" '
    assert cmds["SessionStart"] == [prefix + "session_start.py"]
    assert cmds["PreToolUse"] == [prefix + "guard_tickets.py"]
    assert cmds["PostToolUse"] == [prefix + "guard_tickets.py --post"]
    for script in ("session_start.py", "guard_tickets.py"):
        assert (PLUGIN / "hooks" / script).is_file()
    assert "python3 " not in (PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8")


def _real_hooks(tmp_path: Path) -> Path:
    hooks = _hooks_dir(tmp_path)
    for name in ("session_start.py", "guard_tickets.py"):
        shutil.copy(PLUGIN / "hooks" / name, hooks / name)
    return hooks


def _project(tmp_path: Path) -> Path:
    import json as _json
    proj = tmp_path / "proj"
    (proj / "kanban").mkdir(parents=True)
    shutil.copy(BOARD_SRC, proj / "kanban" / "board.py")
    (proj / "kanban" / "tickets.json").write_text(_json.dumps({
        "meta": {"project": "Acme", "prefix": "ACME", "slate_version": VERSION, "schema_version": 2,
                 "generated": "2026-09-26", "statuses": ["draft", "backlog", "ready", "in_progress", "review",
                                                         "user_testing", "merge_ready", "done"],
                 "areas": ["backend"], "priorities": ["P0", "P1", "P2", "P3"], "user_test_areas": ["ui"]},
        "phases": [], "tickets": []}), encoding="utf-8")
    return proj


def _run_hook(hooks: Path, args: List[str], cwd: Path, env_extra: Dict[str, str], stdin: str = "") -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "SLATE_PYTHON")}
    env.update(env_extra)
    return subprocess.run([str(SH), str(hooks / "run.sh"), *args], input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=env, cwd=str(cwd), timeout=60)


def test_session_start_through_run_sh(tmp_path: Path) -> None:
    hooks = _real_hooks(tmp_path)
    proj = _project(tmp_path)
    r = _run_hook(hooks, ["session_start.py"], tmp_path, {"CLAUDE_PROJECT_DIR": str(proj),
                                                          "CLAUDE_PLUGIN_ROOT": str(PLUGIN)})
    if "no Python 3.9+" in r.stderr:
        pytest.skip("no python3/python/py -3 on PATH for sh")
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith(f"Slate {VERSION}: ") and "no tickets yet" in r.stdout
    # without CLAUDE_PROJECT_DIR the current directory is the project
    r = _run_hook(hooks, ["session_start.py"], proj, {"CLAUDE_PLUGIN_ROOT": str(PLUGIN)})
    assert r.stdout.startswith(f"Slate {VERSION}: ")


def test_session_start_includes_the_live_board_url(tmp_path: Path) -> None:
    import json as _json
    hooks = _real_hooks(tmp_path)
    proj = _project(tmp_path)
    (proj / "kanban" / ".slate-serve.json").write_text(_json.dumps({
        "pid": os.getpid(), "host": "127.0.0.1", "port": 8123, "url": "http://127.0.0.1:8123/",
        "started": "2026-09-26T10:00:00Z", "board_path": str((proj / "kanban" / "tickets.json").resolve()),
        "slate_version": VERSION}), encoding="utf-8")
    r = _run_hook(hooks, ["session_start.py"], proj, {"CLAUDE_PROJECT_DIR": str(proj), "CLAUDE_PLUGIN_ROOT": str(PLUGIN)})
    if "no Python 3.9+" in r.stderr:
        pytest.skip("no python3/python/py -3 on PATH for sh")
    assert "board page live at http://127.0.0.1:8123/" in r.stdout


def test_session_start_without_a_board_is_silent(tmp_path: Path) -> None:
    hooks = _real_hooks(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    r = _run_hook(hooks, ["session_start.py"], empty, {"CLAUDE_PROJECT_DIR": str(empty)})
    assert r.returncode == 0 and r.stdout == ""


def test_guard_through_run_sh_blocks_and_allows(tmp_path: Path) -> None:
    import json as _json
    hooks = _real_hooks(tmp_path)

    def payload(path: str) -> str:
        return _json.dumps({"hook_event_name": "PreToolUse", "cwd": "/work/acme", "tool_name": "Write",
                            "tool_input": {"file_path": path, "content": "{}"}})

    r = _run_hook(hooks, ["guard_tickets.py"], tmp_path, {}, stdin=payload("/work/acme/kanban/tickets.json"))
    if "no Python 3.9+" in r.stderr:
        pytest.skip("no python3/python/py -3 on PATH for sh")
    assert r.returncode == 2 and "kanban/board.py" in r.stderr
    r = _run_hook(hooks, ["guard_tickets.py"], tmp_path, {}, stdin=payload("/work/acme/src/app.py"))
    assert r.returncode == 0
    r = _run_hook(hooks, ["guard_tickets.py", "--post"], tmp_path, {}, stdin=_json.dumps(
        {"hook_event_name": "PostToolUse", "cwd": str(tmp_path), "tool_name": "Bash", "tool_input": {"command": "ls"}}))
    assert r.returncode == 0


@posix_only
def test_run_sh_tells_board_py_which_python_it_picked(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    fake_bin = tmp_path / "bin"
    _fake(fake_bin, "py", 'if [ "$1" = "-3" ] && [ "$2" = "-c" ]; then exit 0; fi\necho "SLATE_PYTHON=$SLATE_PYTHON"\n')
    r = _run(hooks, ["session_start.py"], str(fake_bin))
    assert r.stdout.strip() == "SLATE_PYTHON=py -3"
