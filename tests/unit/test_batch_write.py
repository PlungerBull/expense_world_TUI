"""The shared batch poster — one atomic chunk, then its unnamed rows again when it is refused.

The TUI's LOG bar and the `.xlsx` importer share this one copy (docs/decisions.md
"What a half-written batch means"). These tests are its own spec;
`tests/unit/test_cmd_import.py` covers what the importer does with it.
"""

import pytest

from expense.batch_write import (
    BATCH_PATH,
    CHUNK_SIZE,
    ENGINE_BATCH_MAX,
    BatchOutcome,
    RowResult,
    post_transaction_batch,
)
from expense.errors import EngineConnectionError, EngineError, engine_words, format_error
from tests.unit.helpers import refuse_read_only_fields


class _Client:
    """Answers POSTs from a script, and records what it was asked."""

    def __init__(self, answers=()):
        self.answers = list(answers)
        self.calls: list[tuple[str, dict]] = []

    def post(self, path, json_body=None):
        refuse_read_only_fields("POST", path, json_body)
        self.calls.append((path, json_body))
        if self.answers:
            answer = self.answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        return {}

    @property
    def sizes(self) -> list[int]:
        return [len(body["transactions"]) for _, body in self.calls]


def _items(n: int) -> list[dict]:
    return [{"id": f"id{i}", "title": f"row {i}"} for i in range(n)]


def _refusal(code: str, status: int, message: str, entries: dict[str, tuple[str, str]]):
    """A batch refusal naming `entries`: key -> (field words, reason)."""
    return EngineError(
        code,
        message,
        {key: words for key, (words, _) in entries.items()},
        status,
        {},
        reasons={key: reason for key, (_, reason) in entries.items()},
    )


def _taken(*indices: int) -> EngineError:
    """Step 2 of a batch: `409` `ID_EXISTS` on every item whose id is taken
    (contract: POST /v1/transactions/batch)."""
    message = (
        "A transaction with id 'x' already exists."
        if len(indices) == 1
        else f"{len(indices)} of these ids are already taken."
    )
    return _refusal(
        "CONFLICT",
        409,
        message,
        {
            f"transactions.{i}.id": ("A transaction with this id already exists.", "ID_EXISTS")
            for i in indices
        },
    )


def _conflict(
    index: int | None = 0, field: str = "id", reason: str = "ID_EXISTS", message: str = "id exists"
) -> EngineError:
    """A batch 409 naming one key: `transactions.<i>.<field>` for an item, or
    `field` alone for a refusal of no item (pass `index=None`), such as the
    system-category refusals keyed `category_id` (contract: "Error reasons")."""
    key = field if index is None else f"transactions.{index}.{field}"
    return _refusal("CONFLICT", 409, message, {key: ("stand-in field words", reason)})


_WORDS = {
    "amount_cents": "Must not be zero.",
    "hashtag_ids": "Some hashtag IDs are invalid.",
    "category_id": "Must reference an active category.",
}


def _invalid(*indices: int, field: str = "amount_cents", reason: str = "ZERO_AMOUNT"):
    """A batch 422 naming each of `indices` on `field`, keyed
    `transactions.<index>.<field>`, its reason under the same key
    (contract: POST /v1/transactions/batch) (contract: "Error reasons")."""
    return _refusal(
        "VALIDATION_ERROR",
        422,
        "Batch validation failed.",
        {
            f"transactions.{i}.{field}": (_WORDS.get(field, "Invalid."), reason)
            for i in indices or (0,)
        },
    )


def _ids(client: _Client) -> list[list[str]]:
    return [[item["id"] for item in body["transactions"]] for _, body in client.calls]


def test_an_empty_list_makes_no_call_at_all():
    client = _Client()
    outcome = post_transaction_batch(client, [])
    assert client.calls == []
    assert outcome.results == [] and not outcome.stopped


def test_a_clean_batch_reports_every_row_created():
    client = _Client()
    outcome = post_transaction_batch(client, _items(3))
    assert client.sizes == [3]  # one call, not three
    assert outcome.results == [RowResult.CREATED] * 3
    assert outcome.failures == [] and not outcome.stopped
    assert outcome.written == [0, 1, 2]


def test_chunking_splits_at_the_size_asked_for():
    client = _Client()
    post_transaction_batch(client, _items(450), chunk_size=200)
    assert client.sizes == [200, 200, 50]


