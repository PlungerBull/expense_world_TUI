"""Statements — the browse, the New statement form, and the statement's screen.

A statement is one account's: one name, one set of days, one status, and a starting
and an ending balance for each currency it covers, never added together
(contract: "Statements"). The browse opens on the bank accounts alone, one row each
with its currencies and their balances; `⏎` on one reads its statements in one read,
`GET /statements?account_id=`, whole, and opens them in a panel under the accounts,
the cursor in it. They stand in the order the engine returns them: `date_start`
ascending, then creation time, oldest first (contract: "Statements", "Ordering").
There `⏎` opens the working screen on the open account, `n` creates one for it, `u`
swaps the panel for the account's bank lines in no statement (`GET /bank-lines`, every
currency together, oldest first, a split transaction one row), and `esc` closes the
panel. Nothing is read for an account until you press `⏎` on it.

The panel lists one row per statement: Name, Period, one Diff per currency the
account holds (`Diff PEN`, `Diff USD`, in the account's order; `Diff` alone on an
account of one currency), Status and, on an account with a statement code, Order:
`in order` when the engine's `unplaced_count` and `shared_place_count` both read 0,
`not in order` otherwise (contract: "Statements", "A statement's order"). A currency
the statement does not cover shows nothing in its Diff column. The code is the
account's own (contract: "What an account is", "Statement code"); an account without
one has no Order column. The panel's title names the account, its currencies and its
code.

New statement (NewStatementScreen): name › account (skipped when opened from the
browse on an account) › date start › date end › a begin and an end balance line for each
currency of the account. The balances are typed off the paper statement, and every
balance line is optional: which currency the statement needs is the engine's call
(contract: POST /v1/statements). The dates are calendar days sent as typed
(contract: "Date inputs"); both are required, and the form refuses an empty one or any
other shape at the field. One POST /statements with `account_id` and an entry in
`balances` for each currency that has a balance typed.

Working screen (StatementScreen): the whole statement. Its head
shows each currency in the statement's `balances` once, begin, end and diff
(`balance_lines`); over a checklist of bank lines — the statement's, every
currency of its account together in the statement's order, then the account's in
its period that are in no statement, oldest first (draft) — or a read-only
list of the statement's lines (completed; numbered only on an account with a
statement code), read by account from
`GET /bank-lines` so a split transaction is one row with its total.
`space` toggles membership (PUT `statement_id` on one part, which moves
the whole line) and reads the statement and its list again;
`c`/`u`/`d` complete/revert/delete the whole statement, every currency of
it, under `/statements/{id}`; `r` reads the statement again by its id,
`GET /statements/{id}`, and the checklist. Complete needs a transaction on at
least one account of the statement and locks the amount, date, title, account,
operation number and statement of each, an empty title or operation number
staying fillable (contract: PUT /v1/transactions/{transaction_id}, "Field locking");
delete is draft-only and just detaches the transactions. Completing also needs
every balance (contract: POST /v1/statements/{statement_id}/complete,
"Every balance must be entered"): `c` on a draft with a blank balance first asks
for each in a box, saves them in the statement's `balances` with one
PUT /statements/{id}, then asks the usual "Complete statement?". A complete
that leaves the statement's review list holding a line opens FlaggedLinesScreen on it. The working
screen keeps a `⚑` line and `f` while the review list counts any line, open or completed,
counted each time the screen reads the statement. An open statement on an account with a
statement code waits for its PDF to be dropped on the LOG bar: it lists no bank lines from
outside the statement, is read-only, and has no `c`, `u` or toggle.
"""

import uuid
from collections.abc import Callable
from functools import partial
from typing import NamedTuple, TypedDict

from rich.console import Group, RenderableType
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import ActiveBinding, Binding
from textual.containers import Container
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Input, Static
from textual.worker import get_current_worker

from expense import formatting, reads
from expense.bank_import.statement import LooseLines, loose_lines
from expense.dates import is_calendar_day
from expense.errors import EngineError, format_error
from expense.formatting import (
    bank_line_columns,
    close_notes,
    format_cents,
    is_split_line,
    name_or_unnamed,
    resolve_name,
    signed_cents,
    title_or_untitled,
)
from expense.number_format import amounts_sentence, current_format
from expense.quickadd.money import amount_to_text, parse_amount
from expense.reads import (
    fetch_all_cursor_pages,
    items_of,
    load_account_name_map,
)
from expense.tui.screens._base import (
    AdaptiveRowsMixin,
    ContentSwapLockMixin,
    EngineWriteMixin,
    LeftBehind,
    NewestReadMixin,
    SectionScreen,
    bank_line_delete_message,
    bank_line_delete_question,
    call_while_attached,
    list_refusal_text,
    not_deleted_line,
    not_done_line,
    not_done_transaction_line,
    screen_fetch_kwargs,
    still_attached,
    transaction_delete_message,
)
from expense.tui.screens._form import FormScreen
from expense.tui.screens._growing import GrowingRead, read_first
from expense.tui.screens.help import HelpBindingMixin
from expense.tui.screens.modals import AmountPromptModal, ConfirmModal
from expense.tui.theme import ACCENT, AMOUNT_RULE, BALANCE_RULE, PALETTE, TRANSACTION_RULE, Palette
from expense.tui.widgets.cells import amount_cell, amount_text, difference_cell, operation_cell
from expense.tui.widgets.checklist import AMOUNT_WIDTH, TITLE_WIDTH, CheckList
from expense.tui.widgets.cursor_list import LIST_KEYS, CursorList, list_cell, waits_for_a_row
from expense.tui.widgets.footer import FittingFooter
from expense.tui.widgets.header import Breadcrumb
from expense.tui.widgets.picker import matching
from expense.tui.widgets.refusal import as_markup, toast, under_itself, warning_note

# Status labels + period formatting are owned by expense/formatting.py
# (format_status / format_period) — one copy, per the §5 rule.
_period = formatting.format_period

#: What the leftover lines' screen hands back when `c` was pressed: the statement asks
#: "Complete statement?" again.
CLOSE_AGAIN = "close"

#: The blank cells between two columns of the browse's lists (accounts, statements, lines in
#: no statement): two, where the shared table has three.
BROWSE_GAP = 2

_UNFILED_HEADERS = ["", "Date", "Title", "Operation", "Cur", "Amount"]


class _UnfiledLayout(TypedDict):
    """The keyword arguments of `CursorList.set_headers` the list sets."""

    align_right: set[int]
    edge: bool
    header_rule: bool
    lead: bool
    gap: int
    gives_way: set[int]
    min_widths: dict[int, int]


class _PanelLayout(TypedDict):
    """The keyword arguments of `CursorList.set_headers` the statements list sets."""

    gap: int
    gives_way: set[int]


#: How the list sits in its room: the `!` mark packed to the date, the columns two cells
#: apart, the title at least `TITLE_WIDTH` wide and the amount `AMOUNT_WIDTH`, and the
#: title the one that is cut, with `…`, when the row is too wide (the statement's own
#: list is drawn the same way, checklist.py).
_UNFILED_LAYOUT = _UnfiledLayout(
    align_right={5},
    edge=False,
    header_rule=False,
    lead=True,
    gap=BROWSE_GAP,
    gives_way={2},
    min_widths={2: TITLE_WIDTH, 5: AMOUNT_WIDTH},
)
#: The keys of the footer in the order it reads while the lines in no statement are
#: listed; any other key the list offers (`pgdn`, `pgup`) follows them.
_UNFILED_FOOTER = ("escape", "enter", "d", "r", "question_mark")

#: What the "no statement" list asks the engine for, with the account and no dates:
#: this account's bank lines in no statement, any day, every currency together. The
#: list and its count both take it (`GET /bank-lines`, `GET /bank-lines/count`).
#: The list alone adds `UNFILED_SORT` (the count takes no order); it opens with the
#: `GROW_STEP` oldest and `pgdn` appends the next ones
#: (contract: GET /v1/bank-lines, "Filters").
UNFILED_FILTER = {"unreconciled": True}
#: Oldest first, the order of the lines of a statement that hold no place
#: (contract: GET /v1/bank-lines, "Ordering").
UNFILED_SORT = "date_asc"


def balance_of(statement: dict, currency_code: object) -> dict:
    """The currency's entry in a statement's `balances`, `{}` when the statement
    does not cover it. A statement holds one per currency it covers, each keyed
    by `currency_code` (contract: "Statements", "Which currencies a statement covers")."""
    for balance in statement.get("balances") or []:
        if isinstance(balance, dict) and balance.get("currency_code") == currency_code:
            return balance
    return {}


def statement_windows(statements: list[dict]) -> list[tuple[str, str, str]]:
    """`(first_day, last_day, name)` of every statement of the account: the days
    inside which the "no statement" list marks a row `!` (`unfiled_rows`).

    Drafts are in here as well: a line in no statement dated inside a draft's
    days is one its close will flag for review, not a refusal: the close goes
    through (contract: POST /v1/statements/{statement_id}/complete). Completed
    statements are in here too: a line in no statement inside one's days is a
    line its close flagged, or one dated on its last day, which stays open
    until the account's next statement is completed
    (contract: "Transactions (Ledger)", "Sealed periods"), and the pane exists
    to surface it.
    """
    return [(s["date_start"], s["date_end"], s.get("name") or "—") for s in statements]


def unfiled_rows(lines: list[dict], windows, palette=None) -> list:
    """Rows for the "no statement" list, one per bank line, in the order given (the
    engine's, oldest first), `!` on the ones dated inside a statement's days
    (`statement_windows`).

    Each row is one line of the bank's own columns, `bank_line_columns`: the
    day, the title, the operation code (a dim `—` when there is none), the
    line's currency and the signed `net_cents`. A split transaction is one row
    with its title alone and its total; nothing on the row says it is split.

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
                    title_or_untitled(title),
                    operation_cell(operation),
                    line.get("currency_code") or "",
                    amount_cell(net_cents, palette, TRANSACTION_RULE),
                ],
            )
        )
    return rows


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
    screen: EngineWriteMixin,
    line: dict,
    account_name: str,
    *,
    after: Callable[[], None],
    error_text: Callable[[Exception], str] | None = None,
) -> None:
    """`d` on a bank line a list holds: the question, then the delete, through
    `confirm_delete` (only `y` deletes). A split transaction (`part_count` above 1)
    goes whole, in one `DELETE /bank-lines/{id}`
    (contract: DELETE /v1/bank-lines/{bank_line_id}), after the question naming its
    part count; a line never split goes as its one transaction, in
    `DELETE /transactions/{id}`, after the ledger's question. Each question says no
    screen can bring it back. The line in hand is the list's own read, so nothing is
    read before asking. Deleted, `after` reads the list again; a refusal reads as
    `error_text` says (`list_refusal_text` unless the screen has no `r`). Shared by the "no
    statement" pane, the flagged lines' screen and the leftover lines' screen."""
    if is_split_line(line):
        _day, line_title, _operation, line_net = bank_line_columns(line)
        screen.confirm_delete(
            "bank-lines",
            line.get("id"),
            bank_line_delete_question(line),
            bank_line_delete_message(line, account_name),
            done="Transaction deleted.",
            after=after,
            left_behind=LeftBehind(not_deleted_line(line_title, line_net)),
            error_text=error_text,
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
        left_behind=LeftBehind(not_deleted_line(record.get("title"), record.get("amount_cents"))),
        error_text=error_text,
    )


def open_edit_form(
    screen: Screen, line: dict, *, crumb: tuple[str, ...], reload: Callable[[], None]
) -> None:
    """`⏎` on a bank line a list holds: the ledger's Edit form on its first part,
    which reads the line fresh by its id, its breadcrumb the list's own then `Edit`.
    A save reads the list again (`reload`), also when it is answered after the form
    is left. Shared by the flagged lines' screen and the leftover lines' screen."""
    from expense.tui.screens.edit_form import EditFormScreen

    part = first_part(line)
    if part is None:
        return
    _day, title, _operation, net_cents = bank_line_columns(line)
    form = EditFormScreen(
        record={**part, "bank_line_id": line.get("id")},
        opener=screen,
        reload=reload,
        shown=(title, net_cents),
    )
    form.crumb = (*crumb, "Edit")
    screen.app.push_screen(form, lambda saved: saved and reload())


