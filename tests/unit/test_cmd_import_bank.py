"""`expense import bank` — the command around the parser and the engine's import.

respx-mocked: the accounts list, `POST /transactions/import` (answered by a
fake that decides each row's outcome) and, when a row is sealed, the
account's reconciliations. The sheet is a SheetData handed to the command
through the `read_workbook` seam, the same way test_cmd_import.py feeds the
sheet importer.
"""

import json

import httpx
import respx
from typer.testing import CliRunner

from expense import config as config_module
from expense.commands import _resource, bank_import_cmd
from expense.import_.reader import RawRow, SheetData
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import error_body, real_cli_app, whole

runner = CliRunner()
#: The real command tree — see the note in test_cmd_import.py. Mounted as a
#: bare `bank`, these tests could not tell `expense import bank` from any other
#: name the command might be given.
cli_app = real_cli_app()

ACCOUNTS = [
    {"id": "bcp-pen", "name": "BCP PEN", "currency_code": "PEN"},
    {"id": "bcp-usd", "name": "BCP USD", "currency_code": "USD"},
    {"id": "sig-pen", "name": "BCP Signature PEN", "currency_code": "PEN"},
    {"id": "sig-usd", "name": "BCP Signature USD", "currency_code": "USD"},
    {"id": "old", "name": "Retired PEN", "currency_code": "PEN", "is_archived": True},
    {"id": "who", "name": "Eliana", "currency_code": "PEN", "is_person": True},
]
CARD_HEADERS = ["Fecha", "Descripcion", "Moneda", "Monto"]
ACCOUNT_HEADERS = ["Fecha", "Descripcion", "Moneda", "Monto", "Numero de Operacion"]
CARD_ROWS = [
    ("2026-09-11", "EDO SUSHI BAR             LI", "S/", -49),
    ("2026-09-09", "APPLE.COM/BILL", "$", -21.17),
    ("2026-09-07", "APPARKA MALL AVENTURA  AREQU", "S/", -3.5),
    ("2026-09-07", "APPARKA MALL AVENTURA  AREQU", "S/", -3.5),
]


def _sheet(headers, rows) -> SheetData:
    return SheetData(headers=headers, rows=[RawRow(i + 2, list(r)) for i, r in enumerate(rows)])


def _feed(monkeypatch, headers, rows) -> None:
    monkeypatch.setattr(bank_import_cmd, "read_workbook", lambda path, **k: _sheet(headers, rows))


def _engine(decide=None, *, excess=None, periods=None):
    """Mock the accounts list and the import. `decide(index, row)` returns the
    row's result keys (default: new); the fake echoes the id, counts the
    outcomes like the engine, and answers `excess` as given. `periods` maps an
    account id to its reconciliations. Returns the import route."""
    respx.get(f"{BASE}/v1/accounts").mock(return_value=httpx.Response(200, json=whole(ACCOUNTS)))

    def answer(request):
        body = json.loads(request.content)
        rows = []
        for i, row in enumerate(body["rows"]):
            result = {
                "id": row["id"],
                "outcome": "new",
                "rule": None,
                "ledger_id": None,
                "backfill_code": None,
                "sealed_by": None,
            }
            result.update((decide or (lambda i, r: {}))(i, row))
            rows.append(result)
        outcomes = [r["outcome"] for r in rows]
        return httpx.Response(
            200,
            json={
                "dry_run": body["dry_run"],
                "rows": rows,
                "excess": excess or [],
                "counts": {
                    "new": outcomes.count("new"),
                    "matched": outcomes.count("matched"),
                    "sealed": outcomes.count("sealed"),
                    "backfilled": sum(1 for r in rows if r["backfill_code"]),
                },
            },
        )

    for account_id, items in (periods or {}).items():
        respx.get(f"{BASE}/v1/reconciliations", params={"account_id": account_id}).mock(
            return_value=httpx.Response(200, json=whole(items))
        )
    return respx.post(f"{BASE}/v1/transactions/import").mock(side_effect=answer)


def _sent(route) -> dict:
    return json.loads(route.calls.last.request.content)


def _run(monkeypatch, args, *, tty=False, **kw):
    monkeypatch.setattr(_resource, "stdin_is_tty", lambda: tty)
    return runner.invoke(cli_app, args, **kw)


