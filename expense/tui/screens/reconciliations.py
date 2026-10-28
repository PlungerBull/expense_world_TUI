"""Reconciliations — list, new batch, and the working/detail screen.

A statement is one holder's (a card, or one bank account alone), with a
balance per account of the holder (contract: "Statements"); every screen
here shows the account it is opened on. The browse opens on the accounts
alone; `⏎` on one reads its holder's statements in one read,
`GET /statements?holder_id=`, whole, and opens them in a panel under the
accounts, the cursor in it. They stand in the order the engine returns them:
`date_start` ascending, then creation time, oldest first
(contract: "Statements", "Ordering"). There `⏎` opens the working screen on
the open account, `n` creates one for its holder, `u` swaps the panel for the
account's bank lines in no batch (`GET /bank-lines`, newest first, a split
purchase one row), and `esc` closes the panel. Nothing is read for an
account until you press `⏎` on it.

On a holder with no statement code the panel lists one row per statement:
Name, Period, the open account's Begin, End and Diff, from its entry in the
statement's `balances`, and Status. On a holder with a code (pane 1 A of
docs/mockups/expense-world-card-statement.html, and task 6's question 3 B
for a holder of one account) its columns are Name, Period, one Diff per
account of the holder (`Diff PEN`, `Diff USD`, in the accounts' order; `Diff`
alone on a holder of one account), Status and Order: each Diff that
account's difference; Order `in order` when the engine's `unplaced_count`
and `shared_place_count` both read 0, `not in order` otherwise
(contract: "Statements", "A statement's order"). The holder's code is read
from `GET /holders`; its accounts are those naming it as `holder_id` in the
accounts read (`statement_columns`). The panel's title names each of them,
then the code, and each of them listed above carries the `▸`.

New batch: name › account › date start › date end › begin › end. Both balances
are typed off the paper statement — the engine never derives a begin, so
`beginning_balance_cents` is required. Both dates are required too
(contract: POST /v1/statements), and are
calendar days sent as typed (contract: "Date inputs"); the form refuses any other shape at
the field. One POST /statements with the holder and the account's balances.

New card statement (NewCardStatementScreen), `n` on an account whose holder
holds another account: name › date start › date end › this account's begin ›
end › the other account's begin › end, the two accounts stated on a line of
their own. One POST /statements with the holder and both accounts' balances
creates the statement (contract: POST /v1/statements).

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
    fetch_all_cursor_pages,
    holder_accounts,
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
#: this account's bank lines in no statement, any day. The list and its count
#: both take it (`GET /bank-lines`, `GET /bank-lines/count`). No `sort` is sent,
#: so the engine lists them newest first, its order when none is asked for
#: (contract: GET /v1/bank-lines, "Ordering"); the list opens with the
#: `GROW_STEP` newest and `pgdn` appends the next ones.
UNFILED_FILTER = {"unreconciled": True}


def balance_of(statement: dict, account_id: object) -> dict:
    """The account's entry in a statement's `balances`, `{}` when it holds none.
    A statement holds one per live account of its holder, each in that
    account's own currency (contract: "Statements", "Statement response")."""
    for balance in statement.get("balances") or []:
        if isinstance(balance, dict) and balance.get("account_id") == account_id:
            return balance
    return {}


def statement_windows(statements: list[dict], account_id) -> list[tuple[str, str, str]]:
    """`(first_day, last_day, name)` of every statement holding a balance of
    this account: the days inside which the "no batch" list marks a row `!`
    (`unfiled_rows`).

    Drafts are in here as well: a line in no statement dated inside a draft's
    days is one its close will flag for review, not a refusal: the close goes
    through (contract: POST /v1/statements/{statement_id}/complete). Completed
    statements are in here too: a line in no statement inside one's days is a
    line its close flagged, or one dated on its last day, which stays open
    until the holder's next statement is completed
    (contract: "Transactions (Ledger)", "Sealed periods"), and the pane exists
    to surface it.
    """
    return [
        (s["date_start"], s["date_end"], s.get("name") or "—")
        for s in statements
        if balance_of(s, account_id)
    ]


