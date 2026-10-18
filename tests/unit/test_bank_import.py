"""The bank importer's pure halves: the parser, and the engine request/response.

Shapes come from two real BCP downloads: a current-account export with `Numero de
Operacion` and `11/09/2026` dates, and a card export with `2026-09-11` dates,
mixed S/ and $, no operation number, and padded merchant descriptors. The
response shape is the contract's (contract: POST /v1/transactions/import).
"""

import pytest

from expense.bank_import.engine import (
    IMPORT_FLOOR,
    AnswerCounts,
    DayMismatch,
    IncompleteAnswer,
    Placed,
    UnclaimedLine,
    answer_counts,
    blocked_accounts,
    day_mismatches,
    placements,
    request_body,
    row_reason,
    row_refusals,
    sent_rows,
    split_floor,
)
from expense.bank_import.flow import AccountGroup, FileLine, Prepared, file_lines
from expense.bank_import.parse import (
    BankFormatError,
    BankRow,
    parse_bank_sheet,
    parse_date,
    parse_operation,
)
from expense.import_.reader import RawRow, SheetData
from tests.unit.helpers import import_part

CARD_HEADERS = ["Fecha", "Descripcion", "Moneda", "Monto"]
ACCOUNT_HEADERS = ["Fecha", "Descripcion", "Moneda", "Monto", "Numero de Operacion"]

LEGS = {"PEN": ("sig-pen", "BCP Signature PEN"), "USD": ("sig-usd", "BCP Signature USD")}


def _sheet(headers, *rows) -> SheetData:
    return SheetData(headers=headers, rows=[RawRow(i + 2, list(r)) for i, r in enumerate(rows)])


def _bank(line, date_iso, title, cents, *, currency="PEN", code=None) -> BankRow:
    return BankRow(line, date_iso, title, currency, cents, code)


def _result(
    ident,
    outcome="new",
    *,
    rule=None,
    line=None,
    code=None,
    retitled=None,
    redated=None,
    blocked_by=None,
    sealed_by=None,
) -> dict:
    return {
        "id": ident,
        "outcome": outcome,
        "rule": rule,
        "bank_line_id": line,
        "backfill_code": code,
        "retitled": retitled,
        "redated": redated,
        "redate_blocked_by": blocked_by,
        "sealed_by": sealed_by,
    }


# ---- cells ------------------------------------------------------------------
def test_dates_come_in_both_of_the_banks_spellings():
    assert parse_date("11/09/2026") == "2026-09-11"
    assert parse_date("2026-09-11") == "2026-09-11"
    assert parse_date("31/13/2026") is None


def test_operation_numbers_keep_their_leading_zeros():
    assert parse_operation("04330935") == "04330935"
    assert parse_operation(4330935) == "04330935"  # a cell that went numeric
    assert parse_operation("") is None and parse_operation(None) is None


def test_parse_sheet_reads_a_card_export():
    rows, bad = parse_bank_sheet(
        _sheet(
            CARD_HEADERS,
            ("2026-09-11", "Plus Ultra Lineas Aereas  00", "$", -1468.87),
            ("2026-09-11", "EDO SUSHI BAR             LI", "S/", -49),
            ("2026-08-16", "PAGO BANCA MOVIL", "S/", 1490.19),
        )
    )
    assert bad == []
    assert [(r.date_iso, r.title, r.currency, r.amount_cents, r.operation_code) for r in rows] == [
        ("2026-09-11", "Plus Ultra Lineas Aereas 00", "USD", -146887, None),
        ("2026-09-11", "EDO SUSHI BAR LI", "PEN", -4900, None),
        ("2026-08-16", "PAGO BANCA MOVIL", "PEN", 149019, None),
    ]


def test_the_title_is_the_banks_text_with_whitespace_collapsed():
    """Titles verbatim (decisions.md, bank downloads): nothing cut, only the padding runs folded."""
    rows, _ = parse_bank_sheet(
        _sheet(CARD_HEADERS, ("2026-09-11", "  MAR DE COLAS           LIMA          PE ", "S/", -1))
    )
    assert rows[0].title == "MAR DE COLAS LIMA PE"


