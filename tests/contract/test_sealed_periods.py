"""Contract: sealed periods.

A completed reconciliation seals its account's days but the last, which seals once
the account's next statement is completed too
(contract: "Transactions (Ledger)", "Sealed periods"). The app computes none of it:
it reports every refusal by reading the engine's `fields` key and message. The unit
suite fakes those 422s; this file is the only place they are checked against the
engine:

  · the wall: five doors refuse a row dated on a sealed day, each naming its own
    key, the message naming the period; the last local minute of the last sealed
    day is inside, the next day is not;
  · a statement's last day stays open until the account's next statement is
    completed, is sealed under the statement's own name once it is, and opens
    again when that next statement is reverted;
  · a draft seals nothing, and revert opens the wall again;
  · a row in the period filed nowhere does not stop `complete`, and its day seals
    with the rest;
  · `warnings` / `coverage_gap` report a skipped stretch, and are empty/null
    when there is none; revert carries neither;
  · periods on one account may not share a day, and may not run backwards.

Each test builds its own account, and every row it sends, a refused one included,
is in its cleanup before the call, so a row the engine takes after all is still
removed. Gating, target and the real-ledger guard: conftest.py.
"""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from expense.errors import EngineError
from tests.contract.conftest import reason_on


def _safe(call, *args, **kw):
    try:
        call(*args, **kw)
    except EngineError:
        pass


class Ledger:
    """Creates accounts, rows and periods, and undoes them in reverse order:
    completed periods are reverted first, since a completed period can be
    neither deleted nor have its rows deleted. Every period carries its ending
    balance, so each one can be completed (contract: POST
    /v1/reconciliations/{reconciliation_id}/complete, "The ending balance must be
    entered")."""

    def __init__(self, client):
        self.c = client
        self.zone = ZoneInfo(client.get("/auth/me")["settings"]["display_timezone"])
        self.accounts: list[str] = []
        self.rows: list[str] = []
        self.periods: list[str] = []

    def at(self, y: int, m: int, d: int, hour: int = 12, minute: int = 0) -> str:
        return datetime(y, m, d, hour, minute, tzinfo=self.zone).isoformat(timespec="seconds")

    def account(self) -> str:
        new_id = str(uuid4())
        self.c.post(
            "/accounts",
            json_body={"id": new_id, "name": f"contract-seal-{new_id[:8]}", "currency_code": "PEN"},
        )
        self.accounts.append(new_id)
        return new_id

    def row(self, account_id: str, date: str) -> str:
        new_id = str(uuid4())
        self.rows.append(new_id)
        self.c.post(
            "/transactions",
            json_body={
                "id": new_id,
                "title": "sealed row",
                "amount_cents": -500,
                "account_id": account_id,
                "date": date,
            },
        )
        return new_id

    def refused_row(self, account_id: str, date: str) -> EngineError:
        """A row sent on `date`, which the engine must refuse; its id joins the
        cleanup before the call."""
        new_id = str(uuid4())
        self.rows.append(new_id)
        return _refused(
            self.c.post,
            "/transactions",
            json_body={
                "id": new_id,
                "amount_cents": -100,
                "account_id": account_id,
                "date": date,
            },
        )

    def period(self, account_id: str, start: str, end: str, *rows: str) -> tuple[str, str]:
        new_id = str(uuid4())
        name = f"contract-seal-{new_id[:8]}"
        self.c.post(
            "/reconciliations",
            json_body={
                "id": new_id,
                "account_id": account_id,
                "name": name,
                "date_start": start,
                "date_end": end,
                "beginning_balance_cents": 0,
                "ending_balance_cents": -500 * len(rows),
            },
        )
        self.periods.append(new_id)
        for row_id in rows:
            self.c.put(f"/transactions/{row_id}", json_body={"reconciliation_id": new_id})
        return new_id, name

    def cleanup(self) -> None:
        for pid in self.periods:
            _safe(self.c.post, f"/reconciliations/{pid}/revert")
        for pid in reversed(self.periods):
            _safe(self.c.delete, f"/reconciliations/{pid}")
        for rid in reversed(self.rows):
            _safe(self.c.delete, f"/transactions/{rid}")
        for aid in reversed(self.accounts):
            _safe(self.c.delete, f"/accounts/{aid}")


