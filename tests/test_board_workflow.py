"""Tests for `workflow --markdown` (SLATE.md's ## Workflow section), doctor's slate-md-workflow-stale and
.gitignore lines, per-state handoff-note rules (meta.status_note), and the portability wiring in board.py
(the interpreter named in fix lines and in the merge driver)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from conftest import BOARD_SRC, Board, base_doc, full_ticket

V2_STATUSES = ["draft", "backlog", "ready", "in_progress", "review", "user_testing", "merge_ready", "done"]


def v2_doc(tickets: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    d = base_doc(tickets or [full_ticket(1, unlocks=["ACME-002"]), full_ticket(2, depends_on=["ACME-001"]),
                             full_ticket(3)])
    d["meta"].update({"slate_version": "0.2.0", "schema_version": 2, "statuses": list(V2_STATUSES)})
    return d


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                           "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
                          cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", check=True)


def make_repo(board: Board) -> None:
    git(board.root, "init", "-q", "-b", "main")
    git(board.root, "add", "kanban/board.py", "kanban/tickets.json")
    git(board.root, "commit", "-q", "-m", "board")


def run_env(board: Board, env: Dict[str, str], *args: str) -> subprocess.CompletedProcess:
    e = dict(os.environ)
    e.update(env)
    return subprocess.run([sys.executable, str(board.script), *args], capture_output=True, text=True,
                          cwd=str(board.root), env=e, timeout=60)


def codes(board: Board) -> Dict[str, Dict[str, Any]]:
    return {p["code"]: p for p in json.loads(board.run("doctor", "--json").stdout)["problems"]}


def rows(md: str) -> Dict[str, List[str]]:
    """State table rows: name -> [column title, role, note, meaning, allowed from]."""
    out = {}
    for ln in md.splitlines():
        if ln.startswith("| `"):
            cells = [c.strip() for c in ln.strip("|").split(" | ")]
            out[cells[0].strip("`")] = cells[1:]
    return out


def load_board_module() -> Any:
    spec = importlib.util.spec_from_file_location("slate_board_under_test", str(BOARD_SRC))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- workflow --markdown


def test_workflow_markdown_default_board(board: Board) -> None:
    board.write(v2_doc())
    md = board.ok("workflow", "--markdown").stdout
    assert md.startswith("## Workflow\n")
    r = rows(md)
    assert list(r) == V2_STATUSES
    assert r["review"][:3] == ["review", "review", "required"] and r["review"][4] == "any"
    assert r["in_progress"][2] == "optional"
    assert r["merge_ready"][3].startswith("Reviewed")
    assert "- Workflow: **free** — no transition rules" in md
    assert "- Merge-ready: after review" in md and "`merge_ready`" in md
    assert "- User tests: tickets in areas `frontend`, `ui` need user tests" in md
    assert "- Bugs:" in md and "- Unscheduled phases: none" in md
    assert "- Board of record: this folder's `kanban/tickets.json` (not a git repository)." in md
    assert "- Merge driver: not a git repository." in md
    assert "- Python: `" in md and "- Unlock:" in md
    assert board.ok("workflow").stdout == md  # --markdown is the only format


def test_workflow_markdown_custom_states_rules_and_phases(board: Board) -> None:
    board.write(v2_doc())
    board.ok("add-status", "qa", "--after", "review", "--like", "review", "--label", "QA | checks")
    board.ok("edit-status", "merge_ready", "label=Waiting for merge")
    board.ok("set-meta", "workflow=strict")
    board.ok("add-phase", "--id", "BACKLOG", "--name", "Someday", "--goal", "g", "--demo", "d", "--unscheduled")
    md = board.ok("workflow", "--markdown").stdout
    r = rows(md)
    assert r["qa"][:3] == ["QA \\| checks", "review", "required"]
    assert r["user_testing"][4] == "`review`, `qa`"
    assert r["in_progress"][4] == "`backlog`, `ready`"
    assert "- Workflow: **strict**" in md
    assert "(Waiting for merge)" in md
    assert "- Unscheduled phases: `BACKLOG`" in md
    board.ok("edit-status", "qa", "from=review")
    assert "- Workflow: **custom**" in board.ok("workflow", "--markdown").stdout


def test_workflow_markdown_uses_the_python_from_slate_md(board: Board) -> None:
    board.write(v2_doc())
    (board.root / "SLATE.md").write_text("# x\n## Commands\nPython: `py -3`\n", encoding="utf-8")
    md = board.ok("workflow", "--markdown").stdout
    assert "- Python: `py -3`" in md and "`py -3 kanban/board.py new --bug" in md


def test_workflow_markdown_in_git(board: Board) -> None:
    board.write(v2_doc())
    make_repo(board)
    md = board.ok("workflow", "--markdown").stdout
    assert "- Board of record: `kanban/tickets.json` on `main` in the main checkout" in md
    assert "- Merge driver: not installed" in md
    board.ok("install-merge-driver", "--python", "python3")
    md = board.ok("workflow", "--markdown").stdout
    assert "- Merge driver: installed (`.gitattributes`: `kanban/tickets.json merge=slate`)" in md


# --------------------------------------------------------------------------- doctor


def test_doctor_workflow_section_stale(board: Board) -> None:
    board.write(v2_doc())
    slate_md = board.root / "SLATE.md"
    slate_md.write_text("# Slate\nPython: `python3`\n\n## Rules\nx\n", encoding="utf-8")
    assert "slate-md-workflow-stale" not in codes(board)  # no section: nothing to compare
    md = board.ok("workflow", "--markdown").stdout
    reflowed = md.replace(" | ", "   |   ").replace("\n- ", "\n\n-  ")  # whitespace doesn't matter
    slate_md.write_text(f"# Slate\nPython: `python3`\n\n{reflowed}\n## Rules\nx\n", encoding="utf-8")
    assert "slate-md-workflow-stale" not in codes(board)
    board.ok("edit-status", "review", "label=Code review")
    c = codes(board)["slate-md-workflow-stale"]
    assert c["kind"] == "setup" and "Workflow" in c["message"]
    assert any("workflow --markdown" in f and f.startswith("ask the user:") for f in c["fix"])
    assert board.run("doctor").returncode == 1
    new = board.ok("workflow", "--markdown").stdout
    slate_md.write_text(f"# Slate\nPython: `python3`\n\n{new}\n## Rules\nx\n", encoding="utf-8")
    assert "slate-md-workflow-stale" not in codes(board)


def test_doctor_gitignore_needs_the_serve_files(board: Board) -> None:
    board.write(v2_doc())
    make_repo(board)
    (board.root / ".gitignore").write_text("kanban/.slate-unlock*.json\nkanban/.slate-write.lock\n", encoding="utf-8")
    c = codes(board)["gitignore-missing"]
    assert "kanban/.slate-serve.json" in c["message"] and "kanban/.slate-serve.log" in c["message"]
    assert "kanban/.slate-unlock.json" not in c["message"]
    (board.root / ".gitignore").write_text("kanban/.slate-unlock*.json\nkanban/.slate-write.lock\n"
                                           "kanban/.slate-serve.json\nkanban/.slate-serve.log\n", encoding="utf-8")
    assert "gitignore-missing" not in codes(board)


# --------------------------------------------------------------------------- per-state handoff notes


def to_in_progress(board: Board, tid: str = "ACME-001") -> None:
    board.ok("set", tid, "in_progress")


def test_builtin_note_rules_by_role(board: Board) -> None:
    board.write(v2_doc())
    to_in_progress(board)
    r = board.fail("set", "ACME-001", "review")
    assert "handoff: moving to review needs a note" in r.stderr
    st = {s["name"]: s["note"] for s in json.loads(board.ok("export", "--json", "--statuses").stdout)["statuses"]}
    assert st == {"draft": "optional", "backlog": "optional", "ready": "optional", "in_progress": "optional",
                  "review": "required", "user_testing": "required", "merge_ready": "required", "done": "required"}


def test_builtin_override_done_optional_in_progress_required(board: Board) -> None:
    board.write(v2_doc())
    board.ok("edit-status", "in_progress", "note=required")
    board.ok("edit-status", "done", "note=optional")
    assert board.load()["meta"]["status_note"] == {"in_progress": "required", "done": "optional"}
    r = board.fail("set", "ACME-001", "in_progress")
    assert "moving to in_progress needs a note" in r.stderr
    board.ok("set", "ACME-003", "in_progress", "--handoff", "starting")
    board.ok("set", "ACME-003", "done", "--no-code", "docs only")  # no --handoff needed now
    t = board.ticket("ACME-003")
    assert t["status"] == "done" and t["handoff"][-1]["note"] == "(no code: docs only)"
    board.ok("check")
    r = board.fail("edit-status", "done", "note=sometimes")
    assert "must be required or optional" in r.stderr


def test_custom_state_required_and_optional(board: Board) -> None:
    board.write(v2_doc())
    board.ok("add-status", "qa", "--after", "review", "--like", "review", "--note", "optional")
    board.ok("add-status", "design", "--after", "ready", "--like", "in_progress", "--note", "required")
    meta = board.load()["meta"]
    assert meta["status_note"] == {"qa": "optional", "design": "required"}
    r = board.fail("set", "ACME-001", "design")
    assert "moving to design needs a note" in r.stderr
    board.ok("set", "ACME-001", "design", "--handoff", "sketching")
    board.ok("set", "ACME-003", "in_progress")
    board.ok("set", "ACME-003", "qa")  # optional: no note needed
    assert board.ticket("ACME-003")["status"] == "qa"


def test_add_status_inherits_the_note_rule(board: Board) -> None:
    board.write(v2_doc())
    board.ok("add-status", "qa", "--after", "review", "--like", "review")
    board.ok("add-status", "spike", "--after", "ready", "--like", "in_progress")
    assert "status_note" not in board.load()["meta"]  # same as the role: nothing stored
    board.ok("edit-status", "qa", "note=optional")
    board.ok("add-status", "qa2", "--after", "qa", "--like", "qa")  # like a status: takes its rule
    assert board.load()["meta"]["status_note"] == {"qa": "optional", "qa2": "optional"}
    st = {s["name"]: s["note"] for s in json.loads(board.ok("export", "--json", "--statuses").stdout)["statuses"]}
    assert st["qa"] == st["qa2"] == "optional" and st["spike"] == "optional" and st["review"] == "required"


def test_rename_and_remove_status_carry_and_drop_the_note_rule(board: Board) -> None:
    board.write(v2_doc())
    board.ok("add-status", "qa", "--after", "review", "--like", "review", "--note", "optional")
    board.ok("rename-status", "qa", "checks")
    assert board.load()["meta"]["status_note"] == {"checks": "optional"}
    board.ok("remove-status", "checks")
    assert "status_note" not in board.load()["meta"]


def test_backward_moves_under_rules_need_a_note_even_when_optional(board: Board) -> None:
    board.write(v2_doc())
    board.ok("edit-status", "in_progress", "note=optional")
    to_in_progress(board)
    board.ok("set", "ACME-001", "review", "--handoff", "built")
    board.ok("set-meta", "workflow=strict")
    r = board.fail("set", "ACME-001", "in_progress")
    assert "needs a reason" in r.stderr


def test_bad_status_note_in_the_file_is_an_error(board: Board) -> None:
    d = v2_doc()
    d["meta"]["status_note"] = {"review": "maybe", "nope": "optional"}
    board.write(d)
    r = board.fail("check")
    assert "status_note: review: must be required or optional" in r.stderr
    assert "status_note: 'nope' is not one of meta.statuses" in r.stderr


# --------------------------------------------------------------------------- portability: the interpreter


def test_fix_lines_use_the_invoking_python(board: Board) -> None:
    board.write(v2_doc())
    to_in_progress(board)
    r = run_env(board, {"SLATE_PYTHON": "py -3"}, "set", "ACME-001", "review")
    assert r.returncode == 1 and "fix: py -3 kanban/board.py set ACME-001 review --handoff" in r.stderr
    r = board.fail("set", "ACME-001", "review")
    assert "fix: python3 kanban/board.py set ACME-001 review" in r.stderr or "fix: python kanban/board.py" in r.stderr


def test_merge_driver_defaults_to_the_invoking_python(board: Board) -> None:
    board.write(v2_doc())
    make_repo(board)
    r = run_env(board, {"SLATE_PYTHON": "py -3"}, "install-merge-driver")
    assert r.returncode == 0, r.stderr
    driver = git(board.root, "config", "--get", "merge.slate.driver").stdout.strip()
    assert driver == "py -3 kanban/board.py merge-driver %O %A %B"
    env = {k: v for k, v in os.environ.items() if k != "SLATE_PYTHON"}
    r = subprocess.run([sys.executable, str(board.script), "install-merge-driver"], capture_output=True, text=True,
                       cwd=str(board.root), env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    driver = git(board.root, "config", "--get", "merge.slate.driver").stdout.strip()
    assert driver.split()[0] in ("python3", "python", "py") or driver.startswith(("'", '"'))
    assert driver.endswith("kanban/board.py merge-driver %O %A %B")


@pytest.mark.parametrize("exe,os_name,which,want", [
    ("/usr/bin/python3", "posix", {"python3"}, "python3"),
    ("/opt/homebrew/bin/python3.13", "posix", set(), "python3"),
    ("/proj/.venv/bin/python", "posix", {"python3", "python"}, "python3"),
    ("/proj/.venv/bin/python", "posix", {"python"}, "python"),
    ("/opt/odd/pypy-custom", "posix", set(), "/opt/odd/pypy-custom"),
    ("C:\\Python313\\python.exe", "nt", {"python", "py"}, "python"),
    ("C:\\Python313\\python.exe", "nt", {"py"}, "py -3"),
])
def test_invoking_python_heuristics(monkeypatch: pytest.MonkeyPatch, exe: str, os_name: str, which: set,
                                    want: str) -> None:
    mod = load_board_module()
    monkeypatch.delenv("SLATE_PYTHON", raising=False)
    # no global monkeypatching of os.name / sys.executable: that breaks pytest itself on Windows
    fake_which = lambda name: f"/bin/{name}" if name in which else None  # noqa: E731
    assert mod.invoking_python(os_name=os_name, executable=exe, which=fake_which) == want
    monkeypatch.setenv("SLATE_PYTHON", "py -3")
    assert mod.invoking_python(os_name=os_name, executable=exe, which=fake_which) == "py -3"
