"""scripts/clean_practice_user.py: what it matches, the order it removes in, what it leaves.

The engine is a small stateful fake, respx-mocked at the practice engine's address: a
delete takes its record off the lists, so the script's read after `--apply` sees what is
left. A request anywhere else is unmocked and fails the test. Records are built with
dict(), not quoted keys: the drift script scans this folder.

The live run of the same removal, on records a test leaves on purpose, is
tests/contract/test_clean_practice_user.py.
"""

import httpx
import pytest
import respx

from tests.scripts_loader import load_script

PRACTICE = "http://127.0.0.1:8002"
TARGET = ["--engine-url", PRACTICE]


def _account(ident, name, code=None, archived=False):
    return dict(
        id=ident,
        name=name,
        currency_code="PEN",
        statement_code=code,
        is_archived=archived,
    )


def _recon(ident, account, twin=None, status=1):
    return dict(id=ident, account_id=account, name=f"stmt {ident}", status=status, twin_id=twin)


class FakeEngine:
    """The practice user's accounts, reconciliations, transactions, categories and
    hashtags; `calls` is every write, `METHOD path`, in the order sent."""

    def __init__(self, accounts, recons=(), txs=(), categories=(), hashtags=(), refuse=()):
        self.accounts = {a["id"]: a for a in accounts}
        self.recons = {r["id"]: r for r in recons}
        self.txs = {t["id"]: t for t in txs}
        self.categories = {c["id"]: c for c in categories}
        self.hashtags = {h["id"]: h for h in hashtags}
        self.refuse = set(refuse)
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/v1")
        query = dict(request.url.params)
        if request.method == "GET":
            return httpx.Response(200, json=self._read(path, query))
        call = f"{request.method} {path}"
        self.calls.append(call)
        if call in self.refuse:
            error = dict(code="CONFLICT", message="refused", reasons=dict(id="HAS_TRANSACTIONS"))
            return httpx.Response(409, json=dict(error=error))
        self._write(request.method, path)
        return httpx.Response(200, json=dict())

    def _read(self, path, query):
        if path == "/accounts":
            return dict(items=list(self.accounts.values()))
        if path == "/reconciliations":
            mine = [r for r in self.recons.values() if r["account_id"] == query["account_id"]]
            return dict(items=mine)
        if path.startswith("/reconciliations/"):
            return self.recons[path.rsplit("/", 1)[1]]
        if path == "/transactions/count":
            if "account_id" in query:
                held = [t for t in self.txs.values() if t["account_id"] == query["account_id"]]
            else:
                held = [t for t in self.txs.values() if query["hashtag_id"] in t["hashtag_ids"]]
            return dict(count=len(held))
        if path == "/transactions":
            mine = [t for t in self.txs.values() if t["account_id"] == query["account_id"]]
            return dict(items=mine, limit=200, next_cursor=None)
        if path == "/categories":
            return dict(items=list(self.categories.values()))
        if path == "/hashtags":
            return dict(items=list(self.hashtags.values()))
        raise AssertionError(f"unexpected read {path}")

    def _write(self, method, path):
        """`/<kind>/<id>` deleted, or `/<kind>/<id>/<action>` posted."""
        _kind, ident, *action = path.split("/")[1:]
        if action == ["unarchive"]:
            self.accounts[ident]["is_archived"] = False
        elif action == ["revert"]:
            for half in (ident, self.recons[ident]["twin_id"]):
                if half:
                    self.recons[half]["status"] = 1
        elif path.startswith("/reconciliations/"):
            twin = self.recons.pop(ident)["twin_id"]
            if twin:
                self.recons.pop(twin)
        else:
            tables = (self.accounts, self.txs, self.categories, self.hashtags)
            [table] = [t for t in tables if ident in t]
            table.pop(ident)


@pytest.fixture
def script(monkeypatch):
    monkeypatch.setenv("EXPENSE_PAT", "ewe_pat_practice")
    return load_script("clean_practice_user.py")


def _serve(engine):
    respx.route(url__startswith=PRACTICE).mock(side_effect=engine)


def test_only_the_practice_engine_is_a_target(script):
    for url in (PRACTICE, f"{PRACTICE}/", "http://localhost:8002"):
        assert script.practice_url(url), url
    for url in (
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8001",
        "https://127.0.0.1:8002",
        "http://example.com:8002",
        "http://127.0.0.1",
        "http://127.0.0.1:port",
    ):
        assert not script.practice_url(url), url


@respx.mock
def test_another_target_is_refused_before_any_request(script, capsys):
    assert script.main(["--engine-url", "http://127.0.0.1:8000", "--apply"]) == 2
    assert "only the practice engine on :8002" in capsys.readouterr().err


