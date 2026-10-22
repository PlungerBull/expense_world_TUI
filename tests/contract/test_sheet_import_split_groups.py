"""Contract: the sheet import brings rows sharing a `COD_EECC` in as one bank line.

The importer sends each row's `COD_EECC` as its `statement_line`, and rows sharing
one as the items of one `line_group`, which the engine creates as the parts of one
bank line sharing one `line_code` and one `statement_line`
(contract: POST /v1/transactions/batch, "Line groups"). Run again, the sheet counts
every row as already there, a group's parts included, since a create sent again
answers `ID_EXISTS` on its own id before anything else
(contract: "Base Conventions", "Which refusal comes first on a create"). A group
whose rows differ, or with a row the parse cannot read, is skipped, and comes in
on a later run once fixed.

Every name and code is fresh per run: the practice user's data outlives a reseed,
and a statement line is one live line per user. The test undoes what it wrote.
Gating, target and the real-ledger guard: conftest.py.
"""

from uuid import uuid4

from expense.errors import EngineError
from expense.import_ import apply as apply_mod
from expense.import_ import plan as plan_mod
from expense.import_.parse import parse_sheet
from expense.import_.reader import RawRow, SheetData
from tests.contract.conftest import read_signed

HEADERS = ["Descripcion", "CATEGORY", "HASHTAG", "Fecha", "Monto", "Cuenta", "Moneda", "COD_EECC"]


def _safe(call, *args) -> None:
    try:
        call(*args)
    except EngineError:
        pass


def _sheet(run: str, *, fixed: bool) -> SheetData:
    """Two rows sharing a code, one row alone, two rows sharing another code on
    two dates unless `fixed`, and two sharing a third, one of them unreadable
    unless `fixed`."""
    account, category, hashtag = f"contract-sheet-{run}", f"contract-{run}", f"contract-{run}"

    def row(line: int, title: str, date: str, amount: float, code: str | None) -> RawRow:
        return RawRow(line, [title, category, hashtag, date, amount, account, "PEN", code])

    return SheetData(
        headers=list(HEADERS),
        rows=[
            row(2, "SUPERMERCADO", "2026-03-14", -60.0, f"SIG-{run}-001"),
            row(3, "SUPERMERCADO", "2026-03-14", -40.0, f"SIG-{run}-001"),
            row(4, "CAFE", "2026-03-15", -9.5, None),
            row(5, "FARMACIA", "2026-03-16", -20.0, f"SIG-{run}-002"),
            row(6, "FARMACIA", "2026-03-16" if fixed else "2026-03-17", -5.0, f"SIG-{run}-002"),
            row(7, "LIBRERIA", "2026-03-18", -12.0, f"SIG-{run}-003"),
            row(8, "LIBRERIA", "2026-03-18" if fixed else "not a date", -3.0, f"SIG-{run}-003"),
        ],
    )


def _run(
    client, sheet: SheetData, resolved: list[apply_mod.ResolveResult]
) -> tuple[plan_mod.ImportPlan, apply_mod.ApplyResult]:
    """Import `sheet` as `expense import sheet --apply` does, keeping what it
    resolved for the cleanup."""
    plan = plan_mod.build_plan(*parse_sheet(sheet))
    res = apply_mod.resolve_or_create(client, plan)
    resolved.append(res)
    return plan, apply_mod.apply_plan(client, plan, res)


