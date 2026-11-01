"""Contract: a statement's order, which only the bank's paper sets, and the statement line it
builds.

An account with a statement code has, for each statement, an order: its lines numbered top to
bottom as the bank's paper numbers them, all the account's currencies in one numbering, an
empty slot for a paper row the ledger lacks. The upload of the bank's PDF
(`POST /statements/import`) sets it and no route writes it; completing needs it, and a
completed line reads `<CODE>-<YYYYMM>-<NNN>` (contract: "Statements", "A statement's order").
No screen calls `GET /statements/{id}/statement-order`, and the live suite exercises the
engine features with no screen (CLAUDE.md "Product scope and role"), so this pins what it
reads and refuses. Every paper here is made up by the test (`savings_paper`, `card_paper`).
Pinned here:

  · the upload sets the order and the read gives it back: the places in paper order, an
    empty slot `null`, each line exactly as `GET /bank-lines/{id}` reads it with its
    `statement_place`, the statement reading no line unplaced and no place shared;
  · a card's soles and dollar rows take one numbering in paper order, each place tied to
    its row by amount, which neither the rows' dates nor a grouping by currency could produce;
    the lines assigned after the upload are unplaced, the opening balance among them, oldest
    first with the currencies mixed by date and lines tied on a day in the order they were
    made, and the opening balance never counts in `unplaced_count`;
  · the statement's lines list in its order (`GET /bank-lines?statement_id=&sort=statement`):
    placed lines by place, then the rest oldest first, one currency's with gaps in its
    places, paged by a cursor bound to the order, `INVALID_CURSOR` across the three orders,
    `INVALID_FORMAT` for any other `sort`, no `sort` on the count, an account without a code
    listing oldest first;
  · completing is `422` `STATEMENT_NOT_ORDERED` on `statement_order` while a line holds no
    place, and the paper uploaded again settles it, taking out the line it does not print;
  · the statement line is built on completion on the line and every part, `null` on a revert
    with the place kept, back when the paper completes it again, and follows a change or a
    clearing of the account's code;
  · the read is `404` for no live statement, `422` `INVALID_FORMAT` for a non-UUID,
    `409` `NO_STATEMENT_CODE` on an account without a code, whose statements complete without
    an order and read `null` counts; no body written to a statement sets a place.

Each test builds its own accounts under codes no account of the practice user holds, and
undoes everything (conftest.py `scratch`). Gating, target and the real-ledger guard:
conftest.py.
"""

from datetime import date
from uuid import uuid4

from tests.contract.conftest import (
    CardRow,
    PaperRow,
    assert_refusal,
    balance_of,
    card_paper,
    free_statement_codes,
    refused,
    savings_paper,
    send_statement,
)

MARCH = {"start": date(2026, 3, 1), "end": date(2026, 3, 31)}


def _order(client, statement_id: str) -> dict:
    return client.get(f"/statements/{statement_id}/statement-order")


def _places(order: dict) -> list[tuple[int, str | None]]:
    """Each place and the id of the line it holds, `None` for an empty slot; the line is
    the one `GET /bank-lines/{id}` reads, and its own `statement_place` is the place it is
    listed under."""
    out = []
    for entry in order["places"]:
        line = entry["bank_line"]
        if line is not None:
            assert line["statement_place"] == entry["place"]
        out.append((entry["place"], None if line is None else line["id"]))
    return out


def _unplaced(order: dict) -> list[str]:
    """The ids of the unplaced lines, in the order the read lists them."""
    for line in order["unplaced"]:
        assert line["statement_place"] is None
    return [line["id"] for line in order["unplaced"]]


def _numbered(client, line_id: str) -> tuple[str | None, int | None]:
    """The line's statement line and place, the same on every part of it."""
    line = client.get(f"/bank-lines/{line_id}")
    for part in line["parts"]:
        read = client.get(f"/transactions/{part['id']}")
        assert (read["statement_line"], read["statement_place"]) == (
            line["statement_line"],
            line["statement_place"],
        )
    return line["statement_line"], line["statement_place"]


def _counts(client, statement_id: str) -> tuple[int | None, int | None]:
    read = client.get(f"/statements/{statement_id}")
    return read["unplaced_count"], read["shared_place_count"]


