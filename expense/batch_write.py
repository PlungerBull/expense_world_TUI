"""Post transactions through the atomic batch endpoint, and land every good row.

`POST /transactions/batch` is all-or-nothing: one bad row in a chunk and none
of the chunk is written. The singleton retry — shared by `expense import`
and the TUI's LOG bar rather than kept in two copies — re-posts the refused
chunk one row per batch, so the good rows land and the bad one is named on
its own.

**Why it is needed although the engine names the failing row** (a 422 from
that endpoint carries flat `fields` keys `transactions.<index>.<field>`, for
every item field `hashtag_ids` included, the same grammar a schema-level
rejection uses). Better diagnostics cannot replace
this pass, because its job is not diagnosis — it is **partial progress out of
an atomic endpoint**. A 409
("a transaction with id X already exists", which is what a re-run after a
half-written save looks like) refuses the whole chunk and carries no per-row
key at all; and even a fully-named 422 leaves the good rows unwritten. That is
the engine behaving as specified — batch is all or nothing by design — so the
client is the right place to decide that a partly-valid import should still
make progress.

**The result is index-aligned with the items handed in**, and carries no
vocabulary of its own. That is the whole point of the split: the importer maps
an index to a sheet line, the LOG bar maps it to a staged row, and neither
phrasing leaks into the other.

**A 409 is not a failure.** Ids are client-minted, so a replayed row means the
row is already in the ledger — which is what makes a retry after a half-written
save safe: nothing can be written twice.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from expense.errors import EngineConnectionError, EngineError, format_error
from expense.http import ExpenseClient

#: The most transactions the engine takes in one request; a longer list is
#: refused whole with a 422 on `transactions` (contract: POST /v1/transactions/batch).
ENGINE_BATCH_MAX = 500

#: Rows per atomic batch. Kept under `ENGINE_BATCH_MAX` to bound how much a
#: singleton retry has to re-post when one row in a chunk is bad.
CHUNK_SIZE = 200

BATCH_PATH = "/transactions/batch"


class RowResult(StrEnum):
    """What became of one item, index-aligned with the request list."""

    CREATED = "created"  # the engine accepted it
    EXISTED = "existed"  # 409 — the id was already there, so the row IS in
    FAILED = "failed"  # 422/4xx that names this row
    UNSENT = "unsent"  # a connection error stopped the run before it went


@dataclass(frozen=True)
class BatchFailure:
    """One refusal, and every item it covers.

    Grouping is not cosmetic. A chunk-level 401/403/5xx refuses the whole chunk
    for one reason, and saying it once per row would be five copies of the same
    sentence; a singleton retry, by contrast, names exactly one row. Callers
    that want it flat read `BatchOutcome.errors`.
    """

    indices: tuple[int, ...]
    message: str
    chunk_index: int


@dataclass
class BatchOutcome:
    """Per-item results plus whatever the engine refused, and why."""

    results: list[RowResult]
    failures: list[BatchFailure] = field(default_factory=list)
    #: True when a connection error halted the run — everything still `UNSENT`
    #: was never sent, so it is safe to retry.
    stopped: bool = False
    stop_error: str | None = None
    stop_chunk_index: int | None = None

    @property
    def errors(self) -> dict[int, str]:
        """item index -> message, for callers that report row by row."""
        return {i: f.message for f in self.failures for i in f.indices}

    def count(self, result: RowResult) -> int:
        return sum(1 for r in self.results if r is result)

    @property
    def written(self) -> list[int]:
        """Indices the engine holds — created now or created earlier."""
        return [
            i for i, r in enumerate(self.results) if r in (RowResult.CREATED, RowResult.EXISTED)
        ]

    @property
    def unsent(self) -> list[int]:
        return [i for i, r in enumerate(self.results) if r is RowResult.UNSENT]


def require_sendable_chunk_size(chunk_size: int) -> None:
    """Raise `ValueError` for a `chunk_size` that cannot be sent.

    Below 1 there is no chunk to send; above `ENGINE_BATCH_MAX` the engine
    refuses every chunk. A programming error, not something a user reaches. A
    caller that writes anything before its batch calls this first, so nothing
    lands ahead of it.
    """
    if chunk_size < 1:
        raise ValueError(f"chunk_size {chunk_size} is below 1 transaction per batch")
    if chunk_size > ENGINE_BATCH_MAX:
        raise ValueError(
            f"chunk_size {chunk_size} is above the engine's limit of {ENGINE_BATCH_MAX} "
            "transactions per batch"
        )


def post_transaction_batch(
    client: ExpenseClient, items: list[dict], *, chunk_size: int = CHUNK_SIZE
) -> BatchOutcome:
    """POST `items` in atomic chunks, falling back to one row per batch on 409/422.

    Never raises for an engine-side outcome: every item comes back with a
    `RowResult`, so the caller renders a summary instead of a traceback. A
    connection error stops the run (`stopped=True`) with the remaining items
    marked `UNSENT` — they were never sent, so they are safe to retry.

    A `chunk_size` below 1 or above `ENGINE_BATCH_MAX` is a programming error
    and raises `ValueError` before anything is sent.
    """
    require_sendable_chunk_size(chunk_size)
    outcome = BatchOutcome(results=[RowResult.UNSENT] * len(items))
    if not items:
        return outcome

    for chunk_index, offset in enumerate(range(0, len(items), chunk_size)):
        chunk = items[offset : offset + chunk_size]
        span = tuple(range(offset, offset + len(chunk)))
        try:
            client.post(BATCH_PATH, json_body={"transactions": chunk})
        except EngineError as err:
            if err.status in (409, 422):
                if not _post_singletons(client, chunk, offset, chunk_index, outcome):
                    return outcome  # a connection error inside the fallback
                continue
            # 401/403/5xx would fail identically per row — don't hammer.
            for index in span:
                outcome.results[index] = RowResult.FAILED
            outcome.failures.append(BatchFailure(span, format_error(err), chunk_index))
            continue
        except EngineConnectionError as err:
            outcome.stopped = True
            outcome.stop_error = format_error(err)
            outcome.stop_chunk_index = chunk_index
            return outcome  # this chunk and every later one stay UNSENT
        for index in span:
            outcome.results[index] = RowResult.CREATED
    return outcome


def _post_singletons(
    client: ExpenseClient,
    chunk: list[dict],
    offset: int,
    chunk_index: int,
    outcome: BatchOutcome,
) -> bool:
    """Re-post a 409'd/422'd chunk one row per batch so the bad row names itself.

    Returns False when a connection error stopped the run; the chunk's unsent
    tail and every later chunk keep their `UNSENT` default.
    """
    for pos, item in enumerate(chunk):
        index = offset + pos
        try:
            client.post(BATCH_PATH, json_body={"transactions": [item]})
        except EngineError as err:
            if err.status == 409:
                outcome.results[index] = RowResult.EXISTED
            else:
                outcome.results[index] = RowResult.FAILED
                outcome.failures.append(BatchFailure((index,), format_error(err), chunk_index))
        except EngineConnectionError as err:
            outcome.stopped = True
            outcome.stop_error = format_error(err)
            outcome.stop_chunk_index = chunk_index
            return False
        else:
            outcome.results[index] = RowResult.CREATED
    return True
