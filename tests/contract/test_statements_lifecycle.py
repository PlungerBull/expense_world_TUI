"""Contract lifecycle for statements against a real engine.

The one resource with a *state machine* (draft, completed, reverted) and the only one whose
completion reaches across and locks rows in another table. None of that is checkable
against a mock: the unit suite asserts the app sends the right call and shows the right
hint, which is a statement about the app, not about what completing a statement does to a
transaction.

A statement is one account's, over one period, holding a balance entry per covered
currency, each named by its `currency_code`; every write acts on the whole statement
(contract: "Statements", "Every write acts on the whole statement"). What this pins, and
why each is a contract claim rather than a client one:

  · made, renamed, completed, reverted and deleted as one record, its balances keyed by
    `currency_code`, and read back the same from the account's list and by its id.
  · `beginning_balance_cents` is required and typed, never derived; a draft may wait for
    its ending balance, completing may not, and a refused complete writes nothing.
  · a complete with nothing assigned is refused in every currency of the statement.
  · the account's list needs `account_id`; an id naming no account lists nothing.
  · a period is two calendar days, never an instant, never overlapping another statement
    of the account, and one statement to a month.
  · completion locks the assigned transaction's fields and revert unlocks them
    (contract: PUT /v1/transactions/{transaction_id}, "Field locking").
  · delete unassigns; the transaction survives.
  · moving an assigned row says what happens to its draft.
  · an archived account's statements, draft and completed, refuse every write until the
    account is unarchived.

Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from datetime import datetime
from uuid import uuid4

from tests.contract.conftest import (
    assert_refusal,
    assert_refusals,
    read_signed,
    refused,
    statement_create_body,
)

BALANCE_KEYS = {
    "currency_code",
    "beginning_balance_cents",
    "ending_balance_cents",
    "difference_cents",
}
BLANK = "Must be entered before completing."
NO_TRANSACTION = "At least one transaction must be assigned."
ARCHIVED = "The account is archived. Unarchive it first."


APRIL = ("2026-04-01", "2026-04-30")
#: PEN beginning at 958000 cents with no ending balance entered, and the same ending at 956800.
OPENING = [{"currency_code": "PEN", "beginning_balance_cents": 958000}]
CLOSING = [{**OPENING[0], "ending_balance_cents": 956800}]


def _balance(statement: dict, code: str) -> dict:
    return next(b for b in statement["balances"] if b["currency_code"] == code)


def test_a_statement_is_made_renamed_completed_reverted_and_deleted_as_one_record(
    client, scratch, statuses
):
    """create, list, read, rename, complete, revert and delete, each one write on the whole
    statement, ending on "deleted is deleted": the statement leaves its account's list and
    its read by id is a `404`. The account's list comes back whole, so absence from it is
    proof. Both currencies of the account sit in the one record, each balance named by
    its `currency_code`, in the account's currency order."""
    account = scratch.account("PEN", "USD")
    pen_tx = scratch.row(account, "2026-04-15", -1200)["id"]
    usd_tx = scratch.row(account, "2026-04-16", -300, "USD")["id"]
    entries = [
        {"currency_code": "PEN", "beginning_balance_cents": 958000},
        {"currency_code": "USD", "beginning_balance_cents": 0, "ending_balance_cents": 0},
    ]

    created = scratch.statement(account, *APRIL, balances=entries)
    sid = created["id"]
    assert statuses[-1] == 201
    assert (created["account_id"], created["status"], created["version"]) == (account, 1, 1)
    # a period's ends are calendar days both ways (contract: "Date inputs")
    assert (created["date_start"], created["date_end"]) == ("2026-04-01", "2026-04-30")
    assert created["deleted_at"] is None
    # an account with no statement code has no order (contract: "Statements", "A statement's order")
    assert (created["unplaced_count"], created["shared_place_count"]) == (None, None)
    assert [set(b) for b in created["balances"]] == [BALANCE_KEYS, BALANCE_KEYS]
    assert created["balances"] == [
        {
            "currency_code": "PEN",
            "beginning_balance_cents": 958000,
            "ending_balance_cents": None,
            "difference_cents": None,
        },
        {
            "currency_code": "USD",
            "beginning_balance_cents": 0,
            "ending_balance_cents": 0,
            "difference_cents": 0,
        },
    ]

    listed = client.get("/statements", params={"account_id": account})
    assert listed == {"items": [created]}
    assert client.get(f"/statements/{sid}") == created

    renamed = client.put(
        f"/statements/{sid}",
        json_body={"name": f"{created['name']}-renamed", "date_end": "2026-04-29"},
    )
    assert renamed["name"] == f"{created['name']}-renamed"
    assert renamed["date_end"] == "2026-04-29"
    assert renamed["balances"] == created["balances"]
    assert renamed["version"] == 2

    scratch.assign(pen_tx, sid)
    scratch.assign(usd_tx, sid)
    entered = client.put(
        f"/statements/{sid}",
        json_body={
            "balances": [
                {"currency_code": "PEN", "ending_balance_cents": 956800},
                {"currency_code": "USD", "ending_balance_cents": -300},
            ]
        },
    )
    assert [(b["currency_code"], b["difference_cents"]) for b in entered["balances"]] == [
        ("PEN", 0),
        ("USD", 0),
    ]

    completed = client.post(f"/statements/{sid}/complete")
    assert (completed["id"], completed["status"]) == (sid, 2)
    assert completed["not_covered"] == []
    for balance in completed["balances"]:
        assert set(balance) == BALANCE_KEYS | {"warnings", "coverage_gap", "review_lines"}
    assert client.get(f"/statements/{sid}")["status"] == 2

    reverted = client.post(f"/statements/{sid}/revert")
    assert (reverted["id"], reverted["status"]) == (sid, 1)
    assert reverted["balances"] == entered["balances"]

    deleted = client.delete(f"/statements/{sid}")
    assert deleted["id"] == sid
    assert deleted["deleted_at"] is not None
    assert client.get("/statements", params={"account_id": account}) == {"items": []}
    gone = refused(lambda: client.get(f"/statements/{sid}"))
    assert (gone.status, gone.code) == (404, "NOT_FOUND")


