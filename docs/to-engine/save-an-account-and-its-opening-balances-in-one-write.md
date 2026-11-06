# Save an account's changes and its opening balances in one write, whole or not at all

Raised 2026-11-06.

## Why

Editing an account and its opening balances takes several writes today: one `PUT` for the
account's own fields, then one write per currency's opening balance (a `POST` to create it, a
`PUT` on its transaction to change it, a `DELETE` to remove it). A client must send them in
order, track which landed, and tell the owner how each part ended. When one is refused the
account is left half-saved: its name changed, its USD opening balance set, its PEN one not.

Every client will rebuild that chain and its partial-save wording, each a little differently,
with an extra round trip per currency. A save the owner makes as one action should land as one.

## The ask

- One write that takes an account's changes (name, colour, statement code, and whatever fields
  the account carries) together with, per currency it holds, its opening balance to create,
  change or remove (amount, date), keyed by currency.
- It applies all of it or none of it. A refusal names each field it refuses, keyed so the
  client can point at the line (the account field, or `opening_balances.<currency>.<field>`),
  and nothing is written.
- It is idempotent on the client's key, as every write is.
- The answer carries the account as it now stands, with each currency's opening balance.

## Done when

- One request changes an account's name and sets, changes and removes opening balances in
  three currencies, and a read shows all of it.
- The same request with one opening balance dated in the future is refused on that currency's
  date, and a read shows the account and every opening balance unchanged.
- Replaying the request with the same idempotency key changes nothing more.

## What this client removes once it lands

The account form's chain of writes (the account first, then one write per currency), its
tracking of which parts landed, and its partial-save messages ("The account's changes are
saved. The PEN opening balance is not", and the one that lists each part after you leave the
form). A save becomes one write that lands whole or is refused whole.
