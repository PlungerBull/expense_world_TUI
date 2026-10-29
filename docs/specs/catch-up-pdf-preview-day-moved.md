# The PDF preview marks a line moved to the bank's day

Catches up to contract `95e8fea031ba6bd1`, the app's side of it: the part of the engine's hand-off
of 2026-10-28, "A person is a holder; unpairing is one write; the PDF upload moves a line one day
off; the change log reaches back; your practice engine serves only shipped code", on the PDF
upload matching a line one day off the paper's row. The live tests of that match are task 1 of
[catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md),
since they sit in a file that spec moves onto the engine's new routes. It stands apart from
[catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md),
the owner's call of 2026-10-28, so it does not wait on the ask "An account holds its currencies:
the holder becomes the account, and each account becomes one of its currencies".

**Status: approved, with its tasks, and named the current spec by the owner on 2026-10-28; no
question open. It touches only the PDF upload's preview, which no spec on hold changes.** When done, the why moves to [decisions.md](../decisions.md)
and this file is deleted.

---

## Why

When you drop a statement PDF, the preview lists every row of the paper and says which are
already in your ledger. Sometimes your line for a purchase sits one day off the bank's date: you
wrote it the day you paid, the bank printed the next day. The engine now treats such a line as
the same transaction when it has the same direction and amount, and moves it to the bank's day
when the statement closes (contract: POST /v1/statements/import, "The bank's day wins"). On the
preview, where nothing is written yet, each row says whether its line would move (its `redated`).

The app still looks for the old warning instead ("… in the ledger is one day off: not paired",
from `near_misses`), which the engine no longer sends. So today such a row shows matched, with
nothing saying your line will move.

## What it must do

1. **A row whose line the engine moves reads `✓ In the ledger · day moved`** on the preview: the
   mark dim at the end of the row, the way a fee row carries its note, with no old day (the
   owner's pick, B, in
   [expense-world-statement-pdf-redated.html](../mockups/expense-world-statement-pdf-redated.html)).
   Every other row reads as today, and so does the screen after `⏎`.
2. **Nothing in the app reads `near_misses`**: the warning line under a new row goes, and so does
   the read of those lines.
3. **The docs say what the screen does**: [tui.md](../tui.md)'s PDF preview gives the mark and no
   longer the warning, and
   [expense-world-statement-pdf-screens.html](../mockups/expense-world-statement-pdf-screens.html)
   stops drawing the warning. The redated mockup is deleted, with its links, once the screen is
   built.

## How the owner knows it is done

1. In the app, against the practice engine, a PDF with a row one day off one of your lines
   previews that row as `✓ In the ledger · day moved`, with no warning line; after `⏎` your line
   is on the paper's day.
2. A row matched on its own day shows no mark.
3. The unit suite and the drift check pass, and no code in the app or its unit tests names
   `near_misses`.

## Questions for the owner

None: the owner picked the screen, B of the redated mockup, on 2026-10-28.

---

## Tasks

Drafted 2026-10-28; approved by the owner on 2026-10-28. Each needs the practice engine for the drift
check, which the orchestrator starts before the task and stops after it.

1. **The mark on a moved row (builder).** The PDF upload's preview reads each row's `redated` and
   draws `· day moved` dim after a matched row's reason, as the fee note is drawn
   ([statement.py](../../expense/bank_import/statement.py),
   [statement_upload.py](../../expense/tui/screens/statement_upload.py)); the unit fixtures in
   [helpers.py](../../tests/unit/helpers.py) carry `redated`; tui.md's preview row says so.
   *Passes if:* a unit test previews a row with `redated: true` and finds `✓ In the ledger · day
   moved`, the mark dim; a row with `redated: false` has no mark; the title column still leaves
   room so no row wraps; tui.md's preview row names the mark with its contract citation; the
   drift script shows no fixture key the contract lacks for the upload.
2. **The old warning goes (builder).** Remove `near_misses` from the app: its rows, its line under
   a new row, its share of the ledger-line read by id and its `—` fallback, its fixtures and its
   tests; tui.md's preview row, the paragraph on reading the lines, and "No `r` on the import
   screens" stop naming near misses; the warning leaves
   [expense-world-statement-pdf-screens.html](../mockups/expense-world-statement-pdf-screens.html);
   [expense-world-statement-pdf-redated.html](../mockups/expense-world-statement-pdf-redated.html)
   is deleted with its links.
   *Passes if:* `grep -rn "near_miss\|NearMiss" expense tests/unit` finds nothing; the lines taken
   out are still read once by id, and their read failing still shows its `!` line (their tests
   pass unchanged); the docs link test passes; the tester's run of the app shows the screen as
   "How the owner knows it is done" 1 and 2 say.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `95e8fea031ba6bd1` of the hand-off "A person is a holder; …", the app's side; its
  live tests are reported with
  [catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md).
- **The engine's "Done when" checks to report on:** from the hand-off "A person is a holder; …":
  the PDF upload shows which lines moved to the bank's day, and no app code reads `near_misses`
  (the live suite's is reported with 2b).
- **The asks it closes:** none.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
