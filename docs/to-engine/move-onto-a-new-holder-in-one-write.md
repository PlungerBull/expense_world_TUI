# Move an account onto a new holder in one write

Raised 2026-10-28.

## Why

Unpairing is two writes today, as your hand-off "An account moves between holders, a holder is
made and unmade with its accounts, and a holder's bank lines list in one read" gives it:
`POST /holders` with no `accounts`, then `POST /accounts/{id}/move` onto it. When the move is
refused (`STATEMENT_KEEPS_ACCOUNT`, `ACCOUNT_ARCHIVED`, or a write at the same moment that makes
it so), the new holder stays, holding nothing, and the client has to delete it with a third write
that can fail too. Your own "Done when" asks that no client flow leave an empty holder behind;
with two writes, every client has to clean up after a refused move, each in its own way.

## The ask

Let the move create the holder it moves onto, in the same write: `POST /accounts/{id}/move` taking,
in place of `holder_id`, a `holder` object shaped as the `POST /holders` body without `accounts`
(`id`, `name`, optional `statement_code`). All or nothing: a refused move creates no holder, and a
refused holder (a taken name, code or id) moves nothing; a refusal of the holder is keyed
`holder.<field>`. The holder the account leaves is deleted when left empty, as today. Idempotency
covers the whole write.

## Done when

Unpairing an account is one write; a refused unpairing leaves no holder behind, and
`GET /holders` lists exactly what it did before.

## What this client removes once it lands

The terminal app's unpairing sends one write instead of two, and needs no step to delete a holder
left empty by a refused move.
