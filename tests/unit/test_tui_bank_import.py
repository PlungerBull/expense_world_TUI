"""The import door — a bank file dropped on the LOG bar → account → preview → result.

Pure builders first, then pilot tests through the LOG bar the way a drop
arrives. The sheet reaches flow.py's reader through its `read_workbook` seam;
the one engine call,
`POST /transactions/import`, is answered by a fake on the shared FakeClient
that echoes each row's id and decides its outcome.
"""

import threading

import pytest
from textual.widgets import Input, Static

from expense.bank_import import flow
from expense.bank_import.engine import ExcessGroup
from expense.bank_import.flow import account_groups
from expense.errors import EngineError
from expense.import_.reader import RawRow, SheetData
from expense.tui.screens.bank_import import (
    ImportAccountScreen,
    ImportPreviewScreen,
    ImportResultScreen,
    account_lines,
    result_lines,
)
from expense.tui.screens.home import HomeScreen
from expense.tui.screens.log_bar import LogBarScreen
from tests.unit.helpers import (
    ENGINE_ORDER_ACCOUNTS,
    ENGINE_ORDER_BANK_NAMES,
    render_text,
    run_app,
    stub_home_month,
    wait_for,
    whole,
)

ACCOUNTS = [
    {
        "id": "sig-pen",
        "name": "BCP Signature PEN",
        "currency_code": "PEN",
        "is_person": False,
        "opening_balance_transaction_id": None,
    },
    {
        "id": "sig-usd",
        "name": "BCP Signature USD",
        "currency_code": "USD",
        "is_person": False,
        "opening_balance_transaction_id": None,
    },
    {
        "id": "bcp-pen",
        "name": "BCP PEN",
        "currency_code": "PEN",
        "is_person": False,
        "opening_balance_transaction_id": None,
    },
    {
        "id": "old",
        "name": "Retired PEN",
        "currency_code": "PEN",
        "is_person": False,
        "is_archived": True,
        "opening_balance_transaction_id": None,
    },
]
HEADERS = ["Fecha", "Descripcion", "Moneda", "Monto"]
CARD_ROWS = [
    ("2026-09-11", "EDO SUSHI BAR             LI", "S/", -49),
    ("2026-09-09", "APPLE.COM/BILL", "$", -21.17),
    ("2026-09-08", "UBER TRIP", "S/", -4.2),
    ("2026-09-07", "APPARKA MALL AVENTURA  AREQU", "S/", -3.5),
]
LEDGER_LINE = "tottus porongoche -38.60 $BCP Signature PEN"
EXCESS_0907 = {
    "account_id": "sig-pen",
    "date": "2026-09-07",
    "amount_cents": 350,
    "transaction_type": 1,
    "unclaimed_ledger_ids": ["l-1"],
}


# ---- the seams ---------------------------------------------------------------
def _sheet(headers, rows) -> SheetData:
    return SheetData(headers=headers, rows=[RawRow(i + 2, list(r)) for i, r in enumerate(rows)])


def _feed(monkeypatch, sheets: dict) -> None:
    """Each dropped file's name → (headers, rows), read through the typed
    command's own reader seam."""
    from pathlib import Path

    def read(path, **_kw):
        headers, rows = sheets[Path(path).name]
        return _sheet(headers, rows)

    monkeypatch.setattr(flow, "read_workbook", read)


def _patch(monkeypatch) -> None:
    """The LOG bar's reference reads, its peek, and the account list."""
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(ACCOUNTS))
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.reads.fetch_transactions", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.reads.count_transactions", lambda *a, **k: 0)


def _engine(fake_client, decide=None, *, excess=None):
    """Answer `POST /transactions/import` like the engine: every sent id back,
    with the outcome `decide(index, row)` gives (default new). Every call is
    still recorded on the fake client."""
    record = fake_client.post

    def post(path, json_body=None):
        record(path, json_body)
        rows = []
        for i, row in enumerate(json_body["rows"]):
            result = {
                "id": row["id"],
                "outcome": "new",
                "rule": None,
                "ledger_id": None,
                "backfill_code": None,
                "sealed_by": None,
            }
            result.update((decide or (lambda i, r: {}))(i, row))
            rows.append(result)
        return {"dry_run": json_body["dry_run"], "rows": rows, "excess": excess or []}

    fake_client.post = post


