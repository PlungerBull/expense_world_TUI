"""Contract: the sheet import through the engine, run by the app's own module
(expense/import_/engine.py) on made-up sheets.

The engine reads the whole sheet, matches every row against the ledger and writes
everything or nothing (contract: POST /v1/transactions/import-sheet). It never
creates a name, and answers outcomes and counts only with a table giving every
name its id (contract: POST /v1/transactions/import-sheet, "Names"): the dry run
lists the names while one is missing, the create step creates each one the
caller lacks and imports nothing, then the dry run counts and the apply writes.
An account is one name whatever currencies its rows are in: the table holds one
entry for it, `{name, account_id}` with no currency, the create step makes one
account holding every currency its rows use, each row lands on its own currency
of it (`MONEDA`), and an account lacking one is `CURRENCY_NOT_HELD` on its entry.
A bad row refuses the whole sheet on every step, keyed by its row, its message
naming the row, a day after today's included, before any name is created
(contract: POST /v1/transactions/import-sheet, "Rejected up front with `422`").
The counts hold `split_lines` (the `COD_EECC` values shared by rows) and `split_rows` (the
rows holding them), on the dry run and on the apply. The same sheet sent again matches
every row and writes nothing
(contract: POST /v1/transactions/import-sheet, "Matching"). An existing person holding two
currencies gets each currency's first non-zero `SALDO INICIAL` row as its opening balance under
`@Opening`, and each later one as an ordinary row
(contract: POST /v1/transactions/import-sheet, "Opening balances").

Every name is fresh per run, so a second run of the suite still finds every row
new on its first apply: the practice user's data outlives a reseed. Each test
hands what it wrote to the `scratch` cleanup. Gating, target and the real-ledger guard: conftest.py.
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
    Step,
    import_sheet,
    rename_key,
    request_body,
    table_body,
)
from tests.contract.conftest import (
    CLEANER,
    account_balance,
    assert_refusal,
    assert_refusals,
    live_ids,
    read_signed,
    refused,
    sheet_file,
    sheet_row,
    transaction_count,
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
    """Rows 2 to 7: two soles rows, a dollar row under the same account name, a soles row
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


#: Each non-zero row of `_good`: its signed cents and its currency (`MONEDA`).
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


def _keep(scratch, run: SheetImport) -> SheetImport:
    """The run's records joined to the scratch, so its cleanup deletes every transaction the
    run created and every name its create step created, whatever the test finds after."""
    owner = {ACCOUNT: scratch.accounts, CATEGORY: scratch.categories, HASHTAG: scratch.hashtags}
    for made in run.created:
        owner[made.kind].append(made.id)
    scratch.transactions.extend(r.transaction_id for r in run.rows if r.transaction_id)
    return run


def _ran(result: SheetImport, scratch) -> SheetImport:
    """The run, which must have gone through; kept in the scratch first, so the cleanup
    reaches what it created even when it did not."""
    _keep(scratch, result)
    assert result.error is None, (result.stage, result.error)
    return result


def _refused_on_every_step(target, data: bytes, scratch) -> list[SheetImport]:
    """The sheet sent as each step: every one refused at its first dry run,
    nothing created."""
    out = []
    for step in Step:
        stopped = _keep(scratch, import_sheet(target, data, step=step, renames={}))
        assert (stopped.stage, stopped.answer, stopped.table, stopped.created) == (
            Stage.NAMES,
            None,
            [],
            [],
        ), step
        assert isinstance(stopped.error, EngineError), step
        out.append(stopped)
    return out


