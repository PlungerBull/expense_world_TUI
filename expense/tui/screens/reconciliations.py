"""Reconciliations — list, new batch, and the working/detail screen (Phase 2).

Per-account bank-statement batches. The browse opens on the accounts alone;
`⏎` on one reads that account's reconciliations (`GET /reconciliations?
account_id=`, whole, in the engine's period order: `date_start ASC,
created_at ASC`) and opens them in a panel under the accounts, the
cursor in it. There `⏎` opens the working screen, `n` creates one for the
account, `u` swaps the panel for the account's rows in no batch, and `esc`
closes the panel (owner, 2026-09-25, mockup expense-world-engine-uptake.html
M2). Nothing is read for an account until you press `⏎` on it.

New batch: name › account › date start › date end › begin › end. Both balances
are typed off the paper statement — the engine deleted derived (chained) begins
on 2026-08-06, so there is nothing to inherit and `beginning_balance_cents` is
required. Both dates are required too, by the engine (`8f22ebb`), and are
calendar days sent as typed (`5922bbf`); the form refuses any other shape at
the field. POST /reconciliations.

Working screen (ReconciliationDetailScreen): a checklist of the account's
unassigned + already-in-batch transactions (draft) or a read-only list of the
batch's transactions (completed). `space` toggles membership (PUT the
transaction's reconciliation_id); `c`/`u`/`d` complete/revert/delete; `r`
refetches the batch + checklist. Complete
needs ≥1 transaction and locks amount/account/title/date on them; delete is
draft-only and just detaches the transactions.
"""

import uuid

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Footer, Input, Static
from textual.worker import get_current_worker

from expense.commands import accounts_cmd, reconcile_cmd, transactions_cmd
from expense.commands._resource import (
    ENGINE_PAGE_CAP,
    account_choices,
    fetch_all_cursor_pages,
    format_cents,
    items_of,
    load_account_name_map,
    load_category_name_map,
    load_hashtag_name_map,
    resolve_name,
)
from expense.dates import is_calendar_day
from expense.errors import format_error
from expense.quickadd.money import amount_to_text, parse_amount
from expense.quickadd.names import matches
from expense.tui.screens._base import (
    AdaptiveRowsMixin,
    ContentSwapLockMixin,
    EngineWriteMixin,
    SectionScreen,
    screen_fetch_kwargs,
)
from expense.tui.screens._form import FormScreen
from expense.tui.screens.help import HelpBindingMixin
from expense.tui.screens.modals import ConfirmModal
from expense.tui.theme import ACCENT, AMOUNT_RULE, BALANCE_RULE, PALETTE, Palette
from expense.tui.widgets.cells import amount_cell, difference_cell
from expense.tui.widgets.checklist import CheckList
from expense.tui.widgets.cursor_list import GROW_STEP, CursorList
from expense.tui.widgets.header import Breadcrumb

# Status labels + period formatting are owned by the commands layer
# (reconcile_cmd.format_status / format_period) — one copy, per the §5 rule.
_period = reconcile_cmd.format_period

_BATCH_HEADERS = ["Name", "Period", "Begin", "End", "Diff", "Status"]
_UNFILED_HEADERS = ["", "Date", "Title", "Amount", "Category"]

#: What the unfiled pane asks the engine for: this account's rows in no batch,
#: oldest first. It opens with the `GROW_STEP` oldest and `pgdn` appends the
#: next ones (owner, 2026-09-25, mockup expense-world-engine-uptake.html M6) —
#: a work queue you walk forward from the oldest, never a jump into the middle.
UNFILED_FILTER = {"unreconciled": True}


def blocking_windows(recons: list[dict], account_id) -> list[tuple[str, str, str]]:
    """`(first_day, last_day, name)` for every batch on this account.

    Used only to draw the `!` hint beside a row (see `unfiled_rows`). Drafts are
    included on purpose: a draft's window is exactly what an unfiled row inside
    it will refuse when you try to close it, which is the question the flag
    answers. Completed windows are in here too — an unfiled row inside one is an
    anomaly the engine's close check would not allow to arise today, and it is
    precisely what the pane exists to surface in pre-2026-09-20 data.
    """
    windows = []
    for r in recons:
        if r.get("account_id") != account_id:
            continue
        windows.append((r["date_start"], r["date_end"], r.get("name") or "—"))
    return windows


def unfiled_rows(items: list[dict], cat_names: dict, windows, palette=None) -> list:
    """Rows for the unfiled pane, in the order given (the engine's `date_asc`),
    `!` on the ones inside a window.

    **The flag is a hint, not a ruling.** It compares each row's date against
    windows this screen already holds, so it costs no request — but the engine
    is the authority at close time (it resolves a window in the user's
    timezone), so an edge day may differ. Nothing downstream reads the flag: it
    only tells you which rows are worth opening first.
    """
    rows = []
    for it in items:
        day = (it.get("date") or "")[:10]
        blocked = any(start <= day <= end for start, end, _name in windows)
        if not blocked:
            flag: object = ""
        else:
            flag = Text("!", style=palette.warning) if palette else "!"
        rows.append(
            (
                it.get("id"),
                [
                    flag,
                    day,
                    it.get("title") or "—",
                    amount_cell(it.get("amount_cents"), palette, AMOUNT_RULE),
                    resolve_name(it.get("category_id"), cat_names),
                ],
            )
        )
    return rows


def batch_rows(items: list[dict], palette: Palette | None = None) -> list:
    """Per-account batch rows (no Account column) for the browse's lower pane."""
    rows = []
    for it in items:
        status = it.get("status")
        cells = [
            it.get("name") or "(unnamed)",
            _period(it),
            amount_cell(it.get("beginning_balance_cents"), palette, BALANCE_RULE),
            amount_cell(it.get("ending_balance_cents"), palette, BALANCE_RULE),
            difference_cell(it.get("difference_cents"), palette),
            reconcile_cmd.format_status(status),
        ]
        rows.append((it.get("id"), cells, "dim" if status == 2 else ""))
    return rows