def test_the_account_list_needs_the_account_and_lists_its_periods_in_order(client, scratch):
    """`?account_id=` is required (`REQUIRED`) and a non-UUID is `INVALID_FORMAT`; an id
    naming no account of the caller's is `200` with `items: []`, never `404`; one account's
    list is `{items}` alone, no paging keys, its periods by `date_start`
    (contract: GET /v1/statements)."""
    account = scratch.account()
    other = scratch.account()
    may = scratch.statement(account, "2026-05-01", "2026-05-31", balances=OPENING)["id"]
    april = scratch.statement(account, *APRIL, balances=OPENING)["id"]

    assert_refusal(
        refused(lambda: client.get("/statements")),
        422,
        "VALIDATION_ERROR",
        "account_id",
        "REQUIRED",
    )
    assert_refusal(
        refused(lambda: client.get("/statements", params={"account_id": "not-a-uuid"})),
        422,
        "VALIDATION_ERROR",
        "account_id",
        "INVALID_FORMAT",
    )
    assert client.get("/statements", params={"account_id": str(uuid4())}) == {"items": []}
    assert client.get("/statements", params={"account_id": other}) == {"items": []}

    listed = client.get("/statements", params={"account_id": account})
    assert set(listed) == {"items"}
    assert [item["id"] for item in listed["items"]] == [april, may]


