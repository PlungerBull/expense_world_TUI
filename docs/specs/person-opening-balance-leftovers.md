# A person's opening balance: the sheet import's live test

A small thing the catch-up on a person's opening balance (contract `4ac20e42cf8566ee`) turned up.
Its other point, the words of a person's `opening` line, was settled by the owner and built by
part 6 of the currencies catch-up, the main views (done on 2026-10-31).

**Status: approved by the owner on 2026-10-28.** Its tasks are drafted when the owner names it
the current spec. It runs after
part 4 of the currencies catch-up, the live tests for the upload, bank lines and kinds (done on 2026-10-31),
which puts the live suite's people on the account and its currencies. When done, the why moves
to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

The engine gives a person its opening balances from the sheet import: a person's first
`SALDO INICIAL` row in each currency becomes that currency's opening balance, by the same rule as
any account's (contract: POST /v1/transactions/import-sheet, "Opening balances"). Nothing in this
client proves that live. The owner's own import does not use it, since every sheet name is
created as a bank account and people are turned into people afterwards, but an import run again
after that does.

## What it must do

1. **The live suite proves the sheet import gives a person its opening balances:** an existing
   person's first `SALDO INICIAL` row of a non-zero amount in each of its currencies becomes that
   currency's opening balance, under `@Opening`, named by that currency's
   `currencies[].opening_balance_transaction_id`; a second apply matches them and creates
   nothing.

## How the owner knows it is done

1. The live suite passes, the sheet import's person case included.
2. The unit suite passes.

## Questions for the owner

None.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
