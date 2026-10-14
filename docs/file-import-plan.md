# File import as the intake — what is left to build

**Open: the one-time title alignment (§6, spec [official-migration.md](specs/official-migration.md));
§11 is a standing warning.** The TUI import door is built ([decisions.md](decisions.md)
"The TUI import door"). Every rule here is an owner decision (2026-09-19
unless dated). When the work ships, its why moves to [decisions.md](decisions.md) and this file
is deleted. Section numbers have gaps on purpose: other docs cite §6 and §10.

The engine half: (contract: POST /v1/transactions/import).

---

## 1. The change

Rows stop being typed and arrive as BCP `.xlsx` downloads: drop the file on the TUI, pick the
account, review, apply. Rows land under `@Pendiente`; classification stays manual, in Home's
bulk `space` + `c`/`b`/`h`. The LOG bar stays for what has no bank row (cash, people).

**BCP only** — no second bank, no CSV, no PDF, no format abstraction. Both export shapes (card:
no operation number, ISO dates, mixed PEN/USD; current account: operation number, `dd/mm/yyyy`)
already parse ([bank_import/parse.py](../expense/bank_import/parse.py)).

**Reuse, don't rebuild:** the TUI import door does parse → account pick → one
`POST /transactions/import` as a dry run → preview → the apply. The request and the
response → rows live once, in [bank_import/engine.py](../expense/bank_import/engine.py). Recovery from a wrong account pick: select the rows in Home, `b`.

---

## 6. The one-time title alignment

The ledger's rows up to the end of the spreadsheet are hand-typed, with no operation codes and
the owner's wording (`MAR DE COLAS LIMA` vs the bank's `MAR DE COLAS LIMA PE`). The engine
matches only identical titles, so a bank file overlapping those days would import them twice.
Giving those rows the bank's wording once removes the overlap at the source. (The only other
floor is 2026-01-01, `IMPORT_FLOOR` in [bank_import/engine.py](../expense/bank_import/engine.py).)

**The overlap is small.** BCP's Excel export holds the last 20 movements of a current account
and the last 80 of a card, so it covers only the few weeks before the spreadsheet ends. The
January–August statements exist only as PDFs, which cut descriptions to 18 characters and carry
no operation number — no use for aligning titles. On the test ledger (2026-09-26): 122 bank
rows, 38 already identical, 69 with exactly one candidate, 14 with several, 1 with none.

**When:** after the official migration (sheet updated and re-imported), **before** any 2026
period is completed — a completed period locks its rows' `title`
(contract: PUT /v1/transactions/{transaction_id}, "Field locking") — and before the first real
bank import.

**How (owner, 2026-09-26: "app proposes, I approve"; no new screen, it runs once):**
1. Re-download every export the bank offers and read them against the migrated ledger — reads
   only.
2. Pair each bank row with ledger rows of the same account and signed amount on the same or
   adjacent day. Identical titles need nothing. Exactly one candidate becomes a proposal
   `ledger title → bank title`. Several or none are listed with what there is.
3. The list is a **local file outside the repo** (the repo is public; this is financial data).
   The owner answers with the exceptions and the picks for the unclear rows.
4. Apply exactly what was approved: one `PUT /transactions/{id}` with `title` only. **The old
   title is dropped**; `description` is untouched.
5. Operation codes are not written here. The first real import writes them (the engine's
   backfill on a `same_day` / `adjacent_day` match), and its dry run is the check: every aligned
   row must read `in ledger · … · +code`, none `new`.

---

## 8. Settled non-goals

| Not doing | Why |
|---|---|
| Merchant memory / category suggestions | Classification stays manual (Home suggestions were rejected 2026-09-13). |
| Transfer / card-payment / ITF detection | `TRAN.CTAS.PROP.BM`, `PAG.T.PROP.VISA.BM`, `IMPUESTO ITF` import as ordinary rows, classified by hand. |
| Import provenance + undo | A wrong-account import is fixed with bulk `b` in Home. |
| A per-row override in the preview | Every verdict is a fact (matching code, or identical text + amount + date), not a guess. |
| Bulk "assign everything shown" on the reconciliation screen | Revisit if monthly closing proves tedious — the draft screen already lists exactly the rows it would assign. |
| Other banks, CSV, PDF | BCP only. |

The TUI door is the only way a bank file comes in ([tui-only-plan.md](specs/tui-only-plan.md)).

---

## 9. Operating rule to write down

**Always export with an explicit date range covering everything since the last import — never
the default view.** BCP's current-account default export returns the last 20 movements, about
twelve days on `BCP PEN`. Import less often and rows fall off the window; nothing in the
importer can detect what a file does not contain. Month-end reconciliation is the only
backstop.

---

## 10. Sequence

1. Owner creates the 2026 reconciliations by hand and closes through the last EECC (statement
   dates come from the EECC; the spreadsheet's `ESTADO_CUENTA` column is the cross-check on what
   each card statement contained, since a card cycle closes mid-month).
2. After the official migration, the title alignment (§6), **before** step 1's periods are
   completed.
3. First real bank import.

`expense import sheet` stays for good: it is the door for the owner's spreadsheet (owner,
2026-09-30; [tui-only-plan.md](specs/tui-only-plan.md)).

---

## 11. Before any import writes a time of day

The "no batch" pane's `!` flag (a row dated inside a reconciliation window) is computed
client-side by comparing the ISO date prefix of the row's `date`; the engine treats a period as
whole calendar days in the user's timezone (contract: "Base Conventions", "Calendar days").
They agree **only because every live row is stored
at 00:00 America/Lima** (and Lima has no daylight saving); nothing enforces midnight. The bank
importer sends bare days. **The first writer that stores a real time of day makes the `!` wrong
near midnight** — that is the point to write an engine ask for the per-row flag
([engine-asks/](engine-asks/)).
