"""SectionScreen — the shared base for every data-backed section screen.

Owns the breadcrumb header, the bounded content card, the worker-backed fetch
(so the UI never blocks), and loading/error states. Subclasses supply only:

    crumb  : tuple[str, ...]          # breadcrumb trail after EXPENSE WORLD
    fetch()                           # runs in a worker thread, returns data
    build(data) -> list[Widget]       # the widgets to show inside the card

`r` refreshes; `escape` pops back to the menu.
"""

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from rich.console import Group
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Footer, LoadingIndicator, Static
from textual.worker import get_current_worker

from expense.commands._resource import DEFAULT_PAGE_ROWS, ENGINE_PAGE_CAP, items_of
from expense.errors import format_error
from expense.tui.screens.help import HelpBindingMixin
from expense.tui.widgets.header import Breadcrumb


def screen_fetch_kwargs(app) -> dict:
    """The standard TUI read kwargs: verbosity off the app."""
    return dict(verbose=app._verbose)


@dataclass
class _QueuedWrite:
    method: str
    path: str
    json_body: dict | None
    success: str
    on_success: Callable[[], None] | None
    on_error: Callable[[str], None] | None
    on_response: Callable[[dict], None] | None = None


class EngineWriteMixin:
    """Engine writes off the UI thread — one at a time, in order, per screen.

    Shared by SectionScreen and the bar-cycle form screens (which subclass
    plain Screen). `run_write` appends to a per-screen FIFO and exactly one
    request is in flight at any moment: thread workers cancel cooperatively,
    so `exclusive=True` alone never serialized overlapping writes
    (backlog 6.4b). Success/error callbacks land on the UI thread; without
    callbacks, errors notify a "Failed" toast and success runs `_after_write`.
    Idempotency + error envelope come from the client. The `engine-write`
    worker group keeps loads/theme changes from ever cancelling a write.

    A failed write **drops the queued remainder** — those intents were decided
    against a screen state the engine just contradicted; the error callback
    typically resyncs. Why, with the rejected alternatives: docs/decisions.md
    "TUI writes: FIFO queue in EngineWriteMixin, error drops the queue".
    """

    _write_queue: deque[_QueuedWrite] | None = None  # lazily created; UI-thread only
    _write_inflight: bool = False

    def run_write(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        success: str = "Done.",
        on_success: Callable[[], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_response: Callable[[dict], None] | None = None,
    ) -> None:
        """Queue one engine write. `on_response` receives the engine's own body
        (before `on_success`) for the one caller that needs it: a `complete`
        carries a `warnings` envelope nothing else can reconstruct. Opt-in, so
        the callbackless callsites are untouched — decisions.md "The TUI sees
        the response body only where it asks for it"."""
        if self._write_queue is None:
            self._write_queue = deque()
        self._write_queue.append(
            _QueuedWrite(method, path, json_body, success, on_success, on_error, on_response)
        )
        self._pump_writes()

    def _pump_writes(self) -> None:
        if self._write_inflight or not self._write_queue:
            return
        self._write_inflight = True
        self._execute_write(self._write_queue.popleft())

    @work(thread=True, group="engine-write")
    def _execute_write(self, item: _QueuedWrite) -> None:
        # Imports stay function-local: the test fixtures patch these module
        # attributes, and only a lazy lookup sees the patch.
        from expense import config as config_module
        from expense.http import ExpenseClient

        error: str | None = None
        body: dict | None = None
        try:
            cfg = config_module.ensure_loaded()
            with ExpenseClient(cfg, verbose=self.app._verbose) as client:
                if item.method == "POST":
                    body = client.post(item.path, json_body=item.json_body)
                elif item.method == "PUT":
                    body = client.put(item.path, json_body=item.json_body)
                elif item.method == "DELETE":
                    body = client.delete(item.path)
                else:
                    raise ValueError(f"unsupported write method: {item.method}")
        except Exception as exc:
            error = format_error(exc)
        self.app.call_from_thread(self._write_finished, item, error, body)

    def _write_finished(
        self, item: _QueuedWrite, error: str | None, body: dict | None = None
    ) -> None:
        # UI thread: report the outcome, then pump the next write.
        self._write_inflight = False
        if error is not None:
            if self._write_queue:
                self._write_queue.clear()
            if item.on_error is not None:
                item.on_error(error)
            else:
                self.notify(error, title="Failed", severity="error")
        else:
            # Before on_success: a screen that reads the body typically repaints
            # in on_success, and the repaint has to see what the body said.
            if item.on_response is not None and isinstance(body, dict):
                item.on_response(body)
            if item.on_success is not None:
                item.on_success()
            else:
                self._after_write(item.success)
        if self._write_queue:
            self._pump_writes()

    def _after_write(self, message: str) -> None:
        self.notify(message)


class ContentSwapLockMixin:
    """Serializes every remove/mount pair on a screen's content container.

    Two repaints can land near-simultaneously (e.g. a manual refresh while a
    write's post-refresh reload is in flight); each swap suspends between
    remove and mount, and interleaved swaps would mount duplicate content
    (DuplicateIds on SectionScreen's '#card', stacked checklists on the
    reconciliation detail screen).
    """

    _swap_lock: asyncio.Lock | None = None

    def _content_lock(self) -> asyncio.Lock:
        if self._swap_lock is None:  # lazily created; only ever touched on the UI thread
            self._swap_lock = asyncio.Lock()
        return self._swap_lock


class GrowingListMixin:
    """A SectionScreen whose one list grows by cursor (M3, 2026-09-25).

    Owner's shape, mockup expense-world-engine-uptake.html: the list opens with
    `GROW_STEP` rows, `pgdn` appends the next `GROW_STEP` under them, and
    `↑`/`↓` scroll across everything loaded. The engine hands out "the rows
    after this one", never "row 41", so a list that only grows at its end is
    the shape that fits it. It replaced page-at-a-time offset paging
    (`PagedListMixin`, 2026-07-11 to 2026-09-26).

    The subclass contract: `fetch()` calls `read_rows(fetch_page, count)` and
    hands the cursor and count to `took_rows`; `build()` sizes the list with
    `measure_list_rows()` and calls `place_list(listing)`; `pgdn` arrives as
    `on_cursor_list_more_requested`, which calls `fetch_more(fetch_page)`, and
    the rows come back through the `append_loaded` hook.

    - **Rows and count load together** (owner, 2026-09-23): a count that cannot
      be read fails the screen, never leaves rows beside a guessed number.
      `pgdn` does not recount — the rows are new, the question is not.
    - **After a write the depth stays** (owner, 2026-09-26): `reload_in_place`
      re-reads as many rows as were loaded, 200 a request past the engine's
      cap, and puts the cursor back on the same row *number*. On a filtered
      list a row that left is gone, and the next one takes its place under the
      cursor.
    - `r` and a first open start again from `GROW_STEP`.
    - **A resize fetches nothing**: the window re-slices the rows in hand.
    """

    _next_cursor: str | None = None
    _total: int | None = None
    _keep: int = 0  # rows the next full read brings back (0 → GROW_STEP)
    _keep_cursor: int = 0  # the row number the cursor returns to after it
    _growing: bool = False  # a `pgdn` read is in flight

    def read_rows(
        self,
        fetch_page: Callable[[int, str | None], Any],
        count: Callable[[], int],
    ) -> tuple[list[dict], str | None, int]:
        """Worker thread: the first rows (as many as were loaded, at least
        `GROW_STEP`), then the count. Returns (items, next_cursor, total)."""
        from expense.tui.widgets.cursor_list import GROW_STEP

        want = max(GROW_STEP, self._keep)
        items: list[dict] = []
        after: str | None = None
        while True:
            body = fetch_page(min(want - len(items), ENGINE_PAGE_CAP), after)
            items.extend(items_of(body))
            after = body.get("next_cursor") if isinstance(body, dict) else None
            if after is None or len(items) >= want:
                break
        return items, after, count()

    def took_rows(self, next_cursor: str | None, total: int) -> None:
        self._next_cursor = next_cursor
        self._total = total

    def place_list(self, listing) -> None:
        """The freshly built list: growing, and the cursor back where it was."""
        listing.set_growth(more=self._next_cursor is not None)
        if self._keep_cursor:
            listing.set_cursor(self._keep_cursor)

    def reload_in_place(self) -> None:
        """Re-read after a write, keeping the depth and the cursor's row number."""
        from expense.tui.widgets.cursor_list import CursorList

        try:
            listing = self.query_one(CursorList)
        except Exception:
            listing = None  # loading / error state: nothing to keep
        if listing is not None:
            self._keep = listing.row_count
            self._keep_cursor = listing.cursor_index
        self._stop_growing()
        self._load()

    def _start_over(self) -> None:
        self._keep = self._keep_cursor = 0
        self._next_cursor = None
        self._stop_growing()

    def _stop_growing(self) -> None:
        """A full read is coming: a `pgdn` read still in flight would append
        onto the list that read replaces."""
        self.workers.cancel_group(self, "grow")
        self._growing = False

    def _start_load(self) -> None:
        self._start_over()
        super()._start_load()

    async def action_reload(self) -> None:
        self._start_over()
        await super().action_reload()

    def _viewport_resized(self) -> None:
        from expense.tui.widgets.cursor_list import CursorList

        try:
            listing = self.query_one(CursorList)
        except Exception:
            return  # loading / error state
        listing.set_page_size(self.measure_list_rows())

    def fetch_more(self, fetch_page: Callable[[int, str], Any]) -> None:
        """`pgdn`: the next `GROW_STEP` rows after the last cursor, appended.
        Nothing when the engine said there are no more, or a read is in flight."""
        if self._growing or not self._next_cursor:
            return
        self._growing = True
        self._read_more(fetch_page, self._next_cursor)

    @work(thread=True, exclusive=True, group="grow")
    def _read_more(self, fetch_page: Callable[[int, str], Any], after: str) -> None:
        from expense.tui.widgets.cursor_list import GROW_STEP

        worker = get_current_worker()
        try:
            body = fetch_page(GROW_STEP, after)
        except Exception as exc:
            if not worker.is_cancelled:
                self.app.call_from_thread(self._more_failed, format_error(exc))
            return
        if worker.is_cancelled:
            return
        self.app.call_from_thread(self._more_arrived, items_of(body), body.get("next_cursor"))

    def _more_failed(self, message: str) -> None:
        """The rows already loaded stay; only the next ones did not arrive."""
        self._growing = False
        self.notify(message, title="Failed", severity="error")

    def _more_arrived(self, items: list, next_cursor: str | None) -> None:
        self._growing = False
        self._next_cursor = next_cursor
        self.append_loaded(items, more=next_cursor is not None)

    def append_loaded(self, items: list, *, more: bool) -> None:
        """Hook: add `items` to the screen's rows and to its list (UI thread)."""
        raise NotImplementedError


class LogTransactionMixin:
    """Adds `+` — jump straight to the LOG bar.

    Logging is the thing you do most, so it is a key, not a menu row
    (2026-08-20). Bound on Home and Transactions — the screens where "and now
    write one down" is the obvious next thought.

    **It opens the LOG bar, not the bar-cycle form** (quick-add phase 4,
    2026-08-25): one typed line, a staged batch, one save. The form keeps its
    *edit* door — `⏎` on an existing row — and lost only its create door
    (docs/mockups/expense-world-two-doors.html). `+` still means one thing
    everywhere it is bound: it logs a posted transaction, and a line too
    sparse to post is refused by the grammar in place — never parked
    somewhere by which screen you happened to be standing on.

    **Plain `+`, no modifier, deliberately.** `shift++` was considered and is not
    bindable: for a printable key the shift is already baked into the character
    the terminal sends (on a US layout the main-row `+` *is* shift+`=`), so there
    is no modifier left to report — Textual says as much in `keys.py`
    (`key_to_character`: "Keys with modifiers don't come from printable keys").
    Plain `+` costs nothing anyway: the numpad key and the main-row key send the
    same byte, so one binding catches both, and none of the three screens has a
    text input for a stray `+` to land in.

    `key_display` is set because Textual renders the key name (`plus`) otherwise.

    Like `HelpBindingMixin`, the BINDINGS have to be splatted into each host —
    Textual does not merge BINDINGS from a plain mixin.
    """

    BINDINGS = [Binding("plus", "log_transaction", "Add", key_display="+")]

    def action_log_transaction(self) -> None:
        # imported here, not at module scope: log_bar imports EngineWriteMixin
        # from this module.
        from expense.tui.screens.log_bar import LogBarScreen

        self.app.push_screen(LogBarScreen(), self._after_log)

    def _after_log(self, _result=None) -> None:
        """Hook for hosts that must react once the form closes. Home refreshes
        its stat cluster on resume already; the list screens override this to
        reload, so a transaction you just wrote appears without pressing `r`."""


class AdaptiveRowsMixin:
    """How many rows a list may ask for, given the room it actually has.

    Adaptive rows (2026-07-13, mockups/expense-world-adaptive-rows.html, pick
    A + cap 20): the page IS the screenful, so every list measures its
    container before fetching and re-measures on a terminal resize.

    The measurement was written three times — here, and twice on the
    reconciliation screens, which each re-derived the try/except, the `avail
    <= 0` guard and the clamp while hardcoding `DEFAULT_PAGE_ROWS` and a bare
    `5` in place of the caps below. Nothing showed, because no screen that
    copied it also raises `PAGE_ROWS_CAP` — but Transactions does raise it, so
    the copies were one shared base class away from silently ignoring it.
    """

    # Lines a CursorList spends on chrome rather than rows. Still 6 after the
    # borders went (2026-09-20), and deliberately re-derived rather than left
    # alone — the terms all changed even though the total did not:
    #
    #     section rule            1   was the top border (it carried the title)
    #     blank edge              1   Rich's box.SIMPLE, inside what was the border
    #     column header           1
    #     header rule             1
    #     blank edge              1
    #     page-status line        1   was the bottom border (it carried the subtitle)
    #
    # It read 4 until 2026-08-29, which overshot by exactly those two blanks:
    # every list whose fitted size was below the 20 cap overflowed #content by
    # 2 lines, clipping its own bottom border and the `rows … · page …`
    # subtitle and growing the undraggable scrollbar the 2026-07-13 decision
    # meant to delete. Invisible while the cap hid it on tall terminals;
    # permanent once Transactions started filling the window. That is why this
    # number is now derived from the render by
    # `test_the_frame_costs_exactly_LIST_FRAME_LINES` instead of from a comment.
    LIST_FRAME_LINES = 6
    # One more line for a list that keeps a caption. Exactly one list does —
    # the Reconciliations batch pane — but the asymmetry is named here rather
    # than buried as a literal in that screen's arithmetic.
    CAPTION_LINES = 1
    # Lower bound on the page size we ASK for — not a clipping guard, despite what
    # this comment claimed until 2026-08-20. It cannot make the viewport show five
    # rows: below a ~18-line terminal the extra rows are fetched and then clipped
    # off the bottom, and the panel's own bottom border goes first (h=20). Measured
    # boundaries and the decision not to guard them: docs/decisions.md "A terminal
    # too small is the user's to fix", docs/tui.md §5.
    PAGE_ROWS_FLOOR = 5
    # Upper bound on the page size. DEFAULT_PAGE_ROWS (20) app-wide — pages stay
    # stable across window sizes and short lists keep a tidy card. Transactions
    # overrides it to grow with the terminal (2026-08-29); its cap is
    # the engine's own `limit` ceiling, so the fetch contract can't be broken by
    # a tall window. See docs/decisions.md "the ledger fills the window".
    PAGE_ROWS_CAP = DEFAULT_PAGE_ROWS

    def list_extra_lines(self) -> int:
        """Lines the screen renders around its list inside #content (legends…)."""
        return 0

    def fit_rows(
        self,
        container: str = "#content",
        *,
        chrome: int = 0,
        lines_per_row: int = 1,
    ) -> int:
        """Rows that fit `container`, clamped to this screen's limits.

        `chrome` is what the container spends on anything but rows (borders,
        headers, a legend); `lines_per_row` is how many physical lines one row
        costs — two for the reconciliation checklist, and two again for a pane
        that splits its room with a sibling. Pre-layout or unmeasurable → the
        20-row default, since a page size of 0 would fetch nothing.
        """
        try:
            avail = self.query_one(container).content_size.height
        except Exception:
            return DEFAULT_PAGE_ROWS
        if avail <= 0:
            return DEFAULT_PAGE_ROWS
        rows = (avail - chrome) // lines_per_row
        return max(self.PAGE_ROWS_FLOOR, min(self.PAGE_ROWS_CAP, rows))

    def measure_list_rows(self) -> int:
        """The standard case: one list filling #content."""
        return self.fit_rows(chrome=self.LIST_FRAME_LINES + self.list_extra_lines())


class SectionScreen(
    HelpBindingMixin,
    EngineWriteMixin,
    ContentSwapLockMixin,
    AdaptiveRowsMixin,
    Screen,
):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("r", "reload", "Refresh"),
        *HelpBindingMixin.BINDINGS,
    ]
    crumb: tuple[str, ...] = ()
    CARD_WIDTH: int | None = 64  # cap the content card; None = fill width
    _started: bool = False  # first load ran (it waits for the first layout pass)

    def compose(self) -> ComposeResult:
        yield Breadcrumb(self.crumb, id="crumb")
        yield VerticalScroll(LoadingIndicator(), id="content")
        yield Footer()

    def on_mount(self) -> None:
        # First load waits for the first layout pass: adaptive page sizing
        # (measure_list_rows) reads #content's height, which is 0 at mount.
        self.call_after_refresh(self._start_load)

    def _start_load(self) -> None:
        if self._started:
            return
        self._started = True
        self._load()

    def on_resize(self, _event) -> None:
        # The initial layout fires Resize too; adaptive re-windowing only makes
        # sense once the first load measured this same geometry.
        if self._started:
            self._viewport_resized()

    def _viewport_resized(self) -> None:
        """Hook — adaptive-list screens re-window when the terminal size changes."""

    async def action_reload(self) -> None:
        async with self._content_lock():
            content = self.query_one("#content", VerticalScroll)
            await content.remove_children()
            await content.mount(LoadingIndicator())
        self._load()

    # Own group: loads may cancel stale loads, but never a run_write worker.
    @work(thread=True, exclusive=True, group="section-load")
    def _load(self) -> None:
        # Cancellation is cooperative: a newer exclusive load only flags this
        # worker, so check before painting or a superseded load can clobber
        # (or race) the fresh one's content swap.
        worker = get_current_worker()
        try:
            data = self.fetch()
        except Exception as exc:  # surface engine/config errors in-app, don't crash
            if not worker.is_cancelled:
                self.app.call_from_thread(self._error, format_error(exc))
            return
        if worker.is_cancelled:
            return
        self.app.call_from_thread(self._show, data)

    async def _show(self, data: object) -> None:
        content = self.query_one("#content", VerticalScroll)
        async with self._content_lock():
            await content.remove_children()
            card = Vertical(*self.build(data), id="card")
            if self.CARD_WIDTH is not None:
                card.styles.max_width = self.CARD_WIDTH
            await content.mount(card)

    async def _error(self, message: str) -> None:
        content = self.query_one("#content", VerticalScroll)
        async with self._content_lock():
            await content.remove_children()
            banner = Group(Text("Could not load.", style="bold"), Text(message))
            await content.mount(Static(banner, classes="error"))

    # ---- shared write helpers (Phase 2) ----------------------------------
    def selected_record(self) -> dict | None:
        """The record under the list cursor (screens keep `_by_id`)."""
        from expense.tui.widgets.cursor_list import CursorList

        try:
            cursor_list = self.query_one(CursorList)
        except Exception:
            return None
        return getattr(self, "_by_id", {}).get(cursor_list.cursor_key)

    def _after_write(self, message: str) -> None:
        self.notify(message)
        self._load()  # re-fetch; content swaps are lock-serialized, no card clash

    # ---- subclass hooks --------------------------------------------------
    def fetch(self) -> object:
        """Fetch data in a worker thread. Raise to surface an in-app error."""
        raise NotImplementedError

    def build(self, data: object) -> list[Widget]:
        """Return the widgets to mount inside the card (runs on the UI thread)."""
        raise NotImplementedError


