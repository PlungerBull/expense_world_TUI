# The app catches up with the engine: the bank download, closing a statement, a card's other account

Catches up to contract `592f2467fa3df75a`, from `309e31fd5c266941`: the engine's hand-off of
2026-10-26, its items 1, 3, 4, 6, 8 and 9, and the changed refusal wording of item 7. Its other
items have specs of their own: item 7, a locked field's words, was caught up by its own spec on
2026-10-26, its reply handed over the same day; after this one
come [sheet-import-through-the-engine.md](sheet-import-through-the-engine.md) (item 2) and
[statements-close-from-their-pdf.md](statements-close-from-their-pdf.md) (item 5).

**Status: current.** The owner approved the tasks on 2026-10-26; the loop runs on it. When done,
the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

The engine changed on 2026-10-26, and three things in the app no longer match it:

- **The bank download import is broken.** The app reads the bank's Excel download itself and
  sends the rows it read; the engine now takes the file itself, reads it, and refuses rows
  (contract: POST /v1/transactions/import). Until this spec lands, no download can be imported.
- **Closing a statement no longer stops on leftover lines.** The engine used to refuse to
  complete a statement while lines dated inside it were in no statement. It now completes it
  and answers the lines it flagged for you to look at
  (contract: POST /v1/reconciliations/{reconciliation_id}/complete). The app still expects the
  refusal, and shows nothing of the flagged lines.
- **The engine names a card's other account.** A card is two accounts, one per currency. The
  app finds the other one by matching statement codes across the account list; the engine now
  sends it on every account (`statement_partner_id`, contract: GET /v1/accounts), so the rule
  lives in one place for every app.

Two more come with it: a closed statement's last day now stays open until the next statement
is closed, and the practice engine now has a second practice user, held on the reserved names,
so the live tests can finally see the engine refuse a write with `RESERVED_NAME_HELD`.

## What it must do

1. **A bank download goes to the engine whole.** You drop the file and pick its account as
   today; the app sends the file and shows what the engine read. The app reads no cell of it,
   and its own Excel reader goes. The preview names each row by its row number in the
   spreadsheet, shows a row of `0` as skipped and counts it, and shows a row the engine refuses
   on that row, in the engine's words. A card's download puts its other-currency rows on the
   card's other account: the engine does it. The screens change, so they are picked from a
   mockup before they are built. The backlog item "Leftovers in the import door" goes with
   this rewrite.
2. **Completing a statement shows the lines it flagged.** Complete always goes through when the
   statement adds up; the lines the close flagged (on a card, on both halves) show after it,
   each leading to its line. Nothing in the app treats leftover lines as a refusal of complete
   any more. Where they show is picked from a mockup before it is built.
3. **A card's other account comes from the engine** everywhere the app pairs a card's two
   accounts (the import door's account list, a card statement's two halves, Reconciliations),
   never by matching statement codes. Nothing you see changes.
4. **The app's words about sealed days match the new rule**: a completed statement locks its
   days but the last, which locks once the next statement is completed too. The app computes
   nothing: it shows the engine's refusal as it comes.
5. **The tests quote the engine's current words**: a refusal caused by one part of a split
   transaction no longer starts "Part … of this bank line is the cause", and a part's amount
   refused because the parts don't add up no longer states both totals. The unit tests' fake
   engine answers a completed statement with its flagged lines, as the real one does.
6. **Live tests prove each change against the practice engine**: a made-up bank download, dry
   run and apply, a card's landing on both its accounts, a zero row skipped; a close that
   flags a leftover line; a card's other account, and when it is empty; and, as the second
   practice user, `RESERVED_NAME_HELD` on each route the engine's check names. Every test file
   is made up: never one of your real downloads, since this repo is public.
7. **The practice engine's second key is handled like the first**: the practice-engine script
   and the live-run instructions carry it, and the guards keep it out of files.

## How the owner knows it is done

1. In the app against the practice engine, a made-up bank download imports: the preview lists
   its rows by their spreadsheet row number, a zero row shows as skipped, and the import writes
   what the preview showed.
2. A made-up card download puts its soles rows on the soles account and its dollar rows on the
   dollar account.
3. Completing a statement with a leftover line goes through and shows the line as flagged.
4. The unit suite, the live suite and the drift check pass: the live suite failed 21 tests and
   errored on 1 on 2026-10-26, every one from the engine's move (the bank import's `rows` gone,
   `review_lines` on the close's answer, the close no longer refusing `UNASSIGNED_IN_PERIOD`,
   and a statement's last day staying open). The last of these leaves one
   `contract-seal-…` account on the practice user each live run (five by 2026-10-26), which the
   practice-data cleaner removes
   ([runtime.md](../runtime.md) "Leftovers").

## What the engine declined

- **The account read names a card's other account by id only**, not with its name and currency
  as the ask offered: a reference to another record carries only its id. The app reads the
  account it names from the account list it already holds.
- **Probes on the practice engine clean up after themselves** was done another way: the engine's
  own checks run as a practice user of their own, so they never write to this app's practice
  user.

## Questions for the owner

None beyond the two mockup picks (points 1 and 2).

