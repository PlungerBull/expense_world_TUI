"""Bank downloads → the ledger, through the TUI import door.

Three modules, none of which prints or imports typer:

    parse.py   the bank's sheet → BankRow per line: date, the bank's title
               (whitespace collapsed), currency, signed cents, operation code
    engine.py  BankRows → the `POST /transactions/import` body, and the
               engine's answer → one view per row (new, in the ledger as which
               bank line and by which rule, retitled or not, or inside a
               closed period), the engine's counts, and the days whose file
               and ledger totals disagree
    flow.py    the steps every door shares: read the file, fold the accounts
               into picks, place the rows on the pick's legs, make the one
               call, count the answer

parse.py and engine.py are pure (no HTTP, no config). The matching itself is
the engine's (contract: POST /v1/transactions/import). The door is
expense/tui/screens/bank_import.py, and it runs flow.py. The account is
asked every run, never remembered by file name.
"""
