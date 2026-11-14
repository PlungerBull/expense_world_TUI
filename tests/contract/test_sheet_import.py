"""Contract: the sheet import through the engine, run by the app's own module
(expense/import_/engine.py) on made-up sheets.

The engine reads the whole sheet, matches every row against the ledger and writes
everything or nothing (contract: POST /v1/transactions/import-sheet). It makes an account,
category or hashtag only from the `create` the request lists, all of it landing with the rows or
none of it (contract: POST /v1/transactions/import-sheet, "Create"), as the `Creation` tests
show, and answers outcomes and counts only with a table giving every name its id
(contract: POST /v1/transactions/import-sheet, "Names"): the dry run
lists the names while one is missing, the app's create step makes each category and
hashtag the caller lacks through the create routes and imports nothing, then the dry run counts
and the apply writes. The other tests make their accounts first, through the engine, and put
the sheet's names on them with `renames`, as `--account-name`
does. An account is one name whatever currencies its rows are in: the table holds one
entry for it, `{name, account_id}` with no currency, each row lands on its own currency
of it (`MONEDA`), and an account lacking one is `CURRENCY_NOT_HELD` on its entry.
A bad row refuses the whole sheet on every step, keyed by its row,
a day after today's included, before any name is created
(contract: POST /v1/transactions/import-sheet, "Rejected up front with `422`").
The counts hold `split_lines` (the `COD_EECC` values shared by rows) and `split_rows` (the
rows holding them), on the dry run and on the apply
(contract: POST /v1/transactions/import-sheet, "Response"). The same sheet sent again matches
every row and writes nothing
(contract: POST /v1/transactions/import-sheet, "Matching"). An existing person holding two
currencies gets each currency's first non-zero `SALDO INICIAL` row as its opening balance under
`@Opening`, and each later one as an ordinary row
(contract: POST /v1/transactions/import-sheet, "Opening balances").

Every name is fresh per run, so a second run of the suite still finds every row
new on its first apply: the practice user's data outlives a reseed. Each test
hands what it wrote to the `scratch` cleanup. Gating, target and the real-ledger guard: conftest.py.
"""

