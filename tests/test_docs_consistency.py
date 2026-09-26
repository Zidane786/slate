"""The docs, skills and templates only name board.py subcommands that exist.

Every `board.py <subcommand>` inside inline code or a fenced code block in the skills, the
command reference, the upgrade steps, the templates and the READMEs must be a subcommand (or
alias) of board.py's argparse parser. Subcommands the reference marks "(pending)" are expected
to be missing for now: those mentions are xfail, not failures. A pending mark on a command that
now exists fails, so the reference gets updated.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
from pathlib import Path
from typing import Dict, List, Set

import pytest

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "slate"
BOARD = PLUGIN / "assets" / "board" / "board.py"
REFERENCE = PLUGIN / "reference" / "commands.md"


def doc_files() -> List[Path]:
    files: List[Path] = []
    files += sorted(PLUGIN.glob("skills/*/SKILL.md"))
    files += [REFERENCE] if REFERENCE.exists() else []
    files += sorted(PLUGIN.glob("upgrades/*.md"))
    files += sorted(PLUGIN.glob("templates/*.md"))
    files += [p for p in (REPO / "README.md", PLUGIN / "README.md", PLUGIN / "assets" / "board" / "README.md")
              if p.exists()]
    return files


def board_subcommands() -> Set[str]:
    spec = importlib.util.spec_from_file_location("slate_board_for_docs_test", BOARD)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # board.py only runs main() under __main__
    parser = mod.build_parser()
    names: Set[str] = set()
    for action in parser._actions:  # noqa: SLF001 - argparse has no public API for this
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            names.update(action.choices.keys())  # includes aliases
    assert names, "board.py build_parser() has no subcommands"
    return names


FENCE = re.compile(r"^\s*(```|~~~)")
INLINE = re.compile(r"`([^`\n]+)`")
# A command, not prose: `kanban/board.py sub`, `python3 board.py sub`, `<python> board.py sub`,
# or a code span / line that starts with `board.py sub`. ("the board and board.py by hand" is prose.)
MENTION = re.compile(
    r"(?:kanban/|\b(?:python3?|py -3)\s+|<[a-z]+>\s+|^\s*)board\.py\s+([a-z][a-z0-9-]*)(?=[\s`]|$)",
    re.M,
)


def code_spans(text: str) -> List[str]:
    """Inline code spans and fenced block lines (where commands are written)."""
    spans: List[str] = []
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            spans.append(line)
        else:
            spans.extend(INLINE.findall(line))
    return spans


def mentions() -> Dict[str, List[str]]:
    """subcommand -> ["file:line", …] for every board.py mention in code."""
    found: Dict[str, List[str]] = {}
    for path in doc_files():
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO).as_posix()
        for span in code_spans(text):
            for m in MENTION.finditer(span):
                found.setdefault(m.group(1), []).append(rel)
    return found


PENDING_HEADING = re.compile(r"^#{2,6}\s+(.*)\(pending\)", re.M)


def pending_commands() -> Set[str]:
    if not REFERENCE.exists():
        return set()
    names: Set[str] = set()
    for m in PENDING_HEADING.finditer(REFERENCE.read_text(encoding="utf-8")):
        names.update(re.findall(r"`([a-z][a-z0-9-]*)`", m.group(1)))
    return names


SUBCOMMANDS = board_subcommands()
MENTIONS = mentions()
PENDING = pending_commands()


def test_docs_mention_board_commands_at_all() -> None:
    assert MENTIONS, "no board.py mentions found: the scanner is broken"
    assert "next" in MENTIONS and "set" in MENTIONS


@pytest.mark.parametrize("sub", sorted(MENTIONS))
def test_mentioned_subcommand_exists(sub: str) -> None:
    where = sorted(set(MENTIONS[sub]))
    if sub not in SUBCOMMANDS and sub in PENDING:
        pytest.xfail(f"`board.py {sub}` is pending (reference/commands.md); mentioned in {where}")
    assert sub in SUBCOMMANDS, (
        f"`board.py {sub}` is not a board.py subcommand but is mentioned in {where}. "
        f"Fix the docs, or mark it '(pending)' in plugins/slate/reference/commands.md."
    )


def test_reference_lists_every_subcommand() -> None:
    text = REFERENCE.read_text(encoding="utf-8")
    listed = {n for line in re.findall(r"^#{2,6}\s+(.*)$", text, re.M)
              for n in re.findall(r"`([a-z][a-z0-9-]*)`", line)}
    missing = sorted(SUBCOMMANDS - listed)
    assert not missing, f"plugins/slate/reference/commands.md has no entry for: {missing}"


def test_pending_marks_are_not_stale() -> None:
    stale = sorted(PENDING & SUBCOMMANDS)
    assert not stale, (
        f"these commands exist in board.py now; remove '(pending)' from their entries in "
        f"plugins/slate/reference/commands.md: {stale}"
    )


FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)


@pytest.mark.parametrize("skill_dir", sorted(p.name for p in (PLUGIN / "skills").iterdir() if p.is_dir()))
def test_skill_dir_has_skill_md_with_matching_name(skill_dir: str) -> None:
    skill = PLUGIN / "skills" / skill_dir / "SKILL.md"
    assert skill.is_file(), f"{skill_dir}/ has no SKILL.md"
    m = FRONTMATTER.match(skill.read_text(encoding="utf-8"))
    assert m, f"{skill_dir}/SKILL.md has no --- frontmatter --- block"
    fields = dict(
        (k.strip(), v.strip().strip('"').strip("'"))
        for k, _, v in (ln.partition(":") for ln in m.group(1).splitlines() if ":" in ln and not ln.startswith(" "))
    )
    assert fields.get("name") == skill_dir, f"{skill_dir}/SKILL.md name is {fields.get('name')!r}"
    assert fields.get("description"), f"{skill_dir}/SKILL.md has no description"


@pytest.mark.parametrize("skill_dir", sorted(p.name for p in (PLUGIN / "skills").iterdir() if p.is_dir()))
def test_skill_links_command_reference(skill_dir: str) -> None:
    text = (PLUGIN / "skills" / skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "<ROOT>/reference/commands.md" in text, (
        f"{skill_dir}/SKILL.md must link the command reference as `<ROOT>/reference/commands.md`"
    )


PY_FORMS = ("Bash(python3 kanban/board.py *)", "Bash(python kanban/board.py *)", "Bash(py -3 kanban/board.py *)")


@pytest.mark.parametrize("skill_dir", sorted(p.name for p in (PLUGIN / "skills").iterdir() if p.is_dir()))
def test_skill_allows_every_python_form(skill_dir: str) -> None:
    m = FRONTMATTER.match((PLUGIN / "skills" / skill_dir / "SKILL.md").read_text(encoding="utf-8"))
    assert m
    allowed = next((ln for ln in m.group(1).splitlines() if ln.startswith("allowed-tools:")), "")
    missing = [f for f in PY_FORMS if f not in allowed]
    assert not missing, f"{skill_dir}/SKILL.md allowed-tools lacks {missing}"


STALE_UNLOCK = re.compile(r"pop-?up|tkinter|osascript|zenity|dialog window", re.I)


def test_no_stale_unlock_wording() -> None:
    stale = [f"{p.relative_to(REPO).as_posix()}:{i}" for p in doc_files()
             for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
             if STALE_UNLOCK.search(line)]
    assert not stale, f"old pop-up unlock wording (the unlock is Claude Code's card or a typed terminal code): {stale}"
