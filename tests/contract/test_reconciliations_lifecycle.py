"""Contract lifecycle for reconciliations against a real engine.

The one resource with a *state machine* — draft → complete → reverted — and the
only one whose completion reaches across and locks rows in another table. None of
that is checkable against a mock: the unit suite asserts the CLI sends the right
call and renders the right hint, which is a statement about the CLI, not about
what completing a batch actually does to a transaction.

What this pins, and why each is a contract claim rather than a CLI one:

  · `beginning_balance_cents` is required and typed, not derived. The engine
    has no chained beginning balances; a re-introduction would
    show up here as a create that suddenly succeeds without it.
  · `complete` on an empty batch is a 422. The CLI prints a hint on exactly that
    shape, and the hint is only correct while the engine keeps refusing.
  · completion locks the assigned transaction's amount/account/title/date, and
    revert unlocks them. This is the field-locking semantic docs/cli-runtime.md
    promises, and the only place it is exercised end to end.
  · delete cascade-unassigns; the transaction survives.
  · moving an assigned row to another account must say what happens to its
    draft reconciliation; `reconciliation_id: null` in the same body moves and
    unassigns. The TUI's edit form and bulk `b` send exactly that.

Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from expense.errors import EngineError, reason_on


def _safe_delete(client, path):
    try:
        client.delete(path)
    except EngineError:
        pass


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _make_account(client) -> str:
    new_id = str(uuid4())
    client.post(
        "/accounts",
        json_body={
            "id": new_id,
            "name": f"contract-recon-acct-{new_id[:8]}",
            "currency_code": "PEN",
        },
    )
    return new_id


def _make_transaction(client, account_id: str) -> str:
    new_id = str(uuid4())
    client.post(
        "/transactions",
        json_body={
            "id": new_id,
            "title": "statement row",
            "amount_cents": -1200,
            "account_id": account_id,
            "date": _now_iso(),
        },
    )
    return new_id


def _make_reconciliation(client, account_id: str) -> str:
    new_id = str(uuid4())
    client.post(
        "/reconciliations",
        json_body={
            "id": new_id,
            "account_id": account_id,
            "name": f"contract-recon-{new_id[:8]}",
            "date_start": "2026-04-01",
            "date_end": "2026-04-30",
            "beginning_balance_cents": 958000,
            "ending_balance_cents": 946000,
        },
    )
    return new_id


def test_reconciliations_lifecycle(client):
    """create → list → update → delete, ending on "deleted is deleted":
    the row leaves its account's list and the old
    restore route is a 404. There is no get: the engine has no by-id read,
    and its path answers 405 because PUT and DELETE still live
    there. An account's list comes back whole, so absence from it is proof.
    The state machine is the next test."""
    account_id = _make_account(client)
    recon_id = str(uuid4())
    name = f"contract-recon-{recon_id[:8]}"

    try:
        created = client.post(
            "/reconciliations",
            json_body={
                "id": recon_id,
                "account_id": account_id,
                "name": name,
                "date_start": "2026-04-01",
                "date_end": "2026-04-30",
                "beginning_balance_cents": 958000,
            },
        )
        assert created["id"] == recon_id
        assert created["beginning_balance_cents"] == 958000
        # a period's ends are calendar days both ways (contract: "Date inputs")
        assert (created["date_start"], created["date_end"]) == ("2026-04-01", "2026-04-30")

        listed = client.get("/reconciliations", params={"account_id": account_id})
        assert any(item["id"] == recon_id for item in listed["items"])

        updated = client.put(
            f"/reconciliations/{recon_id}",
            json_body={"name": f"{name}-renamed", "date_end": "2026-05-01"},
        )
        assert updated["name"] == f"{name}-renamed"
        assert updated["date_end"] == "2026-05-01"

        deleted = client.delete(f"/reconciliations/{recon_id}")
        assert deleted.get("deleted_at") is not None

        listed = client.get("/reconciliations", params={"account_id": account_id})
        assert not any(item["id"] == recon_id for item in listed["items"])
        with pytest.raises(EngineError) as excinfo:
            client.post(f"/reconciliations/{recon_id}/restore")
        assert excinfo.value.status == 404
    finally:
        _safe_delete(client, f"/reconciliations/{recon_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_the_list_is_one_account_whole_and_there_is_no_read_by_id(client):
    """The two reads the CLI does not make. Without an
    account the list is a 422 naming `account_id`; one account's list comes
    back as `{items}` alone, with no paging keys; a GET on one reconciliation
    is a 405. The browse screen, `reconcile list --account-id` and the working
    screen's refresh are all built on these three facts."""
    account_id = _make_account(client)
    recon_id = _make_reconciliation(client, account_id)
    try:
        with pytest.raises(EngineError) as excinfo:
            client.get("/reconciliations")
        assert excinfo.value.status == 422
        assert "account_id" in (excinfo.value.fields or {})

        listed = client.get("/reconciliations", params={"account_id": account_id})
        assert set(listed) == {"items"}
        assert [item["id"] for item in listed["items"]] == [recon_id]

        with pytest.raises(EngineError) as excinfo:
            client.get(f"/reconciliations/{recon_id}")
        assert excinfo.value.status == 405
    finally:
        _safe_delete(client, f"/reconciliations/{recon_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_a_period_refuses_any_datetime(client):
    """Periods are days (contract: "Date inputs"): a midnight instant is a 422
    naming the field, so a client that converts a typed day to an instant cannot
    save a period at all."""
    account_id = _make_account(client)
    recon_id = str(uuid4())
    try:
        with pytest.raises(EngineError) as excinfo:
            client.post(
                "/reconciliations",
                json_body={
                    "id": recon_id,
                    "account_id": account_id,
                    "name": f"contract-recon-{recon_id[:8]}",
                    "date_start": "2026-04-01T00:00:00-05:00",
                    "date_end": "2026-04-30",
                    "beginning_balance_cents": 0,
                },
            )
        assert excinfo.value.status == 422
        assert "date_start" in (excinfo.value.fields or {})
    finally:
        _safe_delete(client, f"/reconciliations/{recon_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_a_period_always_has_both_days(client):
    """Both days required on create (contract: POST /v1/reconciliations), and
    `null` refused for either on update
    (contract: PUT /v1/reconciliations/{reconciliation_id}). The CLI has no
    missing-date hint on `complete`, no half-dated display and no undated guard
    in the "no batch" list because of this; if it relaxes, they are needed."""
    account_id = _make_account(client)
    recon_id = _make_reconciliation(client, account_id)
    missing_id = str(uuid4())
    try:
        with pytest.raises(EngineError) as excinfo:
            client.post(
                "/reconciliations",
                json_body={
                    "id": missing_id,
                    "account_id": account_id,
                    "name": f"contract-recon-{missing_id[:8]}",
                    "date_start": "2026-05-01",
                    "beginning_balance_cents": 0,
                },
            )
        assert excinfo.value.status == 422
        assert "date_end" in (excinfo.value.fields or {})

        for key in ("date_start", "date_end"):
            with pytest.raises(EngineError) as excinfo:
                client.put(f"/reconciliations/{recon_id}", json_body={key: None})
            assert excinfo.value.status == 422
            assert key in (excinfo.value.fields or {})
    finally:
        _safe_delete(client, f"/reconciliations/{missing_id}")
        _safe_delete(client, f"/reconciliations/{recon_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_the_tick_list_read_includes_a_row_late_on_the_last_day(client):
    """Rows on `date_end` must not be left out. The working screen
    reads the account's rows with `date_from` / `date_to` set to the period's
    own days; a row logged at 23:30 local on `date_end` must be in that read."""
    zone = ZoneInfo(client.get("/auth/me")["settings"]["display_timezone"])
    late = datetime(2026, 4, 30, 23, 30, tzinfo=zone).isoformat(timespec="seconds")
    account_id = _make_account(client)
    recon_id = _make_reconciliation(client, account_id)
    txn_id = str(uuid4())
    try:
        client.post(
            "/transactions",
            json_body={
                "id": txn_id,
                "title": "last-day row",
                "amount_cents": -1200,
                "account_id": account_id,
                "date": late,
            },
        )
        period = next(
            r
            for r in client.get("/reconciliations", params={"account_id": account_id})["items"]
            if r["id"] == recon_id
        )
        page = client.get(
            "/transactions",
            params={
                "account_id": account_id,
                "date_from": period["date_start"],
                "date_to": period["date_end"],
            },
        )
        assert txn_id in [row["id"] for row in page["items"]]
    finally:
        _safe_delete(client, f"/transactions/{txn_id}")
        _safe_delete(client, f"/reconciliations/{recon_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_beginning_balance_is_required_not_derived(client):
    """No chained beginning balance, pinned from the outside.

    While this 422s, `expense reconcile create --beginning-balance` is right to
    be a required flag. If the engine ever derives it again, this is the test
    that says the flag can relax — nothing in the unit suite can know.
    """
    account_id = _make_account(client)
    recon_id = str(uuid4())
    try:
        with pytest.raises(EngineError) as excinfo:
            client.post(
                "/reconciliations",
                json_body={
                    "id": recon_id,
                    "account_id": account_id,
                    "name": f"contract-recon-{recon_id[:8]}",
                    "date_start": "2026-04-01",
                    "date_end": "2026-04-30",
                },
            )
        assert excinfo.value.status == 422
    finally:
        _safe_delete(client, f"/reconciliations/{recon_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_completing_an_empty_batch_is_refused(client):
    """`reconcile complete` prints a hint on this exact 422.

    The hint is text the CLI owns; that it is ever shown is the engine's call.
    A batch with nothing assigned must stay a refusal, or the hint becomes a
    sentence nobody ever reads and the command silently changes meaning.
    """
    account_id = _make_account(client)
    recon_id = _make_reconciliation(client, account_id)
    try:
        with pytest.raises(EngineError) as excinfo:
            client.post(f"/reconciliations/{recon_id}/complete")
        assert excinfo.value.status == 422
    finally:
        _safe_delete(client, f"/reconciliations/{recon_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_complete_locks_the_assigned_transaction_and_revert_unlocks_it(client):
    """The cross-table half of the state machine.

    `expense transactions update` renders a "locked" hint off a 422 here; this
    is the only place the CLI finds out that completing a batch really does make
    the amount unwritable, and that reverting really does give it back.
    """
    account_id = _make_account(client)
    tx_id = _make_transaction(client, account_id)
    recon_id = _make_reconciliation(client, account_id)

    try:
        client.put(f"/transactions/{tx_id}", json_body={"reconciliation_id": recon_id})

        completed = client.post(f"/reconciliations/{recon_id}/complete")
        assert completed["id"] == recon_id

        with pytest.raises(EngineError) as excinfo:
            client.put(f"/transactions/{tx_id}", json_body={"amount_cents": -9999})
        assert excinfo.value.status in (409, 422)

        client.post(f"/reconciliations/{recon_id}/revert")
        client.put(f"/transactions/{tx_id}", json_body={"amount_cents": -9999})

        # Read it back the way the CLI does. The engine stores the magnitude and
        # signs it only when asked — see test_a_write_is_signed_but_a_bare_read
        # _is_not in test_reports_and_dashboard.py, which pins that on its own.
        after = client.get(f"/transactions/{tx_id}", params={"debit_as_negative": "true"})
        assert after["amount_cents"] == -9999
    finally:
        _safe_delete(client, f"/transactions/{tx_id}")
        _safe_delete(client, f"/reconciliations/{recon_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_deleting_a_batch_unassigns_its_transactions_and_keeps_them(client):
    """Cascade-unassign, which the delete command's docstring promises.

    The row is the user's data and the batch is bookkeeping over it — deleting
    the bookkeeping must never take the row with it.
    """
    account_id = _make_account(client)
    tx_id = _make_transaction(client, account_id)
    recon_id = _make_reconciliation(client, account_id)

    try:
        client.put(f"/transactions/{tx_id}", json_body={"reconciliation_id": recon_id})
        assert client.get(f"/transactions/{tx_id}")["reconciliation_id"] == recon_id

        client.delete(f"/reconciliations/{recon_id}")

        after = client.get(f"/transactions/{tx_id}")
        assert after["id"] == tx_id  # the row survived
        assert after.get("reconciliation_id") is None  # and was let go
    finally:
        _safe_delete(client, f"/transactions/{tx_id}")
        _safe_delete(client, f"/reconciliations/{recon_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_moving_an_assigned_row_needs_the_unassign_in_the_same_body(client):
    """The move the TUI's edit form and bulk `b` make
    (contract: "Assigning transactions") (contract: PUT /v1/transactions/{id}).

    An account change on a row in a draft reconciliation, with no
    `reconciliation_id` in the body, is a 422 on `account_id` with reason
    `ASSIGNED_TO_RECONCILIATION` and changes nothing. With
    `reconciliation_id: null` in the same body the row moves and leaves the
    batch — which is why `unassign_on_move` adds it.
    """
    account_id = _make_account(client)
    other_id = _make_account(client)
    tx_id = _make_transaction(client, account_id)
    recon_id = _make_reconciliation(client, account_id)

    try:
        client.put(f"/transactions/{tx_id}", json_body={"reconciliation_id": recon_id})

        with pytest.raises(EngineError) as excinfo:
            client.put(f"/transactions/{tx_id}", json_body={"account_id": other_id})
        assert excinfo.value.status == 422
        assert reason_on(excinfo.value, "account_id") == "ASSIGNED_TO_RECONCILIATION"
        unchanged = client.get(f"/transactions/{tx_id}")
        assert unchanged["account_id"] == account_id
        assert unchanged["reconciliation_id"] == recon_id

        # the account it already has is not a move: no refusal, still assigned
        client.put(f"/transactions/{tx_id}", json_body={"account_id": account_id})
        assert client.get(f"/transactions/{tx_id}")["reconciliation_id"] == recon_id

        client.put(
            f"/transactions/{tx_id}",
            json_body={"account_id": other_id, "reconciliation_id": None},
        )
        moved = client.get(f"/transactions/{tx_id}")
        assert moved["account_id"] == other_id
        assert moved.get("reconciliation_id") is None
    finally:
        _safe_delete(client, f"/transactions/{tx_id}")
        _safe_delete(client, f"/reconciliations/{recon_id}")
        _safe_delete(client, f"/accounts/{other_id}")
        _safe_delete(client, f"/accounts/{account_id}")