def _imports(fake_client) -> list[bool]:
    """The `dry_run` of every import call, in order."""
    return [body["dry_run"] for path, body in fake_client.posts if path == "/transactions/import"]


def _matched(rule):
    return {"outcome": "matched", "rule": rule, "ledger_id": "l-x"}


def _two_new_two_in_ledger(i, _row):
    return {1: _matched("same_day"), 2: _matched("adjacent_day")}.get(i, {})


def _bank_file(tmp_path, name: str = "Sueldo Soles (1).xlsx"):
    path = tmp_path / name
    path.write_bytes(b"")
    return path


def _escaped(path) -> str:
    """What Terminal.app types for a drop."""
    return "".join("\\" + c if c in " ()" else c for c in str(path))


def _shown(screen) -> dict[str, str]:
    return {
        key: active.binding.description
        for key, active in screen.active_bindings.items()
        if active.binding.show
    }


def _body(screen) -> str:
    return render_text(screen.query_one("#import-body", Static).content, width=120)


def _crumb(screen) -> str:
    return render_text(screen.query_one("#crumb", Static).render(), width=120)


async def _open(app, pilot) -> LogBarScreen:
    screen = LogBarScreen()
    await app.push_screen(screen)
    await wait_for(pilot, lambda: screen._refs is not None, message="refs never loaded")
    return screen


def _type(screen, text) -> None:
    bar = screen.query_one("#bar", Input)
    bar.value = text
    bar.cursor_position = len(text)
    screen.on_input_changed(Input.Changed(bar, text))


async def _drop(pilot, screen, *paths) -> None:
    _type(screen, " ".join(_escaped(p) for p in paths))
    await pilot.pause()  # the bar's own Changed lands before the key, as when typed
    await pilot.press("enter")


async def _on(pilot, app, kind, message: str):
    await wait_for(pilot, lambda: isinstance(app.screen, kind), message=message)
    return app.screen


async def _preview(pilot, app):
    """From the account list: pick the cursor row, wait for the dry run."""
    account = await _on(pilot, app, ImportAccountScreen, "no account list")
    await wait_for(pilot, lambda: account._run.groups is not None, message="accounts not read")
    return account


async def _previewed(pilot, app) -> ImportPreviewScreen:
    preview = await _on(pilot, app, ImportPreviewScreen, "no preview")
    await wait_for(pilot, lambda: preview._placed is not None, message="dry run never answered")
    return preview


# ---- pure ----------------------------------------------------------------------
def test_a_cards_two_legs_fold_into_one_line():
    groups = account_groups(ACCOUNTS)
    lines = [line.plain.rstrip() for line in account_lines(groups, 0)]
    assert [line.split()[0:2] for line in lines] == [["BCP", "Signature"], ["BCP", "PEN"]]
    assert lines[0].endswith("PEN + USD")
    assert "Retired" not in " ".join(lines)  # archived: the typed import's list too
    assert lines[1].endswith("PEN")


def test_result_lines_say_one_day_and_several_days():
    group = account_groups(ACCOUNTS)[1]
    one = [ExcessGroup("BCP PEN", "2026-09-10", -2800, 1)]
    text = "\n".join(t.plain for t in result_lines(group, [], one))
    assert (
        "! 1 day where the ledger may now hold the same movement twice — check it and "
        "delete the extra one" in text
    )
    assert "    2026-09-10 · -28.00" in text
    two = [*one, ExcessGroup("BCP PEN", "2026-09-12", -1000, 2)]
    text = "\n".join(t.plain for t in result_lines(group, [], two))
    assert (
        "! 2 days where the ledger may now hold the same movement twice — check them and "
        "delete the extra ones" in text
    )


