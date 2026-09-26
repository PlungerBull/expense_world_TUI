"""Home screen — four months of the ledger, today's balances, then the screens.

Home is the month grid (2026-09-13, docs/mockups/expense-world-home-absorbs-
overview.html, option A — which folded the Overview screen into this one and
deleted it). One worker reads `/dashboard` for the balances and
`/reports/monthly` for a four-month window, and the page draws:

- **CATEGORIES** × the four months, home currency, `—` for a month with no
  activity. A category with nothing in the whole window is not drawn at all
  (owner pick; `build_range_grid` already drops it). `→` unfolds a category's
  hashtag rows, `←` folds them. Under the categories: inflow, outflow, net.
- **BANK ACCOUNTS** with today's balance in each account's own currency.
- **PEOPLE** the same way, settled people folded behind `▶ N settled`.
- **LEDGER / MANAGE / SYSTEM** — section headers with their screens always
  listed under them; they never collapse (owner, 2026-09-13).

`pgdn` walks the window one month back, `pgup` one month forward (never past
this month). Balances do not move with it: there is no balances-as-of-date
endpoint, which is why the accounts header says `balance today`.

`⏎` is the ledger, filtered (owner picks, 2026-09-13):

- on a category — that category, every month;
- on a hashtag row — that category and that hashtag;
- on an account or a person — that account.

The data has no row with two hashtags and no untagged row outside `@Pendiente`
(checked 2026-09-13). A combo row that is either is still drawn, so the sums
add up, but `⏎` on it says it cannot be filtered: the engine filters by one
hashtag and has no untagged filter, and a looser filter would show rows the
cell does not count.
"""

import calendar
from datetime import date
from typing import NamedTuple

from rich.table import Table
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from expense.commands import dashboard_cmd, reports_cmd
from expense.commands._resource import (
    load_hashtag_name_map,
    settled_label,
    split_settled,
)
from expense.errors import format_error
from expense.tui.screens._base import LogTransactionMixin, screen_fetch_kwargs
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.categories import CategoriesScreen
from expense.tui.screens.hashtags import HashtagsScreen
from expense.tui.screens.help import HelpBindingMixin
from expense.tui.screens.reconciliations import ReconciliationsScreen
from expense.tui.screens.system import AuthScreen, ConfigScreen
from expense.tui.screens.transactions import LedgerFilter, TransactionsScreen
from expense.tui.theme import ACCENT, AMOUNT_RULE, PALETTE, Palette
from expense.tui.widgets.cells import aggregate_cell, amount_cell
from expense.tui.widgets.cursor_list import CursorOptionList
from expense.tui.widgets.header import RATE_ALERT_GAP, rate_alert

_BANNER = "◈  EXPENSE WORLD"

#: Months side by side. Four is the owner's number (2026-09-13).
WINDOW_MONTHS = 4

#: The screen sections, in order: (section id, header, [(screen kind, label)…]).
#: Always listed in full — they do not fold (owner, 2026-09-13).
_SECTIONS: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "ledger",
        "LEDGER",
        [("transactions", "Transactions"), ("reconciliations", "Reconciliations")],
    ),
    (
        "manage",
        "MANAGE",
        [("accounts", "Accounts"), ("categories", "Categories"), ("hashtags", "Hashtags")],
    ),
    (
        "system",
        "SYSTEM",
        [("config", "Config"), ("auth", "Auth & profile")],
    ),
]

# kind → screen to push. The `test_screens_map_covers_every_section_entry` guard
# keeps it in lockstep with the section entries, so a new row can't be left dead.
_SCREENS: dict[str, type[Screen]] = {
    "transactions": TransactionsScreen,
    "reconciliations": ReconciliationsScreen,
    "accounts": AccountsScreen,
    "categories": CategoriesScreen,
    "hashtags": HashtagsScreen,
    "config": ConfigScreen,
    "auth": AuthScreen,
}

#: Option-id prefixes; the rest of the id is the engine row.
CATEGORY_PREFIX = "category:"
TAG_PREFIX = "tag:"  # tag:<category id>:<hashtag id>, or tag:<category id>:#<n>
ACCOUNT_PREFIX = "account:"
SETTLED_ID = "fold:settled"

_MIN_NAME_WIDTH = 14
_MAX_NAME_WIDTH = 32
_MIN_CELL_WIDTH = 11