def run_assignment(
    screen: EngineWriteMixin,
    part_id: object,
    statement_id: object | None,
    *,
    not_done: str,
    words: tuple[object, object],
    on_success: Callable[[], None],
    on_error: Callable[[str], None],
    error_text: Callable[[Exception], str] = list_refusal_text,
) -> None:
    """`space` on a line: one `PUT` of `statement_id` on one part of the line, which puts
    every part in the statement, or (`None`) takes every part out
    (contract: PUT /v1/transactions/{transaction_id}, "Line fields"). `not_done` and `words`
    (the line's title and amount as its list shows them) are the first line of the note of
    a refusal that arrives after the screen has left; `error_text` says how a refusal reads.
    Shared by the statement's checklist and the leftover lines' screen."""
    screen.run_write(
        "PUT",
        f"/transactions/{part_id}",
        json_body={"statement_id": statement_id},
        on_success=on_success,
        on_error=on_error,
        error_text=error_text,
        left_behind=LeftBehind(
            not_done_transaction_line(not_done, *words),
            success_from=lambda _body: None,  # a tick that lands shows nothing
        ),
    )


def first_part(line: dict) -> dict | None:
    """The line's first part, the one a write on the line names; None when
    the read holds no part with an id."""
    parts = line.get("parts")
    if not isinstance(parts, list) or not parts:
        return None
    part = parts[0]
    return part if isinstance(part, dict) and part.get("id") else None


class BrowseAccount(NamedTuple):
    """One row of the browse: a bank account, its currencies with the balance in
    each as `(code, current_balance_cents)` in the engine's order, and its own
    statement code, `None` when it has none."""

    id: str
    name: str
    currencies: tuple[tuple[str, int | None], ...]
    code: str | None

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(code for code, _cents in self.currencies)

    @property
    def phrase(self) -> str:
        """`PEN`, or `PEN + USD`."""
        return formatting.currencies_phrase(self.codes)


def browse_accounts(items: list[dict]) -> list[BrowseAccount]:
    """The browse's rows from one accounts read, in the order given: every bank
    account once under its own name, people and cash accounts left out
    (`reads.takes_statements`). The currencies are the
    account's `currencies` as sent (`reads.held_currencies`, the one walk over
    them), and the statement code is the account's
    (contract: "What an account is", "Statement code"). `AccountPick` of the bank
    import carries no balance, so it does not serve here."""
    banks = [a for a in items if a.get("id") and reads.takes_statements(a)]
    held: dict[str, list[tuple[str, int | None]]] = {}
    for account, _name, entry in reads.held_currencies(banks):
        held.setdefault(account["id"], []).append(
            (entry["currency_code"], entry.get("current_balance_cents"))
        )
    return [
        BrowseAccount(
            a["id"],
            name_or_unnamed(a.get("name")),
            tuple(held.get(a["id"], [])),
            a.get("statement_code") or None,
        )
        for a in banks
    ]


def balance_figure(code: str, cents: int | None, palette: Palette | None) -> Text:
    """One currency's balance as `-234.20 PEN`."""
    figure = amount_text(cents, palette, AMOUNT_RULE)
    figure.append(f" {code}")
    return figure


def balances_cells(accounts: list[BrowseAccount], palette: Palette | None) -> list[Text]:
    """Each account's balances, one figure and its code per currency, never added
    together. Every account's first figure ends in one place, the widest one's,
    and the second follows it: `-234.20 PEN   -30.98 USD` over `12,450.00 PEN`."""
    firsts = [
        balance_figure(*acct.currencies[0], palette) if acct.currencies else Text()
        for acct in accounts
    ]
    width = max((first.cell_len for first in firsts), default=0)
    cells = []
    for acct, first in zip(accounts, firsts, strict=True):
        cell = Text(" " * (width - first.cell_len))
        cell.append_text(first)
        for code, cents in acct.currencies[1:]:
            cell.append("   ")
            cell.append_text(balance_figure(code, cents, palette))
        cells.append(cell)
    return cells


#: The statements' gap on an account with a statement code, whose Order column needs the room.
ORDER_GAP = 1
#: The account list's headers: `Account` over the names, which stand two cells in, after
#: the open account's `▸`.
_ACCOUNT_HEADERS = ["  Account", "Currencies", "Balances"]
#: The rule under that header: 60 cells of `─` starting under the `A` of `Account`.
ACCOUNT_RULE_INDENT = 2
ACCOUNT_RULE_WIDTH = 60
#: The Account column's least width (its two-cell gutter included); a longer name is cut with
#: `…` before a balance loses a letter.
ACCOUNT_NAME_WIDTH = 18


def statement_headers(
    currencies: tuple[str, ...], *, with_order: bool
) -> tuple[list[str], set[int]]:
    """`(headers, right-aligned columns)` of a statement list: Name, Period,
    a Diff per currency of the account in its order (`Diff` alone on one), Status,
    and Order when the account has a statement code."""
    diffs = ["Diff"] if len(currencies) == 1 else [f"Diff {code}" for code in currencies]
    headers = ["Name", "Period", *diffs, "Status", *(["Order"] if with_order else [])]
    return headers, set(range(2, 2 + len(diffs)))


def order_cell(item: dict, palette: Palette | None = None) -> str | Text:
    """Whether a statement is in order, as the engine counts it: `in order`
    when its lines with no place and its places held twice both read 0,
    `not in order` otherwise; null counts (an account with no statement code,
    so no order) show nothing (contract: "Statements", "A statement's order")."""
    unplaced, shared = item.get("unplaced_count"), item.get("shared_place_count")
    if unplaced is None or shared is None:
        return ""
    if unplaced == 0 and shared == 0:
        return "in order"
    return Text("not in order", style=palette.warning) if palette else "not in order"


def statement_rows(
    items: list[dict],
    currencies: tuple[str, ...],
    palette: Palette | None = None,
    *,
    with_order: bool,
) -> list:
    """One row per statement of an account, from one `GET /statements?account_id=`
    answer in the engine's order, keyed by the statement's id.

    `currencies` are the account's, one Diff column each: that currency's
    `difference_cents`, from its entry in the statement's `balances`. A currency
    the statement does not cover has no entry and shows nothing, and a difference
    not checked yet (`null`) shows nothing too (`difference_cell`). The status is
    the statement's one status (contract: "Statements"); `with_order` adds the
    Order cell, on an account with a statement code.
    """
    rows = []
    for item in items:
        status = item.get("status")
        cells = [
            name_or_unnamed(item.get("name")),
            _period(item),
            *(
                difference_cell(balance_of(item, code).get("difference_cents"), palette)
                for code in currencies
            ),
            formatting.format_status(status),
        ]
        if with_order:
            cells.append(order_cell(item, palette))
        rows.append((item.get("id"), cells, "dim" if status == 2 else ""))
    return rows


def _read_statements(cfg, account_id: object, kw: dict) -> list:
    """The panel's one read: every statement of the account, whole
    (`GET /statements?account_id=`)."""
    return items_of(reads.fetch_statements(cfg, str(account_id), **kw))


class _AccountList(CursorList):
    """The browse's account list. Only `enter` changes: on this list it opens
    the account's panel, so the footer names that instead of `Open`."""

    BINDINGS = [Binding("enter", "select", "Its statements")]
    #: The `?` card lists the page keys only while `check_action` allows them, and no list
    #: key while there is no account (help.py).
    CARD_FOLLOWS_CHECK = frozenset({"more", "page"})


