"""Refused rows read one line per kind of error: each refused field's name and the
engine's words for it, then the rows they hit (screens 1 A, 2 A and 3 A,
docs/mockups/expense-world-grouped-refusals.html).

The batch writer says what kind each failure is (`BatchFailure.kind`),
`formatting.grouped_refusals` turns kinds into lines, and the sheet import and
the LOG bar both print those lines. This file pins the shared pieces and what
`expense import sheet --apply` prints; `test_tui_log_bar.py` pins the LOG bar's.
"""

import json

import httpx
import respx
from typer.testing import CliRunner

from expense.batch_write import SPLIT_PART_KIND, post_transaction_batch
from expense.errors import EngineError, row_words
from expense.formatting import grouped_refusals, rows_phrase
from expense.import_.apply import SPLIT_PART_NOT_SENT, SPLIT_PART_REFUSED
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import error_response, real_cli_app
from tests.unit.test_batch_write import _Client, _invalid, _items, _refusal
from tests.unit.test_import_split_groups import _apply, _plan, _raw, _seeded, _use_sheet

runner = CliRunner()
cli_app = real_cli_app()

_ZERO = "Must not be zero."
_SEALED = "The date falls inside a completed reconciliation's period."
_ZERO_LINE = f"amount_cents: {_ZERO}"
_SEALED_LINE = f"date: {_SEALED}"


# --- the shared lines ------------------------------------------------------------


def test_rows_phrase_names_one_row_or_several_in_order():
    assert rows_phrase([41]) == "row 41"
    assert rows_phrase([9, 3, 5, 7, 3]) == "rows 3, 5, 7, 9"


def test_grouped_refusals_joins_a_kind_and_keeps_an_own_line_alone():
    lines = grouped_refusals(
        [
            ("a", "Words A.", [3]),
            ("b", "CODE — message\n  key: words\n\nThe app's line.", [4]),
            (None, "sheet lines 6-7 were not sent", [6, 7]),
            ("a", "Words A.", [5]),
            (None, "sheet lines 6-7 were not sent", [6, 7]),
        ]
    )
    assert lines == [
        ("Words A.", "rows 3, 5", []),
        ("CODE — message", "row 4", ["  key: words", "The app's line."]),  # no blank line
        ("sheet lines 6-7 were not sent", "", []),
        ("sheet lines 6-7 were not sent", "", []),  # never joined, even alike
    ]


def test_row_words_name_each_field_then_its_words():
    """Screen 3 A: the field the engine names, then its words; two fields on one
    row are kept apart by ` · `; a refusal naming no field reads its message."""
    one = EngineError("VALIDATION_ERROR", "Invalid input.", {"date": "Must not be null."}, 422, {})
    two = EngineError(
        "VALIDATION_ERROR",
        "Invalid input.",
        {"amount_cents": _ZERO, "date": "Must not be null."},
        422,
        {},
    )
    none = EngineError("CONFLICT", "It changed at the same moment.", None, 409, {})
    assert row_words(one) == "date: Must not be null."
    assert row_words(two) == "amount_cents: Must not be zero. · date: Must not be null."
    assert row_words(none) == "It changed at the same moment."


# --- the batch writer's kinds ----------------------------------------------------


def test_a_kind_is_the_rows_words_never_the_count_message():
    """Two sends of one refusal, worded differently at the top (a count of the
    items), are one kind: the rows' own code, fields and reasons."""
    first = _invalid(1)
    second = _refusal(
        "VALIDATION_ERROR",
        422,
        "2 of these items are not valid.",
        {"transactions.1.amount_cents": (_ZERO, "ZERO_AMOUNT")},
    )
    outcome = post_transaction_batch(_Client([first, second, {}]), _items(4))

    assert len(outcome.failures) == 2
    assert outcome.failures[0].kind == outcome.failures[1].kind


def test_two_reasons_are_two_kinds():
    refusal = _refusal(
        "VALIDATION_ERROR",
        422,
        "Batch validation failed.",
        {
            "transactions.0.amount_cents": (_ZERO, "ZERO_AMOUNT"),
            "transactions.1.date": (_SEALED, "SEALED_PERIOD"),
            "transactions.2.amount_cents": (_ZERO, "ZERO_AMOUNT"),
        },
    )
    outcome = post_transaction_batch(_Client([refusal, {}]), _items(4))

    zero, sealed, zero_again = sorted(outcome.failures, key=lambda f: f.indices)
    assert zero.kind == zero_again.kind != sealed.kind


