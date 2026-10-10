@echo off
rem Slate hook launcher for Windows (GitHub Copilot CLI runs hooks through PowerShell there).
rem   hooks.json: powershell -> run.cmd guard_tickets.py [--post], run.cmd session_start.py
rem Same job as run.sh: runs <script.py> from this hooks folder with the first of py -3, python,
rem python3 that is Python 3.9 or newer; stdin and the arguments pass through unchanged. If no
rem suitable Python is found it prints one line to stderr and exits 0: a missing Python must never
rem block the user's tool calls. The version probes read nul so the hook's JSON input is kept.
rem Keep CRLF line endings (cmd.exe needs them for labels; .gitattributes pins it).
setlocal
if "%~1"=="" (
  echo slate: run.cmd needs a script name; hook skipped 1>&2
  exit /b 0
)
set "SLATE_SCRIPT=%~dp0%~1"
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" <nul >nul 2>&1 && goto py3
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" <nul >nul 2>&1 && goto python
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" <nul >nul 2>&1 && goto python3
echo slate: no Python 3.9+ found (tried py -3, python, python3); Slate hook skipped 1>&2
exit /b 0

:py3
rem SLATE_PYTHON tells board.py how the user starts Python, for the commands it prints.
set "SLATE_PYTHON=py -3"
py -3 "%SLATE_SCRIPT%" %2 %3 %4
exit /b %ERRORLEVEL%

:python
set "SLATE_PYTHON=python"
python "%SLATE_SCRIPT%" %2 %3 %4
exit /b %ERRORLEVEL%

:python3
set "SLATE_PYTHON=python3"
python3 "%SLATE_SCRIPT%" %2 %3 %4
exit /b %ERRORLEVEL%