class HomeRow(NamedTuple):
    """One line of Home before it becomes an `Option`.

    `id` None = a header, rule or note (disabled, never the cursor). `right` is
    a list of month cells on grid rows, one Text on balance rows, a caption on
    nothing on header and entry rows. `name` is what the ledger's crumb says; `hashtag` is the one
    hashtag a tag row filters by (None when it cannot be filtered)."""

    id: str | None
    left: str
    right: object = ""
    name: str = ""
    dim: bool = False
    hashtag: str | None = None


class HomeState(NamedTuple):
    """What the viewer has unfolded: categories and the settled people."""

    expanded: frozenset = frozenset()
    settled_open: bool = False


#: Nothing unfolded — the page as it first opens.
FOLDED = HomeState()


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """(year, month) shifted by delta months; 1-based months, rolls over years."""
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def month_title(year_month: tuple[int, int]) -> str:
    """(2026, 9) → `September 2026`."""
    year, month = year_month
    return f"{calendar.month_name[month]} {year}"


def short_label(label: str) -> str:
    """The grid's `2026-09` → `Sep 2026`; anything unparseable passes through."""
    try:
        year, month = (int(part) for part in label.split("-"))
        return f"{calendar.month_abbr[month]} {year}"
    except (ValueError, IndexError):
        return label


def _as_text(value: object, style: str = "") -> Text:
    text = value.copy() if isinstance(value, Text) else Text(str(value))
    if style:
        text.stylize(style)
    return text


def _grid_cell(value: object, palette: Palette | None, rule: str = AMOUNT_RULE) -> Text:
    """A month cell: the amount, a dim `—` for no activity, or `3 unrated`."""
    if reports_cmd.cell_is_empty(value):
        return Text(reports_cmd.NO_ACTIVITY_MARK, style="dim")
    assert isinstance(value, dict)
    return _as_text(aggregate_cell(value.get("cents"), value.get("unconverted"), palette, rule))


def _balance_cell(item: dict, palette: Palette | None) -> Text:
    """A balance in its own currency, the code beside it (pick A, 2026-09-12)."""
    cell = _as_text(amount_cell(item.get("current_balance_cents"), palette, AMOUNT_RULE))
    return Text.assemble(cell, " ", (item.get("currency_code") or "?", "dim"))


def tag_label(ids: list[str], names: dict[str, str]) -> str:
    """`#SALIDAS`, `#A + #B`, or `(no hashtags)`."""
    if not ids:
        return "(no hashtags)"
    return " + ".join("#" + names.get(i, i) for i in ids)


def _category_rows(data: dict, state: HomeState, palette: Palette | None) -> list:
    grid = data["grid"]
    names = data.get("names") or {}
    labels: list[str] = grid["labels"]
    newest = len(labels) - 1
    header = [
        Text(
            ("▸ " if i == newest else "") + short_label(lbl),
            style=ACCENT if i == newest else "dim",
        )
        for i, lbl in enumerate(labels)
    ]
    rows: list = [HomeRow(None, "CATEGORIES", header, dim=True)]
    if not grid["rows"]:
        rows.append(HomeRow(None, "  (no activity in this window)", dim=True))
    for row in grid["rows"]:
        cat_id = row["id"]
        name = row["name"] or "(unnamed)"
        combos = row["breakdown"]
        # A category whose only combo is "no hashtags" has nothing to unfold.
        foldable = any(combo["hashtag_ids"] for combo in combos)
        caret = ("▼ " if cat_id in state.expanded else "▶ ") if foldable else "  "
        cells = [_grid_cell(row["cells"].get(lbl), palette) for lbl in labels]
        rows.append(HomeRow(f"{CATEGORY_PREFIX}{cat_id}", caret + name, cells, name=name))
        if not (foldable and cat_id in state.expanded):
            continue
        for n, combo in enumerate(combos):
            ids = combo["hashtag_ids"]
            label = tag_label(ids, names)
            single = ids[0] if len(ids) == 1 else None
            tail = single if single is not None else f"#{n}"
            rows.append(
                HomeRow(
                    f"{TAG_PREFIX}{cat_id}:{tail}",
                    "    " + label,
                    [_grid_cell(combo["cells"].get(lbl), palette) for lbl in labels],
                    name=f"{name} {label}",
                    dim=True,
                    hashtag=single,
                )
            )
    rows.append(HomeRow(None, "", ["─" for _ in labels], dim=True))
    totals = grid["totals"]
    for key in reports_cmd.TOTALS_KEYS:
        signed = key == "net"
        cells = [
            _grid_cell(totals[key].get(lbl), palette, AMOUNT_RULE if signed else "plain")
            for lbl in labels
        ]
        if not signed:
            cells = [_as_text(c, "dim") for c in cells]
        rows.append(HomeRow(None, "  " + key, cells, dim=True))
    return rows


