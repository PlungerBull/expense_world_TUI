"""Contract: a statement holds a balance entry per currency it covers, against a real engine.

A statement is one account's, and an account of PEN and USD has one statement for a month,
not one per currency: its `balances` hold an entry for each currency with something in the
statement, each named by its `currency_code`, in the account's currency order
(contract: "Statements", "Which currencies a statement covers"). A currency with nothing in
the month may be left out. Pinned here, per currency:

  · one statement holds both currencies of the account, each balance adding up on its own;
  · a currency left out of `POST /statements` is listed in `not_covered` at the close, with
    its own notes, and a line in no statement in it is flagged there;
  · `DIFFERENCE_NOT_ZERO` is keyed `balances.<code>.difference_cents`, every currency that
    fails named in one answer, and a refused close writes nothing;
  · a currency with no line closes when its beginning and ending balances are equal;
  · a `PUT` naming one currency keeps the others, and a list that names a currency twice, or
    one the account does not hold, is refused on the entry's position;
  · an archived account's statements, draft and completed, are frozen in each currency.

The single-record lifecycle, the period's refusals, locking and the account's list are in
test_statements_lifecycle.py. Gating, target resolution and the real-ledger guard live in
conftest.py.
"""

from tests.contract.conftest import assert_refusal, assert_refusals, refused

APRIL = ("2026-04-01", "2026-04-30")
MAY = ("2026-05-01", "2026-05-31")
ARCHIVED = "The account is archived. Unarchive it first."
NOT_ZERO = (
    "Must be 0: the account's transactions in the statement must add up to its ending balance "
    "minus its beginning balance."
)
NOTES = {"warnings", "coverage_gap", "review_lines"}


def _entry(code: str, beginning: int, ending: int | None) -> dict:
    return {
        "currency_code": code,
        "beginning_balance_cents": beginning,
        "ending_balance_cents": ending,
    }


def _balance(statement: dict, code: str) -> dict:
    return next(b for b in statement["balances"] if b["currency_code"] == code)


def _codes(statement: dict) -> list[str]:
    return [b["currency_code"] for b in statement["balances"]]


def test_one_statement_holds_both_currencies_each_adding_up_on_its_own(client, scratch):
    """An account of PEN and USD has one statement for April, not two. Its balances come back
    in the account's currency order whatever order the request listed them in, and a
    transaction counts only in its own currency's `difference_cents`: the PEN row of -1200
    leaves PEN at 0 and USD, which has none, at its ending balance minus its beginning."""
    account = scratch.account("PEN", "USD")
    pen_tx = scratch.row(account, "2026-04-15", -1200)["id"]
    usd_tx = scratch.row(account, "2026-04-16", -300, "USD")["id"]

    created = scratch.statement(
        account, *APRIL, balances=[_entry("USD", 5000, 4700), _entry("PEN", 10000, 8800)]
    )
    sid = created["id"]
    assert _codes(created) == ["PEN", "USD"]
    assert client.get("/statements", params={"account_id": account}) == {"items": [created]}

    scratch.assign(pen_tx, sid)
    read = client.get(f"/statements/{sid}")
    assert _balance(read, "PEN")["difference_cents"] == 0
    assert _balance(read, "USD")["difference_cents"] == -300

    scratch.assign(usd_tx, sid)
    read = client.get(f"/statements/{sid}")
    assert [b["difference_cents"] for b in read["balances"]] == [0, 0]

    completed = client.post(f"/statements/{sid}/complete")
    assert (completed["status"], _codes(completed), completed["not_covered"]) == (
        2,
        ["PEN", "USD"],
        [],
    )
    for balance in completed["balances"]:
        assert NOTES <= set(balance)


