# Footers that fit the screen

What [every screen's frame](../decisions.md) (done on 2026-11-04) turned up: once `pgup Prev`
shows only past a list's first page, some footers outgrow the terminal on page 2 and after, and
their last key is cut.

**Status: drafted on 2026-11-04 for the owner to rewrite or approve; one question, with a
mockup to draw before you pick.** It waits on no other spec. When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

At 80 columns, Manage's footer draws `d Delete` as `d Del` whenever `pgup Prev` shows. At 140
columns, the ledger's footer loses `s Edit` the same way. The Statements screens already draw
their footer in a tighter spacing when it would not fit, so their last key is never cut; Manage
and the ledger do not.

## What it must do

1. **No footer cuts a key,** at 80 columns and wider, on any page, as question 1 picks.

## How the owner knows it is done

1. At 80×24, Manage on page 2 shows `d Delete` whole; at 140×24, the ledger on page 2 shows
   `s Edit` whole.
2. The unit suite passes.

## Questions for the owner

### 1. A footer too wide for the screen? (mockup to draw)
- **A.** Every screen draws its footer in the tighter spacing the Statements screens use, only
  when it would not fit.
- **B.** The keys that don't fit leave the footer; `?` still lists them all.

**Recommended:** A, because it is already how the Statements screens read, and no key goes
missing.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
