# The sheet import suggests the accounts it is missing and makes the ones the user confirms, with its names and rows, in one write

2026-11-13

## Why

The sheet import never makes an account (contract: POST /v1/transactions/import-sheet, "Names"),
so before the owner's one import onto an empty ledger every account the sheet names is made by
hand, and each bank account's sheet name is then given its id. The categories and hashtags are
made by a step of their own before the rows. Every client would repeat those steps.

The engine's answer to "The engine says why its bank list is closed" says the rule comes from
"an account is never made as a side effect of another write", and that an account the user
confirms by name in the request is no side effect. The dry run already lists every sheet account
name with its rows and currencies, and a proposed match the user confirms.

## The ask

- **A suggestion for each sheet account name no account holds,** in the dry run, beside today's
  proposed match: a kind (`bank`, `person`, `cash`), a bank (from the catalogue's codes and other
  names, and the user's own banks, as the ask "A bank account is at a bank from the engine's
  catalogue or one the user adds, and each bank says what the engine can read for it" gives
  them), a last 4 when the name holds four digits, and the currencies its rows use. **An unsure
  guess is `null`, never a default:** `ALEJO` gets no kind. The guessing rules are written in the
  contract, so every client shows the same suggestion.
- **The import makes only what its request lists,** and nothing else: the accounts to make (each
  with its client id, kind, bank, last 4, a person's name, its currencies, an optional statement
  code), the categories and hashtags to make, each sheet name given its id, and the rows, in one
  write. A refusal leaves nothing made. The first `SALDO INICIAL` row of a made account's currency
  is its opening balance, as for an account that exists.
- **An account can be made archived:** the request marks it, and it is archived once its rows are
  in, for a closed account that only holds history.
- The dry run of such a request counts what the write would make and import, so the client shows
  it before the user sends it.

## Done when

- A dry run on an empty ledger lists each sheet account with its suggestion: a name holding
  `IBK` suggests a bank account at Interbank, a name holding `BCP` and four digits suggests a BCP
  account with that last 4, `ALEJO` suggests nothing.
- One apply makes two bank accounts, one person, one archived account, three categories and two
  hashtags, and imports every row onto them; each account's balance in each currency is the
  sheet's total.
- An apply refused for any row leaves no account, category or hashtag made.

To pick the guessing rules, the engine coders need the account names the owner's sheet uses; the
owner gives them those directly.

## What this client removes once it lands

Making every account by hand before the import, the `--account-name` option and the sheet names
it saves in the config, the separate `--create-names` step, the "make it in the app" lines in the
dry run, and archiving the closed accounts by hand after the import.
