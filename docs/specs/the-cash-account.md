# The cash account

Part of the catch-up to contract `2fa4967b8eed9c3f` (the engine's hand-off of 2026-11-08,
part C, 3 and 4): the cash account's screens. It runs after
[accounts-carry-their-numbers.md](accounts-carry-their-numbers.md), whose New and Edit forms it
builds on.

**Status: draft, 2026-11-08, for the owner to approve, with its two questions on the mockup
[expense-world-cash-account.html](../mockups/expense-world-cash-account.html).** When done, the
why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

Cash is money like any account's, but it has no bank, no card number and no statements. The
engine now holds it as one account per user named `Efectivo`, which a user makes when they ask
for it, and which can be archived but never deleted.

## What it must do

1. **The owner can make the cash account once,** with its currencies and their opening
   balances, while they hold none (an archived one counts).
2. **It shows as cash** on Home and on Manage ▸ Accounts, each currency's balance on its own.
3. **It offers only what cash can do:** no rename, bank, number, statement code, kind change or
   delete; archive and unarchive work.
4. **It never appears where only a bank account belongs:** the Statements screen, a PDF upload's
   account question, a bank download's.
5. Everywhere else (the LOG bar's `$`, the ledger, moves, the account pickers) it works like any
   account.

## How the owner knows it is done

1. With no cash account, the owner makes `Efectivo` from the app with soles and dollars and an
   opening balance in each; after that, the app offers no second one, archived or not.
2. Home shows `Efectivo` with its balance in each currency.
3. On Manage ▸ Accounts, the cash account offers no rename, number, statement code, kind change
   or delete; archive and unarchive work.
4. `Efectivo` is not offered on the Statements screen or as a PDF's or a download's account.
5. A cash expense logged on the LOG bar with `$efectivo` lands on it.

## What the engine declined, or did differently

- **Made only when asked,** not for every user: not on sign-up, not in the practice seed, not
  for the owner's books.
- **Shared names:** a person named `Efectivo` (any case) keeps the cash account from being made
  (`NAME_EXISTS` on `kind`); once it exists, no account can take that name.

## Questions

Drawn on [expense-world-cash-account.html](../mockups/expense-world-cash-account.html).

| # | Question | Options | Recommended |
|---|---|---|---|
| 1 | Where is it made? Pane 1. | A: a third type, `cash`, on Manage ▸ Accounts' New form, offered only while you hold none · B: a waiting `+ Efectivo · not made yet` row on the accounts list | A: no new key or row; the form already drops lines by type |
| 2 | How does Home show it? Pane 2. | A: one `ACCOUNTS` list, cash among them in the accounts' order, marked `cash` · B: a `CASH` section of its own | A: the engine lists it among the accounts in their order |

---

## Tasks

Drafted 2026-11-08 on the recommended answers (1A, 2A). Each reads the live contract on the
practice engine before building.

1. **Home shows cash** (question 2): the block's header reads `ACCOUNTS`; each row of
   `/dashboard`'s `accounts` in the engine's order, the cash one marked `cash`.
2. **Making it** (question 1): the New form's type offers `cash` while
   `GET /accounts?include_archived=true` lists no account of kind `cash`; with `cash` picked, name
   reads `Efectivo · set by the engine`, bank, last 4 and statement code leave the form; one
   `POST /accounts` with `kind: "cash"`, its currencies and openings, and no name, bank, number
   or code. `CASH_EXISTS` and `NAME_EXISTS` (keyed `kind`) in the engine's words on the type line.
3. **The cash account's row and Edit form** (pane 3): Type `cash` on Manage ▸ Accounts; no `t`
   and no `d` on its row; its Edit form holds type, name and currencies read-only, color and the
   openings; `CASH_TAKES_NO_FIELD`, `CASH_KIND_FIXED` and `CASH_NOT_DELETABLE` in the engine's
   words should one come anyway.
4. **Cash out of the bank-only places:** the Statements browse, the PDF upload's account question
   and the bank download's leave out kind `cash`; `CASH_TAKES_NO_STATEMENT` in the engine's words
   should one come anyway.
5. **The live contract tests:** a cash account made with no name, bank or number, named
   `Efectivo`; `CASH_EXISTS`, the archived one included; `CASH_TAKES_NO_FIELD` on create and
   update; `CASH_KIND_FIXED` on both kind changes; `CASH_NOT_DELETABLE`; `CASH_TAKES_NO_STATEMENT`
   on `POST /statements`, `POST /statements/import` and `POST /transactions/import`; a person
   named `Efectivo` refused `NAME_EXISTS` on `kind`; its `/dashboard` row; archive and unarchive.
   The cash account cannot be deleted, so the suite copes with one left by an earlier run.

## Reply to the engine

Part 2 of the reply to the hand-off of 2026-11-08 ("A closed day never holds a line in no
statement…"): part C, 3 and 4. It reports on the hand-off's "Done when" checks for the dashboard
showing cash, making `Efectivo` once and the cash account's refusals, any contract problem found,
and closes the ask "Every user holds one cash account, named `Efectivo`, with no bank and no
number".

## Found along the way

Not built in this spec; sorted when it is done.
