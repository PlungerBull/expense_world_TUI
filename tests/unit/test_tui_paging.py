"""Pagination — widget window/indicator/keys + the shared helpers.

Pages are min(PAGE_ROWS_CAP, what fits the terminal) since 2026-07-13 (adaptive
rows, pick A): the tier-E wire tests at the bottom pin `run_test(size=…)` so the
expected rows-per-page is deterministic — a 30-line harness proves the shrink, a
tiny one proves the floor. The cap is `DEFAULT_PAGE_ROWS` (20) app-wide but
`ENGINE_PAGE_CAP` on Transactions, which grows with the window (2026-08-29).

Mostly pure tests in the style of the other widget suites: `_build()` renders
through a Rich Console; action handlers run with `_refresh`/`post_message`
stubbed so no event loop is needed.
"""

import re

from textual.containers import VerticalScroll

from expense.commands._resource import DEFAULT_PAGE_ROWS, ENGINE_PAGE_CAP, effective_limit, items_of
from expense.tui.screens._base import AdaptiveRowsMixin, PagedListMixin
from expense.tui.widgets.checklist import CheckList
from expense.tui.widgets.cursor_list import CursorList, page_indicator
from expense.tui.widgets.windowed import CURSOR_STYLE, WindowedList
from tests.unit.helpers import page, render_text, run_app, wait_for, wait_for_list, whole


def _text(renderable) -> str:
    return render_text(renderable, width=120)


def _rows(n: int) -> list[tuple]:
    return [(f"id{i}", (f"row {i:02d}", f"{i}.00")) for i in range(n)]


def _list(n: int = 45, **kwargs) -> CursorList:
    lst = CursorList(["Title", "Amount"], _rows(n), align_right={1}, **kwargs)
    lst._refresh = lambda: None  # pure: no event loop, no live repaint
    return lst


# ---- page_indicator / effective_limit (shared helpers) ---------------------


def test_page_indicator_none_when_single_page():
    assert page_indicator(0, 5, 5, 20) is None
    assert page_indicator(0, 20, 20, 20) is None
    assert page_indicator(0, 0, 0, 20) is None


def test_page_indicator_counts_rows_and_pages():
    assert page_indicator(0, 20, 133, 20) == "rows 1-20 of 133 · page 1 of 7"
    assert page_indicator(20, 20, 133, 20) == "rows 21-40 of 133 · page 2 of 7"
    assert page_indicator(120, 13, 133, 20) == "rows 121-133 of 133 · page 7 of 7"
    assert page_indicator(20, 5, 25, 20, unit="items") == "items 21-25 of 25 · page 2 of 2"


