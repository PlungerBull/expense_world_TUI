# A person's opening balance: its hint and the sheet import's test

Two small things the catch-up on a person's opening balance turned up (contract
`4ac20e42cf8566ee`, done on 2026-10-28).

**Status: approved by the owner on 2026-10-28, question 1 answered.** Its tasks
are drafted when the owner approves it. Point 2's live test runs after the cards and statements
catch-up's live tests
([catch-up-cards-statements-2a-live-suite-foundation.md](catch-up-cards-statements-2a-live-suite-foundation.md)
and
[catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md)),
which put the live suite back on the engine's holders. When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

A person's Edit form takes an opening balance, as a bank account's does (decisions.md "A person
carries an opening balance"). While you type on its `opening` line, the line under it explains
the sign in the bank account's words: `350.00 is money you have · -350.00 is money you owe`. On a
person, the balance is a debt: a positive one is money they owe you, which "money you have" only
roughly says.

The engine also gives a person its opening balance from the sheet import: a person's first
`SALDO INICIAL` row becomes it, by the same rule as any account's
(contract: POST /v1/transactions/import-sheet, "Opening balances"). Nothing in this client proves
that live. The owner's own import does not use it, since every sheet name is created as a bank
account and people are turned into people afterwards, but an import run again after that does.

## What it must do

1. **A person's `opening` hint reads as question 1 decides.** A bank account's stays as it is.
2. **The live suite proves the sheet import gives a person its opening balance:** an existing
   person's first `SALDO INICIAL` row of a non-zero amount becomes its opening balance, under
   `@Opening`, named by the person's `opening_balance_transaction_id`; a second apply matches it
   and creates nothing.

## How the owner knows it is done

1. On a person's Edit form, the line under `opening` reads as question 1 picks.
2. The live suite passes, the sheet import's person case included.
3. The unit suite passes.

## Questions for the owner

1. **The words of a person's `opening` line** (drawn in
   [expense-world-person-opening-hint.html](../mockups/expense-world-person-opening-hint.html)).
   The owner's design, 2026-10-28: no line under it; on the right of the `OPENING` line, `debt`
   when the amount is negative and `credit` when positive, then the currency (`debt · PEN`).
   Two parts wait on the owner:
   - **a.** The line empty or `0.00`: the currency alone, or nothing.
     **Recommended:** the currency alone, so it is always there.
   - **b.** A bank account's opening line: the same word, or today's line under it.
     **Recommended:** the same word on every account, so one sign reads one way everywhere.

   **Answered 2026-10-28:** a, nothing on the right while the line is empty or `0.00`; b, the same word on
   every account.

---

## Tasks

Drafted when the owner approves this spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
