"""Spreadsheet import for the `expense import sheet` command.

Client-specific input handling (like dates.py): parses an .xlsx
client-side and feeds the existing engine write endpoints. No business logic
lives here — accounts/categories/hashtags are resolved-or-created by name and
transactions are sent through POST /v1/transactions/batch.

engine.py is the import through the engine instead: it sends the workbook
whole (contract: POST /v1/transactions/import-sheet), builds the names table
from the engine's answer, creates the names that go to a new one, and sends
the apply with the table. It reads no cell of the sheet; the command does not
run it.
"""
