# Leftovers from the statement catch-up

**Status: draft, for the owner to rewrite or approve. Its tasks are drafted when the owner names
it the current spec.** When done, the why moves to [decisions.md](../decisions.md) and this file
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
3. The engine's account read names a card's other account, and the create form reads it there.
4. The practice user's Reconciliations browse lists only accounts a test is using.

## Questions for the owner

1. **Point 9's note.** A mockup comes when the spec starts.
