# System categories and the pending hashtag can no longer be renamed

Shipped 2026-10-17 · ⚠️ breaking · contract `aa72f160099133ac` → `890453f80a08cec9`

Answers the TUI's ask of 2026-10-16 ("system rows keep their names"). It is live once the owner has applied the ledger update and the engine has restarted; until then the live contract does not show it.

## What changed

**Which rows:** the two system categories, `@Opening` (`system_key` `"opening_balance"`) and `@Pendiente` (`system_key` `"pending"`), and the built-in pending hashtag, `Pendiente` (`system_key` `"pending"`). Every other category and hashtag is unchanged.

**The refusal**
- `PUT /categories/{id}` on a system category and `PUT /hashtags/{id}` on the pending hashtag trim `name`, as on every name, and it must then be exactly the current name, character for character.
- Any other value is `422 VALIDATION_ERROR` on `name`, reason `SYSTEM_NAME_FIXED`, message `"Must be the current name: a system record keeps its name."`. Nothing is written.
- A change of letter case only is a rename and is refused: `"@pendiente"`, `"PENDIENTE"`.
- It answers before `RESERVED_NAME` and `NAME_EXISTS`: on these rows, a different name is always `SYSTEM_NAME_FIXED`. An empty name is still `EMPTY`, and on a category an invalid `color` is still refused first.

**What stays accepted**
- Sending the current name, or one that trims to it (`"  @Pendiente "`), is an ordinary update: `version` bumps and an `updated` activity entry is written, as for any field sent with its current value.
- On a system category, `color` and `sort_order` stay editable. On the pending hashtag, `sort_order` stays editable.
- Leaving `name` out works as before.
- `DELETE` on any of them is still `403` (`SYSTEM_CATEGORY` on `category_id`, `SYSTEM_HASHTAG` on `hashtag_id`), unchanged.
- The reserved-name rules for the user's own rows are unchanged: no user category may take `@Opening` or `@Pendiente`, and no user hashtag may take `Pendiente` (`422` on `name`, `RESERVED_NAME`).

**Existing data:** any system category or pending hashtag that had been renamed got its default name back, with one `updated` activity entry each recording the old name in its before snapshot. After the update every system category and the pending hashtag carry exactly `@Opening`, `@Pendiente` and `Pendiente`.

**Still the rule:** find these rows by `system_key`, never by name.

## What the TUI does

1. Don't offer a rename on a row whose `system_key` is not `null`, for categories and hashtags. Colour and order editing stay offered (order only, for the hashtag).
2. If the edit form always sends `name`, send the row's current name unchanged; that is accepted.
3. Handle `SYSTEM_NAME_FIXED` on `name` with its message, in case it comes back.
4. Drop any text or help that says these rows can be renamed or can take their default name back.

## Done when

- No TUI screen offers a rename on `@Opening`, `@Pendiente` or the pending hashtag.
- Editing a system row's colour or order still works.
- `SYSTEM_NAME_FIXED` has a handled path.
