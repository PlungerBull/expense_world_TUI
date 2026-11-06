# The "no statement" Edit form's heading writes a deposit's `+`

What [a split's parts show an income's `+`](../decisions.md) (done on 2026-11-06) turned up:
the Edit form opened from the Statements screen's "no statement" list writes the line's total in
its heading without the `+` its parts now carry.

**Status: drafted on 2026-11-06; one question; for the owner to answer and approve.** It waits
on no other spec. When done, the why moves to [decisions.md](../decisions.md) and this file is
deleted.

---

## Why

That form's heading names the line: its title, then its total and currency
(`Liquidación  ·  800.00 PEN`). The parts table under it, and the line adding the parts up, write
the same deposit as `+800.00`, as every list writes a transaction ([decisions.md](../decisions.md)
"Every screen's frame: no blank lines at the crumb, refusals under the form, `+` on incomes").

## Question

**Does the heading write a deposit with its `+`?**

- **A — Yes, `Liquidación  ·  +800.00 PEN`**, as the parts under it and every list write it.
- **B — No, `800.00`**: the heading stays as it is.

**Recommended: A.** The heading names a transaction, and a transaction's positive amount is
written with its `+` wherever it is named.

Its mockup is drawn once the question is answered.

## What it must do

1. Per the answer above.

## How the owner knows it is done

1. With A: the Edit form opened on a deposit from the "no statement" list reads `+800.00` in its
   heading.
2. The unit suite passes.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
