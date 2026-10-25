"""Shared gating, target resolution and the real-ledger guard for tests/contract.

These tests hit a real engine and make real writes, so a contract run that would write to
the real ledger **refuses to start**. Point it at the disposable practice database
instead, or set EXPENSE_ALLOW_REAL_LEDGER=1 to say you meant it.

How to seed the practice user, start the test engine on :8002 and run this suite:
docs/runtime.md "Working against the live engine".
"""

import os
import random
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from expense import config as config_module
from expense.bank_line_write import line_body, new_part
from expense.config import Config
from expense.errors import EngineError
from expense.http import ExpenseClient

# The default is the one real engine, the local deployment. A practice run sets
# EXPENSE_ENGINE_URL to the disposable test engine on :8002.
DEFAULT_ENGINE_URL = "http://127.0.0.1:8000"

ENGINE_URL = os.environ.get("EXPENSE_ENGINE_URL", DEFAULT_ENGINE_URL)
PAT = os.environ.get("EXPENSE_PAT")
ALLOW_REAL_LEDGER = os.environ.get("EXPENSE_ALLOW_REAL_LEDGER") == "1"

LIVE = os.environ.get("PYTEST_LIVE") == "1"


def reason_on(err: EngineError, field: str) -> str | None:
    """The engine's reason code for `field`, or None when it names no reason there
    (contract: "Error reasons")."""
    if not isinstance(err.reasons, dict):
        return None
    return err.reasons.get(field)


def read_signed(client: ExpenseClient, tx_id: str) -> dict:
    """The transaction read signed, negative for money out, so its `amount_cents` can
    be compared or sent back as is: write responses carry the magnitude and
    `transaction_type` (contract: "Base Conventions", "Sign convention — responses")."""
    return client.get(f"/transactions/{tx_id}", params={"debit_as_negative": "true"})


def replace_parts(
    client: ExpenseClient, line_id: str, amounts: list[int], written: list[str]
) -> list[dict]:
    """Rewrite the bank line `line_id` into new parts of `amounts`, in one whole-line
    write sending only new ids, which replaces every part and keeps the line
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts"). The body is the app's own
    (expense/bank_line_write.py). Each part id joins `written` before the call, so
    cleanup reaches whatever the engine created. Returns the parts as the answer reads
    them, in request order."""
    parts = [new_part(amount_cents=amount) for amount in amounts]
    written.extend(part["id"] for part in parts)
    answer = client.put(f"/bank-lines/{line_id}", json_body=line_body(parts))
    by_id = {part["id"]: part for part in answer["parts"]}
    return [by_id[part["id"]] for part in parts]


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_auto_num_workers(config):
    """Run this suite in one process when `-n auto` comes from pyproject's addopts.

    Its tests share one practice user and make real writes (one seals periods the
    others write into), so they run one after another. xdist reads 0 workers as no
    distribution at all; an explicit `-n 4` still asks for workers. Holds when the
    run starts in tests/contract, where this conftest is loaded before xdist asks;
    tests/conftest.py covers a live run started above it.
    """
    return 0


def pytest_collection_modifyitems(config, items):
    """Gate the whole directory on PYTEST_LIVE=1.

    This is a hook, not a module-level `pytestmark`: a `pytestmark` assigned in a
    conftest does NOT apply to tests in other modules, so relying on it lets
    `pytest tests/contract` run against the live engine and create rows. The gate
    belongs somewhere that provably covers every item.
    """
    if LIVE:
        return
    skip = pytest.mark.skip(reason="Contract tests require PYTEST_LIVE=1")
    for item in items:
        item.add_marker(skip)


_REFUSAL = """
┌────────────────────────────────────────────────────────────┐
│  REFUSING TO RUN                                           │
│  this would write to your real ledger                      │
│    engine       {url:<42}│
│    signed in as you, from ~/.expense-config                │
│    rows created here are soft-deleted, never removed       │
│                                                            │
│  practice database instead:                                │
│    ../expense_world_engine/deploy/local/seed-test-user.sh  │
│    then EXPENSE_PAT=… EXPENSE_ENGINE_URL=http://127.0.0.1:8002
│                                                            │
│  or, to mean it:                                           │
│    EXPENSE_ALLOW_REAL_LEDGER=1                             │
└────────────────────────────────────────────────────────────┘
"""


