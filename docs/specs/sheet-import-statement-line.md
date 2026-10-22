# The sheet import brings split rows in as one movement and keeps each row's statement line

**Status: draft (owner, 2026-10-21).** The engine half is the engine repo's spec
`bank-line-id-and-statement-line.md`: it gives every movement its internal ID and keeps the
statement line. This spec is the client half, the sheet import, and waits for it to land.

---

## Why

Some single bank movements are several rows in the sheet (one purchase split across categories:
9 of them today). The import brings each row in as its own movement, so the app does not see
them as one split purchase, and a later bank upload adds the movement again.

The sheet already marks them: each row checked against a bank statement carries its statement
line in `COD_EECC` (`SIG-202603-029`: the Signature card's statement closing in March 2026,
line 29), and split rows share one. The owner wants that reference kept in the ledger as well.

Every movement also gets an internal ID (`#000001` upwards), given by the engine at the import
and on every movement after it; the sheet has no ID column and the import sends none (owner,
2026-10-21). After the import the app is the record, and the sheet is not imported again.

## What the import must do

- **Rows sharing a `COD_EECC` come in as one movement,** with a part per row. They must share
  account, date and description; a group that does not is refused at the dry run, naming its
  rows.
- **Each movement's `COD_EECC` is sent with it,** so the engine keeps it as the statement line.
  Rows with an empty `COD_EECC` (mirror rows, rows with no statement) come in as movements of
  their own with no statement line.
- The dry run says how many split transactions come in as one movement each.
- No screen shows the ID or the statement line (owner, 2026-10-21).

`COD_EECC` is not the bank's operation number: the sheet has no column for it, and bank uploads
write it on later (contract: POST /v1/transactions/import, "Matching").

## How the owner knows it is done

1. The dry run says 9 split transactions come in as one movement each.
2. After the import, the ledger shows each split group as one split transaction, and the engine
   holds each coded row's `COD_EECC` and an ID on every movement.
3. A sheet with two rows sharing a `COD_EECC` on different accounts or dates is refused at the
   dry run, naming both rows.

## Catching up with the engine

**Catches up to contract `54fd1012f7d60abc`:** every contract change after `ab14bd54f4c8b016`
up to it except the account half, from the engine's hand-off "Every bank line carries an
engine-given code and an optional statement-line reference, an account can become a person and
back, and a create sent again answers `ID_EXISTS` before anything else" (shipped 2026-10-21):
the line codes and statement lines (`9a6eb171966731ff`, `56a43798fc1f2915`) and the order in
which a create's refusals come (`60ccfaac33320536`, `54fd1012f7d60abc`). Its account half,
contract `fab230c456c2dba2`, is [accounts-become-people.md](accounts-become-people.md). The
contract version this client holds is `54fd1012f7d60abc`, recorded 2026-10-22.

**The engine's checks** — its "Done when" for this half. The tester's acceptance check runs them,
and the reply reports each result.

1. The TUI holds contract `54fd1012f7d60abc` and reads `line_code` and `statement_line` without
   error.
2. A sheet import sends each row's statement line. Every part of a split group lands on one line,
   sharing one `line_code` and one `statement_line`.
3. No TUI request carries `line_code`.
4. A sheet-import re-run with statement lines counts every row that landed as already there, and
   creates only the rows that are new.
5. A batch's refusals show grouped by reason.

**What the engine declined:** nothing. It answers the ask "A create whose `id` is already in the
ledger answers `ID_EXISTS` on that id before any other conflict" as asked, and wider: on every
create, before every rule that reads the ledger, and a batch names every item a step refuses, not
only the first.

**Questions for the owner:** none open.

## Tasks

Approved by the owner 2026-10-21, who picks 1 B · 2 B in
[expense-world-sheet-import-groups.html](../mockups/expense-world-sheet-import-groups.html).
Tasks 3 and 6, from the engine's hand-off, are approved by the owner 2026-10-22, who picks
1 A · 2 A · 3 A in
[expense-world-grouped-refusals.html](../mockups/expense-world-grouped-refusals.html). Every task
is done; the tester's acceptance check and the librarian's sweep follow.

## Reply to the engine

Written once the spec is done, into [to-engine/](../to-engine/), for the owner to hand over.

- **Covers:** contract `ab14bd54f4c8b016` (exclusive) to `54fd1012f7d60abc` (inclusive), all
  of the hand-off named above but its account half, which has its own reply, from
  [accounts-become-people.md](accounts-become-people.md). `54fd1012f7d60abc` is the version the
  owner quotes for the next catch-up once both replies are handed over.
- **Done when, checked:** the five engine's checks above, with the tester's results.
- **Contract problems found:** what the build and the tester's run find, and this one from the
  build: the contract says a statement line is trimmed and compared after trimming, but not
  whether case counts. The practice engine treats `SIG-x` and `sig-x` as two statement lines
  (2026-10-22), and the sheet import groups by exact text to match; the contract should say so.
- **Asks this closes:** "A create whose `id` is already in the ledger answers `ID_EXISTS` on that
  id before any other conflict".
