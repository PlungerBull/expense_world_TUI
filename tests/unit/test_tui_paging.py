"""Pagination — widget window/indicator/keys + the shared helpers.

Pages are min(PAGE_ROWS_CAP, what fits the terminal) (adaptive
rows): the ledger tests pin `run_test(size=…)` so the expected window
is deterministic — a 30-line harness proves the shrink, a tiny one proves the
floor. The cap is `DEFAULT_PAGE_ROWS` (20) app-wide but `ENGINE_PAGE_CAP` on
Transactions, which grows with the window. The
ledger is one growing list: the window sizes what is drawn, and every read
is `GROW_STEP` rows by cursor (`GrowingRead`, shared with the "no batch" pane).

Mostly pure tests in the style of the other widget suites: `_build()` renders
through a Rich Console; action handlers run with `_refresh`/`post_message`
stubbed so no event loop is needed.
"""

import re
import threading

import pytest
from textual.containers import VerticalScroll

from expense.reads import DEFAULT_PAGE_ROWS, ENGINE_PAGE_CAP, AccountIndex, items_of
from expense.tui.screens._base import AdaptiveRowsMixin
from expense.tui.screens._growing import read_first
from expense.tui.widgets.checklist import CheckList
from expense.tui.widgets.cursor_list import GROW_STEP, CursorList, page_indicator
from expense.tui.widgets.windowed import CURSOR_STYLE, WindowedList
from tests.unit.helpers import (
    bank_line_row,
    cursor_page,
    fake_ledger,
    import_part,
    list_ready,
    render_text,
    run_app,
    wait_for,
    wait_for_list,
    wait_for_loaded,
    whole,
)


def _text(renderable) -> str:
    return render_text(renderable, width=120)


def _rows(n: int) -> list[tuple]:
    return [(f"id{i}", (f"row {i:02d}", f"{i}.00")) for i in range(n)]


def _list(n: int = 45, **kwargs) -> CursorList:
    lst = CursorList(["Title", "Amount"], _rows(n), align_right={1}, **kwargs)
    lst._refresh = lambda: None  # pure: no event loop, no live repaint
    return lst


# ---- page_indicator (shared helper) -----------------------------------------


def test_page_indicator_none_when_single_page():
    assert page_indicator(0, 5, 5, 20) is None
    assert page_indicator(0, 20, 20, 20) is None
    assert page_indicator(0, 0, 0, 20) is None


def test_page_indicator_counts_rows_and_pages():
    assert page_indicator(0, 20, 133, 20) == "rows 1-20 of 133 · page 1 of 7"
    assert page_indicator(20, 20, 133, 20) == "rows 21-40 of 133 · page 2 of 7"
    assert page_indicator(120, 13, 133, 20) == "rows 121-133 of 133 · page 7 of 7"


# ---- CursorList window mode (full data in memory) ---------------------------


def test_build_windows_to_page_size():
    out = _text(_list(45)._build())
    assert "row 00" in out and "row 19" in out
    assert "row 20" not in out  # window ends at page_size


def test_window_follows_cursor_across_pages():
    lst = _list(45)
    lst.set_cursor(20)  # j past the boundary lands here
    out = _text(lst._build())
    assert "row 20" in out and "row 39" in out
    assert "row 19" not in out and "row 40" not in out


def test_cursor_restore_lands_on_its_page():
    lst = _list(45)
    lst.set_cursor(lst.index_of("id33"))  # the _restore_key pattern after a write
    assert "row 33" in _text(lst._build())
    assert lst.page_status == "rows 21-40 of 45 · page 2 of 3"


def test_action_page_jumps_and_clamps():
    lst = _list(45)
    lst.post_message = lambda m: True
    lst.action_page(1)
    assert lst._cursor == 20
    lst.action_page(1)
    assert lst._cursor == 40
    lst.action_page(1)
    assert lst._cursor == 44  # clamped to the last row
    lst.action_page(-1)
    assert lst._cursor == 24


def test_action_page_posts_highlighted_in_window_mode():
    lst = _list(45)
    captured = []
    lst.post_message = captured.append
    lst.action_page(1)
    assert len(captured) == 1 and isinstance(captured[0], CursorList.Highlighted)
    assert captured[0].key == "id20"  # two-pane screens stay in sync on page jumps


