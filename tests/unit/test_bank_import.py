"""The bank import's pure halves: what is sent, and how the engine's answer reads.

The app sends the bank's download whole and reads no cell of it; the answer's
shape is the contract's (contract: POST /v1/transactions/import), built here
by the fake engine's own builders in tests/unit/helpers.py.
"""

import ast
import base64
from pathlib import Path

import httpx
import pytest
import respx

from expense import config as config_module
from expense.bank_import.engine import (
    AnswerCounts,
    DayMismatch,
    Verdict,
    answer_counts,
    answer_rows,
    blocking_reconciliations,
    day_mismatches,
    preview_line,
    request_body,
)
from expense.bank_import.flow import (
    AccountPick,
    ImportRefused,
    account_picks,
    card_name,
    read_file,
    reconciliation_names,
)
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import (
    ORDERED_ALONE,
    error_response,
    import_answer,
    import_day,
    import_part,
    import_row,
    unclaimed_line,
)

PACKAGE = Path(__file__).resolve().parents[2] / "expense"


def _account(ident, name, currency="PEN", *, partner=None, **extra) -> dict:
    return {
        "id": ident,
        "name": name,
        "currency_code": currency,
        "is_person": False,
        "is_archived": False,
        "statement_code": "SIG" if partner else None,
        "statement_partner_id": partner,
        **extra,
    }


# ---- the request ----------------------------------------------------------------
def test_the_body_is_the_account_and_the_files_bytes_in_standard_base64():
    """Exactly the three keys, the file's bytes in the RFC 4648 alphabet,
    padded, with no line breaks, however long the file
    (contract: POST /v1/transactions/import, "Body")."""
    data = bytes(range(256)) * 200  # every byte, and longer than one base64 line
    body = request_body("sig-pen", data, dry_run=True)
    assert set(body) == {"dry_run", "account_id", "file"}
    assert (body["dry_run"], body["account_id"]) == (True, "sig-pen")
    assert "\n" not in body["file"] and body["file"].endswith("=")
    assert set(body["file"]) <= set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
    )
    assert base64.b64decode(body["file"], validate=True) == data
    assert request_body("sig-pen", b"x", dry_run=False)["dry_run"] is False


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_the_door_reads_no_cell_of_the_file():
    """Nothing the door runs opens a workbook: no spreadsheet library and no
    reader of the sheet import. The file goes to the engine as bytes."""
    door = [
        *(PACKAGE / "bank_import").glob("*.py"),
        PACKAGE / "tui" / "screens" / "bank_import.py",
        PACKAGE / "tui" / "screens" / "statement_upload.py",
    ]
    for path in door:
        imported = _imports(path)
        assert not any(
            name == "openpyxl" or name.startswith(("openpyxl.", "expense.import_"))
            for name in imported
        ), path


def test_a_file_is_read_as_its_bytes(tmp_path):
    path = tmp_path / "Movimientos.xlsx"
    path.write_bytes(b"PK\x03\x04 anything at all")
    assert read_file(path) == b"PK\x03\x04 anything at all"


def test_a_missing_file_is_refused_before_anything_is_sent(tmp_path):
    path = tmp_path / "gone.xlsx"
    with pytest.raises(ImportRefused) as refused:
        read_file(path)
    assert str(refused.value) == f"File not found: {path}"
    assert isinstance(refused.value.__cause__, FileNotFoundError)


def test_a_file_that_cannot_be_opened_is_refused_with_why(tmp_path):
    """A directory where a file should be: the disk's own reason."""
    with pytest.raises(ImportRefused) as refused:
        read_file(tmp_path)
    assert str(refused.value).startswith(f"Could not open {tmp_path}: ")
    assert isinstance(refused.value.__cause__, OSError)


