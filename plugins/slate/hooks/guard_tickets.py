#!/usr/bin/env python3
"""Slate guard: block direct edits to kanban/tickets.json (PreToolUse) and activate an approved
unlock (PostToolUse, run with --post).

Claude Code runs this before Edit, Write, MultiEdit, NotebookEdit, Bash and PowerShell. The
hook payload arrives as JSON on stdin. If the target file is a `kanban/tickets.json`
(or, for Bash/PowerShell, the command looks like it writes to one without going through
board.py), the tool call is blocked (exit 2, reason on stderr, which Claude Code shows to
Claude). Anything else, including malformed input, is allowed (exit 0): this
guard must never break an unrelated edit.

GitHub Copilot CLI runs the same hooks.json and sends the same Claude-style input, except: its
edit tool sends apply_patch text ("*** Update File: <path>") instead of {file_path}; it shows an
exit-2 refusal to the model only as "hook exited with code 2"; it sends no permission_mode;
PostToolUse has tool_result instead of tool_response. So under Copilot (COPILOT_CLI set, patch
text, or Copilot's own camelCase toolName/toolArgs input) a refusal is JSON on stdout
(permissionDecision "deny" with the reason, flat and in hookSpecificOutput) with exit 0, and
patch text is checked file by file. Copilot shows the "ask" card in every mode, even Autopilot
with Allow all, so a missing permission_mode means "ask" there too.

Two exceptions and one extra rule:

- While `kanban/.slate-unlock.json` (next to the targeted tickets.json) holds an `until`
  time in the future, ONE direct edit to that tickets.json is allowed: the guard consumes
  the record (renames it to `.slate-unlock.used.json`, adding `used_at` and `tool`) before
  letting the edit through, so the next edit is blocked again. `board.py unlock` writes the
  record; an expired, malformed or already-used record changes nothing.
- A Bash command that runs `board.py unlock` is never run silently. By the hook input's
  permission_mode: default, acceptEdits and auto (or no mode given) -> permissionDecision
  "ask", so Claude Code shows its approval card; that card is the approval. plan -> denied
  (leave plan mode first). bypassPermissions, dontAsk or any other mode -> denied: nobody is
  there to approve, so the user runs `board.py unlock` in their own terminal and types a code.
- Post mode (`guard_tickets.py --post`, PostToolUse on Bash): when the command that just ran
  is exactly `python3|python|py -3 kanban/board.py unlock ...` (no &&, ;, |, &, backticks, $(
  or newlines), the mode allows approval, and kanban/.slate-unlock-request.json is younger
  than 2 minutes, the request becomes the active unlock (approved: "permission prompt",
  with permission_mode) and the request is deleted. Nothing else ever activates an unlock.
- The unlock files (`kanban/.slate-unlock*.json`) and the write lock
  (`kanban/.slate-write.lock`) can't be written directly (only board.py and this guard
  touch them).

Standard library only.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys

MESSAGE = "Change tickets through kanban/board.py (new, add, edit, set, rerank, usertest)."
UNLOCK_FILE = ".slate-unlock.json"
USED_FILE = ".slate-unlock.used.json"
REQUEST_FILE = ".slate-unlock-request.json"
UNLOCK_MESSAGE = ('Use: python3 kanban/board.py unlock --reason "…" --minutes 5 '
                  "(the user will be asked to approve).")
# permission_mode values from the Claude Code hook input (code.claude.com/docs hooks reference).
ASK_MODES = ("default", "acceptEdits", "auto")
PLAN_MESSAGE = "Unlock isn't available in plan mode — leave plan mode first."
NOBODY_MESSAGE = ("Nobody is here to approve an unlock in this mode. Ask the user to run in their own terminal: "
                  'python3 kanban/board.py unlock --reason "…" (they type a code).')
# Post mode: only these exact command starts can activate an unlock (after the approval card).
EXACT_UNLOCK_FORMS = ("python3 kanban/board.py unlock", "python kanban/board.py unlock",
                      "py -3 kanban/board.py unlock")
NOT_IN_EXACT = ("&", ";", "|", "`", "$(", "\n", "\r")
REQUEST_MAX_AGE = _dt.timedelta(minutes=2)
MAX_MINUTES = 30
# An unlock never lasts longer than board.py allows (30 min); a record further out is ignored.
MAX_UNLOCK = _dt.timedelta(minutes=31)

# Keys that name the target file, by tool: Edit/Write/MultiEdit use file_path,
# NotebookEdit uses notebook_path. `path` is accepted defensively.
PATH_KEYS = ("file_path", "notebook_path", "path")

# Bash: a command that mentions tickets.json and has a write-like operation.
# Best effort, deliberately simple: reads (cat, grep, jq, python json.load, git diff/add/commit)
# and version control operations (git checkout/restore/merge/rebase/stash) pass; the next
# board.py call validates the file anyway.
TICKETS_RE = re.compile(r"tickets\.json", re.IGNORECASE)
# Files only board.py and this guard write: every kanban/.slate-unlock*.json and the write lock.
PROTECTED_RE = re.compile(r"\.slate-unlock[\w.-]*\.json|\.slate-write\.lock", re.IGNORECASE)
UNLOCK_FILE_RE = PROTECTED_RE
WRITE_RE = re.compile(
    r"(>|\btee\b|\bsed\s+(-[a-z]*\s+)*-[a-z]*i|\bperl\s+-[a-z]*i|\bcp\b|\bmv\b|\brm\b|"
    r"\btruncate\b|\bdd\b|\binstall\b|\bln\b|write_text|write_bytes|\.write\(|json\.dump|"
    # downloads and sync tools that write a file: curl -o/-O/--output, wget -O/--output-document,
    # rsync, sponge; Python file moves/copies that don't use the words above
    r"\bcurl\b[^|;&]*\s(-[a-z]*[oO](?!-)(?!\s*-(?:\s|$))|--output\b(?!\s*-(?:\s|$)))|\bwget\b[^|;&]*\s(-[a-z]*O(?!-)(?!\s*-(?:\s|$))|--output-document(?!=-))|"
    r"\brsync\b|\bsponge\b|\bshutil\.(copy\w*|move)\(|\bos\.(replace|rename|renames|link|symlink)\(|"
    r"\.(replace|rename|symlink_to|hardlink_to|touch)\(|"
    # PowerShell (Claude Code's PowerShell tool, Copilot CLI on Windows)
    r"\b(set|add|clear)-content\b|\bout-file\b|\b(copy|move|remove|rename|new)-item\b|::(write|append)all\w*\()",
    re.IGNORECASE,
)
# open(...) is a write only with a mode that contains w, a, x or +: open(p, "w"),
# open(p, mode='a'), Path(p).open("w"). Quotes may be backslash-escaped inside bash -c "…".
_Q = r"\\?['\"]"
_MODE = _Q + r"[rbt]*[wax+][rbtwax+]*" + _Q
OPEN_WRITE_RE = re.compile(
    r"(\bopen\(.*?,\s*(mode\s*=\s*)?" + _MODE + r"|\.open\(\s*(mode\s*=\s*)?" + _MODE + r")",
    re.IGNORECASE,
)
BOARD_PY_RE = re.compile(r"^\s*(python3?|uv\s+run\s+python3?)\s+\S*board\.py\b")
# `board.py unlock` anywhere in a command, including inside python3 -c / bash -c / subshells.
# Also the list form subprocess.run([..., 'board.py', 'unlock', '--reason', 'x']).
UNLOCK_CMD_RE = re.compile(r"board\.py[\\'\",\s]+unlock\b", re.IGNORECASE)
_SEP = r"\\?['\"]?(?:\s*,\s*|\s+|=)"
REASON_RE = re.compile(
    r"--reason" + _SEP + r"(?:\\?\"((?:[^\"\\]|\\.)*?)\\?\"|'([^']*)'|([^\s'\"\\]+))", re.IGNORECASE
)
MINUTES_RE = re.compile(r"--minutes" + _SEP + r"\\?['\"]?(\d+)", re.IGNORECASE)


def split_commands(command: str) -> list[str]:
    """Split a shell command at top-level &&, ||, ; and newlines (not inside quotes)."""
    parts: list[str] = []
    cur: list[str] = []
    quote = ""
    i = 0
    n = len(command)
    while i < n:
        ch = command[i]
        if quote:
            cur.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < n:
                cur.append(command[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            cur.append(ch + command[i + 1])
            i += 2
            continue
        if ch in "'\"":
            quote = ch
            cur.append(ch)
            i += 1
            continue
        if command[i:i + 2] in ("&&", "||"):
            parts.append("".join(cur))
            cur = []
            i += 2
            continue
        if ch in ";\n":
            parts.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    parts.append("".join(cur))
    return [p for p in parts if p.strip()]


# A redirect (> file, >> file) and tee name the file they write. When those are the only writes in
# a simple command, the command writes the protected file only if it is one of those targets:
# `printf 'kanban/.slate-unlock*.json\n' >> .gitignore` merely mentions it and writes .gitignore.
_WORD = r"(\"[^\"]*\"|'[^']*'|[^\s;&|<>]+)"
REDIR_RE = re.compile(r"\d?>>?\|?\s*" + _WORD)
TEE_RE = re.compile(r"\btee\b((?:\s+-{1,2}[\w-]+)*)((?:\s+" + _WORD + r")+)")


def _unquote(word: str) -> str:
    return word[1:-1] if len(word) >= 2 and word[0] == word[-1] and word[0] in "\"'" else word


def bash_writes(command: str, target_re: re.Pattern[str] = TICKETS_RE, skip_board_py: bool = True) -> bool:
    """True when a Bash command looks like it writes a file matching target_re directly.
    skip_board_py: a simple command that runs board.py doesn't count (it writes tickets.json itself)."""
    if not target_re.search(command):
        return False
    # Check each simple command separately so `board.py x && cat tickets.json` passes.
    for part in split_commands(command):
        if not target_re.search(part) or (skip_board_py and BOARD_PY_RE.search(part)):
            continue
        # `2>&1` and `>/dev/null` redirections don't write the file.
        cleaned = re.sub(r"\d?>&\d|\d?>\s*/dev/null", "", part)
        targets = [_unquote(m.group(1)) for m in REDIR_RE.finditer(cleaned)]
        for m in TEE_RE.finditer(cleaned):
            targets += [_unquote(w) for w in re.findall(_WORD, m.group(2))]
        rest = TEE_RE.sub(" ", REDIR_RE.sub(" ", cleaned))
        if WRITE_RE.search(rest) or OPEN_WRITE_RE.search(rest):
            return True  # a write that doesn't name its target here (sed -i, cp, python open(.., "w"), ...)
        if any(target_re.search(t) for t in targets):
            return True  # the redirect / tee target is the protected file
    return False


