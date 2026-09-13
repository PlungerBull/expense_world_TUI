"""Home screen — the month itself, then the doors.

Home is a live list, not a menu with a stats line (2026-09-12, mockup
docs/mockups/expense-world-home-as-ledger.html, picks A and C): every category
with what it holds this month in the home currency and a `net` line under
them, every bank account with today's balance in its own currency, every
person with what is owed in theirs (the section folds to `none` when there is
nobody), and then three door rows — LEDGER, MANAGE, SYSTEM — that open in place
to the screens they hold. One `/dashboard` read feeds the whole page, on mount
and again whenever you return home, so a transaction you just wrote is
reflected; while it is in flight, or if it fails, the doors are there and
usable and the failure is a row that says so.

`⏎` on a category, an account or a person pushes the ledger filtered to it —
that is the categorising pass, and why `@Pendiente` needs no door of its own.
`+` logs (`LogTransactionMixin`), `?` opens the keys card, `r` re-reads the
month, `q` quits.

The wordmark line carries the month on the right, where the `net · spent ·
owed` cluster used to be — those numbers are rows now.
"""

import calendar
from typing import NamedTuple

from rich.table import Table
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from expense.commands import dashboard_cmd
from expense.commands._resource import unconverted_of
from expense.errors import format_error
from expense.tui.screens._base import LogTransactionMixin, screen_fetch_kwargs
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.categories import CategoriesScreen
from expense.tui.screens.hashtags import HashtagsScreen
from expense.tui.screens.help import HelpBindingMixin
from expense.tui.screens.overview import OverviewScreen
from expense.tui.screens.reconciliations import ReconciliationsScreen
from expense.tui.screens.system import (
    ActivityScreen,
    AuthScreen,
    ConfigScreen,
    RatesScreen,
)
from expense.tui.screens.transactions import LedgerFilter, TransactionsScreen
from expense.tui.theme import AMOUNT_RULE, PALETTE, Palette
from expense.tui.widgets.cells import aggregate_cell, amount_cell
from expense.tui.widgets.cursor_list import CursorOptionList
from expense.tui.widgets.header import RATE_ALERT_GAP, rate_alert

_BANNER = "◈  EXPENSE WORLD"

#: The door rows, in order: (door id, label, [(screen kind, entry label)…]).
#: A door opens in place — `⏎` toggles it and its entries appear under it.
_DOORS: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "ledger",
        "LEDGER",
        [
            ("transactions", "Transactions"),
            ("reconciliations", "Reconciliations"),
            ("overview", "Overview"),
        ],
    ),
    (
        "manage",
        "MANAGE",
        [("accounts", "Accounts"), ("categories", "Categories"), ("hashtags", "Hashtags")],
    ),
    (
        "system",
        "SYSTEM",
        [
            ("config", "Config"),
            ("auth", "Auth & profile"),
            ("activity", "Activity"),
            ("rates", "Rates"),
        ],
    ),
]

# kind → screen to push. One table instead of a 14-arm elif (backlog §5); the
# `test_screens_map_covers_every_wired_menu_entry` guard keeps it in lockstep
# with the door entries, so a new row can't be left dead.
_SCREENS: dict[str, type[Screen]] = {
    "transactions": TransactionsScreen,
    "reconciliations": ReconciliationsScreen,
    "overview": OverviewScreen,
    "accounts": AccountsScreen,
    "categories": CategoriesScreen,
    "hashtags": HashtagsScreen,
    "config": ConfigScreen,
    "auth": AuthScreen,
    "activity": ActivityScreen,
    "rates": RatesScreen,
}

#: Option-id prefixes for the live rows; the rest of the id is the engine row.
CATEGORY_PREFIX = "category:"
ACCOUNT_PREFIX = "account:"
DOOR_PREFIX = "door:"

_MIN_NAME_WIDTH = 14
_MAX_NAME_WIDTH = 40


class HomeRow(NamedTuple):
    """One line of Home before it becomes an `Option`.

    `id` None = a header or a note (disabled, never the cursor); `right` is
    the amount cell (a Text when it is styled) or a caption; `name` carries
    the filter name so `⏎` can hand it to the ledger's crumb."""

    id: str | None
    left: str
    right: object = ""
    name: str = ""
    dim: bool = False


def month_label(month: dict | None) -> str:
    """`{year: 2026, month: 9}` → `September 2026`; anything else → ``."""
    if isinstance(month, dict):
        year, m = month.get("year"), month.get("month")
        if isinstance(year, int) and isinstance(m, int) and 1 <= m <= 12:
            return f"{calendar.month_name[m]} {year}"
    return ""


def _spent_cell(cents: object, unconverted: int, palette: Palette | None) -> object:
    """A category's month figure: `3 unrated`, a dim `0.00` for nothing spent,
    else the sign-coloured amount."""
    if unconverted == 0 and cents == 0:
        return Text("0.00", style="dim")
    return aggregate_cell(cents, unconverted, palette, AMOUNT_RULE)