def unfiled_rows(lines: list[dict], windows, palette=None) -> list:
    """Rows for the "no batch" list, one per bank line, in the order given (the
    engine's, newest first), `!` on the ones dated inside a statement's days
    (`statement_windows`).

    Each row is one line of the bank's own columns, `bank_line_columns`: the
    day, the title, the operation code (a dim `—` when there is none) and the
    signed `net_cents`. A purchase split into parts is one row with its title
    alone and its total; nothing on the row says it is split.

    **The flag is a hint, not a ruling.** It compares each row's day with the
    days of the statements this screen already holds, so it costs no request.
    It stops nothing: a close goes through with such lines in no statement and
    flags them for review, and which lines it flags is the engine's alone
    (contract: POST /v1/statements/{statement_id}/complete). Nothing downstream
    reads the flag: it only tells you which rows are worth opening first.
    """
    rows = []
    for line in lines:
        day, title, operation, net_cents = bank_line_columns(line)
        inside = any(start <= day <= end for start, end, _name in windows)
        if not inside:
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


def batch_rows(items: list[dict], account_id: object, palette: Palette | None = None) -> list:
    """The browse's lower pane on a holder with no statement code, one row per
    statement (no Account column): its name and days, then `account_id`'s
    balances in it, from that account's entry in `balances` (`balance_of`),
    and its status."""
    rows = []
    for it in items:
        status = it.get("status")
        balance = balance_of(it, account_id)
        cells = [
            it.get("name") or "(unnamed)",
            _period(it),
            amount_cell(balance.get("beginning_balance_cents"), palette, BALANCE_RULE),
            amount_cell(balance.get("ending_balance_cents"), palette, BALANCE_RULE),
            difference_cell(balance.get("difference_cents"), palette),
            formatting.format_status(status),
        ]
        rows.append((it.get("id"), cells, "dim" if status == 2 else ""))
    return rows


def holder_of(accounts: list[dict], account_id: object) -> str | None:
    """The id of the holder `account_id` is on, from one accounts read: every
    real account is on exactly one (contract: "Holders")."""
    own = next((a for a in accounts if a.get("id") == account_id), None)
    holder = own.get("holder_id") if own else None
    return str(holder) if holder else None


def holder_mates(accounts: list[dict], account_id: object) -> list[tuple[str, str, str]]:
    """Every account on `account_id`'s holder as `(id, name, currency)`, the
    account itself included, in the accounts read's order: the accounts a
    statement of the holder holds a balance for
    (contract: "Statements", "A statement covers its whole holder")."""
    holder = holder_of(accounts, account_id)
    held = holder_accounts(accounts).get(holder, []) if holder else []
    return [(a["id"], a.get("name") or "(unnamed)", a.get("currency_code") or "?") for a in held]


class StatementAccounts(NamedTuple):
    """What a statement list is titled and laid out by: the open account's
    holder's statement code, and the accounts it shows a Diff column for as
    `(id, name, currency)`, in the accounts read's order."""

    code: str
    accounts: tuple[tuple[str, str, str], ...]


def statement_columns(
    account_id: object, accounts: list[dict], codes: dict[str, str | None]
) -> StatementAccounts | None:
    """The statement list of `account_id`'s panel: its holder's statement code
    and the holder's accounts (`holder_mates`); None on a holder with no code.

    The code is the holder's, never an account's (contract: "Holders",
    "Statement code"): `codes` maps each holder's id to its `statement_code`,
    from one `GET /holders`. Every account of the holder shows, since each
    statement holds a balance for each of them; a holder is archived whole,
    so its accounts are listed or archived together
    (contract: "Holders", "A holder is archived whole").
    """
    holder = holder_of(accounts, account_id)
    code = codes.get(holder) if holder else None
    if not code:
        return None
    return StatementAccounts(code, tuple(holder_mates(accounts, account_id)))


