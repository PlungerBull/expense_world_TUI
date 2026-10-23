# The sheet import uses `COD_EECC` only to group split transactions, and stores it nowhere

## Why

The ledger has three identifiers for a bank movement (owner, 2026-10-23):

- **The bank line** (the engine's internal id) groups the parts of a split transaction. It works
  together with the bank's operation number.
- **The bank's operation number** lets a bank upload recognise a movement it has already seen.
- **`COD_EECC`, the statement line**, gives a movement's place in the statement's order. It is
  filled **only by a reconciliation**. Generating it there is open engine work
  (`statement-line-from-reconciliation` in the engine's todo.md).

The sheet has no internal-id column and no operation-number column (checked 2026-10-23: its
columns are description, HASHTAG, CATEGORY, FECHA, MONTO, CUENTA, T.C., MONEDA, Solarizado,
ESTADO_CUENTA, NOTAS, COD_EECC). So `COD_EECC` is the only way to tell from the sheet which rows
were one bank movement: 2,275 rows carry one, 2,266 distinct, and the 9 codes shared by more than
one row are the 9 split purchases.

Today the import uses `COD_EECC` to group those rows **and** saves it as each line's statement
line ([decisions.md](../decisions.md) "The sheet import brings a split purchase in as one split
transaction"). Saving it breaks the rule above. It would also leave 2,275 hand-typed codes in
the ledger for generated codes to clash with, because the engine refuses two lines with one
statement line.

## What it must do

1. The import still reads `COD_EECC`, and only to group rows. Rows sharing one come in as one
   split transaction under one bank line, exactly as today: grouped by the exact text with spaces
   trimmed, and a group comes in whole or not at all.
2. The import never sends a statement line. No transaction or bank line it creates has one, and
   this holds for single rows and split transactions alike.
3. Nothing else changes. Row ids stay as they are, so a re-run is still safe. What the dry run
   prints and the opening balances stay the same.
4. The docs say it: `COD_EECC` groups split transactions and is not stored, and a statement line
   comes only from a reconciliation. The import's `STATEMENT_LINE_EXISTS` refusal goes from the
   docs, since the import can no longer hit it.

## How the owner knows it is done

1. A dry run on the sheet still prints `Parsed 4188 transactions to import, as 4167 movements.`
   and `9 split transactions (30 rows) come in as one movement each.`
2. After an import into the practice engine, every split purchase is one transaction with its
   parts, and no imported row shows a statement line.
3. [commands.md](../commands.md) describes `COD_EECC` as the grouping column only.

## Tasks

Drafted 2026-10-23, waiting for the owner's approval.

1. **The import stops sending `COD_EECC`.** Passes if: no payload the import builds carries
   `statement_line`, for a single row or a group's part (unit tests); grouping, all-or-nothing
   and the dry-run counts keep their existing tests green; a live contract test imports a
   two-row group and reads one bank line with two parts and a `null` statement line;
   [commands.md](../commands.md) "import sheet" says `COD_EECC` groups and is not stored, and
   drops the `STATEMENT_LINE_EXISTS` lines that belong to the import.

When it ships, the orchestrator updates [decisions.md](../decisions.md) "The sheet import brings a
split purchase in as one split transaction" (the code is no longer kept on the line), and the
owner tells the engine coders that the import sets no statement lines. That closes the question
"what happens to the ones the sheet import already set" in the engine's
`statement-line-from-reconciliation`.
