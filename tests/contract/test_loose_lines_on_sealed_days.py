"""Contract: `LOOSE_LINES_ON_SEALED_DAYS`, a close or an upload refused while a line in no
statement sits on a day the close would seal
(contract: POST /v1/statements/{statement_id}/complete, "No line in no statement on a day the
completion seals") (contract: POST /v1/statements/import, "Matching"). The app lists the
refusal's lines from its `details`, so this file pins what it reads:

  · a close refused for one loose line is `422` on `statement_id`, its `details` the line and
    a count of 1, nothing written; the request the message names answers `200` with that line;
    once the line is deleted the close goes through;
  · the ids come in the order `?unassigned_in_period_of=<id>&sort=statement` lists them, and a
    flagged line on a day that stays open is listed there but is no id of the refusal;
  · the previous statement's last day is sealed once that statement is completed: a line left
    on it then refuses the next statement's close;
  · an upload's dry run and its apply are refused alike, on `file`, for a line in no statement
    and for a line of the draft the paper does not print (taken out, so in no statement), the
    request the message names answering `200`, nothing written; with both lines deleted the
    apply closes the month;
  · 201 loose lines answer 200 ids and a `count` of 201, on a close and on an upload's dry run,
    the ids the first 200 of the review list.

A flagged line on the open last day letting a close through is in test_sealed_periods.py
(`test_a_row_filed_nowhere_on_the_open_last_day_does_not_stop_complete`); the review list
itself is in test_bank_lines.py; an upload's dry run flagging a line on a day that stays open is
in test_statement_import.py.

Each test builds its own accounts (conftest.py `scratch`). Gating, target and the real-ledger
guard: conftest.py.
"""

from datetime import date
from functools import partial

import pytest

from tests.contract.conftest import (
    DRAWN_LAST4,
    PaperRow,
    assert_refusal,
    free_statement_codes,
    refused,
    refused_keeping,
    savings_paper,
    send_statement,
    transaction_count,
)

MARCH = ("2026-03-01", "2026-03-31")
APRIL = ("2026-04-01", "2026-04-30")
LOOSE = "LOOSE_LINES_ON_SEALED_DAYS"
#: The most ids a refusal names.
CAP = 200


def _soles(ending: int) -> list[dict]:
    return [{"currency_code": "PEN", "beginning_balance_cents": 0, "ending_balance_cents": ending}]


def _review(client, statement: str) -> list[str]:
    """Every id of the statement's review list, in its order, over all its pages
    (contract: GET /v1/bank-lines, "Read in the statement's order, and only in it")."""
    ids: list[str] = []
    after = None
    while True:
        params = {"unassigned_in_period_of": statement, "sort": "statement"}
        page = client.get("/bank-lines", params={**params, **({"after": after} if after else {})})
        ids += [row["id"] for row in page["items"]]
        after = page["next_cursor"]
        if after is None:
            return ids


def _assert_loose(err, key: str, ids: list[str], count: int) -> None:
    """The refusal is `422` `LOOSE_LINES_ON_SEALED_DAYS` on `key`, naming `ids` in that order
    and the full `count`."""
    assert_refusal(err, 422, "VALIDATION_ERROR", key, LOOSE)
    assert err.details == {"bank_line_ids": ids, "count": count}, err.details


def _coded(scratch) -> str:
    """A bank account with a statement code, numbered as a made-up paper prints it."""
    code = free_statement_codes(scratch.client, 1)[0]
    return scratch.account(code=code, last4=DRAWN_LAST4)


def _held(client, account: str, statement: str):
    """What a refusal must leave as it was: the statement, the account's transaction count and
    its loose and filed lines as the statement's review list reads them."""
    return (
        client.get(f"/statements/{statement}"),
        transaction_count(client, account),
        _review(client, statement),
    )


def test_a_close_refused_for_one_loose_line_names_it_and_writes_nothing(client, scratch):
    account = scratch.account()
    filed = scratch.row(account, "2026-03-10", -1000)
    loose = scratch.row(account, "2026-03-15", -500)["bank_line_id"]
    statement = scratch.statement(account, *MARCH, balances=_soles(-1000))["id"]
    scratch.assign(filed["id"], statement)

    err = refused_keeping(
        lambda: _held(client, account, statement),
        lambda: client.post(f"/statements/{statement}/complete"),
    )
    _assert_loose(err, "statement_id", [loose], 1)

    # The request the message names lists the line.
    assert _review(client, statement) == [loose]

    client.delete(f"/bank-lines/{loose}")
    assert client.post(f"/statements/{statement}/complete")["status"] == 2


