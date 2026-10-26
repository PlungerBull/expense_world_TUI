# Caught up with contract 592f2467fa3df75a: the terminal app sends a bank download whole, shows what a close flags, and takes a card's other account from the engine

2026-10-26

## Covers

Items 1, 3, 4, 6, 8 and 9 of the hand-off "The engine reads the bank's files and the owner's
sheet, a bank PDF closes its statement, a locked field says why, and a card account names its
other account" (contract `309e31fd5c266941` through `592f2467fa3df75a`), and the changed refusal
words of its item 7. This client has read `x-changelog` over the whole range and caught up to
it: item 7 was answered by its own reply on 2026-10-26, and items 2 (the sheet read by the
engine) and 5 (a statement closed from its PDF) are answered by the replies of their own work,
still to come.

## Done when, checked

All checked on 2026-10-26 against the practice engine at `592f2467fa3df75a`: the whole live
contract suite passed (203 tests, none failed or skipped), the unit suite passed (3,416 tests),
and the fixture drift check found nothing. The 21 failures and 1 error of the earlier live run
on 2026-10-26, all from this hand-off, are gone.

- **No code sends `rows` to `POST /transactions/import` or reads an Excel download itself:**
  worked. The terminal app sends `{dry_run, account_id, file}` with the file's bytes in standard
  base64 and reads no cell; its own reader of bank downloads is deleted, and a test fails if the
  import door imports a spreadsheet reader. No contract test sends `rows` either.
- **The contract tests upload a made-up download with a dry run and an apply:** worked. Every
  import test builds its own made-up `.xlsx` in the test: the apply writes what the dry run
  showed, and the same file sent again matches every row; a card's download lands its soles rows
  on the soles account and its dollar rows on the dollar account; a row of `0` comes back
  `skipped` and is never written; the earlier ground (reported days, a split line and a line
  group matched on re-import, a line moved to the bank's day and a move stopped by a completed
  reconciliation, a matched line keeping its statement line and place) holds on the new body.
- **Complete shows `review_lines` and nothing handles `UNASSIGNED_IN_PERIOD` from it:** worked.
  After a complete that flags lines, the app opens a screen of them, both halves of a card
  together, each line opening in the line editor or deleted after a question; nothing in the app
  or its tests expects `UNASSIGNED_IN_PERIOD`. Live: a close flags each half's leftover lines from
  either half, the previous statement's last day included; a line in a draft, a line before that
  day and a half already completed flag nothing; the lines `?unassigned_in_period_of=` lists
  before the close are exactly the ones it flags.
- **A card's other account is found only through `statement_partner_id`:** worked. The app no
  longer matches statement codes between accounts anywhere; Reconciliations and the import door's
  account list pair a card only through the field. Live: a card's two accounts name each other,
  an account with no code or a code no other account holds reads `null`, and both read `null`
  while one is archived, back after the unarchive.
- **The live tests draw `RESERVED_NAME_HELD` as the reserved-names user:** worked on eight of the
  nine routes whose error reasons list it (`POST /transactions`, `/transactions/batch`,
  `PUT /transactions/{transaction_id}`, `PUT /bank-lines/{bank_line_id}`,
  `DELETE /hashtags/{hashtag_id}`, `POST /accounts/{account_id}/opening-balance`,
  `/transactions/import`, `/transactions/import-sheet`), each writing nothing. The ninth,
  `POST /reconciliations/import`, needs a made-up statement PDF before any row is filed; this
  client's work on closing a statement from its PDF builds one and draws it there.
- **A statement's last day stays open until the next statement is completed:** worked. Live: the
  last day takes rows while the next statement is a draft, is refused `SEALED_PERIOD` under its
  own reconciliation once the next one is completed, and opens again after that one is reverted.
- **The changed refusal words (item 7):** the unit tests quote the engine's current words for a
  refusal caused by one part of a split line and for a part's amount that does not add up.

## Contract problems found

- **An import row refusal without its row.** `POST /transactions/import` says each refusal
  keyed `rows.<row>.<field>` has a message beginning `Row <row>:`, but `FUTURE_DATE` sends only
  "Must not be in the future." (seen on `rows.3.date`). This client shows the key beside such a
  message, so nothing is lost on screen; the contract and the engine disagree.
- **A heading named differently.** The complete route points to *Transactions* → *Sealed
  periods*; the tag is named "Transactions (Ledger)".

## Asks this closes

- "The account read names a card's other account"
- "Probes on the practice engine clean up after themselves"
- "The practice engine seeds a second practice user whose own category and hashtag hold the
  reserved names"
