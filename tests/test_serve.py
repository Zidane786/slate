"""Tests for `board.py serve`: the board page server and its JSON API (docs/plans/2026-09-26-v0.2-build-plan.md,
"Browser clicks become real board changes", "Board server started automatically", "Every board-page action
saves in live mode").

Servers run as real subprocesses on free local ports; every test stops what it started.
"""

from __future__ import annotations

import http.client
import json
import os
import signal
import socket
import urllib.request
import subprocess
import sys
import threading
import time
from email.utils import formatdate
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import pytest

from conftest import USER_TEST, Board, base_doc, full_ticket

V2_STATUSES = ["draft", "backlog", "ready", "in_progress", "review", "user_testing", "merge_ready", "done"]


# --------------------------------------------------------------------------- helpers


def v2_doc(tickets: List[Dict[str, Any]]) -> Dict[str, Any]:
    d = base_doc(tickets)
    d["meta"].update({"slate_version": "0.2.0", "schema_version": 2, "statuses": list(V2_STATUSES)})
    return d


def demo_doc() -> Dict[str, Any]:
    """001 backlog; 002 waits for 001; 003 in user testing with one required user test;
    004 a complete draft; 005 a bare draft (can't be promoted)."""
    return v2_doc([
        full_ticket(1, unlocks=["ACME-002"], acceptance=["It works", "It is fast"]),
        full_ticket(2, depends_on=["ACME-001"]),
        full_ticket(3, areas=["frontend"], user_tests=[USER_TEST], status="user_testing",
                    handoff=[{"date": "2026-09-20", "status": "review", "note": "built"},
                             {"date": "2026-09-21", "status": "user_testing", "note": "try it"}]),
        full_ticket(4, status="draft"),
        {"id": "ACME-005", "title": "Someday idea", "summary": "Maybe.", "phase": "P1", "status": "draft",
         "rank": 5, "priority": "P2", "depends_on": [], "areas": ["backend"], "estimate": "1d"},
    ])


def free_port() -> int:
    for _ in range(500):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
        s.close()
        if p < 65000 and all(port_free(p + i) for i in range(1, 3)):
            return p
    raise RuntimeError("no free port")


def port_free(p: int) -> bool:
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p))
        return True
    except OSError:
        return False
    finally:
        s.close()


def runtime(board: Board) -> Optional[Dict[str, Any]]:
    p = board.dir / ".slate-serve.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def pid_alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:  # a zombie (exited, not yet reaped) counts as gone
        with open(f"/proc/{pid}/status") as f:
            return "zombie" not in f.read()
    except OSError:
        pass
    r = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return bool(r.stdout.strip()) and not r.stdout.strip().startswith("Z")


def wait_for(cond: Any, timeout: float = 15.0, step: float = 0.1) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        v = cond()
        if v:
            return v
        time.sleep(step)
    return cond()


