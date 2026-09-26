# Security policy

Please report security problems **privately** through GitHub:
**Security → Report a vulnerability** on https://github.com/Zidane786/slate
(private vulnerability reporting is enabled). Don't open a public issue for security bugs.

Useful areas to look at: the tickets.json guard hook (`plugins/slate/hooks/guard_tickets.py`),
the one-edit unlock flow, and the local board server (`board.py serve`: token check, loopback-only
binding, files served only from `kanban/`).

You'll get an answer as soon as possible; fixes are released as a new plugin version with a
CHANGELOG entry.