def test_single_page_hides_page_keys_and_subtitle():
    lst = _list(5)
    assert lst.page_status is None
    assert lst.check_action("page", ()) is False
    assert _list(45).check_action("page", ()) is True


def test_set_page_size_rewindows_around_cursor():
    """Terminal resize (adaptive rows): the window re-slices to the
    new size and keeps following the cursor."""
    lst = _list(45)
    lst.set_page_size(10)
    out = _text(lst._build())
    assert "row 00" in out and "row 09" in out and "row 10" not in out
    assert lst.page_status == "rows 1-10 of 45 · page 1 of 5"
    lst.set_cursor(23)
    assert lst.page_status == "rows 21-30 of 45 · page 3 of 5"
    lst.set_page_size(10)  # no-op: same size must not re-render
    assert lst._page_size == 10


# ---- CheckList (always window mode; one physical line per row) -------------


def _chk_rows(n: int) -> list[tuple]:
    return [(f"l{i}", "2026-07-01", f"txn {i:02d}", f"op{i}", -1000 - i) for i in range(n)]


def _checklist(n: int = 25, **kwargs) -> CheckList:
    chk = CheckList(_chk_rows(n), **kwargs)
    chk._refresh = lambda: None
    return chk


def test_checklist_windows_rows():
    out = _text(_checklist(25)._build())
    assert "txn 00" in out and "txn 19" in out
    assert "txn 20" not in out  # 20 rows per page


def test_checklist_page_status_counts_rows():
    chk = _checklist(25)
    assert chk.page_status == "rows 1-20 of 25 · page 1 of 2"
    chk._cursor = 20
    assert chk.page_status == "rows 21-25 of 25 · page 2 of 2"


def test_checklist_checked_state_survives_paging():
    chk = _checklist(25, checked=["l3", "l22"])
    chk.post_message = lambda m: True
    chk.action_page(1)  # display window moves; membership must not
    assert chk.checked == {"l3", "l22"}
    out = _text(chk._build())
    assert "txn 22" in out and "[x]" in out


def test_checklist_toggle_on_page_two_targets_the_right_key():
    chk = _checklist(25)
    captured = []
    chk.post_message = captured.append
    chk.action_page(1)
    chk.action_toggle()
    assert chk.checked == {"l20"}
    toggles = [m for m in captured if isinstance(m, CheckList.Toggled)]
    assert len(toggles) == 1 and toggles[0].key == "l20" and toggles[0].checked


def test_checklist_single_page_hides_page_keys():
    assert _checklist(8).check_action("page", ()) is False
    assert _checklist(25).check_action("page", ()) is True


def test_checklist_set_page_size_keeps_checks():
    """Resize re-slices the window; membership is a key-set over the whole
    batch, so checks survive (adaptive rows)."""
    chk = _checklist(25, checked=["l3", "l22"])
    chk.set_page_size(6)
    out = _text(chk._build())
    assert "txn 05" in out and "txn 06" not in out
    assert chk.checked == {"l3", "l22"}
    assert chk.page_status == "rows 1-6 of 25 · page 1 of 5"


# ---- manage-list fetch: one read, the whole list -----------------------------


def _whole_fetch(n: int, prefix: str, calls: list):
    """A fake that behaves like the engine: every row, and a 422
    for any paging parameter."""

    def fake_fetch(cfg, **kw):
        assert "limit" not in kw and "offset" not in kw, "the engine refuses paging"
        calls.append(kw)
        return whole([{"id": f"{prefix}{i}"} for i in range(n)])

    return fake_fetch


def test_categories_manage_reads_the_whole_list_once(monkeypatch):
    """The manage screens window locally over the full set; the engine
    returns it whole, so one read holds every row."""
    calls: list = []
    monkeypatch.setattr("expense.reads.fetch_categories", _whole_fetch(150, "c", calls))
    from expense.tui.screens.categories import CategoriesScreen

    assert len(items_of(CategoriesScreen().fetch_items(None))) == 150
    assert len(calls) == 1


def test_hashtags_manage_reads_the_whole_list_once(monkeypatch):
    calls: list = []
    monkeypatch.setattr("expense.reads.fetch_hashtags", _whole_fetch(130, "h", calls))
    from expense.tui.screens.hashtags import HashtagsScreen

    assert len(items_of(HashtagsScreen().fetch_items(None))) == 130
    assert len(calls) == 1


