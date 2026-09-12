"""The bank importer's pure halves: the parser and the matcher.

Shapes come from the two real BCP downloads of 2026-09-12 (docs/mockups/
expense-world-bank-import.html): a current-account export with `Numero de
Operacion` and `11/09/2026` dates, and a card export with `2026-09-11` dates,
mixed S/ and $, no operation number, and padded merchant descriptors.
"""

from expense.bank_import.match import (
    RULE_NEAR_DAY_AMOUNT,
    RULE_NEAR_DAY_TITLE,
    RULE_OPERATION,
    RULE_SAME_DAY_TITLE,
    LedgerRow,
    match_rows,
)
from expense.bank_import.parse import (
    BankFormatError,
    BankRow,
    clean_title,
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
    return BankRow(line, date_iso, title, title, currency, cents, code)


def _ledger(ident, date_iso, cents, title, *, account="sig-pen", code=None) -> LedgerRow:
    return LedgerRow(ident, account, date_iso, cents, title, code)


# ---- title cleaning ---------------------------------------------------------
def test_clean_title_cuts_the_padding_after_a_short_merchant():
    assert clean_title("EDO SUSHI BAR             LI") == "EDO SUSHI BAR"
    assert clean_title("Google One             650-2") == "Google One"


def test_clean_title_cuts_at_the_field_boundary_when_the_merchant_fills_it():
    assert clean_title("LIDERMAN OUTLET AREQUI ICA           PE") == "LIDERMAN OUTLET AREQUI"
    assert clean_title("T6168 MAP AQP PORONGOC AREQU") == "T6168 MAP AQP PORONGOC"


def test_clean_title_leaves_a_merchant_that_overruns_the_field_whole():
    """No space on the boundary → not a boundary. Cutting mid-word would be worse."""
    assert clean_title("Plus Ultra Lineas Aereas  00") == "Plus Ultra Lineas Aereas"


def test_clean_title_leaves_current_account_labels_alone():
    assert clean_title("TRAN.CEL.BM.") == "TRAN.CEL.BM."
    assert clean_title("TRAN.CTAS.TERC.BM") == "TRAN.CTAS.TERC.BM"
    assert clean_title("  IZI*Fitrex ") == "IZI*Fitrex"


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
        ("2026-09-11", "Plus Ultra Lineas Aereas", "USD", -146887, None),
        ("2026-09-11", "EDO SUSHI BAR", "PEN", -4900, None),
        ("2026-08-16", "PAGO BANCA MOVIL", "PEN", 149019, None),
    ]
    assert rows[1].raw_title == "EDO SUSHI BAR             LI"  # kept for the description


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


# ---- matching ---------------------------------------------------------------
def test_operation_code_decides_matched_or_not():
    rows = [
        _bank(2, "2026-09-10", "TRAN.CEL.BM.", -6000, code="03144753"),
        _bank(3, "2026-09-10", "TRAN.CEL.BM.", -6000, code="99999999"),
    ]
    # An identical row sits in the ledger with the FIRST code: only that one
    # matches; the second is new even though every other field agrees, because
    # the code has spoken.
    ledger = [_ledger("t1", "2026-09-10", -6000, "TRAN.CEL.BM.", code="03144753")]
    verdicts, _ = match_rows(rows, LEGS, ledger)
    assert (verdicts[0].rule, verdicts[0].ledger_id) == (RULE_OPERATION, "t1")
    assert verdicts[1].new


def test_same_day_and_title_beats_the_looser_rules():
    rows = [_bank(2, "2026-08-18", "SHIMAYA RAMEN", -9600)]
    ledger = [
        _ledger("near", "2026-08-17", -9600, "shimaya ramen"),
        _ledger("exact", "2026-08-18", -9600, "Shimaya Ramen"),
    ]
    verdicts, _ = match_rows(rows, LEGS, ledger)
    assert (verdicts[0].rule, verdicts[0].ledger_id) == (RULE_SAME_DAY_TITLE, "exact")