def bash_writes_tickets(command: str) -> bool:
    """True when a Bash command looks like it writes kanban/tickets.json directly."""
    return bash_writes(command, TICKETS_RE)


def unlock_request(command: str) -> tuple[str, str] | None:
    """(minutes, reason) when the command runs `board.py unlock`, else None."""
    if not UNLOCK_CMD_RE.search(command):
        return None
    m = MINUTES_RE.search(command)
    minutes = m.group(1) if m else "5"
    r = REASON_RE.search(command)
    reason = ""
    if r:
        reason = next((g for g in r.groups() if g is not None), "")
        reason = reason.replace('\\"', '"').strip()
    return minutes, (reason or "none given")


def resolve(path: str, cwd: object) -> str:
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        base = cwd if isinstance(cwd, str) and cwd else os.getcwd()
        path = os.path.join(base, path)
    return os.path.normpath(path)


def _parts(path: str, cwd: object) -> list[str]:
    return resolve(path, cwd).replace("\\", "/").split("/")


def is_tickets_file(path: str, cwd: str | None) -> bool:
    """True when path (relative paths resolved against cwd) is .../kanban/tickets.json."""
    parts = _parts(path, cwd)
    # Case-insensitive: macOS and Windows file systems treat Kanban/Tickets.json as the same file.
    return len(parts) >= 2 and parts[-1].lower() == "tickets.json" and parts[-2].lower() == "kanban"


