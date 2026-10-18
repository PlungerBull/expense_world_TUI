# Caught up with contract 7ff6a09d863d6e44: a bank line is read, reconciled, deleted and listed whole

2026-10-17

## Covers

Contract `890453f80a08cec9` (exclusive) to `7ff6a09d863d6e44` (inclusive): `ce4e5cb642e53fdb`,
`0e71bf2787f9464e`, `5572fee599cd06e8`, `1baf89c4d8dd9f40` and `7ff6a09d863d6e44`. It answers
sections 1 to 4 of your hand-off "A bank line is read, reconciled, deleted and listed whole; the
import moves a code-matched line to the bank's day; six contract texts are corrected", and its
"What the TUI does" steps 1 to 6.

Not yet caught up: `1efa6f4627ff9acf` (the import's move to the bank's day) and
`786d68f3b071dbf4` (wording). They are sections 5 and 6 of the same hand-off, and the TUI's next
catch-up takes them; its reply will say so. You need not send them again.

What the TUI does now:

- The ledger stays one row per part.
- The reconciliation screens list bank lines, one row per line with its total, in the bank's
  columns: date, title, operation code and amount.
- The list of lines in no reconciliation is newest first, the list's one order.
- `PUT /transactions/{id}` with `reconciliation_id` on any one part ticks or unticks a line.
- Deleting from a part, in the ledger or in a reconciliation, deletes the whole line after a
  confirmation naming how many parts go.
- Editing a line from a reconciliation edits the bank's fields, which reach every part.

## Done when, checked

Checked on 2026-10-17 against the practice engine, which served `786d68f3b071dbf4`. The TUI's
full contract suite passed: 101 tests.

| Check | Result |
|---|---|
| Opening a line is one `GET /bank-lines/{id}`, read from `parts`; the TUI adds no amounts of its own and reads no `transaction_ids` | worked. The re-split screen makes that one read. Its total is `net_cents` and its count is `part_count`. The only sum the TUI makes is how much of `net_cents` the typed parts leave, shown as a guide. |
| The reconciliation screen lists lines from `GET /bank-lines`, ticks a line with one `PUT` on any part, and never shows half a line ticked | worked. A −100.00 charge split −60.00 / −40.00 lists as one row of −100.00. A `PUT` on part 2 put both parts in the reconciliation. `?reconciliation_id=` then listed 1 row and `?unreconciled=true` listed 0. The reconciliation read `difference_cents` 0 against an ending balance of −100.00, and complete answered with no warnings. Sending `null` on part 1 took both parts out. |
| Deleting a line is one `DELETE /bank-lines/{id}` behind a confirmation, from the ledger or the reconciliation screen | worked. The answer held both parts; the ledger then counted 0 and listed nothing. |
| `IN_COMPLETED_RECONCILIATION` on `bank_line_id` has a handled path; no code handles `SPLIT_RECONCILIATION_MIXED` | worked. The `409` answers "Cannot delete a bank line assigned to a completed reconciliation. Revert the reconciliation to draft first." The TUI shows it whole, and the line keeps both parts and its total. No TUI code names `SPLIT_RECONCILIATION_MIXED`. |

## Contract problems found

None.

The leftover you named is closed: on `786d68f3b071dbf4`, `409 OPERATION_CODE_EXISTS` answers
"Another bank line on this account already has operation code '<code>'.", with the field message
"Must not be an operation code already on this account."

`SPLIT_LINE_PARTS_DIVERGE`: understood. The TUI keeps showing it like any other `422` on the split.

## Asks this closes

- "A bank line is reconciled whole: assigning or unassigning one part does the same to every part"
- "Deleting a bank line deletes every one of its parts, in one write"
- "The ledger can be read one bank line per row, with each line's parts inside". It is answered
  differently, as agreed: the ledger stays one row per part, and only the reconciliation screens
  list by line.
