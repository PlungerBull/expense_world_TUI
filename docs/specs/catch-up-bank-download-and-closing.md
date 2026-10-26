# The app catches up with the engine: the bank download, closing a statement, a card's other account

Catches up to contract `592f2467fa3df75a`, from `309e31fd5c266941`: the engine's hand-off of
2026-10-26, its items 1, 3, 4, 6, 8 and 9, and the changed refusal wording of item 7. Its other
items have specs of their own: item 7, a locked field's words, was caught up by its own spec on
2026-10-26, its reply handed over the same day; after this one
come [sheet-import-through-the-engine.md](sheet-import-through-the-engine.md) (item 2) and
[statements-close-from-their-pdf.md](statements-close-from-their-pdf.md) (item 5).

**Status: current (owner, 2026-10-26); its tasks wait for the owner's approval.** When done,
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

---

## Tasks

Drafted 2026-10-26; the loop runs them once the owner approves them. Tasks 1 to 4 can run now;
tasks 5 and 6 wait for their mockup pick.

1. **The second practice key is handled like the first** (point 7). `scripts/practice-engine up`
   passes both keys the reseed prints through to the terminal: the shared practice user's and
   the reserved-names practice user's. [runtime.md](../runtime.md) "Working against the live
   engine" names the second one and the variable it goes in on the contract suite's command line,
   good for one check only like the first; [tests/contract/conftest.py](../../tests/contract/conftest.py)
   gives the tests a client as that user, and a live run without the variable fails those tests
   naming it. A test in [test_claude_hooks.py](../../tests/unit/test_claude_hooks.py) proves the
   guard keeps the second key out of files as it does the first.
2. **A card's other account comes from the engine on Reconciliations** (point 3). Every place
   Reconciliations pairs a card's two accounts (the list's columns, a new card statement's two
   halves) reads the account's `statement_partner_id` (contract: GET /v1/accounts), never matching
   statement codes: `code_holders`, `statement_partners` and `statement_accounts` in
   [reads.py](../../expense/reads.py) go, or keep only what is not pairing. The unit tests'
   accounts carry `statement_partner_id`. A live test reads a card's two accounts naming each
   other, and `null` on an account with no code and on one whose code no other account holds.
   Nothing you see changes. (The import door's account list changes with its rewrite, task 6.)
3. **The engine's current words in the tests, and a statement's last day** (points 4 and 5). No
   unit test quotes a part's refusal starting "Part … of this bank line is the cause", or a parts
   total refusal stating both totals; each quotes the engine's current words. The app's words
   about sealed days ([tui.md](../tui.md), hints, code comments) say a completed statement locks
   its days but the last, which locks once the next statement is completed too; the app shows
   the engine's refusal as it comes and computes nothing. The live sealed-period tests prove the
   last day open until the next statement completes, and leave no `contract-seal-…` account
   behind.
4. **A held reserved name, live** (point 6). As the reserved-names practice user, a live test
   draws `RESERVED_NAME_HELD` on each route the engine's check names, reading the routes from the
   live contract; each refusal writes nothing.
5. **[UI] Completing a statement shows the lines it flagged** (point 2). First a mockup of where
   the flagged lines show after complete, each leading to its line; the task waits for the
   owner's pick. Then: complete goes through whenever the engine takes it, and nothing in the
   app or its unit tests treats leftover lines as a refusal of complete (the
   `UNASSIGNED_IN_PERIOD` test in
   [test_tui_reconcile_detail.py](../../tests/unit/test_tui_reconcile_detail.py) goes); the fake
   engine answers a complete with each half's `review_lines` and the `twin`, as the real one does
   (contract: POST /v1/reconciliations/{reconciliation_id}/complete); a card shows both halves'
   lines. The live tests stop expecting the refusal ([test_card_statement.py](../../tests/contract/test_card_statement.py),
   [test_statement_order.py](../../tests/contract/test_statement_order.py)) and prove a close
   flagging a leftover line, on a card on both halves.
6. **[UI] A bank download goes to the engine whole** (point 1). First a mockup of the import
   door's account list, preview and result, the task waiting for the owner's pick. Then: the door
   sends the file itself (`dry_run`, `account_id`, `file`; contract: POST /v1/transactions/import)
   and reads no cell of it; [parse.py](../../expense/bank_import/parse.py) and every other piece
   of the app's own bank-file reading go (the sheet import's reader stays: it has its own spec).
   The preview names each row by its spreadsheet row number, shows and counts a `skipped` row,
   and shows a refused row on that row in the engine's words; a refused file shows the engine's
   words. The account list pairs a card through `statement_partner_id`. Every row of the file
   goes in, whatever its date: the 2026 rule (`IMPORT_FLOOR`) goes. The backlog item "Leftovers
   in the import door" is deleted with it. Live tests ([test_bank_import.py](../../tests/contract/test_bank_import.py)) build a
   made-up download in the test itself, never a real file: a dry run and an apply, a card's
   rows landing on both its accounts, a zero row skipped.

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

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
