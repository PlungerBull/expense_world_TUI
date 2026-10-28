"""Every note shows the engine's words as sent, `[` and all, never as styling.

One test per place the app puts the engine's words on screen: each toast, the
lines under a screen, a status line. The engine refuses with a message and a
field's words that hold `[like this]` and a lone `[`, which content markup
would read as a style and drop; each test finds both whole in what the screen
draws. Toasts are read as drawn (`run_app(..., toasts=True)`, `toasts_shown`);
the rule they follow is guarded in test_toast_words.py.
"""

from dataclasses import replace

import pytest
import respx
from textual.content import Content
from textual.widgets import Input, Static

import expense.reads as reads_mod
import expense.tui.screens.transactions as tx_mod
from expense.errors import EngineError
from expense.reads import AccountIndex, QuickAddRefs
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.bulk_pick import BulkPickScreen
from expense.tui.screens.categories import CategoriesScreen
from expense.tui.screens.create_forms import EditAccountScreen, NewHashtagScreen
from expense.tui.screens.edit_form import EditFormScreen
from expense.tui.screens.log_bar import LogBarScreen
from expense.tui.screens.modals import ConfirmModal
from expense.tui.screens.reconciliations import (
    NewReconciliationScreen,
    ReconciliationDetailScreen,
    ReconciliationsScreen,
)
from expense.tui.screens.transactions import TransactionsScreen
from expense.tui.widgets.cursor_list import CursorList, CursorOptionList
from expense.tui.widgets.refusal import as_markup
from tests.unit.helpers import (
    ENGINE_URL,
    error_response,
    fake_ledger,
    render_text,
    run_app,
    styled_stretches,
    toasts_shown,
    wait_for,
    wait_for_list,
    whole,
)
from tests.unit.test_tui_bank_import import (
    CARD_ROWS,
    _bank_file,
    _body,
    _drop,
    _engine,
    _preview,
    _previewed,
)
from tests.unit.test_tui_bank_import import _open as _open_import
from tests.unit.test_tui_bank_import import _patch as _patch_import
from tests.unit.test_tui_edit_form import TXN
from tests.unit.test_tui_edit_form import _enter as _enter_edit
from tests.unit.test_tui_edit_form import _on as _on_edit
from tests.unit.test_tui_edit_form import _patch as _patch_edit
from tests.unit.test_tui_log_bar import (
    LEDGER_LINE,
    _peek,
    _PeekFetch,
    _save_settled,
    _script,
    _stage_lines,
)
from tests.unit.test_tui_log_bar import _open as _open_log
from tests.unit.test_tui_log_bar import _patch as _patch_log
from tests.unit.test_tui_log_bar import _refused as _refused_row
from tests.unit.test_tui_log_bar import _type as _type_log
from tests.unit.test_tui_opening_balance import EFECTIVO, SUELDO
from tests.unit.test_tui_opening_balance import _type as _type_account
from tests.unit.test_tui_reconcile_detail import (
    DRAFT,
    _complete_with_warnings,
    _open_box,
    _wait_list,
)
from tests.unit.test_tui_reconcile_detail import _patch as _patch_detail
from tests.unit.test_tui_reconcile_detail import _type as _type_box
from tests.unit.test_tui_reconciliations import _open_panel, _patch_browse, _patch_unfiled
from tests.unit.test_tui_setup import _address_and_key, _health_ok
from tests.unit.test_tui_setup import _text as _setup_text
from tests.unit.test_tui_system import _open_bootstrap_prompt, _patch_auth

#: The engine's words: a message holding `[like this]`, and one field's words
#: holding a lone `[` and a `[b]…[/b]` pair, each of which markup reads as a style.
MESSAGE = "Must be one of [like this]."
FIELD_WORDS = "A lone [ and [b]this[/b] too."


def refusal(code: str = "VALIDATION_ERROR", status: int = 422, key: str = "name") -> EngineError:
    """The engine's refusal, its message and one field's words holding brackets."""
    return EngineError(code, MESSAGE, {key: FIELD_WORDS}, status, {}, reasons={key: "INVALID"})


def whole_in(shown: str) -> bool:
    """Both the message and the field's words are there, every character."""
    return MESSAGE in shown and FIELD_WORDS in shown


