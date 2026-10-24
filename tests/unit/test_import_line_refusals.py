"""`expense import sheet` and the refusals a bank line draws, against the sheet
lines they hit.

The import sends no `statement_line`, and a group's parts share one account,
date and title, so `LINE_GROUP_FIELDS_DIFFER` has nothing to refuse; should it
come, it fails the rows it names and the rest go again (contract: POST
/v1/transactions/batch, "Line groups"). `LIMIT_REACHED` with
`LINE_CODES_EXHAUSTED` holds for the rest of the run, so it stops the run once.
"""

import json

import httpx
import respx
from typer.testing import CliRunner

from expense.import_ import apply as apply_mod
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import error_response, real_cli_app
from tests.unit.test_import_split_groups import _apply, _plan, _raw, _seeded, _sent, _use_sheet

runner = CliRunner()
cli_app = real_cli_app()

_EXHAUSTED = ("No bank line codes are left.", "No line code is left for a new line.")


def _ok() -> httpx.Response:
    return httpx.Response(201, json={"created": []})


def _created(request: httpx.Request) -> httpx.Response:
    return _ok()


def _exhausted(index: int, key: str = "transactions.{i}.id") -> httpx.Response:
    field = key.format(i=index)
    return error_response(
        422,
        "LIMIT_REACHED",
        _EXHAUSTED[0],
        {field: _EXHAUSTED[1]},
        {field: "LINE_CODES_EXHAUSTED"},
    )


# --- LINE_GROUP_FIELDS_DIFFER -------------------------------------------------


def _items_for(rows) -> list[dict]:
    """The items the import sends for `rows`, as the engine receives them."""
    plan = _plan(rows)
    with respx.mock:
        _seeded()
        route = respx.post(f"{BASE}/v1/transactions/batch").mock(side_effect=_created)
        _apply(plan)
    return [item for sent in _sent(route) for item in sent]


def test_the_import_sends_no_statement_line(configured):
    """Rows alone, the parts of a group and a code differing only in case: none
    carries a `statement_line`, so no statement-line refusal can come."""
    items = _items_for(
        [_raw(2, "SIG-1"), _raw(3, " SIG-1 "), _raw(4, "sig-1"), _raw(5, "SIG-2"), _raw(6)]
    )

    assert len(items) == 5
    assert [item for item in items if "statement_line" in item] == []
    assert len([item for item in items if "line_group" in item]) == 2


def test_a_groups_parts_carry_one_account_date_and_title(configured):
    """Every field the engine compares across a group is sent byte for byte the
    same on every part, so `LINE_GROUP_FIELDS_DIFFER` has nothing to refuse
    (contract: POST /v1/transactions/batch, "Line groups"): the plan skips a group
    whose rows differ, and sends the parts' shared values from one key."""
    items = _items_for(
        [
            _raw(2, "SIG-1", Cuenta="BCP PEN"),
            _raw(3, "SIG-1", Cuenta=" bcp pen "),
            _raw(4, "SIG-1"),
            _raw(5, "sig-1"),  # another code: never a part of SIG-1
        ]
    )

    parts = [item for item in items if "line_group" in item]
    fields = ("account_id", "date", "title", "line_group")
    shared = {tuple(item[f] for f in fields) for item in parts}
    assert len(parts) == 3 and len(shared) == 1


@respx.mock
def test_a_group_whose_fields_differ_fails_every_part(configured):
    plan = _plan([_raw(2, "SIG-1"), _raw(3, "SIG-1"), _raw(4)])
    _seeded()
    keys = ["transactions.0.date", "transactions.1.date"]
    words = f"Must be the same on every item of line group '{plan.tx_ids[2]}'."
    respx.post(f"{BASE}/v1/transactions/batch").mock(
        side_effect=[
            error_response(
                422,
                "VALIDATION_ERROR",
                "Batch validation failed.",
                dict.fromkeys(keys, words),
                dict.fromkeys(keys, "LINE_GROUP_FIELDS_DIFFER"),
            ),
            _ok(),
        ]
    )

    result = _apply(plan)

    assert (result.tx_created, result.tx_failed) == (1, 2)
    # the engine names both parts, alike: one kind
    line = f"date: {words}"
    assert [(f.words, f.lines) for f in result.failures] == [(line, (2,)), (line, (3,))]
    assert result.failures[0].kind == result.failures[1].kind


# --- LINE_CODES_EXHAUSTED -----------------------------------------------------