def is_unlock_file(path: str, cwd: str | None) -> bool:
    """True when path is a protected Slate file: .slate-unlock*.json or .slate-write.lock (anywhere;
    case-insensitive)."""
    return PROTECTED_RE.search(_parts(path, cwd)[-1]) is not None  # also their .tmp / .claim-* siblings


def unlock_active(kanban_dir: str, now: _dt.datetime | None = None) -> bool:
    """True while kanban_dir/.slate-unlock.json has an `until` (ISO 8601, UTC) in the future."""
    try:
        with open(os.path.join(kanban_dir, UNLOCK_FILE), encoding="utf-8") as fh:
            rec = json.load(fh)
        until_s = rec.get("until") if isinstance(rec, dict) else None
        if not isinstance(until_s, str) or not until_s.strip():
            return False
        s = until_s.strip()
        if s.endswith(("Z", "z")):
            s = s[:-1] + "+00:00"
        until = _dt.datetime.fromisoformat(s)
        if until.tzinfo is None:
            until = until.replace(tzinfo=_dt.timezone.utc)
        now = now or _dt.datetime.now(_dt.timezone.utc)
        return now < until <= now + MAX_UNLOCK
    except Exception:  # missing, unreadable, malformed: not unlocked
        return False


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def consume_unlock(kanban_dir: str, tool: str) -> bool:
    """Use up an active unlock: rename it to .slate-unlock.used.json (atomic, so two edits
    can't share one unlock), then add used_at and tool. True when this call consumed it."""
    if not unlock_active(kanban_dir):
        return False
    src = os.path.join(kanban_dir, UNLOCK_FILE)
    used = os.path.join(kanban_dir, USED_FILE)
    try:
        os.replace(src, used)
    except OSError:  # someone else consumed it first, or the folder is read-only
        return False
    try:
        with open(used, encoding="utf-8") as fh:
            rec = json.load(fh)
        if not isinstance(rec, dict):
            rec = {}
        rec["used_at"] = _now_iso()
        rec["tool"] = tool
        tmp = used + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, used)
    except Exception:  # the unlock is already used up; the note is best effort
        pass
    return True


