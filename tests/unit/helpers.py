"""Shared, importable helpers for tests/unit — the non-fixture half of the
test infrastructure (fixtures live in conftest.py).

Import style: `from tests.unit.helpers import FakeClient, wait_for, ...`.
Keep this module free of Textual imports at module level so CLI command test
files pay no TUI import cost.
"""

import asyncio
import io
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import typer
from rich.console import Console

from expense.context import AppContext
from expense.errors import EngineError

ENGINE_URL = "https://api.example.com"


# ---------------------------------------------------------------------------
# Typer root wiring
# ---------------------------------------------------------------------------


def real_cli_app() -> typer.Typer:
    """The app `expense` actually runs — `expense.__main__.app`.

    Prefer this to `make_cli_app` whenever the *path* to the command is part of
    what the test is asserting: a group name, a subcommand name, or a command
    that moved. A hand-wired root proves the callback does its job with whatever
    name the test chose, which is exactly no coverage of the name the user types.

    The import is function-local because `__main__` pulls in the TUI, and the
    CLI command test files should not pay Textual's import cost just to exist.
    """
    from expense.__main__ import app

    return app


def make_cli_app(
    sub_app: typer.Typer | None = None,
    name: str | None = None,
    *,
    commands: dict[str, Callable] | None = None,
) -> typer.Typer:
    """Root Typer app wired like expense/__main__.py (minus --verbose).

    Two mount styles:

        make_cli_app(accounts_app, "accounts")            # add_typer group
        make_cli_app(commands={"dashboard": dashboard})   # bare command(s)
    """
    cli_app = typer.Typer()

    @cli_app.callback()
    def _root(ctx: typer.Context) -> None:
        ctx.obj = AppContext()

    if sub_app is not None:
        cli_app.add_typer(sub_app, name=name)
    for command_name, callback in (commands or {}).items():
        cli_app.command(command_name)(callback)
    return cli_app


# ---------------------------------------------------------------------------
# CLI output normalisation
# ---------------------------------------------------------------------------


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[mGKH]")


def strip_panel(output: str) -> str:
    """Flatten Typer/Rich error output to one plain, searchable line.

    Rich decides whether to colour by sniffing the environment, so the *same*
    error prints differently in CI than it does locally: GitHub Actions is
    treated as a terminal, which wraps usage errors in a box AND highlights the
    offending flag — splicing escape codes *inside* the token, so a plain
    ``"No such option: --include-deleted" in result.output`` finds nothing
    (`--include-deleted` arrives as `-` + `-include` + `-deleted`).

    Assert against this, never raw ``result.output``, whenever the expected text
    contains a flag name or could wrap at the panel edge.
    """
    no_ansi = _ANSI_ESCAPE_RE.sub("", output)
    no_box = "".join(c for c in no_ansi if c not in "│╭╮╰╯─\n\t")
    return " ".join(no_box.split())


# ---------------------------------------------------------------------------
# Rich rendering
# ---------------------------------------------------------------------------


def render_text(*renderables: object, width: int = 100, ansi: bool = False) -> str:
    """Print Rich renderables to a string with terminal detection turned OFF.

    `force_terminal` is passed explicitly in both directions, and that is the
    whole point. Left unset, Rich *sniffs the environment* — FORCE_COLOR, TERM,
    CI — so the same renderable comes back as plain text on one machine and as
    ANSI spans on another, which splits `-134.60 PEN` into separate spans and
    breaks a plain substring assertion that is not wrong about anything. An
    assertion that depends on the environment it runs in is the bug; this is
    the fix, so the suite needs no "never set FORCE_COLOR" instruction.

    `legacy_windows=False` is pinned for the same reason — box-drawing must not
    depend on the host OS.

    Pass `ansi=True` when the escape codes ARE the assertion (reverse-video
    cursor rows, colour-by-sign). That is the one case that wants a terminal,
    and saying so at the call site is what makes it readable as deliberate.
    """
    console = Console(file=io.StringIO(), width=width, force_terminal=ansi, legacy_windows=False)
    for renderable in renderables:
        console.print(renderable)
    return console.file.getvalue()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Engine envelopes
