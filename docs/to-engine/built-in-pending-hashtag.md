# A built-in `#Pendiente` hashtag that every row with no hashtag lands on, as `@Pendiente` does for categories

Raised 2026-10-15.

## Why

The owner classifies every transaction twice: a category and a hashtag. "Not classified yet" has
to be visible on both. The engine already handles the category side: `@Pendiente` is a built-in
category, and a row written with no category is filed under it. The hashtag side has nothing, so
a row with no hashtag is just untagged. That makes "what still needs a hashtag" a different
question from "what still needs a category", and every client has to work it out on its own.

## The ask

1. **A built-in pending hashtag**, made for every user the way `@Pendiente` is: a stable system
   key so clients find it without matching its name, its display name `Pendiente`, and the same
   protection as the built-in category (renamable like it, never deleted).
2. **A row written with no hashtag gets the pending hashtag**: on create, on import, and on an
   edit that removes the row's last hashtag. A row then always has at least one hashtag.
3. **Giving a row a real hashtag takes the pending one off**, the way setting a category moves a
   row out of `@Pendiente`.
4. **Existing rows with no hashtag** get the pending hashtag when this lands.
5. Hashtag lists and filters treat it like any other hashtag, so "rows still pending a hashtag"
   is an ordinary hashtag filter.

## Done when

- A new user has the pending hashtag, with its system key, next to `@Pendiente`.
- A transaction created, imported or edited with no hashtag comes back carrying the pending
  hashtag.
- Adding a real hashtag to a pending row leaves only the real one.
- The pending hashtag cannot be deleted; the refusal is a structured error.
- No row in the ledger is left without a hashtag.

## What this client removes once it lands

Nothing yet: this client has no pending hashtag of its own. Once it lands, the spreadsheet
import sends a `PENDIENTES` hashtag to the pending hashtag by its system key, the way it sends a
`PENDIENTES` category to `@Pendiente`.