def test_a_period_is_two_calendar_days_that_clash_with_no_other_statement(client, scratch):
    """Periods are days (contract: "Date inputs"): a midnight instant is `INVALID_FORMAT`
    on the field, a missing day `REQUIRED`, `null` on an update `NOT_NULL`, an inverted
    period `RANGE_INVERTED` on `date_end`. No two live statements of an account share a
    day (`PERIOD_OVERLAPS` on `date_start`) and an account has one a month
    (`STATEMENT_MONTH_TAKEN` on `date_end`), each message naming the one in the way
    (contract: POST /v1/statements, "Order")."""
    account = scratch.account()
    held = scratch.statement(account, *APRIL, balances=OPENING, name="April 2026")["id"]
    may = scratch.statement(account, "2026-05-01", "2026-05-31", balances=OPENING)["id"]

    def refusal(start, end, **fields):
        return refused(lambda: scratch.statement(account, start, end, balances=OPENING, **fields))

    assert_refusal(
        refusal("2026-05-01T00:00:00-05:00", "2026-05-31"),
        422,
        "VALIDATION_ERROR",
        "date_start",
        "INVALID_FORMAT",
    )
    body = statement_create_body(account, "2026-06-01", "2026-06-30", balances=OPENING)
    del body["date_end"]
    scratch.statements.append(body["id"])
    assert_refusal(
        refused(lambda: client.post("/statements", json_body=body)),
        422,
        "VALIDATION_ERROR",
        "date_end",
        "REQUIRED",
    )
    assert_refusal(
        refusal("2026-06-30", "2026-06-01"),
        422,
        "VALIDATION_ERROR",
        "date_end",
        "RANGE_INVERTED",
    )

    overlaps = refusal("2026-03-20", "2026-04-05")
    assert_refusal(overlaps, 422, "VALIDATION_ERROR", "date_start", "PERIOD_OVERLAPS")
    assert overlaps.fields == {
        "date_start": (
            "Overlaps 'April 2026' (2026-04-01 to 2026-04-30). A day belongs to one statement."
        )
    }
    # a month holds one statement even when its days do not clash
    client.put(
        f"/statements/{held}", json_body={"date_start": "2026-04-01", "date_end": "2026-04-10"}
    )
    same_month = refusal("2026-04-20", "2026-04-30")
    assert_refusal(same_month, 422, "VALIDATION_ERROR", "date_end", "STATEMENT_MONTH_TAKEN")
    assert "April 2026" in same_month.fields["date_end"]

    # the same two rules judge a write that moves the days of another statement
    moved = refused(
        lambda: client.put(f"/statements/{may}", json_body={"date_start": "2026-04-05"})
    )
    assert_refusal(moved, 422, "VALIDATION_ERROR", "date_start", "PERIOD_OVERLAPS")
    assert "April 2026" in moved.fields["date_start"]
    moved = refused(
        lambda: client.put(
            f"/statements/{may}", json_body={"date_start": "2026-04-20", "date_end": "2026-04-30"}
        )
    )
    assert_refusal(moved, 422, "VALIDATION_ERROR", "date_end", "STATEMENT_MONTH_TAKEN")
    assert "April 2026" in moved.fields["date_end"]

    for key in ("date_start", "date_end"):
        assert_refusal(
            refused(lambda key=key: client.put(f"/statements/{held}", json_body={key: None})),
            422,
            "VALIDATION_ERROR",
            key,
            "NOT_NULL",
        )
    assert_refusal(
        refused(lambda: client.put(f"/statements/{held}", json_body={"date_end": "2026-03-01"})),
        422,
        "VALIDATION_ERROR",
        "date_end",
        "RANGE_INVERTED",
    )
    listed = client.get("/statements", params={"account_id": account})["items"]
    assert [item["id"] for item in listed] == [held, may]
    assert (listed[1]["date_start"], listed[1]["date_end"]) == ("2026-05-01", "2026-05-31")


def test_the_review_read_includes_a_row_late_on_the_last_day(client, scratch):
    """Rows on `date_end` must not be left out. A read of the account's lines in no
    statement with `date_from` / `date_to` set to the period's own days holds a row logged
    at 23:30 local on `date_end` (contract: GET /v1/bank-lines)."""
    account = scratch.account()
    statement = scratch.statement(account, *APRIL, balances=OPENING)
    night = datetime(2026, 4, 30, 23, 30, tzinfo=scratch.zone).isoformat(timespec="seconds")
    late = scratch.row(account, "2026-04-30", -1200, date=night)
    page = client.get(
        "/bank-lines",
        params={
            "account_id": account,
            "unreconciled": "true",
            "date_from": statement["date_start"],
            "date_to": statement["date_end"],
        },
    )
    assert [[part["id"] for part in line["parts"]] for line in page["items"]] == [[late["id"]]]


def test_the_balances_are_required_and_typed_not_derived(client, scratch):
    """No chained beginning balance, pinned from the outside: a create whose entry lacks
    `beginning_balance_cents` is `REQUIRED` on that entry, a create with an empty list is
    `OUT_OF_RANGE` on `balances`, and a create naming `status` or another unknown field is
    `UNKNOWN_FIELD`. While this refuses, a form is right to ask for the balance; if the
    engine derives it again, this is the test that says it can relax
    (contract: POST /v1/statements, "Required")."""
    account = scratch.account()

    def refusal(**fields):
        return refused(lambda: scratch.statement(account, *APRIL, **fields))

    assert_refusal(
        refusal(balances=[{"currency_code": "PEN"}]),
        422,
        "VALIDATION_ERROR",
        "balances.0.beginning_balance_cents",
        "REQUIRED",
    )
    assert_refusal(refusal(balances=[]), 422, "VALIDATION_ERROR", "balances", "OUT_OF_RANGE")
    assert_refusal(refusal(status=2), 422, "VALIDATION_ERROR", "status", "UNKNOWN_FIELD")
    assert client.get("/statements", params={"account_id": account}) == {"items": []}