# ---------------------------------------------------------------------------
#
# The two wrappers every endpoint speaks. Written out by hand at every site, a
# change of shape would have to be chased through a dozen files. One definition
# each means a change is a single edit — and means a fixture cannot quietly
# disagree with its neighbours about what the engine sends.


def error_body(code: str, message: str = "boom", fields: object = None) -> dict:
    """The engine's standard error envelope — see CLAUDE.md "Engine errors
    surface cleanly" and docs/cli-runtime.md.

    `fields` defaults to None (the shape a non-validation refusal has); pass a
    dict for a 422, whose keys the engine names per row.
    """
    return {"error": {"code": code, "message": message, "fields": fields}}


def error_response(
    status: int, code: str, message: str = "boom", fields: object = None
) -> httpx.Response:
    """`error_body` as a respx-ready response."""
    return httpx.Response(status, json=error_body(code, message, fields))


def whole(items: list) -> dict:
    """The whole-list envelope: accounts, categories, hashtags.
    No `total`, `limit` or `offset` — the engine returns every row and refuses
    both paging parameters."""
    return {"items": items}


def cursor_page(items: list, *, next_cursor: str | None = None, limit: int = 50) -> dict:
    """The `GET /transactions` envelope — cursor-paged, so no `total` and no
    `offset`. `next_cursor=None` (the default) is the last page."""
    return {"items": items, "limit": limit, "next_cursor": next_cursor}


def fake_ledger(monkeypatch, rows: list, *, count_fails: bool = False) -> tuple[list, list]:
    """`fetch_transactions` + `count_transactions` over `rows`, the engine's way:
    it refuses `offset`, serves slices of the requested `limit`, and hands back
    `c<next index>` as the cursor. `rows` is read on every call, so a test can
    shrink it to play a write the engine applied. Returns the (reads, counts)
    call logs."""
    calls: list = []
    counts: list = []

    def fetch(_cfg=None, *, limit=None, after=None, **kw):
        assert "offset" not in kw, "the engine refuses offset"
        calls.append({"limit": limit, "after": after, **kw})
        start = int(after[1:]) if after else 0
        end = start + (limit or 50)
        nxt = f"c{end}" if end < len(rows) else None
        return cursor_page(rows[start:end], next_cursor=nxt, limit=limit or 50)

    def count(_cfg=None, **kw):
        counts.append(kw)
        if count_fails:
            raise RuntimeError("count unavailable")
        return len(rows)

    monkeypatch.setattr("expense.commands.transactions_cmd.fetch_transactions", fetch)
    monkeypatch.setattr("expense.commands.transactions_cmd.count_transactions", count)
    return calls, counts


def window_page(
    items: list,
    *,
    date_from: str,
    date_to: str,
    next_cursor: str | None = None,
    limit: int = 50,
) -> dict:
    """The `GET /activity` and `/exchange-rates/history` envelope — cursor-paged
    inside a date window the engine echoes back (engine-spec, Date windows)."""
    return {
        **cursor_page(items, next_cursor=next_cursor, limit=limit),
        "date_from": date_from,
        "date_to": date_to,
    }


# ---------------------------------------------------------------------------
# TUI fakes and waits
# ---------------------------------------------------------------------------


