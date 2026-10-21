# File import as the intake — what is left to build

**§11 is a standing warning.** There is no one-time title alignment: every row the
bank files overlap already carries the statement's wording (owner, 2026-10-21). The TUI import door is built ([decisions.md](decisions.md)
"The TUI import door"). Every rule here is an owner decision (2026-09-19
unless dated). When the work ships, its why moves to [decisions.md](decisions.md) and this file
is deleted. Section numbers have gaps on purpose.

The engine half: (contract: POST /v1/transactions/import).

---

## 1. The change

Rows stop being typed and arrive as BCP `.xlsx` downloads: drop the file on the TUI, pick the
account, review, apply. Rows land under `@Pendiente` and `#Pendiente`; classification stays
manual, in Home's bulk `space` + `c`/`b`/`h`. The LOG bar stays for what has no bank row (cash,
people).

**BCP only** — no second bank, no CSV, no PDF, no format abstraction. Both export shapes (card:
no operation number, ISO dates, mixed PEN/USD; current account: operation number, `dd/mm/yyyy`)
already parse ([bank_import/parse.py](../expense/bank_import/parse.py)).

**Reuse, don't rebuild:** the TUI import door does parse → account pick → one
`POST /transactions/import` as a dry run → preview → the apply. The request and the
response → rows live once, in [bank_import/engine.py](../expense/bank_import/engine.py). Recovery from a wrong account pick: select the rows in Home, `b`.

---

## 8. Settled non-goals

| Not doing | Why |
|---|---|
| Merchant memory / category suggestions | Classification stays manual (Home suggestions were rejected 2026-09-13). |
| Transfer / card-payment / ITF detection | `TRAN.CTAS.PROP.BM`, `PAG.T.PROP.VISA.BM`, `IMPUESTO ITF` import as ordinary rows, classified by hand. |
| Import provenance + undo | A wrong-account import is fixed with bulk `b` in Home. |
| A per-row override in the preview | Every verdict is a fact (the same operation code, or the same account, exact day and total, titles playing no part), not a guess (contract: POST /v1/transactions/import, "Matching"). |
| Bulk "assign everything shown" on the reconciliation screen | Revisit if monthly closing proves tedious — the draft screen already lists exactly the rows it would assign. |
| Other banks, CSV, PDF | BCP only. |

The TUI door is the only way a bank file comes in ([decisions.md](decisions.md) "The TUI is the only surface").

---

## 9. Operating rule to write down

**Always export with an explicit date range covering everything since the last import — never
the default view.** BCP's current-account default export returns the last 20 movements, about
twelve days on `BCP PEN`. Import less often and rows fall off the window; nothing in the
importer can detect what a file does not contain. Month-end reconciliation is the only
backstop.

---

## 10. Sequence

1. The official import ([before-the-official-import.md](specs/before-the-official-import.md)).
2. First real bank import. Reconciling is the owner's call, made later (owner, 2026-10-21).

`expense import sheet` stays for good: it is the door for the owner's spreadsheet (owner,
2026-09-30; [decisions.md](decisions.md) "The TUI is the only surface").

---

## 11. Before any import writes a time of day

The "no batch" pane's `!` flag (a row dated inside a reconciliation window) is computed
client-side by comparing the ISO date prefix of the row's `date`; the engine treats a period as
whole calendar days in the user's timezone (contract: "Base Conventions", "Calendar days").
They agree **only because every live row is stored
at 00:00 America/Lima** (and Lima has no daylight saving); nothing enforces midnight. The bank
importer sends bare days. **The first writer that stores a real time of day makes the `!` wrong
near midnight** — that is the point to write an engine ask for the per-row flag
([to-engine/](to-engine/)).
