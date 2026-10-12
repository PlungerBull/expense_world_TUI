# The engine runs on Python 3.12

Shipped 2026-10-11 · ➕ additive · contract `8d2430081e64cd7c` (unchanged)

Answers the CLI's ask "The practice engine starts again, on the Python version its code needs" (raised 2026-09-30).

## What changed

The engine's environment is built on Python 3.12, and the engine declares 3.12 as the minimum it runs on. Its code uses 3.12 syntax, so it no longer starts on an older Python. No route, field, status or error changed: the contract version is the same before and after.

## What the CLI does

Start the practice engine with the engine checkout's own `.venv/bin/python`, exactly as the header of the engine's `deploy/local/seed-test-user.sh` shows. Never start it with the CLI's Python or the system `python3`. Drop any workaround or note that says the practice engine cannot start, or that names Python 3.9.

## Done when

The CLI's contract suite runs against a practice engine started that way, and no CLI doc names an older engine Python.
