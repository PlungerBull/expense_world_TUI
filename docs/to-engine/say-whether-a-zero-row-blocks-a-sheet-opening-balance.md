# Say whether a zero-amount row dated earlier stops a sheet row being the opening balance

Raised 2026-11-03.

## Why

Contract `f82426fb0a099676`, `POST /v1/transactions/import-sheet`, "Opening balances": a row whose
`CATEGORY` reads exactly `SALDO INICIAL`, with an amount other than zero, "and with no row of the
same currency of the same account … dated before it", is that currency's opening balance.

The same operation skips every row whose amount is zero (outcome `skipped`). The rule does not say
whether such a skipped row counts as "a row … dated before it". Take a sheet whose first row in an
account's PEN is a `SALDO INICIAL` of `0.00` on 2 January and whose next is a `SALDO INICIAL` of
`1,000.00` on 5 January. Read one way, the 5 January row is the opening balance. Read the other,
it is an ordinary row under the category the table gives `SALDO INICIAL`, and the account has no
opening balance in PEN.

The owner reads it the first way: each currency's opening balance is its first `SALDO INICIAL`
row of a non-zero amount. A sheet kept by hand can easily start a currency at zero.

## The ask

Make the rule state which reading holds. The owner's reading is that a skipped zero-amount row
never counts as a row dated before it. If the engine does otherwise today, say so and why, so the
owner can decide.

## Done when

- "Opening balances" says whether a zero-amount row dated earlier stops a later `SALDO INICIAL`
  row being the opening balance.

## What this client removes once it lands

Nothing. This client's live test of a sheet opening balance leaves zero-amount rows out because
the rule is unclear. Once the rule is clear, that test adds the case.
