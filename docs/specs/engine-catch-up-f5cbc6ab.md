# Catch up with contract f5cbc6ab4841f0a7: a move says which rows it moved

**Catches up to contract `9dd1358d455f9e47` → `f5cbc6ab4841f0a7`** (from `3eec27cc7b11e663`).
**Status: drafted by the orchestrator on 2026-10-24 from the engine's hand-off of that day; the
owner approved the tasks on 2026-10-24.** The owner picked catching up next (2026-10-24). When
done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## What it must do

A write that changes a transaction's account, date, title, operation or reconciliation reaches
every part of its bank line. The engine now answers with each part the write changed and whether
it left its reconciliation (contract: PUT /v1/transactions/{transaction_id}, "Response"). The
app's notes count what the engine says moved, never the requests sent.

1. **The note after `b` counts the rows that moved.** Moving one part of a 60 + 40 transaction
   out of a draft reconciliation says `2 rows → <account> · 2 left their reconciliation`.
   Selecting both parts and moving them says `2 rows`, not 3 or 4. A one-part transaction in no
   reconciliation says nothing about leaving one.
2. **The Edit form's "Saved. It left its reconciliation."** shows when the engine says a part
   left its reconciliation, not from the list read before the save.
3. **No second read of the line** is made to learn what a move changed.

## How the owner knows it is done

The engine's "Done when", checked against the practice engine:

1. The drift script's version check passes, with the engine's current version recorded when the
   spec closes: the engine is past `f5cbc6ab4841f0a7` (at `a1859d71873b8807` on 2026-10-24), and
   the owner chose on 2026-10-24 to close this spec on its own checks, with every newer version
   caught up by the next catch-up spec (from `f5cbc6ab4841f0a7`). Live contract tests that fail only because a write no longer takes
   `statement_line` belong to that spec, not this one.
2. Moving one part of a 60 + 40 line to another account, with `reconciliation_id: null` while
   the line is in a draft reconciliation, says `2 rows` moved and `2 left their reconciliation`.
3. Selecting both parts of that line and moving them says `2 rows` moved, not 3 or 4.
4. Moving a one-part line in no reconciliation says nothing about leaving one.

What the engine did differently from the ask: `left_reconciliation` is a flag, not the part's
reconciliation before and after. A body changing only amount, category, note or hashtags lists
no part, not even the one named.

---

## Tasks

Drafted by the orchestrator; approved by the owner on 2026-10-24.

3. **The Edit form reads `left_reconciliation`.** In
   [edit_form.py](../../expense/tui/screens/edit_form.py). Passes if: a unit test shows "Saved.
   It left its reconciliation." when the answer flags a part, and "Saved." when `changed_parts`
   is `[]` or flags none; the old before-the-save check is gone.

---

## Reply to the engine

- **Covers:** contract `3eec27cc7b11e663` → `f5cbc6ab4841f0a7`, the hand-off "Changing a line
  field answers with every part it changed, and whether each left its reconciliation" (shipped
  2026-10-24).
- **Done when, to report on:** the engine's four checks, as under "How the owner knows it is
  done" above, each worked or what happened instead, with the tester's evidence.
- **Contract problems found:** from the tester's and builders' reports; "none" when none.
- **Asks this closes:** "Changing a line field answers with every part it moved and whether each
  left its reconciliation" (raised 2026-10-23).
