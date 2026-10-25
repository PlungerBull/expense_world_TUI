"""Reconciliations — list, new batch, and the working/detail screen.

Per-account bank-statement batches. The browse opens on the accounts alone;
`⏎` on one reads that account's reconciliations (`GET /reconciliations?
account_id=`, whole) and opens them in a panel under the accounts, the
cursor in it. They stand in the order the engine returns them: `date_start`
ascending, then creation time, oldest first
(contract: "Reconciliations", "Ordering"). There `⏎` opens the working
screen, `n` creates one for the account, `u` swaps the panel for the
account's bank lines in no batch (`GET /bank-lines`, newest first, a split
purchase one row), and `esc` closes the panel. Nothing is read for an
account until you press `⏎` on it.

New batch: name › account › date start › date end › begin › end. Both balances
are typed off the paper statement — the engine has no derived (chained) begin,
so `beginning_balance_cents` is required. Both dates are required too
(contract: POST /v1/reconciliations), and are
calendar days sent as typed (contract: "Date inputs"); the form refuses any other shape at
the field. POST /reconciliations.

New card statement (NewCardStatementScreen), `n` on a card account: name ›
date start › date end › this account's begin › end › the other account's begin
› end, the two accounts stated on a line of their own. One POST /reconciliations
with `twin` creates both halves (contract: POST /v1/reconciliations).

Working screen (ReconciliationDetailScreen): a checklist of bank lines — the
batch's, then the account's in its period that are in no batch (draft) — or a
read-only list of the batch's lines (completed), read from `GET /bank-lines`
so a purchase split into parts is one row with its total. `space` toggles
membership (PUT `reconciliation_id` on one part, which moves the whole line)
and reads the batch and its list again; `c`/`u`/`d` complete/revert/delete;
`r` refetches the batch + checklist. Complete
needs ≥1 transaction and locks amount/account/title/date on them; delete is
draft-only and just detaches the transactions. Completing also needs the
ending balance (contract: POST /v1/reconciliations/{reconciliation_id}/complete,
"The ending balance must be entered"): `c` on a draft that has none first asks
for it in a box, saves it with PUT /reconciliations/{id}, then asks the usual
"Complete reconciliation?".
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

from expense import formatting, reads
from expense.dates import is_calendar_day
from expense.errors import format_error
from expense.formatting import (
    bank_line_columns,
    bank_line_part_count,
    format_cents,
    resolve_name,
    signed_cents,
)
from expense.quickadd.money import amount_to_text, parse_amount
from expense.quickadd.names import matches
from expense.reads import (
    account_choices,
    fetch_all_cursor_pages,
    items_of,
    load_account_name_map,
    statement_partners,
)
from expense.tui.screens._base import (
    AdaptiveRowsMixin,
    ContentSwapLockMixin,
    EngineWriteMixin,
    SectionScreen,
    bank_line_delete_message,
    bank_line_delete_question,
    call_while_attached,
    list_refusal_text,
    screen_fetch_kwargs,
    transaction_delete_message,
)
from expense.tui.screens._form import FormScreen, form_bindings
from expense.tui.screens._growing import GrowingRead, read_first
from expense.tui.screens.help import HelpBindingMixin
from expense.tui.screens.modals import AmountPromptModal, ConfirmModal
from expense.tui.theme import ACCENT, AMOUNT_RULE, BALANCE_RULE, PALETTE, Palette
from expense.tui.widgets.cells import amount_cell, difference_cell, operation_cell
from expense.tui.widgets.checklist import CheckList
from expense.tui.widgets.cursor_list import CursorList
from expense.tui.widgets.header import Breadcrumb

# Status labels + period formatting are owned by expense/formatting.py
# (format_status / format_period) — one copy, per the §5 rule.
_period = formatting.format_period

_BATCH_HEADERS = ["Name", "Period", "Begin", "End", "Diff", "Status"]
_UNFILED_HEADERS = ["", "Date", "Title", "Operation", "Amount"]

#: What the "no batch" list asks the engine for, with the account and no dates:
#: this account's bank lines in no reconciliation, any day. The list and its
#: count both take it (`GET /bank-lines`, `GET /bank-lines/count`). The engine
#: lists them newest first, its one order (contract: GET /v1/bank-lines); the
#: list opens with the `GROW_STEP` newest and `pgdn` appends the next ones.
UNFILED_FILTER = {"unreconciled": True}


def blocking_windows(recons: list[dict], account_id) -> list[tuple[str, str, str]]:
    """`(first_day, last_day, name)` for every batch on this account.

    Used only to draw the `!` hint beside a row (see `unfiled_rows`). Drafts are
    included on purpose: a draft's window is exactly what an unfiled row inside
    it will refuse when you try to close it, which is the question the flag
    answers. Completed windows are in here too — an unfiled row inside one is an
    anomaly the engine's close check would not allow to arise today, and it is
    precisely what the pane exists to surface in older data.
    """
    windows = []
    for r in recons:
        if r.get("account_id") != account_id:
            continue
        windows.append((r["date_start"], r["date_end"], r.get("name") or "—"))
    return windows


def unfiled_rows(lines: list[dict], windows, palette=None) -> list:
    """Rows for the "no batch" list, one per bank line, in the order given (the
    engine's, newest first), `!` on the ones inside a window.

    Each row is one line of the bank's own columns, `bank_line_columns`: the
    day, the title, the operation code (a dim `—` when there is none) and the
    signed `net_cents`. A purchase split into parts is one row with its title
    alone and its total; nothing on the row says it is split.

    **The flag is a hint, not a ruling.** It compares each row's date against
    windows this screen already holds, so it costs no request — but the engine
    is the authority at close time (it resolves a window in the user's
    timezone), so an edge day may differ. Nothing downstream reads the flag: it
    only tells you which rows are worth opening first.
    """
    rows = []
    for line in lines:
        day, title, operation, net_cents = bank_line_columns(line)
        blocked = any(start <= day <= end for start, end, _name in windows)
        if not blocked:
            flag: object = ""
        else:
            flag = Text("!", style=palette.warning) if palette else "!"
        rows.append(
            (
                line.get("id"),
                [
                    flag,
                    day,
                    title or "(untitled)",
                    operation_cell(operation),
                    amount_cell(net_cents, palette, AMOUNT_RULE),
                ],
            )
        )
    return rows


def is_split_line(line: object) -> bool:
    """A bank line holding more than one part, as the engine counts them."""
    return bank_line_part_count(line) > 1


def lone_transaction(line: dict) -> dict | None:
    """A line never split as the transaction it is: its one part, the
    transaction response, with `amount_cents` signed the app's way. The part
    arrives as a magnitude and its `transaction_type`
    (contract: GET /v1/bank-lines/{bank_line_id}); `signed_cents` signs it, so
    the edit form and the delete question get the record a ledger read gives.
    None for a split line or a line with no part."""
    if is_split_line(line):
        return None
    part = first_part(line)
    return None if part is None else {**part, "amount_cents": signed_cents(part)}


def first_part(line: dict) -> dict | None:
    """The line's first part, the one a write on the line names; None when
    the read holds no part with an id."""
    parts = line.get("parts")
    if not isinstance(parts, list) or not parts:
        return None
    part = parts[0]
    return part if isinstance(part, dict) and part.get("id") else None


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
            formatting.format_status(status),
        ]
        rows.append((it.get("id"), cells, "dim" if status == 2 else ""))
    return rows


class _AccountList(CursorList):
    """The browse's account list. Only `enter` changes: on this list it opens
    the account's panel, so the footer names that instead of `Open`."""

    BINDINGS = [Binding("enter", "select", "Its reconciliations")]


class _PanelList(CursorList):
    """The panel under the accounts. It lists two things: a
    reconciliation, which `enter` opens, or a row in no batch, which `enter`
    edits — so the footer says `Edit` there. Two bindings on one key: Textual takes the first whose
    `check_action` allows it."""

    BINDINGS = [
        Binding(
            "enter",
            "edit_row",
            "Edit",
            tooltip="Edit the row: its date, title, operation, amount or account",
        ),
        Binding("enter", "select", "Open"),
    ]
    #: The `?` card lists these only while `check_action` allows them (help.py).
    CARD_FOLLOWS_CHECK = frozenset({"edit_row", "select"})

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
    """Accounts first; one account's reconciliations on `⏎`.

    The screen opens on the account list alone, and nothing about
    reconciliations is read until you press `⏎` on an account: the engine lists
    them one account at a time (`GET /reconciliations?account_id=`, whole, in
    the order the module docstring gives), so moving the cursor costs nothing.
    `⏎` reads that account's list and opens the panel under the accounts with
    the cursor in it. There `⏎` opens a reconciliation, `n` creates one, `u`
    swaps the panel for the account's rows in no batch, and `esc` closes the
    panel.
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
        # a card account → its other half's (id, name, currency, statement code)
        self._partners: dict = {}
        self._acct_idx = 0
        self._open_aid: str | None = None  # the account whose panel is open
        self._mode = "accts"  # "accts" | "batches" | "unfiled"
        self._unfiled: list = []  # every bank line in no batch loaded so far, newest first
        # the cursor past the last row, the count, and `pgdn` — shared with the ledger
        self._unfiled_grow = GrowingRead(self, on_more=self._append_unfiled)
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
        accts = items_of(reads.fetch_accounts(cfg, **kw))
        accounts = account_choices(accts, include_people=False, with_balance=True)
        recons = None
        if self._open_aid is not None:
            recons = items_of(reads.fetch_reconciliations(cfg, account_id=self._open_aid, **kw))
        return {"recons": recons, "accounts": accounts, "partners": statement_partners(accts)}

    def _selected_account(self):
        return self._accounts[self._acct_idx] if self._accounts else None

    def _open_account(self):
        return next((a for a in self._accounts if a[0] == self._open_aid), None)

    def _batch_caption(self) -> str:
        acct = self._open_account()
        return f"Reconciliations · {acct[1] if acct else '—'}   ·   oldest → newest"

    # ---- adaptive window: the panel splits #content -----------------------
    def pane_rows(self) -> int:
        """Rows per list. Alone, the account list fills #content;
        with the panel open the two split it equally — auto-height
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
        self._partners = data["partners"]
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
        self._unfiled = []
        self._unfiled_grow.reset()
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
        if self._mode == "unfiled" and event.control is self._batch_list:
            return
        # Source guard: only the account list moves the account
        # cursor, and only while it is the list in use. Moving it reads nothing.
        if self._mode != "accts" or event.control is not self._accts_list:
            return
        self._acct_idx = event.index

    def on_cursor_list_selected(self, event: CursorList.Selected) -> None:
        if self._mode == "unfiled":
            # `⏎` opens the Edit form on the line, the bank's columns only:
            # date and account are the two remedies for a row in no batch
            line = self._unfiled_record()
            if line is not None and first_part(line) is not None:
                from expense.tui.screens.edit_form import BankLineEditFormScreen

                acct = self._open_account()
                self.app.push_screen(
                    BankLineEditFormScreen(line=line, currency=acct[2] if acct else None),
                    lambda saved: saved and self._reload_unfiled(),  # `esc` keeps the cursor
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
            acct = self._open_account()
            self.app.push_screen(
                ReconciliationDetailScreen(item, currency=acct[2] if acct else None),
                lambda _result: self._load(),
            )

    @work(thread=True, exclusive=True, group="recon-batches")
    def _load_batches(self, account_id: str) -> None:
        """`⏎` on an account: read its reconciliations. A read that fails
        leaves the panel closed, with a toast."""
        from expense import config as config_module

        worker = get_current_worker()
        try:
            cfg = config_module.ensure_loaded()
            body = reads.fetch_reconciliations(
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
        self._unfiled = []
        self._unfiled_grow.reset()
        if self._batch_list is not None:
            self._batch_list.set_growth(more=None)
            self._batch_list.set_headers(_BATCH_HEADERS, align_right={2, 3, 4})
            self._batch_list.set_caption(self._batch_caption())
            self._batch_list.set_rows(batch_rows(self._recons, palette=PALETTE))
            self._batch_list.focus()
        self.refresh_bindings()

    def _reload_unfiled(self) -> None:
        """After `⏎` edit or `d`: the newest `GROW_STEP` again, the cursor on
        row 1 (any write starts the list over, like any app's list). A row whose
        date or account moved is gone, which is the point of editing it."""
        if self._open_aid and self._mode == "unfiled" and self._batch_list is not None:
            self._unfiled_grow.reset()
            self._unfiled_busy = True
            self._load_unfiled(self._open_aid)

    async def action_reload(self) -> None:
        """`r` — in the unfiled pane, start again from the newest `GROW_STEP`;
        anywhere else, reload the screen (an open panel stays open)."""
        if self._mode == "unfiled":
            if not self._unfiled_busy:
                self._reload_unfiled()
            return
        if self._batch_list is not None:
            self._resume_key = self._batch_list.cursor_key
        await super().action_reload()

    # ---- the unfiled pane ------------------------------------------------
    def action_unfiled(self) -> None:
        """`u` — swap the panel to the open account's rows in no batch.

        Only while a panel is open: the panel is the slot
        it swaps into, and the account whose rows it lists is the open one.
        `esc` swaps it back. Reconciliation work stays in the
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

    def _unfiled_page(self, account_id: str):
        """`(limit, after) -> body`: this account's bank lines in no batch,
        newest first (worker thread)."""
        from expense import config as config_module

        def page(limit: int, after: str | None) -> dict:
            return reads.fetch_bank_lines(
                config_module.ensure_loaded(),
                account=account_id,
                after=after,
                limit=limit,
                **UNFILED_FILTER,
                **screen_fetch_kwargs(self.app),
            )

        return page

    @work(thread=True, exclusive=True, group="recon-unfiled")
    def _load_unfiled(self, account_id: str) -> None:
        """The first rows and the count, together: the pane
        shows nothing until both are in, and a count that cannot be read fails
        the pane rather than leave rows beside a guessed number."""
        from expense import config as config_module

        worker = get_current_worker()
        try:
            cfg = config_module.ensure_loaded()
            kw = screen_fetch_kwargs(self.app)
            items, next_cursor, total = read_first(
                self._unfiled_page(account_id),
                lambda: reads.count_bank_lines(cfg, account=account_id, **UNFILED_FILTER, **kw),
            )
        except Exception as exc:
            if not worker.is_cancelled:
                self.app.call_from_thread(self._unfiled_failed, format_error(exc))
            return
        if worker.is_cancelled:
            return
        self.app.call_from_thread(self._show_unfiled, items, total, next_cursor)

    def on_cursor_list_more_requested(self, event: CursorList.MoreRequested) -> None:
        """`pgdn` in the unfiled pane: the next `GROW_STEP` rows, appended."""
        if self._mode != "unfiled" or self._unfiled_busy or not self._open_aid:
            return
        self._unfiled_grow.grow(self._unfiled_page(self._open_aid))

    def _append_unfiled(self, items: list, more: bool) -> None:
        if self._mode != "unfiled" or self._batch_list is None:  # esc landed mid-read
            return
        self._unfiled.extend(items)
        windows = blocking_windows(self._recons, self._open_aid)
        rows = unfiled_rows(items, windows, palette=PALETTE)
        self._batch_list.set_caption(self._unfiled_caption())
        self._batch_list.append_rows(rows, more=more)
        self._batch_list.refresh_bindings()

    def _unfiled_failed(self, message: str) -> None:
        self._unfiled_busy = False
        self._show_batches()
        self.notify(message, title="Failed", severity="error")

    def _show_unfiled(self, items: list, total: int, next_cursor: str | None) -> None:
        self._unfiled_busy = False
        if self._mode != "unfiled" or self._batch_list is None:  # esc landed mid-read
            return
        self._unfiled = list(items)
        self._unfiled_grow.took(next_cursor, total)
        # the panel already holds this account's reconciliations: the `!`
        # windows cost no read of their own
        windows = blocking_windows(self._recons, self._open_aid)
        rows = unfiled_rows(items, windows, palette=PALETTE)
        self._batch_list.set_caption(self._unfiled_caption())
        self._batch_list.set_rows(rows)
        self._batch_list.set_growth(more=self._unfiled_grow.more)
        self._batch_list.set_cursor(0)
        self._batch_list.focus()
        self._batch_list.refresh_bindings()

    def _unfiled_caption(self) -> str:
        """`In no batch · BCP PEN · 20 of 1716 loaded · newest first · …`"""
        acct = self._open_account()
        label = acct[1] if acct else "—"
        return (
            f"In no batch · {label}   ·   {len(self._unfiled)} of {self._unfiled_grow.total} loaded"
            " · newest first   ·   ! blocks a batch's close"
        )

    def _unfiled_record(self) -> dict | None:
        """The bank line under the cursor in the "no batch" list, as listed."""
        key = self._batch_list.cursor_key if self._batch_list is not None else None
        return next((it for it in self._unfiled if it.get("id") == key), None)

    def action_delete_row(self) -> None:
        """`d` — delete the line under the cursor, in the unfiled pane only.

        Cursor row only, never a selection, and the question says a delete is
        final. The line in hand is the list's own read, so nothing is read
        before asking. A split purchase (`part_count` above 1) goes whole, in
        one `DELETE /bank-lines/{id}` (contract: DELETE /v1/bank-lines/{bank_line_id}),
        after the question naming its part count; a line never split goes as
        its one transaction, in `DELETE /transactions/{id}`, after the ledger's
        question. Why: docs/decisions.md "Rows in no batch live in the
        reconciliation view".
        """
        if self._mode != "unfiled":
            return
        line = self._unfiled_record()
        if line is None:
            return
        acct = self._open_account()
        account_name = acct[1] if acct else "—"
        if is_split_line(line):
            self.confirm_delete(
                "bank-lines",
                line.get("id"),
                bank_line_delete_question(line),
                bank_line_delete_message(line, account_name),
                done="Transaction deleted.",
                after=self._reload_unfiled,
            )
            return
        record = lone_transaction(line)
        if record is None:
            return
        self.confirm_delete(
            "transactions",
            record.get("id"),
            "Delete this transaction?",
            transaction_delete_message(record, account_name),
            done="Transaction deleted.",
            after=self._reload_unfiled,
        )

    def action_new(self) -> None:
        """`n` — a reconciliation for the open account, or, with no panel open,
        for the account under the cursor. Saved, it opens that account's panel
        with the cursor on the new one. On a card account it is the card
        statement's form, both halves in one write, and the cursor lands on
        this account's half."""
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

        partner = self._partners.get(acct[0])
        form = (
            NewReconciliationScreen(account_id=acct[0], account_name=acct[1])
            if partner is None
            else NewCardStatementScreen(account=acct[:3], partner=partner[:3], code=partner[3])
        )
        self.app.push_screen(form, saved)


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
    "name": "e.g. “April 2026” · enter to go on",
    "account": "pick a bank account · ↑↓ highlight · enter select",
    "date_start": "YYYY-MM-DD · the statement's first day · it orders the batch",
    "date_end": "YYYY-MM-DD · the statement's last day",
    "begin": "signed decimal · your statement's opening balance",
    "end": "signed decimal · statement's closing balance · optional · enter saves",
}
#: A balance's keys: the reconciliation's own, and on a card statement's form
#: the other half's too (`twin_…`).
_BEGINS = {"begin", "twin_begin"}
_ENDS = {"end", "twin_end"}
_AMOUNTS = _BEGINS | _ENDS
_BEGIN_UNREADABLE = "Begin balance: a signed decimal, e.g. 9580.00"
#: The note for an ending balance the money parser cannot read — the New
#: Reconciliation form's and the batch screen's ending-balance box.
_END_UNREADABLE = "End balance: a signed decimal, e.g. 9460.00"
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
        # statement. Both dates: the engine requires them
        # (contract: POST /v1/reconciliations); asking here refuses an empty
        # one at the field instead of as a 422 on save.
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
            body = reads.fetch_accounts(cfg, **screen_fetch_kwargs(self.app))
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
            # app uses: substring, case-blind AND accent-blind, so `bcp credito`
            # finds `BCP Crédito` here as it does everywhere else.
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
            # (contract: "Date inputs"), caught here at the field rather
            # than as a 422 on save; the typed text is what gets sent.
            if not text:
                self.notify(f"{_R_LABELS[key].capitalize()} is required.", severity="error")
                return
            if not is_calendar_day(text):
                self.notify(f"{_R_LABELS[key].title()}: use YYYY-MM-DD.", severity="error")
                return
            self._values[key] = self._display[key] = text
            self._advance()
        elif key in _BEGINS:
            cents = parse_amount(text)
            if cents is None:
                self.notify(_BEGIN_UNREADABLE, severity="error")
                return
            self._values[key] = cents
            self._display[key] = format_cents(cents)
            self._advance()
        elif key in _ENDS:
            # optional: an empty line leaves it out (`ending_balance_cents` null)
            if text:
                cents = parse_amount(text)
                if cents is None:
                    self.notify(_END_UNREADABLE, severity="error")
                    return
                self._values[key] = cents
                self._display[key] = format_cents(cents)
            else:
                self._values.pop(key, None)
                self._display.pop(key, None)
            self._advance()  # on the last line, the save
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
        # never send beginning_balance_source — the engine forbids it, so it
        # would 422 (contract: POST /v1/reconciliations)
        payload["beginning_balance_cents"] = self._values["begin"]
        if self._values.get("end") is not None:
            payload["ending_balance_cents"] = self._values["end"]
        return payload

    def _done(self) -> None:
        """Dismiss with the new id — minted here, in `_payload` — so the browse
        can land its cursor on the reconciliation just made."""
        self.notify("Reconciliation created.")
        self.dismiss(self._new_id)


class NewCardStatementScreen(NewReconciliationScreen):
    """A card statement: both halves in one form and one write (pane 2 A of
    docs/mockups/expense-world-card-statement.html).

    Opened by `n` on a card account, one of the two bank accounts sharing a
    statement code (`reads.statement_partners`). The name and the days are
    typed once; then this account's balances, then the other account's, each
    in its own currency. `^s Create both` sends one `POST /reconciliations`
    whose `twin` is the other half: its own id, its account and its balances,
    taking the request's name and days (contract: POST /v1/reconciliations).
    Both halves are created, or neither is; a refusal is the engine's words
    in the form's `Failed` note, a `twin.` key naming the other half, and the
    form stays with what was typed. Saved, it says `Statement created.` and
    hands back the id of this account's half, as the one-account form does.
    """

    BINDINGS = form_bindings("Create both")
    _STATED = frozenset({"accounts"})

    def __init__(self, *, account: tuple, partner: tuple, code: str) -> None:
        """`account` and `partner` are `(id, name, currency)`: the account the
        list was opened from, whose half the write's top level is, and the
        other account holding `code`."""
        super().__init__(account_id=account[0], account_name=account[1])
        self._currencies = {"": account[2], "twin_": partner[2]}
        self._partner_id = partner[0]
        self._locked = {"accounts"}
        self._display["accounts"] = f"{account[1]} + {partner[1]} · {code}"

    def _sequence(self) -> list[str]:
        return [
            "name",
            "accounts",
            "date_start",
            "date_end",
            "begin",
            "end",
            "twin_begin",
            "twin_end",
        ]

    def _required(self) -> tuple[str, ...]:
        return ("name", "date_start", "date_end", "begin", "twin_begin")

    def _balance(self, key: str) -> tuple[str, str] | None:
        """`(BEGIN BALANCE|END BALANCE, currency)` for a balance's key, else None."""
        if key not in _AMOUNTS:
            return None
        side = "twin_" if key.startswith("twin_") else ""
        return _R_LABELS[key.removeprefix("twin_")], self._currencies[side]

    def _label(self, key: str) -> str:
        balance = self._balance(key)
        if balance is not None:
            return f"{balance[0]} {balance[1]}"
        return "ACCOUNTS" if key == "accounts" else super()._label(key)

    def _summary_label(self, key: str) -> str:
        balance = self._balance(key)
        if balance is not None:
            return f"{balance[0].lower()} {balance[1]}"
        return super()._summary_label(key)

    def _required_note(self, key: str) -> str:
        label = self._summary_label(key)
        return f"{label[:1].upper()}{label[1:]} is required."

    def _hint_for(self, key: str) -> str:
        balance = self._balance(key)
        if balance is None:
            return super()._hint_for(key)
        half = formatting.half_name(balance[1])
        if key in _BEGINS:
            return f"signed decimal · the {half}'s opening balance"
        last = "" if self._goes_on(key) else " · enter saves"
        return f"signed decimal · the {half}'s closing balance · optional{last}"

    def _payload(self) -> dict:
        payload = super()._payload()  # this account's half, its id minted there
        twin = {
            "id": str(uuid.uuid4()),
            "account_id": self._partner_id,
            "beginning_balance_cents": self._values["twin_begin"],
        }
        if self._values.get("twin_end") is not None:
            twin["ending_balance_cents"] = self._values["twin_end"]
        payload["twin"] = twin
        return payload

    def _done(self) -> None:
        self.notify("Statement created.")
        self.dismiss(self._new_id)


# --------------------------------------------------------------------------- #
# Working / detail screen — assign transactions, complete / revert / delete
# --------------------------------------------------------------------------- #
def _fetch_all_lines(cfg, **kw) -> list[dict]:
    """Every matching bank line, cursor-paged at the engine cap.

    A single limit=500 request 422s live (cap is 200) and silently truncates
    the checklist; page through instead.
    """
    return fetch_all_cursor_pages(
        lambda limit, after: reads.fetch_bank_lines(cfg, after=after, limit=limit, **kw)
    )


def _status_span(status: str, palette: Palette) -> tuple[str, str]:
    """(text, style) for the header's status word — completed→success, draft→warning."""
    return status, palette.success if status == "completed" else palette.warning


def line_rows(assigned: list[dict], available: list[dict]) -> tuple[list, list, dict]:
    """`(rows, checked, part_of)` for the batch screen's checklist.

    One row per bank line, the batch's lines first, then the ones in no batch,
    each read in the engine's order; a line in both reads is listed once.
    `part_of` maps a line to the one part a tick is sent on: `reconciliation_id`
    is a line field, so a `PUT` on any part moves every part
    (contract: PUT /v1/transactions/{transaction_id}, "Reconciliation assignment").
    """
    rows, checked, part_of = [], [], {}
    in_batch = {line.get("id") for line in assigned}
    for line in [*assigned, *available]:
        key = line.get("id")
        parts = [p for p in line.get("parts") or [] if isinstance(p, dict) and p.get("id")]
        if key in part_of or not parts:
            continue
        part_of[key] = parts[0]["id"]
        if key in in_batch:
            checked.append(key)
        rows.append((key, *formatting.bank_line_columns(line)))
    return rows, checked, part_of


#: A status action's done word → the verb its failure note names: `Couldn't delete`.
_UNDONE = {"completed": "complete", "reverted": "revert", "deleted": "delete"}

#: The first line of a refused complete that follows the ending balance's save:
#: which half went through, above the engine's words.
_BALANCE_SAVED = "The ending balance is saved. The reconciliation is not completed:"


class ReconciliationDetailScreen(
    HelpBindingMixin,
    EngineWriteMixin,
    ContentSwapLockMixin,
    AdaptiveRowsMixin,
    Screen,
):
    """One batch: header + a bank-line checklist (draft) or read-only list
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

    def __init__(self, record: dict, *, currency: str | None = None) -> None:
        super().__init__()
        self._record = record
        self._currency = currency  # the account's, for the ending-balance box
        self._id = record.get("id")
        self._account_id = record.get("account_id")
        self._busy = False
        self._list: CheckList | None = None
        self._part_of: dict = {}  # line id → the part a tick is sent on
        self._land_on: object | None = None  # the line just ticked: the cursor's row after
        self._acct_name: str | None = None  # resolved worker-side in _load_txns
        # last painted rows, cached so a theme change repaints from memory
        # instead of re-fetching

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
        # checklist to #rlist's real height (adaptive rows).
        self.call_after_refresh(self._load_txns)

    # ---- adaptive window ---------------------------------------------------
    def _checklist_items(self) -> int:
        """Rows-per-page = what fits #rlist, one line each.

        The chrome is `LIST_FRAME_LINES` — the same frame every other list
        pays, with no caption here (the crumb and #rhead both name the batch).
        Never a literal: #rlist is `overflow: hidden`, so a miscount clips the
        page status in silence.
        """
        return self.fit_rows("#rlist", chrome=self.LIST_FRAME_LINES)

    def on_resize(self, _event) -> None:
        if self._list is not None and self._list.is_attached:
            self._list.set_page_size(self._checklist_items())

    def _apply_fresh_record(self, fresh: dict) -> None:
        """Main-thread: rebind _record from a refreshed batch, then repaint the
        header. Called on the UI thread so the worker never mutates screen
        state directly, and a cancelled stale load can't clobber _record."""
        self._record = fresh
        self._render_header()

    def _set_acct_name(self, name: str | None) -> None:
        self._acct_name = name

    def _render_header(self) -> None:
        r = self._record
        palette = PALETTE
        # short-id placeholder until _load_txns resolves the name worker-side
        acct = self._acct_name or resolve_name(self._account_id, {})
        status = formatting.format_status(r.get("status"))
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
        # and stack duplicate checklists.
        worker = get_current_worker()
        try:
            cfg = config_module.ensure_loaded()
            kw = screen_fetch_kwargs(self.app)
            if refresh_record:
                # refetch the batch itself too — a stale header/status would
                # misrepresent balances and the read-only gate. There is no
                # read by id: the account's list is whole,
                # so a row missing from it is a row that was deleted.
                listed = reads.fetch_reconciliations(cfg, account_id=self._account_id, **kw)
                fresh = next((r for r in items_of(listed) if r.get("id") == self._id), None)
                if worker.is_cancelled:
                    return
                if fresh is None:
                    call_while_attached(self, self._record_gone)
                    return
                # Marshal onto the main thread — worker mustn't mutate screen state.
                call_while_attached(self, self._apply_fresh_record, fresh)
            # the batch's lines (always; any date)
            assigned = _fetch_all_lines(cfg, reconciliation=self._id, **kw)
            available = []
            if not self._completed:  # a draft also offers the account's lines in no batch
                available = _fetch_all_lines(
                    cfg,
                    account=self._account_id,
                    unreconciled=True,
                    date_from=self._record["date_start"],
                    date_to=self._record["date_end"],
                    **kw,
                )
            acct_name = resolve_name(self._account_id, load_account_name_map())
        except Exception as exc:  # surface engine/config errors in-app, don't crash
            if not worker.is_cancelled:
                call_while_attached(self, self.notify, format_error(exc), severity="error")
            return
        rows, checked, part_of = line_rows(assigned, available)
        if worker.is_cancelled:
            return
        call_while_attached(self, self._set_acct_name, acct_name)
        call_while_attached(self, self._render_header)  # picks up _acct_name
        call_while_attached(self, self._populate, rows, checked, part_of)

    async def _populate(self, rows: list, checked: list, part_of: dict) -> None:
        """Paint a read. Not while a tick is unanswered: the read may predate
        it, and the read after the last tick paints with the cursor on the line
        ticked last, so ticking down a statement never lands on another row."""
        if self._ticks_unanswered():
            return
        land_on, self._land_on = self._land_on, None
        async with self._content_lock():
            container = self.query_one("#rlist", Container)
            await container.remove_children()
            empty = (
                "(no transactions in this batch)"
                if self._completed
                else "(no transactions for this account in range)"
            )
            self._part_of = part_of
            self._list = CheckList(
                rows,
                checked,
                read_only=self._completed,
                empty=empty,
                palette=PALETTE,
                page_size=self._checklist_items(),  # adaptive window
                land_on=land_on,
            )
            await container.mount(self._list)
            if not self._completed:
                self._list.focus()

    # ---- assign / unassign ----------------------------------------------
    def on_check_list_toggled(self, event: CheckList.Toggled) -> None:
        """`space`: one `PUT` of `reconciliation_id` on one part of the line,
        which puts every part in the batch or takes every part out
        (contract: PUT /v1/transactions/{transaction_id}, "Line fields"). The
        mixin queue sends one PUT at a time, in order; once the last one is in,
        the screen reads the batch and its lines again, the cursor on the line
        just ticked."""
        part = self._part_of.get(event.key)
        if part is None:
            return
        self._land_on = event.key
        self.run_write(
            "PUT",
            f"/transactions/{part}",
            json_body={"reconciliation_id": self._id if event.checked else None},
            on_success=self._assigned,
            on_error=self._assign_failed,
        )

    def _is_tick(self, write) -> bool:
        return write.on_success == self._assigned

    def _ticks_unanswered(self) -> bool:
        """A tick is sent or queued and its answer has not come back. Read off
        the write queue itself, so a dropped queue can never leave it stuck."""
        return any(self._is_tick(w) for w in self.writes_unanswered())

    def _assigned(self) -> None:
        if not self._ticks_unanswered():  # a tick still unanswered reads again when it lands
            self._load_txns(refresh_record=True)

    def _writes_dropped(self, failed, dropped: list) -> None:
        """A refused complete, revert, delete or balance save dropped ticks
        queued behind it: their boxes show a state the engine never got, so
        the month and its list are read again, the cursor on row 1. A refused
        tick reads again on its own (`_assign_failed`)."""
        if not self._is_tick(failed) and any(self._is_tick(w) for w in dropped):
            self._land_on = None
            self._load_txns(refresh_record=True)

    def _assign_failed(self, message: str) -> None:
        # The mixin already dropped the queued intents (they were made against
        # a checklist state the engine just contradicted) — resync to truth:
        # the month too, since a tick before this one may have landed.
        self.notify(message, title="Couldn't update", severity="error")
        self._land_on = None
        self._load_txns(refresh_record=True)

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
        if self._busy:
            return
        # The engine refuses to complete without the ending balance (contract:
        # POST /v1/reconciliations/{reconciliation_id}/complete, "The ending
        # balance must be entered"), so an empty one is asked for first.
        if self._record.get("ending_balance_cents") is None:
            self._ask_ending_balance()
            return
        self._confirm_complete()

    def _confirm_complete(self, *, after_save: bool = False) -> None:
        # No ≥1-assigned pre-guard: the engine 422s an empty complete and
        # run_write toasts its message (thin wrapper).
        n = len(self._list.checked) if self._list else 0
        rows = "row" if n == 1 else "rows"
        self._confirm(
            "Complete reconciliation?",
            f"Locks amount/account/title/date on the {n} ticked {rows}.",
            lambda: self._status_action(
                "POST",
                f"/reconciliations/{self._id}/complete",
                2,
                "completed",
                on_response=self._report_gap,
                lead=_BALANCE_SAVED if after_save else "",
            ),
        )

    # ---- the ending balance, asked for at complete ----------------------
    def _ask_ending_balance(self) -> None:
        """The box: the statement's closing figure, read by the shared money
        parser exactly as typed — the sign is the one typed, never added or
        flipped. Unreadable text keeps the box open; `esc` sends nothing."""
        acct = self._acct_name or resolve_name(self._account_id, {})
        currency = f"in {self._currency} · " if self._currency else ""
        self.app.push_screen(
            AmountPromptModal(
                "Ending balance first",
                f"The statement's closing figure for {acct},\n{currency}signed · e.g. 13,853.20",
                unreadable=_END_UNREADABLE,
            ),
            self._save_ending_balance,
        )

    def _save_ending_balance(self, cents: int | None) -> None:
        if cents is None or self._busy:
            return  # esc: nothing saved
        self._busy = True
        self.run_write(
            "PUT",
            f"/reconciliations/{self._id}",
            json_body={"ending_balance_cents": cents},
            on_response=self._balance_saved_record,
            on_success=self._balance_saved,
            on_error=self._balance_failed,
            # `r` on this screen reads the reconciliation again
            error_text=list_refusal_text,
        )

    def _balance_saved_record(self, body: dict) -> None:
        """The engine's own record after the save: the header shows its end and
        diff before the complete question asks."""
        if body.get("id") == self._id:
            self._apply_fresh_record(body)

    def _balance_saved(self) -> None:
        self._busy = False
        self._confirm_complete(after_save=True)

    def _balance_failed(self, message: str) -> None:
        self._busy = False
        self.notify(message, title="Couldn't save", severity="error")

    def action_revert(self) -> None:
        # No completed-only pre-guard: the engine treats revert-on-draft as
        # an idempotent 200 no-op (thin wrapper).
        self._confirm(
            "Revert to draft?",
            "Unlocks the assigned transactions and this batch's balances.",
            lambda: self._status_action(
                "POST", f"/reconciliations/{self._id}/revert", 1, "reverted to draft"
            ),
        )

    def action_delete(self) -> None:
        # No draft-only pre-guard: the engine refuses to delete a completed
        # reconciliation (`RECONCILIATION_NOT_DRAFT`), and the note shows its words
        # with the line naming `u` (thin wrapper). Sent from this screen, where
        # `r` reads it again, so a refusal's line is the list one.
        self._confirm(
            "Delete reconciliation?",
            "Detaches its transactions and removes the batch. Its transactions stay. "
            "No screen can bring it back.",
            lambda: self._status_action(
                "DELETE",
                f"/reconciliations/{self._id}",
                None,
                "deleted",
                error_text=list_refusal_text,
            ),
        )

    def _confirm(self, title: str, message: str, action) -> None:
        def cb(ok: bool) -> None:
            if ok:
                action()

        self.app.push_screen(ConfirmModal(title, message), cb)

    def _status_action(
        self, method: str, path: str, new_status, verb: str, *, lead: str = "", **kw
    ) -> None:
        """`lead`, when given, is the failure note's first line, above the
        engine's words."""
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
            on_error=lambda m: self._action_failed(f"{lead}\n{m}" if lead else m, verb),
            **kw,
        )

    def _report_gap(self, body: dict) -> None:
        """Surface `complete`'s `warnings` — the uncovered-days report.

        Shown as a line under the header rather than a toast: the whole value of
        this message is not being missed, and a toast fades in five seconds. It
        stays for as long as the screen does, survives `r`, and clears on the
        next status change.

        The text is the engine's own sentence, verbatim — the dates in it are
        prose, not fields, so this side neither parses them nor goes looking for
        the rows they name. The review surface for that is the "no batch"
        pane (`u`).
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
        done = verb.split()[0]
        self.notify(message, title=f"Couldn't {_UNDONE.get(done, done)}", severity="error")
        if verb == "completed":
            # Read the reconciliation fresh: a refusal can say what the screen
            # last read is out of date (an ending balance cleared elsewhere),
            # and the next `c` decides on the header it shows.
            self._load_txns(refresh_record=True)

    def _action_done(self, new_status, verb: str) -> None:
        self._busy = False
        self.notify(f"Reconciliation {verb}.")
        if verb == "deleted":
            self.dismiss()
            return
        self._record["status"] = new_status
        self._render_header()
        self._load_txns()
