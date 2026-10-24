"""Write path: resolve-or-create resources, then POST transactions in batches.

Accounts/categories/hashtags are created FIRST (so they have ids); transactions
then reference those ids. The batch endpoint is atomic: a refused chunk writes
none of its rows (contract: POST /v1/transactions/batch, "No partial success").
The shared batch writer ([batch_write.py](../batch_write.py)) reads every row a
refused chunk names: a row refused only because its own id is taken
(`ID_EXISTS`, an earlier run's write) is skipped as already imported, every
other refused row reports its sheet line, and the rest go again and land.
Re-runs after a partial run or with appended sheet rows converge instead of
silently dropping.

A row's ``COD_EECC`` is never sent: it only groups. The rows of a split
transaction (`plan.SplitGroup`) go as the items of one `line_group`, so the
engine makes them the parts of one bank line
(contract: POST /v1/transactions/batch, "Line groups"). A split transaction is
sent whole or not at all: the plan holds back a group missing a row the parse
could not read (a zero-amount part is no movement, and is only dropped), and
a group with a row whose resource was not created stays here unsent.

Every refusal this module reports is in the engine's words alone
(`errors.engine_text`, or `errors.row_words` for a refused row): the import is
typed and printed, so no line of the app's (a key to press, a screen to open)
is added to them. The app's own lines say only what the engine never saw: a
row held back, a split transaction's other rows, the rows never sent.
"""

from collections.abc import Hashable
from dataclasses import dataclass, field
from uuid import uuid4

from expense.batch_write import (
    CHUNK_SIZE,
    BatchOutcome,
    RowResult,
    post_transaction_batch,
    require_sendable_chunk_size,
)
from expense.dates import to_canonical_aware
from expense.errors import (
    EngineConnectionError,
    EngineError,
    engine_text,
    is_own_id_replay,
    refuses_every_write,
    row_words,
)
from expense.http import ExpenseClient
from expense.import_.parse import OpeningRow, ParsedRow
from expense.import_.plan import ImportPlan
from expense.reads import items_of, query_params


@dataclass
class ResolveResult:
    account_ids: dict[tuple[str, str], str]  # (name.casefold, currency) -> id
    category_ids: dict[str, str]  # name.casefold -> id
    hashtag_ids: dict[str, str]  # name.casefold -> id
    accounts_created: int = 0
    accounts_reused: int = 0
    categories_created: int = 0
    categories_reused: int = 0
    hashtags_created: int = 0
    hashtags_reused: int = 0
    # Per-resource create failures (name + engine error). A failed resource is
    # left out of the *_ids maps, so its dependent transactions are skipped
    # pre-flight rather than crashing on a KeyError.
    resolve_failures: list[str] = field(default_factory=list)
    # Each resource not created, as its failure names it (`category 'NEW'`),
    # keyed by its kind and the key its *_ids map would hold: every row needing
    # it names it alike, however its own cell spells it.
    not_created: dict[tuple[str, Hashable], str] = field(default_factory=dict)


#: The app's line for the other rows of a split transaction the engine refused
#: one part of: the transaction fails whole, the refused row shows the engine's
#: words, and these rows show here.
SPLIT_PART_REFUSED = "Part of a split transaction refused for another row."
#: The app's line for the other rows of a split transaction held back because
#: one part could not be sent: that row shows its own `Not sent:` line.
SPLIT_PART_NOT_SENT = "Part of a split transaction not sent for another row."
_PART_NOT_SENT_KIND = ("part not sent",)


@dataclass(frozen=True)
class Failure:
    """One refusal or stop the import reports, and the sheet lines it covers.

    `kind` decides how it prints. Failures of one kind print as one line:
    `words`, then the rows they hit (`formatting.rows_phrase`). A kind is a
    refusal's (`batch_write.BatchFailure.kind`), one resource not created (its
    rows read `Not sent: category 'NEW' was not created.`), or the other rows
    of split transactions held back (`SPLIT_PART_NOT_SENT`). A failure with no
    kind is a line of its own, its `words` as they stand: a stop, the sheet
    lines never sent, an opening balance. `detail` is the engine's whole answer
    for these rows, its code and message included, kept for `--json`; empty for
    a line the app writes.
    """

    words: str
    lines: tuple[int, ...] = ()
    kind: Hashable | None = None
    chunk: int = -1  # -1: before or beside the batch
    detail: str = ""


