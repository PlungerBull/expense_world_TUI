"""Column mapping + constants for the spreadsheet import.

Single source of truth for the sheet layout. Columns are matched by HEADER
NAME (case/space-insensitive), not position, so the importer survives column
reordering. Each field
accepts a tuple of labels, so a sheet re-exported with a renamed column keeps
importing; to support a differently-shaped sheet, add its label here and the
pipeline needs no other change.
"""

import uuid
from collections.abc import Container, Mapping, Sequence

from expense.currencies import SUPPORTED_CURRENCIES

#: Worksheet that holds the transaction rows. Matched case-insensitively —
#: see ``reader.read_workbook``.
SHEET_NAME = "Data"

#: Canonical field -> the normalized header labels it accepts, best first.
#: The first entry is the canonical spelling and is what the missing-column
#: error names. No two fields may share a label: `title` takes `description`
#: while the `description` field is fed by `notas`, and both can coexist on
#: one sheet.
FIELD_HEADERS = {
    "title": ("descripcion", "description", "titulo"),
    "category": ("category", "categoria"),
    "hashtag": ("hashtag",),
    "date": ("fecha",),
    "amount": ("monto",),
    "account": ("cuenta",),
    "currency": ("moneda",),
    "description": ("notas",),
    "statement_line": ("cod_eecc",),
}

#: Every field except ``description`` and ``statement_line`` must be present in
#: the header row. A sheet with no ``COD_EECC`` column imports every row as a
#: movement of its own, with no statement line.
REQUIRED_FIELDS = frozenset(FIELD_HEADERS) - {"description", "statement_line"}

#: Currencies the engine accepts — see expense/currencies.py for the
#: schema-lock provenance.
VALID_CURRENCIES = frozenset(SUPPORTED_CURRENCIES)

#: Deterministic-id namespace. DO NOT CHANGE — changing it breaks re-run dedup
#: (the same sheet must always produce the same transaction ids).
IMPORT_NAMESPACE = uuid.UUID("6f8a1e2c-3b4d-5e6f-7a8b-9c0d1e2f3a4b")


def normalize_header(label: object) -> str:
    """Header cell -> its match key: casefolded, every run of whitespace
    collapsed to one space.

    **The one normaliser for both importers** — `bank_import/parse.py` imports
    this rather than keeping its own. Two implementations that disagree on, say,
    doubled interior spaces (`Numero  de  Operacion`) make a header match on one
    importer and silently go missing on the other.
    """
    return " ".join(str(label).split()).casefold() if label is not None else ""


def match_headers(
    headers: list[object],
    field_headers: Mapping[str, Sequence[str]],
    required: Container[str],
) -> tuple[dict[str, int], list[str]]:
    """Canonical field -> column index, plus the canonical labels of any
    required field with no column.

    **The one header matcher for both importers**, for the reason
    `normalize_header` above is the one normaliser: the two spelled out the
    same nested loop, and a fix to how a label is matched has to land in both
    or it has not landed. The sheet layouts stay apart — each importer owns its
    own `FIELD_HEADERS` and `REQUIRED_FIELDS`, which is where they genuinely
    differ — and so does the refusal, because the two raise different
    exceptions with different wording. This returns what is missing; the
    caller decides what to say about it.

    Labels are matched best-first: the first label a field lists that appears
    in the header row wins, so a sheet carrying both an old and a new spelling
    resolves to the preferred one rather than to whichever came first.
    """
    normalized = [normalize_header(h) for h in headers]
    index: dict[str, int] = {}
    for field, labels in field_headers.items():
        for label in labels:
            if label in normalized:
                index[field] = normalized.index(label)
                break
    missing = sorted(field_headers[f][0] for f in field_headers if f in required and f not in index)
    return index, missing