async def toast_with_words(pilot, app) -> str:
    """The first toast holding the engine's message, as drawn."""
    await wait_for(
        pilot,
        lambda: any(MESSAGE[:12] in t for t in toasts_shown(app)),
        message="no toast holds the engine's words",
    )
    return next(t for t in toasts_shown(app) if MESSAGE[:12] in t)


@pytest.mark.parametrize(
    "words",
    [
        MESSAGE,
        FIELD_WORDS,
        "[/]",
        "[$error]x[/]",
        "\\[b]",
        "a \\\\[b] c",
        "[[x]]",
        "x\\y",
        "x\\",
        "x\\\\",
        "",
    ],
)
@pytest.mark.parametrize("styles", [[""], ["$error"], ["dim", ""], ["$error", "", "dim"]])
def test_words_written_as_markup_read_back_as_sent(words, styles):
    """`as_markup` keeps every line's words as sent, `[` and a backslash at
    their end and all, alone or in the app's styles, each line in its own."""
    lines = [(words, style) for style in styles]
    content = Content.from_markup(as_markup(lines))
    assert content.plain == "\n".join(words for _ in styles)
    styled = styled_stretches(as_markup(lines))
    starts = [n * (len(words) + 1) for n in range(len(styles))]
    lines_at = zip(starts, styles, strict=True)
    # a style over a line break alone shows nothing, so only words are compared
    assert [span for span in styled if span[1]] == [
        (start, words, style) for start, style in lines_at if style and words
    ]


# ---- Manage ------------------------------------------------------------------


def test_a_refused_delete_on_a_list_shows_the_words_whole(fake_client, monkeypatch):
    """`d` then `y` on Manage ▸ Categories, refused: `run_write`'s own "Failed"
    toast, which every write with no failure handler of its own shows."""
    rows = [{"id": "c1", "name": "HOGAR", "is_system": False, "color": None}]
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: whole(rows))
    fake_client.errors["DELETE"] = refusal("CONFLICT", 409, "category_id")

    async def scenario(pilot, app):
        await app.push_screen(CategoriesScreen())
        await wait_for_list(pilot, app)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        shown = await toast_with_words(pilot, app)
        assert shown.startswith("Failed\nCONFLICT — ")
        assert whole_in(shown)

    run_app(scenario, toasts=True)


def test_a_refused_archive_shows_the_words_whole(fake_client, monkeypatch):
    """`a` on Manage ▸ Accounts, refused: the toggle's own "Failed" toast."""
    rows = [
        {
            "id": "a1",
            "name": "BCP",
            "is_person": False,
            "is_archived": False,
            "currency_code": "PEN",
            "color": None,
            "opening_balance_transaction_id": None,
        }
    ]
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(rows))
    fake_client.errors["POST"] = refusal("CONFLICT", 409, "account_id")

    async def scenario(pilot, app):
        await app.push_screen(AccountsScreen())
        await wait_for_list(pilot, app)
        await pilot.press("a")
        assert whole_in(await toast_with_words(pilot, app))

    run_app(scenario, toasts=True)


def test_a_refused_create_form_shows_the_words_whole(fake_client):
    """A new hashtag the engine refuses: the form's "Failed" toast."""
    fake_client.errors["POST"] = refusal()

    async def scenario(pilot, app):
        screen = NewHashtagScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        screen.query_one("#bar", Input).value = "groceries"
        screen._recompute("groceries")
        screen.on_input_submitted(None)
        shown = await toast_with_words(pilot, app)
        assert shown.startswith("Failed\n") and whole_in(shown)
        assert screen.is_attached

    run_app(scenario, toasts=True)


def test_a_section_that_cannot_load_shows_the_words_whole(fake_client, monkeypatch):
    """A Manage list whose read is refused: the "Could not load." banner."""

    def refused(*a, **k):
        raise refusal("FORBIDDEN", 403)

    monkeypatch.setattr("expense.reads.fetch_accounts", refused)

    async def scenario(pilot, app):
        await app.push_screen(AccountsScreen())
        await wait_for(pilot, lambda: app.screen.query(".error"))
        banner = app.screen.query_one(".error", Static).content
        assert whole_in(render_text(banner, width=200))

    run_app(scenario)


