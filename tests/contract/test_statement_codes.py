"""Contract: an account's statement code and one statement per code per month.

A statement code is three capital letters naming the bank product an account belongs to,
and it begins the statement line of every line of the account in a completed
reconciliation (contract: "Bank Accounts", "Statement code"). Account management sets it
and the reconciliations browse groups accounts and their statements by it, so only the
engine can say what it takes and what it refuses. Pinned here:

  · it is set on the create, changed and cleared (`null`) with `PUT`, on an archived
    account too, and an account without one reads `null`;
  · `sig`, `SI`, `SIGN`, ` SIG`, `S1G` and `""` are each `422` `INVALID_FORMAT` on
    `statement_code`, on the create and on `PUT`, writing nothing;
  · two live accounts share a code only across currencies: the same code in the same
    currency is `409` `STATEMENT_CODE_EXISTS` on the create and on `PUT`, writing
    nothing, and a deleted account holds no code;
  · a person never carries one: `POST /people` refuses the field as `UNKNOWN_FIELD`,
    `PUT` gives a person a code only as `422` `PERSON_ACCOUNT` (`null` passes), and an
    account holding a code is not made a person (`409` `HAS_STATEMENT_CODE`) until the
    code is cleared;
  · one statement per code per month: a reconciliation under a code ending in a month
    another one under the code already ends in, and not its twin over exactly the same
    days, is `422` `STATEMENT_MONTH_TAKEN` on `date_end` from the create and the
    update (a card moved as one, `twin.date_end` naming its other half), and on
    `statement_code` from the account's `PUT` that would make such a pair; clearing a
    code never clashes, and a deleted reconciliation does not count.

Each test builds its own accounts under codes no account of the practice user holds, and
undoes everything (conftest.py `scratch`). Gating, target and the real-ledger guard:
conftest.py.
"""

from uuid import uuid4

from expense.errors import EngineError
from tests.contract.conftest import (
    account_body,
    assert_refusal,
    assert_refusals,
    free_statement_codes,
    reconciliation_body,
    refused,
)

MALFORMED = ("sig", "SI", "SIGN", " SIG", "S1G", "")


def _gone(client, account_id: str) -> bool:
    try:
        client.get(f"/accounts/{account_id}")
    except EngineError as err:
        return err.status == 404
    return False


def _set_code(client, account_id: str, code: str | None) -> str | None:
    """`PUT /accounts/{id}` with `statement_code` alone; the code the response reads."""
    return client.put(f"/accounts/{account_id}", json_body={"statement_code": code})[
        "statement_code"
    ]


def _recon_ids(client, account_id: str) -> list[str]:
    listed = client.get("/reconciliations", params={"account_id": account_id})
    return [item["id"] for item in listed["items"]]


# ---- the code itself ----------------------------------------------------------


def test_a_statement_code_is_set_changed_and_cleared(client, scratch, statuses):
    """`statement_code` is set on `POST /accounts` and set, changed or cleared with
    `PUT /accounts/{id}`, on an archived account too, and `null` when the account has
    none (contract: "Bank Accounts", "Statement code") (contract: POST /v1/accounts,
    "Optional") (contract: PUT /v1/accounts/{account_id}, "`statement_code`")."""
    first, second = free_statement_codes(client, 2)
    coded = scratch.account("PEN", first)
    assert statuses[-1] == 201
    plain = scratch.account("PEN")
    assert client.get(f"/accounts/{coded}")["statement_code"] == first
    assert client.get(f"/accounts/{plain}")["statement_code"] is None

    assert _set_code(client, coded, second) == second
    assert client.get(f"/accounts/{coded}")["statement_code"] == second
    assert _set_code(client, coded, None) is None
    assert client.get(f"/accounts/{coded}")["statement_code"] is None
    assert _set_code(client, plain, first) == first

    client.post(f"/accounts/{plain}/archive")
    client.put(f"/accounts/{plain}", json_body={"statement_code": second})
    assert client.get(f"/accounts/{plain}")["statement_code"] == second
    client.put(f"/accounts/{plain}", json_body={"statement_code": None})
    assert client.get(f"/accounts/{plain}")["statement_code"] is None


