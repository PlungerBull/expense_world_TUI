"""Contract: sealed periods.

A completed statement seals its account's days, in every currency, but the last, which
seals once the account's next statement is completed too
(contract: "Transactions (Ledger)", "Sealed periods"). The app computes none of it:
it reports every refusal by reading the engine's `fields` key and message. The unit
suite fakes those 422s; this file is the only place they are checked against the
engine:

  · the wall: five doors refuse a row dated on a sealed day, each naming its own
    key, the message naming the period; the last local minute of the last sealed
    day is inside, the next day is not;
  · a move onto a sealed day, through `PUT /transactions/{id}` and `PUT /bank-lines/{id}`:
    `date` moved in is `SEALED_PERIOD` on `date`; `account_id`, `currency_code` or both
    moved in is `SEALED_PERIOD` on each of those sent; the date moved with them, on
    `date` alone; the row read back as it was;
  · a statement's last day stays open until the account's next statement is
    completed, is sealed under the statement's own name once it is, and opens
    again when that next statement is reverted;
  · a draft seals nothing, and revert opens the wall again;
  · a line in a draft can be dated on a day another completed statement seals, and the writes
    that would leave it in no statement there are refused `SEALED_PERIOD` on `statement_id`,
    naming the sealing statement, nothing written: unassigning it (`PUT /transactions/{id}` or
    `PUT /bank-lines/{id}`) and deleting its draft; deleting the line itself is allowed, and
    then the draft deletes;
  · a `PUT /transactions/{id}` sending its `date` unchanged beside a new category is `200` for
    a line on a sealed day outside a completed statement, and `LOCKED` on `date` alone inside
    one;
  · a row in the period filed nowhere does not stop `complete`, whose answer flags
    its line in `review_lines`, and its day seals with the rest;
  · `warnings` / `coverage_gap` report a skipped stretch, and are empty/null
    when there is none; revert carries neither;
  · statements of one account may not share a day, and may not run backwards;
  · the account's closed days hold for a currency added later: a soles-only account with
    a completed statement takes dollars (`201`), the statement still holding soles only;
    a dollar row on a sealed day is `SEALED_PERIOD` as a soles row is, one the day after
    the statement is taken, nothing written by the refusal; reverted, the statement still
    holds soles only and the dollar row on that day is taken.

Left out: a dollar line placed in a draft giving it dollar balances and the close's
`not_covered` notes for a currency the statement holds no balances for (both in
test_statement_currencies.py), and a statement that holds the added currency.

Each test builds its own accounts (conftest.py `scratch`), and every row it sends, a
refused one included, is in its cleanup before the call, so a row the engine takes after
all is still removed. Gating, target and the real-ledger guard: conftest.py.
"""

import pytest

from tests.contract.conftest import (
    LOOSE_LINES_ON_SEALED_DAYS,
    all_accounts,
    assert_refusal,
    assert_refusals,
    balance_of,
    live_ids,
    read_signed,
    refused,
    refused_keeping,
    refused_line_write,
    statement_codes,
    transaction_count,
)

MARCH = ("2026-03-01", "2026-03-31")
APRIL = ("2026-04-01", "2026-04-30")
JANUARY = ("2026-01-01", "2026-01-31")


def _soles(ending: int) -> list[dict]:
    """The soles balances of a statement beginning at 0 and ending at `ending`."""
    return [{"currency_code": "PEN", "beginning_balance_cents": 0, "ending_balance_cents": ending}]


@pytest.fixture
def sealed_march(client, scratch):
    """An account holding soles and dollars whose March 2026 is completed, plus one row
    outside it (April 10) and one in it filed nowhere (March 12): the completed statement
    as the engine reads it, the outside row, the loose one. Its sealed days are March 1 to
    30: the 31st waits for April's statement."""
    account = scratch.account("PEN", "USD")
    inside = scratch.row(account, "2026-03-10")
    loose = scratch.row(account, "2026-03-12")
    march = scratch.completed(account, *MARCH, inside["id"])
    outside = scratch.row(account, "2026-04-10")
    return account, march, outside, loose


@LOOSE_LINES_ON_SEALED_DAYS
def test_the_wall_on_create_and_batch(client, scratch, sealed_march):
    account, march, _, _ = sealed_march
    when = scratch.at("2026-03-15")
    err = scratch.refused_row(account, when)
    assert_refusal(err, 422, "VALIDATION_ERROR", "date", "SEALED_PERIOD")
    assert march["name"] in err.fields["date"]

    err = scratch.refused_row(account, when, batch=True)
    assert_refusal(err, 422, "VALIDATION_ERROR", "transactions.0.date", "SEALED_PERIOD")
    assert march["name"] in err.fields["transactions.0.date"]