class ResourceListScreen(SectionScreen):
    """Scaffold for the simple manage lists (Accounts / Categories / Hashtags):
    quiet fetch → title + CursorList of rows (+ optional legend). `n` pushes
    the new-record form; `e` the prefilled edit form for the cursor row.
    `enter` is a no-op here. The `a` archive toggle lives on AccountsScreen
    only — the engine removed category/hashtag archive (2026-08-06 schema
    slimming); the no-confirm toggle decision (2026-07-11 in decisions.md)
    still governs it there.

    Subclasses set the class attrs and four hooks. Row builders stay pure
    module functions (they have direct unit tests).
    """

    TITLE: str = ""
    HEADERS: list[str] = []
    EMPTY: str = "(empty)"
    LEGEND: str | None = None
    ALIGN_RIGHT: set[int] = set()
    RESOURCE: str = ""  # engine collection, e.g. "accounts"
    BINDINGS = [
        ("n", "new", "New"),
        ("e", "edit", "Edit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict = {}
        self._restore_key: object | None = None  # cursor row to re-select after a reload
        self._toggle_busy = False  # one archive toggle at a time until the reload lands

    # ---- hooks ------------------------------------------------------------
    def fetch_items(self, cfg, **kw) -> object:
        """Call the shared fetch_* for this resource (worker thread)."""
        raise NotImplementedError

    def rows(self, items: list) -> list:
        """items → the pure row builder's (id, cells, style) rows."""
        raise NotImplementedError

    def edit_screen(self, item: dict):
        """The prefilled edit form for `e` on a row."""
        raise NotImplementedError

    def new_screen(self):
        """The create-form screen for `n`."""
        raise NotImplementedError

    # ---- binding availability ----------------------------------------------
    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action in ("edit", "archive") and self.selected_record() is None:
            return None  # empty list → nothing to act on
        return True

    def on_cursor_list_highlighted(self, event) -> None:
        self.refresh_bindings()  # re-check e/a for the row the cursor just landed on

    # ---- adaptive window (2026-07-13) --------------------------------------
    def list_extra_lines(self) -> int:
        return 2 if self.LEGEND else 0  # legend Static: margin-top 1 + one text line

    def _viewport_resized(self) -> None:
        from expense.tui.widgets.cursor_list import CursorList

        try:
            cursor_list = self.query_one(CursorList)
        except Exception:
            return  # not built yet (loading/error state)
        cursor_list.set_page_size(self.measure_list_rows())

    # ---- scaffold ----------------------------------------------------------
    def fetch(self) -> list:
        from expense import config as config_module
        from expense.commands._resource import items_of

        cfg = config_module.ensure_loaded()
        return items_of(self.fetch_items(cfg, **screen_fetch_kwargs(self.app)))

    def build(self, items: list) -> list[Widget]:
        from expense.tui.widgets.cursor_list import CursorList

        self._by_id = {it.get("id"): it for it in items}
        cursor_list = CursorList(
            self.HEADERS,
            self.rows(items),
            align_right=self.ALIGN_RIGHT,
            empty=self.EMPTY,
            page_size=self.measure_list_rows(),  # adaptive window (2026-07-13)
        )
        # Re-select the acted-on row: _show mounts a fresh CursorList each load,
        # so without this an archive toggle would snap the cursor back to row 0
        # and "press `a` again to undo" would hit the wrong record.
        if self._restore_key is not None:
            cursor_list.set_cursor(cursor_list.index_of(self._restore_key))
            self._restore_key = None
        self._toggle_busy = False
        self.call_after_refresh(self.refresh_bindings)
        widgets: list[Widget] = [cursor_list]
        if self.LEGEND:
            widgets.append(Static(Text(self.LEGEND), classes="legend"))
        return widgets

    def action_new(self) -> None:
        self.app.push_screen(self.new_screen(), lambda _result: self._load())

    def action_edit(self) -> None:
        item = self.selected_record()
        if not item:
            return
        self._restore_key = item.get("id")
        self.app.push_screen(self.edit_screen(item), lambda _result: self._load())
