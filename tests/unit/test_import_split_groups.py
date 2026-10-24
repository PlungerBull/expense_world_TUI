"""`expense import sheet` and `COD_EECC`: rows sharing one come in as one movement.

Rows sharing a `COD_EECC` go as the items of one `line_group` (contract: POST
/v1/transactions/batch, "Line groups"); the code only groups, and no row sends it
or any `statement_line`. A group whose rows differ on account, date or title is
skipped whole as `split-mismatch`, and the rest imports.
"""

import json

import httpx
import respx
from typer.testing import CliRunner

from expense import config as config_module
from expense.http import ExpenseClient
from expense.import_ import apply as apply_mod
from expense.import_ import plan as plan_mod
from expense.import_.parse import ParsedRow, parse_sheet
from expense.import_.reader import RawRow, SheetData
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import error_response, real_cli_app

runner = CliRunner()
cli_app = real_cli_app()

HEADERS = ["Descripcion", "CATEGORY", "HASHTAG", "Fecha", "Monto", "Cuenta", "Moneda", "COD_EECC"]


def _raw(line: int, code: object = None, **over: object) -> RawRow:
    base: dict[str, object] = {
        "Descripcion": "SUPERMERCADO NORTE",
        "CATEGORY": "WANTS",
        "HASHTAG": "Casa",
        "Fecha": "2026-03-14",
        "Monto": -10 * line,
        "Cuenta": "BCP PEN",
        "Moneda": "PEN",
        "COD_EECC": code,
    }
    base.update(over)
    return RawRow(line=line, cells=[base[h] for h in HEADERS])


def _sheet(rows: list[RawRow], headers: list[str] = HEADERS) -> SheetData:
    return SheetData(headers=list(headers), rows=rows)


def _plan(rows: list[RawRow]) -> plan_mod.ImportPlan:
    parsed, openings, skipped = parse_sheet(_sheet(rows))
    return plan_mod.build_plan(parsed, openings, skipped)


def _prow(line: int, code: str | None, **over: object) -> ParsedRow:
    base: dict[str, object] = dict(
        line=line,
        title="SUPERMERCADO NORTE",
        category="WANTS",
        hashtag="Casa",
        date_iso="2026-03-14",
        amount_cents=-1000 * line,
        currency="PEN",
        account="BCP PEN",
        description=None,
        group_code=code,
    )
    base.update(over)
    return ParsedRow(**base)  # type: ignore[arg-type]


# --- reading COD_EECC --------------------------------------------------------


def test_cod_eecc_is_each_rows_group_code_and_blank_is_none():
    rows = [_raw(2, "SIG-202603-029"), _raw(3, "  "), _raw(4, None), _raw(5, "None")]
    parsed, _, _ = parse_sheet(_sheet(rows))

    assert [r.group_code for r in parsed] == ["SIG-202603-029", None, None, None]


def test_cod_eecc_is_trimmed():
    parsed, _, _ = parse_sheet(_sheet([_raw(2, "  SIG-202603-029 ")]))

    assert parsed[0].group_code == "SIG-202603-029"


def test_a_sheet_without_the_column_imports_every_row_alone():
    headers = HEADERS[:-1]
    rows = [RawRow(line, _raw(line, "SIG-1").cells[:-1]) for line in (2, 3)]
    parsed, openings, skipped = parse_sheet(_sheet(rows, headers))
    plan = plan_mod.build_plan(parsed, openings, skipped)

    assert [r.group_code for r in parsed] == [None, None]
    assert plan.groups == [] and plan.movements == 2 and plan.skipped == []


# --- the plan ---------------------------------------------------------------


def test_rows_sharing_a_code_are_one_split_transaction():
    plan = _plan(
        [
            _raw(2, "SIG-1"),
            _raw(3, None),
            _raw(4, "SIG-1"),
            _raw(5, "SIG-2"),
            _raw(6, "SIG-1"),
        ]
    )

    (group,) = plan.groups
    assert (group.group_code, group.lines) == ("SIG-1", (2, 4, 6))
    assert group.name == plan.tx_ids[2]
    assert (len(plan.rows), plan.movements, plan.split_rows) == (5, 3, 3)


