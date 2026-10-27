"""The sheet import of `expense import sheet`: the owner's spreadsheet, sent
to the engine whole (contract: POST /v1/transactions/import-sheet).

engine.py holds every step: the names table built from the engine's answer,
the create step for the names the sheet lacks, the renames of
`--account-name`, and the calls. The app reads no cell of the sheet.
"""