def _only_the_import_was_written():
    """No ledger read, no PUT, no batch — the matching is the engine's."""
    for call in respx.calls:
        method, path = call.request.method, call.request.url.path
        assert path != "/v1/transactions", "the ledger is never read by the importer"
        assert method != "PUT" and path != "/v1/transactions/batch"
    posts = [c for c in respx.calls if c.request.method == "POST"]
    assert len(posts) == 1


# ---- the account ------------------------------------------------------------
@respx.mock
def test_account_flag_is_used_and_remembered(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS)
    _engine()
    result = _run(
        monkeypatch, ["import", "bank", "VISA Infinite Sapphire.xlsx", "--account", "BCP Signature"]
    )
    assert result.exit_code == 0, result.output
    assert "Account: BCP Signature" in result.output
    assert config_module.load().bank_files == {"VISA Infinite Sapphire": "BCP Signature"}


@respx.mock
def test_remembered_account_needs_no_flag(configured, monkeypatch):
    cfg = config_module.load()
    cfg.bank_files = {"VISA Infinite Sapphire": "BCP Signature"}
    config_module.save(cfg)
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS)
    _engine()
    result = _run(monkeypatch, ["import", "bank", "/tmp/VISA Infinite Sapphire.xlsx"])
    assert result.exit_code == 0, result.output
    assert 'remembered for "VISA Infinite Sapphire"' in result.output


@respx.mock
def test_off_a_tty_with_nothing_remembered_the_flag_is_required(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS)
    _engine()
    result = _run(monkeypatch, ["import", "bank", "VISA Infinite Sapphire.xlsx"])
    assert result.exit_code == 1
    assert "--account is required" in result.output


@respx.mock
def test_on_a_tty_the_accounts_are_listed_folded_and_the_answer_is_remembered(
    configured, monkeypatch
):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS)
    _engine()
    result = _run(
        monkeypatch, ["import", "bank", "VISA Infinite Sapphire.xlsx"], tty=True, input="2\n"
    )
    assert result.exit_code == 0, result.output
    # Folded by base name; archived and person accounts are not offered.
    assert "1  BCP     PEN + USD" in result.output
    assert "2  BCP Signature     PEN + USD" in result.output
    assert "Retired" not in result.output and "Eliana" not in result.output
    assert config_module.load().bank_files == {"VISA Infinite Sapphire": "BCP Signature"}


@respx.mock
def test_a_currency_the_pick_has_no_leg_for_refuses_the_file(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS)  # holds one $ row
    _engine()
    result = _run(monkeypatch, ["import", "bank", "x.xlsx", "--account", "BCP Signature PEN"])
    assert result.exit_code == 1
    assert "1 row in USD" in result.output and "BCP Signature PEN holds PEN only" in result.output


# ---- the request ------------------------------------------------------------
@respx.mock
def test_a_dry_run_is_one_import_call_with_dry_run_true(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS)
    route = _engine()
    result = _run(monkeypatch, ["import", "bank", "x.xlsx", "--account", "BCP Signature"])
    assert result.exit_code == 0, result.output
    body = _sent(route)
    assert body["dry_run"] is True
    assert [(r["account_id"], r["date"], r["amount_cents"]) for r in body["rows"]] == [
        ("sig-pen", "2026-09-11", -4900),
        ("sig-usd", "2026-09-09", -2117),
        ("sig-pen", "2026-09-07", -350),
        ("sig-pen", "2026-09-07", -350),
    ]
    assert body["rows"][0]["title"] == "EDO SUSHI BAR LI"  # the bank's text, collapsed
    assert all("description" not in r for r in body["rows"])
    _only_the_import_was_written()
    assert "Pass --apply to write the 4 new rows" in result.output


@respx.mock
def test_apply_is_one_call_with_dry_run_false(configured, monkeypatch):
    _feed(monkeypatch, ACCOUNT_HEADERS, [("11/09/2026", "TRAN.CEL.BM.", "S/", -50, "04330935")])
    route = _engine()
    result = _run(
        monkeypatch, ["import", "bank", "Sueldo Soles.xlsx", "--account", "BCP", "--apply"]
    )
    assert result.exit_code == 0, result.output
    body = _sent(route)
    assert body["dry_run"] is False
    assert body["rows"][0]["operation_code"] == "04330935"
    _only_the_import_was_written()
    assert "1 written · 1 → BCP PEN · all under @Pendiente" in result.output
    assert "Categorise them: expense world → Home → @Pendiente → ⏎" in result.output