@LOOSE_LINES_ON_SEALED_DAYS
def test_the_wall_holds_in_the_accounts_other_currency(client, scratch, sealed_march):
    """The days are the account's: a dollar row, in a currency the statement holds no
    balances for, is refused on a sealed day too."""
    account, march, _, _ = sealed_march
    err = scratch.refused_row(account, scratch.at("2026-03-15"), "USD")
    assert_refusal(err, 422, "VALIDATION_ERROR", "date", "SEALED_PERIOD")
    assert march["name"] in err.fields["date"]


@LOOSE_LINES_ON_SEALED_DAYS
def test_the_wall_is_whole_days_in_the_display_timezone(client, scratch, sealed_march):
    """23:59 local on the last sealed day (March 30) is inside; 00:00 of the next
    day, the statement's own last day, is not."""
    account, *_ = sealed_march
    err = scratch.refused_row(account, scratch.at("2026-03-30", 23, 59))
    assert_refusal(err, 422, "VALIDATION_ERROR", "date", "SEALED_PERIOD")
    scratch.row_at(account, scratch.at("2026-03-31", 0, 0))


@LOOSE_LINES_ON_SEALED_DAYS
def test_the_last_day_seals_once_the_next_statement_is_completed(client, scratch, sealed_march):
    """March is completed and April is not: March 31 takes a row. April completed:
    March 31 is refused, named under March's own statement, up to 23:59 local,
    while April 1 is sealed and April 30, April's own last day, takes a row. April
    reverted: March 31 takes a row again."""
    account, march, outside, _ = sealed_march
    scratch.row(account, "2026-03-31")

    april = scratch.statement(account, *APRIL, balances=_soles(-1000))
    scratch.assign(outside["id"], april["id"])
    # A draft next statement seals nothing.
    scratch.row_at(account, scratch.at("2026-03-31", 23, 59))
    client.post(f"/statements/{april['id']}/complete")

    for hour, minute in ((0, 0), (12, 0), (23, 59)):
        err = scratch.refused_row(account, scratch.at("2026-03-31", hour, minute))
        assert_refusal(err, 422, "VALIDATION_ERROR", "date", "SEALED_PERIOD")
        assert march["name"] in err.fields["date"]
        assert april["name"] not in err.fields["date"]
    err = scratch.refused_row(account, scratch.at("2026-04-01", 0, 0))
    assert_refusal(err, 422, "VALIDATION_ERROR", "date", "SEALED_PERIOD")
    assert april["name"] in err.fields["date"]
    scratch.row_at(account, scratch.at("2026-04-30", 23, 59))

    client.post(f"/statements/{april['id']}/revert")
    scratch.row(account, "2026-03-31")


def _unwritten_refusal(client, path: str, body: dict, keys: set[str], name: str) -> None:
    """`body` sent to `path` is `422` `SEALED_PERIOD` on exactly `keys`, each field naming
    the statement `name`, and the resource reads as before."""
    err = refused_keeping(
        lambda: client.get(path, params={"debit_as_negative": "true"}),
        lambda: client.put(path, json_body=body),
    )
    assert_refusals(err, 422, "VALIDATION_ERROR", dict.fromkeys(keys, "SEALED_PERIOD"))
    assert all(name in err.fields[key] for key in keys), err.fields


@LOOSE_LINES_ON_SEALED_DAYS
def test_the_wall_on_moving_a_row_in(client, scratch, sealed_march):
    """Moving the date in names `date`; moving the account, the currency or both in names
    each of `account_id` and `currency_code` sent (Home's bulk `b` reports those keys);
    moving the date with them names `date` alone; `PUT /bank-lines/{id}` moving the line in
    answers as `PUT /transactions/{id}`. Each leaves the row as it was
    (contract: "Transactions (Ledger)", "Sealed periods")
    (contract: PUT /v1/transactions/{transaction_id}, "Moving a transaction")."""
    account, march, outside, loose = sealed_march
    name = march["name"]
    other = scratch.account("PEN", "USD")
    stray = scratch.row(other, "2026-03-15")

    cases = [
        (outside["id"], {"date": scratch.at("2026-03-15")}, {"date"}),
        (stray["id"], {"account_id": account}, {"account_id"}),
        (loose["id"], {"currency_code": "USD"}, {"currency_code"}),
        (
            stray["id"],
            {"account_id": account, "currency_code": "USD"},
            {"account_id", "currency_code"},
        ),
        (stray["id"], {"date": scratch.at("2026-03-16"), "account_id": account}, {"date"}),
    ]
    for tx_id, body, keys in cases:
        _unwritten_refusal(client, f"/transactions/{tx_id}", body, keys, name)

    line = client.get(f"/transactions/{stray['id']}")["bank_line_id"]
    body = {"account_id": account, "currency_code": "PEN"}
    err = refused_line_write(client, line, body)
    assert_refusals(err, 422, "VALIDATION_ERROR", dict.fromkeys(body, "SEALED_PERIOD"))
    assert read_signed(client, stray["id"])["account_id"] == other