def kill(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def request(port: int, method: str, path: str, body: Any = None, token: Optional[str] = None,
            headers: Optional[Dict[str, str]] = None, raw: Optional[bytes] = None) -> Tuple[int, Any, Any]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    h = dict(headers or {})
    data = raw
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    if token is not None:
        h["X-Slate-Token"] = token
    conn.request(method, path, body=data, headers=h)
    r = conn.getresponse()
    payload = r.read()
    conn.close()
    if (r.getheader("Content-Type") or "").startswith("application/json"):
        return r.status, json.loads(payload.decode("utf-8")), r
    return r.status, payload, r


class Live:
    """A foreground `serve` subprocess on its own port."""

    def __init__(self, board: Board, *extra: str) -> None:
        self.board = board
        self.port = free_port()
        self.proc = subprocess.Popen([sys.executable, str(board.script), "serve", "--port", str(self.port),
                                      "--strict-port", "--idle-exit", "0", *extra],
                                     cwd=str(board.root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        ok = wait_for(lambda: (runtime(board) or {}).get("pid") == self.proc.pid and self._answers())
        if not ok:
            self.stop()
            raise AssertionError(f"server didn't start: {self.proc.stdout.read() if self.proc.stdout else ''}")
        self.info = self.get("/api/info")[1]
        self.token = self.info["token"]

    def _answers(self) -> bool:
        try:
            return request(self.port, "GET", "/api/info")[0] == 200
        except OSError:
            return False

    def get(self, path: str, **kw: Any) -> Tuple[int, Any, Any]:
        return request(self.port, "GET", path, **kw)

    def post(self, path: str, body: Any, token: Any = "default", **kw: Any) -> Tuple[int, Any, Any]:
        return request(self.port, "POST", path, body=body, token=self.token if token == "default" else token, **kw)

    def stop(self) -> str:
        if self.proc.poll() is None:
            self.proc.terminate()
        try:
            out, _ = self.proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            out, _ = self.proc.communicate()
        return out or ""


@pytest.fixture
def live(board: Board) -> Iterator[Live]:
    board.write(demo_doc())
    (board.dir / "index.html").write_text("<!doctype html><html><head></head><body>Slate board</body></html>\n",
                                          encoding="utf-8")
    srv = Live(board)
    yield srv
    srv.stop()


@pytest.fixture
def cleanup(board: Board) -> Iterator[List[int]]:
    """pids to kill after the test (background servers started by --ensure)."""
    pids: List[int] = []
    yield pids
    rec = runtime(board)
    if rec and isinstance(rec.get("pid"), int):
        pids.append(rec["pid"])
    for pid in pids:
        kill(pid)


# --------------------------------------------------------------------------- GET /api/info, /api/allowed


def test_info_reports_board_token_statuses_and_health(live: Live, board: Board) -> None:
    code, info, _ = live.get("/api/info")
    assert code == 200
    assert info["slate"] is True and info["version"] == "0.2.0"
    assert os.path.normcase(info["board_path"]) == os.path.normcase(str(board.tickets.resolve()))
    assert isinstance(info["token"], str) and len(info["token"]) >= 20
    assert info["workflow"] == "free"
    assert [s["name"] for s in info["statuses"]] == V2_STATUSES
    assert set(info["statuses"][0]) >= {"name", "label", "role", "from"}
    assert info["unlock_active"] is None
    assert isinstance(info["doctor"]["issues"], list)
    assert all(set(i) >= {"code", "kind", "message"} for i in info["doctor"]["issues"])


def test_info_shows_active_unlock_and_workflow_mode(live: Live, board: Board) -> None:
    board.ok("set-meta", "workflow=strict")
    until = "2099-01-01T00:00:00Z"
    (board.dir / ".slate-unlock.json").write_text(json.dumps({"until": until, "reason": "merge fix"}), encoding="utf-8")
    info = live.get("/api/info")[1]
    assert info["unlock_active"] == {"until": until, "reason": "merge fix"}
    assert info["workflow"] == "strict"
    assert next(s for s in info["statuses"] if s["name"] == "review")["from"] == ["in_progress"]
    assert any(i["code"] == "unlock-active" for i in info["doctor"]["issues"])


def test_allowed_evaluates_gates_without_writing(live: Live, board: Board) -> None:
    before = board.tickets.read_bytes()
    code, out, _ = live.get("/api/allowed?id=ACME-002")
    assert code == 200
    assert "in_progress" in out["reasons"] and "ACME-001" in out["reasons"]["in_progress"]
    assert "ready" in out["allowed"] and "backlog" not in out["allowed"]  # its own status is left out
    assert "done" in out["reasons"]
    code, out, _ = live.get("/api/allowed?id=ACME-001")
    assert "in_progress" in out["allowed"] and "review" in out["allowed"]  # a note is assumed
    code, out, _ = live.get("/api/allowed?id=ACME-003")
    assert "merge_ready" in out["reasons"] and "user test" in out["reasons"]["merge_ready"]
    assert board.tickets.read_bytes() == before


def test_allowed_follows_transition_rules(live: Live, board: Board) -> None:
    board.ok("set-meta", "workflow=strict")
    out = live.get("/api/allowed?id=ACME-001")[1]
    assert "in_progress" in out["allowed"]
    assert "review" in out["reasons"] and "can't move" in out["reasons"]["review"]


def test_allowed_unknown_ticket_and_missing_id(live: Live) -> None:
    code, out, _ = live.get("/api/allowed?id=ACME-999")
    assert code == 409 and out["ok"] is False and out["errors"][0]["message"]
    assert live.get("/api/allowed")[0] == 400


# --------------------------------------------------------------------------- POST: token and body


def test_post_needs_the_token(live: Live, board: Board) -> None:
    before = board.tickets.read_bytes()
    for token in (None, "wrong"):
        code, out, _ = live.post("/api/note", {"id": "ACME-001", "text": "hi"}, token=token)
        assert code == 403 and out["ok"] is False and out["errors"][0]["field"] == "token"
    assert board.tickets.read_bytes() == before


def test_post_bad_body_and_unknown_endpoint(live: Live) -> None:
    assert live.post("/api/note", None, raw=b"not json")[0] == 400
    assert live.post("/api/note", ["a"])[0] == 400
    assert live.post("/api/note", {"id": "ACME-001"})[0] == 400                    # no text
    assert live.post("/api/note", {"id": "ACME-001,ACME-002", "text": "x"})[0] == 400  # one ticket only
    assert live.post("/api/usertest", {"id": "ACME-003", "index": 0, "result": "maybe"})[0] == 400
    assert live.post("/api/check-item", {"id": "ACME-001", "kind": "other", "index": 0})[0] == 400
    assert live.post("/api/nope", {"id": "ACME-001"})[0] == 404


def test_host_header_from_another_site_is_refused(live: Live) -> None:
    assert live.get("/api/info", headers={"Host": "evil.example:80"})[0] == 403
    assert live.post("/api/note", {"id": "ACME-001", "text": "x"}, headers={"Origin": "http://evil.example"})[0] == 403
    assert live.get("/api/info", headers={"Host": f"localhost:{live.port}"})[0] == 200


# --------------------------------------------------------------------------- POST /api/set


def test_set_happy_path_records_via_board_page(live: Live, board: Board) -> None:
    code, out, _ = live.post("/api/set", {"id": "ACME-001", "status": "in_progress"})
    assert code == 200 and out["ok"] is True, out
    t = board.ticket("ACME-001")
    assert t["status"] == "in_progress" and t["claimed_by"]["by"]
    code, out, _ = live.post("/api/set", {"id": "ACME-001", "status": "review", "handoff": "built it"})
    assert code == 200, out
    last = board.ticket("ACME-001")["handoff"][-1]
    assert last["status"] == "review" and last["note"] == "built it" and last["via"] == "board page"
    assert board.ok("check").returncode == 0


def test_set_without_note_returns_needs_handoff(live: Live, board: Board) -> None:
    live.post("/api/set", {"id": "ACME-001", "status": "in_progress"})
    code, out, _ = live.post("/api/set", {"id": "ACME-001", "status": "review"})
    assert code == 409 and out["ok"] is False and out["code"] == "needs_handoff"
    e = out["errors"][0]
    assert e["id"] == "ACME-001" and e["field"] == "handoff" and e["fix"]
    assert board.ticket("ACME-001")["status"] == "in_progress"


def test_set_refusal_comes_before_asking_for_a_note(live: Live, board: Board) -> None:
    code, out, _ = live.post("/api/set", {"id": "ACME-002", "status": "review"})
    assert code == 409 and "code" not in out
    e = out["errors"][0]
    assert e["id"] == "ACME-002" and e["field"] == "depends_on" and "ACME-001" in e["message"]
    assert any("ACME-001" in f for f in e["fix"])


def test_set_backward_move_under_rules_needs_handoff(live: Live, board: Board) -> None:
    board.ok("set", "ACME-001", "in_progress")
    board.ok("set", "ACME-001", "review", "--handoff", "built")
    board.ok("set-meta", "workflow=strict")
    code, out, _ = live.post("/api/set", {"id": "ACME-001", "status": "in_progress"})
    assert code == 409 and out["code"] == "needs_handoff" and "back" in out["errors"][0]["message"]
    code, out, _ = live.post("/api/set", {"id": "ACME-001", "status": "in_progress", "handoff": "review found a bug"})
    assert code == 200, out
    assert board.ticket("ACME-001")["status"] == "in_progress"


def test_set_forward_move_breaking_rules_is_refused_with_fix(live: Live, board: Board) -> None:
    board.ok("set-meta", "workflow=strict")
    code, out, _ = live.post("/api/set", {"id": "ACME-001", "status": "review", "handoff": "skip"})
    assert code == 409
    assert out["errors"][0]["field"] == "status" and "can't move" in out["errors"][0]["message"]
    assert any("in_progress" in f for f in out["errors"][0]["fix"])


# --------------------------------------------------------------------------- POST: items, user tests, notes


def test_check_and_uncheck_item(live: Live, board: Board) -> None:
    code, out, _ = live.post("/api/check-item", {"id": "ACME-001", "kind": "acceptance", "index": 1,
                                                 "evidence": "timing test"})
    assert code == 200, out
    assert board.ticket("ACME-001")["item_checks"]["acceptance:1"]["evidence"] == "timing test"
    code, out, _ = live.post("/api/uncheck-item", {"id": "ACME-001", "kind": "acceptance", "index": 1})
    assert code == 200, out
    assert "item_checks" not in board.ticket("ACME-001")


def test_check_item_refusal(live: Live) -> None:
    code, out, _ = live.post("/api/check-item", {"id": "ACME-001", "kind": "test", "index": 7})
    assert code == 409
    e = out["errors"][0]
    assert e["id"] == "ACME-001" and e["field"] == "test_scenarios" and "index 7" in e["message"] and e["fix"]


def test_usertest_pass_reset_and_fail(live: Live, board: Board) -> None:
    code, out, _ = live.post("/api/usertest", {"id": "ACME-003", "index": 0, "result": "pass", "note": "fine"})
    assert code == 200, out
    assert board.ticket("ACME-003")["user_checks"]["0"]["result"] == "pass"
    code, out, _ = live.post("/api/usertest", {"id": "ACME-003", "index": 0, "result": "reset"})
    assert code == 200, out
    t = board.ticket("ACME-003")
    assert "user_checks" not in t and t["handoff"][-1]["via"] == "board page"
    code, out, _ = live.post("/api/usertest", {"id": "ACME-003", "index": 0, "result": "fail", "note": "blank"})
    assert code == 200, out
    t = board.ticket("ACME-003")
    assert t["status"] == "in_progress" and t["handoff"][-1]["via"] == "board page"
    assert "User test failed" in t["handoff"][-1]["note"]


def test_usertest_refusal(live: Live) -> None:
    code, out, _ = live.post("/api/usertest", {"id": "ACME-003", "index": 4, "result": "pass"})
    assert code == 409 and out["errors"][0]["field"] == "user_tests"


def test_note(live: Live, board: Board) -> None:
    code, out, _ = live.post("/api/note", {"id": "ACME-002", "text": "waiting on design"})
    assert code == 200, out
    h = board.ticket("ACME-002")["handoff"][-1]
    assert h == {"date": h["date"], "status": "backlog", "note": "waiting on design", "via": "board page"}
    code, out, _ = live.post("/api/note", {"id": "ACME-404", "text": "x"})
    assert code == 409 and out["errors"][0]["message"]


def test_promote(live: Live, board: Board) -> None:
    code, out, _ = live.post("/api/promote", {"id": "ACME-004"})
    assert code == 200, out
    assert board.ticket("ACME-004")["status"] == "backlog"
    code, out, _ = live.post("/api/promote", {"id": "ACME-005"})
    assert code == 409 and len(out["errors"]) > 1  # names every missing field
    assert board.ticket("ACME-005")["status"] == "draft"


def test_claim_and_release(live: Live, board: Board) -> None:
    code, out, _ = live.post("/api/claim", {"id": "ACME-001", "as": "Priya"})
    assert code == 200, out
    assert board.ticket("ACME-001")["claimed_by"]["by"] == "Priya"
    code, out, _ = live.post("/api/claim", {"id": "ACME-001", "as": "Sam"})
    assert code == 409 and out["errors"][0]["field"] == "claimed_by"
    code, out, _ = live.post("/api/release", {"id": "ACME-001"})  # the server's own name isn't Priya
    assert code == 409 and "Priya" in out["errors"][0]["message"]
    code, out, _ = live.post("/api/release", {"id": "ACME-001", "as": "Priya"})
    assert code == 200, out
    assert "claimed_by" not in board.ticket("ACME-001")


def test_write_waits_for_the_write_lock(live: Live, board: Board) -> None:
    lock = board.dir / ".slate-write.lock"
    lock.write_text(json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "time": "now", "cmd": "test"}),
                    encoding="utf-8")
    result: Dict[str, Any] = {}

    def go() -> None:
        result["r"] = live.post("/api/note", {"id": "ACME-001", "text": "after the lock"})

    th = threading.Thread(target=go)
    th.start()
    time.sleep(0.6)
    assert "r" not in result  # still waiting
    lock.unlink()
    th.join(15)
    assert result["r"][0] == 200
    assert board.ticket("ACME-001")["handoff"][-1]["note"] == "after the lock"


# --------------------------------------------------------------------------- files


def test_serves_page_and_304(live: Live, board: Board) -> None:
    code, body, _ = live.get("/")
    assert code == 200 and b"Slate board" in body
    code, body, r = live.get("/tickets.json")
    assert code == 200 and body["meta"]["project"] == "Acme"  # served as application/json
    lm = r.getheader("Last-Modified")
    assert lm and r.getheader("Cache-Control") == "no-cache"
    assert live.get("/tickets.json", headers={"If-Modified-Since": lm})[0] == 304
    old = formatdate(time.time() - 3600, usegmt=True)
    assert live.get("/tickets.json", headers={"If-Modified-Since": old})[0] == 200
    time.sleep(1.1)
    assert live.post("/api/note", {"id": "ACME-001", "text": "changed"})[0] == 200
    assert live.get("/tickets.json", headers={"If-Modified-Since": lm})[0] == 200


def test_only_files_inside_the_kanban_folder(live: Live, board: Board) -> None:
    (board.root / "secret.txt").write_text("TOP SECRET", encoding="utf-8")
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt", "/%2e%2e%2fsecret.txt",
                 "/.slate-serve.json", "/.slate-write.lock", "/sub/", "/..\\secret.txt"):
        code, body, _ = live.get(path)
        assert code in (403, 404), (path, code)
        assert b"TOP SECRET" not in (body if isinstance(body, bytes) else json.dumps(body).encode())
    if hasattr(os, "symlink") and os.name != "nt":
        os.symlink(str(board.root / "secret.txt"), str(board.dir / "link.txt"))
        code, body, _ = live.get("/link.txt")
        assert code == 404 and b"TOP SECRET" not in body