def statement_headers(accounts: tuple) -> tuple[list[str], set[int]]:
    """`(headers, right-aligned columns)` of a statement list: Name, Period,
    a Diff per account of the statement, `(id, name, currency)` in the
    accounts' order, then Status and Order. One account: `Diff` alone."""
    if len(accounts) == 1:
        diffs = ["Diff"]
    else:
        diffs = [f"Diff {currency}" for _aid, _name, currency in accounts]
    return ["Name", "Period", *diffs, "Status", "Order"], set(range(2, 2 + len(diffs)))


def order_cell(item: dict, palette: Palette | None = None) -> str | Text:
    """Whether a statement is in order, as the engine counts it: `in order`
    when its lines with no place and its places held twice both read 0,
    `not in order` otherwise; null counts (a holder with no statement code,
    so no order) show nothing (contract: "Statements", "A statement's order")."""
    unplaced, shared = item.get("unplaced_count"), item.get("shared_place_count")
    if unplaced is None or shared is None:
        return ""
    if unplaced == 0 and shared == 0:
        return "in order"
    return Text("not in order", style=palette.warning) if palette else "not in order"


def statement_rows(items: list[dict], accounts: tuple, palette: Palette | None = None) -> list:
    """One row per statement of a holder with a statement code, from one
    `GET /statements?holder_id=` answer in the engine's order, keyed by the
    statement's id.

    `accounts` are the holder's accounts (`statement_columns`),
    `(id, name, currency)`, one Diff column each: that account's
    `difference_cents`, from its entry in the statement's `balances`. The
    status is the statement's one status, which holds for every account of
    its holder (contract: "Statements").
    """
    rows = []
    for item in items:
        status = item.get("status")
        diffs = [
            difference_cell(balance_of(item, aid).get("difference_cents"), palette)
            for aid, _name, _currency in accounts
        ]
        cells = [
            item.get("name") or "(unnamed)",
            _period(item),
            *diffs,
            formatting.format_status(status),
            order_cell(item, palette),
        ]
        rows.append((item.get("id"), cells, "dim" if status == 2 else ""))
    return rows


def _read_statements(cfg, accounts: list[dict], account_id: object, kw: dict) -> list:
    """The panel's one read: every statement of `account_id`'s holder, whole
    (`GET /statements?holder_id=`). A listed account is a real one, on exactly
    one holder (contract: "Holders"); were it on none, the engine's refusal of
    the empty `holder_id` is what shows."""
    holder = holder_of(accounts, account_id) or ""
    return items_of(reads.fetch_statements(cfg, holder, **kw))


