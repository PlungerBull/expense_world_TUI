# A bank line is read, reconciled, deleted and listed whole; the import moves a code-matched line to the bank's day; six contract texts are corrected

Shipped 2026-10-17 · ⚠️ breaking · contract `890453f80a08cec9` (exclusive) → `786d68f3b071dbf4` (inclusive)

Answers: "A bank line is reconciled whole: assigning or unassigning one part does the same to every part" (2026-10-17), "Deleting a bank line deletes every one of its parts, in one write" (2026-10-17), "The ledger can be read one bank line per row, with each line's parts inside" (2026-10-17), and the two contract questions in the TUI's catch-up to `890453f80a08cec9` (2026-10-17).

This one file covers every contract version after `890453f80a08cec9`, the last one the TUI has read, through `786d68f3b071dbf4`, with no version skipped: `ce4e5cb642e53fdb`, `0e71bf2787f9464e`, `5572fee599cd06e8`, `1baf89c4d8dd9f40`, `7ff6a09d863d6e44`, `1efa6f4627ff9acf`, `786d68f3b071dbf4`. It describes where each route ends up at `786d68f3b071dbf4`, not the steps in between; the `x-changelog` in `GET /openapi.json` has one entry per version. It replaces the earlier, longer version of this answer ("A bank line is read, reconciled, deleted and listed whole; the import's mismatched days show what each unclaimed line is; system rows keep their names"); drop it unread. Check `info.version` in `GET /openapi.json` before relying on anything here.

## Each ask

- **A bank line is reconciled whole:** done as asked. Point 2 needed no change: no create route accepts a reconciliation, and a split already puts every part in the line's reconciliation. Point 3: no settling logic, because the owner's ledger is wiped and re-imported before go-live; the ledger update refused to run if a line was half in a reconciliation (it found none), and the database refuses such a line from then on. Point 4: `SPLIT_RECONCILIATION_MIXED` is no longer sent, and the reconciliation refusals "caused by another part" no longer arise.
- **Deleting a bank line deletes every one of its parts:** done, with one change: the completed-reconciliation refusal is keyed on `bank_line_id`, not `transaction_id`, because a delete is keyed by its path id. `DELETE /transactions/{id}` still deletes one part.
- **The ledger can be read one bank line per row:** done differently, by the owner's ruling. **The ledger stays one row per part:** `GET /transactions` and its count are unchanged, so a purchase split 60 + 40 is two ledger rows and counts 2. Only the reconciliation features work on, and list, a purchase as one row: `GET /bank-lines` is that list, with the filters a reconciliation screen needs (`account_id`, dates, `reconciliation_id` / `unreconciled`). `search` is left out, since finding rows by text is the ledger's job; ask if the reconciliation screen needs it. Point 4: no read of several lines is needed beside this list.
- **Question 1, the `OPERATION_CODE_EXISTS` message:** fixed. The `409` message now names a bank line (5 below).
- **Question 2, how to produce `SPLIT_LINE_PARTS_DIVERGE`:** the TUI cannot. Every write of the contract moves a line's parts together, so no client write leaves a line whose parts are on different accounts or dates. The refusal guards a line whose parts were set apart outside the contract. It stays declared, and the contract now says so (5 below). Keep handling it like any other `422` on the split; there is nothing to test it with.

## What changed

### 1. Reading one line returns its parts: `GET /bank-lines/{id}` (`1baf89c4d8dd9f40`), ⚠️ breaking

```json
{
  "id": "8c1e…",
  "account_id": "3f0a…",
  "operation_code": "123456",
  "net_cents": -10000,
  "part_count": 2,
  "parts": [
    { "id": "a1…", "title": "WONG", "amount_cents": 6000, "transaction_type": 1,
      "category_id": "…", "hashtag_ids": ["…"], "bank_line_id": "8c1e…", "…": "…" },
    { "id": "b2…", "title": "WONG", "amount_cents": 4000, "transaction_type": 1,
      "category_id": "…", "hashtag_ids": ["…"], "bank_line_id": "8c1e…", "…": "…" }
  ]
}
```

