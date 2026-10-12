# Every list ordering in the contract states its direction

Shipped 2026-10-11 · ➕ additive · contract `8d2430081e64cd7c` → `26c9f9880ad3540c`

Answers the CLI's request of 2026-10-11 to state whether the creation-time tie-break of `GET /v1/categories/{category_id}/hashtags` is oldest or newest first.

## What changed

Wording only; no list changed its order. Wherever a list's ordering ends on creation time, the contract now says "oldest first":

- `GET /v1/accounts`: `sort_order` ascending, then creation time, oldest first.
- `GET /v1/categories`: system categories first, then `sort_order` ascending, then creation time, oldest first.
- `GET /v1/categories/{category_id}/hashtags`: `uses` descending, then the hashtag's creation time, oldest first.
- `GET /v1/hashtags`: `sort_order` ascending, then creation time, oldest first.
- `GET /v1/reconciliations?account_id=`: `date_start` ascending, then creation time, oldest first.

## What the CLI does

Nothing in code if it shows these lists in the order the engine returns them. Move the contract version it holds to `26c9f9880ad3540c` and refresh any fixture that pins the version or the wording.

## Done when

The CLI's contract checks pass against an engine serving `26c9f9880ad3540c`.