# ---- the account picks ------------------------------------------------------------
def test_a_card_is_one_pick_paired_by_the_engine():
    """Two accounts the engine pairs through `statement_partner_id` are one
    pick, where the first of them stands; it names its soles account, whichever
    comes first (contract: GET /v1/accounts)."""
    picks = account_picks(
        [
            _account("sig-usd", "BCP Signature USD", "USD", partner="sig-pen"),
            _account("bcp-pen", "BCP PEN"),
            _account("sig-pen", "BCP Signature PEN", partner="sig-usd"),
        ]
    )
    assert [(p.name, p.currencies, p.account_id) for p in picks] == [
        ("BCP Signature", "PEN + USD", "sig-pen"),
        ("BCP PEN", "PEN", "bcp-pen"),
    ]
    card = picks[0]
    assert card.is_card and not picks[1].is_card
    assert card.account_names == {"sig-usd": "BCP Signature USD", "sig-pen": "BCP Signature PEN"}
    assert (card.currency_of("sig-usd"), card.currency_of("sig-pen")) == ("USD", "PEN")
    assert card.currency_of("someone-else") == "?"


def test_accounts_sharing_a_name_are_not_folded_without_the_engines_pairing():
    """A current account's download holds one currency: two accounts whose
    names differ only by their currency are two picks unless the engine pairs
    them."""
    picks = account_picks(
        [
            _account("ia-pen", "Interbank Ahorros PEN"),
            _account("ia-usd", "Interbank Ahorros USD", "USD"),
        ]
    )
    assert [(p.name, p.currencies) for p in picks] == [
        ("Interbank Ahorros PEN", "PEN"),
        ("Interbank Ahorros USD", "USD"),
    ]


def test_archived_accounts_people_and_a_partner_not_listed_are_left_out():
    picks = account_picks(
        [
            _account("old", "Retired PEN", is_archived=True),
            _account("ana", "Ana", is_person=True),
            # its partner is archived, so not read here: the account stands alone
            _account("half", "Visa PEN", partner="other-half"),
            {"name": "no id"},
        ]
    )
    assert [(p.name, p.accounts) for p in picks] == [("Visa PEN", (("half", "Visa PEN", "PEN"),))]


def test_a_cards_line_is_the_name_its_two_accounts_share():
    assert card_name(("a", "BCP Signature PEN", "PEN"), ("b", "BCP Signature USD", "USD")) == (
        "BCP Signature"
    )
    assert card_name(("a", "Visa", "PEN"), ("b", "Visa", "USD")) == "Visa"
    # names that share nothing: both, as the engine pairs them
    assert card_name(("a", "Visa Oro", "PEN"), ("b", "Dolares", "USD")) == "Visa Oro / Dolares"


def test_a_pick_with_no_soles_account_sends_its_first():
    pick = AccountPick("Euro", (("e1", "Euro A", "EUR"), ("e2", "Euro B", "USD")))
    assert pick.account_id == "e1"


# ---- the answer -----------------------------------------------------------------
def test_each_row_is_read_by_its_spreadsheet_row_and_signed():
    """A row's amount comes as a magnitude and a type; the app signs it with
    its one helper. A skipped row reads `0` with no type, and stays `0`."""
    answer = import_answer(
        [
            import_row(2, -1850, title="CAFE ANDINO"),
            import_row(3, 650000, title="PAGO PLANILLA", account_id="sig-usd"),
            import_row(7, 0, outcome="skipped", title=None),
        ]
    )
    rows = answer_rows(answer)
    assert [(r.row, r.amount_cents, r.title, r.outcome) for r in rows] == [
        (2, -1850, "CAFE ANDINO", "new"),
        (3, 650000, "PAGO PLANILLA", "new"),
        (7, 0, None, "skipped"),
    ]
    assert rows[1].account_id == "sig-usd" and rows[0].date_iso == "2026-09-07"