class FakeClient:
    """Instance-level recorder standing in for expense.http.ExpenseClient.

    Only intercepts LAZY imports (`from expense.http import ExpenseClient`
    inside a function) — all TUI write/read sites qualify. CLI command modules
    bind ExpenseClient at module top; keep respx for those.

    Every request is recorded as (METHOD, path, body) in `calls`; the
    `requests`/`posts`/`puts`/`deletes` properties are filtered views. GETs
    answer from `get_responses` (miss → EngineError 404, matching the engine's
    not-provisioned behavior). Set `errors["POST"] = exc` to make a verb raise.

    Writes answer `{}` unless `write_responses[path]` says otherwise — needed
    because `run_write`'s `on_response` reads the engine's own body (`complete`
    carries a `warnings` envelope).
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []
        self.get_responses: dict[str, Any] = {}
        self.write_responses: dict[str, Any] = {}
        self.errors: dict[str, Exception] = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def _record(self, method: str, path: str, body: Any = None) -> None:
        self.calls.append((method, path, body))
        err = self.errors.get(method)
        if err is not None:
            raise err

    def get(self, path: str, *, auth: bool = True, params: dict | None = None) -> dict:
        self._record("GET", path, params)
        if path in self.get_responses:
            return self.get_responses[path]
        raise EngineError("NOT_FOUND", f"no fake response for GET {path}", None, 404, {})

    def post(self, path: str, json_body: dict | None = None) -> dict:
        self._record("POST", path, json_body)
        return self.write_responses.get(path, {})

    def put(self, path: str, json_body: dict | None = None) -> dict:
        self._record("PUT", path, json_body)
        return self.write_responses.get(path, {})

    def delete(self, path: str) -> dict:
        self._record("DELETE", path)
        return {}

    @property
    def requests(self) -> list[tuple[str, str]]:
        return [(method, path) for method, path, _ in self.calls]

    @property
    def posts(self) -> list[tuple[str, Any]]:
        return [(path, body) for method, path, body in self.calls if method == "POST"]

    @property
    def puts(self) -> list[tuple[str, Any]]:
        return [(path, body) for method, path, body in self.calls if method == "PUT"]

    @property
    def deletes(self) -> list[str]:
        return [path for method, path, _ in self.calls if method == "DELETE"]


def run_app(body: Callable, *, size: tuple[int, int] | None = None):
    """Run `body(pilot, app)` inside a live ExpenseApp and return its result.

    Every TUI test needs the same four lines — an app, `run_test`, a pilot, and
    an `asyncio.run` to drive it. A copy per test is not only repetition: it is
    an independent chance to boot the app slightly differently, and a
    suite-wide change (a default size, a fixture, an exception-handling
    wrapper) would have to be made in every one or not at all.

    `size` is passed through to `run_test` only when given, so the default stays
    Textual's rather than a number this helper invented. A screen that depends
    on a viewport says so at its own call site.

    The ExpenseApp import is function-local: this module stays free of Textual
    at import time so the CLI command tests do not pay for it (see the module
    docstring).
    """
    from expense.tui.app import ExpenseApp

    async def scenario():
        app = ExpenseApp()
        async with app.run_test(**(dict(size=size) if size else {})) as pilot:
            return await body(pilot, app)

    return asyncio.run(scenario())


async def wait_for(
    pilot,
    predicate: Callable[[], object],
    *,
    timeout: float = 2.0,
    interval: float = 0.02,
    message: str | None = None,
) -> None:
    """Pause the pilot until predicate() is truthy.

    Fails the test on timeout — a timed-out wait should point at the wait
    site, not surface as a confusing assert a few lines later.
    """
    for _ in range(max(1, round(timeout / interval))):
        await pilot.pause(interval)
        if predicate():
            return
    pytest.fail(message or f"wait_for: condition still false after {timeout}s")


async def wait_for_loaded(pilot, app) -> None:
    """Until the active SectionScreen resolved — #card (data) or .error mounted."""
    await wait_for(
        pilot,
        lambda: bool(app.screen.query("#card")) or bool(app.screen.query(".error")),
        message="SectionScreen never finished loading (no #card or .error mounted)",
    )


def list_ready(app) -> bool:
    """The active SectionScreen's CursorList is mounted and its loader is gone.

    Exposed as a plain predicate, not only as the waiter below, so call sites
    that need an *extra* condition (a row count, a filtered legend) can write
    `list_ready(app) and ...` instead of re-open-coding the pair.
    """
    from expense.tui.widgets.cursor_list import CursorList  # local: see module docstring

    return bool(app.screen.query(CursorList)) and not app.screen.query("#content LoadingIndicator")


async def wait_for_list(pilot, app) -> None:
    """Until the active SectionScreen's list is mounted and done loading."""
    await wait_for(
        pilot,
        lambda: list_ready(app),
        message="list never finished loading (no CursorList, or LoadingIndicator still up)",
    )


