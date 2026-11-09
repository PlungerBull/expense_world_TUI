# A loose-lines refusal names its lines by id, in a field a client reads

Raised 2026-11-08.

## Why

`LOOSE_LINES_ON_SEALED_DAYS` asks the owner to resolve each line before closing, so every client
lists those lines with a way to delete, fix or assign each one. Today the lines are named only in
prose: the field message of `POST /statements/import` spells `GET /bank-lines?ids=<id>,<id>,…`
inside a sentence, and the message of `POST /statements/{id}/complete` names
`GET /bank-lines?unassigned_in_period_of=<id>&sort=statement`, which also lists flagged lines on
days that stay open, with nothing in each line saying which of the two it is. A client would have
to read ids out of a sentence, or work out for itself which days the close seals. Both are engine
rules re-implemented, subtly wrong, in every client.

## The ask

1. **Both refusals carry the ids of the lines they count,** on `POST /statements/import` (dry run
   and apply) and `POST /statements/{id}/complete`: the bank line ids, in a documented place of the
   error body a client reads without parsing a message, in the statement's order (date, then the
   line's own order).
2. **Exactly the lines that refuse,** never the flagged lines on days that stay open.
3. **The same cap as today's message:** past 200 lines, the first 200 and the full count, so
   `GET /bank-lines?ids=` takes them in one read.
4. The contract states the field, its shape and the cap, on both routes and on the error body.

## Done when

- A close refused for one loose line answers its id in that field, and a flagged line on the
  statement's open last day is not in it.
- An upload's dry run refused for two loose lines, one of them taken out of the draft, answers
  both ids.
- A refusal for 201 lines answers 200 ids and the count 201.

## What this client removes once it lands

Nothing is built yet. Without it, the screen that lists the loose lines would read ids out of the
message text, or list the period's lines and guess which are sealed; with it, the client reads the
ids and lists exactly those lines.