- **`transaction_ids` is removed.** Read each part's `id` from `parts`.
- `parts` are the line's live parts, each exactly what `GET /transactions/{id}` returns for it, in the order `GET /transactions?bank_line_id=` lists them by default: by `date`, then `created_at`, then `id`, newest first. A transaction never split is a line with one part.
- `net_cents` is the **signed** sum of the live parts: inflow positive, outflow negative. A charge of 100 split 60 + 40 reads `-10000`; a line can mix directions (−60 + 15 reads `-4500`).
- `part_count` is always the length of `parts`. The figures and the parts are read together, so they always agree.
- `operation_code` is `null` when the line has none; the key is always present. No home-currency value.
- `404` when the id names no live line of yours; a malformed id is `422` on `bank_line_id` (`INVALID_FORMAT`). Takes no query parameters.

### 2. A bank line is reconciled whole (`ce4e5cb642e53fdb`, ⚠️ breaking; `0e71bf2787f9464e`)

- **`reconciliation_id` is a line field,** like `title`, `date`, `account_id` and `operation_code`. `PUT /transactions/{id}` sending it assigns, moves or unassigns **every live part** of the line in one write. Each other part it changes gets its own `updated` activity entry and its `version` bumps by one; a part that already has the value is not written. The response is the transaction named by `{id}`.
- **Breaking:** assigning or unassigning one part bumps the `version` of every other part it changes. Re-read a part's `version` after sending `reconciliation_id` on another part of its line. Sending it once is enough; there is no need to send it on each part.
- Every assignment rule (`INVALID_REFERENCE`, `ACCOUNT_MISMATCH`, `RECONCILIATION_COMPLETED`) and the field lock (`LOCKED`) is checked on every part it would write; if one refuses, nothing changes.
- Moving a line to another account with `reconciliation_id` in the same request settles every part (`null` unassigns them all; a draft on the new account puts them all in it). Without it, while the line is in a draft: `422 ASSIGNED_TO_RECONCILIATION` on `account_id`, as before.
- **A line's live parts are always in one reconciliation, or all in none.** The database refuses anything else. So:
  - `LOCKED` and `ASSIGNED_TO_RECONCILIATION` are the line's own refusals: the message never names another part. A refusal naming another part ("Another part of this bank line (<id>) is the cause: …") now comes only from a rule that can differ between parts: a sealed period, an opening balance, or a reconciliation on another account.
  - `POST /transactions/{id}/split` no longer declares or sends `SPLIT_RECONCILIATION_MIXED` (`0e71bf2787f9464e`). The reason stays defined, and its text says it is no longer sent.
- A reconciliation's `difference_cents`, `POST /reconciliations/{id}/complete` and `GET /transactions?reconciliation_id=` take in every part of each line it holds.
- A locked `title` that is `null` may be filled only while it is `null` on every part of the line.
- An assignment racing a delete of its reconciliation, or an edit of a reconciliation racing its complete, now runs one after the other: an assignment never lands on a deleted reconciliation, and an edit never changes a reconciliation that has just been completed. No status, key or reason changed.

### 3. Delete a line whole: `DELETE /bank-lines/{id}` (`5572fee599cd06e8`), additive

- Soft-deletes every live part of the line in one write, all or nothing, each exactly as `DELETE /transactions/{id}` deletes it, with its own `deleted` activity entry.
- Returns `200` with `{"parts": [...]}`: each part as `DELETE /transactions/{id}` returns its row (`deleted_at` set, `hashtag_ids` `[]`), in the order `GET /transactions?bank_line_id=` listed them by default.
- The line goes with its parts: its `operation_code` is free again on the account, and the account's balance drops the whole line at once.
- A line in a completed reconciliation is `409 CONFLICT` on `bank_line_id` (`IN_COMPLETED_RECONCILIATION`), judged on every part before anything changes; nothing is deleted.
- An id that names no live line of yours is `404`; a malformed id is `422` on `bank_line_id` (`INVALID_FORMAT`). Standard idempotency.
- `DELETE /transactions/{id}` is unchanged and still deletes one part.

### 4. The reconciliation list: `GET /bank-lines` and `GET /bank-lines/count` (`7ff6a09d863d6e44`), additive