def _not_ordered(client, statement_id: str) -> str:
    """Completing is refused as not ordered, and the statement stays a draft at its
    `version`; the field's text, which names what is wrong."""
    before = client.get(f"/statements/{statement_id}")
    err = refused(lambda: client.post(f"/statements/{statement_id}/complete"))
    assert_refusal(err, 422, "VALIDATION_ERROR", "statement_order", "STATEMENT_NOT_ORDERED")
    after = client.get(f"/statements/{statement_id}")
    assert (after["status"], after["version"]) == (1, before["version"])
    return err.fields["statement_order"]


def _march_on_a_savings_account(client, scratch):
    """A coded soles account whose March is closed from a made-up paper of five rows: a single
    line, a `0.00` fee, a split line and an income (all held by the ledger already, matched by
    day and total) and a purchase the upload creates; the statement is completed. Returns the
    account, its code, the statement's id, the paper, the ids of the lines in paper order
    (`None` for the empty slot) and the statement's lines' ids."""
    (code,) = free_statement_codes(client, 1)
    account = scratch.account(code=code)
    single = scratch.line(account, "2026-03-05", -1000)
    grouped = scratch.line(account, "2026-03-10", -600, -400)
    income = scratch.line(account, "2026-03-15", 2500)
    paper = savings_paper(
        [
            PaperRow(date(2026, 3, 5), "COMPRA UNO", -1000),
            PaperRow(date(2026, 3, 6), "MANT. CUENTA", 0),
            PaperRow(date(2026, 3, 10), "COMPRA DOS", -1000),
            PaperRow(date(2026, 3, 15), "ABONO", 2500),
            PaperRow(date(2026, 3, 20), "COMPRA TRES", -300),
        ],
        before_cents=100000,
        **MARCH,
    )
    done = send_statement(client, account, paper, dry_run=False)
    scratch.took(done)
    created = done["rows"][4]["bank_line_id"]
    assert done["rows"][4]["outcome"] == "new"
    return account, code, done["statement_id"], paper, [single, None, grouped, income, created]


def test_the_upload_sets_the_order_and_the_read_gives_it_back(client, scratch):
    """The bank's paper sets the order: each line takes its row's position counting from 1,
    an empty slot standing for the `0.00` row, so the next line keeps the paper's number.
    The read lists the places in order, each `bank_line` exactly as `GET /bank-lines/{id}`
    returns it, and nothing unplaced; the statement reads `unplaced_count` and
    `shared_place_count` of `0`. Completed, every line and part reads
    `<CODE>-<YYYYMM>-<NNN>` from the account's code, the month of the end day and the place
    (contract: GET /v1/statements/{statement_id}/statement-order, "Response")
    (contract: "Statements", "A statement's order")
    (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields"); a revert makes it
    `null` and keeps the place, and a change or clearing of the account's code changes or
    clears every statement line at once (contract: "What an account is", "Statement code")."""
    account, code, statement, _paper, lines = _march_on_a_savings_account(client, scratch)
    other = free_statement_codes(client, 1)[0]
    placed = {line: place for place, line in enumerate(lines, start=1) if line is not None}

    order = _order(client, statement)
    assert set(order) == {"statement_id", "places", "unplaced"}
    assert order["statement_id"] == statement
    assert _places(order) == list(enumerate(lines, start=1))
    assert [entry["bank_line"] for entry in order["places"] if entry["bank_line"]] == [
        client.get(f"/bank-lines/{line}") for line in lines if line is not None
    ]
    assert _unplaced(order) == []
    assert _counts(client, statement) == (0, 0)

    for line, place in placed.items():
        assert _numbered(client, line) == (f"{code}-202603-{place:03d}", place)
    assert len(client.get(f"/bank-lines/{lines[2]}")["parts"]) == 2

    client.post(f"/statements/{statement}/revert")
    for line, place in placed.items():
        assert _numbered(client, line) == (None, place)
    assert _places(_order(client, statement)) == list(enumerate(lines, start=1))

    client.post(f"/statements/{statement}/complete")
    for line, place in placed.items():
        assert _numbered(client, line) == (f"{code}-202603-{place:03d}", place)

    client.put(f"/accounts/{account}", json_body={"statement_code": other})
    for line, place in placed.items():
        assert _numbered(client, line) == (f"{other}-202603-{place:03d}", place)
    client.put(f"/accounts/{account}", json_body={"statement_code": None})
    for line, place in placed.items():
        assert _numbered(client, line) == (None, place)