def _balance_cell(item: dict, palette: Palette | None) -> Text:
    """An account's balance in its own currency, the code beside it (pick A,
    2026-09-12: the balance you act on is the native one)."""
    cell = amount_cell(item.get("current_balance_cents"), palette, AMOUNT_RULE)
    text = cell if isinstance(cell, Text) else Text(str(cell))
    return Text.assemble(text, " ", (item.get("currency_code") or "?", "dim"))


def home_rows(
    body: dict | None,
    open_doors: set[str],
    palette: Palette | None = None,
    error: str | None = None,
) -> list[HomeRow | None]:
    """The whole page as rows; `None` is a separator. Pure — unit-testable.

    `body` None (pre-fetch, or a failed fetch with `error` set) draws only the
    doors and, when there is an error, one note saying so.
    """
    rows: list[HomeRow | None] = []
    if body is not None:
        rows.append(HomeRow(None, "CATEGORIES", "this month", dim=True))
        totals = body.get("totals") or {}
        for cat in body.get("categories") or []:
            cat_id = cat.get("id")
            if not cat_id:
                continue
            name = cat.get("name") or "(unnamed)"
            cell = _spent_cell(cat.get("spent_home_cents"), unconverted_of(cat), palette)
            rows.append(HomeRow(f"{CATEGORY_PREFIX}{cat_id}", name, cell, name=name))
        rows.append(
            HomeRow(
                None,
                "net",
                aggregate_cell(
                    totals.get("net_home_cents"), unconverted_of(totals), palette, AMOUNT_RULE
                ),
                dim=True,
            )
        )
        rows.append(None)
        rows.append(HomeRow(None, "BANK ACCOUNTS", "balance", dim=True))
        for acct in body.get("bank_accounts") or []:
            if not acct.get("id"):
                continue
            name = acct.get("name") or "(unnamed)"
            rows.append(
                HomeRow(
                    f"{ACCOUNT_PREFIX}{acct['id']}", name, _balance_cell(acct, palette), name=name
                )
            )
        rows.append(None)
        people = [p for p in body.get("people") or [] if p.get("id")]
        rows.append(HomeRow(None, "PEOPLE", "owed" if people else "none", dim=True))
        for person in people:
            name = person.get("name") or "(unnamed)"
            rows.append(
                HomeRow(
                    f"{ACCOUNT_PREFIX}{person['id']}",
                    name,
                    _balance_cell(person, palette),
                    name=name,
                )
            )
        rows.append(None)
    elif error is not None:
        rows.append(HomeRow(None, f"could not load the month — {error}", dim=True))
        rows.append(None)
    for door_id, label, entries in _DOORS:
        if door_id in open_doors:
            rows.append(HomeRow(f"{DOOR_PREFIX}{door_id}", f"{label} ▾"))
            rows.extend(HomeRow(kind, f"  {text}") for kind, text in entries)
        else:
            caption = " · ".join(text for _kind, text in entries)
            rows.append(HomeRow(f"{DOOR_PREFIX}{door_id}", f"{label} ▸", caption, dim=True))
    return rows


def _plain(value: object) -> str:
    return value.plain if isinstance(value, Text) else str(value)


def home_options(rows: list[HomeRow | None]) -> list:
    """Rows → `Option`s for the menu, name column and amount column aligned
    across every row (each option renders alone, so the alignment is padding).
    A door's caption sits beside its label, never right-aligned: it is a list
    of names, not a number."""
    live = [r for r in rows if r is not None]
    # a note (no id, nothing on the right) is a sentence, not a name: it is
    # drawn whole and takes no part in the column width
    columned = [r for r in live if r.id is not None or _plain(r.right)]
    name_w = max((len(r.left) for r in columned), default=_MIN_NAME_WIDTH)
    name_w = max(_MIN_NAME_WIDTH, min(_MAX_NAME_WIDTH, name_w))
    amount_w = max(
        (len(_plain(r.right)) for r in live if r.id is None or not r.id.startswith(DOOR_PREFIX)),
        default=0,
    )
    options: list = []
    for row in rows:
        if row is None:
            options.append(None)
            continue
        style = "dim" if row.dim else ""
        if row.id is None and not _plain(row.right):
            options.append(Option(Text(row.left, style=style), disabled=True))
            continue
        text = Text(row.left[:name_w].ljust(name_w), style=style)
        right = row.right
        if row.id is not None and row.id.startswith(DOOR_PREFIX):
            text.append("   ")
            text.append(_plain(right), style="dim")
        elif _plain(right):
            pad = "  " + " " * max(0, amount_w - len(_plain(right)))
            text.append(pad)
            if isinstance(right, Text):
                text.append_text(right)
            else:
                text.append(str(right), style=style)
        options.append(Option(text, id=row.id, disabled=row.id is None))
    return options


