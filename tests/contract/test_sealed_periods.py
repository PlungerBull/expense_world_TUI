"""Contract: sealed periods (engine, 2026-09-20; CLI side built 2026-09-21/22).

A completed reconciliation seals its account's days, and the CLI reports every
refusal that follows by reading the engine's `fields` key and message. The unit
suite fakes those 422s; this file is the only place they are checked against the
engine, and the check the sealed-periods work closed on:

  · the wall: five doors refuse a row dated inside a completed period, each
    naming its own key, the message naming the period; the last local minute
    of the last day is inside, the next day is not;
  · a draft seals nothing, and revert opens the wall again;
  · `complete` refuses while a row in the period is filed nowhere. It shares
    `fields["transactions"]` with the empty-batch refusal, so only the message
    tells them apart (the hint the CLI prints depends on reading it);
  · `warnings` / `coverage_gap` report a skipped stretch, and are empty/null
    when there is none; revert carries neither;
  · periods on one account may not share a day, and may not run backwards.

Each test builds its own account. Gating, target and the real-ledger guard:
conftest.py.
"""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from expense.errors import EngineError


def _safe(call, *args, **kw):
    try:
        call(*args, **kw)
    except EngineError:
        pass


class Ledger:
    """Creates accounts, rows and periods, and undoes them in reverse order:
    completed periods are reverted first, since a completed period can be
    neither deleted nor have its rows deleted."""

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
        self.rows.append(new_id)
        return new_id

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
    """An account whose March 2026 is completed, plus one row outside it."""
    account = ledger.account()
    inside = ledger.row(account, ledger.at(2026, 3, 10))
    period, name = ledger.period(account, "2026-03-01", "2026-03-31", inside)
    client.post(f"/reconciliations/{period}/complete")
    outside = ledger.row(account, ledger.at(2026, 4, 10))
    return account, period, name, outside


def test_the_wall_on_create_and_batch(client, ledger, sealed_march):
    account, _, name, _ = sealed_march
    err = _refused(
        client.post,
        "/transactions",
        json_body={
            "id": str(uuid4()),
            "amount_cents": -100,
            "account_id": account,
            "date": ledger.at(2026, 3, 15),
        },
    )
    assert "date" in err.fields
    assert name in err.message or name in err.fields["date"]

    err = _refused(
        client.post,
        "/transactions/batch",
        json_body={
            "transactions": [
                {
                    "id": str(uuid4()),
                    "amount_cents": -100,
                    "account_id": account,
                    "date": ledger.at(2026, 3, 15),
                }
            ]
        },
    )
    assert "transactions.0.date" in err.fields


def test_the_wall_is_whole_days_in_the_display_timezone(client, ledger, sealed_march):
    """23:59 local on the last day is inside; 00:00 of the next day is not."""
    account, *_ = sealed_march
    err = _refused(
        client.post,
        "/transactions",
        json_body={
            "id": str(uuid4()),
            "amount_cents": -100,
            "account_id": account,
            "date": ledger.at(2026, 3, 31, 23, 59),
        },
    )
    assert "date" in err.fields
    ledger.row(account, ledger.at(2026, 4, 1, 0, 0))


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
    err = _refused(
        client.post,
        f"/accounts/{account}/opening-balance",
        json_body={
            "transaction_id": str(uuid4()),
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


def test_complete_refuses_while_a_row_in_the_period_is_filed_nowhere(client, ledger):
    """Same key as the empty-batch refusal, different message: the CLI's hint
    reads the message, so the message is the contract."""
    account = ledger.account()
    filed = ledger.row(account, ledger.at(2026, 3, 10))
    ledger.row(account, ledger.at(2026, 3, 11))
    period, _ = ledger.period(account, "2026-03-01", "2026-03-31", filed)

    err = _refused(client.post, f"/reconciliations/{period}/complete")
    assert "transactions" in err.fields
    assert "not assigned to any reconciliation" in err.fields["transactions"]
    assert "At least one transaction" not in err.fields["transactions"]


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