class _PanelList(CursorList):
    """The panel under the accounts. It lists two things: a
    statement, which `enter` opens, or a row in no statement, which `enter`
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
    CARD_FOLLOWS_CHECK = frozenset({"edit_row", "select", "more", "page"})
    #: Every list key, and `edit_row`, leaves with no row to open or edit.
    CARD_NEEDS_A_ROW = LIST_KEYS | {"edit_row"}

    def _listing_unfiled(self) -> bool:
        try:
            return getattr(self.screen, "_mode", None) == "unfiled"
        except Exception:
            return False

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if waits_for_a_row(self, action):
            return False
        if action == "edit_row":
            return self._listing_unfiled()
        if action == "select" and self._listing_unfiled():
            return False
        return super().check_action(action, parameters)

    def action_edit_row(self) -> None:
        self.action_select()  # the screen's Selected handler opens the edit form


class StatementsScreen(SectionScreen):
    """Accounts first; the statements of one account on `⏎`.

    The screen opens on the account list alone, and nothing about statements
    is read until you press `⏎` on an account, so moving the cursor costs
    nothing. `⏎` reads its statements in one read, `GET /statements?account_id=`,
    whole, in the order the module docstring gives, each row showing a Diff per
    currency of the account, its status and, on an account with a statement code,
    its order. It opens the panel under the accounts with the cursor in it.
    There `⏎` opens a statement on the open account, `n` creates one, `u` swaps
    the panel for the account's rows in no statement, and `esc` closes the panel.

    The accounts are one read, archived ones left out; each shows its currencies
    and the balance in each, and its own statement code decides whether the
    statement list has an Order column.
    """

    crumb = ("Capture & ledger", "Statements")
    CARD_WIDTH = 100
    BINDINGS = [
        # Two bindings on one key: Textual takes the first whose `check_action`
        # allows it, so the footer reads "Close the panel" only while it would.
        Binding("escape", "close_panel", "Close the panel"),
        ("escape", "back", "Back"),
        ("n", "new", "New"),
        Binding(
            "u", "unfiled", "No statement", tooltip="This account's rows that are in no statement"
        ),
        Binding("d", "delete_row", "Delete"),  # the lines in no statement only
    ]
    #: The `?` card lists these only while `check_action` allows them (help.py).
    CARD_FOLLOWS_CHECK = frozenset({"close_panel", "back", "new", "unfiled", "delete_row"})
    #: `d` deletes the line under the cursor, so it waits for one (`waits_for_a_row`).
    CARD_NEEDS_A_ROW = frozenset({"delete_row"})

    def __init__(self) -> None:
        super().__init__()
        self._statements: list = []  # the open account's statements, engine order
        self._accounts: list[BrowseAccount] = []
        self._acct_idx = 0
        self._open_aid: str | None = None  # the account whose panel is open
        self._mode = "accts"  # "accts" | "statements" | "unfiled"
        self._unfiled: list = []  # every bank line in no statement loaded so far, oldest first
        # the cursor past the last row, the count, and `pgdn` — shared with the ledger
        self._unfiled_grow = GrowingRead(self, on_more=self._append_unfiled)
        self._unfiled_busy = False
        self._by_id: dict = {}
        self._resume_key: object | None = None  # the panel row to land on after a reload
        self._accts_list: CursorList | None = None
        self._statement_list: CursorList | None = None

    def fetch(self) -> dict:
        """The accounts, and the open account's statements
        when a panel is open — which is how a return from a
        statement, or from `n`, comes back to the same panel."""
        from expense import config as config_module

        cfg = config_module.ensure_loaded()
        kw = screen_fetch_kwargs(self.app)
        accts = items_of(reads.fetch_accounts(cfg, **kw))
        accounts = browse_accounts(accts)
        statements = None
        if self._open_aid is not None:
            statements = _read_statements(cfg, self._open_aid, kw)
        return {
            "statements": statements,
            "accounts": accounts,
        }

    def _selected_account(self) -> BrowseAccount | None:
        return self._accounts[self._acct_idx] if self._accounts else None

    def _open_account(self) -> BrowseAccount | None:
        return next((a for a in self._accounts if a.id == self._open_aid), None)

    def _statement_caption(self) -> str:
        """`Statements · Visa BCP · PEN + USD · VIS   ·   oldest → newest`, the
        account's own code last when it has one."""
        acct = self._open_account()
        if acct is None:
            return "Statements · —   ·   oldest → newest"
        parts = ["Statements", acct.name, acct.phrase]
        if acct.code:
            parts.append(acct.code)
        return " · ".join(part for part in parts if part) + "   ·   oldest → newest"

    def _panel_headers(self) -> tuple[list[str], set[int]]:
        acct = self._open_account()
        return statement_headers(acct.codes if acct else (), with_order=bool(acct and acct.code))

    def _panel_layout(self) -> _PanelLayout:
        """How the statements list sits in its room: columns `ORDER_GAP` apart on an account
        with a statement code (`BROWSE_GAP` otherwise), the Name column the one that gives
        way, cut with `…`, when the row is too wide."""
        acct = self._open_account()
        return _PanelLayout(
            gap=ORDER_GAP if acct and acct.code else BROWSE_GAP,
            gives_way={0},
        )

    def _panel_rows(self) -> list:
        acct = self._open_account()
        return statement_rows(
            self._statements,
            acct.codes if acct else (),
            palette=PALETTE,
            with_order=bool(acct and acct.code),
        )

    # ---- adaptive window: the panel splits #content -----------------------
    #: Lines each of the browse's lists spends beside its rows and caption: the account
    #: list its header, the rule under it and the page status; the statements their divider under
    #: the caption (a rule), the header and the page status; the lines in no statement
    #: (`UNFILED_FRAME_LINES`) a blank divider and the header, no status line.
    BROWSE_FRAME_LINES = 3
    #: The lines in no statement grow by cursor and say what is loaded in their caption, so
    #: they draw no page-status line: one line less than the other two.
    UNFILED_FRAME_LINES = BROWSE_FRAME_LINES - 1

    def pane_rows(self) -> int:
        """Rows per account page. Alone, the account list fills #content; with the panel
        open the two split it equally, and the panel gives unused rows back
        (`panel_page_rows`). The chrome is the section title (2) plus the two lists'
        frames and the panel's caption."""
        if self._open_aid is None:
            return self.fit_rows(chrome=2 + self.BROWSE_FRAME_LINES)
        return self._split_rows(self._panel_gap())

    def _split_rows(self, gap: int) -> int:
        """Rows per page when the accounts and the panel split `#content`, with `gap` blank
        lines between them."""
        return self.fit_rows(
            chrome=2 + 2 * self.BROWSE_FRAME_LINES + gap + self.CAPTION_LINES, lines_per_row=2
        )

    def _panel_gap(self) -> int:
        """Blank lines between the accounts' page line and the panel's caption: one when the
        accounts page (the page line says `rows 1-5 of 6 · page 1 of 2`), none when it stands
        blank on one page, as it is itself the blank line. The accounts page when they outnumber
        the rows the panel's equal split gives them with no gap."""
        if self._open_aid is None:
            return 0
        return 1 if len(self._accounts) > self._split_rows(0) else 0

    def _space_panel(self) -> None:
        """Set the blank line `_panel_gap` says stands over the panel."""
        if self._statement_list is not None:
            self._statement_list.styles.margin = (self._panel_gap(), 0, 0, 0)

    def panel_page_rows(self) -> int:
        """Rows per page of the panel: its share, or what the accounts really leave under
        them when that is less (at least one), so a short terminal pages the panel instead
        of scrolling `#content`: `#content` less the title, the accounts' frame and rows,
        and the panel's frame and caption. The lines in no statement take all the room the
        accounts leave; the statements list keeps the equal split."""
        accounts = self.BROWSE_FRAME_LINES + min(self.pane_rows(), max(1, len(self._accounts)))
        frame = self.UNFILED_FRAME_LINES if self._mode == "unfiled" else self.BROWSE_FRAME_LINES
        panel = self._panel_gap() + frame + self._caption_lines()
        room = self.fit_rows(chrome=2 + accounts + panel, floor=1)
        # The lines in no statement take all the room the accounts leave; the statements stop
        # at the equal split.
        return room if self._mode == "unfiled" else min(self.pane_rows(), room)

    def _caption_lines(self) -> int:
        """Lines the caption the panel is about to draw takes at the width the list really
        gets (it wraps): #content's width, capped at the card's `CARD_WIDTH`. Known before
        the list exists."""
        caption = self._unfiled_caption() if self._mode == "unfiled" else self._statement_caption()
        try:
            width = self.query_one("#content").content_size.width
        except NoMatches:
            width = 0
        if width and self.CARD_WIDTH is not None:
            width = min(width, self.CARD_WIDTH)
        return max(1, len(Text(caption).wrap(self.app.console, width or self.size.width)))

    def _viewport_resized(self) -> None:
        if self._accts_list is not None and self._accts_list.is_attached:
            self._accts_list.set_page_size(self.pane_rows())
        if self._statement_list is not None and self._statement_list.is_attached:
            self._space_panel()
            self._statement_list.set_page_size(self.panel_page_rows())

    def _account_rows(self) -> list:
        """The open account carries an accent `▸` in a two-cell gutter before its name, so
        you can see whose panel is showing once the cursor has gone down into it, and
        every name stays where it is (`_ACCOUNT_HEADERS` indents the header the same)."""
        balances = balances_cells(self._accounts, PALETTE)
        return [
            (
                acct.id,
                [
                    Text.assemble(("▸ ", ACCENT), acct.name)
                    if acct.id == self._open_aid
                    else Text(f"  {acct.name}"),
                    acct.phrase,
                    cell,
                ],
            )
            for acct, cell in zip(self._accounts, balances, strict=True)
        ]

    def _new_statement_list(self) -> CursorList:
        headers, align_right = self._panel_headers()
        statement_list = _PanelList(
            headers,
            self._panel_rows(),
            align_right=align_right,
            empty="none yet · n to create one",
            caption=self._statement_caption(),
            page_size=self.panel_page_rows(),
            edge=False,
            header_rule=False,
            **self._panel_layout(),
        )
        statement_list.id = "statements"
        statement_list.styles.margin = (self._panel_gap(), 0, 0, 0)
        return statement_list

    def build(self, data: dict) -> list[Widget]:
        self._accounts = data["accounts"]
        if data["statements"] is None or self._open_account() is None:
            self._open_aid, self._statements = None, []
        else:
            self._statements = data["statements"]
        self._by_id = {r.get("id"): r for r in self._statements}
        self._acct_idx = min(self._acct_idx, max(0, len(self._accounts) - 1))
        self._accts_list = _AccountList(
            _ACCOUNT_HEADERS,
            self._account_rows(),
            empty="(no bank accounts)",
            page_size=self.pane_rows(),
            gap=BROWSE_GAP,
            edge=False,
            header_rule=False,
            header_rule_span=(ACCOUNT_RULE_INDENT, ACCOUNT_RULE_WIDTH),
            gives_way={0},
            min_widths={0: ACCOUNT_NAME_WIDTH},
            divider=None,
        )
        self._accts_list.id = "accts"
        widgets: list[Widget] = [
            Static(Text("Statements — pick an account"), classes="section-title"),
            self._accts_list,
        ]
        self._statement_list = None
        if self._open_aid is not None:
            self._statement_list = self._new_statement_list()
            widgets.append(self._statement_list)
        return widgets

    async def _show(self, data: object, started: int | None = None) -> None:
        await super()._show(data, started)
        if not still_attached(self):
            return
        self._unfiled = []
        self._unfiled_grow.reset()
        if self._accts_list is None or not self._accounts:
            self._mode = "accts"
            self._set_crumb()
            return
        self._accts_list.set_cursor(self._acct_idx)
        if self._statement_list is not None:
            self._mode = "statements"
            if self._resume_key is not None:
                self._statement_list.set_cursor(self._statement_list.index_of(self._resume_key))
                self._resume_key = None
            self._statement_list.focus()
        else:
            self._mode = "accts"
            self._accts_list.focus()
        self._set_crumb()

    def _set_crumb(self) -> None:
        acct = self._open_account()
        trail = self.crumb + ((acct.name,) if acct else ())
        self.query_one("#crumb", Breadcrumb).set_trail(trail)
        self.refresh_bindings()

    # ---- keys ------------------------------------------------------------
    def check_action(self, action: str, parameters: tuple) -> bool | None:
        # False, not None: hidden from the footer as well as dead (Textual 8)
        if action == "close_panel":
            return self._mode == "statements"
        if action == "back":
            return self._mode != "statements"
        # the lines in no statement have `⏎ Edit` and `d Delete` of their own, and neither
        # `n` nor `u`
        if action == "delete_row":
            return self._mode == "unfiled" and not waits_for_a_row(self, action)
        if action == "unfiled":
            return self._open_aid is not None and self._mode != "unfiled"
        if action == "new":
            return self._mode != "unfiled"
        return True

    @property
    def has_rows(self) -> bool:
        """Whether the list on screen holds a row: what `CARD_NEEDS_A_ROW` waits for."""
        shown = self._statement_list if self._mode != "accts" else self._accts_list
        return shown is not None and shown.is_attached and shown.has_rows

    @property
    def active_bindings(self) -> dict[str, ActiveBinding]:
        """The keys in play, the lines in no statement with their footer in the order
        `_UNFILED_FOOTER` gives: a focused list's keys would lead it otherwise."""
        bindings = super().active_bindings
        if self._mode != "unfiled":
            return bindings
        first = [k for k in _UNFILED_FOOTER if k in bindings]
        return {k: bindings[k] for k in (*first, *(k for k in bindings if k not in first))}

    def on_cursor_list_highlighted(self, event: CursorList.Highlighted) -> None:
        if self._mode == "unfiled" and event.control is self._statement_list:
            return
        # Source guard: only the account list moves the account
        # cursor, and only while it is the list in use. Moving it reads nothing.
        if self._mode != "accts" or event.control is not self._accts_list:
            return
        self._acct_idx = event.index

    def on_cursor_list_selected(self, event: CursorList.Selected) -> None:
        if self._mode == "unfiled":
            # `⏎` opens the Edit form on the line, the bank's columns only:
            # date and account are the two remedies for a row in no statement
            line = self._unfiled_record()
            if line is not None and first_part(line) is not None:
                from expense.tui.screens.edit_form import BankLineEditFormScreen

                self.app.push_screen(
                    BankLineEditFormScreen(line=line, opener=self, reload=self._reload_unfiled),
                    lambda saved: saved and self._reload_unfiled(),  # `esc` keeps the cursor
                )
            return
        if event.control is self._accts_list:
            if self._mode == "accts":
                self._acct_idx = event.index
                self._load_statements(event.key)
            return
        # `⏎` on a statement opens the whole statement, every currency it covers
        item = self._by_id.get(event.key)
        if item and self._open_account():
            self._resume_key = event.key
            self.app.push_screen(
                StatementScreen(
                    item,
                    statement_code=self._open_account().code,
                    opener=self,
                    reload=self._load,
                ),
                lambda _result: self._load(),
            )

    @work(thread=True, exclusive=True, group="statements")
    def _load_statements(self, account_id: str) -> None:
        """`⏎` on an account: read its statements. A read that fails
        leaves the panel closed, with a toast."""
        from expense import config as config_module

        worker = get_current_worker()
        try:
            cfg = config_module.ensure_loaded()
            kw = screen_fetch_kwargs(self.app)
            statements = _read_statements(cfg, account_id, kw)
        except Exception as exc:
            if not worker.is_cancelled:
                call_while_attached(
                    self, toast, self, format_error(exc), title="Failed", severity="error"
                )
            return
        if worker.is_cancelled:
            return
        call_while_attached(self, self._open_panel, account_id, statements)

    async def _open_panel(self, account_id: str, statements: list) -> None:
        if self._mode != "accts" or self._accts_list is None:
            return
        self._open_aid = account_id
        self._statements = statements
        self._by_id = {r.get("id"): r for r in statements}
        async with self._content_lock():
            if not still_attached(self):
                return
            self._statement_list = self._new_statement_list()
            await self.query_one("#card").mount(self._statement_list)
        if not still_attached(self):
            return
        self._accts_list.set_rows(self._account_rows())
        self._accts_list.set_page_size(self.pane_rows())
        self._mode = "statements"
        self._statement_list.focus()
        self._set_crumb()

    async def action_close_panel(self) -> None:
        """`esc` in the panel: back to the account list alone."""
        if self._mode != "statements":
            return
        self._open_aid, self._statements, self._by_id = None, [], {}
        if self._statement_list is not None:
            async with self._content_lock():
                await self._statement_list.remove()
            self._statement_list = None
        self._mode = "accts"
        if self._accts_list is not None:
            self._accts_list.set_rows(self._account_rows())
            self._accts_list.set_page_size(self.pane_rows())
            self._accts_list.focus()
        self._set_crumb()

    def action_back(self) -> None:
        if self._mode == "unfiled":
            # the pane swaps back to the statements; the screen stays put
            self._show_statements()
        elif self._mode == "accts":
            self.app.pop_screen()

    def _show_statements(self) -> None:
        """The panel lists the open account's statements again."""
        self._mode = "statements"
        self._unfiled = []
        self._unfiled_grow.reset()
        if self._statement_list is not None:
            self._statement_list.set_growth(more=None)
            headers, align_right = self._panel_headers()
            self._statement_list.set_headers(
                headers,
                align_right=align_right,
                edge=False,
                header_rule=False,
                **self._panel_layout(),
            )
            self._statement_list.set_divider("rule")
            self._statement_list.set_status_line(True)
            self._statement_list.set_caption(self._statement_caption())
            self._statement_list.set_page_size(self.panel_page_rows())
            self._statement_list.set_rows(self._panel_rows())
            self._statement_list.focus()
        self.refresh_bindings()

    def _reload_unfiled(self) -> None:
        """After `⏎` edit or `d`: the oldest `GROW_STEP` again, the cursor on
        row 1 (any write starts the list over, like any app's list). A row whose
        date or account moved is gone, which is the point of editing it."""
        if self._open_aid and self._mode == "unfiled" and self._statement_list is not None:
            self._unfiled_grow.reset()
            self._unfiled_busy = True
            self._load_unfiled(self._open_aid)

    async def action_reload(self) -> None:
        """`r` — in the unfiled pane, start again from the oldest `GROW_STEP`;
        anywhere else, reload the screen (an open panel stays open)."""
        if self._mode == "unfiled":
            if not self._unfiled_busy:
                self._reload_unfiled()
            return
        if self._statement_list is not None:
            self._resume_key = self._statement_list.cursor_key
        await super().action_reload()

    # ---- the unfiled pane ------------------------------------------------
    def action_unfiled(self) -> None:
        """`u` — swap the panel to the open account's rows in no statement.

        Only while a panel is open: the panel is the slot
        it swaps into, and the account whose rows it lists is the open one.
        `esc` swaps it back. Statement work stays in the
        Statements view, so this is a pane, not a filtered ledger.
        """
        acct = self._open_account()
        if acct is None or self._statement_list is None or self._unfiled_busy:
            return
        self._unfiled_busy = True
        self._mode = "unfiled"
        self._statement_list.set_headers(_UNFILED_HEADERS, **_UNFILED_LAYOUT)
        self._statement_list.set_divider("blank")
        self._statement_list.set_status_line(False)
        self._statement_list.set_caption(f"In no statement · {acct.name}   ·   loading…")
        self._statement_list.set_rows([])
        self.refresh_bindings()
        self._load_unfiled(acct.id)

    def _unfiled_page(self, account_id: str):
        """`(limit, after) -> body`: this account's bank lines in no statement, every
        currency together, oldest first (worker thread)."""
        from expense import config as config_module

        def page(limit: int, after: str | None) -> dict:
            return reads.fetch_bank_lines(
                config_module.ensure_loaded(),
                account=account_id,
                after=after,
                limit=limit,
                sort=UNFILED_SORT,
                **UNFILED_FILTER,
                **screen_fetch_kwargs(self.app),
            )

        return page

    @work(thread=True, exclusive=True, group="statements-unfiled")
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
                call_while_attached(self, self._unfiled_failed, format_error(exc))
            return
        if worker.is_cancelled:
            return
        call_while_attached(self, self._show_unfiled, items, total, next_cursor)

    def on_cursor_list_more_requested(self, event: CursorList.MoreRequested) -> None:
        """`pgdn` in the unfiled pane: the next `GROW_STEP` rows, appended."""
        if self._mode != "unfiled" or self._unfiled_busy or not self._open_aid:
            return
        self._unfiled_grow.grow(self._unfiled_page(self._open_aid))

    def _append_unfiled(self, items: list, more: bool) -> None:
        if self._mode != "unfiled" or self._statement_list is None:  # esc landed mid-read
            return
        self._unfiled.extend(items)
        windows = statement_windows(self._statements)
        rows = unfiled_rows(items, windows, palette=PALETTE)
        self._statement_list.set_caption(self._unfiled_caption())
        self._statement_list.set_page_size(self.panel_page_rows())
        self._statement_list.append_rows(rows, more=more)
        self._statement_list.refresh_bindings()

    def _unfiled_failed(self, message: str) -> None:
        self._unfiled_busy = False
        self._show_statements()
        toast(self, message, title="Failed", severity="error")

    def _show_unfiled(self, items: list, total: int, next_cursor: str | None) -> None:
        self._unfiled_busy = False
        if self._mode != "unfiled" or self._statement_list is None:  # esc landed mid-read
            return
        self._unfiled = list(items)
        self._unfiled_grow.took(next_cursor, total)
        # the panel already holds the account's statements: the `!` costs no
        # read of its own
        windows = statement_windows(self._statements)
        rows = unfiled_rows(items, windows, palette=PALETTE)
        self._statement_list.set_caption(self._unfiled_caption())
        self._statement_list.set_page_size(self.panel_page_rows())
        self._statement_list.set_rows(rows)
        self._statement_list.set_growth(more=self._unfiled_grow.more)
        self._statement_list.set_cursor(0)
        self._statement_list.focus()
        self._statement_list.refresh_bindings()

    def _unfiled_caption(self) -> str:
        """`In no statement · Visa BCP · 20 of 1716 loaded · oldest first · …`"""
        acct = self._open_account()
        label = acct.name if acct else "—"
        return (
            f"In no statement · {label}   ·   {len(self._unfiled)} of {self._unfiled_grow.total}"
            " loaded"
            " · oldest first   ·\n! dated inside a statement"
        )

    def _unfiled_record(self) -> dict | None:
        """The bank line under the cursor in the "no statement" list, as listed."""
        key = self._statement_list.cursor_key if self._statement_list is not None else None
        return next((it for it in self._unfiled if it.get("id") == key), None)

    def action_delete_row(self) -> None:
        """`d` — delete the line under the cursor, in the unfiled pane only.

        Cursor row only, never a selection, and the question says a delete is
        final (`ask_line_delete`). Why: docs/decisions.md "Rows in no statement
        live in the Statements view".
        """
        if self._mode != "unfiled":
            return
        line = self._unfiled_record()
        if line is None:
            return
        acct = self._open_account()
        ask_line_delete(self, line, acct.name if acct else "—", after=self._reload_unfiled)

    def action_new(self) -> None:
        """`n` — a statement for the open account, or, with no panel open, for the
        account under the cursor. Saved, it opens that account's panel with the
        cursor on the new one."""
        acct = self._open_account() or self._selected_account()
        if not acct:
            self.notify("No account selected.", severity="error")
            return

        def open_on(new_id: str) -> None:
            self._acct_idx = next(
                (i for i, a in enumerate(self._accounts) if a.id == acct.id), self._acct_idx
            )
            self._open_aid = acct.id
            self._resume_key = new_id
            self._load()

        def saved(new_id: str | None) -> None:
            if new_id is not None:  # None: left without saving, nothing changed
                open_on(new_id)

        self.app.push_screen(
            NewStatementScreen(
                account_id=acct.id,
                account_name=acct.name,
                currencies=acct.codes,
                code=acct.code,
                opener=self,
                created=open_on,
            ),
            saved,
        )