def test_no_payload_carries_a_statement_line_for_a_row_or_a_part():
    """`build_tx_payload` sends neither the row's COD_EECC nor a `statement_line`:
    not for a row alone, and not for a group's part."""
    res = apply_mod.ResolveResult(
        account_ids={("bcp pen", "PEN"): "acc-pen"},
        category_ids={"wants": "cat"},
        hashtag_ids={"casa": "tag"},
    )
    row = _prow(2, "SIG-1")

    alone = apply_mod.build_tx_payload(row, "tx-2", res)
    part = apply_mod.build_tx_payload(row, "tx-2", res, line_group="tx-2")

    assert "statement_line" not in alone and "statement_line" not in part
    assert "SIG-1" not in json.dumps(alone) and "SIG-1" not in json.dumps(part)
    assert part["line_group"] == "tx-2" and "line_group" not in alone


def test_the_ids_do_not_depend_on_the_code():
    """An earlier import of the sheet, before COD_EECC was read, counts as already there."""
    assert plan_mod.tx_id_for(_prow(2, "SIG-1")) == plan_mod.tx_id_for(_prow(2, None))


def test_a_group_on_two_dates_is_skipped_whole_and_the_rest_imports():
    plan = plan_mod.build_plan(
        [
            _prow(3120, "SIG-202603-029"),
            _prow(3121, "SIG-202603-029"),
            _prow(3122, "SIG-202603-029", date_iso="2026-03-15"),
            _prow(3123, "SIG-202603-030"),
            _prow(3124, None),
        ],
        [],
        [],
    )

    assert [r.line for r in plan.rows] == [3123, 3124]
    assert [(s.line, s.reason, s.detail) for s in plan.skipped] == [
        (line, "split-mismatch", "SIG-202603-029") for line in (3120, 3121, 3122)
    ]
    assert plan.split_mismatches == [
        "SIG-202603-029: line 3120 is 2026-03-14, line 3122 is 2026-03-15."
    ]
    assert plan.groups == []


def test_a_group_on_two_accounts_is_skipped_naming_them():
    plan = plan_mod.build_plan(
        [_prow(10, "SIG-1"), _prow(11, "SIG-1", account="Interbank")], [], []
    )

    assert plan.split_mismatches == ["SIG-1: line 10 is BCP PEN [PEN], line 11 is Interbank [PEN]."]
    assert plan.rows == []


def test_a_group_on_two_currencies_of_one_name_is_two_accounts():
    plan = plan_mod.build_plan([_prow(10, "SIG-1"), _prow(11, "SIG-1", currency="USD")], [], [])

    assert plan.split_mismatches == ["SIG-1: line 10 is BCP PEN [PEN], line 11 is BCP PEN [USD]."]


def test_a_group_whose_account_differs_only_in_case_is_one_account():
    """Rows resolve to an account ignoring case and spaces, so they agree."""
    plan = plan_mod.build_plan([_prow(10, "SIG-1"), _prow(11, "SIG-1", account=" bcp pen")], [], [])

    assert plan.split_mismatches == [] and len(plan.groups) == 1


def test_a_group_on_two_titles_is_skipped_naming_them():
    plan = plan_mod.build_plan(
        [_prow(10, "SIG-1"), _prow(11, "SIG-1"), _prow(12, "SIG-1", title="FARMACIA")], [], []
    )

    assert plan.split_mismatches == [
        'SIG-1: line 10 is "SUPERMERCADO NORTE", line 12 is "FARMACIA".'
    ]
    assert [s.reason for s in plan.skipped] == ["split-mismatch"] * 3


def test_a_group_differing_on_two_fields_gets_a_line_for_each():
    plan = plan_mod.build_plan(
        [_prow(10, "SIG-1"), _prow(11, "SIG-1", date_iso="2026-03-15", title="FARMACIA")], [], []
    )

    assert plan.split_mismatches == [
        "SIG-1: line 10 is 2026-03-14, line 11 is 2026-03-15.",
        'SIG-1: line 10 is "SUPERMERCADO NORTE", line 11 is "FARMACIA".',
    ]


def test_a_skipped_groups_names_are_not_ensured():
    plan = plan_mod.build_plan(
        [_prow(10, "SIG-1", category="ONLY HERE"), _prow(11, "SIG-1", date_iso="2026-03-15")],
        [],
        [],
    )

    assert plan.categories == [] and plan.accounts == []


# --- what goes to the engine ------------------------------------------------


def _seeded() -> None:
    def whole(rows):
        return lambda request: httpx.Response(200, json={"items": rows})

    respx.get(f"{BASE}/v1/accounts").mock(
        side_effect=whole([{"id": "acc-pen", "name": "BCP PEN", "currency_code": "PEN"}])
    )
    respx.get(f"{BASE}/v1/categories").mock(side_effect=whole([{"id": "c", "name": "WANTS"}]))
    respx.get(f"{BASE}/v1/hashtags").mock(side_effect=whole([{"id": "h", "name": "Casa"}]))