@respx.mock
def test_no_key_is_refused_before_any_request(script, monkeypatch, capsys):
    monkeypatch.delenv("EXPENSE_PAT")
    assert script.main(TARGET) == 2
    assert "EXPENSE_PAT is not set" in capsys.readouterr().err


@respx.mock
def test_a_read_only_run_lists_what_the_test_names_match_and_writes_nothing(script, capsys):
    engine = FakeEngine(
        accounts=[_account("a1", "contract-stmt-1", "ZZQ"), _account("a2", "BCP Signature PEN")],
        recons=[_recon("r1", "a1"), _recon("r2", "a2")],
        categories=[dict(id="c1", name="contract-c-1"), dict(id="c2", name="@Pendiente")],
        hashtags=[dict(id="h1", name="freshman-h"), dict(id="h2", name="Pendiente")],
    )
    _serve(engine)

    assert script.main(TARGET) == 0

    out = capsys.readouterr().out
    assert "'contract-stmt-1'" in out and "'stmt r1'" in out
    assert "'contract-c-1'" in out and "'freshman-h'" in out
    for untouched in ("BCP Signature", "stmt r2", "@Pendiente", "'Pendiente'"):
        assert untouched not in out
    assert engine.calls == []


@respx.mock
def test_apply_removes_in_the_order_the_deletes_need(script):
    engine = FakeEngine(
        accounts=[
            _account("a1", "contract-card-pen", "ZZQ", archived=True),
            _account("a2", "contract-card-usd", "ZZQ"),
        ],
        recons=[_recon("r1", "a1", twin="r2", status=2), _recon("r2", "a2", twin="r1", status=2)],
        txs=[dict(id="t1", account_id="a1", hashtag_ids=["h1"])],
        categories=[dict(id="c1", name="contract-c-1")],
        hashtags=[dict(id="h1", name="contract-h-1")],
    )
    _serve(engine)

    assert script.main([*TARGET, "--apply"]) == 0

    assert engine.calls == [
        "POST /accounts/a1/unarchive",
        "POST /reconciliations/r1/revert",
        "DELETE /reconciliations/r1",
        "DELETE /transactions/t1",
        "DELETE /hashtags/h1",
        "DELETE /categories/c1",
        "DELETE /accounts/a1",
        "DELETE /accounts/a2",
    ]
    assert not (engine.accounts or engine.recons or engine.txs)


@respx.mock
def test_a_card_statement_half_on_an_unmatched_account_is_left_whole(script, capsys):
    engine = FakeEngine(
        accounts=[_account("a1", "contract-card-pen", "ZZQ"), _account("a2", "Card USD", "ZZQ")],
        recons=[_recon("r1", "a1", twin="r2"), _recon("r2", "a2", twin="r1")],
    )
    _serve(engine)

    assert script.main([*TARGET, "--apply"]) == 1

    assert set(engine.recons) == {"r1", "r2"}
    assert not [call for call in engine.calls if "reconciliations" in call]
    out = capsys.readouterr().out
    assert "left statement 'stmt r1' + 'stmt r2': its other half is on an unmatched account" in out


@respx.mock
def test_a_hashtag_still_on_a_live_transaction_is_left(script, capsys):
    engine = FakeEngine(
        accounts=[_account("a1", "BCP PEN")],
        txs=[dict(id="t1", account_id="a1", hashtag_ids=["h1"])],
        hashtags=[dict(id="h1", name="contract-h-1")],
    )
    _serve(engine)

    assert script.main([*TARGET, "--apply"]) == 1

    assert engine.calls == []
    assert "left hashtag 'contract-h-1': still on 1 live transaction(s)" in capsys.readouterr().out


@respx.mock
def test_a_refused_delete_is_left_and_fails_the_run(script, capsys):
    engine = FakeEngine(
        accounts=[_account("a1", "contract-acct-1")], refuse=["DELETE /accounts/a1"]
    )
    _serve(engine)

    assert script.main([*TARGET, "--apply"]) == 1

    out = capsys.readouterr().out
    assert "left delete account 'contract-acct-1': 409 CONFLICT" in out
    assert "1 matched record(s) remain" in out


@respx.mock
def test_a_prefix_replaces_the_test_names(script, capsys):
    engine = FakeEngine(accounts=[_account("a1", "probe-1"), _account("a2", "contract-x")])
    _serve(engine)

    assert script.main([*TARGET, "--prefix", "probe-", "--apply"]) == 0

    assert engine.calls == ["DELETE /accounts/a1"]
    assert list(engine.accounts) == ["a2"]
