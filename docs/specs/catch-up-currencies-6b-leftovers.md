# What part 6's leftovers turned up

What part 6's leftovers, the main views' words and the Accounts list's one-write guard (done on
2026-11-02), turned up while they ran.

**Status: both questions picked on 2026-11-02 in
[expense-world-staged-list-and-operation.html](../mockups/expense-world-staged-list-and-operation.html);
the tasks wait on the owner's approval.** It waits on no other spec. When done, the why moves
to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

- **The LOG bar's staged list cuts cells at 80 columns** with ordinary names, such as an
  account called `BCP Signature PEN`, though [tui.md](../tui.md) §5 says everything is correct
  at 80×24. With a long title the `cur` column shrinks to nothing at 80 columns, and at 60
  columns even with short titles. The list cut cells before it had a `Cur` column too. The
  ledger keeps its narrow columns whole and lets title and tags give way.
- **The Reconciliations "no batch" form's OPERATION line has no `changes every part of the
  transaction` note,** though every part of the line shares its operation as it shares the
  date, title, account and currency, whose lines carry the note on a line of two parts or more.

## What it must do

1. **The LOG bar's staged list reads whole at 80 columns:** when a row does not fit, the title
   and tags give way, as in the Transactions list, and the date, amount, currency, account and
   category stay whole.
2. **The "no batch" form's OPERATION line** carries the `changes every part of the transaction`
   note on a line of two parts or more, as the date, title, account and currency lines do.

## How the owner knows it is done

1. At 80 columns the staged list shows each row's amount, currency and account whole.
2. On a line of two parts or more, the OPERATION line's hint ends in `changes every part of the
   transaction`; on a line of one part it does not.
3. The unit suite and the drift check pass.

## Questions for the owner

1. **The staged list at 80 columns** (pane 1 of the mockup): **picked A** — when a row does not
   fit, the title and tags give way, as the ledger's do; the date, amount, currency, account and
   category stay whole.
2. **The OPERATION line's note** (pane 2 of the mockup): **picked A** — it shows `changes every
   part of the transaction` on a line of two parts or more, as the date, title, account and
   currency do.

---

## Tasks

All done on 2026-11-02; the spec's acceptance check and doc sweep follow.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
