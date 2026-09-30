# Tag suggestions that know the category

**Status: draft.** The owner reviews and completes this spec before the loop starts on it.
How it gets built: [category-hashtags-plan.md](../category-hashtags-plan.md). When done, the why
moves to [decisions.md](../decisions.md), and this file and the plan are deleted.

---

## What it must do

- In the LOG bar, once a category is typed, `#` lists **that category's tags first**, most-used
  first, then a dim divider, then **every other tag**, A–Z. No tag is ever hidden (mockup pane D,
  [expense-world-log-legend-and-picker.html](../mockups/expense-world-log-legend-and-picker.html) §3).
- With no category, an unclear one, a category never tagged before, or while the list is still
  loading, `#` shows the same list as today.
- Any tag can still be typed and saved with any category, even one never used with it before.
- A deleted transaction no longer counts as using its tags.
- Only the LOG bar orders tags this way. Bulk tagging (`h`) and the edit form keep today's list.
- The suggestion list shows no usage counts.
- A typed command, `expense categories hashtags <category-id>`, lists the tags a category has used,
  with how often; `--json` gives the engine's answer as is.

## How the owner knows it is done

1. In `expense world`, `+`, type `farmacia -28.90 $<account> @SALUD #`: the tags used with
   `@SALUD` come first, then the divider, then all other tags.
2. Pick a tag never used with `@SALUD` from below the divider and save: the row saves.
3. Do the same with a category that has never been tagged: the list looks exactly as before.
4. `expense categories hashtags <SALUD's id>` prints the table picked below.

## Open questions for the owner

### Which columns does the typed command show?
Asked 2026-09-29
| Name | Uses | Id |
|---|---|---|
| ALQUILER | 142 | 3f9c… |
| LUZ | 25 | 81ab… |
- **A.** These three.
- **B.** Other columns. Say which.

**Recommended:** A. It is everything the engine returns.

## Tasks

Draft, for the owner's approval.

1. Re-show mockup pane D; the owner confirms it (**[UI] gate**).
2. The typed command and the shared fetch it uses, with the picked columns.
3. The LOG bar ordering: fetch once per category, keep it for the screen's life, fall back to
   today's list whenever the category's list is missing.
4. A contract test against the practice engine: nothing calls this endpoint yet.
