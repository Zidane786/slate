"""Tests for board.py branches, worktrees and merges (docs/plans/2026-09-26-v0.2-build-plan.md,
workstream B: #15 diff, #16 sync, #17 merge driver, #18 board of record, #19 copy-to), repair writes,
the write lock, claims and doctor (section D)."""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from conftest import VERSION, USER_TEST, Board, base_doc, full_ticket

V2_STATUSES = ["draft", "backlog", "ready", "in_progress", "review", "user_testing", "merge_ready", "done"]


def v2_doc(tickets: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    d = base_doc(tickets)
    d["meta"].update({"slate_version": VERSION, "schema_version": 2, "statuses": list(V2_STATUSES)})
    return d


def three() -> Dict[str, Any]:
    return v2_doc([full_ticket(1, unlocks=["ACME-002"]), full_ticket(2, depends_on=["ACME-001"]), full_ticket(3)])


def three_current() -> Dict[str, Any]:
    """three() at the current schema (3: the cancelled state), so doctor has no schema problem."""
    d = three()
    d["meta"].update({"schema_version": 3, "statuses": V2_STATUSES + ["cancelled"]})
    return d


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                           "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
                          cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", check=check)


def make_repo(board: Board, doc: Optional[Dict[str, Any]] = None) -> None:
    """A git repo on main with kanban/board.py and tickets.json committed."""
    board.write(doc or three())
    git(board.root, "init", "-q", "-b", "main")
    git(board.root, "add", "kanban/board.py", "kanban/tickets.json")
    git(board.root, "commit", "-q", "-m", "board")


def commit_all(board: Board, msg: str) -> None:
    git(board.root, "add", "-A")
    git(board.root, "commit", "-q", "-m", msg)


def other_file(tmp_path: Path, doc: Dict[str, Any], name: str = "other.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return p


def diff_json(board: Board, *args: str) -> Dict[str, Any]:
    return json.loads(board.ok("diff", *args, "--json").stdout)


def load_module(board: Board) -> Any:
    spec = importlib.util.spec_from_file_location(f"slate_board_{abs(hash(str(board.script)))}", board.script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- diff (#15)


def test_diff_path_added_removed_changed(board: Board, tmp_path: Path) -> None:
    board.write(three())
    other = three()
    other["tickets"][1]["title"] = "Renamed there"
    other["tickets"][2]["labels"] = ["later"]
    other["tickets"].append(full_ticket(4))
    del other["tickets"][0]["technical"]
    d = diff_json(board, str(other_file(tmp_path, other)))
    assert [x["id"] for x in d["added"]] == ["ACME-004"] and d["removed"] == []
    assert d["changed"]["ACME-002"]["changed"]["title"] == {"here": "Ticket number 2", "there": "Renamed there"}
    assert d["changed"]["ACME-003"]["changed"]["labels"] == {"here": [], "there": ["later"]}
    assert d["changed"]["ACME-001"]["removed"] == {"technical": "Files: x.py"}
    assert d["same"] is False
    out = board.ok("diff", str(tmp_path / "other.json")).stdout
    assert "+ ACME-004" in out and "~ ACME-002" in out and "sync --from" in out


def test_diff_directory_forms(board: Board, tmp_path: Path) -> None:
    board.write(three())
    other = three()
    other["tickets"].pop()
    (tmp_path / "wt" / "kanban").mkdir(parents=True)
    (tmp_path / "wt" / "kanban" / "tickets.json").write_text(json.dumps(other), encoding="utf-8")
    assert [x["id"] for x in diff_json(board, str(tmp_path / "wt"))["removed"]] == ["ACME-003"]
    (tmp_path / "flat").mkdir()
    (tmp_path / "flat" / "tickets.json").write_text(json.dumps(other), encoding="utf-8")
    assert [x["id"] for x in diff_json(board, str(tmp_path / "flat"))["removed"]] == ["ACME-003"]
    (tmp_path / "empty").mkdir()
    r = board.fail("diff", str(tmp_path / "empty"))
    assert "no kanban/tickets.json" in r.stderr and "fix:" in r.stderr


def test_diff_git_ref(board: Board) -> None:
    make_repo(board)
    git(board.root, "checkout", "-q", "-b", "feat")
    board.ok("edit", "ACME-003", "title=Changed on feat")
    d = diff_json(board, "main")
    assert d["changed"]["ACME-003"]["changed"]["title"]["there"] == "Ticket number 3"
    r = board.fail("diff", "no-such-branch")
    assert "not a file, a folder, or a git branch" in r.stderr and "fix:" in r.stderr


def test_diff_ignores_rank_only_unless_asked(board: Board, tmp_path: Path) -> None:
    board.write(three())
    other = three()
    other["tickets"][2]["rank"] = 10
    p = other_file(tmp_path, other)
    assert diff_json(board, str(p))["same"] is True
    assert "No differences" in board.ok("diff", str(p)).stdout
    d = diff_json(board, str(p), "--include-rank")
    assert d["changed"]["ACME-003"]["changed"]["rank"] == {"here": 3, "there": 10}


def test_diff_handoff_ignores_dates(board: Board, tmp_path: Path) -> None:
    doc = three()
    doc["tickets"][0]["handoff"] = [{"date": "2026-09-20", "status": "in_progress", "note": "Started"}]
    board.write(doc)
    other = three()
    other["tickets"][0]["handoff"] = [{"date": "2026-09-26", "status": "in_progress", "note": "Started"}]
    assert diff_json(board, str(other_file(tmp_path, other)))["same"] is True
    other["tickets"][0]["handoff"].append({"date": "2026-09-26", "status": "review", "note": "Done"})
    d = diff_json(board, str(other_file(tmp_path, other)))
    assert d["changed"]["ACME-001"]["changed"]["handoff"]["only_there"][0]["note"] == "Done"


# --------------------------------------------------------------------------- sync (#16)


def test_sync_new_tickets_unions_and_status(board: Board, tmp_path: Path) -> None:
    doc = three()
    doc["tickets"][0].update(status="review", handoff=[{"date": "2026-09-20", "status": "review", "note": "ours"}],
                             commits=[{"sha": "aaaaaaa", "date": "2026-09-20", "message": "a"}],
                             item_checks={"acceptance:0": {"date": "2026-09-20", "evidence": "ours"}})
    doc["tickets"][2]["user_tests"] = [dict(USER_TEST, required=False)]
    board.write(doc)
    other = three()
    other["tickets"][0].update(status="in_progress",
                               handoff=[{"date": "2026-09-21", "status": "in_progress", "note": "theirs"}],
                               commits=[{"sha": "bbbbbbb", "date": "2026-09-21", "message": "b"}],
                               item_checks={"test:0": {"date": "2026-09-21", "evidence": "theirs"}})
    other["tickets"][1]["status"] = "in_progress"
    other["tickets"][1]["depends_on"] = ["ACME-001"]
    other["tickets"][2]["user_tests"] = [dict(USER_TEST, required=False)]
    other["tickets"][2]["user_checks"] = {"0": {"result": "pass", "date": "2026-09-21", "note": ""}}
    other["tickets"].insert(1, full_ticket(4, rank=2))
    for i, t in enumerate(other["tickets"], 1):
        t["rank"] = i
    r = board.ok("sync", "--from", str(other_file(tmp_path, other)))
    assert "+ ACME-004" in r.stdout
    t1 = board.ticket("ACME-001")
    assert t1["status"] == "review"  # further along wins
    assert [h["note"] for h in t1["handoff"]] == ["ours", "theirs"]
    assert [c["sha"] for c in t1["commits"]] == ["aaaaaaa", "bbbbbbb"]
    assert set(t1["item_checks"]) == {"acceptance:0", "test:0"}
    assert board.ticket("ACME-002")["status"] == "in_progress"  # further along (open deps are allowed there)
    assert board.ticket("ACME-003")["user_checks"]["0"]["result"] == "pass"
    ranks = {t["id"]: t["rank"] for t in board.load()["tickets"]}
    assert ranks["ACME-001"] < ranks["ACME-004"] < ranks["ACME-002"] < ranks["ACME-003"]
    assert len(set(ranks.values())) == 4
    board.ok("check")


def test_sync_status_further_along(board: Board, tmp_path: Path) -> None:
    board.write(three())
    other = three()
    other["tickets"][2]["status"] = "in_progress"
    board.ok("sync", "--from", str(other_file(tmp_path, other)))
    assert board.ticket("ACME-003")["status"] == "in_progress"


def test_sync_prefer_theirs_default_and_ours(board: Board, tmp_path: Path) -> None:
    board.write(three())
    other = three()
    other["tickets"][2]["title"] = "Their title"
    p = other_file(tmp_path, other)
    board.ok("sync", "--from", str(p), "--prefer", "ours")
    assert board.ticket("ACME-003")["title"] == "Ticket number 3"
    board.ok("sync", "--from", str(p))
    assert board.ticket("ACME-003")["title"] == "Their title"
    assert "Nothing to sync" in board.ok("sync", "--from", str(p)).stdout


def test_sync_id_clash_refused(board: Board, tmp_path: Path) -> None:
    board.write(three())
    before = board.tickets.read_bytes()
    other = three()
    other["tickets"][2].update(title="A different ticket", summary="Something else entirely")
    other["tickets"].append(full_ticket(4))
    r = board.fail("sync", "--from", str(other_file(tmp_path, other)))
    assert "ACME-003 id: is a different ticket on each board" in r.stderr
    assert "ask the user:" in r.stderr and "--only ACME-001,ACME-002,ACME-004" in r.stderr
    assert board.tickets.read_bytes() == before


def test_sync_dry_run_and_only(board: Board, tmp_path: Path) -> None:
    board.write(three())
    before = board.tickets.read_bytes()
    other = three()
    other["tickets"].append(full_ticket(4))
    other["tickets"].append(full_ticket(5))
    p = other_file(tmp_path, other)
    out = board.ok("sync", "--from", str(p), "--dry-run").stdout
    assert "Dry run: nothing saved" in out and "+ ACME-004" in out and "+ ACME-005" in out
    assert board.tickets.read_bytes() == before
    board.ok("sync", "--from", str(p), "--only", "ACME-005")
    ids = [t["id"] for t in board.load()["tickets"]]
    assert "ACME-005" in ids and "ACME-004" not in ids
    r = board.fail("sync", "--from", str(p), "--only", "ACME-009")
    assert "ACME-009 id: not on" in r.stderr


def test_sync_from_git_ref(board: Board) -> None:
    make_repo(board)
    git(board.root, "checkout", "-q", "-b", "feat")
    git(board.root, "checkout", "-q", "main")
    board.ok("set", "ACME-003", "in_progress", "--as", "someone")
    commit_all(board, "main moves on")
    git(board.root, "checkout", "-q", "feat")
    board.ok("sync", "--from", "main")
    assert board.ticket("ACME-003")["status"] == "in_progress"


# --------------------------------------------------------------------------- merge driver (#17)


def run_driver(board: Board, tmp_path: Path, base: Any, ours: Any, theirs: Any) -> subprocess.CompletedProcess:
    paths = []
    for name, doc in (("base", base), ("ours", ours), ("theirs", theirs)):
        p = tmp_path / f"{name}.json"
        p.write_text(doc if isinstance(doc, str) else json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        paths.append(str(p))
    return board.run("merge-driver", *paths)


def merged(tmp_path: Path) -> Dict[str, Any]:
    return json.loads((tmp_path / "ours.json").read_text(encoding="utf-8"))


def by_id(doc: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {t["id"]: t for t in doc["tickets"]}


def test_merge_driver_clean_merge_of_different_fields(board: Board, tmp_path: Path) -> None:
    base, ours, theirs = three(), three(), three()
    ours["tickets"][1]["title"] = "Ours title"
    theirs["tickets"][1]["summary"] = "Their summary"
    theirs["tickets"][2]["labels"] = ["x"]
    r = run_driver(board, tmp_path, base, ours, theirs)
    assert r.returncode == 0, r.stderr
    m = by_id(merged(tmp_path))
    assert m["ACME-002"]["title"] == "Ours title" and m["ACME-002"]["summary"] == "Their summary"
    assert m["ACME-003"]["labels"] == ["x"]


def test_merge_driver_both_sides_records_union(board: Board, tmp_path: Path) -> None:
    base, ours, theirs = three(), three(), three()
    ours["tickets"][2].update(status="in_progress", handoff=[{"date": "2026-09-26", "status": "in_progress", "note": "A"}])
    theirs["tickets"][2].update(status="review", handoff=[{"date": "2026-09-26", "status": "review", "note": "B"}],
                                item_checks={"acceptance:0": {"date": "2026-09-26", "evidence": "t"}})
    ours["tickets"][2]["commits"] = [{"sha": "aaaaaaa", "date": "2026-09-26", "message": "a"}]
    theirs["tickets"][2]["commits"] = [{"sha": "bbbbbbb", "date": "2026-09-26", "message": "b"}]
    r = run_driver(board, tmp_path, base, ours, theirs)
    assert r.returncode == 0, r.stderr
    t = by_id(merged(tmp_path))["ACME-003"]
    assert t["status"] == "review"
    assert [h["note"] for h in t["handoff"]] == ["A", "B"]
    assert [c["sha"] for c in t["commits"]] == ["aaaaaaa", "bbbbbbb"]
    assert "acceptance:0" in t["item_checks"]


def test_merge_driver_true_conflict_keeps_ours(board: Board, tmp_path: Path) -> None:
    base, ours, theirs = three(), three(), three()
    ours["tickets"][0]["title"] = "Ours"
    theirs["tickets"][0]["title"] = "Theirs"
    theirs["tickets"][2]["labels"] = ["kept"]
    r = run_driver(board, tmp_path, base, ours, theirs)
    assert r.returncode == 1
    assert "slate merge conflict: ACME-001 title: changed on both sides" in r.stderr
    m = by_id(merged(tmp_path))
    assert m["ACME-001"]["title"] == "Ours" and m["ACME-003"]["labels"] == ["kept"]


def test_merge_driver_ranks_unique_and_deps_first(board: Board, tmp_path: Path) -> None:
    base = three()
    ours = three()
    ours["tickets"].append(full_ticket(4, rank=4))
    theirs = three()
    theirs["tickets"].append(full_ticket(5, rank=2, unlocks=["ACME-002"]))
    t = by_id(theirs)
    t["ACME-002"].update(depends_on=["ACME-001", "ACME-005"], rank=3)
    t["ACME-003"]["rank"] = 4
    t["ACME-001"]["unlocks"] = ["ACME-002"]
    r = run_driver(board, tmp_path, base, ours, theirs)
    assert r.returncode == 0, r.stderr
    m = merged(tmp_path)
    ranks = {x["id"]: x["rank"] for x in m["tickets"]}
    assert len(set(ranks.values())) == 5
    assert ranks["ACME-005"] < ranks["ACME-002"] and ranks["ACME-001"] < ranks["ACME-002"]
    assert by_id(m)["ACME-005"]["unlocks"] == ["ACME-002"]
    board.write(m)
    board.ok("check")


def test_merge_driver_deletions_and_bad_input(board: Board, tmp_path: Path) -> None:
    base, ours, theirs = three(), three(), three()
    theirs["tickets"].pop()  # deleted on their side, untouched on ours
    assert run_driver(board, tmp_path, base, ours, theirs).returncode == 0
    assert "ACME-003" not in by_id(merged(tmp_path))
    r = run_driver(board, tmp_path, base, three(), "<<<<<<< not json")
    assert r.returncode == 1 and "not a valid board" in r.stderr


def test_install_merge_driver_is_idempotent(board: Board) -> None:
    make_repo(board)
    (board.root / ".gitattributes").write_text("*.png binary", encoding="utf-8")
    board.ok("install-merge-driver", "--python", "python3")
    board.ok("install-merge-driver", "--python", "python3")
    attrs = (board.root / ".gitattributes").read_text(encoding="utf-8")
    assert attrs == "*.png binary\nkanban/tickets.json merge=slate text eol=lf\n"
    assert git(board.root, "config", "merge.slate.driver").stdout.strip() == \
        "python3 kanban/board.py merge-driver %O %A %B"
    assert git(board.root, "config", "merge.slate.name").stdout.strip() == "Slate board merge"


def test_install_merge_driver_needs_git(board: Board) -> None:
    board.write(three())
    r = board.fail("install-merge-driver")
    assert "isn't a git repository" in r.stderr and "fix:" in r.stderr


def test_git_merge_end_to_end_with_driver(board: Board) -> None:
    make_repo(board)
    git(board.root, "checkout", "-q", "-b", "a")
    board.ok("edit", "ACME-002", "title=Title from A")
    board.ok("set", "ACME-001", "in_progress", "--handoff", "started on A")
    commit_all(board, "a")
    git(board.root, "checkout", "-q", "main")
    git(board.root, "checkout", "-q", "-b", "b")
    board.ok("edit", "ACME-002", "summary=Summary from B")
    board.ok("set", "ACME-001", "in_progress", "--handoff", "started on B")
    commit_all(board, "b")
    git(board.root, "checkout", "-q", "a")
    # without the driver, git's line merge conflicts (adjacent lines, both appended handoff notes)
    assert git(board.root, "merge", "-q", "b", "-m", "merge", check=False).returncode != 0
    git(board.root, "merge", "--abort")
    board.ok("install-merge-driver", "--python", shlex.quote(sys.executable))
    commit_all(board, "merge driver")
    r = git(board.root, "merge", "-q", "b", "-m", "merge b", check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    t2, t1 = board.ticket("ACME-002"), board.ticket("ACME-001")
    assert t2["title"] == "Title from A" and t2["summary"] == "Summary from B"
    assert [h["note"] for h in t1["handoff"]] == ["started on A", "started on B"]
    assert "<<<<<<<" not in board.tickets.read_text(encoding="utf-8")
    board.ok("check")


# --------------------------------------------------------------------------- board of record (#18)


def test_worktree_warning(board: Board, tmp_path: Path) -> None:
    make_repo(board)
    wt = tmp_path / "wt"
    git(board.root, "worktree", "add", "-q", str(wt), "-b", "feat")
    r = subprocess.run([sys.executable, str(wt / "kanban" / "board.py"), "set-meta", "project=Other"],
                       capture_output=True, text=True, encoding="utf-8", cwd=str(wt))
    assert r.returncode == 0, r.stderr
    assert "warning: this is a secondary git worktree" in r.stderr
    assert "fix: python3 kanban/board.py diff" in r.stderr and "kanban" in r.stderr.split("board of record")[1]
    main_r = board.ok("set-meta", "project=Main")
    assert "secondary git worktree" not in main_r.stderr


def test_behind_default_branch_warning(board: Board) -> None:
    doc = three()
    doc["tickets"].append(full_ticket(4))
    doc["tickets"][2]["handoff"] = [{"date": "2026-09-26", "status": "backlog", "note": "note on main"}]
    make_repo(board, doc)
    git(board.root, "checkout", "-q", "-b", "feat")
    board.write(three())
    r = board.ok("edit", "ACME-001", "estimate=2d")
    assert "warning: the board on main has changes this board lacks" in r.stderr
    assert "ACME-004" in r.stderr and "ACME-003 handoff: 1 note only there" in r.stderr
    assert "fix: python3 kanban/board.py diff main" in r.stderr
    assert "fix: python3 kanban/board.py sync --from main" in r.stderr


def test_board_of_record_env(board: Board, tmp_path: Path) -> None:
    board.write(three())
    other = other_file(tmp_path, three(), "record.json")
    env = dict(os.environ, SLATE_BOARD_OF_RECORD=str(other))
    r = subprocess.run([sys.executable, str(board.script), "edit", "ACME-001", "estimate=2d"],
                       capture_output=True, text=True, encoding="utf-8", cwd=str(board.root), env=env)
    assert r.returncode == 0 and "warning: SLATE_BOARD_OF_RECORD is" in r.stderr and "fix:" in r.stderr
    env["SLATE_BOARD_OF_RECORD"] = str(board.root)  # a folder holding this very board
    r = subprocess.run([sys.executable, str(board.script), "edit", "ACME-001", "estimate=3d"],
                       capture_output=True, text=True, encoding="utf-8", cwd=str(board.root), env=env)
    assert r.returncode == 0 and "SLATE_BOARD_OF_RECORD" not in r.stderr


# --------------------------------------------------------------------------- copy-to (#19)


def test_copy_to_file_refusal_and_force(board: Board, tmp_path: Path) -> None:
    board.write(three())
    target = tmp_path / "copy.json"
    board.ok("copy-to", str(target))
    assert json.loads(target.read_text(encoding="utf-8")) == board.load()
    richer = three()
    richer["tickets"].append(full_ticket(4))
    target.write_text(json.dumps(richer), encoding="utf-8")
    r = board.fail("copy-to", str(target))
    assert "has changes this board lacks" in r.stderr and "ACME-004" in r.stderr and "--force" in r.stderr
    assert "ACME-004" in target.read_text(encoding="utf-8")
    board.ok("export-file", str(target), "--force")
    assert json.loads(target.read_text(encoding="utf-8")) == board.load()


def test_copy_to_directory_and_invalid_board(board: Board, tmp_path: Path) -> None:
    board.write(three())
    (tmp_path / "wt" / "kanban").mkdir(parents=True)
    board.ok("copy-to", str(tmp_path / "wt"))
    assert (tmp_path / "wt" / "kanban" / "tickets.json").is_file()
    (tmp_path / "bare").mkdir()
    assert "has no kanban/ folder" in board.fail("copy-to", str(tmp_path / "bare")).stderr
    doc = three()
    del doc["tickets"][0]["story"]
    board.write(doc)
    assert "not copied: kanban/tickets.json has errors" in board.fail("copy-to", str(tmp_path / "x.json")).stderr


# --------------------------------------------------------------------------- repair writes


def broken_two() -> Dict[str, Any]:
    doc = three()
    del doc["tickets"][0]["story"]
    del doc["tickets"][1]["story"]
    return doc


def test_repair_write_that_reduces_errors_is_allowed(board: Board) -> None:
    board.write(broken_two())
    r = board.ok("edit", "ACME-001", "story=Priya does it")
    assert "repair: 1 error left" in r.stdout
    r = board.ok("edit", "ACME-002", "story=Priya does it too")
    assert "repair: 0 errors left (the board is valid again)" in r.stdout
    board.ok("check")


def test_repair_writes_refuse_adding_or_not_reducing(board: Board) -> None:
    board.write(broken_two())
    before = board.tickets.read_bytes()
    r = board.fail("edit", "ACME-003", "title=Unrelated")
    assert "has errors, so nothing was changed" in r.stderr and "ACME-001 story" in r.stderr
    r = board.fail("edit", "ACME-001", "story=fixed", "depends_on:=[\"ACME-999\"]")
    assert "would add new ones" in r.stderr and "ACME-999" in r.stderr
    assert board.tickets.read_bytes() == before


def test_sync_and_lock_work_on_invalid_board(board: Board, tmp_path: Path) -> None:
    board.write(broken_two())
    other = broken_two()
    other["tickets"].append(full_ticket(4))
    board.ok("sync", "--from", str(other_file(tmp_path, other)))  # no new errors: allowed
    assert "ACME-004" in [t["id"] for t in board.load()["tickets"]]
    board.ok("lock")
    assert board.load()["meta"]["unlock_log"][-1]["event"] == "locked"


# --------------------------------------------------------------------------- write lock


def test_concurrent_writes_all_land(board: Board) -> None:
    board.write(three())
    procs = [subprocess.Popen([sys.executable, str(board.script), "new", "--title", f"Parallel {i}", "--summary", "s",
                               "--phase", "P1", "--story", "s", "--description", "d", "--acceptance", "a",
                               "--test", "When a, then b", "--areas", "backend"],
                              cwd=str(board.root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
             for i in range(4)]
    results = [p.communicate(timeout=60) + (p.returncode,) for p in procs]
    assert all(code == 0 for _, _, code in results), results
    titles = {t["title"] for t in board.load()["tickets"]}
    assert {f"Parallel {i}" for i in range(4)} <= titles
    assert len(board.load()["tickets"]) == 7
    assert not (board.dir / ".slate-write.lock").exists()
    board.ok("check")


def write_lock(board: Board, pid: int, age: float = 0.0) -> Path:
    p = board.dir / ".slate-write.lock"
    p.write_text(json.dumps({"pid": pid, "host": socket.gethostname(), "time": "2026-09-26T10:00:00Z"}),
                 encoding="utf-8")
    if age:
        t = time.time() - age
        os.utime(p, (t, t))
    return p


def test_held_lock_refuses_after_waiting(board: Board, monkeypatch: pytest.MonkeyPatch,
                                         capsys: pytest.CaptureFixture[str]) -> None:
    board.write(three())
    lock = write_lock(board, os.getpid())
    mod = load_module(board)
    monkeypatch.setattr(mod, "LOCK_WAIT_SECONDS", 0.3)
    assert mod.main(["set-meta", "project=Other"]) == 1
    err = capsys.readouterr().err
    assert "another board.py command is changing the board" in err
    assert "fix: python3 kanban/board.py unlock-write   (remove stale lock" in err
    assert lock.exists() and board.load()["meta"]["project"] == "Acme"


def test_unlock_write_only_removes_stale_locks(board: Board) -> None:
    board.write(three())
    lock = write_lock(board, os.getpid())
    r = board.fail("unlock-write")
    assert "isn't stale" in r.stderr and lock.exists()
    write_lock(board, os.getpid(), age=120)
    assert "Removed a stale write lock" in board.ok("unlock-write").stdout and not lock.exists()
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    write_lock(board, dead.pid)
    assert "is gone" in board.ok("unlock-write").stdout
    assert "nothing to remove" in board.ok("unlock-write").stdout


# --------------------------------------------------------------------------- claims


def test_set_in_progress_claims_by_branch(board: Board) -> None:
    make_repo(board)
    git(board.root, "checkout", "-q", "-b", "feat/a")
    board.ok("set", "ACME-001", "in_progress")
    c = board.ticket("ACME-001")["claimed_by"]
    assert c["by"] == "feat/a" and len(c["since"]) == 16
    board.ok("set", "ACME-001", "review", "--handoff", "x")
    assert board.ticket("ACME-001")["claimed_by"]["by"] == "feat/a"  # review keeps it
    board.ok("set", "ACME-001", "backlog")
    assert "claimed_by" not in board.ticket("ACME-001")


def test_claims_next_list_takeover(board: Board) -> None:
    board.write(three())
    board.ok("set", "ACME-001", "in_progress", "--as", "alice")
    out = board.ok("next", "--as", "bob").stdout
    assert "Being worked on elsewhere" in out and "on: alice" in out
    assert "Resume first" not in out and "ACME-003" in out.split("Next ticket")[1]
    assert "Resume first" in board.ok("next", "--as", "alice").stdout
    r = board.fail("set", "ACME-001", "review", "--handoff", "x", "--as", "bob")
    assert "ACME-001 claimed_by: being worked on by alice" in r.stderr
    assert "ask the user:" in r.stderr and "--take-over" in r.stderr
    board.ok("set", "ACME-001", "review", "--handoff", "x", "--as", "bob", "--take-over", "alice is away")
    t = board.ticket("ACME-001")
    assert t["claimed_by"]["by"] == "bob" and "took over from alice: alice is away" in t["handoff"][-1]["note"]


def test_claim_release_list_status(board: Board) -> None:
    board.write(three())
    board.ok("claim", "ACME-003", "--as", "alice")
    assert "ACME-003" not in board.ok("list", "--as", "bob").stdout
    assert "on: alice" in board.ok("list", "--as", "alice").stdout
    r = board.fail("claim", "ACME-003", "--as", "bob")
    assert "ask the user:" in r.stderr and "--take-over" in r.stderr
    assert "ask the user:" in board.fail("release", "ACME-003", "--as", "bob").stderr
    status = board.ok("status").stdout
    assert "Claimed (who is on what)" in status and "ACME-003  on: alice" in status
    assert json.loads(board.ok("status", "--json").stdout)["claims"][0]["by"] == "alice"
    board.ok("release", "ACME-003", "--as", "alice")
    assert "claimed_by" not in board.ticket("ACME-003")
    board.ok("claim", "ACME-003", "--as", "bob")
    board.ok("claim", "ACME-003", "--as", "carol", "--take-over", "bob left")
    t = board.ticket("ACME-003")
    assert t["claimed_by"]["by"] == "carol" and t["handoff"][-1]["note"] == "Took over from bob: bob left"
    assert "claims have their own commands" in board.fail("edit", "ACME-003", "claimed_by:=null").stderr


def test_bad_claim_is_a_validation_error(board: Board) -> None:
    doc = three()
    doc["tickets"][0]["claimed_by"] = {"by": "", "since": "now"}
    board.write(doc)
    r = board.fail("check")
    assert "ACME-001 claimed_by: must be" in r.stderr and "fix:" in r.stderr


# --------------------------------------------------------------------------- doctor


def codes(board: Board, *args: str) -> Dict[str, Dict[str, Any]]:
    r = board.run("doctor", "--json", *args)
    return {p["code"]: p for p in json.loads(r.stdout)["problems"]}


def test_doctor_healthy_outside_git(board: Board) -> None:
    board.write(three_current())
    r = board.ok("doctor")
    assert "ok: no problems found" in r.stdout
    assert board.ok("doctor", "--brief").stdout.strip() == "Slate: healthy"


def test_doctor_git_setup_problems_and_fixes(board: Board) -> None:
    make_repo(board, three_current())
    git(board.root, "remote", "add", "origin", "git@github.com:acme/app.git")
    c = codes(board)
    assert {"merge-driver-missing", "gitignore-missing", "repo-url-missing"} <= set(c)
    assert all(p["kind"] == "setup" and p["fix"] for p in c.values())
    assert c["repo-url-missing"]["fix"] == ["python3 kanban/board.py set-meta repo_url=https://github.com/acme/app"]
    assert board.run("doctor").returncode == 1
    brief = board.run("doctor", "--brief").stdout.strip()
    assert brief == "Slate: 3 setup issues — run /slate:upgrade"
    board.ok("install-merge-driver", "--python", "python3")
    (board.root / ".gitignore").write_text("kanban/.slate-unlock*.json\nkanban/.slate-write.lock\n"
                                           "kanban/.slate-serve.json\nkanban/.slate-serve.log\n", encoding="utf-8")
    board.ok("set-meta", "repo_url=https://github.com/acme/app")
    assert codes(board) == {}


def test_doctor_board_behind_is_tickets_kind(board: Board) -> None:
    doc = three()
    doc["tickets"].append(full_ticket(4))
    make_repo(board, doc)
    git(board.root, "checkout", "-q", "-b", "feat")
    board.write(three())
    c = codes(board)
    assert c["board-behind"]["kind"] == "tickets"
    assert c["board-behind"]["fix"] == ["python3 kanban/board.py diff main",
                                        "python3 kanban/board.py sync --from main --dry-run"]
    assert "board behind main — run /slate:sync" in board.run("doctor", "--brief").stdout


def test_doctor_state_and_slate_md(board: Board, tmp_path: Path) -> None:
    board.write(three())
    write_lock(board, os.getpid(), age=300)
    root = tmp_path / "plugin"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"version": VERSION}), encoding="utf-8")
    (root / "templates").mkdir()
    (root / "templates" / "SLATE.md").write_text("# x\n## Commands\n## Board of record\n", encoding="utf-8")
    c = codes(board, "--against", str(root))
    assert c["write-lock-stale"]["fix"] == ["python3 kanban/board.py unlock-write"]
    assert "slate-md-missing" in c
    (board.root / "SLATE.md").write_text("# x\n## Commands\nBoard: kanban\n", encoding="utf-8")
    c = codes(board, "--against", str(root))
    assert "Board of record" in c["slate-md-sections"]["message"] and "python-cmd-missing" in c
    (board.root / "SLATE.md").write_text(f"## Commands\nPython: `{Path(sys.executable).name}`\n## Board of record\n",
                                         encoding="utf-8")
    c = codes(board, "--against", str(root))
    assert "slate-md-sections" not in c and "python-cmd-missing" not in c


def test_next_brief_carries_doctor_findings(board: Board, tmp_path: Path) -> None:
    make_repo(board)
    root = tmp_path / "plugin"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"version": VERSION}), encoding="utf-8")
    out = board.ok("next", "--brief", "--against", str(root)).stdout.strip()
    assert out.endswith("· 2 setup issues — run /slate:upgrade")
    assert "setup issue" not in board.ok("next", "--brief").stdout  # only with --against (SessionStart)
