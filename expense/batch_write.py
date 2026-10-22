"""Post transactions through the atomic batch endpoint, and land every good row.

`POST /transactions/batch` is all-or-nothing: one bad row in a chunk and none
of the chunk is written
(contract: POST /v1/transactions/batch, "No partial success"). This module,
shared by `expense import sheet` and the TUI's LOG bar rather than kept in two
copies, turns that into partial progress: a refused chunk's named rows are set
aside and the rest go again as one batch, until a batch lands or no row is left.

**The engine names every row it refuses.** A batch is judged in four steps and
answers with the first step that refuses it, naming every item that step
refuses, one `fields` entry per item and field, keyed `transactions.<i>.<field>`
by the item's place in the request (contract: POST /v1/transactions/batch)
(contract: POST /v1/transactions/batch, "Error shape"). So one refused send
settles every row it names, and the rows it does not name go again: a chunk
costs one request, plus one for each send that drops rows.

**A taken id is not a failure.** Ids are client-minted, so a row refused only
because its own id is taken (`ID_EXISTS` on `transactions.<i>.id`) is already in
the ledger, and a create sent again answers that before any other refusal
(contract: "Base Conventions", "Which refusal comes first on a create"). That is
what makes a retry after a half-written save safe, and a re-run converge: nothing
can be written twice. Every other refusal of a row (a zero amount, a taken
operation code, a sealed period) fails that row, in the engine's words for it.

**A line group goes whole or not at all.** Items sharing a `line_group` are the
parts of one bank line, and the engine names a line's ledger refusals on its
first item (contract: POST /v1/transactions/batch, "Line groups"). A refused part
fails every part of its group, so no line lands with a part missing.

**A refusal that names no row fails the whole chunk.** A `401`, `403` or `5xx`,
or a `409`/`422` with any key that is no item of the send (`transactions` itself,
`category_id`, `X-Idempotency-Key`, an index past the end of the send) or with no
key at all, would fail every row alike: the chunk's unsettled rows are one
failure, nothing is sent again, and later chunks still go. An account-wide refusal
(`errors.refuses_every_write`) fails its chunk the same way and stops the run.

**The result is index-aligned with the items handed in**, and carries no
vocabulary of its own: the importer maps an index to a sheet line, the LOG bar
maps it to a staged row, and neither phrasing leaks into the other. The
refusals' words are the caller's choice too (`error_text`): the engine's alone
by default, as the importer prints them; the LOG bar adds the app's line saying
what to do.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from expense.errors import (
    EngineConnectionError,
    EngineError,
    engine_text,
    is_own_id_replay,
    key_field,
    key_index,
    refuses_every_write,
)
from expense.http import ExpenseClient

#: The most transactions the engine takes in one request; a longer list is
#: refused whole with a 422 on `transactions` (contract: POST /v1/transactions/batch).
ENGINE_BATCH_MAX = 500

#: Rows per atomic batch. Kept under `ENGINE_BATCH_MAX` to bound how much one
#: refused chunk has to send again.
CHUNK_SIZE = 200

BATCH_PATH = "/transactions/batch"

#: The list a batch item's refusal is keyed under, `transactions.<i>.<field>`
#: (contract: POST /v1/transactions/batch, "Error shape").
ITEMS_KEY = "transactions"


class RowResult(StrEnum):
    """What became of one item, index-aligned with the request list."""

    CREATED = "created"  # the engine accepted it
    EXISTED = "existed"  # 409 ID_EXISTS on its own id alone: the row IS in
    FAILED = "failed"  # any other refusal of this row
    UNSENT = "unsent"  # the run stopped before it went


@dataclass(frozen=True)
class BatchFailure:
    """One refusal, and every item it covers.

    A refusal of one row covers that row alone, and `error` is the engine's
    refusal as it reads for that row: its own `fields` and `reasons`, keyed by
    the field without the `transactions.<i>.` place it had in the request. Two
    rows refused alike carry the same `message`. A refusal that names no row
    (`whole_chunk`) covers every row of its chunk still unsent, said once rather
    than once per row; its `error` is the refusal as the engine sent it. Callers
    that want it flat read `BatchOutcome.errors`.
    """

    indices: tuple[int, ...]
    message: str
    chunk_index: int
    error: EngineError
    whole_chunk: bool = False


@dataclass
class BatchOutcome:
    """Per-item results plus whatever the engine refused, and why."""

    results: list[RowResult]
    failures: list[BatchFailure] = field(default_factory=list)
    #: The connection error that halted the run before the end, as text.
    stop_error: str | None = None
    stop_chunk_index: int | None = None
    #: The refusal that stopped the run because every further write would draw
    #: it too (`errors.refuses_every_write`). Its chunk is one `BatchFailure`;
    #: a caller reports it once, not per row.
    refusal: EngineError | None = None

    @property
    def stopped(self) -> bool:
        """True when the run halted before the end — on a connection error
        (`stop_error`) or on an account-wide refusal (`refusal`). Everything
        still `UNSENT` was never sent, so it is safe to retry."""
        return self.stop_error is not None or self.refusal is not None

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


ErrorText = Callable[[Exception], str]


def post_transaction_batch(
    client: ExpenseClient,
    items: list[dict],
    *,
    chunk_size: int = CHUNK_SIZE,
    error_text: ErrorText = engine_text,
) -> BatchOutcome:
    """POST `items` in atomic chunks; a refused chunk sends its unnamed rows again.

    Never raises for an engine-side outcome: every item comes back with a
    `RowResult`, so the caller renders a summary instead of a traceback. A
    connection error stops the run (`stopped`) with the rows not yet settled
    marked `UNSENT` — no send of them landed, so they are safe to retry. So does
    an account-wide refusal (`errors.refuses_every_write`): the rows of its
    chunk still unsettled fail as one group, and no later chunk goes out.

    Each send is its own request with its own idempotency key, since a send
    that drops rows carries a different body.

    A `chunk_size` below 1 or above `ENGINE_BATCH_MAX` is a programming error
    and raises `ValueError` before anything is sent. `error_text` turns each
    refusal into the words a failure carries.
    """
    require_sendable_chunk_size(chunk_size)
    outcome = BatchOutcome(results=[RowResult.UNSENT] * len(items))
    for chunk_index, offset in enumerate(range(0, len(items), chunk_size)):
        span = list(range(offset, min(offset + chunk_size, len(items))))
        if not _post_chunk(client, items, span, chunk_index, outcome, error_text):
            return outcome  # every later chunk stays UNSENT
    return outcome


def _post_chunk(
    client: ExpenseClient,
    items: list[dict],
    pending: list[int],
    chunk_index: int,
    outcome: BatchOutcome,
    error_text: ErrorText,
) -> bool:
    """Send one chunk's `pending` rows until a send lands or none is left.

    Returns False when a connection error or an account-wide refusal stopped the
    run; the rows still pending keep their `UNSENT` default.
    """
    while pending:
        sent = [items[i] for i in pending]
        try:
            client.post(BATCH_PATH, json_body={ITEMS_KEY: sent})
        except EngineError as err:
            if refuses_every_write(err):
                _fail_whole(outcome, pending, err, chunk_index, error_text)
                outcome.stop_chunk_index = chunk_index
                outcome.refusal = err
                return False
            named = _named_rows(err, len(sent))
            if not named:
                _fail_whole(outcome, pending, err, chunk_index, error_text)
                return True
            settled = _settle(named, _line_groups(sent))
            for pos, row_err in sorted(settled.items()):
                index = pending[pos]
                if row_err is None:
                    outcome.results[index] = RowResult.EXISTED
                    continue
                outcome.results[index] = RowResult.FAILED
                outcome.failures.append(
                    BatchFailure((index,), error_text(row_err), chunk_index, row_err)
                )
            pending = [index for pos, index in enumerate(pending) if pos not in settled]
            continue
        except EngineConnectionError as err:
            outcome.stop_error = error_text(err)
            outcome.stop_chunk_index = chunk_index
            return False
        for index in pending:
            outcome.results[index] = RowResult.CREATED
        return True
    return True


def _fail_whole(
    outcome: BatchOutcome,
    pending: list[int],
    err: EngineError,
    chunk_index: int,
    error_text: ErrorText,
) -> None:
    """Fail every row of `pending` as one refusal that names no row."""
    for index in pending:
        outcome.results[index] = RowResult.FAILED
    outcome.failures.append(
        BatchFailure(tuple(pending), error_text(err), chunk_index, err, whole_chunk=True)
    )


def _named_rows(err: EngineError, size: int) -> dict[int, EngineError] | None:
    """Each row a `409`/`422` names, by its place in the send, with the engine's
    refusal as it reads for that row; None when the refusal names no row.

    A row's refusal keeps the engine's code, message and status, and its own
    `fields` and `reasons` keyed by the field alone: the `transactions.<i>.` place
    is the send's, not the row's, and a row sent again sits elsewhere. A refusal
    with any key that is not one of the send's items (`transactions` itself, a
    header, a key of no item, an index past the end of the send), or with no key
    at all, is about the whole send, and names no row.
    """
    if err.status not in (409, 422):
        return None
    named: dict[int, tuple[dict, dict]] = {}
    for slot, entries in enumerate((err.fields or {}, err.reasons or {})):
        for key, value in entries.items():
            pos = key_index(key, ITEMS_KEY)
            if pos is None or pos >= size:
                return None
            named.setdefault(pos, ({}, {}))[slot][_row_key(key)] = value
    if not named:
        return None
    return {pos: _row_refusal(err, fields, reasons) for pos, (fields, reasons) in named.items()}


def _row_key(key: str) -> str:
    """`transactions.<i>.<field>` as the row reads it: `<field>`. A key naming
    the item itself, with no field, stays whole."""
    return key_field(key, ITEMS_KEY) or key


def _row_refusal(err: EngineError, fields: dict, reasons: dict) -> EngineError:
    """`err` as it reads for one row: the engine's code, message and status, the
    row's own `fields` and `reasons`, and a body that holds exactly those."""
    row_fields = fields or None
    row_reasons = reasons or None
    body = {
        "error": {
            "code": err.code,
            "message": err.message,
            "fields": row_fields,
            "reasons": row_reasons,
        }
    }
    return EngineError(err.code, err.message, row_fields, err.status, body, reasons=row_reasons)


def _line_groups(sent: list[dict]) -> list[list[int]]:
    """The places in `sent` of each `line_group`'s items, its first item first,
    in request order (contract: POST /v1/transactions/batch, "Line groups").
    An item with no `line_group` is a line of its own and in no group here."""
    groups: dict[str, list[int]] = {}
    for pos, item in enumerate(sent):
        name = item.get("line_group")
        if isinstance(name, str) and name.strip():
            groups.setdefault(name.strip(), []).append(pos)
    return list(groups.values())


def _settle(
    named: dict[int, EngineError], groups: list[list[int]]
) -> dict[int, EngineError | None]:
    """What a refused send settles, by place: None for a row already in the
    ledger, its refusal for a row that fails.

    A row named only `ID_EXISTS` on its own id is in. Any other named row fails,
    and so does every part of its `line_group` the send did not name, with the
    refusal of the group's first named part: a line lands whole or not at all.
    """
    settled: dict[int, EngineError | None] = {
        pos: None if is_own_id_replay(row_err, "id") else row_err for pos, row_err in named.items()
    }
    for group in groups:
        refusals = [settled[pos] for pos in group if settled.get(pos) is not None]
        if refusals:
            for pos in group:
                settled.setdefault(pos, refusals[0])
    return settled