def test_parse_sheet_reads_a_current_account_export_with_codes():
    rows, bad = parse_bank_sheet(
        _sheet(
            ACCOUNT_HEADERS,
            ("11/09/2026", "TRAN.CEL.BM.", "S/", -50, "04330935"),
            ("09/09/2026", "TRAN.CTAS.TERC.BM", "S/", 42, "00022409"),
        )
    )
    assert bad == []
    assert [r.operation_code for r in rows] == ["04330935", "00022409"]
    assert rows[0].amount_cents == -5000 and rows[1].amount_cents == 4200


def test_parse_sheet_refuses_bad_cells_and_keeps_going():
    rows, bad = parse_bank_sheet(
        _sheet(
            CARD_HEADERS,
            ("31/13/2026", "X", "S/", -1),
            ("2026-09-01", "", "S/", -1),
            ("2026-09-01", "Y", "€", -1),
            ("2026-09-01", "Z", "S/", "abc"),
            ("2026-09-01", "W", "S/", 0),
            ("2026-09-01", "OK", "S/", -1),
            (None, None, None, None),  # the blank trailing line an export leaves
        )
    )
    assert [r.title for r in rows] == ["OK"]
    assert [b.line for b in bad] == [2, 3, 4, 5, 6]
    assert "not a date" in bad[0].reason and "no description" in bad[1].reason
    assert "not a currency" in bad[2].reason and "not an amount" in bad[3].reason
    assert "zero" in bad[4].reason
    # each refused line keeps the cells that could be read, None for the rest
    assert [(b.date_iso, b.title, b.amount_cents) for b in bad] == [
        (None, "X", -100),
        ("2026-09-01", None, -100),
        ("2026-09-01", "Y", -100),
        ("2026-09-01", "Z", None),
        ("2026-09-01", "W", 0),
    ]


def test_parse_sheet_refuses_both_rows_of_a_repeated_operation_number():
    rows, bad = parse_bank_sheet(
        _sheet(
            ACCOUNT_HEADERS,
            ("11/09/2026", "A", "S/", -1, "00000001"),
            ("11/09/2026", "B", "S/", -2, "00000002"),
            ("11/09/2026", "C", "S/", -3, "00000001"),
        )
    )
    assert [r.title for r in rows] == ["A", "B"]
    assert len(bad) == 1 and "appears twice" in bad[0].reason and "rows 2 and 4" in bad[0].reason
    assert (bad[0].date_iso, bad[0].title, bad[0].amount_cents) == ("2026-09-11", "C", -300)


def test_missing_columns_are_named():
    try:
        parse_bank_sheet(_sheet(["Fecha", "Monto"]))
    except BankFormatError as exc:
        assert "descripcion" in str(exc) and "moneda" in str(exc)
    else:
        raise AssertionError("expected BankFormatError")


# ---- the floor --------------------------------------------------------------
def test_the_floor_is_2026_01_01_and_the_day_itself_goes():
    rows = [_bank(2, "2025-12-31", "OLD", -1), _bank(3, "2026-01-01", "NEW", -1)]
    kept, skipped = split_floor(rows)
    assert IMPORT_FLOOR.isoformat() == "2026-01-01"
    assert [r.line for r in kept] == [3] and [r.line for r in skipped] == [2]


# ---- the request --------------------------------------------------------------
def test_each_row_goes_on_its_currencys_leg_as_a_bare_day_with_the_banks_title():
    sent = sent_rows(
        [
            _bank(2, "2026-09-11", "EDO SUSHI BAR LI", -4900),
            _bank(3, "2026-09-09", "APPLE.COM/BILL", -2117, currency="USD"),
        ],
        LEGS,
    )
    body = request_body(sent, dry_run=True)
    assert body["dry_run"] is True
    first, second = body["rows"]
    assert first == {
        "id": sent[0].id,
        "account_id": "sig-pen",
        "date": "2026-09-11",
        "amount_cents": -4900,
        "title": "EDO SUSHI BAR LI",
    }
    assert second["account_id"] == "sig-usd" and second["date"] == "2026-09-09"
    assert "description" not in first and "operation_code" not in first
    assert sent[0].id != sent[1].id


