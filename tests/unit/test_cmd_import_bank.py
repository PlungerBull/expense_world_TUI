"""`expense import bank` — the command around the pure parser and matcher.

respx-mocked: the accounts list, the ledger reads the matcher needs, and the
batch write. The sheet is a SheetData handed to the command through the
`read_workbook` seam, the same way test_cmd_import.py feeds the sheet importer.
"""

import json

import httpx
import respx
from typer.testing import CliRunner

from expense import config as config_module
from expense.commands import _resource, bank_import_cmd
from expense.import_.reader import RawRow, SheetData
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import make_cli_app

runner = CliRunner()
cli_app = make_cli_app(commands={"bank": bank_import_cmd.bank})

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


def _engine(ledger_by_account: dict[str, list[dict]] | None = None):
    """Mock the reads: the accounts list and one ledger page per account."""
    respx.get(f"{BASE}/v1/accounts").mock(return_value=httpx.Response(200, json=ACCOUNTS))

    def transactions(request):
        account = request.url.params.get("account_id")
        items = (ledger_by_account or {}).get(account, [])
        return httpx.Response(200, json={"items": items, "total": len(items)})

    respx.get(f"{BASE}/v1/transactions").mock(side_effect=transactions)


def _ledger(ident, account, date, cents, title, code=None) -> dict:
    return {
        "id": ident,
        "account_id": account,
        "date": f"{date}T12:00:00-05:00",
        "amount_cents": cents,
        "title": title,
        "operation_code": code,
    }


def _run(monkeypatch, args, *, tty=False, **kw):
    monkeypatch.setattr(_resource, "stdin_is_tty", lambda: tty)
    return runner.invoke(cli_app, args, **kw)


# ---- the account ------------------------------------------------------------
@respx.mock
def test_account_flag_is_used_and_remembered(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS)
    _engine()
    result = _run(
        monkeypatch, ["bank", "VISA Infinite Sapphire.xlsx", "--account", "BCP Signature"]
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
    result = _run(monkeypatch, ["bank", "/tmp/VISA Infinite Sapphire.xlsx"])
    assert result.exit_code == 0, result.output
    assert 'remembered for "VISA Infinite Sapphire"' in result.output


@respx.mock
def test_off_a_tty_with_nothing_remembered_the_flag_is_required(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS)
    _engine()
    result = _run(monkeypatch, ["bank", "VISA Infinite Sapphire.xlsx"])
    assert result.exit_code == 1
    assert "--account is required" in result.output


@respx.mock
def test_on_a_tty_the_accounts_are_listed_folded_and_the_answer_is_remembered(
    configured, monkeypatch
):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS)
    _engine()
    result = _run(monkeypatch, ["bank", "VISA Infinite Sapphire.xlsx"], tty=True, input="2\n")
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
    result = _run(monkeypatch, ["bank", "x.xlsx", "--account", "BCP Signature PEN"])
    assert result.exit_code == 1
    assert "1 row in USD" in result.output and "BCP Signature PEN holds PEN only" in result.output


# ---- the preview ------------------------------------------------------------
@respx.mock
def test_dry_run_places_rows_and_writes_nothing(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS)
    _engine(
        {
            # EDO SUSHI typed in the LOG bar the day before, under its own title.
            "sig-pen": [_ledger("t1", "sig-pen", "2026-09-10", -4900, "sushi")],
            "sig-usd": [_ledger("t2", "sig-usd", "2026-09-09", -2117, "APPLE.COM/BILL")],
        }
    )
    batch = respx.post(f"{BASE}/v1/transactions/batch")
    result = _run(monkeypatch, ["bank", "x.xlsx", "--account", "BCP Signature"])
    assert result.exit_code == 0, result.output
    assert not batch.called
    out = result.output
    assert "EDO SUSHI BAR" in out and "in ledger · ±1 day, amount only" in out
    assert "APPLE.COM/BILL" in out and "in ledger · same day + title" in out
    assert "4 rows  ·  2 new  ·  2 in the ledger" in out
    assert "2 → BCP Signature PEN" in out
    assert "Pass --apply to write the 2 new rows" in out


@respx.mock
def test_operation_codes_are_shown_and_decide(configured, monkeypatch):
    _feed(
        monkeypatch,
        ACCOUNT_HEADERS,
        [
            ("11/09/2026", "TRAN.CEL.BM.", "S/", -50, "04330935"),
            ("10/09/2026", "TRAN.CEL.BM.", "S/", -60, "03144753"),
        ],
    )
    _engine(
        {"bcp-pen": [_ledger("t1", "bcp-pen", "2026-09-10", -6000, "TRAN.CEL.BM.", "03144753")]}
    )
    result = _run(monkeypatch, ["bank", "Sueldo Soles.xlsx", "--account", "BCP", "--all"])
    assert result.exit_code == 0, result.output
    assert "operation numbers on every row" in result.output
    assert "04330935  new" in result.output
    assert "03144753  in ledger · operation 03144753" in result.output


