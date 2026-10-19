# Catch up with the frozen archived account

**Status: draft, 2026-10-18.** The owner picked its screens; its tasks wait for approval.
**Catches up to contract `ab14bd54f4c8b016`:** every contract change after `15063ec5587491ad`.
It holds the engine's hand-off "An archived account is frozen except for its transactions'
categorisation". What it asks of this client is in the tasks, and its checks are in "The
engine's checks". When done, the why moves to [decisions.md](../decisions.md), and this file is
deleted.

---

## What it must do

**An archived account's history stays as it is.** Of its transactions, only the category, the
hashtags and the note change, and a title that is still empty can be filled once. Their amount,
date, title and account don't change, and they can't be split or deleted. Its reconciliations
don't change at all. Unarchiving the account in Manage ▸ Accounts (`a`) lifts all of it.

**The app doesn't offer what is frozen.** The owner's picks of
[expense-world-archived-account.html](../mockups/expense-world-archived-account.html), 2026-10-18:

1. **The ledger (screen 1 A):** with the cursor on an archived account's transaction, `s` Split
   and `d` Delete leave the footer. The row looks as it does on any other account.
2. **The Edit form (screen 2 B):** on such a transaction, date, title, amount and account are
   read-only and skipped, drawn as an opening balance's read-only lines are today, with no line
   saying why. A title that is still empty stays editable until it is filled.
3. **A refusal (screen 3 A):** a frozen change sent anyway (a screen opened before the account
   was archived, or a bulk `b` that includes such rows) shows the engine's words alone, as
   every refusal shows today. Nothing changes.
4. **Reconciliations (screen 4 A):** the Reconciliations screen keeps listing only active
   accounts, so an archived account's reconciliations don't appear.

## How the owner knows it is done

1. In the ledger, on a transaction of an archived account, `c`, `h` and `⏎` work, and `s` and
   `d` are not in the footer; on the next row, of an active account, they are.
2. `⏎` on it opens the Edit form with date, title, amount and account read-only; changing its
   category saves.
3. After unarchiving the account, the same transaction can be split and deleted again.
4. A frozen change sent from a screen opened before the account was archived shows the engine's
   words, and nothing changes.

## The engine's checks

The engine's own "Done when" for this range. The tester's acceptance check runs them, and the
reply to the engine reports each result.

1. The TUI has stored `ab14bd54f4c8b016` as the version it was checked against.
2. The TUI no longer offers the frozen writes on an archived account's transactions, and lists
   no archived account's reconciliations (the engine's "points to unarchiving" is the engine's
   own words in a refusal, as the owner picked).
3. `ACCOUNT_ARCHIVED` is shown with its message wherever the TUI calls one of the eight routes
   that answer it.
4. The TUI's archived-account contract test is turned around, and the contract tests pass
   against a practice engine started fresh on `ab14bd54f4c8b016`.

## What the engine declined

Nothing; the hand-off answers no ask. Its point 5 (a blank reconciliation `name` on a missing
reconciliation answers `404` before `EMPTY`) needs nothing here: no screen sends a
reconciliation's `name`.

## Tasks

Drafted 2026-10-18 from the owner's picks; wait for the owner's approval.

1. **The live contract tests follow the freeze.** The archived-account test in
   [test_resources_lifecycle.py](../../tests/contract/test_resources_lifecycle.py) is turned
   around: on an archived account's transaction, `PUT` of `category_id`, `hashtag_ids` and
   `description` goes through; `PUT` of each of `amount_cents`, `date`, `title`,
   `operation_code`, `account_id` and `reconciliation_id`, at its current value too, is `422`
   `ACCOUNT_ARCHIVED` on that key, and a mixed `PUT` writes nothing and names only the frozen
   keys; an empty `title` is filled once and then refused; `DELETE /transactions/{id}` and
   `DELETE /bank-lines/{id}` are `409`, the split `422`, all `ACCOUNT_ARCHIVED`, the balance
   unchanged; a row also in a completed reconciliation answers `ACCOUNT_ARCHIVED`, not
   `LOCKED`. On its reconciliations, draft and completed, `PUT /reconciliations/{id}` is `422`
   on every field sent, and complete, revert and delete are `409` `ACCOUNT_ARCHIVED`. After
   `POST /accounts/{id}/unarchive` each refused write works again. Moving another account's
   transaction onto an archived one stays `INVALID_REFERENCE`. Run against a practice engine
   stopped and started fresh; every unit fixture passes the drift script. Passes check 4 of the
   engine's.
2. **A refusal on an archived account shows the engine's words alone.** `ACCOUNT_ARCHIVED`, as
   `VALIDATION_ERROR` and as `CONFLICT`, shows on every screen that sends one of the eight
   routes: the ledger's delete and bulk `b`, the Edit form and the bank-line Edit form, the split
   screen's refusal lines, the "no batch" delete, and a reconciliation's `space`, `c`, `u` and
   `d`, with no line of the app's own added. Unit tests: one per screen. Passes 4 above and check 3 of the engine's.
3. **The ledger knows an archived account's rows** from the accounts read's `is_archived`, and
   hides `s` and `d` while the cursor is on one; the row is drawn as any other. Unit tests: the
   footer on such a row and on any other, and after an unarchive. Passes 1 and 3 above.
4. **The Edit form on an archived account's transaction** shows read-only lines alone: date, title,
   amount and account read-only and skipped, a title editable only while it is empty, and the
   save sends only `category_id`, `hashtag_ids`, `description` and an empty title's first
   value. The bank-line Edit form follows the same rule for its fields, its operation code
   included. Unit tests: no frozen key is ever sent, at its current value either. Passes 2 above.

## Reply to the engine

Written once the spec is done, into [to-engine/](../to-engine/), for the owner to hand over.

- **Covers:** contract `15063ec5587491ad` (exclusive) to `ab14bd54f4c8b016` (inclusive),
  answering every section of the hand-off named above.
- **Done when, checked:** the four checks in "The engine's checks" above, with the tester's
  results.
- **Contract problems found:** what the build and the tester's run find.
- **Asks this closes:** none.
