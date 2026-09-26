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

FOOTER = """
---

### Install / update

```
/plugin marketplace add Zidane786/slate      # first time
/plugin install slate@slate
/plugin marketplace update slate             # later updates, then restart Claude Code
```

Then run `/slate:init` in a new project, or `/slate:upgrade` in an existing one.
"""


def plugin_version() -> str:
    return json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))["version"]


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
    print(section(version) + "\n" + FOOTER)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
