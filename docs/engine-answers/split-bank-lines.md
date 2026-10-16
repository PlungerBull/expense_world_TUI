# A bank line split into several transactions keeps one identity, so a re-import recognises it

Shipped 2026-10-16 · ⚠️ breaking · contract `42d70a629215928d` → `66d65a86a9cf1c19`

This answers the TUI's ask "split bank lines keep one identity" (2026-10-15). The live engine serves this contract once the owner has applied its database change and restarted it; until then `/openapi.json` still shows the earlier version. Check `info.version` before relying on it.

## What changed

**Bank lines.** Every transaction belongs to exactly one bank line, the engine's record of one bank movement. Every transaction response carries `bank_line_id` (never `null`, minted by the engine) on `GET /transactions`, `GET /transactions/{id}`, `POST /transactions`, `PUT /transactions/{id}`, `DELETE /transactions/{id}`, `POST /transactions/batch` and `POST /accounts/{id}/opening-balance`, and in transaction entries of the activity log written from now on. A line stores no figures of its own: its account, day, direction and total are always those of its live transactions (its *parts*). `operation_code` lives on the line, so every part shows the same code. Requests and responses carry it exactly as before.

**Splitting: `POST /transactions/{id}/split`.**
- Body: `{"parts": [...]}`, 2 to 500 parts, each `{"id": <new UUID>, "amount_cents": <signed, non-zero>, "category_id": <optional>, "hashtag_ids": [...], "description": <optional>}`. `title`, `date`, `account_id` and `operation_code` are not accepted (`422`): parts take the line's account, date and code, and the title of the transaction named by `{id}`.
- `{id}` is any live part of the line. The parts are the line's **complete new set**: every live part is deleted and the new parts are created on the same `bank_line_id`. The same call splits a single transaction, splits one part again, or re-splits 60 + 40 into 70 + 30.
- The parts' signed sum must equal the line's current total (the signed sum of its live parts). Mixed directions are allowed (120 out + 20 in = 100 out).
- Allowed inside a completed reconciliation, inside a sealed period and on an archived account. Every part joins the line's reconciliation.
- Returns `201` with `{"parts": [...]}`, the new transactions in request order.
- New reasons:
  - `SPLIT_TOTAL_MISMATCH`: the sum is wrong. Keyed on `parts` and on each `parts.<i>.amount_cents`; the message gives both totals in cents.
  - `SPLIT_RECONCILIATION_MIXED`: the line's parts are in different reconciliations. Keyed on `transaction_id`.
  - `SPLIT_LINE_PARTS_DIVERGE`: the line's parts are on different accounts or dates. Keyed on `transaction_id`; fix it by sending the account and date on one part with `PUT`.
  - `OPENING_BALANCE_NOT_SPLIT`: the opening balance cannot be split. Keyed on `transaction_id`.
- A deleted or unknown `{id}` is `404`.
- Each part's other refusals are `422` keyed `parts.<i>.<field>` (`ZERO_AMOUNT`, `INVALID_REFERENCE`, `RESERVED_CATEGORY`, `DUPLICATE_IN_REQUEST`). A part `id` already taken is `409` on `parts.<i>.id` (`ID_EXISTS`). Fewer than 2 or more than 500 parts is `422` on `parts` (`OUT_OF_RANGE`).

**Editing a part.**
- `PUT /transactions/{id}` sending `title`, `date`, `account_id` or `operation_code` writes the value onto **every live part** of the line, in one write. Each part that changes gets its own `updated` activity entry. The response is still the transaction named by `{id}`.
- If any part refuses, nothing is written. The refusal keeps the key you sent and the usual reason (`LOCKED`, `SEALED_PERIOD`, `ASSIGNED_TO_RECONCILIATION`, `OPENING_BALANCE_ACCOUNT_FIXED`), and its message names the part that caused it.
- `amount_cents`, `category_id`, `hashtag_ids`, `description` and `reconciliation_id` change only `{id}`.
- Because `reconciliation_id` settles `{id}` alone, moving a line's account while another part is in a draft reconciliation is `422` `ASSIGNED_TO_RECONCILIATION` on `account_id` until that part is unassigned, and `LOCKED` while it is in a completed one.
- Deleting a part works as before. Deleting the last part of a line frees the line and its code.

