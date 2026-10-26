# The sheet import marks the names only opening balances use

Raised 2026-10-26.

## Why

In the sheet import, a category or hashtag that only opening balances use needs no entry in the
table, since an opening balance takes neither (contract: POST /v1/transactions/import-sheet,
"Opening balances"). The answer's `names` lists those names like every other, with their rows
and proposal, and nothing tells them apart. On the owner's sheet that is the `SALDO INICIAL`
category, and any hashtag only those rows carry.

A client cannot tell which names they are without re-running the engine's opening-balance rule
itself (the category reads exactly `SALDO INICIAL`, a non-zero amount, an account that is not a
person, no earlier row of the same account), which is the engine's rule and would drift. So it
creates a `SALDO INICIAL` category, and such hashtags, that the import never uses, and cannot tell
the owner that the name goes nowhere.

## The ask

Each category and hashtag in the answer's `names` says whether only rows that are opening
balances use it, so a client can leave it out of the table and create nothing for it. Whether a
row is an opening balance depends on which account its name goes to; when that is not yet known
(a dry run without a table), the answer judges it as the dry run judges the rows (see the ask "The
sheet import's dry run counts the rows before every name has an id").

How it is shaped is the engine's call: a boolean per name (`only_opening_balances`), or a count of
the rows using it that are not opening balances, would both do.

## Done when

- The `SALDO INICIAL` category of a made-up sheet whose only `SALDO INICIAL` rows are opening
  balances is marked as used only by opening balances; one that an ordinary row also uses is not.
- The same holds for a hashtag only opening-balance rows carry.
- An apply whose table leaves out the marked names is accepted.

## What this client removes once it lands

The sheet import stops creating a category and hashtags no row uses, and its names table shows
such a name as going to opening balances only, instead of as a new name to create.