def _balance_row(person_or_account: dict, indent: str, palette, dim: bool = False) -> HomeRow:
    name = person_or_account.get("name") or "(unnamed)"
    return HomeRow(
        f"{ACCOUNT_PREFIX}{person_or_account['id']}",
        indent + name,
        _balance_cell(person_or_account, palette),
        name=name,
        dim=dim,
    )


def home_rows(
    data: dict | None,
    state: HomeState = FOLDED,
    palette: Palette | None = None,
    error: str | None = None,
) -> list[HomeRow | None]:
    """The whole page as rows; `None` is a separator. Pure — unit-testable.

    `data` is `{dashboard, grid, names}`; None (pre-fetch, or a failed fetch
    with `error` set) draws only the screen sections, and the error as one note.
    """
    rows: list[HomeRow | None] = []
    if data is not None:
        rows.extend(_category_rows(data, state, palette))
        rows.append(None)
        dashboard = data.get("dashboard") or {}
        rows.append(HomeRow(None, "BANK ACCOUNTS", Text("balance today", style="dim"), dim=True))
        for acct in dashboard.get("bank_accounts") or []:
            if acct.get("id"):
                rows.append(_balance_row(acct, "  ", palette))
        people = [p for p in dashboard.get("people") or [] if p.get("id")]
        outstanding, settled = split_settled(people)
        caption = Text("none" if not people else "", style="dim")
        rows.append(HomeRow(None, "PEOPLE", caption, dim=True))
        for person in outstanding:
            rows.append(_balance_row(person, "  ", palette))
        if settled:
            caret = "▼ " if state.settled_open else "▶ "
            label = settled_label(len(settled)).removeprefix("▸ ")
            rows.append(HomeRow(SETTLED_ID, "  " + caret + label, dim=True))
            if state.settled_open:
                for person in settled:
                    rows.append(_balance_row(person, "      ", palette, dim=True))
        rows.append(None)
    elif error is not None:
        rows.append(HomeRow(None, f"could not load the month — {error}", dim=True))
        rows.append(None)
    for _section, header, entries in _SECTIONS:
        rows.append(HomeRow(None, header, dim=True))
        rows.extend(HomeRow(kind, f"  {text}") for kind, text in entries)
    return rows


def _plain(value: object) -> str:
    return value.plain if isinstance(value, Text) else str(value)


def _is_whole(row: HomeRow) -> bool:
    """A line with nothing on the right — a note, a section header, a screen
    entry, the settled fold: drawn as written, outside the columns."""
    return not isinstance(row.right, list) and not _plain(row.right)


def home_options(rows: list[HomeRow | None]) -> list:
    """Rows → `Option`s, the name column and the month columns aligned across
    every row (each option renders alone, so the alignment is padding). A
    balance ends where the last month column ends."""
    live = [r for r in rows if r is not None]
    columned = [r for r in live if not _is_whole(r)]
    name_w = max((len(r.left) for r in columned), default=_MIN_NAME_WIDTH)
    name_w = max(_MIN_NAME_WIDTH, min(_MAX_NAME_WIDTH, name_w))
    grid_cells = [c for r in live if isinstance(r.right, list) for c in r.right]
    cell_w = max([_MIN_CELL_WIDTH, *(len(_plain(c)) + 2 for c in grid_cells)])
    months = max((len(r.right) for r in live if isinstance(r.right, list)), default=0)
    balances = [len(_plain(r.right)) for r in columned if not isinstance(r.right, list)]
    body_w = max(cell_w * months, max(balances, default=0) + 2)

    options: list = []
    for row in rows:
        if row is None:
            options.append(None)
            continue
        style = "dim" if row.dim else ""
        if _is_whole(row):
            options.append(Option(Text(row.left, style=style), id=row.id, disabled=row.id is None))
            continue
        text = Text(row.left[:name_w].ljust(name_w), style=style)
        right = row.right
        if isinstance(right, list):
            if all(_plain(c) == "─" for c in right):  # the rule over the totals
                text.append("─" * (cell_w * len(right)), style="dim")
            else:
                for cell in right:
                    text.append(" " * (cell_w - len(_plain(cell))))
                    text.append_text(_as_text(cell, "dim" if row.dim and row.id else ""))
        else:
            text.append(" " * max(2, body_w - len(_plain(right))))
            text.append_text(_as_text(right))
        options.append(Option(text, id=row.id, disabled=row.id is None))
    return options