# ---- the ledger as one growing list ------------------------------------------


def _ledger_rows(n: int) -> list[dict]:
    return [
        {
            "id": f"t{i}",
            "title": f"Txn {i}",
            "amount_cents": -100 - i,
            "date": "2026-07-01",
            "line_code": f"#{i + 1:06d}",
            "statement_line": None,
            "statement_place": None,
        }
        for i in range(n)
    ]


def test_read_first_reads_one_step_then_counts():
    reads: list = []

    def fetch_page(limit, after):
        reads.append((limit, after))
        return cursor_page(_ledger_rows(limit), next_cursor=f"c{limit}")

    items, nxt, total = read_first(fetch_page, lambda: 133)
    assert reads == [(GROW_STEP, None)]
    assert len(items) == GROW_STEP and nxt == "c10" and total == 133


def test_read_first_fails_when_the_count_does():
    def count():
        raise RuntimeError("count unavailable")

    with pytest.raises(RuntimeError):
        read_first(lambda limit, after: cursor_page(_ledger_rows(3)), count)


def _patch_transactions(monkeypatch, n: int = 133, **kw) -> tuple[list, list, list]:
    """`n` fake transactions behind the cursor fake; returns (rows, reads, counts)."""
    import expense.tui.screens.transactions as tx_mod

    rows = _ledger_rows(n)
    reads, counts = fake_ledger(monkeypatch, rows, **kw)
    monkeypatch.setattr(tx_mod, "load_account_index", lambda: AccountIndex({}))
    monkeypatch.setattr(tx_mod, "load_category_name_map", lambda: {})
    monkeypatch.setattr(tx_mod, "load_hashtag_name_map", lambda: {})
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    return rows, reads, counts


def _drive_transactions(size: tuple[int, int], checks, *, wait=wait_for_list) -> None:
    """Push a TransactionsScreen in a `size` harness and run `checks(pilot, screen)`."""

    async def scenario(pilot, app):
        from expense.tui.screens.transactions import TransactionsScreen

        screen = TransactionsScreen()
        await app.push_screen(screen)
        await wait(pilot, app)
        await checks(pilot, screen)

    run_app(scenario, size=size)


def _ledger(screen) -> CursorList:
    return screen.query_one(CursorList)


def test_the_ledger_opens_with_ten_and_the_count(monkeypatch):
    _rows, reads, counts = _patch_transactions(monkeypatch)

    async def checks(pilot, screen):
        assert reads == [{"limit": GROW_STEP, "after": None, "verbose": False}]
        assert len(counts) == 1
        assert _ledger(screen).row_count == GROW_STEP
        assert screen._legend() == "no filter · 10 of 133 loaded"
        # a growing list states its count in the legend, never `rows 1-10 of 10`
        assert _ledger(screen).page_status is None

    _drive_transactions((120, 35), checks)


def test_pgdn_appends_the_next_ten_by_cursor_and_lands_on_the_first_new_row(monkeypatch):
    _rows, reads, counts = _patch_transactions(monkeypatch)

    async def checks(pilot, screen):
        _ledger(screen).focus()
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: _ledger(screen).row_count == 20)
        assert reads[-1] == {"limit": GROW_STEP, "after": "c10", "verbose": False}
        assert _ledger(screen).cursor_index == 10
        assert _ledger(screen).cursor_key == "t10"
        assert len(counts) == 1  # `pgdn` does not recount
        assert screen._legend() == "no filter · 20 of 133 loaded"
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: _ledger(screen).row_count == 30)
        assert reads[-1]["after"] == "c20"

    _drive_transactions((120, 35), checks)


def test_pgdn_at_the_end_sends_nothing(monkeypatch):
    _rows, reads, _counts = _patch_transactions(monkeypatch, n=7)

    async def checks(pilot, screen):
        _ledger(screen).focus()
        assert not _ledger(screen).check_action("more", ())
        await pilot.press("pagedown")
        await pilot.pause()
        assert len(reads) == 1
        screen._grow.grow(lambda limit, after: pytest.fail("read past the end"))
        assert len(reads) == 1

    _drive_transactions((120, 35), checks)


