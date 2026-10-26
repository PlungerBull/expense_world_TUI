"""Reconciliations — list, new batch, and the working/detail screen.

Per-account bank-statement batches. The browse opens on the accounts alone;
`⏎` on one reads its reconciliations in one read, whole, and opens them in a
panel under the accounts, the cursor in it. They stand in the order the
engine returns them: `date_start` ascending, then by account in the
accounts' order, then creation time, oldest first
(contract: "Reconciliations", "Ordering"). There `⏎` opens the working
screen, `n` creates one for the account, `u` swaps the panel for the
account's bank lines in no batch (`GET /bank-lines`, newest first, a split
purchase one row), and `esc` closes the panel. Nothing is read for an
account until you press `⏎` on it.

An account with no statement code reads `GET /reconciliations?account_id=`
and lists one row per reconciliation: Name, Period, Begin, End, Diff,
Status. An account with a statement code reads
`GET /reconciliations?statement_of=` instead, the reconciliations of every
account holding its code, and lists **one row per statement** (pane 1 A of
docs/mockups/expense-world-card-statement.html, and task 6's question 3 B
for a code no other account holds): an item and, when its `twin_id` is set,
the item of the same answer that id names (contract: GET /v1/reconciliations),
the row standing where its first item stands. Its columns are Name, Period,
one Diff per account of the statement (`Diff PEN`, `Diff USD`, in the
accounts' order; `Diff` alone on a code one account holds), Status and Order:
each Diff that half's difference, `no half` where the statement has no half
on that account; Status `completed` or `draft` when the halves agree, `half
completed` when they do not; Order `in order` when the engine's
`unplaced_count` and `shared_place_count` both read 0, `not in order`
otherwise (contract: "Reconciliations", "A statement's order"). The
statement's accounts are the open one, the card's other account the engine
names on it (`statement_partner_id`), and any account a reconciliation of the
answer is on (`statement_columns`). The panel's title names each of them,
then the code, and each of them listed above carries the `▸`.

New batch: name › account › date start › date end › begin › end. Both balances
are typed off the paper statement — the engine has no derived (chained) begin,
so `beginning_balance_cents` is required. Both dates are required too
(contract: POST /v1/reconciliations), and are
calendar days sent as typed (contract: "Date inputs"); the form refuses any other shape at
the field. POST /reconciliations.

New card statement (NewCardStatementScreen), `n` on a card account, one the
engine names another account on as `statement_partner_id`: name ›
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
needs ≥1 transaction and locks the amount, date, title, account, operation
number and reconciliation of each, an empty title or operation number staying
fillable (contract: PUT /v1/transactions/{transaction_id}, "Field locking");
delete is draft-only and just detaches the transactions. Completing also needs the
ending balance (contract: POST /v1/reconciliations/{reconciliation_id}/complete,
"The ending balance must be entered"): `c` on a draft that has none first asks
for it in a box, saves it with PUT /reconciliations/{id}, then asks the usual
"Complete reconciliation?". A complete whose answer flags lines for review
(`review_lines`, a card's other half's too) opens FlaggedLinesScreen on them
(pick 1A of docs/mockups/expense-world-statement-flagged-lines.html), and the
working screen keeps a `⚑` line and `f` until its next status change.
"""

import uuid
from collections.abc import Callable
from typing import NamedTuple

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
    card_partners,
    fetch_all_cursor_pages,
    items_of,
    load_account_name_map,
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
from expense.tui.widgets.refusal import toast

# Status labels + period formatting are owned by expense/formatting.py
# (format_status / format_period) — one copy, per the §5 rule.
_period = formatting.format_period

_BATCH_HEADERS = ["Name", "Period", "Begin", "End", "Diff", "Status"]
_BATCH_RIGHT = {2, 3, 4}
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
    included on purpose: an unfiled row inside a draft's window is one its close
    will flag for review, not a refusal: the close goes through
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Response").
    Completed windows are in here too: an unfiled row inside one is a line its
    close flagged, or one dated on its last day, which stays open until the
    account's next statement is completed (contract: "Transactions (Ledger)",
    "Sealed periods"), and the pane exists to surface it.
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


