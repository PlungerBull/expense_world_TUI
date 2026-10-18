# Caught up with contract 786d68f3b071dbf4: the import moves a code-matched line to the bank's day

2026-10-18

## Covers

Contract `7ff6a09d863d6e44` (exclusive) to `786d68f3b071dbf4` (inclusive): `1efa6f4627ff9acf`
and `786d68f3b071dbf4`. It answers sections 5 and 6 of your hand-off "A bank line is read,
reconciled, deleted and listed whole; the import moves a code-matched line to the bank's day;
six contract texts are corrected", and its "What the TUI does" steps 7 to 9. With the reply for
`7ff6a09d863d6e44`, that hand-off is fully answered.

What the TUI does now:

- The import's preview is one table of the file's rows. Each row has a mark (✓ in the ledger
  after the import, ✗ left out or needing a look) and one reason from a short list: `New`,
  `Already in the ledger`, `Modified existing transaction`, `Not moved: <reconciliation> is
  reconciled`, `Closed period`, `Before 2026`, `Couldn't read the row`.
- A row that moves to the bank's day reads `Modified existing transaction`, like a row that
  takes the bank's title or operation code. That was the owner's choice.
- A row whose move a completed reconciliation stops reads `✗ Not moved: <name> is reconciled`.
  The name comes from `redate_blocked_by`, looked up in `GET /v1/reconciliations?account_id=…`.
- The counts line adds `counts.redated` (`1 moves to the bank's day` before applying, `1 moved
  to the bank's day` after), only when it is not zero.
- Section 6, the corrected texts: the TUI shows every engine message whole and quotes none, so
  nothing changed.

## Done when, checked

Checked on 2026-10-18 against the practice engine, which served `786d68f3b071dbf4`. The TUI's
full contract suite passed: 103 tests, two of them new for this range.

| Check | Result |
|---|---|
| The import screen shows, before applying, which code-matched lines will move to the bank's day and which keep their date because of a completed reconciliation, and shows the moved count after applying | worked, with one difference by the owner's choice. A line split in two parts (-15.90 and -10.00), coded and on 3 October in the ledger, came in a file on 4 October. The preview counted `1 moves to the bank's day`. After applying, both parts were on 4 October at 00:00 Lima time, and the result counted `1 moved to the bank's day`. A coded line on 3 October inside a completed reconciliation (1 to 3 October) showed `✗ Not moved: Octubre inicio 2026 is reconciled`. It stayed on 3 October, still in that reconciliation, and the file's other row was created. The difference: the moving row is not singled out. It reads `Modified existing transaction`, and only the count says a move happens. |

## Contract problems found

- There is no `GET /v1/reconciliations/{id}`, so naming the reconciliation in
  `redate_blocked_by` takes a second read of the account's whole list. Sent as its own ask, "The
  import answer names the reconciliation that stops a move to the bank's day".
- Not a problem, noted to confirm our reading: when a move is stopped, the bank's title and
  operation code still land on the line. The TUI says "not moved" rather than "not modified" for
  that reason.

## Asks this closes

None.
