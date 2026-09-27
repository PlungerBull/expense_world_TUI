"""The bank importer's pure halves: the parser, and the engine request/response.

Shapes come from two real BCP downloads: a current-account export with `Numero de
Operacion` and `11/09/2026` dates, and a card export with `2026-09-11` dates,
mixed S/ and $, no operation number, and padded merchant descriptors. The
response shape is engine-spec `POST /transactions/import`.
"""

import pytest

from expense.bank_import.engine import (
    IMPORT_FLOOR,
    IncompleteAnswer,
    Placed,
    excess_groups,
    match_label,
    placements,
    request_body,
    row_refusals,
    sealed_accounts,
    sent_rows,
    split_floor,
)
from expense.bank_import.parse import (
    BankFormatError,
    BankRow,
    parse_bank_sheet,
    parse_date,
    parse_operation,
)
from expense.import_.reader import RawRow, SheetData

CARD_HEADERS = ["Fecha", "Descripcion", "Moneda", "Monto"]
ACCOUNT_HEADERS = ["Fecha", "Descripcion", "Moneda", "Monto", "Numero de Operacion"]

LEGS = {"PEN": ("sig-pen", "BCP Signature PEN"), "USD": ("sig-usd", "BCP Signature USD")}


def _sheet(headers, *rows) -> SheetData:
    return SheetData(headers=headers, rows=[RawRow(i + 2, list(r)) for i, r in enumerate(rows)])


def _bank(line, date_iso, title, cents, *, currency="PEN", code=None) -> BankRow:
    return BankRow(line, date_iso, title, currency, cents, code)


def _result(ident, outcome="new", *, rule=None, ledger_id=None, code=None, sealed_by=None) -> dict:
    return {
        "id": ident,
        "outcome": outcome,
        "rule": rule,
        "ledger_id": ledger_id,
        "backfill_code": code,
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
                _result(sent[1].id, "matched", rule="same_day", ledger_id="t1", code="00000009"),
                _result(sent[2].id, "sealed", sealed_by="r1"),
            ]
        },
        sent,
    )
    assert [p.sent.row.line for p in placed] == [2, 3, 4]
    assert [p.outcome for p in placed] == ["new", "matched", "sealed"]
    assert sealed_accounts(placed) == ["sig-pen"]


def test_each_outcome_and_rule_has_its_words():
    sent = _sent()

    def label(**kw):
        return match_label(Placed(sent=sent[0], **kw), {"r1": "September 2026"})

    base = {"rule": None, "ledger_id": None, "backfill_code": None, "sealed_by": None}
    assert label(**{**base, "outcome": "new"}) == "new"
    matched = {**base, "outcome": "matched", "ledger_id": "t1"}
    assert label(**{**matched, "rule": "operation_code"}) == "in ledger · operation"
    assert label(**{**matched, "rule": "same_day"}) == "in ledger · same day"
    assert label(**{**matched, "rule": "adjacent_day"}) == "in ledger · ± 1 day"
    coded = {**matched, "rule": "adjacent_day", "backfill_code": "1"}
    assert label(**coded) == "in ledger · ± 1 day · +code"
    sealed = {**base, "outcome": "sealed", "sealed_by": "r1"}
    assert label(**sealed) == "closed · September 2026"
    assert label(**{**sealed, "sealed_by": "gone"}) == "closed · a closed period"


def test_excess_is_signed_by_direction_and_named_by_leg():
    groups = excess_groups(
        {
            "excess": [
                {
                    "account_id": "sig-pen",
                    "date": "2026-09-07",
                    "amount_cents": 350,
                    "transaction_type": 1,
                    "file_count": 1,
                    "ledger_count": 2,
                    "unclaimed_ledger_ids": ["t2"],
                },
                {
                    "account_id": "sig-usd",
                    "date": "2026-09-08",
                    "amount_cents": 100,
                    "transaction_type": 2,
                    "file_count": 1,
                    "ledger_count": 2,
                    "unclaimed_ledger_ids": ["t3"],
                },
            ]
        },
        {"sig-pen": "BCP Signature PEN", "sig-usd": "BCP Signature USD"},
    )
    assert [(g.account_name, g.amount_cents, g.unclaimed) for g in groups] == [
        ("BCP Signature PEN", -350, 1),
        ("BCP Signature USD", 100, 1),
    ]


def test_a_refusal_names_the_files_line_not_the_engines_index():
    sent = _sent()
    refusals = row_refusals({"rows.2.date": "Must not be in the future.", "rows": "odd"}, sent)
    assert refusals == [(4, "date", "Must not be in the future."), (None, "rows", "odd")]


# ---- an operation code the bank never issued --------------------------------
def test_operation_refuses_booleans_and_fractions():
    """`True` must not stringify to "True", nor `12345.67` truncate to
    "12345". Either would be matched against the ledger and then WRITTEN onto
    a transaction, where the engine's per-account UNIQUE (`sql/039`) makes the
    invented code permanent."""
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
