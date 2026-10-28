# An account moves between holders, a holder is made and unmade with its accounts, and a holder's bank lines list in one read

Shipped 2026-10-28 · ⚠️ breaking · contract `3e472b3256dcdc69` → `256f3190cf24fc36` (seven versions: `3e472b3256dcdc69`, `b2c5af41336bae5f`, `7ec7a4bcf9e5a3fd`, `1cdd1d94e43321ee`, `903200521b7c116a`, `3e3bd0b766c709fc`, `256f3190cf24fc36`)

Answers, all raised 2026-10-27 (they say card; the engine says holder):
- "Yes to moving an account to another card, with the limits you proposed; no to the sheet import refusing a name used in two currencies"
- "Delete a card with its last account, so no client leaves an empty card behind"
- "Create a bank account and its own card in one write"
- "List a card's bank lines in no statement in one read"
- "Say what a client does with a flagged line on a card with a statement code"

## Each ask

- **The move:** done as asked. `POST /accounts/{id}/move` (section 1). Pairing is a move onto the other currency's holder; unpairing is `POST /holders` and a move onto the new holder. An account that has ever been in a statement, a deleted one included, stays on its holder.
- **The sheet-import check:** declined by the owner. `POST /transactions/import-sheet` neither refuses nor warns about a name used in both currencies whose two accounts sit on different holders; the owner pairs them with the move after the import.
- **Deleted with its last account:** done as asked (section 3).
- **Created in one write:** done differently. You asked for `POST /accounts` with a `card` object; the owner chose `POST /holders` with an `accounts` list (section 4), so the Visa's soles and dollar accounts are one write too, and the holder stays the thing that is archived and stated whole. `POST /accounts` is unchanged: `holder_id` stays required. The `make-account` half is answered by the coming person-holders change (conversion moves onto the holder), so it is not changed here.
- **The holder's bank lines:** done as asked, as `?holder_id=` (section 5). With `account_id`, both apply. One difference from your text: you wrote that an unknown id is refused as an unknown `account_id` is refused, but an unknown `account_id` is not refused on these routes; it matches nothing. So an unknown `holder_id` lists nothing and counts `0`, exactly as an unknown `account_id` does.
- **The flagged line:** done differently (section 6). Your suggested path (fix the line, revert, upload again) leaves a duplicate: on a holder with a statement code, the upload already created the paper's row as a second line, the flagged line's twin. The advice now names the twin and the two ways to keep one.
- **No ask:** `DELETE /accounts/{id}` is refused while a live statement holds a balance for the account (section 7). Without it, deleting a holder's last account could leave a statement on a deleted holder.

## What changed

### 1. `POST /accounts/{id}/move` (`3e472b3256dcdc69`) ➕

- **Body:** `{"holder_id": "<uuid>"}`, required. Any other field is `422` (`UNKNOWN_FIELD`); no body or `{}` is `422` on `holder_id` (`REQUIRED`). Takes `X-Idempotency-Key` like every write.
- **Answer:** `200` with the account. Only `holder_id` changes and `version` bumps; the id, name, currency, colour, `sort_order`, transactions, opening balance and balance stay.
- **The holder it leaves empty is deleted** in the same write, with its own `DELETED` entry under `resource_type = "holder"`, releasing its name and statement code. `GET /holders/{id}` on it is then `404`.
- **Activity:** one `UPDATED` entry for the account, its snapshots showing `holder_id` before and after.
- **Refusals,** the first that applies answers, nothing written:

  | # | When | Status | Key | Reason |
  |---|---|---|---|---|
  | 1 | the account is archived | `409` | `account_id` | `ACCOUNT_ARCHIVED` |
  | 2 | the account is a person | `409` | `account_id` | `PERSON_NOT_MOVED` (new) |
  | 3 | the account has ever been in a statement, a deleted one included | `409` | `account_id` | `STATEMENT_KEEPS_ACCOUNT` (new) |
  | 4 | `holder_id` is the account's own holder | `409` | `holder_id` | `HOLDER_UNCHANGED` (new) |
  | 5 | the target is not a live holder of yours, or is archived | `422` | `holder_id` | `INVALID_REFERENCE` |
  | 6 | the target holds a live account in that currency | `409` | `holder_id` | `HOLDER_CURRENCY_TAKEN` |
  | 7 | the target has a live statement | `409` | `holder_id` | `HOLDER_HAS_STATEMENT` |

  An unknown, deleted or another user's account is `404`.
- **Example, pairing:** holder `A` holds the soles account `S`, holder `B` the dollar account `D`.
  - `POST /accounts/D/move` `{"holder_id": "A"}` → `200`, `D` with `holder_id` `A`.
  - `GET /holders/A` → `account_ids` `["S", "D"]`; `GET /holders/B` → `404`.