def test_the_chunk_size_stays_at_or_under_the_engines_limit():
    """The engine refuses a longer list whole (contract: POST /v1/transactions/batch)."""
    assert ENGINE_BATCH_MAX == 500
    assert 1 <= CHUNK_SIZE <= ENGINE_BATCH_MAX


def test_the_default_chunk_is_the_module_constant():
    client = _Client()
    post_transaction_batch(client, _items(CHUNK_SIZE + 1))
    assert client.sizes == [CHUNK_SIZE, 1]


def test_a_chunk_at_the_engines_limit_goes_out_whole():
    client = _Client()
    post_transaction_batch(client, _items(ENGINE_BATCH_MAX + 1), chunk_size=ENGINE_BATCH_MAX)
    assert client.sizes == [ENGINE_BATCH_MAX, 1]


@pytest.mark.parametrize("chunk_size", [0, -1, -200])
@pytest.mark.parametrize("n_items", [0, 3])
def test_a_chunk_size_below_one_is_refused_before_anything_is_sent(chunk_size, n_items):
    client = _Client()
    with pytest.raises(ValueError, match="below 1 transaction per batch"):
        post_transaction_batch(client, _items(n_items), chunk_size=chunk_size)
    assert client.calls == []


@pytest.mark.parametrize("n_items", [0, 3, ENGINE_BATCH_MAX + 1])
def test_a_chunk_size_above_the_engines_limit_is_refused_before_anything_is_sent(n_items):
    client = _Client()
    with pytest.raises(ValueError, match="above the engine's limit of 500"):
        post_transaction_batch(client, _items(n_items), chunk_size=ENGINE_BATCH_MAX + 1)
    assert client.calls == []


def test_a_refused_row_fails_and_the_rest_go_again_as_one_batch():
    """The engine refuses the chunk naming its bad row; that row fails in the
    engine's words for it, and the others go again as one batch, and land."""
    client = _Client([_invalid(1), {}])
    outcome = post_transaction_batch(client, _items(3))

    assert _ids(client) == [["id0", "id1", "id2"], ["id0", "id2"]]
    assert outcome.results == [RowResult.CREATED, RowResult.FAILED, RowResult.CREATED]
    (failure,) = outcome.failures
    assert (failure.indices, failure.message) == (
        (1,),
        "VALIDATION_ERROR — Batch validation failed.\n  amount_cents: Must not be zero.",
    )


def test_a_chunk_naming_several_taken_ids_counts_each_already_there():
    """Step 2 names every item whose id is taken; each is in the ledger, and the
    rows it does not name go again and land."""
    client = _Client([_taken(0, 2, 3), {}])
    outcome = post_transaction_batch(client, _items(5))

    assert _ids(client) == [["id0", "id1", "id2", "id3", "id4"], ["id1", "id4"]]
    assert outcome.results == [
        RowResult.EXISTED,
        RowResult.CREATED,
        RowResult.EXISTED,
        RowResult.EXISTED,
        RowResult.CREATED,
    ]
    assert outcome.failures == [] and outcome.written == [0, 1, 2, 3, 4]


def test_a_request_refusal_then_a_ledger_refusal_then_the_rest_lands():
    """The four steps answer one at a time: a send refused for what the request
    shows (step 1) drops its rows, the next is refused by the ledger (step 3)
    and drops its own, and the third lands. Each failure carries its own words."""
    ledger = _invalid(0, field="category_id", reason="INVALID_REFERENCE")
    client = _Client([_invalid(1, 3), ledger, {}])
    outcome = post_transaction_batch(client, _items(5))

    assert _ids(client) == [
        ["id0", "id1", "id2", "id3", "id4"],
        ["id0", "id2", "id4"],
        ["id2", "id4"],
    ]
    assert outcome.results == [
        RowResult.FAILED,
        RowResult.FAILED,
        RowResult.CREATED,
        RowResult.FAILED,
        RowResult.CREATED,
    ]
    assert [f.indices for f in outcome.failures] == [(1,), (3,), (0,)]
    one, three, zero = (f.message for f in outcome.failures)
    assert "category_id: Must reference an active category." in zero
    assert "amount_cents" not in zero
    assert one == three  # refused alike, said alike
    assert "amount_cents: Must not be zero." in one
    assert not any(f.whole_chunk for f in outcome.failures)


