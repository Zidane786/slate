"""Tests for per-state behaviour flags (meta.status_flags, 0.3.0): defaults by role, overrides via
edit-status, inheritance via add-status --like, rename/remove, check, workflow --markdown and flow."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest

from conftest import VERSION, Board, base_doc, full_ticket

V3_STATUSES = ["draft", "backlog", "ready", "in_progress", "review", "user_testing", "merge_ready", "done",
               "cancelled"]
CANCELLED_FLAGS = {"resolves_deps": True, "from_any": True, "progress": "excluded", "terminal": True,
                   "notify_dependents": True, "folded": True}
OPEN_FLAGS = {"resolves_deps": False, "from_any": False, "progress": "open", "terminal": False,
              "notify_dependents": False, "folded": False}


def v3_doc(tickets: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    d = base_doc(tickets)
    d["meta"].update({"slate_version": VERSION, "schema_version": 3, "statuses": list(V3_STATUSES),
                      "status_labels": {"cancelled": "Cancelled"}})
    return d


def has_fix(stderr: str) -> bool:
    return "fix: " in stderr or "ask the user: " in stderr


def flags(board: Board) -> Dict[str, Dict[str, Any]]:
    return {s["name"]: s["flags"] for s in json.loads(board.ok("export", "--json", "--statuses").stdout)["statuses"]}


def meta(board: Board) -> Dict[str, Any]:
    return board.load()["meta"]


@pytest.fixture
def b(board: Board) -> Board:
    """001 and 002 on their own; 003 depends on 001."""
    board.write(v3_doc([full_ticket(1, unlocks=["ACME-003"]), full_ticket(2),
                        full_ticket(3, depends_on=["ACME-001"])]))
    return board


# --------------------------------------------------------------------------- defaults, --like


def test_defaults_come_from_the_role(b: Board) -> None:
    f = flags(b)
    assert f["cancelled"] == CANCELLED_FLAGS
    assert f["done"] == dict(OPEN_FLAGS, resolves_deps=True, progress="done", terminal=True)
    for s in ("draft", "backlog", "ready", "in_progress", "review", "user_testing", "merge_ready"):
        assert f[s] == OPEN_FLAGS, s
    assert "status_flags" not in meta(b)


def test_add_status_like_cancelled_inherits_flags(b: Board) -> None:
    out = b.ok("add-status", "wontfix", "--after", "cancelled", "--like", "cancelled", "--label", "Won't fix").stdout
    assert "role cancelled" in out and "handoff note required" in out and "reachable from any state" in out
    m = meta(b)
    assert m["status_roles"]["wontfix"] == "cancelled" and "status_flags" not in m  # same as its role
    assert flags(b)["wontfix"] == CANCELLED_FLAGS
    b.ok("set", "ACME-001", "wontfix", "--handoff", "works as intended")
    assert b.ticket("ACME-001")["cancelled_from"] == "backlog"
    assert b.ticket("ACME-003")["handoff"][-1]["note"] == "depended on ACME-001, Won't fix: works as intended"
    # a state --like a state with overrides takes its effective flags; only the differences are stored
    b.ok("edit-status", "wontfix", "notify_dependents=false")
    b.ok("add-status", "duplicate", "--after", "wontfix", "--like", "wontfix", "--label", "Duplicate")
    assert meta(b)["status_flags"]["duplicate"] == {"notify_dependents": False}
    b.ok("add-status", "on_hold", "--after", "backlog", "--like", "cancelled", "--label", "On hold")
    b.ok("check")


# --------------------------------------------------------------------------- edit-status: set, clear, refuse


def test_edit_status_sets_and_clears_overrides(b: Board) -> None:
    out = b.ok("edit-status", "cancelled", "folded=false", "progress=done").stdout
    assert "folded = false" in out and "progress = done" in out
    assert meta(b)["status_flags"] == {"cancelled": {"progress": "done", "folded": False}}
    assert flags(b)["cancelled"] == dict(CANCELLED_FLAGS, folded=False, progress="done")
    out = b.ok("edit-status", "cancelled", "folded=default").stdout
    assert "folded = true (the default for its role)" in out
    assert meta(b)["status_flags"] == {"cancelled": {"progress": "done"}}
    b.ok("edit-status", "cancelled", "progress=default")
    assert "status_flags" not in meta(b)


def test_edit_status_flag_refusals(b: Board) -> None:
    r = b.fail("edit-status", "review", "terminal=maybe")
    assert "status review terminal: 'maybe' must be true or false (or default)" in r.stderr and has_fix(r.stderr)
    r = b.fail("edit-status", "review", "progress=half")
    assert "must be done, excluded or open" in r.stderr and has_fix(r.stderr)
    r = b.fail("edit-status", "review", "termnal=true")
    assert "not a status setting" in r.stderr and "edit-status review terminal=true   (did you mean this?)" in r.stderr
    assert "status_flags" not in meta(b)


def test_edit_status_flag_that_would_break_the_board_is_refused(b: Board) -> None:
    b.ok("cancel", "ACME-001", "--reason", "dropped")
    b.ok("set", "ACME-003", "done", "--handoff", "shipped", "--no-code", "test")
    r = b.fail("edit-status", "cancelled", "resolves_deps=false")
    assert "would make ACME-003 invalid" in r.stderr and has_fix(r.stderr)
    assert "status_flags" not in meta(b)


def test_check_validates_hand_edited_flags(b: Board) -> None:
    doc = b.load()
    doc["meta"]["status_flags"] = {"review": {"terminal": "yes", "fold": True}, "ghost": {"terminal": True},
                                   "done": ["terminal"]}
    b.write(doc)
    r = b.fail("check")
    assert "meta status_flags: review: terminal must be true or false" in r.stderr
    assert "meta status_flags: review: 'fold' is not a flag" in r.stderr
    assert "meta status_flags: 'ghost' is not one of meta.statuses" in r.stderr
    assert "meta status_flags: done: must be an object" in r.stderr and has_fix(r.stderr)


def test_rename_and_remove_status_carry_and_drop_flags(b: Board) -> None:
    b.ok("add-status", "parked", "--after", "backlog", "--like", "backlog")
    b.ok("edit-status", "parked", "terminal=true", "folded=true")
    b.ok("rename-status", "parked", "shelved")
    assert meta(b)["status_flags"] == {"shelved": {"terminal": True, "folded": True}}
    b.ok("remove-status", "shelved")
    assert "status_flags" not in meta(b)
    b.ok("rename-status", "cancelled", "dropped")
    m = meta(b)
    assert m["status_roles"]["dropped"] == "cancelled" and flags(b)["dropped"] == CANCELLED_FLAGS


# --------------------------------------------------------------------------- each flag on a custom state


def test_flag_resolves_deps(b: Board) -> None:
    b.ok("add-status", "handed_off", "--after", "done", "--like", "review", "--label", "Handed off")
    b.ok("set", "ACME-001", "in_progress")
    b.ok("set", "ACME-001", "handed_off", "--handoff", "the other team finishes it")
    assert "ACME-003" not in b.ok("list").stdout
    b.ok("edit-status", "handed_off", "resolves_deps=true")
    assert "ACME-003" in b.ok("list").stdout
    b.ok("set", "ACME-003", "in_progress")
    b.ok("set", "ACME-003", "done", "--handoff", "shipped", "--no-code", "test")
    b.ok("check")


def test_flag_from_any(b: Board) -> None:
    b.ok("add-status", "on_hold", "--after", "review", "--like", "backlog", "--label", "On hold")
    b.ok("set-meta", "workflow=strict")
    b.ok("edit-status", "on_hold", "from=backlog")
    b.ok("set", "ACME-003", "in_progress", "--ignore-deps", "stacked")
    r = b.fail("set", "ACME-003", "on_hold")
    assert "can't move" in r.stderr  # path rule: only from backlog
    b.ok("edit-status", "on_hold", "from_any=true")
    r = b.fail("set", "ACME-003", "on_hold")
    assert "needs a note" in r.stderr and has_fix(r.stderr)
    b.ok("set", "ACME-003", "on_hold", "--handoff", "waiting for legal")
    h = b.ticket("ACME-003")["handoff"][-1]
    assert h["from"] == "in_progress" and h["status"] == "on_hold"
    assert "cancelled_from" not in b.ticket("ACME-003")  # only cancelled-role states record it
    assert "any state" in b.ok("workflow", "--markdown").stdout


def test_flag_progress_excluded_and_done(b: Board) -> None:
    b.ok("add-status", "on_hold", "--after", "backlog", "--like", "backlog", "--label", "On hold")
    b.ok("edit-status", "on_hold", "progress=excluded")
    b.ok("set", "ACME-002", "on_hold")
    b.ok("cancel", "ACME-001", "--reason", "dropped")
    assert "0/1  done · 0 in flight · 1 on hold · 1 cancelled" in b.ok("status").stdout
    p1 = json.loads(b.ok("status", "--json").stdout)["phases"][0]
    assert p1["excluded_by"] == {"on_hold": 1, "cancelled": 1} and p1["cancelled"] == 1 and p1["total"] == 1
    b.ok("edit-status", "on_hold", "progress=done")
    assert "1/2  done · 0 in flight · 1 cancelled" in b.ok("status").stdout


def test_flag_terminal(b: Board) -> None:
    b.ok("add-status", "someday", "--after", "backlog", "--like", "backlog", "--label", "Someday")
    b.ok("set", "ACME-002", "someday")
    assert "ACME-002" in b.ok("list").stdout
    b.ok("edit-status", "someday", "terminal=true")
    assert "ACME-002" not in b.ok("list").stdout
    assert "ACME-002" not in json.dumps(json.loads(b.ok("next", "--json").stdout))
    assert "nothing to claim" in b.fail("claim", "ACME-002").stderr
    # entering a terminal state clears the claim, even for an in-progress-like state
    b.ok("add-status", "frozen", "--after", "in_progress", "--like", "in_progress")
    b.ok("edit-status", "frozen", "terminal=true")
    b.ok("set", "ACME-001", "in_progress", "--as", "me")
    assert b.ticket("ACME-001")["claimed_by"]["by"] == "me"
    b.ok("set", "ACME-001", "frozen", "--as", "me")
    assert "claimed_by" not in b.ticket("ACME-001")


def test_flag_notify_dependents(b: Board) -> None:
    b.ok("add-status", "blocked", "--after", "backlog", "--like", "backlog", "--label", "Blocked")
    b.ok("set", "ACME-001", "blocked", "--handoff", "no API key")
    assert "Blocked" not in json.dumps(b.ticket("ACME-003").get("handoff", []))
    b.ok("set", "ACME-001", "backlog")
    b.ok("edit-status", "blocked", "notify_dependents=true")
    b.ok("set", "ACME-001", "blocked", "--handoff", "no API key")
    assert b.ticket("ACME-003")["handoff"][-1]["note"] == "depended on ACME-001, Blocked: no API key"
    b.ok("edit-status", "cancelled", "notify_dependents=false")
    b.ok("set", "ACME-001", "backlog")
    n = len(b.ticket("ACME-003")["handoff"])
    b.ok("cancel", "ACME-001", "--reason", "dropped")
    assert len(b.ticket("ACME-003")["handoff"]) == n


def test_flag_folded_is_reported(b: Board) -> None:
    b.ok("add-status", "archive", "--after", "cancelled", "--like", "done")
    b.ok("edit-status", "archive", "folded=true")
    assert flags(b)["archive"]["folded"] is True


# --------------------------------------------------------------------------- workflow --markdown, flow


def test_workflow_markdown_behaves_column(b: Board) -> None:
    md = b.ok("workflow", "--markdown").stdout
    assert "| Behaves |" in md
    row = next(ln for ln in md.splitlines() if ln.startswith("| `cancelled`"))
    assert "| any state | no check |" in row and "reachable from any state" in row and "left out of progress" in row
    assert next(ln for ln in md.splitlines() if ln.startswith("| `review`")).rstrip().endswith("| normal |")
    assert "cancel ID --reason" in md


def test_flow_ignores_moves_into_from_any_states(b: Board) -> None:
    for tid in ("ACME-001", "ACME-002"):
        b.ok("set", tid, "in_progress")
        b.ok("set", tid, "review", "--handoff", "built")
        b.ok("cancel", tid, "--reason", "dropped")
    data = json.loads(b.ok("flow", "--json").stdout)
    assert {"from": "review", "to": "cancelled", "count": 2, "backward": False} in data["transitions"]
    assert "cancelled" not in data["suggested_from"]
    # notes left on dependents are not moves
    assert not any(t["to"] == "backlog" for t in data["transitions"])
