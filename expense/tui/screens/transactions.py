"""Transactions screen — the ledger, whole or filtered, with bulk edits.

Built on SectionScreen + the shared CursorList, as **one list that grows**
(`GrowingListMixin`, M3 of docs/mockups/expense-world-engine-uptake.html,
2026-09-26): it opens with the newest 10, `pgdn` appends the next 10 by the
engine's cursor, and the legend reads `N of M loaded`. `enter` opens the
record in the editable QuickAddLogScreen and `+` opens the LOG bar
(`LogTransactionMixin`).

**The filtered ledger is the categorising pass** (2026-09-12, mockup
docs/mockups/expense-world-home-as-ledger.html). Home pushes this screen with
a `LedgerFilter` — a category or an account — and it becomes `Ledger › NAME`:
the same list over the engine's own `?category_id=` / `?account_id=`, with the
legend saying what the filter is and how many rows it holds. `space` selects
rows, `a` selects every loaded row, and one key changes the category (`c`), the bank
account (`b`) or the hashtags (`h`) of the selection — or of the cursor row
when nothing is selected. Each opens `PickerModal`; the write is one
`PUT /transactions/{id}` per row, in order, and then one re-read of as many
rows as were loaded, so on a filtered list the changed rows leave at once
(pane 6, option C) and the cursor stays on the same row number. A refused
row is named by its number; the others go through. Title, description,
amount and date stay single-row edits behind `⏎`.

`esc` clears the selection when there is one; otherwise it goes back to where
you came from — Home, for a filter Home opened (owner, 2026-09-13: esc on a
filtered ledger is back to Home, never to the unfiltered ledger).

The `p` filter (all → pendiente) lived here from the morning of 2026-09-12 to
the evening: `@Pendiente` is a row on Home now, and `⏎` on it is the filter.
"""

from typing import NamedTuple

from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static

from expense.commands import transactions_cmd
from expense.commands._resource import (
    ENGINE_PAGE_CAP,
    format_hashtag_cell,
    format_short_date,
    load_account_name_map,
    load_category_name_map,
    load_hashtag_name_map,
    load_quickadd_refs,
    resolve_name,
)
from expense.errors import format_error
from expense.tui.screens._base import (
    GrowingListMixin,
    LogTransactionMixin,
    SectionScreen,
    screen_fetch_kwargs,
)
from expense.tui.screens.modals import PickerModal
from expense.tui.screens.quick_log import QuickAddLogScreen
from expense.tui.theme import ACCENT, AMOUNT_RULE, PALETTE, Palette
from expense.tui.widgets.cells import amount_cell
from expense.tui.widgets.cursor_list import CursorList

_HEADERS = ["Title", "Description", "Amount", "Date", "Account", "Cat", "Hashtags"]
#: The free-text columns and their share of the width left after Amount, Date,
#: Account and Cat take their natural size (2026-09-12, option A of
#: docs/mockups/expense-world-ledger-column-fit.html). The cells are handed to
#: the table whole and cut by it at the column edge; the row builder used to cap
#: them at 20/18/20 characters, a size for the 80-column card this screen left on
#: 2026-08-29, which is why a wide terminal showed wide columns of cut text.
_FLEX = {0: 3, 1: 3, 6: 2}

#: The selection marker, drawn in the title cell's two-column gutter so the
#: column header and every unselected row keep their alignment.
SELECTED_MARK = "● "
_GUTTER = "  "

#: What each bulk key writes: the picker's kind → the PUT field it fills.
BULK_FIELDS = {"category": "category_id", "account": "account_id", "hashtags": "hashtag_ids"}


class LedgerFilter(NamedTuple):
    """What Home handed the ledger: `kind` is `category` or `account`, `id` the
    engine row, `name` what the crumb and the legend say. `hashtag_id` narrows
    a category filter to one hashtag — `⏎` on a hashtag row under a category
    on Home (2026-09-13); the name then reads `WANTS #SALIDAS`."""

    kind: str
    id: str
    name: str
    hashtag_id: str | None = None