def test_completing_with_nothing_assigned_is_refused_in_every_currency(client, scratch):
    """A statement with no transaction in any currency is `422` on
    `balances.<code>.transactions` for every currency of the statement, each
    `NO_TRANSACTIONS_ASSIGNED` reading "At least one transaction must be assigned.". One
    transaction in any currency clears it: the quiet currency is not refused here, it
    completes once its two balances are equal (contract: POST
    /v1/statements/{statement_id}/complete, "The statement holds a transaction in at least
    one currency")."""
    account = scratch.account("PEN", "USD")
    sid = scratch.statement(account, *APRIL, "PEN", "USD")["id"]
    usd_tx = scratch.row(account, "2026-04-15", -300, "USD")["id"]

    err = refused(lambda: client.post(f"/statements/{sid}/complete"))
    assert_refusals(
        err,
        422,
        "VALIDATION_ERROR",
        {
            "balances.PEN.transactions": "NO_TRANSACTIONS_ASSIGNED",
            "balances.USD.transactions": "NO_TRANSACTIONS_ASSIGNED",
        },
    )
    assert err.fields == {
        "balances.PEN.transactions": NO_TRANSACTION,
        "balances.USD.transactions": NO_TRANSACTION,
    }
    assert client.get(f"/statements/{sid}")["status"] == 1

    scratch.assign(usd_tx, sid)
    err = refused(lambda: client.post(f"/statements/{sid}/complete"))
    assert_refusal(
        err, 422, "VALIDATION_ERROR", "balances.USD.difference_cents", "DIFFERENCE_NOT_ZERO"
    )
    client.put(
        f"/statements/{sid}",
        json_body={"balances": [{"currency_code": "USD", "ending_balance_cents": -300}]},
    )
    completed = client.post(f"/statements/{sid}/complete")
    assert completed["status"] == 2
    assert _balance(completed, "PEN")["difference_cents"] == 0


def test_completing_without_an_ending_balance_is_refused_and_writes_nothing(client, scratch):
    """A draft may wait for its paper; completing may not (contract: POST
    /v1/statements/{statement_id}/complete, "Every balance must be entered").

    The draft has a row assigned, so the ending balance is the only thing missing.
    Completing it is a `422` `VALIDATION_ERROR` keyed `balances.PEN.ending_balance_cents`
    with reason `ENDING_BALANCE_REQUIRED` and the message "Must be entered before
    completing."; the draft stays a draft at the same version. Entering the balance with
    `PUT` and completing again succeeds."""
    account = scratch.account()
    tx = scratch.row(account, "2026-04-15", -1200)["id"]
    draft = scratch.statement(account, *APRIL, balances=OPENING)
    sid = draft["id"]
    assert _balance(draft, "PEN")["ending_balance_cents"] is None
    scratch.assign(tx, sid)
    before = client.get(f"/statements/{sid}")

    err = refused(lambda: client.post(f"/statements/{sid}/complete"))
    assert_refusal(
        err,
        422,
        "VALIDATION_ERROR",
        "balances.PEN.ending_balance_cents",
        "ENDING_BALANCE_REQUIRED",
    )
    assert err.fields == {"balances.PEN.ending_balance_cents": BLANK}
    assert client.get(f"/statements/{sid}") == before
    assert (before["status"], _balance(before, "PEN")["ending_balance_cents"]) == (1, None)

    client.put(
        f"/statements/{sid}",
        json_body={"balances": [{"currency_code": "PEN", "ending_balance_cents": 956800}]},
    )
    assert client.post(f"/statements/{sid}/complete")["status"] == 2


