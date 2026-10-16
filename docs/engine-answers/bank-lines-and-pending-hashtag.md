# Bank lines and splits keep one identity across re-imports, and every transaction now carries at least one hashtag

Shipped 2026-10-16 · ⚠️ breaking · contract `42d70a629215928d` → `3129bfa2c43a4446` (last version covered: `3129bfa2c43a4446`)

This answers two TUI asks of 2026-10-15: "split bank lines keep one identity" and "a pending hashtag, as `@Pendiente` is for categories". It covers every contract change from `42d70a629215928d` (exclusive) to `3129bfa2c43a4446` (inclusive) and replaces the earlier split-bank-lines answer, which stopped at `66d65a86a9cf1c19`. Both the live engine and the practice engine serve `3129bfa2c43a4446`. Check `info.version` in `GET /openapi.json` before relying on it; its `x-changelog` has one entry per version in this range.

## What changed

### Part 1 — Bank lines

**`bank_line_id` on every transaction** (`d09030c7f3719106`)
- Every transaction belongs to exactly one bank line, the engine's record of one bank movement. Every transaction response carries `bank_line_id`. It is minted by the engine and is never `null`. The routes are `GET /transactions`, `GET /transactions/{id}`, `POST /transactions`, `PUT /transactions/{id}`, `DELETE /transactions/{id}`, `POST /transactions/batch` and `POST /accounts/{id}/opening-balance`. Activity-log entries for transactions written from now on carry it too.
- Every transaction that existed before has a line of its own.
- A line stores no figures of its own. Its account, day, direction and total are always those of its live transactions, its *parts*, so editing a part changes them (`1a064b29a1a77b01`).
- `operation_code` lives on the line, so every part shows the same code. Requests and responses carry it exactly as before: same field, same trimming, same `409 OPERATION_CODE_EXISTS`, same reconciliation lock, same import backfill.
- The code is unique per account among live **lines**, not transactions (`b2b60cf39d8f51c9`). The parts of one line share its code. A line releases its code only when its last live part is deleted.
- A bank line has no activity entries of its own. The entries of its transactions carry `bank_line_id` and `operation_code`.

**Splitting: `POST /transactions/{id}/split`** (`a55cc4c271a45287`)
- **Body:** `{"parts": [...]}`, 2 to 500 parts. Each part is `{"id": <new UUID>, "amount_cents": <signed, non-zero>, "category_id": <optional>, "hashtag_ids": [...], "description": <optional>}`.
- `title`, `date`, `account_id` and `operation_code` are not accepted (`422`). Parts take the line's account, date and code, and the title of the transaction named by `{id}`.
- `{id}` is any live part of the line. The parts are the line's **complete new set**: every live part is deleted and the new parts are created on the same `bank_line_id`. The same call splits a single transaction, splits one part again, or re-splits 60 + 40 into 70 + 30.
- **Total:** the parts' signed sum must equal the line's current total, the signed sum of its live parts. Mixed directions are allowed: 120 out + 20 in = 100 out.
- **Where it's allowed:** inside a completed reconciliation, inside a sealed period and on an archived account. Every part joins the line's reconciliation.
- **Hashtags:** a part with `hashtag_ids` omitted or `[]` lands on the pending hashtag (Part 2).
- **Response:** `201` with `{"parts": [...]}`, the new transactions in request order.
- **New reasons:**
  - `SPLIT_TOTAL_MISMATCH`: the sum is wrong. Keyed on `parts` and on each `parts.<i>.amount_cents`; the message gives both totals in cents.
  - `SPLIT_RECONCILIATION_MIXED`: the line's parts are in different reconciliations. Keyed on `transaction_id`.
  - `SPLIT_LINE_PARTS_DIVERGE`: the line's parts are on different accounts or dates. Keyed on `transaction_id`. Fix it by sending the account and date on one part with `PUT`.
  - `OPENING_BALANCE_NOT_SPLIT`: an opening balance cannot be split. Keyed on `transaction_id`.
- **Other refusals:**
  - A deleted or unknown `{id}` is `404`.
  - A part's own field errors are `422` keyed `parts.<i>.<field>`: `ZERO_AMOUNT`, `INVALID_REFERENCE`, `RESERVED_CATEGORY`, `DUPLICATE_IN_REQUEST`, and `PENDING_HASHTAG_NOT_ALONE` (Part 2).
  - A part `id` already taken is `409` on `parts.<i>.id` (`ID_EXISTS`).
  - Fewer than 2 or more than 500 parts is `422` on `parts` (`OUT_OF_RANGE`).
  - As on the other create routes, `409` with `RESERVED_NAME_HELD` or `CONCURRENT_CHANGE` when the engine has to create `@Pendiente` (keyed `category_id`) or the pending hashtag (keyed `hashtag_ids`).

