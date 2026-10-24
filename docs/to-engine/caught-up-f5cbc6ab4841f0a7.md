# Caught up with contract `f5cbc6ab4841f0a7`: a line move answers with every part it changed

2026-10-24

## Covers

Contract `3eec27cc7b11e663` (exclusive) to `f5cbc6ab4841f0a7` (inclusive), all of the hand-off
"Changing a line field answers with every part it changed, and whether each left its
reconciliation" (shipped 2026-10-24). `f5cbc6ab4841f0a7` is the version to start the next
catch-up file from.

What the TUI does with it:

- The note after a bulk account move counts the distinct parts listed in `changed_parts`
  across the answers that landed, and the parts flagged `left_reconciliation`: moving one part
  of a 60 + 40 line out of a draft reconciliation says `2 rows → <account> · 2 left their
  reconciliation`. A move that changes nothing shows no note.
- The edit form's "Saved. It left its reconciliation." shows when the save's answer flags a
  part, and "Saved." otherwise.
- Nothing is read before or after a move to work out what it changed.
- The live contract suite pins your checks: one part of a 60 + 40 line moved out of a draft
  lists both parts, both flagged; the same `account_id` on the other part lists none; a
  one-part line lists itself, flagged only when it was assigned; a body of only `category_id`
  lists none and still bumps `version`; a replay under the same key answers the same.

## Done when, checked

Run against the practice engine on 2026-10-24, at contract `a1859d71873b8807`.

1. **The TUI holds contract `f5cbc6ab4841f0a7`:** not as written. By the time of the check the
   engine had moved to `a1859d71873b8807`, so the version check failed on the newer versions
   `0cd36b98415f5f0c`, `48d909f787839fa8` and `a1859d71873b8807`. The owner chose to close this
   catch-up on its own checks and catch up with those three from `f5cbc6ab4841f0a7` next. Every
   fixture field this client mocks is one you serve. The live suite passed 138 tests; the 8 that
   failed all send `statement_line` on a transaction write, which `0cd36b98415f5f0c` refuses with
   `UNKNOWN_FIELD`. This client's sheet import sends no `statement_line`: it sets no statement
   lines.
2. **Moving one part of a 60 + 40 line to another account, with `reconciliation_id: null`
   while the line is in a draft reconciliation, says 2 rows moved and 2 left their
   reconciliation:** worked. Live, the answer lists both parts with `left_reconciliation: true`;
   the TUI's note reads `2 rows → <account> · 2 left their reconciliation`.
3. **Selecting both parts of that line and moving them says 2 rows moved, not 3 or 4:**
   worked. Live, the second write's answer lists no parts; the TUI's note reads `2 rows`.
4. **Moving a one-part line in no reconciliation says nothing about leaving one:** worked.
   Live, the part lists itself with `left_reconciliation: false`; the note reads `1 row →
   <account>`.

The answers' shape and values were checked live; the TUI's notes were checked against answers
in that shape, not on screen against your engine.

## Contract problems found

None.

## Asks this closes

"Changing a line field answers with every part it moved and whether each left its
reconciliation" (raised 2026-10-23).
