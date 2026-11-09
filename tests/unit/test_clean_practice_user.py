"""scripts/clean_practice_user.py: what it matches, the order it removes in, what it leaves.

A bank account's name is the engine's (`BCP-9234`), so a bank account is the suite's by its
number starting `9`, never by its name; a person, a category and a hashtag by a `contract-` or
`freshman-` name; the practice account `BCP-0000` never.

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

from expense.config import Config
from expense.http import ExpenseClient
from tests.scripts_loader import load_script
from tests.unit.helpers import account_with_currencies, held_currency

PRACTICE = "http://127.0.0.1:8002"
TARGET = ["--engine-url", PRACTICE]


def _bank(ident, last4, **fields):
    """A bank account named as the engine builds it from its number; `last4` None: no number."""
    numbers = [dict(last4=last4, start_date=None, end_date=None)] if last4 else []
    name = f"BCP-{last4}" if last4 else "BCP"
    held = dict(id=ident, name=name, bank_code="BCP", numbers=numbers)
    return account_with_currencies(**{**held, **fields})


def _person(ident, name, **fields):
    return account_with_currencies(
        id=ident, name=name, kind="person", bank_code=None, numbers=[], **fields
    )


def _statement(ident, account, status=1):
    return dict(id=ident, account_id=account, name=f"stmt {ident}", status=status)


class FakeEngine:
    """The practice user's accounts, statements, transactions, categories and hashtags;
    `calls` is every write, `METHOD path`, in the order sent; the transactions list
    comes `page` rows at a time under a cursor."""

    def __init__(
        self, accounts, statements=(), txs=(), categories=(), hashtags=(), refuse=(), page=200
    ):
        self.accounts = {a["id"]: a for a in accounts}
        self.statements = {r["id"]: r for r in statements}
        self.page = page
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
        if path == "/statements":
            mine = [r for r in self.statements.values() if r["account_id"] == query["account_id"]]
            return dict(items=mine)
        if path == "/transactions/count":
            if "account_id" in query:
                held = [t for t in self.txs.values() if t["account_id"] == query["account_id"]]
            else:
                held = [t for t in self.txs.values() if query["hashtag_id"] in t["hashtag_ids"]]
            return dict(count=len(held))
        if path == "/transactions":
            mine = [t for t in self.txs.values() if t["account_id"] == query["account_id"]]
            if "after" in query:
                mine = [t for t in mine if t["id"] > query["after"]]
            shown = mine[: self.page]
            more = len(mine) > self.page
            return dict(items=shown, limit=200, next_cursor=shown[-1]["id"] if more else None)
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
            self.statements[ident]["status"] = 1
        elif path.startswith("/statements/"):
            self.statements.pop(ident)
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
def test_a_read_only_run_lists_what_the_test_numbers_and_names_match_and_writes_nothing(
    script, capsys
):
    engine = FakeEngine(
        accounts=[
            _bank("a1", "9234"),
            _bank("a2", "0123"),
            _bank("a3", "0000"),
            _bank("a4", None),
            _person("p1", "contract-p-1"),
            _person("p2", "ALEJO"),
            _person("p3", "BCP-9999"),
        ],
        statements=[_statement("r1", "a1"), _statement("r2", "a2")],
        categories=[dict(id="c1", name="contract-c-1"), dict(id="c2", name="@Pendiente")],
        hashtags=[dict(id="h1", name="freshman-h"), dict(id="h2", name="Pendiente")],
    )
    _serve(engine)

    assert script.main(TARGET) == 0

    out = capsys.readouterr().out
    assert "'BCP-9234'" in out and "'stmt r1' (draft)" in out and "'contract-p-1'" in out
    assert "'contract-c-1'" in out and "'freshman-h'" in out
    for untouched in (
        "BCP-0123",
        "BCP-0000",
        "'BCP'",
        "ALEJO",
        "BCP-9999",
        "stmt r2",
        "@Pendiente",
        "'Pendiente'",
    ):
        assert untouched not in out
    assert engine.calls == []


@respx.mock
def test_a_bank_account_is_never_matched_by_its_name(script, capsys):
    engine = FakeEngine(accounts=[_bank("a1", "0123", name="contract-x")])
    _serve(engine)

    assert script.main([*TARGET, "--apply"]) == 0

    assert engine.calls == []
    assert "contract-x" not in capsys.readouterr().out


@respx.mock
def test_the_practice_account_is_never_removed_whatever_it_is_asked_to_match(script):
    engine = FakeEngine(accounts=[_bank("a1", "0000")])
    _serve(engine)

    assert script.main([*TARGET, "--prefix", "BCP", "--apply"]) == 0

    assert engine.calls == [] and list(engine.accounts) == ["a1"]


@respx.mock
def test_the_listing_names_each_account_with_its_currencies_and_code(script, capsys):
    engine = FakeEngine(
        accounts=[
            _bank(
                "a1",
                "9301",
                statement_code="CRD",
                currencies=[held_currency("PEN"), held_currency("USD")],
            ),
            _bank("a2", "9302"),
        ],
    )
    _serve(engine)

    assert script.main(TARGET) == 0

    out = capsys.readouterr().out
    assert "'BCP-9301' (PEN, USD; CRD), 0 tx" in out
    assert "'BCP-9302' (PEN; no code), 0 tx" in out
    assert engine.calls == []


@respx.mock
def test_apply_removes_in_the_order_the_deletes_need(script):
    engine = FakeEngine(
        accounts=[
            _bank("a1", "9401", is_archived=True),
            _bank("a2", "9402", currencies=[held_currency("PEN"), held_currency("USD")]),
        ],
        statements=[_statement("r1", "a1", status=2), _statement("r2", "a2")],
        txs=[dict(id="t1", account_id="a1", hashtag_ids=["h1"])],
        categories=[dict(id="c1", name="contract-c-1")],
        hashtags=[dict(id="h1", name="contract-h-1")],
    )
    _serve(engine)

    assert script.main([*TARGET, "--apply"]) == 0

    assert engine.calls == [
        "POST /accounts/a1/unarchive",
        "POST /statements/r1/revert",
        "DELETE /statements/r1",
        "DELETE /statements/r2",
        "DELETE /transactions/t1",
        "DELETE /hashtags/h1",
        "DELETE /categories/c1",
        "DELETE /accounts/a1",
        "DELETE /accounts/a2",
    ]
    assert not (engine.accounts or engine.statements or engine.txs)


@respx.mock
def test_a_hashtag_still_on_a_live_transaction_is_left(script, capsys):
    engine = FakeEngine(
        accounts=[_bank("a1", "0123")],
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
        accounts=[_bank("a1", "9501")],
        refuse=["DELETE /accounts/a1"],
    )
    _serve(engine)

    assert script.main([*TARGET, "--apply"]) == 1

    out = capsys.readouterr().out
    assert "left delete account 'BCP-9501': 409 CONFLICT" in out
    assert "1 matched record(s) remain" in out


@respx.mock
def test_a_prefix_replaces_the_test_names(script, capsys):
    engine = FakeEngine(
        accounts=[
            _person("a1", "probe-1"),
            _person("a2", "contract-x"),
            _bank("a3", "9601"),
        ]
    )
    _serve(engine)

    assert script.main([*TARGET, "--prefix", "probe-", "--apply"]) == 0

    assert engine.calls == ["DELETE /accounts/a1"]
    assert list(engine.accounts) == ["a2", "a3"]


@respx.mock
def test_a_system_row_appearing_between_two_snapshots_is_no_leftover(script):
    """The engine creates `@Pendiente`, `@Opening` and the pending hashtag on first need
    and never deletes them, so a test that brings one about leaves nothing behind."""
    engine = FakeEngine(accounts=[_bank("a1", None)])
    _serve(engine)
    with ExpenseClient(Config(engine_url=PRACTICE, token="ewe_pat_practice")) as client:
        before = script.holdings(client)
        for ident, name, key in (("c8", "@Pendiente", "pending"), ("c9", "@Opening", "opening")):
            engine.categories[ident] = dict(id=ident, name=name, system_key=key)
        engine.hashtags["h9"] = dict(id="h9", name="Pendiente", system_key="pending")
        engine.categories["c1"] = dict(id="c1", name="contract-c-1", system_key=None)
        after = script.holdings(client)

    assert {ident: after[ident] for ident in set(after) - set(before)} == {
        "c1": "category 'contract-c-1'"
    }


@respx.mock
def test_a_system_row_is_never_matched_or_deleted(script, capsys):
    engine = FakeEngine(
        accounts=[],
        categories=[dict(id="c1", name="contract-sys", system_key="pending")],
        hashtags=[dict(id="h1", name="contract-sys", system_key="pending")],
    )
    _serve(engine)

    assert script.main([*TARGET, "--apply"]) == 0

    assert engine.calls == []
    assert "contract-sys" not in capsys.readouterr().out


@respx.mock
def test_a_refused_transaction_delete_is_listed_once(script, capsys):
    engine = FakeEngine(
        accounts=[_bank("a1", "9501")],
        txs=[
            dict(id="t1", account_id="a1", hashtag_ids=[]),
            dict(id="t2", account_id="a1", hashtag_ids=[]),
        ],
        refuse=["DELETE /transactions/t1"],
    )
    _serve(engine)

    assert script.main([*TARGET, "--apply"]) == 1

    assert set(engine.txs) == {"t1"}
    assert capsys.readouterr().out.count("left delete transaction t1 ") == 1


@respx.mock
def test_a_page_holding_only_refused_deletes_does_not_hide_the_rows_behind_it(script, capsys):
    engine = FakeEngine(
        accounts=[_bank("a1", "9501")],
        txs=[dict(id=f"t{n}", account_id="a1", hashtag_ids=[]) for n in range(1, 6)],
        refuse=["DELETE /transactions/t1", "DELETE /transactions/t2"],
        page=2,
    )
    _serve(engine)

    assert script.main([*TARGET, "--apply"]) == 1

    assert set(engine.txs) == {"t1", "t2"}
    out = capsys.readouterr().out
    assert out.count("left delete transaction t1 ") == 1
    assert out.count("left delete transaction t2 ") == 1
