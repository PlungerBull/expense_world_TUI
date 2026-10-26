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

1. **A unit test proves the Edit form shows the engine's words alone for a held reserved
   name** (point 1). Passes if a unit test on the Edit form has the fake engine refuse the
   whole-line write (`PUT /bank-lines/{id}`) with `409` `RESERVED_NAME_HELD` keyed
   `hashtag_ids` itself (contract: "Hashtags"), and proves that the form stays open, shows the
   engine's words whole with no line of the app's under them (not the category line), says
   nothing was saved, and sent exactly that one write; the test fails if the category line
   shows; and the unit suite passes.
2. **The two test comments say what their case proves** (point 3). Passes if the comments in
   test_tui_edit_form_parts.py and test_errors.py no longer name "edit-form-words-and-keys 3 A"
   and instead say what the case proves (a part's `parts.<i>.hashtag_ids` refusal shows the
   engine's words alone), no other pick tag is added, and what the tests check is unchanged.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **Live tests draw a held reserved name** (this spec's point 2, widened to every route that
  answers it): once the engine ships the ask "The practice engine seeds a second practice user
  whose own category and hashtag hold the reserved names", live tests run as that user prove
  that `PUT /bank-lines/{id}` with `parts`, and the other transaction routes, send
  `RESERVED_NAME_HELD` on `hashtag_ids` or `category_id` and write nothing.
