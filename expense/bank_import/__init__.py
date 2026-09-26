"""Bank downloads → the ledger: `expense import bank <file.xlsx>`.

Two modules, both pure (no HTTP, no typer, no config):

    parse.py   the bank's sheet → BankRow per line: date, the bank's title
               (whitespace collapsed), currency, signed cents, operation code
    engine.py  BankRows → the `POST /transactions/import` body, and the
               engine's answer → one view per row (new, in the ledger by which
               rule, or inside a closed period), plus the groups where the
               ledger holds MORE than the file

The matching itself is the engine's (engine-spec `POST /transactions/import`,
taken up 2026-09-26). The command that reads the file, asks which account and
makes the one call is expense/commands/bank_import_cmd.py. Design and the
owner's picks (2026-09-12): docs/mockups/expense-world-bank-import.html —
option B (the file name → account choice is remembered in the config) and
option D (a loud warning when the ledger holds more than the file).
"""