def test_complete_locks_the_assigned_transaction_and_revert_unlocks_it(client, scratch):
    """The cross-table side of the state machine (contract: PUT
    /v1/transactions/{transaction_id}, "Field locking").

    Completing makes the amount unwritable (`422` `LOCKED` on the field), as unassigning
    the row, and the row undeletable (`409` `IN_COMPLETED_RECONCILIATION`); reverting
    gives the amount back."""
    account = scratch.account()
    tx = scratch.row(account, "2026-04-15", -1200)["id"]
    sid = scratch.statement(account, *APRIL, balances=CLOSING)["id"]
    scratch.assign(tx, sid)
    client.post(f"/statements/{sid}/complete")

    for body, key in (
        ({"amount_cents": -9999}, "amount_cents"),
        ({"statement_id": None}, "statement_id"),
    ):
        assert_refusal(
            refused(lambda body=body: client.put(f"/transactions/{tx}", json_body=body)),
            422,
            "VALIDATION_ERROR",
            key,
            "LOCKED",
        )
    assert_refusal(
        refused(lambda: client.delete(f"/transactions/{tx}")),
        409,
        "CONFLICT",
        "transaction_id",
        "IN_COMPLETED_RECONCILIATION",
    )
    assert read_signed(client, tx)["amount_cents"] == -1200

    client.post(f"/statements/{sid}/revert")
    client.put(f"/transactions/{tx}", json_body={"amount_cents": -9999})
    # the engine stores the magnitude and signs it only when asked (contract: "Base Conventions")
    assert read_signed(client, tx)["amount_cents"] == -9999


def test_deleting_a_statement_unassigns_its_transactions_and_keeps_them(client, scratch):
    """Cascade-unassign: deleting a draft takes its rows out of it. The row is the user's
    data and the statement is bookkeeping over it; deleting the bookkeeping must never take
    the row with it. A completed statement is not deleted (`409` `RECONCILIATION_NOT_DRAFT`,
    "Must be a draft statement.") until it is reverted
    (contract: DELETE /v1/statements/{statement_id})."""
    account = scratch.account()
    tx = scratch.row(account, "2026-04-15", -1200)["id"]
    sid = scratch.statement(account, *APRIL, balances=CLOSING)["id"]
    scratch.assign(tx, sid)
    assert client.get(f"/transactions/{tx}")["statement_id"] == sid

    client.post(f"/statements/{sid}/complete")
    err = refused(lambda: client.delete(f"/statements/{sid}"))
    assert_refusal(err, 409, "CONFLICT", "statement_id", "RECONCILIATION_NOT_DRAFT")
    assert err.fields == {"statement_id": "Must be a draft statement."}
    assert client.get(f"/transactions/{tx}")["statement_id"] == sid

    client.post(f"/statements/{sid}/revert")
    client.delete(f"/statements/{sid}")
    after = client.get(f"/transactions/{tx}")
    assert after["id"] == tx  # the row survived
    assert after["statement_id"] is None  # and was let go
    assert after["deleted_at"] is None


def test_moving_an_assigned_row_needs_the_unassign_in_the_same_body(client, scratch):
    """The move an edit form and a bulk move make (contract: "Statements", "Assigning
    transactions") (contract: PUT /v1/transactions/{transaction_id}).

    An account or currency change on a row in a draft statement, with no `statement_id` in
    the body, is a `422` `ASSIGNED_TO_RECONCILIATION` keyed on each of `account_id` and
    `currency_code` the request sent, and changes nothing. With `statement_id: null` in the
    same body the row moves and leaves the statement."""
    account = scratch.account("PEN", "USD")
    other = scratch.account()
    tx = scratch.row(account, "2026-04-15", -1200)["id"]
    sid = scratch.statement(account, *APRIL)["id"]
    scratch.assign(tx, sid)

    for body in (
        {"account_id": other},
        {"currency_code": "USD"},
        {"account_id": other, "currency_code": "PEN"},
    ):
        err = refused(lambda body=body: client.put(f"/transactions/{tx}", json_body=body))
        assert_refusals(
            err, 422, "VALIDATION_ERROR", dict.fromkeys(body, "ASSIGNED_TO_RECONCILIATION")
        )
        unchanged = client.get(f"/transactions/{tx}")
        assert (unchanged["account_id"], unchanged["currency_code"]) == (account, "PEN")
        assert unchanged["statement_id"] == sid

    # the account and currency it already has are not a move: no refusal, still assigned
    client.put(f"/transactions/{tx}", json_body={"account_id": account, "currency_code": "PEN"})
    assert client.get(f"/transactions/{tx}")["statement_id"] == sid

    client.put(f"/transactions/{tx}", json_body={"account_id": other, "statement_id": None})
    moved = client.get(f"/transactions/{tx}")
    assert (moved["account_id"], moved["statement_id"]) == (other, None)