def test_a_malformed_statement_code_isrefused(client, scratch):
    """A statement code is exactly three capital letters, `A` to `Z`, compared as sent:
    `sig`, `SI`, `SIGN`, ` SIG`, `S1G` and `""` are each `422` on `statement_code`
    (`INVALID_FORMAT`) (contract: "Bank Accounts", "Statement code"), on the create
    (contract: POST /v1/accounts, "Validation") and on `PUT`
    (contract: PUT /v1/accounts/{account_id}, "`statement_code`"). Nothing is written:
    no account is created, and the account sent to keeps its code and `version`."""
    (code,) = free_statement_codes(client, 1)
    account = scratch.account("PEN", code)
    version = client.get(f"/accounts/{account}")["version"]
    for value in MALFORMED:
        body = account_body("PEN", value)
        scratch.accounts.append(body["id"])
        err = refused(lambda body=body: client.post("/accounts", json_body=body))
        assert_refusal(err, 422, "VALIDATION_ERROR", "statement_code", "INVALID_FORMAT")
        assert _gone(client, body["id"]), value

        err = refused(
            lambda value=value: client.put(
                f"/accounts/{account}", json_body={"statement_code": value}
            )
        )
        assert_refusal(err, 422, "VALIDATION_ERROR", "statement_code", "INVALID_FORMAT")
    after = client.get(f"/accounts/{account}")
    assert (after["statement_code"], after["version"]) == (code, version)


def test_a_code_is_shared_only_across_currencies(client, scratch, statuses):
    """Two live accounts share a code only when their currencies differ: a soles and a
    dollar account take one code, and a second account in the same currency with it is
    `409` on `statement_code` (`STATEMENT_CODE_EXISTS`), nothing written, on the
    create and on `PUT`. A deleted account does not hold its code
    (contract: "Bank Accounts", "Shared only across currencies")
    (contract: POST /v1/accounts, "Validation")
    (contract: PUT /v1/accounts/{account_id}, "`statement_code`")."""
    (code,) = free_statement_codes(client, 1)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)
    assert statuses[-1] == 201
    assert client.get(f"/accounts/{dollars}")["statement_code"] == code

    body = account_body("PEN", code)
    scratch.accounts.append(body["id"])
    err = refused(lambda: client.post("/accounts", json_body=body))
    assert_refusal(err, 409, "CONFLICT", "statement_code", "STATEMENT_CODE_EXISTS")
    assert _gone(client, body["id"])

    other = scratch.account("PEN")
    version = client.get(f"/accounts/{other}")["version"]
    err = refused(lambda: client.put(f"/accounts/{other}", json_body={"statement_code": code}))
    assert_refusal(err, 409, "CONFLICT", "statement_code", "STATEMENT_CODE_EXISTS")
    after = client.get(f"/accounts/{other}")
    assert (after["statement_code"], after["version"]) == (None, version)

    client.delete(f"/accounts/{soles}")
    assert _set_code(client, other, code) == code


def test_a_person_never_carries_a_code(client, scratch):
    """Only a real account carries a code, never a person
    (contract: "Bank Accounts", "Only a real account carries one"): `POST /people`
    does not take the field, `422` `UNKNOWN_FIELD` with nothing written
    (contract: POST /v1/people, "Forbidden"); a person reads `null`, and `PUT` giving
    it a code is `422` on `statement_code` (`PERSON_ACCOUNT`), nothing written, while
    `null` passes (contract: PUT /v1/accounts/{account_id}, "`statement_code`")."""
    (code,) = free_statement_codes(client, 1)
    new_id = str(uuid4())
    scratch.accounts.append(new_id)
    body = {
        "id": new_id,
        "name": f"contract-stmt-p-{new_id[:8]}",
        "currency_code": "PEN",
        "statement_code": code,
    }
    err = refused(lambda: client.post("/people", json_body=body))
    assert_refusal(err, 422, "VALIDATION_ERROR", "statement_code", "UNKNOWN_FIELD")
    assert _gone(client, new_id)

    person = scratch.person("PEN")
    read = client.get(f"/accounts/{person}")
    assert (read["is_person"], read["statement_code"]) == (True, None)
    err = refused(lambda: client.put(f"/accounts/{person}", json_body={"statement_code": code}))
    assert_refusal(err, 422, "VALIDATION_ERROR", "statement_code", "PERSON_ACCOUNT")
    after = client.get(f"/accounts/{person}")
    assert (after["statement_code"], after["version"]) == (None, read["version"])
    assert _set_code(client, person, None) is None


