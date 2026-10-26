"""No request carries `line_code`, `statement_line` or `statement_place`: the guard trips.

The engine sets each of these fields itself and refuses it in every request body as
`422` `UNKNOWN_FIELD` (contract: "Transactions (Ledger)", "Bank lines"). The guard is
conftest's autouse `_no_read_only_fields_in_requests` with
`helpers.refuse_read_only_fields`; these tests prove it fails a test whose request body
holds any of the keys, wherever the key sits and whichever fake engine answers.
"""

import inspect
from contextlib import contextmanager

import httpx
import pytest
import respx

from expense.config import Config
from expense.http import ExpenseClient
from tests.unit.helpers import (
    ENGINE_URL,
    READ_ONLY_FIELD_LEAKS,
    READ_ONLY_FIELDS,
    FakeClient,
    ReadOnlyFieldLeak,
    import_part,
    line_code_of,
    put_answer,
    read_only_field_paths,
)

CODE = line_code_of("bl1")

#: A value each field reads on a line, as a read row would pass it back.
VALUES = {"line_code": CODE, "statement_line": "SIG-202603-029", "statement_place": 29}


def test_the_guarded_fields_are_the_three_the_engine_sets():
    assert set(READ_ONLY_FIELDS) == set(VALUES)


@contextmanager
def tripped(field: str):
    """The block must raise `ReadOnlyFieldLeak` naming `field` and record its leak.
    The record is emptied afterwards, so the autouse check passes the tripping test
    itself."""
    with pytest.raises(ReadOnlyFieldLeak, match=field) as caught:
        yield caught
    leaks = list(READ_ONLY_FIELD_LEAKS)
    READ_ONLY_FIELD_LEAKS.clear()
    assert leaks, "the leak was raised but not recorded"
    assert all(field in leak for leak in leaks), leaks


# ---- where the key sits -------------------------------------------------------


def _bodies(field: str) -> list[tuple[dict, list[str]]]:
    value = VALUES[field]
    return [
        ({"title": "x", field: value}, [f"body.{field}"]),
        (
            {"transactions": [{"id": "a"}, {"id": "b", field: value}]},
            [f"body.transactions[1].{field}"],
        ),
        (
            {"parts": [{"amount_cents": -100, field: value}, {"amount_cents": -200}]},
            [f"body.parts[0].{field}"],
        ),
        (
            {
                "dry_run": True,
                "rows": [
                    {"id": "r1", "title": "x", "operation_code": "0001"},
                    {"id": "r2", "title": "y", "operation_code": "0002", field: value},
                ],
            },
            [f"body.rows[1].{field}"],
        ),
        (
            {"title": "x", "hashtag_ids": [], "operation_code": "12", field: value},
            [f"body.{field}"],
        ),
        ({"amount_cents": 1000, "date": "2026-10-01", field: None}, [f"body.{field}"]),
        ({"name": "Octubre", "date_end": "2026-10-31", field: value}, [f"body.{field}"]),
    ]


_WHERE_IDS = [
    "top-level",
    "batch-item",
    "split-part",
    "import-row",
    "put-body",
    "sent-as-null",
    "reconciliation",
]


@pytest.mark.parametrize(
    ("field", "body", "where"),
    [(field, body, where) for field in READ_ONLY_FIELDS for body, where in _bodies(field)],
    ids=[f"{field}-{case}" for field in READ_ONLY_FIELDS for case in _WHERE_IDS],
)
def test_the_key_is_found_at_any_depth(field, body, where):
    assert read_only_field_paths(body) == where


def test_every_key_in_one_body_is_found():
    body = {"line_code": CODE, "parts": [{"statement_line": "x", "statement_place": 1}]}
    assert read_only_field_paths(body) == [
        "body.line_code",
        "body.parts[0].statement_line",
        "body.parts[0].statement_place",
    ]


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"title": "line_code", "operation_code": "12"},
        {"transactions": [{"description": "statement_line"}]},
        ["statement_place"],
        # `PUT /reconciliations/{id}/statement-order`: a statement's places are a
        # list of line ids and empty slots under `places`
        # (contract: "Reconciliations", "A statement's order").
        {"places": ["bl1", None, "bl2"]},
    ],
    ids=["no-body", "empty", "value-not-key", "nested-value", "bare-list", "statement-order"],
)
def test_a_clean_body_passes(body):
    assert read_only_field_paths(body) == []


# ---- every fake engine refuses it --------------------------------------------


@pytest.mark.parametrize("field", READ_ONLY_FIELDS)
@pytest.mark.parametrize("verb", ["post", "put"])
def test_fake_client_refuses_it_before_sending(verb, field):
    client = FakeClient()
    with tripped(field):
        getattr(client, verb)("/transactions/t1", json_body={field: VALUES[field]})
    assert client.calls == []


@pytest.mark.parametrize("field", READ_ONLY_FIELDS)
def test_fake_client_refuses_it_by_position_too(field):
    client = FakeClient()
    with tripped(field):
        client.post("/transactions/batch", {"transactions": [{field: VALUES[field]}]})
    assert client.calls == []


