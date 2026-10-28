# Say what a client does with a flagged line on a card with a statement code

Raised 2026-10-27.

## Why

When a statement completes, the engine flags the lines in no statement on the card's days, and
the complete operation tells every client what the owner does with one (contract: POST /v1/statements/{statement_id}/complete, "What a client does with a flagged line"):

> It belongs to this statement: revert, assign it (*Assigning transactions*), complete again.

On a card with a statement code, that path is always refused:

- "A line assigned from none, or created in the statement, arrives with no place"
  (contract: "Statements", "A line's place in its statement stays only while the line stays in it"),
  and "A line assigned after the upload has no place until the paper is uploaded again"
  (contract: "Statements", "Nothing renumbers on its own").
- "No route sets the order by hand" (contract: "Statements", "The bank's paper sets the order").
- Completing is refused until "every live bank line in it holds a place" (contract: POST /v1/statements/{statement_id}/complete, "On a card with a statement code, the statement must be fully ordered"),
  with `422 STATEMENT_NOT_ORDERED`.

So a client that follows the advice word for word gets `STATEMENT_NOT_ORDERED` on the third
step, and its message ("Upload the bank's statement (POST /statements/import), which sets the
order.") points somewhere the advice never mentions.

On such a card the upload decides which lines are the statement's. A flagged line the paper
prints was left out because it does not match the paper's row: usually its day, sometimes its
amount. What works is to fix the line, revert the statement and upload the paper again, which
then matches it. A flagged line the paper does not print does not belong to this statement.
The contract says neither.

## The ask

State the path per kind of card in "What a client does with a flagged line": on a card with no
statement code, as today; on a card with a statement code, what the owner does with a line that
belongs to this statement (for example: fix the line so it matches the paper's row, revert, and
upload the paper again), with the near misses of the upload's answer named as the likely cause
where they apply.

## Done when

- The complete operation's advice names the path for a card with a statement code, and a client
  following it word for word completes the statement with the line in it.
- The advice and the `STATEMENT_NOT_ORDERED` message no longer point different ways.

## What this client removes once it lands

Its own wording of the path for a card with a statement code, on the screen listing a close's
flagged lines; it shows the engine's advice instead.
