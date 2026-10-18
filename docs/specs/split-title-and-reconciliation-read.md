# Catch up with the split's title and the read of one reconciliation

**Status: approved 2026-10-18.**
**Catches up to contract `c4327854a6d6e301`:** every contract change after `786d68f3b071dbf4`.
It holds the engine's hand-off "A split can rename its line in the same write, and one
reconciliation can be read by its id". What it asks of this client is in the tasks, and its
checks are in "The engine's checks". The split screen's title is task 2 of
[split-screen-fields.md](split-screen-fields.md), moved here. When done, the why moves to
[decisions.md](../decisions.md), and this file is deleted.

---

## What it must do

**The split screen changes the title in the same write as the split.** The title line above the
table of parts is edited as screen 4 of
[expense-world-split-screen.html](../mockups/expense-world-split-screen.html) draws it.

- **`⏎` on the title opens one field below;** `⏎` there puts the new title on the line above
  the table. `^s` sends it with the split, and every part carries it.
- **A title left untouched is not sent,** so the transaction keeps the title it has.
- **An emptied title is refused, as on the Edit form:** `⏎` on an empty field says
  `Title is required.` and the field stays open. A split never removes a title.
- **A transaction in a completed reconciliation** may be split, but its title cannot change.
  The engine refuses a changed title; the refusal shows under the parts like any other, together
  with any part's refusal from the same answer, and nothing is split.

**The import preview names the stopping reconciliation from a read of that one
reconciliation.** A row whose move to the bank's day a completed reconciliation stops still
reads `✗ Not moved: <reconciliation> is reconciled`; its name now comes from reading that
reconciliation by its id, not from reading the account's whole list. When that read fails, the
row still reads `✗ Not moved: a reconciliation is reconciled`. Nothing on screen changes.

## How the owner knows it is done

1. `s` on `Tottus Jockey Plaza -100.00`, the title changed to `Tottus — semana`, two parts and
   `^s` leave both rows titled `Tottus — semana`.
2. The same split with the title left alone leaves both rows titled `Tottus Jockey Plaza`.
3. Emptying the title and pressing `⏎` says `Title is required.`, and the title is still there.
4. On a transaction in a completed reconciliation, a changed title and `^s` show the engine's
   refusal under the parts, and the transaction is still one row; with the title left alone,
   the split goes through.
5. An import with a move stopped by a completed reconciliation still names it on the preview:
   `✗ Not moved: <reconciliation> is reconciled`.

## The engine's checks

The engine's own "Done when" for this range. The tester's acceptance check runs them, and the
reply to the engine reports each result.

1. The split screen renames a line in the same write as the split, and leaves the title alone
   when the owner did not touch it.
2. The import preview names a stopping reconciliation from `GET /reconciliations/{id}`, without
   reading the account's whole list.
3. The TUI's contract tests pass against an engine serving `c4327854a6d6e301`.
4. The TUI's catch-up note names `c4327854a6d6e301` as the last version read.

## What the engine declined

- **The import's answer does not carry the stopping reconciliation's name.** On every route,
  a reference to another record carries its id only, and a name on this row would be the first
  exception. The engine adds `GET /reconciliations/{id}` instead, so the client reads only the
  reconciliations its rows name. That is still a second read, so the fallback wording stays.

## Tasks

Approved 2026-10-18, with screens 4 to 6 of the mockup. Both tasks are done; the acceptance
check runs next.

## Reply to the engine

Written once the spec is done, into [to-engine/](../to-engine/), for the owner to hand over.

- **Covers:** contract `786d68f3b071dbf4` (exclusive) to `c4327854a6d6e301` (inclusive),
  answering every section of the hand-off named above.
- **Done when, checked:** the four checks in "The engine's checks" above, with the tester's
  results.
- **Contract problems found:** what the build and the tester's run find.
- **Asks this closes:** "Splitting a transaction can also change its title, in the same write"
  and "The import answer names the reconciliation that stops a move to the bank's day", both
  handed over on 2026-10-18.