def test_a_made_up_sheet_from_names_to_apply_and_sent_again(client, target, scratch):
    n = Names()
    data = sheet_file(_good(n))
    # The first dry run lists every name missing, with its rows and no outcome: the account
    # once, holding the two currencies its rows are in.
    before = CLEANER.holdings(client)
    dry = _ran(import_sheet(target, data, step=Step.DRY_RUN, renames={}), scratch)
    assert [(e.kind, e.name, e.currencies, e.rows, e.goes, e.target_id) for e in dry.table] == [
        (ACCOUNT, n.account, ("PEN", "USD"), 6, Goes.MISSING, None),
        (CATEGORY, n.food, (), 4, Goes.MISSING, None),
        (CATEGORY, n.pay, (), 2, Goes.MISSING, None),
        (HASHTAG, n.home, (), 4, Goes.MISSING, None),
        (HASHTAG, n.work, (), 2, Goes.MISSING, None),
    ]
    (listed,) = dry.answer["names"]["accounts"]
    assert (listed["name"], listed["currencies"], listed["proposed_id"]) == (
        n.account,
        ["PEN", "USD"],
        None,
    )
    assert not dry.counted and len(dry.missing) == 5
    assert [(r.row, r.outcome, r.transaction_id) for r in dry.rows] == [
        (row, None, None) for row in range(2, 8)
    ]
    # each row reads its own currency on every answer; its account only with the table
    assert [(r["row"], r["account_id"], r["currency_code"]) for r in dry.answer["rows"]] == [
        (2, None, "PEN"),
        (3, None, "PEN"),
        (4, None, "USD"),
        (5, None, "PEN"),
        (6, None, "PEN"),
        (7, None, "PEN"),
    ]
    assert dry.created == []

    # The apply while names are missing sends nothing more.
    early = _ran(import_sheet(target, data, step=Step.APPLY, renames={}), scratch)
    assert (early.counted, early.created, len(early.missing)) == (False, [], 5)
    assert all(r.transaction_id is None for r in early.rows)
    assert CLEANER.holdings(client) == before

    # The sheet's bad rows refuse every step, each keyed by its row, before any name.
    bad = sheet_file(_good(n) + _bad_rows(n))
    for stopped in _refused_on_every_step(target, bad, scratch):
        assert_refusals(
            stopped.error,
            422,
            "VALIDATION_ERROR",
            {
                "rows.8.currency": "UNEXPECTED_LAYOUT",
                "rows.9.amount_cents": "NOT_WHOLE_CENTS",
                "rows.10.date": "FUTURE_DATE",
            },
        )
        assert stopped.error.fields["rows.8.currency"].startswith("Row 8:")
        assert stopped.error.fields["rows.9.amount_cents"].startswith("Row 9:")
        # A day after today names its row in the engine's words
        # (contract: POST /v1/transactions/import-sheet, "Rejected up front with `422`").
        assert stopped.error.fields["rows.10.date"] == "Row 10: Must not be in the future."
    assert CLEANER.holdings(client) == before

    # The create step creates every name, one account holding both currencies under the
    # name, and imports nothing.
    made_run = _ran(import_sheet(target, data, step=Step.CREATE_NAMES, renames={}), scratch)
    assert sorted((c.kind, c.name, c.currencies) for c in made_run.created) == sorted(
        [
            (ACCOUNT, n.account, ("PEN", "USD")),
            (CATEGORY, n.food, ()),
            (CATEGORY, n.pay, ()),
            (HASHTAG, n.home, ()),
            (HASHTAG, n.work, ()),
        ]
    )
    made = {(c.kind, c.name): c.id for c in made_run.created}
    assert all(c.answer["id"] == c.id for c in made_run.created)
    account = made[(ACCOUNT, n.account)]
    held = client.get("/accounts", params={"include_archived": "true"})["items"]
    (only,) = [a for a in held if a["name"] == n.account]
    assert only["id"] == account
    assert sorted(c["currency_code"] for c in only["currencies"]) == ["PEN", "USD"]
    assert live_ids(client, account) == set()

    # Run again, it creates nothing: every name is proposed as the one just made.
    again_made = _ran(import_sheet(target, data, step=Step.CREATE_NAMES, renames={}), scratch)
    assert again_made.created == []
    assert {(e.kind, e.name): e.target_id for e in again_made.table} == made

    # The table sent holds one entry per account name, mapped to its account, and no currency.
    sent = table_body(again_made.table)
    assert sent["accounts"] == [{"name": n.account, "account_id": account}]

    # The dry run now counts: every non-zero row new, the zero row skipped, the split one
    # line; nothing written.
    held = CLEANER.holdings(client)
    counted = _ran(import_sheet(target, data, step=Step.DRY_RUN, renames={}), scratch)
    assert counted.counted and counted.missing == []
    assert {r.row: r.outcome for r in counted.rows} == {
        2: "new", 3: "new", 4: "new", 5: "skipped", 6: "new", 7: "new"
    }  # fmt: skip
    assert all(r.transaction_id is None for r in counted.rows)
    assert (counted.counts.new, counted.counts.skipped, counted.counts.split_lines) == (5, 1, 1)
    # the one split line comes from rows 6 and 7
    assert counted.counts.split_rows == 2
    assert CLEANER.holdings(client) == held
    assert live_ids(client, account) == set()

    # The apply writes every non-zero row new. A table carrying a `currency_code` on an
    # account would be refused whole (`UNKNOWN_FIELD`), so a run that goes through sent none.
    first = _ran(import_sheet(target, data, step=Step.APPLY, renames={}), scratch)
    assert first.created == []
    rows = {r.row: r for r in first.rows}
    assert {row: r.outcome for row, r in rows.items()} == {
        2: "new", 3: "new", 4: "new", 5: "skipped", 6: "new", 7: "new"
    }  # fmt: skip
    assert rows[5].transaction_id is None
    assert rows[6].bank_line_id == rows[7].bank_line_id
    assert first.counts.new == 5 and first.counts.skipped == 1
    assert (first.counts.split_lines, first.counts.split_rows) == (1, 2)
    # every answer row reads the account the table gave it and the currency of its MONEDA
    assert [(r["row"], r["account_id"], r["currency_code"]) for r in first.answer["rows"]] == [
        (row, account, currency)
        for row, currency in zip(
            range(2, 8), ("PEN", "PEN", "USD", "PEN", "PEN", "PEN"), strict=True
        )
    ]
    for row, (cents, currency) in GOOD_ROWS.items():
        assert rows[row].transaction_id, row
        tx = read_signed(client, rows[row].transaction_id)
        assert (tx["amount_cents"], tx["account_id"], tx["currency_code"]) == (
            cents,
            account,
            currency,
        ), row
        assert tx["bank_line_id"] == rows[row].bank_line_id, row
    cafe = read_signed(client, rows[2].transaction_id)
    assert (cafe["title"], cafe["description"]) == ("CAFE", "made up")
    assert cafe["category_id"] == made[(CATEGORY, n.food)]
    assert cafe["hashtag_ids"] == [made[(HASHTAG, n.home)]]
    written = live_ids(client, account)
    assert written == {rows[row].transaction_id for row in GOOD_ROWS}
    assert account_balance(client, account, "PEN") == -950 + 150000 - 6000 - 4000
    assert account_balance(client, account, "USD") == -2025

    # Applied again: nothing created, every non-zero row matched on its line, nothing written.
    held = CLEANER.holdings(client)
    again = _ran(import_sheet(target, data, step=Step.APPLY, renames={}), scratch)
    assert again.created == []
    assert all(e.goes is Goes.YOURS for e in again.table)
    assert [(r.row, r.outcome, r.transaction_id, r.bank_line_id) for r in again.rows] == [
        (row, "matched", None, rows[row].bank_line_id) if row in GOOD_ROWS
        else (row, "skipped", None, None)
        for row in range(2, 8)
    ]  # fmt: skip
    assert (again.counts.new, again.counts.matched, again.counts.skipped) == (0, 5, 1)
    assert CLEANER.holdings(client) == held
    assert live_ids(client, account) == written

    # One bad row beside a new one, a new name included: refused whole on every step,
    # naming the row, and with a full table alike; nothing created or written.
    new_name = f"{n.food}-new"
    one_bad = sheet_file(
        [
            *_good(n),
            sheet_row("NUEVO", n.home, new_name, date(2026, 3, 20), -7, n.account, "PEN"),
            sheet_row("CENTIMOS", n.home, n.food, date(2026, 3, 20), -1.234, n.account, "PEN"),
        ]
    )
    only_row_9 = {"rows.9.amount_cents": "NOT_WHOLE_CENTS"}
    for stopped in _refused_on_every_step(target, one_bad, scratch):
        assert_refusals(stopped.error, 422, "VALIDATION_ERROR", only_row_9)
    table = table_body(again.table)
    table["categories"].append({"name": new_name, "category_id": made[(CATEGORY, n.food)]})
    err = refused(
        lambda: client.post(
            "/transactions/import-sheet",
            json_body=request_body(one_bad, dry_run=False, names=table),
        )
    )
    assert_refusals(err, 422, "VALIDATION_ERROR", only_row_9)
    assert CLEANER.holdings(client) == held
    assert live_ids(client, account) == written