@dataclass
class ApplyResult:
    resolve: ResolveResult
    tx_created: int = 0
    tx_skipped_existing: int = 0  # rows refused ID_EXISTS on their own id: already in
    tx_failed: int = 0
    opening_created: int = 0
    # seeds already written: refused ID_EXISTS on their own transaction_id
    opening_skipped_existing: int = 0
    opening_failed: int = 0
    # what failed, each with the sheet lines it covers, so a failed row can be
    # found in the workbook without bisecting
    failures: list[Failure] = field(default_factory=list)


def _list_all(
    client: ExpenseClient,
    resource: str,
    *,
    include_archived: bool = False,
    include_people: bool = False,
) -> list[dict]:
    """GET every existing row for a resource — one read, the engine returns it whole.

    `include_archived` and `include_people` apply to accounts only: the engine
    lists archived accounts and person accounts only when asked (contract:
    GET /v1/accounts). An account name is unique per currency across real and
    person accounts (contract: "People / Person Accounts"), so the import asks
    for both, or a re-run would POST an account that exists and draw a refusal.
    """
    params = query_params(include_archived=include_archived, include_people=include_people)
    return items_of(client.get(f"/{resource}", params=params or None))


def _resolve_each(
    client: ExpenseClient,
    resource: str,
    noun: str,
    wanted,
    *,
    existing: dict,
    key_of,
    payload_of,
    describe,
    index_of=None,
) -> tuple[dict, int, int, list[str], dict]:
    """Resolve each wanted spec against `existing` (reuse) or POST it (create).

    Returns (key → id, created, reused, failures, key → name of each spec not
    created), both maps keyed by `index_of`. A spec is named `noun` (the
    resource in the singular) then `describe(spec)`. The one copy of the
    resolve-or-POST loop the three resource blocks below share. `existing`
    is mutated so a duplicate spec reuses the row created for the first one;
    `payload_of(spec)` is the create body beyond the minted `id`.

    `key_of` identifies the spec *engine-side* — it must match how `existing`
    was keyed, or a row that already exists would be created again. `index_of`
    identifies it *sheet-side* — it is how the returned map is keyed, i.e. what
    callers look a row's resource up by. They coincide for categories and
    hashtags (the sheet cell is the engine name) and diverge for accounts,
    whose engine name may carry a currency suffix the sheet never had.

    A per-spec `EngineError` (422/409/5xx-after-retries) is collected under the
    spec's name and the loop continues, so one bad resource does not abort
    the whole import. An `EngineConnectionError`
    propagates: the engine is unreachable, so nothing further can succeed and a
    re-run converges once it's back. So does a refusal every later write would
    draw too (`errors.refuses_every_write`: `SETTINGS_MISSING`, or
    `LINE_CODES_EXHAUSTED`, which no resource create can draw): the run ends
    there and the command reports it once.
    """
    index_of = index_of or key_of
    ids: dict = {}
    created = reused = 0
    failures: list[str] = []
    not_created: dict = {}
    for spec in wanted:
        key = key_of(spec)
        if key in existing:
            ids[index_of(spec)] = existing[key]
            reused += 1
        else:
            nid = str(uuid4())
            try:
                client.post(f"/{resource}", json_body={"id": nid, **payload_of(spec)})
            except EngineError as err:
                if refuses_every_write(err):
                    raise
                named = f"{noun} {describe(spec)}"
                failures.append(f"{named}: {engine_text(err)}")
                not_created[index_of(spec)] = named
                continue
            existing[key] = nid
            ids[index_of(spec)] = nid
            created += 1
    return ids, created, reused, failures, not_created