class _AccountList(CursorList):
    """The browse's account list. Only `enter` changes: on this list it opens
    the account's panel, so the footer names that instead of `Open` (mockup
    expense-world-engine-uptake.html, M2)."""

    BINDINGS = [Binding("enter", "select", "Its reconciliations")]


class _PanelList(CursorList):
    """The panel under the accounts. It lists two things (M6): a
    reconciliation, which `enter` opens, or a row in no batch, which `enter`
    edits — so the footer says `Edit` there, as the mockup draws it (owner,
    2026-09-26). Two bindings on one key: Textual takes the first whose
    `check_action` allows it."""

    BINDINGS = [
        Binding("enter", "edit_row", "Edit", tooltip="Edit the row: its date or its account"),
        Binding("enter", "select", "Open"),
    ]

    def _listing_unfiled(self) -> bool:
        try:
            return getattr(self.screen, "_mode", None) == "unfiled"
        except Exception:
            return False

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "edit_row":
            return self._listing_unfiled()
        if action == "select" and self._listing_unfiled():
            return False
        return super().check_action(action, parameters)

    def action_edit_row(self) -> None:
        self.action_select()  # the screen's Selected handler opens the edit form


class ReconciliationsScreen(SectionScreen):
    """Accounts first; one account's reconciliations on `⏎` (owner, 2026-09-25,
    mockup expense-world-engine-uptake.html M2).

    The screen opens on the account list alone, and nothing about
    reconciliations is read until you press `⏎` on an account: the engine lists
    them one account at a time (`GET /reconciliations?account_id=`, whole, in
    period order), so moving the cursor costs nothing. `⏎` reads that account's
    list and opens the panel under the accounts with the cursor in it. There
    `⏎` opens a reconciliation, `n` creates one, `u` swaps the panel for the
    account's rows in no batch, and `esc` closes the panel.
    """

    crumb = ("Capture & ledger", "Reconciliations")
    CARD_WIDTH = 100
    BINDINGS = [
        # Two bindings on one key: Textual takes the first whose `check_action`
        # allows it, so the footer reads "Close the panel" only while it would.
        Binding("escape", "close_panel", "Close the panel"),
        ("escape", "back", "Back"),
        ("n", "new", "New"),
        Binding("u", "unfiled", "No batch", tooltip="This account's rows that are in no batch"),
        Binding("d", "delete_row", "Delete", show=False),  # unfiled pane only
    ]

    def __init__(self) -> None:
        super().__init__()
        self._recons: list = []  # the open account's reconciliations, engine order
        self._accounts: list = []  # (id, name, currency, balance_cents)
        self._acct_idx = 0
        self._open_aid: str | None = None  # the account whose panel is open
        self._mode = "accts"  # "accts" | "batches" | "unfiled"
        self._unfiled: list = []  # every unfiled row loaded so far, oldest first
        self._unfiled_total: int | None = None
        self._unfiled_next: str | None = None  # the engine's cursor past the last row
        self._unfiled_cats: dict = {}
        self._unfiled_busy = False
        self._by_id: dict = {}
        self._resume_key: object | None = None  # the panel row to land on after a reload
        self._accts_list: CursorList | None = None
        self._batch_list: CursorList | None = None

    def fetch(self) -> dict:
        """The accounts, and the open account's reconciliations when a panel is
        open — which is how a return from a reconciliation, or from `n`, comes
        back to the same panel."""
        from expense import config as config_module

        cfg = config_module.ensure_loaded()
        kw = screen_fetch_kwargs(self.app)
        accts = items_of(accounts_cmd.fetch_accounts(cfg, **kw))
        accounts = account_choices(accts, include_people=False, with_balance=True)
        recons = None
        if self._open_aid is not None:
            recons = items_of(
                reconcile_cmd.fetch_reconciliations(cfg, account_id=self._open_aid, **kw)
            )
        return {"recons": recons, "accounts": accounts}

    def _selected_account(self):
        return self._accounts[self._acct_idx] if self._accounts else None

    def _open_account(self):
        return next((a for a in self._accounts if a[0] == self._open_aid), None)

    def _batch_caption(self) -> str:
        acct = self._open_account()
        return f"Reconciliations · {acct[1] if acct else '—'}   ·   oldest → newest"

    # ---- adaptive window (2026-07-13): the panel splits #content ----------
    def pane_rows(self) -> int:
        """Rows per list. Alone, the account list fills #content (owner,
        2026-09-25); with the panel open the two split it equally — auto-height
        panes give unused rows back when a pane has fewer rows than its share.

        With the panel, the chrome is the section title (2) plus the two
        panes' frames, which are **not** the same size: the panel keeps a
        caption naming the account and the accounts pane does not, so it is
        `2 * LIST_FRAME_LINES + CAPTION_LINES` rather than an even doubling.
        """
        if self._open_aid is None:
            return self.fit_rows(chrome=2 + self.LIST_FRAME_LINES)
        return self.fit_rows(
            chrome=2 + 2 * self.LIST_FRAME_LINES + self.CAPTION_LINES, lines_per_row=2
        )

    def _viewport_resized(self) -> None:
        for lst in (self._accts_list, self._batch_list):
            if lst is not None and lst.is_attached:
                lst.set_page_size(self.pane_rows())

    def _account_rows(self) -> list:
        """The open account carries an accent `▸`, so you can see whose panel
        is showing once the cursor has gone down into it."""
        rows = []
        for aid, name, cur, bal in self._accounts:
            label = Text.assemble(("▸ ", ACCENT), name) if aid == self._open_aid else name
            rows.append((aid, [label, cur, amount_cell(bal, PALETTE, AMOUNT_RULE)]))
        return rows

    def _new_batch_list(self) -> CursorList:
        batch_list = _PanelList(
            _BATCH_HEADERS,
            batch_rows(self._recons, palette=PALETTE),
            align_right={2, 3, 4},
            empty="none yet · n to create one",
            caption=self._batch_caption(),
            page_size=self.pane_rows(),
        )
        batch_list.id = "batches"
        return batch_list

    def build(self, data: dict) -> list[Widget]:
        self._accounts = data["accounts"]
        if data["recons"] is None or self._open_account() is None:
            self._open_aid, self._recons = None, []
        else:
            self._recons = data["recons"]
        self._by_id = {r.get("id"): r for r in self._recons}
        self._acct_idx = min(self._acct_idx, max(0, len(self._accounts) - 1))
        self._accts_list = _AccountList(
            ["Account", "Cur", "Balance"],
            self._account_rows(),
            align_right={2},
            empty="(no bank accounts)",
            page_size=self.pane_rows(),
        )
        self._accts_list.id = "accts"
        widgets: list[Widget] = [
            Static(Text("Reconciliations — pick an account"), classes="section-title"),
            self._accts_list,
        ]
        self._batch_list = None
        if self._open_aid is not None:
            self._batch_list = self._new_batch_list()
            widgets.append(self._batch_list)
        return widgets

    async def _show(self, data: object) -> None:
        await super()._show(data)
        self._unfiled, self._unfiled_total, self._unfiled_next = [], None, None
        if self._accts_list is None or not self._accounts:
            self._mode = "accts"
            self._set_crumb()
            return
        self._accts_list.set_cursor(self._acct_idx)
        if self._batch_list is not None:
            self._mode = "batches"
            if self._resume_key is not None:
                self._batch_list.set_cursor(self._batch_list.index_of(self._resume_key))
                self._resume_key = None
            self._batch_list.focus()
        else:
            self._mode = "accts"
            self._accts_list.focus()
        self._set_crumb()

    def _set_crumb(self) -> None:
        acct = self._open_account()
        trail = self.crumb + ((acct[1],) if acct else ())
        self.query_one("#crumb", Breadcrumb).set_trail(trail)
        self.refresh_bindings()

    # ---- keys ------------------------------------------------------------
    def check_action(self, action: str, parameters: tuple) -> bool | None:
        # False, not None: hidden from the footer as well as dead (Textual 8)
        if action == "close_panel":
            return self._mode == "batches"
        if action == "back":
            return self._mode != "batches"
        if action == "unfiled":
            return self._open_aid is not None
        return True

    def on_cursor_list_highlighted(self, event: CursorList.Highlighted) -> None:
        # Source guard (backlog 6.2c): only the account list moves the account
        # cursor, and only while it is the list in use. Moving it reads nothing.
        if self._mode != "accts" or event.control is not self._accts_list:
            return
        self._acct_idx = event.index

    def on_cursor_list_selected(self, event: CursorList.Selected) -> None:
        if self._mode == "unfiled":
            # `⏎` opens the form that already edits date and account — the two
            # remedies for a row that is in no batch (owner, 2026-09-22).
            record = self._unfiled_record()
            if record is not None:
                from expense.tui.screens.quick_log import QuickAddLogScreen

                self.app.push_screen(
                    QuickAddLogScreen(record=record),
                    lambda _result: self._reload_unfiled(),
                )
            return
        if event.control is self._accts_list:
            if self._mode == "accts":
                self._acct_idx = event.index
                self._load_batches(event.key)
            return
        item = self._by_id.get(event.key)
        if item:
            self._resume_key = event.key
            self.app.push_screen(ReconciliationDetailScreen(item), lambda _result: self._load())

    @work(thread=True, exclusive=True, group="recon-batches")
    def _load_batches(self, account_id: str) -> None:
        """`⏎` on an account: read its reconciliations. A read that fails
        leaves the panel closed, with a toast."""
        from expense import config as config_module

        worker = get_current_worker()
        try:
            cfg = config_module.ensure_loaded()
            body = reconcile_cmd.fetch_reconciliations(
                cfg, account_id=account_id, **screen_fetch_kwargs(self.app)
            )
        except Exception as exc:
            if not worker.is_cancelled:
                self.app.call_from_thread(
                    self.notify, format_error(exc), title="Failed", severity="error"
                )
            return
        if worker.is_cancelled:
            return
        self.app.call_from_thread(self._open_panel, account_id, items_of(body))

    async def _open_panel(self, account_id: str, recons: list) -> None:
        if self._mode != "accts" or self._accts_list is None:
            return
        self._open_aid = account_id
        self._recons = recons
        self._by_id = {r.get("id"): r for r in recons}
        async with self._content_lock():
            self._batch_list = self._new_batch_list()
            await self.query_one("#card").mount(self._batch_list)
        self._accts_list.set_rows(self._account_rows())
        self._accts_list.set_page_size(self.pane_rows())
        self._mode = "batches"
        self._batch_list.focus()
        self._set_crumb()

    async def action_close_panel(self) -> None:
        """`esc` in the panel: back to the account list alone."""
        if self._mode != "batches":
            return
        self._open_aid, self._recons, self._by_id = None, [], {}
        if self._batch_list is not None:
            async with self._content_lock():
                await self._batch_list.remove()
            self._batch_list = None
        self._mode = "accts"
        if self._accts_list is not None:
            self._accts_list.set_rows(self._account_rows())
            self._accts_list.set_page_size(self.pane_rows())
            self._accts_list.focus()
        self._set_crumb()

    def action_back(self) -> None:
        if self._mode == "unfiled":
            # the pane swaps back to the reconciliations; the screen stays put
            self._show_batches()
        elif self._mode == "accts":
            self.app.pop_screen()

    def _show_batches(self) -> None:
        """The panel lists the open account's reconciliations again."""
        self._mode = "batches"
        self._unfiled, self._unfiled_total, self._unfiled_next = [], None, None
        if self._batch_list is not None:
            self._batch_list.set_growth(more=None)
            self._batch_list.set_headers(_BATCH_HEADERS, align_right={2, 3, 4})
            self._batch_list.set_caption(self._batch_caption())
            self._batch_list.set_rows(batch_rows(self._recons, palette=PALETTE))
            self._batch_list.focus()
        self.refresh_bindings()

    def _reload_unfiled(self) -> None:
        """Refetch the pane after an edit or a delete — a row whose date or
        account moved is no longer in this list, which is the point of editing
        it. As many rows as were loaded come back, and the cursor keeps its
        position, so fixing row 34 does not throw you back to the first ten."""
        if self._open_aid and self._mode == "unfiled" and self._batch_list is not None:
            self._unfiled_busy = True
            self._load_unfiled(
                self._open_aid, keep=len(self._unfiled), cursor=self._batch_list.cursor_index
            )

    async def action_reload(self) -> None:
        """`r` — in the unfiled pane, start again from the oldest `GROW_STEP`;
        anywhere else, reload the screen (an open panel stays open)."""
        if self._mode == "unfiled":
            if self._open_aid and not self._unfiled_busy:
                self._unfiled_busy = True
                self._load_unfiled(self._open_aid)
            return
        if self._batch_list is not None:
            self._resume_key = self._batch_list.cursor_key
        await super().action_reload()

    # ---- the unfiled pane (2026-09-22) -----------------------------------
    def action_unfiled(self) -> None:
        """`u` — swap the panel to the open account's rows in no batch.

        Only while a panel is open (owner, 2026-09-25): the panel is the slot
        it swaps into, and the account whose rows it lists is the open one.
        `esc` swaps it back. Owner's shape, mockup
        expense-world-rows-in-no-batch.html — reconciliation work stays in the
        reconciliation view, so this is a pane, not a filtered ledger.
        """
        acct = self._open_account()
        if acct is None or self._batch_list is None or self._unfiled_busy:
            return
        self._unfiled_busy = True
        self._mode = "unfiled"
        self._batch_list.set_headers(_UNFILED_HEADERS, align_right={3})
        self._batch_list.set_caption(f"In no batch · {acct[1]}   ·   loading…")
        self._batch_list.set_rows([])
        self.refresh_bindings()
        self._load_unfiled(acct[0])

    @work(thread=True, exclusive=True, group="recon-unfiled")
    def _load_unfiled(self, account_id: str, keep: int = 0, cursor: int = 0) -> None:
        """The first rows and the count, together (owner, 2026-09-23): the pane
        shows nothing until both are in, and a count that cannot be read fails
        the pane rather than leave rows beside a guessed number."""
        from expense import config as config_module

        worker = get_current_worker()
        try:
            cfg = config_module.ensure_loaded()
            kw = screen_fetch_kwargs(self.app)
            body = transactions_cmd.fetch_transactions(
                cfg,
                account=account_id,
                sort="date_asc",
                limit=min(max(GROW_STEP, keep), ENGINE_PAGE_CAP),
                **UNFILED_FILTER,
                **kw,
            )
            total = transactions_cmd.count_transactions(
                cfg, account=account_id, **UNFILED_FILTER, **kw
            )
            cat_names = load_category_name_map()
        except Exception as exc:
            if not worker.is_cancelled:
                self.app.call_from_thread(self._unfiled_failed, format_error(exc))
            return
        if worker.is_cancelled:
            return
        self.app.call_from_thread(
            self._show_unfiled,
            items_of(body),
            total,
            body.get("next_cursor"),
            cat_names,
            cursor,
        )

    def on_cursor_list_more_requested(self, event: CursorList.MoreRequested) -> None:
        """`pgdn` in the unfiled pane: the next `GROW_STEP` rows, appended."""
        if (
            self._mode != "unfiled"
            or self._unfiled_busy
            or not self._unfiled_next
            or not self._open_aid
        ):
            return
        self._unfiled_busy = True
        self._load_more_unfiled(self._open_aid, self._unfiled_next)

    @work(thread=True, exclusive=True, group="recon-unfiled")
    def _load_more_unfiled(self, account_id: str, after: str) -> None:
        """No recount on `pgdn`: the rows are new, the question is not."""
        from expense import config as config_module

        worker = get_current_worker()
        try:
            cfg = config_module.ensure_loaded()
            body = transactions_cmd.fetch_transactions(
                cfg,
                account=account_id,
                sort="date_asc",
                after=after,
                limit=GROW_STEP,
                **UNFILED_FILTER,
                **screen_fetch_kwargs(self.app),
            )
        except Exception as exc:
            if not worker.is_cancelled:
                self.app.call_from_thread(self._more_failed, format_error(exc))
            return
        if worker.is_cancelled:
            return
        self.app.call_from_thread(self._append_unfiled, items_of(body), body.get("next_cursor"))

    def _more_failed(self, message: str) -> None:
        """The rows already loaded stay; only the next ones did not arrive."""
        self._unfiled_busy = False
        self.notify(message, title="Failed", severity="error")

    def _append_unfiled(self, items: list, next_cursor: str | None) -> None:
        self._unfiled_busy = False
        if self._mode != "unfiled" or self._batch_list is None:  # esc landed mid-read
            return
        self._unfiled.extend(items)
        self._unfiled_next = next_cursor
        windows = blocking_windows(self._recons, self._open_aid)
        rows = unfiled_rows(items, self._unfiled_cats, windows, palette=PALETTE)
        self._batch_list.set_caption(self._unfiled_caption())
        self._batch_list.append_rows(rows, more=next_cursor is not None)

    def _unfiled_failed(self, message: str) -> None:
        self._unfiled_busy = False
        self._show_batches()
        self.notify(message, title="Failed", severity="error")

    def _show_unfiled(
        self,
        items: list,
        total: int,
        next_cursor: str | None,
        cat_names: dict,
        cursor: int = 0,
    ) -> None:
        self._unfiled_busy = False
        if self._mode != "unfiled" or self._batch_list is None:  # esc landed mid-read
            return
        self._unfiled = list(items)
        self._unfiled_total = total
        self._unfiled_next = next_cursor
        self._unfiled_cats = cat_names
        # the panel already holds this account's reconciliations: the `!`
        # windows cost no read of their own
        windows = blocking_windows(self._recons, self._open_aid)
        rows = unfiled_rows(items, cat_names, windows, palette=PALETTE)
        self._batch_list.set_caption(self._unfiled_caption())
        self._batch_list.set_rows(rows)
        self._batch_list.set_growth(more=next_cursor is not None)
        self._batch_list.set_cursor(cursor)
        self._batch_list.focus()

    def _unfiled_caption(self) -> str:
        """`In no batch · BCP PEN · 20 of 1716 loaded · oldest first · …`"""
        acct = self._open_account()
        label = acct[1] if acct else "—"
        return (
            f"In no batch · {label}   ·   {len(self._unfiled)} of {self._unfiled_total} loaded"
            " · oldest first   ·   ! blocks a batch's close"
        )

    def _unfiled_record(self) -> dict | None:
        key = self._batch_list.cursor_key if self._batch_list is not None else None
        return next((it for it in self._unfiled if it.get("id") == key), None)

    def action_delete_row(self) -> None:
        """`d` — delete the row under the cursor, in the unfiled pane only.

        The one destructive key in the TUI (owner, 2026-09-22). Cursor row only,
        never a selection: `a`-style page selects live on the ledger and this
        pane deliberately has none. The engine keeps the row in its table, but
        since 2026-09-23 no client can restore it (undeleting is operator SQL),
        so the confirm says a delete is final.
        """
        if self._mode != "unfiled":
            return
        record = self._unfiled_record()
        if record is None:
            return
        title = record.get("title") or "—"
        amount = format_cents(record.get("amount_cents"))
        day = (record.get("date") or "")[:10]
        acct = self._open_account()
        self._confirm_delete(
            record,
            f"{title} · {amount} · {day} · {acct[1] if acct else '—'}\n"
            "It leaves every balance and report, and no screen or command can bring "
            "it back.",
        )

    def _confirm_delete(self, record: dict, message: str) -> None:
        def cb(ok: bool) -> None:
            if ok:
                self._delete_row(record)

        self.app.push_screen(ConfirmModal("Delete this transaction?", message), cb)

    @work(thread=True, group="engine-write")
    def _delete_row(self, record: dict) -> None:
        from expense import config as config_module
        from expense.http import ExpenseClient

        error = None
        try:
            cfg = config_module.ensure_loaded()
            with ExpenseClient(cfg, verbose=self.app._verbose) as client:
                client.delete(f"/transactions/{record.get('id')}")
        except Exception as exc:
            error = format_error(exc)
        self.app.call_from_thread(self._delete_finished, error)

    def _delete_finished(self, error: str | None) -> None:
        if error is not None:
            self.notify(error, title="Failed", severity="error")
            return
        self.notify("Transaction deleted.")
        self._reload_unfiled()

    def action_new(self) -> None:
        """`n` — a reconciliation for the open account, or, with no panel open,
        for the account under the cursor. Saved, it opens that account's panel
        with the cursor on the new one (owner, 2026-09-25)."""
        acct = self._open_account() or self._selected_account()
        if not acct:
            self.notify("No account selected.", severity="error")
            return

        def saved(new_id: str | None) -> None:
            if new_id is None:  # left without saving: nothing changed
                return
            self._open_aid = acct[0]
            self._resume_key = new_id
            self._load()

        self.app.push_screen(
            NewReconciliationScreen(account_id=acct[0], account_name=acct[1]), saved
        )


