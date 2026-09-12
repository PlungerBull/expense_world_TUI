"""The bank's sheet → one BankRow per line. Pure: no I/O, no HTTP.

Read from the two real BCP downloads of 2026-09-12 (docs/mockups/
expense-world-bank-import.html): a sheet named `data`, columns Fecha,
Descripcion, Moneda, Monto and — on a current-account export only — Numero de
Operacion. Dates come as `11/09/2026` on one export and `2026-09-11` on the
other; currency as `S/` or `$`; amounts as signed numbers, outflows negative,
which is the engine's own sign convention so nothing is flipped here.

Columns are matched by header name, case- and whitespace-insensitively, the
way expense/import_/mapping.py does for the personal sheet — one tolerant
mapping covers both bank files, and a second bank's export is a label added
here, not a module.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from expense.currencies import SUPPORTED_CURRENCIES
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

#: Where a card descriptor's merchant field ends. The bank pads the merchant
#: to this width and appends city and country; a space exactly here is the
#: field boundary, and the same descriptor with a shorter merchant shows the
#: boundary as a run of spaces instead. Both cases are handled by
#: `clean_title`; a merchant that fills the field with no space at the
#: boundary (an airline name of 24 letters) is left whole rather than cut
#: mid-word — the raw text is kept in the description regardless.
MERCHANT_WIDTH = 23

_DDMMYYYY = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")
_RUN_OF_SPACES = re.compile(r"\s{2,}")


@dataclass(frozen=True)
class BankRow:
    """One movement as the bank reported it, in the engine's terms."""

    line: int
    date_iso: str
    title: str
    raw_title: str
    currency: str
    amount_cents: int  # signed: negative = outflow, as the engine wants it
    operation_code: str | None


@dataclass(frozen=True)
class BadRow:
    """A line the parser could not read. Listed, never guessed."""

    line: int
    reason: str


class BankFormatError(Exception):
    """The header row is missing a required column."""


def normalize_header(label: object) -> str:
    return " ".join(str(label).split()).casefold() if label is not None else ""


def header_index(headers: list[object]) -> dict[str, int]:
    """Field → column index, or BankFormatError naming what is missing."""
    normalized = [normalize_header(h) for h in headers]
    index: dict[str, int] = {}
    for field, labels in FIELD_HEADERS.items():
        for label in labels:
            if label in normalized:
                index[field] = normalized.index(label)
                break
    missing = REQUIRED_FIELDS - index.keys()
    if missing:
        wanted = ", ".join(sorted(FIELD_HEADERS[m][0] for m in missing))
        found = ", ".join(repr(h) for h in headers if h is not None) or "(none)"
        raise BankFormatError(
            f"The sheet is missing required column(s): {wanted}. Found headers: {found}"
        )
    return index


def clean_title(raw: str) -> str:
    """The merchant part of a card descriptor; a current-account label untouched.

    `LIDERMAN OUTLET AREQUI ICA           PE` → `LIDERMAN OUTLET AREQUI`.
    `EDO SUSHI BAR             LI` → `EDO SUSHI BAR`.
    `TRAN.CEL.BM.` → `TRAN.CEL.BM.`.

    Two cuts, in order: at the first run of two or more spaces (the padding
    after a short merchant), then at the space on the merchant field's
    boundary when the merchant filled it exactly. Inner single spaces are the
    merchant's own and stay.
    """
    text = raw.strip()
    head = _RUN_OF_SPACES.split(text, maxsplit=1)[0]
    if len(head) > MERCHANT_WIDTH and head[MERCHANT_WIDTH - 1] == " ":
        head = head[: MERCHANT_WIDTH - 1]
    return " ".join(head.split())


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
        cents = Decimal(text).scaleb(2)
    except (ArithmeticError, ValueError):
        return None
    return int(cents.to_integral_value(rounding=ROUND_HALF_UP))


def parse_operation(value: object) -> str | None:
    """The bank's number as text, zero-padded back to 8 when a cell lost its
    leading zeros to a numeric type. Blank → None."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
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
                title=clean_title(raw_title),
                raw_title=raw_title,
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