def test_an_archived_accounts_statements_are_frozen_until_unarchived(client, scratch):
    """On an archived account, a draft and a completed statement alike: `PUT` is `422`
    `ACCOUNT_ARCHIVED` on every key sent, `name` included and each at its current value, a
    balance on `balances.<code>.<field>`; complete, revert and delete are `409`
    `ACCOUNT_ARCHIVED` on `statement_id`, complete of the completed one and revert of the
    draft included; both stay as they were; a new statement is `422` on `account_id`
    (contract: PUT /v1/statements/{statement_id}, "An archived account")
    (contract: POST /v1/statements/{statement_id}/complete, "An archived account").

    A row in the completed one answers `ACCOUNT_ARCHIVED` before `LOCKED` and
    `IN_COMPLETED_RECONCILIATION` (contract: PUT /v1/transactions/{transaction_id},
    "Checked first"). After `POST /accounts/{id}/unarchive` a `PUT` of the draft's `name`,
    a revert and a complete again of the completed one, and a delete of the draft go
    through."""
    account = scratch.account()
    tx = scratch.row(account, "2026-04-15", -1200)["id"]
    done = scratch.statement(account, *APRIL, balances=CLOSING)["id"]
    draft = scratch.statement(
        account,
        "2026-05-01",
        "2026-05-31",
        balances=[
            {
                "currency_code": "PEN",
                "beginning_balance_cents": 946000,
                "ending_balance_cents": 946000,
            }
        ],
    )["id"]
    scratch.assign(tx, done)
    client.post(f"/statements/{done}/complete")
    scratch.archive(account)

    assert_refusal(
        refused(lambda: client.put(f"/transactions/{tx}", json_body={"amount_cents": -9999})),
        422,
        "VALIDATION_ERROR",
        "amount_cents",
        "ACCOUNT_ARCHIVED",
    )
    assert_refusal(
        refused(lambda: client.delete(f"/transactions/{tx}")),
        409,
        "CONFLICT",
        "transaction_id",
        "ACCOUNT_ARCHIVED",
    )
    assert_refusal(
        refused(lambda: scratch.statement(account, "2026-06-01", "2026-06-30", balances=OPENING)),
        422,
        "VALIDATION_ERROR",
        "account_id",
        "ACCOUNT_ARCHIVED",
    )

    before = {sid: client.get(f"/statements/{sid}") for sid in (draft, done)}
    assert (before[draft]["status"], before[done]["status"]) == (1, 2)
    for sid, current in before.items():
        path = f"/statements/{sid}"
        pen = _balance(current, "PEN")
        every_field = {
            "name": current["name"],
            "date_start": current["date_start"],
            "date_end": current["date_end"],
            "balances": [
                {
                    "currency_code": "PEN",
                    "beginning_balance_cents": pen["beginning_balance_cents"],
                    "ending_balance_cents": pen["ending_balance_cents"],
                }
            ],
        }
        err = refused(lambda path=path, body=every_field: client.put(path, json_body=body))
        assert_refusals(
            err,
            422,
            "VALIDATION_ERROR",
            {
                "name": "ACCOUNT_ARCHIVED",
                "date_start": "ACCOUNT_ARCHIVED",
                "date_end": "ACCOUNT_ARCHIVED",
                "balances.PEN.beginning_balance_cents": "ACCOUNT_ARCHIVED",
                "balances.PEN.ending_balance_cents": "ACCOUNT_ARCHIVED",
            },
        )
        assert set(err.fields.values()) == {ARCHIVED}
        assert_refusal(
            refused(
                lambda path=path, name=current["name"]: client.put(
                    path, json_body={"name": name + "-x"}
                )
            ),
            422,
            "VALIDATION_ERROR",
            "name",
            "ACCOUNT_ARCHIVED",
        )
        for call, route in (
            (client.post, f"{path}/complete"),
            (client.post, f"{path}/revert"),
            (client.delete, path),
        ):
            err = refused(lambda call=call, route=route: call(route))
            assert_refusal(err, 409, "CONFLICT", "statement_id", "ACCOUNT_ARCHIVED")
            assert err.fields == {"statement_id": ARCHIVED}
    assert {sid: client.get(f"/statements/{sid}") for sid in before} == before

    client.post(f"/accounts/{account}/unarchive")
    name = f"{before[draft]['name']}-r"
    assert client.put(f"/statements/{draft}", json_body={"name": name})["name"] == name
    assert client.post(f"/statements/{done}/revert")["status"] == 1
    assert client.post(f"/statements/{done}/complete")["status"] == 2
    assert client.delete(f"/statements/{draft}")["deleted_at"] is not None
