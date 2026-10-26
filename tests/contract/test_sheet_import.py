"""Contract: the sheet import through the engine, run by the app's own module
(expense/import_/engine.py) on made-up sheets.

The engine reads the whole sheet, matches every row against the ledger and writes
everything or nothing (contract: POST /v1/transactions/import-sheet). It never
creates a name: the module creates each one the sheet uses that the caller lacks,
then sends the table giving every name its id
(contract: POST /v1/transactions/import-sheet, "Names"). A bad row refuses the
whole sheet, keyed by its row, before any name is created
(contract: POST /v1/transactions/import-sheet, "Rejected up front with `422`").
The same sheet sent again matches every row and writes nothing
(contract: POST /v1/transactions/import-sheet, "Matching").

Every name is fresh per run, so a second run of the suite still finds every row
new on its first apply: the practice user's data outlives a reseed. Each test
undoes what it wrote. Gating, target and the real-ledger guard: conftest.py.
"""

from datetime import date
from uuid import uuid4

from expense.errors import EngineError
from expense.import_.engine import (
    ACCOUNT,
    CATEGORY,
    HASHTAG,
    Goes,
    SheetImport,
    Stage,
    import_sheet,
    rename_key,
    request_body,
    table_body,
)
from tests.contract.conftest import (
    CLEANER,
    assert_refusals,
    live_ids,
    read_signed,
    refused,
    sheet_file,
    sheet_row,
)


class Names:
    """One run's made-up names: an account, two categories and two hashtags."""

    def __init__(self) -> None:
        run = uuid4().hex[:10]
        self.account = f"contract-sheet-{run}"
        self.food = f"contract-sheet-c-food-{run}"
        self.pay = f"contract-sheet-c-pay-{run}"
        self.home = f"contract-sheet-h-home-{run}"
        self.work = f"contract-sheet-h-work-{run}"


def _good(n: Names) -> list[list]:
    """Rows 2 to 7: two soles rows, a dollar row under the same account name, a row
    of zero, and a split of two parts sharing a `COD_EECC`."""
    a, code = n.account, f"SIG-{n.account}"
    return [
        sheet_row("CAFE", n.home, n.food, date(2026, 3, 14), -9.5, a, "PEN", note="made up"),
        sheet_row("SUELDO", n.work, n.pay, date(2026, 3, 15), 1500, a, "PEN"),
        sheet_row("TIENDA", n.home, n.food, date(2026, 3, 16), -20.25, a, "USD"),
        sheet_row("NADA", n.home, n.food, date(2026, 3, 17), 0, a, "PEN"),
        sheet_row("SUPERMERCADO", n.home, n.food, date(2026, 3, 18), -60, a, "PEN", code=code),
        sheet_row("SUPERMERCADO", n.work, n.pay, date(2026, 3, 18), -40, a, "PEN", code=code),
    ]


#: Each non-zero row of `_good`: its signed cents and its account's currency.
GOOD_ROWS = {2: (-950, "PEN"), 3: (150000, "PEN"), 4: (-2025, "USD"), 6: (-6000, "PEN"),
             7: (-4000, "PEN")}  # fmt: skip


def _bad_rows(n: Names) -> list[list]:
    """Rows 8 to 10: a currency the engine does not know, an amount that is not whole
    cents, and a day after today."""
    a = n.account
    return [
        sheet_row("EURO", n.home, n.food, date(2026, 3, 19), -5, a, "EUR"),
        sheet_row("CENTIMOS", n.home, n.food, date(2026, 3, 19), -1.234, a, "PEN"),
        sheet_row("MANANA", n.home, n.food, date(2099, 3, 19), -5, a, "PEN"),
    ]


def _undo(client, runs: list[SheetImport]) -> None:
    """Deletes every transaction the runs created, then every name they created,
    best-effort."""
    for run in runs:
        for row in run.rows:
            if row.transaction_id:
                _quietly(client.delete, f"/transactions/{row.transaction_id}")
    paths = {ACCOUNT: "/accounts", CATEGORY: "/categories", HASHTAG: "/hashtags"}
    for kind in (HASHTAG, CATEGORY, ACCOUNT):
        for run in runs:
            for made in run.created:
                if made.kind == kind:
                    _quietly(client.delete, f"{paths[kind]}/{made.id}")


def _quietly(call, path: str) -> None:
    try:
        call(path)
    except EngineError:
        pass


def _ran(result: SheetImport, runs: list[SheetImport] | None = None) -> SheetImport:
    """The run, which must have gone through; kept in `runs` first, when given, so
    the cleanup reaches what it created even when it did not."""
    if runs is not None:
        runs.append(result)
    assert result.error is None, (result.stage, result.error)
    return result