def resolve_or_create(client: ExpenseClient, plan: ImportPlan) -> ResolveResult:
    res = ResolveResult(account_ids={}, category_ids={}, hashtag_ids={})

    # --- accounts: keyed by (name, currency) ---
    amap: dict[tuple[str, str], str] = {}
    for acc in _list_all(client, "accounts", include_archived=True, include_people=True):
        name, cur, aid = acc.get("name"), acc.get("currency_code"), acc.get("id")
        if name and cur and aid:
            amap[(str(name).strip().casefold(), str(cur).upper())] = aid
    res.account_ids, res.accounts_created, res.accounts_reused, af, an = _resolve_each(
        client,
        "accounts",
        "account",
        plan.accounts,
        existing=amap,
        key_of=lambda s: (s.name.strip().casefold(), s.currency),
        index_of=lambda s: (s.source_name.strip().casefold(), s.currency),
        payload_of=lambda s: {"name": s.name, "currency_code": s.currency},
        describe=lambda s: f"{s.name!r} ({s.currency})",
    )
    res.resolve_failures.extend(af)
    res.not_created.update({("account", key): named for key, named in an.items()})

    # --- categories: case-insensitive; no color is sent, so a created one takes
    # the engine's default (contract: POST /v1/categories) ---
    cmap: dict[str, str] = {}
    for cat in _list_all(client, "categories"):
        name, cid = cat.get("name"), cat.get("id")
        if name and cid:
            cmap[str(name).strip().casefold()] = cid
    res.category_ids, res.categories_created, res.categories_reused, cf, cn = _resolve_each(
        client,
        "categories",
        "category",
        plan.categories,
        existing=cmap,
        key_of=lambda n: n.strip().casefold(),
        payload_of=lambda n: {"name": n},
        describe=repr,
    )
    res.resolve_failures.extend(cf)
    res.not_created.update({("category", key): named for key, named in cn.items()})

    # --- hashtags: case-insensitive, no color ---
    hmap: dict[str, str] = {}
    for tag in _list_all(client, "hashtags"):
        name, hid = tag.get("name"), tag.get("id")
        if name and hid:
            hmap[str(name).strip().casefold()] = hid
    res.hashtag_ids, res.hashtags_created, res.hashtags_reused, hf, hn = _resolve_each(
        client,
        "hashtags",
        "hashtag",
        plan.hashtags,
        existing=hmap,
        key_of=lambda n: n.strip().casefold(),
        payload_of=lambda n: {"name": n},
        describe=repr,
    )
    res.resolve_failures.extend(hf)
    res.not_created.update({("hashtag", key): named for key, named in hn.items()})

    return res


def _not_created(res: ResolveResult, noun: str, key: Hashable, spelled: str) -> str:
    """The resource of kind `noun` under `key` that was not created, named as its
    create failure names it (`ResolveResult.not_created`), so rows spelling it
    `NEW` and `new` name it alike; `spelled` (the row's own cell) only for a key
    no create was tried for."""
    return res.not_created.get((noun, key), f"{noun} {spelled}")


def _missing_dep(row: ParsedRow, res: ResolveResult) -> str | None:
    """Name the first resource `row` needs that failed to resolve, else None.

    Guards `build_tx_payload`'s `*_ids[...]` lookups: a resource whose create
    POST failed is absent from the maps, so its dependent rows are skipped
    pre-flight instead of raising `KeyError` mid-batch.
    """
    account = (row.account.strip().casefold(), row.currency)
    if account not in res.account_ids:
        return _not_created(res, "account", account, f"{row.account!r} ({row.currency})")
    category = row.category.strip().casefold()
    if category not in res.category_ids:
        return _not_created(res, "category", category, repr(row.category))
    hashtag = row.hashtag.strip().casefold()
    if hashtag not in res.hashtag_ids:
        return _not_created(res, "hashtag", hashtag, repr(row.hashtag))
    return None


def build_tx_payload(
    row: ParsedRow, tx_id: str, res: ResolveResult, line_group: str | None = None
) -> dict:
    payload: dict = {
        "id": tx_id,
        "title": row.title,
        "amount_cents": row.amount_cents,
        "account_id": res.account_ids[(row.account.strip().casefold(), row.currency)],
        "category_id": res.category_ids[row.category.strip().casefold()],
        "hashtag_ids": [res.hashtag_ids[row.hashtag.strip().casefold()]],
        "date": to_canonical_aware(row.date_iso),
    }
    if row.description is not None:
        payload["description"] = row.description
    if line_group is not None:
        payload["line_group"] = line_group
    return payload


