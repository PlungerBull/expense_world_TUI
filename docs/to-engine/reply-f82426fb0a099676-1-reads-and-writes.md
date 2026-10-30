# Caught up with contract f82426fb0a099676: the terminal app reads and writes an account holding its currencies (part 1 of 7)

2026-10-30

## Covers

`e020782e3579d011` → `f82426fb0a099676` (`07475793a38b47b4`, `d5241e52676b19f9`,
`2d7db5f914b565d9`, `b54580104fce4fde`, `394b3a9034b36d98`, `ba0f857bc43b95ce`,
`02fb846290642261`, `4d57bb4f05ecc3b3`, `4329913878f62787`, `3d0afdaa03d87d5c`,
`7aec8f6ed9928caf`, `f82426fb0a099676`), your hand-off of 2026-10-29, "An account holds its
currencies: every route names an account and a currency code; holders are gone": its part on
accounts, transactions, bank lines and the dashboard. The terminal app catches up in seven parts;
statements, the statement PDF upload, the bank download and the sheet import are part 2, its live
contract suite parts 3 to 5, its redrawn screens parts 6 and 7.

## Done when, checked

All checked on 2026-10-30 against the practice engine, on a practice account holding soles and
dollars.

- **"The TUI has read up to `f82426fb0a099676` and says so":** worked. The app's contract
  snapshot is at `f82426fb0a099676`, recorded on 2026-10-29, and its version check reads the
  same version served.
- **"A transaction names an account and a currency it holds; one in a currency the account does
  not hold is refused, nothing written, and the app shows why":** worked. Every transaction
  write sends `account_id` and `currency_code`: a create and each batch item, a move on the edit
  form and a bulk move in the ledger (only the key that changed), and the whole-line write.
  `CURRENCY_NOT_HELD` shows in your words alone, nothing written, on a batch item's
  `currency_code`, on a move sending `account_id` alone, and on a bulk move sending both.
  Logging on the account's dollars, and moving a transaction from its soles to its dollars out
  of a draft statement, saved and read back in dollars.
- **"Archiving, unarchiving, turning into a person and back, and deleting act on the account,
  all its currencies at once":** worked at the level of the routes. The accounts list shows one
  row per account and currency for now; archive, unarchive, make-person and make-account, and
  delete send one call with the account's id from either row, and archiving from the dollars row
  read both currencies back archived. A new bank account and a new person, each in one
  currency, were created with `POST /accounts` and `currencies`.
- **"No request in the TUI sends a `/holders` route, `POST /accounts/{id}/move`, `?holder_id=`
  or a per-currency id":** worked for the transaction, bank-line, dashboard and account calls.
  The statement and import calls still send the old shapes until part 2.

## Contract problems found

- **Can an account hold no currency?** The account response's `currencies` rule says "`[]` for
  an account holding none", while `LAST_CURRENCY` and `DELETE /accounts/{id}/currencies/{code}`
  say "an account always holds at least one currency". The terminal app keeps a row for an
  account read with `[]` so it can still be found and deleted. Raised as the ask "Say whether an
  account can hold no currency, and what a client does with one".

## Asks this closes

None. "An account holds its currencies: the holder becomes the account, and each account becomes
one of its currencies" closes with part 7.