- **Example, unpairing:** `POST /holders` `{"id": "C", "name": "Visa dólares"}`, then `POST /accounts/D/move` `{"holder_id": "C"}` → `200`; `A` holds only `S`.
- **At the same moment** as a `POST /statements` naming either holder, a `POST /accounts` or another move onto the target, an archive of either holder, or a `DELETE /accounts/{id}` of the account, a move is judged wholly before or wholly after it: of two that conflict, one succeeds and the other is refused with its usual reason, never both (`b2c5af41336bae5f` states each outcome).
- The rule "an account never moves between holders" is gone; *Holders* says *An account in no statement moves between holders*.

### 2. A delete that waited logs the account as it found it (`b2c5af41336bae5f`)

`DELETE /accounts/{id}` sent while a move or a conversion holds the account now judges and logs the account as that write left it: its `DELETED` entry's `before` snapshot shows the account as it then stands (on its new holder, for example). Before, that snapshot could show it as it was before the other write. No status, reason or field changes.

### 3. ⚠️ `DELETE /accounts/{id}` deletes the holder it leaves empty (`7ec7a4bcf9e5a3fd`)

- Deleting the last live account of a holder (an archived account counts as live) deletes the holder in the same write: its own `DELETED` entry under `resource_type = "holder"`, its name and statement code released, gone from `GET /holders`, `404` on `GET /holders/{id}`.
- A holder still holding another live account is untouched; its `account_ids` names the others.
- A person's delete and the delete's refusals are unchanged; a refused delete deletes no holder.
- **Example.** Holder "Savings" holds one soles account; `DELETE /accounts/<it>` answers `200` as before.
  - Before: "Savings" stayed, `account_ids` `[]`, until a `DELETE /holders/{id}`.
  - After: "Savings" is deleted with it. A client holding its id gets `404` on the next read of it, and a `DELETE /holders/{id}` sent after the account's delete now answers `404`: drop that second call.

### 4. `POST /holders` takes `accounts` (`1cdd1d94e43321ee`) ➕

- **`accounts`**, optional: the accounts created on the holder in the same write, at most 10 (more is `422 OUT_OF_RANGE` on `accounts`). Omitted or `[]`, the holder is created empty, as before.
- **Each item** is the `POST /accounts` body without `holder_id`: `id`, `name`, `currency_code`, optional `color` and `sort_order`. `holder_id` or any other unknown field in an item is `422` (`UNKNOWN_FIELD`). Each is judged and created exactly as `POST /accounts` judges and creates an account on that holder.
- **All or nothing:** a refused account leaves no holder, a refused holder leaves no account.
- **Keys:** a refusal of an item is keyed `accounts.<i>.<field>`, for example `accounts.0.name` `NAME_EXISTS`, `accounts.1.id` `ID_EXISTS`.
  - Two items in one currency: `409 HOLDER_CURRENCY_TAKEN` on the later item's `accounts.<i>.currency_code`.
  - Two items with one `id`: `422 DUPLICATE_IN_REQUEST` on the later item's `accounts.<i>.id`.
  - The account cap counts every item: `LIMIT_REACHED` (`CAP_REACHED`) on `accounts.<i>.id` of each item past it.