def transaction_rows(
    items: list[dict],
    accounts: dict,
    categories: dict,
    hashtags: dict,
    palette: Palette | None = None,
) -> list:
    """Pure (id, cells) rows for a CursorList. Unit-testable without a screen."""
    rows = []
    for it in items:
        rows.append(
            (
                it.get("id"),
                [
                    it.get("title") or "—",
                    it.get("description") or "",
                    amount_cell(it.get("amount_cents"), palette, AMOUNT_RULE),
                    format_short_date(it.get("date")),
                    resolve_name(it.get("account_id"), accounts),
                    resolve_name(it.get("category_id"), categories),
                    format_hashtag_cell(it.get("hashtag_ids"), hashtags),
                ],
            )
        )
    return rows


def mark_selected(rows: list, selected: set) -> list:
    """The same rows with the selection drawn: a marker in the title gutter and
    the accent as the row's base style; every other row gets a blank gutter so
    titles stay aligned. Pure — the widget re-renders, the screen re-marks."""
    marked = []
    for key, cells, *rest in rows:
        cells = list(cells)
        if key in selected:
            cells[0] = Text.assemble((SELECTED_MARK, ACCENT), str(cells[0]))
            marked.append((key, cells, ACCENT))
        else:
            cells[0] = _GUTTER + str(cells[0])
            marked.append((key, cells, *rest))
    return marked


def legend_text(filter: LedgerFilter | None, loaded: int, total: int | None, selected: int) -> str:
    """`filter: category @Pendiente · 20 of 57 loaded · 3 selected` — the
    filter, how many of the engine's count are loaded, and the selection when
    there is one (one line, owner 2026-09-26: `of M loaded` took the place of
    `M rows`)."""
    head = f"filter: {filter.kind} {filter.name}" if filter else "no filter"
    parts = [head]
    if isinstance(total, int):
        parts.append(f"{loaded} of {total} loaded")
    if selected:
        parts.append(f"{selected} selected")
    return " · ".join(parts)


#: Row numbers listed in full before a refusal summary starts counting instead.
REFUSAL_ROWS_SHOWN = 8


def group_refusals(failed: list[tuple[object, int, str]]) -> list[str]:
    """One line per distinct reason — `rows 1, 2, 3: <the engine's message>`.

    Sealed periods (2026-09-20) made the old one-toast-per-row shape unusable: a
    bulk account move across a closed month refuses every row it touches for the
    *same* reason, so eight rows meant eight ten-second toasts saying the same
    sentence (owner, 2026-09-22 — mockup expense-world-rows-in-no-batch.html §4).

    Grouping is by the message **as the engine wrote it**, never by anything read
    out of it. The period's name lives inside that sentence and nothing here goes
    looking for it: identical refusals collapse because the strings are equal.
    """
    order: list[str] = []
    rows: dict[str, list[int]] = {}
    for _key, number, message in failed:
        if message not in rows:
            order.append(message)
            rows[message] = []
        if number:
            rows[message].append(number)
    lines = []
    for message in order:
        numbers = rows[message]
        if not numbers:
            lines.append(message)
            continue
        shown = ", ".join(str(n) for n in numbers[:REFUSAL_ROWS_SHOWN])
        if len(numbers) > REFUSAL_ROWS_SHOWN:
            shown += f" +{len(numbers) - REFUSAL_ROWS_SHOWN} more"
        label = "row" if len(numbers) == 1 else "rows"
        lines.append(f"{label} {shown}: {message}")
    return lines


def bulk_receipt(count: int, label: str) -> str:
    """The toast after a bulk write: `3 rows → KORAKUEN`."""
    return f"{count} {'row' if count == 1 else 'rows'} → {label}"


