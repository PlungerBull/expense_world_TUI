# Catch up with bank lines, splits and the pending hashtag

**Status: approved by the owner (2026-10-16); the loop runs on it.**
**Catches up to contract `890453f80a08cec9`:** every contract change after `42d70a629215928d`.
It holds the engine's two hand-offs for that range, "Bank lines and splits keep one identity
across re-imports, and every transaction now carries at least one hashtag" (up to
`3129bfa2c43a4446`) and "A bank line can be read, the import's mismatched days show what each
unclaimed line is, and system rows keep their names" (up to `890453f80a08cec9`): what they ask of
this client is in the tasks, their checks in "The engine's checks", and what the engine declined
in "What the engine declined". When done, the why moves to [decisions.md](../decisions.md), where
it replaces "Manage detail: system categories are editable, not immutable", and this file is
deleted.

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
  claim, each part as its own row; a day is listed even when its totals agree if it holds such a
  row. The upload removes nothing and asks nothing about them: they stay out of that month's
  reconciliation, and the owner deletes them there (owner, 2026-10-17). When another
  change lands on a matched row while the upload runs, the screen says so and offers to run it
  again.
- **A row a day off is new.** Accepted by the owner (2026-10-16): a purchase the bank posts a day
  after it was typed is added again, and shows in the days that disagree.
- **Split a purchase.** On a transaction, a split action divides it into parts, each with its own
  amount, category, hashtags and note; the parts must add up to the purchase. The same action
  re-splits a split purchase, opening with its current parts. When the parts do not add up, the
  screen shows both totals as the engine gives them.
- **Each part is its own ledger row (owner, 2026-10-17).** The ledger, whole or filtered from
  Home, shows every part of a split purchase as an ordinary row: the purchase's title, its own
  amount, category, hashtags and note. A category or hashtag change reaches only the parts
  selected; only the bank's fields (title, date, account, bank code) belong to every part.
- **Editing a part says what it reaches.** Changing the title, date or account of a part of a
  split purchase changes every part of it; the form says so before saving.
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
  hashtag cannot be named `Pendiente`. The engine refuses a rename too; refusals show as the
  engine sends them.
- **An opening balance carries no hashtag.** Its edit form offers no hashtag change.

No client-side matching, title comparison, neighbouring-day logic, "untagged" computing or
adding up of a purchase's parts is left in the app; the engine decides.

Every one of these that changes what a screen shows is drawn as a mockup and picked by the owner
before it is built.

## How the owner knows it is done

1. A bank file uploaded twice on the practice engine shows every row as already in the ledger the
   second time, none new.
2. A purchase split into two parts, then the same bank file uploaded again: still nothing new,
   including a card purchase with no bank code.
3. The ledger shows the two parts as two rows; `c` on one of them changes only that part, and
   re-splitting either opens with both.
4. Changing a part's description changes both parts, and the form said so first.
5. An upload with a day that disagrees lists that day with both totals.
6. A transaction logged with no hashtag shows the pending hashtag; tagging it leaves only the
   real one, and Home's pending row lists it until then.
7. Deleting or renaming the pending hashtag, `@Pendiente` or `@Opening` is not offered.
8. An upload with a day whose totals agree but which holds a ledger purchase the file did not
   claim lists that day and that purchase, each part as its own row, and changes nothing.

## The engine's checks

The engine's own "Done when" for this range. The tester's acceptance check runs each one, and
the reply to the engine reports each result.

1. The app splits a transaction, re-splits a line and edits a part through the split and edit
   routes.
2. A statement imported, split, and imported again shows every row as matched and nothing new,
   including a card line with no operation code.
3. A grouped batch creates one line, and a later import of the bank's row matches it. The sheet
   import does not group (owner, 2026-10-16), so the live contract suite is what proves it.
4. The upload reads `bank_line_id`, `retitled` and `day_mismatches`, and no longer reads
   `ledger_id`, `excess` or `adjacent_day`.
5. The upload draws each unclaimed line from `parts` and `net_cents`, with no read of
   `transaction_ids` and no read per transaction; a day with equal totals but an unclaimed line
   shows that line.
6. The pending hashtag is found by `system_key`; "needs a hashtag" lists through `?hashtag_id=`
   and shows the same count as `/transactions/count`.
7. A transaction created with no hashtag shows the pending one; tagging it with a real hashtag
   leaves only the real one. No client code computes or shows an empty hashtag row in reports.
8. Re-split and the "reaches every part" note read `GET /bank-lines/{id}` and `?bank_line_id=`;
   the app adds no amounts of its own.
