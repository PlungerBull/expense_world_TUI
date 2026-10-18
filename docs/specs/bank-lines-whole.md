# Catch up with purchases read, reconciled and deleted whole

**Status: approved by the owner (2026-10-17); the loop runs on it.**
**Catches up to contract `7ff6a09d863d6e44`:** every contract change after `890453f80a08cec9`.
It holds the engine's hand-off "A bank line is read, reconciled, deleted and listed whole; the
import's mismatched days show what each unclaimed line is; system rows keep their names", whose
parts up to `890453f80a08cec9` the previous spec already covers: what it asks of this client is
in the tasks, its checks in "The engine's checks", and what the engine declined in "What the
engine declined". When done, the why moves to [decisions.md](../decisions.md), and this file is
deleted.

---

## What it must do

A purchase split into parts stays one bank movement everywhere it matters to the bank: it is
read, reconciled and deleted whole. The ledger stays one row per part (owner, 2026-10-17).

- **Opening a purchase is one read.** Re-splitting opens with the purchase's parts and total
  from one engine read; the app adds up nothing.
- **A purchase is reconciled whole.** The reconciliation screen lists each purchase once, with
  its total, and ticking it puts every part in the reconciliation; unticking takes every part
  out. It never shows half a purchase ticked.
- **`d` deletes the whole purchase (owner, 2026-10-17).** On any part of a split purchase, in
  the ledger or the reconciliation screen, `d` deletes every part in one go, after a question
  naming how many parts go. A purchase in a completed reconciliation cannot be deleted, and the
  engine's refusal says so.
- **The ledger's other keys on a part (owner, 2026-10-17).** `c` and `h` change only the
  selected parts; `b` moves the whole purchase, as the engine does.

Every one of these that changes what a screen shows is drawn as a mockup and picked by the owner
before it is built.

## How the owner knows it is done

1. Re-splitting a purchase opens with its parts and total, and the app made one read for it.
2. On the reconciliation screen, a purchase split in two is one row with its total; ticking it
   ticks both parts, unticking unticks both, and completing the month counts the whole total.
3. `d` on one part of a split purchase asks first, naming how many parts go, then deletes them
   all; the ledger shows neither part afterwards.
4. Deleting a purchase in a completed reconciliation is refused, and nothing is deleted.
5. `c` on one part of a split purchase changes only that part; `b` moves both.

## The engine's checks

The engine's own "Done when" for this range, beyond what the previous spec reports. The tester's
acceptance check runs each one, and the reply to the engine reports each result.

1. Opening a purchase is one `GET /bank-lines/{id}`; the app adds no amounts of its own.
2. The reconciliation screen lists purchases from `GET /bank-lines`, ticks a purchase with one
   `PUT` on any part, and never shows half a purchase ticked.
3. Deleting a purchase is one `DELETE /bank-lines/{id}` behind a confirmation, from the ledger
   or the reconciliation screen.
4. `IN_COMPLETED_RECONCILIATION` on `bank_line_id` has a handled path; no code handles
   `SPLIT_RECONCILIATION_MIXED`.

## What the engine declined

- **A ledger read one purchase per row.** The ledger stays one row per part (the owner's
  ruling); only the reconciliation features list a purchase as one row, through
  `GET /bank-lines`. It takes no `search`: finding rows by text is the ledger's job.
- **Reading several purchases by id in one call.** `GET /bank-lines` replaces it.
- **A purchase's total and part count on every transaction**, and **signed amounts on parts**:
  as in the previous spec.

The engine names one leftover, unchanged: the `OPERATION_CODE_EXISTS` refusal's message still
says "transaction".

Where it runs: the practice engine serves `7ff6a09d863d6e44`; the live engine serves it only
once the owner has applied the ledger update that installs the one-reconciliation-per-purchase
rule, and serves `ce4e5cb642e53fdb` until then.

## Tasks

Approved by the owner (2026-10-17). Each **[UI]** task starts with its mockup; the build waits
for the owner's pick.

2. **[UI]** The reconciliation screen lists purchases from `GET /bank-lines` and its count, one
   row per purchase with its total; ticking sends one `PUT` with `reconciliation_id` on any one
   part, unticking sends `null`, and the screen re-reads what it shows after each tick. Every
   reconciliation list shows a purchase this way (a draft month, a completed month, the "no
   batch" list); the row carries the purchase's title alone and its total, says nothing of its
   parts, and the parts are not listed there. Every reconciliation list shows only the bank's
   columns, on every row, one line per row: date · title · operation number · amount, with no
   category, hashtags or note (owner, 2026-10-17). Picked as drawn in
   [expense-world-bank-lines-whole.html](../mockups/expense-world-bank-lines-whole.html) 2a B–2d:
   the column is named `Operation`, and the date comes first on every list.
3. **[UI]** `d` on a part of a split purchase, from the ledger and the reconciliation screen:
   one `DELETE /bank-lines/{id}` behind a question naming how many parts go, and the
   `IN_COMPLETED_RECONCILIATION` refusal. A transaction never split deletes as today. The
   question reads "Delete this purchase and its 3 parts? No screen can bring it back." with the
   real part count (owner, 2026-10-17). Picked as drawn in 3a–3e of the same mockup; the note
   after the delete reads `Purchase deleted.`
4. The ledger's `c`, `h` and `b` on parts: confirm with tests that `c` and `h` change only the
   selected parts and that `b` on one part moves the whole purchase (the engine's rule), and
   that the ledger reloads fresh after each.

## Reply to the engine

Written once the spec is done, into [to-engine/](../to-engine/), for the owner to hand over.

- **Covers:** contract `890453f80a08cec9` (exclusive) to `7ff6a09d863d6e44` (inclusive),
  answering the hand-off "A bank line is read, reconciled, deleted and listed whole; the
  import's mismatched days show what each unclaimed line is; system rows keep their names"; its
  parts up to `890453f80a08cec9` are answered by the previous spec's reply.
- **Done when, checked:** each of "The engine's checks" above, with the tester's result.
- **Contract problems found:** what the builds and the tester's run find, and whether the
  `OPERATION_CODE_EXISTS` message still says "transaction".
- **Asks this closes:** "A bank line is reconciled whole: assigning or unassigning one part does
  the same to every part"; "Deleting a bank line deletes every one of its parts, in one write";
  "The ledger can be read one bank line per row, with each line's parts inside" (answered
  differently: the ledger stays one row per part).