# ---- the ledger --------------------------------------------------------------

LEDGER = [
    {
        "id": f"t{i}",
        "title": f"Txn {i}",
        "description": None,
        "amount_cents": -100 - i,
        "date": "2026-07-01",
        "account_id": "acc1",
        "category_id": "pend",
        "hashtag_ids": [],
        "bank_line_id": f"bl-{i}",
        "line_code": f"#{i + 1:06d}",
        "statement_line": None,
        "statement_place": None,
    }
    for i in range(23)
]
NAMES = {"acc1": "BCP Signature PEN", "cat1": "KORAKUEN", "pend": "@Pendiente"}
REFS = QuickAddRefs(
    accounts=[("acc1", "BCP Signature PEN", "PEN")],
    categories=[("cat1", "KORAKUEN")],
    hashtags=[],
    account_names={"acc1": "BCP Signature PEN"},
    category_names={"cat1": "KORAKUEN", "pend": "@Pendiente"},
    hashtag_names={},
    pending=("pend", "@Pendiente"),
    pickable_categories=[("cat1", "KORAKUEN"), ("pend", "@Pendiente")],
)


def _stub_ledger(monkeypatch, *, refs=REFS) -> None:
    fake_ledger(monkeypatch, LEDGER)
    monkeypatch.setattr(tx_mod, "load_account_index", lambda: AccountIndex(NAMES))
    for name in ("load_category_name_map", "load_hashtag_name_map"):
        monkeypatch.setattr(tx_mod, name, lambda: NAMES)

    def load_refs(cfg, **kw):
        if isinstance(refs, Exception):
            raise refs
        return refs

    monkeypatch.setattr(tx_mod, "load_quickadd_refs", load_refs)


async def _open_ledger(pilot, app) -> TransactionsScreen:
    screen = TransactionsScreen()
    await app.push_screen(screen)
    await wait_for_list(pilot, app)
    screen.query_one(CursorList).focus()
    await pilot.pause()
    return screen


def test_more_rows_that_cannot_be_read_show_the_words_whole(fake_client, monkeypatch):
    """`pgdn` on the ledger, the next rows' read refused: the growing list's
    "Failed" toast."""
    _stub_ledger(monkeypatch)
    real = reads_mod.fetch_transactions

    def fetch(*a, after=None, **k):
        if after:
            raise refusal("FORBIDDEN", 403)
        return real(*a, after=after, **k)

    monkeypatch.setattr("expense.reads.fetch_transactions", fetch)

    async def scenario(pilot, app):
        await _open_ledger(pilot, app)
        await pilot.press("pagedown")
        assert whole_in(await toast_with_words(pilot, app))

    run_app(scenario, size=(120, 35), toasts=True)


def test_a_delete_whose_line_cannot_be_read_shows_the_words_whole(fake_client, monkeypatch):
    """`d` on a ledger row, its bank line's read refused: no question, the
    "Failed" toast."""
    _stub_ledger(monkeypatch)

    def refused(*a, **k):
        raise refusal("FORBIDDEN", 403)

    monkeypatch.setattr("expense.reads.fetch_bank_line", refused)

    async def scenario(pilot, app):
        await _open_ledger(pilot, app)
        await pilot.press("d")
        assert whole_in(await toast_with_words(pilot, app))

    run_app(scenario, size=(120, 35), toasts=True)


def test_pickers_that_cannot_load_show_the_words_whole(fake_client, monkeypatch):
    """`c` on the ledger, the pickers' names refused: "Could not load the pickers"."""
    _stub_ledger(monkeypatch, refs=refusal("FORBIDDEN", 403))

    async def scenario(pilot, app):
        await _open_ledger(pilot, app)
        await pilot.press("c")
        shown = await toast_with_words(pilot, app)
        assert shown.startswith("Could not load the pickers\n") and whole_in(shown)

    run_app(scenario, size=(120, 35), toasts=True)