def test_a_sheet_with_a_group_lands_one_line_and_a_re_run_finds_every_row(client):
    run = uuid4().hex[:10]
    written: set[str] = set()
    resolved: list[apply_mod.ResolveResult] = []
    try:
        plan, result = _run(client, _sheet(run, fixed=False), resolved)
        written |= set(plan.tx_ids.values())

        assert plan.split_mismatches == [
            f"SIG-{run}-002: line 5 is 2026-03-16, line 6 is 2026-03-17.",
            f"SIG-{run}-003: line 8 can't be read, so line 7 waits for it.",
        ]
        assert (result.tx_created, result.tx_skipped_existing, result.tx_failed) == (3, 0, 0)
        part_a, part_b, alone = (read_signed(client, plan.tx_ids[line]) for line in (2, 3, 4))
        assert part_a["bank_line_id"] == part_b["bank_line_id"] != alone["bank_line_id"]
        assert part_a["line_code"] == part_b["line_code"] != alone["line_code"]
        assert part_a["statement_line"] == part_b["statement_line"] == f"SIG-{run}-001"
        assert alone["statement_line"] is None
        line = client.get(f"/bank-lines/{part_a['bank_line_id']}")
        assert sorted(p["id"] for p in line["parts"]) == sorted([part_a["id"], part_b["id"]])
        assert (line["line_code"], line["statement_line"]) == (
            part_a["line_code"],
            f"SIG-{run}-001",
        )

        # The sheet fixed: what landed is already there, the fixed groups come in.
        plan, result = _run(client, _sheet(run, fixed=True), resolved)
        written |= set(plan.tx_ids.values())
        assert plan.split_mismatches == []
        assert (result.tx_created, result.tx_skipped_existing, result.tx_failed) == (4, 3, 0)
        for first, second, code in ((5, 6, "002"), (7, 8, "003")):
            part_c, part_d = (read_signed(client, plan.tx_ids[line]) for line in (first, second))
            assert part_c["line_code"] == part_d["line_code"]
            assert part_c["statement_line"] == part_d["statement_line"] == f"SIG-{run}-{code}"

        # Run again: every row is already there, groups included.
        plan, result = _run(client, _sheet(run, fixed=True), resolved)
        assert (result.tx_created, result.tx_skipped_existing, result.tx_failed) == (0, 7, 0)
        assert result.failures == []
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        for res in resolved:
            for account_id in res.account_ids.values():
                _safe(client.delete, f"/accounts/{account_id}")
            for category_id in res.category_ids.values():
                _safe(client.delete, f"/categories/{category_id}")
            for hashtag_id in res.hashtag_ids.values():
                _safe(client.delete, f"/hashtags/{hashtag_id}")


def test_an_edited_split_whose_statement_line_is_in_the_ledger_fails_on_its_sheet_lines(client):
    """Edited rows have new ids, so they are no replay: the engine refuses the
    group `STATEMENT_LINE_EXISTS` on its first part, since the line imported
    before still holds the statement line (contract: POST /v1/transactions/batch, "Line groups").
    The importer shows the first part's sheet line with the engine's words for
    it, and the other part's with the app's line for a split transaction's
    other rows."""
    run = uuid4().hex[:10]
    code = f"SIG-{run}-009"
    account, category = f"contract-sheet-{run}", f"contract-{run}"

    def sheet(first: float, second: float) -> SheetData:
        def cells(amount: float) -> list:
            return ["PANADERIA", category, category, "2026-03-20", amount, account, "PEN", code]

        return SheetData(
            headers=list(HEADERS), rows=[RawRow(2, cells(first)), RawRow(3, cells(second))]
        )

    written: set[str] = set()
    resolved: list[apply_mod.ResolveResult] = []
    try:
        plan, result = _run(client, sheet(-7.0, -3.0), resolved)
        written |= set(plan.tx_ids.values())
        assert result.tx_created == 2

        plan, result = _run(client, sheet(-8.0, -4.0), resolved)
        written |= set(plan.tx_ids.values())
        assert (result.tx_created, result.tx_skipped_existing, result.tx_failed) == (0, 0, 2)
        named, part = result.failures
        assert named.lines == (2,) and named.words.startswith("statement_line: ")
        assert named.detail.startswith("CONFLICT — ")
        assert f"'{code}'" in named.detail and "statement_line: " in named.detail
        assert (part.words, part.lines) == (apply_mod.SPLIT_PART_REFUSED, (3,))
        assert named.kind != part.kind
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        for res in resolved:
            for account_id in res.account_ids.values():
                _safe(client.delete, f"/accounts/{account_id}")
            for category_id in res.category_ids.values():
                _safe(client.delete, f"/categories/{category_id}")
            for hashtag_id in res.hashtag_ids.values():
                _safe(client.delete, f"/hashtags/{hashtag_id}")
