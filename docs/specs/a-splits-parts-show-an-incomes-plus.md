# A split's parts show an income's `+`

What [the delete question shows an income's `+`](../decisions.md) (done on 2026-11-06) turned
up: the Edit form's parts table writes a part's amount without the `+` every list shows an
income with.

**Status: drafted on 2026-11-06; one question; for the owner to answer and approve.** It waits
on no other spec. When done, the why moves to [decisions.md](../decisions.md) and this file is
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

**Recommended: A.** The parts table is a list of amounts, and the `+` is how every other list
tells an income from an expense with colour off.

## What it must do

1. Per the answer above.

## How the owner knows it is done

1. With A: the Edit form of a split with an income part shows `+800.00` in its parts table.
2. The unit suite passes.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