# --------------------------------------------------------------------------- #
# New statement form
# --------------------------------------------------------------------------- #
_STATEMENT_LABELS = {
    "name": "NAME",
    "account": "ACCOUNT",
    "date_start": "DATE START",
    "date_end": "DATE END",
}


def _opening_note() -> str:
    """The begin balance hint's second line, on every begin field: a statement holding
    the account's opening balance begins at zero, as the engine sums every assigned
    transaction, that line included, into the account's add-up check
    (contract: "Statements", "`difference_cents` — the add-up check").
    The hint widget lays out one line per `\n`."""
    return f"{format_cents(0)} if it holds the account's opening balance, which already counts it"


_R_HINTS = {
    "name": "e.g. “April 2026” · enter to go on",
    "account": "pick a bank account · ↑↓ highlight · enter select",
    "date_start": "YYYY-MM-DD · the statement's first day · it orders the statement",
    "date_end": "YYYY-MM-DD · the statement's last day",
}
_DATES = {"date_start", "date_end"}


def balance_key(kind: str, code: str) -> str:
    """The form line of a currency's `begin` or `end` balance: `begin:PEN`."""
    return f"{kind}:{code}"


def unreadable_note(kind: str, code: str) -> str:
    """The note for a `begin` or `end` balance the money parser cannot read, naming
    its currency like the form's line label, then the format: `Begin balance USD: a
    signed decimal, e.g. 9580.00. Amounts are 1,234.56.` The New statement form and
    the statement screen's balance boxes share it."""
    example = format_cents(958000 if kind == "begin" else 946000, grouped=False)
    head = f"{kind.capitalize()} balance {code}: a signed decimal, e.g. {example}."
    return f"{head} {amounts_sentence()}"


def balance_label(kind: str, code: str) -> str:
    """The bar label of that line: `BEGIN BALANCE PEN`."""
    return f"{kind.upper()} BALANCE {code}"


def _balance_line(key: str) -> tuple[str, str] | None:
    """`(kind, code)` of a currency's balance line, `None` for any other line."""
    kind, _, code = key.partition(":")
    return (kind, code) if code else None


def account_line(name: str, codes: tuple[str, ...], code: str | None) -> str:
    """The summary's account line, stated: `Visa BCP · PEN + USD · VIS`, the
    statement code left off on an account with none."""
    return " · ".join(part for part in (name, formatting.currencies_phrase(codes), code) if part)