def test_a_write_starts_the_list_over(monkeypatch):
    """Any write reloads the list fresh — the newest 10,
    recounted, the cursor on row 1 — like any app's list."""
    rows, reads, counts = _patch_transactions(monkeypatch)

    async def checks(pilot, screen):
        _ledger(screen).focus()
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: _ledger(screen).row_count == 20)
        _ledger(screen).set_cursor(15)
        del rows[15]  # the engine applied the write: t15 left the filter
        screen._reload_fresh()
        # mid-swap the old list is gone and the new one not yet in: wait for the load to settle
        await wait_for(
            pilot,
            lambda: len(counts) == 2 and list_ready(pilot.app) and _ledger(screen).row_count == 10,
        )
        assert reads[-1] == {"limit": GROW_STEP, "after": None, "verbose": False}
        assert _ledger(screen).cursor_index == 0 and _ledger(screen).cursor_key == "t0"
        assert screen._legend() == "no filter · 10 of 132 loaded"
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: _ledger(screen).row_count == 20)
        assert reads[-1]["after"] == "c10"

    _drive_transactions((120, 35), checks)


def test_pgdn_during_a_rereading_write_reads_nothing(monkeypatch):
    """While the re-read after a write is in flight, the old list is still on
    screen, and its cursor points at the old list's end. A `pgdn` there must
    read nothing: on a filtered ledger the new list already ends one row
    further along, so rows read from the old end would repeat one."""
    import expense.reads as tc

    rows, reads, counts = _patch_transactions(monkeypatch)
    fetch = tc.fetch_transactions
    gate = threading.Event()
    held = threading.Event()

    def slow_reread(*a, **kw):
        if kw.get("after") is None:
            held.set()
            gate.wait(5)
        return fetch(*a, **kw)

    async def checks(pilot, screen):
        _ledger(screen).focus()
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: _ledger(screen).row_count == 20)
        monkeypatch.setattr(tc, "fetch_transactions", slow_reread)
        del rows[15]  # the write took t15 out of the filter
        screen._reload_fresh()
        await wait_for(pilot, held.is_set)
        before = len(reads)
        await pilot.press("pagedown")  # the old list is still the one on screen
        await pilot.pause()
        gate.set()
        await wait_for(pilot, lambda: len(counts) == 2 and list_ready(pilot.app))
        assert [r["after"] for r in reads[before:]] == [None]  # only the re-read
        keys = [row.key for row in _ledger(screen)._rows]
        assert len(keys) == len(set(keys)) == 10
        # and once the new list is in, pgdn grows it from its own end
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: _ledger(screen).row_count == 20)
        assert reads[-1]["after"] == "c10"


def test_a_pgdn_read_that_lands_after_a_write_is_dropped(monkeypatch):
    """The other half of the same race: `pgdn` read the next 10, a write
    started the list over while that read was out, and the read came back
    after the fresh list was in. Its rows belong to the old list — they are
    dropped, never appended onto the new one."""
    import expense.reads as tc

    rows, reads, counts = _patch_transactions(monkeypatch)
    fetch = tc.fetch_transactions
    gate = threading.Event()
    held = threading.Event()

    def slow_more(*a, **kw):
        if kw.get("after") == "c10":
            held.set()
            gate.wait(5)
        return fetch(*a, **kw)

    async def checks(pilot, screen):
        monkeypatch.setattr(tc, "fetch_transactions", slow_more)
        _ledger(screen).focus()
        await pilot.press("pagedown")
        await wait_for(pilot, held.is_set)
        del rows[3]  # a write, and the fresh read that follows it
        screen._reload_fresh()
        await wait_for(pilot, lambda: len(counts) == 2 and list_ready(pilot.app))
        gate.set()
        await wait_for(pilot, lambda: not screen._grow.busy and len(reads) == 3)
        await pilot.pause()
        keys = [row.key for row in _ledger(screen)._rows]
        assert keys == [f"t{i}" for i in (0, 1, 2, 4, 5, 6, 7, 8, 9, 10)]

    _drive_transactions((120, 35), checks)


def test_r_starts_again_from_the_newest_ten(monkeypatch):
    _rows, reads, counts = _patch_transactions(monkeypatch)

    async def checks(pilot, screen):
        _ledger(screen).focus()
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: _ledger(screen).row_count == 20)
        await pilot.press("r")
        await wait_for(pilot, lambda: len(counts) == 2 and list_ready(pilot.app))
        assert reads[-1] == {"limit": GROW_STEP, "after": None, "verbose": False}
        assert _ledger(screen).row_count == GROW_STEP and _ledger(screen).cursor_index == 0

    _drive_transactions((120, 35), checks)