def _is_real_ledger() -> bool:
    """True when the run would write as the developer, to their own ledger.

    A PAT in the environment is the isolation signal: it is how the practice user
    is addressed. Without one, the only credential available is the developer's
    saved config — which is the real ledger by definition, whatever the URL says.
    """
    return not PAT


def pytest_sessionstart(session):
    """Refuse rather than warn — before collection, before any fixture.

    Deliberately a session hook rather than an autouse fixture: a fixture only runs
    when something requests it, and the guard must hold even if a future test
    forgets the `client` fixture entirely.
    """
    if not LIVE:
        return
    if _is_real_ledger() and not ALLOW_REAL_LEDGER:
        pytest.exit(_REFUSAL.format(url=ENGINE_URL), returncode=2)
    source = "EXPENSE_PAT" if PAT else "~/.expense-config (ALLOWED EXPLICITLY)"
    print(f"\ncontract target: {ENGINE_URL} · credential: {source}")


@pytest.fixture
def client():
    """An ExpenseClient aimed at the resolved target.

    Prefers EXPENSE_PAT + EXPENSE_ENGINE_URL so every module obeys the same target
    as the freshman walk; falls back to the developer's config only when the guard
    above has explicitly allowed it.
    """
    cfg = Config(engine_url=ENGINE_URL, token=PAT) if PAT else config_module.ensure_loaded()
    with ExpenseClient(cfg) as c:
        yield c


@pytest.fixture
def statuses(client):
    """The HTTP status of every response `client` receives, in order. The client
    returns only the body on success, so a status such as `201` is read off httpx's
    own hook on the repo client's transport."""
    seen: list[int] = []
    hooks = client._client.event_hooks
    hooks["response"] = [*hooks.get("response", []), lambda r: seen.append(r.status_code)]
    return seen


# ---- statements: accounts with a statement code, their reconciliations and lines ----

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def free_statement_codes(client: ExpenseClient, count: int) -> list[str]:
    """`count` different statement codes no account of the caller's holds, so a test's
    codes clash with nothing but what it builds itself, whatever an earlier run left.
    A deleted account holds no code; an archived account and a person are read too
    (contract: "Bank Accounts", "Shared only across currencies")."""
    listed = client.get("/accounts", params={"include_people": "true", "include_archived": "true"})
    held = {item["statement_code"] for item in listed["items"]}
    rng = random.SystemRandom()
    codes: list[str] = []
    while len(codes) < count:
        code = "".join(rng.choice(_LETTERS) for _ in range(3))
        if code not in held and code not in codes:
            codes.append(code)
    return codes


def refused(call) -> EngineError:
    """The engine's refusal of `call`, which must be refused."""
    with pytest.raises(EngineError) as excinfo:
        call()
    return excinfo.value


def assert_refusal(err: EngineError, status: int, code: str, key: str, reason: str) -> None:
    """The refusal is `status` `code`, keyed on `key` alone, carrying `reason` there
    (contract: "Base Conventions", "`fields` and `reasons` semantics")."""
    assert (err.status, err.code) == (status, code), (err.status, err.code, err.reasons)
    assert isinstance(err.reasons, dict) and set(err.reasons) == {key}, err.reasons
    assert isinstance(err.fields, dict) and set(err.fields) == {key}, err.fields
    assert reason_on(err, key) == reason


def account_body(currency: str = "PEN", code: str | None = None) -> dict:
    """A `POST /accounts` body under a fresh id, with `statement_code` when given."""
    new_id = str(uuid4())
    body = {"id": new_id, "name": f"contract-stmt-{new_id[:8]}", "currency_code": currency}
    if code is not None:
        body["statement_code"] = code
    return body


