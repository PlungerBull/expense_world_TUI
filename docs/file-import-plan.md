# File import as the intake — what is left

Rows arrive as BCP `.xlsx` downloads through the TUI import door ([tui.md](tui.md) "The import
door"), sent to the engine whole (contract: POST /v1/transactions/import). The door is built; its
non-goals and the "no batch" flag's time-of-day limit are in [decisions.md](decisions.md) "Bank
downloads are matched against the ledger" and "Rows in no batch live in the reconciliation view".
The bank's PDF comes in only as a month's statement
([statements-close-from-their-pdf.md](specs/statements-close-from-their-pdf.md)).

What is left is the first real bank import, after the official import
([before-the-official-import.md](specs/before-the-official-import.md)). Reconciling is the
owner's call, made later. This file is deleted once that import is done.
