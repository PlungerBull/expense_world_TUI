# A read lists the supported currencies

Raised 2026-10-29.

## Why

Since `f82426fb0a099676` an account holds its currencies, and a client picks a currency in many
places: a new account's currencies, adding a currency to an account, a transaction's currency,
the ledger's currency filter, a statement's balances. Every one of those pickers needs the list
of currencies the engine takes.

The contract states that list only in prose, inside refusal rules ("a supported currency (`PEN`
or `USD`)"), and no route returns it. So each client keeps its own copy: the terminal app has a
hard-coded `PEN, USD`, and the web and iPhone apps would each write theirs. When the engine takes
a third currency, every copy is wrong until someone edits it, and a client offers a currency the
engine refuses, or hides one it takes, with nothing telling it so.

## The ask

A read that returns the currencies the engine takes, in the order a picker should show them, for
example `GET /currencies` answering `[{"currency_code": "PEN"}, {"currency_code": "USD"}]`, or
the same list on a read every client already makes at start (such as `GET /auth/me`). Each entry
could also carry what a client needs to show amounts in it, such as its number of decimal places,
since the contract states every amount in cents with no per-currency exponent today.

## Done when

- One read returns the supported currencies, in a stated order, and the contract describes it.
- The refusals that speak of "a supported currency" point at that read.

## What this client removes once it lands

The terminal app's own list of supported currencies and the rule that it must be edited by hand
whenever the contract admits a new currency; its currency pickers read the list from the engine.
