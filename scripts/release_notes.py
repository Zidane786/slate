#!/usr/bin/env python3
"""Print the GitHub Release notes for a Slate version, taken from plugins/slate/CHANGELOG.md.

usage: python3 scripts/release_notes.py [VERSION]     (default: the version in plugin.json)
       python3 scripts/release_notes.py --version     (print the plugin.json version only)

Exit 1 when the CHANGELOG has no "## VERSION — date" section. Standard library only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_JSON = ROOT / "plugins" / "slate" / ".claude-plugin" / "plugin.json"
CHANGELOG = ROOT / "plugins" / "slate" / "CHANGELOG.md"

INSTALL = """### Install (new project)

In a terminal:

```
claude plugin marketplace add Zidane786/slate
claude plugin install slate@slate
```

(or inside Claude Code: `/plugin marketplace add Zidane786/slate`, then
`/plugin install slate@slate`). Restart Claude Code, then run `/slate:init` in the project.
"""

UPGRADE_HEAD = """### Upgrade (existing projects)

1. Update the plugin, in a terminal:

   ```
   claude plugin marketplace update slate
   claude plugin update slate@slate
   ```

   (or inside Claude Code: `/plugin marketplace update slate`).
2. Restart Claude Code.
3. In each project, run `/slate:upgrade`.
"""


def plugin_version() -> str:
    return json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))["version"]


def split_upgrade(body: str) -> "tuple[str, str]":
    """Take the '### Upgrade notes' section out of a version's body: (rest, upgrade notes)."""
    m = re.search(r"^### Upgrade notes\s*$\n(.*?)(?=^### |\Z)", body, re.S | re.M)
    if not m:
        return body.strip(), ""
    return (body[:m.start()] + body[m.end():]).strip(), m.group(1).strip()


def notes(version: str) -> str:
    """Release notes: Install and Upgrade first (with this version's upgrade notes), then the rest."""
    rest, upgrade = split_upgrade(section(version))
    intro, _, sections = rest.partition("### ")
    parts = [intro.strip()] if intro.strip() else []
    parts.append(INSTALL.strip())
    parts.append(UPGRADE_HEAD.strip() + ("\n\n**What `/slate:upgrade` does for " + version + ":**\n\n"
                                          + upgrade if upgrade else ""))
    parts.append("---")
    if sections:
        parts.append("### " + sections.strip())
    return "\n\n".join(parts) + "\n"


def section(version: str) -> str:
    text = CHANGELOG.read_text(encoding="utf-8")
    m = re.search(r"^## " + re.escape(version) + r"(?:\s|$).*?$\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        raise SystemExit(f"error: {CHANGELOG.relative_to(ROOT)} has no '## {version} — date' section\n"
                         f"  fix: add one (Highlights / Added / Changed / Fixed / Security / Removed / Upgrade notes)")
    return m.group(1).strip()


def main(argv: list) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    if argv[:1] == ["--version"]:
        print(plugin_version())
        return 0
    version = argv[0] if argv else plugin_version()
    print(notes(version), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
