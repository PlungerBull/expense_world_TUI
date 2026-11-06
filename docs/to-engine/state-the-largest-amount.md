# State the largest amount the engine takes, and refuse past it everywhere

Raised 2026-11-05.

## Why

The contract states no bound on an amount. `amount_cents` and every other money field is a
signed whole number of cents of any size, and `OUT_OF_RANGE` ("a number too small or too large")
names no limit for money. A client therefore cannot tell a typed amount that is too big from a
real one. For example, `1e5000` is a finite number, and in cents it has over 5,000 digits.
The terminal client accepts it, and its screens then crash printing it. The same amount can
come in a spreadsheet or a bank file, which the client sends to the engine whole.

Any limit a client picks for itself is a copy of a money rule that belongs to the engine, and
four clients would pick four different limits. The bound has to be the engine's, stated once in
the contract.

## The ask

- The contract states the largest absolute amount, in cents, that any money field takes: a
  transaction's or a part's `amount_cents`, a statement's balances, an opening balance, and any
  other amount a client sends. It states it once, by name, and as `maximum` / `minimum` on
  every such field in the schema, so a client can read it.
- Past that bound, every write refuses with `422` on the field (`OUT_OF_RANGE`), naming the
  bound in the message. This covers the bulk and batch writes too, by item.
- Every file the engine reads (the owner's spreadsheet, a bank download, a statement PDF)
  refuses a row whose amount is past the bound, naming the row, before anything is written. Its
  dry run says so too.
- No answer ever carries an amount past the bound.

## Done when

- `GET /openapi.json` names the bound in one place, and every money field's schema carries it
  as `maximum` / `minimum`.
- A transaction, a part, a statement balance and an opening balance one cent past the bound are
  each refused with `OUT_OF_RANGE` on that field. At the bound itself they are accepted.
- A spreadsheet, a bank download and a statement PDF with one row past the bound are refused,
  naming that row, on the dry run and on the apply, and nothing is written.

## What this client removes once it lands

The client stops letting an amount of any size reach its screens. It refuses an amount past the
contract's bound where it is typed, citing the contract, and shows the engine's refusal for a
file. The crash on printing a huge amount goes away.