@respx.mock
def test_the_ledger_holding_more_than_the_file_is_a_loud_warning(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS[2:3])  # one 3.50 on the 7th
    _engine(
        {
            "sig-pen": [
                _ledger("t1", "sig-pen", "2026-09-07", -350, "APPARKA"),
                _ledger("t2", "sig-pen", "2026-09-07", -350, "APPARKA"),
            ]
        }
    )
    result = _run(monkeypatch, ["bank", "x.xlsx", "--account", "BCP Signature"])
    assert result.exit_code == 0, result.output
    assert "! 1 group has more in the ledger than in the file" in result.output
    assert "2026-09-07 · -3.50 · BCP Signature PEN — ledger 2, file 1" in result.output


@respx.mock
def test_json_is_the_placement(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS[:1])
    _engine()
    result = _run(monkeypatch, ["bank", "x.xlsx", "--account", "BCP Signature", "--json"])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.output)
    assert doc["account"] == "BCP Signature"
    assert doc["rows"][0]["title"] == "EDO SUSHI BAR"
    assert doc["rows"][0]["description"] == "EDO SUSHI BAR             LI"
    assert doc["rows"][0]["match"] is None and doc["rows"][0]["account_id"] == "sig-pen"
    assert doc["written"] is None


# ---- apply ------------------------------------------------------------------
@respx.mock
def test_apply_writes_only_the_new_rows_under_no_category(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS)
    _engine({"sig-usd": [_ledger("t2", "sig-usd", "2026-09-09", -2117, "APPLE.COM/BILL")]})
    batch = respx.post(f"{BASE}/v1/transactions/batch").mock(
        return_value=httpx.Response(201, json={"created": []})
    )
    result = _run(monkeypatch, ["bank", "x.xlsx", "--account", "BCP Signature", "--apply"])
    assert result.exit_code == 0, result.output
    body = json.loads(batch.calls.last.request.content)
    items = body["transactions"]
    assert [i["title"] for i in items] == [
        "EDO SUSHI BAR",
        "APPARKA MALL AVENTURA",
        "APPARKA MALL AVENTURA",
    ]
    for item in items:
        assert "category_id" not in item and "hashtag_ids" not in item
        assert item["account_id"] == "sig-pen"
        assert item["date"].startswith(("2026-09-11", "2026-09-07"))
    assert items[0]["description"] == "EDO SUSHI BAR             LI"
    assert "3 written · 3 → BCP Signature PEN · all under @Pendiente" in result.output
    assert "Categorise them: expense world → Home → @Pendiente → ⏎" in result.output


@respx.mock
def test_apply_carries_the_operation_code(configured, monkeypatch):
    _feed(monkeypatch, ACCOUNT_HEADERS, [("11/09/2026", "TRAN.CEL.BM.", "S/", -50, "04330935")])
    _engine()
    batch = respx.post(f"{BASE}/v1/transactions/batch").mock(
        return_value=httpx.Response(201, json={"created": []})
    )
    result = _run(monkeypatch, ["bank", "Sueldo Soles.xlsx", "--account", "BCP", "--apply"])
    assert result.exit_code == 0, result.output
    item = json.loads(batch.calls.last.request.content)["transactions"][0]
    assert item["operation_code"] == "04330935"


@respx.mock
def test_apply_with_nothing_new_writes_nothing(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS[:1])
    _engine({"sig-pen": [_ledger("t1", "sig-pen", "2026-09-11", -4900, "EDO SUSHI BAR")]})
    batch = respx.post(f"{BASE}/v1/transactions/batch")
    result = _run(monkeypatch, ["bank", "x.xlsx", "--account", "BCP Signature", "--apply"])
    assert result.exit_code == 0, result.output
    assert not batch.called
    assert "the ledger already has every row" in result.output


@respx.mock
def test_apply_reports_a_refused_row_and_exits_1(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS[:2])
    _engine()
    error = {
        "error": {"code": "VALIDATION_ERROR", "message": "Batch validation failed.", "fields": {}}
    }
    respx.post(f"{BASE}/v1/transactions/batch").mock(
        side_effect=[
            httpx.Response(422, json=error),  # the chunk
            httpx.Response(201, json={"created": []}),  # row 1 alone
            httpx.Response(422, json=error),  # row 2 alone
        ]
    )
    result = _run(monkeypatch, ["bank", "x.xlsx", "--account", "BCP Signature", "--apply"])
    assert result.exit_code == 1, result.output
    assert "1 written" in result.output
    assert "! row 3:" in result.output