def _build_header(
    month: str | None, palette: Palette | None, rate_stale: bool | None = None
) -> Table:
    """Wordmark (left) + the window's newest month (right), one line.

    The rate alert trails the month, so it sits in the same place as on the
    section screens (far right of the header). Empty unless the rate is
    known-stale — see `rate_alert`.
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
    #
    # The window and fold keys are `priority=True`: the menu is an OptionList,
    # which binds pgdn/pgup to scroll a page, and a focused widget's binding
    # wins over its screen's. Without priority, pgdn would scroll the list on
    # any terminal short enough to need it — silently, as it once did on the
    # Overview screen these keys came from.
    BINDINGS = [
        *LogTransactionMixin.BINDINGS,
        Binding(
            "pagedown",
            "older",
            "Older",
            key_display="pgdn",
            tooltip="One month further back",
            priority=True,
        ),
        Binding(
            "pageup",
            "newer",
            "Newer",
            key_display="pgup",
            tooltip="One month forward, up to this month",
            priority=True,
        ),
        Binding("right", "expand", "Tags", tooltip="Unfold a category's hashtags", priority=True),
        Binding("left", "collapse", "Fold", tooltip="Fold them again", priority=True),
        ("r", "reload", "Refresh"),
        ("q", "app.quit", "Quit"),
        *HelpBindingMixin.BINDINGS,
    ]

    _data: dict | None = None
    _error: str | None = None

    def __init__(self) -> None:
        super().__init__()
        today = date.today()
        self._today = (today.year, today.month)
        self._end: tuple[int, int] = self._today
        self._state = FOLDED
        self._menu_has_month = False  # the first month to land takes the cursor
        self._rows_by_id: dict[str, HomeRow] = {}

    # ---- widgets ------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Static(_build_header(None, None), id="brand")
        yield CursorOptionList(*home_options(home_rows(None, self._state)), id="menu")
        yield Footer()

    def on_mount(self) -> None:
        self._load_month()

    def on_screen_resume(self) -> None:
        # returning home after a write should reflect the new numbers
        self._load_month()

    def action_reload(self) -> None:
        self._load_month()

    # ---- data ---------------------------------------------------------------
    @work(thread=True, exclusive=True, group="home-month")
    def _load_month(self) -> None:
        # Failure lands as a row, never a crash: Home must stay usable offline /
        # unconfigured / engine-down, with the screen entries still there.
        from expense import config as config_module

        end = self._end
        try:
            cfg = config_module.ensure_loaded()
            kw = screen_fetch_kwargs(self.app)
            dashboard = dashboard_cmd.fetch_dashboard(cfg, **kw)
            body = reports_cmd.fetch_range(
                cfg, from_ym=shift_month(*end, -(WINDOW_MONTHS - 1)), to_ym=end, **kw
            )
            data = {
                "dashboard": dashboard,
                "grid": reports_cmd.build_range_grid(body.get("months") or []),
                "names": load_hashtag_name_map(),
                "end": end,
            }
        except Exception as exc:
            self.app.call_from_thread(self._set_data, None, format_error(exc))
            return
        self.app.call_from_thread(self._set_data, data, None)

    def _set_data(self, data: dict | None, error: str | None) -> None:
        if data is not None and data.get("end", self._end) != self._end:
            return  # a window the viewer has already moved away from
        self._data, self._error = data, error
        self.repaint_header()
        self._rebuild_menu()

    def repaint_header(self) -> None:
        """The app's hook for when `rate_stale` lands (see `ExpenseApp`).

        Home builds its own header instead of using `Breadcrumb`, so the app's
        blanket breadcrumb refresh cannot reach it. The two fetches race, and
        whichever lands second must not paint away the first, which is why
        both go through this one build against the current state.
        """
        month = month_title(self._end) if self._data is not None else None
        self.query_one("#brand", Static).update(
            _build_header(month, PALETTE, getattr(self.app, "rate_stale", None))
        )

    def _rebuild_menu(self, focus_id: str | None = None) -> None:
        menu = self.query_one("#menu", CursorOptionList)
        keep = focus_id
        # The cursor stays where it was across a re-read — except the first
        # time the month lands, when it moves from the screen entries to the first
        # category.
        if keep is None and (self._menu_has_month or self._data is None):
            keep = self._cursor_id()
        self._menu_has_month = self._data is not None
        rows = home_rows(self._data, self._state, PALETTE, self._error)
        self._rows_by_id = {r.id: r for r in rows if r is not None and r.id is not None}
        menu.clear_options()
        menu.add_options(home_options(rows))
        target = None
        if keep is not None and keep in self._rows_by_id:
            target = menu.get_option_index(keep)
        if target is None:
            target = next(
                (i for i in range(menu.option_count) if not menu.get_option_at_index(i).disabled),
                None,
            )
        menu.highlighted = target

    def _cursor_id(self) -> str | None:
        menu = self.query_one("#menu", CursorOptionList)
        if menu.highlighted is None or menu.highlighted >= menu.option_count:
            return None
        return menu.get_option_at_index(menu.highlighted).id

    # ---- keys ---------------------------------------------------------------
    def action_older(self) -> None:
        self._end = shift_month(*self._end, -1)
        self.repaint_header()
        self._load_month()

    def action_newer(self) -> None:
        if self._end >= self._today:
            return  # the window never runs past this month
        self._end = shift_month(*self._end, 1)
        self.repaint_header()
        self._load_month()

    def _foldable(self, option_id: str) -> bool:
        row = self._rows_by_id.get(option_id)
        return row is not None and row.left.lstrip().startswith(("▶", "▼"))

    def action_expand(self) -> None:
        option_id = self._cursor_id() or ""
        state = self._state
        if option_id.startswith(CATEGORY_PREFIX) and self._foldable(option_id):
            cat = option_id[len(CATEGORY_PREFIX) :]
            self._state = state._replace(expanded=state.expanded | {cat})
        elif option_id == SETTLED_ID:
            self._state = state._replace(settled_open=True)
        else:
            return  # a screen entry: the sections do not fold
        self._rebuild_menu(focus_id=option_id)

    def action_collapse(self) -> None:
        option_id = self._cursor_id() or ""
        state = self._state
        focus = option_id
        if option_id.startswith(CATEGORY_PREFIX):
            cat = option_id[len(CATEGORY_PREFIX) :]
            self._state = state._replace(expanded=state.expanded - {cat})
        elif option_id.startswith(TAG_PREFIX):
            cat = option_id[len(TAG_PREFIX) :].split(":", 1)[0]
            self._state = state._replace(expanded=state.expanded - {cat})
            focus = f"{CATEGORY_PREFIX}{cat}"
        elif option_id == SETTLED_ID:
            self._state = state._replace(settled_open=False)
        else:
            return  # a screen entry: the sections do not fold
        self._rebuild_menu(focus_id=focus)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option.id or ""
        row = self._rows_by_id.get(option_id)
        if option_id == SETTLED_ID:
            self._state = self._state._replace(settled_open=not self._state.settled_open)
            self._rebuild_menu(focus_id=option_id)
            return
        flt: LedgerFilter | None = None
        if row is not None and option_id.startswith(CATEGORY_PREFIX):
            flt = LedgerFilter("category", option_id[len(CATEGORY_PREFIX) :], row.name)
        elif row is not None and option_id.startswith(TAG_PREFIX):
            if row.hashtag is None:
                self.notify(
                    "This row is several hashtags or none; the ledger filters by one hashtag.",
                    severity="warning",
                )
                return
            cat = option_id[len(TAG_PREFIX) :].split(":", 1)[0]
            flt = LedgerFilter("category", cat, row.name, hashtag_id=row.hashtag)
        elif row is not None and option_id.startswith(ACCOUNT_PREFIX):
            flt = LedgerFilter("account", option_id[len(ACCOUNT_PREFIX) :], row.name)
        if flt is not None:
            self.app.push_screen(TransactionsScreen(filter=flt))
            return
        screen_cls = _SCREENS.get(option_id)
        if screen_cls is not None:
            self.app.push_screen(screen_cls())