def build_opening_payload(row: OpeningRow, transaction_id: str) -> dict:
    payload: dict = {
        "transaction_id": transaction_id,
        "amount_cents": row.amount_cents,
        "date": to_canonical_aware(row.date_iso),
        "title": row.title,
    }
    return payload


def _apply_openings(client: ExpenseClient, plan: ImportPlan, res, result: ApplyResult) -> bool:
    """POST each opening balance to /accounts/{id}/opening-balance.

    A seed refused only because its own `transaction_id` is taken (`ID_EXISTS`)
    already landed, and counts as already present: a create sent again answers
    that before any other refusal, an existing opening balance included
    (contract: "Base Conventions", "Which refusal comes first on a create")
    (contract: POST /v1/accounts/{account_id}/opening-balance). Any other refusal
    is a failure. Returns False when a connection error stopped the run
    (remaining openings are counted failed). A refusal every later write would
    draw too (`errors.refuses_every_write`: `SETTINGS_MISSING`, or
    `LINE_CODES_EXHAUSTED` on the seed's `transaction_id`) propagates, ending the
    run.
    """
    for pos, row in enumerate(plan.openings):
        account_key = (row.account.strip().casefold(), row.currency)
        account_id = res.account_ids.get(account_key)
        if account_id is None:
            result.opening_failed += 1
            account = _not_created(res, "account", account_key, f"{row.account!r} ({row.currency})")
            result.failures.append(
                Failure(
                    f"sheet line {row.line}: opening balance not sent — {account} was not created",
                    (row.line,),
                )
            )
            continue
        try:
            client.post(
                f"/accounts/{account_id}/opening-balance",
                json_body=build_opening_payload(row, plan.opening_ids[row.line]),
            )
            result.opening_created += 1
        except EngineError as err:
            if refuses_every_write(err):
                raise
            if is_own_id_replay(err, "transaction_id"):
                result.opening_skipped_existing += 1
            else:
                result.opening_failed += 1
                words = f"sheet line {row.line} (opening balance): {engine_text(err)}"
                result.failures.append(Failure(words, (row.line,), detail=engine_text(err)))
        except EngineConnectionError as err:
            result.opening_failed += len(plan.openings) - pos
            result.failures.append(
                Failure(
                    f"CONNECTION_ERROR: {engine_text(err)} — opening balances from "
                    f"sheet line {row.line} on were not sent",
                    tuple(later.line for later in plan.openings[pos:]),
                )
            )
            return False
    return True


def _fold_outcome(
    outcome: BatchOutcome, items: list[dict], line_by_id: dict[str, int], result: ApplyResult
) -> None:
    """Turn an index-aligned `BatchOutcome` into this importer's vocabulary.

    The batch mechanics live in [batch_write.py](../batch_write.py), shared with
    the TUI's LOG bar; what stays here is the sheet lines, which only a workbook
    has. Each failure keeps its kind (`BatchFailure.kind`), so the command says
    one kind of refusal on one line: a row's refusal in the engine's words for
    it (`errors.row_words`), a split transaction's other parts on the app's line
    (`SPLIT_PART_REFUSED`), and a refusal naming no row, such as a
    chunk-level 403, once for its chunk.

    A refusal that stopped the run (`outcome.refusal`) and names no row
    (`SETTINGS_MISSING`) is raised instead of folded, leaving `result` untouched:
    it ends the run like one on a resource create or an opening balance does, and
    the command reports it once. One that names its row (`LINE_CODES_EXHAUSTED`,
    on the first item that needed a new line) is folded like a connection stop:
    that row fails against its sheet line in the engine's words, and the rows
    not sent are named once (`_not_sent`).
    """
    if outcome.refusal is not None and any(
        f.whole_chunk and f.error is outcome.refusal for f in outcome.failures
    ):
        raise outcome.refusal

    for row in outcome.results:
        if row is RowResult.CREATED:
            result.tx_created += 1
        elif row is RowResult.EXISTED:
            result.tx_skipped_existing += 1
        else:
            result.tx_failed += 1

    for failure in outcome.failures:
        lines = tuple(line_by_id[items[i]["id"]] for i in failure.indices)
        if failure.whole_chunk:
            words = engine_text(failure.error)
        elif failure.for_part:
            words = SPLIT_PART_REFUSED
        else:
            words = row_words(failure.error)
        result.failures.append(
            Failure(
                words,
                lines,
                kind=failure.kind,
                chunk=failure.chunk_index,
                detail="" if failure.for_part else engine_text(failure.error),
            )
        )

    stop_chunk = outcome.stop_chunk_index if outcome.stop_chunk_index is not None else -1
    where = _not_sent(outcome.unsent, items, line_by_id)
    unsent = tuple(line_by_id[items[i]["id"]] for i in outcome.unsent)
    if outcome.stop_error is not None:
        said = where or "run stopped"
        result.failures.append(
            Failure(f"CONNECTION_ERROR: {outcome.stop_error} — {said}", unsent, chunk=stop_chunk)
        )
    elif outcome.refusal is not None and where:
        result.failures.append(Failure(where, unsent, chunk=stop_chunk))