**Answered:** a bank download imports every row of the file, whatever its date: the import
door's rule of leaving out rows dated before 2026 goes (owner, 2026-10-26).

**Answered (owner, 2026-10-26):** an archived card account with no statement gets no column on
the card's list (question 2, A: as built in task 2); the "no batch" list explains its `!` as
`! dated inside a statement` (question 3, A, drawn in
[expense-world-no-batch-caption.html](../mockups/expense-world-no-batch-caption.html)); a dropped
file the app cannot open is noted `can't read the file · …` (question 4, B).

---

## Tasks

9. **The note for a dropped file the app cannot open** (question 4, B). The LOG bar notes such
   a file `can't read the file · File not found: <path>` (or `· Could not open <path>: <why>`),
   never `not a BCP bank file`; [tui.md](../tui.md) and the tests say the same.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** this client has read `x-changelog` from `309e31fd5c266941` through
  `592f2467fa3df75a` and caught up to it; items 2, 5 and 7 are answered by the replies of their
  own specs.
- **The engine's "Done when" checks to report on:** no code sends `rows` to
  `POST /transactions/import` or reads an Excel download itself; the contract tests upload a
  made-up download with a dry run and an apply; complete shows `review_lines` and nothing
  handles `UNASSIGNED_IN_PERIOD` from it; a card's other account is found only through
  `statement_partner_id`; the live tests draw `RESERVED_NAME_HELD` as the reserved-names user.
- **The asks it closes:** "The account read names a card's other account", "Probes on the
  practice engine clean up after themselves" and "The practice engine seeds a second practice
  user whose own category and hashtag hold the reserved names".
- **An import row refusal without its row:** the contract says every `rows.<row>` message of
  `POST /transactions/import` begins `Row <row>:`, but `FUTURE_DATE` sends only "Must not be in
  the future." (seen live on `rows.3.date`).
- **A wording slip in the contract:** the complete route points to *Transactions* → *Sealed
  periods*, while the tag is named "Transactions (Ledger)".

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **Old sealed-day words in tests, docs and a mockup.** The `SEALED_PERIOD` sentence "The date
  falls inside a completed reconciliation's period." is still quoted in [tui.md](../tui.md)
  (around line 959), test_grouped_refusals.py, test_tui_log_bar.py and
  `expense-world-grouped-refusals.html`; the engine now sends "Period … is sealed by completed
  reconciliation '…'. Revert it to draft to change anything inside it." Same kind as the backlog
  item "A unit fixture quotes an old refusal". (Task 3.)
- **`RESERVED_NAME_HELD` on the statement-PDF upload.** `POST /v1/reconciliations/import` can
  answer it, but drawing it live needs a made-up bank statement PDF the engine reads before any
  row; the live tests of [statements-close-from-their-pdf.md](statements-close-from-their-pdf.md)
  build one, so that spec draws it. (Task 4.)
- **The practice-data cleaner speaks of one practice user.** `scripts/clean_practice_user.py`
  takes its key only from `EXPENSE_PAT`, and [runtime.md](../runtime.md) "Leftovers" says it
  cleans "the practice user"; a leftover on the reserved-names user is cleaned by passing that
  user's key as `EXPENSE_PAT`, which no doc says. (Task 4.)
- **The flagged lines are read one call each.** The engine has no read of several bank lines by
  their ids, so the screen of a close's flagged lines reads each line by its own id. Engine ask
  "The bank-line list reads several lines by their ids in one call", in
  [to-engine/](../to-engine/). (Task 5.)
- **A completed statement's footer still offers `c Complete` and `d Delete`.** The picked
  mockup's statement pane (1A, after `esc`) draws `esc Back  r Refresh  u Revert  f Flagged  ?
  Keys`; the screen shows `c` and `d` on a completed statement too, as before this spec.
  (Task 5.)
- **The sheet reader keeps an unused keyword.** `read_workbook`'s `sheet_name` in
  [expense/import_/reader.py](../../expense/import_/reader.py) has no caller passing it since
  the bank door stopped reading files. (Task 6.)
- **One live test builds its download body by hand.** `test_reserved_name_held.py` (around line
  219) writes its own header and body where the shared `download_body` and `CURRENT_HEADER` in
  the contract conftest now do it. (Task 7.)
- **The `!` helper's name and one tui.md sentence still speak of blocking.** `blocking_windows`
  in [reconciliations.py](../../expense/tui/screens/reconciliations.py) names what is now a
  "dated inside a statement" hint, and [tui.md](../tui.md) (around line 559) says "the engine
  stays the authority at close time", though the close decides nothing about these lines.
  (Task 8.)
- **A tick refusal test fakes a reason the engine lacks.** The first case of the tick-refusal
  test in test_tui_reconcile_detail.py sends `PERIOD_SEALED` ("Period is sealed."); the engine's
  reason is `SEALED_PERIOD`, and a tick is never refused for sealing. (Task 3.)
- **Two mockups show old refusal words.** `expense-world-split-transaction-screen.html` (a part's
  amount stating both totals) and `expense-world-edit-part.html` ("Another part of this bank line
  …"). (Task 3.)