def test_a_line_assigned_after_the_upload_is_unplaced_until_the_paper_is_uploaded_again(
    client, scratch
):
    """Nothing renumbers on its own: on a reverted statement, a line assigned after the
    upload holds no place and is listed unplaced beside the opening balance, which is never
    placed and never counted; the places stay. Completing is then refused as
    `STATEMENT_NOT_ORDERED`, the message counting the line, until the same paper uploaded
    again takes out the lines it does not print, the opening balance too, and completes the
    statement
    (contract: "Statements", "Nothing renumbers on its own")
    (contract: POST /v1/statements/{statement_id}/complete, "Validation")."""
    account, code, statement, paper, lines = _march_on_a_savings_account(client, scratch)
    client.post(f"/statements/{statement}/revert")  # the closed days are sealed against new rows
    opening = scratch.opening_balance(account, "2026-02-15")
    opening_tx = client.get(f"/bank-lines/{opening}")["parts"][0]["id"]
    late = scratch.row(account, "2026-03-22", -300)
    scratch.assign(opening_tx, statement)
    scratch.assign(late["id"], statement)

    order = _order(client, statement)
    assert _places(order) == list(enumerate(lines, start=1))
    assert _unplaced(order) == [opening, late["bank_line_id"]]
    assert _counts(client, statement) == (1, 0)
    # The lines move the statement's sum, so the ending balance follows to leave the order the
    # only thing the close lacks.
    balance = balance_of(client.get(f"/statements/{statement}"), "PEN")
    ending = balance["ending_balance_cents"] - balance["difference_cents"]
    sent = [{"currency_code": "PEN", "ending_balance_cents": ending}]
    client.put(f"/statements/{statement}", json_body={"balances": sent})
    assert balance_of(client.get(f"/statements/{statement}"), "PEN")["difference_cents"] == 0
    assert "1 line(s)" in _not_ordered(client, statement)

    again = send_statement(client, account, paper, dry_run=False)
    scratch.took(again)
    assert (again["statement_id"], again["creates"]) == (statement, False)
    assert late["bank_line_id"] in again["taken_out"]
    # The opening balance matches no row, so the upload takes it out of the statement too.
    assert opening in again["taken_out"]
    assert client.get(f"/transactions/{opening_tx}")["statement_id"] is None
    assert client.get(f"/bank-lines/{opening}")["statement_place"] is None
    assert _unplaced(_order(client, statement)) == []
    assert _places(_order(client, statement)) == list(enumerate(lines, start=1))
    assert client.get(f"/statements/{statement}")["status"] == 2
    assert _numbered(client, lines[3]) == (f"{code}-202603-004", 4)
    assert _numbered(client, late["bank_line_id"]) == (None, None)


#: A card's March, rows in paper order with their days: neither the days nor a grouping by
#: currency gives the currencies in this order (days: USD, PEN, PEN, USD; grouped: PEN, PEN,
#: USD, USD), and each amount is its own, so a place is tied to its row.
CARD_ROWS = [
    CardRow(date(2026, 3, 10), "COMPRA UNO", "CONSUMO", 5000, "PEN"),
    CardRow(date(2026, 3, 20), "COMPRA DOS", "CONSUMO", 1000, "USD"),
    CardRow(date(2026, 3, 2), "COMPRA TRES", "CONSUMO", 2000, "USD"),
    CardRow(date(2026, 3, 4), "COMPRA CUATRO", "CONSUMO", 3000, "PEN"),
]


def _card_march(client, scratch):
    """A coded account of soles and dollars whose March the made-up card paper `CARD_ROWS`
    closes; returns the account, its code, the statement's id and the lines in paper order."""
    (code,) = free_statement_codes(client, 1)
    account = scratch.account("PEN", "USD", code=code)
    done = send_statement(client, account, card_paper(CARD_ROWS, **MARCH), dry_run=False)
    scratch.took(done)
    rows = done["rows"]
    assert [(r["place"], r["currency_code"], r["amount_cents"], r["date"]) for r in rows] == [
        (place, row.currency, row.amount_cents, row.day.isoformat())
        for place, row in enumerate(CARD_ROWS, start=1)
    ]
    return account, code, done["statement_id"], [r["bank_line_id"] for r in rows]


