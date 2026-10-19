# An archived account is frozen except for its transactions' categorisation; the contract's wording was trimmed

Shipped 2026-10-18 · ⚠️ breaking · contract `c4327854a6d6e301` → `15063ec5587491ad` → `6088c6255f258ce7` → `98fd5c39226bc126` → `ab14bd54f4c8b016`

Answers: no ask (the owner raised the freeze, 2026-10-18)

## Each ask

No ask.

## What changed

### ⚠️ An archived account is frozen (`6088c6255f258ce7`, `98fd5c39226bc126`)

On an archived account, the only thing that changes is its transactions' categorisation. Unarchive the account (`POST /accounts/{id}/unarchive`) to change anything else; unarchiving lifts every refusal below.

**Still allowed** on a transaction whose account is archived: `PUT /transactions/{id}` sending `category_id`, `hashtag_ids` or `description`. A `title` or `operation_code` that is `null` may also be filled once (a title counts as empty only while it is `null` on every part of the bank line); changing or clearing it after that is refused. Writes that re-categorise as a side effect still reach these rows (`DELETE /hashtags/{id}` moving them onto the pending hashtag).

**Refused, with the new reason `ACCOUNT_ARCHIVED`:**

| Route | Status | Key |
|---|---|---|
| `PUT /transactions/{id}` sending `amount_cents`, `date`, `title`, `operation_code`, `account_id` or `reconciliation_id` | `422` | one key per refused field |
| `DELETE /transactions/{id}` | `409` | `transaction_id` |
| `DELETE /bank-lines/{id}` (any part of the line on an archived account) | `409` | `bank_line_id` |
| `POST /transactions/{id}/split` | `422` | `transaction_id` |
| `PUT /reconciliations/{id}`, every field (`name`, `date_start`, `date_end`, `beginning_balance_cents`, `ending_balance_cents`) | `422` | one key per field sent |
| `POST /reconciliations/{id}/complete` | `409` | `reconciliation_id` |
| `POST /reconciliations/{id}/revert` | `409` | `reconciliation_id` |
| `DELETE /reconciliations/{id}` | `409` | `reconciliation_id` |

- **Refused on the key, not the value:** sending a field's current value is refused too. A `PUT` mixing allowed and refused fields writes nothing; only the refused keys are named.
- **Another part of the line:** a line field (`title`, `date`, `account_id`, `operation_code`, `reconciliation_id`) sent on a transaction of a live account is refused the same way when it would change another part of the same bank line that sits on an archived account. The message names that part: "Another part of this bank line (<id>) is the cause: …".
- **Reconciliations, drafts and completed alike.** Completing an already completed reconciliation and reverting a draft, which are silent no-ops elsewhere, are `409` here too. An empty `PUT /reconciliations/{id}` body still returns the reconciliation and writes nothing.
- **Order:** `ACCOUNT_ARCHIVED` answers before every other rule on these routes — `LOCKED`, `IN_COMPLETED_RECONCILIATION`, `ASSIGNED_TO_RECONCILIATION`, `OPENING_BALANCE_NOT_SPLIT`, `RECONCILIATION_NOT_DRAFT`, `EMPTY`, `RANGE_INVERTED`, `PERIOD_OVERLAPS`, `ENDING_BALANCE_REQUIRED`, `NO_TRANSACTIONS_ASSIGNED`, `UNASSIGNED_IN_PERIOD` and the rest. Only the request's shape (a malformed or unknown field, a forbidden `null`) and a `404` come first.
- **Nothing is written on a refusal**, and the account's balance does not move.
- **Unchanged:** `PUT /accounts/{id}`, `/archive`, `/unarchive`; every read, balance and report; the writes that already refused an archived account (`POST /transactions`, `POST /transactions/batch`, `POST /transactions/import`, `POST /accounts/{id}/opening-balance`, `POST /reconciliations`) keep answering `422 INVALID_REFERENCE`, and moving a transaction *onto* an archived account is still `INVALID_REFERENCE`.

**Before → after.** `DELETE /transactions/{id}` on an archived account's transaction:
- Before: `200`, the transaction deleted.
- After: `409`
  ```json
  {"error":{"code":"CONFLICT","message":"Cannot delete a transaction on an archived account. Unarchive the account first.","fields":{"transaction_id":"The account is archived. Unarchive it first."},"reasons":{"transaction_id":"ACCOUNT_ARCHIVED"}}}
  ```