**Editing a part: `PUT /transactions/{id}`** (`5c5ae48b4583046f`)
- Sending `title`, `date`, `account_id` or `operation_code` writes the value onto **every live part** of the line, in one write.
  - Each other part that changes gets its own `updated` activity entry and a `version` bump.
  - A part that already has the value is untouched.
  - The response is still the transaction named by `{id}`.
- *Field locking*, *Opening balances stay put*, *Reconciliation assignment* and *Sealed periods* are checked on every part the request would change. If any part refuses, nothing is written. The refusal keeps the key you sent and the usual reason (`LOCKED`, `ASSIGNED_TO_RECONCILIATION`, `SEALED_PERIOD`, `OPENING_BALANCE_ACCOUNT_FIXED`), and its message names the part that caused it.
- `amount_cents`, `category_id`, `description`, `hashtag_ids` and `reconciliation_id` change only `{id}`.
- `reconciliation_id` settles `{id}` alone. So moving a line's account while another part is in a draft reconciliation is `422 ASSIGNED_TO_RECONCILIATION` on `account_id` until that part is unassigned. While that part is in a completed reconciliation, it is `LOCKED`.
- Deleting a part works as before. Deleting the last part of a line frees the line and its code.

**Grouped batch: `line_group` on `POST /transactions/batch` items** (`66d65a86a9cf1c19`)
- An optional string: trimmed, not blank (`EMPTY`), at most 64 characters (`OUT_OF_RANGE`). It is scoped to the request, and never stored or returned.
- Items naming the same `line_group` become the parts of one new bank line. Items without one each get their own line, as before.
- The items of a group must have the same `account_id`, `date` (the same instant, not only the same day), `title` and `operation_code`. Otherwise every item of the group is `422` on each field that differs, keyed `transactions.<i>.<field>`, with reason `LINE_GROUP_FIELDS_DIFFER`, and nothing is written.
- Items of one group may share an `operation_code`. Two different lines with one code on one account are still `DUPLICATE_IN_REQUEST`. A code already on the account is the `409 OPERATION_CODE_EXISTS`, keyed by the group's first item.

**Bank import: `POST /transactions/import`** (`086a35cfb55a35e2`, `5c5ae48b4583046f`)
- **Matching:**
  - It compares the file's rows with **bank lines**, not transactions.
  - A line matches a row by `operation_code` first. Otherwise it matches by the same account, the **exact** same calendar day, the same direction and the same total.
  - **Titles play no part in matching.**
  - `same_day` never claims a line carrying a different code. A line whose parts are on different accounts or days matches by code only.
  - So split lines, grouped lines and edited titles are all recognised on re-import.
- **Removed:** the `adjacent_day` rule and its `rule` value. A row one day off is `new`. `rule` is now `operation_code` or `same_day`.
- **On a match:**
  - The apply writes **the bank's title onto every part** of the line whose title differs.
  - A part whose description is empty gets its old title as its description; otherwise the old title is dropped.
  - A row without a title writes none.
  - This, and the code backfill, also reach lines inside a completed reconciliation. Each changed part gets one `updated` activity entry.
- **Row results:**
  - `ledger_id` is removed. A `matched` row carries `bank_line_id`, the line it matched.
  - New `retitled`: `true` or `false` on a `matched` row, `null` otherwise.
  - `backfill_code` is the code written onto the line.
- **Counts:** `counts` gains `retitled`.
- **`excess` is removed and replaced by `day_mismatches`.**
  - For each account in the file, every day from its first to its last file date is checked, inclusive, days without file rows included. A day where the file's signed total differs from the ledger's **after this import** is reported. Days that agree are not listed. It is a report only.
  - Each entry is `{account_id, date, file_net_cents, ledger_net_cents, unmatched_rows: [<file row index>], unclaimed_lines: [{bank_line_id, transaction_ids}]}`.
  - Both totals are signed: inflow positive, outflow negative.
- **Concurrent changes:** the apply re-checks every match while holding the matched lines. If another request split, deleted or changed a matched line while the import ran, the apply is `409 CONFLICT` keyed `rows.<index>` (`CONCURRENT_CHANGE`) and writes nothing. Send it again.
- **Hashtags:** every row the import creates lands on the pending hashtag (Part 2). Import rows carry no hashtags.