@LOOSE_LINES_ON_SEALED_DAYS
def test_the_wall_on_an_opening_balance(client, scratch, sealed_march):
    account, march, _, _ = sealed_march
    err = refused(lambda: scratch.opening_balance(account, "2026-03-20"))
    assert_refusal(err, 422, "VALIDATION_ERROR", "date", "SEALED_PERIOD")
    assert march["name"] in err.fields["date"]


@LOOSE_LINES_ON_SEALED_DAYS
def test_revert_opens_the_wall(client, scratch, sealed_march):
    account, march, _, _ = sealed_march
    client.post(f"/statements/{march['id']}/revert")
    scratch.row(account, "2026-03-15")


@pytest.fixture
def soles_march_then_dollars(client, scratch):
    """A soles-only account whose March 2026 is completed with one soles row, then given
    dollars: the account and the completed statement. Sealed days: March 1 to 30; April 1 is
    after the statement."""
    account = scratch.account("PEN")
    inside = scratch.row(account, "2026-03-10")
    march = scratch.completed(account, *MARCH, inside["id"])
    assert statement_codes(march) == ["PEN"]
    client.post(f"/accounts/{account}/currencies", json_body={"currency_code": "USD"})
    return account, march


def test_a_soles_account_with_a_completed_statement_takes_dollars(client, scratch):
    """Builds its own account (the fixture adds the dollars at once; this test needs the
    account and the statement as they were before the add). The add is `201` with the
    account's currencies soles then dollars at `0`, its `version` unmoved, and the
    completed statement is read as it was: soles only, still completed
    (contract: POST /v1/accounts/{account_id}/currencies)."""
    account = scratch.account("PEN")
    inside = scratch.row(account, "2026-03-10")
    march = scratch.completed(account, *MARCH, inside["id"])
    assert (march["status"], statement_codes(march)) == (2, ["PEN"])
    before = client.get(f"/accounts/{account}")
    assert [c["currency_code"] for c in before["currencies"]] == ["PEN"]

    added = client.post(f"/accounts/{account}/currencies", json_body={"currency_code": "USD"})

    assert [c["currency_code"] for c in added["currencies"]] == ["PEN", "USD"]
    assert added["currencies"][1]["current_balance_cents"] == 0
    assert added["version"] == before["version"]
    assert client.get(f"/accounts/{account}") == added
    assert client.get(f"/statements/{march['id']}") == march


def test_a_dollar_row_on_a_sealed_day_is_refused_and_one_after_it_is_taken(
    client, scratch, soles_march_then_dollars
):
    """March 15 is sealed for the dollars added after March was completed, named under
    March's own statement, as it is for soles (the control: the same row in soles is refused
    in the same words); the same dollar row with only its date moved to April 1, the day after
    the statement, is taken, so the seal is the only thing the refused row broke. The
    refusal writes nothing: the account, the statement and the account's rows read the
    same after
    (contract: "Transactions (Ledger)", "Sealed periods")
    (contract: POST /v1/accounts/{account_id}/currencies)."""
    account, march = soles_march_then_dollars
    before = (
        all_accounts(client),
        client.get(f"/statements/{march['id']}"),
        live_ids(client, account),
        transaction_count(client, account),
    )
    sealed = scratch.at("2026-03-15")

    errors = [scratch.refused_row(account, sealed, code) for code in ("USD", "PEN")]
    errors.append(scratch.refused_row(account, sealed, "USD", batch=True))
    for err, key in zip(errors, ("date", "date", "transactions.0.date"), strict=True):
        assert_refusal(err, 422, "VALIDATION_ERROR", key, "SEALED_PERIOD")
        assert march["name"] in err.fields[key]
    assert errors[0].fields == errors[1].fields

    after = (
        all_accounts(client),
        client.get(f"/statements/{march['id']}"),
        live_ids(client, account),
        transaction_count(client, account),
    )
    assert after == before

    taken = scratch.row(account, "2026-04-01", -100, "USD", title="contract statement line")
    assert taken["date"].startswith("2026-04-01")
    assert transaction_count(client, account) == before[3] + 1
    assert statement_codes(client.get(f"/statements/{march['id']}")) == ["PEN"]


