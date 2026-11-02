# What part 3's leftovers turned up

What part 3's leftovers, one helper for a plain transaction dated a minute ago (done on
2026-11-02), turned up while they ran.

**Status: drafted on 2026-11-02; no questions. The current spec since 2026-11-02, the owner
naming it; its tasks approved by the owner on 2026-11-02.** It waits on no other spec. When
done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

The live tests make their records through the shared helpers in
[conftest.py](../../tests/contract/conftest.py), but a few still build a transaction by hand:

- Four live files date a transaction now in UTC with their own helper or body, instead of a
  minute ago in the display timezone through `Scratch.recent_row`:
  [test_log_lifecycle.py](../../tests/contract/test_log_lifecycle.py),
  [test_category_hashtags.py](../../tests/contract/test_category_hashtags.py),
  [test_transactions_lifecycle.py](../../tests/contract/test_transactions_lifecycle.py) and
  [test_resources_lifecycle.py](../../tests/contract/test_resources_lifecycle.py).
- Three places build by hand a body `Scratch` already builds: `_tagged_row` in
  [test_reserved_name_held.py](../../tests/contract/test_reserved_name_held.py), `_body` in
  [test_line_codes_and_statement_lines.py](../../tests/contract/test_line_codes_and_statement_lines.py)
  and the batch items in [test_bank_lines.py](../../tests/contract/test_bank_lines.py)'s batch
  tests.
- `minute_before` in conftest.py turns to the display timezone before it takes the minute off.
  In the first minute after a daylight-saving jump that gives a time that does not exist, which
  the engine reads as an hour ahead and refuses (`FUTURE_DATE`). Lima has no daylight saving,
  so the owner's runs never hit it.
- `Scratch._item`'s description calls its result a batch item, though `refused_row` also sends
  it alone, and the opening description of
  [test_reports_and_dashboard.py](../../tests/contract/test_reports_and_dashboard.py) names a
  count of unit tests that no longer holds.

Nothing you see changes. Only the live tests change.

## What it must do

1. **Every live test makes a plain transaction through the shared helpers**, none by hand, a
   row dated now a minute ago in the display timezone.
2. **A row dated a minute ago is never in the future**, whatever the timezone's daylight saving.
3. **The two descriptions say what holds**: `Scratch._item`'s, and the reports' tests' without a
   count that drifts.

## How the owner knows it is done

1. The live files this spec touches pass against the practice engine and leave nothing on
   either practice user.
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

- `Scratch._item` types its extra fields as text, though callers pass lists such as
  `hashtag_ids`; `row_at` adds those after the item is built to get past it.
- Two edits in test_resources_lifecycle.py send a date read in UTC (the frozen-fields edit's
  "yesterday" and the bank-line split's date); they are edits, not new rows, so this spec leaves
  them.
- Five more live files build a new transaction's body by hand instead of through `Scratch`:
  test_freshman_flow.py (its end-to-end walk), test_pending_hashtag.py,
  test_refusal_reasons.py (dated at midnight UTC), test_create_sent_again.py and
  test_transaction_currency.py (each with its own copy of `Scratch._item`).