class TransactionsScreen(LogTransactionMixin, GrowingListMixin, SectionScreen):
    BINDINGS = [
        *LogTransactionMixin.BINDINGS,
        Binding("a", "select_all", "All/none", tooltip="Select every loaded row, or none"),
        Binding("c", "pick('category')", "Category", tooltip="Set the category of the selection"),
        Binding("b", "pick('account')", "Account", tooltip="Move the selection to an account"),
        Binding("h", "pick('hashtags')", "Hashtags", tooltip="Replace the selection's hashtags"),
        Binding(
            "escape",
            "back",
            "Back",
            tooltip="Clear the selection, else go back",
        ),
    ]
    crumb = ("Capture & ledger", "Transactions")
    # None = the card fills the terminal width, and PAGE_ROWS_CAP lets the list
    # window fill its height: the ledger is the screen you sit in, so it takes
    # the window you gave it instead of holding a 110x20 card in the corner of
    # a large one (2026-08-29). Since the list grows (2026-09-26) the cap sizes
    # only the window, never a read.
    CARD_WIDTH = None
    PAGE_ROWS_CAP = ENGINE_PAGE_CAP

    def __init__(self, filter: LedgerFilter | None = None) -> None:
        super().__init__()
        self._by_id: dict = {}
        self._filter = filter
        self._selected: set = set()
        self._rows: list = []  # every loaded row, unmarked, in list order
        self._maps: tuple[dict, dict, dict] = ({}, {}, {})
        self._refs = None  # QuickAddRefs, loaded on the first bulk key
        self._pending_pick: str | None = None
        self._bulk_busy = False
        self.crumb = _crumb_for(filter)

    def list_extra_lines(self) -> int:
        return 2  # the filter legend below the list (margin-top 1 + text)

    # ---- data ---------------------------------------------------------------
    def _scope(self) -> dict:
        flt = self._filter
        if flt is None:
            return {}
        scope = {"category": flt.id} if flt.kind == "category" else {"account": flt.id}
        if flt.hashtag_id is not None:
            scope["hashtag"] = flt.hashtag_id
        return scope

    def _page_reader(self):
        """`(limit, after) -> body` over this ledger's filter (worker thread)."""
        from expense import config as config_module

        cfg = config_module.ensure_loaded()
        kw = screen_fetch_kwargs(self.app)
        scope = self._scope()

        def page(limit: int, after: str | None) -> dict:
            return transactions_cmd.fetch_transactions(cfg, **scope, after=after, limit=limit, **kw)

        return cfg, kw, page

    def fetch(self) -> dict:
        cfg, kw, page = self._page_reader()
        items, next_cursor, total = self.read_rows(
            page,
            lambda: transactions_cmd.count_transactions(cfg, **self._scope(), **kw),
        )
        return {
            "items": items,
            "next_cursor": next_cursor,
            "total": total,
            "accounts": load_account_name_map(),
            "categories": load_category_name_map(),
            "hashtags": load_hashtag_name_map(),
        }

    def build(self, data: dict) -> list[Widget]:
        items = data["items"]
        self.took_rows(data["next_cursor"], data["total"])
        self._by_id = {it.get("id"): it for it in items}
        self._maps = (data["accounts"], data["categories"], data["hashtags"])
        self._rows = transaction_rows(items, *self._maps, palette=PALETTE)
        # a reload drops selections that left the list (option C: they left)
        self._selected &= set(self._by_id)
        flt = self._filter
        # The panel title went with the border (2026-09-20): the crumb reads
        # `Ledger ▸ @Pendiente` and the legend below says `filter: category
        # @Pendiente · 57 rows`, so a third naming of the filter was chrome.
        # Only the empty-state text is still computed from the filter.
        if flt is not None:
            empty = f"(no transactions under {flt.name})"
        else:
            empty = "(no transactions)"
        self.call_after_refresh(self.refresh_bindings)
        listing = CursorList(
            _HEADERS,
            mark_selected(self._rows, self._selected),
            align_right={2},
            flex=_FLEX,
            empty=empty,
            page_size=self.measure_list_rows(),
        )
        self.place_list(listing)
        return [listing, Static(Text(self._legend()), classes="legend", id="legend")]

    def _legend(self) -> str:
        return legend_text(self._filter, len(self._rows), self._total, len(self._selected))

    # ---- growing (M3) -------------------------------------------------------
    def on_cursor_list_more_requested(self, event: CursorList.MoreRequested) -> None:
        """`pgdn`: the next 10, appended under the rows in hand."""
        event.stop()
        self.fetch_more(lambda limit, after: self._page_reader()[2](limit, after))

    def append_loaded(self, items: list, *, more: bool) -> None:
        try:
            listing = self.query_one(CursorList)
            legend = self.query_one("#legend", Static)
        except Exception:
            return  # a reload replaced the list mid-read
        self._by_id.update((it.get("id"), it) for it in items)
        rows = transaction_rows(items, *self._maps, palette=PALETTE)
        self._rows.extend(rows)
        listing.append_rows(mark_selected(rows, self._selected), more=more)
        legend.update(Text(self._legend()))
        self.refresh_bindings()

    def _repaint_selection(self) -> None:
        try:
            listing = self.query_one(CursorList)
            legend = self.query_one("#legend", Static)
        except Exception:
            return  # loading / error state — nothing to mark
        listing.set_rows(mark_selected(self._rows, self._selected))
        legend.update(Text(self._legend()))
        self.refresh_bindings()

    # ---- keys ---------------------------------------------------------------
    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action in ("select_all", "pick") and not self._rows:
            return False  # empty list → nothing to act on; the keys leave the footer
        if action == "pick" and self._bulk_busy:
            return None  # greyed, not gone: one bulk write at a time until its reload lands
        return True

    def on_cursor_list_toggled(self, event: CursorList.Toggled) -> None:
        event.stop()
        if event.key in self._selected:
            self._selected.discard(event.key)
        else:
            self._selected.add(event.key)
        self._repaint_selection()

    def action_select_all(self) -> None:
        keys = {key for key, *_ in self._rows}
        self._selected = set() if keys and keys <= self._selected else keys
        self._repaint_selection()

    def action_back(self) -> None:
        """Selection first, then back to the screen that pushed this one.

        Until 2026-09-13 a filtered ledger cleared its filter on the second
        `esc` and left on the third. The owner's report: from Home, `⏏` on a
        category then `esc` should be Home again, not the whole ledger — the
        filter is the door you came in by, not a state to step out of."""
        if self._selected:
            self._selected = set()
            self._repaint_selection()
            return
        self.app.pop_screen()

    def _targets(self) -> list:
        """The ids a bulk key acts on: the selection in list order, else the
        cursor row."""
        if self._selected:
            return [key for key, *_ in self._rows if key in self._selected]
        try:
            cursor = self.query_one(CursorList).cursor_key
        except Exception:
            return []
        return [cursor] if cursor in self._by_id else []

    def action_pick(self, kind: str) -> None:
        if kind not in BULK_FIELDS or not self._targets():
            return
        if self._refs is None:
            # the reference lists load on the first bulk key, not with every
            # page: browsing the ledger costs no picker reads
            self._pending_pick = kind
            self._load_refs()
            return
        self._open_picker(kind)

    @work(thread=True, exclusive=True, group="ledger-refs")
    def _load_refs(self) -> None:
        from expense import config as config_module

        try:
            cfg = config_module.ensure_loaded()
            refs = load_quickadd_refs(cfg, **screen_fetch_kwargs(self.app))
        except Exception as exc:
            self.app.call_from_thread(self._refs_failed, format_error(exc))
            return
        self.app.call_from_thread(self._set_refs, refs)

    def _refs_failed(self, message: str) -> None:
        self._pending_pick = None
        self.notify(message, title="Could not load the pickers", severity="error")

    def _set_refs(self, refs) -> None:
        self._refs = refs
        kind, self._pending_pick = self._pending_pick, None
        if kind is not None and self._targets():
            self._open_picker(kind)

    def _picker_options(self, kind: str) -> list[tuple[str, str]]:
        refs = self._refs
        if kind == "category":
            # @Pendiente is pickable here on purpose: sending rows back to
            # pending is how a wrong bulk pick is undone
            pool = list(refs.categories)
            if refs.pending is not None:
                pool.append(refs.pending)
            return pool
        if kind == "account":
            return [(i, n) for i, n, *_ in refs.accounts]
        return list(refs.hashtags)

    def _open_picker(self, kind: str) -> None:
        targets = self._targets()
        count = len(targets)
        rows = "row" if count == 1 else "rows"
        title = f"{kind.upper()} for {count} {rows}"
        note = f"replaces every tag on the {count} {rows}" if kind == "hashtags" else ""
        options = self._picker_options(kind)
        if not options:
            self.notify(f"There is nothing to pick — no {kind} exists yet.", severity="warning")
            return
        modal = PickerModal(title, options, note=note, multi=(kind == "hashtags"))
        self.app.push_screen(modal, lambda picked: self._apply_pick(kind, targets, picked))

    def _apply_pick(self, kind: str, targets: list, picked: object) -> None:
        if picked is None or self._bulk_busy:
            return
        names = dict(self._picker_options(kind))
        if kind == "hashtags":
            ids = list(picked) if isinstance(picked, list) else [picked]
            label = " ".join("#" + names.get(i, i) for i in ids) or "(no tags)"
            payload = {"hashtag_ids": ids}
        else:
            label = names.get(picked, str(picked))
            payload = {BULK_FIELDS[kind]: picked}
        self._bulk_busy = True
        self.refresh_bindings()
        self._bulk_write(targets, payload, label)

    # ---- the bulk write -------------------------------------------------------
    @work(thread=True, group="engine-write")
    def _bulk_write(self, targets: list, payload: dict, label: str) -> None:
        """One PUT per row, in order, on one client; a refused row is kept by
        number and the rest go through — unlike `run_write`'s queue, which
        drops the remainder on the first error, because here every row's
        intent is independent of its neighbours'."""
        from expense import config as config_module
        from expense.http import ExpenseClient

        numbers = {key: n for n, (key, *_) in enumerate(self._rows, start=1)}
        done = 0
        failed: list[tuple[object, int, str]] = []
        try:
            cfg = config_module.ensure_loaded()
            with ExpenseClient(cfg, verbose=self.app._verbose) as client:
                for key in targets:
                    try:
                        client.put(f"/transactions/{key}", json_body=payload)
                        done += 1
                    except Exception as exc:
                        failed.append((key, numbers.get(key, 0), format_error(exc)))
        except Exception as exc:
            failed.append((None, 0, format_error(exc)))
        self.app.call_from_thread(self._bulk_finished, done, failed, label)

    def _bulk_finished(self, done: int, failed: list, label: str) -> None:
        self._bulk_busy = False
        if done:
            self.notify(bulk_receipt(done, label))
        # One toast per distinct reason, not per row — see `group_refusals`.
        lines = group_refusals(failed)
        head = f"{len(failed)} of {done + len(failed)} refused" if len(failed) > 1 else "Refused"
        for line in lines:
            self.notify(line, title=head, severity="error", timeout=10)
        # the rows that went through no longer belong to a filtered list — they
        # leave at once (pane 6, option C). A refused row stays selected, so
        # once its lock is lifted the same key retries exactly it.
        self._selected = {key for key, _n, _m in failed if key is not None}
        self.reload_in_place()

    # ---- single-row doors ----------------------------------------------------
    def _after_log(self, _result=None) -> None:
        self.reload_in_place()  # a transaction written with `+` belongs in this list now

    def on_cursor_list_selected(self, event: CursorList.Selected) -> None:
        item = self._by_id.get(event.key)
        if item:
            self.app.push_screen(
                QuickAddLogScreen(record=item, resource="transactions"),
                lambda _result: self.reload_in_place(),  # the edit shows, the depth stays
            )


def _crumb_for(flt: LedgerFilter | None) -> tuple[str, ...]:
    return ("Ledger", flt.name) if flt is not None else ("Capture & ledger", "Transactions")