def ask_line_delete(
    screen: EngineWriteMixin, line: dict, account_name: str, *, after: Callable[[], None]
) -> None:
    """`d` on a bank line a list holds: the question, then the delete, through
    `confirm_delete` (only `y` deletes). A split purchase (`part_count` above 1)
    goes whole, in one `DELETE /bank-lines/{id}`
    (contract: DELETE /v1/bank-lines/{bank_line_id}), after the question naming its
    part count; a line never split goes as its one transaction, in
    `DELETE /transactions/{id}`, after the ledger's question. Each question says no
    screen can bring it back. The line in hand is the list's own read, so nothing is
    read before asking. Deleted, `after` reads the list again. Shared by the "no
    batch" pane and the flagged lines' screen."""
    if is_split_line(line):
        screen.confirm_delete(
            "bank-lines",
            line.get("id"),
            bank_line_delete_question(line),
            bank_line_delete_message(line, account_name),
            done="Transaction deleted.",
            after=after,
        )
        return
    record = lone_transaction(line)
    if record is None:
        return
    screen.confirm_delete(
        "transactions",
        record.get("id"),
        "Delete this transaction?",
        transaction_delete_message(record, account_name),
        done="Transaction deleted.",
        after=after,
    )


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


class StatementAccounts(NamedTuple):
    """What a statement list is titled and laid out by: the open account's
    statement code, and the accounts it shows a Diff column for as
    `(id, name, currency)`, in the accounts read's order."""

    code: str
    accounts: tuple[tuple[str, str, str], ...]


def statement_columns(
    account_id: object, accounts: list[dict], recons: list[dict]
) -> StatementAccounts | None:
    """The statement list of `account_id`'s panel: its own statement code and
    the accounts it shows; None on an account with no code.

    The accounts are the open account, the card's other account the engine
    names on it as `statement_partner_id`
    (contract: "Bank Accounts", "Statement partner"), and every account a
    reconciliation of the panel's `statement_of` answer is on: that answer
    holds the reconciliations of every account holding the code, an archived
    one included (contract: GET /v1/reconciliations). The answer is how an
    archived card account, which names no other account and is named by none
    (contract: "Bank Accounts", "While one of the two accounts is archived"),
    keeps its column and its place in the title while it holds a half.
    `accounts` is one read with `include_archived`; their order is its order.
    """
    rows = {row["id"]: row for row in accounts if row.get("id")}
    own = rows.get(account_id)
    code = own.get("statement_code") if own else None
    if not code:
        return None
    shown = {account_id, own.get("statement_partner_id")}
    shown |= {item.get("account_id") for item in recons}
    return StatementAccounts(
        code,
        tuple(
            (aid, row.get("name") or "(unnamed)", row.get("currency_code") or "?")
            for aid, row in rows.items()
            if aid in shown
        ),
    )


def statement_headers(accounts: tuple) -> tuple[list[str], set[int]]:
    """`(headers, right-aligned columns)` of a statement list: Name, Period,
    a Diff per account of the statement, `(id, name, currency)` in the
    accounts' order, then Status and Order. One account: `Diff` alone."""
    if len(accounts) == 1:
        diffs = ["Diff"]
    else:
        diffs = [f"Diff {currency}" for _aid, _name, currency in accounts]
    return ["Name", "Period", *diffs, "Status", "Order"], set(range(2, 2 + len(diffs)))


def statement_status(halves: list[dict]) -> str:
    """A statement's status: its halves' when they agree, `half completed`
    when one is completed and another is not."""
    statuses = {half.get("status") for half in halves}
    if len(statuses) > 1:
        return "half completed"
    return formatting.format_status(statuses.pop() if statuses else None)


