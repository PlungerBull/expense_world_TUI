"""Contract lifecycle for reconciliations against a real engine.

The one resource with a *state machine* — draft → complete → reverted — and the
only one whose completion reaches across and locks rows in another table. None of
that is checkable against a mock: the unit suite asserts the CLI sends the right
call and renders the right hint, which is a statement about the CLI, not about
what completing a batch actually does to a transaction.

What this pins, and why each is a contract claim rather than a CLI one:

  · `beginning_balance_cents` is required and typed, not derived. The engine
    deleted chained beginning balances on 2026-08-06; a re-introduction would
    show up here as a create that suddenly succeeds without it.
  · `complete` on an empty batch is a 422. The CLI prints a hint on exactly that
    shape, and the hint is only correct while the engine keeps refusing.
  · completion locks the assigned transaction's amount/account/title/date, and
    revert unlocks them. This is the field-locking semantic docs/cli-runtime.md
    promises, and the only place it is exercised end to end.
  · delete cascade-unassigns; the transaction survives.

Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from expense.errors import EngineError


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
            "date_start": "2026-04-01T00:00:00Z",
            "date_end": "2026-04-30T00:00:00Z",
            "beginning_balance_cents": 958000,
            "ending_balance_cents": 946000,
        },
    )
    return new_id


def test_reconciliations_lifecycle(client):
    """create → get → list → update → delete, the shape every resource
    shares, ending on "deleted is deleted" (engine, 2026-09-23): the get and
    the old restore route are both 404. The state machine is the next test."""
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
                "date_start": "2026-04-01T00:00:00Z",
                "beginning_balance_cents": 958000,
            },
        )
        assert created["id"] == recon_id
        assert created["beginning_balance_cents"] == 958000

        fetched = client.get(f"/reconciliations/{recon_id}")
        assert fetched["id"] == recon_id

        listed = client.get("/reconciliations", params={"account_id": account_id})
        assert any(item["id"] == recon_id for item in listed["items"])

        updated = client.put(f"/reconciliations/{recon_id}", json_body={"name": f"{name}-renamed"})
        assert updated["name"] == f"{name}-renamed"

        deleted = client.delete(f"/reconciliations/{recon_id}")
        assert deleted.get("deleted_at") is not None

        for gone in (
            lambda: client.get(f"/reconciliations/{recon_id}"),
            lambda: client.post(f"/reconciliations/{recon_id}/restore"),
        ):
            with pytest.raises(EngineError) as excinfo:
                gone()
            assert excinfo.value.status == 404
    finally:
        _safe_delete(client, f"/reconciliations/{recon_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_beginning_balance_is_required_not_derived(client):
    """The 2026-08-06 de-chaining, pinned from the outside.

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
                    "date_start": "2026-04-01T00:00:00Z",
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
