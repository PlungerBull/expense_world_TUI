# Leftovers from the statement catch-up

**Status: approved by the owner and the current spec, 2026-10-25.** When done, the why moves to [decisions.md](../decisions.md) and this file
is deleted.

---

## Why

Small things found while catching up with the engine's statement lines and card statements
(2026-10-24 and 2026-10-25), not fixed there. Nothing you see changes, except the create form's
note in point 9 and the engine ask in point 10.

## What it must do

1. **A guard refuses `statement_line` and `statement_place` in any request body** the unit
   tests send, as one already does for `line_code` (`_no_line_code_in_requests` in
   [tests/unit/conftest.py](../../tests/unit/conftest.py)).
2. **One small builder for an account record** in
   [test_cmd_import.py](../../tests/unit/test_cmd_import.py), which copies one record about 25
   times.
3. **The complete answer's unit fixtures carry `coverage_gap`**, which the contract requires on
   that answer (contract: POST /v1/reconciliations/{reconciliation_id}/complete); the drift check
   catches only fields the engine does not serve, never a required one a fixture leaves out, so
   it learns to catch those too.
4. **The fake engine answers a reconciliation write as the engine does**: `FakeClient` answers
   every write with a bare `{}`, so a create, revert, delete or complete in the unit tests gets
   no `twin`.
5. **One copy of each contract-suite helper**: `_live_ids` (four files), `_send`
   ([test_card_statement.py](../../tests/contract/test_card_statement.py) and
   test_statement_order.py), `_batch_into` and `_assign` in
   [test_statement_order.py](../../tests/contract/test_statement_order.py), which repeat
   `Scratch.line` in [conftest.py](../../tests/contract/conftest.py) (`_assign` through
   `PUT /bank-lines/{id}` where `Scratch.line(recon=…)` uses `PUT /transactions/{id}`); and one
   guard, over the whole repo, that nothing names the split route, in place of the two in
   [test_bank_line_write.py](../../tests/unit/test_bank_line_write.py), worded in the present
   tense.