def test_a_made_up_sheet_dry_run_apply_and_sent_again(client, target):
    n = Names()
    data = sheet_file(_good(n))
    runs: list[SheetImport] = []
    try:
        # The dry run without a table lists every name with its rows, creates nothing.
        before = CLEANER.holdings(client)
        dry = _ran(import_sheet(target, data, apply=False, renames={}))
        assert [(e.kind, e.name, e.currency, e.rows, e.goes, e.target_id) for e in dry.table] == [
            (ACCOUNT, n.account, "PEN", 5, Goes.NEW, None),
            (ACCOUNT, n.account, "USD", 1, Goes.NEW, None),
            (CATEGORY, n.food, None, 4, Goes.NEW, None),
            (CATEGORY, n.pay, None, 2, Goes.NEW, None),
            (HASHTAG, n.home, None, 4, Goes.NEW, None),
            (HASHTAG, n.work, None, 2, Goes.NEW, None),
        ]
        assert [(r.row, r.outcome, r.transaction_id) for r in dry.rows] == [
            (row, None, None) for row in range(2, 8)
        ]
        assert dry.created == []
        assert CLEANER.holdings(client) == before

        # The sheet's bad rows refuse it, each keyed by its row, before any name.
        bad = import_sheet(target, sheet_file(_good(n) + _bad_rows(n)), apply=False, renames={})
        assert (bad.stage, bad.answer, bad.table, bad.created) == (Stage.DRY_RUN, None, [], [])
        assert isinstance(bad.error, EngineError)
        assert_refusals(
            bad.error,
            422,
            "VALIDATION_ERROR",
            {
                "rows.8.currency": "UNEXPECTED_LAYOUT",
                "rows.9.amount_cents": "NOT_WHOLE_CENTS",
                "rows.10.date": "FUTURE_DATE",
            },
        )
        assert bad.error.fields["rows.8.currency"].startswith("Row 8:")
        assert bad.error.fields["rows.9.amount_cents"].startswith("Row 9:")
        # Row 10's FUTURE_DATE is not a rule of the sheet's own, the only messages the
        # contract says begin `Row <row>:`, so its words are not checked.
        assert CLEANER.holdings(client) == before

        # The apply creates every name, an account per currency under one name, and
        # writes every non-zero row new.
        first = _ran(import_sheet(target, data, apply=True, renames={}), runs)
        assert sorted((c.kind, c.name, c.currency) for c in first.created) == sorted(
            [
                (ACCOUNT, n.account, "PEN"),
                (ACCOUNT, n.account, "USD"),
                (CATEGORY, n.food, None),
                (CATEGORY, n.pay, None),
                (HASHTAG, n.home, None),
                (HASHTAG, n.work, None),
            ]
        )
        made = {(c.kind, c.name, c.currency): c.id for c in first.created}
        soles, dollars = made[(ACCOUNT, n.account, "PEN")], made[(ACCOUNT, n.account, "USD")]
        assert soles != dollars
        listed = client.get("/accounts", params={"include_archived": "true"})["items"]
        assert sorted(
            (a["currency_code"], a["id"]) for a in listed if a["name"] == n.account
        ) == sorted([("PEN", soles), ("USD", dollars)])

        rows = {r.row: r for r in first.rows}
        assert {row: r.outcome for row, r in rows.items()} == {
            2: "new", 3: "new", 4: "new", 5: "skipped", 6: "new", 7: "new"
        }  # fmt: skip
        assert rows[5].transaction_id is None
        assert rows[6].bank_line_id == rows[7].bank_line_id
        assert first.counts.new == 5 and first.counts.skipped == 1
        assert first.counts.split_lines == 1
        account_of = {"PEN": soles, "USD": dollars}
        for row, (cents, currency) in GOOD_ROWS.items():
            assert rows[row].transaction_id, row
            tx = read_signed(client, rows[row].transaction_id)
            assert (tx["amount_cents"], tx["account_id"]) == (cents, account_of[currency]), row
            assert tx["bank_line_id"] == rows[row].bank_line_id, row
        cafe = read_signed(client, rows[2].transaction_id)
        assert (cafe["title"], cafe["description"]) == ("CAFE", "made up")
        assert cafe["category_id"] == made[(CATEGORY, n.food, None)]
        assert cafe["hashtag_ids"] == [made[(HASHTAG, n.home, None)]]
        written = live_ids(client, soles) | live_ids(client, dollars)
        assert written == {rows[row].transaction_id for row in GOOD_ROWS}

        # Sent again: every name proposed as the one just made, nothing created,
        # every non-zero row matched on its line, nothing written.
        held = CLEANER.holdings(client)
        again = _ran(import_sheet(target, data, apply=True, renames={}), runs)
        assert again.created == []
        assert {(e.kind, e.name, e.currency): e.target_id for e in again.table} == made
        assert all(e.goes is Goes.YOURS for e in again.table)
        assert [(r.row, r.outcome, r.transaction_id, r.bank_line_id) for r in again.rows] == [
            (row, "matched", None, rows[row].bank_line_id) if row in GOOD_ROWS
            else (row, "skipped", None, None)
            for row in range(2, 8)
        ]  # fmt: skip
        assert (again.counts.new, again.counts.matched, again.counts.skipped) == (0, 5, 1)
        assert CLEANER.holdings(client) == held
        assert live_ids(client, soles) | live_ids(client, dollars) == written

        # One bad row beside a new one, a new name included: refused whole, naming
        # the row, through the module and with a full table alike; nothing written.
        new_name = f"{n.food}-new"
        one_bad = sheet_file(
            [
                *_good(n),
                sheet_row("NUEVO", n.home, new_name, date(2026, 3, 20), -7, n.account, "PEN"),
                sheet_row("CENTIMOS", n.home, n.food, date(2026, 3, 20), -1.234, n.account, "PEN"),
            ]
        )
        stopped = import_sheet(target, one_bad, apply=True, renames={})
        runs.append(stopped)
        assert (stopped.stage, stopped.answer, stopped.created) == (Stage.DRY_RUN, None, [])
        assert isinstance(stopped.error, EngineError)
        only_row_9 = {"rows.9.amount_cents": "NOT_WHOLE_CENTS"}
        assert_refusals(stopped.error, 422, "VALIDATION_ERROR", only_row_9)
        table = table_body(again.table, {})
        table["categories"].append(
            {"name": new_name, "category_id": made[(CATEGORY, n.food, None)]}
        )
        err = refused(
            lambda: client.post(
                "/transactions/import-sheet",
                json_body=request_body(one_bad, dry_run=False, names=table),
            )
        )
        assert_refusals(err, 422, "VALIDATION_ERROR", only_row_9)
        assert CLEANER.holdings(client) == held
        assert live_ids(client, soles) | live_ids(client, dollars) == written
    finally:
        _undo(client, runs)


