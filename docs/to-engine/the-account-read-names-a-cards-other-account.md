# The account read names a card's other account

Raised 2026-10-25.

## Why

A card is two bank accounts under one statement code, one in soles and one in dollars, and a
card statement is created on both in one write: `POST /v1/reconciliations` with `twin` naming
the other account. So a client that offers "new card statement" on a card account must know
which account is the other one.

Nothing in the account read says so. A client today reads the whole account list and works the
pair out itself: group the live, non-person accounts by `statement_code`, keep the codes held by
exactly two of them, and call each the other's partner. That is the engine's own rule
("Shared only across currencies", what `twin` accepts, an archived account refused as a twin)
copied into every client, where it drifts as soon as the rule moves, and it needs the whole
list to answer a question about one account.

## The ask

`AccountResponse` (on `GET /v1/accounts`, `GET /v1/accounts/{id}` and every write's answer)
names the account's card partner: the other live account the engine would take as `twin` on
`POST /v1/reconciliations` for a reconciliation on this one. For example a
`statement_partner` field holding the other account's `id`, the name the engine shows for it and
its `currency_code`, or its id alone; the shape is the engine's call. It is `null` when there is
none: no statement code, no other live account holding the code, a person, or an archived
account on either side.

## Done when

- Each account of a card reads the other as its partner, on the list and on the read by id.
- An account with no code, a code no other live account holds, a person, and an archived account
  read `null`, and so does the live account whose partner is archived.
- A code change, a cleared code, an archive, an unarchive and a delete move the field on the
  next read of both accounts.
- The contract states the field, when it is `null`, and that it names exactly the account
  `twin` accepts.

## What this client removes once it lands

The client-side grouping of accounts by statement code that finds a card's partner for the new
card statement form, and the whole-list read it needs; the form reads the partner from the
account instead.
