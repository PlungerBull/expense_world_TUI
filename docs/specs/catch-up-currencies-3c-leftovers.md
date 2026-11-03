# What part 3b's leftovers turned up

What part 3b's leftovers, the live tests' rows made through the shared helpers (done on
2026-11-02), turned up while they ran.

**Status: drafted on 2026-11-02; no questions. Approved by the owner on 2026-11-02; its tasks
drafted for the owner's approval.** It waits on no other spec. When done, the why moves to [decisions.md](../decisions.md) and this file is
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

---

## Tasks

Drafted 2026-11-02. Each needs the practice engine, which the orchestrator starts before the
task and stops after it.

1. **`Scratch._item` takes every field as it is, and the unit test names both its cases
   (builder).** `Scratch._item` in [conftest.py](../../tests/contract/conftest.py) types its
   extra fields as any value a caller sends, lists such as `hashtag_ids` included, and puts
   them in the body itself, so `row_at` no longer adds them after the body is built; the
   opening description of
   [test_contract_month_of_a_recent_row.py](../../tests/unit/test_contract_month_of_a_recent_row.py)
   names its month's-first-minute case and its daylight-saving case.
   *Passes if:* no `Scratch` helper adds a field to a body `_item` built; mypy and ruff are
   clean on the touched files; the live files that call `row_at` with a list pass live and leave
   nothing; the unit test passes and its description names both cases.
2. **Three live files build a new transaction through the shared helpers (builder).**
   [test_freshman_flow.py](../../tests/contract/test_freshman_flow.py),
   [test_pending_hashtag.py](../../tests/contract/test_pending_hashtag.py) and
   [test_refusal_reasons.py](../../tests/contract/test_refusal_reasons.py) build each new
   transaction's body with the `Scratch` helpers, dated now a minute ago in the display
   timezone, keeping the route and the refusal each test proves.
   *Passes if:* none of the three builds a transaction body by hand or dates a row at midnight
   UTC; the three pass live twice and leave nothing.
3. **Two live files drop their copies of the shared body (builder).**
   [test_create_sent_again.py](../../tests/contract/test_create_sent_again.py) and
   [test_transaction_currency.py](../../tests/contract/test_transaction_currency.py) build each
   new transaction's body with the `Scratch` helpers instead of their own copy, keeping the
   route each test proves (`POST /transactions` alone or in a batch, a create sent again with
   the same key).
   *Passes if:* neither file holds its own body builder; no live file builds a transaction body
   by hand (the grep in the report); both pass live twice and leave nothing.
4. **The two edits date in the display timezone, and the opening balance goes through
   `Scratch` (builder).** The frozen-fields edit's "yesterday" and the bank-line split's date in
   [test_resources_lifecycle.py](../../tests/contract/test_resources_lifecycle.py) are read in
   the display timezone, as new rows are dated; `_writes_sending` in
   [test_line_codes_and_statement_lines.py](../../tests/contract/test_line_codes_and_statement_lines.py)
   builds its opening balance's body through `Scratch.opening_balance`'s body.
   *Passes if:* neither file reads a date in UTC or builds an opening balance's body by hand;
   both pass live twice and leave nothing.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
