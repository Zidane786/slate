#!/usr/bin/env python3
"""Assemble an OpenCode V2 plugin folder from an installed Slate plugin.

This is the stand-alone path for people who only use OpenCode: clone or download a Slate release,
point --root at its plugins/slate folder, and this script writes the same folder /slate:init copies.
Standard library only, Python 3.9+, works on Windows/macOS/Linux.

usage: python3 scripts/assemble_opencode.py --root <path/to/plugins/slate> [--project <dir> | --global]
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

SHARED_DIRS = ("skills", "assets", "templates", "reference", "upgrades")
SHARED_FILES = (
    "hooks/guard_tickets.py",
    ".claude-plugin/plugin.json",
    "CHANGELOG.md",
)


def out(message: str) -> None:
    stream = sys.stdout
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    print(message)


def fail(message: str) -> None:
    stream = sys.stderr
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    print(message, file=stream)
    raise SystemExit(1)


def assemble(root: Path, target: Path, commands: Path) -> None:
    index = root / "opencode" / "index.js"
    if not index.is_file():
        fail(f"error: OpenCode files missing: {index}\n"
             "fix: use a 0.5.0+ release (plugins/slate/opencode/index.js must exist), or run the "
             "steps from the repository checkout")

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in SHARED_DIRS:
        shutil.copytree(root / name, target / name)
    for rel in SHARED_FILES:
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, destination)
    # index.js, package.json and the command stubs; stubs are also copied to commands/ below.
    shutil.copytree(root / "opencode", target, dirs_exist_ok=True)

    commands.mkdir(parents=True, exist_ok=True)
    for stub in (root / "opencode" / "commands").glob("slate-*.md"):
        shutil.copy2(stub, commands / stub.name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path,
                        help="installed Slate plugin folder (path containing opencode/index.js)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--project", type=Path, default=Path.cwd(),
                       help="project directory (default: current directory)")
    group.add_argument("--global", action="store_true", dest="global_install",
                       help="install for every project under $XDG_CONFIG_HOME/opencode or ~/.config/opencode")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()

    if args.global_install:
        config = os.environ.get("XDG_CONFIG_HOME")
        base = Path(config).expanduser() if config else Path.home() / ".config"
        base = base / "opencode"
    else:
        base = args.project.expanduser().resolve() / ".opencode"

    target = base / "plugins" / "slate"
    assemble(root, target, base / "commands")
    out(f"Slate OpenCode plugin assembled at {target}")
    out("Restart OpenCode (or its background service) so it loads the new plugin.")


if __name__ == "__main__":
    main()