def test_a_day_either_side_with_the_title_is_the_third_rule():
    rows = [_bank(2, "2026-08-18", "PCH AREQUIPA", -3940)]
    ledger = [_ledger("t1", "2026-08-19", -3940, "PCH AREQUIPA")]
    verdicts, _ = match_rows(rows, LEGS, ledger)
    assert (verdicts[0].rule, verdicts[0].ledger_id) == (RULE_NEAR_DAY_TITLE, "t1")


def test_amount_only_catches_a_hand_logged_row_under_its_own_title():
    """The row typed in the LOG bar as `fitrex` on the day before."""
    rows = [_bank(2, "2026-09-10", "IZI*Fitrex", -27390)]
    ledger = [_ledger("t1", "2026-09-09", -27390, "fitrex")]
    verdicts, _ = match_rows(rows, LEGS, ledger)
    assert (verdicts[0].rule, verdicts[0].ledger_id) == (RULE_NEAR_DAY_AMOUNT, "t1")


def test_amount_only_prefers_the_exact_day_over_a_neighbour():
    rows = [_bank(2, "2026-09-10", "X", -5000)]
    ledger = [
        _ledger("monday", "2026-09-09", -5000, "a"),
        _ledger("tuesday", "2026-09-10", -5000, "b"),
    ]
    verdicts, _ = match_rows(rows, LEGS, ledger)
    assert verdicts[0].ledger_id == "tuesday"


def test_the_count_rule_three_in_the_file_one_in_the_ledger_means_two_new():
    rows = [_bank(n, "2026-09-07", "APPARKA MALL AVENTURA", -350) for n in (2, 3, 4)]
    ledger = [_ledger("t1", "2026-09-07", -350, "apparka")]
    verdicts, excess = match_rows(rows, LEGS, ledger)
    assert [v.new for v in verdicts] == [False, True, True]
    assert excess == []


def test_two_rides_at_one_fare_on_one_day_are_two_rows():
    """The reason title sits before amount-only: same fare, different merchant."""
    rows = [
        _bank(2, "2026-09-11", "DLC*RIDES", -1290),
        _bank(3, "2026-09-11", "IZI*TAXI", -1290),
    ]
    ledger = [_ledger("taxi", "2026-09-11", -1290, "IZI*TAXI")]
    verdicts, _ = match_rows(rows, LEGS, ledger)
    assert verdicts[0].new  # the ride
    assert verdicts[1].ledger_id == "taxi"  # the taxi took its own row, not the ride's


def test_a_ledger_row_is_claimed_once():
    rows = [_bank(2, "2026-09-11", "A", -100), _bank(3, "2026-09-11", "A", -100)]
    ledger = [_ledger("t1", "2026-09-11", -100, "A")]
    verdicts, _ = match_rows(rows, LEGS, ledger)
    assert [v.ledger_id for v in verdicts] == ["t1", None]


def test_currency_picks_the_leg_and_the_ledger_is_per_account():
    rows = [
        _bank(2, "2026-09-09", "APPLE.COM/BILL", -2117, currency="USD"),
        _bank(3, "2026-09-09", "APPLE.COM/BILL", -2117, currency="PEN"),
    ]
    # The USD row is in the USD account already; the PEN twin is not.
    ledger = [_ledger("usd", "2026-09-09", -2117, "APPLE.COM/BILL", account="sig-usd")]
    verdicts, _ = match_rows(rows, LEGS, ledger)
    assert verdicts[0].account_id == "sig-usd" and verdicts[0].ledger_id == "usd"
    assert verdicts[1].account_id == "sig-pen" and verdicts[1].new


def test_excess_names_the_group_where_the_ledger_holds_more_than_the_file():
    rows = [_bank(2, "2026-08-18", "DAJOYA SAC", -350)]
    ledger = [
        _ledger("t1", "2026-08-18", -350, "DAJOYA SAC"),
        _ledger("t2", "2026-08-18", -350, "apparka"),
    ]
    verdicts, excess = match_rows(rows, LEGS, ledger)
    assert not verdicts[0].new
    assert len(excess) == 1
    e = excess[0]
    assert (e.date_iso, e.amount_cents, e.ledger_count, e.file_count) == ("2026-08-18", -350, 2, 1)
    assert e.account_name == "BCP Signature PEN"