# --------------------------------------------------------------------------- #
# New batch form
# --------------------------------------------------------------------------- #
_R_LABELS = {
    "name": "NAME",
    "account": "ACCOUNT",
    "date_start": "DATE START",
    "date_end": "DATE END",
    "begin": "BEGIN BALANCE",
    "end": "END BALANCE",
}
_R_HINTS = {
    "name": "e.g. “April 2026” · enter to save",
    "account": "pick a bank account · ↑↓ highlight · enter select",
    "date_start": "YYYY-MM-DD · the statement's first day · it orders the batch",
    "date_end": "YYYY-MM-DD · the statement's last day",
    "begin": "signed decimal · your statement's opening balance",
    "end": "signed decimal · statement's closing balance · optional · enter saves",
}
_AMOUNTS = {"begin", "end"}
_DATES = {"date_start", "date_end"}


class NewReconciliationScreen(FormScreen):
    RESOURCE = "reconciliations"

    def __init__(self, account_id: str | None = None, account_name: str | None = None) -> None:
        super().__init__()
        self._values: dict = {}
        self._display: dict = {}
        self._accounts: list = []
        self._preset_account = account_id
        self._new_id: str | None = None
        if account_id:  # created from within an account — don't ask for it again
            self._values["account"] = account_id
            self._display["account"] = account_name or account_id[:8]
            self.crumb = ("Reconciliations", account_name or "—", "New")
        else:
            self.crumb = ("Reconciliations", "New")

    def _sequence(self) -> list[str]:
        seq = ["name"] if self._preset_account else ["name", "account"]
        return seq + ["date_start", "date_end", "begin", "end"]

    def _required(self) -> tuple[str, ...]:
        # begin: the engine has no derived mode left, so it is typed off the
        # statement. Both dates: the engine requires them (`8f22ebb`); asking
        # here refuses an empty one at the field instead of as a 422 on save.
        return ("name", "account", "date_start", "date_end", "begin")

    def _label(self, key: str) -> str:
        return _R_LABELS[key]

    def _hint_for(self, key: str) -> str:
        return _R_HINTS.get(key, "")

    def _suggests(self, key: str) -> bool:
        return key == "account"

    def _bar_value(self, key: str) -> str:
        if key in _AMOUNTS and key in self._values:
            return amount_to_text(self._values[key])
        if key in ("name", *_DATES):
            return str(self._values.get(key, "") or "")
        return ""  # account re-pick

    def _after_mount(self) -> None:
        if not self._preset_account:  # only need the account picker for standalone create
            self._load_accounts()

    @work(thread=True, exclusive=True)
    def _load_accounts(self) -> None:
        from expense import config as config_module

        try:
            cfg = config_module.ensure_loaded()
            body = accounts_cmd.fetch_accounts(cfg, **screen_fetch_kwargs(self.app))
        except Exception as exc:  # surface engine/config errors in-app, don't crash
            self.app.call_from_thread(self.notify, format_error(exc), severity="error")
            return
        accounts = account_choices(items_of(body), include_people=False)
        self.app.call_from_thread(self._set_accounts, accounts)

    def _set_accounts(self, accounts: list) -> None:
        self._accounts = accounts
        self._recompute(self.query_one("#bar", Input).value)
        self._refresh_view()

    # ---- suggestions -----------------------------------------------------
    def _recompute(self, text: str) -> None:
        key = self._key
        needle = text.strip()
        if key == "account":
            # `quickadd.names.matches` — the one matcher every picker in the
            # app uses: substring, case-blind AND accent-blind. This was the
            # last one still on a plain `.lower()`, so `bcp credito` found no
            # `BCP Crédito` here while the same text matched everywhere else.
            self._suggestions = [(i, n, c) for (i, n, c) in self._accounts if matches(needle, n)]
        else:
            self._suggestions = []
        self._suggest_idx = 0

    # ---- commit ----------------------------------------------------------
    def on_input_submitted(self, event: Input.Submitted) -> None:
        key = self._key
        text = self.query_one("#bar", Input).value.strip()
        if key == "name":
            if not text:
                self.notify("Name is required.", severity="error")
                return
            self._values["name"] = self._display["name"] = text
            self._advance()
        elif key == "account":
            picked = self._suggestions[self._suggest_idx] if self._suggestions else None
            if picked is None:
                self.notify(f"No account matches “{text}”.", severity="error")
                return
            self._values["account"] = picked[0]
            self._display["account"] = picked[1]
            self._advance()
        elif key in _DATES:
            # Both required. The check is the exact day shape the engine takes
            # (engine-spec *Date inputs*), caught here at the field rather
            # than as a 422 on save; the typed text is what gets sent.
            if not text:
                self.notify(f"{_R_LABELS[key].capitalize()} is required.", severity="error")
                return
            if not is_calendar_day(text):
                self.notify(f"{_R_LABELS[key].title()}: use YYYY-MM-DD.", severity="error")
                return
            self._values[key] = self._display[key] = text
            self._advance()
        elif key == "begin":
            cents = parse_amount(text)
            if cents is None:
                self.notify("Begin balance: a signed decimal, e.g. 9580.00", severity="error")
                return
            self._values["begin"] = cents
            self._display["begin"] = format_cents(cents)
            self._advance()
        elif key == "end":
            if text:
                cents = parse_amount(text)
                if cents is None:
                    self.notify("End balance: a signed decimal, e.g. 9460.00", severity="error")
                    return
                self._values["end"] = cents
                self._display["end"] = format_cents(cents)
            else:
                self._values.pop("end", None)
                self._display.pop("end", None)
            self.action_submit()
            return
        self._refresh_view()

    # ---- submit ----------------------------------------------------------
    def _payload(self) -> dict:
        self._new_id = str(uuid.uuid4())
        payload = {
            "id": self._new_id,
            "account_id": self._values["account"],
            "name": self._values["name"],
        }
        # calendar days, sent as typed — the engine refuses any datetime here
        payload["date_start"] = self._values["date_start"]
        payload["date_end"] = self._values["date_end"]
        # never send beginning_balance_source — the engine's request schemas are
        # extra="forbid" since the 2026-08-06 de-chaining, so it would 422
        payload["beginning_balance_cents"] = self._values["begin"]
        if self._values.get("end") is not None:
            payload["ending_balance_cents"] = self._values["end"]
        return payload

    def _done(self) -> None:
        """Dismiss with the new id — minted here, in `_payload` — so the browse
        can land its cursor on the reconciliation just made."""
        self.notify("Reconciliation created.")
        self.dismiss(self._new_id)