### Part 2 — The built-in pending hashtag

**The hashtag itself** (`d42b8bb6bf2db3d9`)
- Every hashtag response carries `system_key`: `"pending"` on the built-in one, `null` on every other. It is never omitted. This covers `GET /hashtags`, `GET /hashtags/{id}`, and the `POST`, `PUT` and `DELETE` responses.
- `GET /hashtags` lists it like any other hashtag. **Find it by `system_key`, never by its name.**
- Its default name is `Pendiente`. It can be renamed with `PUT /hashtags/{id}`, and can take its default name back.
- It is created the first time the engine needs it, so a user may not have one yet.
- It does not count toward the hashtag cap.
- `DELETE /hashtags/{id}` on it is `403 FORBIDDEN` on `hashtag_id` with reason `SYSTEM_HASHTAG`, and nothing is written.
- No other hashtag may take the name `Pendiente`, compared after trimming and ignoring case. `POST /hashtags` and `PUT /hashtags/{id}` refuse it with `422` on `name`, reason `RESERVED_NAME`.

**A transaction with no hashtag lands on it** (`83b6028df1b5b3a1`, `f572e39676480e0e`, `77162c89a5c8ca68`)
- These come back with `hashtag_ids: ["<pending_id>"]` when they name no hashtag (`hashtag_ids` omitted or `[]`):
  - `POST /transactions`
  - every item of `POST /transactions/batch`, `line_group` parts included
  - every row `POST /transactions/import` creates
  - every part of `POST /transactions/{id}/split`
- **`PUT /transactions/{id}`:**
  - `hashtag_ids: []` puts the transaction on `["<pending_id>"]`.
  - Omitting `hashtag_ids` leaves the set as it is.
  - Sending `["<real_id>"]` replaces the pending hashtag. There is no separate "remove pending" step.
  - Sending `hashtag_ids` always bumps `version`, even when the set does not change.
- **`DELETE /hashtags/{id}` on an ordinary hashtag:**
  - Every live transaction whose only hashtag it was ends on `["<pending_id>"]`, in the same write.
  - Transactions with other hashtags just lose it, as before.
  - Each affected transaction's `version` and `updated_at` bump, with no activity entry per transaction.
  - It can now return `409` on `hashtag_id` (`RESERVED_NAME_HELD`, `CONCURRENT_CHANGE`) when the pending hashtag has to be created.
- **Existing transactions:** every one that had no hashtag was moved onto the pending hashtag in one go, and every opening balance lost its hashtags. Each changed transaction's `version` bumped, with no activity entry per transaction.
- **The rule:** `hashtag_ids` is never `[]` on a live transaction **except an opening balance**, which always carries none. A deleted transaction still returns `hashtag_ids: []`.

**Opening balances carry no hashtag** (`83b6028df1b5b3a1`)
- `POST /accounts/{id}/opening-balance` creates the opening balance with `hashtag_ids: []`.
- `PUT /transactions/{id}` giving an opening balance any hashtag, the pending one included, is `422` on `hashtag_ids` with reason `OPENING_BALANCE_NOT_TAGGED`. `hashtag_ids: []` on it is accepted.

**New refusals.** Nothing is written, and a batch writes none of its items.

| When | Status | Field | Reason |
|---|---|---|---|
| A hashtag set names the pending hashtag together with any other hashtag | `422` | `hashtag_ids` (batch: `transactions.<i>.hashtag_ids`; split: `parts.<i>.hashtag_ids`) | `PENDING_HASHTAG_NOT_ALONE` |
| `PUT /transactions/{id}` gives an opening balance any hashtag | `422` | `hashtag_ids` | `OPENING_BALANCE_NOT_TAGGED` |
| `DELETE /hashtags/{id}` on the pending hashtag | `403` | `hashtag_id` | `SYSTEM_HASHTAG` |
| A user hashtag created or renamed to `Pendiente` | `422` | `name` | `RESERVED_NAME` |
| The engine must create the pending hashtag, but an ordinary hashtag already holds the name `Pendiente` | `409` | `hashtag_ids` on every transaction route, batch, import and split included; `hashtag_id` on `DELETE /hashtags/{id}` | `RESERVED_NAME_HELD`: rename that hashtag, then retry |
| The pending hashtag was being created while another request changed it | `409` | as above | `CONCURRENT_CHANGE`: retry |
| A write names a hashtag that another request deletes at the same moment | `422` | `hashtag_ids` | `INVALID_REFERENCE` |