def test_an_account_holding_a_code_is_not_made_a_person(client, scratch):
    """`POST /accounts/{id}/make-person` on an account with a statement code is `409` on
    `account_id` (`HAS_STATEMENT_CODE`), nothing written (no `version` bump); cleared
    with `statement_code: null`, the account becomes a person
    (contract: POST /v1/accounts/{account_id}/make-person, "Refusals")."""
    (code,) = free_statement_codes(client, 1)
    account = scratch.account("PEN", code)
    version = client.get(f"/accounts/{account}")["version"]
    err = refused(lambda: client.post(f"/accounts/{account}/make-person"))
    assert_refusal(err, 409, "CONFLICT", "account_id", "HAS_STATEMENT_CODE")
    after = client.get(f"/accounts/{account}")
    assert (after["is_person"], after["statement_code"], after["version"]) == (
        False,
        code,
        version,
    )

    client.put(f"/accounts/{account}", json_body={"statement_code": None})
    made = client.post(f"/accounts/{account}/make-person")
    assert (made["is_person"], made["statement_code"]) == (True, None)


# ---- one statement per code per month ----------------------------------------


def test_one_statement_per_code_per_month_on_reconciliation_writes(client, scratch):
    """Among the live accounts sharing a code, a reconciliation whose `date_end` falls
    in the month another one's does must be that one's twin, on the other account over
    exactly the same days; anything else is `422` on `date_end`
    (`STATEMENT_MONTH_TAKEN`), nothing written
    (contract: "Bank Accounts", "One statement per code per month"), from the create
    (contract: POST /v1/reconciliations, "One statement per code per month") and the
    update, which moves a card statement as one, both halves judged and each named,
    `twin.date_end` for the other half, and never against each other
    (contract: PUT /v1/reconciliations/{reconciliation_id}, "One statement per code per month")."""
    (code,) = free_statement_codes(client, 1)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)
    half = scratch.reconciliation(soles, "2026-02-26", "2026-03-25")

    for account, start, end in (
        (soles, "2026-03-26", "2026-03-31"),  # the same account, the same month
        (dollars, "2026-03-01", "2026-03-25"),  # the other account, other days
    ):
        body = reconciliation_body(account, start, end)
        scratch.reconciliations.append(body["id"])
        err = refused(lambda body=body: client.post("/reconciliations", json_body=body))
        assert_refusal(err, 422, "VALIDATION_ERROR", "date_end", "STATEMENT_MONTH_TAKEN")
    assert _recon_ids(client, soles) == [half]
    assert _recon_ids(client, dollars) == []

    twin = scratch.reconciliation(dollars, "2026-02-26", "2026-03-25")
    assert _recon_ids(client, dollars) == [twin]

    april = scratch.reconciliation(soles, "2026-03-26", "2026-04-25")
    taken = "STATEMENT_MONTH_TAKEN"
    for recon, change, reasons in (
        (april, {"date_end": "2026-03-31"}, {"date_end": taken}),
        # The card moved into April, which `april` holds under the code: both halves.
        (
            twin,
            {"date_start": "2026-04-26", "date_end": "2026-04-30"},
            {"date_end": taken, "twin.date_end": taken},
        ),
    ):
        before = [client.get(f"/reconciliations/{r}") for r in (half, twin, april)]
        err = refused(
            lambda recon=recon, change=change: client.put(
                f"/reconciliations/{recon}", json_body=change
            )
        )
        assert_refusals(err, 422, "VALIDATION_ERROR", reasons)
        assert [client.get(f"/reconciliations/{r}") for r in (half, twin, april)] == before

    # Moved as one into a month no other statement holds, from either half.
    for recon, other, days in (
        (twin, half, ("2026-04-26", "2026-05-25")),
        (half, twin, ("2026-05-26", "2026-06-25")),
    ):
        moved = client.put(
            f"/reconciliations/{recon}", json_body={"date_start": days[0], "date_end": days[1]}
        )
        assert moved["twin"]["id"] == other
        for read in (moved, moved["twin"]):
            assert (read["date_start"], read["date_end"]) == days