- **One row per live bank line,** each exactly what `GET /bank-lines/{id}` returns, so a split purchase is one row holding every part. The ledger (`GET /transactions`) is unchanged and stays one row per part.
- **Order:** newest first, by the line's date, then its parts' `created_at`, then the line's `id`: a line sits where its parts sit in the ledger's default order. There is no `sort`.
- **Paging** as on `GET /transactions`: `{items, limit, next_cursor}`, `limit` `[1, 200]` default 50, `after=<next_cursor>`, `offset` refused. `limit` counts **lines**, and a page never cuts a line in two. A cursor is bound to the list that issued it and to its filters: a `GET /transactions` cursor sent here, or one from here sent to the ledger, is `422 INVALID_CURSOR` on `after`.
- **Filters, each applying to a whole line:** `account_id`, `reconciliation_id`, `unreconciled=true` (with `reconciliation_id` it is `422` on `unreconciled`, `CONFLICTING_PARAMETERS`), and `date_from` / `date_to`, read exactly as on `GET /transactions` (a bare day in `display_timezone`, or an RFC 3339 instant). Any other parameter — `search`, `category_id`, `hashtag_id`, `bank_line_id`, `sort`, `debit_as_negative` — is `422` (`UNKNOWN_PARAMETER`). `422 SETTINGS_MISSING` before bootstrap, like the ledger.
- `GET /bank-lines/count` → `{"count": n}` for the same filters and the same refusals. A purchase split 60 + 40 counts 1 here and 2 on `GET /transactions/count`. The list's pages add up to it.

### 5. The import moves a code-matched line to the bank's day (`1efa6f4627ff9acf`), additive

When a file row matches a ledger line by `operation_code` and the bank has another day, the apply now moves the line to the bank's day: every part whose `date` differs takes 00:00 of the row's day in `display_timezone`, the way the import dates the rows it creates. A line whose parts are on different days counts as differing. A `same_day` match never moves anything.

**The move is not made** when the line is in a completed reconciliation, or when the bank's day falls inside a sealed period of the line's account. The row is still `matched`, its title and code are still written as before, its date stays, and every other row of the file is applied. A stopped move is not an error.

**Two new keys on every row,** always present, on the dry run and the apply alike:

| Key | Value |
|---|---|
| `redated` | `true` when the line is (on a dry run: would be) moved to the bank's day; `false` on any other `matched` row; `null` on a `new` or `sealed` row |
| `redate_blocked_by` | the id of the completed reconciliation that stopped the move — the line's own when it is in one, else the one sealing the bank's day; `null` otherwise |

`counts` gains `redated`, the number of lines moved.

A moved line (WONG −100.00 split 60 + 40, coded `123456`, on 3 October in the ledger; the bank has it on 4 October):
```json
{ "id": "…", "outcome": "matched", "rule": "operation_code", "bank_line_id": "8c1e…",
  "backfill_code": null, "retitled": false, "sealed_by": null,
  "redated": true, "redate_blocked_by": null }
```

The same line, inside a completed reconciliation:
```json
{ "id": "…", "outcome": "matched", "rule": "operation_code", "bank_line_id": "8c1e…",
  "backfill_code": null, "retitled": false, "sealed_by": null,
  "redated": false, "redate_blocked_by": "65008eff-…" }
```

- `day_mismatches` counts a moved line on the bank's day, not its old one, on the dry run as on the apply, so the move itself never makes two days disagree.
- Each part moved gets one `updated` activity entry; a part moved and retitled in the same apply gets one entry carrying both changes.
- Unchanged: a file row that matches nothing is created, and its day is reported if it still does not add up. A ledger −45.00 against a statement −45.50 on one day, no codes, stays two rows: the −45.50 is created and the day is reported with both.

### 6. Six contract texts and the settings rule (`786d68f3b071dbf4`), wording only

No status, key, reason or behaviour changed. What the engine sends:

| Text | Before | Now |
|---|---|---|
| `409 OPERATION_CODE_EXISTS` message (`POST /transactions`, `PUT /transactions/{id}`, `POST /transactions/batch`, `POST /transactions/import`) | `"A transaction with operation code '<code>' already exists on this account."` | `"Another bank line on this account already has operation code '<code>'."` |
| `409 ID_EXISTS` message on an account (`POST /accounts`, `POST /people`) | `"A account with id '<id>' already exists."` / `"A account with this id already exists."` | `"An account with id '<id>' already exists."` / `"An account with this id already exists."` (every other resource unchanged, `POST /auth/pat` included) |
| `IN_COMPLETED_RECONCILIATION` reason text | "The transaction is assigned to a completed reconciliation. Revert the reconciliation to draft first." | "The transaction, or the bank line, is assigned to a completed reconciliation, so it cannot be deleted. Revert the reconciliation to draft first." |

