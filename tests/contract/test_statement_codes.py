"""Contract: an account's statement code and one statement per account per month.

A statement code is three capital letters naming the bank product an account belongs to,
and it begins the statement line of every line of the account's completed statements, in
every currency (contract: "What an account is", "Statement code"). The code is the
account's, not a currency's, and a person carries one like any account. Pinned here:

  · it is set on the create, changed and cleared (`null`) with `PUT`, on an archived
    account too, and an account without one reads `null`;
  · `sig`, `SI`, `SIGN`, ` SIG`, `S1G` and `""` are each `422` `INVALID_FORMAT` on
    `statement_code`, on the create and on `PUT`, writing nothing;
  · one account per code: a second live account of the caller's with the same code, in any
    currency, of either kind, archived or not, is `409` `STATEMENT_CODE_EXISTS` on the create
    and on `PUT`, writing nothing, and a deleted account holds no code;
  · a person carries a code like any account: set on the create, changed and cleared with
    `PUT`, held against every other live account, kept when it changes kind in either
    direction, and it begins no statement line;
  · one statement per account per month: a statement ending in a month another live
    statement of the account ends in, a draft or a completed one, with a code or without
    one, is `422` `STATEMENT_MONTH_TAKEN` on `date_end` from `POST` and `PUT /statements`,
    writing nothing; a deleted statement does not count, another account's never clashes,
    and the account's code changes none of it.

Each test builds its own accounts under codes no account of the practice user holds, and
undoes everything (conftest.py `scratch`). Gating, target and the real-ledger guard:
conftest.py.
"""

from datetime import date

import pytest

from expense.errors import EngineError
from tests.contract.conftest import (
    PaperRow,
    account_body,
    assert_refusal,
    free_statement_codes,
    refused_keeping,
    refused_writing_nothing,
    savings_paper,
    send_statement,
    statement_create_body,
)

MALFORMED = ("sig", "SI", "SIGN", " SIG", "S1G", "")


def _set_code(client, account_id: str, code: str | None) -> str | None:
    """`PUT /accounts/{id}` with `statement_code` alone; the code the response reads."""
    return client.put(f"/accounts/{account_id}", json_body={"statement_code": code})[
        "statement_code"
    ]


def _code_of(client, account_id: str) -> str | None:
    return client.get(f"/accounts/{account_id}")["statement_code"]


def _put_code(client, account_id: str, code: str):
    """The call `PUT /accounts/{id}` giving the account `code`, for a test of its refusal."""
    return lambda: client.put(f"/accounts/{account_id}", json_body={"statement_code": code})


def _post_account(client, scratch, *codes: str, **kwargs):
    """The call `POST /accounts` on a new account holding `codes`, its id taken on by
    `scratch`, for a test of its refusal."""
    body = account_body(*codes, **kwargs)
    scratch.accounts.append(body["id"])
    return lambda: client.post("/accounts", json_body=body)


# ---- the code itself ----------------------------------------------------------


def test_a_statement_code_is_set_changed_and_cleared(client, scratch, statuses):
    """`statement_code` is set on `POST /accounts` and set, changed or cleared with
    `PUT /accounts/{id}`, on an archived account too, and `null` when the account has
    none; it is the account's, so one of two currencies carries it once
    (contract: "What an account is", "Statement code")
    (contract: POST /v1/accounts, "Validation")."""
    first, second = free_statement_codes(client, 2)
    coded = scratch.account("PEN", "USD", code=first)
    assert statuses[-1] == 201
    plain = scratch.account()
    held = client.get(f"/accounts/{coded}")
    assert held["statement_code"] == first
    assert [c["currency_code"] for c in held["currencies"]] == ["PEN", "USD"]
    assert _code_of(client, plain) is None

    assert _set_code(client, coded, second) == second
    assert _code_of(client, coded) == second
    assert _set_code(client, coded, None) is None
    assert _code_of(client, coded) is None
    assert _set_code(client, plain, first) == first

    scratch.archive(plain)
    assert _set_code(client, plain, second) == second
    assert _code_of(client, plain) == second
    assert _set_code(client, plain, None) is None
    assert _code_of(client, plain) is None