def test_foreground_refuses_a_second_server(live: Live, board: Board) -> None:
    r = board.run("serve", "--port", str(free_port()))
    assert r.returncode == 1 and "already running" in r.stderr and live.info["token"] not in r.stderr


def test_non_loopback_host_warns_loudly(board: Board) -> None:
    board.write(demo_doc())
    port = free_port()
    proc = subprocess.Popen([sys.executable, str(board.script), "serve", "--host", "0.0.0.0", "--port", str(port),
                             "--strict-port", "--idle-exit", "0"], cwd=str(board.root),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        assert wait_for(lambda: (runtime(board) or {}).get("pid") == proc.pid)
    finally:
        proc.terminate()
        out = proc.communicate(timeout=10)[0]
    assert "WARNING" in out and "CHANGE TICKETS" in out
    assert runtime(board) is None  # removed on a clean exit


# --------------------------------------------------------------------------- --ensure / --status / --stop


def test_ensure_starts_once_then_reuses(board: Board, cleanup: List[int]) -> None:
    board.write(demo_doc())
    port = free_port()
    r = board.ok("serve", "--ensure", "--port", str(port))
    rec = runtime(board)
    assert rec is not None
    assert set(rec) == {"pid", "host", "port", "url", "started", "board_path", "slate_version"}
    assert rec["port"] == port and rec["host"] == "127.0.0.1" and rec["url"] == f"http://127.0.0.1:{port}/"
    assert rec["slate_version"] == "0.2.0" and os.path.normcase(rec["board_path"]) == os.path.normcase(str(board.tickets.resolve()))
    assert rec["url"] in r.stdout and "background" in r.stdout
    assert (board.dir / ".slate-serve.log").exists()
    r2 = board.ok("serve", "--ensure", "--port", str(port))
    assert "already running" in r2.stdout and rec["url"] in r2.stdout
    assert runtime(board)["pid"] == rec["pid"]
    assert request(port, "GET", "/api/info")[1]["pid"] == rec["pid"]
    st = board.ok("serve", "--status")
    assert "running" in st.stdout and rec["url"] in st.stdout


def test_ensure_cleans_up_a_stale_runtime_file(board: Board, cleanup: List[int]) -> None:
    board.write(demo_doc())
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    port = free_port()
    (board.dir / ".slate-serve.json").write_text(json.dumps({
        "pid": dead.pid, "host": "127.0.0.1", "port": port, "url": f"http://127.0.0.1:{port}/",
        "started": "2026-01-01T00:00:00Z", "board_path": str(board.tickets.resolve()), "slate_version": "0.2.0"}),
        encoding="utf-8")
    assert "stale" in board.ok("serve", "--status").stdout
    r = board.ok("serve", "--ensure", "--port", str(port))
    assert "Removed a stale kanban/.slate-serve.json" in r.stdout
    rec = runtime(board)
    assert rec["pid"] != dead.pid and pid_alive(rec["pid"])


def test_ensure_next_to_a_foreign_server(board: Board, cleanup: List[int], tmp_path: Path) -> None:
    board.write(demo_doc())
    port = free_port()
    other = tmp_path / "other"
    other.mkdir()
    foreign = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                               cwd=str(other), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_for(lambda: not port_free(port))

        def answers() -> bool:
            try:
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                        f"http://127.0.0.1:{port}/", timeout=2) as resp:
                    return resp.status == 200
            except Exception:
                return False
        assert wait_for(answers)
        r = board.ok("serve", "--ensure", "--port", str(port))
        rec = runtime(board)
        assert rec["port"] != port
        assert f"Port {port} answers but isn't a Slate server" in r.stdout and "view-only" in r.stdout
        assert rec["url"] in r.stdout
    finally:
        foreign.terminate()
        foreign.wait(10)


