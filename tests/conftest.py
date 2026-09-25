"""Shared helpers for the board.py tests.

Every test gets its own copy of board.py in tmp_path/kanban/ and runs it in a subprocess,
so the "tickets.json lives next to board.py" logic is exercised for real.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

REPO = Path(__file__).resolve().parents[1]
BOARD_SRC = REPO / "plugins" / "slate" / "assets" / "board" / "board.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
FORGE_BOARD = REPO.parent / "forge" / "kanban" / "tickets.json"


def full_ticket(n: int, prefix: str = "ACME", **over: Any) -> Dict[str, Any]:
    """A complete, strictly valid ticket (backend, so no user test needed)."""
    t: Dict[str, Any] = {
        "id": f"{prefix}-{n:03d}",
        "title": f"Ticket number {n}",
        "summary": "People get a thing.",
        "story": "Priya uses the thing.",
        "description": "All the detail.",
        "acceptance": ["It works"],
        "test_scenarios": ["When X happens, then Y"],
        "technical": "Files: x.py",
        "phase": "P1",
        "areas": ["backend"],
        "priority": "P1",
        "rank": n,
        "status": "backlog",
        "depends_on": [],
        "unlocks": [],
        "estimate": "1d",
        "labels": [],
        "handoff": [],
    }
    t.update(over)
    return t


USER_TEST = {
    "title": "Reset with a known email",
    "setup": "Open the app at http://localhost:3000.",
    "steps": ["Click 'Forgot password'", "Type priya@example.com", "Click 'Send link'"],
    "expect": "You see 'Check your email'.",
    "required": True,
}


def base_doc(tickets: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    return {
        "meta": {
            "project": "Acme",
            "prefix": "ACME",
            "slate_version": "0.1.0",
            "schema_version": 1,
            "generated": "2026-09-26",
            "statuses": ["draft", "backlog", "ready", "in_progress", "review", "user_testing", "done"],
            "areas": ["backend", "frontend", "infra"],
            "priorities": ["P0", "P1", "P2", "P3"],
            "user_test_areas": ["frontend", "ui"],
        },
        "phases": [
            {"id": "P1", "name": "Link arrives", "goal": "g", "demo": "d"},
            {"id": "P2", "name": "Password changes", "goal": "g", "demo": "d"},
        ],
        "tickets": copy.deepcopy(tickets or []),
    }


class Board:
    """A kanban/ folder in tmp_path with a copy of board.py."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.dir = root / "kanban"
        self.dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BOARD_SRC, self.dir / "board.py")
        self.script = self.dir / "board.py"
        self.tickets = self.dir / "tickets.json"
        self.preview = self.dir / "preview.json"

    def run(self, *args: str, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.script), *args],
            capture_output=True, text=True, cwd=str(cwd or self.root), timeout=60,
        )

    def ok(self, *args: str, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        r = self.run(*args, cwd=cwd)
        assert r.returncode == 0, f"{args} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}"
        return r

    def fail(self, *args: str, code: int = 1) -> subprocess.CompletedProcess:
        r = self.run(*args)
        assert r.returncode == code, f"{args} expected exit {code}, got {r.returncode}:\n{r.stdout}\n{r.stderr}"
        return r

    def write(self, doc: Any) -> None:
        self.tickets.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def load(self) -> Dict[str, Any]:
        return json.loads(self.tickets.read_text(encoding="utf-8"))

    def ticket(self, tid: str) -> Dict[str, Any]:
        return next(t for t in self.load()["tickets"] if t["id"] == tid)

    def batch(self, data: Any, name: str = "batch.json") -> str:
        p = self.root / name
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return str(p)


@pytest.fixture
def board(tmp_path: Path) -> Board:
    return Board(tmp_path)


@pytest.fixture
def seeded(board: Board) -> Board:
    """Board with three valid backlog tickets: 002 depends on 001."""
    board.write(base_doc([
        full_ticket(1, unlocks=["ACME-002"]),
        full_ticket(2, depends_on=["ACME-001"]),
        full_ticket(3),
    ]))
    return board
