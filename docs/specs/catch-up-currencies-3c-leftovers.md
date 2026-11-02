# What part 3b's leftovers turned up

What part 3b's leftovers, the live tests' rows made through the shared helpers (done on
2026-11-02), turned up while they ran.

**Status: drafted on 2026-11-02 for the owner to rewrite or approve; no questions.** It waits
on no other spec. When done, the why moves to [decisions.md](../decisions.md) and this file is
deleted.

---

## Why

The live tests make their records through the shared helpers in
[conftest.py](../../tests/contract/conftest.py), but a few still do not:

- Five live files build a new transaction's body by hand:
  [test_freshman_flow.py](../../tests/contract/test_freshman_flow.py) (its end-to-end walk),
  [test_pending_hashtag.py](../../tests/contract/test_pending_hashtag.py),
  [test_refusal_reasons.py](../../tests/contract/test_refusal_reasons.py) (dated at midnight
  UTC), [test_create_sent_again.py](../../tests/contract/test_create_sent_again.py) and
  [test_transaction_currency.py](../../tests/contract/test_transaction_currency.py) (each with
  its own copy of the shared body).
- Two edits in [test_resources_lifecycle.py](../../tests/contract/test_resources_lifecycle.py)
  send a date read in UTC rather than in the display timezone: the frozen-fields edit's
  "yesterday" and the bank-line split's date.
- `_writes_sending` in
  [test_line_codes_and_statement_lines.py](../../tests/contract/test_line_codes_and_statement_lines.py)
  builds an opening balance's body by hand, though `Scratch.opening_balance` makes one.
- `Scratch._item` describes its extra fields as text, though callers pass lists such as
  `hashtag_ids`, so `row_at` adds those after the body is built.
- The opening description of
  [test_contract_month_of_a_recent_row.py](../../tests/unit/test_contract_month_of_a_recent_row.py)
  names only its month's-first-minute case, not its daylight-saving one.

Nothing you see changes. Only the live tests change.

## What it must do

1. **Every live test builds a new transaction's or opening balance's body through the shared
   helpers**, none by hand, a row dated now a minute ago in the display timezone.
2. **The two edits date what they send in the display timezone**, as the new rows are dated.
3. **`Scratch._item` takes every field a caller sends as it is**, lists included, and the unit
   test's description names both its cases.

## How the owner knows it is done

1. The live files this spec touches pass against the practice engine and leave nothing on
   either practice user.
2. The unit suite passes.

## Questions for the owner

None.
