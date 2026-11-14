# The sheet import's `create.accounts` takes an account's `color`, as `POST /accounts` does

Raised 2026-11-14

## Why

The sheet import's `create.accounts` entries are judged by `POST /accounts`'s rules, but they refuse `color` (`422`, `UNKNOWN_FIELD`), while `POST /accounts` takes it. A client that lets the owner set up each account before the one write can ask for every line of the New account form but its colour. The owner then has to open each account made by the import and set its colour one by one, about 18 accounts on the official import, which is the kind of second pass the one-write import exists to avoid.

## The ask

`create.accounts.<i>` takes the optional `color` exactly as `POST /accounts` does: the same values, the same refusals keyed `create.accounts.<i>.color`, left out meaning the same default. Nothing else in `create` changes.

## Done when

- An apply whose `create.accounts` entry carries a valid `color` makes the account with that colour.
- An invalid `color` there is refused with `POST /accounts`'s reason, keyed `create.accounts.<i>.color`, and nothing is made.
- An entry without `color` is made as today.

## What this client removes once it lands

The review's account form leaves out the colour line that the New account form has, so the owner sets each imported account's colour afterwards in its Edit form. Once this lands, the review's form holds the colour line too.
