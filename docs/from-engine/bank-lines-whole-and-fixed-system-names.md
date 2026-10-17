# A bank line is read, reconciled, deleted and listed whole; the import's mismatched days show what each unclaimed line is; system rows keep their names

Shipped 2026-10-17 · ⚠️ breaking · contract `3129bfa2c43a4446` (exclusive) → `7ff6a09d863d6e44` (inclusive)

Answers: "Let a client read a bank line" (2026-10-16), "A bank import's unclaimed ledger lines carry their total and their parts" (2026-10-16), "The built-in categories and the built-in pending hashtag cannot be renamed" (2026-10-16), "A bank line is reconciled whole: assigning or unassigning one part does the same to every part" (2026-10-17), "Deleting a bank line deletes every one of its parts, in one write" (2026-10-17), "The ledger can be read one bank line per row, with each line's parts inside" (2026-10-17).

This one file covers every contract version after `3129bfa2c43a4446`, the last one the TUI has read, through `7ff6a09d863d6e44`, with no version skipped: `3d7205a872889283`, `c572d3a5f4f509d1`, `a924900619285f56`, `aa72f160099133ac`, `890453f80a08cec9`, `ce4e5cb642e53fdb`, `0e71bf2787f9464e`, `5572fee599cd06e8`, `1baf89c4d8dd9f40`, `7ff6a09d863d6e44`. It describes where each route ends up at `7ff6a09d863d6e44`, not the steps in between; the `x-changelog` in `GET /openapi.json` has one entry per version. It replaces every earlier version of this answer, and the answers "A bank line can be read — its parts, signed total and part count — …" and "System categories and the pending hashtag can no longer be renamed"; drop them unread. Check `info.version` in `GET /openapi.json` before relying on anything here.

## Each ask

- **Let a client read a bank line:** done, with changes. `?bank_line_id=` on the ledger as asked. The read of one line returns the parts themselves, not their ids, so opening a line is one call. **The read of up to 200 lines per call is declined:** `GET /bank-lines` (the last ask) replaces it. Also declined: a line's total and part count on every transaction response. A transaction carries `bank_line_id` only, because copying another record's figures onto it would break the rule that responses name other records by id only, and would change a transaction's response without its `version` moving.
- **Unclaimed lines carry their total and their parts:** done as asked, plus a new reporting rule (3 below). Declined: a shorter part shape with a signed `amount_cents`. Every response returns `amount_cents` positive with the direction in `transaction_type`; only totals are signed.
- **System rows keep their names:** done as asked.
- **A bank line is reconciled whole:** done as asked. Point 2 needed no change: no create route accepts a reconciliation, and a split already puts every part in the line's reconciliation. Point 3: no settling logic, because the owner's ledger is wiped and re-imported before go-live; the ledger update refuses to run, naming each line, if a line is half in a reconciliation, and the database refuses such a line from then on. Point 4: `SPLIT_RECONCILIATION_MIXED` is no longer sent, and the reconciliation refusals "caused by another part" no longer arise.
- **Deleting a bank line deletes every one of its parts:** done, with one change: the completed-reconciliation refusal is keyed on `bank_line_id`, not `transaction_id`, because a delete is keyed by its path id. `DELETE /transactions/{id}` still deletes one part.
- **The ledger can be read one bank line per row:** done differently, by the owner's ruling. **The ledger stays one row per part:** `GET /transactions` and its count are unchanged, so a purchase split 60 + 40 is two ledger rows and counts 2. Only the reconciliation features work on, and list, a purchase as one row: `GET /bank-lines` is that list, with the filters a reconciliation screen needs (`account_id`, dates, `reconciliation_id` / `unreconciled`). `search` is left out, since finding rows by text is the ledger's job; ask if the reconciliation screen needs it. Point 4: no read of several lines is needed beside this list.

## What changed

### 1. List a line's parts: `?bank_line_id=` on the ledger (`3d7205a872889283`), additive

