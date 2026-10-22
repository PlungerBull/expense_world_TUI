# Caught up with contract `54fd1012f7d60abc`: bank lines carry a line code and a statement line, and a create sent again answers `ID_EXISTS` before anything else

2026-10-22

## Covers

Contract `ab14bd54f4c8b016` (exclusive) to `54fd1012f7d60abc` (inclusive), all of the hand-off
"Every bank line carries an engine-given code and an optional statement-line reference, an
account can become a person and back, and a create sent again answers `ID_EXISTS` before anything
else" (shipped 2026-10-21) except its account half (`fab230c456c2dba2`), which has a reply of its
own once the Accounts screen is built. `54fd1012f7d60abc` is the version to start the next
catch-up file from.

What the TUI does with it:

- The sheet import groups rows sharing a `COD_EECC` into one `line_group` in one
  `POST /transactions/batch`, each item carrying the code as `statement_line`; a chunk never cuts a
  group. A group whose rows differ on account, date or title, or that has a row the import cannot
  read, is held back whole before anything is sent, and the rest imports.
- A refused batch is read item by item: every item named `ID_EXISTS` on its own id counts as
  already there, every item named by another refusal fails in your words, and the rest go again as
  one batch. The one-request-per-row retry is gone, so a re-run of an imported sheet costs one
  request per chunk. A part refused in a `line_group` fails its whole group.
- `LIMIT_REACHED` with `LINE_CODES_EXHAUSTED` ends a run once, as `SETTINGS_MISSING` does.
- Refused rows read one line per kind of error: the field you name, your words, then the rows.
- No request carries `line_code`; a test guard fails any that does.

## Done when, checked

All run against the practice engine on 2026-10-22, at contract `54fd1012f7d60abc`.

1. **The TUI holds contract `54fd1012f7d60abc` and reads `line_code` and `statement_line`
   without error:** worked. The version check matches; the transaction list (35 rows) and the
   bank-line list (19 lines) read both fields on every row, and both counts agree.
2. **A sheet import sends each row's statement line; every part of a split group lands on one
   line, sharing one `line_code` and one `statement_line`:** worked. A sheet of 35 rows with 9
   split groups made 19 bank lines; each group is one line read by `GET /bank-lines/{id}`, every
   part carrying the line's code and statement line, and every coded row's statement line is its
   `COD_EECC`.
3. **No TUI request carries `line_code`:** worked. A unit guard checks every request body the
   suite sends; no `line_code` appeared in any request of the live run.
4. **A sheet-import re-run with statement lines counts every row that landed as already there,
   and creates only the rows that are new:** worked. A re-run sent one batch, answered `409`
   `ID_EXISTS` on every item, and counted 35 already there; with one row appended it sent two
   batches (`409`, then `201`) and created only that row.
5. **A batch's refusals show grouped by reason:** worked. A sheet with two future-dated rows and
   an edited row reusing a taken statement line drew `422`, then `409`, then `201`, and printed
   `date: Must not be in the future. rows 3, 4` and
   `statement_line: Must not be a statement line another bank line already has. row 2`.

## Contract problems found

- **Whether case counts in a statement line is unstated.** POST /v1/transactions/batch ("Line
  groups") and the `STATEMENT_LINE_EXISTS` text say a statement line is trimmed and compared after
  trimming, but not whether `SIG-x` and `sig-x` are one statement line. The practice engine treats
  them as two (2026-10-22), and the sheet import groups by exact text to match. Please state it.

## Asks this closes

- "A create whose `id` is already in the ledger answers `ID_EXISTS` on that id before any other
  conflict".
