"""Bank downloads → the ledger: `expense import bank <file.xlsx>`.

Two modules, both pure (no HTTP, no typer, no config):

    parse.py   the bank's sheet → BankRow per line: date, the bank's title
               (whitespace collapsed), currency, signed cents, operation code
    engine.py  BankRows → the `POST /transactions/import` body, and the
               engine's answer → one view per row (new, in the ledger by which
               rule, or inside a closed period), plus the days where the
               ledger holds a row of the same amount that no file row matched

The matching itself is the engine's (engine-spec `POST /transactions/import`).
The command that reads the file, asks which account and
makes the one call is expense/commands/bank_import_cmd.py. The file name →
account choice is remembered in the config, and the ledger holding more
than the file is a loud warning.
"""