def test_a_cards_two_currencies_are_one_order_and_unplaced_lines_mix_by_date(client, scratch):
    """A card's rows of both currencies take one numbering in paper order: the placed lines
    read soles, dollars, dollars, soles with the amounts 5000, 1000, 2000, 3000 of their
    rows, which neither their days (dollars, soles, soles, dollars) nor a grouping by
    currency could give. Every line reads its code in that one numbering. After a revert,
    lines assigned later in both currencies are listed unplaced oldest first by date with
    the currencies mixed, not grouped, and two lines of one day in the order they were made,
    each the line `GET /bank-lines/{id}` returns; they count in `unplaced_count`
    (contract: "Statements", "A statement's order")
    (contract: GET /v1/statements/{statement_id}/statement-order, "Response")."""
    account, code, statement, lines = _card_march(client, scratch)

    order = _order(client, statement)
    assert _places(order) == list(enumerate(lines, start=1))
    placed = [e["bank_line"] for e in order["places"]]
    assert [(x["currency_code"], x["net_cents"]) for x in placed] == [
        ("PEN", -5000),
        ("USD", -1000),
        ("USD", -2000),
        ("PEN", -3000),
    ]
    assert _unplaced(order) == []
    for place, line in enumerate(lines, start=1):
        assert _numbered(client, line) == (f"{code}-202603-{place:03d}", place)

    client.post(f"/statements/{statement}/revert")
    later = _assign_later(scratch, account, statement)
    order = _order(client, statement)
    assert _unplaced(order) == [row["bank_line_id"] for row in later]
    assert [line["currency_code"] for line in order["unplaced"]] == [
        "USD",
        "PEN",
        "PEN",
        "USD",
        "PEN",
    ]
    for line in order["unplaced"]:
        assert line == client.get(f"/bank-lines/{line['id']}")
    assert _places(order) == list(enumerate(lines, start=1))
    assert _counts(client, statement) == (5, 0)


def _assign_later(scratch, account: str, statement: str) -> list[dict]:
    """Five rows of both currencies assigned to the statement in reverse of the order they
    are listed unplaced in (oldest first by day, the two of the 14th in creation order);
    returned in that order."""
    usd12 = scratch.row(account, "2026-03-12", -100, "USD")
    pen14a = scratch.row(account, "2026-03-14", -200, "PEN")
    pen14b = scratch.row(account, "2026-03-14", -300, "PEN")
    usd18 = scratch.row(account, "2026-03-18", -400, "USD")
    pen22 = scratch.row(account, "2026-03-22", -500, "PEN")
    later = [usd12, pen14a, pen14b, usd18, pen22]
    for row in reversed(later):
        scratch.assign(row["id"], statement)
    return later


def _listed(client, path: str = "/bank-lines", **params) -> list[str]:
    return [line["id"] for line in client.get(path, params=params)["items"]]