def _apply(plan: plan_mod.ImportPlan, chunk_size: int = 200) -> apply_mod.ApplyResult:
    cfg = config_module.ensure_loaded()
    with ExpenseClient(cfg) as client:
        res = apply_mod.resolve_or_create(client, plan)
        return apply_mod.apply_plan(client, plan, res, chunk_size=chunk_size)


def _sent(route) -> list[list[dict]]:
    return [json.loads(call.request.content)["transactions"] for call in route.calls]


@respx.mock
def test_a_group_goes_as_one_line_group_and_no_row_sends_a_statement_line(configured):
    plan = _plan([_raw(2, "SIG-1"), _raw(3, "SIG-2"), _raw(4, None), _raw(5, "SIG-1")])
    _seeded()
    route = respx.post(f"{BASE}/v1/transactions/batch").mock(
        return_value=httpx.Response(201, json={"created": []})
    )

    result = _apply(plan)

    (sent,) = _sent(route)
    by_line = {plan.tx_ids[line]: line for line in (2, 3, 4, 5)}
    assert [by_line[item["id"]] for item in sent] == [2, 5, 3, 4]  # the group's parts together
    group, coded, blank = sent[:2], sent[2], sent[3]
    assert {item["line_group"] for item in group} == {plan.tx_ids[2]}
    assert "line_group" not in coded and "line_group" not in blank
    # COD_EECC only groups: no part, coded row or blank row sends a statement line
    assert [item for item in sent if "statement_line" in item] == []
    assert result.tx_created == 4


@respx.mock
def test_codes_differing_only_in_case_are_two_movements(configured):
    """Rows group by the code's exact text, trimmed: case counts."""
    plan = _plan([_raw(2, "SIG-1"), _raw(3, "sig-1"), _raw(4, "SIG-1")])
    _seeded()
    route = respx.post(f"{BASE}/v1/transactions/batch").mock(
        return_value=httpx.Response(201, json={"created": []})
    )

    result = _apply(plan)

    (group,) = plan.groups
    assert (group.group_code, group.lines) == ("SIG-1", (2, 4))
    (sent,) = _sent(route)
    by_line = {plan.tx_ids[line]: line for line in (2, 3, 4)}
    assert [by_line[item["id"]] for item in sent] == [2, 4, 3]
    assert [item for item in sent if "statement_line" in item] == []
    assert {item["line_group"] for item in sent[:2]} == {plan.tx_ids[2]}
    assert "line_group" not in sent[2]
    assert result.tx_created == 3


@respx.mock
def test_a_chunk_boundary_inside_a_group_moves_the_group_to_the_next_chunk(configured):
    plan = _plan([_raw(2), _raw(3, "SIG-1"), _raw(4, "SIG-1"), _raw(5)])
    _seeded()
    route = respx.post(f"{BASE}/v1/transactions/batch").mock(
        return_value=httpx.Response(201, json={"created": []})
    )

    result = _apply(plan, chunk_size=2)

    ids = [[item["id"] for item in sent] for sent in _sent(route)]
    assert ids == [[plan.tx_ids[2]], [plan.tx_ids[3], plan.tx_ids[4]], [plan.tx_ids[5]]]
    assert result.tx_created == 4


def _all_taken(request: httpx.Request) -> httpx.Response:
    """A batch sent again whole: `409` `ID_EXISTS` on every item, a line group's
    included (contract: POST /v1/transactions/batch)."""
    keys = [f"transactions.{i}.id" for i in range(len(json.loads(request.content)["transactions"]))]
    return error_response(
        409,
        "CONFLICT",
        f"{len(keys)} of these ids are already taken.",
        dict.fromkeys(keys, "A transaction with this id already exists."),
        dict.fromkeys(keys, "ID_EXISTS"),
    )


@respx.mock
def test_a_re_run_counts_every_row_already_there_groups_included(configured):
    plan = _plan([_raw(2, "SIG-1"), _raw(3, "SIG-1"), _raw(4, "SIG-2"), _raw(5), _raw(6, "SIG-3")])
    _seeded()
    route = respx.post(f"{BASE}/v1/transactions/batch").mock(side_effect=_all_taken)

    result = _apply(plan, chunk_size=3)

    assert route.call_count == 2  # one request per chunk
    assert (result.tx_created, result.tx_skipped_existing, result.tx_failed) == (0, 5, 0)
    assert result.failures == []


