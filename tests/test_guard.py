"""Tests for plugins/slate/hooks/guard_tickets.py, fed JSON on stdin like Claude Code does."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[1] / "plugins" / "slate" / "hooks" / "guard_tickets.py"
MESSAGE = "Change tickets through kanban/board.py (new, add, edit, set, rerank, usertest)."


def run_guard(stdin: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=stdin,
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
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
        "python3 kanban/board.py check && echo {} > kanban/tickets.json",
        "python3 -c \"open('kanban/tickets.json','w')\"",
        "python3 -c 'p=\"kanban/tickets.json\"; open(p, mode=\"a\")'",
        "python3 -c \"import json; json.dump({}, open('kanban/tickets.json', 'w'))\"",
        "python3 -c \"from pathlib import Path; Path('kanban/tickets.json').open('r+')\"",
        "python3 -c \"from pathlib import Path; Path('kanban/tickets.json').write_text('{}')\"",
        "bash -c \"echo {} > kanban/tickets.json\"",
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
        "python3 -c \"json.load(open('kanban/tickets.json'))\"",
        "python3 -c \"import json; print(len(json.load(open('kanban/tickets.json', 'r'))['tickets']))\"",
        "python3 -c \"import json; d = json.load(open('kanban/tickets.json', encoding='utf-8')); print(d['meta'])\"",
        "git checkout -- kanban/tickets.json",
        "git checkout --theirs kanban/tickets.json && git add kanban/tickets.json",
        "git restore --staged kanban/tickets.json",
        "git merge main && python3 kanban/board.py check",
        "git rebase main && cat kanban/tickets.json",
        "git stash push kanban/tickets.json",
        "python3 kanban/board.py lock",
        "python3 kanban/board.py diff main && python3 kanban/board.py sync --from main",
    ],
)
def test_bash_reads_and_board_py_pass(command: str, tmp_path: Path) -> None:
    result = run_guard(payload("Bash", {"command": command}), cwd=tmp_path)
    assert result.returncode == 0, (command, result.stderr)


@pytest.mark.parametrize("path", ["Kanban/Tickets.json", "KANBAN/TICKETS.JSON", "kanban/Tickets.json"])
def test_case_variants_are_blocked(path: str, tmp_path: Path) -> None:
    result = run_guard(payload("Write", {"file_path": path, "content": "{}"}, cwd=str(tmp_path)))
    assert result.returncode == 2


# ---------------- unlock (single use) ----------------

UNLOCK_MESSAGE = 'Use: python3 kanban/board.py unlock --reason "…" --minutes 5 (the user will be asked to approve).'


def _iso(delta_minutes: float) -> str:
    t = datetime.now(timezone.utc) + timedelta(minutes=delta_minutes)
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_unlock(root: Path, until: object, reason: str = "fix a merge by hand") -> Path:
    k = root / "kanban"
    k.mkdir(parents=True, exist_ok=True)
    (k / "tickets.json").write_text("{}", encoding="utf-8")
    rec = root / "kanban" / ".slate-unlock.json"
    rec.write_text(json.dumps({"until": until, "reason": reason}) if not isinstance(until, bytes)
                   else until.decode(), encoding="utf-8")
    return rec


def test_active_unlock_allows_one_edit_then_blocks(tmp_path: Path) -> None:
    rec = make_unlock(tmp_path, _iso(5))
    target = str(tmp_path / "kanban" / "tickets.json")
    first = run_guard(payload("Edit", {"file_path": target, "old_string": "a", "new_string": "b"}, cwd=str(tmp_path)))
    assert first.returncode == 0, first.stderr
    assert not rec.exists()
    used = json.loads((tmp_path / "kanban" / ".slate-unlock.used.json").read_text(encoding="utf-8"))
    assert used["tool"] == "Edit" and used["reason"] == "fix a merge by hand"
    assert datetime.fromisoformat(used["used_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    second = run_guard(payload("Write", {"file_path": target, "content": "{}"}, cwd=str(tmp_path)))
    assert second.returncode == 2
    assert second.stderr.strip() == MESSAGE


def test_relative_path_unlock_resolved_against_cwd(tmp_path: Path) -> None:
    make_unlock(tmp_path, _iso(5))
    r = run_guard(payload("Write", {"file_path": "kanban/tickets.json", "content": "{}"}, cwd=str(tmp_path)))
    assert r.returncode == 0


def test_new_unlock_overwrites_previous_used_record(tmp_path: Path) -> None:
    (tmp_path / "kanban").mkdir()
    (tmp_path / "kanban" / ".slate-unlock.used.json").write_text('{"until": "old"}', encoding="utf-8")
    make_unlock(tmp_path, _iso(5), reason="second")
    r = run_guard(payload("Write", {"file_path": str(tmp_path / "kanban" / "tickets.json")}, cwd=str(tmp_path)))
    assert r.returncode == 0
    used = json.loads((tmp_path / "kanban" / ".slate-unlock.used.json").read_text(encoding="utf-8"))
    assert used["reason"] == "second"


@pytest.mark.parametrize(
    "until",
    [
        "EXPIRED",
        "not a date",
        "",
        42,
        None,
        "FAR",  # further out than any unlock board.py can grant
        b"{broken json",
        b"[]",
    ],
)
def test_expired_or_malformed_unlock_blocks(tmp_path: Path, until: object) -> None:
    value = {"EXPIRED": _iso(-1), "FAR": _iso(24 * 60)}.get(until, until) if isinstance(until, str) else until
    rec = make_unlock(tmp_path, value)
    r = run_guard(payload("Edit", {"file_path": str(tmp_path / "kanban" / "tickets.json")}, cwd=str(tmp_path)))
    assert r.returncode == 2
    assert rec.exists()  # not consumed
    assert "Traceback" not in r.stderr


def test_naive_and_offset_timestamps_are_utc(tmp_path: Path) -> None:
    naive = (datetime.now(timezone.utc) + timedelta(minutes=5)).replace(tzinfo=None, microsecond=0).isoformat()
    edit = payload("Edit", {"file_path": str(tmp_path / "kanban" / "tickets.json")}, cwd=str(tmp_path))
    make_unlock(tmp_path, naive)
    assert run_guard(edit).returncode == 0
    offset = (datetime.now(timezone(timedelta(hours=5, minutes=30))) + timedelta(minutes=5)).isoformat()
    make_unlock(tmp_path, offset)
    assert run_guard(edit).returncode == 0


def test_unlock_only_applies_to_its_own_kanban_folder(tmp_path: Path) -> None:
    make_unlock(tmp_path / "a", _iso(5))
    (tmp_path / "b" / "kanban").mkdir(parents=True)
    r = run_guard(payload("Edit", {"file_path": str(tmp_path / "b" / "kanban" / "tickets.json")}, cwd=str(tmp_path)))
    assert r.returncode == 2
    assert (tmp_path / "a" / "kanban" / ".slate-unlock.json").exists()


def test_bash_write_consumes_unlock(tmp_path: Path) -> None:
    rec = make_unlock(tmp_path, _iso(5))
    cmd = "cp /tmp/merged.json kanban/tickets.json"
    first = run_guard(payload("Bash", {"command": cmd}, cwd=str(tmp_path)), cwd=tmp_path)
    assert first.returncode == 0, first.stderr
    assert not rec.exists()
    used = json.loads((tmp_path / "kanban" / ".slate-unlock.used.json").read_text(encoding="utf-8"))
    assert used["tool"] == "Bash"
    second = run_guard(payload("Bash", {"command": cmd}, cwd=str(tmp_path)), cwd=tmp_path)
    assert second.returncode == 2


def test_bash_read_does_not_consume_unlock(tmp_path: Path) -> None:
    rec = make_unlock(tmp_path, _iso(5))
    r = run_guard(payload("Bash", {"command": "cat kanban/tickets.json"}, cwd=str(tmp_path)), cwd=tmp_path)
    assert r.returncode == 0
    assert rec.exists()


def test_bash_expired_unlock_blocks(tmp_path: Path) -> None:
    make_unlock(tmp_path, _iso(-5))
    r = run_guard(payload("Bash", {"command": "echo {} > kanban/tickets.json"}, cwd=str(tmp_path)), cwd=tmp_path)
    assert r.returncode == 2


@pytest.mark.parametrize("name", [".slate-unlock.json", ".slate-unlock.used.json", ".Slate-Unlock.JSON"])
@pytest.mark.parametrize("tool", ["Edit", "Write", "MultiEdit"])
def test_unlock_files_cannot_be_written_directly(tmp_path: Path, name: str, tool: str) -> None:
    make_unlock(tmp_path, _iso(5))  # an active unlock never unlocks writes to itself
    r = run_guard(payload(tool, {"file_path": str(tmp_path / "kanban" / name), "content": "{}"}, cwd=str(tmp_path)))
    assert r.returncode == 2
    assert r.stderr.strip() == UNLOCK_MESSAGE
    assert (tmp_path / "kanban" / ".slate-unlock.json").exists()


@pytest.mark.parametrize(
    "command",
    [
        "echo '{\"until\": \"2999-01-01T00:00:00Z\"}' > kanban/.slate-unlock.json",
        "cp /tmp/u.json kanban/.slate-unlock.json",
        "python3 -c \"open('kanban/.slate-unlock.json','w').write('{}')\"",
        "rm kanban/.slate-unlock.used.json",
        "tee kanban/.slate-unlock.json < /tmp/u.json",
    ],
)
def test_bash_writes_to_unlock_files_are_blocked(tmp_path: Path, command: str) -> None:
    r = run_guard(payload("Bash", {"command": command}, cwd=str(tmp_path)), cwd=tmp_path)
    assert r.returncode == 2, command
    assert UNLOCK_MESSAGE in r.stderr


def test_reading_unlock_file_is_fine(tmp_path: Path) -> None:
    r = run_guard(payload("Bash", {"command": "cat kanban/.slate-unlock.json"}, cwd=str(tmp_path)), cwd=tmp_path)
    assert r.returncode == 0


# ---------------- board.py unlock asks the person ----------------

def _ask(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    "command,minutes,reason",
    [
        ('python3 kanban/board.py unlock --reason "fix merge conflict" --minutes 5', "5", "fix merge conflict"),
        ("python3 kanban/board.py unlock --reason 'hand fix' --minutes 10", "10", "hand fix"),
        ("python3 kanban/board.py unlock --reason=typo", "5", "typo"),
        ("python3 kanban/board.py unlock", "5", "none given"),
        ('bash -c "python3 kanban/board.py unlock --reason x"', "5", "x"),
        ('bash -c "python3 kanban/board.py unlock --reason \\"two words\\" --minutes 3"', "3", "two words"),
        ("cd /repo && (python3 kanban/board.py unlock --reason sub --minutes 2)", "2", "sub"),
        ("python3 -c \"import subprocess; subprocess.run(['python3', 'kanban/board.py', 'unlock', '--reason', 'y'])\"",
         "5", "y"),
        ("uv run python kanban/board.py unlock --reason uv", "5", "uv"),
        ("sh -c 'python3 kanban/board.py unlock --minutes 7 --reason later'", "7", "later"),
    ],
)
def test_board_py_unlock_forces_permission_prompt(tmp_path: Path, command: str, minutes: str, reason: str) -> None:
    out = _ask(run_guard(payload("Bash", {"command": command}, cwd=str(tmp_path)), cwd=tmp_path))
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "ask"
    assert hso["permissionDecisionReason"] == (
        f"Slate: allow ONE direct edit to kanban/tickets.json (within {minutes} minutes)? Reason: {reason}")


def test_python_list_form_unlock_still_asks(tmp_path: Path) -> None:
    # 'board.py', 'unlock' in a Python list still counts as an unlock request.
    command = "python3 -c \"import subprocess; subprocess.run(['python3', 'kanban/board.py', 'unlock'])\""
    out = _ask(run_guard(payload("Bash", {"command": command}, cwd=str(tmp_path)), cwd=tmp_path))
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_copilot_style_unlock_gets_flat_ask(tmp_path: Path) -> None:
    body = json.dumps({"toolName": "bash", "cwd": str(tmp_path),
                       "toolArgs": json.dumps({"command": "python3 kanban/board.py unlock --reason merge"})})
    out = _ask(run_guard(body, cwd=tmp_path))
    assert out == {"permissionDecision": "ask",
                   "permissionDecisionReason": "Slate: allow ONE direct edit to kanban/tickets.json "
                                               "(within 5 minutes)? Reason: merge"}


def test_copilot_style_write_is_blocked(tmp_path: Path) -> None:
    body = json.dumps({"toolName": "bash", "cwd": str(tmp_path),
                       "toolArgs": {"command": "echo {} > kanban/tickets.json"}})
    assert run_guard(body, cwd=tmp_path).returncode == 2


@pytest.mark.parametrize(
    "command",
    [
        "python3 kanban/board.py lock",
        "python3 kanban/board.py check",
        "python3 kanban/board.py show ACME-001 # mentions unlock later",
        "echo unlock",
    ],
)
def test_lock_and_other_commands_pass_without_prompt(tmp_path: Path, command: str) -> None:
    r = run_guard(payload("Bash", {"command": command}, cwd=str(tmp_path)), cwd=tmp_path)
    assert r.returncode == 0
    assert r.stdout == ""


# ---------------- permission modes (PreToolUse) ----------------

UNLOCK_CMD = 'python3 kanban/board.py unlock --reason "fix merge" --minutes 5'
PLAN_MESSAGE = "Unlock isn't available in plan mode — leave plan mode first."
NOBODY_START = "Nobody is here to approve an unlock in this mode."


def mode_payload(command: str, mode: object, cwd: str, event: str = "PreToolUse") -> str:
    p = json.loads(payload("Bash", {"command": command}, cwd=cwd))
    p["hook_event_name"] = event
    if mode is not None:
        p["permission_mode"] = mode
    return json.dumps(p)


@pytest.mark.parametrize("mode", ["default", "acceptEdits", "auto", None])
def test_unlock_asks_in_modes_with_a_person(tmp_path: Path, mode: object) -> None:
    out = _ask(run_guard(mode_payload(UNLOCK_CMD, mode, str(tmp_path)), cwd=tmp_path))
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_unlock_denied_in_plan_mode(tmp_path: Path) -> None:
    r = run_guard(mode_payload(UNLOCK_CMD, "plan", str(tmp_path)), cwd=tmp_path)
    assert r.returncode == 2 and r.stderr.strip() == PLAN_MESSAGE and r.stdout == ""


@pytest.mark.parametrize("mode", ["bypassPermissions", "dontAsk", "somethingNew", ""])
def test_unlock_denied_when_nobody_can_approve(tmp_path: Path, mode: str) -> None:
    r = run_guard(mode_payload(UNLOCK_CMD, mode, str(tmp_path)), cwd=tmp_path)
    assert r.returncode == 2 and r.stderr.startswith(NOBODY_START) and "they type a code" in r.stderr


@pytest.mark.parametrize("mode", ["plan", "bypassPermissions", "dontAsk"])
def test_other_commands_unaffected_by_mode(tmp_path: Path, mode: str) -> None:
    r = run_guard(mode_payload("python3 kanban/board.py lock", mode, str(tmp_path)), cwd=tmp_path)
    assert r.returncode == 0 and r.stdout == ""


# ---------------- PostToolUse activation (--post) ----------------

def run_post(stdin: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(GUARD), "--post"], input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=cwd, timeout=10)


def make_request(root: Path, created: str | None = None, minutes: object = 5) -> Path:
    (root / "kanban").mkdir(parents=True, exist_ok=True)
    p = root / "kanban" / ".slate-unlock-request.json"
    p.write_text(json.dumps({"id": "ab12cd34", "reason": "fix merge", "minutes": minutes,
                             "created": created or _iso(0)}), encoding="utf-8")
    return p


def active(root: Path) -> dict | None:
    p = root / "kanban" / ".slate-unlock.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


@pytest.mark.parametrize("command", [
    "python3 kanban/board.py unlock --reason 'fix merge' --minutes 5",
    "python kanban/board.py unlock --reason x",
    "py -3 kanban/board.py unlock --reason x",
    "  python3 kanban/board.py unlock --reason x  ",
])
def test_post_activates_exact_forms(tmp_path: Path, command: str) -> None:
    req = make_request(tmp_path)
    r = run_post(mode_payload(command, "default", str(tmp_path), "PostToolUse"), tmp_path)
    assert r.returncode == 0
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PostToolUse" and "ONE direct edit" in out["additionalContext"]
    rec = active(tmp_path)
    assert rec and rec["approved"] == "permission prompt" and rec["reason"] == "fix merge"
    assert rec["permission_mode"] == "default" and rec["request_id"] == "ab12cd34"
    assert not req.exists()
    # the next edit is allowed once, then blocked again
    edit = payload("Edit", {"file_path": str(tmp_path / "kanban" / "tickets.json")}, cwd=str(tmp_path))
    assert run_guard(edit, cwd=tmp_path).returncode == 0
    assert run_guard(edit, cwd=tmp_path).returncode == 2


@pytest.mark.parametrize("command", [
    'bash -c "python3 kanban/board.py unlock --reason x"',
    "cd /repo && python3 kanban/board.py unlock --reason x",
    "python3 kanban/board.py unlock --reason x; echo hi",
    "python3 kanban/board.py unlock --reason x | cat",
    "python3 kanban/board.py unlock --reason x & sleep 1",
    "python3 kanban/board.py unlock --reason `whoami`",
    "python3 kanban/board.py unlock --reason $(whoami)",
    "python3 kanban/board.py unlock --reason x\necho hi",
    "uv run python kanban/board.py unlock --reason x",
    "python3 ./kanban/board.py unlock --reason x",
    "python3 kanban/board.py unlocks",
    "python3 kanban/board.py lock",
    "echo python3 kanban/board.py unlock",
])
def test_post_ignores_wrapped_or_other_commands(tmp_path: Path, command: str) -> None:
    req = make_request(tmp_path)
    r = run_post(mode_payload(command, "default", str(tmp_path), "PostToolUse"), tmp_path)
    assert r.returncode == 0 and r.stdout == ""
    assert active(tmp_path) is None and req.exists()


@pytest.mark.parametrize("mode,activates", [
    ("default", True), ("acceptEdits", True), ("auto", True), (None, True),
    ("plan", False), ("bypassPermissions", False), ("dontAsk", False), ("other", False),
])
def test_post_activation_by_mode(tmp_path: Path, mode: object, activates: bool) -> None:
    make_request(tmp_path)
    run_post(mode_payload("python3 kanban/board.py unlock --reason x", mode, str(tmp_path), "PostToolUse"), tmp_path)
    assert (active(tmp_path) is not None) is activates


@pytest.mark.parametrize("created,minutes", [(_iso(-3), 5), (_iso(10), 5), ("garbage", 5), (_iso(0), 99),
                                             (_iso(0), "5")])
def test_post_ignores_stale_or_bad_requests(tmp_path: Path, created: str, minutes: object) -> None:
    make_request(tmp_path, created=created, minutes=minutes)
    r = run_post(mode_payload("python3 kanban/board.py unlock --reason x", "default", str(tmp_path), "PostToolUse"),
                 tmp_path)
    assert r.returncode == 0 and r.stdout == "" and active(tmp_path) is None


def test_post_without_request_or_twice_does_nothing(tmp_path: Path) -> None:
    body = mode_payload("python3 kanban/board.py unlock --reason x", "default", str(tmp_path), "PostToolUse")
    assert run_post(body, tmp_path).stdout == "" and active(tmp_path) is None
    make_request(tmp_path)
    assert run_post(body, tmp_path).stdout
    (tmp_path / "kanban" / ".slate-unlock.json").unlink()
    assert run_post(body, tmp_path).stdout == "" and active(tmp_path) is None  # the request was used up


def test_post_ignores_non_claude_payloads(tmp_path: Path) -> None:
    make_request(tmp_path)
    body = json.dumps({"toolName": "bash", "cwd": str(tmp_path),
                       "toolArgs": json.dumps({"command": "python3 kanban/board.py unlock --reason x"})})
    assert run_post(body, tmp_path).stdout == "" and active(tmp_path) is None
    assert run_post("not json", tmp_path).returncode == 0


# ---------------- more protected files ----------------

@pytest.mark.parametrize("name", [".slate-unlock-request.json", ".slate-unlock-log.json", ".slate-write.lock",
                                  ".slate-unlock-request.json.claim-12"])
def test_request_log_and_lock_files_are_protected(tmp_path: Path, name: str) -> None:
    target = str(tmp_path / "kanban" / name)
    r = run_guard(payload("Write", {"file_path": target, "content": "{}"}, cwd=str(tmp_path)), cwd=tmp_path)
    assert r.returncode == 2
    r = run_guard(payload("Bash", {"command": f"echo '{{}}' > kanban/{name}"}, cwd=str(tmp_path)), cwd=tmp_path)
    assert r.returncode == 2


def test_board_py_output_redirected_into_unlock_file_is_blocked(tmp_path: Path) -> None:
    cmd = "python3 kanban/board.py export --json > kanban/.slate-unlock.json"
    assert run_guard(payload("Bash", {"command": cmd}, cwd=str(tmp_path)), cwd=tmp_path).returncode == 2


@pytest.mark.parametrize(
    "command",
    [
        "curl -s https://example.com/forged.json -o kanban/tickets.json",
        "curl -sSfL --output kanban/tickets.json https://example.com/x",
        "wget -q -O kanban/tickets.json https://example.com/x",
        "wget --output-document=kanban/tickets.json https://example.com/x",
        "rsync /tmp/x.json kanban/tickets.json",
        "jq '.x=1' kanban/tickets.json | sponge kanban/tickets.json",
        "python3 -c \"import shutil; shutil.copy('x.json', 'kanban/tickets.json')\"",
        "python3 -c \"import shutil; shutil.move('x.json', 'kanban/tickets.json')\"",
        "python3 -c \"import os; os.replace('x.json', 'kanban/tickets.json')\"",
        "python3 -c \"import os; os.rename('x.json', 'kanban/tickets.json')\"",
        "python3 -c \"from pathlib import Path; Path('x.json').replace('kanban/tickets.json')\"",
    ],
)
def test_bash_download_and_python_moves_are_blocked(command: str, tmp_path: Path) -> None:
    result = run_guard(payload("Bash", {"command": command}), cwd=tmp_path)
    assert result.returncode == 2, command


@pytest.mark.parametrize(
    "command",
    [
        "curl -s http://127.0.0.1:8088/tickets.json | jq .meta",
        "wget -qO- http://127.0.0.1:8088/tickets.json | head",
        "wget -q -O - http://127.0.0.1:8088/tickets.json | head",
        "curl -s -o - http://127.0.0.1:8088/tickets.json | jq .",
        "python3 -c \"import json; print(json.load(open('kanban/tickets.json'))['meta'])\"",
    ],
)
def test_reading_via_curl_wget_python_still_allowed(command: str, tmp_path: Path) -> None:
    result = run_guard(payload("Bash", {"command": command}), cwd=tmp_path)
    assert result.returncode == 0, (command, result.stderr)
