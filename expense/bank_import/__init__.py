"""Bank files → the ledger, through the TUI import door: the bank's downloads,
and a month's statement PDF, which closes the month.

Three modules, none of which prints or imports typer:

    engine.py     the body of both uploads (the file whole, in base64, and the
                  account), and the download's answer → one row per
                  spreadsheet row with its verdict and reason, the engine's
                  counts, and the days whose file and ledger totals disagree
    statement.py  the statement upload's answer → its name and days, whether
                  it creates the statement, each account's balances, one row
                  per row of the paper with its outcome, the lines taken out,
                  the counts, and the lines its close flagged
    flow.py       the door's steps: read the dropped file's bytes, list the
                  accounts as picks (one per account, its currencies its own), make the
                  one call (`import_call`, `statement_call`), name the
                  statements that stop a move, read the lines a
                  statement's answer names by id

engine.py and statement.py are pure (no HTTP, no config). The app reads no
cell of a download and nothing in a PDF: reading, matching and refusing are
the engine's (contract: POST /v1/transactions/import)
(contract: POST /v1/statements/import). The door is
expense/tui/screens/bank_import.py and the upload
expense/tui/screens/statement_upload.py, and both run flow.py. The account is
asked every run, never remembered by file name.
"""