@respx.mock
def test_rows_before_2026_are_never_sent(configured, monkeypatch):
    _feed(
        monkeypatch,
        CARD_HEADERS,
        [("2025-12-31", "OLD", "S/", -1), ("2026-01-01", "NEW", "S/", -2)],
    )
    route = _engine()
    result = _run(monkeypatch, ["import", "bank", "x.xlsx", "--account", "BCP Signature"])
    assert result.exit_code == 0, result.output
    assert [r["title"] for r in _sent(route)["rows"]] == ["NEW"]
    assert "1 before 2026" in result.output
    assert "1 row dated before 2026-01-01 not sent" in result.output


@respx.mock
def test_a_file_with_nothing_from_2026_sends_nothing(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, [("2025-12-31", "OLD", "S/", -1)])
    route = _engine()
    result = _run(monkeypatch, ["import", "bank", "x.xlsx", "--account", "BCP Signature"])
    assert result.exit_code == 1
    assert "nothing to import" in result.output
    assert not route.called


@respx.mock
def test_more_than_500_rows_are_refused_before_any_call(configured, monkeypatch):
    rows = [("2026-09-11", f"ROW {i}", "S/", -1) for i in range(501)]
    _feed(monkeypatch, CARD_HEADERS, rows)
    route = _engine()
    result = _run(monkeypatch, ["import", "bank", "x.xlsx", "--account", "BCP Signature"])
    assert result.exit_code == 1
    assert "501 rows to import" in result.output and "at most 500" in result.output
    assert "shorter date range" in result.output
    assert not route.called


@respx.mock
def test_exactly_500_rows_go_in_one_call(configured, monkeypatch):
    rows = [("2026-09-11", f"ROW {i}", "S/", -1) for i in range(500)]
    _feed(monkeypatch, CARD_HEADERS, rows)
    route = _engine()
    result = _run(monkeypatch, ["import", "bank", "x.xlsx", "--account", "BCP Signature"])
    assert result.exit_code == 0, result.output
    assert route.call_count == 1 and len(_sent(route)["rows"]) == 500


# ---- the preview ------------------------------------------------------------
@respx.mock
def test_each_outcome_reads_in_the_match_column(configured, monkeypatch):
    _feed(
        monkeypatch,
        ACCOUNT_HEADERS,
        [
            ("11/09/2026", "TRAN.CEL.BM.", "S/", -50, "04330935"),
            ("10/09/2026", "TRAN.CEL.BM.", "S/", -60, "03144753"),
            ("09/09/2026", "PLAZA VEA", "S/", -70, "03144754"),
            ("08/09/2026", "TOTTUS", "S/", -80, "03144755"),
        ],
    )
    outcomes = {
        1: {"outcome": "matched", "rule": "operation_code", "ledger_id": "t1"},
        2: {
            "outcome": "matched",
            "rule": "same_day",
            "ledger_id": "t2",
            "backfill_code": "03144754",
        },
        3: {"outcome": "matched", "rule": "adjacent_day", "ledger_id": "t3"},
    }
    _engine(lambda i, row: outcomes.get(i, {}))
    result = _run(monkeypatch, ["import", "bank", "Sueldo Soles.xlsx", "--account", "BCP"])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "operation numbers on every row" in out
    assert "04330935  new" in out
    assert "03144753  in ledger · operation" in out
    assert "03144754  in ledger · same day · +code" in out
    assert "03144755  in ledger · ± 1 day" in out
    assert (
        "4 rows  ·  1 new  ·  3 in the ledger (1 by operation · 1 by same day · 1 by ± 1 day)"
        "  ·  1 code to write" in out
    )
    assert "1 matched row in the ledger have no operation code yet — --apply writes it" in out


