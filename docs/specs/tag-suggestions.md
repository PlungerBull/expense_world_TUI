# Tag suggestions that know the category

**Status: draft.** The owner reviews and completes this spec before the loop starts on it.
How it gets built: [category-hashtags-plan.md](../category-hashtags-plan.md). When done, the why
moves to [decisions.md](../decisions.md), and this file and the plan are deleted.
The engine side is live: the tags a category's transactions use, most-used first, the whole list
in one answer (contract: GET /v1/categories/{category_id}/hashtags).

---

## What it must do

- In the LOG bar, once a category is typed, `#` lists **that category's tags first**, most-used
  first, then a dim divider, then **every other tag**, A–Z. No tag is ever hidden (mockup pane D, approved 2026-09-30,
  [expense-world-log-legend-and-picker.html](../mockups/expense-world-log-legend-and-picker.html)).
- With no category, an unclear one, a category never tagged before, or while the list is still
  loading, `#` shows the same list as today.
- Any tag can still be typed and saved with any category, even one never used with it before.
- A deleted transaction no longer counts as using its tags.
- Only the LOG bar orders tags this way. Bulk tagging (`h`) and the edit form keep today's list.
- The suggestion list shows no usage counts.
- A typed command, `expense categories hashtags <category-id>`, lists the names of the tags a
  category has used, most-used first; `--json` gives the engine's answer as is.

## How the owner knows it is done

1. In `expense world`, `+`, type `farmacia -28.90 $<account> @SALUD #`: the tags used with
   `@SALUD` come first, then the divider, then all other tags.
2. Pick a tag never used with `@SALUD` from below the divider and save: the row saves.
3. Do the same with a category that has never been tagged: the list looks exactly as before.
4. `expense categories hashtags <SALUD's id>` prints the tag names, most-used first.

## Tasks

Draft, for the owner's approval.

1. The typed command (one column, Name) and the shared fetch it uses.
2. The LOG bar ordering: fetch once per category, keep it for the screen's life, fall back to
   today's list whenever the category's list is missing.
