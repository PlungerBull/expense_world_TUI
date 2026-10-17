# Decide before the official import

**Status: draft, written at the owner's ask (2026-10-17); every question waits on the owner.**
It feeds [official-migration.md](official-migration.md): each answer moves into that spec's
"What it must do", and this file is deleted when the last one is in.

---

## Where things stand (2026-10-17)

- The spreadsheet is checked against the bank for 2026: the current account matches every
  statement January–September to the cent, the dollar account January–August, and both legs of
  the card every line January–September; October matches the bank downloads. Every 2026 row
  carries the bank's date, and the current account's rows carry their statement month in
  `ESTADO_CUENTA`. The figures stay outside this repo.
- The live database still holds the sheet as it was on 2026-09-14, so the import is a wipe and
  one fresh import ([official-migration.md](official-migration.md)).
- Built and waiting for nothing: the sheet import itself. Not built yet: its task 1 (`PENDIENTES`
  and empty cells go to the pending category and hashtag). Without it, the rows with no category
  are dropped and the current account's balance comes out wrong.

## What the owner decides

### 1. Keep the one-time pass that renames typed rows to the bank's wording?
The engine already does this on every bank upload: when a file row matches a ledger row (same
bank code, or same account, exact day and amount), the engine writes the bank's wording onto the
ledger row and keeps the old wording as its note when the note is empty
(contract: POST /v1/transactions/import, "Matching"). The app only shows the result.
- **A.** Drop the pass.
- **B.** Keep it as a one-off tidy-up before the first upload.

**Recommended:** A, because every 2026 row now carries the bank's date and amount, so every
upload renames it anyway.

### 2. How are January–September 2026 confirmed in the app?
The plan says "upload each month's statement", but the upload reads only the bank's `.xlsx`
download, which holds the last 20 movements of an account or 80 of a card, a few weeks at most.
January–August exist only as PDF statements, which the app does not read (settled:
[file-import-plan.md](../file-import-plan.md) §8, "Other banks, CSV, PDF").
- **A.** The sheet import also creates each 2026 statement's reconciliation from the
  `ESTADO_CUENTA` column and the statement's opening and closing balances (one list, kept outside
  the repo), and completes the ones that come to zero. About 35 statements over four accounts.
- **B.** The owner creates each reconciliation by hand in the app's reconciliation screen.
- **C.** No reconciliations before the first bank upload; 2026 stays checked only in the sheet.

**Recommended:** A, because the sheet already says which statement each row belongs to, and the
engine still judges every balance. It needs the `ESTADO_CUENTA` marks finished for the dollar
account and the card first.

### 3. Group the split purchases before importing?
Some single bank charges are two rows in the sheet (one purchase split across categories); 2026
has 7. The engine joins rows into one purchase only when they are written together, never
afterwards. Left as separate rows, each such day shows as "totals disagree" on any upload that
covers it.
- **A.** Mark them in the sheet (a new column naming the purchase), and the import sends each
  pair as one purchase with two parts.
- **B.** Leave them as separate rows (the decision of 2026-10-16) and fix by hand if an upload
  flags them.
- **C.** Merge each pair into one row in the sheet.

**Recommended:** A, because it is 7 pairs, and the app then shows them as one split purchase,
the way the split screens being built expect.

### 4. Classify the rows waiting for a category before or after the import?
About 20 rows have `PENDIENTES` or an empty category or hashtag. They import as `@Pendiente`
and the pending hashtag either way.
- **A.** Classify them in the sheet before the import.
- **B.** Classify them in the app afterwards (Home, `space` + `c` / `h`).

**Recommended:** A, because the pending hashtag's Home row is not built yet; B is fine if you
want to try the app's bulk edit on real rows.

### 5. Is anything still owed on the old Oro card?
It has had no movement since January 2026 but still carries a balance in both currencies, and
there is no 2026 statement for it in the folder. A fact only the owner knows.
- **A.** It is paid off: a final payment is missing from the sheet; add it before the import.
- **B.** The balance is real debt; leave it.

**Recommended:** none.

### 6. Is the April `EXTORNO` row the bank's `ABON PLIN-PALOMA G` two days later?
The bank shows that money arriving two days after the sheet's date, with another description. A
fact only the owner knows.
- **A.** Yes: move it to the bank's date.
- **B.** No: leave it.

**Recommended:** none.

### 7. Archive the closed accounts after the import?
The two Interbank accounts and Alcancía end at exactly zero and have had no movement since 2024.
Archived means retired but real: hidden from pickers, history still counted.
- **A.** Archive them right after the import.
- **B.** Leave them active.

**Recommended:** A.

### 8. After the import, is the sheet frozen?
A second sheet import cannot add to the ledger safely: the import identifies rows by their
position, so edits above the last row duplicate rows.
- **A.** Frozen: from the import on, every movement goes into the app (bank uploads and the LOG
  bar); the sheet is kept as an archive.
- **B.** Keep both for a while; a later import means wiping again and losing whatever was done
  in the app.

**Recommended:** A.

### 9. Accept the app's exchange rates for the dollar rows?
The sheet's `T.C.` and `Solarizado` columns are ignored: the engine converts each dollar row with
that day's market rate, so soles totals of dollar spending differ slightly from the sheet's.
- **A.** Accept the engine's rates.
- **B.** The sheet's own rates matter: that is an engine change, raised as an ask.

**Recommended:** A.

### 10. Import now, or wait for the October statements?
October matches the bank downloads; its statements arrive in early November.
- **A.** Import once 1–9 are answered and task 1 is built; reconcile October when its statements
  arrive.
- **B.** Wait for the October statements.

**Recommended:** A.

## How the owner knows it is done

1. Every question above has an answer, and each answer is written into
   [official-migration.md](official-migration.md).
2. That spec's task list covers every answer that needs building, ready for the owner's approval.