- `GET /transactions?bank_line_id=<id>` lists exactly the live transactions of that bank line: the ledger's usual ordering, paging and response shape.
- It combines with every other filter. A cursor is bound to it like to any other filter: reusing a cursor with a different `bank_line_id` (or without it) is `422 INVALID_CURSOR` on `after`.
- `GET /transactions/count` takes the same filter.
- An id that names no live line of yours (no such line, a line whose last part was deleted, another user's line) lists nothing and counts `0`. It is never `404`.
- A value that is not a UUID is `422` on `bank_line_id` (`INVALID_FORMAT`).

### 2. Read one line: `GET /bank-lines/{id}` (`c572d3a5f4f509d1`, reshaped in `1baf89c4d8dd9f40`)

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

- `parts` are the line's live parts, each exactly what `GET /transactions/{id}` returns for it, in the order `GET /transactions?bank_line_id=` lists them by default: by `date`, then `created_at`, then `id`, newest first. A transaction never split is a line with one part.
- `net_cents` is the **signed** sum of the live parts: inflow positive, outflow negative, like `ledger_net_cents` and account balances. A charge of 100 split 60 + 40 reads `-10000`; a line can mix directions (−60 + 15 reads `-4500`).
- `part_count` is always the length of `parts`. The figures and the parts are read together, so they always agree.
- `operation_code` is `null` when the line has none; the key is always present. No home-currency value.
- **`404`** when the id names no live line of yours: no such line, a line whose last part was deleted, or another user's line. A malformed id is `422` on `bank_line_id` (`INVALID_FORMAT`). Takes no query parameters.
- **If the TUI has read an earlier version of this answer:** there is no `transaction_ids` key; read each part's `id`.

### 3. Import: unclaimed lines carry their parts (`a924900619285f56`), ⚠️ breaking

`POST /transactions/import` → each `day_mismatches[].unclaimed_lines[]` entry changes.

**Before:**
```json
{ "bank_line_id": "L1", "transaction_ids": ["t301", "t302"] }
```

**Now:**
```json
{
  "bank_line_id": "L1",
  "net_cents": -5000,
  "parts": [
    { "id": "t301", "title": "Plaza Vea", "amount_cents": 3000, "transaction_type": 1,
      "category_id": "…", "description": null, "bank_line_id": "L1", "…": "…" },
    { "id": "t302", "title": "Plaza Vea", "amount_cents": 2000, "transaction_type": 1,
      "category_id": "…", "description": "detergent", "bank_line_id": "L1", "…": "…" }
  ]
}
```

- **`transaction_ids` is removed.** Read each part's `id` instead.
- `parts` are ordinary transaction responses, exactly what `GET /transactions/{id}` returns: `amount_cents` positive, direction in `transaction_type`. They come in the order `GET /transactions` lists them by default. A split line is **one** entry holding all its parts on that day.
- `net_cents` is the parts' signed sum, inflow positive.
- Dry run and apply return the same shape. The parts are the ledger as it stands after the import; the import never writes an unclaimed line, so on a dry run they are the ledger as it stands now.
- **A day's figures add up:** the transactions on lines a file row matched, plus the rows the import creates on that day, plus the unclaimed lines' `net_cents`, equal the day's `ledger_net_cents`.

**New reporting rule** (same version): a day is now reported when its totals differ **or** when it holds a line no file row claimed. A +50 and a −50 in the ledger that the bank does not have used to cancel out and stay hidden; now that day is reported with both lines. A day whose totals agree and whose every line was claimed is still not reported, and an opening balance never makes a day reported. Expect days in `day_mismatches` whose `file_net_cents` equals `ledger_net_cents`.

### 4. `OPERATION_CODE_EXISTS` wording (`aa72f160099133ac`), wording only

The reason text for `OPERATION_CODE_EXISTS` now says the code is held by another live **bank line** on the same account, not another live transaction: the parts of one line share its code. When the `409` is sent, and its key (`operation_code`), are unchanged.

### 5. System categories and the pending hashtag keep their names (`890453f80a08cec9`), ⚠️ breaking

**Which rows:** the two system categories, `@Opening` (`system_key` `"opening_balance"`) and `@Pendiente` (`system_key` `"pending"`), and the built-in pending hashtag, `Pendiente` (`system_key` `"pending"`). Every other category and hashtag is unchanged.

**The refusal**
- `PUT /categories/{id}` on a system category and `PUT /hashtags/{id}` on the pending hashtag trim `name`, as on every name, and it must then be exactly the current name, character for character.
- Any other value is `422 VALIDATION_ERROR` on `name`, reason `SYSTEM_NAME_FIXED`, message `"Must be the current name: a system record keeps its name."`. Nothing is written.
- A change of letter case only is a rename and is refused: `"@pendiente"`, `"PENDIENTE"`.
- It answers before `RESERVED_NAME` and `NAME_EXISTS`: on these rows, a different name is always `SYSTEM_NAME_FIXED`. An empty name is still `EMPTY`, and on a category an invalid `color` is still refused first.

**What stays accepted**
- Sending the current name, or one that trims to it (`"  @Pendiente "`), is an ordinary update: `version` bumps and an `updated` activity entry is written, as for any field sent with its current value.
- On a system category, `color` and `sort_order` stay editable. On the pending hashtag, `sort_order` stays editable.
- Leaving `name` out works as before.
- `DELETE` on any of them is still `403` (`SYSTEM_CATEGORY` on `category_id`, `SYSTEM_HASHTAG` on `hashtag_id`), unchanged.
- The reserved-name rules for the user's own rows are unchanged: no user category may take `@Opening` or `@Pendiente`, and no user hashtag may take `Pendiente` (`422` on `name`, `RESERVED_NAME`).

**Existing data:** any system category or pending hashtag that had been renamed got its default name back, with one `updated` activity entry each recording the old name in its before snapshot. On the owner's ledger none had been renamed. Every system category and the pending hashtag now carry exactly `@Opening`, `@Pendiente` and `Pendiente`.

**Still the rule:** find these rows by `system_key`, never by name.

### 6. A bank line is reconciled whole (`ce4e5cb642e53fdb`, ⚠️ breaking; `0e71bf2787f9464e`)

- **`reconciliation_id` is a line field,** like `title`, `date`, `account_id` and `operation_code`. `PUT /transactions/{id}` sending it assigns, moves or unassigns **every live part** of the line in one write. Each other part it changes gets its own `updated` activity entry and its `version` bumps by one; a part that already has the value is not written. The response is the transaction named by `{id}`.
- **Breaking:** assigning or unassigning one part bumps the `version` of every other part it changes. Re-read a part's `version` after sending `reconciliation_id` on another part of its line. Sending it once is enough; there is no need to send it on each part.
- Every assignment rule (`INVALID_REFERENCE`, `ACCOUNT_MISMATCH`, `RECONCILIATION_COMPLETED`) and the field lock (`LOCKED`) is checked on every part it would write; if one refuses, nothing changes.
- Moving a line to another account with `reconciliation_id` in the same request settles every part (`null` unassigns them all; a draft on the new account puts them all in it). Without it, while the line is in a draft: `422 ASSIGNED_TO_RECONCILIATION` on `account_id`, as before.
- **A line's live parts are always in one reconciliation, or all in none.** The database refuses anything else. So:
  - `LOCKED` and `ASSIGNED_TO_RECONCILIATION` are the line's own refusals: the message never names another part. A refusal naming another part ("Another part of this bank line (<id>) is the cause: …") now comes only from a rule that can differ between parts: a sealed period, an opening balance, or a reconciliation on another account.
  - `POST /transactions/{id}/split` no longer declares or sends `SPLIT_RECONCILIATION_MIXED` (`0e71bf2787f9464e`). The reason stays defined, and its text says it is no longer sent.
- A reconciliation's `difference_cents`, `POST /reconciliations/{id}/complete` and `GET /transactions?reconciliation_id=` take in every part of each line it holds.
- A locked `title` that is `null` may be filled only while it is `null` on every part of the line.

### 7. Delete a line whole: `DELETE /bank-lines/{id}` (`5572fee599cd06e8`), additive

- Soft-deletes every live part of the line in one write, all or nothing, each exactly as `DELETE /transactions/{id}` deletes it, with its own `deleted` activity entry.
- Returns `200` with `{"parts": [...]}`: each part as `DELETE /transactions/{id}` returns its row (`deleted_at` set, `hashtag_ids` `[]`), in the order `GET /transactions?bank_line_id=` listed them by default.
- The line goes with its parts: its `operation_code` is free again on the account, and the account's balance drops the whole line at once.
- A line in a completed reconciliation is `409 CONFLICT` on `bank_line_id` (`IN_COMPLETED_RECONCILIATION`), judged on every part before anything changes; nothing is deleted.
- An id that names no live line of yours is `404`; a malformed id is `422` on `bank_line_id` (`INVALID_FORMAT`). Standard idempotency.
- A one-part line deletes exactly like `DELETE /transactions/{id}` on its transaction, except that the deleted row comes inside `parts`.
- `DELETE /transactions/{id}` is unchanged and still deletes one part.

### 8. The reconciliation list: `GET /bank-lines` and `GET /bank-lines/count` (`7ff6a09d863d6e44`), additive

- **One row per live bank line,** each exactly what `GET /bank-lines/{id}` returns, so a split purchase is one row holding every part. The ledger (`GET /transactions`) is unchanged and stays one row per part.
- **Order:** newest first, by the line's date, then its parts' `created_at`, then the line's `id`: a line sits where its parts sit in the ledger's default order. There is no `sort`.
- **Paging** as on `GET /transactions`: `{items, limit, next_cursor}`, `limit` `[1, 200]` default 50, `after=<next_cursor>`, `offset` refused. `limit` counts **lines**, and a page never cuts a line in two. A cursor is bound to the filters and to this list: a `GET /transactions` cursor sent here, or one from here sent to the ledger, is `422 INVALID_CURSOR` on `after` ("This cursor was issued by another list.").
- **Filters, each applying to a whole line:** `account_id`, `reconciliation_id`, `unreconciled=true` (with `reconciliation_id` it is `422` on `unreconciled`, `CONFLICTING_PARAMETERS`), and `date_from` / `date_to`, read exactly as on `GET /transactions` (a bare day in `display_timezone`, or an RFC 3339 instant). Any other parameter — `search`, `category_id`, `hashtag_id`, `bank_line_id`, `sort`, `debit_as_negative` — is `422` (`UNKNOWN_PARAMETER`). `422 SETTINGS_MISSING` before bootstrap, like the ledger.
- `GET /bank-lines/count` → `{"count": n}` for the same filters and the same refusals. A purchase split 60 + 40 counts 1 here and 2 on `GET /transactions/count`. The list's pages add up to it.

## How it was checked

Two runs against the practice engine, over the wire, each after the engine's full test suite passed. Every check is one of the asks' own **Done when**, or one the engine added. All passed.

**Run 1, 2026-10-17, practice engine on `890453f80a08cec9`** (suite: 1426 tests). The bank-line read was then still `transaction_ids`; run 2 checks it again in its final shape.

| Check | Result |
|---|---|
| A −100.00 charge split into −60.00 and −40.00: `?bank_line_id=` lists exactly the two parts; the line reads `net_cents` −10000, `part_count` 2 | pass |
| A transaction never split reads `part_count` 1 and its own signed amount (+25.50 → `2550`, −19.99 → `-1999`) | pass |
| Deleting the −60.00 part leaves the line at `part_count` 1, `net_cents` −4000, and the list showing only the other part | pass |
| `?bank_line_id=` with `account_id` and `date_from`, paged with `limit=1`: two pages, one part each; `/count` says 2; another account or a later day lists 0 and counts 0; a cursor reused with another filter is `422 INVALID_CURSOR` | pass |
| An import dry run with a ledger line the file does not claim: the entry has exactly `bank_line_id`, `net_cents` and `parts` (full transaction responses), and matched −50.00 plus unclaimed −25.00 equals the day's `ledger_net_cents` −75.00 | pass |
| An unclaimed split line is one entry with both parts (−60.00 and −40.00, `net_cents` −10000) | pass |
| Renaming `@Pendiente`, `@Opening` and the pending hashtag, case-only changes included (11 attempts): each `422` on `name`, `SYSTEM_NAME_FIXED`, and a re-read shows the same name and `version` | pass |
| Sending the current name (padded or not), or changing only colour or order: accepted | pass |
| Every system row carries `@Opening`, `@Pendiente` or `Pendiente` | pass |
| A second line with one operation code on one account: `409` on `operation_code`, `OPERATION_CODE_EXISTS`; the same code on another account is accepted | pass |

**Run 2, 2026-10-17, practice engine on `7ff6a09d863d6e44`** (suite: 1527 tests). Every example is a −100.00 charge split into −60.00 and −40.00.

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
| A write leaving a line's parts in two reconciliations is refused by the database, for the engine and for the database owner | pass |
| `POST /transactions/{id}/split` declares no `SPLIT_RECONCILIATION_MIXED`, and no route does | pass |
| `GET /bank-lines/{id}` equals that line's row in `GET /bank-lines` | pass |
| The ledger is unchanged: the split is two rows on `GET /transactions` and counts 2, against 1 row on `GET /bank-lines` | pass |

**One leftover:** the reason `OPERATION_CODE_EXISTS` is described as a code held by another bank line, but the human-readable `message` of that `409` still reads `"A transaction with operation code '<code>' already exists on this account."`. Rely on the reason and the key, as always; the message will be brought in line in a later reply.

**Where it runs:** the practice engine serves `7ff6a09d863d6e44`. The live engine serves it once the owner has applied the ledger update that installs the one-reconciliation-per-line rule; until then it serves `ce4e5cb642e53fdb`. Check `info.version`.

## What the TUI does

1. **Import screen (breaking):** stop reading `unclaimed_lines[].transaction_ids`. Draw each unclaimed line from `parts` (title, amount with `transaction_type`, category, description) and its `net_cents`, one entry per line. Make no per-transaction lookups to fill that screen.
2. **Import screen:** handle days reported with equal `file_net_cents` and `ledger_net_cents`; the reason is the unclaimed lines listed.
3. **Opening a purchase** (re-split, the line-field warning): read `GET /bank-lines/{id}` once. Its `parts` are the current parts and `net_cents` is the total a re-split must match. No search around the date, no second call, no client-side sum.
4. **Editing a part's title, date, account, operation code or reconciliation:** when `part_count` is above 1, the change reaches every part; warn as the TUI sees fit.
5. **Ledger:** unchanged, one row per part from `GET /transactions`. A part row can offer "delete purchase" through its `bank_line_id`.
6. **Reconciliation screen:** draw it from `GET /bank-lines` with `account_id`, the period's dates and `unreconciled=true` or `reconciliation_id`, and its count from `GET /bank-lines/count`. Ticking a purchase is one `PUT /transactions/{id}` with `reconciliation_id` on any one of its parts; unticking sends `null`. Re-read the other parts' `version` after it (breaking). Never build a screen explaining a refusal caused by another part for reconciliation.
7. **Deleting a purchase:** `DELETE /bank-lines/{id}`, behind a confirmation screen (the owner's rule). Handle `409 IN_COMPLETED_RECONCILIATION` on `bank_line_id`. `DELETE /transactions/{id}` still deletes one part.
8. Drop any handling of `SPLIT_RECONCILIATION_MIXED`.
9. **System rows (breaking):** offer no rename on a category or hashtag whose `system_key` is not `null`. Colour and order editing stay offered (order only, for the hashtag). If the edit form always sends `name`, send the row's current name unchanged; that is accepted. Drop any text that says these rows can be renamed. Handle `SYSTEM_NAME_FIXED` on `name` with its message.
10. Record `7ff6a09d863d6e44` as the last version read once every step above is in the TUI's plan.

## Done when

- The import screen renders unclaimed lines from `parts` and `net_cents`, with no read of `transaction_ids` and no per-transaction lookup; a day with equal totals but an unclaimed line shows that line.
- Opening a purchase is one `GET /bank-lines/{id}`; the TUI adds no amounts of its own.
- The reconciliation screen lists purchases from `GET /bank-lines`, ticks a purchase with one `PUT` on any part, and never shows half a purchase ticked.
- Deleting a purchase is one `DELETE /bank-lines/{id}` behind a confirmation, from the ledger or the reconciliation screen.
- No TUI screen offers a rename on `@Opening`, `@Pendiente` or the pending hashtag, and editing a system row's colour or order still works.
- `SYSTEM_NAME_FIXED` and `IN_COMPLETED_RECONCILIATION` on `bank_line_id` have handled paths; no code handles `SPLIT_RECONCILIATION_MIXED`.