@respx.mock
def test_a_fixed_group_comes_in_on_a_re_run_while_the_rest_is_already_there(configured):
    """The first run skipped lines 3-4; once the date is fixed, they go and land."""
    _seeded()
    fixed = _plan([_raw(2), _raw(3, "SIG-1"), _raw(4, "SIG-1")])
    landed = {fixed.tx_ids[2]}

    def engine(request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.content)["transactions"]
        taken = [f"transactions.{i}.id" for i, item in enumerate(sent) if item["id"] in landed]
        if taken:
            return error_response(
                409,
                "CONFLICT",
                "A transaction with id 'x' already exists.",
                dict.fromkeys(taken, "A transaction with this id already exists."),
                dict.fromkeys(taken, "ID_EXISTS"),
            )
        return httpx.Response(201, json={"created": []})

    route = respx.post(f"{BASE}/v1/transactions/batch").mock(side_effect=engine)

    result = _apply(fixed)

    assert (result.tx_created, result.tx_skipped_existing, result.tx_failed) == (2, 1, 0)
    last = _sent(route)[-1]
    assert [item["id"] for item in last] == [fixed.tx_ids[3], fixed.tx_ids[4]]
    assert {item["line_group"] for item in last} == {fixed.tx_ids[3]}


@respx.mock
def test_a_part_whose_category_was_not_created_keeps_its_whole_group_back(configured):
    plan = _plan([_raw(2, "SIG-1"), _raw(3, "SIG-1", CATEGORY="NEW"), _raw(4)])
    _seeded()
    respx.post(f"{BASE}/v1/categories").mock(
        return_value=error_response(422, "VALIDATION_ERROR", "Invalid input.", {"name": "Bad."})
    )
    route = respx.post(f"{BASE}/v1/transactions/batch").mock(
        return_value=httpx.Response(201, json={"created": []})
    )

    result = _apply(plan)

    assert [[item["id"] for item in sent] for sent in _sent(route)] == [[plan.tx_ids[4]]]
    assert (result.tx_created, result.tx_failed) == (1, 2)
    assert [(f.words, f.lines) for f in result.failures] == [
        ("Part of a split transaction not sent for another row.", (2,)),
        ("Not sent: category 'NEW' was not created.", (3,)),
    ]


# --- what the command prints ------------------------------------------------


def _use_sheet(monkeypatch, rows: list[RawRow]) -> None:
    from expense.commands import import_cmd

    monkeypatch.setattr(import_cmd, "read_workbook", lambda path, **k: _sheet(rows))


def _nine_groups() -> list[RawRow]:
    """9 split transactions of 30 rows, 2 rows alone, and 2 zero amounts."""
    rows: list[RawRow] = []
    line = 2
    for g, size in enumerate([6, 4, 3, 3, 3, 3, 3, 3, 2]):
        for _ in range(size):
            rows.append(_raw(line, f"SIG-{g}"))
            line += 1
    rows += [_raw(line, None), _raw(line + 1, "SIG-X")]
    rows += [_raw(line + 2, Monto=0), _raw(line + 3, Monto=0)]
    return rows


def test_dry_run_counts_the_split_transactions_in_one_line(configured, monkeypatch):
    _use_sheet(monkeypatch, _nine_groups())

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx"])

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[:3] == [
        "Parsed 32 transactions to import, as 11 movements.",
        "Skipped 2 row(s) — zero-amount: 2",
        "9 split transactions (30 rows) come in as one movement each.",
    ]
    assert lines[3] == ""
    assert lines[4].startswith("Accounts to ensure")


def test_dry_run_says_one_split_transaction_in_the_singular(configured, monkeypatch):
    _use_sheet(monkeypatch, [_raw(2, "SIG-1"), _raw(3, "SIG-1"), _raw(4, "SIG-1"), _raw(5)])

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx"])

    assert result.output.splitlines()[:2] == [
        "Parsed 4 transactions to import, as 2 movements.",
        "1 split transaction (3 rows) comes in as one movement.",
    ]


def test_dry_run_has_no_split_line_with_no_group(configured, monkeypatch):
    _use_sheet(monkeypatch, [_raw(2, "SIG-1"), _raw(3)])

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx"])

    assert "split transaction" not in result.output
    assert result.output.splitlines()[:2] == [
        "Parsed 2 transactions to import, as 2 movements.",
        "",
    ]


