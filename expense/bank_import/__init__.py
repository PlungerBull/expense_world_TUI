"""Bank downloads → the ledger, through the TUI import door.

Two modules, neither of which prints or imports typer:

    engine.py  the `POST /transactions/import` body (the file whole, in
               base64, and the account), and the engine's answer → one row
               per spreadsheet row with its verdict and reason, the engine's
               counts, and the days whose file and ledger totals disagree
    flow.py    the door's steps: read the dropped file's bytes, list the
               accounts as picks (a card's two accounts as one), make the one
               call, name the reconciliations that stop a move

engine.py is pure (no HTTP, no config). The app reads no cell of the file:
reading it, matching it and refusing its rows are the engine's
(contract: POST /v1/transactions/import). The door is
expense/tui/screens/bank_import.py, and it runs flow.py. The account is
asked every run, never remembered by file name.
"""