def test_a_row_refused_carries_its_own_refusal_keyed_by_field():
    """What a caller groups refusals on: the refusal as it reads for the row,
    its keys stripped of the place the row had in the send."""
    client = _Client([_invalid(2, field="hashtag_ids", reason="INVALID_REFERENCE"), {}])
    outcome = post_transaction_batch(client, _items(3))

    (failure,) = outcome.failures
    assert failure.indices == (2,) and failure.chunk_index == 0
    assert failure.error is not None
    assert failure.error.fields == {"hashtag_ids": "Some hashtag IDs are invalid."}
    assert failure.error.reasons == {"hashtag_ids": "INVALID_REFERENCE"}
    assert (failure.error.code, failure.error.status) == ("VALIDATION_ERROR", 422)


def test_a_rows_refusal_carries_a_body_holding_only_its_own_entries():
    """The row's body agrees with its `fields` and `reasons`: no other row's
    entries, and no place in the send."""
    client = _Client([_invalid(0, 2), {}])
    outcome = post_transaction_batch(client, _items(3))

    first, second = (f.error for f in outcome.failures)
    for row_err in (first, second):
        assert row_err.raw_body == {
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Batch validation failed.",
                "fields": {"amount_cents": "Must not be zero."},
                "reasons": {"amount_cents": "ZERO_AMOUNT"},
            }
        }


def test_taken_ids_beside_new_rows_then_a_refusal_on_the_next_send():
    """A replay and a refusal in one chunk: the taken ids settle on the first
    send, a zero amount on the second, and the rest lands on the third."""
    client = _Client([_taken(0), _invalid(1), {}])
    outcome = post_transaction_batch(client, _items(4))

    assert _ids(client) == [["id0", "id1", "id2", "id3"], ["id1", "id2", "id3"], ["id1", "id3"]]
    assert outcome.results == [
        RowResult.EXISTED,
        RowResult.CREATED,
        RowResult.FAILED,
        RowResult.CREATED,
    ]


def test_a_re_run_costs_one_request_per_chunk():
    """Every row already landed: each chunk's one send names all of them, and
    nothing goes again."""
    client = _Client([_taken(*range(3)), _taken(*range(3)), _taken(0, 1)])
    outcome = post_transaction_batch(client, _items(8), chunk_size=3)

    assert client.sizes == [3, 3, 2]  # one request per chunk
    assert outcome.results == [RowResult.EXISTED] * 8


def test_a_chunk_mixing_landed_and_new_rows_costs_one_more_request():
    client = _Client([_taken(*range(3)), _taken(0), {}, _taken(0, 1)])
    outcome = post_transaction_batch(client, _items(8), chunk_size=3)

    assert client.sizes == [3, 3, 2, 2]  # the second chunk sends its new rows again
    assert outcome.count(RowResult.EXISTED) == 6
    assert outcome.count(RowResult.CREATED) == 2


def _grouped(n: int, groups: dict[str, list[int]]) -> list[dict]:
    """`n` items, those listed under a name carrying it as their `line_group`."""
    items = _items(n)
    for name, members in groups.items():
        for i in members:
            items[i]["line_group"] = name
    return items


def test_a_refusal_on_a_groups_first_item_fails_the_whole_group():
    """A line's ledger refusal is keyed by its first item; every part of that
    line fails with it, so no line lands with a part missing
    (contract: POST /v1/transactions/batch, "Line groups")."""
    client = _Client([_conflict(1, field="operation_code", reason="OPERATION_CODE_EXISTS"), {}])
    outcome = post_transaction_batch(client, _grouped(5, {"g1": [1, 2, 4]}))

    # the group's parts go together, in the place of its first item
    assert _ids(client) == [["id0", "id1", "id2", "id4", "id3"], ["id0", "id3"]]
    assert outcome.results == [
        RowResult.CREATED,
        RowResult.FAILED,
        RowResult.FAILED,
        RowResult.CREATED,
        RowResult.FAILED,
    ]
    assert sorted(f.indices for f in outcome.failures) == [(1,), (2,), (4,)]
    messages = {f.message for f in outcome.failures}
    assert len(messages) == 1  # every part fails in the words of the one refused
    assert "operation_code: stand-in field words" in messages.pop()


def test_a_chunk_never_cuts_a_group():
    """A group that does not fit in the chunk's room starts the next chunk
    (contract: POST /v1/transactions/batch, "Line groups")."""
    client = _Client()
    outcome = post_transaction_batch(client, _grouped(5, {"g": [2, 3]}), chunk_size=3)

    assert _ids(client) == [["id0", "id1"], ["id2", "id3", "id4"]]
    assert outcome.results == [RowResult.CREATED] * 5


