"""Tests for the v0.2 board.py core (docs/plans/2026-09-26-v0.2-build-plan.md, workstream A):
items #1-#14, #26, #27, #5 and schema 2 + migrate 1->2."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from conftest import FIXTURES, USER_TEST, Board, base_doc, full_ticket

V2_STATUSES = ["draft", "backlog", "ready", "in_progress", "review", "user_testing", "merge_ready", "done"]
PR = "https://github.com/acme/app/pull/7"


def v2_doc(tickets: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    d = base_doc(tickets)
    d["meta"].update({"slate_version": "0.2.0", "schema_version": 2, "statuses": list(V2_STATUSES)})
    return d


def has_fix(stderr: str) -> bool:
    return "fix: " in stderr or "ask the user: " in stderr


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                        "-c", "commit.gpgsign=false", *args],
                       cwd=str(cwd), capture_output=True, text=True, check=True)
    return r.stdout.strip()


def git_repo(board: Board, remote: bool = False) -> str:
    git(board.root, "init", "-q", "-b", "feat/x")
    (board.root / "app.txt").write_text("hello\n")
    git(board.root, "add", "app.txt")
    git(board.root, "commit", "-q", "-m", "Add the page")
    if remote:
        git(board.root, "remote", "add", "origin", "https://example.com/acme/app.git")
    return git(board.root, "rev-parse", "HEAD")


def ranks(board: Board) -> Dict[str, int]:
    return {t["id"]: t["rank"] for t in board.load()["tickets"]}


@pytest.fixture
def v2(board: Board) -> Board:
    """v2 board: 001, 002 (needs 001), 003."""
    board.write(v2_doc([full_ticket(1, unlocks=["ACME-002"]), full_ticket(2, depends_on=["ACME-001"]),
                        full_ticket(3)]))
    return board


STRICT = ["--story", "s", "--description", "d", "--acceptance", "a", "--test", "When a, then b", "--areas", "backend"]


def new_args(title: str = "A new ticket", *extra: str) -> List[str]:
    return ["new", "--title", title, "--summary", "s", "--phase", "P1", *STRICT, *extra]


# --------------------------------------------------------------------------- schema 2 + migrate


def test_init_is_schema_2(board: Board) -> None:
    board.ok("init", "--project", "Acme", "--prefix", "ACME")
    m = board.load()["meta"]
    assert m["schema_version"] == 2 and m["slate_version"] == "0.2.0" and m["statuses"] == V2_STATUSES


def test_migrate_1_to_2_inserts_merge_ready_and_is_idempotent(seeded: Board) -> None:
    out = seeded.ok("migrate").stdout
    assert "added status merge_ready (before done)" in out
    assert "set meta.schema_version = 2 (was 1)" in out
    m = seeded.load()["meta"]
    assert m["schema_version"] == 2 and m["statuses"] == V2_STATUSES
    once = seeded.tickets.read_bytes()
    assert "already at schema 2" in seeded.ok("migrate").stdout
    assert seeded.tickets.read_bytes() == once
    seeded.ok("check")


def test_migrate_keeps_tickets_and_custom_statuses(board: Board) -> None:
    doc = base_doc([full_ticket(1)])
    doc["meta"]["statuses"] = ["draft", "backlog", "doing", "user_testing", "shipped"]  # no "done"
    doc["tickets"][0]["status"] = "doing"
    board.write(doc)
    board.ok("migrate")
    after = board.load()
    assert after["meta"]["statuses"] == ["draft", "backlog", "doing", "user_testing", "shipped", "merge_ready"]
    assert after["tickets"] == doc["tickets"]


def test_migrate_does_not_duplicate_existing_merge_ready(board: Board) -> None:
    doc = base_doc([full_ticket(1)])
    doc["meta"]["statuses"] = V2_STATUSES
    board.write(doc)
    out = board.ok("migrate").stdout
    assert "added status merge_ready" not in out
    assert board.load()["meta"]["statuses"] == V2_STATUSES


def test_legacy_forge_fixture_migrates_to_2(board: Board) -> None:
    shutil.copy(FIXTURES / "legacy-forge-mini.json", board.tickets)
    board.ok("migrate")
    m = board.load()["meta"]
    assert m["schema_version"] == 2 and m["statuses"] == V2_STATUSES
    board.ok("check")


def test_v1_board_still_passes_check_and_stays_v1_on_write(seeded: Board) -> None:
    assert seeded.ok("check").stdout.startswith("ok:")
    seeded.ok("edit", "ACME-003", "estimate=2d")
    m = seeded.load()["meta"]
    assert m["schema_version"] == 1 and "merge_ready" not in m["statuses"]  # no silent migration


def test_v1_board_merge_ready_suggests_migrate(seeded: Board) -> None:
    r = seeded.fail("set", "ACME-001", "merge_ready", "--handoff", "x")
    assert "'merge_ready' is not one of meta.statuses" in r.stderr
    assert "fix: python3 kanban/board.py migrate" in r.stderr


def test_writes_refuse_schema_3(v2: Board) -> None:
    doc = v2.load()
    doc["meta"]["schema_version"] = 3
    v2.write(doc)
    r = v2.fail("check-item", "ACME-001", "acceptance", "0")
    assert "board is newer than this board.py" in r.stderr


# --------------------------------------------------------------------------- #6 repeated flags


def test_new_repeated_flags_and_comma_lists(v2: Board) -> None:
    v2.ok("new", "--title", "Many flags", "--summary", "s", "--phase", "P1", "--story", "s", "--description", "d",
          "--acceptance", "Works, even with commas", "--acceptance", "Second, also with commas",
          "--test", "When a, then b", "--test", "When c, then d, e",
          "--labels", "a,b", "--labels", "c", "--labels", "a",
          "--areas", "backend", "--areas", "infra",
          "--depends", "ACME-001", "--depends", "ACME-003,ACME-002")
    t = v2.ticket("ACME-004")
    assert t["labels"] == ["a", "b", "c"]
    assert t["areas"] == ["backend", "infra"]
    assert t["depends_on"] == ["ACME-001", "ACME-003", "ACME-002"]
    # acceptance and test sentences are never split on commas
    assert t["acceptance"] == ["Works, even with commas", "Second, also with commas"]
    assert t["test_scenarios"] == ["When a, then b", "When c, then d, e"]
    assert v2.ticket("ACME-003")["unlocks"] == ["ACME-004"]


def test_new_repeated_user_test_json(v2: Board) -> None:
    v2.ok(*new_args("UI thing", "--areas", "frontend", "--user-test-json", json.dumps(USER_TEST),
                    "--user-test-json", json.dumps(dict(USER_TEST, title="Second", required=False))))
    assert [u["title"] for u in v2.ticket("ACME-004")["user_tests"]] == [USER_TEST["title"], "Second"]


# --------------------------------------------------------------------------- #7 field+=


def test_edit_append_adds_blank_line(v2: Board) -> None:
    v2.ok("edit", "ACME-001", "description+=Found during review: X.")
    assert v2.ticket("ACME-001")["description"] == "All the detail.\n\nFound during review: X."
    v2.ok("edit", "ACME-001", "technical+=Risk: Y.", "technical+=Risk: Z.")
    assert v2.ticket("ACME-001")["technical"] == "Files: x.py\n\nRisk: Y.\n\nRisk: Z."


def test_edit_append_to_missing_field_sets_it(v2: Board) -> None:
    v2.ok("edit", "ACME-001", "visual+=```\na -> b\n```")
    assert v2.ticket("ACME-001")["visual"] == "```\na -> b\n```"


@pytest.mark.parametrize("field", ["summary", "story", "description", "technical", "visual"])
def test_edit_append_allowed_fields(v2: Board, field: str) -> None:
    v2.ok("edit", "ACME-003", f"{field}+=more")
    assert v2.ticket("ACME-003")[field].endswith("more")


@pytest.mark.parametrize("field", ["title", "labels", "acceptance", "estimate"])
def test_edit_append_refused_elsewhere(v2: Board, field: str) -> None:
    before = v2.tickets.read_bytes()
    r = v2.fail("edit", "ACME-001", f"{field}+=x")
    assert f"ACME-001 {field}: += only appends to text fields" in r.stderr and has_fix(r.stderr)
    assert v2.tickets.read_bytes() == before


# --------------------------------------------------------------------------- #8 bugs


def test_new_bug_label_only(v2: Board) -> None:
    v2.ok(*new_args("Crash on save", "--bug", "--labels", "ui-polish"))
    t = v2.ticket("ACME-004")
    assert t["labels"] == ["ui-polish", "bug"] and t["rank"] == 4


def test_new_fixes_ranks_before_earliest_and_adds_deps(v2: Board) -> None:
    out = v2.ok(*new_args("Crash on save", "--bug", "--fixes", "ACME-003", "--fixes", "ACME-002")).stdout
    t = v2.ticket("ACME-004")
    assert t["labels"] == ["bug", "fixes-ACME-003", "fixes-ACME-002"]
    assert ranks(v2) == {"ACME-001": 1, "ACME-004": 2, "ACME-002": 3, "ACME-003": 4}
    assert v2.ticket("ACME-002")["depends_on"] == ["ACME-001", "ACME-004"]
    assert v2.ticket("ACME-003")["depends_on"] == ["ACME-004"]
    assert t["unlocks"] == ["ACME-002", "ACME-003"]
    assert "ACME-002 now waits for ACME-004" in out
    v2.ok("check")


def test_new_fixes_implies_bug_and_comma_list(v2: Board) -> None:
    v2.ok(*new_args("Crash", "--fixes", "ACME-002,ACME-003"))
    assert v2.ticket("ACME-004")["labels"] == ["bug", "fixes-ACME-002", "fixes-ACME-003"]


@pytest.mark.parametrize("status", ["done", "merge_ready"])
def test_new_fixes_finished_ticket_refused_then_reopen(board: Board, status: str) -> None:
    board.write(v2_doc([full_ticket(1, status=status), full_ticket(2)]))
    before = board.tickets.read_bytes()
    r = board.fail(*new_args("Regression", "--fixes", "ACME-001"))
    assert f"ACME-001 status: is {status}, so a bug that fixes it means reopening it" in r.stderr
    assert "ask the user:" in r.stderr and "--fixes ACME-001 --reopen" in r.stderr
    assert board.tickets.read_bytes() == before
    out = board.ok(*new_args("Regression", "--fixes", "ACME-001", "--reopen")).stdout
    assert f"ACME-001 reopened: {status} -> in_progress" in out
    t = board.ticket("ACME-001")
    assert t["status"] == "in_progress" and t["depends_on"] == ["ACME-003"]
    assert t["handoff"][-1]["status"] == "in_progress"
    assert t["handoff"][-1]["note"].startswith(f"Reopened (was {status}): bug ACME-003")
    assert ranks(board) == {"ACME-003": 1, "ACME-001": 2, "ACME-002": 3}
    board.ok("check")


def test_new_reopen_leaves_open_fixed_tickets_alone(board: Board) -> None:
    board.write(v2_doc([full_ticket(1, status="review")]))
    board.ok(*new_args("Found in review", "--fixes", "ACME-001", "--reopen"))
    assert board.ticket("ACME-001")["status"] == "review"


def test_new_fixes_refusals(v2: Board) -> None:
    before = v2.tickets.read_bytes()
    r = v2.fail(*new_args("x", "--fixes", "ACME-099"))
    assert "ACME-099 id: no such ticket (named in --fixes)" in r.stderr and has_fix(r.stderr)
    r = v2.fail(*new_args("x", "--fixes", "ACME-001", "--after", "ACME-002"), code=2)
    assert "--after" in r.stderr and has_fix(r.stderr)
    r = v2.fail(*new_args("x", "--reopen"), code=2)
    assert "--reopen only goes with --fixes" in r.stderr and has_fix(r.stderr)
    assert v2.tickets.read_bytes() == before


def test_new_fixes_dry_run_writes_nothing(v2: Board) -> None:
    before = v2.tickets.read_bytes()
    v2.ok(*new_args("x", "--fixes", "ACME-002", "--dry-run"))
    assert v2.tickets.read_bytes() == before
    prev = json.loads(v2.preview.read_text())
    assert prev["tickets"][0]["rank"] == 2


# --------------------------------------------------------------------------- #9 --rerank


def test_rank_error_prints_rerank_fix(v2: Board) -> None:
    r = v2.fail("edit", "ACME-001", 'depends_on:=["ACME-003"]')
    assert "ACME-001 rank: 1 must come after dependency ACME-003" in r.stderr
    assert "fix: python3 kanban/board.py edit ACME-001 --rerank" in r.stderr
    assert "fix: python3 kanban/board.py rerank ACME-001 --after ACME-003" in r.stderr


def test_edit_rerank_moves_after_latest_dependency_and_cascades(v2: Board) -> None:
    out = v2.ok("edit", "ACME-001", 'depends_on:=["ACME-003"]', "--rerank").stdout
    # 001 moves after 003; 002 (which needs 001) moves after 001 too
    assert ranks(v2) == {"ACME-003": 1, "ACME-001": 2, "ACME-002": 3}
    assert "moved ACME-001 to rank 2" in out and "moved ACME-002 to rank 3" in out
    assert v2.ticket("ACME-003")["unlocks"] == ["ACME-001"]
    v2.ok("check")


def test_edit_rerank_repairs_rank_error_already_on_disk(board: Board) -> None:
    # e.g. after a hand edit or a git merge: 001 needs 003 but ranks before it
    board.write(v2_doc([full_ticket(1, depends_on=["ACME-003"]), full_ticket(2), full_ticket(3, unlocks=["ACME-001"])]))
    r = board.fail("check")
    assert "fix: python3 kanban/board.py edit ACME-001 --rerank" in r.stderr
    assert "has errors" in board.fail("edit", "ACME-002", "estimate=2d").stderr  # other writes still refuse
    board.ok("edit", "ACME-001", "--rerank")
    assert ranks(board) == {"ACME-002": 1, "ACME-003": 2, "ACME-001": 3}
    board.ok("check")


def test_edit_rerank_when_already_in_order(v2: Board) -> None:
    before = v2.tickets.read_bytes()
    assert "nothing to change" in v2.ok("edit", "ACME-002", "--rerank").stdout
    assert v2.tickets.read_bytes() == before
    v2.ok("edit", "ACME-003", 'depends_on:=["ACME-001"]', "--rerank")
    assert ranks(v2) == {"ACME-001": 1, "ACME-002": 2, "ACME-003": 3}


# --------------------------------------------------------------------------- #10 --ignore-deps


@pytest.fixture
def stacked(board: Board) -> Board:
    """002 (UI, has user tests) needs 001 which is still in review."""
    board.write(v2_doc([full_ticket(1, status="review"),
                        full_ticket(2, depends_on=["ACME-001"], areas=["frontend"], user_tests=[USER_TEST])]))
    return board


@pytest.mark.parametrize("status", ["in_progress", "review", "user_testing"])
def test_ignore_deps_allowed(stacked: Board, status: str) -> None:
    stacked.ok("set", "ACME-002", status, "--handoff", "built on 001's branch", "--ignore-deps", "stacked on 001")
    t = stacked.ticket("ACME-002")
    assert t["status"] == status
    assert t["handoff"][-1]["note"] == "built on 001's branch (deps open: ACME-001 — stacked on 001)"


def test_ignore_deps_without_handoff_records_note(stacked: Board) -> None:
    stacked.ok("set", "ACME-002", "in_progress", "--ignore-deps", "stacked PR")
    assert stacked.ticket("ACME-002")["handoff"][-1] == {
        "date": stacked.ticket("ACME-002")["handoff"][-1]["date"], "status": "in_progress",
        "note": "(deps open: ACME-001 — stacked PR)"}


def test_blocked_refusal_offers_ignore_deps(stacked: Board) -> None:
    r = stacked.fail("set", "ACME-002", "in_progress")
    assert "--ignore-deps" in r.stderr


@pytest.mark.parametrize("status", ["merge_ready", "done"])
def test_ignore_deps_forbidden_for_finished(stacked: Board, status: str) -> None:
    before = stacked.tickets.read_bytes()
    r = stacked.fail("set", "ACME-002", status, "--handoff", "x", "--ignore-deps", "trust me")
    assert f"ACME-002 depends_on: --ignore-deps can't be used for {status}" in r.stderr and has_fix(r.stderr)
    assert stacked.tickets.read_bytes() == before


def test_ignore_deps_other_refusals(stacked: Board) -> None:
    r = stacked.fail("set", "ACME-002", "backlog", "--ignore-deps", "x")
    assert "--ignore-deps only goes with in_progress, review, user_testing" in r.stderr and has_fix(r.stderr)
    r = stacked.fail("set", "ACME-002", "in_progress", "--ignore-deps", "  ")
    assert "--ignore-deps needs a reason" in r.stderr and has_fix(r.stderr)


# --------------------------------------------------------------------------- #11 bulk


def test_bulk_set_all_or_nothing(v2: Board) -> None:
    before = v2.tickets.read_bytes()
    r = v2.fail("set", "ACME-003,ACME-002,ACME-099", "in_progress")
    assert "nothing was changed: 2 of 3 tickets can't move to in_progress" in r.stderr
    assert "ACME-002 depends_on" in r.stderr and "ACME-099: no such ticket" in r.stderr
    assert has_fix(r.stderr)
    assert v2.tickets.read_bytes() == before


def test_bulk_set_in_order(v2: Board) -> None:
    out = v2.ok("set", "ACME-001,ACME-003", "in_progress").stdout
    assert "ACME-001" in out and "ACME-003" in out
    assert v2.ticket("ACME-001")["status"] == v2.ticket("ACME-003")["status"] == "in_progress"
    # 001 becomes done before 002 is checked, so 002's dependency is satisfied
    r = v2.ok("set", "ACME-001,ACME-002", "done", "--handoff", "shipped together")
    assert r.stdout.count("warning: git isn't available") == 1
    assert v2.ticket("ACME-002")["status"] == "done"
    assert v2.ticket("ACME-002")["handoff"][-1]["note"] == "shipped together"


def test_bulk_link_pr(v2: Board) -> None:
    v2.ok("link", "ACME-001,ACME-002", "--pr", PR, "--pr-state", "open")
    for tid in ("ACME-001", "ACME-002"):
        assert v2.ticket(tid)["pr"] == {"url": PR, "number": 7, "state": "open"}
    v2.ok("link", "ACME-001,ACME-002", "--pr-state", "merged")
    assert v2.ticket("ACME-002")["pr"]["state"] == "merged"


def test_bulk_link_all_or_nothing(v2: Board) -> None:
    before = v2.tickets.read_bytes()
    r = v2.fail("link", "ACME-001,ACME-099", "--pr", PR)
    assert "nothing was changed: 1 of 2 tickets can't be linked" in r.stderr and has_fix(r.stderr)
    v2.ok("link", "ACME-001", "--pr", PR)
    before = v2.tickets.read_bytes()
    r = v2.fail("link", "ACME-001,ACME-003", "--pr-state", "merged")  # 003 has no PR yet
    assert "ACME-003 pr: the ticket has no pull request yet" in r.stderr
    assert v2.tickets.read_bytes() == before


# --------------------------------------------------------------------------- #12 export, #13 filters


@pytest.fixture
def filtered(board: Board) -> Board:
    board.write(v2_doc([
        full_ticket(1, labels=["api"], status="done"),
        full_ticket(2, phase="P2", labels=["bug"], areas=["infra"]),
        full_ticket(3, phase="P2", labels=["api", "bug"]),
        {"id": "ACME-004", "title": "Idea", "summary": "s", "phase": "P1", "rank": 4, "status": "draft"},
    ]))
    return board


def export(board: Board, *args: str) -> List[str]:
    return [t["id"] for t in json.loads(board.ok("export", "--json", *args).stdout)]


def test_export_full_tickets_and_filters(filtered: Board) -> None:
    j = json.loads(filtered.ok("export", "--json").stdout)
    assert [t["id"] for t in j] == ["ACME-001", "ACME-002", "ACME-003"]  # drafts left out
    assert j[0]["story"] == "Priya uses the thing." and "handoff" in j[0]  # full tickets
    assert export(filtered, "--drafts") == ["ACME-001", "ACME-002", "ACME-003", "ACME-004"]
    assert export(filtered, "--status", "draft") == ["ACME-004"]
    assert export(filtered, "--phase", "P2") == ["ACME-002", "ACME-003"]
    assert export(filtered, "--label", "api") == ["ACME-001", "ACME-003"]
    assert export(filtered, "--label", "api", "--phase", "P2") == ["ACME-003"]  # AND across flags
    assert export(filtered, "--label", "api,bug") == ["ACME-001", "ACME-002", "ACME-003"]  # OR within
    assert export(filtered, "--area", "infra") == ["ACME-002"]
    assert export(filtered, "--status", "done", "--status", "backlog") == ["ACME-001", "ACME-002", "ACME-003"]
    assert export(filtered, "--label", "nope") == []
    assert export(filtered) == export(filtered, "--json")  # --json is the only format


def test_export_unknown_filters_refused(filtered: Board) -> None:
    r = filtered.fail("export", "--json", "--status", "doing")
    assert "status doing: not one of meta.statuses" in r.stderr and has_fix(r.stderr)
    r = filtered.fail("export", "--json", "--phase", "P9")
    assert "phase P9 id: no such phase" in r.stderr and has_fix(r.stderr)


def test_list_filters(filtered: Board) -> None:
    ids = [t["id"] for t in json.loads(filtered.ok("list", "--json", "--phase", "P2", "--label", "bug").stdout)]
    assert ids == ["ACME-002", "ACME-003"]
    assert [t["id"] for t in json.loads(filtered.ok("list", "--json", "--area", "infra").stdout)] == ["ACME-002"]
    assert "No ready tickets." in filtered.ok("list", "--phase", "P1").stdout
    r = filtered.fail("list", "--status", "nope")
    assert has_fix(r.stderr)


def test_status_filters(filtered: Board) -> None:
    j = json.loads(filtered.ok("status", "--json", "--label", "bug").stdout)
    assert j["total"] == 2 and j["counts"]["backlog"] == 2 and j["counts"]["done"] == 0
    j = json.loads(filtered.ok("status", "--json", "--phase", "P2").stdout)
    assert [p["id"] for p in j["phases"]] == ["P2"] and j["total"] == 2
    out = filtered.ok("status", "--phase", "P1").stdout
    assert "P1 Link arrives" in out and "P2 Password" not in out
    assert has_fix(filtered.fail("status", "--phase", "PX").stderr)


# --------------------------------------------------------------------------- #14 check --quiet-optional


def test_check_quiet_optional(board: Board) -> None:
    t1 = full_ticket(1)
    del t1["technical"]
    t2 = full_ticket(2, title="x" * 90)
    del t2["technical"]
    board.write(v2_doc([t1, t2]))
    out = board.ok("check").stdout
    assert out.count("technical: missing") == 2
    out = board.ok("check", "--quiet-optional").stdout
    assert "technical: missing" not in out and "warning: ACME-002 title" in out  # other warnings still shown
    assert "2 optional warnings hidden" in out
    j = json.loads(board.ok("check", "--json", "--quiet-optional").stdout)
    assert j["optional_hidden"] == 2 and [w["field"] for w in j["warnings"]] == ["title"]
    assert json.loads(board.ok("check", "--json").stdout)["optional_hidden"] == 0


def test_check_quiet_optional_from_meta(board: Board) -> None:
    t1 = full_ticket(1)
    del t1["technical"]
    board.write(v2_doc([t1]))
    board.ok("set-meta", "check_quiet_optional:=true")
    assert board.load()["meta"]["check_quiet_optional"] is True
    out = board.ok("check").stdout
    assert "technical: missing" not in out and "1 optional warning hidden" in out
    r = board.fail("set-meta", "check_quiet_optional=true")
    assert "must be true or false" in r.stderr and has_fix(r.stderr)
    doc = board.load()
    doc["meta"]["check_quiet_optional"] = "yes"
    board.write(doc)
    r = board.fail("check")
    assert "meta check_quiet_optional: must be true or false" in r.stderr and has_fix(r.stderr)


# --------------------------------------------------------------------------- #26 item checks


def test_check_item_and_show(v2: Board) -> None:
    v2.ok("edit", "ACME-001", 'acceptance:=["First thing", "Second thing"]')
    out = v2.ok("check-item", "ACME-001", "test", "0", "--evidence", "pytest tests/test_x.py passed").stdout
    assert "Ticked ACME-001 test 0" in out
    v2.ok("check-item", "ACME-001", "acceptance", "1")
    t = v2.ticket("ACME-001")
    assert list(t["item_checks"]) == ["acceptance:1", "test:0"]  # stable order
    assert t["item_checks"]["test:0"]["evidence"] == "pytest tests/test_x.py passed"
    assert t["item_checks"]["acceptance:1"]["evidence"] == ""
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", t["item_checks"]["acceptance:1"]["date"])
    keys = list(t)
    assert keys.index("item_checks") > keys.index("handoff")
    show = v2.ok("show", "ACME-001").stdout
    assert "  [ ] First thing\n  [x] Second thing\n      checked " in show
    assert "  [x] When X happens, then Y\n      checked " in show and ": pytest tests/test_x.py passed" in show
    v2.ok("check")


def test_check_item_again_updates_evidence(v2: Board) -> None:
    v2.ok("check-item", "ACME-001", "acceptance", "0", "--evidence", "old")
    v2.ok("check-item", "ACME-001", "acceptance", "0", "--evidence", "new")
    assert v2.ticket("ACME-001")["item_checks"] == {"acceptance:0": {"date": v2.ticket("ACME-001")["item_checks"]
                                                                     ["acceptance:0"]["date"], "evidence": "new"}}


def test_uncheck_item(v2: Board) -> None:
    v2.ok("check-item", "ACME-001", "acceptance", "0")
    v2.ok("uncheck-item", "ACME-001", "acceptance", "0")
    assert "item_checks" not in v2.ticket("ACME-001")
    before = v2.tickets.read_bytes()
    assert "was not ticked; nothing changed" in v2.ok("uncheck-item", "ACME-001", "acceptance", "0").stdout
    assert v2.tickets.read_bytes() == before


def test_check_item_refusals(v2: Board) -> None:
    before = v2.tickets.read_bytes()
    r = v2.fail("check-item", "ACME-001", "acceptance", "3")
    assert "ACME-001 acceptance: no item at index 3; it has 1 (index 0 to 0)" in r.stderr and has_fix(r.stderr)
    r = v2.fail("check-item", "ACME-001", "test", "-1")
    assert "ACME-001 test_scenarios: no item at index -1" in r.stderr and has_fix(r.stderr)
    r = v2.fail("uncheck-item", "ACME-001", "test", "5")
    assert has_fix(r.stderr)
    assert has_fix(v2.fail("check-item", "ACME-099", "test", "0").stderr)
    v2.fail("check-item", "ACME-001", "story", "0", code=2)
    assert v2.tickets.read_bytes() == before


def test_done_ticket_shows_every_item_ticked(board: Board) -> None:
    board.write(v2_doc([full_ticket(1, status="done", acceptance=["a", "b"])]))
    show = board.ok("show", "ACME-001").stdout
    assert "  [x] a\n  [x] b" in show and "[ ]" not in show


def test_edit_shortening_list_drops_stale_ticks(v2: Board) -> None:
    v2.ok("edit", "ACME-001", 'acceptance:=["a", "b", "c"]')
    v2.ok("check-item", "ACME-001", "acceptance", "0")
    v2.ok("check-item", "ACME-001", "acceptance", "2")
    out = v2.ok("edit", "ACME-001", 'acceptance:=["a", "b"]').stdout
    assert "dropped ticks for items that no longer exist: acceptance:2" in out
    assert list(v2.ticket("ACME-001")["item_checks"]) == ["acceptance:0"]


def test_edit_item_checks_refused(v2: Board) -> None:
    r = v2.fail("edit", "ACME-001", "item_checks:={}")
    assert "ACME-001 item_checks: can't be changed with edit" in r.stderr and "check-item" in r.stderr


@pytest.mark.parametrize("value,fragment", [
    ({"done:0": {"date": "2026-09-26", "evidence": ""}}, "item_checks[done:0]: key must be"),
    ({"acceptance:4": {"date": "2026-09-26", "evidence": ""}}, "item_checks[acceptance:4]: no acceptance item"),
    ({"test:0": {"date": "yesterday"}}, "item_checks[test:0]: must be"),
    ([], "item_checks: must be an object"),
])
def test_item_checks_validation(board: Board, value: Any, fragment: str) -> None:
    board.write(v2_doc([full_ticket(1, item_checks=value)]))
    r = board.fail("check")
    assert f"ACME-001 {fragment}" in r.stderr and has_fix(r.stderr)


def test_item_checks_forbidden_in_batch(v2: Board) -> None:
    batch = {"tickets": [{"key": "a", "title": "A", "summary": "s", "phase": "P1", "item_checks": {}}]}
    r = v2.fail("add", "--file", v2.batch(batch), "--as-draft")
    assert "'a' item_checks: set by board.py" in r.stderr


# --------------------------------------------------------------------------- #27 merge_ready


@pytest.fixture
def testing(board: Board) -> Board:
    """A UI ticket in user_testing on a v2 board inside a git repo with a remote."""
    board.write(v2_doc([full_ticket(1, areas=["frontend"], user_tests=[USER_TEST], status="user_testing")]))
    git_repo(board, remote=True)
    return board


def test_merge_ready_gates_in_order(testing: Board) -> None:
    r = testing.fail("set", "ACME-001", "merge_ready")
    assert "ACME-001 handoff: moving to merge_ready needs a note" in r.stderr
    r = testing.fail("set", "ACME-001", "merge_ready", "--handoff", "ready")
    assert "ACME-001 user_checks: can't move to merge_ready until these required user tests pass" in r.stderr
    assert "usertest ACME-001 0 pass" in r.stderr
    testing.ok("usertest", "ACME-001", "0", "pass")
    r = testing.fail("set", "ACME-001", "merge_ready", "--handoff", "ready")
    assert "ACME-001 commits: has no commits linked, so it can't move to merge_ready" in r.stderr
    assert "fix: python3 kanban/board.py link ACME-001 --commit HEAD" in r.stderr
    testing.ok("link", "ACME-001", "--commit", "HEAD")
    r = testing.fail("set", "ACME-001", "merge_ready", "--handoff", "ready")
    assert "ACME-001 pr: no pull request linked" in r.stderr
    assert "link ACME-001 --pr URL --pr-state open" in r.stderr and "--no-pr" in r.stderr
    testing.ok("link", "ACME-001", "--pr", PR, "--pr-state", "open")
    testing.ok("set", "ACME-001", "merge_ready", "--handoff", "PR open, tests pass")
    assert testing.ticket("ACME-001")["status"] == "merge_ready"
    testing.ok("check")


def test_usertest_fail_on_merge_ready_moves_back(board: Board) -> None:
    board.write(v2_doc([full_ticket(1, areas=["frontend"], user_tests=[USER_TEST], status="merge_ready",
                                    user_checks={"0": {"result": "pass", "date": "2026-09-26", "note": ""}})]))
    board.ok("usertest", "ACME-001", "0", "fail", "--note", "broke after rebase")
    t = board.ticket("ACME-001")
    assert t["status"] == "in_progress"
    assert t["handoff"][-1]["note"] == "User test failed: Reset with a known email: broke after rebase"


def test_merge_ready_no_remote_needs_no_pr(board: Board) -> None:
    board.write(v2_doc([full_ticket(1, status="review")]))
    git_repo(board)
    board.ok("link", "ACME-001", "--commit", "HEAD")
    board.ok("set", "ACME-001", "merge_ready", "--handoff", "local only")
    assert board.ticket("ACME-001")["status"] == "merge_ready"


def test_merge_ready_no_pr_then_done(board: Board) -> None:
    board.write(v2_doc([full_ticket(1, status="review")]))
    git_repo(board, remote=True)
    board.ok("link", "ACME-001", "--commit", "HEAD")
    board.ok("set", "ACME-001", "merge_ready", "--handoff", "pushed", "--no-pr", "pushed straight to main")
    t = board.ticket("ACME-001")
    assert t["done_without"] == {"pr": "pushed straight to main"}
    assert t["handoff"][-1]["note"] == "pushed (no PR: pushed straight to main)"
    board.ok("set", "ACME-001", "done", "--handoff", "merged")  # the recorded --no-pr carries over
    assert board.ticket("ACME-001")["status"] == "done"


def test_merge_ready_refuses_no_code(v2: Board) -> None:
    r = v2.fail("set", "ACME-001", "merge_ready", "--handoff", "x", "--no-code", "docs")
    assert "--no-code only goes with done" in r.stderr and "set ACME-001 done" in r.stderr


def test_merge_ready_needs_deps_done(v2: Board) -> None:
    r = v2.fail("set", "ACME-002", "merge_ready", "--handoff", "x")
    assert "ACME-002 depends_on: can't move to merge_ready" in r.stderr and has_fix(r.stderr)


def test_check_flags_merge_ready_with_open_dependency(board: Board) -> None:
    board.write(v2_doc([full_ticket(1), full_ticket(2, depends_on=["ACME-001"], status="merge_ready")]))
    r = board.fail("check")
    assert "ACME-002 status: merge_ready, but dependency ACME-001 is backlog" in r.stderr and has_fix(r.stderr)


def test_done_refuses_unmerged_pr(board: Board) -> None:
    board.write(v2_doc([full_ticket(1, status="merge_ready", pr={"url": PR, "number": 7, "state": "open"})]))
    git_repo(board, remote=True)
    board.ok("link", "ACME-001", "--commit", "HEAD")
    before = board.tickets.read_bytes()
    r = board.fail("set", "ACME-001", "done", "--handoff", "merged?")
    assert "ACME-001 pr: the pull request is open, not merged" in r.stderr
    assert "fix: python3 kanban/board.py link ACME-001 --pr-state merged" in r.stderr
    assert "ask the user:" in r.stderr and '--no-pr "why"' in r.stderr
    assert board.tickets.read_bytes() == before
    board.ok("link", "ACME-001", "--pr-state", "merged")
    board.ok("set", "ACME-001", "done", "--handoff", "merged")
    assert board.ticket("ACME-001")["status"] == "done"


def test_done_unmerged_pr_with_no_pr_override(board: Board) -> None:
    board.write(v2_doc([full_ticket(1, status="merge_ready", pr={"url": PR, "state": "closed"})]))
    git_repo(board, remote=True)
    board.ok("link", "ACME-001", "--commit", "HEAD")
    board.ok("set", "ACME-001", "done", "--handoff", "landed another way", "--no-pr", "PR closed; cherry-picked")
    assert board.ticket("ACME-001")["done_without"] == {"pr": "PR closed; cherry-picked"}


def test_done_unmerged_pr_checked_even_without_git(board: Board) -> None:
    board.write(v2_doc([full_ticket(1, status="review", pr={"url": PR, "state": "draft"})]))
    r = board.fail("set", "ACME-001", "done", "--handoff", "x")
    assert "the pull request is draft, not merged" in r.stderr


@pytest.fixture
def merging(board: Board) -> Board:
    board.write(v2_doc([full_ticket(1, status="merge_ready", pr={"url": PR, "number": 7, "state": "open"}),
                        full_ticket(2, status="review"), full_ticket(3)]))
    return board


def test_next_waiting_for_merge_section(merging: Board) -> None:
    out = merging.ok("next").stdout
    resume = out.split("Waiting for merge")[0]
    assert "ACME-002" in resume and "ACME-001" not in resume  # not resumable work
    assert "Waiting for merge" in out and PR in out.split("Waiting for merge")[1].split("Next ticket")[0]
    j = json.loads(merging.ok("next", "--json").stdout)
    assert [t["id"] for t in j["merge_ready"]] == ["ACME-001"] and [t["id"] for t in j["open"]] == ["ACME-002"]
    assert merging.ok("next", "--brief").stdout.strip() == \
        "Slate 0.2.0: ACME-002 in review · 1 waiting for merge · next ready ACME-003"


def test_status_waiting_for_merge(merging: Board) -> None:
    out = merging.ok("status").stdout
    assert "Waiting for merge\n  ACME-001  Ticket number 1  (" + PR + ", open)" in out
    assert "merge_ready 1" in out
    j = json.loads(merging.ok("status", "--json").stdout)
    assert [t["id"] for t in j["merge_ready"]] == ["ACME-001"]


# --------------------------------------------------------------------------- #5 unscheduled phases


@pytest.fixture
def someday(v2: Board) -> Board:
    v2.ok("add-phase", "--id", "BACKLOG", "--name", "Someday", "--goal", "g", "--demo", "d", "--unscheduled")
    v2.ok("new", "--title", "Dark mode", "--summary", "s", "--phase", "BACKLOG", *STRICT)  # ACME-004, rank 4
    v2.ok("rerank", "ACME-004", "--first")
    return v2


def test_add_phase_unscheduled(someday: Board) -> None:
    assert someday.load()["phases"][-1] == {"id": "BACKLOG", "name": "Someday", "goal": "g", "demo": "d",
                                            "unscheduled": True}
    someday.ok("check")


def test_next_and_list_skip_unscheduled(someday: Board) -> None:
    j = json.loads(someday.ok("next", "--json").stdout)
    assert j["next"]["id"] == "ACME-001"  # ACME-004 ranks first but is unscheduled
    assert "ACME-004" not in someday.ok("list").stdout
    assert "ACME-004" not in someday.ok("next", "--brief").stdout


def test_status_and_show_put_unscheduled_last(someday: Board) -> None:
    doc = someday.load()
    doc["phases"].insert(0, doc["phases"].pop())  # unscheduled phase first in the array
    someday.write(doc)
    out = someday.ok("status").stdout
    assert out.index("P1 Link arrives") < out.index("P2 Password") < out.index("BACKLOG Someday (unscheduled)")
    assert "Unscheduled: 1 ticket in unscheduled phases" in out
    j = json.loads(someday.ok("status", "--json").stdout)
    assert [p["id"] for p in j["phases"]] == ["P1", "P2", "BACKLOG"]
    assert j["phases"][-1]["unscheduled"] is True and "unscheduled" not in j["phases"][0]
    assert j["unscheduled"] == 1
    assert "Phase BACKLOG (Someday, unscheduled)" in someday.ok("show", "ACME-004").stdout


@pytest.mark.parametrize("status", ["in_progress", "review", "user_testing", "merge_ready", "done"])
def test_set_refused_in_unscheduled_phase(someday: Board, status: str) -> None:
    before = someday.tickets.read_bytes()
    r = someday.fail("set", "ACME-004", status, "--handoff", "x")
    assert f"ACME-004 phase: BACKLOG is an unscheduled phase, so ACME-004 can't move to {status}" in r.stderr
    assert "fix: python3 kanban/board.py edit ACME-004 phase=P1" in r.stderr
    assert someday.tickets.read_bytes() == before


def test_set_allowed_after_moving_to_scheduled_phase(someday: Board) -> None:
    someday.ok("edit", "ACME-004", "phase=P1")
    someday.ok("set", "ACME-004", "in_progress")


def test_promote_in_unscheduled_phase_hints(someday: Board) -> None:
    someday.ok("new", "--title", "Maybe", "--summary", "s", "--phase", "BACKLOG", "--draft")
    someday.ok("edit", "ACME-005", "story=s", "description=d", 'acceptance:=["a"]',
               'test_scenarios:=["When a, then b"]')
    out = someday.ok("promote", "ACME-005").stdout
    assert someday.ticket("ACME-005")["status"] == "backlog"
    assert "unscheduled phase BACKLOG" in out and "edit ACME-005 phase=P1" in out


def test_edit_phase_schedules_again(someday: Board) -> None:
    someday.ok("edit-phase", "BACKLOG", "unscheduled:=false")
    assert "unscheduled" not in someday.load()["phases"][-1]
    assert json.loads(someday.ok("next", "--json").stdout)["next"]["id"] == "ACME-004"
    someday.ok("edit-phase", "BACKLOG", "unscheduled:=true")
    assert someday.load()["phases"][-1]["unscheduled"] is True


def test_unscheduled_must_be_bool(board: Board) -> None:
    doc = v2_doc([full_ticket(1)])
    doc["phases"][1]["unscheduled"] = "yes"
    board.write(doc)
    r = board.fail("check")
    assert "phase P2 unscheduled: must be true or false" in r.stderr
    assert "edit-phase P2 unscheduled:=true" in r.stderr


@pytest.mark.parametrize("pid", ["1st", "has space", "a" * 21, "P.1"])
def test_add_phase_id_rules(v2: Board, pid: str) -> None:
    r = v2.fail("add-phase", "--id", pid, "--name", "n", "--goal", "g", "--demo", "d")
    assert f"phase {pid} id: must start with a letter" in r.stderr and has_fix(r.stderr)


@pytest.mark.parametrize("pid", ["BACKLOG", "p3", "Later_2", "v2-polish", "A" * 20])
def test_add_phase_id_accepted(v2: Board, pid: str) -> None:
    v2.ok("add-phase", "--id", pid, "--name", "n", "--goal", "g", "--demo", "d")


# --------------------------------------------------------------------------- #1-#4 phase commands


def test_edit_phase_fields(v2: Board) -> None:
    v2.ok("edit-phase", "P1", "name=Links arrive", "goal=New goal", "demo:=null")
    assert v2.load()["phases"][0] == {"id": "P1", "name": "Links arrive", "goal": "New goal"}
    v2.ok("edit-phase", "P1", "demo=Show it", "unscheduled:=true")
    assert list(v2.load()["phases"][0]) == ["id", "name", "goal", "demo", "unscheduled"]


@pytest.mark.parametrize("args,fragment,code", [
    (("edit-phase", "P9", "name=x"), "phase P9 id: no such phase", 1),
    (("edit-phase", "P1", "id=P7"), "phase P1 id: can't be changed with edit-phase", 1),
    (("edit-phase", "P1", "colour=red"), "phase P1 colour: not a phase field", 1),
    (("edit-phase", "P1", "unscheduled=true"), "phase P1 unscheduled: must be true or false", 1),
    (("edit-phase", "P1", "name="), "phase P1 name: must be non-empty text", 1),
    (("edit-phase", "P1", "goal:=3"), "phase P1 goal: must be text", 1),
    (("edit-phase", "P1"), "edit-phase: give at least one", 2),
    (("edit-phase", "P1", "name"), "should be key=value", 2),
])
def test_edit_phase_refusals(v2: Board, args: Any, fragment: str, code: int) -> None:
    before = v2.tickets.read_bytes()
    r = v2.fail(*args, code=code)
    assert fragment in r.stderr and has_fix(r.stderr)
    assert v2.tickets.read_bytes() == before


def test_edit_phase_unknown_suggests_close_match(v2: Board) -> None:
    r = v2.fail("edit-phase", "p1", "name=x")
    assert "fix: python3 kanban/board.py edit-phase P1 name=x   (did you mean this?)" in r.stderr


def test_rename_phase(v2: Board) -> None:
    out = v2.ok("rename-phase", "P1", "LINKS").stdout
    assert "3 tickets moved with it" in out
    doc = v2.load()
    assert [p["id"] for p in doc["phases"]] == ["LINKS", "P2"]
    assert {t["phase"] for t in doc["tickets"]} == {"LINKS"}
    v2.ok("check")
    assert "nothing changed" in v2.ok("rename-phase", "LINKS", "LINKS").stdout


def test_rename_phase_refusals(v2: Board) -> None:
    before = v2.tickets.read_bytes()
    r = v2.fail("rename-phase", "P1", "P2")
    assert "phase P2 id: already exists" in r.stderr and "remove-phase P1 --move-to P2" in r.stderr
    r = v2.fail("rename-phase", "P1", "9lives")
    assert "phase 9lives id: must start with a letter" in r.stderr and has_fix(r.stderr)
    r = v2.fail("rename-phase", "P8", "P9")
    assert "phase P8 id: no such phase" in r.stderr and has_fix(r.stderr)
    assert v2.tickets.read_bytes() == before


def test_remove_phase(v2: Board) -> None:
    before = v2.tickets.read_bytes()
    r = v2.fail("remove-phase", "P1")
    assert "phase P1: 3 tickets are in it (ACME-001, ACME-002, ACME-003)" in r.stderr
    assert "fix: python3 kanban/board.py remove-phase P1 --move-to P2" in r.stderr
    assert v2.tickets.read_bytes() == before
    r = v2.fail("remove-phase", "P1", "--move-to", "P1")
    assert "--move-to must name a different phase" in r.stderr and has_fix(r.stderr)
    r = v2.fail("remove-phase", "P1", "--move-to", "P9")
    assert "phase P9 id: no such phase" in r.stderr
    assert v2.tickets.read_bytes() == before
    out = v2.ok("remove-phase", "P1", "--move-to", "P2").stdout
    assert "moved 3 tickets to P2" in out
    doc = v2.load()
    assert [p["id"] for p in doc["phases"]] == ["P2"] and {t["phase"] for t in doc["tickets"]} == {"P2"}
    v2.ok("add-phase", "--id", "P3", "--name", "n", "--goal", "g", "--demo", "d")
    v2.ok("remove-phase", "P3")  # unused: no --move-to needed
    assert [p["id"] for p in v2.load()["phases"]] == ["P2"]


def test_reorder_phases(v2: Board) -> None:
    v2.ok("add-phase", "--id", "P3", "--name", "n", "--goal", "g", "--demo", "d")
    v2.ok("reorder-phases", "P3", "P1", "P2")
    assert [p["id"] for p in v2.load()["phases"]] == ["P3", "P1", "P2"]
    v2.ok("reorder-phases", "P1,P2", "P3")
    assert [p["id"] for p in v2.load()["phases"]] == ["P1", "P2", "P3"]
    assert v2.load()["phases"][0] == {"id": "P1", "name": "Link arrives", "goal": "g", "demo": "d"}


@pytest.mark.parametrize("ids,fragment", [
    (["P1"], "missing: P2"),
    (["P1", "P2", "P1"], "listed twice: P1"),
    (["P1", "P2", "P7"], "not a phase: P7"),
])
def test_reorder_phases_refusals(v2: Board, ids: List[str], fragment: str) -> None:
    before = v2.tickets.read_bytes()
    r = v2.fail("reorder-phases", *ids)
    assert "phases order: list every phase exactly once" in r.stderr and fragment in r.stderr
    assert "fix: python3 kanban/board.py reorder-phases P1 P2" in r.stderr
    assert v2.tickets.read_bytes() == before


# --------------------------------------------------------------------------- every new refusal says how to fix


V2_REFUSALS = [
    (("set", "ACME-001,ACME-002", "review", "--handoff", "x"), 1),
    (("set", "ACME-002", "merge_ready", "--handoff", "x"), 1),
    (("set", "ACME-001", "merge_ready"), 1),
    (("set", "ACME-001", "merge_ready", "--handoff", "x", "--no-code", "y"), 1),
    (("set", "ACME-002", "done", "--handoff", "x", "--ignore-deps", "r"), 1),
    (("set", "ACME-002", "backlog", "--ignore-deps", "r"), 1),
    (("set", "ACME-002", "in_progress", "--ignore-deps", " "), 1),
    (("link", "ACME-001,ACME-099", "--pr", PR), 1),
    (("edit", "ACME-001", "title+=x"), 1),
    (("edit", "ACME-001", "item_checks:={}"), 1),
    (("edit-phase", "P9", "name=x"), 1),
    (("edit-phase", "P1", "id=P3"), 1),
    (("edit-phase", "P1", "unscheduled=yes"), 1),
    (("edit-phase", "P1"), 2),
    (("rename-phase", "P1", "P2"), 1),
    (("rename-phase", "P1", "bad id"), 1),
    (("remove-phase", "P1"), 1),
    (("remove-phase", "P1", "--move-to", "P9"), 1),
    (("reorder-phases", "P2"), 1),
    (("add-phase", "--id", "bad id", "--name", "n", "--goal", "g", "--demo", "d"), 1),
    (("new", "--title", "T", "--summary", "s", "--phase", "P1", "--draft", "--fixes", "ACME-099"), 1),
    (("new", "--title", "T", "--summary", "s", "--phase", "P1", "--draft", "--fixes", "ACME-001",
      "--after", "ACME-002"), 2),
    (("new", "--title", "T", "--summary", "s", "--phase", "P1", "--draft", "--reopen"), 2),
    (("check-item", "ACME-001", "acceptance", "5"), 1),
    (("check-item", "ACME-099", "test", "0"), 1),
    (("check-item", "ACME-001", "nope", "0"), 2),
    (("uncheck-item", "ACME-001", "test", "9"), 1),
    (("export", "--json", "--status", "doing"), 1),
    (("list", "--phase", "P9"), 1),
    (("status", "--status", "nope"), 1),
    (("set-meta", "check_quiet_optional=yes"), 1),
]


@pytest.mark.parametrize("args,code", V2_REFUSALS, ids=[" ".join(a) for a, _ in V2_REFUSALS])
def test_every_v2_refusal_says_how_to_fix(v2: Board, args: Any, code: int) -> None:
    before = v2.tickets.read_bytes()
    r = v2.fail(*args, code=code)
    assert has_fix(r.stderr), r.stderr
    assert r.stderr.startswith("error: ") or "usage error" in r.stderr, r.stderr
    assert v2.tickets.read_bytes() == before


# --------------------------------------------------------------------------- portability


def test_non_ascii_written_as_utf8_with_lf_only(v2: Board) -> None:
    text = "café — ✓ 日本"
    v2.ok("edit", "ACME-001", f"summary={text}", f"description+={text}")
    v2.ok("check-item", "ACME-001", "acceptance", "0", "--evidence", text)
    raw = v2.tickets.read_bytes()
    assert b"\r\n" not in raw and b"\\u" not in raw
    assert text.encode("utf-8") in raw
    doc = json.loads(raw.decode("utf-8"))
    t = next(x for x in doc["tickets"] if x["id"] == "ACME-001")
    assert t["summary"] == text and t["item_checks"]["acceptance:0"]["evidence"] == text
    assert raw.decode("utf-8") == json.dumps(doc, indent=2, ensure_ascii=False) + "\n"  # exact round trip
    assert text in v2.ok("show", "ACME-001").stdout
