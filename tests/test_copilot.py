"""GitHub Copilot CLI support: the same plugin, hooks and board as Claude Code.

Copilot CLI loads Slate's Claude-format hooks.json (PascalCase events, matchers,
${CLAUDE_PLUGIN_ROOT}) and sends Claude-style hook input, with these differences, each pinned
here (seen with Copilot CLI 1.0.94):

- its edit tool sends tool_input as apply_patch text ("*** Update File: <path>"), not {file_path};
- it shows exit-2 refusals to the model as "hook exited with code 2", so the reason is lost:
  under Copilot the guard refuses with JSON (permissionDecision "deny") and exit 0;
- it sends no permission_mode, and its "ask" card shows in every mode (even Autopilot + Allow all);
- PostToolUse reports tool_result, not tool_response;
- SessionStart plain stdout never reaches the model; {"additionalContext": ...} does;
- it sets COPILOT_CLI=1 for hooks and for the agent's shell (so board.py can name the right tool).

Claude Code's behaviour is unchanged: tests without COPILOT_CLI keep exit 2 + stderr.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from conftest import VERSION, Board, base_doc, full_ticket

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "slate"
HOOKS = PLUGIN / "hooks"
GUARD = HOOKS / "guard_tickets.py"
SESSION_START = HOOKS / "session_start.py"
MESSAGE = "Change tickets through kanban/board.py (new, add, edit, set, rerank, usertest)."
V2 = ["draft", "backlog", "ready", "in_progress", "review", "user_testing", "merge_ready", "done"]


def _env(copilot: bool, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("COPILOT_CLI", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT")}
    if copilot:
        env["COPILOT_CLI"] = "1"
    env.update(extra or {})
    return env


def run_guard(body: Any, *args: str, copilot: bool = True) -> subprocess.CompletedProcess:
    stdin = body if isinstance(body, str) else json.dumps(body)
    return subprocess.run([sys.executable, str(GUARD), *args], input=stdin, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=_env(copilot), timeout=10)


def patch(*sections: str) -> str:
    return "*** Begin Patch\n" + "".join(sections) + "*** End Patch\n"


def update(path: str, old: str = "Probe", new: str = "Hacked") -> str:
    return f"*** Update File: {path}\n@@\n-  \"project\": \"{old}\",\n+  \"project\": \"{new}\",\n"


def pre(tool: str, tool_input: Any, cwd: str = "/work/acme") -> Dict[str, Any]:
    # Exactly what Copilot CLI 1.0.94 sends for a plugin's PascalCase PreToolUse hook (no permission_mode).
    return {"hook_event_name": "PreToolUse", "session_id": "757c9cc2", "timestamp": "2026-10-09T10:36:54.715Z",
            "cwd": cwd, "tool_name": tool, "tool_input": tool_input}


def denied(r: subprocess.CompletedProcess) -> str:
    """The reason of a Copilot-style refusal (exit 0 + JSON deny); fails if it isn't one."""
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse" and hso["permissionDecision"] == "deny"
    assert out["permissionDecision"] == "deny" and out["permissionDecisionReason"] == hso["permissionDecisionReason"]
    return hso["permissionDecisionReason"]


# --------------------------------------------------------------------------- the edit tool's patch text

@pytest.mark.parametrize("header", ["Update File", "Add File", "Delete File"])
def test_patch_that_touches_tickets_json_is_refused_with_the_reason(header: str) -> None:
    body = patch(f"*** {header}: /work/acme/kanban/tickets.json\n+{{}}\n")
    assert denied(run_guard(pre("Edit", body))) == MESSAGE


def test_patch_with_relative_path_resolves_against_cwd() -> None:
    assert denied(run_guard(pre("Edit", patch(update("kanban/tickets.json"))))) == MESSAGE


def test_patch_moving_a_file_onto_tickets_json_is_refused() -> None:
    body = patch("*** Update File: /work/acme/notes.json\n*** Move to: /work/acme/kanban/tickets.json\n@@\n-a\n+b\n")
    assert denied(run_guard(pre("Edit", body))) == MESSAGE


def test_multi_file_patch_is_refused_when_any_file_is_tickets_json() -> None:
    body = patch("*** Add File: /work/acme/kanban/new.json\n+{}\n", update("/work/acme/kanban/tickets.json"),
                 "*** Update File: /work/acme/notes.txt\n@@\n-hello\n+bye\n")
    assert denied(run_guard(pre("Edit", body))) == MESSAGE