# ---- screen 5 A: not a bank file -----------------------------------------------
def test_a_file_that_is_not_a_bank_export_stays_in_the_bar(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path, "presupuesto.xlsx")
    _patch(monkeypatch)
    _feed(monkeypatch, {"presupuesto.xlsx": (["Fecha", "Descripcion", "Moneda", "Total"], [])})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await pilot.pause()
        assert app.screen is screen
        hint = screen.query_one("#hint", Static).content
        assert hint.plain.split("\n") == [
            "not a BCP bank file · missing the column Monto",
            "it has: Fecha, Descripcion, Moneda, Total",
        ]
        assert _shown(screen) == {"escape": "Cancel"}
        await pilot.press("enter")  # ⏎ does nothing more
        await pilot.pause()
        assert app.screen is screen
        assert fake_client.calls == []  # nothing sent, not even the account list
        # the next keystroke is a new attempt
        _type(screen, "")
        assert screen._file_problem is None

    run_app(scenario)


def test_a_bad_second_file_stops_the_drop_before_the_first_starts(
    fake_client, monkeypatch, tmp_path
):
    good, bad = _bank_file(tmp_path), _bank_file(tmp_path, "presupuesto.xlsx")
    _patch(monkeypatch)
    _feed(
        monkeypatch,
        {
            good.name: (HEADERS, CARD_ROWS),
            bad.name: (["Mes", "Categoria", "Total"], []),
        },
    )
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, good, bad)
        await pilot.pause()
        assert app.screen is screen
        hint = screen.query_one("#hint", Static).content.plain.split("\n")
        assert hint == [
            "presupuesto.xlsx · not a BCP bank file · missing the columns "
            "Fecha, Descripcion, Moneda, Monto",
            "it has: Mes, Categoria, Total",
        ]
        assert fake_client.calls == []

    run_app(scenario)


