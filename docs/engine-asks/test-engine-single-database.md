# A test engine refuses to start half-pointed at the real ledger

Raised 2026-09-27 by the CLI client.

## Why

The engine reads any database URL that is missing from its start command from its `.env`, and
there `ADMIN_DB_URL` names the real ledger (`expense_world`). So a test-engine start (port
`8002`, over `expense_world_test`) that forgets `ADMIN_DB_URL` runs its admin pool, which
writes `exchange_rates`, against the real ledger, while the app pool uses the test database.
One missing variable turns a practice run into writes on real data, and every client's test
setup (CLI today, web and iOS later) can make the same slip.

Clients currently guard against this themselves by checking the start command for both URLs.
That is a copy of an engine safety rule in each client, and it only protects clients that
remember to add it.

## The ask

The engine refuses to start when its two database URLs name different databases. Or,
alternatively, a start flag such as `--test` that requires both URLs to name
`expense_world_test` and refuses to start otherwise.

## Done when

- Starting the engine with the app URL on `expense_world_test` and the admin URL on
  `expense_world` (from `.env` or explicitly) fails at startup with a clear message naming both
  databases.
- A start with both URLs on the same database behaves exactly as today.
- An engine test covers the refusal.

## What the CLI removes once it lands

Its own check that a test-engine start command names both database URLs. It keeps only the
rule that tests use port `8002`.
