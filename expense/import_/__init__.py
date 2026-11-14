"""The sheet import of `expense import sheet`: the owner's spreadsheet, sent
to the engine whole (contract: POST /v1/transactions/import-sheet).

engine.py holds every step: the names table built from the engine's answer, the body the
import's review sends to make what the sheet lacks, and the calls. The app reads no cell of
the sheet.
"""
