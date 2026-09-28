# `POST /v1/transactions` states its own non-zero amount rule

Raised 2026-09-27 by the CLI client.

## Why

A transaction's `amount_cents` must not be zero. The contract says so for
`PUT /v1/transactions/{transaction_id}` ("`amount_cents` is non-zero"), for the opening balance
and for the import, but the description of `POST /v1/transactions` itself does not. A client
reading the create operation alone learns the rule only indirectly, through PUT's "the value
rules match `POST`" or the made-up example in "Error format". Clients that check the contract
per operation (as every client should) can miss it, and the error message a zero amount
returns is not published anywhere.

## The ask

The `POST /v1/transactions` description states that `amount_cents` is non-zero and what the
`422` for a zero amount looks like (the field it names and its message or reason), in the same
words PUT uses.

## Done when

- `POST /v1/transactions` in `/openapi.json` states the non-zero rule and its `422`.
- The change is in the contract's change log.

## What the CLI removes once it lands

Nothing in code. Its comment on the edit form's non-zero check cites the create operation
instead of the edit one.