`PUT /transactions/{id}` with `{"account_id": "<its current, archived account>"}`:
- Before: `422` on `account_id`, reason `INVALID_REFERENCE`.
- After: `422` on `account_id`, reason `ACCOUNT_ARCHIVED`.

The other bodies, verbatim from the practice engine:

`PUT /transactions/{id}`, `422`, body `{"amount_cents":-11111,"date":"2026-09-04T12:00:00-05:00","title":"Other","category_id":"<id>"}` (the category is not applied either):
```json
{"error":{"code":"VALIDATION_ERROR","message":"The transaction's account is archived: only its category, hashtags and description can change. Unarchive the account first.","fields":{"amount_cents":"The account is archived. Unarchive it first.","date":"The account is archived. Unarchive it first.","title":"The account is archived. Unarchive it first."},"reasons":{"amount_cents":"ACCOUNT_ARCHIVED","date":"ACCOUNT_ARCHIVED","title":"ACCOUNT_ARCHIVED"}}}
```

`DELETE /bank-lines/{id}`, `409`:
```json
{"error":{"code":"CONFLICT","message":"Cannot delete a bank line on an archived account. Unarchive the account first.","fields":{"bank_line_id":"The account is archived. Unarchive it first."},"reasons":{"bank_line_id":"ACCOUNT_ARCHIVED"}}}
```

`POST /transactions/{id}/split`, `422`:
```json
{"error":{"code":"VALIDATION_ERROR","message":"Cannot split a transaction on an archived account. Unarchive the account first.","fields":{"transaction_id":"The account is archived. Unarchive it first."},"reasons":{"transaction_id":"ACCOUNT_ARCHIVED"}}}
```

`PUT /reconciliations/{id}`, `422`, body `{"name":"Renamed draft"}`:
```json
{"error":{"code":"VALIDATION_ERROR","message":"The reconciliation's account is archived. Unarchive the account first.","fields":{"name":"The account is archived. Unarchive it first."},"reasons":{"name":"ACCOUNT_ARCHIVED"}}}
```

`POST /reconciliations/{id}/complete`, `409` (`revert` and `DELETE` answer the same, with "Cannot revert …" and "Cannot delete …"):
```json
{"error":{"code":"CONFLICT","message":"Cannot complete a reconciliation on an archived account. Unarchive the account first.","fields":{"reconciliation_id":"The account is archived. Unarchive it first."},"reasons":{"reconciliation_id":"ACCOUNT_ARCHIVED"}}}
```

### `PUT /reconciliations/{id}`: the reconciliation is found first (`98fd5c39226bc126`)

A blank `name` sent to a reconciliation that does not exist, is deleted or is another user's now answers `404`, not `422 EMPTY`, on any account.

### Wording only (`ab14bd54f4c8b016`)

No behaviour changed. `POST /accounts/{id}/opening-balance` now says that on an archived account the opening balance changes only in its categorisation and is not deleted, as everything above says. `POST /transactions/{id}/split` states the archived-account refusal once instead of twice.

### The contract's wording was trimmed and corrected (`15063ec5587491ad`)

No route, field, status, error code or reason changed in this version.

- **`x-changelog` is short now.** It lists recent versions newest first, down to and including the oldest one a client is expected to hold; older entries are dropped. A client whose version is not listed treats the whole contract as changed.
- **Where rules are published moved:**
  - *Settings preconditions* (which requests answer `422 SETTINGS_MISSING`) and *No exchange-rate preconditions on writes* are now in the contract's general description (`info.description`), not inside `PUT /auth/settings`'s operation description.
  - *Balances* is now in the `Bank Accounts` tag description, *Engine-created system categories* in `Categories`, *Person rules* in `People / Person Accounts`, and *Sealed periods* in `Transactions (Ledger)`, not inside one operation.
  - *Aggregate exceptions* (activity log) are named, not numbered: **Hashtag links**, **Login bumps**, **Reconciliation side-effects**, **Hashtag delete**, **Exchange rates**, **Idempotency keys**, **Bank lines**.
  - The `sort_order` default on create (omitted or `null` → one more than the highest in its list, deleted rows included, `0` for an empty list; real accounts and people are separate lists) is stated once, in *Defaults on create*.
  - Cursor behaviour shared by every cursor-paged list (no cursor to an empty page; edits behind the bookmark move no later page; a malformed cursor is `INVALID_CURSOR`) is stated once, in *Cursors*.