def test_a_refused_bulk_edit_shows_the_words_whole(fake_client, monkeypatch):
    """`c` on a ledger row, its `PUT` refused: the bulk edit's "Refused" note,
    the field's words in its colour, escaped inside it (a row's note leaves the
    engine's first sentence out, as the LOG bar's does)."""
    _stub_ledger(monkeypatch)
    fake_client.errors["PUT"] = refusal(key="category_id")

    async def scenario(pilot, app):
        await _open_ledger(pilot, app)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, BulkPickScreen))
        await pilot.press(*"kor", "enter")
        await wait_for(pilot, lambda: any("Refused" in t for t in toasts_shown(app)))
        shown = next(t for t in toasts_shown(app) if t.startswith("Refused"))
        assert f"category_id: {FIELD_WORDS}" in shown

    run_app(scenario, size=(120, 35), toasts=True)


@pytest.mark.parametrize(
    "words", ["Ends in a backslash \\", "Ends in two \\\\", "A \\[b] escape.", "[like this]"]
)
def test_a_refused_bulk_edit_keeps_a_backslash_before_its_colour_ends(
    fake_client, monkeypatch, words
):
    """The bulk edit's note styles the engine's words in the error colour, the
    app's own markup closing after them: a backslash at their end, two, or one
    before a `[` all show as sent, and so does `[like this]`."""
    _stub_ledger(monkeypatch)
    fake_client.errors["PUT"] = EngineError(
        "VALIDATION_ERROR", MESSAGE, {"category_id": words}, 422, {}, {"category_id": "INVALID"}
    )

    async def scenario(pilot, app):
        await _open_ledger(pilot, app)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, BulkPickScreen))
        await pilot.press(*"kor", "enter")
        await wait_for(pilot, lambda: any("Refused" in t for t in toasts_shown(app)))
        shown = next(t for t in toasts_shown(app) if t.startswith("Refused"))
        assert f"\ncategory_id: {words}\nrow 1" in shown

    run_app(scenario, size=(120, 35), toasts=True)


def test_a_bulk_edit_the_engine_stops_shows_the_words_whole(fake_client, monkeypatch):
    """A refusal every row would draw too (`SETTINGS_MISSING`) stops the bulk
    edit: one "Failed" toast, the LOG bar's."""
    _stub_ledger(monkeypatch)
    fake_client.errors["PUT"] = refusal("SETTINGS_MISSING", 422, "user_settings")

    async def scenario(pilot, app):
        screen = await _open_ledger(pilot, app)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, BulkPickScreen))
        await pilot.press(*"kor", "enter")
        shown = await toast_with_words(pilot, app)
        await wait_for(pilot, lambda: not screen._bulk_busy)
        assert shown.startswith("Failed") and whole_in(shown)

    run_app(scenario, size=(120, 35), toasts=True)


def test_a_bulk_receipt_shows_a_name_whole(fake_client, monkeypatch):
    """The receipt after a bulk edit names what the rows went to, as the
    engine holds its name."""
    name = "KORAKUEN [like this]"
    refs = replace(
        REFS,
        categories=[("cat1", name)],
        category_names={"cat1": name, "pend": "@Pendiente"},
        pickable_categories=[("cat1", name), ("pend", "@Pendiente")],
    )
    _stub_ledger(monkeypatch, refs=refs)

    async def scenario(pilot, app):
        screen = await _open_ledger(pilot, app)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, BulkPickScreen))
        await pilot.press(*"kor", "enter")
        await wait_for(pilot, lambda: not screen._bulk_busy and toasts_shown(app))
        assert f"1 row → {name}" in toasts_shown(app)

    run_app(scenario, size=(120, 35), toasts=True)


def test_a_delete_question_shows_a_name_whole(fake_client, monkeypatch):
    """`d` on a category whose name holds brackets: the question names it as
    the engine holds it."""
    name = "HOGAR [like this]"
    rows = [{"id": "c1", "name": name, "is_system": False, "color": None}]
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: whole(rows))

    async def scenario(pilot, app):
        await app.push_screen(CategoriesScreen())
        await wait_for_list(pilot, app)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        shown = "\n".join(str(s.visual) for s in app.screen.query(Static))
        assert name in shown

    run_app(scenario)


# ---- the account Edit form's opening balance ---------------------------------


