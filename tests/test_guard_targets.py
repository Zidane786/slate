"""The guard checks what a shell command WRITES, not every file it mentions.

Found live: writing the .gitignore lines /slate:init adds (which mention the unlock files) was
blocked because the command contained both a protected file name and a `>`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from test_guard import payload, run_guard


@pytest.mark.parametrize(
    "command",
    [
        "printf 'kanban/.slate-unlock*.json\\nkanban/.slate-write.lock\\n' >> .gitignore",
        "echo 'kanban/.slate-serve.json' >> .gitignore",
        "echo 'kanban/tickets.json merge=slate text eol=lf' >> .gitattributes",
        "grep -n tickets.json README.md > notes.txt",
        "echo 'kanban/tickets.json' | tee -a .gitignore",
    ],
)
def test_mentioning_a_protected_file_while_writing_another_is_allowed(command: str, tmp_path: Path) -> None:
    result = run_guard(payload("Bash", {"command": command}), cwd=tmp_path)
    assert result.returncode == 0, (command, result.stderr)


@pytest.mark.parametrize(
    "command",
    [
        "printf '{}' > kanban/tickets.json",
        "echo '{}' >> 'kanban/tickets.json'",
        "echo x > kanban/.slate-unlock.json",
        "cat x | tee kanban/tickets.json",
        "printf 'x' > .gitignore && sed -i '' 's/a/b/' kanban/tickets.json",
        "python3 -c \"open('kanban/tickets.json','w').write('{}')\" > out.txt",
    ],
)
def test_writing_the_protected_file_itself_is_still_blocked(command: str, tmp_path: Path) -> None:
    result = run_guard(payload("Bash", {"command": command}), cwd=tmp_path)
    assert result.returncode == 2, command