What the contract says:
- *Cursors* and `GET /transactions`: a cursor is bound to the list that issued it as well as to its filters; another list's cursor is `422` on `after` (`INVALID_CURSOR`), as it already was.
- `PUT /transactions/{id}` → *Line fields* points to *Reconciliations* → *Assigning transactions* for the account match.
- `SPLIT_LINE_PARTS_DIVERGE`, in its reason text and in `POST /transactions/{id}/split`: no write of the contract produces it (Each ask, question 2).
- *Settings preconditions* (published under `PUT /auth/settings`) says exactly which requests answer `422 SETTINGS_MISSING`: every request of the routes it lists, except `PUT /transactions/{id}`, which needs the settings only when the body sends `date` or `account_id` (even at its current value), and `POST /reconciliations/{id}/complete`, only on a reconciliation already completed or on a draft past the ending-balance and assigned-transaction checks. It also lists which refusals of those two routes answer before the settings are read and which after.

## How it was checked

Two runs against the practice engine, over the wire, each after the engine's full test suite passed. Every check is one of the asks' own **Done when**, or one the engine added. All passed, except one check only the owner can run, marked below.

**Run 1, 2026-10-17, practice engine on `7ff6a09d863d6e44`** (suite: 1527 tests). Every example is a −100.00 charge split into −60.00 and −40.00.