def test_dry_run_says_one_movement_in_the_singular(configured, monkeypatch):
    _use_sheet(monkeypatch, [_raw(2, "SIG-1"), _raw(3, "SIG-1")])

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx"])

    assert result.output.splitlines()[0] == "Parsed 2 transactions to import, as 1 movement."


def _mismatched() -> list[RawRow]:
    return [
        _raw(3120, "SIG-202603-029"),
        _raw(3121, "SIG-202603-029"),
        _raw(3122, "SIG-202603-029", Fecha="2026-03-15"),
        _raw(3123, Monto=0),
        _raw(3124, Monto=0),
        _raw(3125),
    ]


_MISMATCH_LINES = [
    "Skipped 5 row(s) — split-mismatch: 3, zero-amount: 2",
    "  SIG-202603-029: line 3120 is 2026-03-14, line 3122 is 2026-03-15.",
]


def test_dry_run_shows_a_split_mismatch_under_the_skipped_line(configured, monkeypatch):
    _use_sheet(monkeypatch, _mismatched())

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx"])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[:3] == [
        "Parsed 1 transactions to import, as 1 movement.",
        *_MISMATCH_LINES,
    ]


@respx.mock
def test_apply_shows_a_split_mismatch_and_imports_the_rest(configured, monkeypatch):
    _use_sheet(monkeypatch, _mismatched())
    _seeded()
    route = respx.post(f"{BASE}/v1/transactions/batch").mock(
        return_value=httpx.Response(201, json={"created": []})
    )

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx", "--apply"])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[:2] == _MISMATCH_LINES
    assert "Transactions: created 1, already-present 0, failed 0" in result.output
    assert [len(sent) for sent in _sent(route)] == [1]


def test_dry_run_json_carries_the_counts(configured, monkeypatch):
    _use_sheet(monkeypatch, [*_nine_groups(), *_mismatched()])

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx", "--json"])

    payload = json.loads(result.output)
    assert (payload["valid_rows"], payload["movements"]) == (33, 12)
    assert (payload["split_transactions"], payload["split_rows"]) == (9, 30)
    assert payload["split_mismatches"] == [
        "SIG-202603-029: line 3120 is 2026-03-14, line 3122 is 2026-03-15."
    ]
    skipped = [tuple(s.values()) for s in payload["skipped"]]  # line, reason, detail
    assert [s for s in skipped if s[1] == "split-mismatch"] == [
        (line, "split-mismatch", "SIG-202603-029") for line in (3120, 3121, 3122)
    ]


@respx.mock
def test_apply_json_carries_the_skipped_rows_and_mismatches(configured, monkeypatch):
    _use_sheet(monkeypatch, _mismatched())
    _seeded()
    respx.post(f"{BASE}/v1/transactions/batch").mock(
        return_value=httpx.Response(201, json={"created": []})
    )

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx", "--apply", "--json"])

    payload = json.loads(result.output)
    assert payload["tx_created"] == 1
    assert payload["split_mismatches"] == [_MISMATCH_LINES[1].strip()]
    assert [s["reason"] for s in payload["skipped"]].count("split-mismatch") == 3


# --- a part the parse skipped -------------------------------------------------


def _bad_date_group() -> list[RawRow]:
    return [
        _raw(3120, "SIG-202603-029"),
        _raw(3121, "SIG-202603-029"),
        _raw(3122, "SIG-202603-029", Fecha="not a date"),
        _raw(3123),
    ]


_WAITING_LINES = [
    "Skipped 3 row(s) — bad-date: 1, split-mismatch: 2",
    "  SIG-202603-029: line 3122 can't be read, so lines 3120, 3121 wait for it.",
]


def test_a_skipped_row_carries_its_code():
    _, _, skipped = parse_sheet(_sheet([_raw(2, "SIG-1", Fecha="not a date")]))

    assert [(s.reason, s.group_code) for s in skipped] == [("bad-date", "SIG-1")]


def test_a_part_the_parse_skipped_holds_back_its_group():
    plan = _plan(_bad_date_group())

    assert [r.line for r in plan.rows] == [3123]
    assert plan.groups == []
    assert [(s.line, s.reason) for s in plan.skipped] == [
        (3122, "bad-date"),
        (3120, "split-mismatch"),
        (3121, "split-mismatch"),
    ]
    assert plan.split_mismatches == [_WAITING_LINES[1].strip()]


