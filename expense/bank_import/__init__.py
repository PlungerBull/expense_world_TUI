"""Bank downloads → the ledger: `expense import bank <file.xlsx>`.

Three modules, none of which prints or imports typer:

    parse.py   the bank's sheet → BankRow per line: date, the bank's title
               (whitespace collapsed), currency, signed cents, operation code
    engine.py  BankRows → the `POST /transactions/import` body, and the
               engine's answer → one view per row (new, in the ledger by which
               rule, or inside a closed period), plus the days where the
               ledger holds a row of the same amount that no file row matched
    flow.py    the steps every door shares: read the file, fold the accounts
               into picks, place the rows on the pick's legs, make the one
               call, count the answer

parse.py and engine.py are pure (no HTTP, no config). The matching itself is
the engine's (contract: POST /v1/transactions/import). The typed door is
expense/commands/bank_import_cmd.py, the TUI's is
expense/tui/screens/bank_import.py; both run flow.py. The account is
asked every run, never remembered by file name, and the ledger holding more
than the file is a loud warning.
"""