def test_a_statements_lines_list_in_the_statement_order(client, scratch):
    """`GET /bank-lines?statement_id=&sort=statement` lists the statement's lines, every
    currency of the account together: the lines holding a place by place, then the ones
    holding none oldest first; with `currency_code` one currency's, whose places have gaps.
    It pages by cursor, a cursor bound to its order: one of `date_desc`, `date_asc` and
    `statement` is `422` on `after` (`INVALID_CURSOR`) with either of the other two, a
    request without `sort` and one with `sort=date_desc` take each other's, and a
    transactions cursor is refused. Any other `sort` is `INVALID_FORMAT`; the count takes
    no `sort` (`UNKNOWN_PARAMETER`) and counts the same lines. `sort=date_asc` beside the
    statement is the newest-first list read backwards, and `sort=statement` without
    `statement_id` is `REQUIRED` on it, `unreconciled=true` beside it too. A line keeps its
    place after its account's code is cleared and is listed by it; an account that never had a code
    lists its lines oldest first (contract: GET /v1/bank-lines, "Ordering")
    (contract: GET /v1/bank-lines, "Paging is by cursor")
    (contract: GET /v1/bank-lines/count)."""
    account, _code, statement, lines = _card_march(client, scratch)
    client.post(f"/statements/{statement}/revert")
    later = _assign_later(scratch, account, statement)
    unplaced = [row["bank_line_id"] for row in later]
    expected = [*lines, *unplaced]

    assert _listed(client, statement_id=statement, sort="statement") == expected
    # Oldest first is taken beside a statement too: the newest-first list read backwards.
    assert (
        _listed(client, statement_id=statement, sort="date_asc")
        == _listed(client, statement_id=statement)[::-1]
    )
    assert _listed(client, statement_id=statement) == _listed(
        client, statement_id=statement, sort="date_desc"
    )
    soles = client.get(
        "/bank-lines",
        params={"statement_id": statement, "sort": "statement", "currency_code": "PEN"},
    )["items"]
    assert [(x["statement_place"], x["currency_code"]) for x in soles[:2]] == [
        (1, "PEN"),
        (4, "PEN"),
    ]
    assert [x["id"] for x in soles] == [
        lines[0],
        lines[3],
        *(row["bank_line_id"] for row in later if row["currency_code"] == "PEN"),
    ]

    pages, after = [], None
    while True:
        params = {"statement_id": statement, "sort": "statement", "limit": 2}
        page = client.get("/bank-lines", params={**params, **({"after": after} if after else {})})
        pages.append([line["id"] for line in page["items"]])
        after = page["next_cursor"]
        if after is None:
            break
    assert [len(page) for page in pages] == [2, 2, 2, 2, 1]
    assert [line for page in pages for line in page] == expected

    def cursor(**params) -> str:
        page = client.get("/bank-lines", params={"statement_id": statement, "limit": 1, **params})
        return page["next_cursor"]

    statement_cursor = cursor(sort="statement")
    default_cursor = cursor()
    oldest_cursor = cursor(sort="date_asc")
    assert _listed(client, statement_id=statement, sort="date_desc", after=default_cursor) == (
        _listed(client, statement_id=statement, after=default_cursor)
    )
    transactions_cursor = client.get("/transactions", params={"account_id": account, "limit": 1})[
        "next_cursor"
    ]
    for params in (
        {"after": statement_cursor},
        {"sort": "date_desc", "after": statement_cursor},
        {"sort": "date_asc", "after": statement_cursor},
        {"sort": "statement", "after": default_cursor},
        {"sort": "statement", "after": oldest_cursor},
        {"sort": "date_desc", "after": oldest_cursor},
        {"after": oldest_cursor},
        {"sort": "statement", "after": transactions_cursor},
    ):
        err = refused(
            lambda params=params: client.get(
                "/bank-lines", params={"statement_id": statement, **params}
            )
        )
        assert_refusal(err, 422, "VALIDATION_ERROR", "after", "INVALID_CURSOR")

    err = refused(
        lambda: client.get("/bank-lines", params={"statement_id": statement, "sort": "oldest"})
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "sort", "INVALID_FORMAT")
    # `sort=statement` names its statement even beside `unreconciled=true`.
    err = refused(
        lambda: client.get("/bank-lines", params={"sort": "statement", "unreconciled": "true"})
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "statement_id", "REQUIRED")
    assert client.get("/bank-lines/count", params={"statement_id": statement}) == {
        "count": len(expected)
    }
    for sort in ("statement", "date_desc", "date_asc"):
        err = refused(
            lambda sort=sort: client.get(
                "/bank-lines/count", params={"statement_id": statement, "sort": sort}
            )
        )
        assert_refusal(err, 422, "VALIDATION_ERROR", "sort", "UNKNOWN_PARAMETER")

    # The code cleared: the lines keep their places and are still listed by them.
    client.put(f"/accounts/{account}", json_body={"statement_code": None})
    assert _listed(client, statement_id=statement, sort="statement") == expected

    # An account that never had a code: every line holds no place, oldest first.
    plain = scratch.account()
    second = scratch.row(plain, "2026-03-10", -100)
    first = scratch.row(plain, "2026-03-05", -200)
    plain_statement = scratch.statement(plain, "2026-03-01", "2026-03-31")["id"]
    scratch.assign(second["id"], plain_statement)
    scratch.assign(first["id"], plain_statement)
    assert _listed(client, statement_id=plain_statement, sort="statement") == [
        first["bank_line_id"],
        second["bank_line_id"],
    ]


