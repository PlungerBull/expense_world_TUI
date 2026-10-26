# A held reserved name is proven on the Edit form

**Status: the current spec, approved with its tasks on 2026-10-25.** When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

When one of your categories has a built-in category's name, the engine refuses a hashtag change
with `RESERVED_NAME_HELD`. On a hashtag change the app adds no line of its own, since the
engine's words already say what to do. The engine sends this refusal on the transaction's
hashtags as a whole, never on one part's (contract: "Hashtags"), so the Edit form shows the
engine's words alone, as [tui.md](../tui.md) says. No test proves it: not the Edit form's unit
tests, and not the live contract suite for the whole-line write.

Two test comments also name the retired spec's pick ("edit-form-words-and-keys 3 A"), in
[test_tui_edit_form_parts.py](../../tests/unit/test_tui_edit_form_parts.py) and
[test_errors.py](../../tests/unit/test_errors.py); they should say what the case proves.

## What it must do

1. **A unit test proves the Edit form shows the engine's words alone** for `RESERVED_NAME_HELD`.
2. **A live contract test proves the whole-line write sends it on `hashtag_ids`**, and writes
   nothing.
3. **The two test comments say what their case proves**, not which pick it came from.

## How the owner knows it is done

1. The new tests pass, live against the practice engine and in the unit suite.
2. Nothing you see in the app changes.

## Questions for the owner

None.

---

## Tasks

Approved by the owner on 2026-10-25. One task at a time, in this order; each says what it must
do and when it passes. Point 2 is not built in this spec: the practice user cannot reach a held
reserved name, because its pending hashtag already exists and can never be deleted, and no
hashtag of the user's may take the name `Pendiente` (contract: "Hashtags"). The owner chose on
2026-10-25 to ask the engine for a practice user that can, and to finish this spec without the
live test; the ask is "The practice engine seeds a second practice user whose own category and
hashtag hold the reserved names", and the live test waits under "Found along the way".

Every task is done; the acceptance check and the librarian's sweep follow.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **Live tests draw a held reserved name** (this spec's point 2, widened to every route that
  answers it): once the engine ships the ask "The practice engine seeds a second practice user
  whose own category and hashtag hold the reserved names", live tests run as that user prove
  that `PUT /bank-lines/{id}` with `parts`, and the other transaction routes, send
  `RESERVED_NAME_HELD` on `hashtag_ids` or `category_id` and write nothing.
- **Four more test comments name a retired spec's pick.** In test_errors.py, the comments
  heading the refusal rows still say "pending-hashtag-manage 4 B, both refusals, and 5 B",
  "pending-hashtag-manage 7 B", "archived-account 3 A" and "account-to-person 4 B"; each should
  say what its rows prove instead.
- **The Edit form's shared hashtag-refusal test proves less than it says.**
  `test_a_hashtag_refusal_shows_under_the_parts_as_sent` in test_tui_edit_form.py runs every
  hashtag refusal, `RESERVED_NAME_HELD` among them, but when a reason has no line of the app's
  it checks nothing, so it would pass with one showing; it also checks neither "Nothing was
  saved." nor that one write was sent.