def test_a_malformed_statement_code_is_refused(client, scratch):
    """A statement code is exactly three capital letters, `A` to `Z`, compared as sent:
    `sig`, `SI`, `SIGN`, ` SIG`, `S1G` and `""` are each `422` on `statement_code`
    (`INVALID_FORMAT`) (contract: "What an account is", "Statement code"), on the create
    and on `PUT` (contract: PUT /v1/accounts/{account_id}). Nothing is written: every
    account the caller has reads the same, `version` and `updated_at` included, after
    each refusal."""
    (code,) = free_statement_codes(client, 1)
    account = scratch.account(code=code)
    for value in MALFORMED:
        err = refused_writing_nothing(client, _post_account(client, scratch, code=value))
        assert_refusal(err, 422, "VALIDATION_ERROR", "statement_code", "INVALID_FORMAT")
        err = refused_writing_nothing(client, _put_code(client, account, value))
        assert_refusal(err, 422, "VALIDATION_ERROR", "statement_code", "INVALID_FORMAT")
    assert _code_of(client, account) == code


def test_one_account_holds_a_code_whatever_its_currencies(client, scratch):
    """A second live account of the caller's with a code another holds is `409` on
    `statement_code` (`STATEMENT_CODE_EXISTS`), nothing written, on the create and on
    `PUT`, whatever its currencies: a dollar account is refused the code of a soles one.
    The account holding it keeps it while archived; a deleted account holds no code
    (contract: "What an account is", "One account per code")
    (contract: PUT /v1/accounts/{account_id})."""
    (code,) = free_statement_codes(client, 1)
    coded_account = scratch.account("PEN", code=code)
    other = scratch.account("PEN", "USD")

    def refusals() -> None:
        for call in (
            _post_account(client, scratch, "PEN", code=code),
            _post_account(client, scratch, "USD", code=code),
            _post_account(client, scratch, "PEN", "USD", code=code),
            _put_code(client, other, code),
        ):
            err = refused_writing_nothing(client, call)
            assert_refusal(err, 409, "CONFLICT", "statement_code", "STATEMENT_CODE_EXISTS")

    refusals()
    scratch.archive(coded_account)
    refusals()
    client.post(f"/accounts/{coded_account}/unarchive")
    client.delete(f"/accounts/{coded_account}")
    assert _set_code(client, other, code) == code
    assert _code_of(client, other) == code


def test_a_person_carries_a_code_like_any_account(client, scratch):
    """A person is set a code on the create, and changed and cleared it with `PUT`, as any
    account is; it is held against every other live account of either kind
    (`STATEMENT_CODE_EXISTS`), and it holds against a bank account's code the same way. A
    person has no statement, so the code is a label: its lines read a `null` statement
    line. An account keeps its code when it changes kind, in either direction
    (contract: "What an account is", "A person carries a code like any account")."""
    first, second, third = free_statement_codes(client, 3)
    person = scratch.account("PEN", "USD", code=first, person=True)
    read = client.get(f"/accounts/{person}")
    assert (read["is_person"], read["statement_code"]) == (True, first)
    assert _set_code(client, person, second) == second
    assert _set_code(client, person, None) is None
    assert _set_code(client, person, first) == first

    bank = scratch.account(code=second)
    err = refused_writing_nothing(client, _put_code(client, bank, first))
    assert_refusal(err, 409, "CONFLICT", "statement_code", "STATEMENT_CODE_EXISTS")
    err = refused_writing_nothing(client, _put_code(client, person, second))
    assert_refusal(err, 409, "CONFLICT", "statement_code", "STATEMENT_CODE_EXISTS")
    err = refused_writing_nothing(client, _post_account(client, scratch, code=first, person=True))
    assert_refusal(err, 409, "CONFLICT", "statement_code", "STATEMENT_CODE_EXISTS")

    row = scratch.row(person, "2026-03-05")
    line = client.get(f"/bank-lines/{row['bank_line_id']}")
    assert (line["statement_line"], line["statement_place"]) == (None, None)

    made = client.post(f"/accounts/{bank}/make-person")
    assert (made["is_person"], made["statement_code"]) == (True, second)
    assert _code_of(client, bank) == second
    back = client.post(f"/accounts/{bank}/make-account")
    assert (back["is_person"], back["statement_code"]) == (False, second)
    assert client.post(f"/accounts/{person}/make-account")["statement_code"] == first
    assert _set_code(client, person, third) == third