def test_ensure_takes_the_next_free_port(board: Board, cleanup: List[int]) -> None:
    board.write(demo_doc())
    port = free_port()
    holder = socket.socket()
    holder.bind(("127.0.0.1", port))
    holder.listen(1)
    try:
        r = board.ok("serve", "--ensure", "--port", str(port))
        rec = runtime(board)
        assert rec["port"] == port + 1
        assert f"Port {port} is taken; using {port + 1}" in r.stdout and rec["url"] in r.stdout
    finally:
        holder.close()


def test_strict_port_refuses_a_taken_port(board: Board, cleanup: List[int]) -> None:
    board.write(demo_doc())
    port = free_port()
    holder = socket.socket()
    holder.bind(("127.0.0.1", port))
    holder.listen(1)
    try:
        r = board.fail("serve", "--ensure", "--port", str(port), "--strict-port")
        assert f"port {port} is taken" in r.stderr and "fix:" in r.stderr
        assert runtime(board) is None
        r = board.fail("serve", "--port", str(port), "--strict-port")
        assert f"port {port} is taken" in r.stderr
    finally:
        holder.close()


def test_stop(board: Board, cleanup: List[int]) -> None:
    board.write(demo_doc())
    port = free_port()
    board.ok("serve", "--ensure", "--port", str(port))
    pid = runtime(board)["pid"]
    r = board.ok("serve", "--stop")
    assert "Stopped the board server" in r.stdout
    assert runtime(board) is None
    assert wait_for(lambda: not pid_alive(pid), timeout=10)
    assert "nothing to stop" in board.ok("serve", "--stop").stdout
    assert "No board server" in board.ok("serve", "--status").stdout