- **Corrections that make the text match what the engine already did:**
  - A stored exchange rate can change when it is corrected, which changes every figure that reads it, past ones included.
  - *Optimistic locking* is renamed *Version*: every mutable resource carries `version`, but no write compares it.
  - `GET /exchange-rates`: a `base` or `target` that is not 3 letters is `422` `OUT_OF_RANGE`.
  - `GET /transactions/count` and `GET /bank-lines/count` take bare dates in their date filters, like their lists.
  - `PUT /transactions/{id}`: `description` is stored as sent; `""` empties it; `null` is `NOT_NULL`.
- **Reason texts reworded** (meaning unchanged): `RETIRED_PARAMETER`, `SPLIT_RECONCILIATION_MIXED` ("Not sent by any operation."), `SPLIT_LINE_PARTS_DIVERGE`.

## How it was checked

The engine's full test suite passed against the test database (1647 tests), including the contract checks that every route has its section, that every version has a changelog entry, and that every reason a route sends is declared. Against the practice engine on contract `98fd5c39226bc126`, with an account holding an opening balance, transactions (one split into two parts, one with an empty title), a draft and a completed reconciliation, then archived:

1. Changing a transaction's category, hashtags and description works; the response shows the new values. **Pass.**
2. Changing its amount, date, title, operation code, account or reconciliation is refused with `ACCOUNT_ARCHIVED`, its current amount included, and the transaction is unchanged afterwards (same `version`). A row also in the completed reconciliation answers `ACCOUNT_ARCHIVED`, not `LOCKED`. **Pass.**
3. The empty title (and an empty operation code) can be filled; changing or clearing it afterwards is refused. **Pass.**
4. Deleting a transaction, deleting a bank line (a split line included) and splitting are each refused with `ACCOUNT_ARCHIVED`; the balance is the same before and after, and every row is still live. **Pass.**
5. Renaming, editing the dates of, completing, reverting and deleting each reconciliation, draft and completed, are refused with `ACCOUNT_ARCHIVED`; both are unchanged afterwards. **Pass.**
6. Renaming the archived account works. **Pass.**
7. After `POST /accounts/{id}/unarchive`, every write refused above works again. **Pass.**
8. `GET /openapi.json` lists `ACCOUNT_ARCHIVED` in `x-error-reasons` on exactly the eight routes in the table above, and `POST /accounts/{id}/archive` describes the rule. **Pass.**

The live engine serves `ab14bd54f4c8b016` (the checks above ran on `98fd5c39226bc126`; `ab14bd54f4c8b016` changes wording only).

## What the TUI does

1. Read the `15063ec5587491ad`, `6088c6255f258ce7`, `98fd5c39226bc126` and `ab14bd54f4c8b016` entries of `x-changelog`, and store `ab14bd54f4c8b016` as the version it was checked against.
2. On an archived account's transactions, offer only category, hashtag and description edits, plus filling an empty title or operation code. Hide or disable editing amount, date, title, operation code, account and reconciliation, and delete, bank-line delete and split, and point to unarchiving the account.
3. On an archived account's reconciliations, hide or disable rename, date and balance edits, complete, revert and delete, and point to unarchiving.
4. Handle `ACCOUNT_ARCHIVED` wherever these routes are called (a stale screen can still send one): show the message and offer to unarchive. A `PUT /transactions/{id}` that sends `account_id` on an archived account's transaction now answers `ACCOUNT_ARCHIVED`, not `INVALID_REFERENCE`.
5. If the TUI shows an `EMPTY` name error for a reconciliation rename, expect `404` first when the reconciliation is gone.
6. If the TUI quotes an *Aggregate exceptions* item by number, or reads *Settings preconditions* from `PUT /auth/settings`, point it at the new names and place.

## Done when

The TUI has stored `ab14bd54f4c8b016`, no longer offers the frozen writes on an archived account, and the owner relays that the TUI has read up to `ab14bd54f4c8b016`.