class NewStatementScreen(FormScreen):
    """A new statement of an account: one `POST /statements` with `account_id`
    and an entry in `balances` for each currency of the account that has a
    balance typed (contract: POST /v1/statements). Opened from the browse on its
    account (`account_id`, its `currencies` and statement `code`), or alone, with
    the account picked on the form and its currencies read off the accounts read.
    Every balance line is optional: which currency the statement needs is the
    engine's call."""

    RESOURCE = "statements"

    def __init__(
        self,
        account_id: str | None = None,
        account_name: str | None = None,
        *,
        currencies: tuple[str, ...] = (),
        code: str | None = None,
        opener: Screen | None = None,
        created: Callable[[str], None] | None = None,
    ) -> None:
        """`opener` is the screen that opened the form and `created` what it does with
        the new statement's id when the save answers after the form has been left and
        `opener` is the screen shown."""
        super().__init__()
        self._opener, self._created = opener, created
        self._values: dict = {}
        self._display: dict = {}
        self._accounts: list = []  # (id, name) of each account the picker offers
        self._browse: dict[str, BrowseAccount] = {}
        self._codes = tuple(currencies)
        self._preset_account = account_id
        self._new_id: str | None = None
        self._sent: list[str] = []  # the currencies of the last body's `balances`, in order
        if account_id:  # created from within an account — don't ask for it again
            name = account_name or account_id[:8]
            self._values["account"] = account_id
            self._display["account"] = account_line(name, self._codes, code)
            self.crumb = ("Statements", name, "New")
        else:
            self.crumb = ("Statements", "New")

    def _sequence(self) -> list[str]:
        seq = ["name"] if self._preset_account else ["name", "account"]
        seq += ["date_start", "date_end"]
        for code in self._codes:
            seq += [balance_key("begin", code), balance_key("end", code)]
        return seq

    def _required(self) -> tuple[str, ...]:
        # Both dates: the engine requires them (contract: POST /v1/statements);
        # asking here refuses an empty one at the field instead of as a 422 on
        # save. No balance line is required: the engine says which currency
        # needs one.
        return ("name", "account", "date_start", "date_end")

    def _label(self, key: str) -> str:
        line = _balance_line(key)
        return balance_label(*line) if line else _STATEMENT_LABELS[key]

    def _summary_label(self, key: str) -> str:
        line = _balance_line(key)
        return f"{line[0]} balance {line[1]}" if line else super()._summary_label(key)

    def _summary_renderable(self):
        """The account's line is stated in the summary even when it is preset and
        so not a line of the bar."""
        seq = self._sequence()
        if self._preset_account:
            seq.insert(1, "account")
        return self._summary_table(seq)

    def _hint_for(self, key: str) -> str:
        line = _balance_line(key)
        if line is None:
            return _R_HINTS.get(key, "")
        kind, code = line
        if kind == "begin":
            return (
                f"signed decimal · the statement's opening balance in {code} · optional"
                f"\n{_opening_note()}"
            )
        hint = "signed decimal · statement's closing balance · optional"
        return f"{hint} · enter saves" if not self._goes_on(key) else hint

    def _suggests(self, key: str) -> bool:
        return key == "account"

    def _bar_value(self, key: str) -> str:
        if _balance_line(key) and key in self._values:
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
            call_while_attached(self, toast, self, format_error(exc), severity="error")
            return
        call_while_attached(self, self._set_accounts, browse_accounts(items_of(body)))

    def _set_accounts(self, rows: list[BrowseAccount]) -> None:
        self._accounts = [(a.id, a.name) for a in rows]
        self._browse = {a.id: a for a in rows}
        self._recompute(self.query_one("#bar", Input).value)
        self._refresh_view()

    # ---- suggestions -----------------------------------------------------
    def _recompute(self, text: str) -> None:
        key = self._key
        needle = text.strip()
        if key == "account":
            self._suggestions = matching(self._accounts, needle)
        else:
            self._suggestions = []
        self._suggest_idx = 0

    # ---- commit ----------------------------------------------------------
    def _pick_account(self, account_id: str, name: str) -> None:
        """The account picked: its currencies give the form its balance lines, and
        the lines of another account's currencies are dropped."""
        acct = self._browse.get(account_id)
        self._codes = acct.codes if acct else ()
        for key in [k for k in self._values if _balance_line(k)]:
            if _balance_line(key)[1] not in self._codes:
                self._values.pop(key)
                self._display.pop(key, None)
        self._values["account"] = account_id
        self._display["account"] = account_line(name, self._codes, acct.code if acct else None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        key = self._key
        text = self.query_one("#bar", Input).value.strip()
        line = _balance_line(key)
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
            self._pick_account(picked[0], picked[1])
            self._advance()
        elif key in _DATES:
            # Both required. The check is the exact day shape the engine takes
            # (contract: "Date inputs"), caught here at the field rather
            # than as a 422 on save; the typed text is what gets sent.
            if not text:
                toast(self, f"{_STATEMENT_LABELS[key].capitalize()} is required.", severity="error")
                return
            if not is_calendar_day(text):
                toast(self, f"{_STATEMENT_LABELS[key].title()}: use YYYY-MM-DD.", severity="error")
                return
            self._values[key] = self._display[key] = text
            self._advance()
        elif line is not None:
            # optional: an empty line leaves the figure out
            if text:
                cents = parse_amount(text, current_format())
                if cents is None:
                    toast(
                        self,
                        unreadable_note(*line),
                        severity="error",
                    )
                    return
                self._values[key] = cents
                self._display[key] = format_cents(cents)
            else:
                self._values.pop(key, None)
                self._display.pop(key, None)
            self._advance()  # on the last line, the save
        self._refresh_view()

    # ---- submit ----------------------------------------------------------
    def _submit_request(self) -> tuple[str, str, dict, str] | None:
        """The save, unless a currency has an ending balance and no starting one: an
        entry of `balances` takes `beginning_balance_cents` always
        (contract: POST /v1/statements, "`balances`"), so it cannot be sent
        well-formed. Whether a currency needs a figure at all stays the engine's call."""
        for code in self._codes:
            if balance_key("end", code) in self._values and balance_key("begin", code) not in (
                self._values
            ):
                self._current = self._sequence().index(balance_key("begin", code))
                self._refresh_bar()
                self._refresh_view()
                toast(
                    self,
                    f"Begin balance {code}: an end balance needs it too.",
                    severity="error",
                )
                return None
        return super()._submit_request()

    def _payload(self) -> dict:
        """The statement: its id, minted here, its account, name and days, and one
        entry in `balances` per currency with a balance typed
        (contract: POST /v1/statements)."""
        self._new_id = str(uuid.uuid4())
        entries = self._balance_entries()
        self._sent = [entry["currency_code"] for entry in entries]
        return {
            "id": self._new_id,
            "account_id": self._values["account"],
            "name": self._values["name"],
            # calendar days, sent as typed — the engine refuses any datetime here
            "date_start": self._values["date_start"],
            "date_end": self._values["date_end"],
            "balances": entries,
        }

    def _balance_entries(self) -> list[dict]:
        """A currency's entry in `balances`: its begin, and its end when one was
        typed (left out, it is not entered yet). A currency with neither typed
        is not sent."""
        entries = []
        for code in self._codes:
            begin = self._values.get(balance_key("begin", code))
            if begin is None:
                continue
            entry = {"currency_code": code, "beginning_balance_cents": begin}
            end = self._values.get(balance_key("end", code))
            if end is not None:
                entry["ending_balance_cents"] = end
            entries.append(entry)
        return entries

    def _refusal_text(self, exc: Exception) -> str:
        """The engine's words whole; a refusal naming one currency's entry
        (`balances.USD`, or `balances.<i>.…` by its place in the body) puts the
        cursor on that currency's begin balance (contract: POST /v1/statements, "Order")."""
        self._refused_line = None
        if isinstance(exc, EngineError):
            for field in [*(exc.reasons or {}), *(exc.fields or {})]:
                code = self._currency_named(field)
                if code is not None and balance_key("begin", code) in self._sequence():
                    self._refused_line = balance_key("begin", code)
                    break
        return format_error(exc)

    def _currency_named(self, field: object) -> str | None:
        """The currency a refusal's `field` names: `balances.USD`, or
        `balances.<i>.<field>` for the i-th entry sent."""
        parts = str(field).split(".")
        if len(parts) < 2 or parts[0] != "balances":
            return None
        if parts[1].isdigit():
            index = int(parts[1])
            return self._sent[index] if index < len(self._sent) else None
        return parts[1]

    def _done(self) -> None:
        """Dismiss with the new id — minted here, in `_payload` — so the browse
        can land its cursor on the statement just made."""
        toast(self, self._saved_words())
        self.dismiss(self._new_id)

    def _saved_words(self) -> str:
        return "Statement created."

    def _left_behind(self) -> str | None:
        return not_done_line("Not created", "Statement", self._values.get("name"))

    def _write_finished_after_leaving(self, app, item, error, *answer) -> None:
        """A statement that was made once the form was gone: the app says how it ended
        (`EngineWriteMixin`), and the screen that opened the form, if it is the one
        shown, opens that account's panel on it."""
        super()._write_finished_after_leaving(app, item, error, *answer)
        if (
            error is None
            and self._created is not None
            and self._new_id is not None
            and app.screen is self._opener
        ):
            self._created(self._new_id)


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


def fetch_month_lines(
    cfg,
    statement_id: str,
    account_id: str,
    date_start: str,
    date_end: str,
    *,
    with_available: bool,
    **kw,
) -> tuple[list[dict], list[dict]]:
    """`(assigned, available)`: the statement screen's two reads.

    The statement's lines on the opened account, any date, in the statement's order
    (contract: GET /v1/bank-lines, "Filters") (contract: GET /v1/bank-lines, "Ordering");
    and, on a draft that offers them, the account's lines in no statement inside the
    period, oldest first, as a statement lists lines with no place."""
    assigned = _fetch_all_lines(
        cfg, statement=statement_id, account=account_id, sort="statement", **kw
    )
    available = []
    if with_available:
        available = _fetch_all_lines(
            cfg,
            account=account_id,
            unreconciled=True,
            date_from=date_start,
            date_to=date_end,
            sort="date_asc",
            **kw,
        )
    return assigned, available


def fetch_review_lines(cfg, statement_id: str, **kw) -> list[dict]:
    """The flagged lines' screen's list: every page of the statement's review list, in the
    statement's order
    (contract: GET /v1/bank-lines, "Read in the statement's order, and only in it")."""
    return _fetch_all_lines(cfg, review_of=statement_id, sort="statement", **kw)


def _status_span(status: str, palette: Palette) -> tuple[str, str]:
    """(text, style) for the header's status word — completed→success, draft→warning."""
    return status, palette.success if status == "completed" else palette.warning


def bank_line_row(line: dict, *rest: object) -> tuple:
    """A bank line as a `CheckList` row: its id, the bank's columns
    (`bank_line_columns`), its currency, then `rest` (the number on the paper and
    whether it is apart). The one copy of the row, for the statement's list and the
    flagged lines'."""
    return (line.get("id"), *formatting.bank_line_columns(line), line.get("currency_code"), *rest)


def line_rows(assigned: list[dict], available: list[dict]) -> tuple[list, list, dict]:
    """`(rows, checked, part_of)` for the statement screen's list.

    One row per bank line, the statement's lines first, then the ones in no
    statement, each read in the engine's order; a line in both reads is listed
    once. A row carries its currency and its number on the paper: 1, 2, 3 … down
    the rows, with no gaps, whatever the places the engine holds. An opening
    balance holds no place on the paper, so its rows are marked `apart`, have no
    number and come after the others, in the order read.
    `part_of` maps a line to the one part a tick is sent on: `statement_id`
    is a line field, so a `PUT` on any part moves every part
    (contract: PUT /v1/transactions/{transaction_id}, "Statement assignment").
    """
    rows, checked, part_of = [], [], {}
    apart = []
    in_statement = {line.get("id") for line in assigned}
    for line in [*assigned, *available]:
        key = line.get("id")
        parts = [p for p in line.get("parts") or [] if isinstance(p, dict) and p.get("id")]
        if key in part_of or not parts:
            continue
        part_of[key] = parts[0]["id"]
        if key in in_statement:
            checked.append(key)
        opening = bool(line.get("is_opening_balance"))
        row = bank_line_row(line, None if opening else len(rows) + 1, opening)
        if opening:
            apart.append(row)
        else:
            rows.append(row)
    return [*rows, *apart], checked, part_of


#: A balance `c` asks for: the currency, then `beginning` or `ending`.
BalanceAsk = tuple[str, str]

_ASKED_FIELD = {"beginning": "beginning_balance_cents", "ending": "ending_balance_cents"}

#: The refusal reasons of a complete that lead to a box for the currency they
#: name, each with the balances it asks for. A currency the statement holds no
#: balances for gains its starting and its ending balance together
#: (contract: PUT /v1/statements/{statement_id}, "`balances`").
_ASKED_BY_REASON = {
    "BEGINNING_BALANCE_REQUIRED": ("beginning",),
    "ENDING_BALANCE_REQUIRED": ("ending",),
    "MONEY_AT_START_NOT_COVERED": ("beginning", "ending"),
}


def blank_balances(statement: dict) -> list[BalanceAsk]:
    """The balances `c` asks for on the statement as read: each covered currency's
    blank starting balance, then its blank ending balance, currency by currency
    in the engine's order (contract: "Statements", "Which currencies a statement covers")."""
    asks: list[BalanceAsk] = []
    for balance in statement.get("balances") or []:
        if not isinstance(balance, dict) or not balance.get("currency_code"):
            continue
        for kind in ("beginning", "ending"):
            if balance.get(_ASKED_FIELD[kind]) is None:
                asks.append((str(balance["currency_code"]), kind))
    return asks


def balances_named(failure: Exception) -> list[BalanceAsk]:
    """The balances a refused complete names, read off the engine's own
    `reasons`, each keyed `balances.<currency_code>[.<field>]`
    (contract: POST /v1/statements/{statement_id}/complete, "Every balance must be entered")
    (contract: POST /v1/statements/{statement_id}/complete,
    "Every currency with money at the start has balances in it"). Which currency needs
    a balance is the engine's call; none named when the refusal is another."""
    reasons = failure.reasons if isinstance(failure, EngineError) else None
    asked: list[BalanceAsk] = []
    for key, reason in (reasons or {}).items():
        parts = str(key).split(".")
        if len(parts) < 2 or parts[0] != "balances":
            continue
        for kind in _ASKED_BY_REASON.get(str(reason), ()):
            if (parts[1], kind) not in asked:
                asked.append((parts[1], kind))
    order = {code: i for i, code in enumerate(dict.fromkeys(code for code, _ in asked))}
    return sorted(asked, key=lambda ask: (order[ask[0]], ask[1] != "beginning"))


def balances_body(typed: dict[BalanceAsk, int]) -> dict:
    """`PUT /statements/{id}`'s body saving the balances typed. Its `balances` names
    only the currencies that change, each with only the balances typed, so the
    engine keeps every other as it is
    (contract: PUT /v1/statements/{statement_id}, "`balances`")."""
    entries: dict[str, dict] = {}
    for (code, kind), cents in typed.items():
        entries.setdefault(code, {"currency_code": code})[_ASKED_FIELD[kind]] = cents
    return {"balances": list(entries.values())}


#: The line under the balances of an open statement on an account with a statement code.
_WAITS_FOR_PDF = "  closes when its PDF is dropped on the LOG bar"

#: A status action's done word → the verb its failure note names: `Couldn't delete`.
_UNDONE = {"completed": "complete", "reverted": "revert", "deleted": "delete"}

#: The first line of a refused complete that follows the balances' save:
#: which half went through, above the engine's words.
_BALANCE_SAVED = "The balances are saved. The statement is not completed:"


#: The balances table of a statement's head: the width of the begin, end and diff
#: columns after the currency code, each at least this wide and as wide as its
#: longest figure needs (two blank cells before it).
_HEAD_WIDTHS = (12, 13, 10)


def balance_lines(balances: object, palette: Palette) -> list[Text]:
    """The head's balances: a `begin  end  diff` line, then one line for each
    currency the statement covers, in the engine's order
    (contract: "Statements", "Which currencies a statement covers"). A currency
    it does not cover has no line. A balance not entered is a dim `—`, never zero,
    and its difference, not checked yet, stays blank
    (contract: "Statements", "A balance not entered is `null`, never zero").
    Empty when the statement covers none."""
    covered = [b for b in balances or [] if isinstance(b, dict)]
    if not covered:
        return []
    columns = [
        [amount_text(b.get("beginning_balance_cents"), palette, BALANCE_RULE) for b in covered],
        [amount_text(b.get("ending_balance_cents"), palette, BALANCE_RULE) for b in covered],
        [list_cell(difference_cell(b.get("difference_cents"), palette)) for b in covered],
    ]
    widths = [
        max(base, *(c.cell_len + 2 for c in col))
        for base, col in zip(_HEAD_WIDTHS, columns, strict=True)
    ]
    head = Text("  " + " " * 3, style="dim")
    for title, width in zip(("begin", "end", "diff"), widths, strict=True):
        head.append(title.rjust(width))
    lines = [head]
    for i, balance in enumerate(covered):
        line = Text("  ")
        line.append(str(balance.get("currency_code") or "—").ljust(3))
        for col, width in zip(columns, widths, strict=True):
            cell = col[i].copy()
            cell.align("right", width)
            line.append_text(cell)
        lines.append(line)
    return lines


class StatementScreen(
    HelpBindingMixin,
    EngineWriteMixin,
    ContentSwapLockMixin,
    AdaptiveRowsMixin,
    NewestReadMixin,
    Screen,
):
    """One statement: header + a bank-line checklist (draft) or read-only list
    (completed). `space` toggles membership; `c`/`u`/`d` complete/revert/delete;
    `r` refetches the statement + checklist (r = refresh everywhere, never a write).

    A complete whose answer flags lines for review opens `FlaggedLinesScreen` on
    them. The `⚑` line under the header says how many the statement's review list
    counts, and `f` opens that screen, both whenever it counts any, open or
    completed, counted each time the screen reads the statement."""

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
    CARD_FOLLOWS_CHECK = frozenset({"flagged", "complete", "revert"})

    def __init__(
        self,
        record: dict,
        *,
        statement_code: str | None = None,
        opener: Screen | None = None,
        reload: Callable[[], None] | None = None,
    ) -> None:
        """`statement_code` is the statement code of the record's account
        (`BrowseAccount.code`), `None` when it has none. `opener` is the screen that
        opened this one and `reload` how it reads again after a write that answers once
        this screen has been left, when `opener` is the screen shown."""
        super().__init__()
        self._opener, self._reload = opener, reload
        self._line_words: dict = {}  # line id → (title, amount) as the list shows it
        self._record = record
        self._statement_code = statement_code
        self._id = record.get("id")
        self._account_id = record.get("account_id")
        self._busy = False
        self._list: CheckList | None = None
        self._part_of: dict = {}  # line id → the part a tick is sent on
        self._land_on: object | None = None  # the line just ticked: the cursor's row after
        self._acct_name: str | None = None  # resolved worker-side in _read_txns
        self._open_when_counted = False  # a complete waits for the review list's count
        self._close_when_loaded = False  # `c` on the leftover lines waits for the list to read
        # how many bank lines the statement's review list counts: the engine's
        # count each time the statement is read, the flagged lines' screen's last
        # count on the way back
        self._flagged = 0
        # last painted rows, cached so a theme change repaints from memory
        # instead of re-fetching

    @property
    def _completed(self) -> bool:
        return self._record.get("status") == 2

    @property
    def _waits_for_pdf(self) -> bool:
        """An open statement on an account with a statement code closes when its PDF
        is dropped on the LOG bar: no ticking, no `c`, no lines from outside it."""
        return not self._completed and bool(self._statement_code)

    @property
    def crumb(self) -> tuple[str, ...]:
        """The trail, which `?` also reads for its title."""
        return ("Statements", self._record.get("name") or "—")

    def compose(self) -> ComposeResult:
        yield Breadcrumb(self.crumb, id="crumb")
        yield Static("", id="rhead")
        yield Static("", id="rnote")  # a refused complete's words; hidden until the next key
        yield Static("", id="rwarn")  # the gap report; hidden until a complete carries one
        yield Static("", id="rflag")  # the flagged lines; hidden until a complete flags one
        yield Container(id="rlist")
        yield FittingFooter()

    def on_mount(self) -> None:
        self.query_one("#rnote", Static).display = False
        self.query_one("#rwarn", Static).display = False
        self.query_one("#rflag", Static).display = False
        # the list is measured again after every layout of this screen, beneath a box
        # too: the head, a note or the `⚑` line coming or going changes its room
        # (a size that did not change sets nothing)
        self.screen_layout_refresh_signal.subscribe(self, lambda _screen: self._refit_list())
        self._render_header()
        # First fetch waits for the first layout pass: _populate sizes the
        # checklist to #rlist's real height (adaptive rows).
        self.call_after_refresh(self._load_txns)

    # ---- adaptive window ---------------------------------------------------
    def _checklist_items(self) -> int:
        """Rows-per-page = what fits #rlist, one line each.

        The chrome is the checklist's own `FRAME_LINES` (the crumb and #rhead
        both name the statement, so it keeps no caption). Never a literal:
        #rlist is `overflow: hidden`, so a miscount clips the page status in
        silence.
        """
        return self.fit_rows("#rlist", chrome=CheckList.FRAME_LINES)

    def on_resize(self, _event) -> None:
        if self._list is not None and self._list.is_attached:
            self._list.set_page_size(self._checklist_items())

    def _apply_fresh_record(self, fresh: dict) -> None:
        """Main-thread: rebind _record from a refreshed statement, then repaint the
        header. Called on the UI thread so the worker never mutates screen
        state directly; a load's hand-back goes through `_if_newest`."""
        self._record = fresh
        self._render_header()
        self.refresh_bindings()

    def _set_acct_name(self, name: str | None) -> None:
        self._acct_name = name

    def _render_header(self) -> None:
        r = self._record
        # short-id placeholder until _read_txns resolves the name worker-side
        acct = self._acct_name or resolve_name(self._account_id, {})
        status = formatting.format_status(r.get("status"))
        first = Text.assemble(
            (r.get("name") or "—", "bold"),
            ("  ·  ", "dim"),
            (acct, ""),
            ("  ·  ", "dim"),
            (_period(r), "dim"),
            ("  ·  ", "dim"),
            ("status ", "dim"),
            _status_span(status, PALETTE),
        )
        # the first line wraps under the statement's name, never at column 1
        lines: list[RenderableType] = [under_itself(Text("  "), first)]
        lines.extend(balance_lines(r.get("balances"), PALETTE))
        if self._waits_for_pdf:
            lines.append(Text(_WAITS_FOR_PDF, style="dim"))
        self.query_one("#rhead", Static).update(Group(*lines))

    def _refit_list(self) -> None:
        """The checklist's page, measured again once the head or the notes above it
        have taken the lines they draw at this width."""
        if self._list is not None and self._list.is_attached:
            self._list.set_page_size(self._checklist_items())

    def _load_txns(self, refresh_record: bool = False) -> None:
        self._read_txns(self._start_read(), refresh_record)

    # own load group (mirrors SectionScreen._load's "section-load"): a refresh
    # cancels stale refreshes only, never a run_write ("engine-write") worker
    @work(thread=True, exclusive=True, group="statement-detail-load")
    def _read_txns(self, generation: int, refresh_record: bool) -> None:
        from expense import config as config_module

        # Exclusive cancellation is cooperative: a superseded load keeps
        # running, so it must stop painting or two _populate swaps interleave
        # and stack duplicate checklists.
        worker = get_current_worker()
        try:
            cfg = config_module.ensure_loaded()
            kw = screen_fetch_kwargs(self.app)
            if refresh_record:
                # read the statement itself too, by its id — a stale header or
                # status would misrepresent balances and the read-only gate. A
                # deleted one is a 404 (contract: GET /v1/statements/{statement_id}).
                try:
                    statement = reads.fetch_statement(cfg, self._id, **kw)
                except EngineError as exc:
                    if exc.status != 404:
                        raise
                    if not worker.is_cancelled:
                        call_while_attached(self, self._record_gone)
                    return
                if worker.is_cancelled:
                    return
                # Marshal onto the main thread — worker mustn't mutate screen state.
                call_while_attached(
                    self, self._if_newest, generation, self._apply_fresh_record, statement
                )
            assigned, available = fetch_month_lines(
                cfg,
                self._id,
                self._account_id,
                self._record["date_start"],
                self._record["date_end"],
                with_available=not self._completed and not self._waits_for_pdf,
                **kw,
            )
            acct_name = resolve_name(self._account_id, load_account_name_map())
        except Exception as exc:  # surface engine/config errors in-app, don't crash
            if not worker.is_cancelled:
                call_while_attached(self, self._if_newest, generation, self._count_failed)
                call_while_attached(
                    self,
                    self._if_newest,
                    generation,
                    toast,
                    self,
                    format_error(exc),
                    severity="error",
                )
            return
        rows, checked, part_of = line_rows(assigned, available)
        if worker.is_cancelled:
            return
        call_while_attached(self, self._if_newest, generation, self._set_acct_name, acct_name)
        call_while_attached(
            self, self._if_newest, generation, self._render_header
        )  # picks up _acct_name
        call_while_attached(self, self._populate, rows, checked, part_of, generation)
        # the review list's count, on a draft or a completed statement alike: the list
        # is on screen whatever it says (contract: GET /v1/bank-lines/count)
        try:
            flagged = reads.count_bank_lines(cfg, review_of=self._id, **kw)
        except Exception as exc:
            if not worker.is_cancelled:
                call_while_attached(self, self._if_newest, generation, self._count_failed)
                call_while_attached(
                    self,
                    self._if_newest,
                    generation,
                    toast,
                    self,
                    format_error(exc),
                    severity="error",
                )
            return
        if not worker.is_cancelled:
            call_while_attached(self, self._if_newest, generation, self._counted, flagged)

    def _counted(self, count: int) -> None:
        """The engine's count of the review list landed: show it, and, when a complete
        is waiting on it, open the flagged lines' screen if it is above zero and this
        screen is the one showing (an `f` pressed meanwhile has opened it already)."""
        self._show_flagged(count)
        waiting, self._open_when_counted = self._open_when_counted, False
        if waiting and count and self.app.screen is self:
            self._open_flagged()

    def _count_failed(self) -> None:
        """A read of the lines or their count failed: a complete waiting on the count
        opens nothing."""
        self._open_when_counted = False
        self._close_when_loaded = False

    async def _populate(self, rows: list, checked: list, part_of: dict, generation: int) -> None:
        """Paint a read. Not while a tick is unanswered: the read may predate
        it, and the read after the last tick paints with the cursor on the line
        ticked last, so ticking down a statement never lands on another row. Not
        a read a newer one has replaced either, checked here on the UI thread."""
        if not self._is_newest(generation) or self._ticks_unanswered():
            return
        land_on, self._land_on = self._land_on, None
        async with self._content_lock():
            if not still_attached(self):
                return
            container = self.query_one("#rlist", Container)
            await container.remove_children()
            if not still_attached(self):
                return
            empty = (
                "(no transactions in this statement)"
                if self._completed or self._waits_for_pdf
                else "(no transactions for this account in range)"
            )
            self._part_of = part_of
            self._line_words = {row[0]: (row[2], row[4]) for row in rows}
            self._list = CheckList(
                rows,
                checked,
                read_only=self._completed or self._waits_for_pdf,
                numbered=self._completed and bool(self._statement_code),
                empty=empty,
                palette=PALETTE,
                page_size=self._checklist_items(),  # adaptive window
                land_on=land_on,
            )
            await container.mount(self._list)
            if not still_attached(self):
                return
            self._list.focus()  # the page keys reach a completed statement's list too
        if self._close_when_loaded:  # the list is read: its ticked rows are the ones counted
            self._close_when_loaded = False
            self.action_complete()

    # ---- assign / unassign ----------------------------------------------
    def on_check_list_toggled(self, event: CheckList.Toggled) -> None:
        """`space`: one `PUT` of `statement_id` on one part of the line,
        which puts every part in the statement or takes every part out
        (contract: PUT /v1/transactions/{transaction_id}, "Line fields"). The
        mixin queue sends one PUT at a time, in order; once the last one is in,
        the screen reads the statement and its lines again, the cursor on the line
        just ticked."""
        part = self._part_of.get(event.key)
        if part is None:
            return
        self._land_on = event.key
        run_assignment(
            self,
            part,
            self._id if event.checked else None,
            not_done="Not ticked" if event.checked else "Not unticked",
            words=self._line_words.get(event.key, (None, None)),
            on_success=self._assigned,
            on_error=self._assign_failed,
        )

    def _write_finished_after_leaving(self, app, item, error, *answer) -> None:
        """A write that answered once this screen was gone: the app says how it ended
        (`EngineWriteMixin`), and the screen that opened this one, if it is the one
        shown, reads again: after the last tick, however it ended, or after a revert or
        a delete that went through."""
        super()._write_finished_after_leaving(app, item, error, *answer)
        if error is None:
            self._say_after_leaving(app, item, (answer or ({},))[0] or {})
        if self._reload is None or app.screen is not self._opener:
            return
        if self._is_tick(item):
            if not self._ticks_unanswered():
                self._reload()
        elif error is None:
            self._reload()

    def _say_after_leaving(self, app, item, body: dict) -> None:
        """The words of a complete or a balances save that went through after this screen
        left, which `LeftBehind` has no way to say: the close's notes and the review
        list's count, or that the statement is still open. No widget of this screen."""
        name = name_or_unnamed(self._record.get("name"))
        if item.path == f"/statements/{self._id}/complete":
            app.run_worker(
                partial(self._count_then_say, app, self._id, name, close_notes(body)),
                thread=True,
                group="engine-read",
                exit_on_error=False,
            )
        elif item.method == "PUT" and item.path == f"/statements/{self._id}":
            app.notify(
                as_markup([("The statement is not completed: open it and press c.", "dim")]),
                title=f"Balances saved · {name}",
                markup=True,
            )

    def _count_then_say(self, app, statement_id, name: str, notes: list[str]) -> None:
        """Thread side: the engine's count of the statement's review list as on screen
        (a failed read leaves the `⚑` line out), then the message on the app, unless it
        is quitting. The screen is gone: it is only the node the hand-back is checked on."""
        from expense import config as config_module

        try:
            count = reads.count_bank_lines(
                config_module.ensure_loaded(), review_of=statement_id, verbose=app._verbose
            )
        except Exception:
            count = 0
        lines = [(f"⚠ {note}", PALETTE.warning) for note in notes]
        if count:
            lines.append((flagged_after_leaving(count), PALETTE.warning))

        def say() -> None:
            if not lines:  # nothing more to say than the screen's own toast
                toast(app, _status_words("completed"))
                return
            app.notify(as_markup(lines), title=f"Statement completed · {name}", markup=True)

        call_while_attached(self, lambda: None, app=app, if_left=say)

    def on_key(self, _event) -> None:
        """The next key takes a refused complete's lines away."""
        self._clear_refusal()

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
        self.notify("This statement no longer exists.", severity="error")
        self.dismiss()

    def action_complete(self) -> None:
        if self._busy:
            return
        # The engine refuses to complete without every balance (contract:
        # POST /v1/statements/{statement_id}/complete, "Every balance must be
        # entered"), so each blank one is asked for first.
        asks = blank_balances(self._record)
        if asks:
            self._ask_balances(asks, {})
            return
        self._confirm_complete()

    def _confirm_complete(self, *, after_save: bool = False) -> None:
        # No ≥1-assigned pre-guard: the engine 422s an empty complete and
        # run_write toasts its message (thin wrapper).
        n = len(self._list.checked) if self._list else 0
        rows = "row" if n == 1 else "rows"
        self._confirm(
            "Complete statement?",
            "Locks the amount, date, title, account, operation number and statement"
            f" of the {n} ticked {rows}.",
            lambda: self._status_action(
                "POST",
                f"/statements/{self._id}/complete",
                2,
                "completed",
                on_response=self._report_gap,
                lead=_BALANCE_SAVED if after_save else "",
                left_behind=LeftBehind(
                    self._not_done("Not completed"),
                    success_from=lambda _body: None,  # said by `_say_after_leaving`
                ),
            ),
            under=self._below_head,
        )

    # ---- the balances, asked for at complete -----------------------------
    def _ask_balances(self, asks: list[BalanceAsk], typed: dict[BalanceAsk, int]) -> None:
        """A box for the first balance in `asks`, then the next, until none is left;
        then one save of everything typed. The figure is read by the shared money
        parser exactly as typed — the sign is the one typed, never added or
        flipped. Unreadable text keeps the box open; `esc` sends nothing."""
        if not asks:
            self._save_balances(typed)
            return
        (currency, kind), rest = asks[0], asks[1:]
        acct = self._acct_name or resolve_name(self._account_id, {})
        where = f"{acct},\nin {currency} · signed · e.g. {format_cents(1385320)}"
        if kind == "beginning":
            title, message, unreadable = (
                "Starting balance first",
                f"The statement's opening figure for {where}",
                unreadable_note("begin", currency),
            )
        else:
            title, message, unreadable = (
                "Ending balance first",
                f"The statement's closing figure for {where}",
                unreadable_note("end", currency),
            )

        def typed_in(cents: int | None) -> None:
            if cents is None or self._busy:
                return  # esc: nothing saved
            self._ask_balances(rest, {**typed, (currency, kind): cents})

        self.app.push_screen(
            AmountPromptModal(
                title,
                message,
                unreadable=unreadable,
                under=self._below_head,
                touched=self._clear_refusal,
            ),
            typed_in,
        )

    def _below_head(self) -> int:
        """The line the list starts on, read from the layout as it stands: `c`'s
        boxes and its question open from there, so the crumb, the head and the notes
        above stay in sight."""
        return self.query_one("#rlist").region.y

    def _save_balances(self, typed: dict[BalanceAsk, int]) -> None:
        self._busy = True
        self.run_write(
            "PUT",
            f"/statements/{self._id}",
            json_body=balances_body(typed),
            on_response=self._balance_saved_record,
            on_success=self._balance_saved,
            on_error=self._balance_failed,
            error_text=list_refusal_text,  # CONCURRENT_CHANGE: `r`, then try again
            left_behind=LeftBehind(
                self._not_done("Not saved"),
                success_from=lambda _body: None,  # said by `_say_after_leaving`
            ),
        )

    def _balance_saved_record(self, body: dict) -> None:
        """The engine's own statement after the save, opened on this account:
        the header shows its end and diff before the complete question asks."""
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
            "Unlocks the assigned transactions and this statement's balances.",
            lambda: self._status_action(
                "POST",
                f"/statements/{self._id}/revert",
                1,
                "reverted to draft",
                left_behind=LeftBehind(self._not_done("Not reverted")),
            ),
        )

    def action_delete(self) -> None:
        # No draft-only pre-guard: the engine refuses to delete a completed
        # statement (`RECONCILIATION_NOT_DRAFT`), and the note shows its words
        # with the line naming `u` (thin wrapper). Sent from this screen, where
        # `r` reads it again, so a refusal's line is the list one.
        self._confirm(
            "Delete statement?",
            "Detaches its transactions and removes the statement. Its transactions stay. "
            "No screen can bring it back.",
            lambda: self._status_action(
                "DELETE",
                f"/statements/{self._id}",
                None,
                "deleted",
                error_text=list_refusal_text,
                left_behind=LeftBehind(self._not_done("Not deleted")),
            ),
        )

    def _not_done(self, not_done: str) -> str:
        """The first line of a refusal of a write on this statement shown after the
        screen has left: `Not reverted · Statement NAME`."""
        return not_done_line(not_done, "Statement", self._record.get("name"))

    def _confirm(
        self, title: str, message: str, action, *, under: Callable[[], int] | None = None
    ) -> None:
        def cb(ok: bool) -> None:
            if ok:
                action()

        self.app.push_screen(ConfirmModal(title, message, under=under), cb)

    def _status_action(
        self, method: str, path: str, new_status, verb: str, *, lead: str = "", **kw
    ) -> None:
        """`lead`, when given, is the failure note's first line, above the
        engine's words."""
        if self._busy:
            return
        self._busy = True
        error_text = kw.get("error_text", format_error)

        def failed(exc: Exception) -> None:
            message = error_text(exc)
            self._action_failed(f"{lead}\n{message}" if lead else message, verb, exc)

        # A status change invalidates a gap report: it was true of the record as it
        # stood one write ago (a revert unseals the very window it named). The
        # flagged lines stay until the read after a change that went through counts
        # them again; a refused change leaves them as they were.
        self._show_warnings([])
        self.run_write(
            method,
            path,
            success=_status_words(verb),
            on_success=lambda: self._action_done(new_status, verb),
            on_failure=failed,
            **kw,
        )

    def _report_gap(self, body: dict) -> None:
        """Surface the `warnings` from `complete` — the uncovered-days report of
        each currency, read off its own entry in `balances` beside its
        `coverage_gap`, one after the other in the engine's order, then each
        `not_covered` currency's, led by its code.

        Shown as a line under the header rather than a toast: the whole value of
        this message is not being missed, and a toast fades in five seconds. It
        stays for as long as the screen does, survives `r`, and clears on the
        next status change.

        The text is the engine's own sentence, verbatim — the dates in it are
        prose, not fields, so this side neither parses them nor goes looking for
        the rows they name. The review surface for that is the "no statement"
        pane (`u`).
        """
        self._show_warnings(close_notes(body))

    def _show_warnings(self, lines: list[str]) -> None:
        line = self.query_one("#rwarn", Static)
        if not lines:
            line.display = False
            line.update("")
            return
        line.update(Group(*(warning_note(text, "  ") for text in lines)))
        line.display = True

    def _show_flagged(self, count: int) -> None:
        """The `⚑` line under the header, and `f` with it, while the close's
        review list holds any line; hidden otherwise."""
        self._flagged = count
        line = self.query_one("#rflag", Static)
        self.refresh_bindings()
        if not self._flagged:
            line.display = False
            line.update("")
            return
        line.update(flagged_note(self._flagged))
        line.display = True

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        # False, not None: hidden from the footer as well as dead
        if action == "flagged":
            return bool(self._flagged)
        if action == "complete":
            return not self._completed and not self._waits_for_pdf
        if action == "revert":  # the statement waiting for its PDF is a draft: nothing to revert
            return not self._waits_for_pdf
        return super().check_action(action, parameters)

    def action_flagged(self) -> None:
        """`f` — the flagged lines' screen again, on the lines still flagged."""
        if self._flagged:
            self._open_flagged()

    def _open_flagged(self) -> None:
        self._open_when_counted = False  # opened now: the count landing opens no second
        self.app.push_screen(
            FlaggedLinesScreen(
                self._id,
                statement=self._record.get("name") or "—",
                statement_code=self._statement_code,
            ),
            self._flagged_back,
        )

    def _open_leftover(self, loose: LooseLines) -> None:
        """A complete refused for lines in no statement on days it seals: their screen
        (leftover_lines.py), which hands back `CLOSE_AGAIN` for `c`."""
        from expense.tui.screens.leftover_lines import StatementLeftoverScreen

        self.app.push_screen(
            StatementLeftoverScreen(
                self._id,
                name=self._record.get("name") or "—",
                account=self._acct_name or resolve_name(self._account_id, {}),
                crumb=self.crumb,
                loose=loose,
            ),
            self._leftover_back,
        )

    def _leftover_back(self, result: str | None) -> None:
        """Back from the leftover lines: the statement is read again (lines may be in it
        now), and after `c` it asks "Complete statement?" once that read has landed."""
        self._close_when_loaded = result == CLOSE_AGAIN
        self._load_txns(refresh_record=True)

    def _flagged_back(self, count: int | None) -> None:
        """Back from the flagged lines: the engine's count of them; None when
        no read landed, which leaves the `⚑` line as it was."""
        if count is not None:
            self._show_flagged(count)

    def _action_failed(self, message: str, verb: str, failure: Exception | None = None) -> None:
        self._busy = False
        done = verb.split()[0]
        title = f"Couldn't {_UNDONE.get(done, done)}"
        if verb != "completed":
            toast(self, message, title=title, severity="error")
        else:
            loose = loose_lines(failure, on="statement_id") if failure is not None else None
            if loose is not None and self.app.screen is self:
                self._load_txns(refresh_record=True)
                self._open_leftover(loose)
                return
            self._show_refusal(title, message)
            # Read the statement fresh: a refusal can say what the screen
            # last read is out of date (an ending balance cleared elsewhere),
            # and the next `c` decides on the header it shows.
            self._load_txns(refresh_record=True)
            # a refusal naming balances leads to a box for each, then the question
            asks = balances_named(failure) if failure is not None else []
            if asks:
                self._ask_balances(asks, {})

    def _show_refusal(self, title: str, message: str) -> None:
        """A refused complete as lines between the head and the list, or the box that
        opens under them: `title`, then the engine's words as sent, each line wrapping
        under its own first word, until the next key."""
        words = [
            # a line the engine's words indent wraps under its own first word
            under_itself(
                Text("  " + line[: len(line) - len(line.lstrip())]),
                Text(line.lstrip(), style="dim"),
            )
            for line in message.split("\n")
        ]
        note = self.query_one("#rnote", Static)
        note.update(Group(Text(f"  {title}", style=f"bold {PALETTE.error}"), *words))
        note.display = True

    def _clear_refusal(self) -> None:
        note = self.query_one("#rnote", Static)
        if note.display:
            note.display = False
            note.update("")

    def _action_done(self, new_status, verb: str) -> None:
        self._busy = False
        toast(self, _status_words(verb))
        if verb == "deleted":
            self.dismiss()
            return
        self._record["status"] = new_status
        self._render_header()
        self.refresh_bindings()
        # the flagged lines' screen opens off the engine's count, whichever read brings it
        self._open_when_counted = verb == "completed"
        self._load_txns()


