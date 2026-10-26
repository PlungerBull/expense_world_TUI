# The app catches up with the engine: the bank download, closing a statement, a card's other account

Catches up to contract `592f2467fa3df75a`, from `309e31fd5c266941`: the engine's hand-off of
2026-10-26, its items 1, 3, 4, 6, 8 and 9, and the changed refusal wording of item 7. Its other
items have specs of their own: item 7, a locked field's words, was caught up by its own spec on
2026-10-26, its reply waiting in [to-engine/](../to-engine/) to be handed over; after this one
come [sheet-import-through-the-engine.md](sheet-import-through-the-engine.md) (item 2) and
[statements-close-from-their-pdf.md](statements-close-from-their-pdf.md) (item 5).

**Status: draft, for the owner to rewrite or approve. Its tasks are drafted when the owner names
it the current spec.** When done, the why moves to [decisions.md](../decisions.md) and this file
is deleted.

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

None beyond the two mockup picks (points 1 and 2), made when the spec starts.

---

## Tasks

Drafted when the owner names this the current spec.

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