- **Order:** six steps, each answer naming every refusal of its step, the holder's and every item's:
  1. what the request alone shows, `422` (the request's shape, a missing, unknown or malformed field anywhere in it, is answered alone, before the blank names, colours and repeated ids of this step);
  2. taken ids, `409 ID_EXISTS`;
  3. the holder and account caps, `LIMIT_REACHED`;
  4. an unsupported item currency, `422 UNSUPPORTED_VALUE`;
  5. taken names and an earlier item's currency, `409`;
  6. a taken `statement_code`, `409 STATEMENT_CODE_EXISTS`, alone.
- **Answer:** `201` with the holder, `account_ids` naming the new accounts. Activity: the holder's `CREATED` entry and one `CREATED` entry per account. Idempotency covers the whole write.
- **Example:**
  ```json
  {"id": "H", "name": "Visa Oro", "statement_code": "SIG",
   "accounts": [{"id": "S", "name": "Visa Oro", "currency_code": "PEN"},
                {"id": "D", "name": "Visa Oro", "currency_code": "USD"}]}
  ```
  answers `201` with `account_ids` `["S", "D"]`.
- **One message changed:** `POST /holders` with a blank `name` answers the top-level message `"Holder validation failed."`; before, `"Name must not be empty."`. The status (`422`), the reason (`EMPTY`) and the field message (`"Must not be empty."`) are unchanged.

### 5. `?holder_id=` on `GET /bank-lines` and `GET /bank-lines/count` (`903200521b7c116a`) ➕

- The lines on any live account of that holder, an archived account included, every currency together.
- It combines as every filter does: a line is listed when it matches every filter sent. With `account_id` both apply, so an account on the holder narrows the list to that account, and an account on another holder lists nothing.
- It takes every `sort` (`sort=statement` still needs `statement_id`) and pages by cursor; its cursors are bound to it.
- An id naming no live holder of yours (unknown, deleted, another user's) lists nothing and counts `0`, as an unknown `account_id` does. An id that is not a UUID is `422 INVALID_FORMAT` on `holder_id`.
- With `unassigned_in_period_of` it is `422 CONFLICTING_PARAMETERS` on `unassigned_in_period_of`, like the other filters.
- **Example:** `GET /bank-lines?holder_id=<id>&unreconciled=true&sort=date_asc` lists a two-currency holder's lines in no statement, soles and dollars together, oldest first; `GET /bank-lines/count?holder_id=<id>&unreconciled=true` counts them.

### 6. What a client does with a flagged line (`3e3bd0b766c709fc`)

Wording only: no status, reason, field or message changed. `POST /statements/{id}/complete` → *What a client does with a flagged line* now gives a path per kind of holder:

- **A holder with no statement code:** as before. It belongs to this statement: revert, assign it, complete again. It belongs to a later statement: leave it in no statement and assign it to that statement's draft. It is a mistake: move it (`PUT /bank-lines/{id}`) or delete it (`DELETE /bank-lines/{id}`).
- **A holder with a statement code, and the bank's paper prints the line:** the line has a twin, the line `POST /statements/import` created from the paper's row. Where the two differ only by a day, that row's `near_misses` names the flagged line. The owner keeps one:
  - **Keep the paper's:** `DELETE /bank-lines/{flagged line}`. The statement stays completed.
  - **Keep their own** (its category, hashtags and text):
    1. `POST /statements/{id}/revert`;
    2. `DELETE /bank-lines/{twin}`, its id the row's `bank_line_id`;
    3. `PUT /bank-lines/{flagged line}` with `date` a moment of the row's day in the user's `display_timezone`, such as 00:00 of that day (for a user in `America/Lima` and a row dated `2025-03-03`: `"2025-03-03T00:00:00-05:00"`; `"2025-03-03T00:00:00Z"` lands on 2 March and stays a near miss), and through `parts` the row's total where it differs;
    4. `POST /statements/import` with the same paper. It matches the fixed line, gives it the row's place and completes the statement, with no twin left.

    Skipping step 2 leaves two lines for one row: the upload keeps the older of the two and the close flags the other.
  - Assigning the flagged line by hand does not settle it: the line holds no place, so the complete is refused `STATEMENT_NOT_ORDERED` until the paper is uploaded again.
- **A holder with a statement code, and the paper does not print the line:** as on a holder with no code, it belongs to a later statement or is a mistake.

`POST /statements/import`'s *No neighbouring day* and its `near_misses` field point to this advice.

### 7. ⚠️ `DELETE /accounts/{id}` is refused while a live statement holds the account (`256f3190cf24fc36`)

- A live statement (a draft or a completed one) holding a balance for the account refuses the delete: `409` on `account_id`, new reason `IN_LIVE_STATEMENT`, `"Must be an account no live statement holds, draft or completed: delete the statement first."`. Nothing is written, the holder included.
- It is judged after `HAS_TRANSACTIONS`, which still answers first when both apply. A deleted statement does not count.
- So a holder with a live statement is never deleted with its last account.
- **Example.** A holder holds a soles and a dollar account, and its October statement, a draft, holds a balance for each; the dollar account has no transaction.
  - Before: `DELETE /accounts/<dollars>` answered `200`, and the statement kept a balance for a deleted account.
  - After: `409 IN_LIVE_STATEMENT`. Delete the statement first (`DELETE /statements/{id}`, a completed one reverted first); then the same `DELETE` answers `200`.
- **At the same moment as a `POST /statements` on the account's holder:** either the statement is written and the delete is refused `IN_LIVE_STATEMENT`, or the account is deleted and the statement is refused, never both. The statement's refusal is `409 CONCURRENT_CHANGE` on `holder_id` or `ACCOUNT_NOT_ON_HOLDER`, or, when the holder went with its last account, `422 INVALID_REFERENCE` on `holder_id` or `ACCOUNT_NOT_ON_HOLDER`. The statement is not trimmed for you: send it again with balances for the holder's remaining accounts.

## How it was checked

Against the practice engine over `expense_world_test`, serving `256f3190cf24fc36`, plus the full suite (3082 passed, 2 skipped). The live engine serves `256f3190cf24fc36` since its restart on 2026-10-28; no ledger update was needed.

- **The move:**
  - The contract states the route, its body and every refusal with its reason and key, and "an account never changes card" is replaced: pass (`x-error-reasons` lists all seven; the old rule's wording appears nowhere).
  - Moving an account in no statement onto a live holder with no account in its currency and no statement answers the account on its new holder; its old holder, left empty, is deleted with its own `DELETED` entry; both holders' `account_ids` read the change: pass (pair, then unpair, balances unchanged).
  - Each refusal answers as stated and writes nothing (an account once in a statement, a deleted one included; an archived or deleted target; a target holding that currency; a target with a statement): pass, each read back with its activity.
  - The sheet-import warning: not built (declined).
- **Deleted with its last account:**
  - Deleting a holder's only account leaves no live holder: `GET /holders` no longer lists it, and its name and statement code are free (a new holder takes them, `201`): pass.
  - Deleting one account of a holder holding two leaves the holder with the other: pass.
  - The activity log holds the account's `DELETED` entry and the holder's: pass.
- **Created in one write** (read as `POST /holders` with `accounts`):
  - One `POST /holders` with one account answers `201`, the holder holding only it; with a PEN and a USD account, holding both: pass.
  - A refused account (a taken name, two in one currency, a taken id, a blank name) leaves no holder; a refused holder (a taken name, code or id) leaves no account: pass.
  - The same request sent again under the same key answers the stored response and writes nothing; a changed body under that key is `409 IDEMPOTENCY_KEY_REUSED`: pass.
  - `make-account` with a new holder: not here (the person-holders change).
- **The holder's bank lines:**
  - `GET /bank-lines?holder_id=<id>&unreconciled=true&sort=date_asc` lists a two-currency holder's lines in no statement, both currencies together, oldest first, paged by cursor: pass (`limit=2`, two pages, no gap or repeat).
  - `GET /bank-lines/count?holder_id=<id>&unreconciled=true` counts the same lines: pass (`4`).
  - The contract states the filter, its refusals and how it combines with the others: pass.
- **The flagged line:**
  - The complete operation's advice names the path for a holder with a statement code, and a client following it word for word completes the statement with the line in it: pass. Run over HTTP with the `savings` sample paper (`GET /statements/samples/savings`) for a user in `America/Lima`: the upload created the twin naming the owner's line in `near_misses` and flagged the owner's line; revert, delete the twin, `PUT` the line to `"2025-03-03T00:00:00-05:00"`, upload again → every row matched, the statement completed, the owner's line in it at place 1 with its title, description, category and hashtag, the twin `404`.
  - The advice and the `STATEMENT_NOT_ORDERED` message no longer point different ways: pass (both send the client to the upload).
- **Covered account (no ask):** a draft statement on a two-account holder, its dollar account with no transaction: `DELETE` → `409 IN_LIVE_STATEMENT`, nothing written; after `DELETE /statements/{id}`, the same `DELETE` → `200`: pass.
- **At the same moment** (the move's, the last-account delete's and the covered account's races): run by the suite, both orders and at once; never both writes, never a `500`.

## What the TUI does

1. **Pair and unpair with the move.** Pairing: `POST /accounts/{id}/move` `{"holder_id": <the other currency's holder>}`. Unpairing: `POST /holders` (no `accounts`), then the move onto it. Show `PERSON_NOT_MOVED`, `STATEMENT_KEEPS_ACCOUNT`, `HOLDER_UNCHANGED`, `HOLDER_CURRENCY_TAKEN` and `HOLDER_HAS_STATEMENT` with their messages; do not offer the move on an archived account, a person, or an account that has ever been in a statement.
2. **After an account delete or a move, re-read the holder.** It may be gone (`404`). Drop any `DELETE /holders/{id}` that followed the delete of a holder's last account.
3. **Create a bank account with its holder in one write** where the TUI makes both: `POST /holders` with `accounts`, the Visa's two currencies as two items. Show item refusals by `accounts.<i>.<field>`.
4. **List a holder's lines with `?holder_id=`** (with `unreconciled=true` for the lines in no statement) and count them with `GET /bank-lines/count`, in place of one read per account.
5. **Follow the new flagged-line advice** on a holder with a statement code: offer "keep the bank's" and "keep mine", and for "keep mine" send `date` as 00:00 of the row's day in the user's `display_timezone`, never `Z`.
6. **Handle `409 IN_LIVE_STATEMENT` on `DELETE /accounts/{id}`:** tell the owner a statement holds the account, and offer deleting (or keeping) that statement first. A statement refused because an account was deleted while it was written is sent again with the remaining accounts.

## Done when

- Pairing two accounts on different holders and unpairing them again works from the TUI, and every move refusal shows its message.
- No TUI flow leaves an empty holder behind or calls `DELETE /holders/{id}` on a holder its last account's delete already removed.
- A new bank account with its own holder, and a two-currency holder, are each one `POST /holders`.
- A holder's lines in no statement show in one list, both currencies together, with their count.
- The flagged-line screen offers both paths on a holder with a statement code, and "keep mine" completes the statement with no twin.
- Deleting an account a live statement holds shows `IN_LIVE_STATEMENT` and what to do next.