def test_an_account_lacking_a_currency_of_its_rows_is_refused_on_its_entry(client, target, scratch):
    """A name whose rows are in soles and dollars, sent to an account holding soles only, is
    `CURRENCY_NOT_HELD` on `names.accounts.<i>.account_id`, `<i>` its place in the table, on the
    dry run with the table and the apply, nothing written (contract:
    POST /v1/transactions/import-sheet, "Names")."""
    n = Names()
    soles_only = scratch.account("PEN")
    soles_name = client.get(f"/accounts/{soles_only}")["name"]
    ok, short = f"{n.account}-ok", f"{n.account}-short"
    renames = {rename_key(ok): soles_name, rename_key(short): soles_name}
    data = sheet_file(
        [
            sheet_row("CAFE", n.home, n.food, date(2026, 4, 2), -9.5, ok, "PEN"),
            sheet_row("TIENDA", n.home, n.food, date(2026, 4, 3), -12, short, "PEN"),
            sheet_row("DOLARES", n.home, n.food, date(2026, 4, 4), -3, short, "USD"),
        ]
    )
    # the category and the hashtag are made first: the table is sent only with every name
    made = _ran(import_sheet(target, data, step=Step.CREATE_NAMES, renames=renames), scratch)
    assert [(c.kind, c.name) for c in made.created] == [(CATEGORY, n.food), (HASHTAG, n.home)]
    held = CLEANER.holdings(client)
    account_read = client.get(f"/accounts/{soles_only}")
    for step in (Step.DRY_RUN, Step.APPLY):
        stopped = _keep(scratch, import_sheet(target, data, step=step, renames=renames))
        assert stopped.stage is (Stage.COUNTS if step is Step.DRY_RUN else Stage.APPLY)
        assert [e.target_id for e in stopped.table if e.kind == ACCOUNT] == [soles_only] * 2
        assert isinstance(stopped.error, EngineError)
        assert_refusal(
            stopped.error,
            422,
            "VALIDATION_ERROR",
            "names.accounts.1.account_id",
            "CURRENCY_NOT_HELD",
        )
        assert stopped.error.fields["names.accounts.1.account_id"] == "The account holds no USD."
        assert CLEANER.holdings(client) == held
        assert transaction_count(client, soles_only) == 0
        assert account_balance(client, soles_only) == 0
        assert client.get(f"/accounts/{soles_only}") == account_read