def test_an_operation_code_is_sent_when_the_file_has_one():
    sent = sent_rows([_bank(2, "2026-09-11", "TRAN.CEL.BM.", -5000, code="04330935")], LEGS)
    assert request_body(sent, dry_run=False)["rows"][0]["operation_code"] == "04330935"
    assert request_body(sent, dry_run=False)["dry_run"] is False


# ---- the response -------------------------------------------------------------
def _sent():
    return sent_rows(
        [
            _bank(2, "2026-09-11", "A", -100),
            _bank(3, "2026-09-10", "B", -200, code="00000009"),
            _bank(4, "2026-09-09", "C", -300),
        ],
        LEGS,
    )


def test_response_rows_join_back_to_the_file_by_id():
    sent = _sent()
    placed = placements(
        {
            "rows": [
                _result(sent[0].id),
                _result(
                    sent[1].id,
                    "matched",
                    rule="same_day",
                    line="bl-1",
                    code="00000009",
                    retitled=True,
                ),
                _result(sent[2].id, "sealed", sealed_by="r1"),
            ]
        },
        sent,
    )
    assert [p.sent.row.line for p in placed] == [2, 3, 4]
    assert [p.outcome for p in placed] == ["new", "matched", "sealed"]


def test_a_matched_row_carries_its_bank_line_and_whether_it_was_retitled():
    """A `matched` row names the bank line it is and says whether the bank's
    title is written onto it; the other outcomes carry neither (null)."""
    sent = _sent()
    placed = placements(
        {
            "rows": [
                _result(sent[0].id, "matched", rule="operation_code", line="bl-1", retitled=True),
                _result(sent[1].id, "matched", rule="same_day", line="bl-2", retitled=False),
                _result(sent[2].id),
            ]
        },
        sent,
    )
    assert [(p.bank_line_id, p.retitled) for p in placed] == [
        ("bl-1", True),
        ("bl-2", False),
        (None, None),
    ]


def test_a_matched_row_carries_whether_its_line_moves_and_what_stops_it():
    """`redated` says the line moves to the bank's day; `redate_blocked_by`
    names the completed reconciliation that stops the move (contract:
    POST /v1/transactions/import); a row with neither keeps null."""
    sent = _sent()
    placed = placements(
        {
            "rows": [
                _result(sent[0].id, "matched", rule="operation_code", line="bl-1", redated=True),
                _result(
                    sent[1].id,
                    "matched",
                    rule="operation_code",
                    line="bl-2",
                    redated=False,
                    blocked_by="r9",
                ),
                _result(sent[2].id),
            ]
        },
        sent,
    )
    assert [(p.redated, p.redate_blocked_by) for p in placed] == [
        (True, None),
        (False, "r9"),
        (None, None),
    ]
    assert blocked_accounts(placed) == ["sig-pen"]


def _placed(**kw) -> Placed:
    base = {
        "outcome": "matched",
        "rule": "operation_code",
        "bank_line_id": "bl-1",
        "backfill_code": None,
        "retitled": False,
        "redated": False,
        "redate_blocked_by": None,
        "sealed_by": None,
    }
    return Placed(sent=_sent()[0], **{**base, **kw})


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        ({"outcome": "new", "rule": None, "bank_line_id": None}, (True, "New")),
        ({}, (True, "Already in the ledger")),
        ({"rule": "same_day"}, (True, "Already in the ledger")),
        ({"retitled": True}, (True, "Modified existing transaction")),
        ({"backfill_code": "00000009"}, (True, "Modified existing transaction")),
        ({"redated": True}, (True, "Modified existing transaction")),
        (
            {"redate_blocked_by": "r1", "retitled": True},
            (False, "Not moved: Septiembre 2026 is reconciled"),
        ),
        (
            {"redate_blocked_by": "gone"},
            (False, "Not moved: a reconciliation is reconciled"),
        ),
        ({"outcome": "sealed", "sealed_by": "r1", "rule": None}, (False, "Closed period")),
    ],
    ids=[
        "new",
        "in-ledger",
        "in-ledger-same-day",
        "took-title",
        "got-code",
        "moves",
        "move-stopped",
        "move-stopped-unnamed",
        "closed",
    ],
)
def test_each_answered_row_has_its_mark_and_reason(kw, expected):
    """✓ for a row in the ledger after the import, ✗ for one left out; a move
    a completed reconciliation stops is ✗, named, whatever else is written."""
    assert row_reason(_placed(**kw), {"r1": "Septiembre 2026"}) == expected