def test_a_draft_statement_with_assigned_lines_has_no_places(client, scratch):
    """A statement no paper has been uploaded for lists no place and every line assigned to
    it unplaced, oldest first, drafts and completed statements alike; completing it is
    refused as `STATEMENT_NOT_ORDERED` and counts its lines
    (contract: GET /v1/statements/{statement_id}/statement-order)
    (contract: POST /v1/statements/{statement_id}/complete, "Validation")."""
    (code,) = free_statement_codes(client, 1)
    account = scratch.account(code=code)
    later = scratch.row(account, "2026-03-20", -100)
    sooner = scratch.row(account, "2026-03-05", -200)
    balances = [
        {"currency_code": "PEN", "beginning_balance_cents": 0, "ending_balance_cents": -300}
    ]
    statement = scratch.statement(account, "2026-03-01", "2026-03-31", balances=balances)["id"]
    scratch.assign(later["id"], statement)
    scratch.assign(sooner["id"], statement)

    order = _order(client, statement)
    assert order["places"] == []
    assert _unplaced(order) == [sooner["bank_line_id"], later["bank_line_id"]]
    assert _counts(client, statement) == (2, 0)
    assert "2 line(s)" in _not_ordered(client, statement)


def test_the_order_read_refusals(client, scratch):
    """The read is `404` for an id naming no live statement of the caller's (none, or a
    deleted one) and `422` `INVALID_FORMAT` on `statement_id` for a non-UUID; on an account
    with no statement code it is `409` on `statement_id` (`NO_STATEMENT_CODE`), also for an
    account whose code was cleared after its paper closed the month
    (contract: GET /v1/statements/{statement_id}/statement-order)."""
    account, _code, statement, _paper, _lines = _march_on_a_savings_account(client, scratch)
    plain = scratch.account()
    plain_statement = scratch.statement(plain, "2026-03-01", "2026-03-31")["id"]
    deleted = scratch.statement(plain, "2026-04-01", "2026-04-30")["id"]
    client.delete(f"/statements/{deleted}")

    for missing in (str(uuid4()), deleted):
        err = refused(lambda missing=missing: _order(client, missing))
        assert (err.status, err.code) == (404, "NOT_FOUND")
    err = refused(lambda: _order(client, "not-a-uuid"))
    assert_refusal(err, 422, "VALIDATION_ERROR", "statement_id", "INVALID_FORMAT")

    err = refused(lambda: _order(client, plain_statement))
    assert_refusal(err, 409, "CONFLICT", "statement_id", "NO_STATEMENT_CODE")
    client.put(f"/accounts/{account}", json_body={"statement_code": None})
    err = refused(lambda: _order(client, statement))
    assert_refusal(err, 409, "CONFLICT", "statement_id", "NO_STATEMENT_CODE")


def test_an_account_without_a_code_completes_without_an_order(client, scratch):
    """An account with no statement code has no order: its statement reads `null` for
    `unplaced_count` and `shared_place_count`, completes with lines holding no place, and its
    lines read no statement line (contract: "Statements", "A statement's order")."""
    account = scratch.account()
    row = scratch.row(account, "2026-03-05", -1000)
    statement = scratch.completed(account, "2026-03-01", "2026-03-31", row["id"])
    assert (statement["unplaced_count"], statement["shared_place_count"]) == (None, None)
    assert statement["status"] == 2
    assert _numbered(client, row["bank_line_id"]) == (None, None)


def test_no_statement_write_sets_a_place(client, scratch):
    """No route writes the order, so a body naming `places` or `statement_place` on a
    statement's `PUT` is `422` `UNKNOWN_FIELD` under its own key, nothing written: the
    statement and its order read the same after
    (contract: PUT /v1/statements/{statement_id}, "Nullable here")."""
    _account, _code, statement, _paper, lines = _march_on_a_savings_account(client, scratch)
    client.post(f"/statements/{statement}/revert")
    before = client.get(f"/statements/{statement}"), _order(client, statement)
    for key, value in (("places", lines), ("statement_place", 1)):
        err = refused(
            lambda key=key, value=value: client.put(
                f"/statements/{statement}", json_body={key: value}
            )
        )
        assert_refusal(err, 422, "VALIDATION_ERROR", key, "UNKNOWN_FIELD")
    assert (client.get(f"/statements/{statement}"), _order(client, statement)) == before
    assert _places(before[1]) == list(enumerate(lines, start=1))
