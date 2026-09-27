"""Tests for the per-state dependency rule (meta.status_deps): where a ticket's dependencies must be before
it may move INTO each status. Default by the target's role: in_progress / review / user_testing / done
need dependencies done; merge_ready accepts dependencies in merge_ready or done (tickets that ship in the
same PR); draft / backlog / ready have no check."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional

import pytest

from conftest import VERSION, Board, base_doc, full_ticket
from test_serve import Live

V2 = ["draft", "backlog", "ready", "in_progress", "review", "user_testing", "merge_ready", "done"]


def v2_doc(tickets: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    d = base_doc(tickets)
    d["meta"].update({"slate_version": VERSION, "schema_version": 2, "statuses": list(V2),
                      "status_labels": {"merge_ready": "Waiting for merge", "done": "Done"}})
    return d


def pair(dep_status: str, status: str = "review") -> Dict[str, Any]:
    """ACME-001 in dep_status; ACME-002 (in status) depends on it."""
    return v2_doc([full_ticket(1, status=dep_status, unlocks=["ACME-002"]),
                   full_ticket(2, status=status, depends_on=["ACME-001"])])


def has_fix(stderr: str) -> bool:
    return "fix: " in stderr or "ask the user: " in stderr


def meta(board: Board) -> Dict[str, Any]:
    return board.load()["meta"]


# --------------------------------------------------------------------------- set: the default rule


def test_merge_ready_with_a_dependency_in_merge_ready_is_allowed(board: Board) -> None:
    board.write(pair("merge_ready"))
    board.ok("set", "ACME-002", "merge_ready", "--handoff", "same PR as ACME-001")
    assert board.ticket("ACME-002")["status"] == "merge_ready"
    board.ok("check")


def test_merge_ready_with_a_dependency_in_review_is_refused(board: Board) -> None:
    board.write(pair("review"))
    r = board.fail("set", "ACME-002", "merge_ready", "--handoff", "x")
    assert ("ACME-002 depends_on: can't move to Waiting for merge until these are in Waiting for merge or Done: "
            "ACME-001 (review)") in r.stderr
    assert has_fix(r.stderr) and "edit-status merge_ready deps=" in r.stderr
    assert board.ticket("ACME-002")["status"] == "review"


def test_merge_ready_still_refuses_ignore_deps(board: Board) -> None:
    board.write(pair("review"))
    r = board.fail("set", "ACME-002", "merge_ready", "--handoff", "x", "--ignore-deps", "stacked")
    assert "--ignore-deps can't be used for merge_ready" in r.stderr and has_fix(r.stderr)


def test_done_still_needs_dependencies_done(board: Board) -> None:
    board.write(pair("merge_ready", status="merge_ready"))
    r = board.fail("set", "ACME-002", "done", "--handoff", "merged", "--no-code", "docs")
    assert "ACME-002 depends_on: can't move to Done until these are done: ACME-001 (merge_ready)" in r.stderr
    assert has_fix(r.stderr)
    r = board.fail("set", "ACME-002", "done", "--handoff", "merged", "--no-code", "docs", "--ignore-deps", "why")
    assert "--ignore-deps can't be used for done" in r.stderr and has_fix(r.stderr)


def test_in_progress_keeps_needing_done_and_ignore_deps(board: Board) -> None:
    board.write(pair("merge_ready", status="backlog"))
    r = board.fail("set", "ACME-002", "in_progress")
    assert "can't move to in_progress until these are done: ACME-001 (merge_ready)" in r.stderr
    assert "--ignore-deps" in r.stderr
    board.ok("set", "ACME-002", "in_progress", "--ignore-deps", "stacked branch")
    assert board.ticket("ACME-002")["status"] == "in_progress"


def test_bulk_set_follows_the_rule(board: Board) -> None:
    board.write(v2_doc([full_ticket(1, status="review", unlocks=["ACME-002"]),
                        full_ticket(2, status="review", depends_on=["ACME-001"])]))
    board.ok("set", "ACME-001,ACME-002", "merge_ready", "--handoff", "one PR")
    assert board.ticket("ACME-002")["status"] == "merge_ready"


# --------------------------------------------------------------------------- edit-status deps=


def test_custom_deps_by_status_name_and_role(board: Board) -> None:
    board.write(pair("user_testing"))
    board.fail("set", "ACME-002", "merge_ready", "--handoff", "x")
    board.ok("edit-status", "merge_ready", "deps=user_testing,merge_ready,done")
    assert meta(board)["status_deps"] == {"merge_ready": ["user_testing", "merge_ready", "done"]}
    board.ok("set", "ACME-002", "merge_ready", "--handoff", "x")
    # a role name matches a custom status with that role
    board.write(pair("review"))
    board.ok("add-status", "qa", "--after", "review", "--like", "review")
    board.ok("set", "ACME-001", "qa", "--handoff", "to QA")
    board.ok("edit-status", "merge_ready", "deps=review,done")
    board.ok("set", "ACME-002", "merge_ready", "--handoff", "x")


def test_deps_none_turns_the_check_off_and_empty_clears_it(board: Board) -> None:
    board.write(pair("backlog"))
    board.ok("edit-status", "review", "deps=none")
    assert meta(board)["status_deps"] == {"review": ["none"]}
    board.ok("set", "ACME-002", "review", "--handoff", "no check")
    setup = json.loads(board.ok("export", "--json", "--statuses").stdout)
    assert next(s for s in setup["statuses"] if s["name"] == "review")["deps"] == ["none"]
    board.ok("set", "ACME-002", "backlog", "--handoff", "back")
    board.ok("edit-status", "review", "deps=")
    assert "status_deps" not in meta(board)
    r = board.fail("set", "ACME-002", "review", "--handoff", "x")
    assert "until these are done" in r.stderr


def test_edit_status_deps_refuses_unknown_names_and_mixed_none(board: Board) -> None:
    board.write(pair("backlog"))
    r = board.fail("edit-status", "merge_ready", "deps=reveiw,done")
    assert "status merge_ready deps: 'reveiw' is neither a status nor a role" in r.stderr and has_fix(r.stderr)
    assert "deps=review,done" in r.stderr  # did you mean
    r = board.fail("edit-status", "merge_ready", "deps=none,done")
    assert "goes alone" in r.stderr and has_fix(r.stderr)
    assert "status_deps" not in meta(board)


def test_edit_status_deps_refuses_a_rule_that_breaks_finished_tickets(board: Board) -> None:
    board.write(pair("merge_ready", status="merge_ready"))
    r = board.fail("edit-status", "merge_ready", "deps=done")
    assert "would make ACME-002 invalid" in r.stderr and has_fix(r.stderr)
    assert "status_deps" not in meta(board)


def test_add_status_with_deps(board: Board) -> None:
    board.write(pair("review", status="review"))
    board.ok("add-status", "staging", "--after", "review", "--like", "merge_ready", "--deps", "review,merge_ready,done")
    assert meta(board)["status_deps"] == {"staging": ["review", "merge_ready", "done"]}
    board.ok("set", "ACME-002", "staging", "--handoff", "x")
    r = board.fail("add-status", "other", "--first", "--like", "backlog", "--deps", "nope")
    assert "neither a status nor a role" in r.stderr and has_fix(r.stderr)


def test_rename_status_keeps_deps_references(board: Board) -> None:
    board.write(pair("backlog"))
    board.ok("add-status", "qa", "--after", "review", "--like", "review")
    board.ok("edit-status", "merge_ready", "deps=qa,merge_ready,done")
    board.ok("edit-status", "qa", "deps=none")
    board.ok("rename-status", "qa", "testing")
    board.ok("rename-status", "merge_ready", "waiting")
    sd = meta(board)["status_deps"]
    # the renamed key follows; a role name (merge_ready) stays, it still matches `waiting` by role
    assert sd == {"waiting": ["testing", "merge_ready", "done"], "testing": ["none"]}
    board.ok("check")


def test_remove_status_drops_deps_references(board: Board) -> None:
    board.write(pair("backlog"))
    board.ok("add-status", "qa", "--after", "review", "--like", "review")
    board.ok("add-status", "staging", "--after", "qa", "--like", "review", "--deps", "qa")
    board.ok("edit-status", "merge_ready", "deps=qa,done")
    out = board.ok("remove-status", "qa").stdout
    sd = meta(board).get("status_deps", {})
    assert sd == {"merge_ready": ["done"]}
    assert "back to the default" in out and "dropped qa" in out
    board.ok("remove-status", "staging")
    board.ok("check")


# --------------------------------------------------------------------------- check


def test_check_accepts_merge_ready_with_merge_ready_deps(board: Board) -> None:
    board.write(pair("merge_ready", status="merge_ready"))
    board.ok("check")


def test_check_errors_on_merge_ready_with_open_deps(board: Board) -> None:
    board.write(pair("review", status="merge_ready"))
    r = board.fail("check")
    assert "ACME-002 status: merge_ready, but dependency ACME-001 is review" in r.stderr and has_fix(r.stderr)


def test_check_still_errors_on_done_with_open_deps(board: Board) -> None:
    board.write(pair("merge_ready", status="done"))
    r = board.fail("check")
    assert "ACME-002 status: done, but dependency ACME-001 is merge_ready" in r.stderr and has_fix(r.stderr)


def test_check_rejects_a_malformed_status_deps(board: Board) -> None:
    doc = pair("backlog")
    doc["meta"]["status_deps"] = {"review": ["nope"], "ghost": ["done"]}
    board.write(doc)
    r = board.fail("check")
    assert "meta status_deps: review: must be a list of existing statuses or roles" in r.stderr
    assert "meta status_deps: 'ghost' is not one of meta.statuses" in r.stderr and has_fix(r.stderr)


# --------------------------------------------------------------------------- workflow --markdown, export


def test_workflow_markdown_shows_the_dependencies_column(board: Board) -> None:
    board.write(pair("backlog"))
    board.ok("edit-status", "review", "deps=none")
    md = board.ok("workflow", "--markdown").stdout
    assert "| Dependencies must be in |" in md
    row = {ln.split("|")[1].strip(): ln for ln in md.splitlines() if ln.startswith("| `")}
    # the last column (Behaves) follows the dependencies column
    deps_cell = {k: v.rstrip().rstrip("|").rsplit("|", 2)[-2].strip() for k, v in row.items()}
    assert deps_cell["`merge_ready`"] == "`merge_ready`, `done`"
    assert deps_cell["`done`"] == "`done`"
    assert deps_cell["`review`"] == "no check"
    assert deps_cell["`backlog`"] == "no check"


def test_export_statuses_lists_deps(board: Board) -> None:
    board.write(pair("backlog"))
    setup = {s["name"]: s["deps"] for s in json.loads(board.ok("export", "--json", "--statuses").stdout)["statuses"]}
    assert setup == {"draft": ["none"], "backlog": ["none"], "ready": ["none"], "in_progress": ["done"],
                     "review": ["done"], "user_testing": ["done"], "merge_ready": ["merge_ready", "done"],
                     "done": ["done"]}


# --------------------------------------------------------------------------- the serve API


@pytest.fixture
def served(board: Board) -> Iterator[Live]:
    board.write(pair("merge_ready"))
    (board.dir / "index.html").write_text("<!doctype html><html><head></head><body>Slate</body></html>\n",
                                          encoding="utf-8")
    srv = Live(board)
    yield srv
    srv.stop()


def test_api_info_lists_deps_per_status(served: Live) -> None:
    sts = {s["name"]: s for s in served.info["statuses"]}
    assert sts["merge_ready"]["deps"] == ["merge_ready", "done"] and sts["backlog"]["deps"] == ["none"]


def test_api_allowed_and_set_follow_the_rule(served: Live, board: Board) -> None:
    code, out, _ = served.get("/api/allowed?id=ACME-002")
    assert code == 200 and "merge_ready" in out["allowed"]
    assert "done" not in out["allowed"] and "until these are done: ACME-001" in out["reasons"]["done"]
    code, out, _ = served.post("/api/set", {"id": "ACME-002", "status": "merge_ready", "handoff": "same PR"})
    assert code == 200, out
    assert board.ticket("ACME-002")["status"] == "merge_ready"
    board.write(pair("review"))  # the dependency is only in review now
    code, out, _ = served.get("/api/allowed?id=ACME-002")
    assert "merge_ready" not in out["allowed"]
    assert "until these are in Waiting for merge or Done: ACME-001 (review)" in out["reasons"]["merge_ready"]
    code, out, _ = served.post("/api/set", {"id": "ACME-002", "status": "merge_ready", "handoff": "x"})
    assert code == 409 and out["errors"][0]["field"] == "depends_on" and out["errors"][0]["fix"]
