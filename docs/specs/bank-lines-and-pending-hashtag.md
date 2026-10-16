# Catch up with bank lines, splits and the pending hashtag

**Status: approved by the owner (2026-10-16); the loop runs on it.**
The engine change it catches up with:
[engine-answers/bank-lines-and-pending-hashtag.md](../engine-answers/bank-lines-and-pending-hashtag.md),
every contract change from `42d70a629215928d` to `3129bfa2c43a4446`. When done, the why moves to
[decisions.md](../decisions.md), and this file, that answer and the two asks it answers are
deleted: [engine-asks/split-bank-lines-keep-one-identity.md](../engine-asks/split-bank-lines-keep-one-identity.md)
and [engine-asks/built-in-pending-hashtag.md](../engine-asks/built-in-pending-hashtag.md).

---

## What it must do

The app works with the engine's bank lines (one bank movement, held by one transaction or split
into several parts) and with the built-in pending hashtag (where every transaction with no
hashtag lands).

**Bank lines and splits**

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
- **The spreadsheet import does not group split rows.** The sheet comes in as it is, one
  transaction per row (owner, 2026-10-16), so the engine's grouped batch (`line_group`) is not
  used yet.

**The pending hashtag**

- **"Needs a hashtag" is the pending hashtag.** Home's hashtag rows show it like any other
  hashtag, under its current name, and `⏎` on it lists exactly the transactions still waiting for
  a hashtag. The "(no hashtags)" row is gone.
- **Tagging a pending transaction leaves only the real hashtag.** Every screen that sets
  hashtags sends only the real ones.
- **The built-in rows keep their names (owner, 2026-10-16).** The pending hashtag, `@Pendiente`
  and `@Opening` are system values: no screen offers to delete or rename them, and a user
  hashtag cannot be named `Pendiente`. Refusals show as the engine sends them. Renaming is
  refused by the engine once
  [engine-asks/system-rows-keep-their-names.md](../engine-asks/system-rows-keep-their-names.md)
  lands; until then the rename stays offered.
- **An opening balance carries no hashtag.** Its edit form offers no hashtag change.

No client-side matching, title comparison, neighbouring-day logic or "untagged" computing is
left in the app; the engine decides.

Every one of these that changes what a screen shows is drawn as a mockup and picked by the owner
before it is built.

## How the owner knows it is done

1. A bank file uploaded twice on the practice engine shows every row as already in the ledger the
   second time, none new.
2. A purchase split into two parts, then the same bank file uploaded again: still nothing new,
   including a card purchase with no bank code.
3. The ledger shows the two parts together as one purchase, and re-splitting opens with them.
4. Changing a part's description changes both parts, and the form said so first.
5. An upload with a day that disagrees lists that day with both totals.
6. A transaction logged with no hashtag shows the pending hashtag; tagging it leaves only the
   real one, and Home's pending row lists it until then.
7. Deleting or renaming the pending hashtag, `@Pendiente` or `@Opening` is not offered.

## Tasks

Approved by the owner (2026-10-16). Each **[UI]** task starts with its mockup; the build waits for
the owner's pick. Tasks 1, 2 and 9 are done; the live contract tests cover every new refusal
reason except `SPLIT_LINE_PARTS_DIVERGE`, which no current route can produce.

3. **[UI]** The bank upload's days-that-disagree view, replacing the rows-left-over view; the
   matched rows that took the bank's description, and their count; and the "changed while
   running, run it again" refusal. The upload's summary reads the engine's `counts` instead of
   counting rows itself.
4. **[UI]** The ledger shows the parts of one purchase together.
5. **[UI]** The split action: split, re-split, and the totals-don't-add-up refusal.
6. **[UI]** The edit form's note that description, date and account reach every part, and its
   refusal naming the part.
7. **[UI]** The pending hashtag on Home: its row under its current name, `⏎` listing the
   transactions still waiting for a hashtag, and no "(no hashtags)" row. The mockup also shows
   the edit form and the LOG bar's staged line when the owner names a real hashtag on a pending
   row: the save sends only the real one, and the screen today still lists both.
8. **[UI]** The hashtags screen marks the pending hashtag and offers no delete or rename on it,
   and the categories screen offers no rename on `@Pendiente` and `@Opening`, with the
   `SYSTEM_HASHTAG`, `RESERVED_NAME` and the engine's new rename refusals (the rename part waits
   on [engine-asks/system-rows-keep-their-names.md](../engine-asks/system-rows-keep-their-names.md)); the
   categories legend and the `SYSTEM_CATEGORY` hint, which say system categories can be renamed,
   take the picked wording); an opening balance's edit form offers no
   hashtag change, with the `OPENING_BALANCE_NOT_TAGGED` refusal.