@respx.mock
def test_a_sealed_row_names_its_period_and_is_listed_apart(configured, monkeypatch):
    """C5: rows inside a closed period are shown, never hidden, and never
    written. The response carries the period's id; its name comes from the
    account's reconciliations."""
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS[:1] + CARD_ROWS[2:3])
    _engine(
        lambda i, row: {"outcome": "sealed", "sealed_by": "r1"} if i == 1 else {},
        periods={"sig-pen": [{"id": "r1", "name": "September 2026"}]},
    )
    result = _run(
        monkeypatch, ["import", "bank", "x.xlsx", "--account", "BCP Signature", "--apply"]
    )
    assert result.exit_code == 0, result.output  # sealed is an outcome, not a failure
    out = result.output
    assert "closed · September 2026" in out
    assert "1 in a closed period" in out
    assert "! 1 row falls inside a closed period and never goes in" in out
    assert "row 3 · 2026-09-07 · APPARKA MALL AVENTURA AREQU · -3.50" in out
    assert "1 written · 1 → BCP Signature PEN" in out


@respx.mock
def test_a_failed_period_read_still_shows_the_import(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS[:1])
    _engine(lambda i, row: {"outcome": "sealed", "sealed_by": "r1"})
    respx.get(f"{BASE}/v1/reconciliations").mock(
        return_value=httpx.Response(500, json=error_body("INTERNAL", "down"))
    )
    result = _run(monkeypatch, ["import", "bank", "x.xlsx", "--account", "BCP Signature"])
    assert result.exit_code == 0, result.output
    assert "closed · a closed period" in result.output
    assert "could not read the closed periods' names" in result.output


@respx.mock
def test_unmatched_ledger_rows_are_one_line_per_day_counted_up_front(configured, monkeypatch):
    """The count is the
    ledger rows no file row matched, never the ledger's total: the equal-count
    day shows 1, and the day holding three against the file's one shows 2."""
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS[2:3])
    _engine(
        lambda i, row: {"outcome": "matched", "rule": "same_day", "ledger_id": "t1"},
        excess=[
            {
                "account_id": "sig-pen",
                "date": "2026-09-10",
                "amount_cents": 2800,
                "transaction_type": 1,
                "file_count": 1,
                "ledger_count": 1,
                "unclaimed_ledger_ids": ["t9"],
            },
            {
                "account_id": "sig-pen",
                "date": "2026-09-07",
                "amount_cents": 350,
                "transaction_type": 1,
                "file_count": 1,
                "ledger_count": 3,
                "unclaimed_ledger_ids": ["t2", "t3"],
            },
        ],
    )
    for apply in ([], ["--apply"]):
        result = _run(
            monkeypatch, ["import", "bank", "x.xlsx", "--account", "BCP Signature", *apply]
        )
        assert result.exit_code == 0, result.output
        out = result.output
        assert "! 3 ledger rows no file row matched — check" in out
        assert "before --apply, one may be logged twice" in out
        assert "    1 on 2026-09-10 · -28.00 · BCP Signature PEN" in out
        assert "    2 on 2026-09-07 · -3.50 · BCP Signature PEN" in out
        assert "ledger 1, file 1" not in out


@respx.mock
def test_the_number_column_is_the_files_line(configured, monkeypatch):
    """`#` is the Excel row, the number every message under the table
    uses. Line 3 is from 2025 and line 4 has a zero amount, so neither is in the
    table and the numbers jump from 2 to 5."""
    _feed(
        monkeypatch,
        CARD_HEADERS,
        [
            ("2026-09-11", "CAFE", "S/", -18.5),
            ("2025-12-30", "OLD", "S/", -35),
            ("2026-09-09", "ZERO", "S/", 0),
            ("2026-09-08", "GRIFO", "S/", -120),
        ],
    )
    _engine()
    result = _run(monkeypatch, ["import", "bank", "x.xlsx", "--account", "BCP Signature"])
    assert result.exit_code == 0, result.output
    table = [ln.split() for ln in result.output.splitlines()]
    rows = [t[0] for t in table if len(t) > 1 and t[1].startswith("2026-09-")]
    assert rows == ["2", "5"]
    assert "! row 4: the amount is zero" in result.output


@respx.mock
def test_apply_with_nothing_new_says_so(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS[:1])
    _engine(lambda i, row: {"outcome": "matched", "rule": "same_day", "ledger_id": "t1"})
    result = _run(
        monkeypatch, ["import", "bank", "x.xlsx", "--account", "BCP Signature", "--apply"]
    )
    assert result.exit_code == 0, result.output
    assert "the ledger already has every row" in result.output