def test_patch_of_other_files_is_allowed_silently() -> None:
    body = patch("*** Add File: /work/acme/kanban/new.json\n+{}\n", "*** Update File: /work/acme/notes.txt\n@@\n-a\n+b\n")
    r = run_guard(pre("Edit", body))
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


def test_patch_that_only_mentions_tickets_json_in_its_lines_is_allowed() -> None:
    body = patch("*** Update File: /work/acme/README.md\n@@\n-old\n+*** Update File: kanban/tickets.json is blocked\n")
    assert run_guard(pre("Edit", body)).stdout == ""


def test_patch_of_an_unlock_file_is_refused() -> None:
    reason = denied(run_guard(pre("Edit", patch("*** Add File: /work/acme/kanban/.slate-unlock.json\n+{}\n"))))
    assert "board.py unlock" in reason


def test_patch_without_copilot_env_is_still_refused() -> None:
    # Only Copilot sends patch text, so it is answered in Copilot's dialect even if COPILOT_CLI is missing.
    assert denied(run_guard(pre("Edit", patch(update("/work/acme/kanban/tickets.json"))), copilot=False)) == MESSAGE


def test_camel_case_input_with_raw_patch_text_is_refused() -> None:
    body = {"sessionId": "s", "timestamp": 1, "cwd": "/work/acme", "toolName": "apply_patch",
            "toolArgs": patch(update("/work/acme/kanban/tickets.json"))}
    r = run_guard(body)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["permissionDecision"] == "deny" and out["permissionDecisionReason"] == MESSAGE


@pytest.mark.parametrize("tool_input", [
    {"path": "/work/acme/kanban/tickets.json", "old_str": "a", "new_str": "b"},
    {"path": "/work/acme/kanban/tickets.json", "file_text": "{}"},
    {"file_path": "/work/acme/kanban/tickets.json", "content": "{}"},
])
def test_path_style_edit_and_create_tools_are_refused(tool_input: Dict[str, str]) -> None:
    assert denied(run_guard(pre("Edit", tool_input))) == MESSAGE


# --------------------------------------------------------------------------- shell commands

def test_shell_write_to_tickets_json_is_refused_with_the_reason() -> None:
    reason = denied(run_guard(pre("Bash", {"command": "sed -i '' 's/a/b/' kanban/tickets.json"})))
    assert reason.startswith(MESSAGE)


@pytest.mark.parametrize("command", [
    "Set-Content kanban/tickets.json '{}'",
    "'{}' | Out-File -FilePath kanban\\tickets.json",
    "Copy-Item backup.json kanban/tickets.json",
    "[IO.File]::WriteAllText('kanban/tickets.json', '{}')",
    "Remove-Item kanban/tickets.json",
])
def test_powershell_writes_to_tickets_json_are_refused(command: str) -> None:
    assert denied(run_guard(pre("PowerShell", {"command": command}))).startswith(MESSAGE)


@pytest.mark.parametrize("command", [
    "Get-Content kanban/tickets.json",
    "Select-String -Path kanban/tickets.json -Pattern ACME",
    "python kanban/board.py set ACME-001 done",
])
def test_powershell_reads_and_board_py_are_allowed(command: str) -> None:
    r = run_guard(pre("PowerShell", {"command": command}))
    assert r.returncode == 0 and r.stdout == ""


def test_powershell_writes_are_refused_for_claude_code_too() -> None:
    r = run_guard(pre("PowerShell", {"command": "Set-Content kanban/tickets.json '{}'"}), copilot=False)
    assert r.returncode == 2 and r.stderr.strip().startswith(MESSAGE)


def test_unlock_asks_for_approval_with_no_permission_mode() -> None:
    r = run_guard(pre("Bash", {"command": "python3 kanban/board.py unlock --reason 'fix merge' --minutes 5"}))
    assert r.returncode == 0
    hso = json.loads(r.stdout)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "ask"
    assert hso["permissionDecisionReason"] == ("Slate: allow ONE direct edit to kanban/tickets.json (within 5 minutes)? "
                                               "Reason: fix merge")


def test_claude_code_refusals_are_unchanged() -> None:
    r = run_guard(pre("Edit", {"file_path": "/work/acme/kanban/tickets.json", "old_string": "a", "new_string": "b"}),
                  copilot=False)
    assert r.returncode == 2 and r.stderr.strip() == MESSAGE and r.stdout == ""


# --------------------------------------------------------------------------- unlock end to end