def flagged_after_leaving(n: int) -> str:
    """The `⚑` line of a complete that flagged `n` lines, said on the app once the
    statement's screen has left."""
    return f"⚑ {line_count(n)} flagged for review: open the statement and press f."


def _status_words(verb: str) -> str:
    """`Statement reverted to draft.`: the words of a status write that went through,
    on the screen and, after it has left, on the app."""
    return f"Statement {verb}."


# --------------------------------------------------------------------------- #
# The lines a complete flagged for review
# --------------------------------------------------------------------------- #
def line_count(n: int) -> str:
    """`1 line`, `3 lines`."""
    return f"{n} line" if n == 1 else f"{n} lines"


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


#: What to do with a flagged line on an account with a statement code, under the list:
#: the engine's two ways, one paragraph each, `(indent beyond the list's, words)`
#: (contract: POST /v1/statements/{statement_id}/complete, "What a client does with a
#: flagged line"). The app does none of the steps here: each is done on the screen it
#: belongs to.
FLAGGED_WAYS = (
    (
        0,
        "On an account with a statement code, when the paper prints the line, the upload made"
        " the paper's row a line of its own, its twin. Keep one:",
    ),
    (2, "the bank's: delete your line. The statement stays completed."),
    (
        2,
        "yours: revert, delete the twin, set your line's day to the row's day, upload the PDF"
        " again.",
    ),
    (
        0,
        "When the paper does not print it: leave it for a later statement, or fix it, or"
        " delete it.",
    ),
)