@respx.mock
def test_apply_reports_the_codes_it_wrote(configured, monkeypatch):
    _feed(monkeypatch, ACCOUNT_HEADERS, [("10/09/2026", "TRAN.CEL.BM.", "S/", -60, "03144753")])
    _engine(
        lambda i, row: {
            "outcome": "matched",
            "rule": "same_day",
            "ledger_id": "t1",
            "backfill_code": "03144753",
        }
    )
    result = _run(
        monkeypatch, ["import", "bank", "Sueldo Soles.xlsx", "--account", "BCP", "--apply"]
    )
    assert result.exit_code == 0, result.output
    assert "1 operation code written onto existing rows" in result.output
    assert "1 code written" in result.output


@respx.mock
def test_an_answer_short_of_a_row_is_an_error_not_a_smaller_count(configured, monkeypatch):
    """If the engine answers fewer rows than were sent, every count would be
    quietly short. Exit 1, naming the row with no answer, and say an apply
    may have been written."""
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS[:2])
    _engine()
    respx.post(f"{BASE}/v1/transactions/import").mock(
        side_effect=lambda request: httpx.Response(
            200,
            json={
                "dry_run": False,
                "rows": [
                    {
                        "id": json.loads(request.content)["rows"][0]["id"],
                        "outcome": "new",
                        "rule": None,
                        "ledger_id": None,
                        "backfill_code": None,
                        "sealed_by": None,
                    }
                ],
                "excess": [],
                "counts": {"new": 1, "matched": 0, "sealed": 0, "backfilled": 0},
            },
        )
    )
    result = _run(
        monkeypatch, ["import", "bank", "x.xlsx", "--account", "BCP Signature", "--apply"]
    )
    assert result.exit_code == 1
    assert "the engine answered 1 of the 2 rows sent" in result.output
    assert "! row 3: no answer" in result.output
    assert "may have been written" in result.output
    assert "written ·" not in result.output  # no partial summary


@respx.mock
def test_a_parser_refused_row_is_listed_and_apply_exits_1(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, [*CARD_ROWS[:1], ("2026-09-01", "ZERO", "S/", 0)])
    route = _engine()
    result = _run(
        monkeypatch, ["import", "bank", "x.xlsx", "--account", "BCP Signature", "--apply"]
    )
    assert result.exit_code == 1
    assert len(_sent(route)["rows"]) == 1  # the good row still went
    assert "! row 3: the amount is zero" in result.output
    assert "1 refused" in result.output


# ---- --json -----------------------------------------------------------------
@respx.mock
def test_json_is_the_engines_body_byte_for_byte(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, [("2025-12-31", "OLD", "S/", -1), *CARD_ROWS[:1]])
    route = _engine()
    result = _run(monkeypatch, ["import", "bank", "x.xlsx", "--account", "BCP Signature", "--json"])
    assert result.exit_code == 0, result.output
    engine_body = route.calls.last.response.json()
    assert json.loads(result.stdout) == engine_body
    assert "not sent" in result.stderr and "not sent" not in result.stdout


# ---- refusals ---------------------------------------------------------------
@respx.mock
def test_a_422_names_the_files_line_and_nothing_is_written(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, [("2025-12-31", "OLD", "S/", -1), *CARD_ROWS])
    _engine()
    respx.post(f"{BASE}/v1/transactions/import").mock(
        return_value=httpx.Response(
            422,
            json=error_body(
                "VALIDATION_ERROR",
                "Import validation failed.",
                {"rows.3.date": "Must not be in the future."},
            ),
        )
    )
    result = _run(
        monkeypatch, ["import", "bank", "x.xlsx", "--account", "BCP Signature", "--apply"]
    )
    assert result.exit_code == 1
    # engine index 3 is the 4th row SENT; the 2025 row on line 2 was never sent,
    # so it is the file's line 6.
    assert "VALIDATION_ERROR — Import validation failed." in result.output
    assert "! row 6 (date): Must not be in the future." in result.output
    assert "Nothing was written." in result.output


@respx.mock
def test_a_422_under_json_is_the_raw_envelope(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS[:1])
    _engine()
    envelope = error_body("VALIDATION_ERROR", "Import validation failed.", {"rows.0.date": "x"})
    respx.post(f"{BASE}/v1/transactions/import").mock(
        return_value=httpx.Response(422, json=envelope)
    )
    result = _run(monkeypatch, ["import", "bank", "x.xlsx", "--account", "BCP Signature", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout) == envelope