def test_a_resize_reads_nothing_and_keeps_the_cursor_row(monkeypatch):
    _rows, reads, counts = _patch_transactions(monkeypatch)

    async def checks(pilot, screen):
        _ledger(screen).focus()
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: _ledger(screen).row_count == 20)
        before = len(reads)
        await pilot.resize_terminal(120, 22)
        await wait_for(pilot, lambda: _ledger(screen)._page_size < 20)
        assert len(reads) == before and len(counts) == 1
        assert _ledger(screen).cursor_key == "t10" and _ledger(screen).row_count == 20

    _drive_transactions((120, 35), checks)


def test_a_selects_every_loaded_row(monkeypatch):
    _patch_transactions(monkeypatch)

    async def checks(pilot, screen):
        _ledger(screen).focus()
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: _ledger(screen).row_count == 20)
        await pilot.press("a")
        await wait_for(pilot, lambda: len(screen._selected) == 20)
        assert screen._legend() == "no filter · 20 of 133 loaded · 20 selected"

    _drive_transactions((120, 35), checks)


def test_a_count_that_cannot_be_read_fails_the_ledger(monkeypatch):
    """Never rows beside a missing or guessed number."""
    _patch_transactions(monkeypatch, count_fails=True)

    async def checks(pilot, screen):
        assert screen.query(".error") and not screen.query(CursorList)

    _drive_transactions((120, 35), checks, wait=wait_for_loaded)


def test_transactions_panel_fills_and_fits_the_viewport(monkeypatch):
    """The ledger takes the window it is given and no more: the
    card spans #content's full width, and the panel's own height never exceeds
    it — a clipped bottom border and the undraggable scrollbar are what an
    overshooting LIST_FRAME_LINES looked like."""
    _patch_transactions(monkeypatch)

    async def checks(pilot, screen):
        content = screen.query_one("#content", VerticalScroll)
        # `list_ready` only proves the list mounted and the loader went away — it
        # says nothing about a layout pass having run, so every `.size` below can
        # still be 0. Locally the layout usually lands by this point; on CI it
        # may not, depending on collection order and the preceding workload.
        await wait_for(
            pilot,
            lambda: screen.query_one("#card").size.width > 0,
            message="the card was never laid out",
        )
        assert screen.query_one("#card").size.width == content.content_size.width
        assert screen.query(CursorList).first().outer_size.height <= content.content_size.height
        assert not content.show_vertical_scrollbar

    for size in ((120, 30), (180, 45), (200, 60)):
        _drive_transactions(size, checks)


def test_the_ledger_window_fits_the_terminal_and_floors_at_five(monkeypatch):
    """The window is the screenful (a 30-line terminal fits 15 rows: chrome 13,
    the legend 2), capped at ENGINE_PAGE_CAP and floored at 5 — and it
    sizes only what is drawn, never a read: every open asks for
    `GROW_STEP`."""
    _rows, reads, _counts = _patch_transactions(monkeypatch)

    def sized(expected: int):
        async def checks(pilot, screen):
            assert screen.measure_list_rows() == expected
            assert _ledger(screen)._page_size == expected
            assert reads[-1]["limit"] == GROW_STEP

        return checks

    _drive_transactions((120, 30), sized(15))
    _drive_transactions((120, 14), sized(5))
    _drive_transactions((120, 300), sized(ENGINE_PAGE_CAP))


# ---- the shared base --------------------------------------------------------
def test_both_list_widgets_page_on_the_same_arithmetic():
    """`CursorList` and `CheckList` render nothing alike, but they window, page
    and count identically — one implementation, so they cannot drift."""
    assert issubclass(CursorList, WindowedList) and issubclass(CheckList, WindowedList)
    lst, chk = _list(45), _checklist(45)
    for widget in (lst, chk):
        assert widget._window_start == 0
        widget._cursor = 27
        start, window = widget._window()
        assert start == 20 and len(window) == 20
    assert lst.page_status == "rows 21-40 of 45 · page 2 of 3"
    assert chk.page_status == "rows 21-40 of 45 · page 2 of 3"


