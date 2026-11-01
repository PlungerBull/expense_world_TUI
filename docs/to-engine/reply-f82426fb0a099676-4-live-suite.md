# Caught up with contract f82426fb0a099676: the terminal app's live contract suite tests an account holding its currencies (parts 3 and 4 of 7)

2026-10-31

## Covers

`e020782e3579d011` → `f82426fb0a099676` (`07475793a38b47b4`, `d5241e52676b19f9`,
`2d7db5f914b565d9`, `b54580104fce4fde`, `394b3a9034b36d98`, `ba0f857bc43b95ce`,
`02fb846290642261`, `4d57bb4f05ecc3b3`, `4329913878f62787`, `3d0afdaa03d87d5c`,
`7aec8f6ed9928caf`, `f82426fb0a099676`), your hand-off of 2026-10-29, "An account holds its
currencies: every route names an account and a currency code; holders are gone": its live
contract suite, which calls your practice engine directly and walks real flows. Part 3 rebuilt the
suite's shared setup and its first sixteen files; part 4 moved the rest of the suite: the bank
lines and the review list, moves and closed days, the bank download and the sheet import, an
account's kind and archiving, statement codes, the statement order and the PDF upload. The live
tests of adding and removing a currency are part 5. The live checks your hand-offs of 2026-10-27
and 2026-10-28 asked for on a holder and its accounts are superseded: the suite tests the account
model only.

## Done when, checked

All checked against the practice engine: part 3 on 2026-10-30 (its 16 files, 92 tests, passed
and left nothing on either practice user), part 4 on 2026-10-31 (the whole suite, 256 tests
passed; the one failure is the suite's own check that every contract citation in this repo
resolves, on citations in the app's statement screens and their unit tests, which part 7
rewrites; nothing left on either practice user; contract version unmoved).

- **"A statement is the account's, with a starting and ending balance per currency it covers,
  and the PDF upload closes it":** worked.
  - A statement is made, renamed, completed, reverted and deleted as one record on the account.
  - Each currency is judged on its own: `NO_TRANSACTIONS_ASSIGNED`, `DIFFERENCE_NOT_ZERO`, and a
    currency with nothing left out and listed in `not_covered`.
  - A line gives a draft its currency's null balances, then `BEGINNING_BALANCE_REQUIRED` and
    `ENDING_BALANCE_REQUIRED` come in one answer; a completed statement gaining a currency is
    `LOCKED`.
  - One statement per account per month holds with or without a statement code
    (`STATEMENT_MONTH_TAKEN` from `POST` and `PUT /statements`, a deleted statement not counting).
  - The PDF upload is tested on your three published samples (`savings`, `card`,
    `card-no-dollars`) and on savings and card papers the tests draw. A card paper with dollars
    at zero closes a soles-only account in soles only, and `MONEY_AT_START_NOT_COVERED` comes
    where the account's dollars hold money at the start. The order and statement lines it sets
    read back with every currency of the account in the paper's order, which is neither date
    order nor grouped by currency. No write sets a place.
  - A statement's lines list by place, then oldest first, paged by cursor bound to the order.
  - The review list (`?unassigned_in_period_of=`) lists every currency's lines of the account by
    date, before and after the close, matching the close's `review_lines`, an opening balance
    never listed.
- **"A transaction names an account and a currency it holds; one in a currency the account does
  not hold is refused, nothing written":** worked.
  - Every transaction, batch item, bank line and part names its account and currency; the bank
    lines' list and count filter by account and currency.
  - A line moves by `currency_code` alone, by `account_id` alone and by both. Onto an account
    lacking its currency it is `CURRENCY_NOT_HELD` on the key sent. Onto a sealed day it is
    `SEALED_PERIOD` on every key sent.
  - `edit_limits` names `currency_code` exactly when it names `account_id`.
  - No create takes a statement (`statement_id` is `UNKNOWN_FIELD`).
  - The bank download lands each row on its `Moneda`'s currency of one account, leaves a
    matching dollar line alone on a soles download, refuses a dollar row to a soles-only account
    on its row, and reports leftover days grouped in each currency's first file row order.
  - The sheet import maps one entry per account name, its create step makes one account holding
    its rows' currencies, and an account lacking one is refused on its entry.
- **"Archiving, unarchiving, turning into a person and back, and deleting act on the account,
  all its currencies at once":** worked.
  - A person is one `POST /accounts` with `is_person: true` and its currencies.
  - `make-person` and `make-account` turn the whole account, each currency's opening balance
    kept, their refusals in your order, pair by pair (`ACCOUNT_ARCHIVED`, `KIND_UNCHANGED`,
    `HAS_RECONCILIATION`, a deleted statement counting).
  - Archive and unarchive act on every currency in one write, and a new row in either currency
    of an archived account is `INVALID_REFERENCE`.
  - A person takes no statement (`PERSON_TAKES_NO_STATEMENT`), and takes it once turned back.
  - A person carries a statement code like any account; one account holds a code whatever its
    currencies.
- **The hand-off of 2026-10-27, the upload tested against the published samples:** worked, as
  above, on the account model.

## Contract problems found

- **A refusal of the PDF upload that only a race reaches.** `POST /statements/import` lists
  `STATEMENT_MONTH_TAKEN` on `file` among its refusals, but its own rule makes the account's live
  statement whose `date_end` is in the paper's month the paper's, so no other statement can hold
  that month. Only a `POST` or `PUT /statements` landing between the upload's read and its write
  reaches it. Either drop it from the upload's refusals, or state that it comes only from a
  concurrent statement write and name it under the upload's "Concurrency" part.
- **A sentence on a route that no longer exists.** `GET /bank-lines/{id}`'s "Response fields"
  (`is_opening_balance`) still says "a `PUT /statements/{id}/statement-order` that lists it is
  refused on its entry (`OPENING_BALANCE_NOT_PLACED`)". No such route exists: `GET
  …/statement-order` is the only operation on that path, and no route sets the order by hand.
  Drop the sentence.
- **`is_person` takes values that are not booleans.** `POST /accounts` says `is_person` that is
  `null` or "a value that is not a boolean is `422` (`INVALID_FORMAT`)". The engine takes
  `"yes"`, `"no"`, `"true"`, `1` and `0` as booleans. This was checked live on 2026-10-31 with a
  body missing `name`, so nothing was written: `"maybe"` and `null` are refused on `is_person`;
  those five are not. Refuse them, or state which values count.
- **A refusal of `make-account` that cannot be reached.** `make-account` lists
  `HAS_RECONCILIATION`, but no person ever holds a statement: a person is refused every
  statement write, and an account that has had one never becomes a person. A bank account with a
  statement is answered `KIND_UNCHANGED` first. Drop it from `make-account`'s refusals, or say
  when it comes.

## Asks this closes

None of its own. "Publish one made-up sample statement PDF per paper, so every client can test
the statement upload" stays closed: the samples are tested live. "An account holds its currencies:
the holder becomes the account, and each account becomes one of its currencies" closes with part
7, the statement screen.