def test_a_part_the_engine_did_not_name_fails_for_the_part_it_did():
    items = _items(3)
    for item in items[:2]:
        item["line_group"] = "g"
    outcome = post_transaction_batch(_Client([_invalid(1), {}]), items)

    part, named = sorted(outcome.failures, key=lambda f: f.indices)
    assert (part.indices, part.for_part, part.kind) == ((0,), True, SPLIT_PART_KIND)
    assert (named.indices, named.for_part) == ((1,), False)
    assert part.error.fields == {"amount_cents": _ZERO}  # the refused part's own words


def test_a_refusal_naming_no_row_is_a_kind_of_its_own_per_send():
    whole = EngineError("FORBIDDEN", "nope", None, 403, {})
    outcome = post_transaction_batch(_Client([whole, whole]), _items(4), chunk_size=2)

    assert [f.whole_chunk for f in outcome.failures] == [True, True]
    assert outcome.failures[0].kind != outcome.failures[1].kind


# --- the sheet import's Failures block -------------------------------------------


def _zero(*indices: int, message: str = "Batch validation failed.") -> httpx.Response:
    keys = [f"transactions.{i}.amount_cents" for i in indices]
    return error_response(
        422,
        "VALIDATION_ERROR",
        message,
        dict.fromkeys(keys, _ZERO),
        dict.fromkeys(keys, "ZERO_AMOUNT"),
    )


def _ok() -> httpx.Response:
    return httpx.Response(201, json={"created": []})


@respx.mock
def test_failures_read_one_line_per_kind_with_one_row_or_several(configured, monkeypatch):
    rows = [_raw(n) for n in range(2, 7)]
    plan = _plan(rows)
    _use_sheet(monkeypatch, rows)
    _seeded()
    two_kinds = error_response(
        422,
        "VALIDATION_ERROR",
        "Batch validation failed.",
        {
            "transactions.0.amount_cents": _ZERO,
            "transactions.2.amount_cents": _ZERO,
            "transactions.3.date": _SEALED,
        },
        {
            "transactions.0.amount_cents": "ZERO_AMOUNT",
            "transactions.2.amount_cents": "ZERO_AMOUNT",
            "transactions.3.date": "SEALED_PERIOD",
        },
    )
    respx.post(f"{BASE}/v1/transactions/batch").mock(side_effect=[two_kinds, _ok()])

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx", "--apply"])

    assert result.exit_code == 1
    assert "Transactions: created 2, already-present 0, failed 3" in result.output
    assert result.output.endswith(
        f"Failures (3 rows):\n  {_ZERO_LINE} rows 2, 4\n  {_SEALED_LINE} row 5\n"
    )
    assert "chunk" not in result.output and plan.tx_ids[2] not in result.output


@respx.mock
def test_one_kind_across_two_chunks_is_one_line(configured, monkeypatch):
    """The second chunk's refusal counts its items at the top; its row's words
    are the first chunk's, so both rows share the line."""
    rows = [_raw(n) for n in range(2, 6)]
    _use_sheet(monkeypatch, rows)
    _seeded()
    respx.post(f"{BASE}/v1/transactions/batch").mock(
        side_effect=[_zero(1), _ok(), _zero(0, message="1 of these items is not valid."), _ok()]
    )

    result = runner.invoke(
        cli_app, ["import", "sheet", "whatever.xlsx", "--apply", "--chunk-size", "2"]
    )

    assert result.output.endswith(f"Failures (2 rows):\n  {_ZERO_LINE} rows 3, 4\n")


@respx.mock
def test_a_split_transactions_other_rows_read_the_apps_line(configured, monkeypatch):
    """Rows 2-3 and 5-6 are two split transactions; the engine refuses row 3 and
    row 6. Rows 2 and 5 failed for them, and say so on one line of their own."""
    rows = [_raw(2, "SIG-1"), _raw(3, "SIG-1"), _raw(4), _raw(5, "SIG-2"), _raw(6, "SIG-2")]
    _use_sheet(monkeypatch, rows)
    _seeded()
    respx.post(f"{BASE}/v1/transactions/batch").mock(side_effect=[_zero(1, 4), _ok()])

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx", "--apply"])

    assert result.output.endswith(
        f"Failures (4 rows):\n  {SPLIT_PART_REFUSED} rows 2, 5\n  {_ZERO_LINE} rows 3, 6\n"
    )


