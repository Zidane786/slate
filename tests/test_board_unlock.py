"""Tests for board.py unlock / lock (#21) and the guard's PostToolUse activation (C-21b), end to end.
The terminal is simulated by replacing board.py's is_interactive / new_code / read_code; no real prompts."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from conftest import Board, base_doc, full_ticket

GUARD = Path(__file__).resolve().parents[1] / "plugins" / "slate" / "hooks" / "guard_tickets.py"
V2 = ["draft", "backlog", "ready", "in_progress", "review", "user_testing", "merge_ready", "done"]


@pytest.fixture
def b(board: Board) -> Board:
    d = base_doc([full_ticket(1), full_ticket(2)])
    d["meta"].update({"slate_version": "0.2.0", "schema_version": 2, "statuses": list(V2)})
    board.write(d)
    return board


def load_module(board: Board) -> Any:
    spec = importlib.util.spec_from_file_location(f"slate_unlock_{abs(hash(str(board.script)))}", board.script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def terminal(mod: Any, monkeypatch: pytest.MonkeyPatch, typed: str, code: str = "ABCD") -> List[str]:
    prompts: List[str] = []
    monkeypatch.setattr(mod, "is_interactive", lambda: True)
    monkeypatch.setattr(mod, "new_code", lambda: code)

    def read(prompt: str) -> str:
        prompts.append(prompt)
        return typed

    monkeypatch.setattr(mod, "read_code", read)
    return prompts


def log(board: Board) -> List[Dict[str, Any]]:
    return board.load()["meta"].get("unlock_log", [])


def iso(delta_minutes: float = 0) -> str:
    t = datetime.now(timezone.utc) + timedelta(minutes=delta_minutes)
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def guard(payload: Dict[str, Any], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(GUARD), *args], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)


def post(root: Path, command: str = "python3 kanban/board.py unlock --reason 'fix merge'",
         mode: Any = "default") -> subprocess.CompletedProcess:
    p: Dict[str, Any] = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": str(root),
                         "tool_input": {"command": command}, "tool_response": {"stdout": "", "stderr": ""}}
    if mode is not None:
        p["permission_mode"] = mode
    return guard(p, "--post")


def edit(root: Path) -> subprocess.CompletedProcess:
    return guard({"hook_event_name": "PreToolUse", "tool_name": "Edit", "cwd": str(root),
                  "tool_input": {"file_path": str(root / "kanban" / "tickets.json"), "old_string": "a",
                                 "new_string": "b"}})


# --------------------------------------------------------------------------- terminal path


def test_unlock_in_terminal_with_right_code(b: Board, monkeypatch: pytest.MonkeyPatch,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    mod = load_module(b)
    prompts = terminal(mod, monkeypatch, typed="abcd ")
    assert mod.main(["unlock", "--reason", "fix a merge by hand", "--minutes", "7"]) == 0
    assert "Type ABCD" in prompts[0]
    rec = json.loads((b.dir / ".slate-unlock.json").read_text(encoding="utf-8"))
    assert rec["approved"] == "terminal code" and rec["reason"] == "fix a merge by hand" and rec["minutes"] == 7
    until = datetime.fromisoformat(rec["until"].replace("Z", "+00:00"))
    assert timedelta(minutes=6) < until - datetime.now(timezone.utc) <= timedelta(minutes=7)
    assert not (b.dir / ".slate-unlock-request.json").exists()
    assert log(b)[-1]["event"] == "activated" and log(b)[-1]["approved"] == "terminal code"
    assert "Unlocked: ONE direct edit" in capsys.readouterr().out


def test_unlock_in_terminal_with_wrong_code(b: Board, monkeypatch: pytest.MonkeyPatch,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    mod = load_module(b)
    terminal(mod, monkeypatch, typed="WXYZ")
    assert mod.main(["unlock", "--reason", "fix"]) == 1
    assert not (b.dir / ".slate-unlock.json").exists()
    assert log(b)[-1]["event"] == "refused"
    err = capsys.readouterr().err
    assert "the code didn't match" in err and "fix:" in err


def test_unlock_needs_reason_and_sane_minutes(b: Board) -> None:
    assert "--reason is required" in b.fail("unlock").stderr
    assert "must be 1 to 30" in b.fail("unlock", "--reason", "x", "--minutes", "45").stderr
    assert not (b.dir / ".slate-unlock-request.json").exists()


# --------------------------------------------------------------------------- agent path: request only


def test_unlock_non_interactive_writes_only_a_request(b: Board) -> None:
    r = b.ok("unlock", "--reason", "fix merge", "--minutes", "5")  # pipes, not a terminal
    assert "Unlock requested (not active yet)" in r.stdout and "permission prompt" in r.stdout
    assert "python3 kanban/board.py unlock --reason 'fix merge' --minutes 5" in r.stdout
    assert not (b.dir / ".slate-unlock.json").exists()
    req = json.loads((b.dir / ".slate-unlock-request.json").read_text(encoding="utf-8"))
    assert req["reason"] == "fix merge" and req["minutes"] == 5 and req["id"] and req["created"]
    assert log(b)[-1]["event"] == "requested"
    assert edit(b.root).returncode == 2  # a request never unlocks anything


def test_lock_removes_unlock_and_request(b: Board) -> None:
    (b.dir / ".slate-unlock.json").write_text(json.dumps({"until": iso(5), "reason": "r"}), encoding="utf-8")
    b.ok("unlock", "--reason", "again")
    r = b.ok("lock")
    assert "active unlock" in r.stdout and "pending request" in r.stdout
    assert not (b.dir / ".slate-unlock.json").exists() and not (b.dir / ".slate-unlock-request.json").exists()
    assert log(b)[-1]["event"] == "locked"
    assert "no active unlock" in b.ok("lock").stdout


def test_check_and_status_warn_while_active(b: Board) -> None:
    (b.dir / ".slate-unlock.json").write_text(json.dumps({"until": iso(5), "reason": "hand fix"}), encoding="utf-8")
    out = b.ok("check").stdout
    assert "warning: an unlock is active until" in out and "hand fix" in out and "fix: python3 kanban/board.py lock" in out
    assert "an unlock is active" in b.ok("status").stdout
    assert json.loads(b.ok("check", "--json").stdout)["unlock"]
    b.ok("lock")
    assert "unlock" not in b.ok("check").stdout


# --------------------------------------------------------------------------- log folding


def test_used_and_expired_records_fold_into_the_log(b: Board) -> None:
    (b.dir / ".slate-unlock.used.json").write_text(json.dumps({
        "until": iso(3), "reason": "fix", "minutes": 5, "created": iso(-2), "activated": iso(-1),
        "approved": "permission prompt", "permission_mode": "auto", "used_at": iso(0), "tool": "Edit"}),
        encoding="utf-8")
    b.ok("edit", "ACME-001", "estimate=2d")
    events = [(e["event"], e.get("permission_mode")) for e in log(b)]
    assert events == [("activated", "auto"), ("used", None)]
    assert log(b)[1]["tool"] == "Edit"
    assert not (b.dir / ".slate-unlock.used.json").exists()
    (b.dir / ".slate-unlock.json").write_text(json.dumps({"until": iso(-1), "reason": "old"}), encoding="utf-8")
    b.ok("edit", "ACME-001", "estimate=3d")
    assert log(b)[-1]["event"] == "expired" and not (b.dir / ".slate-unlock.json").exists()


def test_unlock_on_unreadable_board_keeps_log_pending(b: Board) -> None:
    good = b.tickets.read_text(encoding="utf-8")
    b.tickets.write_text("<<<<<<< HEAD\n{broken\n", encoding="utf-8")
    b.ok("unlock", "--reason", "repair conflict markers")
    pending = json.loads((b.dir / ".slate-unlock-log.json").read_text(encoding="utf-8"))
    assert pending[0]["event"] == "requested"
    b.tickets.write_text(good, encoding="utf-8")
    b.ok("lock")
    assert [e["event"] for e in log(b)] == ["requested", "locked"]
    assert not (b.dir / ".slate-unlock-log.json").exists()


def test_unlock_log_on_board_with_errors(b: Board) -> None:
    doc = b.load()
    del doc["tickets"][0]["story"]
    b.write(doc)
    b.ok("unlock", "--reason", "hand fix")  # a log entry adds no error, so it is written
    assert log(b)[-1]["event"] == "requested"


# --------------------------------------------------------------------------- end to end with the guard


def test_single_use_end_to_end(b: Board) -> None:
    b.ok("unlock", "--reason", "fix merge")
    r = post(b.root, mode="acceptEdits")
    assert r.returncode == 0 and "Slate: unlock approved" in r.stdout
    assert not (b.dir / ".slate-unlock-request.json").exists()
    rec = json.loads((b.dir / ".slate-unlock.json").read_text(encoding="utf-8"))
    assert rec["approved"] == "permission prompt" and rec["permission_mode"] == "acceptEdits"
    assert edit(b.root).returncode == 0  # the one edit
    assert edit(b.root).returncode == 2  # used up
    b.ok("edit", "ACME-002", "estimate=2d")
    assert [e["event"] for e in log(b)] == ["requested", "activated", "used"]
    assert log(b)[1]["permission_mode"] == "acceptEdits"


def test_post_activation_needs_the_exact_command(b: Board) -> None:
    b.ok("unlock", "--reason", "fix merge")
    for cmd in ('bash -c "python3 kanban/board.py unlock --reason x"',
                "cd . && python3 kanban/board.py unlock --reason x",
                "uv run python kanban/board.py unlock --reason x"):
        assert post(b.root, command=cmd).stdout == ""
    assert not (b.dir / ".slate-unlock.json").exists()
    assert post(b.root, command="py -3 kanban/board.py unlock --reason x").returncode == 0
    assert (b.dir / ".slate-unlock.json").exists()