def test_stop_leaves_an_unrelated_process_alone(board: Board) -> None:
    board.write(demo_doc())
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        (board.dir / ".slate-serve.json").write_text(json.dumps({
            "pid": other.pid, "host": "127.0.0.1", "port": free_port(), "url": f"http://127.0.0.1:{free_port()}/",
            "started": "2026-01-01T00:00:00Z", "board_path": str(board.tickets.resolve())}), encoding="utf-8")
        r = board.ok("serve", "--stop")
        assert "left alone" in r.stdout and runtime(board) is None
        assert other.poll() is None
    finally:
        other.kill()
        other.wait()


def test_idle_exit(board: Board, cleanup: List[int]) -> None:
    board.write(demo_doc())
    port = free_port()
    board.ok("serve", "--ensure", "--port", str(port), "--idle-exit", "0.0004")  # about 1.4 s
    pid = runtime(board)["pid"]
    assert wait_for(lambda: runtime(board) is None and not pid_alive(pid), timeout=20)
    assert "no request for" in (board.dir / ".slate-serve.log").read_text(encoding="utf-8")


def test_next_brief_shows_the_live_url(board: Board, cleanup: List[int]) -> None:
    board.write(demo_doc())
    port = free_port()
    board.ok("serve", "--ensure", "--port", str(port))
    out = board.ok("next", "--brief").stdout
    assert f"board page live at http://127.0.0.1:{port}/" in out
    board.ok("serve", "--stop")
    assert "board page live" not in board.ok("next", "--brief").stdout