def test_day_mismatches_keep_both_signed_totals_and_name_the_leg():
    """Each reported day as the engine sends it: both totals signed (inflow
    positive, outflow negative), the unmatched file rows by index, and each
    unclaimed ledger line with its signed `net_cents` and its parts, the
    engine's whole transaction responses; the account named by its leg, or by
    its id when no leg is known."""
    t3 = import_part("t3", -5000, line="bl-3")
    t4a = import_part("t4a", -6000, account_id="sig-usd", line="bl-4", day="2026-09-08")
    t4b = import_part("t4b", -4000, account_id="sig-usd", line="bl-4", day="2026-09-08")
    mismatches = day_mismatches(
        {
            "day_mismatches": [
                {
                    "account_id": "sig-pen",
                    "date": "2026-09-07",
                    "file_net_cents": -10000,
                    "ledger_net_cents": -15000,
                    "unmatched_rows": [],
                    "unclaimed_lines": [
                        {"bank_line_id": "bl-3", "net_cents": -5000, "parts": [t3]}
                    ],
                },
                {
                    "account_id": "sig-usd",
                    "date": "2026-09-08",
                    "file_net_cents": 2500,
                    "ledger_net_cents": 0,
                    "unmatched_rows": [1, 3],
                    "unclaimed_lines": [
                        {"bank_line_id": "bl-4", "net_cents": -10000, "parts": [t4a, t4b]},
                    ],
                },
                {
                    "account_id": "elsewhere",
                    "date": "2026-09-09",
                    "file_net_cents": 0,
                    "ledger_net_cents": -700,
                    "unmatched_rows": [],
                    "unclaimed_lines": [],
                },
            ]
        },
        {"sig-pen": "BCP Signature PEN", "sig-usd": "BCP Signature USD"},
    )
    assert mismatches == [
        DayMismatch(
            account_id="sig-pen",
            account_name="BCP Signature PEN",
            date_iso="2026-09-07",
            file_net_cents=-10000,
            ledger_net_cents=-15000,
            unmatched_rows=(),
            unclaimed_lines=(UnclaimedLine("bl-3", -5000, (t3,)),),
        ),
        DayMismatch(
            account_id="sig-usd",
            account_name="BCP Signature USD",
            date_iso="2026-09-08",
            file_net_cents=2500,
            ledger_net_cents=0,
            unmatched_rows=(1, 3),
            unclaimed_lines=(UnclaimedLine("bl-4", -10000, (t4a, t4b)),),
        ),
        DayMismatch(
            account_id="elsewhere",
            account_name="elsewhere",
            date_iso="2026-09-09",
            file_net_cents=0,
            ledger_net_cents=-700,
            unmatched_rows=(),
            unclaimed_lines=(),
        ),
    ]


def test_a_day_with_equal_totals_keeps_its_unclaimed_line():
    """The engine reports a day whose totals agree when it holds a line no
    file row claimed (contract: POST /v1/transactions/import): the day is
    kept with both totals as sent, and its line with every part."""
    plus = import_part("t5a", 5000, line="bl-5")
    minus = import_part("t5b", -5000, line="bl-6")
    (day,) = day_mismatches(
        {
            "day_mismatches": [
                {
                    "account_id": "sig-pen",
                    "date": "2026-09-07",
                    "file_net_cents": -2590,
                    "ledger_net_cents": -2590,
                    "unmatched_rows": [],
                    "unclaimed_lines": [
                        {"bank_line_id": "bl-5", "net_cents": 5000, "parts": [plus]},
                        {"bank_line_id": "bl-6", "net_cents": -5000, "parts": [minus]},
                    ],
                }
            ]
        },
        {"sig-pen": "BCP Signature PEN"},
    )
    assert day.file_net_cents == day.ledger_net_cents == -2590
    assert day.unclaimed_lines == (
        UnclaimedLine("bl-5", 5000, (plus,)),
        UnclaimedLine("bl-6", -5000, (minus,)),
    )
    # the parts are the engine's responses, unchanged: a magnitude and a direction
    assert [(p["amount_cents"], p["transaction_type"]) for p in (plus, minus)] == [
        (5000, 2),
        (5000, 1),
    ]