@pytest.fixture
def b(board: Board) -> Board:
    d = base_doc([full_ticket(1), full_ticket(2)])
    d["meta"].update({"slate_version": VERSION, "schema_version": 2, "statuses": list(V2)})
    board.write(d)
    return board


def board_run(b: Board, *args: str, copilot: bool) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(b.script), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(b.root), env=_env(copilot), timeout=60)


def copilot_post(root: Path, command: str = "python3 kanban/board.py unlock --reason 'fix merge'",
                 tool: str = "Bash") -> subprocess.CompletedProcess:
    return run_guard({"hook_event_name": "PostToolUse", "session_id": "s", "timestamp": "2026-10-09T10:40:45.337Z",
                      "cwd": str(root), "tool_name": tool, "tool_input": {"command": command, "description": "x"},
                      "tool_result": {"result_type": "success", "text_result_for_llm": "Unlock requested"}}, "--post")


def copilot_edit(root: Path) -> subprocess.CompletedProcess:
    return run_guard(pre("Edit", patch(update(str(root / "kanban" / "tickets.json"))), cwd=str(root)))


def test_unlock_text_names_copilot_cli_when_run_there(b: Board) -> None:
    r = board_run(b, "unlock", "--reason", "fix merge", "--minutes", "5", copilot=True)
    assert r.returncode == 0, r.stderr
    assert "Approve it in Copilot CLI's permission card" in r.stdout and "Claude Code" not in r.stdout
    assert "python3 kanban/board.py unlock --reason 'fix merge' --minutes 5" in r.stdout


def test_unlock_text_for_claude_code_is_unchanged(b: Board) -> None:
    r = board_run(b, "unlock", "--reason", "fix merge", "--minutes", "5", copilot=False)
    assert "Approve it in Claude Code's permission prompt" in r.stdout and "Copilot" not in r.stdout


def test_single_use_unlock_end_to_end_in_copilot(b: Board) -> None:
    board_run(b, "unlock", "--reason", "fix merge", copilot=True)
    assert denied(copilot_edit(b.root)) == MESSAGE  # a request alone unlocks nothing
    r = copilot_post(b.root)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["additionalContext"].startswith("Slate: unlock approved")
    assert out["hookSpecificOutput"]["additionalContext"] == out["additionalContext"]
    rec = json.loads((b.dir / ".slate-unlock.json").read_text(encoding="utf-8"))
    assert rec["approved"] == "permission prompt" and "permission_mode" not in rec
    r = copilot_edit(b.root)
    assert r.returncode == 0 and r.stdout == ""  # the one edit
    used = json.loads((b.dir / ".slate-unlock.used.json").read_text(encoding="utf-8"))
    assert used["tool"] == "Edit"
    assert denied(copilot_edit(b.root)) == MESSAGE  # used up


def test_post_activation_from_the_powershell_tool(b: Board) -> None:
    board_run(b, "unlock", "--reason", "fix merge", copilot=True)
    assert copilot_post(b.root, command="py -3 kanban/board.py unlock --reason x", tool="PowerShell").returncode == 0
    assert (b.dir / ".slate-unlock.json").exists()


def test_post_activation_still_needs_the_exact_command(b: Board) -> None:
    board_run(b, "unlock", "--reason", "fix merge", copilot=True)
    assert copilot_post(b.root, command="cd . && python3 kanban/board.py unlock --reason x").stdout == ""
    assert not (b.dir / ".slate-unlock.json").exists()


# --------------------------------------------------------------------------- session start

def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / "kanban").mkdir(parents=True)
    shutil.copy(PLUGIN / "assets" / "board" / "board.py", proj / "kanban" / "board.py")
    (proj / "kanban" / "tickets.json").write_text(json.dumps({
        "meta": {"project": "Acme", "prefix": "ACME", "slate_version": VERSION, "schema_version": 2,
                 "generated": "2026-09-26", "statuses": V2, "areas": ["backend"],
                 "priorities": ["P0", "P1", "P2", "P3"], "user_test_areas": ["ui"]},
        "phases": [], "tickets": []}), encoding="utf-8")
    return proj


def run_session_start(cwd: Path, copilot: bool, extra: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SESSION_START)], input="{}", capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=str(cwd), env=_env(copilot, extra), timeout=30)