**Grouped batch: `line_group` on `POST /transactions/batch` items.**
- Optional string, trimmed, not blank (`EMPTY`), at most 64 characters (`OUT_OF_RANGE`). It is scoped to the request, and never stored or returned.
- Items naming the same `line_group` become the parts of one new bank line. Items without one each get their own line, as before.
- The items of a group must have the same `account_id`, `date` (the same instant, not only the same day), `title` and `operation_code`. Otherwise every item of the group is `422` on each field that differs, reason `LINE_GROUP_FIELDS_DIFFER`, keyed `transactions.<i>.<field>`, and nothing is written.
- Items of one group may share an `operation_code`. Two different lines with one code on one account are still `DUPLICATE_IN_REQUEST`.

**Bank import: `POST /transactions/import`.**
- It compares the file's rows with **bank lines**, not transactions. A line matches a row by `operation_code` first; otherwise by the same account, the **exact** same calendar day, direction and total. **Titles play no part in matching.** `same_day` never claims a line carrying a different code, and a line whose parts are on different accounts or days matches by code only. So a split line, a grouped line and an edited title are all recognised on re-import.
- Removed: the `adjacent_day` rule and its `rule` value. A row one day off is `new`. `rule` is now `operation_code` or `same_day`.
- On a match, the apply writes **the bank's title onto every part** of the line whose title differs. A part whose description is empty gets its old title as its description; otherwise the old title is dropped. A row without a title writes none. This, and the code backfill, also reach lines inside a completed reconciliation.
- Row results:
  - `ledger_id` is removed. A `matched` row carries `bank_line_id`, the line it matched.
  - New `retitled`: `true` or `false` on a `matched` row, `null` otherwise.
  - `backfill_code` is the code written onto the line.
- `counts` gains `retitled`.
- `excess` is removed and replaced by `day_mismatches`. For each account in the file, every day from its first to its last file date (inclusive, days without file rows included) where the file's signed total differs from the ledger's **after this import** is reported. Each entry is `{account_id, date, file_net_cents, ledger_net_cents, unmatched_rows: [<file row index>], unclaimed_lines: [{bank_line_id, transaction_ids}]}`. Both totals are signed: inflow positive, outflow negative. Days that agree are not listed. It is a report only.
- The apply is `409 CONFLICT` keyed `rows.<index>` (`CONCURRENT_CHANGE`), writing nothing, when another request split, deleted or changed a matched line while the import ran. Send it again.

## What the TUI does

1. Read `bank_line_id` on transactions. Show parts that share it as one bank movement, for example grouped under the line's title and total.
2. Offer a split action that sends the full new set of parts to `POST /transactions/{id}/split`, and show `SPLIT_TOTAL_MISMATCH` with both totals from its message. Re-splitting uses the same call with the line's current parts preloaded.
3. When editing title, date, account or code on a part, tell the owner it applies to every part of the line. Show a refusal's message as sent, since it names the part that caused it.
4. In the spreadsheet upload, send rows that are the parts of one bank charge with a shared `line_group`, and show `LINE_GROUP_FIELDS_DIFFER` per row.
5. In the import screen:
   - replace `ledger_id` with `bank_line_id`;
   - drop `adjacent_day`;
   - show `retitled` and `counts.retitled`;
   - replace the `excess` view with `day_mismatches`, listing each disagreeing day with both totals, the unmatched file rows and the unclaimed ledger lines;
   - on `409 CONCURRENT_CHANGE`, offer to run it again.
6. Remove any client-side matching, title comparison or neighbouring-day logic the TUI keeps for imports or splits; the engine decides.

## Done when

- The TUI splits a transaction, re-splits a line and edits a part through the routes above, against the live contract `66d65a86a9cf1c19` or later.
- A statement imported, split, and imported again shows every row as `matched` and nothing `new`, including a card line with no operation code.
- A grouped spreadsheet upload creates one line, and a later import of the bank's row matches it.
- The import screen reads `bank_line_id`, `retitled` and `day_mismatches`, and no longer reads `ledger_id`, `excess` or `adjacent_day`.
