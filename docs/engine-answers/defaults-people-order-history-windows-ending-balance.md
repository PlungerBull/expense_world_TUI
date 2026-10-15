# Empty fields take their default, people list after accounts, history windows say where the previous one ends, and completing a reconciliation needs its ending balance

Shipped 2026-10-15 · ⚠️ breaking · contract `409e74aa98fce38a` → `42d70a629215928d`

Four independent changes. Each one is below with what the CLI does about it.

## What changed

### 1. A create treats `null` like a missing field (additive)
- `POST /accounts` and `POST /people` accept `"color": null` (gives `#3b82f6`) and `"sort_order": null` (adds the row at the end of its list). These used to be refused with `422 NOT_NULL`.
- `POST /categories` no longer requires `color`. Leaving it out or sending `null` gives `#3b82f6`.
- `POST /hashtags` with `"sort_order": null` adds the hashtag at the end, and `POST /accounts/{id}/opening-balance` with `"title": null` gives `"Opening balance"`. Both already worked this way and are now documented.
- **Updates are unchanged.** `PUT /accounts/{id}`, `PUT /categories/{id}` and `PUT /hashtags/{id}` still refuse `null` on `color` or `sort_order` with `422 NOT_NULL`.

### 2. People come after accounts (order change)
`GET /accounts?include_people=true` lists every real account first, then every person. Within each group the order is the same as before: `sort_order` ascending, then oldest first. Before this change the two groups were mixed together. The `/dashboard` panels were already one group each and are unchanged.

### 3. History windows say where the previous one ends (⚠️ breaking)
On `GET /activity` and `GET /exchange-rates/history`:
- **New field `previous_date_to`**, always present. Send it back **unchanged** as `date_to` to read the window just before this one. Walking back this way reads every row exactly once.
  - On exchange rates it is the day before `date_from`, for example `2026-08-30`.
  - On activity it is the instant one microsecond before `date_from`, in `display_timezone`, for example `2026-08-30T23:59:59.999999-05:00`.
  - It is `null` only when nothing earlier exists on the calendar.
- **⚠️ Using the echoed `date_from` as the next `date_to` reads the boundary moment twice.** The contract used to say to do that. Stop.
- **An omitted `date_from` now gives exactly 30 calendar days, counting `date_to`'s own day.**
  - On exchange rates that is `date_to` minus 29 days. It used to be 31 days.
  - On activity it is the first instant of the day 29 days before, in `display_timezone`. It used to be the same time of day 30 days earlier.
- **⚠️ The widest window is 366 calendar days, counting both ends.** `GET /exchange-rates/history?date_from=2025-01-01&date_to=2026-01-02` is now `422 RANGE_TOO_WIDE`; `2026-01-01` is the widest end date allowed. Activity already had this limit.
- **A date the calendar cannot hold** (before `0001-01-01` or after `9999-12-31`, also after converting to or from `display_timezone`) is now `422 OUT_OF_RANGE` on that key, where it used to be a `500`. On activity a bare `date_to=9999-12-31` is always refused; send an instant instead.

### 4. Completing a reconciliation needs the ending balance (⚠️ breaking)
- `POST /reconciliations/{id}/complete` on a reconciliation whose `ending_balance_cents` is `null` is now `422 VALIDATION_ERROR` with `reasons: {"ending_balance_cents": "ENDING_BALANCE_REQUIRED"}`, and nothing is written. It used to complete.
- This check comes after the `404` and after the already-completed no-op, and before `NO_TRANSACTIONS_ASSIGNED`, `SETTINGS_MISSING` and `UNASSIGNED_IN_PERIOD`.
- Drafts are unchanged: `POST /reconciliations` and `PUT /reconciliations/{id}` still accept `null`, for when the statement hasn't arrived yet.
- A reconciliation already completed without an ending balance stays as it is. To fill the balance in, do `POST /reconciliations/{id}/revert`, then `PUT /reconciliations/{id}` with `ending_balance_cents`, then `POST /reconciliations/{id}/complete`.

## What the CLI does

1. **Creates:** if the CLI fills in `color` or `sort_order` itself before `POST /accounts`, `/people`, `/categories` or `/hashtags`, or refuses `null` on them, drop that and let the engine apply the default. Remove any `NOT_NULL` handling on those `POST`s. Make `color` optional in the category create model.
2. **Account lists:** don't re-sort or group what `GET /accounts?include_people=true` returns; show it in the order it comes. Any client-side sort that put accounts before people can go.
3. **History paging** (`activity` and exchange-rate history):
   - Read `previous_date_to` from each response and send it unchanged as the next `date_to`. Don't do any date arithmetic.
   - Stop when it is `null`.
   - Add `previous_date_to: str | None` to both response models. It is always present.
   - Keep any window the CLI builds to 366 calendar days or fewer, counting both ends. If the CLI states the default window, say 30 days counting today.
   - Handle `OUT_OF_RANGE` on `date_from` / `date_to`.
4. **Reconciliation complete:**
   - Before calling complete, check `ending_balance_cents`. If it is `null`, ask for it, `PUT` it, then complete.
   - Handle `ENDING_BALANCE_REQUIRED` if it comes back anyway.
   - For a completed reconciliation that shows no ending balance, offer revert → enter balance → complete.

## Done when

- The CLI creates an account and a category without sending a colour, and both come back `#3b82f6`.
- The account list with people shows the order the engine returns.
- Paging back through activity and exchange-rate history uses only `previous_date_to`, and never shows a row twice.
- Completing a reconciliation without an ending balance asks for the balance instead of failing.
