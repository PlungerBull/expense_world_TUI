# Every account names its opening balance, and an opening balance can no longer move

Shipped 2026-10-14 · ⚠️ breaking · contract `e22e614517dd8393` → `409e74aa98fce38a`

This answers the CLI's ask of 2026-10-14: the account response carries its opening balance, so the account Edit form can show and change it.

## What changed

- **New field on every account response:** `opening_balance_transaction_id` is the id of the account's opening-balance transaction, or `null` when it has none. It is always present. It is on `GET /accounts`, `GET /accounts/{id}`, `POST /accounts`, `PUT /accounts/{id}`, `DELETE /accounts/{id}`, `POST /accounts/{id}/archive`, `POST /accounts/{id}/unarchive` and `POST /people`. Person accounts always show `null`. It is not on `/dashboard`, and it is not in account snapshots in `GET /activity`.
- **Only the id, not the amount or date.** A response names another resource by its id only. To show the amount and date, read `GET /transactions/{opening_balance_transaction_id}`. It returns `amount_cents` (always positive), `transaction_type` (1 = outflow, 2 = inflow) and `date`.
- **The field is always current.** It is read at request time. After the transaction is edited it shows the same id; after it is deleted it shows `null`; after a new one is created it shows the new id.
- **⚠️ An opening balance stays on its account and in `@Opening`.** On an opening-balance transaction, `PUT /transactions/{id}` now refuses:
  - a different `account_id`: `422 VALIDATION_ERROR`, `reasons: {"account_id": "OPENING_BALANCE_ACCOUNT_FIXED"}`
  - a different `category_id`, `@Pendiente` included: `422 VALIDATION_ERROR`, `reasons: {"category_id": "OPENING_BALANCE_CATEGORY_FIXED"}`
  - Sending both reports both fields. Amount, date, title and description stay editable, and `DELETE /transactions/{id}` still works.
- **Resending its own values is accepted.** Sending the transaction's current `account_id`, or its own `@Opening` `category_id`, is treated as no change. Resending its own `@Opening` id used to be refused with `RESERVED_CATEGORY`. Moving any other transaction into `@Opening` is still refused with `RESERVED_CATEGORY`.
- **Never two at once.** If two `POST /accounts/{id}/opening-balance` requests for the same account arrive at the same moment, one gets `201` and the other gets `409 CONFLICT`, `reasons: {"account_id": "OPENING_BALANCE_EXISTS"}`, the same refusal as when the account already has one.

## What the CLI does

1. **Account Edit form:**
   - Read `opening_balance_transaction_id` from the account.
   - If it is not `null`, fetch `GET /transactions/{id}` to show the amount and date.
   - Drop the lookup through `GET /categories` (finding `system_key: "opening_balance"`) and `GET /transactions?account_id=…&category_id=…`.
2. **Changing the opening balance:**
   - Edit the amount or date with `PUT /transactions/{opening_balance_transaction_id}`, sending only the fields that changed.
   - Remove it with `DELETE /transactions/{opening_balance_transaction_id}`.
   - Add one when the field is `null` with `POST /accounts/{id}/opening-balance`.
3. **Moving an opening balance to another account** is a delete on the old account and a `POST /accounts/{new_id}/opening-balance` on the new one. Never a `PUT` with a new `account_id`.
4. **Any transaction edit form** that lets the user change account or category: when the transaction is an opening balance, don't offer those two fields. Handle `OPENING_BALANCE_ACCOUNT_FIXED` and `OPENING_BALANCE_CATEGORY_FIXED` if they come back anyway.
5. **Model:** add `opening_balance_transaction_id: str | None` to the account model. It is required in the response.

## Done when

The account Edit form shows, edits, adds and removes an opening balance using only `opening_balance_transaction_id` and the transaction routes, and no transaction edit can move an opening balance to another account or category.
