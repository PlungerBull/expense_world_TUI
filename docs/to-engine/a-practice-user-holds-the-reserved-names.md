# The practice engine seeds a second practice user whose own category and hashtag hold the reserved names

Raised 2026-10-25.

## Why

`RESERVED_NAME_HELD` comes back only when a write needs a system category or the built-in
pending hashtag, that system row does not exist yet, and one of the user's own categories or
hashtags already holds its name. On every transaction route the hashtag case is keyed
`hashtag_ids` itself, never `parts.<i>.hashtag_ids` or `transactions.<i>.hashtag_ids`, and the
category case is keyed `category_id`; nothing is written.

No live test can produce this refusal. The practice engine's one practice user already holds
`@Pendiente`, `@Opening` and the pending hashtag, and none of them can ever be deleted. The API
also refuses a user category or hashtag that takes a reserved name (`RESERVED_NAME`), so no
client can recreate the held state through the API. The terminal client therefore proves its
handling of this refusal only against a fake engine, on every screen that can receive it, and
cannot check that the real engine sends it on the key the contract names.

## The ask

The local test-user seed, the script that seeds the practice user and reseeds it with
`--force`, also seeds a second practice user, on the same
`expense_world_test` database, that is held on the reserved names:

- a category of the user's own (`system_key` null) named `@Pendiente` and one named `@Opening`;
- a hashtag of the user's own (`system_key` null) named `Pendiente`;
- no system category and no pending hashtag.

The seed writes these rows straight into the database, since the API refuses those names. Each
`--force` run puts the user back in that state: it restores the three held names if a test
renamed them, removes any system row that somehow appeared, and prints one fresh PAT for this
user beside the first user's, clearly labelled, in the same output and never to a file. The
first practice user is unchanged.

## Done when

- After a `--force` reseed, the second practice user holds exactly the rows above, and
  its PAT is printed beside the first one's.
- As that user, `POST /transactions` with a category and no `hashtag_ids` returns `409`
  `RESERVED_NAME_HELD` on `hashtag_ids`; with a hashtag and no category it returns `409`
  `RESERVED_NAME_HELD` on `category_id`; `POST /accounts/{id}/opening-balance` returns it on
  `category_id`; and nothing is written by any of them.
- As that user, `PUT /bank-lines/{id}` with `parts` that leaves a part with no hashtag returns
  `409` `RESERVED_NAME_HELD` on `hashtag_ids`, and the bank line is unchanged.
- A further `--force` run leaves the second user in the same state, whatever a test did to it.

## What this client removes once it lands

Nothing: the client has no workaround for this refusal. Its proof of how it handles the refusal
stops resting on a fake engine alone; it adds live tests that draw the refusal as the second
practice user on each route above.
