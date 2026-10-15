# Every 409, 403 and LIMIT_REACHED now names the rule that fired, so the CLI can switch on `reasons` instead of status and route

Shipped 2026-10-14 · ➕ additive · contract `2b73f0360f06e29d` → `9b0a6d4e6d7b6b5b`

Answers the CLI's ask of 2026-10-14 ("refusals that are not form errors carry a reason"). The engine went further than the ask: every refusal of this kind carries a reason, not only the six the CLI listed.

## What changed

No HTTP status and no `code` changed. Every error with code `CONFLICT`, `FORBIDDEN` or `LIMIT_REACHED` now has `fields` and `reasons` filled, keyed by the thing refused. Before this change they had `null`. Neither is ever `null` on these codes now. `UNAUTHORIZED`, `NOT_FOUND`, `INTERNAL_ERROR`, `SERVICE_UNAVAILABLE` and the router-level codes keep `fields: null, reasons: null`, because their code already says everything.

The envelope is the one the CLI already parses. Example, `DELETE /accounts/{id}` on an account with transactions:

```json
{"error": {
  "code": "CONFLICT",
  "message": "Account has active transactions. Archive instead.",
  "fields":  {"account_id": "Must not be used by any active transaction."},
  "reasons": {"account_id": "HAS_TRANSACTIONS"}
}}
```

### The CLI's six, and the idempotency key

| Refusal | Status | Key | Reason |
|---|---|---|---|
| `DELETE /accounts/{id}`: the account has non-deleted transactions | 409 | `account_id` | `HAS_TRANSACTIONS` |
| `DELETE /categories/{id}`: a non-deleted transaction uses it | 409 | `category_id` | `HAS_TRANSACTIONS` |
| `DELETE /categories/{id}`: a system category | 403 | `category_id` | `SYSTEM_CATEGORY` |
| `DELETE /transactions/{id}`: the row is in a completed reconciliation | 409 | `transaction_id` | `IN_COMPLETED_RECONCILIATION` |
| `POST /accounts/{id}/opening-balance`: the account already has one | 409 | `account_id` | `OPENING_BALANCE_EXISTS` |
| `POST /accounts/{id}/opening-balance`: `transaction_id` already taken | 409 | `transaction_id` | `ID_EXISTS` |
| Any write with `X-Idempotency-Key`: the key was used for a different request | 409 | `X-Idempotency-Key` | `IDEMPOTENCY_KEY_REUSED` |
| `POST /auth/pat`: its key was used before (the secret cannot be shown again) | 409 | `X-Idempotency-Key` | `SECRET_NOT_REPLAYABLE` |

`HAS_TRANSACTIONS` is the one reason shared by two resources: the rule is the same ("still in use"), and the CLI knows which resource it tried to delete. The two idempotency reasons need different fixes. `IDEMPOTENCY_KEY_REUSED` is a client bug: the CLI sent one key for two different writes. `SECRET_NOT_REPLAYABLE` only needs a new key.

### Every other refusal

| Refusal | Status | Key | Reason |
|---|---|---|---|
| `DELETE /reconciliations/{id}` on a completed reconciliation | 409 | `reconciliation_id` | `RECONCILIATION_NOT_DRAFT` |
| A taken `id` on any create: `POST /accounts`, `/people`, `/categories`, `/hashtags`, `/reconciliations`, `/auth/pat`, `/transactions` | 409 | `id` | `ID_EXISTS` |
| A taken id in `POST /transactions/batch` | 409 | `transactions.<i>.id` | `ID_EXISTS` |
| A taken id in `POST /transactions/import` (one another user holds) | 409 | `rows.<i>.id` | `ID_EXISTS` |
| A name already taken: `POST /accounts`, `/people`, `/categories`, `/hashtags`, and renames through `PUT /accounts/{id}`, `/categories/{id}`, `/hashtags/{id}` | 409 | `name` | `NAME_EXISTS` |
| An operation code already on the account: `POST /transactions`, `PUT /transactions/{id}` | 409 | `operation_code` | `OPERATION_CODE_EXISTS` |
| The same, in `POST /transactions/batch` | 409 | `transactions.<i>.operation_code` | `OPERATION_CODE_EXISTS` |
| The same, in `POST /transactions/import` (a created row, or a code written onto a matched row) | 409 | `rows.<i>.operation_code` | `OPERATION_CODE_EXISTS` |
| A delete that lost a race with another delete: `DELETE /accounts/{id}`, `/categories/{id}`, `/hashtags/{id}`, `/reconciliations/{id}` | 409 | the path id (`account_id`, …) | `CONCURRENT_CHANGE` |
| The engine's own system-category creation lost a race (on `POST /transactions`, `/transactions/batch`, `/transactions/import`, `/accounts/{id}/opening-balance`) | 409 | `category_id` | `CONCURRENT_CHANGE` |
| On those same four routes: a user category holds `@Pendiente`'s or `@Opening`'s name when the engine needs that system category | 409 | `category_id` | `RESERVED_NAME_HELD` |
| A create at its collection's cap: `POST /accounts`, `/people`, `/categories`, `/hashtags` | 422 `LIMIT_REACHED` | `id` | `CAP_REACHED` |

Notes:
- `ID_EXISTS` now means any taken client-chosen id. It used to mean only "one of your transactions".
- `PUT /transactions/{id}` that only changes `account_id`, onto an account where another live transaction already has this row's `operation_code`, is `409` on `operation_code` even though the body did not send it. The key names the field that holds the clashing value.
- The batch's `409` used to have `fields: null` and no index. It is now keyed by item index.
- `CONCURRENT_CHANGE` means "re-fetch and retry".

Each operation's `x-error-reasons` in `GET /openapi.json` lists exactly the reasons it can send. *Error reasons* describes each one, and the `x-changelog` entries for both versions above list every change.

## What the CLI does

- Pick the "what to do next" line by `reasons`, and delete the guess from HTTP status and route. Suggested lines:
  - `HAS_TRANSACTIONS` on an account: offer to archive it.
  - `SYSTEM_CATEGORY`: it cannot be deleted.
  - `IN_COMPLETED_RECONCILIATION` and `RECONCILIATION_NOT_DRAFT`: revert the reconciliation to draft first.
  - `OPENING_BALANCE_EXISTS`: edit or delete the existing opening balance.
  - `NAME_EXISTS`, `OPERATION_CODE_EXISTS`: pick another value.
  - `CONCURRENT_CHANGE`: re-fetch and retry.
  - `RESERVED_NAME_HELD`: rename the category that holds the system name.
  - `CAP_REACHED`: delete one first.
  - `ID_EXISTS`: a fresh id. On a create this is almost always a CLI bug.
  - `IDEMPOTENCY_KEY_REUSED`: a CLI bug, report it as one.
  - `SECRET_NOT_REPLAYABLE`: retry with a new key.
- Anything that assumed `fields: null` on `LIMIT_REACHED` or on the batch's `409` should read the keyed `fields`/`reasons` instead.
- Practice it against the practice engine. Each refusal above can be provoked there, for example deleting an account that has a transaction.

## Done when

- The CLI decides its next-step line from `code` and `reasons` alone, on every `CONFLICT`, `FORBIDDEN` and `LIMIT_REACHED`.
- The status-and-route guess is deleted from the CLI.
- The owner tells the engine the CLI has caught up, and this file is deleted.
