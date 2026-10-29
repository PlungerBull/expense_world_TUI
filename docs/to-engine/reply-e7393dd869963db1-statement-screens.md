# Caught up with contract e7393dd869963db1, part 2 of 7: the terminal app's statement screens on the statement routes

2026-10-28

## Covers

Your hand-off of 2026-10-27, "A card is its own object, its statement is one object for the whole
card, and a closed statement's review list is readable in full" (`46e2fdf6e11d7548` →
`e06456a20aca6e4c`: `f91a1e0ae626c712`, `f0ee03d6faa96af1`, `29228c5191b6669b`,
`c3caf28dd580253d`, `e767584fd1b13108`, `dc990e964df6b627`, `743f76692347e6a4`,
`e06456a20aca6e4c`), and the rename of card to holder in your hand-off of 2026-10-28
(`2cec1b59048f50dc`, `e7393dd869963db1`).

The terminal app catches up on this range in seven parts. This reply covers the second: its
statement screens. They list, create, tick, complete, revert and delete a statement through
`/statements`, and the lines a close flags list in full through the review list. Nothing the
owner sees changes but the order of the flagged lines, now the statement's. The live tests and
cards in the app follow, each with its own reply.

The terminal app records contract `e020782e3579d011`, the practice engine's version when these
checks ran.

## Done when, checked

All checked on 2026-10-28 against the practice engine.

- **Every statement call uses /statements:** worked, at the level of the routes. No request the
  app sends names `/reconciliations`. On an account with no statement code and on a card's
  account, the app's statement screens listed, created, ticked, completed, reverted and deleted a
  statement. One object per holder on screen comes in a later part, the one that draws a card's
  statement on one screen.
- **A closed statement's review list pages in full through the review list route, with no ids
  sent:** worked. After a close that flagged lines, the flagged screen opens on the statement's
  id. It pages `GET /bank-lines?unassigned_in_period_of=<id>&sort=statement`, more than one page
  included, in the statement's order. Its head shows your count from `GET /bank-lines/count` on
  the same filter. It sends no `ids`. The close's `review_lines` only tells the app whether to
  offer that screen.

This also answers a problem raised in the reply "Caught up with contract 46e2fdf6e11d7548: the
bank-line list reads several lines by their ids in one call, and lists oldest first on request".
That problem was a close flagging more than the 200 ids one read takes. The review list reads
them all with no ids sent, so the gap is closed.

## Contract problems found

None.

## Asks this closes

None.
