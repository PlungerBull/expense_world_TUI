"""Refused rows read one line per kind of error: each refused field's name and the
engine's words for it, then the rows they hit (screens 1 A, 2 A and 3 A,
docs/mockups/expense-world-grouped-refusals.html).

The batch writer says what kind each failure is (`BatchFailure.kind`),
`formatting.grouped_refusals` turns kinds into lines, and the LOG bar and the
ledger's bulk edit print those lines; the sheet import prints the engine's
refused rows through them too. This file pins the shared pieces;
`test_tui_log_bar.py` pins the LOG bar's lines and `test_cmd_import.py` the
sheet import's.
"""

from expense.batch_write import SPLIT_PART_KIND, post_transaction_batch
from expense.errors import EngineError, row_words
from expense.formatting import grouped_refusals, rows_phrase
from tests.unit.test_batch_write import _Client, _invalid, _items, _refusal

_ZERO = "Must not be zero."
_SEALED = "The date falls inside a completed reconciliation's period."


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
