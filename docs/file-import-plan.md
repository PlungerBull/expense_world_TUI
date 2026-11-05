# File import as the intake — what is left

Rows arrive as BCP `.xlsx` downloads through the TUI import door ([tui.md](tui.md) "The import
door"), sent to the engine whole (contract: POST /v1/transactions/import). The door is built; its
non-goals, and the time-of-day limit of the `!` flag on lines in no statement, are in
[decisions.md](decisions.md) "Bank downloads are matched against the ledger" and "Rows in no
batch live in the reconciliation view".
A month's PDF closes the account's statement for that month, every currency on it
([tui.md](tui.md) "A statement PDF closes its month").

What is left is the first real bank import, after the official import
([before-the-official-import.md](specs/before-the-official-import.md)). Reconciling is the
owner's call, made later. This file is deleted once that import is done.
