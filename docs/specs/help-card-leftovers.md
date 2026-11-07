# The `?` card's leftovers

Two small things you see on the `?` card, found while the small fixes on screen ran (done on
2026-11-07) and not fixed there.

**Status: drafted on 2026-11-07; one question open; for the owner to answer and approve.** It
waits on no other spec. When done, the why moves to [decisions.md](../decisions.md) and this
file is deleted.

---

## Why

1. **The card's side gutters show the screen behind it.** With the card open over the ledger,
   the ledger's own rule peeks out as a one-cell `─` on each side of the card's frame (at 80×24,
   columns 3 and 76 of row 4; the wide card the same at columns 3 and 136); over the "no
   statement" list, bits of the Statements screen show there (`St`, `▸`, `In`, `!`). Every
   mockup of the card draws those gutters blank.
2. **The Statements account list's card lists page keys that do nothing.** With the panel
   closed, the account list's card lists `pgdn Load the next 10 rows under these`, `pgdn Next
   page` and `pgup Previous page`; none of them works there and the footer shows none of them.
   A card lists a key only while it works ([decisions.md](../decisions.md) "The `?` card shows
   whole and lists only keys that work"), so this one needs no question.

## What it must do

Point 1 as its question below picks; point 2 lists the page keys only while they work, as the
statements panel's card already does.

## How the owner knows it is done

1. With the `?` card open over the ledger at 80×24 and at 140×24, and over the "no statement"
   list at 80×24, the gutters beside the card show as picked.
2. With the panel closed, the Statements account list's card lists no `pgdn` or `pgup` row
   while those keys do nothing there.
3. The unit suite passes.

## Questions for the owner

1. **The gutters beside the `?` card?** Pick in
   [the mockup](../mockups/expense-world-help-card-gutters.html):
   - **A.** Blank, as every mockup draws them: the card covers what is behind it right up to
     its frame.
   - **B.** As today: the screen behind shows through, one cell each side.
   **Recommended:** A. The card reads as one block, and nothing half-drawn shows beside it.

---

## Tasks

Drafted once the question is answered.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