class Scratch:
    """What one test builds on the practice user, undone in reverse dependency order:
    archived accounts unarchived, reconciliations reverted and deleted, transactions
    deleted, accounts deleted. Every step is best-effort, so a failed test still frees
    its statement codes."""

    def __init__(self, client: ExpenseClient) -> None:
        self.client = client
        self.zone = ZoneInfo(client.get("/auth/me")["settings"]["display_timezone"])
        self.accounts: list[str] = []
        self.reconciliations: list[str] = []
        self.transactions: list[str] = []

    def account(self, currency: str = "PEN", code: str | None = None) -> str:
        body = account_body(currency, code)
        self.accounts.append(body["id"])
        self.client.post("/accounts", json_body=body)
        return body["id"]

    def person(self, currency: str = "PEN") -> str:
        new_id = str(uuid4())
        self.accounts.append(new_id)
        self.client.post(
            "/people",
            json_body={
                "id": new_id,
                "name": f"contract-stmt-p-{new_id[:8]}",
                "currency_code": currency,
            },
        )
        return new_id

    def reconciliation(self, account_id: str, start: str, end: str) -> str:
        """A draft over the calendar days `start` to `end`, with an ending balance so
        nothing but the rule under test stands in the way of completing it."""
        new_id = str(uuid4())
        self.reconciliations.append(new_id)
        self.client.post(
            "/reconciliations",
            json_body={
                "id": new_id,
                "account_id": account_id,
                "name": f"contract-stmt-recon-{new_id[:8]}",
                "date_start": start,
                "date_end": end,
                "beginning_balance_cents": 0,
                "ending_balance_cents": 0,
            },
        )
        return new_id

    def noon(self, day: str) -> str:
        y, m, d = (int(part) for part in day.split("-"))
        return datetime(y, m, d, 12, tzinfo=self.zone).isoformat(timespec="seconds")

    def line(self, account_id: str, day: str, *amounts: int, recon: str | None = None) -> str:
        """A new bank line on `day` holding one part per amount (a batch `line_group`
        for more than one), assigned whole to `recon` when given; its id."""
        items = [
            {
                "id": str(uuid4()),
                "title": "contract statement line",
                "amount_cents": amount,
                "account_id": account_id,
                "date": self.noon(day),
                **({"line_group": "g"} if len(amounts) > 1 else {}),
            }
            for amount in amounts
        ]
        self.transactions.extend(item["id"] for item in items)
        created = self.client.post("/transactions/batch", json_body={"transactions": items})
        first = created["created"][0]
        if recon is not None:
            self.client.put(f"/transactions/{first['id']}", json_body={"reconciliation_id": recon})
        return first["bank_line_id"]

    def opening_balance(self, account_id: str, day: str, recon: str | None = None) -> str:
        """The account's opening balance, assigned to `recon` when given; its line's id."""
        tx_id = str(uuid4())
        self.transactions.append(tx_id)
        made = self.client.post(
            f"/accounts/{account_id}/opening-balance",
            json_body={"transaction_id": tx_id, "amount_cents": 50000, "date": self.noon(day)},
        )
        if recon is not None:
            self.client.put(f"/transactions/{tx_id}", json_body={"reconciliation_id": recon})
        return made["bank_line_id"]

    def cleanup(self) -> None:
        steps = [
            *(("POST", f"/accounts/{a}/unarchive") for a in self.accounts),
            *(("POST", f"/reconciliations/{r}/revert") for r in self.reconciliations),
            *(("DELETE", f"/reconciliations/{r}") for r in self.reconciliations),
            *(("DELETE", f"/transactions/{t}") for t in self.transactions),
            *(("DELETE", f"/accounts/{a}") for a in self.accounts),
        ]
        for method, path in steps:
            try:
                if method == "POST":
                    self.client.post(path)
                else:
                    self.client.delete(path)
            except EngineError:
                pass


@pytest.fixture
def scratch(client):
    """A `Scratch` on the practice user, cleaned up after the test whatever its outcome."""
    made = Scratch(client)
    yield made
    made.cleanup()