# ---- Home's month ---------------------------------------------------------------
#: Two months as `/reports/monthly` returns them. @Pendiente holds only untagged
#: rows, WANTS two hashtags, and HOGAR nothing in either month — so Home must not
#: draw it. Ids carry a hyphen so scripts/check_fixture_drift.py does not read the
#: hashtag-name map's keys as engine fields.
HOME_MONTHS = [
    {
        "month": {"year": 2026, "month": 8},
        "categories": [
            {
                "id": "c-pend",
                "name": "@Pendiente",
                "spent_home_cents": -26620,
                "unconverted_count": 0,
                "hashtag_breakdown": [
                    {"hashtag_ids": [], "spent_home_cents": -26620, "unconverted_count": 0}
                ],
            },
            {
                "id": "c-wants",
                "name": "WANTS",
                "spent_home_cents": -160843,
                "unconverted_count": 0,
                "hashtag_breakdown": [
                    {"hashtag_ids": ["h-sal"], "spent_home_cents": -64850, "unconverted_count": 0},
                    {"hashtag_ids": ["h-otr"], "spent_home_cents": -95993, "unconverted_count": 0},
                ],
            },
            {
                "id": "c-hogar",
                "name": "HOGAR",
                "spent_home_cents": 0,
                "unconverted_count": 0,
                "hashtag_breakdown": [],
            },
        ],
        "totals": {
            "inflow_home_cents": 0,
            "outflow_home_cents": 187463,
            "net_home_cents": -187463,
            "unconverted_count": 0,
        },
    },
    {
        "month": {"year": 2026, "month": 9},
        "categories": [
            {
                "id": "c-pend",
                "name": "@Pendiente",
                "spent_home_cents": -1148746,
                "unconverted_count": 0,
                "hashtag_breakdown": [
                    {"hashtag_ids": [], "spent_home_cents": -1148746, "unconverted_count": 0}
                ],
            },
            {
                "id": "c-wants",
                "name": "WANTS",
                "spent_home_cents": 0,
                "unconverted_count": 0,
                "hashtag_breakdown": [],
            },
            {
                "id": "c-hogar",
                "name": "HOGAR",
                "spent_home_cents": 0,
                "unconverted_count": 0,
                "hashtag_breakdown": [],
            },
        ],
        "totals": {
            "inflow_home_cents": 82288,
            "outflow_home_cents": 1231034,
            "net_home_cents": -1148746,
            "unconverted_count": 0,
        },
    },
]
HOME_DASHBOARD = {
    "month": {"year": 2026, "month": 9},
    "bank_accounts": [
        {"id": "a-pen", "name": "BCP PEN", "currency_code": "PEN", "current_balance_cents": 514582},
        {"id": "a-usd", "name": "BCP USD", "currency_code": "USD", "current_balance_cents": 130},
    ],
    "people": [],
    "categories": [],
    "totals": {"net_home_cents": -1148746, "unconverted_count": 0},
}
HOME_TAG_NAMES = dict([("h-sal", "SALIDAS"), ("h-otr", "OTROS")])


def stub_home_month(monkeypatch, *, months=None, dashboard=None, names=None, calls=None):
    """Answer Home's worker from the fixtures above. `calls`, when given, records
    each range read's `(from_ym, to_ym)`."""

    def fake_range(cfg, *, from_ym, to_ym, **kw):
        if calls is not None:
            calls.append((from_ym, to_ym))
        return dict(months=HOME_MONTHS if months is None else months)

    monkeypatch.setattr(
        "expense.commands.dashboard_cmd.fetch_dashboard",
        lambda *a, **k: HOME_DASHBOARD if dashboard is None else dashboard,
    )
    monkeypatch.setattr("expense.commands.reports_cmd.fetch_range", fake_range)
    monkeypatch.setattr(
        "expense.tui.screens.home.load_hashtag_name_map",
        lambda: HOME_TAG_NAMES if names is None else names,
    )
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())


# ---------------------------------------------------------------------------
# scripts/check_fixture_drift.py, loaded as a module
# ---------------------------------------------------------------------------

DRIFT_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "check_fixture_drift.py"


def load_drift_script():
    """Load scripts/check_fixture_drift.py without importing `scripts` as a package.

    The script is deliberately not a pytest file — it reads the engine's
    openapi.json, and tests/unit is hermetic. Loading it costs no network; a
    test that runs its `main` mocks the engine with respx.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("_check_fixture_drift", DRIFT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
