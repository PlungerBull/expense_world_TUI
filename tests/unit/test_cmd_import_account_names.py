"""`expense import sheet --account-name`: renaming a sheet account leg in the ledger."""

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from expense import config as config_module
from expense.commands import import_cmd
from expense.import_ import plan as plan_mod
from expense.import_.reader import RawRow, SheetData
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import real_cli_app, strip_panel

runner = CliRunner()
cli_app = real_cli_app()

_HEADERS = [
    "Descripcion",
    "CATEGORY",
    "HASHTAG",
    "Fecha",
    "Monto",
    "Cuenta",
    "T.C.",
    "Moneda",
    "Solarizado",
    "Estado Cuenta",
    "Notas",
]


def _cells(title, category, hashtag, amount, account, currency):
    return [
        title,
        category,
        hashtag,
        44896,
        amount,
        account,
        "None",
        currency,
        amount,
        "None",
        "None",
    ]


#: "BCP" spans PEN and USD, and the PEN leg has an opening balance.
_ROWS = [
    RawRow(2, _cells("SALDO INICIAL", None, None, 3500, "BCP", "PEN")),
    RawRow(3, _cells("Groomers", "WANTS", "Salidas", -44, "BCP", "PEN")),
    RawRow(4, _cells("Netflix", "WANTS", "Salidas", -10, "BCP", "USD")),
]


@pytest.fixture
def sheet(monkeypatch):
    monkeypatch.setattr(
        import_cmd, "read_workbook", lambda path, **k: SheetData(headers=_HEADERS, rows=_ROWS)
    )


def _invoke(*args: str):
    return runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx", *args])


def _saved() -> dict[str, str]:
    return config_module.ensure_loaded().sheet_account_names


def _accounts_block(output: str) -> list[str]:
    lines = output.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Accounts to ensure"))
    end = lines.index("", start)
    return lines[start:end]


# --- dry run ----------------------------------------------------------------


@respx.mock
def test_dry_run_lists_renamed_leg_and_leaves_the_other(configured, sheet):
    result = _invoke("--account-name", "BCP:PEN=Sueldo Soles")
    assert result.exit_code == 0, result.output
    assert _accounts_block(result.output) == [
        "Accounts to ensure (2):",
        '  BCP USD [USD]  (from "BCP")',
        '  Sueldo Soles [PEN]  (from "BCP")',
    ]
    assert not respx.calls


@respx.mock
def test_dry_run_json_carries_renamed_name_and_source(configured, sheet):
    result = _invoke("--account-name", "BCP:PEN=Sueldo Soles", "--json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["accounts"] == [
        {"name": "Sueldo Soles", "currency": "PEN", "source_name": "BCP"},
        {"name": "BCP USD", "currency": "USD", "source_name": "BCP"},
    ]


@respx.mock
def test_without_a_mapping_the_split_is_unchanged(configured, sheet):
    result = _invoke()
    assert result.exit_code == 0, result.output
    assert _accounts_block(result.output) == [
        "Accounts to ensure (2):",
        '  BCP PEN [PEN]  (from "BCP")',
        '  BCP USD [USD]  (from "BCP")',
    ]
    assert _saved() == {}


def test_build_plan_with_no_matching_rename_is_identical():
    from expense.import_.parse import ParsedRow

    rows = [
        ParsedRow(2, "t", "C", "H", "2022-12-01", -1, "PEN", "BCP Oro", None),
        ParsedRow(3, "t", "C", "H", "2022-12-01", -1, "USD", "BCP Oro", None),
        ParsedRow(4, "t", "C", "H", "2022-12-01", -1, "PEN", "Interbank", None),
    ]
    plain = plan_mod.build_plan(rows, [], [])
    unrelated = plan_mod.build_plan(rows, [], [], account_names={("other", "PEN"): "X"})
    assert plain == unrelated


# --- remembered in the config ------------------------------------------------


@respx.mock
def test_mapping_is_saved_and_applied_without_the_flag(configured, sheet):
    assert _invoke("--account-name", "bcp : pen = Sueldo Soles").exit_code == 0
    assert _saved() == {"bcp:PEN": "Sueldo Soles"}

    result = _invoke("--json")
    assert result.exit_code == 0, result.output
    names = {a["currency"]: a["name"] for a in json.loads(result.output)["accounts"]}
    assert names == {"PEN": "Sueldo Soles", "USD": "BCP USD"}


@respx.mock
def test_flag_replaces_the_saved_name_for_the_same_leg(configured, sheet):
    cfg = config_module.ensure_loaded()
    cfg.sheet_account_names = {"BCP:PEN": "Old Name", "BCP Signature:USD": "Kept"}
    config_module.save(cfg)

    result = _invoke("--account-name", "bcp:pen=Sueldo Soles", "--json")
    assert result.exit_code == 0, result.output
    assert _saved() == {"bcp:PEN": "Sueldo Soles", "BCP Signature:USD": "Kept"}