| Check | Result |
|---|---|
| Assigning one part to a draft reconciliation assigns both; unassigning either part unassigns both (tried through each part) | pass |
| No line has parts in different reconciliations, or some in one and others in none (checked on the practice database; the owner's ledger is checked by the update that installs the rule, which refuses to run otherwise) | pass |
| Changing the date of a part whose line is in a completed reconciliation: `422` `LOCKED` on `date`, and the message names no other part | pass |
| Completing a reconciliation holding the split line counts its full total: ending balance −100.00, `difference_cents` 0, complete `200` | pass |
| `DELETE /bank-lines/{id}`: `200` with both parts, both `GET /transactions/{id}` and `GET /bank-lines/{id}` then `404`, balance from −100.00 to 0 in one request | pass |
| Deleting a line in a completed reconciliation: `409`, `IN_COMPLETED_RECONCILIATION` on `bank_line_id`; both parts still live | pass |
| A one-part line deletes like `DELETE /transactions/{id}`: the same row (inside `parts`), the same balance effect | pass |
| Two single transactions plus the split: `GET /bank-lines?account_id=` lists 3 rows and counts 3; the split row has `part_count` 2, `net_cents` −10000 and both parts | pass |
| With `limit=1`: three pages, each line whole on its page, in the same order as without a limit | pass |
| `?account_id=` lists only that account's lines; a date range lists the lines on those days, and the count agrees | pass |
| Splitting a single, changing a part's amount (60 → 70: `net_cents` −11000), deleting a part (`part_count` 1): each shows on the next read | pass |
| `POST /transactions/{id}/split` declares no `SPLIT_RECONCILIATION_MIXED`, and no route does | pass |
| `GET /bank-lines/{id}` equals that line's row in `GET /bank-lines` | pass |
| The ledger is unchanged: the split is two rows on `GET /transactions` and counts 2, against 1 row on `GET /bank-lines` | pass |

**Run 2, 2026-10-17, practice engine on `786d68f3b071dbf4`** (suite: 1560 tests).

| Check | Result |
|---|---|
| WONG −100.00 split 60 + 40, coded `123456`, 3 October; file row `123456` on 4 October. Dry run: `matched`, `operation_code`, `redated: true`, `counts.redated` 1, nothing moved yet. Apply: both parts on 4 October 00:00 (Lima); `day_mismatches` empty; each part has exactly one new `updated` entry, date 3 → 4 October | pass |
| The same line inside a completed reconciliation: `matched`, `redated: false`, `redate_blocked_by` = that reconciliation; the line stays on 3 October; the file's other row is created | pass |
| The same with 4 October inside a completed reconciliation covering 4–10 October: the same outcome, `redate_blocked_by` = the sealing reconciliation | pass |
| A `same_day` match, and a code match on the same day: `redated: false`, `counts.redated` 0, no date changed, no `updated` entry | pass |
| Ledger −45.00 and statement −45.50 on one day, no codes: the row is `new` and created (4550, outflow); the day is reported with `file_net_cents` −4550, `ledger_net_cents` −9050 and the −45.00 as an unclaimed line | pass |
| `OPERATION_CODE_EXISTS` sent: `409` `"Another bank line on this account already has operation code '123456'."` | pass |
| `ID_EXISTS` on an account: `409` `"An account with id '<id>' already exists."`, field message `"An account with this id already exists."` | pass |
| `DELETE /bank-lines/{id}` and `DELETE /transactions/{id}` on a completed reconciliation's line: `409 IN_COMPLETED_RECONCILIATION` on `bank_line_id` and `transaction_id`; the reason text names both | pass |
| Without settings: `PUT /transactions/{id}` with only `title` → `200`; with `date`, or `account_id` at its current value → `422 SETTINGS_MISSING`. `POST /reconciliations/{id}/complete` with no ending balance → `ENDING_BALANCE_REQUIRED`; with nothing assigned → `NO_TRANSACTIONS_ASSIGNED`; past both → `SETTINGS_MISSING` | pass |
| The cursor, *Line fields*, `SPLIT_LINE_PARTS_DIVERGE` and *Settings preconditions* texts read as in 6, in the practice engine's `GET /openapi.json` | pass |
| The two reconciliation races (an edit against a complete, an assignment against a delete), forced in the engine's tests, five runs each | pass |
| The owner's health check passes a healthy engine right after a restart | pass in the engine's tests; the owner's own run is still to come (engine-side only, nothing for the TUI) |

**Where it runs:** both the live engine and the practice engine serve `786d68f3b071dbf4`. Check `info.version`.

## What the TUI does

1. **Opening a purchase (breaking):** read `GET /bank-lines/{id}` once and use its `parts`; stop reading `transaction_ids`. `net_cents` is the total a re-split must match. No search around the date, no second call, no client-side sum.
2. **Editing a part's title, date, account, operation code or reconciliation:** when `part_count` is above 1, the change reaches every part; warn as the TUI sees fit.
3. **Ledger:** unchanged, one row per part from `GET /transactions`. A part row can offer "delete purchase" through its `bank_line_id`.
4. **Reconciliation screen:** draw it from `GET /bank-lines` with `account_id`, the period's dates and `unreconciled=true` or `reconciliation_id`, and its count from `GET /bank-lines/count`. Ticking a purchase is one `PUT /transactions/{id}` with `reconciliation_id` on any one of its parts; unticking sends `null`. Re-read the other parts' `version` after it (breaking). Never build a screen explaining a refusal caused by another part for reconciliation.
5. **Deleting a purchase:** `DELETE /bank-lines/{id}`, behind a confirmation screen (the owner's rule). Handle `409 IN_COMPLETED_RECONCILIATION` on `bank_line_id`. `DELETE /transactions/{id}` still deletes one part.
6. Drop any handling of `SPLIT_RECONCILIATION_MIXED`.
7. **Import screen:** read `redated`, `redate_blocked_by` and `counts.redated`. On the dry run, mark a row with `redated: true` as "moves to the bank's day" (show the line's current date and the file's date); mark a row with `redate_blocked_by` as "keeps its date: reconciliation <name> is completed", looking the name up by id. Show the number of lines moved beside the other counts. If the TUI checks the exact set of row or count keys, add the new ones.
8. **Texts:** if the TUI quotes any message from 6 (the `OPERATION_CODE_EXISTS` or account `ID_EXISTS` text), use the new wording or, better, the reason. Nothing else changes.
9. Record `786d68f3b071dbf4` as the last version read once every step above is in the TUI's plan.

## Done when

- Opening a purchase is one `GET /bank-lines/{id}` read from `parts`; the TUI adds no amounts of its own and reads no `transaction_ids`.
- The reconciliation screen lists purchases from `GET /bank-lines`, ticks a purchase with one `PUT` on any part, and never shows half a purchase ticked.
- Deleting a purchase is one `DELETE /bank-lines/{id}` behind a confirmation, from the ledger or the reconciliation screen.
- `IN_COMPLETED_RECONCILIATION` on `bank_line_id` has a handled path; no code handles `SPLIT_RECONCILIATION_MIXED`.
- The import screen shows, before applying, which code-matched lines will move to the bank's day and which keep their date because of a completed reconciliation, and shows the moved count after applying.
