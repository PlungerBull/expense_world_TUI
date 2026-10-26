# A held reserved name is proven live, and the refusal tests say what they prove

**Status: draft, for the owner to rewrite or approve. Its tasks are drafted when the owner names
it the current spec.** When done, the why moves to [decisions.md](../decisions.md) and this file
is deleted.

---

## Why

When one of your categories or hashtags has a built-in name, the engine refuses a write that
would file a transaction under the built-in one, with `RESERVED_NAME_HELD` on `hashtag_ids`
(contract: "Hashtags") or on `category_id` (contract: POST /v1/categories, "Reserved names").
A unit test now proves the Edit form shows the engine's words alone for it, but no live test
proves the engine sends it: the practice user cannot reach
that state, because its pending hashtag already exists and can never be deleted. The ask "The
practice engine seeds a second practice user whose own category and hashtag hold the reserved
names" gives the live tests a user that can; the owner handed it over on 2026-10-26, and on
2026-10-26 the practice engine's reseed already prints that user and its key
(`EXPENSE_RESERVED_PAT`).

The same work found two weaker spots in the unit tests: comments that name a retired spec's
pick instead of what their rows prove, and a shared Edit form test that checks less than its
name says.

## What it must do

1. **Live tests prove the engine refuses a write on a held reserved name.** Run as the second
   practice user, they prove that `PUT /bank-lines/{id}` with `parts`, and every other
   transaction route that answers `RESERVED_NAME_HELD`, sends it on `hashtag_ids` or
   `category_id` and writes nothing.
2. **Four test comments say what their rows prove.** In
   [test_errors.py](../../tests/unit/test_errors.py), the comments heading the refusal rows
   say "pending-hashtag-manage 4 B, both refusals, and 5 B", "pending-hashtag-manage 7 B",
   "archived-account 3 A" and "account-to-person 4 B"; each says what its rows prove instead.
3. **The Edit form's shared hashtag-refusal test checks what it says.**
   `test_a_hashtag_refusal_shows_under_the_parts_as_sent` in
   [test_tui_edit_form.py](../../tests/unit/test_tui_edit_form.py) runs every hashtag refusal,
   `RESERVED_NAME_HELD` among them, but when a reason has no line of the app's it checks
   nothing, so it would pass with one showing. It proves no line of the app's shows for those
   reasons, and for every reason that "Nothing was saved." shows and one write was sent.

## How the owner knows it is done

1. The new live tests pass against the practice engine, and the unit suite passes.
2. Nothing you see in the app changes.

## Questions for the owner

None.
