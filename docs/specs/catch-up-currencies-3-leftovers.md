# What the live tests' foundation turned up

One small thing that part 3 of the catch-up to contract `f82426fb0a099676`, the live tests'
foundation (done on 2026-10-30), turned up while it ran.

**Status: approved by the owner on 2026-10-30; no question. The current spec since 2026-11-02;
its tasks approved by the owner on 2026-11-02.** It runs after
part 4 of the currencies catch-up, the live tests for the upload, bank lines and kinds (done on 2026-10-31),
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

Drafted 2026-11-02. Each needs the practice engine, which the orchestrator starts before the
task and stops after it.

None left.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- Four more live files build a transaction dated now by hand, in UTC rather than a minute ago in
  the display timezone, instead of `Scratch.recent_row`: test_log_lifecycle.py,
  test_category_hashtags.py, test_transactions_lifecycle.py and test_resources_lifecycle.py
  (each with its own `datetime.now(UTC)` helper or body).
- `_tagged_row` in test_reserved_name_held.py builds by hand a plain row with a category and a
  hashtag on its fixed past day, which `Scratch.row` already makes.
- Two more places build a transaction body by hand that `Scratch` already builds: `_body` in
  test_line_codes_and_statement_lines.py and the inline batch items in test_bank_lines.py's
  batch tests.
- `Scratch._item`'s docstring calls its result a batch item, though `refused_row` also sends it
  alone to `POST /transactions`.
- `minute_before` in tests/contract/conftest.py turns to the display zone before it takes the
  minute off, so in the first minute after a daylight-saving jump it gives a time that does not
  exist, read as an hour ahead (`FUTURE_DATE`); taking the minute off first avoids it. Lima has
  no daylight saving.
