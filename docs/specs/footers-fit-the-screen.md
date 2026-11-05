# Footers that fit the screen

What [every screen's frame](../decisions.md) (done on 2026-11-04) turned up: once `pgup Prev`
shows only past a list's first page, some footers outgrow the terminal on page 2 and after, and
their last key is cut.

**Status: drafted on 2026-11-04; question 1 answered on 2026-11-05 from
[expense-world-footers-fit.html](../mockups/expense-world-footers-fit.html); for the owner to
approve.** It waits on no other spec. When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

At 80 columns, Manage's footer draws `d Delete` as `d Del` whenever `pgup Prev` shows. At 140
columns, the ledger's footer loses `d Delete` on page 1, and past page 1 it cuts `m Currency` and
loses `s Edit` and `d Delete`; tightening alone leaves it 144 wide there. The Statements screens already draw
their footer in a tighter spacing when it would not fit, so their last key is never cut; Manage
and the ledger do not.

## What it must do

1. **No footer cuts a key,** at 80 columns and wider, on any page, as question 1 picks.

## How the owner knows it is done

1. At 80×24, Manage on page 2 shows `d Delete` whole; at 140×24, the ledger on page 2 shows
   `s Edit` whole.
2. The unit suite passes.

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | A footer too wide for the screen? | C: the spacing tightens first, as on the Statements screens; keys that still do not fit leave the footer, and `?` lists them all. No key is ever cut mid-word (2026-11-05). |

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