def test_the_completed_statement_holds_soles_only_after_a_revert(
    client, scratch, soles_march_then_dollars
):
    """The completed statement holds soles only; reverted, it still holds soles only
    while the dollars have nothing in it, its days are open again, and the dollar row
    refused on March 15 is taken (the control: the refusal was the seal)
    (contract: "Statements", "Which currencies a statement covers")
    (contract: "Transactions (Ledger)", "What is sealed is read at each write")."""
    account, march = soles_march_then_dollars
    err = scratch.refused_row(account, scratch.at("2026-03-15"), "USD")
    assert_refusal(err, 422, "VALIDATION_ERROR", "date", "SEALED_PERIOD")

    reverted = client.post(f"/statements/{march['id']}/revert")

    assert reverted["status"] == 1
    assert statement_codes(reverted) == ["PEN"]
    assert statement_codes(client.get(f"/statements/{march['id']}")) == ["PEN"]
    taken = scratch.row(account, "2026-03-15", currency="USD")
    assert taken["date"].startswith("2026-03-15")
    # A row in the draft's days that is in no statement gives it nothing.
    assert statement_codes(client.get(f"/statements/{march['id']}")) == ["PEN"]


def test_a_draft_seals_nothing(client, scratch):
    account = scratch.account()
    scratch.statement(account, *MARCH)
    scratch.row(account, "2026-03-15")


@LOOSE_LINES_ON_SEALED_DAYS
def test_a_row_filed_nowhere_does_not_stop_complete_and_its_day_seals(client, scratch):
    """A line in no statement is not a refusal of complete
    (contract: POST /v1/statements/{statement_id}/complete): the statement
    completes, its answer flags the unfiled row's line in `review_lines` of its
    soles balance, and the unfiled row's day is sealed with the rest."""
    account = scratch.account()
    filed = scratch.row(account, "2026-03-10")
    unfiled = scratch.row(account, "2026-03-11")
    statement = scratch.statement(account, *MARCH, balances=_soles(-1000))
    scratch.assign(filed["id"], statement["id"])

    done = client.post(f"/statements/{statement['id']}/complete")
    assert done["status"] == 2
    assert balance_of(done, "PEN")["review_lines"] == [unfiled["bank_line_id"]]
    err = scratch.refused_row(account, scratch.at("2026-03-11"))
    assert_refusal(err, 422, "VALIDATION_ERROR", "date", "SEALED_PERIOD")
    assert statement["name"] in err.fields["date"]


def test_a_skipped_stretch_is_reported_and_a_clean_one_is_not(client, scratch):
    account = scratch.account()
    jan_row = scratch.row(account, "2026-01-10")
    scratch.row(account, "2026-02-10")  # filed nowhere, in the gap: unfiled_count 1
    mar_row = scratch.row(account, "2026-03-10")
    jan = scratch.statement(account, *JANUARY, balances=_soles(-1000))["id"]
    mar = scratch.statement(account, *MARCH, balances=_soles(-1000))["id"]
    scratch.assign(jan_row["id"], jan)
    scratch.assign(mar_row["id"], mar)

    first = balance_of(client.post(f"/statements/{jan}/complete"), "PEN")
    assert first["warnings"] == []
    assert first["coverage_gap"] is None

    second = balance_of(client.post(f"/statements/{mar}/complete"), "PEN")
    assert len(second["warnings"]) == 1
    assert second["coverage_gap"] == {
        "first_uncovered_day": "2026-02-01",
        "last_uncovered_day": "2026-02-28",
        "unfiled_count": 1,
    }

    reverted = client.post(f"/statements/{mar}/revert")
    for entry in reverted["balances"]:
        assert "warnings" not in entry
        assert "coverage_gap" not in entry


@pytest.fixture
def sealed_line_in_a_draft(client, scratch):
    """An account whose March 2026 is completed with one row (March 10), and a draft April
    holding a row dated March 15, a day March seals (the row joined the draft before March was
    completed, where it was in a statement and refused nothing): the account, March, the draft,
    the row in the draft and the row in March."""
    account = scratch.account()
    inside = scratch.row(account, "2026-03-10")
    strayed = scratch.row(account, "2026-03-15")
    april = scratch.statement(account, *APRIL)
    scratch.assign(strayed["id"], april["id"])
    march = scratch.completed(account, *MARCH, inside["id"])
    assert (march["status"], april["status"]) == (2, 1)
    assert client.get(f"/transactions/{strayed['id']}")["statement_id"] == april["id"]
    return account, march, april, strayed, inside