# --------------------------------------------------------------------------- #
# Working / detail screen — assign transactions, complete / revert / delete
# --------------------------------------------------------------------------- #
def _fetch_all_txns(cfg, **kw) -> list[dict]:
    """Every matching transaction, cursor-paged at the engine cap.

    A single limit=500 request 422s live (cap is 200) and silently truncates
    the checklist; page through instead (backlog 3.3 → 6.4a).
    """
    return fetch_all_cursor_pages(
        lambda limit, after: transactions_cmd.fetch_transactions(
            cfg, after=after, limit=limit, **kw
        )
    )


def _status_span(status: str, palette: Palette) -> tuple[str, str]:
    """(text, style) for the header's status word — completed→success, draft→warning."""
    return status, palette.success if status == "completed" else palette.warning


def _txn_sub(it: dict, cat_names: dict, tag_names: dict) -> str:
    """The dim category · #tags · note sub-line for a transaction row."""
    parts = []
    cat = cat_names.get(it.get("category_id"))
    if cat:
        parts.append(cat)
    tags = it.get("hashtag_ids") or []
    if tags:
        parts.append(" ".join("#" + tag_names.get(t, t[:6]) for t in tags))
    note = it.get("description")
    if note:
        parts.append(f'"{note}"')
    return "  ·  ".join(parts)