@pytest.fixture
def ledger(client):
    book = Ledger(client)
    try:
        yield book
    finally:
        book.cleanup()


def _refused(call, *args, **kw) -> EngineError:
    with pytest.raises(EngineError) as excinfo:
        call(*args, **kw)
    assert excinfo.value.status == 422
    return excinfo.value


@pytest.fixture
def sealed_march(client, ledger):
    """An account whose March 2026 is completed, plus one row outside it. Its sealed
    days are March 1 to 30: the 31st waits for April's statement."""
    account = ledger.account()
    inside = ledger.row(account, ledger.at(2026, 3, 10))
    period, name = ledger.period(account, "2026-03-01", "2026-03-31", inside)
    client.post(f"/reconciliations/{period}/complete")
    outside = ledger.row(account, ledger.at(2026, 4, 10))
    return account, period, name, outside


def test_the_wall_on_create_and_batch(client, ledger, sealed_march):
    account, _, name, _ = sealed_march
    err = ledger.refused_row(account, ledger.at(2026, 3, 15))
    assert "date" in err.fields
    assert name in err.message or name in err.fields["date"]

    batched = str(uuid4())
    ledger.rows.append(batched)
    err = _refused(
        client.post,
        "/transactions/batch",
        json_body={
            "transactions": [
                {
                    "id": batched,
                    "amount_cents": -100,
                    "account_id": account,
                    "date": ledger.at(2026, 3, 15),
                }
            ]
        },
    )
    assert "transactions.0.date" in err.fields


def test_the_wall_is_whole_days_in_the_display_timezone(client, ledger, sealed_march):
    """23:59 local on the last sealed day (March 30) is inside; 00:00 of the next
    day, the statement's own last day, is not."""
    account, *_ = sealed_march
    err = ledger.refused_row(account, ledger.at(2026, 3, 30, 23, 59))
    assert "date" in err.fields
    ledger.row(account, ledger.at(2026, 3, 31, 0, 0))


def test_the_last_day_seals_once_the_next_statement_is_completed(client, ledger, sealed_march):
    """March is completed and April is not: March 31 takes a row. April completed:
    March 31 is refused, named under March's own reconciliation, up to 23:59 local,
    while April 1 is sealed and April 30, April's own last day, takes a row. April
    reverted: March 31 takes a row again."""
    account, _, march_name, outside = sealed_march
    ledger.row(account, ledger.at(2026, 3, 31))

    april, april_name = ledger.period(account, "2026-04-01", "2026-04-30", outside)
    ledger.row(account, ledger.at(2026, 3, 31, 23, 59))  # a draft next statement seals nothing
    client.post(f"/reconciliations/{april}/complete")

    for hour, minute in ((0, 0), (12, 0), (23, 59)):
        err = ledger.refused_row(account, ledger.at(2026, 3, 31, hour, minute))
        assert reason_on(err, "date") == "SEALED_PERIOD"
        assert march_name in err.fields["date"]
        assert april_name not in err.fields["date"]
    err = ledger.refused_row(account, ledger.at(2026, 4, 1, 0, 0))
    assert april_name in err.fields["date"]
    ledger.row(account, ledger.at(2026, 4, 30, 23, 59))

    client.post(f"/reconciliations/{april}/revert")
    ledger.row(account, ledger.at(2026, 3, 31))


def test_the_wall_on_moving_a_row_in(client, ledger, sealed_march):
    """Moving the date in names `date`; moving the account in names `account_id`
    (Home's bulk `b` reports that key)."""
    account, _, _, outside = sealed_march
    err = _refused(
        client.put, f"/transactions/{outside}", json_body={"date": ledger.at(2026, 3, 15)}
    )
    assert "date" in err.fields

    other = ledger.account()
    stray = ledger.row(other, ledger.at(2026, 3, 15))
    err = _refused(client.put, f"/transactions/{stray}", json_body={"account_id": account})
    assert "account_id" in err.fields


