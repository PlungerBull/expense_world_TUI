# Catch up with the import moving a matched line to the bank's day

**Status: draft, waiting for the owner's approval.**
**Catches up to contract `786d68f3b071dbf4`:** every contract change after `7ff6a09d863d6e44`.
It holds sections 5 and 6 of the engine's hand-off "A bank line is read, reconciled, deleted and
listed whole; the import moves a code-matched line to the bank's day; six contract texts are
corrected". The spec before this one took its sections 1 to 4. What it asks of this client is
in the tasks, and its check is in "The engine's checks". The engine counts a moved line on the
bank's day, so the move itself leaves no day disagreeing. A line whose move is stopped is still
matched, and the file's other rows are created. When done, the why moves to
[decisions.md](../decisions.md), and this file is deleted.

---

## What it must do

**The import moves a transaction to the bank's day.** When a file row matches a ledger
transaction by its operation number and the bank has it on another day, importing moves the
transaction, every part of it, to the bank's day. The preview says so before anything is
written.

- **On the preview, a row that moves says so.** It shows the ledger's day and the bank's day.
- **A row that keeps its day says why.** A completed reconciliation stops the move, either
  because the transaction is in it or because it covers the bank's day. The row names that
  reconciliation. The row is still matched, and the rest of the file still imports.
- **The counts say how many move.** The preview's summary line and the "imported" screen give
  the number of transactions moved to the bank's day, next to the other counts. That number is
  the engine's.
- **Wording only, nothing to show.** Contract `786d68f3b071dbf4` changes six engine texts. The
  app shows every engine message whole and quotes none of them, so no screen changes. No test
  pins an old wording either.

Every one of these that changes what a screen shows is drawn as a mockup and picked by the owner
before it is built.

## How the owner knows it is done

1. A file with a transaction the ledger has on 3 October and the bank on 4 October, matched by
   its operation number, shows on the preview as moving from 3 to 4 October. After importing,
   the ledger has it, every part, on 4 October.
2. The same transaction inside a completed reconciliation shows on the preview as keeping its
   day, naming that reconciliation. After importing it is still on 3 October, and the file's
   other rows are in the ledger.
3. The preview's summary and the "imported" screen give how many transactions moved.
4. A row matched on its own day shows nothing new.

## The engine's checks

The engine's own "Done when" for this range. The tester's acceptance check runs it, and the
reply to the engine reports the result.

1. The import screen shows, before applying, which code-matched lines will move to the bank's
   day and which keep their date because of a completed reconciliation, and shows the moved
   count after applying.

## What the engine declined

Nothing in this range.

## Tasks

Drafted 2026-10-17, waiting for the owner's approval. Each **[UI]** task starts with its mockup;
the build waits for the owner's pick.

1. **[UI] The preview and the "imported" screen become one table of the file's rows, with a
   mark (✓/✗) and a reason; the move to the bank's day is one of the reasons.** Mockup:
   [expense-world-import-report.html](../mockups/expense-world-import-report.html).
   - The import reads `redated`, `redate_blocked_by` and `counts.redated` from the engine's
     answer, through the shared reader in [engine.py](../../expense/bank_import/engine.py).
   - A blocking reconciliation is named by a read of it by id.
   - The unit fixtures carry the new keys.
   - A live contract test proves both the move and the blocked move on the practice engine.
   - [tui.md](../tui.md) "The import door" says what the screens show.

## Reply to the engine

Written once the spec is done, into [to-engine/](../to-engine/), for the owner to hand over.

- **Covers:** contract `7ff6a09d863d6e44` (exclusive) to `786d68f3b071dbf4` (inclusive),
  answering sections 5 and 6 and "What the TUI does" steps 7 to 9 of the hand-off named above.
- **Done when, checked:** the one check in "The engine's checks" above, with the tester's
  result.
- **Contract problems found:** what the build and the tester's run find.
- **Asks this closes:** none.
