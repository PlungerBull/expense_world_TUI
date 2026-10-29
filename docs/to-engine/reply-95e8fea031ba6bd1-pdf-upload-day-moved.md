# Caught up with contract 95e8fea031ba6bd1: the PDF upload matches a line one day off and moves it to the bank's day, on the terminal app's screen

2026-10-28

## Covers

`95e8fea031ba6bd1`, from the hand-off of 2026-10-28, "A person is a holder; unpairing is one write;
the PDF upload moves a line one day off; the change log reaches back; your practice engine serves
only shipped code": the part on the PDF upload matching a line one day off the paper's row, as the
terminal app's preview shows it. The live tests of that match, and the hand-off's other parts, are
answered in later replies, with the catch-up that moves the terminal app's live tests onto the
holder routes.

## Done when, checked

- **The PDF upload shows which lines moved to the bank's day: worked.** On the practice engine at
  contract `e020782e3579d011`, the savings sample's March 2025 paper, with a ledger line of -189.50
  on 2025-03-13, one day off the paper's row of 2025-03-12: the dry run's preview reads that row
  `✓ In the ledger · day moved`; a row matched on its own day reads `✓ In the ledger` with no mark.
  After the apply, the line reads `2025-03-12T05:00:00Z`, 00:00 of the paper's day in
  America/Lima, as "The bank's day wins" states. The app draws the row's `redated` as sent and
  decides nothing itself.
- **No code reads `near_misses`: worked in the app.** Nothing in the terminal app or its unit tests
  reads it, and the old "one day off: not paired" warning is gone. The terminal app's live test of
  the upload still asserts it; that test stops at its setup on the holder routes today and is
  rewritten in the catch-up that moves the live tests onto them, reported in its reply.

## Contract problems found

None.

## Asks this closes

None.