def test_an_opening_balance_that_cannot_be_read_shows_the_words_whole(fake_client, monkeypatch):
    """The account's opening balance read refused: the form's "Failed" toast."""

    def refused(*a, **k):
        raise refusal("FORBIDDEN", 403)

    monkeypatch.setattr("expense.reads.fetch_transaction", refused)

    async def scenario(pilot, app):
        await app.push_screen(EditAccountScreen(dict(SUELDO)))
        assert whole_in(await toast_with_words(pilot, app))

    run_app(scenario, toasts=True)


def test_a_refused_opening_balance_after_the_account_saved_shows_the_words_whole(fake_client):
    """The account saves, its opening balance is refused: the note that says
    which half went through."""
    fake_client.errors["POST"] = refusal(key="date")

    async def scenario(pilot, app):
        screen = EditAccountScreen(dict(EFECTIVO))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        _type_account(screen, "color", "green")
        _type_account(screen, "opening", "350.00")
        _type_account(screen, "as_of", "2026-01-01")
        shown = await toast_with_words(pilot, app)
        assert "The opening balance is not:" in shown and whole_in(shown)

    run_app(scenario, toasts=True)


# ---- the Edit form -------------------------------------------------------------


def test_an_edit_form_that_cannot_load_shows_the_words_whole(fake_client, monkeypatch):
    """The Edit form's line read refused: its toast."""
    _patch_edit(monkeypatch)

    def refused(*a, **k):
        raise refusal("FORBIDDEN", 403)

    monkeypatch.setattr("expense.reads.fetch_bank_line", refused)

    async def scenario(pilot, app):
        await app.push_screen(EditFormScreen(record=TXN))
        assert whole_in(await toast_with_words(pilot, app))

    run_app(scenario, toasts=True)


def test_a_refused_save_under_the_parts_shows_the_words_whole(fake_client, monkeypatch):
    """A save on the Edit form refused: the lines under the parts."""
    _patch_edit(monkeypatch)
    fake_client.errors["PUT"] = refusal(key="title")

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._ready)
        _on_edit(screen, "title")
        _enter_edit(screen, "Farmacia Inkafarma")
        screen.action_submit()
        await wait_for(pilot, lambda: screen._refusal is not None and not screen._submitting)
        shown = render_text(screen.query_one("#summary", Static).content, width=200)
        assert f"VALIDATION_ERROR — {MESSAGE}" in shown
        assert f"! title: {FIELD_WORDS}" in shown

    run_app(scenario)


# ---- the LOG bar -----------------------------------------------------------------


def test_a_log_bar_whose_names_cannot_load_shows_the_words_whole(fake_client, monkeypatch):
    """The LOG bar's account, category and hashtag reads refused: its toast."""
    _patch_log(monkeypatch)

    def refused(*a, **k):
        raise refusal("FORBIDDEN", 403)

    monkeypatch.setattr("expense.reads.fetch_accounts", refused)

    async def scenario(pilot, app):
        await app.push_screen(LogBarScreen())
        assert whole_in(await toast_with_words(pilot, app))

    run_app(scenario, toasts=True)


def test_a_save_the_engine_stops_shows_the_words_whole(fake_client, monkeypatch):
    """A refusal every row would draw too (`SETTINGS_MISSING`): one "Failed" toast."""
    _patch_log(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_log(app, pilot)
        _stage_lines(screen, LEDGER_LINE)
        _script(fake_client, [refusal("SETTINGS_MISSING", 422, "user_settings")])
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)
        assert whole_in(await toast_with_words(pilot, app))

    run_app(scenario, toasts=True)


def test_a_refused_row_under_the_log_bar_shows_the_words_whole(fake_client, monkeypatch):
    """A row the batch refuses by key: its line under the staged rows, the
    field's words (a row's line leaves the engine's first sentence out)."""
    _patch_log(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_log(app, pilot)
        _stage_lines(screen, LEDGER_LINE)
        _script(fake_client, [_refused_row(0, "title", FIELD_WORDS, "INVALID")])
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)
        shown = render_text(screen._staged_renderable(), width=200)
        assert f"title: {FIELD_WORDS}" in shown

    run_app(scenario)


def test_a_peek_that_cannot_load_shows_the_words_whole(fake_client, monkeypatch):
    """The account peek's read refused: the note in its own panel."""
    _patch_log(monkeypatch, _PeekFetch(error=refusal("FORBIDDEN", 403)))

    async def scenario(pilot, app):
        screen = await _open_log(app, pilot)
        _type_log(screen, LEDGER_LINE)
        await wait_for(pilot, lambda: bool(screen._peek_note))
        assert whole_in(render_text(_peek(screen).content, width=300))

    run_app(scenario, size=(110, 30))


