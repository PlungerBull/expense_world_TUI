# Tell us which of the terminal app's seven specs for cards and statements your current changes affect

Raised 2026-10-27.

## Why

The terminal app has recorded contract `e06456a20aca6e4c` and planned your hand-off "A card is
its own object, its statement is one object for the whole card, and a closed statement's review
list is readable in full" into seven specs, run in this order. We know you are still changing the
engine. Before we build, tell us whether any of those changes touches what a spec relies on, so
we do not build on a route or field that is about to move.

1. **The app's reads and writes on the new routes.** Nothing the user sees changes. It relies on:
   `card_id` on accounts; `statement_id` and `left_statement` on `PUT /transactions/{id}`,
   `PUT /bank-lines/{id}` and the transaction and bank-line filters; `GET /cards`,
   `GET /statements?card_id=` and `GET /statements/{id}`; the bank download's account list built
   from each card's `account_ids`; `POST /statements/import` and its answer (`balances`,
   `creates`, `statement_id`, `statement`, `CARD_ACCOUNT_NOT_ON_PAPER`).
2. **The statement screens on the new routes.** Nothing the user sees changes. It relies on:
   `POST /statements` with `balances` per account; `PUT /statements/{id}` for the ending
   balances; complete, revert and delete; `warnings` and `coverage_gap` on each balance; the
   review list (`GET /bank-lines?unassigned_in_period_of=<id>&sort=statement` and its count);
   the refusal messages now speaking of statements. The message for deleting a bank line in a
   completed statement is read from the engine, since the contract does not print it.
3. **The live tests' foundation.** It relies on: cards and accounts made with `POST /cards` then
   `POST /accounts`; a statement's life; `CARD_ACCOUNTS_MISSING`, `DIFFERENCE_NOT_ZERO`, a
   currency with no movement closed by hand, an archived card's statements frozen; codes on
   `POST` and `PUT /cards`; `GET /statements/{id}/statement-order`, read only.
4. **The live tests for the upload, bank lines and people.** It relies on: the upload tested
   against `GET /statements/samples` and the stated paper layout; the review list; moves with
   `statement_id`; `statement_id` on `POST /transactions` refused as `UNKNOWN_FIELD`; the card
   routes and their refusals; `make-account` with `card_id`; `make-person`'s refusals; archiving
   through `POST /cards/{id}/archive`, and `ARCHIVE_THE_CARD` on a bank account's own route.
5. **The sheet import's counts line.** It relies on: `counts.split_rows`; a malformed cursor
   answered `422 INVALID_CURSOR` on `GET /transactions`, `/activity`, `/bank-lines` and
   `/exchange-rates/history`.
6. **Cards in the app** (screens, waiting on the owner's picks). Creating, editing and archiving
   cards; the statement code on the card; `make-account` onto a card; pairing and unpairing
   through your proposed move of an account to another card; the sheet import's create step
   giving each new account a card of its own.
7. **A card's statement on one screen** (screens, waiting on the owner's picks). Both currencies
   on one screen; a currency with no movement closed by hand; flagged lines shown any time from
   the review list; a move to the card's other account staying in its open statement.

Handed over beside this note: our answer on moving an account to another card, and four asks:
"Create a bank account and its own card in one write"; "Delete a card with its last account, so
no client leaves an empty card behind"; "List a card's bank lines in no statement in one read";
"Say what a client does with a flagged line on a card with a statement code".

## The ask

For each of the seven specs, say whether a change you have made after `e06456a20aca6e4c`, or are
making now, affects what it relies on, and what changes. A change already shipped comes as a
hand-off covering every version after `e06456a20aca6e4c`, as usual.

## Done when

- The engine coders have answered for each of the seven specs: unaffected, or affected and how.
- Any contract version after `e06456a20aca6e4c` has its hand-off.

## What this client removes once it lands

Nothing. This client may start spec 1, which relies only on routes and fields shipped in
`e06456a20aca6e4c`, before you answer, and builds each later spec on your answer.
