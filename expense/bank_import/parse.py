"""The bank's sheet → one BankRow per line. Pure: no I/O, no HTTP.

Read from the two real BCP downloads: a sheet named `data`, columns Fecha,
Descripcion, Moneda, Monto and — on a current-account export only — Numero de
Operacion. Dates come as `11/09/2026` on one export and `2026-09-11` on the
other; currency as `S/` or `$`; amounts as signed numbers, outflows negative,
which is the engine's own sign convention so nothing is flipped here.

Columns are matched by header name, case- and whitespace-insensitively, using
expense/import_/mapping.py's own `normalize_header` — one tolerant mapping
covers both bank files, and a second bank's export is a label added here, not
a module. That normaliser is *imported*, not copied, so the two importers
cannot drift apart on a header like `Numero  de  Operacion`.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from expense.currencies import MINOR_UNIT_SCALE, SUPPORTED_CURRENCIES
from expense.import_.mapping import match_headers
from expense.import_.parse import to_iso_date
from expense.import_.reader import SheetData

#: The bank's sheet name, matched case-insensitively by the reader.
SHEET_NAME = "data"

#: Canonical field → the normalized header labels it accepts, best first.
FIELD_HEADERS: dict[str, tuple[str, ...]] = {
    "date": ("fecha", "date"),
    "title": ("descripcion", "descripción", "description"),
    "currency": ("moneda", "currency"),
    "amount": ("monto", "importe", "amount"),
    "operation": ("numero de operacion", "número de operación", "operacion", "operation"),
}

#: Every field except the operation number must be present.
REQUIRED_FIELDS = frozenset(FIELD_HEADERS) - {"operation"}

#: What the bank writes in the currency column, folded → ISO code.
CURRENCY_LABELS = {
    "s/": "PEN",
    "s/.": "PEN",
    "soles": "PEN",
    "pen": "PEN",
    "$": "USD",
    "us$": "USD",
    "usd": "USD",
    "dolares": "USD",
    "dólares": "USD",
}

_DDMMYYYY = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")


@dataclass(frozen=True)
class BankRow:
    """One movement as the bank reported it, in the engine's terms."""

    line: int
    date_iso: str
    #: The bank's descriptor with whitespace runs collapsed, nothing removed:
    #: `MAR DE COLAS           LIMA          PE` → `MAR DE COLAS LIMA PE`. The title is
    #: exactly what the bank sent.
    #: Why: docs/decisions.md "Bank downloads are matched against the ledger".
    title: str
    currency: str
    amount_cents: int  # signed: negative = outflow, as the engine wants it
    operation_code: str | None


@dataclass(frozen=True)
class BadRow:
    """A line the parser could not read. Listed, never guessed."""

    line: int
    reason: str


#: The bank's own spelling of each required column, keyed by the normalized
#: label `match_headers` reports as missing — what a refusal names.
COLUMN_TITLES = {
    "fecha": "Fecha",
    "descripcion": "Descripcion",
    "moneda": "Moneda",
    "monto": "Monto",
}


_COLUMN_ORDER = {label: i for i, label in enumerate(COLUMN_TITLES)}


class BankFormatError(Exception):
    """The header row is missing a required column.

    `missing` holds the bank's spelling of each absent column (`Fecha`) and
    `found` the sheet's own non-empty headers, for a screen that lays the two
    out on lines of their own; the message says both in one sentence.
    """

    def __init__(self, message: str, *, missing: list[str], found: list[str]) -> None:
        super().__init__(message)
        self.missing = missing
        self.found = found


def header_index(headers: list[object]) -> dict[str, int]:
    """Field → column index, or BankFormatError naming what is missing."""
    index, missing = match_headers(headers, FIELD_HEADERS, REQUIRED_FIELDS)
    if missing:
        present = [h for h in headers if h is not None and str(h).strip()]
        found = ", ".join(repr(h) for h in headers if h is not None) or "(none)"
        raise BankFormatError(
            f"The sheet is missing required column(s): {', '.join(missing)}. "
            f"Found headers: {found}",
            # in the bank's own column order, not the matcher's
            missing=[
                COLUMN_TITLES.get(label, label)
                for label in sorted(missing, key=lambda m: _COLUMN_ORDER.get(m, len(_COLUMN_ORDER)))
            ],
            found=[str(h).strip() for h in present],
        )
    return index


