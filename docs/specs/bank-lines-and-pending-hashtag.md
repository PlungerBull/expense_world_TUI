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
- **Split parts read as one purchase (owner, 2026-10-17).** In the ledger, a split purchase is
  one line with its title and total and a mark that it is split; its parts show when it is
  opened. A ledger filtered from Home shows each part as its own row.
- **Editing a part says what it reaches.** Changing the title, date or account of a part
  changes every part of the purchase; the form says so before saving.
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
3. The ledger shows the two parts as one purchase line, opening it shows both, and re-splitting
   opens with them.
4. Changing a part's description changes both parts, and the form said so first.
5. An upload with a day that disagrees lists that day with both totals.
6. A transaction logged with no hashtag shows the pending hashtag; tagging it leaves only the
   real one, and Home's pending row lists it until then.
7. Deleting or renaming the pending hashtag, `@Pendiente` or `@Opening` is not offered.

## Tasks

Approved by the owner (2026-10-16). Each **[UI]** task starts with its mockup; the build waits for
the owner's pick. Tasks 1, 2 and 9 are done; the live contract tests cover every new refusal
reason except `SPLIT_LINE_PARTS_DIVERGE`, which no current route can produce.

Engine asks this spec waits on; each task below that needs one waits for its hand-off file and
its contract version, and is built against the live contract, not the ask. Accepted by the engine
coders on 2026-10-16:
[engine-asks/read-a-bank-line.md](../engine-asks/read-a-bank-line.md) (tasks 4–6; its first half
is in contract `c572d3a5f4f509d1`),
[engine-asks/day-mismatch-lines-carry-what-they-are.md](../engine-asks/day-mismatch-lines-carry-what-they-are.md)
(task 3's ledger rows the file did not claim; it removes `transaction_ids` from those entries,
which the upload reads today) and
[engine-asks/system-rows-keep-their-names.md](../engine-asks/system-rows-keep-their-names.md)
(task 8's rename part). Raised on 2026-10-17, for the owner to hand over:
[engine-asks/list-the-ledger-by-bank-line.md](../engine-asks/list-the-ledger-by-bank-line.md)
(task 4), [engine-asks/delete-a-bank-line.md](../engine-asks/delete-a-bank-line.md) (task 4's
`d`) and [engine-asks/reconcile-a-bank-line-whole.md](../engine-asks/reconcile-a-bank-line-whole.md)
(task 6, and the reconciliation screen ticking a purchase whole).

Owner's picks of 2026-10-17 are noted on each task; a task builds once every pick it needs is
in and its engine change has landed.

3. **[UI]** The bank upload's days-that-disagree view, replacing the rows-left-over view; the
   matched rows that took the bank's description, and their count; and the "changed while
   running, run it again" refusal. The upload's summary reads the engine's `counts` instead of
   counting rows itself. Picked: 1 A, 4 A; 2 A to confirm; the after-import table still to pick.
4. **[UI]** The ledger shows a split purchase as one line, its parts inside. Picked: 2 A (a
   filtered ledger shows each part as its own row); `d` on a split purchase deletes the whole
   purchase; the mark, what `⏎` opens, and `c`, `h` with a split purchase selected still to pick.
5. **[UI]** The split action: split, re-split, and the totals-don't-add-up refusal. Picked: 2 B
   (one typed line per part); 3 follows the ledger's pick; whether the screen stops `^s` until
   nothing is left still to answer.
6. **[UI]** The edit form's note that title, date and account reach every part. Picked: 1 B (the
   note in the hint, only on date, title and account). Screen 2, a refusal caused by another
   part, is not built: a purchase is reconciled whole (owner, 2026-10-17), which
   [engine-asks/reconcile-a-bank-line-whole.md](../engine-asks/reconcile-a-bank-line-whole.md)
   asks the engine to enforce.
7. **[UI]** The pending hashtag on Home: its row under its current name, `⏎` listing the
   transactions still waiting for a hashtag, and no "(no hashtags)" row; the edit form and the
   LOG bar send only the real hashtag. Picked: 1 A, 2 A, 3 A, 4 A, 5 B (a LOG bar line with no
   hashtag stages `#Pendiente`, like the category column).
8. **[UI]** The hashtags screen as a table with a System column, marking the pending hashtag and
   offering no delete or rename on it; the categories screen offers no edit and no delete on
   `@Pendiente` and `@Opening`, with the `SYSTEM_HASHTAG`, `RESERVED_NAME` and the engine's new
   rename refusals (the rename part waits on
   [engine-asks/system-rows-keep-their-names.md](../engine-asks/system-rows-keep-their-names.md));
   the categories legend and the `SYSTEM_CATEGORY` hint read "System categories cannot be
   renamed or deleted."; deleting an ordinary hashtag says where its rows go; an opening
   balance's edit form offers no hashtag change, with the `OPENING_BALANCE_NOT_TAGGED` refusal.
   Picked: 2 A, 3 B, 4 B and B, 5 B, 6 A, 7 B; the Hashtags table still to approve.
