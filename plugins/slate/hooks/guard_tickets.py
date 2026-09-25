#!/usr/bin/env python3
"""Slate PreToolUse guard: block direct edits to kanban/tickets.json.

Claude Code runs this before Edit, Write, MultiEdit, NotebookEdit and Bash. The
hook payload arrives as JSON on stdin. If the target file is a `kanban/tickets.json`
(or, for Bash, the command looks like it writes to one without going through
board.py), the tool call is blocked (exit 2, reason on stderr, which Claude Code shows to
Claude). Anything else, including malformed input, is allowed (exit 0): this
guard must never break an unrelated edit.

Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import sys

MESSAGE = "Change tickets through kanban/board.py (new, add, edit, set, rerank, usertest)."

# Keys that name the target file, by tool: Edit/Write/MultiEdit use file_path,
# NotebookEdit uses notebook_path. `path` is accepted defensively.
PATH_KEYS = ("file_path", "notebook_path", "path")

# Bash: a command that mentions tickets.json and has a write-like operation.
# Best effort, deliberately simple: reads (cat, grep, jq, git diff/add/commit) pass.
TICKETS_RE = re.compile(r"tickets\.json", re.IGNORECASE)
WRITE_RE = re.compile(
    r"(>|\btee\b|\bsed\s+(-[a-z]*\s+)*-[a-z]*i|\bperl\s+-[a-z]*i|\bcp\b|\bmv\b|\brm\b|"
    r"\btruncate\b|\bdd\b|\binstall\b|\bln\b|open\(|write_text|\.write\(|json\.dump|"
    r"\bgit\s+(checkout|restore)\b)",
    re.IGNORECASE,
)
BOARD_PY_RE = re.compile(r"^\s*(python3?|uv\s+run\s+python3?)\s+\S*board\.py\b")


def bash_writes_tickets(command: str) -> bool:
    """True when a Bash command looks like it writes kanban/tickets.json directly."""
    if not TICKETS_RE.search(command):
        return False
    # Check each simple command separately so `board.py x && cat tickets.json` passes.
    for part in re.split(r"&&|\|\||;|\n", command):
        if not TICKETS_RE.search(part) or BOARD_PY_RE.search(part):
            continue
        # `2>&1` and `>/dev/null` redirections don't write the tickets file.
        cleaned = re.sub(r"\d?>&\d|\d?>\s*/dev/null", "", part)
        if WRITE_RE.search(cleaned):
            return True
    return False


def target_paths(payload: object) -> list[str]:
    """Return every candidate path string in the hook payload's tool_input."""
    if not isinstance(payload, dict):
        return []
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    return [v for k in PATH_KEYS if isinstance(v := tool_input.get(k), str) and v]


def is_tickets_file(path: str, cwd: str | None) -> bool:
    """True when path (relative paths resolved against cwd) is .../kanban/tickets.json."""
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        base = cwd if isinstance(cwd, str) and cwd else os.getcwd()
        path = os.path.join(base, path)
    norm = os.path.normpath(path)
    parts = norm.replace("\\", "/").split("/")
    # Case-insensitive: macOS and Windows file systems treat Kanban/Tickets.json as the same file.
    return len(parts) >= 2 and parts[-1].lower() == "tickets.json" and parts[-2].lower() == "kanban"


def main(stdin_text: str) -> int:
    try:
        payload = json.loads(stdin_text)
    except (ValueError, TypeError):
        return 0
    cwd = payload.get("cwd") if isinstance(payload, dict) else None
    try:
        tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
        if isinstance(tool_input, dict) and isinstance(tool_input.get("command"), str):
            if bash_writes_tickets(tool_input["command"]):
                print(MESSAGE + " Reading it (cat, grep, jq, git add/commit) is fine.", file=sys.stderr)
                return 2
            return 0
        for path in target_paths(payload):
            if is_tickets_file(path, cwd):
                print(MESSAGE, file=sys.stderr)
                return 2
    except Exception:  # never crash on odd input
        return 0
    return 0


if __name__ == "__main__":
    try:
        data = sys.stdin.read()
    except Exception:
        sys.exit(0)
    sys.exit(main(data))