def order_cell(item: dict, palette: Palette | None = None) -> str | Text:
    """Whether a statement is in order, as the engine counts it: `in order`
    when its lines with no place and its places held twice both read 0,
    `not in order` otherwise. Both halves read the same two counts; null
    counts (no statement order) show nothing
    (contract: "Reconciliations", "A statement's order")."""
    unplaced, shared = item.get("unplaced_count"), item.get("shared_place_count")
    if unplaced is None or shared is None:
        return ""
    if unplaced == 0 and shared == 0:
        return "in order"
    return Text("not in order", style=palette.warning) if palette else "not in order"


def statement_rows(
    items: list[dict], accounts: tuple, open_id: object, palette: Palette | None = None
) -> list:
    """One row per statement, from one `GET /reconciliations?statement_of=`
    answer in the engine's order: an item and the item its `twin_id` names in
    the same answer, found by id, the row where the first of them stands.

    `accounts` are the statement's accounts (`statement_columns`),
    `(id, name, currency)`, one Diff column each. The row's key is the half on
    `open_id`, the account whose panel is open, or the other half when the
    statement has none there.
    """
    by_id = {it.get("id"): it for it in items}
    seen: set = set()
    rows = []
    for item in items:
        if item.get("id") in seen:
            continue
        twin = by_id.get(item.get("twin_id")) if item.get("twin_id") else None
        halves = [item] if twin is None or twin.get("id") in seen else [item, twin]
        seen.update(half.get("id") for half in halves)
        on = {half.get("account_id"): half for half in halves}
        diffs = [
            difference_cell(on[aid].get("difference_cents"), palette) if aid in on else "no half"
            for aid, _name, _currency in accounts
        ]
        status = statement_status(halves)
        status_cell: str | Text = status
        if status == "half completed" and palette is not None:
            status_cell = Text(status, style=palette.warning)
        cells = [
            item.get("name") or "(unnamed)",
            _period(item),
            *diffs,
            status_cell,
            order_cell(item, palette),
        ]
        key = (on.get(open_id) or item).get("id")
        completed = all(half.get("status") == 2 for half in halves)
        rows.append((key, cells, "dim" if completed else ""))
    return rows


def _has_code(accounts: list[dict], account_id: object) -> bool:
    """Whether `account_id` has a statement code, from one accounts read."""
    return any(a.get("id") == account_id and a.get("statement_code") for a in accounts)