def test_a_group_goes_in_the_chunk_of_its_first_item():
    client = _Client()
    post_transaction_batch(client, _grouped(5, {"g": [1, 4]}), chunk_size=3)

    assert _ids(client) == [["id0", "id1", "id4"], ["id2", "id3"]]


def test_a_group_longer_than_the_chunk_size_is_a_chunk_of_its_own():
    client = _Client()
    post_transaction_batch(client, _grouped(6, {"g": [1, 2, 3, 4]}), chunk_size=2)

    assert _ids(client) == [["id0"], ["id1", "id2", "id3", "id4"], ["id5"]]


def test_a_group_longer_than_the_engine_takes_is_refused_by_the_engine_whole():
    """Never cut: it goes as one send, and the engine's refusal of the list
    fails every part in its own words (contract: POST /v1/transactions/batch)."""
    n = ENGINE_BATCH_MAX + 1
    too_many = _refusal(
        "VALIDATION_ERROR",
        422,
        "Invalid input.",
        {"transactions": ("List should have at most 500 items.", "OUT_OF_RANGE")},
    )
    client = _Client([too_many])
    outcome = post_transaction_batch(client, _grouped(n, {"g": list(range(n))}))

    assert client.sizes == [n]
    assert outcome.results == [RowResult.FAILED] * n
    (failure,) = outcome.failures
    assert failure.whole_chunk and len(failure.indices) == n


def test_a_refused_part_fails_its_group_and_no_other_line():
    """A part refused for itself takes its group with it; another group, and a
    line of its own, go again."""
    client = _Client([_invalid(3), {}])
    outcome = post_transaction_batch(client, _grouped(5, {"a": [0, 1], "b": [2, 3]}))

    assert _ids(client)[1] == ["id0", "id1", "id4"]
    assert outcome.results == [
        RowResult.CREATED,
        RowResult.CREATED,
        RowResult.FAILED,
        RowResult.FAILED,
        RowResult.CREATED,
    ]


@pytest.mark.parametrize(
    "refusal",
    [
        _conflict(index=None, field="category_id", reason="CONCURRENT_CHANGE"),
        _conflict(index=None, field="X-Idempotency-Key", reason="IDEMPOTENCY_KEY_REUSED"),
        _refusal(
            "VALIDATION_ERROR",
            422,
            "Invalid input.",
            {"transactions": ("List should have at most 500 items.", "OUT_OF_RANGE")},
        ),
        # an item key beside a key of no item: the refusal is about the whole send
        _refusal(
            "VALIDATION_ERROR",
            422,
            "Invalid input.",
            {
                "transactions.0.amount_cents": ("Must not be zero.", "ZERO_AMOUNT"),
                "category_id": ("Invalid.", "INVALID_REFERENCE"),
            },
        ),
        # a place past the end of what was sent
        _invalid(7),
        # no key at all
        EngineError("CONFLICT", "id exists", None, 409, {}),
    ],
    ids=["no-item-409", "key-reused", "list-itself", "mixed", "out-of-range", "no-key"],
)
def test_a_refusal_naming_no_item_fails_the_whole_chunk_once(refusal):
    """Nothing in it says which row is wrong, so every row fails alike: one
    failure for the chunk, nothing sent again, and later chunks still go."""
    client = _Client([refusal, {}])
    outcome = post_transaction_batch(client, _items(5), chunk_size=3)

    assert client.sizes == [3, 2]
    assert outcome.results == [RowResult.FAILED] * 3 + [RowResult.CREATED] * 2
    (failure,) = outcome.failures
    assert failure.indices == (0, 1, 2) and failure.whole_chunk
    assert failure.message == engine_words(refusal) and failure.error is refusal
    assert not outcome.stopped


def test_a_refusal_naming_no_item_after_a_drop_fails_only_what_is_left():
    client = _Client([_invalid(1), EngineError("FORBIDDEN", "nope", None, 403, {})])
    outcome = post_transaction_batch(client, _items(3))

    assert client.sizes == [3, 2]
    assert outcome.results == [RowResult.FAILED] * 3
    assert [(f.indices, f.whole_chunk) for f in outcome.failures] == [
        ((1,), False),
        ((0, 2), True),
    ]