6. **The live suite pins two card-statement answers**: a complete on a card whose halves are
   both completed already, which writes nothing, and `UNASSIGNED_IN_PERIOD` on both halves at
   once (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Validation").
7. **A unit test pins `c`, `u` and `d` on a card half's batch screen** acting on both halves;
   today only the live suite and a hand check prove it.
8. **One way to group accounts by statement code, one way to dim a completed row**:
   `statement_accounts` and `statement_partners` in [reads.py](../../expense/reads.py) each
   group the accounts by code, and `statement_rows` in
   [reconciliations.py](../../expense/tui/screens/reconciliations.py) dims a row by its status
   label where `batch_rows` reads the engine's `status`.
9. **The create form says a statement holding the opening balance begins at 0.00.** The engine
   adds an assigned opening balance into the statement's sum, so typing the paper's starting
   figure as the begin balance too counts it twice. The wording is picked from a mockup first.
10. **The account read names a card's other account** (an engine ask): the create form finds a
    card's partner by grouping accounts on their statement code, dropping people and codes not
    held by exactly two accounts; the engine knows the pair.
11. **Words that describe dropped screens say what is**: the comment on `⏎` in
    [reconciliations.py](../../expense/tui/screens/reconciliations.py) ("Interim until the
    statement's screen (task 7)"), and the docstrings of
    [test_statement_codes.py](../../tests/contract/test_statement_codes.py) ("the
    statement-order screen leans on it") and
    [test_statement_order.py](../../tests/contract/test_statement_order.py) ("The
    statement-order screen is built on these two routes").
12. **The practice user's leftovers are cleaned**: about 50 accounts with statement codes and
    reconciliations from earlier live runs, which take codes such as `SIG` and fill the
    Reconciliations browse; and the run that leaves them is found.

## How the owner knows it is done

1. The unit and live suites pass, and each point above has its test or its single copy.
2. The create form's note reads as picked.
3. The ask that the engine's account read name a card's other account is written for the engine
   coders. The create form reads it there in the catch-up that follows the engine's answer, not
   in this spec (the owner, 2026-10-25).
4. The practice user's Reconciliations browse lists only accounts a test is using.

## Questions for the owner

1. **Point 9's note.** Answered 2026-10-25: B in
   [expense-world-opening-balance-note.html](../mockups/expense-world-opening-balance-note.html),
   today's hint kept and a second line `0.00 if it holds the account's opening balance, which
   already counts it`.

---

## Tasks

Approved by the owner on 2026-10-25. One task at a time, in this order; each says what it must
do and when it passes.

5. **One copy of each contract-suite helper** (point 5, first half). Passes if `_live_ids`,
   `_send`, `_batch_into` and `_assign` each exist once, in the contract suite's conftest.py, or
   give way to `Scratch.line`, keeping whichever route a test exists to prove, and the live
   suite passes against the practice engine.
6. **One repo-wide guard that nothing names the split route** (point 5, second half). Passes if
   one test over the whole repo replaces the two in test_bank_line_write.py, its docstring in
   the present tense, and it fails when any file names the route.
7. **The live suite pins two card-statement answers** (point 6). Passes if live tests prove
   that a complete on a card whose halves are both completed writes nothing, and that
   `UNASSIGNED_IN_PERIOD` names both halves at once, and the live suite passes.
8. **A unit test pins `c`, `u` and `d` on a card half's batch screen** (point 7; after task 4).
   Passes if unit tests drive each key on a card half and prove the one write sent and that the
   screen shows both halves done.
9. **One way to group accounts by statement code, one way to dim a completed row** (point 8).
   Passes if `statement_accounts` and `statement_partners` share one grouping, `statement_rows`
   dims a row from the engine's `status` as `batch_rows` does, and what the screens show is
   unchanged.
10. **The create form's note on the opening balance** (point 9). Passes if the hint under
    BEGIN BALANCE reads as pick B of
    [expense-world-opening-balance-note.html](../mockups/expense-world-opening-balance-note.html),
    on the one-account form and on each half of a card's form, with tests, and tui.md says it.
12. **Words that describe dropped screens say what is** (point 11). Passes if the `⏎` comment
    in reconciliations.py and the docstrings of test_statement_codes.py and
    test_statement_order.py describe what the code does, naming no screen that does not exist.
13. **The practice user's leftovers are cleaned, and the run that leaves them is fixed** (point
    12). Passes if the live run that leaves accounts with statement codes and reconciliations
    behind is found and fixed, those leftovers are removed from the practice user, and after a
    full live run the practice user's Reconciliations browse lists no account a test made.

## Found along the way

- **test_cmd_import.py repeats its seeded-account mock.** About 20 tests call
  `_mock_existing(accounts=[_account()], categories=[], hashtags=[])`, which the file's own
  `_seeded_account()` already does (found by task 2's builder, 2026-10-25).
- **Several unit files keep their own account-record builder**, each with its own signature:
  `_account` in test_cmd_import.py, test_tui_account_kind.py and test_tui_card_statement.py;
  one shared builder in helpers.py (found by task 2's builder, 2026-10-25).
- **A unit fixture quotes an old `GAP` warning.** The sentence in
  test_tui_reconcile_detail.py ("…sealed by nothing", 2026-02-25 to 2026-04-01) predates the
  contract's wording, and its last day is the period's first day (found by task 3's builder,
  2026-10-25).
- **More answer builders could be marked for the drift check.** Only the complete answer
  carries `@answer_of`; `put_answer`, `bank_line_row` and the create answer could too, and a
  marked answer's extra keys could be checked against its own endpoint (found by task 3's
  builder, 2026-10-25).
- **Two small edges of the drift check's answer markers.** `answer_of` in helpers.py silently
  replaces a builder already marked for the same endpoint, and when the contract allows more
  than one object shape for an answer the script says the contract "holds no JSON answer for
  it", which misnames the case (found by task 3's reviewer, 2026-10-25).
- **A card-statement test builds the create's answer by hand.**
  `test_saved_it_says_so_and_the_panel_lands_on_the_new_statement` in
  test_tui_card_statement.py replaces `fake_client.post` to build the card create's answer,
  which the fake engine now builds by default (found by task 4's builder, 2026-10-25).
- **The drift check does not check a card's twin half.** It checks the bare answers only, so
  the `twin` inside a card's answer is never checked against its own schema (found by task 4's
  builder, 2026-10-25).