def test_the_wall_on_an_opening_balance(client, ledger, sealed_march):
    account, *_ = sealed_march
    seed = str(uuid4())
    ledger.rows.append(seed)
    err = _refused(
        client.post,
        f"/accounts/{account}/opening-balance",
        json_body={
            "transaction_id": seed,
            "amount_cents": 1000,
            "date": ledger.at(2026, 3, 20),
        },
    )
    assert "date" in err.fields


def test_revert_opens_the_wall(client, ledger, sealed_march):
    account, period, _, _ = sealed_march
    client.post(f"/reconciliations/{period}/revert")
    ledger.row(account, ledger.at(2026, 3, 15))


def test_a_draft_seals_nothing(client, ledger):
    account = ledger.account()
    ledger.period(account, "2026-03-01", "2026-03-31")
    ledger.row(account, ledger.at(2026, 3, 15))


def test_a_row_filed_nowhere_does_not_stop_complete_and_its_day_seals(client, ledger):
    """A line in no reconciliation is not a refusal of complete
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete): the period
    completes, and the unfiled row's day is sealed with the rest."""
    account = ledger.account()
    filed = ledger.row(account, ledger.at(2026, 3, 10))
    ledger.row(account, ledger.at(2026, 3, 11))
    period, name = ledger.period(account, "2026-03-01", "2026-03-31", filed)

    assert client.post(f"/reconciliations/{period}/complete")["status"] == 2
    err = ledger.refused_row(account, ledger.at(2026, 3, 11))
    assert reason_on(err, "date") == "SEALED_PERIOD"
    assert name in err.fields["date"]


def test_a_skipped_stretch_is_reported_and_a_clean_one_is_not(client, ledger):
    account = ledger.account()
    jan_row = ledger.row(account, ledger.at(2026, 1, 10))
    ledger.row(account, ledger.at(2026, 2, 10))  # filed nowhere, in the gap: unfiled_count 1
    mar_row = ledger.row(account, ledger.at(2026, 3, 10))
    jan, _ = ledger.period(account, "2026-01-01", "2026-01-31", jan_row)
    mar, _ = ledger.period(account, "2026-03-01", "2026-03-31", mar_row)

    first = client.post(f"/reconciliations/{jan}/complete")
    assert first["warnings"] == []
    assert first["coverage_gap"] is None

    second = client.post(f"/reconciliations/{mar}/complete")
    assert len(second["warnings"]) == 1
    assert second["coverage_gap"] == {
        "first_uncovered_day": "2026-02-01",
        "last_uncovered_day": "2026-02-28",
        "unfiled_count": 1,
    }

    reverted = client.post(f"/reconciliations/{mar}/revert")
    assert "warnings" not in reverted
    assert "coverage_gap" not in reverted


def test_periods_may_not_share_a_day_or_run_backwards(client, ledger):
    account = ledger.account()
    march, march_name = ledger.period(account, "2026-03-01", "2026-03-31")
    april, _ = ledger.period(account, "2026-04-01", "2026-04-30")

    err = _refused(
        client.post,
        "/reconciliations",
        json_body={
            "id": str(uuid4()),
            "account_id": account,
            "name": "overlaps march",
            "date_start": "2026-02-15",
            "date_end": "2026-03-01",
            "beginning_balance_cents": 0,
        },
    )
    assert "date_start" in err.fields
    assert march_name in err.fields["date_start"] or march_name in err.message

    err = _refused(client.put, f"/reconciliations/{april}", json_body={"date_start": "2026-03-31"})
    assert "date_start" in err.fields

    err = _refused(client.put, f"/reconciliations/{march}", json_body={"date_end": "2026-02-01"})
    assert "date_end" in err.fields
