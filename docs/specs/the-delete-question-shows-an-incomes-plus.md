# The delete question shows an income's `+`

What [a save that answers after you leave](../decisions.md) (done on 2026-11-06) turned up: the
question before a delete names an income without the `+` every list shows it with.

**Status: drafted on 2026-11-06; no question; for the owner to approve.** It waits on no other
spec. When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

`d` on the ledger, the "no statement" list or the flagged lines asks `Delete this transaction?`
over the row, `Sueldo · 800.00 · 2026-11-01 · Sueldo Soles`. The ledger shows that row as
`+800.00`, and so does the message the app shows when you leave before the delete answers. The
question is the one place an income loses its `+` ([decisions.md](../decisions.md) "Every
screen's frame: no blank lines at the crumb, refusals under the form, `+` on incomes").

## What it must do

1. **The delete question writes an income's amount with its `+`**, as the lists do.

## How the owner knows it is done

1. `d` on an income in the ledger asks over `Sueldo · +800.00 · …`.
2. The unit suite passes.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