def _build_header(
    month: str | None, palette: Palette | None, rate_stale: bool | None = None
) -> Table:
    """Wordmark (left) + the month (right), one line, full width.

    `expand=True` with a `ratio=1` left column and a right-justified column pins
    the month to the terminal's right edge — the same idiom the section tables
    use. `no_wrap` keeps it on one line; overflow truncates rather than wraps.

    The rate alert trails the month, so it sits in the same place as on the
    section screens (far right of the header) despite the two being built
    differently. It is empty unless the rate is known-stale — see `rate_alert`.
    """
    grid = Table(box=None, expand=True, pad_edge=False, show_header=False)
    grid.add_column(ratio=1, no_wrap=True)
    grid.add_column(justify="right", no_wrap=True)

    right = Text(month or "", style="dim")
    alert = rate_alert(rate_stale, palette)
    if alert.plain:
        if right.plain:
            right.append(RATE_ALERT_GAP)
        right.append_text(alert)

    grid.add_row(Text(_BANNER, style="bold"), right)
    return grid


class HomeScreen(LogTransactionMixin, HelpBindingMixin, Screen):
    # q lives here, not on the App — a stray q mid-flow (modal, list) must
    # never kill the app (backlog 4.6). ctrl+q stays the everywhere-quit.
    BINDINGS = [
        *LogTransactionMixin.BINDINGS,
        ("r", "reload", "Refresh"),
        ("q", "app.quit", "Quit"),
        *HelpBindingMixin.BINDINGS,
    ]

    _body: dict | None = None
    _error: str | None = None

    def __init__(self) -> None:
        super().__init__()
        self._open: set[str] = set()
        self._menu_has_month = False  # the first month to land takes the cursor

    def compose(self) -> ComposeResult:
        yield Static(_build_header(None, None), id="brand")
        yield CursorOptionList(*home_options(home_rows(None, self._open)), id="menu")
        yield Footer()

    def on_mount(self) -> None:
        self._load_dashboard()

    def on_screen_resume(self) -> None:
        # returning home after a write should reflect the new numbers
        self._load_dashboard()

    def action_reload(self) -> None:
        self._load_dashboard()

    @work(thread=True, exclusive=True, group="home-dashboard")
    def _load_dashboard(self) -> None:
        # Failure lands as a row, never a crash: home must stay usable offline /
        # unconfigured / engine-down, with the doors still there.
        from expense import config as config_module

        try:
            cfg = config_module.ensure_loaded()
            body = dashboard_cmd.fetch_dashboard(cfg, **screen_fetch_kwargs(self.app))
        except Exception as exc:
            self.app.call_from_thread(self._set_body, None, format_error(exc))
            return
        self.app.call_from_thread(self._set_body, body, None)

    def _set_body(self, body: dict | None, error: str | None) -> None:
        self._body, self._error = body, error
        self._rerender()

    def _rerender(self) -> None:
        self.repaint_header()
        self._rebuild_menu()

    def _rebuild_menu(self) -> None:
        menu = self.query_one("#menu", CursorOptionList)
        keep = None
        # The cursor stays where it was across a re-read — except the first
        # time the month lands, when it moves from the doors to the first
        # category (mockup pane 1: "the cursor lands on the first category").
        if (
            (self._menu_has_month or self._body is None)
            and menu.highlighted is not None
            and menu.highlighted < menu.option_count
        ):
            keep = menu.get_option_at_index(menu.highlighted).id
        self._menu_has_month = self._body is not None
        menu.clear_options()
        menu.add_options(home_options(home_rows(self._body, self._open, PALETTE, self._error)))
        target = None
        if keep is not None:
            try:
                target = menu.get_option_index(keep)
            except Exception:
                target = None
        if target is None:
            target = next(
                (i for i in range(menu.option_count) if not menu.get_option_at_index(i).disabled),
                None,
            )
        menu.highlighted = target

    def repaint_header(self) -> None:
        """The app's hook for when `rate_stale` lands (see `ExpenseApp`).

        Home builds its own header instead of using `Breadcrumb`, so it cannot
        be repainted by the app's blanket breadcrumb refresh. The two fetches
        race — the dashboard and the rate status — and whichever finishes
        second must not paint away the first, which is why both go through the
        same header build against the current state.
        """
        month = month_label(self._body.get("month")) if self._body else None
        self.query_one("#brand", Static).update(
            _build_header(month, PALETTE, getattr(self.app, "rate_stale", None))
        )

    def _row_name(self, option_id: str) -> str:
        for row in home_rows(self._body, self._open):
            if row is not None and row.id == option_id:
                return row.name
        return ""

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option.id or ""
        if option_id.startswith(DOOR_PREFIX):
            door = option_id[len(DOOR_PREFIX) :]
            self._open ^= {door}
            self._rebuild_menu()
            return
        if option_id.startswith(CATEGORY_PREFIX):
            row_id = option_id[len(CATEGORY_PREFIX) :]
            flt = LedgerFilter("category", row_id, self._row_name(option_id))
            self.app.push_screen(TransactionsScreen(filter=flt))
            return
        if option_id.startswith(ACCOUNT_PREFIX):
            row_id = option_id[len(ACCOUNT_PREFIX) :]
            flt = LedgerFilter("account", row_id, self._row_name(option_id))
            self.app.push_screen(TransactionsScreen(filter=flt))
            return
        screen_cls = _SCREENS.get(option_id)
        if screen_cls is not None:
            self.app.push_screen(screen_cls())