def test_a_currency_with_nothing_this_month_is_left_out_and_listed_in_not_covered(client, scratch):
    """A PEN and USD account with no dollar line and no money in dollars at the start sends
    only its PEN entry, and the statement holds PEN alone. The close reviews every currency
    of the account all the same: the answer's `not_covered` has an entry for USD with its
    own notes, and a dollar line in no statement dated in the days is flagged there, in
    the dollars' `review_lines`. Only the close carries `not_covered`
    (contract: POST /v1/statements/{statement_id}/complete, "`not_covered`")."""
    account = scratch.account("PEN", "USD")
    pen_tx = scratch.row(account, "2026-04-15", -1200)["id"]
    sid = scratch.statement(account, *APRIL, balances=[_entry("PEN", 10000, 8800)])["id"]
    scratch.assign(pen_tx, sid)
    assert _codes(client.get(f"/statements/{sid}")) == ["PEN"]

    quiet = client.post(f"/statements/{sid}/complete")
    assert (quiet["status"], _codes(quiet)) == (2, ["PEN"])
    assert quiet["not_covered"] == [
        {"currency_code": "USD", "warnings": [], "coverage_gap": None, "review_lines": []}
    ]
    assert "not_covered" not in client.get(f"/statements/{sid}")

    client.post(f"/statements/{sid}/revert")
    stray = scratch.row(account, "2026-04-20", -300, "USD")
    flagged = client.post(f"/statements/{sid}/complete")
    assert _codes(flagged) == ["PEN"]
    assert flagged["not_covered"] == [
        {
            "currency_code": "USD",
            "warnings": [],
            "coverage_gap": None,
            "review_lines": [stray["bank_line_id"]],
        }
    ]
    assert _balance(flagged, "PEN")["review_lines"] == []


def test_difference_not_zero_is_keyed_on_each_currency_that_fails_and_writes_nothing(
    client, scratch
):
    """Every currency's `difference_cents` must be 0 to complete. One that is not is `422`
    keyed `balances.<code>.difference_cents` (`DIFFERENCE_NOT_ZERO`, "Must be 0: ..."), the
    currencies that add up left out of the answer, and every currency that fails named in
    the same one. Each refusal leaves the statement a draft, as it was
    (contract: POST /v1/statements/{statement_id}/complete, "Every currency adds up")."""
    account = scratch.account("PEN", "USD")
    pen_tx = scratch.row(account, "2026-04-15", -1200)["id"]
    usd_tx = scratch.row(account, "2026-04-16", -300, "USD")["id"]
    sid = scratch.statement(
        account, *APRIL, balances=[_entry("PEN", 10000, 8800), _entry("USD", 5000, 4000)]
    )["id"]
    scratch.assign(pen_tx, sid)
    scratch.assign(usd_tx, sid)
    before = client.get(f"/statements/{sid}")
    assert [b["difference_cents"] for b in before["balances"]] == [0, -700]

    err = refused(lambda: client.post(f"/statements/{sid}/complete"))
    assert_refusal(
        err, 422, "VALIDATION_ERROR", "balances.USD.difference_cents", "DIFFERENCE_NOT_ZERO"
    )
    assert err.fields == {"balances.USD.difference_cents": NOT_ZERO}
    assert err.message == "Cannot complete the statement until every currency adds up."
    assert client.get(f"/statements/{sid}") == before

    client.put(
        f"/statements/{sid}",
        json_body={"balances": [{"currency_code": "PEN", "ending_balance_cents": 9000}]},
    )
    err = refused(lambda: client.post(f"/statements/{sid}/complete"))
    assert_refusals(
        err,
        422,
        "VALIDATION_ERROR",
        {
            "balances.PEN.difference_cents": "DIFFERENCE_NOT_ZERO",
            "balances.USD.difference_cents": "DIFFERENCE_NOT_ZERO",
        },
    )
    assert set(err.fields.values()) == {NOT_ZERO}
    assert client.get(f"/statements/{sid}")["status"] == 1

    client.put(
        f"/statements/{sid}",
        json_body={
            "balances": [
                {"currency_code": "PEN", "ending_balance_cents": 8800},
                {"currency_code": "USD", "ending_balance_cents": 4700},
            ]
        },
    )
    assert client.post(f"/statements/{sid}/complete")["status"] == 2