def test_a_move_that_goes_nowhere_does_not_repaint():
    """Neither `CheckList.action_move` nor `CursorList` repaints on a keypress
    that is already at an edge."""
    for widget in (_list(5), _checklist(5)):
        painted: list[int] = []
        widget._refresh = lambda sink=painted: sink.append(1)
        widget.post_message = lambda m: True
        widget.action_move(-1)  # already at the top
        assert painted == []
        widget.action_move(1)
        assert painted == [1] and widget._cursor == 1


def test_the_checklist_cursor_uses_the_documented_style():
    """It drew itself with a bare `"reverse"` literal, so the constant that
    carries the reason had exactly one consumer."""
    import expense.tui.widgets.checklist as mod

    assert mod.CURSOR_STYLE is CURSOR_STYLE
    # and it is actually applied: the cursor row renders differently from its
    # neighbour, which a dropped style would not.
    chk = _checklist(3)
    painted = render_text(chk._build(), width=60, ansi=True)
    lines = [ln for ln in painted.splitlines() if "txn 0" in ln]
    assert lines and "\x1b[7m" in lines[0] and "\x1b[7m" not in lines[1]


# ---- the shared measurement -------------------------------------------------
class _Measured(AdaptiveRowsMixin):
    """A screen with a known viewport height and nothing else."""

    def __init__(self, height: int) -> None:
        self._height = height

    def query_one(self, _selector):
        size = type("Size", (), {"height": self._height})()
        return type("Container", (), {"content_size": size})()


def test_fit_rows_clamps_to_the_screen_class_limits_not_hardcoded_ones():
    """The reconciliation screens each re-derived this measurement with a bare
    `5` and a hardcoded 20, so raising `PAGE_ROWS_CAP` on a screen would have
    left them at 20 without saying so."""
    wide = _Measured(200)
    assert wide.fit_rows(chrome=6) == DEFAULT_PAGE_ROWS

    class Taller(_Measured):
        PAGE_ROWS_CAP = 50

    assert Taller(200).fit_rows(chrome=6) == 50
    assert Taller(200).fit_rows(chrome=6, lines_per_row=2) == 50

    class Deeper(_Measured):
        PAGE_ROWS_FLOOR = 2

    assert Deeper(8).fit_rows(chrome=6, lines_per_row=2) == 2


def test_fit_rows_falls_back_to_the_default_before_layout():
    assert _Measured(0).fit_rows(chrome=6) == DEFAULT_PAGE_ROWS


def test_fit_rows_counts_two_line_rows_and_split_panes():
    """The two callers that hand-roll their own chrome: a pane sharing #content
    with a sibling, and the checklist in #rlist, one line per row.

    The browse's two panes are not the same size — the batches pane keeps a
    caption naming the account, the accounts pane does not. The checklist
    counts the two blank edge lines the table draws; leaving them out asks for
    a row that does not fit, and #rlist, which is `overflow: hidden`, clips it
    in silence.

    Mirrors `ReconciliationsScreen.pane_rows` and `_checklist_items`. If those
    change, this is where the new arithmetic gets re-stated.
    """
    frame, caption = AdaptiveRowsMixin.LIST_FRAME_LINES, AdaptiveRowsMixin.CAPTION_LINES
    assert _Measured(40).fit_rows(chrome=2 + 2 * frame + caption, lines_per_row=2) == 12
    assert _Measured(20).fit_rows("#rlist", chrome=frame) == 14


# ---- the frame ---------------------------------------------------------------
def _frame_lines(widget, *, width: int = 60) -> int:
    """Physical lines `framed()` draws, counting the trailing one."""
    return render_text(widget.framed(), width=width).count("\n")


def test_the_frame_costs_exactly_list_frame_lines():
    """`LIST_FRAME_LINES` is derived from what is drawn, not from its comment.

    A constant that disagrees with the widgets makes every fitted list overflow
    its container — and because the containers clip in silence, nothing fails.
    So the number is measured off the render.

    `framed()` takes no app and no layout, which is the whole reason it is a
    named method rather than an expression inside `_refresh`.
    """
    frame = AdaptiveRowsMixin.LIST_FRAME_LINES
    assert _frame_lines(_list(3, page_size=10)) - 3 == frame
    assert _frame_lines(_checklist(3, page_size=10)) - 3 == frame

    captioned = _list(3, page_size=10, caption="BCP PEN · by statement start date")
    assert _frame_lines(captioned) - 3 == frame + AdaptiveRowsMixin.CAPTION_LINES


