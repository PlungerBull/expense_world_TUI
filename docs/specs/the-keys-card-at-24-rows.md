# The `?` card at 24 rows

What [footers that fit the screen](../decisions.md) (done on 2026-11-06) turned up: a footer too
wide for the screen leaves keys out, and says `?` lists them, but at 24 rows the `?` card itself
is cut off at the bottom.

**Status: drafted on 2026-11-06; question 1 open; for the owner to approve.** It waits on no
other spec. When done, the why moves to [decisions.md](../decisions.md) and this file is
deleted.

---

## Why

At 140×24 the ledger's `?` card stops at `m Move the selection to a currency`: `s Edit` and
`d Delete` fall below the bottom of the screen, and the card does not scroll. Past the ledger's
first page at 140 columns, `d Delete` is also left out of the footer, so the key shows nowhere
on screen. At 80×24 the ledger's footer holds 8 of its 14–15 keys, so most of its keys can only
be found on the card. The "no statement" list's card already clips its last line on a 30-row
terminal ([todo.md](../todo.md) "The "no statement" `?` card lists keys that don't apply").

## What it must do

1. **Every key a screen has can be read on its `?` card** at 80×24 and wider, as question 1
   picks.

## How the owner knows it is done

1. At 140×24 and at 80×24, the ledger's `?` card shows `s Edit` and `d Delete`, as question 1
   picks.
2. The unit suite passes.

## Questions for the owner

1. **A `?` card taller than the screen?** The ways to show it whole (the card scrolls, or it
   lays its keys out to fit) are drawn as a mockup in [mockups/](../mockups/) for you to pick
   from before anything is built.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