@respx.mock
def test_a_refusal_naming_no_row_stays_on_its_own_line(configured, monkeypatch):
    """A chunk refused for no row of its own reads whole, its rows after it, and
    never joins the line of a row-level refusal."""
    rows = [_raw(n) for n in range(2, 6)]
    _use_sheet(monkeypatch, rows)
    _seeded()
    respx.post(f"{BASE}/v1/transactions/batch").mock(
        side_effect=[error_response(403, "FORBIDDEN", "nope"), _zero(0), _ok()]
    )

    result = runner.invoke(
        cli_app, ["import", "sheet", "whatever.xlsx", "--apply", "--chunk-size", "2"]
    )

    assert result.output.endswith(
        f"Failures (3 rows):\n  FORBIDDEN — nope rows 2, 3\n  {_ZERO_LINE} row 4\n"
    )


@respx.mock
def test_json_keeps_one_entry_per_row_with_the_engines_whole_refusal(configured, monkeypatch):
    rows = [_raw(n) for n in range(2, 5)]
    _use_sheet(monkeypatch, rows)
    _seeded()
    respx.post(f"{BASE}/v1/transactions/batch").mock(side_effect=[_zero(0, 2), _ok()])

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx", "--apply", "--json"])

    detail = f"VALIDATION_ERROR — Batch validation failed.\n  amount_cents: {_ZERO}"
    failures = json.loads(result.output)["failures"]
    # the import's own keys, compared as a tuple: the drift check reads dict literals
    keys = ("chunk", "lines", "words", "detail")
    assert [tuple(sorted(f)) for f in failures] == [tuple(sorted(keys))] * 2
    assert [tuple(f[k] for k in keys) for f in failures] == [
        (0, [2], _ZERO_LINE, detail),
        (0, [4], _ZERO_LINE, detail),
    ]


@respx.mock
def test_apply_records_each_rows_kind(configured):
    plan = _plan([_raw(2, "SIG-1"), _raw(3, "SIG-1")])
    _seeded()
    respx.post(f"{BASE}/v1/transactions/batch").mock(side_effect=[_zero(1)])

    result = _apply(plan)

    part, named = result.failures
    assert (part.words, part.lines, part.kind) == (SPLIT_PART_REFUSED, (2,), SPLIT_PART_KIND)
    assert part.detail == ""
    assert (named.words, named.lines) == (_ZERO_LINE, (3,))


@respx.mock
def test_one_field_name_keeps_alike_words_apart(configured, monkeypatch):
    """Screen 3 A: `Must not be null.` on a category and on a date are two lines."""
    rows = [_raw(n) for n in range(2, 6)]
    _use_sheet(monkeypatch, rows)
    _seeded()
    keys = {
        "transactions.0.category_id": "category_id",
        "transactions.1.date": "date",
        "transactions.2.category_id": "category_id",
    }
    null = error_response(
        422,
        "VALIDATION_ERROR",
        "Batch validation failed.",
        dict.fromkeys(keys, "Must not be null."),
        dict.fromkeys(keys, "NOT_NULL"),
    )
    respx.post(f"{BASE}/v1/transactions/batch").mock(side_effect=[null, _ok()])

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx", "--apply"])

    assert result.output.endswith(
        "Failures (3 rows):\n"
        "  category_id: Must not be null. rows 2, 4\n"
        "  date: Must not be null. row 3\n"
    )


@respx.mock
def test_rows_held_back_read_one_line_per_missing_resource(configured, monkeypatch):
    """Rows 2 and 5 need a category that was not created: one line, both rows.
    Row 4 shares a split transaction with row 3, held back for its category,
    and reads the app's line for a part not sent; the engine refused nothing."""
    rows = [
        _raw(2, CATEGORY="NEW"),
        _raw(3, "SIG-1", CATEGORY="NEW"),
        _raw(4, "SIG-1"),
        _raw(5, CATEGORY="NEW"),
        _raw(6),
    ]
    _use_sheet(monkeypatch, rows)
    _seeded()
    respx.post(f"{BASE}/v1/categories").mock(
        return_value=error_response(422, "VALIDATION_ERROR", "Invalid input.", {"name": "Bad."})
    )
    route = respx.post(f"{BASE}/v1/transactions/batch").mock(side_effect=[_ok()])

    result = runner.invoke(cli_app, ["import", "sheet", "whatever.xlsx", "--apply"])

    assert route.call_count == 1  # row 6 alone
    assert result.output.endswith(
        "Failures (4 rows):\n"
        "  Not sent: category 'NEW' was not created. rows 2, 3, 5\n"
        f"  {SPLIT_PART_NOT_SENT} row 4\n"
    )
    assert SPLIT_PART_REFUSED not in result.output
