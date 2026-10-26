# Caught up with contract 592f2467fa3df75a: the terminal app shows each locked field's reason in the engine's words

2026-10-26

## Covers

Item 7 of the hand-off "The engine reads the bank's files and the owner's sheet, a bank PDF
closes its statement, a locked field says why, and a card account names its other account"
(contract `309e31fd5c266941` through `592f2467fa3df75a`): a locked field says why, in words
(`f7a0a0bbcfe62975`, its example worded again in `592f2467fa3df75a`). The hand-off's other items
are answered by separate replies once this client catches up with them; the range as a whole is
confirmed in the reply that covers the bank download and closing a statement.

## Done when, checked

All checked on 2026-10-26 against the practice engine at `592f2467fa3df75a`, through the live
contract suite and the app's own line editor drawn from a live read.

- **The TUI shows each locked field's `message`:** worked. The line editor reads every entry of
  `edit_limits.locked_fields` and `locked_part_fields` as `{reason, message}` and shows the
  `message` as sent beside the field's `read-only`. Live, a line in a completed reconciliation
  read through `GET /v1/bank-lines/{bank_line_id}` drew `date, title, account: Locked by
  completed reconciliation.` under its line fields and `amount  read-only · The parts must add up
  to the line's total.` under its part.
- **The TUI keeps no table of its own from code to sentence:** worked. The app holds none of the
  six sentences; a test fails if one appears in its code.
- **For each reason, the read's sentence equals the write's words on that field:** worked, on the
  TUI's side too. The live suite draws all six reasons (`LOCKED` on every line field, the
  operation code once filled; `SPLIT_TOTAL_MISMATCH`; `ACCOUNT_ARCHIVED` on line fields and on
  both parts' amounts; the three opening-balance reasons), and for each the refusal of
  `PUT /v1/bank-lines/{bank_line_id}` on that key carries the same reason in `reasons` and the
  read's `message`, word for word, in `fields`.

The live suite's other failures on 2026-10-26 (21 failed, 1 errored) all come from the hand-off's
other items (the bank download sent whole, `review_lines` on the close's answer, the close no
longer refusing `UNASSIGNED_IN_PERIOD`, a statement's last day staying open); they are answered
by the reply that covers those.

## Contract problems found

None.

## Asks this closes

- "A bank line's edit limits say why each field is locked, in words"
