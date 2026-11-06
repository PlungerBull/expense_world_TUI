# A split's parts show an income's `+`

What [the delete question shows an income's `+`](../decisions.md) (done on 2026-11-06) turned
up: the Edit form's parts table writes a part's amount without the `+` every list shows an
income with.

**Status: drafted on 2026-11-06; question answered (A), its mockup,
[expense-world-split-parts-plus.html](../mockups/expense-world-split-parts-plus.html), and its
tasks approved on 2026-11-06; the current spec.** It waits on no other spec. When done, the why
moves to [decisions.md](../decisions.md) and this file is deleted.

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

All done.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **The Edit form's heading writes a deposit without its `+`.** The heading gives the line's
  total with the account rule (`AMOUNT_RULE`, [edit_form.py](../../expense/tui/screens/edit_form.py)),
  so a deposit's heading reads `800.00` while its count line reads `+800.00`. Something the owner sees.
- **No test draws a marked or refused part row with an income.** Both rows print the same cell as
  the locked row, which a test pins with `+3,200.00`, but neither has a test of its own
  ([parts_table.py](../../expense/tui/widgets/parts_table.py) `parts_lines`).
