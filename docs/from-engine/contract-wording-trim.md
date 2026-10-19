# The contract's wording was trimmed and corrected; no behaviour changed

Shipped 2026-10-18 · ➕ additive (wording only) · contract `c4327854a6d6e301` → `15063ec5587491ad`

Answers: no ask

## Each ask

No ask.

## What changed

- **No route, field, status, error code or reason changed.** Requests and responses are exactly as before.
- **`x-changelog` is short now.** It lists recent versions newest first, down to and including the oldest one a client is expected to hold; older entries are dropped. Today it holds `15063ec5587491ad` and `c4327854a6d6e301`, so the TUI still finds its stored version and reads the one entry above it.
- **Where rules are published moved:**
  - *Settings preconditions* (which requests answer `422 SETTINGS_MISSING`) and *No exchange-rate preconditions on writes* are now in the contract's general description (`info.description`), not inside `PUT /auth/settings`'s operation description.
  - *Balances* is now in the `Bank Accounts` tag description, *Engine-created system categories* in `Categories`, *Person rules* in `People / Person Accounts`, and *Sealed periods* in `Transactions (Ledger)`, not inside one operation.
  - *Aggregate exceptions* (activity log) are named, not numbered: **Hashtag links**, **Login bumps**, **Reconciliation side-effects**, **Hashtag delete**, **Exchange rates**, **Idempotency keys**, **Bank lines**.
  - The `sort_order` default on create (omitted or `null` → one more than the highest in its list, deleted rows included, `0` for an empty list; real accounts and people are separate lists) is stated once, in *Defaults on create*.
  - Cursor behaviour shared by every cursor-paged list (no cursor to an empty page; edits behind the bookmark move no later page; a malformed cursor is `INVALID_CURSOR`) is stated once, in *Cursors*.
- **Corrections that make the text match what the engine already does:**
  - Archived accounts: these are refused with `422 INVALID_REFERENCE` on the field naming the account — `POST /transactions`, `POST /transactions/batch`, `POST /transactions/import`, `POST /accounts/{id}/opening-balance`, `POST /reconciliations`, and a `PUT /transactions/{id}` that sends the archived account's `account_id`, even unchanged. Every other write on its existing transactions is allowed, a split and a delete included.
  - A stored exchange rate can change when it is corrected, which changes every figure that reads it, past ones included.
  - *Optimistic locking* is renamed *Version*: every mutable resource carries `version`, but no write compares it.
  - `GET /exchange-rates`: a `base` or `target` that is not 3 letters is `422` `OUT_OF_RANGE`.
  - `GET /transactions/count` and `GET /bank-lines/count` take bare dates in their date filters, like their lists.
  - `PUT /transactions/{id}`: `description` is stored as sent; `""` empties it; `null` is `NOT_NULL`.
- **Reason texts reworded** (meaning unchanged): `RETIRED_PARAMETER`, `SPLIT_RECONCILIATION_MIXED` ("Not sent by any operation."), `SPLIT_LINE_PARTS_DIVERGE`.

## How it was checked

The engine's full test suite passed against the test database, including the contract checks that every route has its section, that the version has a changelog entry, and two new tests pinning the archived-account and `description` wording. The live engine serves `15063ec5587491ad` from this push on.

## What the TUI does

1. Read the `15063ec5587491ad` entry and store `15063ec5587491ad` as the version it was checked against.
2. If the TUI quotes an *Aggregate exceptions* item by number, or reads *Settings preconditions* from `PUT /auth/settings`, point it at the new names and place.
3. If the TUI offers edits on an archived account's transactions, they keep working; only a `PUT` that sends `account_id` is refused, so send `account_id` only when it changes.

## Done when

The TUI has stored `15063ec5587491ad`, and the owner relays that the TUI has read up to it.