# ---- screen 2: the account list -------------------------------------------------
def test_the_account_list_folds_a_card_and_names_the_file(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        account = await _preview(pilot, app)
        assert "Capture & ledger  ▸  Import  ▸  Sueldo Soles (1).xlsx" in _crumb(account)
        body = _body(account).split("\n")
        assert body[0].strip() == (
            "Which account is this file?   4 movements · 2026-09-07 → 2026-09-11 · PEN + USD"
        )
        listed = [line.strip() for line in body[2:] if line.strip()]
        assert [line.split("  ")[0] for line in listed] == ["BCP Signature", "BCP PEN"]
        assert listed[0].endswith("PEN + USD")
        assert _shown(account) == {"escape": "Cancel", "enter": "Pick"}
        assert _imports(fake_client) == []  # nothing asked of the import yet
        await pilot.press("down")
        assert account._cursor == 1
        await pilot.press("up")
        assert account._cursor == 0

    run_app(scenario, size=(120, 40))


def test_the_account_list_shows_the_engines_order(fake_client, monkeypatch, tmp_path):
    """The "Which account is this file?" list shows the accounts exactly as
    `GET /accounts` returned them — not alphabetical, not by `sort_order`; the
    person is left out and nothing else moves."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    monkeypatch.setattr(
        "expense.reads.fetch_accounts", lambda *a, **k: whole(ENGINE_ORDER_ACCOUNTS)
    )
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        account = await _preview(pilot, app)
        assert [group.base for group in account._groups] == ENGINE_ORDER_BANK_NAMES
        listed = [line.strip() for line in _body(account).split("\n")[2:] if line.strip()]
        assert [line.split("  ")[0] for line in listed] == ENGINE_ORDER_BANK_NAMES

    run_app(scenario, size=(120, 40))


def test_the_card_sends_each_row_to_the_leg_of_its_currency(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        await _previewed(pilot, app)
        (_, body), *_ = fake_client.posts
        assert body["dry_run"] is True
        legs = [(r["account_id"], r["amount_cents"]) for r in body["rows"]]
        assert legs == [
            ("sig-pen", -4900),
            ("sig-usd", -2117),
            ("sig-pen", -420),
            ("sig-pen", -350),
        ]

    run_app(scenario, size=(120, 40))


def test_a_currency_the_picked_account_has_no_leg_for_is_refused_on_the_list(
    fake_client, monkeypatch, tmp_path
):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        account = await _preview(pilot, app)
        await pilot.press("down", "enter")  # BCP PEN: no USD leg
        await pilot.pause()
        assert app.screen is account
        assert account._refused[-1].plain == (
            "BCP holds PEN only, and this file has 1 row in USD. Pick the card that has "
            "both, or an account in that currency."
        )
        assert account._refused[-1].plain in " ".join(_body(account).split())
        assert fake_client.posts == []  # not even a dry run

    run_app(scenario, size=(160, 40))


def test_a_file_with_nothing_on_or_after_the_floor_is_refused_with_its_lines(
    fake_client, monkeypatch, tmp_path
):
    path = _bank_file(tmp_path)
    rows = [
        ("2025-12-30", "UBER TRIP", "S/", -4.2),
        ("2026-09-08", "MYSTERY", "S/", "abc"),
    ]
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, rows)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        account = await _preview(pilot, app)
        await pilot.press("down", "enter")  # BCP PEN
        await pilot.pause()
        assert app.screen is account
        assert [line.plain for line in account._refused] == [
            '! row 3: "abc" is not an amount',
            "nothing to import — no row of this file is dated 2026-01-01 or later.",
        ]
        body = _body(account)
        assert '! row 3: "abc" is not an amount' in body
        assert "nothing to import — no row of this file is dated 2026-01-01 or later." in body
        assert fake_client.posts == []

    run_app(scenario, size=(160, 40))


# ---- screen 3: the preview --------------------------------------------------------
def test_the_preview_shows_verdicts_and_writes_nothing_before_enter(
    fake_client, monkeypatch, tmp_path
):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client, _two_new_two_in_ledger, excess=[EXCESS_0907])

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        body = _body(preview)
        lines = [line.rstrip() for line in body.split("\n")]
        assert lines[0].strip() == "Preview · BCP Signature · nothing written yet"
        assert lines[2].split() == ["#", "date", "title", "amount", "match"]
        rows = [line.split() for line in lines[3:7]]
        assert [r[0] for r in rows] == ["2", "3", "4", "5"]  # the file's own lines
        assert lines[3].endswith("new")
        assert lines[4].endswith("in ledger · same day")
        assert lines[5].endswith("in ledger · ± 1 day")
        assert "4 rows · 2 new · 2 in the ledger" in body
        assert "! 1 ledger row no file row matched — check" in body
        assert "2026-09-07 · -3.50 · 1 unmatched" in body
        assert _shown(preview) == {"escape": "Cancel", "enter": "Import 2 rows"}
        assert _imports(fake_client) == [True]  # the dry run only

    run_app(scenario, size=(120, 40))


def test_the_preview_pages_with_pgdn(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    rows = [(f"2026-09-{d:02d}", f"SHOP {d}", "S/", -d) for d in range(1, 29)]
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, rows)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        size = preview._page_size()
        assert size < 28
        assert f"… {28 - size} more · pgdn" in _body(preview)
        await pilot.press("pagedown")
        assert preview._start == size
        await pilot.press("pageup")
        assert preview._start == 0

    run_app(scenario, size=(120, 30))


def test_an_engine_refusal_on_the_preview_is_shown_and_nothing_follows(
    fake_client, monkeypatch, tmp_path
):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    fake_client.errors["POST"] = EngineError(
        "VALIDATION_ERROR", "Invalid rows", {"rows.1.amount_cents": "must not be 0"}, 422, {}
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _on(pilot, app, ImportPreviewScreen, "no preview")
        await wait_for(pilot, lambda: bool(preview._failure), message="no failure shown")
        body = _body(preview)
        assert "VALIDATION_ERROR — Invalid rows" in body
        assert "! row 3 (amount_cents): must not be 0" in body  # the file's line
        assert "Nothing was written." in body
        assert _shown(preview) == {"escape": "Cancel"}
        await pilot.press("enter")
        await pilot.pause()
        assert len(fake_client.posts) == 1  # the refused dry run, nothing after

    run_app(scenario, size=(120, 40))


# ---- screen 6 A: nothing new -----------------------------------------------------
def test_nothing_new_shows_the_preview_and_enter_writes_nothing(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client, lambda i, r: _matched("operation_code"))

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        lines = [line.strip() for line in _body(preview).split("\n") if line.strip()]
        assert lines[-2:] == ["4 rows · 0 new · 4 in the ledger", "nothing to import"]
        assert _shown(preview) == {"escape": "Back"}
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen is preview
        assert _imports(fake_client) == [True]
        await pilot.press("escape")
        await _on(pilot, app, LogBarScreen, "esc Back did not return to the bar")
        assert _imports(fake_client) == [True]

    run_app(scenario, size=(120, 40))


# ---- apply and screen 4 B ----------------------------------------------------------
def test_apply_writes_once_and_the_result_says_what_to_check(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client, _two_new_two_in_ledger, excess=[EXCESS_0907])

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        await _previewed(pilot, app)
        await pilot.press("enter")
        result = await _on(pilot, app, ImportResultScreen, "no result screen")
        assert _imports(fake_client) == [True, False]
        lines = [line.strip() for line in _body(result).split("\n")]
        assert lines[0] == "✓ 2 rows imported · BCP Signature"
        assert lines[1] == "under @Pendiente"
        warning = " ".join(lines[3:])
        assert (
            "! 1 day where the ledger may now hold the same movement twice — check it and "
            "delete the extra one" in warning
        )
        assert "2026-09-07 · -3.50" in warning
        assert _shown(result) == {"escape": "Back", "enter": "Home"}
        # the two calls are one logical write each: the same rows, the same ids
        (_, dry), (_, applied) = fake_client.posts
        assert [r["id"] for r in dry["rows"]] == [r["id"] for r in applied["rows"]]

    run_app(scenario, size=(120, 40))


def test_a_repeated_enter_on_the_preview_sends_one_apply(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)
    answer = fake_client.post
    release = threading.Event()

    def held(path, json_body=None):
        if not json_body["dry_run"]:
            release.wait(timeout=5)  # the apply is still on its way
        return answer(path, json_body)

    fake_client.post = held

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        await pilot.press("enter", "enter", "enter")
        await pilot.pause()
        assert app.screen is preview and preview._writing
        assert "enter" not in _shown(preview)
        release.set()
        await _on(pilot, app, ImportResultScreen, "no result screen")
        assert _imports(fake_client) == [True, False]

    try:
        run_app(scenario, size=(120, 40))
    finally:
        release.set()


def test_an_engine_error_on_apply_is_shown_and_nothing_more_is_sent(
    fake_client, monkeypatch, tmp_path
):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        fake_client.errors["POST"] = EngineError(
            "PERIOD_LOCKED", "The period is completed.", None, 409, {}
        )
        await pilot.press("enter")
        # the toast is a message to the app: it lands a moment after the screen shows the failure
        await wait_for(
            pilot,
            lambda: bool(preview._failure) and bool(app._notifications),
            message="no failure shown, or no toast",
        )
        assert "PERIOD_LOCKED" in _body(preview)
        assert any("PERIOD_LOCKED" in str(n.message) for n in app._notifications)
        assert _shown(preview) == {"escape": "Cancel"}
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen is preview
        assert len(fake_client.posts) == 2  # the dry run and the refused apply

    run_app(scenario, size=(120, 40))


@pytest.mark.parametrize(
    ("key", "reason", "line"),
    [
        (
            "rows.0.operation_code",
            "OPERATION_CODE_EXISTS",
            "That account already has a row with this operation number: "
            "look there for a duplicate.",
        ),
        ("category_id", "CONCURRENT_CHANGE", "It changed at the same moment: save again."),
        (
            "category_id",
            "RESERVED_NAME_HELD",
            "One of your categories has a built-in category's name: "
            "rename it on Manage ▸ Categories, then save again.",
        ),
        (
            "rows.0.id",
            "ID_EXISTS",
            "Not your mistake: the app sent it wrong and nothing was saved. "
            "Try again; if it happens again, report it.",
        ),
    ],
    ids=["screen-4", "screen-5A", "screen-6B", "screen-9A"],
)
def test_a_refused_import_shows_the_engine_words_and_what_to_do(
    fake_client, monkeypatch, tmp_path, key, reason, line
):
    """`POST /transactions/import` refuses keyed by the row (`rows.<i>.…`) or by
    the system category (contract: "Error reasons"): the note and the screen show
    the engine's words, then the line, where `⏎` is how this screen saves again."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)
    expected = f"CONFLICT — stand-in\n  {key}: stand-in field words\n\n{line}"

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        fake_client.errors["POST"] = EngineError(
            "CONFLICT", "stand-in", {key: "stand-in field words"}, 409, {}, {key: reason}
        )
        await pilot.press("enter")
        # the toast is a message to the app: it lands a moment after the screen shows the failure
        await wait_for(
            pilot,
            lambda: bool(preview._failure) and bool(app._notifications),
            message="no failure shown, or no toast",
        )
        assert [str(t) for t in preview._failure] == [expected]
        assert [str(n.message) for n in app._notifications][-1] == expected

    run_app(scenario, size=(120, 40))


def test_esc_back_returns_to_a_cleared_bar_with_the_staged_rows(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        screen.on_input_submitted()
        assert [e.line for e in screen._staged] == [LEDGER_LINE]
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        await _previewed(pilot, app)
        await pilot.press("enter")
        await _on(pilot, app, ImportResultScreen, "no result screen")
        await pilot.press("escape")
        await _on(pilot, app, LogBarScreen, "esc Back did not return to the bar")
        assert app.screen is screen
        assert screen.query_one("#bar", Input).value == ""
        assert screen._files is None
        assert [e.line for e in screen._staged] == [LEDGER_LINE]
        assert not screen._staged[0].saved

    run_app(scenario, size=(120, 40))


def test_enter_home_goes_home_and_home_reads_fresh(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    stub_home_month(monkeypatch)
    _engine(fake_client)

    async def scenario(pilot, app):
        home = app.screen
        assert isinstance(home, HomeScreen)
        await wait_for(pilot, lambda: home._data is not None, message="home never loaded")
        home.action_older()  # a window and a cursor somewhere else
        await wait_for(pilot, lambda: home._data["end"] == home._end, message="window")
        home.query_one("#menu").highlighted = 3
        await pilot.press("plus")
        screen = await _on(pilot, app, LogBarScreen, "+ did not open the bar")
        await wait_for(pilot, lambda: screen._refs is not None, message="refs never loaded")
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        await _previewed(pilot, app)
        await pilot.press("enter")
        await _on(pilot, app, ImportResultScreen, "no result screen")
        await pilot.press("enter")
        await _on(pilot, app, HomeScreen, "⏎ Home did not go home")
        assert app.screen is home
        assert home._end == home._today
        await wait_for(
            pilot, lambda: home._data and home._data["end"] == home._today, message="no re-read"
        )
        menu = home.query_one("#menu")
        enabled = [i for i in range(menu.option_count) if not menu.get_option_at_index(i).disabled]
        assert menu.highlighted == enabled[0]

    run_app(scenario, size=(120, 40))


def test_enter_home_with_unwritten_staged_rows_asks_first(fake_client, monkeypatch, tmp_path):
    from expense.tui.screens.modals import DiscardStagedModal

    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        screen.on_input_submitted()
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        await _previewed(pilot, app)
        await pilot.press("enter")
        await _on(pilot, app, ImportResultScreen, "no result screen")
        await pilot.press("enter")
        await _on(pilot, app, DiscardStagedModal, "no discard question")
        await pilot.press("escape")  # keep the rows
        await _on(pilot, app, LogBarScreen, "the bar did not come back")
        assert [e.line for e in screen._staged] == [LEDGER_LINE]

    run_app(scenario, size=(120, 40))


# ---- screen 7 B: several files -----------------------------------------------------
def test_two_files_go_one_after_the_other_then_home(fake_client, monkeypatch, tmp_path):
    first = _bank_file(tmp_path)
    second = _bank_file(tmp_path, "Cuenta Corriente.xlsx")
    _patch(monkeypatch)
    _feed(
        monkeypatch,
        {
            first.name: (HEADERS, CARD_ROWS),
            second.name: (HEADERS, [("2026-09-12", "PAGO PLANILLA", "S/", 6519)]),
        },
    )
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, first, second)
        account = await _preview(pilot, app)
        assert "Import  ▸  file 1 of 2" in _crumb(account)
        body = [line.strip() for line in _body(account).split("\n")]
        assert body[:2] == ["Which account is this file?", "Sueldo Soles (1).xlsx · 4 movements"]
        assert _shown(account) == {"escape": "Cancel both", "enter": "Pick"}
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        assert _shown(preview) == {"escape": "Cancel both", "enter": "Import 4 rows"}
        await pilot.press("enter")
        result = await _on(pilot, app, ImportResultScreen, "no first result")
        assert _shown(result) == {"escape": "Back", "enter": "Next file"}

        await pilot.press("enter")
        account = await _preview(pilot, app)
        assert "Import  ▸  file 2 of 2" in _crumb(account)
        assert "Cuenta Corriente.xlsx · 1 movement" in _body(account)
        await pilot.press("down", "enter")  # BCP PEN
        await _previewed(pilot, app)
        await pilot.press("enter")
        result = await _on(pilot, app, ImportResultScreen, "no second result")
        assert result is not None and "· BCP PEN" in _body(result)
        assert _shown(result) == {"escape": "Back", "enter": "Home"}
        assert _imports(fake_client) == [True, False, True, False]
        await pilot.press("enter")
        await _on(pilot, app, HomeScreen, "⏎ Home did not go home")

    run_app(scenario, size=(120, 40))


def test_esc_on_the_first_file_cancels_both(fake_client, monkeypatch, tmp_path):
    first = _bank_file(tmp_path)
    second = _bank_file(tmp_path, "Cuenta Corriente.xlsx")
    third = _bank_file(tmp_path, "Otra.xlsx")
    _patch(monkeypatch)
    _feed(monkeypatch, {p.name: (HEADERS, CARD_ROWS) for p in (first, second, third)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, first, second)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        await pilot.press("escape")
        await _on(pilot, app, LogBarScreen, "esc did not return to the bar")
        await pilot.pause()
        assert app.screen is screen and preview is not app.screen
        assert _imports(fake_client) == [True]  # the first file's dry run; nothing written
        assert screen.query_one("#bar", Input).value == ""

        # three files: the word is `all`
        await _drop(pilot, screen, first, second, third)
        account = await _preview(pilot, app)
        assert _shown(account) == {"escape": "Cancel all", "enter": "Pick"}

    run_app(scenario, size=(120, 40))


def test_nothing_new_with_a_file_to_come_moves_on_without_writing(
    fake_client, monkeypatch, tmp_path
):
    first = _bank_file(tmp_path)
    second = _bank_file(tmp_path, "Cuenta Corriente.xlsx")
    _patch(monkeypatch)
    _feed(
        monkeypatch,
        {
            first.name: (HEADERS, CARD_ROWS),
            second.name: (HEADERS, [("2026-09-12", "PAGO PLANILLA", "S/", 6519)]),
        },
    )
    # the card's four rows are in the ledger already; the second file's one is new
    _engine(
        fake_client, lambda i, r: _matched("operation_code") if r["account_id"] != "bcp-pen" else {}
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, first, second)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        assert "nothing to import" in _body(preview)
        assert _shown(preview) == {"escape": "Cancel both", "enter": "Next file"}
        await pilot.press("enter")
        account = await _preview(pilot, app)
        assert account is not preview
        assert "Import  ▸  file 2 of 2" in _crumb(account)
        assert _imports(fake_client) == [True]  # the dry run only; nothing written
        assert _shown(account) == {"escape": "Cancel", "enter": "Pick"}
        await pilot.press("down", "enter")  # BCP PEN
        preview = await _previewed(pilot, app)
        assert _shown(preview) == {"escape": "Cancel", "enter": "Import 1 row"}

    run_app(scenario, size=(120, 40))


def test_nothing_new_on_the_last_of_several_files_goes_back_only(
    fake_client, monkeypatch, tmp_path
):
    first = _bank_file(tmp_path)
    second = _bank_file(tmp_path, "Cuenta Corriente.xlsx")
    _patch(monkeypatch)
    _feed(
        monkeypatch,
        {
            first.name: (HEADERS, CARD_ROWS),
            second.name: (HEADERS, [("2026-09-12", "PAGO PLANILLA", "S/", 6519)]),
        },
    )
    # the card's rows are new; the second file's one is in the ledger already
    _engine(
        fake_client, lambda i, r: _matched("operation_code") if r["account_id"] == "bcp-pen" else {}
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, first, second)
        await _preview(pilot, app)
        await pilot.press("enter")
        await _previewed(pilot, app)
        await pilot.press("enter")
        await _on(pilot, app, ImportResultScreen, "no first result")
        await pilot.press("enter")
        await _preview(pilot, app)
        await pilot.press("down", "enter")  # BCP PEN
        preview = await _previewed(pilot, app)
        lines = [line.strip() for line in _body(preview).split("\n") if line.strip()]
        assert lines[-1] == "nothing to import"
        assert _shown(preview) == {"escape": "Back"}
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen is preview
        assert _imports(fake_client) == [True, False, True]
        await pilot.press("escape")
        await _on(pilot, app, LogBarScreen, "esc Back did not return to the bar")
        assert _imports(fake_client) == [True, False, True]

    run_app(scenario, size=(120, 40))


def test_the_esc_word_counts_the_files_still_to_come(fake_client, monkeypatch, tmp_path):
    files = [_bank_file(tmp_path, f"{name}.xlsx") for name in ("Uno", "Dos", "Tres")]
    _patch(monkeypatch)
    _feed(monkeypatch, {p.name: (HEADERS, CARD_ROWS) for p in files})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, *files)
        account = await _preview(pilot, app)
        assert _shown(account) == {"escape": "Cancel all", "enter": "Pick"}  # 1 of 3
        await pilot.press("enter")
        await _previewed(pilot, app)
        await pilot.press("enter")
        await _on(pilot, app, ImportResultScreen, "no first result")
        await pilot.press("enter")
        account = await _preview(pilot, app)
        assert "Import  ▸  file 2 of 3" in _crumb(account)
        assert _shown(account) == {"escape": "Cancel both", "enter": "Pick"}
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        assert _shown(preview) == {"escape": "Cancel both", "enter": "Import 4 rows"}
        # esc on file 2 of 3 cancels it and file 3; file 1 stays imported
        await pilot.press("escape")
        await _on(pilot, app, LogBarScreen, "esc did not return to the bar")
        assert app.screen is screen
        assert preview._run.imported == 1
        assert _imports(fake_client) == [True, False, True]

    run_app(scenario, size=(120, 40))


# ---- edit + drop -----------------------------------------------------------------
def test_a_drop_onto_a_lifted_row_drops_the_edit_and_keeps_the_row(
    fake_client, monkeypatch, tmp_path
):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        screen.on_input_submitted()
        screen.action_move(1)
        screen.on_input_submitted()  # lift the picked row into the bar
        assert screen._editing == 0
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        assert screen._editing is None
        assert [e.line for e in screen._staged] == [LEDGER_LINE]
        await pilot.press("escape")
        await _on(pilot, app, LogBarScreen, "esc did not return to the bar")
        assert [e.line for e in screen._staged] == [LEDGER_LINE]
        assert str(screen.query_one("#field").content) == "LOG"
        assert fake_client.posts == []

    run_app(scenario, size=(120, 40))