def test_an_existing_person_gets_its_opening_balance_in_each_currency(client, scratch):
    """The first non-zero `SALDO INICIAL` row of a currency on a person is its opening balance,
    under `@Opening` with no hashtag; each later one is an ordinary row under the category the
    table gives `SALDO INICIAL`; the sheet sent again matches all four and writes nothing
    (contract: POST /v1/transactions/import-sheet, "Opening balances"). The table maps the
    sheet's names to a fresh category and hashtag of the scratch, so nothing fixed-named is
    created."""
    n = Names()
    person = scratch.account("PEN", "USD", person=True)
    category, hashtag = scratch.category(), scratch.hashtag()
    names = {
        "accounts": [{"name": n.account, "account_id": person}],
        "categories": [{"name": "SALDO INICIAL", "category_id": category}],
        "hashtags": [{"name": n.home, "hashtag_id": hashtag}],
    }
    first = {"PEN": (date(2026, 1, 5), 100000), "USD": (date(2026, 1, 6), 25000)}
    later = {"PEN": (date(2026, 2, 1), 30000), "USD": (date(2026, 2, 2), -4000)}
    data = sheet_file(
        [
            sheet_row(
                "SALDO",
                n.home,
                "SALDO INICIAL",
                day,
                cents / 100,
                n.account,
                currency,
                note="inicial",
            )  # fmt: skip
            for rows in (first, later)
            for currency, (day, cents) in rows.items()
        ]
    )

    def send(*, dry_run: bool) -> dict:
        body = request_body(data, dry_run=dry_run, names=names)
        return client.post("/transactions/import-sheet", json_body=body)

    def opening_ids() -> dict[str, str | None]:
        return {
            e["currency_code"]: e["opening_balance_transaction_id"]
            for e in client.get(f"/accounts/{person}")["currencies"]
        }

    def outcomes(answer: dict) -> list[str]:
        return [r["outcome"] for r in answer["rows"]]

    # The dry run counts four new rows and writes nothing, no opening balance included.
    held, total = CLEANER.holdings(client), client.get("/transactions/count")["count"]
    dry = send(dry_run=True)
    assert outcomes(dry) == ["new"] * 4 and dry["counts"]["new"] == 4
    assert opening_ids() == {"PEN": None, "USD": None}
    assert (CLEANER.holdings(client), client.get("/transactions/count")["count"]) == (held, total)

    applied = send(dry_run=False)
    scratch.transactions.extend(r["transaction_id"] for r in applied["rows"])
    assert outcomes(applied) == ["new"] * 4 and applied["counts"]["new"] == 4
    by_row = {r["row"]: r["transaction_id"] for r in applied["rows"]}
    opening_by_currency = opening_ids()
    for place, currency in enumerate(first):
        day, cents = first[currency]
        opening_id = opening_by_currency[currency]
        assert opening_id == by_row[2 + place]
        opening = read_signed(client, opening_id)
        assert client.get(f"/categories/{opening['category_id']}")["system_key"] == (
            "opening_balance"
        )
        assert opening["hashtag_ids"] == []
        assert (opening["account_id"], opening["currency_code"]) == (person, currency)
        assert (opening["amount_cents"], opening["date"][:10]) == (cents, day.isoformat())
        assert (opening["title"], opening["description"]) == ("SALDO", "inicial")
        day, cents = later[currency]
        ordinary = read_signed(client, by_row[4 + place])
        assert ordinary["id"] != opening_id
        assert ordinary["category_id"] == category
        assert (ordinary["account_id"], ordinary["currency_code"]) == (person, currency)
        assert (ordinary["amount_cents"], ordinary["date"][:10]) == (cents, day.isoformat())

    # Applied again: every row matched, nothing created, the ledger unchanged.
    held, total = CLEANER.holdings(client), client.get("/transactions/count")["count"]
    written = live_ids(client, person)
    assert transaction_count(client, person) == len(written) == 4
    again = send(dry_run=False)
    assert outcomes(again) == ["matched"] * 4
    assert (again["counts"]["new"], again["counts"]["matched"]) == (0, 4)
    assert opening_ids() == opening_by_currency
    assert (CLEANER.holdings(client), client.get("/transactions/count")["count"]) == (held, total)
    assert live_ids(client, person) == written


