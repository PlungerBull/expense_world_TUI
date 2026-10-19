# Caught up with contract ab14bd54f4c8b016: an archived account is frozen except for its transactions' categorisation

2026-10-18

## Covers

Contract `15063ec5587491ad` (exclusive) to `ab14bd54f4c8b016` (inclusive). It answers every
section of your hand-off "An archived account is frozen except for its transactions'
categorisation".

What the TUI does now:

- It read the `6088c6255f258ce7`, `98fd5c39226bc126` and `ab14bd54f4c8b016` entries of
  `x-changelog`, and its saved contract version is `ab14bd54f4c8b016`.
- **The ledger** reads `is_archived` from the `GET /accounts?include_archived=true` it already
  makes, and on a transaction whose account is archived it no longer offers split or delete.
  Category, hashtags, note and the Edit form stay offered.
- **The Edit forms** (a transaction, and a bank line in a reconciliation's "no batch" list) show
  amount, date, title, account and, on a bank line, operation code read-only on such a
  transaction. An empty title or operation code stays editable until it is filled. The form
  sends only the fields that changed, and never a frozen key, not even at its current value.
- **Reconciliations:** the TUI lists only active accounts on its Reconciliations screen, so an
  archived account's reconciliations are not offered at all.
- **`ACCOUNT_ARCHIVED`**, as `422 VALIDATION_ERROR` and as `409 CONFLICT`, shows in your words,
  with the field messages, on every screen that calls one of the eight routes: transaction
  delete, bank-line delete, split, transaction `PUT` (one row and bulk), and a reconciliation's
  `PUT`, complete, revert and delete. The TUI adds no words of its own to it. This covers a
  screen opened before the account was archived. The TUI does not offer to unarchive from the
  refusal: your message already says to, and unarchiving stays on the accounts screen.
- **Your point 5** (a blank `name` on a missing reconciliation answers `404` before `EMPTY`)
  needs nothing here: the TUI never sends a reconciliation's `name`.

## Done when, checked

Checked on 2026-10-18 against a practice engine started fresh, serving `ab14bd54f4c8b016`. The
TUI's full contract suite passed: 117 tests. Seven of them are new for this range, and they
replace the test that asserted the old behaviour.

| Check | Result |
|---|---|
| The TUI has stored `ab14bd54f4c8b016` | worked: its saved version is `ab14bd54f4c8b016`, and its version check reports no move. |
| It no longer offers the frozen writes on an archived account | worked. Live, through the TUI's screens: on an archived account's transaction the ledger offered no split or delete, while the next active-account row did. The Edit form showed amount, date, title and account read-only, and a category change sent `{"category_id": …}` alone. After `POST /accounts/{id}/unarchive` and a refresh, the same transaction was split and then deleted. The archived account's draft reconciliation was not listed. |
| `ACCOUNT_ARCHIVED` is shown wherever these routes are called | worked. Live, from a ledger loaded before the account was archived: the delete showed `CONFLICT — Cannot delete a transaction on an archived account. Unarchive the account first.` with its `transaction_id` line, and the split showed your `VALIDATION_ERROR` words under the parts. Nothing changed either time. The TUI's unit tests cover the other routes, one per screen. |
| The archived-account test is turned around | worked. On an archived account's transaction: `category_id`, `hashtag_ids` and `description` go through. Each of `amount_cents`, `date`, `title`, `operation_code`, `account_id` and `reconciliation_id`, at a new value and at its current one, is `422` `ACCOUNT_ARCHIVED`. A mixed `PUT` writes nothing and names only the frozen keys. An empty title and an empty operation code fill once. Both deletes (a split line included) are `409`, and the split is `422`. A row in a completed reconciliation answers `ACCOUNT_ARCHIVED`, not `LOCKED`. On a draft and a completed reconciliation, `PUT` of every field is `422`, and complete, revert and delete are `409`. After unarchiving, every one of these writes works again, a reconciliation's complete included. A move onto an archived account stays `INVALID_REFERENCE`. |

## Contract problems found

- **Lines whose parts are on different accounts or days.** The contract describes such lines in
  three places: the reason `SPLIT_LINE_PARTS_DIVERGE`, the import's match by operation code only
  for "a line whose parts are on different accounts or days", and "Another part on an archived
  account refuses too". But the TUI found no public route that builds one with parts on two
  accounts: a split keeps the line's account, a batch `line_group` must share it
  (`LINE_GROUP_FIELDS_DIFFER`), and a `PUT` of a line field writes it onto every part. So no client can reach or test those rules. Can such lines
  exist, and how? If they cannot, those rules can go.
- **Not the contract, the practice setup.** The TUI's notes say `seed-test-user.sh --force`
  drops the practice user's rows. During this check, accounts made before a reseed were still
  listed after it. If the reseed is meant to keep them, say so and the TUI's notes will follow.

## Asks this closes

None.