def test_the_ids_come_in_the_review_lists_order_and_leave_out_a_flagged_line(client, scratch):
    """Lines made out of date order, two of them on one day, come back by day then by when
    they were made; the line on the open last day is on the review list, not in the refusal."""
    account = scratch.account()
    filed = scratch.row(account, "2026-03-02", -1000)
    late = scratch.row(account, "2026-03-20", -100)["bank_line_id"]
    early = scratch.row(account, "2026-03-05", -100)["bank_line_id"]
    middle_first = scratch.row_at(account, scratch.at("2026-03-12", 9), -100)["bank_line_id"]
    middle_second = scratch.row_at(account, scratch.at("2026-03-12", 9), -100)["bank_line_id"]
    flagged = scratch.row(account, "2026-03-31", -100)["bank_line_id"]
    statement = scratch.statement(account, *MARCH, balances=_soles(-1000))["id"]
    scratch.assign(filed["id"], statement)

    err = refused(lambda: client.post(f"/statements/{statement}/complete"))
    ids = [early, middle_first, middle_second, late]
    _assert_loose(err, "statement_id", ids, 4)
    listed = _review(client, statement)
    assert flagged in listed and flagged not in ids
    assert [line for line in listed if line in ids] == ids


def test_the_previous_statements_last_day_is_sealed_once_it_is_completed(client, scratch):
    """March completed leaves its last day open: a line in no statement there is flagged. April's
    close seals that day, so the same line refuses it, and April closes once it is deleted."""
    account = scratch.account()
    march_row = scratch.row(account, "2026-03-10", -1000)
    stray = scratch.row(account, "2026-03-31", -100)["bank_line_id"]
    march = scratch.statement(account, *MARCH, balances=_soles(-1000))["id"]
    scratch.assign(march_row["id"], march)
    assert client.post(f"/statements/{march}/complete")["status"] == 2

    april_row = scratch.row(account, "2026-04-10", -2000)
    april = scratch.statement(
        account,
        *APRIL,
        balances=[
            {
                "currency_code": "PEN",
                "beginning_balance_cents": -1000,
                "ending_balance_cents": -3000,
            }
        ],
    )["id"]
    scratch.assign(april_row["id"], april)

    err = refused(lambda: client.post(f"/statements/{april}/complete"))
    _assert_loose(err, "statement_id", [stray], 1)

    client.delete(f"/bank-lines/{stray}")
    assert client.post(f"/statements/{april}/complete")["status"] == 2


def test_an_upload_refused_for_a_loose_line_and_a_line_taken_out_writes_nothing(client, scratch):
    """The dry run and the apply are refused alike for two lines: one in no statement, one in the
    draft that the paper does not print, which the upload takes out and so counts. Both sit on
    sealed days; the ids come by day, and the request the message names lists exactly them."""
    account = _coded(scratch)
    loose = scratch.row(account, "2026-03-08", -300)["bank_line_id"]
    draft = scratch.statement(account, *MARCH, "PEN")["id"]
    held = scratch.row(account, "2026-03-15", -700)
    scratch.assign(held["id"], draft)
    paper = savings_paper(
        [PaperRow(date(2026, 3, 5), "COMPRA UNO", -1000)],
        before_cents=100000,
        start=date(2026, 3, 1),
        end=date(2026, 3, 31),
    )
    ids = [loose, held["bank_line_id"]]

    for dry_run in (True, False):
        err = refused_keeping(
            lambda: _held(client, account, draft),
            partial(send_statement, client, account, paper, dry_run=dry_run),
        )
        _assert_loose(err, "file", ids, 2)

    # The request the message names answers 200 with exactly those lines.
    named = client.get("/bank-lines", params={"ids": ",".join(ids), "limit": len(ids)})["items"]
    assert sorted(row["id"] for row in named) == sorted(ids)

    for line in ids:
        client.delete(f"/bank-lines/{line}")
    done = send_statement(client, account, paper, dry_run=False)
    scratch.took(done)
    assert done["statement"]["status"] == 2


@pytest.mark.parametrize("through", ["close", "upload"])
def test_201_loose_lines_answer_200_ids_and_the_full_count(client, scratch, through):
    if through == "close":
        account = scratch.account()
    else:
        account = _coded(scratch)
    filed = scratch.row(account, "2026-03-02", -1000)
    day = scratch.at("2026-03-10")
    bodies = [scratch.body(account, -1, when=day) for _ in range(CAP + 1)]
    client.post("/transactions/batch", json_body={"transactions": bodies})
    draft = scratch.statement(account, *MARCH, balances=_soles(-1000))["id"]
    scratch.assign(filed["id"], draft)
    paper = savings_paper(
        [PaperRow(date(2026, 3, 2), "COMPRA UNO", -1000)],
        before_cents=100000,
        start=date(2026, 3, 1),
        end=date(2026, 3, 31),
    )

    if through == "close":
        err = refused(lambda: client.post(f"/statements/{draft}/complete"))
        key = "statement_id"
    else:
        err = refused(lambda: send_statement(client, account, paper, dry_run=True))
        key = "file"
    listed = _review(client, draft)
    assert len(listed) == CAP + 1
    _assert_loose(err, key, listed[:CAP], CAP + 1)