def test_a_currency_with_no_line_closes_when_its_two_balances_are_equal(client, scratch):
    """A card month with a line in soles only: the dollars hold no line, so their
    `difference_cents` is the ending balance minus the beginning one, and the close takes
    them exactly when the two are equal. $300 owed at both ends (`-30000` to `-30000`) closes
    with no dollar line; $300 at the start and $200 at the end is `DIFFERENCE_NOT_ZERO` on
    the dollars alone, and the soles that add up are not named. No transaction in a
    currency is not `NO_TRANSACTIONS_ASSIGNED` while another currency holds one
    (contract: POST /v1/statements/{statement_id}/complete, "The statement holds a transaction
    in at least one currency")."""
    account = scratch.account("PEN", "USD")
    pen_tx = scratch.row(account, "2026-04-15", -1200)["id"]
    sid = scratch.statement(
        account, *APRIL, balances=[_entry("PEN", 10000, 8800), _entry("USD", -30000, -20000)]
    )["id"]
    scratch.assign(pen_tx, sid)
    assert [b["difference_cents"] for b in client.get(f"/statements/{sid}")["balances"]] == [
        0,
        10000,
    ]

    err = refused(lambda: client.post(f"/statements/{sid}/complete"))
    assert_refusal(
        err, 422, "VALIDATION_ERROR", "balances.USD.difference_cents", "DIFFERENCE_NOT_ZERO"
    )
    assert client.get(f"/statements/{sid}")["status"] == 1

    client.put(
        f"/statements/{sid}",
        json_body={"balances": [{"currency_code": "USD", "ending_balance_cents": -30000}]},
    )
    completed = client.post(f"/statements/{sid}/complete")
    assert completed["status"] == 2
    assert [(b["currency_code"], b["difference_cents"]) for b in completed["balances"]] == [
        ("PEN", 0),
        ("USD", 0),
    ]
    assert _balance(completed, "USD")["review_lines"] == []


def test_a_put_naming_one_currency_keeps_the_others(client, scratch):
    """A currency left out of `balances` is kept as it is, and in an entry an omitted balance
    is kept too: a `PUT` of the dollars' ending balance leaves the soles' two balances and the
    dollars' beginning one alone, one write, one version. `ending_balance_cents: null`
    returns a balance to "not entered" and its difference to `null`, again on its own
    currency. A `null` beginning balance is `NOT_NULL` on the entry's position and writes
    nothing (contract: PUT /v1/statements/{statement_id}, "`balances`")."""
    account = scratch.account("PEN", "USD")
    created = scratch.statement(
        account, *APRIL, balances=[_entry("PEN", 10000, 10000), _entry("USD", 5000, 5000)]
    )
    sid = created["id"]

    put = client.put(
        f"/statements/{sid}",
        json_body={"balances": [{"currency_code": "USD", "ending_balance_cents": 4000}]},
    )
    assert _balance(put, "PEN") == _balance(created, "PEN")
    assert _balance(put, "USD") == {**_entry("USD", 5000, 4000), "difference_cents": -1000}
    assert (put["version"], _codes(put)) == (created["version"] + 1, ["PEN", "USD"])

    put = client.put(
        f"/statements/{sid}",
        json_body={"balances": [{"currency_code": "PEN", "ending_balance_cents": None}]},
    )
    assert _balance(put, "PEN") == {**_entry("PEN", 10000, None), "difference_cents": None}
    assert _balance(put, "USD") == {**_entry("USD", 5000, 4000), "difference_cents": -1000}

    before = client.get(f"/statements/{sid}")
    assert_refusal(
        refused(
            lambda: client.put(
                f"/statements/{sid}",
                json_body={"balances": [{"currency_code": "USD", "beginning_balance_cents": None}]},
            )
        ),
        422,
        "VALIDATION_ERROR",
        "balances.0.beginning_balance_cents",
        "NOT_NULL",
    )
    assert client.get(f"/statements/{sid}") == before


