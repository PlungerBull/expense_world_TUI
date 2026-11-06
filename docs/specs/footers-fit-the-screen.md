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

Drafted on 2026-11-06; for the owner to approve.

1. **The fitting footer leaves out the keys it still cannot fit** (question 1). It tightens its
   spacing first, as now; when the tightened keys are still wider than the screen, whole keys
   leave from the end until the rest fit. A key left out still works, and `?` still lists it.
   Passes if: at 140×24 the ledger on page 2 is tightened, shows `s Edit` whole and leaves
   `d Delete` out; on page 1 at 140×24 it is tightened and shows `d Delete` whole; at 80×24 a
   footer that fits tightened, such as Manage's on page 2, loses no key; `?` on the ledger past
   page 1 still lists `d Delete`; no footer line ends in part of a key; [tui.md](../tui.md) says
   how a footer too wide for the screen reads.
2. **Every screen's footer is the fitting one** (what it must do, 1). The list screens' shared
   base and the screens that draw Textual's own footer (Home, the forms, the questions, the LOG
   bar, `?`, the bank import, the bulk pick) take the fitting footer. Passes if: at 80×24
   Manage on page 2 shows `d Delete` whole (done check 1); a guard test fails on any screen that
   draws Textual's own footer; [tui.md](../tui.md) no longer names the fitting footer as the
   Statements screens' alone.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