def bash_kanban_dirs(command: str, cwd: object) -> list[str]:
    """kanban/ folders a Bash command's tickets.json paths point at, plus <cwd>/kanban."""
    dirs: list[str] = []
    for tok in re.findall(r"[^\s'\"=(),]*tickets\.json", command, re.IGNORECASE):
        parent = os.path.dirname(resolve(tok, cwd))
        if os.path.basename(parent).lower() == "kanban":
            dirs.append(parent)
    base = cwd if isinstance(cwd, str) and cwd else os.getcwd()
    dirs.append(os.path.join(base, "kanban"))
    return list(dict.fromkeys(dirs))


def ask_json(minutes: str, reason: str, copilot: bool) -> str:
    text = (f"Slate: allow ONE direct edit to kanban/tickets.json (within {minutes} minutes)? "
            f"Reason: {reason}")
    if copilot:
        return json.dumps({"permissionDecision": "ask", "permissionDecisionReason": text})
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": text,
    }})


def tool_input_of(payload: dict) -> tuple[object, bool]:
    """(tool_input, copilot_style). Copilot-style hooks send toolName/toolArgs (maybe a JSON string,
    or apply_patch text, which is returned as is)."""
    if "tool_input" in payload or "tool_name" in payload:
        return payload.get("tool_input"), False
    if "toolArgs" in payload or "toolName" in payload:
        args = payload.get("toolArgs")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                pass
        return args, True
    return None, False


# Copilot CLI's edit tool sends apply_patch text; each file it touches has one of these headers.
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Update File|Add File|Delete File|Move to):[ \t]*(.+?)[ \t]*\r?$", re.MULTILINE)


def patch_paths(text: str) -> list[str]:
    """Every file an apply_patch text adds, updates, deletes or moves to."""
    return [p for p in PATCH_FILE_RE.findall(text) if p]


def on_copilot() -> bool:
    """True when Copilot CLI runs this hook (it sets COPILOT_CLI=1 for hooks)."""
    return bool(os.environ.get("COPILOT_CLI"))


def refuse(message: str, copilot: bool) -> int:
    """Block the tool call with an actionable reason. Claude Code: exit 2, reason on stderr.
    Copilot CLI: exit 0 and a JSON deny on stdout (it hides an exit-2 hook's stderr from the model)."""
    if copilot:
        print(json.dumps({"permissionDecision": "deny", "permissionDecisionReason": message,
                          "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": message}}))
        return 0
    print(message, file=sys.stderr)
    return 2


def unlock_gate(payload: dict) -> str:
    """"ask", "plan" or "nobody", from the hook input's permission_mode (missing: old Claude Code -> ask)."""
    if "permission_mode" not in payload:
        return "ask"
    mode = payload.get("permission_mode")
    if mode in ASK_MODES:
        return "ask"
    return "plan" if mode == "plan" else "nobody"


def exact_unlock_command(command: str) -> bool:
    """The plain `board.py unlock` command, nothing wrapped around or chained to it."""
    c = command.strip()
    if any(x in c for x in NOT_IN_EXACT):
        return False
    return any(c == f or c.startswith(f + " ") for f in EXACT_UNLOCK_FORMS)


def _parse_time(s: object) -> _dt.datetime | None:
    if not isinstance(s, str) or not s.strip():
        return None
    s = s.strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    try:
        t = _dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)