def _read_reconciliations(cfg, account_id: str, has_code: bool, kw: dict) -> dict:
    """The panel's one read: the whole statement code's list on an account
    with a code (`statement_of`), the account's own on one without
    (`account_id`)."""
    if has_code:
        return reads.fetch_reconciliations(cfg, statement_of=account_id, **kw)
    return reads.fetch_reconciliations(cfg, account_id=account_id, **kw)


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
            tooltip="Edit the transaction and its parts",
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
    reconciliations is read until you press `⏎` on an account, so moving the
    cursor costs nothing. `⏎` reads that account's list in one read, whole, in
    the order the module docstring gives: `?account_id=` on an account with no
    statement code, one row per reconciliation; `?statement_of=` on one with a
    code, one row per statement, the other half read from the item its
    `twin_id` names, never from a second read. It opens the panel under the
    accounts with the cursor in it. There `⏎` opens a reconciliation, `n`
    creates one, `u` swaps the panel for the account's rows in no batch, and
    `esc` closes the panel.

    The accounts are one read with `include_archived`: the list leaves the
    archived ones out, and they still name a code's columns and title, since
    a `statement_of` answer holds an archived card account's halves too
    (contract: GET /v1/reconciliations).
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
        # a card account → its other account's (id, name, currency), as the engine names it
        self._partners: dict = {}
        # the accounts read, archived ones included: names a statement list's columns
        self._known: list[dict] = []
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
        accts = items_of(reads.fetch_accounts(cfg, include_archived=True, **kw))
        live = [a for a in accts if not a.get("is_archived")]
        accounts = account_choices(live, include_people=False, with_balance=True)
        recons = None
        if self._open_aid is not None:
            has_code = _has_code(accts, self._open_aid)
            recons = items_of(_read_reconciliations(cfg, self._open_aid, has_code, kw))
        return {
            "recons": recons,
            "accounts": accounts,
            "partners": card_partners(accts),
            "known": accts,
        }

    def _selected_account(self):
        return self._accounts[self._acct_idx] if self._accounts else None

    def _open_account(self):
        return next((a for a in self._accounts if a[0] == self._open_aid), None)

    def _open_statement(self) -> StatementAccounts | None:
        """The open account's code and the accounts its statement list shows;
        None with no panel open or on an account with no code."""
        if self._open_aid is None:
            return None
        return statement_columns(self._open_aid, self._known, self._recons)

    def _batch_caption(self) -> str:
        statement = self._open_statement()
        if statement is not None:
            names = " + ".join(name for _aid, name, _currency in statement.accounts)
            return f"Reconciliations · {names} · {statement.code}   ·   oldest → newest"
        acct = self._open_account()
        return f"Reconciliations · {acct[1] if acct else '—'}   ·   oldest → newest"

    def _panel_headers(self) -> tuple[list[str], set[int]]:
        statement = self._open_statement()
        if statement is None:
            return _BATCH_HEADERS, _BATCH_RIGHT
        return statement_headers(statement.accounts)

    def _panel_rows(self) -> list:
        statement = self._open_statement()
        if statement is None:
            return batch_rows(self._recons, palette=PALETTE)
        return statement_rows(self._recons, statement.accounts, self._open_aid, palette=PALETTE)

    def _currency_of(self, account_id: object) -> str | None:
        """The currency of a listed reconciliation's account: a card's other
        account's too, from the accounts its statement list shows."""
        statement = self._open_statement()
        for aid, _name, currency in statement.accounts if statement else ():
            if aid == account_id:
                return currency
        acct = self._open_account()
        return acct[2] if acct else None

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
        is showing once the cursor has gone down into it; on a statement code,
        every account the panel's statement list shows does."""
        statement = self._open_statement()
        marked = {aid for aid, _name, _currency in statement.accounts} if statement else set()
        marked |= {self._open_aid} if self._open_aid else set()
        rows = []
        for aid, name, cur, bal in self._accounts:
            label = Text.assemble(("▸ ", ACCENT), name) if aid in marked else name
            rows.append((aid, [label, cur, amount_cell(bal, PALETTE, AMOUNT_RULE)]))
        return rows

    def _new_batch_list(self) -> CursorList:
        headers, align_right = self._panel_headers()
        batch_list = _PanelList(
            headers,
            self._panel_rows(),
            align_right=align_right,
            empty="none yet · n to create one",
            caption=self._batch_caption(),
            page_size=self.pane_rows(),
        )
        batch_list.id = "batches"
        return batch_list

    def build(self, data: dict) -> list[Widget]:
        self._accounts = data["accounts"]
        self._partners = data["partners"]
        self._known = data["known"]
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
        # `⏎` on a reconciliation opens its detail; on a statement, the row's key half's: the
        # open account's, or the other half when the statement has none there.
        item = self._by_id.get(event.key)
        if item:
            self._resume_key = event.key
            currency = self._currency_of(item.get("account_id"))
            self.app.push_screen(
                ReconciliationDetailScreen(item, currency=currency),
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
            has_code = _has_code(self._known, account_id)
            body = _read_reconciliations(cfg, account_id, has_code, screen_fetch_kwargs(self.app))
        except Exception as exc:
            if not worker.is_cancelled:
                self.app.call_from_thread(
                    toast, self, format_error(exc), title="Failed", severity="error"
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
            headers, align_right = self._panel_headers()
            self._batch_list.set_headers(headers, align_right=align_right)
            self._batch_list.set_caption(self._batch_caption())
            self._batch_list.set_rows(self._panel_rows())
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
        toast(self, message, title="Failed", severity="error")

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
        final (`ask_line_delete`). Why: docs/decisions.md "Rows in no batch
        live in the reconciliation view".
        """
        if self._mode != "unfiled":
            return
        line = self._unfiled_record()
        if line is None:
            return
        acct = self._open_account()
        ask_line_delete(self, line, acct[1] if acct else "—", after=self._reload_unfiled)

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
        code = next((a.get("statement_code") for a in self._known if a.get("id") == acct[0]), "")
        form = (
            NewReconciliationScreen(account_id=acct[0], account_name=acct[1])
            if partner is None
            else NewCardStatementScreen(account=acct[:3], partner=partner, code=code or "")
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
#: The begin balance hint's second line, on every begin field: a statement holding
#: the account's opening balance begins at 0.00, as the engine sums every assigned
#: transaction, that line included, into the statement's add-up check
#: (contract: "Reconciliations", "`difference_cents` — the add-up check").
#: The hint widget lays out one line per `\n`.
_OPENING_NOTE = "0.00 if it holds the account's opening balance, which already counts it"
_R_HINTS = {
    "name": "e.g. “April 2026” · enter to go on",
    "account": "pick a bank account · ↑↓ highlight · enter select",
    "date_start": "YYYY-MM-DD · the statement's first day · it orders the batch",
    "date_end": "YYYY-MM-DD · the statement's last day",
    "begin": f"signed decimal · your statement's opening balance\n{_OPENING_NOTE}",
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
            self.app.call_from_thread(toast, self, format_error(exc), severity="error")
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
                toast(self, f"No account matches “{text}”.", severity="error")
                return
            self._values["account"] = picked[0]
            self._display["account"] = picked[1]
            self._advance()
        elif key in _DATES:
            # Both required. The check is the exact day shape the engine takes
            # (contract: "Date inputs"), caught here at the field rather
            # than as a 422 on save; the typed text is what gets sent.
            if not text:
                toast(self, f"{_R_LABELS[key].capitalize()} is required.", severity="error")
                return
            if not is_calendar_day(text):
                toast(self, f"{_R_LABELS[key].title()}: use YYYY-MM-DD.", severity="error")
                return
            self._values[key] = self._display[key] = text
            self._advance()
        elif key in _BEGINS:
            cents = parse_amount(text)
            if cents is None:
                toast(self, _BEGIN_UNREADABLE, severity="error")
                return
            self._values[key] = cents
            self._display[key] = format_cents(cents)
            self._advance()
        elif key in _ENDS:
            # optional: an empty line leaves it out (`ending_balance_cents` null)
            if text:
                cents = parse_amount(text)
                if cents is None:
                    toast(self, _END_UNREADABLE, severity="error")
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

    Opened by `n` on a card account, one the engine names another account on
    as `statement_partner_id` (`reads.card_partners`). The name and the days are
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
        card's other account, as the engine names it; `code` is the account's
        statement code."""
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
            return f"signed decimal · the {half}'s opening balance\n{_OPENING_NOTE}"
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
    `r` refetches the batch + checklist (r = refresh everywhere, never a write).

    A complete whose answer flags lines for review opens `FlaggedLinesScreen` on
    them; back here, the `⚑` line under the header says how many, and `f` opens
    that screen again, both until the next status change."""

    BINDINGS = [
        ("escape", "back", "Back"),
        ("r", "reload", "Refresh"),
        ("c", "complete", "Complete"),
        ("u", "revert", "Revert"),
        ("d", "delete", "Delete"),
        Binding("f", "flagged", "Flagged", tooltip="The lines the complete flagged for review"),
        *HelpBindingMixin.BINDINGS,
    ]
    #: The `?` card lists `f` only while `check_action` allows it (help.py).
    CARD_FOLLOWS_CHECK = frozenset({"flagged"})

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
        # the bank lines the last complete flagged for review, both halves', as
        # the flagged lines' screen last left them
        self._flagged: list[str] = []
        # last painted rows, cached so a theme change repaints from memory
        # instead of re-fetching

    @property
    def _completed(self) -> bool:
        return self._record.get("status") == 2

    def compose(self) -> ComposeResult:
        yield Breadcrumb(("Reconciliations", self._record.get("name") or "—"), id="crumb")
        yield Static("", id="rhead")
        yield Static("", id="rwarn")  # the gap report; hidden until a complete carries one
        yield Static("", id="rflag")  # the flagged lines; hidden until a complete flags one
        yield Container(id="rlist")
        yield Static("", id="rhint")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#rwarn", Static).display = False
        self.query_one("#rflag", Static).display = False
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
                call_while_attached(self, toast, self, format_error(exc), severity="error")
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
        toast(self, message, title="Couldn't update", severity="error")
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
            "Locks the amount, date, title, account, operation number and reconciliation"
            f" of the {n} ticked {rows}.",
            lambda: self._status_action(
                "POST",
                f"/reconciliations/{self._id}/complete",
                2,
                "completed",
                on_response=self._report_close,
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
        toast(self, message, title="Couldn't save", severity="error")

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
        # Any status change invalidates a gap report and the flagged lines: they
        # were true of the record as it stood one write ago (a revert unseals the
        # very window they named).
        self._show_warnings([])
        self._show_flagged([])
        self.run_write(
            method,
            path,
            on_success=lambda: self._action_done(new_status, verb),
            on_error=lambda m: self._action_failed(f"{lead}\n{m}" if lead else m, verb),
            **kw,
        )

    def _report_close(self, body: dict) -> None:
        """What `complete` answers beside the record: the uncovered-days report
        (`_report_gap`) and the lines it flagged for review (`_take_flagged`)."""
        self._report_gap(body)
        self._take_flagged(body)

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

    def _take_flagged(self, body: dict) -> None:
        """The ids of the bank lines the close flagged for review, the named
        half's `review_lines`, then the other half's (`twin.review_lines`)
        (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Response").
        The screen showing them opens once the complete's success has landed
        (`_action_done`)."""
        twin = body.get("twin")
        halves = [body, twin] if isinstance(twin, dict) else [body]
        ids: list[str] = []
        for half in halves:
            named = half.get("review_lines")
            if isinstance(named, list):
                ids.extend(str(line_id) for line_id in named if line_id)
        self._show_flagged(ids)

    def _show_flagged(self, ids: list[str]) -> None:
        """The `⚑` line under the header, and `f` with it, while any line the
        close flagged is still one the engine has; hidden otherwise."""
        self._flagged = list(ids)
        line = self.query_one("#rflag", Static)
        self.refresh_bindings()
        if not self._flagged:
            line.display = False
            line.update("")
            return
        line.update(
            Text.assemble(
                (
                    f"⚑ {line_count(len(self._flagged))} flagged for review: in no statement,"
                    " dated up to this one's last day",
                    PALETTE.warning,
                ),
                ("  · f shows them", "dim"),
            )
        )
        line.display = True

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        # False, not None: hidden from the footer as well as dead
        if action == "flagged":
            return bool(self._flagged)
        return super().check_action(action, parameters)

    def action_flagged(self) -> None:
        """`f` — the flagged lines' screen again, on the lines still flagged."""
        if self._flagged:
            self._open_flagged()

    def _open_flagged(self) -> None:
        self.app.push_screen(
            FlaggedLinesScreen(self._flagged, statement=self._record.get("name") or "—"),
            self._flagged_back,
        )

    def _flagged_back(self, ids: list[str] | None) -> None:
        """Back from the flagged lines: the ones the engine still has."""
        if ids is not None:
            self._show_flagged(ids)

    def _action_failed(self, message: str, verb: str) -> None:
        self._busy = False
        done = verb.split()[0]
        toast(self, message, title=f"Couldn't {_UNDONE.get(done, done)}", severity="error")
        if verb == "completed":
            # Read the reconciliation fresh: a refusal can say what the screen
            # last read is out of date (an ending balance cleared elsewhere),
            # and the next `c` decides on the header it shows.
            self._load_txns(refresh_record=True)

    def _action_done(self, new_status, verb: str) -> None:
        self._busy = False
        toast(self, f"Reconciliation {verb}.")
        if verb == "deleted":
            self.dismiss()
            return
        self._record["status"] = new_status
        self._render_header()
        self._load_txns()
        if verb == "completed" and self._flagged:
            self._open_flagged()


# --------------------------------------------------------------------------- #
# The lines a complete flagged for review
# --------------------------------------------------------------------------- #
def line_count(n: int) -> str:
    """`1 line`, `3 lines`."""
    return f"{n} line" if n == 1 else f"{n} lines"


#: What to do with a flagged line, under the count (pane 1A of
#: docs/mockups/expense-world-statement-flagged-lines.html): the three choices
#: (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "What a client
#: does with a flagged line").
FLAGGED_CHOICES = (
    "For each: if it belongs to this statement, revert, tick it, complete again.",
    "If it belongs to a later statement, leave it: tick it there when it comes.",
    "If it is a mistake, open it to fix it, or delete it.",
)
_FLAGGED_HEADERS = ["Date", "Account", "Title", "Amount"]


def flagged_order(lines: list[dict]) -> list[dict]:
    """Both halves' flagged lines in one list, oldest first by the line's day:
    the engine answers each half's oldest first, and a stable sort keeps that
    order within a day."""
    return sorted(lines, key=lambda line: bank_line_columns(line)[0])


def flagged_rows(lines: list[dict], names: dict, palette: Palette | None = None) -> list:
    """One row per flagged line, in the order given: its day, its account by
    name, its title and its signed `net_cents`, as every bank line list shows
    them (`bank_line_columns`)."""
    rows = []
    for line in lines:
        day, title, _operation, net_cents = bank_line_columns(line)
        rows.append(
            (
                line.get("id"),
                [
                    day,
                    resolve_name(line.get("account_id"), names),
                    title or "(untitled)",
                    amount_cell(net_cents, palette, AMOUNT_RULE),
                ],
            )
        )
    return rows


def flagged_head(statement: str, n: int, palette: Palette) -> Text:
    """`<statement> is completed. N lines dated up to its last day are in no
    statement.`, then what to do with each, dim."""
    verb = "is" if n == 1 else "are"
    text = Text.assemble(
        (f"{statement} is completed. ", ""),
        (f"{line_count(n)} dated up to its last day {verb} in no statement.", palette.warning),
    )
    for choice in FLAGGED_CHOICES:
        text.append("\n")
        text.append(choice, style="dim")
    return text


class _FlaggedList(CursorList):
    """The flagged lines' list. It takes no focus: its screen holds every key,
    so the footer reads in the screen's own order (a focused widget's keys come
    first in a footer)."""

    can_focus = False


class FlaggedLinesScreen(EngineWriteMixin, ContentSwapLockMixin, AdaptiveRowsMixin, Screen):
    """The lines a statement's close flagged for review (pane 1A of
    docs/mockups/expense-world-statement-flagged-lines.html).

    A complete names them by id alone, on each half
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Response"),
    so the screen reads each by its id (`reads.fetch_live_bank_lines`), drops a
    line the engine no longer has, and lists the rest oldest first, both halves
    together: `Date · Account · Title · Amount`. `⏎` opens the line in the
    ledger's Edit form, `d` deletes it after the delete question, and after
    either the ids are read again. `esc` goes back to the statement, handing it
    the ids still flagged; with none left the screen goes back on its own.
    No `?`: the footer is its whole key list."""

    BINDINGS = [
        Binding("escape", "back", "Back to the statement"),
        Binding("enter", "open", "Open", tooltip="Open the line in its Edit form"),
        Binding("d", "delete_line", "Delete", tooltip="Delete the line, after a question"),
        Binding("down", "move(1)", "Move", key_display="↑↓", tooltip="Down"),
        Binding("up", "move(-1)", "Up", show=False),
        Binding("pagedown", "page(1)", "Next", key_display="pgdn", show=False),
        Binding("pageup", "page(-1)", "Prev", key_display="pgup", show=False),
        Binding("r", "reload", "Refresh", show=False),
    ]

    def __init__(self, ids: list[str], *, statement: str) -> None:
        super().__init__()
        self._ids = list(ids)
        self._statement = statement
        self.crumb = ("Reconciliations", statement, "Flagged")
        self._lines: list[dict] = []
        self._names: dict = {}
        self._list: CursorList | None = None

    def compose(self) -> ComposeResult:
        yield Breadcrumb(self.crumb, id="crumb")
        yield Static(flagged_head(self._statement, len(self._ids), PALETTE), id="fhead")
        yield Container(id="flist")
        yield Footer()

    def on_mount(self) -> None:
        # the list sizes itself to #flist's real height: wait for the first layout
        self.call_after_refresh(self._load)

    def on_resize(self, _event) -> None:
        if self._list is not None and self._list.is_attached:
            self._list.set_page_size(self._page_rows())

    def _page_rows(self) -> int:
        return self.fit_rows("#flist", chrome=self.LIST_FRAME_LINES)

    @work(thread=True, exclusive=True, group="flagged-load")
    def _load(self) -> None:
        """Each id still flagged, read by its id, and the accounts' names. A
        failed read shows the engine's words and keeps what is listed."""
        from expense import config as config_module

        worker = get_current_worker()
        try:
            cfg = config_module.ensure_loaded()
            kw = screen_fetch_kwargs(self.app)
            lines = reads.fetch_live_bank_lines(cfg, self._ids, **kw)
            names = load_account_name_map()
        except Exception as exc:  # surface engine/config errors in-app, don't crash
            if not worker.is_cancelled:
                call_while_attached(self, toast, self, format_error(exc), severity="error")
            return
        if worker.is_cancelled:
            return
        call_while_attached(self, self._populate, flagged_order(lines), names)

    async def _populate(self, lines: list[dict], names: dict) -> None:
        """Paint a read, the cursor on row 1; with no line left, back to the
        statement."""
        self._lines, self._names = lines, names
        self._ids = [str(line.get("id")) for line in lines]
        if not lines:
            self.dismiss(self._ids)
            return
        self.query_one("#fhead", Static).update(flagged_head(self._statement, len(lines), PALETTE))
        rows = flagged_rows(lines, names, palette=PALETTE)
        if self._list is not None:
            self._list.set_rows(rows)
            self._list.set_cursor(0)
            return
        async with self._content_lock():
            self._list = _FlaggedList(
                _FLAGGED_HEADERS, rows, align_right={3}, page_size=self._page_rows()
            )
            await self.query_one("#flist", Container).mount(self._list)

    def _cursor_line(self) -> dict | None:
        key = self._list.cursor_key if self._list is not None else None
        return next((line for line in self._lines if line.get("id") == key), None)

    def action_move(self, delta: int) -> None:
        if self._list is not None:
            self._list.action_move(delta)

    def action_page(self, delta: int) -> None:
        if self._list is not None:
            self._list.action_page(delta)

    def action_open(self) -> None:
        """`⏎` — the line in the ledger's Edit form, which reads it fresh by
        its id; a save reads the flagged lines again."""
        from expense.tui.screens.edit_form import EditFormScreen

        line = self._cursor_line()
        part = first_part(line) if line is not None else None
        if line is None or part is None:
            return
        record = {**part, "bank_line_id": line.get("id")}
        form = EditFormScreen(record=record)
        form.crumb = (*self.crumb, "Edit")
        self.app.push_screen(form, lambda saved: saved and self._load())

    def action_delete_line(self) -> None:
        """`d` — the line under the cursor, after the delete question; deleted,
        the flagged lines are read again and it is gone."""
        line = self._cursor_line()
        if line is not None:
            name = resolve_name(line.get("account_id"), self._names)
            ask_line_delete(self, line, name, after=self._load)

    def action_reload(self) -> None:
        self._load()

    def action_back(self) -> None:
        self.dismiss(self._ids)