#: The lines the words under the list take at 80 columns, until they are drawn and
#: can be measured.
FLAGGED_WAYS_LINES = 7


def flagged_rows(lines: list[dict]) -> list[tuple]:
    """One row per flagged line, in the order given, as the statement's own list
    draws a line (`bank_line_row`)."""
    return [bank_line_row(line) for line in lines]


def flagged_head(statement: str, n: int, palette: Palette) -> Text:
    """`<statement> has N flagged lines. N lines dated up to its last day are in no
    statement.`, the engine's count in the warning colour."""
    verb = "is" if n == 1 else "are"
    flagged = "flagged line" if n == 1 else "flagged lines"
    return Text.assemble(
        (f"{statement} has {n} {flagged}. ", ""),
        (f"{line_count(n)} dated up to its last day {verb} in no statement.", palette.warning),
    )


def flagged_ways() -> RenderableType:
    """The engine's two ways to settle a flagged line, as words, dim, each paragraph
    wrapping under its own first word (`FLAGGED_WAYS`)."""
    return Group(
        *(
            under_itself(Text(" " * indent), Text(words, style="dim"))
            if indent
            else Text(words, style="dim")
            for indent, words in FLAGGED_WAYS
        )
    )


class _FlaggedList(CheckList):
    """The flagged lines' list, drawn as the statement's own list (read-only, no
    numbers). It takes no focus: its screen holds every key, so the footer reads in
    the screen's own order (a focused widget's keys come first in a footer)."""

    can_focus = False


