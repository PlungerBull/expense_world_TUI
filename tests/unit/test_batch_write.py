"""The shared batch poster — one atomic chunk, then row by row when it is refused.

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
from expense.errors import EngineConnectionError, EngineError


class _Client:
    """Answers POSTs from a script, and records what it was asked."""

    def __init__(self, answers=()):
        self.answers = list(answers)
        self.calls: list[tuple[str, dict]] = []

    def post(self, path, json_body=None):
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


def _conflict() -> EngineError:
    return EngineError("CONFLICT", "id exists", None, 409, {})


def _invalid(
    index: int = 0, field: str = "amount_cents", reason: str = "ZERO_AMOUNT"
) -> EngineError:
    """The engine's batch 422: every refused item field keyed
    `transactions.<index>.<field>`, with its reason under the same key
    (contract: POST /v1/transactions/batch) (contract: "Error reasons")."""
    key = f"transactions.{index}.{field}"
    message = {"amount_cents": "Must not be zero.", "hashtag_ids": "Some hashtag IDs are invalid."}
    return EngineError(
        "VALIDATION_ERROR",
        "Invalid input.",
        {key: message.get(field, "Invalid.")},
        422,
        {},
        reasons={key: reason},
    )


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
    assert outcome.errors == {} and not outcome.stopped
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


def test_a_422_falls_back_to_one_row_per_batch_and_names_the_bad_one():
    """The engine refuses the chunk as a whole, so the fallback asks one row at
    a time — the good rows still land and the bad one reports its own error."""
    client = _Client([_invalid(index=1), {}, _invalid(), {}])
    outcome = post_transaction_batch(client, _items(3))

    assert client.sizes == [3, 1, 1, 1]  # the chunk, then each row
    assert outcome.results == [RowResult.CREATED, RowResult.FAILED, RowResult.CREATED]
    assert "Must not be zero" in outcome.errors[1]
    assert 0 not in outcome.errors and 2 not in outcome.errors


def test_an_unknown_hashtag_names_its_own_row():
    """An unknown hashtag is keyed on its item, `transactions.<index>.hashtag_ids`,
    and reported with the other item failures in the same 422. The chunk is
    refused as a whole; the singleton retry lands the good rows and pins the
    refusal to the item whose hashtag the engine does not know."""
    chunk_refusal = EngineError(
        "VALIDATION_ERROR",
        "Invalid input.",
        {
            "transactions.1.hashtag_ids": "Some hashtag IDs are invalid.",
            "transactions.2.amount_cents": "Must not be zero.",
        },
        422,
        {},
        reasons={
            "transactions.1.hashtag_ids": "INVALID_REFERENCE",
            "transactions.2.amount_cents": "ZERO_AMOUNT",
        },
    )
    client = _Client(
        [chunk_refusal, {}, _invalid(field="hashtag_ids", reason="INVALID_REFERENCE"), _invalid()]
    )
    outcome = post_transaction_batch(client, _items(3))

    assert client.sizes == [3, 1, 1, 1]
    assert outcome.results == [RowResult.CREATED, RowResult.FAILED, RowResult.FAILED]
    assert "transactions.0.hashtag_ids: Some hashtag IDs are invalid." in outcome.errors[1]
    assert "Must not be zero" in outcome.errors[2]
    assert "hashtag" not in outcome.errors[2]


def test_a_409_row_counts_as_written_not_failed():
    """A client-minted id that already exists means the row IS in the ledger.
    That is what makes a retry after a half-written save safe."""
    client = _Client([_conflict(), _conflict(), {}])
    outcome = post_transaction_batch(client, _items(2))

    assert outcome.results == [RowResult.EXISTED, RowResult.CREATED]
    assert outcome.errors == {}
    assert outcome.written == [0, 1]


def test_a_chunk_level_refusal_is_not_retried_row_by_row():
    """401/403/5xx would fail identically for every row — one honest message
    beats hammering the engine once per row."""
    client = _Client([EngineError("FORBIDDEN", "nope", None, 403, {})])
    outcome = post_transaction_batch(client, _items(3))

    assert client.sizes == [3]  # no fallback
    assert outcome.results == [RowResult.FAILED] * 3
    assert len(outcome.failures) == 1  # grouped, not one per row
    assert outcome.failures[0].indices == (0, 1, 2)
    assert outcome.errors == {i: "FORBIDDEN — nope" for i in range(3)}


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
    """It is a 422, but about the account and not about any row: no row-by-row
    fallback, no later chunk, and one failure for the chunk it met."""
    refusal = _settings_missing()
    client = _Client([refusal])
    outcome = post_transaction_batch(client, _items(5), chunk_size=3)

    assert client.sizes == [3]  # exactly one POST
    assert outcome.results == [RowResult.FAILED] * 3 + [RowResult.UNSENT] * 2
    assert len(outcome.failures) == 1
    assert outcome.failures[0].indices == (0, 1, 2)
    assert outcome.failures[0].message.count("Hint:") == 1
    assert outcome.stopped and outcome.stop_chunk_index == 0
    assert outcome.refusal is refusal
    assert outcome.stop_error is None  # that one is the connection's
    assert outcome.unsent == [3, 4]


def test_settings_missing_inside_the_fallback_also_stops():
    client = _Client([_invalid(), {}, _settings_missing()])
    outcome = post_transaction_batch(client, _items(3))

    assert client.sizes == [3, 1, 1]  # the third row never went
    assert outcome.results == [RowResult.CREATED, RowResult.FAILED, RowResult.UNSENT]
    assert [f.indices for f in outcome.failures] == [(1,)]
    assert outcome.stopped and outcome.refusal is not None


def test_stopped_is_read_off_what_stopped_the_run():
    """There is no stop without its cause: a run is stopped exactly when it
    carries the connection error or the account-wide refusal that halted it."""
    assert not BatchOutcome(results=[]).stopped
    assert BatchOutcome(results=[], stop_error="down").stopped
    assert BatchOutcome(results=[], refusal=_settings_missing()).stopped


def test_another_refusal_leaves_no_stop_behind():
    outcome = post_transaction_batch(_Client([_invalid(), _invalid()]), _items(1))
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


def test_a_connection_error_inside_the_fallback_also_stops():
    client = _Client(
        [_invalid(), {}, EngineConnectionError(url="http://x", original=OSError("down"))]
    )
    outcome = post_transaction_batch(client, _items(3))

    assert outcome.results == [RowResult.CREATED, RowResult.UNSENT, RowResult.UNSENT]
    assert outcome.stopped


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
