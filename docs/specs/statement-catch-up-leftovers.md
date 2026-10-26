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

1. **Guard `statement_line` and `statement_place` out of request bodies** (point 1). Passes if
   every unit test fails when a request body it sends carries either field at any depth, as it
   does for `line_code`, with a test proving the guard trips on each, and the unit suite still
   passes.
2. **One account-record builder in test_cmd_import.py** (point 2). Passes if the file builds
   every account record through one helper, no copied record is left, and its tests check
   what they checked before.
3. **The complete answer's fixtures carry `coverage_gap`, and the drift check catches a
   required field a fixture leaves out** (point 3). Passes if every unit fixture of the complete
   answer has `coverage_gap`, the drift script reports a fixture that leaves out a field the
   contract marks required on its answer, with a unit test proving it, and a run against the
   practice engine is clean.
4. **The fake engine answers a reconciliation write as the engine does** (point 4). Passes if
   `FakeClient` answers a reconciliation's create, revert, delete and complete in the engine's
   answer shape, `twin` included on a card (contract: POST /v1/reconciliations), the tests that
   set their own answer keep working, and the unit suite passes.
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
11. **Write the engine ask: the account read names a card's other account** (point 10, the
    orchestrator's part). Passes if one file in [to-engine/](../to-engine/) asks for it in that
    folder's shape and says what this client removes once it lands (the grouping by statement
    code that finds a card's partner).
12. **Words that describe dropped screens say what is** (point 11). Passes if the `⏎` comment
    in reconciliations.py and the docstrings of test_statement_codes.py and
    test_statement_order.py describe what the code does, naming no screen that does not exist.
13. **The practice user's leftovers are cleaned, and the run that leaves them is fixed** (point
    12). Passes if the live run that leaves accounts with statement codes and reconciliations
    behind is found and fixed, those leftovers are removed from the practice user, and after a
    full live run the practice user's Reconciliations browse lists no account a test made.

## Found along the way

Nothing yet.
