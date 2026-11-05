# Give the shared practice user an account that every reseed keeps

Raised 2026-11-05.

## Why

The practice seed script gives the client two practice users and a
key for each, but the shared practice user holds no accounts. The client's tester drives the
real app against the practice engine at the end of each piece of work, and every screen that
picks an account (logging a transaction, an account's balances and statements, the account
checks) has nothing to pick. Those checks are then proven only against a fake engine, which
cannot catch the real engine answering differently. The tester may not write to the practice
database by hand, so the account has to come from the seed.

## The ask

The practice seed script, with and without `--force`, leaves the shared practice user holding one
active bank account with a fixed name (for example `Practice account`) that holds both `PEN`
and `USD`:

- If the account is missing, deleted or archived, the seed creates it again or unarchives it,
  so every reseed starts with it in place.
- If it is there and active, the seed leaves it and its transactions alone.
- Its name does not start with `contract-` or `freshman-`, the prefixes the client's tests and
  cleaner use for what they make and remove.
- The seed prints the account's id beside the user's key, so a check can name it.

## Done when

- After a reseed with `--force`, `GET /accounts` as the shared practice user lists the
  account, active, holding `PEN` and `USD`.
- Deleting or archiving it and reseeding brings it back; reseeding with it active changes
  nothing about it.

## What this client removes once it lands

The client's tester stops proving the account-picking screens against a fake engine only, and
checks them in the real app against the practice engine.
