"""`expense import sheet` shows the statement-line and line-code refusals in the
engine's words, against the sheet lines they hit.

`STATEMENT_LINE_EXISTS` (a statement line already on a live line), and
`DUPLICATE_IN_REQUEST` and `LINE_GROUP_FIELDS_DIFFER` on `statement_line`, fail the
rows they name and the rest go again (contract: POST /v1/transactions/batch,
"Line groups"). `LIMIT_REACHED` with `LINE_CODES_EXHAUSTED` holds for the rest of
the run, so it stops the run once.
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

_TAKEN_WORDS = "Must not be a statement line another bank line already has."
_EXHAUSTED = ("No bank line codes are left.", "No line code is left for a new line.")


def _statement_line_taken(*indices: int, value: str = "SIG-1") -> httpx.Response:
    """Step 4 of a batch: `409` `STATEMENT_LINE_EXISTS` on each line it names,
    a group keyed by its first item (contract: POST /v1/transactions/batch)."""
    keys = [f"transactions.{i}.statement_line" for i in indices]
    return error_response(
        409,
        "CONFLICT",
        f"Another bank line already has statement line '{value}'.",
        dict.fromkeys(keys, _TAKEN_WORDS),
        dict.fromkeys(keys, "STATEMENT_LINE_EXISTS"),
    )


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


# --- STATEMENT_LINE_EXISTS ---------------------------------------------------


@respx.mock
def test_an_edited_row_whose_statement_line_is_in_the_ledger_fails_on_its_sheet_line(
    configured, monkeypatch
):
    """An edited row has a new id, so it is no replay: the engine refuses it for
    its statement line, which the row imported before still holds."""
    rows = [_raw(2, "SIG-1", Monto=-99), _raw(3)]
    plan = _plan(rows)
    _use_sheet(monkeypatch, rows)
    _seeded()
    route = respx.post(f"{BASE}/v1/transactions/batch").mock(
        side_effect=[_statement_line_taken(0), _ok()]
    )

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx", "--apply"])

    assert result.exit_code == 1
    assert "Transactions: created 1, already-present 0, failed 1" in result.output
    assert (
        f"  chunk 0: sheet line 2, id {plan.tx_ids[2]}: "
        "CONFLICT — Another bank line already has statement line 'SIG-1'.\n"
        f"  statement_line: {_TAKEN_WORDS}\n"
    ) in result.output
    assert [[item["id"] for item in sent] for sent in _sent(route)][1] == [plan.tx_ids[3]]


@respx.mock
def test_a_taken_statement_line_on_a_group_fails_every_part_on_its_sheet_line(configured):
    plan = _plan([_raw(2, "SIG-1"), _raw(3, "SIG-1"), _raw(4)])
    _seeded()
    respx.post(f"{BASE}/v1/transactions/batch").mock(side_effect=[_statement_line_taken(0), _ok()])

    result = _apply(plan)

    assert (result.tx_created, result.tx_failed) == (1, 2)
    words = (
        "CONFLICT — Another bank line already has statement line 'SIG-1'.\n"
        f"  statement_line: {_TAKEN_WORDS}"
    )
    assert result.failures == [
        (0, f"sheet line 2, id {plan.tx_ids[2]}: {words}"),
        (0, f"sheet line 3, id {plan.tx_ids[3]}: {words}"),
    ]


# --- DUPLICATE_IN_REQUEST and LINE_GROUP_FIELDS_DIFFER ------------------------


def _items_for(rows) -> list[dict]:
    """The items the import sends for `rows`, as the engine receives them."""
    plan = _plan(rows)
    with respx.mock:
        _seeded()
        route = respx.post(f"{BASE}/v1/transactions/batch").mock(side_effect=_created)
        _apply(plan)
    return [item for sent in _sent(route) for item in sent]


def test_the_import_never_sends_one_statement_line_on_two_lines(configured):
    """Rows sharing a code are one `line_group`, compared as the engine compares
    them, after trimming and case-sensitively, so `DUPLICATE_IN_REQUEST` on
    `statement_line` has nothing to refuse (contract: POST /v1/transactions/batch)."""
    items = _items_for(
        [
            _raw(2, "SIG-1"),
            _raw(3, " SIG-1 "),
            _raw(4, "sig-1"),
            _raw(5, "SIG-1 "),
            _raw(6, "SIG-2"),
        ]
    )

    lines: dict[str, set[str]] = {}
    codes: dict[str, set[str]] = {}
    for item in items:
        line = item.get("line_group", item["id"])
        lines.setdefault(item["statement_line"], set()).add(line)
        codes.setdefault(line, set()).add(item["statement_line"])
    assert all(len(owners) == 1 for owners in lines.values())  # one line per statement line
    assert all(len(held) == 1 for held in codes.values())  # one statement line per line
    assert set(lines) == {"SIG-1", "sig-1", "SIG-2"}
    (case_variant,) = [item for item in items if item["statement_line"] == "sig-1"]
    assert "line_group" not in case_variant  # a code of its own, not a part of SIG-1


def test_a_groups_parts_carry_one_account_date_title_and_statement_line(configured):
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
    fields = ("account_id", "date", "title", "statement_line", "line_group")
    shared = {tuple(item[f] for f in fields) for item in parts}
    assert len(parts) == 3 and len(shared) == 1


@respx.mock
def test_a_duplicate_statement_line_in_a_send_fails_the_rows_it_names(configured):
    """Shown in the engine's words should it come: the row named fails on its
    sheet line, and the rest go again."""
    plan = _plan([_raw(2, "SIG-1"), _raw(3, "SIG-2"), _raw(4)])
    _seeded()
    key = "transactions.1.statement_line"
    route = respx.post(f"{BASE}/v1/transactions/batch").mock(
        side_effect=[
            error_response(
                422,
                "VALIDATION_ERROR",
                "Batch validation failed.",
                {key: "Duplicate statement line within batch."},
                {key: "DUPLICATE_IN_REQUEST"},
            ),
            _ok(),
        ]
    )

    result = _apply(plan)

    assert (result.tx_created, result.tx_failed) == (2, 1)
    assert result.failures == [
        (
            0,
            f"sheet line 3, id {plan.tx_ids[3]}: VALIDATION_ERROR — Batch validation failed.\n"
            "  statement_line: Duplicate statement line within batch.",
        )
    ]
    assert len(_sent(route)[1]) == 2


@respx.mock
def test_a_group_whose_statement_lines_differ_fails_every_part(configured):
    plan = _plan([_raw(2, "SIG-1"), _raw(3, "SIG-1"), _raw(4)])
    _seeded()
    keys = ["transactions.0.statement_line", "transactions.1.statement_line"]
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
    said = f"VALIDATION_ERROR — Batch validation failed.\n  statement_line: {words}"
    assert result.failures == [
        (0, f"sheet line 2, id {plan.tx_ids[2]}: {said}"),
        (0, f"sheet line 3, id {plan.tx_ids[3]}: {said}"),
    ]


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
    assert (
        f"  chunk 1: sheet line 4, id {plan.tx_ids[4]}: LIMIT_REACHED — {_EXHAUSTED[0]}\n"
        f"  id: {_EXHAUSTED[1]}\n"
        "  chunk 1: sheet lines 5-6 were not sent\n"
    ) in result.output
    assert result.output.count("LIMIT_REACHED") == 1


@respx.mock
def test_line_codes_exhausted_on_a_group_fails_its_parts_and_stops(configured):
    plan = _plan([_raw(2), _raw(3, "SIG-1"), _raw(4, "SIG-1"), _raw(5)])
    _seeded()
    route = respx.post(f"{BASE}/v1/transactions/batch").mock(side_effect=[_exhausted(1)])

    result = _apply(plan)

    assert route.call_count == 1
    assert (result.tx_created, result.tx_failed) == (0, 4)
    assert [message.split(":")[0] for _, message in result.failures] == [
        "sheet line 3, id " + plan.tx_ids[3],
        "sheet line 4, id " + plan.tx_ids[4],
        "sheet lines 2, 5 were not sent",  # never the failed lines between them
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
    assert [f["error"].split(":")[0] for f in payload["failures"]] == [
        f"sheet line 2, id {_plan(rows).tx_ids[2]}",
        "sheet line 3 was not sent",
    ]


def test_the_not_sent_line_names_runs_and_skips_settled_rows():
    items = [{"id": str(n)} for n in range(6)]
    line_by_id = {str(n): 10 + n for n in range(6)}

    assert apply_mod._not_sent([0, 1, 3, 4, 5], items, line_by_id) == (
        "sheet lines 10-11, 13-15 were not sent"
    )
    assert apply_mod._not_sent([2], items, line_by_id) == "sheet line 12 was not sent"
    assert apply_mod._not_sent([1, 3], items, line_by_id) == "sheet lines 11, 13 were not sent"
    assert apply_mod._not_sent([], items, line_by_id) == ""
