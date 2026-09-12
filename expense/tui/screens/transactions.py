"""Transactions screen — the ledger, and the rows still to classify.

Built on SectionScreen + the shared CursorList. Fetch-paged (PagedListMixin —
real limit/offset against the engine, the page sized to the window);
`enter` opens the record in the editable QuickAddLogScreen and `+` opens the
LOG bar (`LogTransactionMixin`).

**`p` cycles the filter, `all → pendiente`** (2026-09-12, the screen that
replaced the Inbox — docs/mockups/expense-world-pendiente-not-inbox.html pane
6, option A). A pending row is an ordinary ledger row whose category cell
reads `@Pendiente`; the filter is the engine's own `?category_id=` on that
system row, and the legend under the list counts them whatever the filter.
Finishing a row is `⏎` and the edit form, like any other correction.
"""

from rich.text import Text
from textual.widget import Widget
from textual.widgets import Static

from expense.commands import transactions_cmd
from expense.commands._resource import (
    ENGINE_PAGE_CAP,
    format_hashtag_cell,
    format_short_date,
    items_of,
    load_account_name_map,
    load_category_name_map,
    load_hashtag_name_map,
    load_pending_category_id,
    resolve_name,
    truncate,
)
from expense.tui.screens._base import (
    LogTransactionMixin,
    PagedListMixin,
    SectionScreen,
    screen_fetch_kwargs,
)
from expense.tui.screens.quick_log import QuickAddLogScreen
from expense.tui.theme import AMOUNT_RULE, PALETTE, Palette
from expense.tui.widgets.cells import amount_cell
from expense.tui.widgets.cursor_list import CursorList

_HEADERS = ["Title", "Description", "Amount", "Date", "Account", "Cat", "Hashtags"]
_FILTERS = ["all", "pendiente"]


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
                    truncate(it.get("title") or "—", 20),
                    truncate(it.get("description"), 18),
                    amount_cell(it.get("amount_cents"), palette, AMOUNT_RULE),
                    format_short_date(it.get("date")),
                    resolve_name(it.get("account_id"), accounts),
                    resolve_name(it.get("category_id"), categories),
                    format_hashtag_cell(it.get("hashtag_ids"), hashtags, max_width=20),
                ],
            )
        )
    return rows


class TransactionsScreen(LogTransactionMixin, PagedListMixin, SectionScreen):
    BINDINGS = [
        *LogTransactionMixin.BINDINGS,
        ("p", "cycle_filter", "Filter"),
    ]
    crumb = ("Capture & ledger", "Transactions")
    # None = the card fills the terminal width, and PAGE_ROWS_CAP lets the page
    # fill its height: the ledger is the screen you sit in, so it takes the
    # window you gave it instead of holding a 110x20 card in the corner of a
    # large one (2026-08-29). The cap is the engine's own `limit` ceiling.
    CARD_WIDTH = None
    PAGE_ROWS_CAP = ENGINE_PAGE_CAP

    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict = {}
        self._filter = "all"

    def list_extra_lines(self) -> int:
        return 2  # the filter legend below the list (margin-top 1 + text)

    def fetch(self) -> dict:
        from expense import config as config_module

        cfg = config_module.ensure_loaded()
        kw = screen_fetch_kwargs(self.app)
        # Resolved worker-side, never in build(): a reference read on the
        # render path blocks first paint (same rule as overview.py). `None`
        # means the category has never been seeded — nothing is pending.
        pending_id = load_pending_category_id()
        only_pending = self._filter == "pendiente"

        def page(pkw: dict) -> dict:
            if only_pending and pending_id is None:
                return {"items": [], "total": 0, "limit": pkw.get("limit"), "offset": 0}
            category = pending_id if only_pending else None
            return transactions_cmd.fetch_transactions(cfg, category=category, **pkw, **kw)

        body = self.fetch_page_body(page)
        pending_total = 0
        if pending_id is not None:
            probe = transactions_cmd.fetch_transactions(cfg, category=pending_id, limit=1, **kw)
            total = probe.get("total") if isinstance(probe, dict) else None
            pending_total = total if isinstance(total, int) else 0
        return {
            "items": items_of(body),
            "pending_total": pending_total,
            "accounts": load_account_name_map(),
            "categories": load_category_name_map(),
            "hashtags": load_hashtag_name_map(),
        }

    def build(self, data: dict) -> list[Widget]:
        items = data["items"]
        self._by_id = {it.get("id"): it for it in items}
        rows = transaction_rows(
            items,
            data["accounts"],
            data["categories"],
            data["hashtags"],
            palette=PALETTE,
        )
        # Panel title absorbs the old title + legend rows; the border subtitle
        # carries the page status (picks B/A, 2026-07-11).
        pending = data.get("pending_total", 0)
        if self._filter == "pendiente":
            title = "Ledger — pendiente · rows still to classify, most recent first"
            empty = "(nothing pending — every row has a category)"
        else:
            title = "Ledger — posted transactions · most recent first"
            empty = "(no transactions)"
        return [
            CursorList(
                _HEADERS,
                rows,
                align_right={2},
                empty=empty,
                title=title,
                page_size=self.page_rows,
                page_meta=self.page_meta(),
            ),
            Static(
                Text(f"filter: {self._filter} · {pending} pendiente"),
                classes="legend",
            ),
        ]

    async def action_cycle_filter(self) -> None:
        """`p`: all → pendiente → all. A new filter invalidates the old offset."""
        i = _FILTERS.index(self._filter)
        self._filter = _FILTERS[(i + 1) % len(_FILTERS)]
        self.reset_page()
        await self.action_reload()

    def _after_log(self, _result=None) -> None:
        self._load()  # a transaction written with `+` belongs in this list now

    def on_cursor_list_selected(self, event: CursorList.Selected) -> None:
        item = self._by_id.get(event.key)
        if item:
            self.app.push_screen(
                QuickAddLogScreen(record=item, resource="transactions"),
                lambda _result: self._load(),  # refresh the list after editing
            )