def account_view(statement: dict, account_id: object) -> dict:
    """A statement as the batch screen reads it, opened on one account: the
    statement's own fields, then that account's entry in `balances`
    (`account_id` and its balances) over them."""
    return {**statement, **balance_of(statement, account_id)}


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
    """Accounts first; the statements of one account's holder on `⏎`.

    The screen opens on the account list alone, and nothing about statements
    is read until you press `⏎` on an account, so moving the cursor costs
    nothing. `⏎` reads its holder's statements in one read,
    `GET /statements?holder_id=`, whole, in the order the module docstring
    gives, each row showing the open account's balances in it: on a holder
    with no statement code its Begin, End and Diff; on one with a code a Diff
    per account of the holder. It opens the panel under the accounts with the
    cursor in it. There `⏎` opens a statement on the open account, `n`
    creates one, `u` swaps the panel for the account's rows in no batch, and
    `esc` closes the panel.

    The accounts are one read, archived ones left out: a holder is archived
    whole, so an account listed is on a live holder whose every account is
    listed too (contract: "Holders", "A holder is archived whole"). The
    holders are one read, for each one's statement code.
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
        self._recons: list = []  # the open account's holder's statements, engine order
        self._accounts: list = []  # (id, name, currency, balance_cents)
        # the accounts read: pairs an account with its holder's other accounts
        self._known: list[dict] = []
        self._codes: dict[str, str | None] = {}  # holder id → its statement code
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
        """The accounts and the holders, and the open account's holder's
        statements when a panel is open — which is how a return from a
        statement, or from `n`, comes back to the same panel."""
        from expense import config as config_module

        cfg = config_module.ensure_loaded()
        kw = screen_fetch_kwargs(self.app)
        accts = items_of(reads.fetch_accounts(cfg, **kw))
        holders = items_of(reads.fetch_holders(cfg, **kw))
        accounts = account_choices(accts, include_people=False, with_balance=True)
        recons = None
        if self._open_aid is not None:
            recons = _read_statements(cfg, accts, self._open_aid, kw)
        return {
            "recons": recons,
            "accounts": accounts,
            "known": accts,
            "codes": {h.get("id"): h.get("statement_code") for h in holders},
        }

    def _selected_account(self):
        return self._accounts[self._acct_idx] if self._accounts else None

    def _open_account(self):
        return next((a for a in self._accounts if a[0] == self._open_aid), None)

    def _open_statement(self) -> StatementAccounts | None:
        """The open account's holder's code and the accounts its statement list
        shows; None with no panel open or on a holder with no code."""
        if self._open_aid is None:
            return None
        return statement_columns(self._open_aid, self._known, self._codes)

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
            return batch_rows(self._recons, self._open_aid, palette=PALETTE)
        return statement_rows(self._recons, statement.accounts, palette=PALETTE)

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
        is showing once the cursor has gone down into it; on a holder with a
        statement code, every account the panel's statement list shows does."""
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
        self._known = data["known"]
        self._codes = data["codes"]
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
        # `⏎` on a statement opens its detail on the open account, in its currency
        item = self._by_id.get(event.key)
        acct = self._open_account()
        if item and acct:
            self._resume_key = event.key
            self.app.push_screen(
                ReconciliationDetailScreen(account_view(item, acct[0]), currency=acct[2]),
                lambda _result: self._load(),
            )

    @work(thread=True, exclusive=True, group="recon-batches")
    def _load_batches(self, account_id: str) -> None:
        """`⏎` on an account: read its holder's statements. A read that fails
        leaves the panel closed, with a toast."""
        from expense import config as config_module

        worker = get_current_worker()
        try:
            cfg = config_module.ensure_loaded()
            kw = screen_fetch_kwargs(self.app)
            statements = _read_statements(cfg, self._known, account_id, kw)
        except Exception as exc:
            if not worker.is_cancelled:
                self.app.call_from_thread(
                    toast, self, format_error(exc), title="Failed", severity="error"
                )
            return
        if worker.is_cancelled:
            return
        self.app.call_from_thread(self._open_panel, account_id, statements)

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
        windows = statement_windows(self._recons, self._open_aid)
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
        # the panel already holds the holder's statements: the `!` costs no
        # read of its own
        windows = statement_windows(self._recons, self._open_aid)
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
            " · newest first   ·   ! dated inside a statement"
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
        """`n` — a statement for the open account's holder, or, with no panel
        open, for the holder of the account under the cursor. Saved, it opens
        that account's panel with the cursor on the new one. On an account
        whose holder holds another account, a card's, it is the card
        statement's form, both accounts' balances in one write."""
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

        holder = holder_of(self._known, acct[0])
        code = self._codes.get(holder) if holder else None
        others = [mate for mate in holder_mates(self._known, acct[0]) if mate[0] != acct[0]]
        form = (
            NewReconciliationScreen(account_id=acct[0], account_name=acct[1], holder_id=holder)
            if not others
            else NewCardStatementScreen(
                account=acct[:3], partner=others[0], code=code or "", holder_id=holder
            )
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
#: transaction, that line included, into the account's add-up check
#: (contract: "Statements", "`difference_cents` — the add-up check").
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
#: A balance's keys: the open account's, and on a card statement's form the
#: other account's too (`twin_…`).
_BEGINS = {"begin", "twin_begin"}
_ENDS = {"end", "twin_end"}
_AMOUNTS = _BEGINS | _ENDS
_BEGIN_UNREADABLE = "Begin balance: a signed decimal, e.g. 9580.00"
#: The note for an ending balance the money parser cannot read — the New
#: Reconciliation form's and the batch screen's ending-balance box.
_END_UNREADABLE = "End balance: a signed decimal, e.g. 9460.00"
_DATES = {"date_start", "date_end"}


class NewReconciliationScreen(FormScreen):
    """A new statement of a holder of one account: one `POST /statements` with
    the holder and that account's balances (contract: POST /v1/statements).
    Opened from the browse on its account (`account_id`, `holder_id`), or
    alone, with the account picked on the form and its holder read off the
    accounts read."""

    RESOURCE = "statements"

    def __init__(
        self,
        account_id: str | None = None,
        account_name: str | None = None,
        *,
        holder_id: str | None = None,
    ) -> None:
        super().__init__()
        self._values: dict = {}
        self._display: dict = {}
        self._accounts: list = []
        self._holders: dict = {}  # account id → its holder id, from the accounts read
        self._holder_id = holder_id
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
        # begin: the engine never derives it, so it is typed off the paper
        # (contract: "Statements", "Statement response"). Both dates: the
        # engine requires them (contract: POST /v1/statements); asking here
        # refuses an empty one at the field instead of as a 422 on save.
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
        items = items_of(body)
        holders = {a.get("id"): a.get("holder_id") for a in items}
        accounts = account_choices(items, include_people=False)
        self.app.call_from_thread(self._set_accounts, accounts, holders)

    def _set_accounts(self, accounts: list, holders: dict) -> None:
        self._accounts = accounts
        self._holders = holders
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
            self._holder_id = self._holders.get(picked[0])
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
        """The statement: its id, minted here, its holder, name and days, and
        one entry in `balances` per account of the holder
        (contract: POST /v1/statements)."""
        self._new_id = str(uuid.uuid4())
        return {
            "id": self._new_id,
            "holder_id": self._holder_id,
            "name": self._values["name"],
            # calendar days, sent as typed — the engine refuses any datetime here
            "date_start": self._values["date_start"],
            "date_end": self._values["date_end"],
            "balances": self._balances(),
        }

    def _balances(self) -> list[dict]:
        """The holder's one account's balances."""
        return [self._balance_entry(self._values["account"], "")]

    def _balance_entry(self, account_id: str, side: str) -> dict:
        """One account's entry in `balances`: its begin, and its end when one
        was typed (left out, it is not entered yet). `side` is the prefix of
        the form's keys for that account: `""` or `"twin_"`."""
        entry = {"account_id": account_id, "beginning_balance_cents": self._values[f"{side}begin"]}
        if self._values.get(f"{side}end") is not None:
            entry["ending_balance_cents"] = self._values[f"{side}end"]
        return entry

    def _done(self) -> None:
        """Dismiss with the new id — minted here, in `_payload` — so the browse
        can land its cursor on the statement just made."""
        self.notify("Reconciliation created.")
        self.dismiss(self._new_id)


class NewCardStatementScreen(NewReconciliationScreen):
    """A card statement: both accounts' balances in one form and one write
    (pane 2 A of docs/mockups/expense-world-card-statement.html).

    Opened by `n` on an account whose holder holds another account, a card's
    (`holder_mates`). The name and the days are typed once; then this
    account's balances, then the other account's, each in its own currency.
    `^s Create both` sends one `POST /statements` with the holder and an entry
    in `balances` for each account (contract: POST /v1/statements). The
    statement is created whole, or not at all; a refusal is the engine's words
    in the form's `Failed` note, a key on one account's balances naming it by
    its id, or a key on the request's list by its entry's place
    (contract: "Statements", "Which account a refusal names"), and the form
    stays with what was typed. Saved, it says `Statement created.` and hands
    back the statement's id, as the one-account form does.
    """

    BINDINGS = form_bindings("Create both")
    _STATED = frozenset({"accounts"})

    def __init__(self, *, account: tuple, partner: tuple, code: str, holder_id: str | None) -> None:
        """`account` and `partner` are `(id, name, currency)`: the account the
        list was opened from, whose balances come first, and the other account
        of its holder; `code` is the holder's statement code, `""` for none,
        and `holder_id` the holder."""
        super().__init__(account_id=account[0], account_name=account[1], holder_id=holder_id)
        self._currencies = {"": account[2], "twin_": partner[2]}
        self._partner_id = partner[0]
        self._locked = {"accounts"}
        accounts = f"{account[1]} + {partner[1]}"
        self._display["accounts"] = f"{accounts} · {code}" if code else accounts

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

    def _balances(self) -> list[dict]:
        """This account's balances, then the other account's."""
        return [*super()._balances(), self._balance_entry(self._partner_id, "twin_")]

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
        self._show_flagged(review_line_ids(body))

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
        line.update(flagged_note(len(self._flagged)))
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


def review_line_ids(body: dict) -> list[str]:
    """The ids of the bank lines a close flagged for review, the named half's
    `review_lines`, then the other half's (`twin.review_lines`)
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Response")."""
    twin = body.get("twin")
    halves = [body, twin] if isinstance(twin, dict) else [body]
    ids: list[str] = []
    for half in halves:
        named = half.get("review_lines")
        if isinstance(named, list):
            ids.extend(str(line_id) for line_id in named if line_id)
    return ids


def flagged_note(n: int) -> Text:
    """The `⚑` line of a close that flagged `n` lines, and `f` beside it: on a
    statement after its complete, and after a statement PDF closed it."""
    return Text.assemble(
        (
            f"⚑ {line_count(n)} flagged for review: in no statement,"
            " dated up to this one's last day",
            PALETTE.warning,
        ),
        ("  · f shows them", "dim"),
    )


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
    so the screen reads them by those ids, oldest first, both halves together
    (`reads.fetch_bank_lines_by_ids`, `sort=date_asc`), and lists them in the
    engine's order: `Date · Account · Title · Amount`. A line the engine no
    longer has is left out of the read, so it drops from the list. `⏎` opens
    the line in the ledger's Edit form, `d` deletes it after the delete
    question, and after either the ids are read again. `esc` goes back to the statement, handing it
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
        """The lines still flagged, read by their ids oldest first, and the
        accounts' names. More than 200 ids are read 200 at a time, so the order
        is oldest first within each read only (`reads.fetch_bank_lines_by_ids`).
        A failed read shows the engine's words and keeps what is listed."""
        from expense import config as config_module

        worker = get_current_worker()
        try:
            cfg = config_module.ensure_loaded()
            kw = screen_fetch_kwargs(self.app)
            lines = reads.fetch_bank_lines_by_ids(cfg, self._ids, sort="date_asc", **kw)
            names = load_account_name_map()
        except Exception as exc:  # surface engine/config errors in-app, don't crash
            if not worker.is_cancelled:
                call_while_attached(self, toast, self, format_error(exc), severity="error")
            return
        if worker.is_cancelled:
            return
        call_while_attached(self, self._populate, lines, names)

    async def _populate(self, lines: list[dict], names: dict) -> None:
        """Paint a read, the cursor on row 1; with no line left, back to the
        statement. The ids still flagged keep the close's order, so the next
        read splits them as the close sent them."""
        self._lines, self._names = lines, names
        live = {str(line.get("id")) for line in lines}
        self._ids = [line_id for line_id in self._ids if line_id in live]
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