@pytest.mark.parametrize("field", READ_ONLY_FIELDS)
@pytest.mark.parametrize("verb", ["post", "put"])
def test_a_verb_a_test_puts_on_fake_client_is_checked_too(verb, field):
    """Many tests replace `fake_client.post` / `.put` with their own function;
    the check still runs first, and the function never sees the body."""
    client = FakeClient()
    seen: list = []
    setattr(client, verb, lambda path, json_body=None: seen.append(json_body))
    with tripped(field):
        getattr(client, verb)("/transactions/t1", json_body={"parts": [{field: VALUES[field]}]})
    assert seen == []


@pytest.mark.parametrize("field", READ_ONLY_FIELDS)
@respx.mock
def test_the_real_client_refuses_it_before_it_reaches_respx(field):
    """The autouse fixture wraps `httpx.Client.send`, which respx answers below,
    so a write through the real `ExpenseClient` is checked with no setup."""
    route = respx.post(f"{ENGINE_URL}/v1/transactions/import").mock(
        return_value=httpx.Response(200, json={})
    )
    cfg = Config(engine_url=ENGINE_URL, token="ewe_pat_test")
    body = {"dry_run": True, "rows": [{"title": "x", field: VALUES[field]}]}
    with tripped(field), ExpenseClient(cfg) as client:
        client.post("/transactions/import", json_body=body)
    assert not route.called


@respx.mock
def test_the_real_client_sends_a_clean_body():
    titled = {**import_part("t1", -4200, line="bl1", title="x"), "version": 2}
    route = respx.put(f"{ENGINE_URL}/v1/transactions/t1").mock(
        return_value=httpx.Response(200, json=put_answer(titled, [titled]))
    )
    cfg = Config(engine_url=ENGINE_URL, token="ewe_pat_test")
    with ExpenseClient(cfg) as client:
        client.put("/transactions/t1", json_body={"title": "x", "operation_code": "12"})
    assert route.called
    assert READ_ONLY_FIELD_LEAKS == []


@respx.mock
def test_the_real_client_sends_a_statement_order():
    route = respx.put(f"{ENGINE_URL}/v1/reconciliations/r1/statement-order").mock(
        return_value=httpx.Response(200, json={})
    )
    cfg = Config(engine_url=ENGINE_URL, token="ewe_pat_test")
    with ExpenseClient(cfg) as client:
        client.put("/reconciliations/r1/statement-order", json_body={"places": ["bl1", None]})
    assert route.called
    assert READ_ONLY_FIELD_LEAKS == []


# ---- a leak the app swallows still fails the test ----------------------------

_SWALLOWING_SUITE = '''
import httpx
import respx

from expense.config import Config
from expense.http import ExpenseClient


def _swallowed(write):
    """What a screen does with a write that fails: catch it and carry on."""
    try:
        write()
    except Exception:
        pass


def test_fake_client_leak(fake_client):
    from expense.http import ExpenseClient as Factory

    body = {"transactions": [{"title": "x", "line_code": "#000001"}]}
    _swallowed(lambda: Factory().post("/transactions/batch", json_body=body))


def test_fake_client_place_leak(fake_client):
    from expense.http import ExpenseClient as Factory

    body = {"name": "Octubre", "statement_place": 3}
    _swallowed(lambda: Factory().put("/reconciliations/r1", json_body=body))


@respx.mock
def test_respx_leak():
    respx.post("https://api.example.com/v1/transactions/batch").mock(
        return_value=httpx.Response(200, json={})
    )
    cfg = Config(engine_url="https://api.example.com", token="ewe_pat_test")
    body = {"transactions": [{"title": "x", "statement_line": "SIG-202603-029"}]}
    with ExpenseClient(cfg) as client:
        _swallowed(lambda: client.post("/transactions/batch", json_body=body))


def test_clean(fake_client):
    from expense.http import ExpenseClient as Factory

    Factory().post("/transactions/batch", json_body={"transactions": [{"title": "x"}]})
'''


def test_a_swallowed_leak_still_fails_the_test(tmp_path):
    """A tiny suite under a copy of tests/unit's conftest: three tests send a
    read-only field and swallow the refusal, one sends a clean body. The three fail
    at teardown, naming the request; the clean one passes."""
    import os
    import shutil
    import subprocess
    import sys

    from tests.unit import conftest

    unit = tmp_path / "tests" / "unit"
    unit.mkdir(parents=True)
    (tmp_path / "tests" / "__init__.py").write_text("")
    (unit / "__init__.py").write_text("")
    for name in ("conftest.py", "helpers.py"):
        shutil.copy(conftest._UNIT_DIR / name, unit / name)
    (unit / "test_leak.py").write_text(inspect.cleandoc(_SWALLOWING_SUITE) + "\n")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/unit", "-n", "0", "-p", "no:cacheprovider"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 1, out
    assert "ERROR tests/unit/test_leak.py::test_fake_client_leak" in out
    assert "ERROR tests/unit/test_leak.py::test_fake_client_place_leak" in out
    assert "ERROR tests/unit/test_leak.py::test_respx_leak" in out
    assert "POST /transactions/batch sends line_code at body.transactions[0].line_code" in out
    assert "PUT /reconciliations/r1 sends statement_place at body.statement_place" in out
    assert (
        "POST /v1/transactions/batch sends statement_line at body.transactions[0].statement_line"
        in out
    )
    assert "4 passed, 3 errors" in out, out