def test_session_start_gives_copilot_additional_context(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    r = run_session_start(proj, copilot=True, extra={"CLAUDE_PROJECT_DIR": str(proj), "CLAUDE_PLUGIN_ROOT": str(PLUGIN)})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert list(out) == ["additionalContext"]
    assert out["additionalContext"].startswith(f"Slate {VERSION}: ") and "no tickets yet" in out["additionalContext"]


def test_session_start_for_claude_code_stays_plain_text(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    r = run_session_start(proj, copilot=False, extra={"CLAUDE_PROJECT_DIR": str(proj), "CLAUDE_PLUGIN_ROOT": str(PLUGIN)})
    assert r.stdout.startswith(f"Slate {VERSION}: ")


def test_session_start_without_a_board_is_silent_in_copilot(tmp_path: Path) -> None:
    assert run_session_start(tmp_path, copilot=True).stdout == ""


# --------------------------------------------------------------------------- hooks.json for both tools

def _hook_entries() -> Dict[str, List[Dict[str, Any]]]:
    hooks = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    return {event: [h for entry in entries for h in entry["hooks"]] for event, entries in hooks.items()}


def test_hooks_json_has_a_windows_powershell_command_for_every_hook() -> None:
    expected = {"SessionStart": "session_start.py", "PreToolUse": "guard_tickets.py",
                "PostToolUse": "guard_tickets.py --post"}
    for event, args in expected.items():
        (h,) = _hook_entries()[event]
        ps = h["powershell"]
        assert '$s = "$env:CLAUDE_PLUGIN_ROOT\\hooks\\run.cmd"' in ps
        assert f"& $s {args}; exit $LASTEXITCODE" in ps
        assert ps.rstrip().endswith("exit 0")  # a missing launcher never blocks a tool call (Copilot fails closed)


def test_matchers_cover_the_powershell_tool() -> None:
    hooks = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    assert "PowerShell" in hooks["PreToolUse"][0]["matcher"].split("|")
    assert hooks["PostToolUse"][0]["matcher"] == "Bash|PowerShell"


def test_run_cmd_exists_with_crlf_endings_and_tries_each_python() -> None:
    raw = (HOOKS / "run.cmd").read_bytes()
    text = raw.decode("utf-8")
    assert b"\r\n" in raw and raw.count(b"\n") == raw.count(b"\r\n")  # cmd.exe labels need CRLF
    for py in ("py -3", "python", "python3"):
        assert f'{py} -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" <nul' in text
    assert 'set "SLATE_PYTHON=py -3"' in text
    assert "exit /b 0" in text  # no Python: skip the hook, never block


windows_only = pytest.mark.skipif(sys.platform != "win32", reason="runs the real PowerShell/cmd launcher")


def _powershell_hook(event: str, stdin: str, env_extra: Dict[str, str], cwd: Path) -> subprocess.CompletedProcess:
    (h,) = _hook_entries()[event]
    exe = shutil.which("powershell") or shutil.which("pwsh")
    assert exe, "no PowerShell on this Windows machine"
    return subprocess.run([exe, "-NoProfile", "-NonInteractive", "-Command", h["powershell"]], input=stdin,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=_env(True, {"CLAUDE_PLUGIN_ROOT": str(PLUGIN), **env_extra}), cwd=str(cwd), timeout=60)


@windows_only
def test_windows_powershell_guard_refuses_a_patch(tmp_path: Path) -> None:
    body = json.dumps(pre("Edit", patch(update("/work/acme/kanban/tickets.json"))))
    assert denied(_powershell_hook("PreToolUse", body, {}, tmp_path)) == MESSAGE


@windows_only
def test_windows_powershell_guard_allows_other_files(tmp_path: Path) -> None:
    body = json.dumps(pre("Edit", patch("*** Update File: /work/acme/notes.txt\n@@\n-a\n+b\n")))
    r = _powershell_hook("PreToolUse", body, {}, tmp_path)
    assert r.returncode == 0 and r.stdout.strip() == ""


@windows_only
def test_windows_powershell_session_start(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    r = _powershell_hook("SessionStart", "{}", {"CLAUDE_PROJECT_DIR": str(proj)}, proj)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["additionalContext"].startswith(f"Slate {VERSION}: ")


@windows_only
def test_windows_powershell_hook_without_plugin_root_never_blocks(tmp_path: Path) -> None:
    (h,) = _hook_entries()["PreToolUse"]
    exe = shutil.which("powershell") or shutil.which("pwsh")
    r = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-Command", h["powershell"]], input="{}",
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=_env(True), cwd=str(tmp_path), timeout=60)
    assert r.returncode == 0
