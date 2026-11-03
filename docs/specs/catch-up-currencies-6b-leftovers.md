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

1. **The staged list's title and tags give way.** In `staged_table`
   ([log_bar.py](../../expense/tui/screens/log_bar.py)) the title and tags become Rich ratio
   columns, 3:2 as the ledger's Title and Hashtags are (`CursorList(flex=…)`, [tui.md](../tui.md)
   "The ledger's cells fill that width"); the marker, date, amount, `cur`, account and category
   take their natural width first. Passes if: a test renders the list through
   `helpers.render_text` at 74 columns (an 80-column terminal less `#staged`'s padding) with the
   rows of pane 1 A — an account named `BCP Signature PEN`, a title longer than its column — and
   every row's marker, date, amount, `cur`, account and category show whole with no `…`, while
   the long title ends in `…`; a second test at 114 columns with a title of 100 characters shows
   the same; the existing LOG bar tests stay green; tui.md's paragraph on the staged table's
   columns says which give way. Reviewer: the ratios match the ledger's, no width is
   hard-coded, cells still go through `list_cell`.
2. **The OPERATION line says it changes every part.** On the "no batch" Edit form
   (`BankLineEditFormScreen` in [edit_form.py](../../expense/tui/screens/edit_form.py)), with two
   parts or more, the OPERATION line's hint ends in ` · changes every part of the transaction`,
   the note in the accent, as on date, title, account and currency. Passes if: a test with a
   two-part line reads the OPERATION hint as
   `optional · the bank's operation number · empty clears it · changes every part of the transaction`
   with the note styled `ACCENT`; a test with a one-part line shows the plain hint; tui.md's
   "A split transaction says what reaches every part" names OPERATION for the "no batch" form.
   Reviewer: the ledger's Edit form is unchanged, `EVERY_PART_NOTE` is the one copy of the
   words.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