def test_effective_limit_human_default_json_untouched():
    assert effective_limit(None, json_mode=False) == DEFAULT_PAGE_ROWS
    assert effective_limit(None, json_mode=True) is None  # --json: raw request
    assert effective_limit(5, json_mode=False) == 5  # explicit --limit wins
    assert effective_limit(5, json_mode=True) == 5


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
    """Terminal resize (adaptive rows, 2026-07-13): the window re-slices to the
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


# ---- CursorList fetched-page mode (page_meta, tier E) ------------------------


def test_fetched_page_posts_page_requested():
    lst = _list(20, page_meta=(0, 133))
    captured = []
    lst.post_message = captured.append
    lst.action_page(1)
    assert len(captured) == 1 and isinstance(captured[0], CursorList.PageRequested)
    assert captured[0].delta == 1 and captured[0].control is lst


def test_fetched_page_move_clamps_at_edge():
    # pick A (2026-07-11): j at the bottom row never turns the page itself.
    lst = _list(20, page_meta=(0, 133))
    captured = []
    lst.post_message = captured.append
    lst.set_cursor(19)
    lst.action_move(1)
    assert lst._cursor == 19
    assert not any(isinstance(m, CursorList.PageRequested) for m in captured)


def test_fetched_page_status_uses_global_offset():
    lst = _list(20, page_meta=(20, 133))
    assert lst.page_status == "rows 21-40 of 133 · page 2 of 7"


def test_fetched_page_single_page_hides_keys():
    lst = _list(15, page_meta=(0, 15))
    assert lst.page_status is None
    assert lst.check_action("page", ()) is False


# ---- CheckList (always window mode; rows are two physical lines) ------------


def _chk_rows(n: int) -> list[tuple]:
    return [(f"t{i}", f"txn {i:02d}", -1000 - i, "2026-07-01", "cat · #tag") for i in range(n)]


def _checklist(n: int = 25, **kwargs) -> CheckList:
    chk = CheckList(_chk_rows(n), **kwargs)
    chk._refresh = lambda: None
    return chk


def test_checklist_windows_items_not_lines():
    out = _text(_checklist(25)._build())
    assert "txn 00" in out and "txn 19" in out
    assert "txn 20" not in out  # 20 ITEMS per page (40 lines), picked 2026-07-11


def test_checklist_page_status_counts_items():
    chk = _checklist(25)
    assert chk.page_status == "items 1-20 of 25 · page 1 of 2"
    chk._cursor = 20
    assert chk.page_status == "items 21-25 of 25 · page 2 of 2"


def test_checklist_checked_state_survives_paging():
    chk = _checklist(25, checked=["t3", "t22"])
    chk.post_message = lambda m: True
    chk.action_page(1)  # display window moves; membership must not
    assert chk.checked == {"t3", "t22"}
    out = _text(chk._build())
    assert "txn 22" in out and "[x]" in out


def test_checklist_toggle_on_page_two_targets_the_right_key():
    chk = _checklist(25)
    captured = []
    chk.post_message = captured.append
    chk.action_page(1)
    chk.action_toggle()
    assert chk.checked == {"t20"}
    toggles = [m for m in captured if isinstance(m, CheckList.Toggled)]
    assert len(toggles) == 1 and toggles[0].key == "t20" and toggles[0].checked


def test_checklist_single_page_hides_page_keys():
    assert _checklist(8).check_action("page", ()) is False
    assert _checklist(25).check_action("page", ()) is True


def test_checklist_set_page_size_keeps_checks():
    """Resize re-slices the window; membership is a key-set over the whole
    batch, so checks survive (adaptive rows, 2026-07-13)."""
    chk = _checklist(25, checked=["t3", "t22"])
    chk.set_page_size(6)
    out = _text(chk._build())
    assert "txn 05" in out and "txn 06" not in out
    assert chk.checked == {"t3", "t22"}
    assert chk.page_status == "items 1-6 of 25 · page 1 of 5"


# ---- manage-list fetch: one read, the whole list -----------------------------


def _whole_fetch(n: int, prefix: str, calls: list):
    """A fake that behaves like the 2026-09-23 engine: every row, and a 422
    for paging it no longer has."""

    def fake_fetch(cfg, **kw):
        assert "limit" not in kw and "offset" not in kw, "the engine refuses paging"
        calls.append(kw)
        return whole([{"id": f"{prefix}{i}"} for i in range(n)])

    return fake_fetch


def test_categories_manage_reads_the_whole_list_once(monkeypatch):
    """The manage screens window locally over the full set; the engine
    returns it whole, so one read holds every row."""
    calls: list = []
    monkeypatch.setattr(
        "expense.commands.categories_cmd.fetch_categories", _whole_fetch(150, "c", calls)
    )
    from expense.tui.screens.categories import CategoriesScreen

    assert len(items_of(CategoriesScreen().fetch_items(None))) == 150
    assert len(calls) == 1


def test_hashtags_manage_reads_the_whole_list_once(monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        "expense.commands.hashtags_cmd.fetch_hashtags", _whole_fetch(130, "h", calls)
    )
    from expense.tui.screens.hashtags import HashtagsScreen

    assert len(items_of(HashtagsScreen().fetch_items(None))) == 130
    assert len(calls) == 1


# ---- PagedListMixin (tier-E screen plumbing) ---------------------------------


class _FakeScreen(PagedListMixin):
    def __init__(self, total=None):
        self.loads = 0
        self._page_total = total

    def _load(self):
        self.loads += 1


class _Evt:
    def __init__(self, delta):
        self.delta = delta
        self.stopped = False

    def stop(self):
        self.stopped = True


def test_mixin_fetch_kwargs_and_page_turn():
    scr = _FakeScreen(total=133)
    assert scr.page_fetch_kwargs() == {"limit": DEFAULT_PAGE_ROWS, "offset": 0}
    evt = _Evt(1)
    scr.on_cursor_list_page_requested(evt)
    assert evt.stopped and scr._page == 1 and scr.loads == 1
    assert scr.page_fetch_kwargs() == {"limit": DEFAULT_PAGE_ROWS, "offset": 20}


def test_mixin_clamps_below_zero_and_past_total():
    scr = _FakeScreen(total=15)  # one page only
    scr.on_cursor_list_page_requested(_Evt(-1))
    scr.on_cursor_list_page_requested(_Evt(1))
    assert scr._page == 0 and scr.loads == 0


def test_mixin_reset_page_for_filter_changes():
    scr = _FakeScreen(total=133)
    scr.on_cursor_list_page_requested(_Evt(1))
    scr.reset_page()
    assert scr._page == 0


def test_mixin_resize_refetches_and_reanchors():
    """Terminal shrank 19→13 rows: refetch with the new limit, the offset
    re-anchored so the old first visible row stays on the new page (pick A,
    2026-07-13). An unchanged size must not refetch."""
    scr = _FakeScreen(total=133)
    scr._page_rows = 19
    scr._page = 2  # first visible row 38
    scr.measure_list_rows = lambda: 13
    scr._viewport_resized()
    assert scr._page_rows == 13 and scr.loads == 1
    assert scr.page_offset <= 38 < scr.page_offset + 13
    scr._viewport_resized()  # same measure → no spurious refetch
    assert scr.loads == 1


def test_fetch_page_body_snaps_back_when_page_vanishes():
    """Rows shrank under us (e.g. a delete emptied the last page): the mixin
    snaps to the last real page and refetches once."""
    scr = _FakeScreen()
    scr._page = 2  # offset 40, but only 21 rows exist now
    fetched = []

    def fetch(pkw):
        fetched.append(dict(pkw))
        offset = pkw["offset"]
        items = [{"id": i} for i in range(offset, min(offset + 20, 21))]
        return page(items, total=21, limit=pkw["limit"], offset=offset)

    body = scr.fetch_page_body(fetch)
    assert scr._page == 1 and scr._page_total == 21
    assert fetched == [{"limit": 20, "offset": 40}, {"limit": 20, "offset": 20}]
    assert [it["id"] for it in body["items"]] == [20]


# ---- tier-E screens: real limit/offset on the wire ---------------------------


def _patch_transactions(monkeypatch) -> list:
    """133 fake transactions behind fetch_transactions; returns the calls log."""
    import expense.tui.screens.transactions as tx_mod

    calls = []

    def fake_fetch(cfg, *, limit=None, offset=None, **kw):
        calls.append((limit, offset))
        items = [
            {"id": f"t{i}", "title": f"Txn {i}", "amount_cents": -100 - i, "date": "2026-07-01"}
            for i in range(offset, min(offset + limit, 133))
        ]
        return page(items, total=133, limit=limit, offset=offset)

    monkeypatch.setattr("expense.commands.transactions_cmd.fetch_transactions", fake_fetch)
    monkeypatch.setattr(tx_mod, "load_account_name_map", lambda: {})
    monkeypatch.setattr(tx_mod, "load_category_name_map", lambda: {})
    monkeypatch.setattr(tx_mod, "load_hashtag_name_map", lambda: {})
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    return calls


def _drive_transactions(size: tuple[int, int], calls: list, checks) -> None:
    """Push a TransactionsScreen in a `size` harness and run `checks(pilot, screen)`."""

    async def scenario(pilot, app):
        from expense.tui.screens.transactions import TransactionsScreen

        screen = TransactionsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await checks(pilot, screen)

    run_app(scenario, size=size)


def test_transactions_screen_pages_on_the_wire(monkeypatch):
    """A tall terminal keeps growing (2026-08-29: Transactions lifted the
    20 cap to the engine's own): 35 lines fit 20 rows, so it loads with
    limit=20&offset=0 and pgdn refetches offset=20 (picks A+B, 2026-07-11).
    (22 until 2026-09-12 — the pendiente filter legend under the list takes
    two lines now, as the Inbox's did.)"""
    calls = _patch_transactions(monkeypatch)

    async def checks(pilot, screen):
        assert calls == [(20, 0)]
        assert screen.query(CursorList).first().page_status == "rows 1-20 of 133 · page 1 of 7"
        await pilot.press("pagedown")
        await wait_for(
            pilot,
            lambda: (
                screen.query(CursorList)
                and screen.query(CursorList).first().page_status
                == "rows 21-40 of 133 · page 2 of 7"
            ),
        )
        assert calls[-1] == (20, 20)

    # content 28 lines − 6 frame lines − 2 legend lines → 20 rows fit.
    # "Frame" means the rule, the table and the status line since 2026-09-20;
    # it meant the border and the table before. The count is the same 6, which
    # is why this number did not move — see LIST_FRAME_LINES.
    _drive_transactions((120, 35), calls, checks)


def test_transactions_panel_fills_and_fits_the_viewport(monkeypatch):
    """The ledger takes the window it is given and no more (2026-08-29): the
    card spans #content's full width, and the panel's own height never exceeds
    it — a clipped bottom border and the undraggable scrollbar are what an
    overshooting LIST_FRAME_LINES looked like."""
    calls = _patch_transactions(monkeypatch)

    async def checks(pilot, screen):
        content = screen.query_one("#content", VerticalScroll)
        # `list_ready` only proves the list mounted and the loader went away — it
        # says nothing about a layout pass having run, so every `.size` below can
        # still be 0. Locally the layout has always landed by this point; on CI it
        # had not, and this asserted `0 == 116` (2026-08-29, surfaced when a file
        # rename changed collection order and with it the preceding workload).
        await wait_for(
            pilot,
            lambda: screen.query_one("#card").size.width > 0,
            message="the card was never laid out",
        )
        assert screen.query_one("#card").size.width == content.content_size.width
        assert screen.query(CursorList).first().outer_size.height <= content.content_size.height
        assert not content.show_vertical_scrollbar

    for size in ((120, 30), (180, 45), (200, 60)):
        _drive_transactions(size, calls, checks)


def test_transactions_page_stops_at_the_engine_cap(monkeypatch):
    """The ledger grows with the window, but never past `limit`'s ceiling:
    a 300-line terminal still asks for ENGINE_PAGE_CAP rows (2026-08-29)."""
    calls = _patch_transactions(monkeypatch)

    async def checks(pilot, screen):
        assert screen.page_rows == ENGINE_PAGE_CAP
        assert calls == [(ENGINE_PAGE_CAP, 0)]

    _drive_transactions((120, 300), calls, checks)


def test_transactions_screen_adapts_rows_to_short_terminal(monkeypatch):
    """A 30-line terminal fits 15 rows (chrome takes 13, the filter legend 2):
    the page IS the screenful — limit=15 on the wire, 15-row pages in the
    indicator (pick A, 2026-07-13). This is the 2026-07-12 clipped-panel
    screenshot, fixed — and since 2026-08-29 the frame count is honest, so
    the panel really does fit. (17 until the legend arrived, 2026-09-12.)"""
    calls = _patch_transactions(monkeypatch)

    async def checks(pilot, screen):
        assert calls == [(15, 0)]
        assert screen.page_rows == 15
        assert screen.query(CursorList).first().page_status == "rows 1-15 of 133 · page 1 of 9"
        await pilot.press("pagedown")
        await wait_for(
            pilot,
            lambda: (
                screen.query(CursorList)
                and screen.query(CursorList).first().page_status
                == "rows 16-30 of 133 · page 2 of 9"
            ),
        )
        assert calls[-1] == (15, 15)

    _drive_transactions((120, 30), calls, checks)


def test_transactions_screen_floors_at_five_rows(monkeypatch):
    """Below a ~16-line terminal the fit goes under 5; the floor holds (the
    panel clips there — pre-2026-07-13 behavior, terminal was never usable)."""
    calls = _patch_transactions(monkeypatch)

    async def checks(pilot, screen):
        assert calls == [(5, 0)]

    _drive_transactions((120, 14), calls, checks)


# ---- the shared base --------------------------------------------------------
def test_both_list_widgets_page_on_the_same_arithmetic():
    """`CursorList` and `CheckList` render nothing alike, but they window, page
    and count identically — one implementation since the two copies drifted."""
    assert issubclass(CursorList, WindowedList) and issubclass(CheckList, WindowedList)
    lst, chk = _list(45), _checklist(45)
    for widget in (lst, chk):
        assert widget._window_start == 0
        widget._cursor = 27
        start, window = widget._window()
        assert start == 20 and len(window) == 20
    assert lst.page_status == "rows 21-40 of 45 · page 2 of 3"
    assert chk.page_status == "items 21-40 of 45 · page 2 of 3"


def test_a_move_that_goes_nowhere_does_not_repaint():
    """`CheckList.action_move` used to repaint on every keypress, including the
    ones already at an edge; `CursorList` did not. They agree now."""
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
    with a sibling, and a checklist whose items are two physical lines each.

    Both numbers moved on 2026-09-20 and for different reasons. The browse
    gained a line because its two panes stopped being the same size — the
    batches pane keeps a caption naming the account, the accounts pane does
    not. The checklist lost one because its `4` was simply **wrong**: it
    omitted the two blank edge lines the table draws, so it asked for an item
    that did not fit and #rlist, which is `overflow: hidden`, clipped it in
    silence.

    Mirrors `ReconciliationsScreen.pane_rows` and `_checklist_items`. If those
    change, this is where the new arithmetic gets re-stated.
    """
    frame, caption = AdaptiveRowsMixin.LIST_FRAME_LINES, AdaptiveRowsMixin.CAPTION_LINES
    assert _Measured(40).fit_rows(chrome=2 + 2 * frame + caption, lines_per_row=2) == 12
    assert _Measured(40).fit_rows("#rlist", chrome=frame, lines_per_row=2) == 17


# ---- the frame the border became (2026-09-20) -------------------------------
def _frame_lines(widget, *, width: int = 60) -> int:
    """Physical lines `framed()` draws, counting the trailing one."""
    return render_text(widget.framed(), width=width).count("\n")


def test_the_frame_costs_exactly_list_frame_lines():
    """`LIST_FRAME_LINES` is derived from what is drawn, not from its comment.

    This is the test the 2026-08-29 miscount needed and did not have. That
    constant read 4 while the widgets drew 6, so every fitted list overflowed
    its container by two lines — and because the containers clip in silence,
    nothing failed. A comment cannot be wrong here any more: the number is
    measured off the render.

    `framed()` takes no app and no layout, which is the whole reason it is a
    named method rather than an expression inside `_refresh`.
    """
    frame = AdaptiveRowsMixin.LIST_FRAME_LINES
    assert _frame_lines(_list(3, page_size=10)) - 3 == frame
    assert _frame_lines(_checklist(3, page_size=10)) - 3 * 2 == frame

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
        "date_start": "2026-07-24T00:00:00Z",
        "date_end": "2026-08-25T00:00:00Z",
        "beginning_balance_cents": 1248000,
        "ending_balance_cents": 921540,
        "difference_cents": -1250,
    }
    txns = [
        {
            "id": f"t{i}",
            "title": f"row {i}",
            "amount_cents": -100 * i,
            "date": f"2026-08-0{i % 9 + 1}T00:00:00Z",
            "reconciliation_id": None,
            "hashtag_ids": [],
        }
        for i in range(40)
    ]
    monkeypatch.setattr(
        "expense.commands.transactions_cmd.fetch_transactions",
        lambda cfg, **k: page(txns, total=len(txns)),
    )
    for name in ("account", "category", "hashtag"):
        monkeypatch.setattr(f"expense.tui.screens.reconciliations.load_{name}_name_map", dict)

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
