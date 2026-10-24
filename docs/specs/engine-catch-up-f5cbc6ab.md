# Catch up with contract f5cbc6ab4841f0a7: a move says which rows it moved

**Catches up to contract `9dd1358d455f9e47` → `f5cbc6ab4841f0a7`** (from `3eec27cc7b11e663`).
**Status: drafted by the orchestrator on 2026-10-24 from the engine's hand-off of that day; the
tasks wait for the owner's approval.** The owner picked catching up next (2026-10-24). When
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

1. The app holds contract `f5cbc6ab4841f0a7`: the drift script's version check passes.
2. Moving one part of a 60 + 40 line to another account, with `reconciliation_id: null` while
   the line is in a draft reconciliation, says `2 rows` moved and `2 left their reconciliation`.
3. Selecting both parts of that line and moving them says `2 rows` moved, not 3 or 4.
4. Moving a one-part line in no reconciliation says nothing about leaving one.

What the engine did differently from the ask: `left_reconciliation` is a flag, not the part's
reconciliation before and after. A body changing only amount, category, note or hashtags lists
no part, not even the one named.

---

## Tasks

Drafted by the orchestrator; waiting for the owner's approval.

1. **Read `changed_parts` and record the contract.** The unit fixtures of `PUT
   /v1/transactions/{id}` answers carry `changed_parts`. A live contract test covers the
   engine's checks: one part of a 60 + 40 line moved out of a draft lists both parts with
   `left_reconciliation: true`; the same `account_id` on the other part lists none; a one-part
   line lists itself, flagged only when it was assigned; only `category_id` lists none; a replay
   answers the same (compare the parsed JSON). The new version is recorded with `--record-version`.
   Passes if: the drift script exits clean against `:8002`; the new live tests pass there; the
   unit suite passes.
2. **The note after `b` counts `changed_parts`.** In
   [transactions.py](../../expense/tui/screens/transactions.py) (`bulk_receipt` and its caller).
   The row count is the number of distinct parts listed across the answers, and the "left" count
   is the parts listed with `left_reconciliation: true`. Nothing is read before the move to work
   it out. Passes if: unit tests with real key presses show the spec's three cases (one part of
   60 + 40 → `2 rows … · 2 left their reconciliation`; both parts selected → `2 rows`; a one-part
   line in no reconciliation → no "left"); no read of the line or the list is made to count.
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