def test_serve_without_a_board_refuses(board: Board) -> None:
    r = board.fail("serve", "--ensure", "--port", str(free_port()))
    assert "no tickets.json" in r.stderr and "fix:" in r.stderr


def test_needs_handoff_follows_the_per_state_note_rule(live: Live, board: Board) -> None:
    board.ok("edit-status", "in_progress", "note=required")
    board.ok("edit-status", "review", "note=optional")
    info = live.get("/api/info")[1]
    notes = {s["name"]: s["note"] for s in info["statuses"]}
    assert notes["in_progress"] == "required" and notes["review"] == "optional" and notes["done"] == "required"
    code, out, _ = live.post("/api/set", {"id": "ACME-001", "status": "in_progress"})
    assert code == 409 and out["code"] == "needs_handoff"
    assert live.post("/api/set", {"id": "ACME-001", "status": "in_progress", "handoff": "go"})[0] == 200
    code, out, _ = live.post("/api/set", {"id": "ACME-001", "status": "review"})  # optional now
    assert code == 200, out
    assert board.ticket("ACME-001")["status"] == "review"


def test_served_page_carries_the_token(live: Live, board: Board) -> None:
    for path in ("/", "/index.html"):
        code, body, r = live.get(path)
        assert code == 200 and r.getheader("Content-Type").startswith("text/html")
        assert f'<head><meta name="slate-token" content="{live.token}">'.encode() in body and b"Slate board" in body
        lm = r.getheader("Last-Modified")
        assert lm and live.get(path, headers={"If-Modified-Since": lm})[0] == 304
    assert live.token.encode() not in (board.dir / "index.html").read_bytes()  # the file itself is untouched