def _iso(t: _dt.datetime) -> str:
    return t.astimezone(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def activate_request(kanban_dir: str, permission_mode: object, now: _dt.datetime | None = None) -> dict | None:
    """Turn a fresh unlock request into the active unlock. The request is claimed with an atomic
    rename first, so one request activates at most once. Returns the active record, or None."""
    req = os.path.join(kanban_dir, REQUEST_FILE)
    claim = f"{req}.claim-{os.getpid()}"
    try:
        os.replace(req, claim)
    except OSError:
        return None
    try:
        with open(claim, encoding="utf-8") as fh:
            rec = json.load(fh)
        if not isinstance(rec, dict):
            return None
        now = now or _dt.datetime.now(_dt.timezone.utc)
        created = _parse_time(rec.get("created"))
        if created is None or not (now - REQUEST_MAX_AGE <= created <= now + _dt.timedelta(seconds=5)):
            return None  # stale (or from the future): never activates
        minutes = rec.get("minutes")
        if not isinstance(minutes, int) or isinstance(minutes, bool) or not 1 <= minutes <= MAX_MINUTES:
            return None
        active = {"until": _iso(now + _dt.timedelta(minutes=minutes)), "reason": str(rec.get("reason", "")),
                  "minutes": minutes, "created": rec.get("created"), "activated": _iso(now),
                  "approved": "permission prompt", "request_id": rec.get("id")}
        if isinstance(permission_mode, str):
            active["permission_mode"] = permission_mode
        tmp = os.path.join(kanban_dir, f"{UNLOCK_FILE}.{os.getpid()}.tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(active, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, os.path.join(kanban_dir, UNLOCK_FILE))
        return active
    except Exception:
        return None
    finally:
        try:
            os.unlink(claim)
        except OSError:
            pass


def main_post(stdin_text: str) -> int:
    """PostToolUse: activate an unlock request after the approval card said yes. Always exit 0."""
    try:
        payload = json.loads(stdin_text)
        if not isinstance(payload, dict) or payload.get("tool_name") not in ("Bash", "PowerShell"):
            return 0
        if unlock_gate(payload) != "ask":
            return 0
        tool_input = payload.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not isinstance(command, str) or not exact_unlock_command(command):
            return 0
        cwd = payload.get("cwd")
        base = cwd if isinstance(cwd, str) and cwd else os.getcwd()
        active = activate_request(os.path.join(base, "kanban"), payload.get("permission_mode"))
        if active:
            note = ("Slate: unlock approved. ONE direct edit of kanban/tickets.json is allowed "
                    f"until {active['until']}; the next edit after that one is blocked again.")
            out: dict = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": note}}
            if on_copilot() or "tool_result" in payload:
                out = {"additionalContext": note, **out}  # Copilot CLI reads the flat field
            print(json.dumps(out))
    except Exception:
        return 0
    return 0


def main(stdin_text: str) -> int:
    try:
        payload = json.loads(stdin_text)
    except (ValueError, TypeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    cwd = payload.get("cwd")
    tool = payload.get("tool_name") or payload.get("toolName") or ""
    tool = tool if isinstance(tool, str) else ""
    try:
        tool_input, camel = tool_input_of(payload)
        # Only Copilot CLI sends patch text, so that input is answered in Copilot's dialect too.
        copilot = camel or isinstance(tool_input, str) or on_copilot()
        if isinstance(tool_input, str):
            paths = patch_paths(tool_input)
        elif isinstance(tool_input, dict):
            command = tool_input.get("command")
            if isinstance(command, str):
                if bash_writes(command, PROTECTED_RE, skip_board_py=False):
                    return refuse(UNLOCK_MESSAGE, copilot)
                if bash_writes_tickets(command) and not any(
                        consume_unlock(d, tool or "Bash") for d in bash_kanban_dirs(command, cwd)):
                    return refuse(MESSAGE + " Reading it (cat, grep, jq, git add/commit) is fine.", copilot)
                req = unlock_request(command)
                if req:
                    gate = unlock_gate(payload)
                    if gate == "plan":
                        return refuse(PLAN_MESSAGE, copilot)
                    if gate == "nobody":
                        return refuse(NOBODY_MESSAGE, copilot)
                    print(ask_json(req[0], req[1], camel))
                return 0
            paths = [v for k in PATH_KEYS if isinstance(v := tool_input.get(k), str) and v]
        else:
            return 0
        for path in paths:
            if is_unlock_file(path, cwd):
                return refuse(UNLOCK_MESSAGE, copilot)
            if is_tickets_file(path, cwd) and not consume_unlock(
                    os.path.dirname(resolve(path, cwd)), tool or "Edit"):
                return refuse(MESSAGE, copilot)
    except Exception:  # never crash on odd input
        return 0
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):  # Windows consoles/pipes default to cp1252; hooks speak UTF-8
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass
    try:
        data = sys.stdin.buffer.read().decode("utf-8", "replace")
    except Exception:
        sys.exit(0)
    sys.exit(main_post(data) if "--post" in sys.argv[1:] else main(data))
