"""Tests for the built-in cancelled state (0.3.0): cancel / uncancel, dependents, progress, claims,
migrate 2 -> 3 and the board page API (/api/cancel, /api/uncancel, /api/allowed, /api/set)."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional

import pytest

from conftest import VERSION, Board, base_doc, full_ticket

V2_STATUSES = ["draft", "backlog", "ready", "in_progress", "review", "user_testing", "merge_ready", "done"]
V3_STATUSES = V2_STATUSES + ["cancelled"]


def v3_doc(tickets: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    d = base_doc(tickets)
    d["meta"].update({"slate_version": VERSION, "schema_version": 3, "statuses": list(V3_STATUSES),
                      "status_labels": {"cancelled": "Cancelled"}})
    return d


def v2_doc(tickets: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    d = base_doc(tickets)
    d["meta"].update({"slate_version": VERSION, "schema_version": 2, "statuses": list(V2_STATUSES)})
    return d


def has_fix(stderr: str) -> bool:
    return "fix: " in stderr or "ask the user: " in stderr


def notes(board: Board, tid: str) -> List[str]:
    return [h["note"] for h in board.ticket(tid).get("handoff", [])]


@pytest.fixture
def b(board: Board) -> Board:
    """001 in progress (claimed by me); 002 and 003 depend on 001; 004 on its own."""
    board.write(v3_doc([
        full_ticket(1, status="in_progress", unlocks=["ACME-002", "ACME-003"],
                    claimed_by={"by": "me", "since": "2026-09-27 10:00"}),
        full_ticket(2, depends_on=["ACME-001"]),
        full_ticket(3, depends_on=["ACME-001"]),
        full_ticket(4),
    ]))
    return board


# --------------------------------------------------------------------------- cancel


def test_cancel_notes_dependents_and_they_can_finish(b: Board) -> None:
    out = b.ok("cancel", "ACME-001", "--reason", "the vendor does it now", "--as", "me").stdout
    assert "(Cancelled)" in out and "(was in_progress)" in out and "Noted on ACME-002, ACME-003" in out
    t = b.ticket("ACME-001")
    assert t["status"] == "cancelled" and t["cancelled_from"] == "in_progress" and "claimed_by" not in t
    assert t["handoff"][-1]["from"] == "in_progress" and t["handoff"][-1]["status"] == "cancelled"
    assert t["handoff"][-1]["note"] == "the vendor does it now"
    assert "CANCELLED (was in_progress)" in b.ok("show", "ACME-001").stdout
    for tid in ("ACME-002", "ACME-003"):
        last = b.ticket(tid)["handoff"][-1]
        assert last["note"] == "depended on ACME-001, Cancelled: the vendor does it now"
        assert last["status"] == "backlog" and last["about"] == "ACME-001"
    assert "ACME-004" not in json.dumps(b.ticket("ACME-004").get("handoff", []))
    # the dependents are ready now and can go all the way to done
    ready = [t["id"] for t in json.loads(b.ok("list", "--json").stdout)]
    assert ready == ["ACME-002", "ACME-003", "ACME-004"]
    b.ok("set", "ACME-002", "in_progress")
    b.ok("set", "ACME-002", "review", "--handoff", "built")
    b.ok("set", "ACME-002", "merge_ready", "--handoff", "ready to merge")  # outside git: only a warning
    b.ok("set", "ACME-002", "done", "--handoff", "merged", "--no-code", "test")
    b.ok("set", "ACME-003", "done", "--handoff", "closed", "--no-code", "test")
    assert b.ok("check").stdout.startswith("ok:")


def test_cancel_ignores_strict_workflow_and_dependencies_but_needs_a_reason(b: Board) -> None:
    b.ok("set-meta", "workflow=strict")
    r = b.fail("cancel", "ACME-002")
    assert "ACME-002 handoff: cancelling needs --reason" in r.stderr and has_fix(r.stderr)
    r = b.fail("set", "ACME-002", "cancelled")
    assert "ACME-002 handoff: moving to cancelled needs a note" in r.stderr and has_fix(r.stderr)
    # 002 waits for 001 (in progress) and strict rules don't allow backlog -> cancelled; neither applies
    b.ok("set", "ACME-002", "cancelled", "--handoff", "duplicate of ACME-004")
    b.ok("cancel", "ACME-003", "--reason", "not needed")
    assert b.ticket("ACME-003")["status"] == "cancelled"
    b.ok("check")


def test_cancel_refuses_an_already_cancelled_ticket(b: Board) -> None:
    b.ok("cancel", "ACME-004", "--reason", "dropped")
    r = b.fail("cancel", "ACME-004", "--reason", "again")
    assert "ACME-004 status: already Cancelled; nothing to cancel" in r.stderr
    assert "fix: python3 kanban/board.py uncancel ACME-004" in r.stderr


def test_cancel_claimed_by_someone_else_needs_as_or_take_over(b: Board) -> None:
    r = b.fail("cancel", "ACME-001", "--reason", "dropped", "--as", "maya")
    assert "ACME-001 claimed_by: being worked on by me" in r.stderr and has_fix(r.stderr)
    assert b.ticket("ACME-001")["status"] == "in_progress"
    b.ok("cancel", "ACME-001", "--reason", "dropped", "--as", "maya", "--take-over", "the user agreed")
    t = b.ticket("ACME-001")
    assert t["status"] == "cancelled" and "claimed_by" not in t and "took over from me" in t["handoff"][-1]["note"]


def test_cancel_several_all_or_nothing(b: Board) -> None:
    b.ok("cancel", "ACME-001,ACME-004", "--reason", "scope cut", "--as", "me")
    assert {b.ticket(x)["status"] for x in ("ACME-001", "ACME-004")} == {"cancelled"}
    r = b.fail("cancel", "ACME-002,ACME-004", "--reason", "x")
    assert "nothing was changed" in r.stderr and "ACME-004 status: already Cancelled" in r.stderr
    assert b.ticket("ACME-002")["status"] == "backlog"


def test_cancel_a_draft(board: Board) -> None:
    board.write(v3_doc([{"id": "ACME-001", "title": "Idea", "summary": "Maybe.", "phase": "P1", "status": "draft",
                         "rank": 1, "priority": "P2", "depends_on": [], "areas": ["backend"], "estimate": "1d"}]))
    board.ok("cancel", "ACME-001", "--reason", "not doing it")
    assert board.ticket("ACME-001")["cancelled_from"] == "draft"
    board.ok("check")
    board.ok("uncancel", "ACME-001", "--handoff", "back to the idea")
    assert board.ticket("ACME-001")["status"] == "draft"


def test_next_list_and_claim_skip_cancelled(b: Board) -> None:
    b.ok("cancel", "ACME-004", "--reason", "dropped")
    nxt = json.loads(b.ok("next", "--json", "--as", "me").stdout)
    assert "ACME-004" not in json.dumps(nxt)
    assert "ACME-004" not in b.ok("list").stdout
    r = b.fail("claim", "ACME-004")
    assert "it is finished, so there is nothing to claim" in r.stderr and "uncancel ACME-004" in r.stderr


def test_every_ticket_finished_message(board: Board) -> None:
    board.write(v3_doc([full_ticket(1, status="done"), full_ticket(2, status="cancelled")]))
    assert "Every ticket is finished (done or cancelled)." in board.ok("next").stdout
    assert "every ticket is finished" in board.ok("next", "--brief").stdout


def test_edit_refuses_cancel_fields(b: Board) -> None:
    r = b.fail("edit", "ACME-004", "cancelled_from=backlog")
    assert "cancelled_from" in r.stderr and "uncancel" in r.stderr
    r = b.fail("edit", "ACME-004", 'dep_exceptions:={"ACME-001": "x"}')
    assert "dep_exceptions" in r.stderr and has_fix(r.stderr)


def test_check_validates_cancel_fields(b: Board) -> None:
    doc = b.load()
    doc["tickets"][3]["cancelled_from"] = 7
    doc["tickets"][2]["dep_exceptions"] = ["ACME-001"]
    b.write(doc)
    r = b.fail("check")
    assert "ACME-004 cancelled_from: must be the name of the status" in r.stderr
    assert "ACME-003 dep_exceptions: must be" in r.stderr and has_fix(r.stderr)


# --------------------------------------------------------------------------- progress


def test_progress_leaves_cancelled_out_of_the_total(b: Board) -> None:
    b.ok("cancel", "ACME-004", "--reason", "dropped")
    b.ok("set", "ACME-001", "done", "--handoff", "merged", "--no-code", "test", "--as", "me")
    out = b.ok("status").stdout
    assert "1/3  done · 0 in flight · 1 cancelled" in out
    j = json.loads(b.ok("status", "--json").stdout)
    p1 = j["phases"][0]
    assert (p1["total"], p1["done"], p1["cancelled"], p1["excluded"]) == (3, 1, 1, 1)
    assert p1["excluded_by"] == {"cancelled": 1}
    assert j["counts"]["cancelled"] == 1


# --------------------------------------------------------------------------- uncancel


def test_uncancel_goes_back_and_notes_dependents(b: Board) -> None:
    b.ok("cancel", "ACME-001", "--reason", "dropped", "--as", "me")
    out = b.ok("uncancel", "ACME-001", "--handoff", "the vendor pulled out", "--as", "me").stdout
    assert "(in_progress)" in out and "Noted on ACME-002, ACME-003" in out
    t = b.ticket("ACME-001")
    assert t["status"] == "in_progress" and "cancelled_from" not in t and t["claimed_by"]["by"] == "me"
    assert notes(b, "ACME-002")[-1] == "ACME-001 is back (in_progress): the vendor pulled out"
    assert b.ticket("ACME-002")["handoff"][-1]["about"] == "ACME-001"
    b.ok("check")


def test_uncancel_to_and_refusals(b: Board) -> None:
    r = b.fail("uncancel", "ACME-004", "--handoff", "x")
    assert "ACME-004 status: is backlog, not cancelled" in r.stderr and has_fix(r.stderr)
    b.ok("cancel", "ACME-004", "--reason", "dropped")
    r = b.fail("uncancel", "ACME-004")
    assert "ACME-004 handoff: bringing a cancelled ticket back needs --handoff" in r.stderr and has_fix(r.stderr)
    r = b.fail("uncancel", "ACME-004", "--to", "cancelled", "--handoff", "x")
    assert "is a cancelled state" in r.stderr and has_fix(r.stderr)
    r = b.fail("uncancel", "ACME-004", "--to", "nope", "--handoff", "x")
    assert "not one of meta.statuses" in r.stderr and has_fix(r.stderr)
    b.ok("uncancel", "ACME-004", "--to", "ready", "--handoff", "approved again")
    assert b.ticket("ACME-004")["status"] == "ready"


def test_uncancel_ignores_path_rules_but_not_the_targets_dependency_rule(b: Board) -> None:
    b.ok("cancel", "ACME-002", "--reason", "dropped")  # 002 waits for 001 (in progress)
    b.ok("cancel", "ACME-004", "--reason", "dropped")
    b.ok("set-meta", "workflow=strict")
    r = b.fail("uncancel", "ACME-002", "--to", "in_progress", "--handoff", "back")
    assert "ACME-002 depends_on: can't move to in_progress until these are done: ACME-001" in r.stderr
    b.ok("uncancel", "ACME-002", "--handoff", "back")  # backlog: no dependency rule
    b.ok("uncancel", "ACME-004", "--to", "review", "--handoff", "was nearly finished")  # strict path skipped
    assert b.ticket("ACME-004")["status"] == "review"


def test_uncancel_refused_when_a_dependent_went_ahead_then_keep_dependents(b: Board) -> None:
    b.ok("cancel", "ACME-001", "--reason", "dropped", "--as", "me")
    b.ok("set", "ACME-002", "done", "--handoff", "shipped", "--no-code", "test")
    b.ok("set", "ACME-003", "in_progress")
    r = b.fail("uncancel", "ACME-001", "--handoff", "needed after all")
    assert "ACME-001 dependents: ACME-002 (done), ACME-003 (in_progress) depend on ACME-001" in r.stderr
    assert "fix: python3 kanban/board.py set ACME-002 backlog" in r.stderr
    assert "ask the user:" in r.stderr and "--keep-dependents" in r.stderr
    assert b.ticket("ACME-001")["status"] == "cancelled"
    out = b.ok("uncancel", "ACME-001", "--handoff", "needed after all", "--keep-dependents").stdout
    assert "kept ACME-002, ACME-003 where they are" in out
    for tid in ("ACME-002", "ACME-003"):
        t = b.ticket(tid)
        assert t["dep_exceptions"] == {"ACME-001": "needed after all"}
        assert t["handoff"][-1]["note"].startswith("ACME-001 is back (in_progress): needed after all (kept")
    assert b.ok("check").stdout.startswith("ok:")
    assert "Kept past ACME-001 (the user agreed): needed after all" in b.ok("show", "ACME-002").stdout
    # the exception keeps working for later moves of the dependent
    b.ok("set", "ACME-003", "review", "--handoff", "built")


def test_uncancel_without_recorded_origin_goes_to_backlog(b: Board) -> None:
    doc = b.load()
    doc["tickets"][3]["status"] = "cancelled"  # e.g. a board migrated from a hand-made cancelled column
    b.write(doc)
    out = b.ok("uncancel", "ACME-004", "--handoff", "back").stdout
    assert "no recorded state it was cancelled from; it goes to backlog" in out
    assert b.ticket("ACME-004")["status"] == "backlog"


# --------------------------------------------------------------------------- migrate 2 -> 3, v2 boards


def test_migrate_2_to_3_adds_cancelled_after_done(board: Board) -> None:
    board.write(v2_doc([full_ticket(1)]))
    out = board.ok("migrate").stdout
    assert "added status cancelled (after done)" in out and "set meta.schema_version = 3 (was 2)" in out
    m = board.load()["meta"]
    assert m["statuses"] == V3_STATUSES and m["status_labels"] == {"cancelled": "Cancelled"}
    once = board.tickets.read_bytes()
    assert "already at schema 3" in board.ok("migrate").stdout
    assert board.tickets.read_bytes() == once
    board.ok("cancel", "ACME-001", "--reason", "works now")


def test_migrate_converts_a_draft_role_cancelled_status(board: Board) -> None:
    doc = v2_doc([full_ticket(1, status="cancelled"), full_ticket(2, depends_on=["ACME-001"])])
    doc["meta"]["statuses"] = ["cancelled", "draft", "backlog", "ready", "in_progress", "review", "user_testing",
                               "merge_ready", "done"]
    doc["meta"]["status_roles"] = {"cancelled": "draft"}
    doc["meta"]["status_labels"] = {"cancelled": "Dropped"}
    board.write(doc)
    assert "promote ACME-001" in board.fail("check").stderr  # 002 depends on a draft (v2 rules)
    out = board.ok("migrate").stdout
    assert "role draft -> cancelled" in out and "moved status cancelled right after done" in out
    m = board.load()["meta"]
    assert m["statuses"] == V3_STATUSES and "status_roles" not in m and m["status_labels"] == {"cancelled": "Dropped"}
    assert "added status cancelled" not in out
    board.ok("check")
    assert board.ok("migrate").stdout.startswith("kanban/tickets.json is already at schema 3")


def test_migrate_keeps_an_existing_cancelled_role_status(board: Board) -> None:
    doc = v2_doc([full_ticket(1)])
    doc["meta"]["statuses"] = V2_STATUSES + ["wontfix"]
    doc["meta"]["status_roles"] = {"wontfix": "cancelled"}  # written by a 0.3 board.py, schema not bumped
    board.write(doc)
    board.ok("migrate")
    assert board.load()["meta"]["statuses"] == V2_STATUSES + ["wontfix"]


def test_v2_board_loads_and_cancel_suggests_migrate(board: Board) -> None:
    board.write(v2_doc([full_ticket(1), full_ticket(2)]))
    board.ok("check")
    board.ok("edit", "ACME-002", "estimate=2d")
    assert board.load()["meta"]["schema_version"] == 2  # no silent migration
    r = board.fail("cancel", "ACME-001", "--reason", "x")
    assert "no cancelled state yet" in r.stderr and "fix: python3 kanban/board.py migrate" in r.stderr
    r = board.fail("set", "ACME-001", "cancelled", "--handoff", "x")
    assert "fix: python3 kanban/board.py migrate" in r.stderr
    doc = board.load()
    doc["meta"]["schema_version"] = 3
    board.write(doc)
    r = board.fail("cancel", "ACME-001", "--reason", "x")
    assert "no status has the cancelled role" in r.stderr and "add-status cancelled --after done" in r.stderr


def test_cancel_prefers_the_status_named_cancelled(board: Board) -> None:
    doc = v3_doc([full_ticket(1)])
    doc["meta"]["statuses"] = V2_STATUSES + ["wontfix", "cancelled"]
    doc["meta"]["status_roles"] = {"wontfix": "cancelled"}
    board.write(doc)
    board.ok("cancel", "ACME-001", "--reason", "x")
    assert board.ticket("ACME-001")["status"] == "cancelled"


def test_sync_order_cancelled_beats_open_but_not_done() -> None:
    import importlib.util
    from conftest import BOARD_SRC
    spec = importlib.util.spec_from_file_location("board_under_test", BOARD_SRC)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    mod.use_roles(v3_doc())
    assert mod.further(V3_STATUSES, "in_progress", "cancelled") == "cancelled"
    assert mod.further(V3_STATUSES, "done", "cancelled") == "done"
    assert mod.further(V3_STATUSES, "cancelled", "done") == "done"


# --------------------------------------------------------------------------- board page API


@pytest.fixture
def live(b: Board) -> Iterator[Any]:
    from test_serve import Live
    (b.dir / "index.html").write_text("<!doctype html><html><head></head><body>Slate board</body></html>\n",
                                      encoding="utf-8")
    srv = Live(b)
    yield srv
    srv.stop()


def test_api_info_carries_flags(live: Any) -> None:
    info = live.get("/api/info")[1]
    st = {s["name"]: s for s in info["statuses"]}
    assert [s["name"] for s in info["statuses"]] == V3_STATUSES
    assert st["cancelled"]["role"] == "cancelled" and st["cancelled"]["label"] == "Cancelled"
    assert st["cancelled"]["flags"] == {"resolves_deps": True, "from_any": True, "progress": "excluded",
                                        "terminal": True, "notify_dependents": True, "folded": True}
    assert st["done"]["flags"] == {"resolves_deps": True, "from_any": False, "progress": "done",
                                   "terminal": True, "notify_dependents": False, "folded": False}
    assert st["cancelled"]["note"] == "required"


def test_api_cancel_and_uncancel(live: Any, b: Board) -> None:
    code, out, _ = live.post("/api/cancel", {"id": "ACME-004"})
    assert code == 409 and out["code"] == "needs_handoff"
    code, out, _ = live.post("/api/cancel", {"id": "ACME-001", "reason": "dropped", "as": "maya"})
    assert code == 409 and "being worked on by me" in out["errors"][0]["message"]
    code, out, _ = live.post("/api/cancel", {"id": "ACME-001", "reason": "dropped", "as": "me"})
    assert code == 200, out
    t = b.ticket("ACME-001")
    assert t["status"] == "cancelled" and t["handoff"][-1]["via"] == "board page" and t["handoff"][-1]["as"] == "me"
    assert b.ticket("ACME-002")["handoff"][-1]["note"] == "depended on ACME-001, Cancelled: dropped"
    b.ok("set", "ACME-002", "done", "--handoff", "shipped", "--no-code", "test")
    code, out, _ = live.post("/api/uncancel", {"id": "ACME-001", "to": "backlog", "handoff": "back"})
    assert code == 409 and "ACME-002 (done)" in out["errors"][0]["message"] and out["errors"][0]["fix"]
    code, out, _ = live.post("/api/uncancel", {"id": "ACME-001", "to": "backlog", "handoff": "back",
                                               "keep_dependents": "yes"})
    assert code == 400
    code, out, _ = live.post("/api/uncancel", {"id": "ACME-001", "to": "backlog", "handoff": "back",
                                               "keep_dependents": True})
    assert code == 200, out
    assert b.ticket("ACME-001")["status"] == "backlog"
    assert b.ticket("ACME-002")["dep_exceptions"] == {"ACME-001": "back"}
    code, out, _ = live.post("/api/uncancel", {"id": "ACME-004", "to": "backlog"})
    assert code == 409


def test_api_allowed_always_lists_from_any_and_set_needs_a_note(live: Any, b: Board) -> None:
    b.ok("set-meta", "workflow=strict")
    allowed = live.get("/api/allowed?id=ACME-002")[1]
    assert "cancelled" in allowed["allowed"] and "cancelled" not in allowed["reasons"]
    assert "in_progress" not in allowed["allowed"]  # 001 isn't done
    allowed = live.get("/api/allowed?id=ACME-001&as=maya")[1]  # claimed by someone else
    assert "cancelled" in allowed["allowed"]
    code, out, _ = live.post("/api/set", {"id": "ACME-002", "status": "cancelled"})
    assert code == 409 and out["code"] == "needs_handoff"
    code, out, _ = live.post("/api/set", {"id": "ACME-002", "status": "cancelled", "handoff": "duplicate"})
    assert code == 200, out
    t = b.ticket("ACME-002")
    assert t["status"] == "cancelled" and t["cancelled_from"] == "backlog" and t["handoff"][-1]["from"] == "backlog"
