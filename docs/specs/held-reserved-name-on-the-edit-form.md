# A held reserved name is proven on the Edit form

**Status: drafted by the orchestrator on 2026-10-25 from what the spec "The Edit form's words
and keys match what it does" found along the way; waiting on the owner to rewrite or approve
it.** When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

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

Drafted once the owner approves the spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
