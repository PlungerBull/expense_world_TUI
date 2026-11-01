# Caught up with contract f82426fb0a099676: the terminal app's main views on an account holding its currencies (part 6 of 7)

2026-10-31

## Covers

`e020782e3579d011` → `f82426fb0a099676`, your hand-off of 2026-10-29, "An account holds its
currencies: every route names an account and a currency code; holders are gone": its sections 2
to 8 and 12, on screen. That is the accounts list, an account's writes, adding and removing a
currency, the opening balance per currency, `/dashboard`'s account rows and a transaction's
currency.

The terminal app now shows an account once, its currencies inside it:
- Manage ▸ Accounts has one row per account, with a column per currency.
- Home has the account's row and a line per currency.
- Every account picker lists one row per account.

The currency is a field of its own wherever a line names an account:
- the one-line quick-add bar;
- the Edit form;
- the ledger's column, filter and bulk move.

Where an account holds one currency, the app asks for none. Where it holds several, the person
picks one.

## Done when, checked

All checked against the practice engine on 2026-10-31. The accounts half was tried in the app
on the owner's machine. The currency half was checked with:
- the unit suite: 3585 passed;
- the live contract suite: 256 passed. The one failure is the suite's own check that every
  contract citation in this repo resolves, failing on citations in the app's statement screens,
  which part 7 rewrites;
- each check tried in the app, nothing left on either practice user;
- the contract version, unmoved.

- **"The Visa in soles and dollars, and ALEJO in soles and dollars, are each created in one write
  from the app; a currency is added to an account later, and a currency with nothing booked is
  removed":** worked.
  - The New form takes a bank account's or a person's currencies as a list. It sends one
    `POST /accounts` with them, and a bank account's statement code with it.
  - A key on the account's row adds a currency the account does not hold
    (`POST /accounts/{id}/currencies`).
  - Another key removes one, after the person confirms. `LAST_CURRENCY` and `HAS_TRANSACTIONS`
    are shown in your words, nothing written.
  - The Edit form takes an opening balance per currency.
- **"Archiving, unarchiving, turning into a person and back, and deleting act on the account,
  all its currencies at once":** worked.
  - Archive and unarchive are one key on the account's row, acting on every currency.
  - Turning a bank account into a person and back is one key. `KIND_UNCHANGED`,
    `ACCOUNT_ARCHIVED` and `HAS_RECONCILIATION` are shown in your words.
  - A delete names the account and each currency with its balance before the person confirms.
    `IN_LIVE_STATEMENT` is shown in your words.
- **"A transaction names an account and a currency it holds; one in a currency the account does
  not hold is refused, nothing written, and the app shows why":** worked.
  - The quick-add bar names the currency as its own token, sends `account_id` and
    `currency_code`, and shows `CURRENCY_NOT_HELD` under the row, nothing saved.
  - The Edit form moves a line to its account's other currency in one `PUT /bank-lines/{id}`.
    The line keeps a draft statement by sending that statement's own id, as "Assigning
    transactions" states. `edit_limits` naming `currency_code` locks the line.
  - The ledger reads `?currency_code=` beside `?account_id=`, and moves selected rows to another
    currency with one `PUT /transactions/{id}` per row. A refused row is named by number in your
    words, and the others still move.
  - Moving rows to an account holding one currency sends `account_id` and that currency, the
    amount as it is. To an account holding several, it sends `account_id` alone.
  - Live tests: a create in a currency the account does not hold, and a move onto an account
    lacking the line's currency, are both refused with nothing written.

## Contract problems found

None in this part.

## Asks this closes

None of its own. "An account holds its currencies: the holder becomes the account, and each
account becomes one of its currencies" closes with part 7, the statement screen.

This part raised five asks, each handed over as its own file:
- "An account's only currency is taken when a write names none". Until it lands, the app fills
  an account's only currency itself in three places: the quick-add line, the Edit form's account
  change and the bulk move to another account.
- "An account and its opening balances save in one write".
- "Removing a currency names the currency in every refusal".
- "Say whether an account can hold no currency, and what a client does with one".
- "A read lists the supported currencies".