9. No screen offers a rename on `@Opening`, `@Pendiente` or the pending hashtag. The engine keeps
   their colour and order editable; Manage offers no edit on the system categories (task 8), so
   the live contract suite is what proves the engine accepts it.
10. Each new reason has a handled path: `SPLIT_TOTAL_MISMATCH`, `SPLIT_RECONCILIATION_MIXED`,
    `SPLIT_LINE_PARTS_DIVERGE`, `OPENING_BALANCE_NOT_SPLIT`, `LINE_GROUP_FIELDS_DIFFER`,
    `PENDING_HASHTAG_NOT_ALONE`, `OPENING_BALANCE_NOT_TAGGED`, `SYSTEM_HASHTAG`,
    `SYSTEM_NAME_FIXED`.

## What the engine declined

- **Reading up to 200 bank lines in one call.** A line's figures are read when one line is
  opened (re-split, the "reaches every part" note), not across a ledger page.
- **A line's total and part count on every transaction.** A response names other records by id
  only, and a transaction's response would change without its `version` moving. A transaction
  carries `bank_line_id`; the figures come from `GET /bank-lines/{id}`.
- **A signed amount on the upload's unclaimed parts.** The parts are ordinary transaction
  responses: `amount_cents` positive, the direction in `transaction_type`. Only totals are
  signed.

The engine also names one leftover: the `OPERATION_CODE_EXISTS` reason now speaks of bank lines,
but the refusal's message still says "A transaction with operation code … already exists". The
app chooses hints by reason, so nothing here changes; the engine fixes the wording in a later
hand-off.

## Tasks

Approved by the owner (2026-10-16; task 10 on 2026-10-17). Each **[UI]** task starts with
its mockup; the build waits for the owner's pick. Tasks 1, 2 and 9 are done; the live contract
tests cover every new refusal reason of `3129bfa2c43a4446` except `SPLIT_LINE_PARTS_DIVERGE`,
which no current route can produce.

The spec ends at contract `890453f80a08cec9` (owner, 2026-10-17). What the engine changed
after it, and the ledger's keys on a part of a split purchase (the former task 4, which waits on
the engine deleting a purchase whole), go to the next catch-up (todo.md "Catch up with the
engine after `890453f80a08cec9`"). The tester's acceptance check expects one live test to fail
for that reason: `test_a_line_in_two_reconciliations_is_split_reconciliation_mixed`, since the
engine now reconciles a purchase whole.

Owner's picks of 2026-10-17 are noted on each task; a task builds once every pick it needs is
in and its engine change has landed.

5. **[UI]** The split action: split, re-split, and the totals-don't-add-up refusal. Re-split
   opens with the parts `?bank_line_id=` lists and the total `GET /bank-lines/{id}` reads.
   Picked: 2 B (one typed line per part); 3 as drawn (`s` on any part opens all its parts);
   `^s` always sends: the count turns red while it is not 0, and the engine's refusal shows under
   the parts (owner, 2026-10-17).
## Reply to the engine

Written once the spec is done, into [to-engine/](../to-engine/), for the owner to hand over.

- **Covers:** contract `42d70a629215928d` (exclusive) to `890453f80a08cec9` (inclusive),
  answering the hand-offs "Bank lines and splits keep one identity across re-imports, and every
  transaction now carries at least one hashtag" and "A bank line can be read, the import's
  mismatched days show what each unclaimed line is, and system rows keep their names".
- **Done when, checked:** each of "The engine's checks" above, with the tester's result.
- **Contract problems found:** found so far: on `890453f80a08cec9`, `PUT /transactions/{id}`
  with `reconciliation_id` on one part of a split line puts every part of the line in that
  reconciliation, while the contract says it "settles `{id}` alone"; so `SPLIT_RECONCILIATION_MIXED`
  cannot be produced that way, and the live test expecting it fails. The engine has since made
  the whole-line rule its contract (`ce4e5cb642e53fdb`), which the next catch-up covers. Then
  what the builds and the
  tester's run found, and whether the
  `OPERATION_CODE_EXISTS` message still says "transaction".
- **Asks this closes:** "A bank line split into several transactions keeps one identity, so a
  re-import recognises it"; "A built-in `#Pendiente` hashtag that every row with no hashtag lands
  on, as `@Pendiente` does for categories"; "Let a client read a bank line: its parts, its total
  and its part count"; "A bank import's unclaimed ledger lines carry their total and their
  parts"; "The built-in categories and the built-in pending hashtag cannot be renamed".