@pytest.mark.parametrize(
    ("keys", "verdict", "reason"),
    [
        ({}, Verdict.NEW, "New"),
        ({"outcome": "matched", "rule": "same_day"}, Verdict.IN_LEDGER, "Already in the ledger"),
        (
            {"outcome": "matched", "retitled": True},
            Verdict.MODIFIED,
            "Modified existing transaction",
        ),
        (
            {"outcome": "matched", "backfill_code": "00000009"},
            Verdict.MODIFIED,
            "Modified existing transaction",
        ),
        (
            {"outcome": "matched", "redated": True},
            Verdict.MODIFIED,
            "Modified existing transaction",
        ),
        (
            {"outcome": "matched", "redate_blocked_by": "r1", "retitled": True},
            Verdict.NOT_MOVED,
            "Not moved: Septiembre 2026 is reconciled",
        ),
        (
            {"outcome": "matched", "redate_blocked_by": "gone"},
            Verdict.NOT_MOVED,
            "Not moved: a reconciliation is reconciled",
        ),
        ({"outcome": "sealed", "sealed_by": "r1"}, Verdict.CLOSED, "Closed period"),
        ({"outcome": "skipped"}, Verdict.SKIPPED, "Skipped: amount 0"),
    ],
    ids=[
        "new",
        "in-ledger",
        "took-title",
        "got-operation-code",
        "moves",
        "move-stopped",
        "move-stopped-unnamed",
        "closed",
        "skipped",
    ],
)
def test_each_outcome_has_its_verdict_and_reason(keys, verdict, reason):
    """The verdict comes from the engine's outcome; a move a completed
    reconciliation stops is named, whatever else is written."""
    (row,) = answer_rows(import_answer([import_row(2, **keys)]))
    line = preview_line(row, {"r1": "Septiembre 2026"})
    assert (line.verdict, line.reason) == (verdict, reason)


def test_day_mismatches_keep_both_signed_totals_and_every_part_of_each_line():
    """Each reported day as the engine sends it: its account named, its two
    signed totals, the spreadsheet rows not found, and every part of each
    unclaimed line, a split line's parts together, in the engine's order."""
    split = [
        import_part("t-2a", -6000, line="bl-2", day="2026-09-08"),
        import_part("t-2b", -4000, line="bl-2", day="2026-09-08"),
    ]
    alone = import_part("t-3", 5000, line="bl-3", day="2026-09-08")
    answer = import_answer(
        [import_row(2)],
        day_mismatches=[
            import_day(
                "2026-09-08",
                -420,
                -5420,
                unmatched_rows=(5,),
                lines=(unclaimed_line("bl-2", split), unclaimed_line("bl-3", [alone])),
            ),
            import_day("2026-09-09", -2117, 0, account_id="sig-usd"),
            import_day("2026-09-10", 0, -100, account_id="unknown"),
        ],
    )
    days = day_mismatches(answer, {"sig-pen": "BCP Signature PEN", "sig-usd": "BCP Signature USD"})
    assert days[0] == DayMismatch(
        account_id="sig-pen",
        account_name="BCP Signature PEN",
        date_iso="2026-09-08",
        file_net_cents=-420,
        ledger_net_cents=-5420,
        unmatched_rows=(5,),
        unclaimed_parts=(*split, alone),
    )
    assert [(d.account_name, d.unmatched_rows, d.unclaimed_parts) for d in days[1:]] == [
        ("BCP Signature USD", (), ()),
        ("unknown", (), ()),  # an account the pick does not hold: its id
    ]
    assert day_mismatches(import_answer([import_row(2)]), {}) == []


def test_the_engines_counts_and_its_rows():
    answer = import_answer(
        [import_row(2), import_row(3, 0, outcome="skipped")],
        counts={
            "new": 7,
            "matched": 5,
            "sealed": 1,
            "skipped": 2,
            "backfilled": 4,
            "retitled": 3,
            "redated": 1,
        },
    )
    assert answer_counts(answer) == AnswerCounts(
        rows=2, new=7, matched=5, sealed=1, skipped=2, retitled=3, redated=1
    )