def test_one_statement_per_code_per_month_on_the_accounts_code(client, scratch):
    """`PUT /accounts/{id}` setting a code that would make two reconciliations under it
    end in one month without being twins, one of this account's against one of the
    other account holding the code or two of its own, is `422` on `statement_code`
    (`STATEMENT_MONTH_TAKEN`), nothing written; clearing a code never clashes, an
    account without a code is never judged, and a deleted reconciliation does not count
    (contract: "Bank Accounts", "One statement per code per month")
    (contract: PUT /v1/accounts/{account_id}, "`statement_code`")."""
    first, second = free_statement_codes(client, 2)
    holder = scratch.account("PEN", first)
    holders = scratch.reconciliation(holder, "2026-03-01", "2026-03-20")
    joiner = scratch.account("USD")
    scratch.reconciliation(joiner, "2026-03-05", "2026-03-31")
    own = scratch.account("PEN")
    scratch.reconciliation(own, "2026-03-01", "2026-03-10")
    scratch.reconciliation(own, "2026-03-11", "2026-03-31")

    for account, code in ((joiner, first), (own, second)):
        version = client.get(f"/accounts/{account}")["version"]
        err = refused(
            lambda account=account, code=code: client.put(
                f"/accounts/{account}", json_body={"statement_code": code}
            )
        )
        assert_refusal(err, 422, "VALIDATION_ERROR", "statement_code", "STATEMENT_MONTH_TAKEN")
        after = client.get(f"/accounts/{account}")
        assert (after["statement_code"], after["version"]) == (None, version)

    assert _set_code(client, holder, None) is None
    client.put(f"/accounts/{holder}", json_body={"statement_code": first})
    client.delete(f"/reconciliations/{holders}")
    assert _set_code(client, joiner, first) == first


# ---- the card's other account --------------------------------------------------


def _partners(client, *account_ids: str) -> dict[str, str | None]:
    """`statement_partner_id` of each named account, as `GET /accounts` lists it,
    archived ones included."""
    listed = client.get("/accounts", params={"include_archived": "true"})
    read = {item["id"]: item["statement_partner_id"] for item in listed["items"]}
    return {account_id: read[account_id] for account_id in account_ids}


def test_a_cards_two_accounts_name_each_other_and_no_other_account_names_one(client, scratch):
    """`statement_partner_id` is the card's other account: the other live account of
    the caller's holding this account's statement code, so a soles and a dollar account
    sharing a code each name the other; it is `null` on an account with no code and on
    one whose code no other account holds (contract: "Bank Accounts", "Statement partner")
    (contract: GET /v1/accounts). The Reconciliations browse pairs a card's two accounts
    by this field alone."""
    card, lone = free_statement_codes(client, 2)
    soles = scratch.account("PEN", card)
    dollars = scratch.account("USD", card)
    plain = scratch.account("PEN")
    alone = scratch.account("USD", lone)
    assert _partners(client, soles, dollars, plain, alone) == {
        soles: dollars,
        dollars: soles,
        plain: None,
        alone: None,
    }


def test_an_archived_card_account_leaves_both_with_no_partner(client, scratch):
    """While one of a card's two accounts is archived both read `null`, and
    unarchiving it restores both
    (contract: "Bank Accounts", "While one of the two accounts is archived").
    The browse's new-statement form keeps to one account then."""
    (card,) = free_statement_codes(client, 1)
    soles = scratch.account("PEN", card)
    dollars = scratch.account("USD", card)
    scratch.archive(dollars)
    assert _partners(client, soles, dollars) == {soles: None, dollars: None}
    client.post(f"/accounts/{dollars}/unarchive")
    assert _partners(client, soles, dollars) == {soles: dollars, dollars: soles}