def test_the_frame_height_does_not_depend_on_the_page_status():
    """The status line is reserved even when there is nothing to say.

    `page_status` is None on a single page. If the line came and went, a
    widget's height would depend on how many rows it holds — and height is
    exactly what `AdaptiveRowsMixin` measures to decide how many rows to ask
    for. That circularity is what makes the reserved blank line load-bearing
    rather than tidy.
    """
    one_page = _list(3, page_size=10)
    many_pages = _list(30, page_size=3)
    assert one_page.page_status is None
    assert many_pages.page_status is not None
    assert _frame_lines(one_page) - 3 == _frame_lines(many_pages) - 3


def test_the_frame_draws_no_colour():
    """The rule, caption and status carry weight only — never a colour.

    `test_no_literal_color_styles_in_tui` greps source, so it cannot see a
    *library* default: a bare `rich.rule.Rule()` styles itself `rule.line`,
    which resolves to bright green (SGR 92) and would paint a green line
    across every list in the app. The frame must pass an explicit style, and
    only a render can prove it did.
    """
    painted = render_text(_list(30, page_size=3, caption="BCP PEN").framed(), width=50, ansi=True)
    colour = re.compile(r"\x1b\[(?:[0-9;]*;)?(3[0-7]|9[0-7]|4[0-7]|10[0-7])(?:;[0-9;]*)?m")
    offenders = [ln for ln in painted.splitlines() if colour.search(ln)]
    assert not offenders, f"the frame painted a colour: {offenders}"


def test_the_reconciliation_checklist_fits_its_container(fake_client, monkeypatch):
    """The detail screen's checklist never overflows #rlist.

    This is the one that had been failing silently. `_checklist_items` counted
    its chrome by hand as 4 — the border plus the column header and its rule —
    and omitted the two blank edge lines the table draws, so it asked for one
    item too many at every height below the cap. #rlist is `overflow: hidden`,
    so there was no scrollbar and no clipped border to notice: the page status
    simply never appeared on that screen.

    Asserted against the container rather than against a number, so it stays
    true if the frame changes shape again.
    """
    from expense.tui.screens.reconciliations import ReconciliationDetailScreen

    record = {
        "id": "r1",
        "account_id": "acc1",
        "name": "August 2026",
        "status": 1,
        "date_start": "2026-07-24",
        "date_end": "2026-08-25",
        "beginning_balance_cents": 1248000,
        "ending_balance_cents": 921540,
        "difference_cents": -1250,
    }
    lines = [
        bank_line_row(
            f"l{i}",
            [import_part(f"t{i}", -100 * i - 1, line=f"l{i}", day=f"2026-08-0{i % 9 + 1}")],
            net_cents=-100 * i - 1,
        )
        for i in range(40)
    ]
    monkeypatch.setattr(
        "expense.reads.fetch_bank_lines",
        lambda cfg, **k: cursor_page([] if k.get("reconciliation") else lines),
    )
    monkeypatch.setattr("expense.tui.screens.reconciliations.load_account_name_map", dict)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(record))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._list is not None, message="no checklist")
        await wait_for(
            pilot,
            lambda: screen.query_one("#rlist").content_size.height > 0,
            message="#rlist was never laid out",
        )
        rlist = screen.query_one("#rlist")
        assert screen._list.outer_size.height <= rlist.content_size.height

    for size in ((120, 30), (120, 40), (180, 50)):
        run_app(scenario, size=size)


def test_the_batch_caption_repaints_when_the_account_changes():
    """A caption is content, and content does not repaint itself.

    The border title did: assigning it was enough. The Reconciliations browse
    rewrites its lower caption every time the account cursor moves, so it has
    to go through `set_caption`, which repaints. Asserted on the rendered text
    rather than on the attribute — the attribute was never the bug.
    """
    lst = CursorList(["Title", "Amount"], _rows(3), caption="BCP PEN · by statement start date")
    painted: list[str] = []
    lst.update = lambda renderable: painted.append(render_text(renderable, width=60))

    lst.set_caption("BCP USD · by statement start date")
    assert painted, "set_caption did not repaint"
    assert "BCP USD" in painted[-1]

    before = len(painted)
    lst.set_caption("BCP USD · by statement start date")  # unchanged
    assert len(painted) == before, "an unchanged caption repainted anyway"