# ---- the reconciliations that stop a move -------------------------------------------
def _stopped(*blocked_by) -> list:
    return answer_rows(
        import_answer(
            [
                import_row(i + 2, outcome="matched", redate_blocked_by=b)
                for i, b in enumerate(blocked_by)
            ]
        )
    )


SEP = {"id": "r-sep", "account_id": "sig-pen", "name": "Septiembre 2026", "status": 2}
SEP.update(ORDERED_ALONE)
OCT = {"id": "r-oct", "account_id": "sig-usd", "name": "Octubre 2026", "status": 2, **ORDERED_ALONE}


def test_the_distinct_stopping_reconciliations_in_the_rows_order():
    assert blocking_reconciliations(_stopped("r-sep", None, "r-oct", "r-sep")) == [
        "r-sep",
        "r-oct",
    ]
    assert blocking_reconciliations(_stopped(None, None)) == []


@respx.mock
def test_each_stopping_reconciliation_is_named_by_one_read_of_it_by_its_id(configured):
    """One `GET /reconciliations/{id}` per distinct id, however many rows it
    stops, and no account's list is read
    (contract: GET /v1/reconciliations/{reconciliation_id})."""
    listed = respx.get(f"{BASE}/v1/reconciliations").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    sep = respx.get(f"{BASE}/v1/reconciliations/r-sep").mock(
        return_value=httpx.Response(200, json=SEP)
    )
    oct_ = respx.get(f"{BASE}/v1/reconciliations/r-oct").mock(
        return_value=httpx.Response(200, json=OCT)
    )
    rows = _stopped("r-sep", "r-oct", "r-sep", None, "r-sep")
    names, error = reconciliation_names(config_module.ensure_loaded(), rows, verbose=False)
    assert names == {"r-sep": "Septiembre 2026", "r-oct": "Octubre 2026"}
    assert error is None
    assert (sep.call_count, oct_.call_count, listed.call_count) == (1, 1, 0)
    assert [preview_line(r, names).reason for r in rows[:2]] == [
        "Not moved: Septiembre 2026 is reconciled",
        "Not moved: Octubre 2026 is reconciled",
    ]


@respx.mock
def test_no_reconciliation_is_read_when_no_move_is_stopped(configured):
    assert reconciliation_names(
        config_module.ensure_loaded(), _stopped(None, None), verbose=False
    ) == ({}, None)


@pytest.mark.parametrize(
    ("failure", "why"),
    [
        (error_response(404, "NOT_FOUND", "Gone."), "NOT_FOUND — Gone."),
        (error_response(500, "INTERNAL_ERROR", "Failed."), "INTERNAL_ERROR — Failed."),
        (httpx.ConnectError("connection refused"), "could not reach engine"),
    ],
    ids=["deleted", "engine-failed", "unreachable"],
)
@respx.mock
def test_a_failed_read_leaves_its_reconciliation_unnamed_and_the_rest_are_read(
    configured, failure, why
):
    """A read that fails leaves that id out, so its rows read `a
    reconciliation`; the ids after it are still read and named, and the
    failure's reason comes back for the line under the table."""
    route = respx.get(f"{BASE}/v1/reconciliations/r-sep")
    if isinstance(failure, Exception):
        route.mock(side_effect=failure)
    else:
        route.mock(return_value=failure)
    oct_ = respx.get(f"{BASE}/v1/reconciliations/r-oct").mock(
        return_value=httpx.Response(200, json=OCT)
    )
    rows = _stopped("r-sep", "r-oct")
    names, error = reconciliation_names(config_module.ensure_loaded(), rows, verbose=False)
    assert names == {"r-oct": "Octubre 2026"}
    assert oct_.call_count == 1
    assert error is not None and why in error
    assert [preview_line(r, names).reason for r in rows] == [
        "Not moved: a reconciliation is reconciled",
        "Not moved: Octubre 2026 is reconciled",
    ]
