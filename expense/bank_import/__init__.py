"""Bank downloads → the ledger: `expense import bank <file.xlsx>`.

Two modules, both pure (no HTTP, no typer, no config):

    parse.py   the bank's sheet → BankRow per line: date, cleaned title, raw
               description, currency, signed cents, operation code if any
    match.py   BankRows against what the ledger already holds → a Verdict per
               row (new, or in the ledger and by which rule), plus the groups
               where the ledger holds MORE than the file

The command that reads the file, asks which account, fetches the ledger and
writes the new rows is expense/commands/bank_import_cmd.py. Design and the
owner's picks (2026-09-12): docs/mockups/expense-world-bank-import.html —
option B (the file name → account choice is remembered in the config) and
option D (a loud warning when the ledger holds more than the file).
"""