def _held(client, april: dict, tx_id: str):
    """What a refused write on the line or its draft must leave as it was."""
    return (
        client.get(f"/statements/{april['id']}"),
        client.get(f"/transactions/{tx_id}", params={"debit_as_negative": "true"}),
    )


def test_a_line_on_a_sealed_day_cannot_be_unassigned_from_its_draft(
    client, scratch, sealed_line_in_a_draft
):
    """Unassigning the line (`statement_id: null`) through `PUT /transactions/{id}` and through
    `PUT /bank-lines/{id}` is `422` `SEALED_PERIOD` on `statement_id` alone, the message naming
    March, the statement sealing the day, and writes nothing: the draft and the line read as
    before (contract: "Transactions (Ledger)", "Sealed periods")
    (contract: PUT /v1/transactions/{transaction_id})."""
    _, march, april, strayed, _ = sealed_line_in_a_draft
    line = client.get(f"/transactions/{strayed['id']}")["bank_line_id"]

    err = refused_keeping(
        lambda: _held(client, april, strayed["id"]),
        lambda: client.put(f"/transactions/{strayed['id']}", json_body={"statement_id": None}),
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "statement_id", "SEALED_PERIOD")
    assert march["name"] in err.fields["statement_id"]

    err = refused_line_write(client, line, {"statement_id": None})
    assert_refusal(err, 422, "VALIDATION_ERROR", "statement_id", "SEALED_PERIOD")
    assert march["name"] in err.fields["statement_id"]
    assert _held(client, april, strayed["id"])[1]["statement_id"] == april["id"]


def test_the_draft_of_a_line_on_a_sealed_day_cannot_be_deleted_until_the_line_is(
    client, scratch, sealed_line_in_a_draft
):
    """`DELETE /statements/{id}` of the draft is `422` `SEALED_PERIOD` on `statement_id` alone,
    naming March, and writes nothing; deleting the line itself is allowed, and the draft then
    deletes (contract: DELETE /v1/statements/{statement_id}, "Validation")."""
    _, march, april, strayed, _ = sealed_line_in_a_draft

    err = refused_keeping(
        lambda: _held(client, april, strayed["id"]),
        lambda: client.delete(f"/statements/{april['id']}"),
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "statement_id", "SEALED_PERIOD")
    assert march["name"] in err.fields["statement_id"]

    client.delete(f"/transactions/{strayed['id']}")
    deleted = client.delete(f"/statements/{april['id']}")
    assert deleted["deleted_at"] is not None


def test_an_unchanged_date_is_judged_only_inside_a_completed_statement(
    client, scratch, sealed_line_in_a_draft
):
    """The `date` read back and sent unchanged beside a new category is `200` for the line on a
    sealed day in a draft, the category and the date as written; the same for the line inside
    March is `422` `LOCKED` on `date` alone, and the line reads as before, while the category
    alone goes through (contract: PUT /v1/transactions/{transaction_id}, "Field locking")
    (contract: "Transactions (Ledger)", "Sealed periods")."""
    _, _, april, strayed, inside = sealed_line_in_a_draft
    category = scratch.category()

    read = client.get(f"/transactions/{strayed['id']}")
    done = client.put(
        f"/transactions/{strayed['id']}", json_body={"date": read["date"], "category_id": category}
    )
    assert (done["date"], done["category_id"]) == (read["date"], category)
    assert done["statement_id"] == april["id"]

    locked = client.get(f"/transactions/{inside['id']}")
    sent = {"date": locked["date"], "category_id": category}
    err = refused_keeping(
        lambda: client.get(f"/transactions/{inside['id']}"),
        lambda: client.put(f"/transactions/{inside['id']}", json_body=sent),
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "date", "LOCKED")
    changed = client.put(f"/transactions/{inside['id']}", json_body={"category_id": category})
    assert (changed["date"], changed["category_id"]) == (locked["date"], category)


def test_statements_may_not_share_a_day_or_run_backwards(client, scratch):
    account = scratch.account()
    march = scratch.statement(account, *MARCH)
    april = scratch.statement(account, *APRIL)

    err = refused(lambda: scratch.statement(account, "2026-02-15", "2026-03-01"))
    assert_refusal(err, 422, "VALIDATION_ERROR", "date_start", "PERIOD_OVERLAPS")
    assert march["name"] in err.fields["date_start"]

    err = refused(
        lambda: client.put(f"/statements/{april['id']}", json_body={"date_start": "2026-03-31"})
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "date_start", "PERIOD_OVERLAPS")

    err = refused(
        lambda: client.put(f"/statements/{march['id']}", json_body={"date_end": "2026-02-01"})
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "date_end", "RANGE_INVERTED")
