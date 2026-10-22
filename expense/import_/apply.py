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

Everything this module reports is the engine's words alone (`errors.engine_text`):
the import is typed and printed, so no line of the app's (a key to press, a
screen to open) is added to them.
"""

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
    # (chunk_index, message) — messages carry sheet line numbers so a failed
    # row can be found in the workbook without bisecting.
    failures: list[tuple[int, str]] = field(default_factory=list)


def _list_all(
    client: ExpenseClient, resource: str, *, include_archived: bool = False
) -> list[dict]:
    """GET every existing row for a resource — one read, the engine returns it whole.

    `include_archived` applies to accounts only — the only archivable resource.
    """
    params = query_params(include_archived=include_archived)
    return items_of(client.get(f"/{resource}", params=params or None))


def _resolve_each(
    client: ExpenseClient,
    resource: str,
    wanted,
    *,
    existing: dict,
    key_of,
    payload_of,
    describe,
    index_of=None,
) -> tuple[dict, int, int, list[str]]:
    """Resolve each wanted spec against `existing` (reuse) or POST it (create).

    Returns (key → id, created, reused, failures). The one copy of the
    resolve-or-POST loop the three resource blocks below share. `existing`
    is mutated so a duplicate spec reuses the row created for the first one;
    `payload_of(spec)` is the create body beyond the minted `id`.

    `key_of` identifies the spec *engine-side* — it must match how `existing`
    was keyed, or a row that already exists would be created again. `index_of`
    identifies it *sheet-side* — it is how the returned map is keyed, i.e. what
    callers look a row's resource up by. They coincide for categories and
    hashtags (the sheet cell is the engine name) and diverge for accounts,
    whose engine name may carry a currency suffix the sheet never had.

    A per-spec `EngineError` (422/409/5xx-after-retries) is collected via
    `describe(spec)` and the loop continues, so one bad resource does not abort
    the whole import. An `EngineConnectionError`
    propagates: the engine is unreachable, so nothing further can succeed and a
    re-run converges once it's back. So does an account-wide refusal
    (`errors.refuses_every_write`): every later write would draw it too, so the
    run ends there and the command reports it once.
    """
    index_of = index_of or key_of
    ids: dict = {}
    created = reused = 0
    failures: list[str] = []
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
                failures.append(f"{resource[:-1]} {describe(spec)}: {engine_text(err)}")
                continue
            existing[key] = nid
            ids[index_of(spec)] = nid
            created += 1
    return ids, created, reused, failures


def resolve_or_create(client: ExpenseClient, plan: ImportPlan) -> ResolveResult:
    res = ResolveResult(account_ids={}, category_ids={}, hashtag_ids={})

    # --- accounts: keyed by (name, currency) ---
    amap: dict[tuple[str, str], str] = {}
    for acc in _list_all(client, "accounts", include_archived=True):
        name, cur, aid = acc.get("name"), acc.get("currency_code"), acc.get("id")
        if name and cur and aid:
            amap[(str(name).strip().casefold(), str(cur).upper())] = aid
    res.account_ids, res.accounts_created, res.accounts_reused, af = _resolve_each(
        client,
        "accounts",
        plan.accounts,
        existing=amap,
        key_of=lambda s: (s.name.strip().casefold(), s.currency),
        index_of=lambda s: (s.source_name.strip().casefold(), s.currency),
        payload_of=lambda s: {"name": s.name, "currency_code": s.currency},
        describe=lambda s: f"{s.name!r} ({s.currency})",
    )
    res.resolve_failures.extend(af)

    # --- categories: case-insensitive; no color is sent, so a created one takes
    # the engine's default (contract: POST /v1/categories) ---
    cmap: dict[str, str] = {}
    for cat in _list_all(client, "categories"):
        name, cid = cat.get("name"), cat.get("id")
        if name and cid:
            cmap[str(name).strip().casefold()] = cid
    res.category_ids, res.categories_created, res.categories_reused, cf = _resolve_each(
        client,
        "categories",
        plan.categories,
        existing=cmap,
        key_of=lambda n: n.strip().casefold(),
        payload_of=lambda n: {"name": n},
        describe=repr,
    )
    res.resolve_failures.extend(cf)

    # --- hashtags: case-insensitive, no color ---
    hmap: dict[str, str] = {}
    for tag in _list_all(client, "hashtags"):
        name, hid = tag.get("name"), tag.get("id")
        if name and hid:
            hmap[str(name).strip().casefold()] = hid
    res.hashtag_ids, res.hashtags_created, res.hashtags_reused, hf = _resolve_each(
        client,
        "hashtags",
        plan.hashtags,
        existing=hmap,
        key_of=lambda n: n.strip().casefold(),
        payload_of=lambda n: {"name": n},
        describe=repr,
    )
    res.resolve_failures.extend(hf)

    return res


def _missing_dep(row: ParsedRow, res: ResolveResult) -> str | None:
    """Name the first resource `row` needs that failed to resolve, else None.

    Guards `build_tx_payload`'s `*_ids[...]` lookups: a resource whose create
    POST failed is absent from the maps, so its dependent rows are skipped
    pre-flight instead of raising `KeyError` mid-batch.
    """
    if (row.account.strip().casefold(), row.currency) not in res.account_ids:
        return f"account {row.account!r} ({row.currency})"
    if row.category.strip().casefold() not in res.category_ids:
        return f"category {row.category!r}"
    if row.hashtag.strip().casefold() not in res.hashtag_ids:
        return f"hashtag {row.hashtag!r}"
    return None


def build_tx_payload(row: ParsedRow, tx_id: str, res: ResolveResult) -> dict:
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
    (remaining openings are counted failed). An account-wide refusal
    (`errors.refuses_every_write`) propagates, ending the run.
    """
    for pos, row in enumerate(plan.openings):
        account_key = (row.account.strip().casefold(), row.currency)
        account_id = res.account_ids.get(account_key)
        if account_id is None:
            result.opening_failed += 1
            result.failures.append(
                (
                    -1,
                    f"sheet line {row.line}: opening balance not sent — "
                    f"account {row.account!r} ({row.currency}) was not created",
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
                result.failures.append(
                    (-1, f"sheet line {row.line} (opening balance): {engine_text(err)}")
                )
        except EngineConnectionError as err:
            result.opening_failed += len(plan.openings) - pos
            result.failures.append(
                (
                    -1,
                    f"CONNECTION_ERROR: {engine_text(err)} — opening balances from "
                    f"sheet line {row.line} on were not sent",
                )
            )
            return False
    return True


def _line_range(items: list[dict], line_by_id: dict[str, int]) -> str:
    lines = sorted(line_by_id[item["id"]] for item in items)
    if lines[0] == lines[-1]:
        return f"sheet line {lines[0]}"
    return f"sheet lines {lines[0]}-{lines[-1]}"


def _fold_outcome(
    outcome: BatchOutcome, items: list[dict], line_by_id: dict[str, int], result: ApplyResult
) -> None:
    """Turn an index-aligned `BatchOutcome` into this importer's vocabulary.

    The batch mechanics live in [batch_write.py](../batch_write.py), shared with
    the TUI's LOG bar; what stays here is the sheet-line
    phrasing, which only a workbook has. A grouped failure keeps its range
    (`sheet lines 2-3`) so a chunk-level 403 is still reported once.

    An account-wide refusal that stopped the run (`outcome.refusal`) is raised
    instead of folded, leaving `result` untouched: it ends the run like one on
    a resource create or an opening balance does, and the command reports it
    once. The only stop folded here is a connection error.
    """
    if outcome.refusal is not None:
        raise outcome.refusal

    for row in outcome.results:
        if row is RowResult.CREATED:
            result.tx_created += 1
        elif row is RowResult.EXISTED:
            result.tx_skipped_existing += 1
        else:
            result.tx_failed += 1

    for failure in outcome.failures:
        rows = [items[i] for i in failure.indices]
        where = _line_range(rows, line_by_id)
        if len(rows) == 1:
            # one row: name its id too, so a duplicate title is still unambiguous
            where = f"{where}, id {rows[0]['id']}"
        result.failures.append((failure.chunk_index, f"{where}: {failure.message}"))

    if outcome.stop_error is not None:
        unsent = [line_by_id[items[i]["id"]] for i in outcome.unsent]
        where = f"rows from sheet line {min(unsent)} on were not sent" if unsent else "run stopped"
        result.failures.append(
            (
                outcome.stop_chunk_index if outcome.stop_chunk_index is not None else -1,
                f"CONNECTION_ERROR: {outcome.stop_error} — {where}",
            )
        )


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
            (-1, "transactions not sent — connection lost while seeding opening balances")
        )
        return result

    items: list[dict] = []
    line_by_id: dict[str, int] = {}
    for row in plan.rows:
        missing = _missing_dep(row, res)
        if missing is not None:
            # Its dependency's create POST failed (recorded in resolve_failures);
            # this row can't reference a row that doesn't exist.
            result.tx_failed += 1
            result.failures.append(
                (-1, f"sheet line {row.line}: not sent — {missing} was not created")
            )
            continue
        tx_id = plan.tx_ids[row.line]
        items.append(build_tx_payload(row, tx_id, res))
        line_by_id[tx_id] = row.line
    outcome = post_transaction_batch(client, items, chunk_size=chunk_size, error_text=engine_text)
    _fold_outcome(outcome, items, line_by_id, result)  # raises an account-wide refusal
    return result
