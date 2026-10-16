# The built-in categories and the built-in pending hashtag cannot be renamed

Raised 2026-10-16.

## Why

The owner's rule: the built-in rows are system values, so they keep the names the engine gives
them. Today the engine refuses to delete them but lets any client rename them: the `@Pendiente`
and `@Opening` categories, and the pending hashtag `Pendiente` (contract: `PUT
/categories/{id}` "system categories may be renamed"; `PUT /hashtags/{id}` "The pending hashtag
may be renamed"). A renamed `@Pendiente` or `#Pendiente` no longer reads as "not classified yet"
on any screen of any client, and the owner's spreadsheet import, which maps `PENDIENTE` onto
these rows, then lands rows on a name the owner no longer recognises.

If only one client hid the rename, the others would still offer it, so the rule belongs in the
engine.

## The ask

1. **`PUT /categories/{id}` on a system category refuses a `name` that differs from its
   current one**, with a structured `422` on `name` (a reason such as `SYSTEM_NAME_FIXED`), and
   writes nothing. Its other fields (colour, order) stay editable as today, unless the engine
   coders see a reason to lock them too.
2. **`PUT /hashtags/{id}` on the pending hashtag refuses a `name` change the same way.** Its
   `sort_order` stays editable.
3. **Rows already renamed get their default name back** in the same change: `@Pendiente`,
   `@Opening`, and `Pendiente` for the hashtag. If a user row already holds that name, say what
   the engine does instead (the reserved-name rules already keep new user rows off these names).
4. Delete stays refused as today (`SYSTEM_CATEGORY`, `SYSTEM_HASHTAG`).

## Done when

- Renaming `@Pendiente`, `@Opening` or the pending hashtag is `422` on `name` with the new
  reason, and nothing is written.
- Sending the current name unchanged, or changing only colour or order, is accepted.
- After the change, every user's system rows carry their default names.

## What this client removes once it lands

The client stops offering rename on the built-in rows of the categories and hashtags screens and
shows the new refusal as the engine sends it. Until it lands, the client still offers the
rename, so the rule is not half-enforced in one client only.
