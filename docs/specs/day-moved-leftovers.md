# Leftovers from the PDF preview's moved line

What the work on the PDF preview's `· day moved` mark found along the way, on 2026-10-28, and did
not build: one small cleanup, and two pieces that may belong to the holder specs on hold.

**Status: approved and named the current spec by the owner on 2026-10-28, questions 1 and 2
answered A: only point 1 is built here, and points 2 and 3 wait for the holder specs, as
todo.md's backlog notes.** When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

Each piece is small and none changes what you see. They keep the code plain and the docs and test
fixtures in step with the engine's contract.

## What it must do

1. **The statement PDF's preview counts its rows by arithmetic.** Each row of the paper is one
   line on the preview, so finding where a page ends needs no drawing of every row (the
   preview's page end in
   [statement_upload.py](../../expense/tui/screens/statement_upload.py)). Nothing on screen
   changes.
2. **Person accounts in the unit tests sit on a person holder,** as question 1 decides: some
   fixtures make a person account with no holder (`holder_id` empty), where the engine puts every
   person account on a person holder (contract: "Holders", "Its kind").
3. **The docs cite only what the live contract holds,** as question 2 decides: tui.md and
   decisions.md cite routes and parts the engine removed (archiving an account, turning an account
   into a person or back, the "Bank Accounts" tag's "Statement code").

## How the owner knows it is done

1. The PDF preview pages exactly as before, its tests unchanged and passing.
2. The pieces questions 1 and 2 keep here are done, and the unit suite and drift check pass.

## Questions for the owner

1. **The person accounts in the unit tests.** The ask "An account holds its currencies: the
   holder becomes the account, and each account becomes one of its currencies" will change what a
   person is in the engine, and the holder specs on hold rewrite these tests from its hand-off.
   - **A.** Leave them to the holder specs: fixing them now is undone by that hand-off.
   - **B.** Fix them here now, so the tests match today's engine.

   **Recommended:** A: the same tests change again once the hand-off lands.

   **Answered 2026-10-28:** A.
2. **The docs' stale citations.** They describe screens (archiving, turning an account into a
   person) that the holder specs on hold rebuild on the engine's new routes.
   - **A.** Leave them to those specs, which rewrite the same paragraphs.
   - **B.** Fix the citations here now, pointing at today's routes.

   **Recommended:** A: those paragraphs are rewritten when the screens are.

   **Answered 2026-10-28:** A.

---

## Tasks

Drafted 2026-10-28, when the owner named this the current spec.

1. **The preview's page end by arithmetic (builder).** In
   [statement_upload.py](../../expense/tui/screens/statement_upload.py), the preview's page end
   (`_window_end`) counts rows as `min(len(rows), start + budget)` instead of drawing every row.
   *Passes if:* no row is drawn to find the page end; the preview pages exactly as before, every
   test of test_tui_statement_upload.py passing unchanged; ruff and mypy clean.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
