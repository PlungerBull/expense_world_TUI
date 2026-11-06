# A split's parts show an income's `+`

What [the delete question shows an income's `+`](../decisions.md) (done on 2026-11-06) turned
up: the Edit form's parts table writes a part's amount without the `+` every list shows an
income with.

**Status: drafted on 2026-11-06; question answered (A) on 2026-11-06; its mockup,
[expense-world-split-parts-plus.html](../mockups/expense-world-split-parts-plus.html), and its
tasks for the owner to approve.** It waits on no other spec. When done, the why moves to [decisions.md](../decisions.md) and this file is
deleted.

---

## Why

The Edit form of a split transaction lists its parts in a table: amount, category, hashtags,
note. A part of `+800.00` reads `800.00` there, while the ledger, the statement lists and the
question before a delete write an income with its `+` ([decisions.md](../decisions.md) "Every
screen's frame: no blank lines at the crumb, refusals under the form, `+` on incomes").

## Question

**Does the parts table write an income part with its `+`?**

- **A — Yes, `+800.00`**, as every list writes it.
- **B — No, `800.00`**: the table is part of a form, and stays as it is.

**Answered: A** (2026-11-06). The parts table is a list of amounts, and the `+` is how every
other list tells an income from an expense with colour off.

## What it must do

1. The parts table writes an income part with its `+` (`+800.00`), and the line under it that
   adds the parts up writes its two amounts the same way (`+800.00 of +800.00`), as
   [the mockup](../mockups/expense-world-split-parts-plus.html) draws it.

## How the owner knows it is done

1. The Edit form of a split with an income part shows `+800.00` in its parts table.
2. The unit suite passes.

---

## Tasks

### 1. The parts table and its count line write an income with its `+`

The table's amounts and the count line's two amounts are written with the rule every list uses
(`TRANSACTION_RULE` in [theme.py](../../expense/tui/theme.py)), so an income reads `+1000.00` and
an expense `-200.00`; the amount column widens to fit the `+`. The `… left` figure stays as it is.

Passes if:
- a unit test opens the Edit form of a split with an income part and an expense part and finds
  `+1000.00` and `-200.00` in their rows, the header and rows still lined up, and
  `2 parts  ·  +800.00 of +800.00  ✓` under them;
- the tests that pin the table's text today are updated, not deleted;
- [docs/tui.md](../tui.md)'s parts-table section says incomes read with their `+`, if it names
  how amounts are written;
- `pytest tests/unit` passes.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