def _not_sent(unsent: list[int], items: list[dict], line_by_id: dict[str, int]) -> str:
    """The sheet lines of the rows a stopped run never sent, as runs of rows
    next to each other in the sheet's order (`sheet lines 3-5, 9-4188 were not
    sent`); a row that was settled breaks a run, so no line it names was sent.
    Empty when every row was settled."""
    if not unsent:
        return ""
    left = set(unsent)
    runs: list[list[int]] = []
    for index in range(len(items)):
        if index not in left:
            if runs and runs[-1]:
                runs.append([])
            continue
        if not runs:
            runs.append([])
        runs[-1].append(line_by_id[items[index]["id"]])
    spans = [
        f"{min(run)}" if min(run) == max(run) else f"{min(run)}-{max(run)}" for run in runs if run
    ]
    if len(unsent) == 1:
        return f"sheet line {spans[0]} was not sent"
    return f"sheet lines {', '.join(spans)} were not sent"


def apply_plan(
    client: ExpenseClient,
    plan: ImportPlan,
    res: ResolveResult,
    *,
    chunk_size: int = CHUNK_SIZE,
) -> ApplyResult:
    require_sendable_chunk_size(chunk_size)  # before the opening balances are written
    result = ApplyResult(resolve=res)

    # Opening balances go first: seeds are account-level state, and if the
    # engine is unreachable the ordinary rows would fail identically anyway.
    if not _apply_openings(client, plan, res, result):
        result.tx_failed += len(plan.rows)
        result.failures.append(
            Failure(
                "transactions not sent — connection lost while seeding opening balances",
                tuple(row.line for row in plan.rows),
            )
        )
        return result

    items: list[dict] = []
    line_by_id: dict[str, int] = {}
    group_of = plan.group_of()
    missing = {row.line: _missing_dep(row, res) for row in plan.rows}
    for row in plan.rows:
        group = group_of.get(row.line)
        why = missing[row.line]
        if why is not None:
            # Its dependency's create POST failed (recorded in resolve_failures);
            # this row can't reference a row that doesn't exist.
            result.tx_failed += 1
            words = f"Not sent: {why} was not created."
            result.failures.append(Failure(words, (row.line,), kind=("not sent", why)))
            continue
        blocker = next((line for line in group.lines if missing[line]), None) if group else None
        if blocker is not None:
            # A split transaction goes whole or not at all: its other rows show
            # on the app's line for a part held back.
            result.tx_failed += 1
            result.failures.append(
                Failure(SPLIT_PART_NOT_SENT, (row.line,), kind=_PART_NOT_SENT_KIND)
            )
            continue
        tx_id = plan.tx_ids[row.line]
        items.append(build_tx_payload(row, tx_id, res, group.name if group else None))
        line_by_id[tx_id] = row.line
    outcome = post_transaction_batch(client, items, chunk_size=chunk_size, error_text=engine_text)
    _fold_outcome(outcome, items, line_by_id, result)  # raises a run stop naming no row
    return result