@pytest.mark.parametrize(
    "refusal",
    [
        _conflict(field="operation_code", reason="OPERATION_CODE_EXISTS"),
        # a ledger rule refusing the row, under the 422 code
        _invalid(0, field="date", reason="SEALED_PERIOD"),
        # the row's own id, but not taken
        _conflict(field="id", reason="IDEMPOTENCY_KEY_REUSED"),
        # its own id taken, and something else wrong with the row
        _refusal(
            "CONFLICT",
            409,
            "id exists",
            {
                "transactions.0.id": ("taken", "ID_EXISTS"),
                "transactions.0.operation_code": ("taken", "OPERATION_CODE_EXISTS"),
            },
        ),
        # a taken id under the 422 code
        _refusal(
            "VALIDATION_ERROR", 422, "Invalid input.", {"transactions.0.id": ("x", "ID_EXISTS")}
        ),
    ],
    ids=["operation-code", "sealed-period", "key-reused", "id-and-more", "not-a-conflict"],
)
def test_any_other_refusal_of_a_row_is_never_written(refusal):
    """Only `ID_EXISTS` on the row's own id, alone, counts as written; every
    other refusal of the row fails it, in the engine's words alone by default."""
    client = _Client([refusal, {}])
    outcome = post_transaction_batch(client, _items(2))

    assert outcome.results == [RowResult.FAILED, RowResult.CREATED]
    assert outcome.written == [1]
    (failure,) = outcome.failures
    assert failure.indices == (0,)
    assert failure.message.startswith(f"{refusal.code} — {refusal.message}")


def test_the_caller_chooses_the_words_of_a_refusal():
    """The LOG bar passes `format_error`, which adds the app's line under the
    engine's words; the default, the importer's, is the engine's words alone."""
    refusal = _conflict(index=None, field="category_id", reason="RESERVED_NAME_HELD")
    outcome = post_transaction_batch(_Client([refusal]), _items(1), error_text=format_error)

    assert [(f.indices, f.message) for f in outcome.failures] == [((0,), format_error(refusal))]
    assert outcome.failures[0].message.endswith(
        "rename it on Manage ▸ Categories, then save again."
    )


@pytest.mark.parametrize("status", [401, 403, 500])
def test_a_chunk_level_refusal_is_not_sent_again(status):
    """401/403/5xx would fail identically for every row — one honest message
    beats sending the rows again."""
    client = _Client([EngineError("FORBIDDEN", "nope", None, status, {})])
    outcome = post_transaction_batch(client, _items(3))

    assert client.sizes == [3]  # not sent again
    assert outcome.results == [RowResult.FAILED] * 3
    assert len(outcome.failures) == 1  # grouped, not one per row
    assert outcome.failures[0].indices == (0, 1, 2)
    assert outcome.failures[0].message == "FORBIDDEN — nope"


def _settings_missing() -> EngineError:
    """The refusal every route that needs settings gives before first-time setup."""
    return EngineError(
        "SETTINGS_MISSING",
        "User settings have not been provisioned.",
        {"user_settings": "Must be provisioned via POST /v1/auth/bootstrap."},
        422,
        {},
        reasons={"user_settings": "NOT_PROVISIONED"},
    )


def test_settings_missing_fails_the_chunk_once_and_stops_the_run():
    """It is a 422, but about the account and not about any row: nothing sent
    again, no later chunk, and one failure for the chunk it met."""
    refusal = _settings_missing()
    client = _Client([refusal])
    outcome = post_transaction_batch(client, _items(5), chunk_size=3)

    assert client.sizes == [3]  # exactly one POST
    assert outcome.results == [RowResult.FAILED] * 3 + [RowResult.UNSENT] * 2
    assert len(outcome.failures) == 1
    assert outcome.failures[0].indices == (0, 1, 2)
    assert outcome.failures[0].message == engine_words(refusal)  # the default: no hint
    assert outcome.stopped and outcome.stop_chunk_index == 0
    assert outcome.refusal is refusal
    assert outcome.stop_error is None  # that one is the connection's
    assert outcome.unsent == [3, 4]


def test_settings_missing_on_a_second_send_also_stops():
    client = _Client([_invalid(1), _settings_missing()])
    outcome = post_transaction_batch(client, _items(4), chunk_size=3)

    assert client.sizes == [3, 2]  # the second chunk never went
    assert outcome.results == [RowResult.FAILED] * 3 + [RowResult.UNSENT]
    assert [(f.indices, f.whole_chunk) for f in outcome.failures] == [((1,), False), ((0, 2), True)]
    assert outcome.stopped and outcome.refusal is not None


def _codes_exhausted(*indices: int) -> EngineError:
    """Every line code given: `422 LIMIT_REACHED` on `transactions.<i>.id` of the
    first item that needed a new line (contract: POST /v1/transactions/batch, "Line groups")."""
    return _refusal(
        "LIMIT_REACHED",
        422,
        "No bank line codes are left.",
        {
            f"transactions.{i}.id": ("No line code is left for a new line.", "LINE_CODES_EXHAUSTED")
            for i in indices
        },
    )


