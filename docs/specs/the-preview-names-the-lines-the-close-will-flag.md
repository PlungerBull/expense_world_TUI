# A statement PDF's preview names the lines the close will flag

What a month's statement closing from the bank's PDF (done on 2026-11-03) turned up: that spec
asked for a ledger line the paper lacks to show as flagged "before and after the close", and
only "after" is built. The upload's preview shows the lines it would take out of the month, but
not the lines the close would flag; those show only once the month is closed, on the result
screen's `⚑` line and `f`.

**Status: drafted on 2026-11-03 for the owner to rewrite or approve; one question, and the
preview needs a mockup to draw if the answer is A.** It waits on no other spec. When done, the
why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

The preview is where the owner checks an upload before anything is written. A line the owner
logged on a day the paper covers, which the paper does not hold, is worth seeing there: it is
often a typo'd amount or a purchase the bank books next month. Today it shows only after the
close, when the month is already completed.

The engine's dry run does not say which lines the close would flag: its `statement` is `null`
on a dry run (contract: POST /v1/statements/import). Showing them before the close needs the
engine to name them on the dry run, as it already names the lines it would take out.

## What it must do

1. **The preview lists the lines the close would flag,** beside the lines it would take out,
   before anything is written.
2. **The engine names them on the dry run**, so the app reads them and decides nothing.

## How the owner knows it is done

1. A PDF whose month holds a ledger line the paper lacks shows that line in the preview as one
   the close will flag; leaving the preview writes nothing.
2. After the close, the same line shows on the `⚑` line, as today.

## Questions for the owner

### 1. Show the lines the close will flag in the preview?
- **A.** Yes: the preview lists them before you confirm. Needs one engine change and a mockup
  of the preview.
- **B.** No: seeing them after the close is enough; this spec is dropped.

**Recommended:** A, because the preview is the one place to catch a wrong line before the month
completes, and every client gets it from the engine.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