def parse_date(value: object) -> str | None:
    """`11/09/2026`, `2026-09-11`, a date/datetime cell or an Excel serial → ISO."""
    if isinstance(value, (datetime, date)):
        return to_iso_date(value)
    if isinstance(value, str):
        m = _DDMMYYYY.match(value)
        if m:
            day, month, year = (int(g) for g in m.groups())
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                return None
    return to_iso_date(value)


def parse_currency(value: object) -> str | None:
    if value is None:
        return None
    label = str(value).strip().casefold()
    code = CURRENCY_LABELS.get(label) or (
        label.upper() if label.upper() in SUPPORTED_CURRENCIES else None
    )
    return code


def parse_amount(value: object) -> int | None:
    """Signed decimal → signed cents, float-artifact safe; None when unreadable."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        text = str(value).strip().replace(",", "")
        cents = Decimal(text) * MINOR_UNIT_SCALE
    except (ArithmeticError, ValueError):
        return None
    return int(cents.to_integral_value(rounding=ROUND_HALF_UP))


def parse_operation(value: object) -> str | None:
    """The bank's number as text, zero-padded back to 8 when a cell lost its
    leading zeros to a numeric type. Blank → None.

    A boolean or a fractional number is **refused**, not coerced: `True` used
    to fall through and stringify to `"True"`, and `12345.67` truncated to
    `"12345"`. Either would then be matched against the ledger and written
    onto a transaction as an operation code the bank never issued — and the
    engine's per-account uniqueness of the code (contract: POST /v1/transactions)
    would make that invented code permanent.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        # `is_integer` also refuses inf and nan, which `int()` cannot convert.
        if isinstance(value, float) and not value.is_integer():
            return None
        return str(int(value)).zfill(8)
    text = str(value).strip()
    if not text or text.casefold() == "none":
        return None
    return text.zfill(8) if text.isdigit() and len(text) < 8 else text


def parse_bank_sheet(sheet: SheetData) -> tuple[list[BankRow], list[BadRow]]:
    """Every data row → a BankRow, or a BadRow saying why not.

    Raises BankFormatError when the header row lacks a required column.
    """
    index = header_index(sheet.headers)
    has_operation = "operation" in index
    rows: list[BankRow] = []
    bad: list[BadRow] = []

    def cell_of(raw, field: str) -> object:
        i = index.get(field)
        if i is None or i >= len(raw.cells):
            return None
        return raw.cells[i]

    for raw in sheet.rows:

        def cell(field: str, _raw=raw) -> object:  # bound per iteration, not late
            return cell_of(_raw, field)

        cells = [c for c in raw.cells if c is not None and str(c).strip() != ""]
        if not cells:
            continue  # a blank line at the bottom of the export

        date_iso = parse_date(cell("date"))
        if date_iso is None:
            bad.append(BadRow(raw.line, f'"{cell("date")}" is not a date'))
            continue
        raw_title = str(cell("title") or "").strip()
        if not raw_title:
            bad.append(BadRow(raw.line, "the row has no description"))
            continue
        currency = parse_currency(cell("currency"))
        if currency is None:
            bad.append(BadRow(raw.line, f'"{cell("currency")}" is not a currency'))
            continue
        amount = parse_amount(cell("amount"))
        if amount is None:
            bad.append(BadRow(raw.line, f'"{cell("amount")}" is not an amount'))
            continue
        if amount == 0:
            bad.append(BadRow(raw.line, "the amount is zero"))
            continue
        rows.append(
            BankRow(
                line=raw.line,
                date_iso=date_iso,
                title=" ".join(raw_title.split()),
                currency=currency,
                amount_cents=amount,
                operation_code=parse_operation(cell("operation")) if has_operation else None,
            )
        )

    # An operation number that appears twice in one file is the bank's
    # problem, not a duplicate to resolve: both lines are refused, by number.
    seen: dict[str, int] = {}
    kept: list[BankRow] = []
    for row in rows:
        code = row.operation_code
        if code is None:
            kept.append(row)
            continue
        if code in seen:
            twice = (
                f"operation {code} appears twice in this file — rows {seen[code]} and {row.line}"
            )
            bad.append(BadRow(row.line, twice))
            continue
        seen[code] = row.line
        kept.append(row)
    bad.sort(key=lambda b: b.line)
    return kept, bad