from copy import deepcopy
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
    bank_code,
    free_statement_codes,
    live_ids,
    next_last4,
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
    # The account is made first, holding the two currencies its rows are in, and the sheet's
    # name goes onto it by its rename.
    account = scratch.account("PEN", "USD")
    renames = {rename_key(n.account): client.get(f"/accounts/{account}")["name"]}
    # The first dry run lists every category and hashtag missing, with its rows and no outcome;
    # the account once, going to the account it is renamed to.
    before = CLEANER.holdings(client)
    dry = _ran(import_sheet(target, data, step=Step.DRY_RUN, renames=renames), scratch)
    assert [(e.kind, e.name, e.currencies, e.rows, e.goes, e.target_id) for e in dry.table] == [
        (ACCOUNT, n.account, ("PEN", "USD"), 6, Goes.YOURS, account),
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
    assert not dry.counted and len(dry.missing) == 4
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
    early = _ran(import_sheet(target, data, step=Step.APPLY, renames=renames), scratch)
    assert (early.counted, early.created, len(early.missing)) == (False, [], 4)
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
    assert CLEANER.holdings(client) == before

    # The create step creates every category and hashtag, no account, and imports nothing.
    made_run = _ran(import_sheet(target, data, step=Step.CREATE_NAMES, renames=renames), scratch)
    assert sorted((c.kind, c.name) for c in made_run.created) == sorted(
        [(CATEGORY, n.food), (CATEGORY, n.pay), (HASHTAG, n.home), (HASHTAG, n.work)]
    )
    made = {(c.kind, c.name): c.id for c in made_run.created}
    assert all(c.answer["id"] == c.id for c in made_run.created)
    assert live_ids(client, account) == set()

    # Run again, it creates nothing: every name is proposed as the one just made, the account
    # the one it is renamed to.
    again_made = _ran(import_sheet(target, data, step=Step.CREATE_NAMES, renames=renames), scratch)
    assert again_made.created == []
    assert {(e.kind, e.name): e.target_id for e in again_made.table} == {
        **made,
        (ACCOUNT, n.account): account,
    }

    # The table sent holds one entry per account name, mapped to its account, and no currency.
    sent = table_body(again_made.table)
    assert sent["accounts"] == [{"name": n.account, "account_id": account}]

    # The dry run now counts: every non-zero row new, the zero row skipped, the split one
    # line; nothing written.
    held = CLEANER.holdings(client)
    counted = _ran(import_sheet(target, data, step=Step.DRY_RUN, renames=renames), scratch)
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
    first = _ran(import_sheet(target, data, step=Step.APPLY, renames=renames), scratch)
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
    again = _ran(import_sheet(target, data, step=Step.APPLY, renames=renames), scratch)
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
    # and with a full table alike; nothing created or written.
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
        assert CLEANER.holdings(client) == held
        assert transaction_count(client, soles_only) == 0
        assert account_balance(client, soles_only) == 0
        assert client.get(f"/accounts/{soles_only}") == account_read


def test_an_existing_person_gets_its_opening_balance_in_each_currency(client, scratch):
    """The first non-zero `SALDO INICIAL` row of a currency on a person is its opening balance,
    under `@Opening` with no hashtag; each later one is an ordinary row under the category the
    table gives `SALDO INICIAL`; the sheet sent again matches all four and writes nothing
    (contract: POST /v1/transactions/import-sheet, "Opening balances"). The answer marks the
    two first rows `is_opening_balance` and counts them in `counts.opening_balances`, each row
    with its positive amount and the direction of the sign sent, the USD opening balance an outflow
    (contract: POST /v1/transactions/import-sheet, "Response"). The table maps the
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
    first = {"PEN": (date(2026, 1, 5), 100000), "USD": (date(2026, 1, 6), -25000)}
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

    def assert_openings_marked(answer: dict) -> None:
        # Rows 2 and 3 are the two currencies' first rows, rows 4 and 5 the later ones.
        assert [r["is_opening_balance"] for r in answer["rows"]] == [True, True, False, False]
        assert answer["counts"]["opening_balances"] == 2
        sent = [*first.items(), *later.items()]
        for row, (currency, (_, cents)) in zip(answer["rows"], sent, strict=True):
            assert row["currency_code"] == currency
            assert row["amount_cents"] == abs(cents)
            assert row["transaction_type"] == (1 if cents < 0 else 2)

    # The dry run counts four new rows and writes nothing, no opening balance included.
    held, total = CLEANER.holdings(client), client.get("/transactions/count")["count"]
    dry = send(dry_run=True)
    assert outcomes(dry) == ["new"] * 4 and dry["counts"]["new"] == 4
    assert_openings_marked(dry)
    assert opening_ids() == {"PEN": None, "USD": None}
    assert (CLEANER.holdings(client), client.get("/transactions/count")["count"]) == (held, total)

    applied = send(dry_run=False)
    scratch.transactions.extend(r["transaction_id"] for r in applied["rows"])
    assert outcomes(applied) == ["new"] * 4 and applied["counts"]["new"] == 4
    assert_openings_marked(applied)
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
        assert (opening["amount_cents"], opening["day"]) == (cents, day.isoformat())
        assert (opening["title"], opening["description"]) == ("SALDO", "inicial")
        day, cents = later[currency]
        ordinary = read_signed(client, by_row[4 + place])
        assert ordinary["id"] != opening_id
        assert ordinary["category_id"] == category
        assert (ordinary["account_id"], ordinary["currency_code"]) == (person, currency)
        assert (ordinary["amount_cents"], ordinary["day"]) == (cents, day.isoformat())

    # Applied again: every row matched, nothing created, the ledger unchanged.
    held, total = CLEANER.holdings(client), client.get("/transactions/count")["count"]
    written = live_ids(client, person)
    assert transaction_count(client, person) == len(written) == 4
    again = send(dry_run=False)
    assert outcomes(again) == ["matched"] * 4
    assert (again["counts"]["new"], again["counts"]["matched"]) == (0, 4)
    assert_openings_marked(again)
    assert opening_ids() == opening_by_currency
    assert (CLEANER.holdings(client), client.get("/transactions/count")["count"]) == (held, total)
    assert live_ids(client, person) == written


def test_a_zero_saldo_inicial_dated_earlier_leaves_the_first_non_zero_one_the_opening_balance(
    client, scratch
):
    """A `SALDO INICIAL` of `0.00` on 2 January never counts as a row dated before the one of
    1,000.00 on 5 January: that one is the currency's opening balance, `is_opening_balance`
    and counted in `counts.opening_balances`, the zero row `skipped` and never written
    (contract: POST /v1/transactions/import-sheet, "Opening balances")."""
    n = Names()
    person = scratch.account("PEN", person=True)
    category, hashtag = scratch.category(), scratch.hashtag()
    names = {
        "accounts": [{"name": n.account, "account_id": person}],
        "categories": [{"name": "SALDO INICIAL", "category_id": category}],
        "hashtags": [{"name": n.home, "hashtag_id": hashtag}],
    }
    data = sheet_file(
        [
            sheet_row("CERO", n.home, "SALDO INICIAL", date(2026, 1, 2), 0, n.account, "PEN"),
            sheet_row("SALDO", n.home, "SALDO INICIAL", date(2026, 1, 5), 1000, n.account, "PEN"),
        ]
    )
    for dry_run in (True, False):
        answer = client.post(
            "/transactions/import-sheet",
            json_body=request_body(data, dry_run=dry_run, names=names),
        )
        scratch.transactions.extend(
            r["transaction_id"] for r in answer["rows"] if r["transaction_id"]
        )
        assert [r["outcome"] for r in answer["rows"]] == ["skipped", "new"]
        assert [r["is_opening_balance"] for r in answer["rows"]] == [False, True]
        assert answer["counts"]["opening_balances"] == 1
    opening = next(c for c in client.get(f"/accounts/{person}")["currencies"])
    assert opening["opening_balance_transaction_id"] == answer["rows"][1]["transaction_id"]
    read = read_signed(client, opening["opening_balance_transaction_id"])
    assert (read["amount_cents"], read["day"]) == (100000, "2026-01-05")
    assert client.get(f"/categories/{read['category_id']}")["system_key"] == "opening_balance"
    assert transaction_count(client, person) == 1


def test_two_sheet_names_renamed_onto_two_accounts_land_each_on_its_own(client, target, scratch):
    n = Names()
    left_sheet, right_sheet = f"{n.account}-left", f"{n.account}-right"
    left, right = scratch.account("PEN"), scratch.account("PEN")
    left_name = client.get(f"/accounts/{left}")["name"]
    right_name = client.get(f"/accounts/{right}")["name"]
    renames = {rename_key(left_sheet): left_name, rename_key(right_sheet): right_name}
    data = sheet_file(
        [
            sheet_row("CAFE", n.home, n.food, date(2026, 4, 2), -9.5, left_sheet, "PEN"),
            sheet_row("TIENDA", n.home, n.food, date(2026, 4, 3), -12, right_sheet, "PEN"),
        ]
    )
    # Each rename goes to the account of that name; the create step makes the category and
    # hashtag only, never an account, the sheet's names included.
    names = _ran(import_sheet(target, data, step=Step.CREATE_NAMES, renames=renames), scratch)
    table = {e.name: e for e in names.table if e.kind == ACCOUNT}
    assert (table[left_sheet].goes, table[left_sheet].target_id) == (Goes.YOURS, left)
    assert (table[right_sheet].goes, table[right_sheet].target_id) == (Goes.YOURS, right)
    assert table[left_sheet].renamed_to == left_name
    assert [(c.kind, c.name) for c in names.created] == [(CATEGORY, n.food), (HASHTAG, n.home)]
    listed = {a["name"] for a in client.get("/accounts")["items"]}
    assert {left_name, right_name} <= listed
    assert left_sheet not in listed and right_sheet not in listed

    first = _ran(import_sheet(target, data, step=Step.APPLY, renames=renames), scratch)
    rows = {r.row: r for r in first.rows}
    assert [rows[row].outcome for row in (2, 3)] == ["new", "new"]
    assert read_signed(client, rows[2].transaction_id)["account_id"] == left
    assert read_signed(client, rows[3].transaction_id)["account_id"] == right


class Creation:
    """What one `create` makes and the sheet that uses it: a bank account holding soles and
    dollars, a person, a cash account and an archived bank account, two categories and two
    hashtags, each under a client-generated id the `names` table gives its sheet name."""

    def __init__(self, scratch) -> None:
        n = self.names = Names()
        code, self.last4, self.archived_last4 = bank_code(), next_last4(), next_last4()
        self.bank_name = f"{code}-{self.last4}"
        self.archived_name = f"{code}-{self.archived_last4}"
        self.person_name = f"{n.account}-person"
        self.cash_name = f"{n.account}-cash"
        self.bank, self.person, self.cash, self.archived = (str(uuid4()) for _ in range(4))
        self.food, self.pay, self.home, self.work = (str(uuid4()) for _ in range(4))
        scratch.accounts += [self.bank, self.person, self.cash, self.archived]
        scratch.categories += [self.food, self.pay]
        scratch.hashtags += [self.home, self.work]
        self.create = {
            "accounts": [
                {"id": self.bank, "kind": "bank", "bank_code": code, "last4": self.last4,
                 "currencies": ["PEN", "USD"]},
                {"id": self.person, "kind": "person", "name": self.person_name,
                 "currencies": ["PEN"]},
                {"id": self.cash, "kind": "cash", "currencies": ["PEN"]},
                {"id": self.archived, "kind": "bank", "bank_code": code,
                 "last4": self.archived_last4, "currencies": ["PEN"], "archived": True},
            ],
            "categories": [{"id": self.food, "name": n.food}, {"id": self.pay, "name": n.pay}],
            "hashtags": [{"id": self.home, "name": n.home}, {"id": self.work, "name": n.work}],
        }  # fmt: skip
        self.table = {
            "accounts": [
                {"name": self.bank_name, "account_id": self.bank},
                {"name": self.person_name, "account_id": self.person},
                {"name": self.cash_name, "account_id": self.cash},
                {"name": self.archived_name, "account_id": self.archived},
            ],
            "categories": [
                {"name": n.food, "category_id": self.food},
                {"name": n.pay, "category_id": self.pay},
            ],
            "hashtags": [
                {"name": n.home, "hashtag_id": self.home},
                {"name": n.work, "hashtag_id": self.work},
            ],
        }  # fmt: skip
        #: Each row's account id and signed cents, by currency, in sheet order (rows 2 to 9).
        self.rows = [
            (self.bank, "PEN", -950), (self.bank, "PEN", 2000), (self.bank, "USD", -2025),
            (self.person, "PEN", 30000), (self.person, "PEN", -1500),
            (self.cash, "PEN", -400),
            (self.archived, "PEN", -750), (self.archived, "PEN", 10000),
        ]  # fmt: skip

    def sheet(self, *extra: list) -> bytes:
        """The sheet of `rows`; the person's first row is its `SALDO INICIAL`, its currency's
        opening balance, which needs no category in the table."""
        n, name = self.names, {
            self.bank: self.bank_name,
            self.person: self.person_name,
            self.cash: self.cash_name,
            self.archived: self.archived_name,
        }  # fmt: skip
        kinds = [(n.home, n.food), (n.work, n.pay)]
        rows = []
        for place, (account, currency, cents) in enumerate(self.rows):
            hashtag, category = kinds[place % 2]
            if place == 3:
                category = "SALDO INICIAL"
            day = date(2026, 1, 5) if place == 3 else date(2026, 3, 10 + place)
            rows.append(
                sheet_row(
                    "MOVIMIENTO", hashtag, category, day, cents / 100, name[account], currency
                )
            )
        return sheet_file([*rows, *extra])

    def body(self, data: bytes, *, dry_run: bool) -> dict:
        return {**request_body(data, dry_run=dry_run, names=self.table), "create": self.create}


def test_one_apply_with_create_makes_the_accounts_names_and_rows(client, scratch):
    """`create` makes a bank account, a person, a cash account and an archived one, with
    two categories and two hashtags, each under the client's id, which `names` points at:
    `created` counts them on the dry run, which makes none, and on the apply, whose
    rows land on them, each currency's balance their rows' sum, the archived account archived,
    and the person's first `SALDO INICIAL` its currency's opening balance
    (contract: POST /v1/transactions/import-sheet, "Create")
    (contract: POST /v1/transactions/import-sheet, "Response")."""
    made = Creation(scratch)
    data = made.sheet()
    counted = {"accounts": 4, "categories": 2, "hashtags": 2}
    held, total = CLEANER.holdings(client), client.get("/transactions/count")["count"]

    dry = client.post("/transactions/import-sheet", json_body=made.body(data, dry_run=True))
    assert dry["created"] == counted
    assert {r["outcome"] for r in dry["rows"]} == {"new"} and dry["counts"]["new"] == 8
    assert all(r["transaction_id"] is None for r in dry["rows"])
    assert (CLEANER.holdings(client), client.get("/transactions/count")["count"]) == (held, total)

    applied = client.post("/transactions/import-sheet", json_body=made.body(data, dry_run=False))
    scratch.transactions.extend(r["transaction_id"] for r in applied["rows"])
    assert applied["created"] == counted
    assert [r["outcome"] for r in applied["rows"]] == ["new"] * 8
    assert [r["account_id"] for r in applied["rows"]] == [a for a, _, _ in made.rows]
    made_ids = set(CLEANER.holdings(client)) - set(held)
    assert made_ids == {made.bank, made.person, made.cash, made.archived, made.food, made.pay,
                        made.home, made.work}  # fmt: skip

    for account in (made.bank, made.person, made.cash, made.archived):
        for currency in {c for a, c, _ in made.rows if a == account}:
            expected = sum(c for a, cur, c in made.rows if (a, cur) == (account, currency))
            assert account_balance(client, account, currency) == expected, (account, currency)
        assert client.get(f"/accounts/{account}")["is_archived"] is (account == made.archived)
    person = client.get(f"/accounts/{made.person}")["currencies"][0]
    assert person["opening_balance_transaction_id"] == applied["rows"][3]["transaction_id"]


def test_a_refused_create_or_row_leaves_nothing_made(client, scratch):
    """A made thing's refusal under its own route's rules and a row's refusal each answer
    keyed as the contract gives and make nothing, on the dry run and the apply alike: no
    account, category, hashtag or row
    (contract: POST /v1/transactions/import-sheet, "Create")
    (contract: POST /v1/transactions/import-sheet, "Rejected up front with `422`")."""
    made = Creation(scratch)
    data = made.sheet()
    statement_code = free_statement_codes(client, 1)[0]
    two_hashtags = deepcopy(made.create)
    two_hashtags["hashtags"][1]["name"] = made.names.home
    same_code = deepcopy(made.create)
    same_code["accounts"][0]["statement_code"] = same_code["accounts"][3]["statement_code"] = (
        statement_code
    )
    bad_currency = deepcopy(made.create)
    bad_currency["accounts"][1]["currencies"] = ["PEN", "EUR"]
    bad_row = sheet_row(
        "EURO", made.names.home, made.names.food, date(2026, 3, 19), -5, made.bank_name, "EUR"
    )
    invalid, conflict = "VALIDATION_ERROR", "CONFLICT"
    currency_key = "create.accounts.1.currencies.1.currency_code"
    cases = [
        (data, two_hashtags, 409, conflict, "create.hashtags.1.name", "NAME_EXISTS"),
        (
            data,
            same_code,
            409,
            conflict,
            "create.accounts.3.statement_code",
            "STATEMENT_CODE_EXISTS",
        ),
        (data, bad_currency, 422, invalid, currency_key, "UNSUPPORTED_VALUE"),
        (made.sheet(bad_row), made.create, 422, invalid, "rows.10.currency", "UNEXPECTED_LAYOUT"),
    ]
    held, total = CLEANER.holdings(client), client.get("/transactions/count")["count"]
    for sheet, create, status, error_code, key, reason in cases:
        for dry_run in (True, False):
            body = {**made.body(sheet, dry_run=dry_run), "create": create}
            err = refused(
                lambda body=body: client.post("/transactions/import-sheet", json_body=body)
            )
            assert_refusal(err, status, error_code, key, reason)
            assert (CLEANER.holdings(client), client.get("/transactions/count")["count"]) == (
                held,
                total,
            ), (key, dry_run)


def test_a_suggestion_is_null_beside_a_proposal_and_otherwise_follows_the_rules(client, scratch):
    """An account the ledger holds is proposed and has no suggestion; a name it does not is
    suggested by the published rules, on the name as the sheet writes it: the bank code a first
    word the bank list holds (with the last 4 digits taken off its end), the last 4 the one run
    of exactly four digits, none when the name holds two; `Interbank PEN` gives nothing
    (contract: POST /v1/transactions/import-sheet, "Names")."""
    code = bank_code()
    held = scratch.account("PEN")
    held_name = client.get(f"/accounts/{held}")["name"]
    sheet_names = [held_name, f"{code} 5678", f"{code}5678", "Interbank PEN", f"{code} 1234 5678"]
    day = date(2026, 3, 14)
    data = sheet_file(
        [
            sheet_row("CAFE", "contract-sheet-h", "contract-sheet-c", day, -1, name, "PEN")
            for name in sheet_names
        ]
    )
    answer = client.post("/transactions/import-sheet", json_body=request_body(data, dry_run=True))
    listed = {a["name"]: a for a in answer["names"]["accounts"]}
    assert (listed[held_name]["proposed_id"], listed[held_name]["suggestion"]) == (held, None)
    suggested = {name: a["suggestion"] for name, a in listed.items() if name != held_name}
    assert suggested == {
        f"{code} 5678": {"kind": "bank", "bank_code": code, "last4": "5678", "currencies": ["PEN"]},
        f"{code}5678": {"kind": "bank", "bank_code": code, "last4": "5678", "currencies": ["PEN"]},
        "Interbank PEN": {"kind": None, "bank_code": None, "last4": None, "currencies": ["PEN"]},
        f"{code} 1234 5678": {
            "kind": "bank",
            "bank_code": code,
            "last4": None,
            "currencies": ["PEN"],
        },
    }
    assert all(listed[name]["proposed_id"] is None for name in suggested)
