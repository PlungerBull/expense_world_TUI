# Catch up with bank lines and splits

**Status: draft.** The loop starts on it when the owner approves the tasks below.
The engine change it catches up with:
[engine-answers/split-bank-lines.md](../engine-answers/split-bank-lines.md) (contract
`66d65a86a9cf1c19`). When done, the why moves to [decisions.md](../decisions.md), this file and
that answer are deleted, and so is the ask it answers,
[engine-asks/split-bank-lines-keep-one-identity.md](../engine-asks/split-bank-lines-keep-one-identity.md).

---

## What it must do

The app works with the engine's bank lines: one bank movement, held by one transaction or split
into several parts.

- **The bank upload works again on the new engine.** It shows which file rows the ledger
  already has, which are new, and which matched rows took the bank's description. The old "rows
  left over" view is replaced by the engine's list of days whose totals disagree between the file
  and the ledger: both totals, the file rows not found, and the ledger rows the file did not
  claim. When another change lands on a matched row while the upload runs, the screen says so
  and offers to run it again.
- **A row a day off is new.** Accepted by the owner (2026-10-16): a purchase the bank posts a day
  after it was typed is added again, and shows in the days that disagree.
- **Split a purchase.** On a transaction, a split action divides it into parts, each with its own
  amount, category, hashtags and note; the parts must add up to the purchase. The same action
  re-splits a split purchase, opening with its current parts. When the parts do not add up, the
  screen shows both totals as the engine gives them.
- **Split parts read as one purchase.** In the ledger, the parts of one purchase show together,
  under the purchase's description and total.
- **Editing a part says what it reaches.** Changing the description, date or account of a part
  changes every part of the purchase; the form says so before saving. A refusal names the part
  that caused it, shown as the engine sends it.
- No client-side matching, title comparison or neighbouring-day logic is left in the app; the
  engine decides every match.

Every one of these changes what a screen shows, so each is drawn as a mockup and picked by the
owner before it is built.

## How the owner knows it is done

1. A bank file uploaded twice on the practice engine shows every row as already in the ledger the
   second time, none new.
2. A purchase split into two parts, then the same bank file uploaded again: still nothing new,
   including a card purchase with no bank code.
3. The ledger shows the two parts together as one purchase, and re-splitting opens with them.
4. Changing a part's description changes both parts, and the form said so first.
5. An upload with a day that disagrees lists that day with both totals.

## Tasks

Draft, for the owner's approval. Each **[UI]** task starts with its mockup; the build waits for
the owner's pick.

1. The bank upload reads the new import answer: matched rows by bank line, `retitled` and its
   count, and no `adjacent_day`, `ledger_id` or `excess`. The live contract test and the unit
   fixtures follow, and the new contract version is recorded. Screens keep their current look
   where nothing new is shown.
2. **[UI]** The bank upload's days-that-disagree view, replacing the rows-left-over view, and
   the "changed while running, run it again" refusal.
3. **[UI]** The ledger shows the parts of one purchase together.
4. **[UI]** The split action: split, re-split, and the totals-don't-add-up refusal.
5. **[UI]** The edit form's note that description, date and account reach every part, and its
   refusal naming the part.
6. Live contract tests for split, re-split, a part edit reaching every part, and a split line
   matched on re-import.