# ---- the operation-code backfill --------------------------------------------
@respx.mock
def test_preview_says_which_matched_rows_will_get_a_code(configured, monkeypatch):
    _feed(monkeypatch, ACCOUNT_HEADERS, [("10/09/2026", "TRAN.CEL.BM.", "S/", -60, "03144753")])
    _engine({"bcp-pen": [_ledger("t1", "bcp-pen", "2026-09-10", -6000, "TRAN.CEL.BM.")]})
    put = respx.put(f"{BASE}/v1/transactions/t1")
    result = _run(monkeypatch, ["bank", "Sueldo Soles.xlsx", "--account", "BCP"])
    assert result.exit_code == 0, result.output
    assert "in ledger · same day + title · +code" in result.output
    assert "1 matched row in the ledger have no operation code yet" in result.output
    assert not put.called  # a dry run writes nothing


@respx.mock
def test_apply_writes_the_code_onto_the_matched_row_and_nothing_else(configured, monkeypatch):
    _feed(monkeypatch, ACCOUNT_HEADERS, [("10/09/2026", "TRAN.CEL.BM.", "S/", -60, "03144753")])
    _engine({"bcp-pen": [_ledger("t1", "bcp-pen", "2026-09-10", -6000, "TRAN.CEL.BM.")]})
    put = respx.put(f"{BASE}/v1/transactions/t1").mock(return_value=httpx.Response(200, json={}))
    batch = respx.post(f"{BASE}/v1/transactions/batch")
    result = _run(monkeypatch, ["bank", "Sueldo Soles.xlsx", "--account", "BCP", "--apply"])
    assert result.exit_code == 0, result.output
    assert json.loads(put.calls.last.request.content) == {"operation_code": "03144753"}
    assert not batch.called  # nothing was new
    assert "1 operation code written onto existing rows" in result.output
    assert "Nothing new to write" in result.output


@respx.mock
def test_a_second_download_matches_by_the_code_it_wrote(configured, monkeypatch):
    """After the backfill the ledger row carries the code, so rule 1 decides
    and no content rule is consulted."""
    _feed(monkeypatch, ACCOUNT_HEADERS, [("10/09/2026", "TRAN.CEL.BM.", "S/", -60, "03144753")])
    _engine(
        {"bcp-pen": [_ledger("t1", "bcp-pen", "2026-09-10", -6000, "TRAN.CEL.BM.", "03144753")]}
    )
    result = _run(monkeypatch, ["bank", "Sueldo Soles.xlsx", "--account", "BCP"])
    assert result.exit_code == 0, result.output
    assert "in ledger · operation 03144753" in result.output
    assert "+code" not in result.output


# ---- the JSON document ------------------------------------------------------
#: Every key `--json` emits, on every run. The document used to be assembled in
#: three places, so which of the write keys you got depended on which fork the
#: run took; a consumer could not tell "no rows failed" from "this fork never
#: told me about failures".
DOC_KEYS = {
    "file",
    "account",
    "legs",
    "rows",
    "refused",
    "excess",
    "written",
    "already_there",
    "codes_written",
    "failed",
    "stopped",
}


@respx.mock
def test_the_json_document_has_one_shape_on_a_dry_run(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS[:1])
    _engine()
    result = _run(monkeypatch, ["bank", "x.xlsx", "--account", "BCP Signature", "--json"])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.output)
    assert set(doc) == DOC_KEYS
    # `written` is null, not 0: nothing was attempted, which is not the same as
    # nothing needing doing.
    assert doc["written"] is None
    assert doc["already_there"] == 0 and doc["codes_written"] == 0
    assert doc["failed"] == [] and doc["stopped"] is None


@respx.mock
def test_the_json_document_has_one_shape_when_apply_writes(configured, monkeypatch):
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS[:1])
    _engine()
    respx.post(f"{BASE}/v1/transactions/batch").mock(
        return_value=httpx.Response(201, json={"created": []})
    )
    result = _run(
        monkeypatch, ["bank", "x.xlsx", "--account", "BCP Signature", "--apply", "--json"]
    )
    assert result.exit_code == 0, result.output
    doc = json.loads(result.output)
    assert set(doc) == DOC_KEYS
    assert doc["written"] == 1 and doc["failed"] == []


@respx.mock
def test_the_json_document_has_one_shape_when_apply_writes_nothing(configured, monkeypatch):
    """The fork that used to carry neither `failed` nor `already_there`."""
    _feed(monkeypatch, CARD_HEADERS, CARD_ROWS[:1])
    _engine({"sig-pen": [_ledger("t1", "sig-pen", "2026-09-11", -4900, "EDO SUSHI BAR")]})
    result = _run(
        monkeypatch, ["bank", "x.xlsx", "--account", "BCP Signature", "--apply", "--json"]
    )
    assert result.exit_code == 0, result.output
    doc = json.loads(result.output)
    assert set(doc) == DOC_KEYS
    assert doc["written"] == 0 and doc["failed"] == []