# ---- one statement per account per month ----------------------------------------


def _statements(client, account_id: str) -> list[dict]:
    return client.get("/statements", params={"account_id": account_id})["items"]


def _refused_keeping_statements(client, account_id: str, call) -> EngineError:
    """The refusal of `call`, with every statement of the account read the same before
    and after it."""
    return refused_keeping(lambda: _statements(client, account_id), call)


def _post_statement(client, scratch, account_id: str, start: str, end: str):
    body = statement_create_body(account_id, start, end)
    scratch.statements.append(body["id"])
    return lambda: client.post("/statements", json_body=body)


def _put_days(client, statement_id: str, start: str, end: str):
    days = {"date_start": start, "date_end": end}
    return lambda: client.put(f"/statements/{statement_id}", json_body=days)


@pytest.mark.parametrize("coded", [True, False], ids=["with a code", "without a code"])
def test_one_statement_per_account_per_month(client, scratch, coded):
    """An account has at most one live statement in each calendar month, the month its
    `date_end` falls in: another one is `422` on `date_end` (`STATEMENT_MONTH_TAKEN`),
    from the create and from `PUT /statements` moving the days, nothing written, the
    message naming the statement it clashes with. A draft and a completed statement count
    alike, with a code or without one; a statement keeps its own month on an edit, another
    account's statement never clashes, a deleted statement does not count, and setting or
    changing the account's code judges no month
    (contract: "Statements", "The days")
    (contract: POST /v1/statements, "Order")."""
    first, second = free_statement_codes(client, 2)
    account = scratch.account(code=first) if coded else scratch.account()
    march = scratch.statement(account, "2026-03-01", "2026-03-20")
    named = march["name"]
    row = scratch.row(account, "2026-04-05")
    if coded:  # a coded account completes only with the order its bank's paper sets
        paper = savings_paper(
            [PaperRow(date(2026, 4, 5), "COMPRA", -1000)],
            start=date(2026, 4, 1),
            end=date(2026, 4, 20),
            before_cents=100000,
        )
        scratch.took(send_statement(client, account, paper, dry_run=False))
        april = client.get(f"/statements/{scratch.statements[-1]}")
    else:
        april = scratch.completed(account, "2026-04-01", "2026-04-20", row["id"])
    assert april["status"] == 2
    may = scratch.statement(account, "2026-05-01", "2026-05-10")["id"]

    for start, end in (("2026-03-21", "2026-03-31"), ("2026-04-21", "2026-04-30")):
        err = _refused_keeping_statements(
            client, account, _post_statement(client, scratch, account, start, end)
        )
        assert_refusal(err, 422, "VALIDATION_ERROR", "date_end", "STATEMENT_MONTH_TAKEN")
    err = _refused_keeping_statements(
        client, account, _put_days(client, may, "2026-03-21", "2026-03-31")
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "date_end", "STATEMENT_MONTH_TAKEN")
    assert named in err.fields["date_end"]
    err = _refused_keeping_statements(
        client, account, _put_days(client, may, "2026-04-21", "2026-04-30")
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "date_end", "STATEMENT_MONTH_TAKEN")
    assert april["name"] in err.fields["date_end"]

    # Its own month on an edit, and another account's days in a month taken here.
    moved = _put_days(client, may, "2026-05-02", "2026-05-20")()
    assert (moved["date_start"], moved["date_end"]) == ("2026-05-02", "2026-05-20")
    neighbour = scratch.account()
    scratch.statement(neighbour, "2026-03-21", "2026-03-31")

    # The code is the account's: setting or changing it judges no month and leaves the
    # statements, their order included, as they were. An account without a code reads its
    # statements' `unplaced_count` and `shared_place_count` `null`, so those two follow it.
    def comparable(items: list[dict]) -> list[dict]:
        gone = () if coded else ("unplaced_count", "shared_place_count")
        return [{k: v for k, v in item.items() if k not in gone} for item in items]

    before = comparable(_statements(client, account))
    assert _set_code(client, account, second) == second
    assert comparable(_statements(client, account)) == before

    # A deleted statement does not count.
    client.delete(f"/statements/{march['id']}")
    moved = _put_days(client, may, "2026-03-21", "2026-03-31")()
    assert (moved["date_start"], moved["date_end"]) == ("2026-03-21", "2026-03-31")
