# Say whether an account can hold no currency, and what a client does with one

Raised 2026-10-30.

## Why

Contract `f82426fb0a099676` says two things about an account's currencies that do not fit
together:

- the account response's **`currencies`** rule: "one entry per live currency of the account …
  `[]` for an account holding none", and the change-log entry for `07475793a38b47b4` says a
  holder holding none reads `[]`;
- the `LAST_CURRENCY` reason and `DELETE /accounts/{id}/currencies/{currency_code}`: "an account
  always holds at least one currency", so the last one is never removed ("What an account is",
  "Its currencies", says the same), and `POST /accounts` needs at least one.

The second rule stops a new account from ever holding none, but nothing says whether an account
carried over from the holder model, or any other path, can still read `[]`. A client cannot tell
which to believe, so each client has to decide on its own what to draw for an account with
`currencies: []`. If a client lists accounts one row per currency, such an account vanishes from
it, cannot be archived, edited or deleted, and still holds its name and its statement code, so a
new account under that name is refused as `NAME_EXISTS` with no screen able to show why.

## The ask

Make the contract say one thing:

- **either** no live account ever reads `currencies: []` (the migration gave every account at
  least one currency, and no route can leave it with none), and the `currencies` rule drops
  "`[]` for an account holding none";
- **or** an account can read `[]`, the contract says how one comes about, and what a client may
  do with it (rename, archive, delete, add a currency).

## Done when

- The `currencies` rule and "an account always holds at least one currency" agree.
- If `[]` stays possible, the contract names the routes that act on such an account.

## What this client removes once it lands

If no account can hold none: the terminal app's special row on its accounts list for an account
holding no currency (the account's name alone, with no currency and no balance), kept today only
so that such an account can still be found and deleted.
