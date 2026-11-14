# The sheet import says which names only opening balances use, so a client never makes a category or hashtag no transaction needs

Raised 2026-11-14

## Why

The contract's *Names* part for `POST /transactions/import-sheet` says a category or hashtag that only opening balances use needs no entry in the table. But the answer's `names.categories` and `names.hashtags` still list such a name like any other: on a dry run where only a `SALDO INICIAL` row uses the category `SALDO INICIAL`, it comes back as `{"name": "SALDO INICIAL", "rows": 1, "proposed_id": null}`. Nothing in the entry says that no transaction will carry it.

A client that makes every listed name the caller lacks, through `create`, therefore makes a `SALDO INICIAL` category (and any hashtag only those rows use) that no transaction ever holds. On the owner's official import into an empty ledger, that is a stray category in the real ledger from the first day. The only way a client could leave it out today is to re-implement the opening-balance rule (the first `SALDO INICIAL` row of each account and currency), which is the engine's.

## The ask

Either of these, whichever fits the contract better:

- **Leave such names out** of `names.categories` and `names.hashtags`: a name only opening balances use is not listed, since it needs no id.
- **Or mark them:** each entry of `names.categories` and `names.hashtags` carries a field, always present, saying the name is used only by opening balances (for example `"only_opening_balances": true`), and the contract says such a name needs no entry in the table and is not to be sent in `create`.

The answer's counts and rows stay as they are.

## Done when

- A dry run of a sheet whose `SALDO INICIAL` rows are all opening balances, with `SALDO INICIAL` as their category, either lists no `SALDO INICIAL` category or lists it marked as used only by opening balances.
- A category used by an opening balance and by an ordinary row is listed, unmarked, as today.
- The apply with a table and a `create` that leave that name out imports every row, the opening balances included.

## What this client removes once it lands

The review lists, and offers to make, every category and hashtag the dry run names, so the official import would make a `SALDO INICIAL` category no transaction uses, for the owner to delete by hand afterwards. Once this lands, the review leaves out what the engine leaves out or marks, and nothing is made that the ledger does not need.
