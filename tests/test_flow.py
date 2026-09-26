"""Tests for `board.py flow [--json]`: the status transitions tickets actually went through, read from
their handoff history, and the suggested rule set (docs/plans/2026-09-26-v0.2-build-plan.md, "Workflow
rules: defaults, init, upgrade recommendation")."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from conftest import Board, base_doc, full_ticket

V2_STATUSES = ["draft", "backlog", "ready", "in_progress", "review", "user_testing", "merge_ready", "done"]


def notes(*statuses: str) -> List[Dict[str, Any]]:
    return [{"date": "2026-09-20", "status": s, "note": f"to {s}"} for s in statuses]


def history_doc() -> Dict[str, Any]:
    full = ("in_progress", "review", "user_testing", "merge_ready", "done")
    d = base_doc([
        full_ticket(1, status="done", handoff=notes(*full)),
        full_ticket(2, status="done", handoff=notes(*full)),
        full_ticket(3, status="done", handoff=notes("in_progress", "review", "done")),
        # promoted from draft (first note is backlog), a note without a move, now in review
        full_ticket(4, status="review", handoff=notes("backlog", "in_progress", "in_progress", "review")),
        full_ticket(5, status="in_progress"),                       # moved without any note
        full_ticket(6, status="backlog"),                           # never moved
        full_ticket(7, status="in_progress", handoff=notes("review", "in_progress")),  # sent back
    ])
    d["meta"].update({"slate_version": "0.2.0", "schema_version": 2, "statuses": list(V2_STATUSES)})
    return d


def flow(board: Board) -> Dict[str, Any]:
    return json.loads(board.ok("flow", "--json").stdout)


def test_flow_counts_transitions_from_history(board: Board) -> None:
    board.write(history_doc())
    data = flow(board)
    got = {(t["from"], t["to"]): t["count"] for t in data["transitions"]}
    assert got == {
        ("backlog", "in_progress"): 5,
        ("in_progress", "review"): 4,
        ("review", "user_testing"): 2,
        ("user_testing", "merge_ready"): 2,
        ("merge_ready", "done"): 2,
        ("review", "done"): 1,
        ("draft", "backlog"): 1,
        ("backlog", "review"): 1,
        ("review", "in_progress"): 1,
    }
    assert data["tickets"] == 7
    counts = [t["count"] for t in data["transitions"]]
    assert counts == sorted(counts, reverse=True)
    assert data["transitions"][0] == {"from": "backlog", "to": "in_progress", "count": 5, "backward": False}
    back = next(t for t in data["transitions"] if (t["from"], t["to"]) == ("review", "in_progress"))
    assert back["backward"] is True


def test_flow_suggests_rules_from_common_previous_states(board: Board) -> None:
    board.write(history_doc())
    sug = flow(board)["suggested_from"]
    assert sug == {
        "backlog": ["draft"],
        "in_progress": ["backlog"],
        "review": ["backlog", "in_progress"],  # backlog -> review is 1 of 5 moves (20%)
        "user_testing": ["review"],
        "merge_ready": ["user_testing"],
        "done": ["review", "merge_ready"],     # review -> done is 1 of 3
    }


def test_flow_drops_rare_previous_states(board: Board) -> None:
    d = history_doc()
    for n in range(8, 20):  # eleven more tickets going in_progress -> review make backlog -> review rare
        d["tickets"].append(full_ticket(n, status="review", handoff=notes("in_progress", "review")))
    board.write(d)
    assert flow(board)["suggested_from"]["review"] == ["in_progress"]  # backlog -> review: 1 of 16 (6%)


def test_flow_text_output(board: Board) -> None:
    board.write(history_doc())
    out = board.ok("flow").stdout
    lines = out.splitlines()
    assert lines[0].startswith("Status transitions used (7 tickets")
    assert lines[1].split() == ["backlog", "→", "in_progress", "5"]
    assert any(ln.split()[:3] == ["review", "→", "in_progress"] and "(backward)" in ln for ln in lines)
    assert "Suggested rules" in out
    assert "review: from backlog, in_progress" in out and "edit-status review from=backlog,in_progress" in out


def test_flow_on_a_board_without_history(board: Board) -> None:
    board.write(base_doc([full_ticket(1), full_ticket(2)]))
    assert "No status changes recorded yet (2 tickets)" in board.ok("flow").stdout
    data = flow(board)
    assert data == {"tickets": 2, "transitions": [], "suggested_from": {}}


def test_flow_is_read_only(board: Board) -> None:
    board.write(history_doc())
    before = board.tickets.read_bytes()
    board.ok("flow")
    board.ok("flow", "--json")
    assert board.tickets.read_bytes() == before
