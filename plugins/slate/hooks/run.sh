#!/bin/sh
# Slate hook launcher.  Usage: run.sh <script.py> [args...]
#   (hooks.json: run.sh guard_tickets.py [--post], run.sh session_start.py)
#
# Runs <script.py> (relative to this hooks folder unless absolute) with the first of
# python3, python, "py -3" that is Python 3.9 or newer. stdin and the arguments pass through
# unchanged. If no suitable Python is found it prints one line to stderr and exits 0: a
# missing Python must never block the user's tool calls.
# Uses only shell builtins, so it works with a minimal PATH (Linux, macOS, Git Bash on Windows).

if [ $# -lt 1 ]; then
  echo "slate: run.sh needs a script name; hook skipped" >&2
  exit 0
fi

script=$1
shift

# This script's folder; $0 may use / or (on Windows) \ as separator.
a=${0%/*}; [ "$a" = "$0" ] && a=
b=${0%\\*}; [ "$b" = "$0" ] && b=
if [ ${#a} -ge ${#b} ]; then here=$a; else here=$b; fi
[ -n "$here" ] || here=.
here=$(cd "$here" 2>/dev/null && pwd) || here=.

case $script in
  /* | [A-Za-z]:[\\/]*) ;;
  *) script="$here/$script" ;;
esac

# True when "$@" is a Python >= 3.9. stdin is /dev/null so the hook's JSON input is kept.
slate_py_ok() {
  "$@" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' </dev/null >/dev/null 2>&1
}

# SLATE_PYTHON tells board.py how the user starts Python, for the commands it prints.
if slate_py_ok python3; then
  SLATE_PYTHON=python3; export SLATE_PYTHON
  exec python3 "$script" "$@"
fi
if slate_py_ok python; then
  SLATE_PYTHON=python; export SLATE_PYTHON
  exec python "$script" "$@"
fi
if slate_py_ok py -3; then
  SLATE_PYTHON="py -3"; export SLATE_PYTHON
  exec py -3 "$script" "$@"
fi

echo "slate: no Python 3.9+ found (tried python3, python, py -3); Slate hook skipped" >&2
exit 0
