# A bank line can be read — its parts, signed total and part count — and the import's mismatched days show what each unclaimed line is

Shipped 2026-10-17 · ⚠️ breaking · contract `3129bfa2c43a4446` → `a924900619285f56` (last version covered: `a924900619285f56`)

This answers two TUI asks of 2026-10-16: "read a bank line" and "day-mismatch lines carry what they are". It covers every contract change from `3129bfa2c43a4446` (exclusive) to `a924900619285f56` (inclusive). Part 3 replaces what the earlier bank-lines-and-pending-hashtag answer says about `unclaimed_lines`. Check `info.version` in `GET /openapi.json` before relying on it; its `x-changelog` has one entry per version in this range.

## What changed

### 1. List a line's parts: `?bank_line_id=` on the ledger (`3d7205a872889283`) — additive

- `GET /transactions?bank_line_id=<id>` lists exactly the live transactions of that bank line: the ledger's usual ordering, paging and response shape.
- It combines with every other filter. A cursor is bound to it like to any other filter: reusing a cursor with a different `bank_line_id` (or without it) is `422 INVALID_CURSOR` on `after`.
- `GET /transactions/count` takes the same filter.
- An id that names no live line of yours (no such line, a line whose last part was deleted, another user's line) lists nothing and counts `0`. It is never `404`.
- A value that is not a UUID is `422` on `bank_line_id` (`INVALID_FORMAT`).

### 2. Read one line: `GET /bank-lines/{id}` (`c572d3a5f4f509d1`) — additive

```json
{
  "id": "8c1e…",
  "account_id": "3f0a…",
  "operation_code": "123456",
  "net_cents": -10000,
  "part_count": 2,
  "transaction_ids": ["a1…", "b2…"]
}
```

- `net_cents` is the **signed** sum of the line's live parts: inflow positive, outflow negative, like `ledger_net_cents` and account balances. A charge of 100 split 60 + 40 reads `-10000`. A line can mix directions (−60 + 15 reads `-4500`).
- `part_count` is the number of live parts. A transaction never split reads `1`, with its own signed amount as `net_cents`.
- `transaction_ids` are the live parts' ids, in the order `GET /transactions?bank_line_id=` lists them by default.
- `operation_code` is `null` when the line has none; the key is always present.
- The figures are worked out from the live parts on every read, so they follow every split, edit and delete.
- **`404`** when the id names no live line of yours: no such line, a line whose last part was deleted, or another user's line. A malformed id is `422` on `bank_line_id` (`INVALID_FORMAT`).
- There is **no read of several lines in one call**. The engine supplies a line's figures when one line is opened (re-split, the "this changes the other parts too" warning), not across a ledger page.

### 3. Import: unclaimed lines carry their parts (`a924900619285f56`) — ⚠️ breaking

`POST /transactions/import` → each `day_mismatches[].unclaimed_lines[]` entry changes:

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
- `parts` are ordinary transaction responses, exactly what `GET /transactions/{id}` returns: `amount_cents` positive, direction in `transaction_type`. They come in the order `GET /transactions` lists them by default. A split line is **one** entry holding all its parts.
- `net_cents` is the parts' signed sum, inflow positive.
- Dry run and apply return the same shape. The parts are the ledger as it stands after the import; the import never writes an unclaimed line, so on a dry run they are the ledger as it stands now.
- **A day's figures add up:** the transactions on lines a file row matched, plus the rows the import creates on that day, plus the unclaimed lines' `net_cents`, equal the day's `ledger_net_cents`.

**New reporting rule** (same version): a day is now reported when its totals differ **or** when it holds a line no file row claimed. A +50 and a −50 in the ledger that the bank does not have used to cancel out and stay hidden; now that day is reported with both lines. A day whose totals agree and whose every line was claimed is still not reported, and an opening balance never makes a day reported. Expect days in `day_mismatches` whose `file_net_cents` equals `ledger_net_cents`.

### What was asked for and not done, and why

- **A line's total and part count on every transaction response: declined.** A transaction carries `bank_line_id` only. Copying another record's figures onto each transaction would break the IDs-only rule, change a transaction's response without its `version` moving, and need an exception in its activity snapshot. Read the figures from `GET /bank-lines/{id}`.
- **A shorter part shape with a signed `amount_cents`: declined.** Every response returns `amount_cents` positive with the direction in `transaction_type`; parts are the transaction response the TUI already reads. Totals (`net_cents`, `ledger_net_cents`) are signed.

## What the TUI does

1. **Import screen (breaking):** stop reading `unclaimed_lines[].transaction_ids`. Draw each unclaimed line from `parts` (title, amount with `transaction_type`, category, description) and its `net_cents`, grouped as one entry per line. Drop any per-transaction lookups made to fill that screen.
2. **Import screen:** handle days reported with equal `file_net_cents` and `ledger_net_cents`: the reason is the unclaimed lines listed.
3. **Re-split:** open with the line's current parts from `GET /transactions?bank_line_id=<id>` and check the new parts against `net_cents` from `GET /bank-lines/{id}`, instead of searching the ledger around the date.
4. **Editing a part's title, date, account or operation code:** when `part_count` (from `GET /bank-lines/{id}`) is above 1, the change reaches every part; warn as the TUI sees fit.
5. Remove any client-side summing of a line's parts.

## Done when

- The import screen renders unclaimed lines from `parts` and `net_cents`, with no read of `transaction_ids` and no per-transaction lookup.
- A day with equal totals but an unclaimed line shows that line.
- Re-split and the line-field warning read `GET /bank-lines/{id}` and `?bank_line_id=`; the TUI adds no amounts of its own.
