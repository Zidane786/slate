#!/usr/bin/env python3
"""Slate SessionStart hook: print the one-line board status.

Run through hooks/run.sh (which picks python3, python or py -3). Finds the project folder
(CLAUDE_PROJECT_DIR, else the current directory), and when it has kanban/board.py runs
`board.py next --brief --against <plugin root>` with this same interpreter, passing its output
through. The line includes doctor's findings and the board page URL when a server is running.
Never fails the session: any problem means no output and exit 0. Standard library only.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    board = project / "kanban" / "board.py"
    if not board.is_file():
        return 0
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT") or str(Path(__file__).resolve().parent.parent)
    try:
        r = subprocess.run([sys.executable, str(board), "next", "--brief", "--against", plugin_root],
                           cwd=str(project), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=9, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return 0
    out = r.stdout.strip()
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):  # Windows consoles/pipes default to cp1252; hooks speak UTF-8
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass
    try:
        sys.exit(main())
    except Exception:  # a status line must never break the session
        sys.exit(0)