# ---- the import door -------------------------------------------------------------


def test_an_import_whose_accounts_cannot_load_shows_the_words_whole(
    fake_client, monkeypatch, tmp_path
):
    """The import's account list read refused: its toast, and its line on the screen."""
    path = _bank_file(tmp_path)
    _patch_import(monkeypatch)

    def refused(*a, **k):
        raise refusal("FORBIDDEN", 403)

    async def scenario(pilot, app):
        screen = await _open_import(app, pilot)
        monkeypatch.setattr("expense.reads.fetch_accounts", refused)
        await _drop(pilot, screen, path)
        assert whole_in(await toast_with_words(pilot, app))
        assert whole_in(_body(app.screen))

    run_app(scenario, size=(120, 40), toasts=True)


def test_a_refused_import_shows_the_words_whole(fake_client, monkeypatch, tmp_path):
    """The apply refused naming a file row: its toast, and the `!` line the
    preview gives the row's words."""
    path = _bank_file(tmp_path)
    _patch_import(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD_ROWS})

    async def scenario(pilot, app):
        screen = await _open_import(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        fake_client.errors["POST"] = refusal(key="rows.4")
        await pilot.press("enter")
        assert whole_in(await toast_with_words(pilot, app))
        body = _body(preview)
        assert f"VALIDATION_ERROR — {MESSAGE}" in body
        assert f"! rows.4: {FIELD_WORDS}" in body  # words naming no row keep the key

    run_app(scenario, size=(120, 40), toasts=True)


# ---- reconciliations ---------------------------------------------------------------


def test_reconciliations_that_cannot_be_read_show_the_words_whole(monkeypatch):
    """`⏎` on an account, its holder's statements' read refused: the "Failed" toast."""
    _patch_browse(monkeypatch)

    def refused(*a, **k):
        raise refusal("FORBIDDEN", 403)

    monkeypatch.setattr("expense.reads.fetch_statements", refused)

    async def scenario(pilot, app):
        await app.push_screen(ReconciliationsScreen())
        await wait_for_list(pilot, app)
        await pilot.press("enter")
        assert whole_in(await toast_with_words(pilot, app))

    run_app(scenario, toasts=True)


def test_lines_in_no_batch_that_cannot_be_read_show_the_words_whole(monkeypatch):
    """`u` on an account's panel, its lines in no batch refused: the "Failed" toast."""
    _patch_browse(monkeypatch)
    _patch_unfiled(monkeypatch)

    def refused(*a, **k):
        raise refusal("FORBIDDEN", 403)

    monkeypatch.setattr("expense.reads.fetch_bank_lines", refused)

    async def scenario(pilot, app):
        await _open_panel(pilot, app)
        await pilot.press("u")
        assert whole_in(await toast_with_words(pilot, app))

    run_app(scenario, toasts=True)


def test_a_new_reconciliation_whose_accounts_cannot_load_shows_the_words_whole(
    fake_client, monkeypatch
):
    """The new reconciliation form's account read refused: its toast."""

    def refused(*a, **k):
        raise refusal("FORBIDDEN", 403)

    monkeypatch.setattr("expense.reads.fetch_accounts", refused)

    async def scenario(pilot, app):
        await app.push_screen(NewReconciliationScreen())
        assert whole_in(await toast_with_words(pilot, app))

    run_app(scenario, toasts=True)


def test_a_batch_screen_that_cannot_load_shows_the_words_whole(fake_client, monkeypatch):
    """A reconciliation's batch screen, its lines' read refused: its toast."""
    _patch_detail(monkeypatch)

    def refused(*a, **k):
        raise refusal("FORBIDDEN", 403)

    monkeypatch.setattr("expense.reads.fetch_bank_lines", refused)

    async def scenario(pilot, app):
        await app.push_screen(ReconciliationDetailScreen(dict(DRAFT)))
        assert whole_in(await toast_with_words(pilot, app))

    run_app(scenario, toasts=True)


def test_a_refused_tick_shows_the_words_whole(fake_client, monkeypatch):
    """`space` on a row, its `PUT` refused: "Couldn't update"."""
    _patch_detail(monkeypatch)
    fake_client.errors["PUT"] = refusal(key="reconciliation_id")

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        screen._list._cursor = 2
        await pilot.press("space")
        shown = await toast_with_words(pilot, app)
        assert shown.startswith("Couldn't update\n") and whole_in(shown)

    run_app(scenario, toasts=True)


def test_a_refused_ending_balance_shows_the_words_whole(fake_client, monkeypatch):
    """`c` with no ending balance, its save refused: "Couldn't save"."""
    _patch_detail(monkeypatch)
    fake_client.errors["PUT"] = refusal(key="ending_balance_cents")

    async def scenario(pilot, app):
        await _open_box(pilot, app)
        await _type_box(pilot, "13853.20")
        await pilot.press("enter")
        shown = await toast_with_words(pilot, app)
        assert shown.startswith("Couldn't save\n") and whole_in(shown)

    run_app(scenario, toasts=True)


def test_a_refused_delete_of_a_reconciliation_shows_the_words_whole(fake_client, monkeypatch):
    """`d` then `y` on a batch screen, refused: "Couldn't delete"."""
    _patch_detail(monkeypatch)
    fake_client.errors["DELETE"] = refusal("CONFLICT", 409, "reconciliation_id")

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        shown = await toast_with_words(pilot, app)
        assert shown.startswith("Couldn't delete\n") and whole_in(shown)

    run_app(scenario, toasts=True)


def test_a_complete_s_gap_line_shows_the_words_whole(fake_client, monkeypatch):
    """`complete`'s warning: the line under the header, in the engine's words."""
    _patch_detail(monkeypatch)
    _complete_with_warnings(fake_client, [MESSAGE])

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        line = screen.query_one("#rwarn", Static)
        screen.action_complete()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: line.display)
        assert MESSAGE in render_text(line.content, width=200)

    run_app(scenario)


