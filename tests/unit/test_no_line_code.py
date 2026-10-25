"""No request carries `line_code`: the guard trips.

The engine mints every line's `line_code` and refuses it on every write as `422`
`UNKNOWN_FIELD` (contract: "Transactions (Ledger)", "Bank lines"). The guard is
conftest's autouse `_no_line_code_in_requests` with `helpers.refuse_line_code`;
these tests prove it fails a test whose request body holds the key, wherever the
key sits and whichever fake engine answers.
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
    LINE_CODE_LEAKS,
    FakeClient,
    LineCodeLeak,
    import_part,
    line_code_of,
    line_code_paths,
    put_answer,
)

CODE = line_code_of("bl1")


@contextmanager
def tripped():
    """The block must raise `LineCodeLeak` and record its leak. The record is
    emptied afterwards, so the autouse check passes the tripping test itself."""
    with pytest.raises(LineCodeLeak, match="line_code") as caught:
        yield caught
    leaks = list(LINE_CODE_LEAKS)
    LINE_CODE_LEAKS.clear()
    assert leaks, "the leak was raised but not recorded"


# ---- where the key sits -------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "where"),
    [
        ({"title": "x", "line_code": CODE}, ["body.line_code"]),
        (
            {"transactions": [{"id": "a"}, {"id": "b", "line_code": CODE}]},
            ["body.transactions[1].line_code"],
        ),
        (
            {"parts": [{"amount_cents": -100, "line_code": CODE}, {"amount_cents": -200}]},
            ["body.parts[0].line_code"],
        ),
        (
            {
                "dry_run": True,
                "rows": [
                    {"id": "r1", "title": "x", "operation_code": "0001"},
                    {"id": "r2", "title": "y", "operation_code": "0002", "line_code": CODE},
                ],
            },
            ["body.rows[1].line_code"],
        ),
        (
            {"title": "x", "hashtag_ids": [], "operation_code": "12", "line_code": CODE},
            ["body.line_code"],
        ),
    ],
    ids=["top-level", "batch-item", "split-part", "import-row", "put-body"],
)
def test_the_key_is_found_at_any_depth(body, where):
    assert line_code_paths(body) == where


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"title": "line_code", "operation_code": "12"},
        {"transactions": [{"description": "line_code"}]},
        ["line_code"],
    ],
    ids=["no-body", "empty", "value-not-key", "nested-value", "bare-list"],
)
def test_a_clean_body_passes(body):
    assert line_code_paths(body) == []


# ---- every fake engine refuses it --------------------------------------------


@pytest.mark.parametrize("verb", ["post", "put"])
def test_fake_client_refuses_it_before_sending(verb):
    client = FakeClient()
    with tripped():
        getattr(client, verb)("/transactions/t1", json_body={"line_code": CODE})
    assert client.calls == []


def test_fake_client_refuses_it_by_position_too():
    client = FakeClient()
    with tripped():
        client.post("/transactions/batch", {"transactions": [{"line_code": CODE}]})
    assert client.calls == []


@pytest.mark.parametrize("verb", ["post", "put"])
def test_a_verb_a_test_puts_on_fake_client_is_checked_too(verb):
    """Many tests replace `fake_client.post` / `.put` with their own function;
    the check still runs first, and the function never sees the body."""
    client = FakeClient()
    seen: list = []
    setattr(client, verb, lambda path, json_body=None: seen.append(json_body))
    with tripped():
        getattr(client, verb)("/transactions/t1", json_body={"parts": [{"line_code": CODE}]})
    assert seen == []


@respx.mock
def test_the_real_client_refuses_it_before_it_reaches_respx():
    """The autouse fixture wraps `httpx.Client.send`, which respx answers below,
    so a write through the real `ExpenseClient` is checked with no setup."""
    route = respx.post(f"{ENGINE_URL}/v1/transactions/import").mock(
        return_value=httpx.Response(200, json={})
    )
    cfg = Config(engine_url=ENGINE_URL, token="ewe_pat_test")
    body = {"dry_run": True, "rows": [{"title": "x", "line_code": CODE}]}
    with tripped(), ExpenseClient(cfg) as client:
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
    assert LINE_CODE_LEAKS == []


# ---- a leak the app swallows still fails the test ----------------------------

_SWALLOWING_SUITE = '''
import httpx
import respx

from expense.config import Config
from expense.http import ExpenseClient

BODY = {"transactions": [{"title": "x", "line_code": "#000001"}]}


def _swallowed(write):
    """What a screen does with a write that fails: catch it and carry on."""
    try:
        write()
    except Exception:
        pass


def test_fake_client_leak(fake_client):
    from expense.http import ExpenseClient as Factory

    _swallowed(lambda: Factory().post("/transactions/batch", json_body=BODY))


@respx.mock
def test_respx_leak():
    respx.post("https://api.example.com/v1/transactions/batch").mock(
        return_value=httpx.Response(200, json={})
    )
    cfg = Config(engine_url="https://api.example.com", token="ewe_pat_test")
    with ExpenseClient(cfg) as client:
        _swallowed(lambda: client.post("/transactions/batch", json_body=BODY))


def test_clean(fake_client):
    from expense.http import ExpenseClient as Factory

    Factory().post("/transactions/batch", json_body={"transactions": [{"title": "x"}]})
'''


def test_a_swallowed_leak_still_fails_the_test(tmp_path):
    """A tiny suite under a copy of tests/unit's conftest: two tests send
    `line_code` and swallow the refusal, one sends a clean body. The two fail
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
    assert "ERROR tests/unit/test_leak.py::test_respx_leak" in out
    assert "POST /transactions/batch sends line_code at body.transactions[0].line_code" in out
    assert "POST /v1/transactions/batch sends line_code at body.transactions[0].line_code" in out
    assert "3 passed, 2 errors" in out, out