@respx.mock
def test_dry_run_without_config_still_renames(sheet, tmp_path, monkeypatch):
    monkeypatch.setenv("EXPENSE_CONFIG", str(tmp_path / "absent-config"))
    result = _invoke("--account-name", "BCP:PEN=Sueldo Soles", "--json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["accounts"][0]["name"] == "Sueldo Soles"
    assert not (tmp_path / "absent-config").exists()


# --- apply -------------------------------------------------------------------


def _mock_engine(accounts: list) -> tuple[respx.Route, respx.Route, respx.Route]:
    respx.get(f"{BASE}/v1/accounts").mock(
        return_value=httpx.Response(200, json={"items": accounts})
    )
    respx.get(f"{BASE}/v1/categories").mock(return_value=httpx.Response(200, json={"items": []}))
    respx.get(f"{BASE}/v1/hashtags").mock(return_value=httpx.Response(200, json={"items": []}))
    acc_route = respx.post(f"{BASE}/v1/accounts").mock(return_value=httpx.Response(201, json={}))
    respx.post(f"{BASE}/v1/categories").mock(return_value=httpx.Response(201, json={}))
    respx.post(f"{BASE}/v1/hashtags").mock(return_value=httpx.Response(201, json={}))
    opening_route = respx.post(url__regex=rf"{BASE}/v1/accounts/[^/]+/opening-balance").mock(
        return_value=httpx.Response(201, json={})
    )
    batch_route = respx.post(f"{BASE}/v1/transactions/batch").mock(
        return_value=httpx.Response(201, json={"created": []})
    )
    return acc_route, opening_route, batch_route


@respx.mock
def test_apply_creates_renamed_account_and_routes_rows_and_opening_to_it(configured, sheet):
    acc_route, opening_route, batch_route = _mock_engine(accounts=[])

    result = _invoke("--account-name", "BCP:PEN=Sueldo Soles", "--apply", "--json")
    assert result.exit_code == 0, result.output

    posted = {
        json.loads(c.request.content)["name"]: json.loads(c.request.content)
        for c in acc_route.calls
    }
    assert set(posted) == {"Sueldo Soles", "BCP USD"}
    assert posted["Sueldo Soles"]["currency_code"] == "PEN"
    sueldo_id, usd_id = posted["Sueldo Soles"]["id"], posted["BCP USD"]["id"]

    assert opening_route.call_count == 1
    assert opening_route.calls.last.request.url.path == f"/v1/accounts/{sueldo_id}/opening-balance"

    items = json.loads(batch_route.calls.last.request.content)["transactions"]
    by_title = {i["title"]: i["account_id"] for i in items}
    assert by_title == {"Groomers": sueldo_id, "Netflix": usd_id}


@respx.mock
def test_rerun_without_flag_reuses_the_renamed_account(configured, sheet):
    cfg = config_module.ensure_loaded()
    cfg.sheet_account_names = {"BCP:PEN": "Sueldo Soles"}
    config_module.save(cfg)
    acc_route, opening_route, batch_route = _mock_engine(
        accounts=[
            {
                "id": "acc-sueldo",
                "name": "Sueldo Soles",
                "currency_code": "PEN",
                "opening_balance_transaction_id": None,
                "statement_code": None,
            },
            {
                "id": "acc-usd",
                "name": "BCP USD",
                "currency_code": "USD",
                "opening_balance_transaction_id": None,
                "statement_code": None,
            },
        ]
    )

    result = _invoke("--apply", "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert (payload["accounts_created"], payload["accounts_reused"]) == (0, 2)
    assert not acc_route.called
    assert opening_route.calls.last.request.url.path == "/v1/accounts/acc-sueldo/opening-balance"
    items = json.loads(batch_route.calls.last.request.content)["transactions"]
    assert {i["title"]: i["account_id"] for i in items} == {
        "Groomers": "acc-sueldo",
        "Netflix": "acc-usd",
    }


# --- usage errors --------------------------------------------------------------


@respx.mock
@pytest.mark.parametrize(
    "value",
    [
        "BCP",  # no ":" and no "="
        "BCP:PEN",  # no "="
        "BCP=Sueldo Soles",  # no ":"
        ":PEN=Sueldo Soles",  # empty sheet name
        "BCP:=Sueldo Soles",  # empty currency
        "BCP:PEN=",  # empty ledger name
        "BCP:PEN=  ",  # blank ledger name
        "BCP:EUR=Sueldo Euros",  # the sheet has no BCP in EUR
        "Interbank:PEN=Sueldo Soles",  # the sheet has no Interbank
    ],
)
@pytest.mark.parametrize("apply", [False, True])
def test_bad_value_is_a_usage_error_and_saves_nothing(configured, sheet, value, apply):
    before = config_module.config_path().read_text()
    args = ["--account-name", value] + (["--apply"] if apply else [])
    result = _invoke(*args)
    assert result.exit_code == 2, result.output
    assert "--account-name" in strip_panel(result.output)
    assert config_module.config_path().read_text() == before
    assert not respx.calls


@respx.mock
def test_one_name_for_both_currency_legs_is_two_accounts(configured, sheet):
    result = _invoke(
        "--account-name", "BCP:USD=Cuenta", "--account-name", "BCP:PEN=Cuenta", "--json"
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["accounts"] == [
        {"name": "Cuenta", "currency": "PEN", "source_name": "BCP"},
        {"name": "Cuenta", "currency": "USD", "source_name": "BCP"},
    ]


@respx.mock
def test_rename_onto_another_legs_name_is_a_usage_error(configured, monkeypatch):
    rows = [
        RawRow(2, _cells("Groomers", "WANTS", "Salidas", -44, "BCP", "PEN")),
        RawRow(3, _cells("Taxi", "WANTS", "Salidas", -20, "Interbank", "PEN")),
    ]
    monkeypatch.setattr(
        import_cmd, "read_workbook", lambda path, **k: SheetData(headers=_HEADERS, rows=rows)
    )
    before = config_module.config_path().read_text()
    result = _invoke("--account-name", "BCP:PEN=interbank")
    assert result.exit_code == 2, result.output
    assert "would both be written" in strip_panel(result.output)
    assert config_module.config_path().read_text() == before
    assert not respx.calls
