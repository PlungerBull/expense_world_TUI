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
- The dry run shows each group as one movement with its parts.
- No screen shows the ID or the statement line (owner, 2026-10-21).

`COD_EECC` is not the bank's operation number: the sheet has no column for it, and bank uploads
write it on later (contract: POST /v1/transactions/import, "Matching").

## How the owner knows it is done

1. The dry run shows each of the 9 split groups as one movement with its parts.
2. After the import, the ledger shows each split group as one split transaction, and the engine
   holds each coded row's `COD_EECC` and an ID on every movement.
3. A sheet with two rows sharing a `COD_EECC` on different accounts or dates is refused at the
   dry run, naming both rows.

## Catching up with the engine

**Catches up to contract `56a43798fc1f2915`:** every contract change after `ab14bd54f4c8b016`
up to it, the line-code and statement-line half of the engine's hand-off "Every bank line
carries an engine-given code and an optional statement-line reference, and an account can
become a person and back" (shipped 2026-10-21). Its account half, contract `fab230c456c2dba2`,
is [accounts-become-people.md](accounts-become-people.md). The contract version this client
holds is `fab230c456c2dba2`, recorded 2026-10-21.

**The engine's checks** — its "Done when" for this half. The tester's acceptance check runs them,
and the reply reports each result.

1. The TUI holds contract `fab230c456c2dba2` and reads `line_code` and `statement_line` without
   error.
2. A sheet import sends each row's statement line. Every part of a split group lands on one line,
   sharing one `line_code` and one `statement_line`.
3. No TUI request carries `line_code`.

**What the engine declined:** nothing; the hand-off answers no ask.

**Questions for the owner:** how the dry run shows the groups, and what a group whose rows differ
does, drawn in
[expense-world-sheet-import-groups.html](../mockups/expense-world-sheet-import-groups.html): one
letter for screen 1 (A or B) and one for screen 2 (A or B). **Recommended:** 1 A · 2 A — the
list lets you check each group against its statement before writing, and the ledger never holds
half a group.

## Tasks

Drafted 2026-10-21; wait for the owner's approval. Tasks 1 and 2 draw nothing; tasks 3 and 4
wait for the picks above.

1. **The unit fixtures and the live contract tests know both fields.** Every transaction and
   bank-line fixture carries `line_code` (`#` and six digits) and `statement_line` (`null` or a
   value), and the import's `unclaimed_lines` fixtures carry `line_code`; the drift script passes.
   New live contract tests: a batch `line_group` makes one line whose parts read one `line_code`,
   kept by a split; sending `line_code` on any create or `PUT` is `422` `UNKNOWN_FIELD`;
   `statement_line` round-trips on create, batch and `PUT` (written onto every part, `null`
   clears it); a second live line with the same value is `409` `STATEMENT_LINE_EXISTS` and two in
   one batch are `422` `DUPLICATE_IN_REQUEST`; a group whose items differ on it is `422`
   `LINE_GROUP_FIELDS_DIFFER`; the opening balance, the split and the bank upload refuse it as
   `UNKNOWN_FIELD`; in a completed reconciliation a set one is `LOCKED` and an empty one fills.
   The practice user's data outlives a reseed, so every statement line a test writes is unique
   to its run. Passes the engine's check 1.
2. **No request carries `line_code`.** A unit guard fails when any request body the app builds
   holds the key. Passes the engine's check 3.
3. **The sheet import groups by `COD_EECC` and sends it as `statement_line`.** The sheet's
   `COD_EECC` column is read (blank is none); rows sharing one become one movement, sent as the
   items of one `line_group` in one `POST /transactions/batch`, each carrying the
   `statement_line`. A chunk never cuts a group, and the row-by-row retry after a refused chunk
   retries a group as one batch, never row by row. A group whose rows differ on account, date or
   title behaves as picked screen 2 draws. The dry run, and its `--json`, show the groups as
   picked screen 1 draws. A re-run of an imported sheet still counts every row as already there,
   groups included: checked live first — if the engine answers a re-sent group with
   `STATEMENT_LINE_EXISTS` instead of `ID_EXISTS` on its own id, stop and report it, since that
   is an engine ask. Unit tests: the grouping, a chunk boundary inside a group, the retry, the
   re-run, each refusal; a live contract test imports a small sheet with one group. Passes the
   owner's checks 1 to 3 and the engine's check 2.
4. **The import shows the new refusals in the engine's words:** `STATEMENT_LINE_EXISTS`,
   `DUPLICATE_IN_REQUEST` and `LINE_GROUP_FIELDS_DIFFER` on `statement_line`, and
   `LIMIT_REACHED` with `LINE_CODES_EXHAUSTED`, each against its sheet lines. Unit tests: one per
   reason. [commands.md](../commands.md) says what the import does with `COD_EECC`.

## Reply to the engine

Written once the spec is done, into [to-engine/](../to-engine/), for the owner to hand over.

- **Covers:** contract `ab14bd54f4c8b016` (exclusive) to `56a43798fc1f2915` (inclusive), the
  line-code and statement-line half of the hand-off named above; its account half has its own
  reply, from [accounts-become-people.md](accounts-become-people.md).
- **Done when, checked:** the three engine's checks above, with the tester's results.
- **Contract problems found:** what the build and the tester's run find.
- **Asks this closes:** none.