def test_unlock_record_is_the_one_dotfile_served(live: Live, board: Board) -> None:
    assert live.get("/.slate-unlock.json")[0] == 404
    (board.dir / ".slate-unlock.json").write_text('{"until": "2099-01-01T00:00:00Z", "reason": "x"}', encoding="utf-8")
    code, body, _ = live.get("/.slate-unlock.json")
    assert code == 200 and body["reason"] == "x"
    assert live.get("/.slate-unlock-request.json")[0] == 404


def test_needs_handoff_code_is_also_on_the_error(live: Live) -> None:
    live.post("/api/set", {"id": "ACME-001", "status": "in_progress"})
    code, out, _ = live.post("/api/set", {"id": "ACME-001", "status": "review"})
    assert code == 409 and out["code"] == "needs_handoff" and out["errors"][0]["code"] == "needs_handoff"


def test_port_defaults_to_slate_md_board_port(board: Board, cleanup: List[int]) -> None:
    board.write(demo_doc())
    port = free_port()
    (board.root / "SLATE.md").write_text(f"# x\nBoard server: auto\nBoard port: {port}\n", encoding="utf-8")
    r = board.ok("serve", "--ensure")
    assert runtime(board)["port"] == port and f"http://127.0.0.1:{port}/" in r.stdout
