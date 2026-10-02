# The engine's whole contract is published at `GET /openapi.json`

Shipped 2026-09-27 · ⚠️ breaking · contract section *The contract*

## What changed

`GET /openapi.json` is the whole contract. It carries every endpoint's rules as its `description`, sections as `tags`, `x-error-codes` per operation, the `ErrorBody.code` enum, and `info.version`, a digest that moves on any change. It needs no login.

Also breaking:

- `/docs` and `/redoc` are gone (`404`).
- A bank-import row's `date` and the exchange-rate `date` / `date_from` / `date_to` are strict bare days: a number or a datetime is `422`.
- Operation `tags` are the contract's section names, not router names.

## What the CLI does

Read the contract only from a test engine's `/openapi.json`, never from a sibling checkout of the engine repo. Record the `info.version` it was checked against and re-check when it moves. `scripts/check_fixture_drift.py` needs no token.

## Done when

The CLI reads no file from the engine repo.