@respx.mock
def test_line_codes_exhausted_at_the_batch_stops_the_run_once(configured, monkeypatch):
    """The first chunk lands; the second is refused on its first item; nothing
    more is sent, the refused row is named on its sheet line, the rest once."""
    rows = [_raw(line) for line in range(2, 7)]
    plan = _plan(rows)
    _use_sheet(monkeypatch, rows)
    _seeded()
    route = respx.post(f"{BASE}/v1/transactions/batch").mock(side_effect=[_ok(), _exhausted(0)])

    result = runner.invoke(
        cli_app, ["import", "sheet", "whatever.xlsx", "--apply", "--chunk-size", "2"]
    )

    assert result.exit_code == 1
    assert route.call_count == 2  # no third chunk, nothing sent again
    assert "Transactions: created 2, already-present 0, failed 3" in result.output
    assert result.output.endswith(
        f"Failures (3 rows):\n  id: {_EXHAUSTED[1]} row 4\n  sheet lines 5-6 were not sent\n"
    )
    assert plan.tx_ids[4] not in result.output


@respx.mock
def test_line_codes_exhausted_on_a_group_fails_its_parts_and_stops(configured):
    plan = _plan([_raw(2), _raw(3, "SIG-1"), _raw(4, "SIG-1"), _raw(5)])
    _seeded()
    route = respx.post(f"{BASE}/v1/transactions/batch").mock(side_effect=[_exhausted(1)])

    result = _apply(plan)

    assert route.call_count == 1
    assert (result.tx_created, result.tx_failed) == (0, 4)
    assert [(f.words, f.lines) for f in result.failures] == [
        (f"id: {_EXHAUSTED[1]}", (3,)),
        ("Part of a split transaction refused for another row.", (4,)),
        ("sheet lines 2, 5 were not sent", (2, 5)),  # never the failed lines between them
    ]


@respx.mock
def test_line_codes_exhausted_at_an_opening_balance_ends_the_run(configured, monkeypatch):
    """An opening balance needs a new line too: refused on its `transaction_id`
    (contract: POST /v1/accounts/{account_id}/opening-balance), the run ends there,
    said once in the engine's words, and no batch goes."""
    rows = [_raw(2, None, Descripcion="SALDO INICIAL", Monto=500), _raw(3)]
    _use_sheet(monkeypatch, rows)
    _seeded()
    respx.post(f"{BASE}/v1/accounts/acc-pen/opening-balance").mock(
        return_value=_exhausted(0, key="transaction_id")
    )
    batch = respx.post(f"{BASE}/v1/transactions/batch").mock(side_effect=_created)

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx", "--apply"])

    assert result.exit_code == 1
    assert result.output == (
        f"Error: LIMIT_REACHED — {_EXHAUSTED[0]}\n  transaction_id: {_EXHAUSTED[1]}\n"
    )
    assert not batch.called


@respx.mock
def test_line_codes_exhausted_json_carries_the_row_and_the_unsent(configured, monkeypatch):
    rows = [_raw(2), _raw(3)]
    _use_sheet(monkeypatch, rows)
    _seeded()
    respx.post(f"{BASE}/v1/transactions/batch").mock(side_effect=[_exhausted(0)])

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx", "--apply", "--json"])

    payload = json.loads(result.output)
    assert (payload["tx_created"], payload["tx_failed"]) == (0, 2)
    assert [(f["chunk"], f["lines"], f["words"]) for f in payload["failures"]] == [
        (0, [2], f"id: {_EXHAUSTED[1]}"),
        (0, [3], "sheet line 3 was not sent"),
    ]
    assert (
        payload["failures"][0]["detail"]
        == f"LIMIT_REACHED — {_EXHAUSTED[0]}\n  id: {_EXHAUSTED[1]}"
    )
    assert payload["failures"][1]["detail"] == ""


def test_the_not_sent_line_names_runs_and_skips_settled_rows():
    items = [{"id": str(n)} for n in range(6)]
    line_by_id = {str(n): 10 + n for n in range(6)}

    assert apply_mod._not_sent([0, 1, 3, 4, 5], items, line_by_id) == (
        "sheet lines 10-11, 13-15 were not sent"
    )
    assert apply_mod._not_sent([2], items, line_by_id) == "sheet line 12 was not sent"
    assert apply_mod._not_sent([1, 3], items, line_by_id) == "sheet lines 11, 13 were not sent"
    assert apply_mod._not_sent([], items, line_by_id) == ""
