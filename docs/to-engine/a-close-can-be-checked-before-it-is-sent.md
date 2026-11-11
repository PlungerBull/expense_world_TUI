# A close can be checked before it is sent

Raised 2026-11-11.

## Why

`POST /statements/{id}/complete` is refused `LOOSE_LINES_ON_SEALED_DAYS` while a line in no
statement sits on a day the close would seal, and every client lists those lines so the owner can
deal with each one. After the owner fixes a line (moves it to another day, changes its amount),
only the engine knows whether it still blocks the close. A statement PDF's upload answers that
with its dry run; a close has none, so the only way to ask is the close itself, which completes the
statement if nothing is left. A client would otherwise keep a fixed line listed until the owner
closes again, or work out for itself which days the close seals: an engine rule re-implemented.

## The ask

1. **`POST /statements/{id}/complete` takes a dry run,** as `POST /statements/import` does: the
   same validation and the same refusals, `details` included, with nothing written, and on
   success an answer saying the close would go through.
2. The contract states it on the operation, beside its refusals.

## Done when

- A dry-run close of a statement with one loose line is refused `LOOSE_LINES_ON_SEALED_DAYS`
  with that line's id in `details`, and nothing changes.
- Once the line is moved off the sealed days, the same dry run answers that the close would go
  through, and the statement is still a draft.

## What this client removes once it lands

Its leftover-lines screen for a close keeps a fixed line listed until the owner closes again;
with a dry run, a fix re-checks at once and a line that no longer blocks leaves the list, as on
the upload's screen.
