# What the live tests' foundation turned up

One small thing that part 3 of the catch-up to contract `f82426fb0a099676`, the live tests'
foundation (done on 2026-10-30), turned up while it ran.

**Status: draft, written 2026-10-30 for the owner to rewrite or approve; no question.** Its tasks
are drafted when the owner approves it. It runs after
[catch-up-currencies-4-live-suite-upload-lines-kinds.md](catch-up-currencies-4-live-suite-upload-lines-kinds.md),
which rewrites [test_reserved_name_held.py](../../tests/contract/test_reserved_name_held.py). When
done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

The live tests make every record through the shared helpers in
[conftest.py](../../tests/contract/conftest.py), but there is no helper for one plain
transaction dated now:

- `Scratch.line` takes no category.
- `Scratch.line` and `Scratch.row` both date the row at noon, which is in the future before noon
  today, so the engine refuses it (`FUTURE_DATE`).
- [test_reports_and_dashboard.py](../../tests/contract/test_reports_and_dashboard.py) builds its
  own body for this (`_spend`), and so does
  [test_reserved_name_held.py](../../tests/contract/test_reserved_name_held.py).
- `_post_row` in [test_transactions_cursor.py](../../tests/contract/test_transactions_cursor.py)
  passes a day that its own date then overrides.
- The reports' tests date their rows a minute ago and read the current month. Run in the first
  minute of a month (in the display timezone), the row lands in the old month while the report
  reads the new one, and the tests fail.

Nothing you see changes. Only the live tests change.

## What it must do

1. **One shared helper logs a plain transaction dated a minute ago**, taking a category and the
   other fields a test needs, and both hand-built bodies use it.
2. **The cursor test's helper** passes no day it does not use.
3. **The reports' tests pass in a month's first minute** as on any other minute.

## How the owner knows it is done

1. The live files this spec touches pass against the practice engine and leave nothing on the
   practice user.
2. The unit suite passes.

## Questions for the owner

None.

---

## Tasks

Drafted when the owner approves this spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
