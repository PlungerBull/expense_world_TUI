"""Pure parsing: RawRow -> ParsedRow | SkippedRow. No I/O, no HTTP.

Handles Excel serial dates, decimal->signed-cents conversion (float-artifact
safe via Decimal), and currency validation. A T.C. (tipo de cambio) column, if
present, is ignored — the engine converts currency at read time and rejects
per-row rates.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from expense.import_ import mapping
from expense.import_.reader import RawRow, SheetData
from expense.quickadd.money import parse_amount

EXCEL_EPOCH = date(1899, 12, 30)

#: The serial day-numbers ``date`` can actually represent, derived from the
#: epoch rather than guessed. A numeric cell that is not a date at all — a
#: phone number, ``1e309`` — lands in the date column often enough that an
#: unbounded serial is a real hazard: ``timedelta`` and ``int(float(...))``
#: raise OverflowError, which is not ValueError and would abort the whole
#: import instead of skipping one row as ``bad-date``.
MIN_EXCEL_SERIAL = (date.min - EXCEL_EPOCH).days
MAX_EXCEL_SERIAL = (date.max - EXCEL_EPOCH).days


@dataclass(frozen=True)
class ParsedRow:
    line: int
    title: str
    category: str
    hashtag: str
    date_iso: str
    amount_cents: int
    currency: str
    account: str
    description: str | None
    #: The row's ``COD_EECC``, trimmed, or None when the cell is blank or the
    #: sheet has no such column. It only groups: rows sharing one are the parts
    #: of one movement (``plan.build_plan``), and it is never sent or stored.
    group_code: str | None = None


@dataclass(frozen=True)
class OpeningRow:
    """A SALDO INICIAL row — routed to POST /accounts/{id}/opening-balance.

    Detected by title (case/whitespace-insensitive). Category and hashtag are
    deliberately absent: the engine assigns the @Opening system category, and
    spreadsheets typically leave those cells blank on opening rows. So is the
    ``COD_EECC``: an opening balance is a movement of its own, never a part.
    """

    line: int
    title: str
    account: str
    currency: str
    date_iso: str
    amount_cents: int


@dataclass(frozen=True)
class SkippedRow:
    line: int
    reason: str
    detail: str = ""
    #: The row's ``COD_EECC``, when the parse skipped it: a split transaction
    #: missing one of its rows waits for it (``plan.build_plan``).
    group_code: str | None = None


#: Titles that mark a row as an opening balance, normalized via
#: ``_normalize_title`` (casefold + collapsed whitespace).
OPENING_TITLES = frozenset({"saldo inicial"})

#: Categories that mark a row as an opening balance. Sheets disagree on which
#: column carries the marker — some title the row "Saldo Inicial", others give
#: it a descriptive title and file it under a SALDO INICIAL category. Either
#: marker routes the row to the opening-balance endpoint; the category itself
#: is then discarded (the engine assigns @Opening), so the marker never becomes
#: a real user category.
OPENING_CATEGORIES = frozenset({"saldo inicial"})


def _normalize_title(title: str) -> str:
    return " ".join(title.split()).casefold()


def is_opening_title(title: str) -> bool:
    return _normalize_title(title) in OPENING_TITLES


def is_opening_category(category: str | None) -> bool:
    return category is not None and _normalize_title(category) in OPENING_CATEGORIES


class ImportFormatError(Exception):
    """The header row is missing one or more required columns."""


def build_column_index(headers: list[object]) -> dict[str, int]:
    """Map each canonical field to its column index by matching header labels."""
    index, missing = mapping.match_headers(headers, mapping.FIELD_HEADERS, mapping.REQUIRED_FIELDS)
    if missing:
        found = ", ".join(str(h) for h in headers if h is not None)
        raise ImportFormatError(
            f"Spreadsheet is missing required column(s): {', '.join(missing)}. "
            f"Found headers: {found}"
        )
    return index


def _clean(value: object) -> str | None:
    """Trim a cell; treat ``''`` and the literal ``'None'`` as empty."""
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.casefold() == "none":
        return None
    return s


def serial_to_iso(serial: object) -> str:
    """Excel serial day number -> ``YYYY-MM-DD`` (epoch 1899-12-30).

    ValueError for a serial outside the representable range, so a cell that is
    a number but not a date is one skipped row like any other bad date.
    """
    days = int(float(serial))
    if not MIN_EXCEL_SERIAL <= days <= MAX_EXCEL_SERIAL:
        raise ValueError(f"Excel serial out of range: {days}")
    return (EXCEL_EPOCH + timedelta(days=days)).isoformat()


def to_iso_date(value: object) -> str | None:
    """Coerce a date cell to ``YYYY-MM-DD``.

    Handles datetime/date objects, Excel serial day-numbers (int, float, or a
    numeric string), and ISO-formatted **text** cells (``2022-12-01`` or
    ``2022-12-01 10:30``). The text branch is why a column typed as text still
    imports instead of being dropped as ``bad-date``. Numeric-string serials
    (e.g. ``"46170"``) fail ISO parsing and fall through to the serial path,
    which preserves their existing handling.
    """
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        text = value.strip()
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(text).date().isoformat()
        except ValueError:
            pass
    try:
        return serial_to_iso(value)
    except (TypeError, ValueError, OverflowError):
        # OverflowError is NOT a ValueError: `int(float("1e309"))` and a
        # `timedelta` past date.max both raise it, and letting it out would
        # take down the import over a single unreadable cell.
        return None


def amount_to_cents(value: object) -> int | None:
    """An amount cell -> signed integer cents, or None when it is not an amount.

    A cell goes through the typed fields' own
    reader, ``parse_amount``, as its text: a number cell's text is its value
    (``-132.80000000000001`` -> ``-13280``, float-artifact safe via Decimal),
    and a text cell reads as typed — ``13,853.20`` is 1385320, while
    ``13.853,20``, ``nan``, ``inf`` and ``Infinity`` (as text or as a float
    cell) are not amounts. A blank cell is not one either.
    """
    if value is None:
        return None
    return parse_amount(str(value))


def parse_row(raw: RawRow, index: dict[str, int]) -> ParsedRow | OpeningRow | SkippedRow:
    def cell(field: str) -> object:
        i = index.get(field)
        if i is None or i >= len(raw.cells):
            return None
        return raw.cells[i]

    group_code = _clean(cell("group_code"))

    def skip(reason: str, detail: str = "") -> SkippedRow:
        return SkippedRow(raw.line, reason, detail, group_code)

    title = _clean(cell("title"))
    account = _clean(cell("account"))
    category = _clean(cell("category"))
    hashtag = _clean(cell("hashtag"))
    currency_raw = _clean(cell("currency"))

    if title is None:
        return skip("missing-title")
    opening = is_opening_title(title) or is_opening_category(category)
    if account is None:
        return skip("missing-account")
    # Opening rows skip the category/hashtag requirement — the engine assigns
    # the @Opening system category, and sheets leave those cells blank.
    if not opening and category is None:
        return skip("missing-category")
    if not opening and hashtag is None:
        return skip("missing-hashtag")
    if currency_raw is None:
        return skip("missing-currency")

    currency = currency_raw.upper()
    if currency not in mapping.VALID_CURRENCIES:
        return skip("unknown-currency", currency)

    date_iso = to_iso_date(cell("date"))
    if date_iso is None:
        return skip("bad-date", str(cell("date")))

    amount_cents = amount_to_cents(cell("amount"))
    if amount_cents is None:
        return skip("bad-amount", str(cell("amount")))
    if amount_cents == 0:
        return skip("zero-amount")

    if opening:
        return OpeningRow(
            line=raw.line,
            title=title,
            account=account,
            currency=currency,
            date_iso=date_iso,
            amount_cents=amount_cents,
        )

    return ParsedRow(
        line=raw.line,
        title=title,
        category=category,
        hashtag=hashtag,
        date_iso=date_iso,
        amount_cents=amount_cents,
        currency=currency,
        account=account,
        description=_clean(cell("description")),
        group_code=group_code,
    )


def parse_sheet(
    sheet: SheetData,
) -> tuple[list[ParsedRow], list[OpeningRow], list[SkippedRow]]:
    """Parse every data row. Fully-empty rows are ignored (not reported)."""
    index = build_column_index(sheet.headers)
    parsed: list[ParsedRow] = []
    openings: list[OpeningRow] = []
    skipped: list[SkippedRow] = []
    for raw in sheet.rows:
        if all(_clean(c) is None for c in raw.cells):
            continue
        result = parse_row(raw, index)
        if isinstance(result, ParsedRow):
            parsed.append(result)
        elif isinstance(result, OpeningRow):
            openings.append(result)
        else:
            skipped.append(result)
    return parsed, openings, skipped