class FlaggedLinesScreen(
    EngineWriteMixin, ContentSwapLockMixin, AdaptiveRowsMixin, NewestReadMixin, Screen
):
    """The lines a statement's close flagged for review.

    Opened on the statement's id, the screen reads its review list, the lines
    its close flagged and still unresolved, every currency of the account
    together, page by page in the statement's order, with no id of a line sent
    (contract: POST /v1/statements/{statement_id}/complete, "Response"), and
    how many it holds from the count read on the same filter
    (contract: GET /v1/bank-lines/count). It lists them in the engine's order:
    `Date · Title · Operation · Cur · Amount`. On an account with a statement
    code (`statement_code`) the engine's two ways to settle a flagged line read as
    words under the list (`FLAGGED_WAYS`). A line assigned, moved or deleted drops
    out of the engine's list, so it drops from the screen. `⏎` opens the line
    in the ledger's Edit form, `d` deletes it after the delete question, and
    after either the list is read again. `esc` goes back to the statement,
    handing it the engine's count; with no line left the screen goes back on
    its own. No `?`: the footer is its whole key list."""

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

    def __init__(
        self, statement_id: str, *, statement: str, statement_code: str | None = None
    ) -> None:
        """`statement_code` is the statement code of the statement's account
        (`BrowseAccount.code`), `None` when it has none."""
        super().__init__()
        self._statement_id = statement_id
        self._statement = statement
        self._statement_code = statement_code
        self.crumb = ("Statements", statement, "Flagged")
        self._lines: list[dict] = []
        #: How many lines the review list holds, as the engine last counted
        #: them; None until a read lands.
        self._count: int | None = None
        self._names: dict = {}
        self._list: CheckList | None = None

    def compose(self) -> ComposeResult:
        yield Breadcrumb(self.crumb, id="crumb")
        yield Static("", id="fhead")  # the head, once the engine has counted the lines
        yield Container(id="flist")
        yield FittingFooter()

    def on_mount(self) -> None:
        # the list sizes itself to #flist's real height: wait for the first layout
        self.call_after_refresh(self._load)

    def on_resize(self, _event) -> None:
        if self._list is not None and self._list.is_attached:
            self._list.set_page_size(self._page_rows())

    def _page_rows(self) -> int:
        """Rows that fit under the list's own frame and, on an account with a
        statement code, the words under it."""
        chrome = CheckList.FRAME_LINES
        if self._statement_code:
            try:
                chrome += self.query_one("#fways", Static).outer_size.height or FLAGGED_WAYS_LINES
            except Exception:
                chrome += FLAGGED_WAYS_LINES
        return self.fit_rows("#flist", chrome=chrome)

    def _load(self) -> None:
        """Start a read of the flagged lines; every load start goes through here."""
        self._read_lines(self._start_read())

    @work(thread=True, exclusive=True, group="flagged-load")
    def _read_lines(self, generation: int) -> None:
        """The engine's count of the statement's review list, painted into the head
        the moment it arrives; then the list itself, every page of it in the
        statement's order (`fetch_review_lines`), and the accounts' names
        (contract: GET /v1/bank-lines, "It has no bound"). A failed read shows
        the engine's words and keeps what is listed."""
        from expense import config as config_module

        worker = get_current_worker()
        try:
            cfg = config_module.ensure_loaded()
            kw = screen_fetch_kwargs(self.app)
            count = reads.count_bank_lines(cfg, review_of=self._statement_id, **kw)
            if worker.is_cancelled:
                return
            if count > 0:  # a count of none paints no head: the list is gone, the screen leaves
                call_while_attached(self, self._if_newest, generation, self._paint_head, count)
            lines = fetch_review_lines(cfg, self._statement_id, **kw)
            names = load_account_name_map()
        except Exception as exc:  # surface engine/config errors in-app, don't crash
            if not worker.is_cancelled:
                call_while_attached(
                    self,
                    self._if_newest,
                    generation,
                    toast,
                    self,
                    format_error(exc),
                    severity="error",
                )
            return
        if worker.is_cancelled:
            return
        call_while_attached(self, self._populate, lines, count, names, generation)

    def _paint_head(self, count: int) -> None:
        """Remember the engine's count and paint the head under it."""
        self._count = count
        self.query_one("#fhead", Static).update(flagged_head(self._statement, count, PALETTE))

    async def _populate(self, lines: list[dict], count: int, names: dict, generation: int) -> None:
        """Paint a read, the cursor on row 1, under the engine's count; with no
        line left, back to the statement. A read a newer one replaced paints nothing."""
        if not self._is_newest(generation):
            return
        self._lines, self._names = lines, names
        if not lines:
            self._count = count
            self.dismiss(count)
            return
        self._paint_head(count)
        rows = flagged_rows(lines)
        page_size = self._page_rows()
        async with self._content_lock():
            if not still_attached(self):
                return
            container = self.query_one("#flist", Container)
            await container.remove_children()
            if not still_attached(self):
                return
            self._list = _FlaggedList(rows, read_only=True, palette=PALETTE, page_size=page_size)
            widgets: list[Widget] = [self._list]
            if self._statement_code:
                widgets.append(Static(flagged_ways(), id="fways"))
            await container.mount(*widgets)

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
        line = self._cursor_line()
        if line is not None:
            open_edit_form(self, line, crumb=self.crumb, reload=self._load)

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
        self.dismiss(self._count)