def test_no_day_mismatches_is_an_empty_list():
    assert day_mismatches({"day_mismatches": []}, {}) == []


def test_the_engines_counts_include_retitled_and_redated():
    counts = answer_counts(
        {
            "counts": {
                "new": 2,
                "matched": 5,
                "sealed": 1,
                "backfilled": 3,
                "retitled": 4,
                "redated": 6,
            }
        }
    )
    assert counts == AnswerCounts(new=2, matched=5, sealed=1, backfilled=3, retitled=4, redated=6)


def test_a_refusal_names_the_files_line_not_the_engines_index():
    sent = _sent()
    refusals = row_refusals(
        {"rows.2.date": "Must not be in the future.", "rows.0": "Changed.", "rows": "odd"}, sent
    )
    assert refusals == [
        (4, "date", "Must not be in the future."),
        (2, None, "Changed."),  # a key naming the row alone
        (None, "rows", "odd"),
    ]


# ---- an operation code the bank never issued --------------------------------
def test_operation_refuses_booleans_and_fractions():
    """`True` must not stringify to "True", nor `12345.67` truncate to
    "12345". Either would be matched against the ledger and then WRITTEN onto
    a transaction, where the engine's per-account uniqueness of the code
    (contract: POST /v1/transactions) makes the invented code permanent."""
    assert parse_operation(True) is None
    assert parse_operation(False) is None
    assert parse_operation(12345.67) is None
    assert parse_operation(float("nan")) is None
    assert parse_operation(float("inf")) is None
    # a whole number that merely arrived as a float is still a code
    assert parse_operation(4330935.0) == "04330935"


def test_a_row_whose_operation_cell_is_junk_imports_without_a_code():
    """Refusing the code must not refuse the row — it just falls through to
    the content rules like every pre-column ledger row does."""
    rows, bad = parse_bank_sheet(
        _sheet(ACCOUNT_HEADERS, ["11/09/2026", "TRAN.CEL.BM.", "S/", -60, True])
    )
    assert bad == []
    assert rows[0].operation_code is None


def test_a_response_missing_a_row_fails_loudly():
    sent = _sent()
    with pytest.raises(IncompleteAnswer) as gap:
        placements({"rows": [_result(sent[0].id), _result(sent[2].id)]}, sent)
    assert [s.row.line for s in gap.value.missing] == [3]


def test_a_response_with_a_row_never_sent_fails_loudly():
    sent = _sent()
    rows = [_result(s.id) for s in sent] + [_result("stranger")]
    with pytest.raises(IncompleteAnswer) as gap:
        placements({"rows": rows}, sent)
    assert gap.value.unknown == ["stranger"]


def test_the_files_lines_come_back_whole_in_the_files_order():
    """Every line of the file, the answered rows, the ones under the floor and
    the refused ones interleaved by the file's own line, each with its mark
    and its reason."""
    rows, bad = parse_bank_sheet(
        _sheet(
            CARD_HEADERS,
            ("2026-09-11", "A", "S/", -1),
            ("2025-12-31", "OLD", "S/", -2),
            ("nope", "BAD", "S/", -3),
            ("2026-09-09", "B", "S/", -4),
        )
    )
    kept, before = split_floor(rows)
    group = AccountGroup("BCP", {"PEN": ("bcp-pen", "BCP PEN")})
    sent = sent_rows(kept, group.legs)
    prepared = Prepared("f.xlsx", group, rows, bad, before, sent)
    placed = placements({"rows": [_result(sent[0].id), _result(sent[1].id, "sealed")]}, sent)
    assert file_lines(prepared, placed, {}) == [
        FileLine(2, "2026-09-11", "A", -100, True, "New"),
        FileLine(3, "2025-12-31", "OLD", -200, False, "Before 2026"),
        FileLine(4, None, "BAD", -300, False, "Couldn't read the row"),
        FileLine(5, "2026-09-09", "B", -400, False, "Closed period"),
    ]