# ---- setup and System ----------------------------------------------------------------


def test_a_refused_key_on_setup_shows_the_words_whole():
    """Setup's key refused: the engine's words on the hint line."""

    async def scenario(pilot, app):
        screen = app.screen
        await _address_and_key(pilot, screen)
        await wait_for(pilot, lambda: "UNAUTHORIZED" in _setup_text(screen, "#hint"))
        assert whole_in(render_text(screen.query_one("#hint", Static).content, width=200))

    with respx.mock:
        _health_ok()
        respx.get(f"{ENGINE_URL}/v1/auth/me").mock(
            return_value=error_response(401, "UNAUTHORIZED", MESSAGE, {"token": FIELD_WORDS})
        )
        run_app(scenario, setup=True)


def test_a_refused_bootstrap_shows_the_words_whole(fake_client, monkeypatch):
    """System ▸ Auth & profile, `b`, refused: "Bootstrap failed"."""
    _patch_auth(fake_client, monkeypatch, me=None)
    monkeypatch.setattr("expense.dates.detect_timezone", lambda *a, **k: "America/Lima")
    fake_client.errors["POST"] = refusal(key="display_name")

    async def scenario(pilot, app):
        await _open_bootstrap_prompt(pilot, app)
        app.screen.query_one("#prompt").value = "Alex"
        await pilot.press("enter")
        shown = await toast_with_words(pilot, app)
        assert shown.startswith("Bootstrap failed\n") and whole_in(shown)

    run_app(scenario, toasts=True)


def test_home_s_month_that_cannot_load_shows_the_words_whole(monkeypatch):
    """Home's month read refused: its note among the screen entries."""

    def refused(*a, **k):
        raise refusal("FORBIDDEN", 403)

    monkeypatch.setattr("expense.reads.fetch_dashboard", refused)
    monkeypatch.setattr("expense.reads.fetch_range", refused)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        home = app.screen
        await wait_for(pilot, lambda: home._error is not None)
        await pilot.pause()
        menu = home.query_one("#menu", CursorOptionList)
        shown = "\n".join(
            render_text(menu.get_option_at_index(i).prompt, width=300)
            for i in range(menu.option_count)
        )
        assert whole_in(shown)

    run_app(scenario)
