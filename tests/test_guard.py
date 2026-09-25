"""Tests for plugins/slate/hooks/guard_tickets.py, fed JSON on stdin like Claude Code does."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[1] / "plugins" / "slate" / "hooks" / "guard_tickets.py"
MESSAGE = "Change tickets through kanban/board.py (new, add, edit, set, rerank, usertest)."


def run_guard(stdin: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=10,
    )


def payload(tool: str, tool_input: dict, cwd: str = "/work/acme") -> str:
    return json.dumps(
        {
            "session_id": "s1",
            "transcript_path": "/tmp/t.jsonl",
            "cwd": cwd,
            "hook_event_name": "PreToolUse",
            "tool_name": tool,
            "tool_input": tool_input,
        }
    )


@pytest.mark.parametrize(
    "tool,tool_input",
    [
        ("Edit", {"file_path": "/work/acme/kanban/tickets.json", "old_string": "a", "new_string": "b"}),
        ("Write", {"file_path": "/work/acme/kanban/tickets.json", "content": "{}"}),
        ("MultiEdit", {"file_path": "/work/acme/kanban/tickets.json", "edits": [{"old_string": "a", "new_string": "b"}]}),
        ("NotebookEdit", {"notebook_path": "/work/acme/kanban/tickets.json", "new_source": "x"}),
    ],
)
def test_blocks_every_tool_shape(tool: str, tool_input: dict) -> None:
    result = run_guard(payload(tool, tool_input))
    assert result.returncode == 2
    assert result.stderr.strip() == MESSAGE
    assert result.stdout == ""


def test_relative_path_resolved_against_hook_cwd(tmp_path: Path) -> None:
    result = run_guard(payload("Write", {"file_path": "kanban/tickets.json", "content": "{}"}, cwd="/work/acme"), cwd=tmp_path)
    assert result.returncode == 2


def test_relative_path_with_dotdot_that_escapes_kanban_is_allowed() -> None:
    result = run_guard(payload("Write", {"file_path": "kanban/../tickets.json", "content": "{}"}))
    assert result.returncode == 0


def test_dotdot_that_lands_in_kanban_is_blocked() -> None:
    result = run_guard(payload("Edit", {"file_path": "/work/acme/src/../kanban/./tickets.json"}))
    assert result.returncode == 2


def test_relative_path_without_cwd_uses_process_cwd(tmp_path: Path) -> None:
    body = json.dumps({"tool_name": "Write", "tool_input": {"file_path": "kanban/tickets.json"}})
    assert run_guard(body, cwd=tmp_path).returncode == 2


@pytest.mark.parametrize(
    "path",
    [
        "/work/acme/kanban/board.py",
        "/work/acme/kanban/preview.json",
        "/work/acme/kanban/index.html",
        "/work/acme/tickets.json",
        "/work/acme/notkanban/tickets.json",
        "/work/acme/kanban/tickets.json.bak",
        "/work/acme/kanban/tickets.json/x",
        "/tmp/scratch/batch.json",
        "/work/acme/kanban/.batch.json",
    ],
)
def test_allows_other_files(path: str) -> None:
    result = run_guard(payload("Write", {"file_path": path, "content": ""}))
    assert result.returncode == 0
    assert result.stderr == ""


@pytest.mark.parametrize(
    "stdin",
    [
        "",
        "not json",
        "[]",
        "null",
        '"a string"',
        "{}",
        '{"tool_input": null}',
        '{"tool_input": "x"}',
        '{"tool_input": {"file_path": 42}}',
        '{"tool_input": {"file_path": ""}}',
        '{"tool_input": {"file_path": "kanban/tickets.json"}, "cwd": 7}',
        '{"tool_name": "Bash", "tool_input": {"command": "cat kanban/tickets.json"}}',
    ],
)
def test_malformed_or_unrelated_input_never_crashes(stdin: str, tmp_path: Path) -> None:
    result = run_guard(stdin, cwd=tmp_path)
    # the cwd=7 case falls back to the process cwd and correctly blocks; everything else passes
    if '"cwd": 7' in stdin:
        assert result.returncode == 2
    else:
        assert result.returncode == 0
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "echo '{}' > kanban/tickets.json",
        "cat new.json >> kanban/tickets.json",
        "sed -i '' 's/backlog/done/' kanban/tickets.json",
        "sed -i 's/backlog/done/' kanban/tickets.json",
        "python3 -c \"open('kanban/tickets.json','w').write('{}')\"",
        "cp /tmp/x.json kanban/tickets.json",
        "mv /tmp/x.json kanban/Tickets.json",
        "rm kanban/tickets.json",
        "jq '.x=1' kanban/tickets.json | tee kanban/tickets.json",
        "git checkout -- kanban/tickets.json",
        "python3 kanban/board.py check && echo {} > kanban/tickets.json",
    ],
)
def test_bash_writes_to_tickets_are_blocked(command: str, tmp_path: Path) -> None:
    result = run_guard(payload("Bash", {"command": command}), cwd=tmp_path)
    assert result.returncode == 2, command
    assert MESSAGE in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "cat kanban/tickets.json",
        "grep -n NOTE-001 kanban/tickets.json",
        "jq '.tickets | length' kanban/tickets.json",
        "python3 -m json.tool kanban/tickets.json > /dev/null",
        "git add kanban/tickets.json && git commit -m 'NOTE-001: close on board'",
        "git diff kanban/tickets.json 2>&1",
        "python3 kanban/board.py set NOTE-001 done --handoff 'wrote tickets.json via board'",
        "echo hello > notes.txt",
        "ls kanban",
    ],
)
def test_bash_reads_and_board_py_pass(command: str, tmp_path: Path) -> None:
    result = run_guard(payload("Bash", {"command": command}), cwd=tmp_path)
    assert result.returncode == 0, (command, result.stderr)


@pytest.mark.parametrize("path", ["Kanban/Tickets.json", "KANBAN/TICKETS.JSON", "kanban/Tickets.json"])
def test_case_variants_are_blocked(path: str, tmp_path: Path) -> None:
    result = run_guard(payload("Write", {"file_path": path, "content": "{}"}, cwd=str(tmp_path)))
    assert result.returncode == 2