def test_a_renamed_account_lands_under_its_rename(client, target, scratch):
    n = Names()
    fresh, onto = f"{n.account}-fresh", f"{n.account}-onto"
    renamed_to = f"contract-sheet-renamed-{uuid4().hex[:10]}"
    existing = scratch.account("PEN")
    existing_name = client.get(f"/accounts/{existing}")["name"]
    renames = {
        rename_key(fresh, "PEN"): renamed_to,
        rename_key(onto, "PEN"): existing_name,
    }
    data = sheet_file(
        [
            sheet_row("CAFE", n.home, n.food, date(2026, 4, 2), -9.5, fresh, "PEN"),
            sheet_row("TIENDA", n.home, n.food, date(2026, 4, 3), -12, onto, "PEN"),
        ]
    )
    runs: list[SheetImport] = []
    try:
        # A rename to a name you lack is created under it; one to an account you
        # have goes to it, nothing created for it; the sheet's names never are.
        first = _ran(import_sheet(target, data, apply=True, renames=renames), runs)
        table = {e.name: e for e in first.table if e.kind == ACCOUNT}
        assert (table[fresh].goes, table[fresh].ledger_name) == (Goes.NEW, renamed_to)
        assert (table[onto].goes, table[onto].target_id) == (Goes.YOURS, existing)
        accounts = [(c.name, c.currency) for c in first.created if c.kind == ACCOUNT]
        assert accounts == [(renamed_to, "PEN")]
        names = {a["name"] for a in client.get("/accounts")["items"]}
        assert renamed_to in names and fresh not in names and onto not in names

        rows = {r.row: r for r in first.rows}
        assert (rows[2].outcome, rows[3].outcome) == ("new", "new")
        created = next(c.id for c in first.created if c.kind == ACCOUNT)
        assert client.get(f"/accounts/{created}")["name"] == renamed_to
        assert read_signed(client, rows[2].transaction_id)["account_id"] == created
        assert read_signed(client, rows[3].transaction_id)["account_id"] == existing

        # Sent again with the same renames: both found under their renames, nothing
        # created, both rows matched.
        again = _ran(import_sheet(target, data, apply=True, renames=renames), runs)
        assert again.created == []
        table = {e.name: e for e in again.table if e.kind == ACCOUNT}
        assert (table[fresh].goes, table[fresh].target_id) == (Goes.YOURS, created)
        assert (table[onto].goes, table[onto].target_id) == (Goes.YOURS, existing)
        assert [r.outcome for r in again.rows] == ["matched", "matched"]
    finally:
        _undo(client, runs)
