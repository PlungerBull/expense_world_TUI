# Every user holds one cash account, named `Efectivo`, with no bank and no number

Raised 2026-11-08.

## Why

Since contract `d9bd079557801740` an account is either a person, with a typed name, or a bank
account, with a bank from `GET /banks` and a name built from it (`BCP-5678`, or `BCP` with no
number). Cash fits neither. The owner keeps cash in soles and dollars and logs what they spend
from it, and today the only place for it is a bank account at `BCP` with no number, named `BCP`.
That name says the wrong thing, collides with every other numberless bank account, and puts cash
on the bank's side of every rule (statements, the statement code, the PDF's number check).

The owner's answer, 2026-11-08: one generic cash account per user, named `Efectivo`.

## The ask

1. **Every user holds exactly one cash account,** made by the engine, never by a client: a new
   user gets it when they are set up, and the ledger update gives one to every user who has none.
   It holds `PEN` and `USD`, and currencies are added and removed on it as on any account.
2. **Its name is `Efectivo`, set by the engine,** never typed and never built from a bank. A
   `name`, `bank_code` or `last4` sent for it is refused, each on its field.
3. **Every account answer says it is the cash account,** in a field a client can test (for
   example a `kind` of `bank`, `person` or `cash`), not by matching on its name. It carries
   `bank_code` `null` and `numbers` `[]`.
4. **It never becomes a person or a bank account,** and no other account becomes the cash account.
   The two kind changes refuse it.
5. **It holds no statements:** a statement, a statement code or a PDF upload for it is refused in
   words that say cash has no bank statements, not `ACCOUNT_HAS_NO_NUMBER`.
6. **Everything else works on it as on any account:** transactions, opening balances (in the one
   write of `POST /accounts` and `PUT /accounts/{id}`), moves onto and off it, its balances on
   `/dashboard`, and the sheet import naming it in the `names` table.
7. **The contract states what happens when it would be archived or deleted,** and what holds its
   name: whether a person may be named `Efectivo`, and what the ledger update does with an
   account already named that. The engine settles these; the client only shows the answers.
8. **The shared practice user holds it too,** so the client's tester can log cash in the real app.

## Done when

- A new user's `GET /accounts` lists one account named `Efectivo`, marked as cash, holding `PEN`
  and `USD`, with no bank and no numbers.
- A second cash account cannot be made, and `Efectivo` cannot be renamed, given a bank or a
  number, turned into a person or a bank account, or sent a statement, each refusal on its field
  in the contract's words.
- A transaction logged on it, its opening balances and a move onto it save as on any account.
- The contract states the cash account in *Bank Accounts*, with every refusal, and its
  `x-changelog` entry names it.

## What this client removes once it lands

Nothing is removed: the client has no cash workaround. Without this ask, the owner's cash would
sit in a bank account named `BCP`; with it, the account form offers no way to make a cash
account and shows `Efectivo` as the engine names it.
