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

## Tasks

None yet: drafted once the engine has landed its half.