class ReconciliationDetailScreen(
    HelpBindingMixin,
    EngineWriteMixin,
    ContentSwapLockMixin,
    AdaptiveRowsMixin,
    Screen,
):
    """One batch: header + a transaction checklist (draft) or read-only list
    (completed). `space` toggles membership; `c`/`u`/`d` complete/revert/delete;
    `r` refetches the batch + checklist (r = refresh everywhere, never a write)."""

    BINDINGS = [
        ("escape", "back", "Back"),
        ("r", "reload", "Refresh"),
        ("c", "complete", "Complete"),
        ("u", "revert", "Revert"),
        ("d", "delete", "Delete"),
        *HelpBindingMixin.BINDINGS,
    ]

    def __init__(self, record: dict) -> None:
        super().__init__()
        self._record = record
        self._id = record.get("id")
        self._account_id = record.get("account_id")
        self._busy = False
        self._list: CheckList | None = None
        self._acct_name: str | None = None  # resolved worker-side in _load_txns
        # last painted rows, cached so a theme change repaints from memory
        # instead of re-fetching (backlog §5)

    @property
    def _completed(self) -> bool:
        return self._record.get("status") == 2

    def compose(self) -> ComposeResult:
        yield Breadcrumb(("Reconciliations", self._record.get("name") or "—"), id="crumb")
        yield Static("", id="rhead")
        yield Static("", id="rwarn")  # the gap report; hidden until a complete carries one
        yield Container(id="rlist")
        yield Static("", id="rhint")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#rwarn", Static).display = False
        self._render_header()
        # First fetch waits for the first layout pass: _populate sizes the
        # checklist to #rlist's real height (adaptive rows, 2026-07-13).
        self.call_after_refresh(self._load_txns)

    # ---- adaptive window (2026-07-13) --------------------------------------
    def _checklist_items(self) -> int:
        """Items-per-page = what fits #rlist at two lines each.

        The chrome is `LIST_FRAME_LINES` — the same frame every other list
        pays, with no caption here (the crumb and #rhead both name the batch).

        ⚠️ **This read a hand-written `4` until 2026-09-20, and it was wrong.**
        It counted the border plus the column header and its rule, and omitted
        the two blank edge lines `box.SIMPLE_HEAD` draws — the identical
        miscount that was fixed in `LIST_FRAME_LINES` on 2026-08-29 and missed
        here because a literal does not track a constant. At two lines per
        item it asked for one item too many and overflowed #rlist by two lines
        at every height below the cap. #rlist is `overflow: hidden`, so it
        clipped in silence: the page status on this screen had never once been
        visible.
        """
        return self.fit_rows("#rlist", chrome=self.LIST_FRAME_LINES, lines_per_row=2)

    def on_resize(self, _event) -> None:
        if self._list is not None and self._list.is_attached:
            self._list.set_page_size(self._checklist_items())

    def _apply_fresh_record(self, fresh: dict) -> None:
        """Main-thread: rebind _record from a refreshed batch, then repaint the
        header. Called via call_from_thread so the worker never mutates screen
        state directly, and a cancelled stale load can't clobber _record (backlog §5)."""
        self._record = fresh
        self._render_header()

    def _set_acct_name(self, name: str | None) -> None:
        self._acct_name = name

    def _render_header(self) -> None:
        r = self._record
        palette = PALETTE
        # short-id placeholder until _load_txns resolves the name worker-side —
        # a full-table SQLite read here blocked first paint (backlog 6.5c)
        acct = self._acct_name or resolve_name(self._account_id, {})
        status = reconcile_cmd.format_status(r.get("status"))
        begin = amount_cell(r.get("beginning_balance_cents"), palette, BALANCE_RULE)
        end = amount_cell(r.get("ending_balance_cents"), palette, BALANCE_RULE)
        diff = difference_cell(r.get("difference_cents"), palette)
        text = Text.assemble(
            (r.get("name") or "—", "bold"),
            ("  ·  ", "dim"),
            (acct, ""),
            ("  ·  ", "dim"),
            (_period(r), "dim"),
            ("\n", ""),
            ("begin ", "dim"),
            begin if isinstance(begin, Text) else (begin, ""),
            ("    end ", "dim"),
            end if isinstance(end, Text) else (end, ""),
            ("    diff ", "dim"),
            diff if isinstance(diff, Text) else (diff, ""),
            ("    status ", "dim"),
            _status_span(status, palette),
        )
        self.query_one("#rhead", Static).update(text)
        hint = (
            "read-only while completed · u revert to edit · r refresh · esc back"
            if self._completed
            else "space toggle in/out of this batch · c complete · u revert · d delete"
            " · r refresh · esc back"
        )
        self.query_one("#rhint", Static).update(Text(hint, style="dim"))

    # own load group (mirrors SectionScreen._load's "section-load"): a refresh
    # cancels stale refreshes only, never a run_write ("engine-write") worker
    @work(thread=True, exclusive=True, group="recon-detail-load")
    def _load_txns(self, refresh_record: bool = False) -> None:
        from expense import config as config_module

        # Exclusive cancellation is cooperative: a superseded load keeps
        # running, so it must stop painting or two _populate swaps interleave
        # and stack duplicate checklists (backlog 6.2a).
        worker = get_current_worker()
        try:
            cfg = config_module.ensure_loaded()
            kw = screen_fetch_kwargs(self.app)
            if refresh_record:
                # refetch the batch itself too — a stale header/status would
                # misrepresent balances and the read-only gate. There is no
                # read by id (engine, 2026-09-23): the account's list is whole,
                # so a row missing from it is a row that was deleted.
                listed = reconcile_cmd.fetch_reconciliations(cfg, account_id=self._account_id, **kw)
                fresh = next((r for r in items_of(listed) if r.get("id") == self._id), None)
                if worker.is_cancelled:
                    return
                if fresh is None:
                    self.app.call_from_thread(self._record_gone)
                    return
                # Marshal onto the main thread — worker mustn't mutate screen state.
                self.app.call_from_thread(self._apply_fresh_record, fresh)
            # assigned-to-this-batch transactions (always; any date)
            assigned = _fetch_all_txns(cfg, reconciliation=self._id, **kw)
            available = []
            if not self._completed:  # draft also offers the account's unassigned txns in range
                available = [
                    it
                    for it in _fetch_all_txns(
                        cfg,
                        account=self._account_id,
                        date_from=self._record["date_start"],
                        date_to=self._record["date_end"],
                        **kw,
                    )
                    if it.get("reconciliation_id") is None
                ]
            cat_names = load_category_name_map()
            tag_names = load_hashtag_name_map()
            acct_name = resolve_name(self._account_id, load_account_name_map())
        except Exception as exc:  # surface engine/config errors in-app, don't crash
            if not worker.is_cancelled:
                self.app.call_from_thread(self.notify, format_error(exc), severity="error")
            return
        rows, checked, seen = [], [], set()
        for it in [*assigned, *available]:
            key = it.get("id")
            if key in seen:
                continue
            seen.add(key)
            if it.get("reconciliation_id") == self._id:
                checked.append(key)
            rows.append(
                (
                    key,
                    it.get("title"),
                    it.get("amount_cents"),
                    (it.get("date") or "")[:10],
                    _txn_sub(it, cat_names, tag_names),
                )
            )
        if worker.is_cancelled:
            return
        self.app.call_from_thread(self._set_acct_name, acct_name)
        self.app.call_from_thread(self._render_header)  # picks up _acct_name
        self.app.call_from_thread(self._populate, rows, checked)

    async def _populate(self, rows: list, checked: list) -> None:
        async with self._content_lock():
            container = self.query_one("#rlist", Container)
            await container.remove_children()
            empty = (
                "(no transactions in this batch)"
                if self._completed
                else "(no transactions for this account in range)"
            )
            self._list = CheckList(
                rows,
                checked,
                read_only=self._completed,
                empty=empty,
                palette=PALETTE,
                page_size=self._checklist_items(),  # adaptive window (2026-07-13)
            )
            await container.mount(self._list)
            if not self._completed:
                self._list.focus()

    # ---- assign / unassign ----------------------------------------------
    def on_check_list_toggled(self, event: CheckList.Toggled) -> None:
        # The mixin queue sends one PUT at a time, in order (backlog 6.4b).
        # Success is silent — the checklist toggle already shows the new state.
        self.run_write(
            "PUT",
            f"/transactions/{event.key}",
            json_body={"reconciliation_id": self._id if event.checked else None},
            on_success=lambda: None,
            on_error=self._assign_failed,
        )

    def _assign_failed(self, message: str) -> None:
        # The mixin already dropped the queued intents (they were made against
        # a checklist state the engine just contradicted) — resync to truth.
        self.notify(message, title="Couldn't update", severity="error")
        self._load_txns()

    # ---- status actions --------------------------------------------------
    def action_back(self) -> None:
        self.dismiss()

    def action_reload(self) -> None:
        self._load_txns(refresh_record=True)

    def _record_gone(self) -> None:
        self.notify("This reconciliation no longer exists.", severity="error")
        self.dismiss()

    def action_complete(self) -> None:
        if self._completed:
            self.notify("Already completed.")
            return
        # No ≥1-assigned pre-guard: the engine 422s an empty complete and
        # run_write toasts its message (thin wrapper, backlog 2.5).
        n = len(self._list.checked) if self._list else 0
        self._confirm(
            "Complete reconciliation?",
            f"Locks amount/account/title/date on the {n} assigned transaction(s).",
            lambda: self._status_action(
                "POST",
                f"/reconciliations/{self._id}/complete",
                2,
                "completed",
                on_response=self._report_gap,
            ),
        )

    def action_revert(self) -> None:
        # No completed-only pre-guard: the engine treats revert-on-draft as
        # an idempotent 200 no-op (thin wrapper, backlog 2.5).
        self._confirm(
            "Revert to draft?",
            "Unlocks the assigned transactions and this batch's balances.",
            lambda: self._status_action(
                "POST", f"/reconciliations/{self._id}/revert", 1, "reverted to draft"
            ),
        )

    def action_delete(self) -> None:
        # No draft-only pre-guard: deleting a completed reconciliation 409s
        # engine-side ("… Revert to draft first.") and run_write toasts that
        # message (thin wrapper, backlog 2.5).
        self._confirm(
            "Delete reconciliation?",
            "Detaches its transactions (they are not deleted) and removes the batch.",
            lambda: self._status_action("DELETE", f"/reconciliations/{self._id}", None, "deleted"),
        )

    def _confirm(self, title: str, message: str, action) -> None:
        def cb(ok: bool) -> None:
            if ok:
                action()

        self.app.push_screen(ConfirmModal(title, message), cb)

    def _status_action(self, method: str, path: str, new_status, verb: str, **kw) -> None:
        if self._busy:
            return
        self._busy = True
        # Any status change invalidates a gap report: it was true of the record
        # as it stood one write ago (a revert unseals the very window it named).
        self._show_warnings([])
        self.run_write(
            method,
            path,
            on_success=lambda: self._action_done(new_status, verb),
            on_error=lambda m: self._action_failed(m, verb),
            **kw,
        )

    def _report_gap(self, body: dict) -> None:
        """Surface `complete`'s `warnings` — the uncovered-days report (2026-09-20).

        Shown as a line under the header rather than a toast: the whole value of
        this message is not being missed, and a toast fades in five seconds. It
        stays for as long as the screen does, survives `r`, and clears on the
        next status change. Pick B of
        mockups/expense-world-gap-warning.html (owner, 2026-09-22).

        The text is the engine's own sentence, verbatim — the dates in it are
        prose, not fields, so this side neither parses them nor goes looking for
        the rows they name. The review surface for that is
        `transactions list --unreconciled`.
        """
        warnings = body.get("warnings")
        self._show_warnings(warnings if isinstance(warnings, list) else [])

    def _show_warnings(self, warnings: list) -> None:
        line = self.query_one("#rwarn", Static)
        lines = [str(w) for w in warnings if w]
        if not lines:
            line.display = False
            line.update("")
            return
        line.update(Text("\n".join(f"⚠ {text}" for text in lines), style=PALETTE.warning))
        line.display = True

    def _action_failed(self, message: str, verb: str) -> None:
        self._busy = False
        self.notify(message, title=f"Couldn't {verb.split()[0]}", severity="error")

    def _action_done(self, new_status, verb: str) -> None:
        self._busy = False
        self.notify(f"Reconciliation {verb}.")
        if verb == "deleted":
            self.dismiss()
            return
        self._record["status"] = new_status
        self._render_header()
        self._load_txns()