def test_any_parse_skip_but_a_zero_amount_holds_back_the_group():
    for over in ({"Moneda": "XXX"}, {"Monto": "abc"}, {"CATEGORY": None}, {"Descripcion": None}):
        plan = _plan([_raw(2, "SIG-1"), _raw(3, "SIG-1", **over)])
        assert plan.rows == [], over
        assert plan.split_mismatches == ["SIG-1: line 3 can't be read, so line 2 waits for it."]


def test_two_unreadable_parts_are_named_together():
    plan = _plan([_raw(2, "SIG-1", Fecha="x"), _raw(3, "SIG-1"), _raw(4, "SIG-1", Fecha="y")])

    assert plan.split_mismatches == ["SIG-1: lines 2, 4 can't be read, so line 3 waits for them."]


def test_held_back_groups_are_named_in_sheet_order():
    plan = _plan(
        [
            _raw(2, "SIG-B", Fecha="x"),
            _raw(3, "SIG-A"),
            _raw(4, "SIG-A", Fecha="2026-03-15"),
            _raw(5, "SIG-B"),
        ]
    )

    assert plan.split_mismatches == [
        "SIG-B: line 2 can't be read, so line 5 waits for it.",
        "SIG-A: line 3 is 2026-03-14, line 4 is 2026-03-15.",
    ]


def test_a_zero_amount_part_is_dropped_and_the_rest_goes_as_one_group():
    plan = _plan([_raw(2, "SIG-1"), _raw(3, "SIG-1", Monto=0), _raw(4, "SIG-1")])

    (group,) = plan.groups
    assert group.lines == (2, 4)
    assert [(s.line, s.reason) for s in plan.skipped] == [(3, "zero-amount")]
    assert plan.split_mismatches == []


@respx.mock
def test_a_group_left_with_one_row_goes_alone(configured):
    plan = _plan([_raw(2, "SIG-1"), _raw(3, "SIG-1", Monto=0)])
    _seeded()
    route = respx.post(f"{BASE}/v1/transactions/batch").mock(
        return_value=httpx.Response(201, json={"created": []})
    )

    result = _apply(plan)

    ((item,),) = _sent(route)
    assert "line_group" not in item and "statement_line" not in item
    assert plan.groups == [] and result.tx_created == 1


def test_dry_run_names_the_unreadable_part_and_the_rows_waiting(configured, monkeypatch):
    _use_sheet(monkeypatch, _bad_date_group())

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx"])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[:3] == [
        "Parsed 1 transactions to import, as 1 movement.",
        *_WAITING_LINES,
    ]


@respx.mock
def test_apply_holds_back_the_group_and_imports_the_rest(configured, monkeypatch):
    _use_sheet(monkeypatch, _bad_date_group())
    _seeded()
    route = respx.post(f"{BASE}/v1/transactions/batch").mock(
        return_value=httpx.Response(201, json={"created": []})
    )

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx", "--apply"])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[:2] == _WAITING_LINES
    only = _plan(_bad_date_group()).tx_ids[3123]
    assert [[item["id"] for item in sent] for sent in _sent(route)] == [[only]]


@respx.mock
def test_once_fixed_a_re_run_brings_the_whole_group_in(configured):
    """Line 3123 landed on the first run; the group, its date fixed, now goes whole."""
    rows = _bad_date_group()
    rows[2] = _raw(3122, "SIG-202603-029")
    fixed = _plan(rows)
    _seeded()
    landed = {fixed.tx_ids[3123]}

    def engine(request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.content)["transactions"]
        taken = [f"transactions.{i}.id" for i, item in enumerate(sent) if item["id"] in landed]
        if taken:
            return error_response(
                409,
                "CONFLICT",
                "A transaction with id 'x' already exists.",
                dict.fromkeys(taken, "A transaction with this id already exists."),
                dict.fromkeys(taken, "ID_EXISTS"),
            )
        return httpx.Response(201, json={"created": []})

    route = respx.post(f"{BASE}/v1/transactions/batch").mock(side_effect=engine)

    result = _apply(fixed)

    assert (result.tx_created, result.tx_skipped_existing, result.tx_failed) == (3, 1, 0)
    last = _sent(route)[-1]
    assert [item["id"] for item in last] == [fixed.tx_ids[line] for line in (3120, 3121, 3122)]
    assert {item["line_group"] for item in last} == {fixed.tx_ids[3120]}
    assert [item for item in last if "statement_line" in item] == []
