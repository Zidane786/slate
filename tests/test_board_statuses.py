"""Tests for customizable statuses (roles, labels), path rules (meta.status_from, workflow presets),
and the housekeeping commands: remove / restore, unlink, usertest reset, note, bulk edit,
set-meta priorities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from conftest import VERSION, USER_TEST, Board, base_doc, full_ticket

V2 = ["draft", "backlog", "ready", "in_progress", "review", "user_testing", "merge_ready", "done"]


def v2_doc(tickets: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    d = base_doc(tickets)
    d["meta"].update({"slate_version": VERSION, "schema_version": 2, "statuses": list(V2)})
    return d


@pytest.fixture
def b(board: Board) -> Board:
    board.write(v2_doc([full_ticket(1, unlocks=["ACME-002"]), full_ticket(2, depends_on=["ACME-001"]),
                        full_ticket(3)]))
    return board


def meta(board: Board) -> Dict[str, Any]:
    return board.load()["meta"]


# --------------------------------------------------------------------------- roles and labels


def test_add_status_with_role_and_label(b: Board) -> None:
    b.ok("add-status", "qa", "--after", "review", "--like", "review", "--label", "QA")
    m = meta(b)
    assert m["statuses"][m["statuses"].index("review") + 1] == "qa"
    assert m["status_roles"] == {"qa": "review"} and m["status_labels"] == {"qa": "QA"}
    b.ok("set", "ACME-003", "in_progress")
    assert "needs a note" in b.fail("set", "ACME-003", "qa").stderr  # the review role's rule
    b.ok("set", "ACME-003", "qa", "--handoff", "ready for QA")
    assert "(QA)" in b.ok("show", "ACME-003").stdout.splitlines()[1] or "status QA" in b.ok("show", "ACME-003").stdout
    assert "ACME-003" in b.ok("next").stdout.split("Resume first")[1]  # review role: resumable
    assert "QA 1" in b.ok("status").stdout
    ex = json.loads(b.ok("export", "--json").stdout)
    assert next(t for t in ex if t["id"] == "ACME-003")["status_label"] == "QA"
    setup = json.loads(b.ok("export", "--json", "--statuses").stdout)
    assert {"name": "qa", "role": "review", "label": "QA", "from": [], "note": "required"} in setup["statuses"]


def test_add_status_refusals(b: Board) -> None:
    assert "lowercase letters" in b.fail("add-status", "Q A", "--after", "review", "--like", "review").stderr
    assert "already exists" in b.fail("add-status", "review", "--after", "done", "--like", "review").stderr
    assert "neither a role" in b.fail("add-status", "qa", "--after", "review", "--like", "nope").stderr
    assert "did you mean" in b.fail("add-status", "qa", "--after", "reveiw", "--like", "review").stderr


def test_rename_done_keeps_role_and_readiness(b: Board) -> None:
    doc = b.load()
    doc["tickets"][0]["status"] = "done"
    doc["tickets"][0]["handoff"] = [{"date": "2026-09-26", "status": "done", "note": "landed"}]
    b.write(doc)
    b.ok("rename-status", "done", "shipped")
    m = meta(b)
    assert "shipped" in m["statuses"] and "done" not in m["statuses"]
    assert m["status_roles"] == {"shipped": "done"}
    t1 = b.ticket("ACME-001")
    assert t1["status"] == "shipped" and t1["handoff"][0]["status"] == "done"  # history keeps the old name
    assert "ACME-002" in b.ok("list").stdout  # ACME-001 still counts as done
    b.ok("check")


def test_edit_status_label_role_and_refusal(b: Board) -> None:
    b.ok("edit-status", "in_progress", "label=Doing")
    b.ok("set", "ACME-003", "in_progress")
    assert "(Doing)" in b.ok("show", "ACME-003").stdout or "status Doing" in b.ok("show", "ACME-003").stdout
    assert "Doing 1" in b.ok("status").stdout
    doc = b.load()
    doc["tickets"][1].update(areas=["frontend"], user_tests=[USER_TEST], status="review",
                             handoff=[{"date": "2026-09-26", "status": "review", "note": "x"}])
    doc["tickets"][0]["status"] = "done"
    b.write(doc)
    r = b.fail("edit-status", "review", "role=done")  # ACME-002's required user test hasn't passed
    assert "would make ACME-002 invalid" in r.stderr
    assert "status_roles" not in meta(b)  # nothing was changed
    b.ok("edit-status", "in_progress", "label=")
    assert "status_labels" not in meta(b)


def test_reorder_statuses(b: Board) -> None:
    r = b.fail("reorder-statuses", "backlog", "draft")
    assert "list every status exactly once" in r.stderr and "fix:" in r.stderr
    order = ["draft", "backlog", "ready", "in_progress", "user_testing", "review", "merge_ready", "done"]
    b.ok("reorder-statuses", *order)
    assert meta(b)["statuses"] == order


def test_remove_status_move_and_invariants(b: Board) -> None:
    b.ok("set", "ACME-003", "in_progress")
    r = b.fail("remove-status", "in_progress")
    assert "1 ticket is in it (ACME-003)" in r.stderr and "--move-to" in r.stderr
    b.ok("remove-status", "in_progress", "--move-to", "review")
    assert b.ticket("ACME-003")["status"] == "review" and "in_progress" not in meta(b)["statuses"]
    r = b.fail("remove-status", "done")
    assert "no status with the done role" in r.stderr
    b.ok("remove-status", "user_testing")
    b.ok("remove-status", "draft")
    r = b.fail("new", "--title", "Later", "--summary", "s", "--phase", "P1", "--draft")
    assert "no status has the draft role" in r.stderr and "add-status draft --first --like draft" in r.stderr
    b.ok("add-status", "draft", "--first", "--like", "draft")
    b.ok("new", "--title", "Later", "--summary", "s", "--phase", "P1", "--draft")


def test_usertest_works_without_user_testing_status(b: Board) -> None:
    doc = b.load()
    doc["tickets"][2].update(areas=["frontend"], user_tests=[USER_TEST])
    b.write(doc)
    b.ok("remove-status", "user_testing")
    b.ok("usertest", "ACME-003", "0", "pass")
    assert b.ticket("ACME-003")["user_checks"]["0"]["result"] == "pass"


def test_check_validates_status_meta(b: Board) -> None:
    doc = b.load()
    doc["meta"]["status_roles"] = {"review": "reviewing", "ghost": "done"}
    doc["meta"]["status_labels"] = {"review": 7}
    b.write(doc)
    r = b.fail("check")
    assert "meta status_roles: review: role 'reviewing' must be one of" in r.stderr
    assert "meta status_roles: 'ghost' is not one of meta.statuses" in r.stderr
    assert "meta status_labels: review: the label must be text" in r.stderr


def test_sync_further_along_uses_roles(b: Board, tmp_path: Path) -> None:
    b.ok("add-status", "qa", "--after", "review", "--like", "review")
    b.ok("set", "ACME-003", "in_progress")
    other = b.load()
    next(t for t in other["tickets"] if t["id"] == "ACME-003")["status"] = "qa"
    p = tmp_path / "o.json"
    p.write_text(json.dumps(other), encoding="utf-8")
    b.ok("sync", "--from", str(p))
    assert b.ticket("ACME-003")["status"] == "qa"


# --------------------------------------------------------------------------- path rules


def test_strict_workflow_forward_refusal_with_next_step(b: Board) -> None:
    b.ok("set-meta", "workflow=strict")
    rules = meta(b)["status_from"]
    assert rules["in_progress"] == ["backlog", "ready"] and rules["done"] == ["merge_ready"]
    r = b.fail("set", "ACME-003", "review", "--handoff", "x")
    assert "ACME-003 status: can't move backlog → review" in r.stderr
    assert "review can only be reached from: in_progress" in r.stderr
    assert "fix: python3 kanban/board.py set ACME-003 in_progress" in r.stderr
    b.ok("set", "ACME-003", "in_progress")
    b.ok("set", "ACME-003", "review", "--handoff", "built")
    assert "Workflow: strict" in b.ok("show", "ACME-003").stdout
    assert "workflow: strict" in b.ok("status").stdout
    assert json.loads(b.ok("export", "--json", "--statuses").stdout)["workflow"] == "strict"


def test_backward_moves_need_a_reason_under_rules(b: Board) -> None:
    b.ok("set", "ACME-003", "in_progress")
    b.ok("set", "ACME-003", "backlog")  # no rules yet: as before
    b.ok("set", "ACME-003", "in_progress")
    b.ok("set-meta", "workflow=strict")
    r = b.fail("set", "ACME-003", "backlog")
    assert "moving back in_progress → backlog needs a reason" in r.stderr and "--handoff" in r.stderr
    b.ok("set", "ACME-003", "backlog", "--handoff", "paused")


def test_bulk_set_with_rules_is_all_or_nothing(b: Board) -> None:
    b.ok("set", "ACME-001", "in_progress")
    b.ok("set-meta", "workflow=strict")
    before = b.tickets.read_bytes()
    r = b.fail("set", "ACME-001,ACME-003", "review", "--handoff", "x")
    assert "nothing was changed" in r.stderr and "can't move backlog → review" in r.stderr
    assert b.tickets.read_bytes() == before


def test_strict_preset_without_merge_ready(board: Board) -> None:
    board.write(base_doc([full_ticket(1)]))  # schema 1 statuses: no merge_ready
    board.ok("set-meta", "workflow=strict")
    rules = board.load()["meta"]["status_from"]
    assert rules["done"] == ["user_testing", "review"] and "merge_ready" not in rules
    board.ok("set-meta", "workflow=free")
    assert "status_from" not in board.load()["meta"]


def test_edit_status_from_and_rename_remove_update_rules(b: Board) -> None:
    b.ok("edit-status", "review", "from=in_progress,ready")
    assert meta(b)["status_from"] == {"review": ["in_progress", "ready"]}
    assert "not one of meta.statuses" in b.fail("edit-status", "review", "from=nope").stderr
    b.ok("rename-status", "ready", "groomed")
    assert meta(b)["status_from"] == {"review": ["in_progress", "groomed"]}
    out = b.ok("remove-status", "groomed").stdout
    assert "dropped groomed from the statuses review can be reached from" in out
    assert meta(b)["status_from"] == {"review": ["in_progress"]}
    b.ok("edit-status", "review", "from=")
    assert "status_from" not in meta(b)


def test_sync_ignores_path_rules(b: Board, tmp_path: Path) -> None:
    other = b.load()
    next(t for t in other["tickets"] if t["id"] == "ACME-003").update(
        status="review", handoff=[{"date": "2026-09-26", "status": "review", "note": "there"}])
    b.ok("set-meta", "workflow=strict")
    p = tmp_path / "o.json"
    p.write_text(json.dumps(other), encoding="utf-8")
    b.ok("sync", "--from", str(p))
    assert b.ticket("ACME-003")["status"] == "review"


def test_promote_not_blocked_by_rules(b: Board) -> None:
    b.ok("new", "--title", "Idea", "--summary", "s", "--phase", "P1", "--draft")
    b.ok("edit-status", "backlog", "from=ready")
    b.ok("edit", "ACME-004", "story=s", "description=d", "acceptance:=[\"a\"]", "test_scenarios:=[\"When a, then b\"]",
         "areas:=[\"backend\"]")
    b.ok("promote", "ACME-004")
    assert b.ticket("ACME-004")["status"] == "backlog"


# --------------------------------------------------------------------------- remove / restore


def test_remove_detach_archive_and_no_id_reuse(b: Board) -> None:
    r = b.fail("remove", "ACME-001", "--reason", "not needed")
    assert "ACME-002 depends on it" in r.stderr and "--detach" in r.stderr
    b.ok("remove", "ACME-001", "--reason", "not needed", "--detach")
    doc = b.load()
    assert "ACME-001" not in [t["id"] for t in doc["tickets"]]
    arch = doc["meta"]["removed"][0]
    assert arch["ticket"]["id"] == "ACME-001" and arch["reason"] == "not needed" and arch["removed"]
    t2 = b.ticket("ACME-002")
    assert t2["depends_on"] == [] and "Dependency ACME-001 was removed" in t2["handoff"][-1]["note"]
    b.ok("remove", "ACME-003", "--reason", "dup")
    b.ok("new", "--title", "Fresh", "--summary", "s", "--phase", "P1", "--draft")
    assert "ACME-004" in [t["id"] for t in b.load()["tickets"]]  # 003 (removed) is not reused
    listed = json.loads(b.ok("export", "--json", "--removed").stdout)
    assert [x["ticket"]["id"] for x in listed] == ["ACME-001", "ACME-003"]
    b.ok("check")


def test_remove_together_and_done_needs_force(b: Board) -> None:
    b.ok("remove", "ACME-001,ACME-002", "--reason", "scope cut")  # 002 depends on 001, both go
    doc = b.load()
    doc["tickets"][0]["status"] = "done"
    b.write(doc)
    r = b.fail("remove", "ACME-003", "--reason", "x")
    assert "is done" in r.stderr and "--force-done" in r.stderr
    b.ok("remove", "ACME-003", "--reason", "x", "--force-done", "shipped elsewhere")
    assert b.load()["meta"]["removed"][-1]["force_done"] == "shipped elsewhere"
    assert "--reason is required" in b.fail("remove", "ACME-001").stderr


def test_restore(b: Board) -> None:
    b.ok("remove", "ACME-003", "--reason", "later")
    b.ok("restore", "ACME-003")
    t = b.ticket("ACME-003")
    assert t["rank"] == 3 and "Restored" in t["handoff"][-1]["note"]
    assert "removed" not in b.load()["meta"]
    assert "not in the archive" in b.fail("restore", "ACME-003").stderr
    b.ok("remove", "ACME-001,ACME-002", "--reason", "cut")
    r = b.fail("restore", "ACME-002")
    assert "needs ACME-001" in r.stderr and "restore ACME-001" in r.stderr
    b.ok("restore", "ACME-001")
    b.ok("restore", "ACME-002")
    assert b.ticket("ACME-001")["unlocks"] == ["ACME-002"]
    b.ok("check")


# --------------------------------------------------------------------------- unlink, reset, note, bulk edit, priorities


def test_unlink_commit_and_pr(b: Board) -> None:
    b.ok("link", "ACME-003", "--commit", "abcdef1234", "--commit", "1234567", "--pr", "https://github.com/a/b/pull/3")
    b.ok("unlink", "ACME-003", "--commit", "abcdef", "--reason", "wrong ticket")
    t = b.ticket("ACME-003")
    assert [c["sha"] for c in t["commits"]] == ["1234567"]
    assert t["handoff"][-1]["note"] == "Unlinked commit abcdef1: wrong ticket"
    b.ok("unlink", "ACME-003", "--pr")
    assert "pr" not in b.ticket("ACME-003")
    assert "no linked commit matches" in b.fail("unlink", "ACME-003", "--commit", "ffff").stderr
    assert "no pull request is linked" in b.fail("unlink", "ACME-003", "--pr").stderr


def test_usertest_reset(b: Board) -> None:
    doc = b.load()
    doc["tickets"][2].update(areas=["frontend"], user_tests=[USER_TEST])
    b.write(doc)
    b.ok("usertest", "ACME-003", "0", "pass")
    b.ok("usertest", "ACME-003", "0", "reset", "--note", "retest after fix")
    t = b.ticket("ACME-003")
    assert "user_checks" not in t and "result cleared (was pass): retest after fix" in t["handoff"][-1]["note"]
    assert "nothing changed" in b.ok("usertest", "ACME-003", "0", "reset").stdout
    doc = b.load()
    doc["tickets"][2].update(status="merge_ready", user_checks={"0": {"result": "pass", "date": "2026-09-26", "note": ""}})
    b.write(doc)
    r = b.fail("usertest", "ACME-003", "0", "reset")  # merge_ready needs the pass
    assert "user_checks" in r.stderr


def test_note_single_and_bulk(b: Board) -> None:
    b.ok("note", "ACME-001", "talked to design")
    h = b.ticket("ACME-001")["handoff"][-1]
    assert h["status"] == "backlog" and h["note"] == "talked to design"
    b.ok("note", "ACME-001,ACME-003", "blocked on API keys")
    assert b.ticket("ACME-003")["handoff"][-1]["note"] == "blocked on API keys"
    before = b.tickets.read_bytes()
    assert "nothing was changed" in b.fail("note", "ACME-001,ACME-999", "x").stderr
    assert b.tickets.read_bytes() == before


def test_bulk_edit_all_or_nothing(b: Board) -> None:
    b.ok("edit", "ACME-001,ACME-003", "estimate=3d", "labels:=[\"api\"]")
    assert b.ticket("ACME-001")["estimate"] == "3d" and b.ticket("ACME-003")["labels"] == ["api"]
    before = b.tickets.read_bytes()
    r = b.fail("edit", "ACME-001,ACME-999", "estimate=5d")
    assert "nothing was changed" in r.stderr and "ACME-999" in r.stderr
    assert b.tickets.read_bytes() == before


def test_set_meta_priorities(b: Board) -> None:
    r = b.fail("set-meta", "priorities:=[\"P0\", \"P2\"]")  # full_ticket uses P1
    assert "use a priority that isn't in the new list" in r.stderr and "edit ACME-001 priority=P0" in r.stderr
    b.ok("set-meta", "priorities:=[\"P0\", \"P1\", \"P2\"]")
    assert meta(b)["priorities"] == ["P0", "P1", "P2"]
