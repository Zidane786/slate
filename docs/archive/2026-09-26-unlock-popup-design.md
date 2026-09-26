# Archived: desktop pop-up approval for `board.py unlock`

Status: **not used** (archived 2026-09-26). Kept for future reference.

## Why it was dropped

The idea: `board.py unlock` opens a small window on the user's desktop showing a random code,
and approves only when the person types it. The agent never sees the code and can't click the
window, so an agent can't approve itself.

It was replaced because it fails the "works in every setup" rule:

- **SSH / remote / containers:** the window would open on the remote machine (no screen) or fail.
- **Per-OS work:** tkinter may be missing (e.g. some Homebrew Pythons), macOS needs `osascript`,
  Linux needs `zenity`/`kdialog` and a display.

The chosen design (see `docs/plans/2026-09-26-v0.2-build-plan.md`, item 21): approval on the
agent tool's own permission card (hook "ask" + PostToolUse activation), or a typed code in any
real terminal (works over SSH). One unlock = one edit.

## When it might come back

- A desktop-only mode for tools without hooks and users who don't want to open a terminal.
- As an optional extra layer (`SLATE_UNLOCK_POPUP=1`) on machines with a display.

## Design as it was

```
┌─ Slate: unlock the board? ─────────────────────────┐
│ Claude wants to edit kanban/tickets.json directly. │
│ Reason: fix broken phase field after bad merge     │
│ Allows ONE edit, within 5 minutes.                 │
│                                                    │
│ Type this code to approve:  KXQ7                   │
│ [ ____ ]                     [Cancel]  [Approve]   │
└────────────────────────────────────────────────────┘
```

Order tried: tkinter → macOS `osascript` → Linux `zenity` → `kdialog` → none (fall back to the
terminal prompt, else refuse). Code never printed to stdout/stderr. 120 s timeout.

## Reference implementation (untested sketch, stdlib only)

```python
import os, secrets, shutil, string, subprocess, sys

def _code(n: int = 4) -> str:
    alphabet = "".join(c for c in string.ascii_uppercase + string.digits if c not in "O0I1")
    return "".join(secrets.choice(alphabet) for _ in range(n))

def ask_popup(reason: str, minutes: int, timeout: int = 120) -> "bool | None":
    """True = approved, False = refused/wrong code, None = no pop-up method available."""
    code = _code()
    text = (f"Claude wants to edit kanban/tickets.json directly.\n\nReason: {reason}\n"
            f"Allows ONE edit, within {minutes} minutes.\n\nType this code to approve: {code}")

    # 1. tkinter (Windows, most macOS/Linux desktops)
    try:
        import tkinter
        from tkinter import simpledialog
        if os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"):
            root = tkinter.Tk(); root.withdraw(); root.attributes("-topmost", True)
            root.after(timeout * 1000, root.destroy)
            typed = simpledialog.askstring("Slate: unlock the board?", text, parent=root)
            try: root.destroy()
            except Exception: pass
            return (typed or "").strip().upper() == code
    except Exception:
        pass

    # 2. macOS dialog
    if sys.platform == "darwin" and shutil.which("osascript"):
        script = ('display dialog "{}" default answer "" with title "Slate: unlock the board?" '
                  'buttons {{"Cancel", "Approve"}} default button "Approve" giving up after {}'
                  ).format(text.replace('"', "'"), timeout)
        r = subprocess.run(["osascript", "-e", script, "-e", "text returned of result"],
                           capture_output=True, text=True, encoding="utf-8")
        return r.returncode == 0 and r.stdout.strip().upper() == code

    # 3. Linux desktop dialogs
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        for cmd in (["zenity", "--entry", "--title=Slate: unlock the board?", f"--text={text}",
                     f"--timeout={timeout}"],
                    ["kdialog", "--title", "Slate: unlock the board?", "--inputbox", text]):
            if shutil.which(cmd[0]):
                r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
                return r.returncode == 0 and r.stdout.strip().upper() == code

    return None  # no pop-up possible: caller falls back to the terminal prompt or refuses
```
