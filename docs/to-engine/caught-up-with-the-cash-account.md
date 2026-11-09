# Caught up with contract 2fa4967b8eed9c3f: the cash account, one per user, named `Efectivo`

2026-11-09

## Covers

Part 2 of the reply to the hand-off of 2026-11-08 ("A closed day never holds a line in no
statement…"): part C, 3 and 4, the cash account. Part 1, the rest of that hand-off, follows
separately. Checked against the practice engine serving `9b3b43429d8bd11e`. The client's whole
live contract suite ran green there: 384 passed, plus 19 expected failures that wait on the
loose-lines and sheet-import asks.

## Done when, checked

- **The dashboard shows cash:** worked. `GET /dashboard` lists the cash account among the
  accounts in the engine's order, as `{id, name, kind, currencies}` with kind `cash`. Archived,
  it moves to `archived_accounts`; unarchived, it comes back. The client marks it by its `kind`
  alone.
- **`Efectivo` is made once:**
  - A `POST /accounts` with kind `cash` and its currencies, and no name, bank, number or
    statement code, made `Efectivo`. The practice user's cash account was made once, with soles
    and no opening, since it can never be deleted; opening balances on create go the same way
    as a bank account's, which the client proved there.
  - A second one was refused `CASH_EXISTS` on `kind`, whether the first was live or archived,
    with nothing written.
  - A person named `Efectivo` (or `EFECTIVO`) kept the cash account from being made
    (`NAME_EXISTS` on `kind`). Once it existed, a person could not take the name (`NAME_EXISTS`
    on `name`).
  - The client offers `cash` on its New form only while the user holds none, archived included.
- **The cash account's refusals:** worked, each with nothing written.
  - `CASH_TAKES_NO_FIELD` on create, for a name, bank, last 4 or statement code (null included),
    and on update, for a name, current number or statement code (null included), a bank code
    or a new number.
  - `CASH_KIND_FIXED` on make-person and make-account, live and archived.
  - `CASH_NOT_DELETABLE` on delete, live and archived.
  - `CASH_TAKES_NO_STATEMENT` on `POST /statements` and on `POST /statements/import` and
    `POST /transactions/import`, each on a dry run and an apply.
  - Its colour, currencies, opening balances and archive work as on any account.
  - The client never offers what is refused: the cash account's row has no kind change or
    delete; its Edit form shows type, name and currencies read-only; it is left out of every
    list that takes a statement, a bank PDF or a bank download, which hold bank accounts alone.

## Contract problems found

- **`null` on the cash account answers two codes for one mistake.** On `POST /accounts`, a
  `null` `bank_code` for the cash account is `CASH_TAKES_NO_FIELD` ("null included"). On
  `PUT /accounts/{id}`, a `null` `bank_code` or `new_number` is `422 NOT_NULL`, since the shape
  check comes first. The PUT's own refusal order supports that, but "The cash account" says a
  sent `bank_code` or `new_number` is `CASH_TAKES_NO_FIELD`, with no such caveat. Either answer
  `CASH_TAKES_NO_FIELD` on both routes, or say in "The cash account" that a `null` there is
  `NOT_NULL` on update.
- **PUT's null rule leaves out the cash account's `name`.** `PUT /accounts/{id}` says `null` is
  `NOT_NULL` on every field except `statement_code`, `current_number` and a bank account's
  `name`. The engine answers a `null` `name` on the cash account `CASH_TAKES_NO_FIELD`, which
  fits the `name` field's own rule. The exception list should name it too.

## Asks this closes

- Every user holds one cash account, named `Efectivo`, with no bank and no number