**Reports and filters** (`ac063c162217f23e`)
- In `GET /reports/monthly` and `GET /dashboard`, `hashtag_breakdown` no longer has a `hashtag_ids: []` row. Transactions still waiting for a hashtag group under `["<pending_id>"]`, with figures like any other combination. Opening balances are excluded from these reports, as before.
- `GET /categories/{id}/hashtags` counts the pending hashtag like any other. Its rows stay `{id, name, uses}`. Recognise the pending row by matching its `id` against the hashtag whose `system_key` is `"pending"`.
- `GET /transactions?hashtag_id=<pending_id>` lists exactly the transactions still waiting for a hashtag, and `GET /transactions/count?hashtag_id=<pending_id>` counts them. An opening balance never matches.

## What the TUI does

**Bank lines and splits**
1. Read `bank_line_id` on transactions. Show parts that share it as one bank movement, for example grouped under the line's title and total.
2. Offer a split action that sends the full new set of parts to `POST /transactions/{id}/split`. Show `SPLIT_TOTAL_MISMATCH` with both totals from its message. Re-splitting uses the same call, with the line's current parts preloaded.
3. When editing title, date, account or code on a part, tell the owner the change applies to every part of the line. Show a refusal's message as sent, since it names the part that caused it.
4. In the spreadsheet upload, send rows that are the parts of one bank charge with a shared `line_group`. Show `LINE_GROUP_FIELDS_DIFFER` per row.
5. In the import screen:
   - replace `ledger_id` with `bank_line_id`;
   - drop `adjacent_day`;
   - show `retitled` and `counts.retitled`;
   - replace the `excess` view with `day_mismatches`, listing each disagreeing day with both totals, the unmatched file rows and the unclaimed ledger lines;
   - on `409 CONCURRENT_CHANGE`, offer to run it again.
6. Remove any client-side matching, title comparison or neighbouring-day logic the TUI keeps for imports or splits. The engine decides.

**Pending hashtag**

7. Read `system_key` from `GET /hashtags`. Find the pending hashtag by `system_key == "pending"`, never by name, and allow for it not existing yet.
8. Stop computing "untagged" on the client. The transactions still needing a hashtag are `GET /transactions?hashtag_id=<pending_id>`, and their count is `GET /transactions/count?hashtag_id=<pending_id>`.
9. Remove any handling of a `hashtag_ids: []` row in the monthly report and dashboard. Show the pending row like any other, using the hashtag's current name.
10. When the owner tags a pending transaction or split part, send only the real hashtags. Never send the pending id together with another id.
11. Don't offer hashtag editing on an opening balance, and handle `OPENING_BALANCE_NOT_TAGGED` if it comes back.
12. Don't offer delete on the pending hashtag. Handle `SYSTEM_HASHTAG` on delete, and `RESERVED_NAME` on hashtag create and rename.
13. After deleting a hashtag, re-read the affected transactions. Those that had only that hashtag now show the pending one.
14. Show `RESERVED_NAME_HELD`, `CONCURRENT_CHANGE` and `INVALID_REFERENCE` on `hashtag_ids` (or `hashtag_id`) with their messages.

## Done when

- The TUI reads `info.version` `3129bfa2c43a4446` from the practice engine and every step above works against it.
- **Splits:** the TUI splits a transaction, re-splits a line and edits a part through the routes above.
- **Imports:**
  - A statement imported, split, and imported again shows every row as `matched` and nothing `new`, including a card line with no operation code.
  - A grouped spreadsheet upload creates one line, and a later import of the bank's row matches it.
  - The import screen reads `bank_line_id`, `retitled` and `day_mismatches`, and no longer reads `ledger_id`, `excess` or `adjacent_day`.
- **Pending hashtag:**
  - The TUI finds the pending hashtag by `system_key`.
  - It lists "needs a hashtag" through `?hashtag_id=` and shows the same count as `/transactions/count`.
  - A transaction created with no hashtag shows the pending one. Tagging it with a real hashtag leaves only the real one.
  - No client code computes or displays an empty hashtag row in reports.
- Each new reason in this document (`SPLIT_TOTAL_MISMATCH`, `SPLIT_RECONCILIATION_MIXED`, `SPLIT_LINE_PARTS_DIVERGE`, `OPENING_BALANCE_NOT_SPLIT`, `LINE_GROUP_FIELDS_DIFFER`, `PENDING_HASHTAG_NOT_ALONE`, `OPENING_BALANCE_NOT_TAGGED`, `SYSTEM_HASHTAG`) has a handled path.