def test_line_codes_exhausted_fails_its_row_once_and_stops_the_run():
    """It holds for the rest of the run: one request, the named row fails in the
    engine's words for it, every other row stays unsent, no later chunk goes."""
    refusal = _codes_exhausted(1)
    client = _Client([{}, refusal])
    outcome = post_transaction_batch(client, _items(7), chunk_size=3)

    assert client.sizes == [3, 3]  # the first chunk landed; nothing after the refusal
    assert outcome.results == [RowResult.CREATED] * 3 + [
        RowResult.UNSENT,
        RowResult.FAILED,
        RowResult.UNSENT,
        RowResult.UNSENT,
    ]
    (failure,) = outcome.failures
    assert (failure.indices, failure.whole_chunk, failure.chunk_index) == ((4,), False, 1)
    assert failure.message == (
        "LIMIT_REACHED — No bank line codes are left.\n  id: No line code is left for a new line."
    )
    assert outcome.stopped and outcome.refusal is refusal and outcome.stop_chunk_index == 1
    assert outcome.unsent == [3, 5, 6]


def test_line_codes_exhausted_on_a_groups_first_item_fails_the_group():
    client = _Client([_codes_exhausted(1)])
    outcome = post_transaction_batch(client, _grouped(4, {"g": [1, 2]}))

    assert client.sizes == [4]
    assert outcome.results == [
        RowResult.UNSENT,
        RowResult.FAILED,
        RowResult.FAILED,
        RowResult.UNSENT,
    ]
    assert outcome.refusal is not None


def test_line_codes_exhausted_after_a_drop_stops_too():
    client = _Client([_invalid(0), _codes_exhausted(0)])
    outcome = post_transaction_batch(client, _items(3))

    assert client.sizes == [3, 2]
    assert outcome.results == [RowResult.FAILED, RowResult.FAILED, RowResult.UNSENT]
    assert outcome.refusal is not None


def test_stopped_is_read_off_what_stopped_the_run():
    """There is no stop without its cause: a run is stopped exactly when it
    carries the connection error or the account-wide refusal that halted it."""
    assert not BatchOutcome(results=[]).stopped
    assert BatchOutcome(results=[], stop_error="down").stopped
    assert BatchOutcome(results=[], refusal=_settings_missing()).stopped


def test_another_refusal_leaves_no_stop_behind():
    outcome = post_transaction_batch(_Client([_invalid()]), _items(1))
    assert not outcome.stopped and outcome.refusal is None


def test_a_connection_error_stops_and_leaves_the_tail_unsent():
    """Unsent is not failed: those rows never reached the engine, so they are
    safe to retry exactly as they are."""
    client = _Client([{}, EngineConnectionError(url="http://x", original=OSError("down"))])
    outcome = post_transaction_batch(client, _items(3), chunk_size=1)

    assert client.sizes == [1, 1]  # the third chunk was never attempted
    assert outcome.results == [RowResult.CREATED, RowResult.UNSENT, RowResult.UNSENT]
    assert outcome.stopped and outcome.stop_chunk_index == 1
    assert outcome.unsent == [1, 2]


def test_a_connection_error_on_a_second_send_also_stops():
    """The rows sent again never landed, so they stay unsent; the row the first
    send named keeps its failure."""
    client = _Client([_invalid(1), EngineConnectionError(url="http://x", original=OSError("down"))])
    outcome = post_transaction_batch(client, _items(3))

    assert outcome.results == [RowResult.UNSENT, RowResult.FAILED, RowResult.UNSENT]
    assert outcome.stopped and outcome.unsent == [0, 2]


@pytest.mark.parametrize(
    "results,wanted,count",
    [
        ([RowResult.CREATED, RowResult.EXISTED], RowResult.CREATED, 1),
        ([RowResult.FAILED, RowResult.FAILED], RowResult.FAILED, 2),
    ],
)
def test_count_tallies_one_result(results, wanted, count):
    assert BatchOutcome(results=results).count(wanted) == count


def test_the_path_is_the_batch_endpoint_with_the_transactions_envelope():
    client = _Client()
    post_transaction_batch(client, _items(1))
    path, body = client.calls[0]
    assert path == BATCH_PATH == "/transactions/batch"
    assert list(body) == ["transactions"]