def test_a_renamed_account_lands_under_its_rename(client, target, scratch):
    n = Names()
    fresh, onto = f"{n.account}-fresh", f"{n.account}-onto"
    renamed_to = f"contract-sheet-renamed-{uuid4().hex[:10]}"
    existing = scratch.account("PEN")
    existing_name = client.get(f"/accounts/{existing}")["name"]
    renames = {rename_key(fresh): renamed_to, rename_key(onto): existing_name}
    data = sheet_file(
        [
            sheet_row("CAFE", n.home, n.food, date(2026, 4, 2), -9.5, fresh, "PEN"),
            sheet_row("TIENDA", n.home, n.food, date(2026, 4, 3), -12, onto, "PEN"),
            sheet_row("DOLARES", n.home, n.food, date(2026, 4, 4), -3, fresh, "USD"),
        ]
    )
    # A rename to a name you lack is created under it, holding the currencies its rows are
    # in; one to an account you have goes to it, nothing created for it; the sheet's names
    # never are.
    names = _ran(import_sheet(target, data, step=Step.CREATE_NAMES, renames=renames), scratch)
    table = {e.name: e for e in names.table if e.kind == ACCOUNT}
    assert (table[fresh].goes, table[fresh].ledger_name) == (Goes.MISSING, renamed_to)
    assert (table[onto].goes, table[onto].target_id) == (Goes.YOURS, existing)
    accounts = [(c.name, c.currencies) for c in names.created if c.kind == ACCOUNT]
    assert accounts == [(renamed_to, ("PEN", "USD"))]
    listed = {a["name"] for a in client.get("/accounts")["items"]}
    assert renamed_to in listed and fresh not in listed and onto not in listed

    created = next(c.id for c in names.created if c.kind == ACCOUNT)
    first = _ran(import_sheet(target, data, step=Step.APPLY, renames=renames), scratch)
    table = {e.name: e for e in first.table if e.kind == ACCOUNT}
    assert (table[fresh].goes, table[fresh].target_id) == (Goes.YOURS, created)
    rows = {r.row: r for r in first.rows}
    assert [rows[row].outcome for row in (2, 3, 4)] == ["new", "new", "new"]
    assert client.get(f"/accounts/{created}")["name"] == renamed_to
    assert read_signed(client, rows[2].transaction_id)["account_id"] == created
    assert read_signed(client, rows[3].transaction_id)["account_id"] == existing
    dollars = read_signed(client, rows[4].transaction_id)
    assert (dollars["account_id"], dollars["currency_code"]) == (created, "USD")

    # Applied again with the same renames: both found under their renames, every row matched.
    again = _ran(import_sheet(target, data, step=Step.APPLY, renames=renames), scratch)
    table = {e.name: e for e in again.table if e.kind == ACCOUNT}
    assert (table[fresh].goes, table[fresh].target_id) == (Goes.YOURS, created)
    assert (table[onto].goes, table[onto].target_id) == (Goes.YOURS, existing)
    assert [r.outcome for r in again.rows] == ["matched", "matched", "matched"]