def test_a_balances_list_names_each_currency_once_and_only_the_accounts(client, scratch):
    """The list is judged entry by entry and keyed by the entry's position from 0
    (contract: "Statements", "Which currency a refusal names"): a currency twice is
    `DUPLICATE_IN_REQUEST` on the later entry, a code the engine does not support
    `UNSUPPORTED_VALUE` and a supported one the account holds no live currency in
    `CURRENCY_NOT_HELD`, both in one answer, on a create and on a `PUT`. Each refusal writes
    nothing (contract: POST /v1/statements, "Order")."""
    account = scratch.account("PEN")
    sid = scratch.statement(account, *APRIL, balances=[_entry("PEN", 10000, 10000)])["id"]
    before = client.get(f"/statements/{sid}")

    twice = [_entry("PEN", 1, 1), _entry("PEN", 2, 2)]
    not_held = [_entry("PEN", 1, 1), _entry("USD", 2, 2), _entry("ZZZ", 3, 3)]

    def create(entries):
        return refused(lambda: scratch.statement(account, *MAY, balances=entries))

    def put(entries):
        return refused(lambda: client.put(f"/statements/{sid}", json_body={"balances": entries}))

    for send in (create, put):
        assert_refusal(
            send(twice), 422, "VALIDATION_ERROR", "balances.1.currency_code", "DUPLICATE_IN_REQUEST"
        )
        assert_refusals(
            send(not_held),
            422,
            "VALIDATION_ERROR",
            {
                "balances.1.currency_code": "CURRENCY_NOT_HELD",
                "balances.2.currency_code": "UNSUPPORTED_VALUE",
            },
        )
    assert client.get(f"/statements/{sid}") == before
    listed = client.get("/statements", params={"account_id": account})["items"]
    assert [item["id"] for item in listed] == [sid]


def test_an_archived_accounts_statements_are_frozen_in_each_currency(client, scratch):
    """On an archived account a `PUT` is `422` `ACCOUNT_ARCHIVED` on each key it sends, a
    balance on `balances.<code>.<field>` of its own currency, an entry sending no balance on
    `balances.<code>`, draft and completed alike, every message "The account is archived.
    Unarchive it first."; a request naming one currency leaves the other untouched. The
    refusal names the currencies sent, no more, and both statements read as before. After
    `POST /accounts/{id}/unarchive` the draft takes a dollar balance again and keeps its
    soles (contract: PUT /v1/statements/{statement_id}, "An archived account")."""
    account = scratch.account("PEN", "USD")
    tx = scratch.row(account, "2026-04-15", -1200)["id"]
    done = scratch.statement(
        account, *APRIL, balances=[_entry("PEN", 10000, 8800), _entry("USD", 5000, 5000)]
    )["id"]
    draft = scratch.statement(
        account, *MAY, balances=[_entry("PEN", 8800, 8800), _entry("USD", 5000, None)]
    )["id"]
    scratch.assign(tx, done)
    client.post(f"/statements/{done}/complete")
    scratch.archive(account)

    before = {sid: client.get(f"/statements/{sid}") for sid in (draft, done)}
    assert (before[draft]["status"], before[done]["status"]) == (1, 2)
    for sid in before:
        err = refused(
            lambda sid=sid: client.put(
                f"/statements/{sid}",
                json_body={"balances": [{"currency_code": "USD", "ending_balance_cents": 1}]},
            )
        )
        assert_refusal(
            err, 422, "VALIDATION_ERROR", "balances.USD.ending_balance_cents", "ACCOUNT_ARCHIVED"
        )
        assert err.fields == {"balances.USD.ending_balance_cents": ARCHIVED}

        err = refused(
            lambda sid=sid: client.put(
                f"/statements/{sid}",
                json_body={
                    "balances": [
                        {"currency_code": "PEN", "beginning_balance_cents": 1},
                        {"currency_code": "USD"},
                    ]
                },
            )
        )
        assert_refusals(
            err,
            422,
            "VALIDATION_ERROR",
            {
                "balances.PEN.beginning_balance_cents": "ACCOUNT_ARCHIVED",
                "balances.USD": "ACCOUNT_ARCHIVED",
            },
        )
        assert set(err.fields.values()) == {ARCHIVED}
    assert {sid: client.get(f"/statements/{sid}") for sid in before} == before

    client.post(f"/accounts/{account}/unarchive")
    put = client.put(
        f"/statements/{draft}",
        json_body={"balances": [{"currency_code": "USD", "ending_balance_cents": 5000}]},
    )
    assert _balance(put, "USD")["ending_balance_cents"] == 5000
    assert _balance(put, "PEN") == _balance(before[draft], "PEN")
