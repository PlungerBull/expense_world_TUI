"""Transactions screen — the ledger, whole or filtered, with bulk edits.

Built on SectionScreen + the shared CursorList, as **one list that grows**
(`GrowingRead`): it opens with the newest 10, `pgdn` appends the next 10 by
the engine's cursor, and the legend reads `N of M loaded`. Any write starts it
over from the newest 10. `enter` opens the Edit form (`EditFormScreen`) on the
row's bank line, every part of it, and `+` opens the LOG bar
(`LogTransactionMixin`).

**The filtered ledger is the categorising pass**. Home pushes this screen with
a `LedgerFilter` — a category or an account — and it becomes `Ledger › NAME`:
the same list over the engine's own `?category_id=` / `?account_id=`, with the
legend saying what the filter is and how many rows it holds. `space` selects
rows, `a` selects every loaded row, and one key changes the category (`c`), the bank
account (`b`) or the hashtags (`h`) of the selection — or of the cursor row
when nothing is selected. Each opens the bulk pick (`BulkPickScreen` in
bulk_pick.py), a full screen listing the rows it changes over its bar,
at most five and then `+ N more` (`changed_rows`); the write is one
`PUT /transactions/{id}` per row, in order — an account move adds
`reconciliation_id: null` to each row whose account changes, so it leaves its
reconciliation, and a hashtag pick that names a real hashtag drops the pending
one (`hashtags_to_send`) (contract: PUT /v1/transactions/{transaction_id}) — and
then the list reads fresh from the newest 10, so on a filtered list the changed
rows leave at once. The receipt of a move counts the parts the engine's answers
list as moved (`moved_parts`), nothing read to count them, and a move that
changes nothing shows no receipt. A refused row is named by its number;
the others go through. Title, description,
amount and date stay single-row edits behind `⏎`.

`s` opens the same Edit form on the cursor row, on DATE as `⏎` does: its parts
are changed, added and dropped there (edit_form.py). A save reads the list
fresh from the newest 10.

`d` deletes the cursor row after the question and reads the list fresh from
the newest 10. It first reads the row's bank line once
(contract: GET /v1/bank-lines/{bank_line_id}): a part of a split purchase
(`part_count` above 1) asks "Delete this transaction and its N parts?" and goes
whole, every part in one `DELETE /bank-lines/{id}`
(contract: DELETE /v1/bank-lines/{bank_line_id}); a row never split asks and
deletes as any row does. `s` and `d` never act on a selection: while rows are
selected they are off and out of the footer. `d` is off too, and out of the
footer, while the cursor is on a row of an archived account, whose transactions
cannot be deleted (contract: POST /v1/accounts/{account_id}/archive); the row is
drawn as any other, and `s`, `c`, `b`, `h` and `⏎` stay, `s` opening the Edit
form, which reads what is read-only from the line's `edit_limits`. The archived
ids come with the account names, from the one accounts read of each load
(`reads.load_account_index`).

`esc` clears the selection when there is one; otherwise it goes back to where
you came from — Home, for a filter Home opened (esc on a
filtered ledger is back to Home, never to the unfiltered ledger).

`@Pendiente` is a row on Home, and `⏎` on it is the filter.
"""

from collections.abc import Hashable
from typing import NamedTuple

from rich.console import RenderableType
from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static

from expense import reads
from expense.errors import (
    EngineError,
    format_error,
    is_keyed_refusal,
    refusal_kind,
    refuses_every_write,
    row_note,
)
from expense.formatting import (
    bank_line_part_count,
    format_hashtag_cell,
    format_short_date,
    grouped_refusals,
    resolve_name,
)
from expense.reads import (
    ENGINE_PAGE_CAP,
    hashtags_to_send,
    load_account_index,
    load_category_name_map,
    load_hashtag_name_map,
    load_quickadd_refs,
)
from expense.tui.screens._base import (
    DELETE_KEY,
    LogTransactionMixin,
    SectionScreen,
    bank_line_delete_message,
    bank_line_delete_question,
    call_while_attached,
    list_refusal_text,
    screen_fetch_kwargs,
    transaction_delete_message,
)
from expense.tui.screens._growing import GrowingRead, read_first
from expense.tui.screens.bulk_pick import BulkPickScreen
from expense.tui.screens.edit_form import EditFormScreen, moved_parts, unassign_on_move
from expense.tui.theme import ACCENT, AMOUNT_RULE, PALETTE, Palette
from expense.tui.widgets.cells import amount_cell
from expense.tui.widgets.cursor_list import CursorList, list_table
from expense.tui.widgets.refusal import as_markup, toast

_HEADERS = ["Title", "Description", "Amount", "Date", "Account", "Cat", "Hashtags"]
#: The free-text columns and their share of the width left after Amount, Date,
#: Account and Cat take their natural size. The cells are handed to
#: the table whole and cut by it at the column edge, never pre-truncated.
_FLEX = {0: 3, 1: 3, 6: 2}
#: Amount, the one right-aligned column.
_ALIGN_RIGHT = {2}

#: How many rows the bulk pick lists over its bar; the rest read `+ N more`.
PICK_ROWS_SHOWN = 5

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
    on Home; the name then reads `WANTS #SALIDAS`."""

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


def changed_rows(rows: list, *, shown: int = PICK_ROWS_SHOWN) -> RenderableType:
    """The rows a bulk key changes, as the bulk pick lists them over its bar:
    the ledger's own columns, header and title gutter (`list_table`,
    `mark_selected` with nothing marked), the first `shown` of them, then a dim
    `+ N more` under their titles for the rest. Pure."""
    listed = mark_selected(rows[:shown], set())
    rest = len(rows) - shown
    if rest > 0:
        more = [f"{_GUTTER}+ {rest} more", *[""] * (len(_HEADERS) - 1)]
        listed.append((None, more, "dim"))
    return list_table(_HEADERS, listed, align_right=_ALIGN_RIGHT, flex=_FLEX, edge=False)


def legend_text(filter: LedgerFilter | None, loaded: int, total: int | None, selected: int) -> str:
    """`filter: category @Pendiente · 20 of 57 loaded · 3 selected` — the
    filter, how many of the engine's count are loaded, and the selection when
    there is one, on one line."""
    head = f"filter: {filter.kind} {filter.name}" if filter else "no filter"
    parts = [head]
    if isinstance(total, int):
        parts.append(f"{loaded} of {total} loaded")
    if selected:
        parts.append(f"{selected} selected")
    return " · ".join(parts)


#: A refused row of the bulk edit: its key, its place on the list (0 for none),
#: its kind and its words, as `refused_row` gives them.
RefusedRow = tuple[object, int, Hashable | None, str]


def refused_row(exc: Exception) -> tuple[Hashable | None, str]:
    """The kind and the words of one row's refused write, as
    `formatting.grouped_refusals` takes them.

    A refusal naming what it refused by key (`errors.is_keyed_refusal`) reads
    in the engine's words for the row, the app's lines under them
    (`errors.row_note`), and rows refused alike share a kind
    (`errors.refusal_kind`). A refusal every further write would draw too
    (`errors.refuses_every_write`) is about the account, not the row: it reads
    whole (`format_error`) on a line of its own naming no row, as the LOG bar
    says one. Anything else (a `401`, a `5xx`, a refusal naming no key, a lost
    connection) reads whole in the shared text, code and message first, as the
    LOG bar says a refusal naming no row, and rows that met the same words
    share a line."""
    if refuses_every_write(exc):
        return None, format_error(exc)
    if isinstance(exc, EngineError) and is_keyed_refusal(exc):
        return refusal_kind(exc), row_note(exc)
    words = format_error(exc)
    return ("text", words), words


def refusal_notes(failed: list[RefusedRow]) -> list[str]:
    """One note per kind of refusal, not one per row, in the style the LOG bar
    and the sheet import share (`formatting.grouped_refusals`): what was
    refused in the error colour, the rows it hit under it (`row 2`, or
    `rows 1, 3`), then the app's lines, dim. Content markup, with the words
    escaped (`as_markup`), so a bracket in the engine's words shows as the
    engine sent it."""
    refusals = [(kind, words, [n] if n else []) for _key, n, kind, words in failed]
    notes = []
    for first, rows, rest in grouped_refusals(refusals):
        lines = [f"[$error]{as_markup(first)}[/]"]
        if rows:
            lines.append(rows)
        lines.extend(f"[dim]{as_markup(line)}[/]" for line in rest)
        notes.append("\n".join(lines))
    return notes


def bulk_receipt(count: int, label: str, left: int = 0) -> str:
    """The toast after a bulk write: `3 rows → KORAKUEN`, and with `left`
    rows taken out of their reconciliation by an account move,
    `3 rows → BCP USD · 2 left their reconciliation`."""
    receipt = f"{count} {'row' if count == 1 else 'rows'} → {label}"
    if left == 1:
        receipt += " · 1 left its reconciliation"
    elif left > 1:
        receipt += f" · {left} left their reconciliation"
    return receipt


def bulk_writes(targets: list, payload: dict, by_id: dict) -> list[tuple[object, dict]]:
    """(id, PUT body) per target row.

    Each row gets its own copy of `payload`; an account move adds
    `reconciliation_id: None` only to the rows whose account changes
    (`unassign_on_move`), so a row already on the picked account keeps its
    reconciliation."""
    writes = []
    for key in targets:
        body = dict(payload)
        unassign_on_move(body, by_id.get(key) or {})
        writes.append((key, body))
    return writes


class TransactionsScreen(LogTransactionMixin, SectionScreen):
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
        Binding("s", "split", "Edit", tooltip="Edit the transaction and its parts"),
        DELETE_KEY,
    ]
    crumb = ("Capture & ledger", "Transactions")
    # None = the card fills the terminal width, and PAGE_ROWS_CAP lets the list
    # window fill its height: the ledger is the screen you sit in, so it takes
    # the window you gave it instead of holding a 110x20 card in the corner of
    # a large one. The list grows, so the cap sizes
    # only the window, never a read: a resize reads nothing.
    CARD_WIDTH = None
    PAGE_ROWS_CAP = ENGINE_PAGE_CAP

    def __init__(self, filter: LedgerFilter | None = None) -> None:
        super().__init__()
        self._by_id: dict = {}
        self._filter = filter
        self._selected: set = set()
        self._rows: list = []  # every loaded row, unmarked, in list order
        self._maps: tuple[dict, dict, dict] = ({}, {}, {})
        self._archived: frozenset = frozenset()  # ids of the archived accounts
        self._grow = GrowingRead(self, on_more=self._append_loaded)
        self._refs = None  # QuickAddRefs, loaded on the first bulk key
        self._pending_pick: str | None = None
        self._bulk_busy = False
        self._delete_reading = False  # `d` is reading the cursor row's bank line
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

    def _read_page(self, limit: int, after: str | None) -> dict:
        """One cursor page over this ledger's filter (worker thread)."""
        from expense import config as config_module

        cfg = config_module.ensure_loaded()
        return reads.fetch_transactions(
            cfg, **self._scope(), after=after, limit=limit, **screen_fetch_kwargs(self.app)
        )

    def _count(self) -> int:
        from expense import config as config_module

        cfg = config_module.ensure_loaded()
        return reads.count_transactions(cfg, **self._scope(), **screen_fetch_kwargs(self.app))

    def fetch(self) -> dict:
        items, next_cursor, total = read_first(self._read_page, self._count)
        accounts = load_account_index()
        return {
            "items": items,
            "next_cursor": next_cursor,
            "total": total,
            "accounts": accounts.names,
            "archived": accounts.archived,
            "categories": load_category_name_map(),
            "hashtags": load_hashtag_name_map(),
        }

    def build(self, data: dict) -> list[Widget]:
        items = data["items"]
        self._grow.took(data["next_cursor"], data["total"])
        self._by_id = {it.get("id"): it for it in items}
        self._maps = (data["accounts"], data["categories"], data["hashtags"])
        self._archived = data["archived"]
        self._rows = transaction_rows(items, *self._maps, palette=PALETTE)
        # a reload drops selections that left the list
        self._selected &= set(self._by_id)
        flt = self._filter
        # No panel title: the crumb reads `Ledger ▸ @Pendiente` and the legend
        # below says `filter: category @Pendiente · 57 rows`, so a third naming
        # of the filter would be chrome. Only the empty-state text is computed
        # from the filter.
        if flt is not None:
            empty = f"(no transactions under {flt.name})"
        else:
            empty = "(no transactions)"
        self.call_after_refresh(self.refresh_bindings)
        listing = CursorList(
            _HEADERS,
            mark_selected(self._rows, self._selected),
            align_right=_ALIGN_RIGHT,
            flex=_FLEX,
            empty=empty,
            page_size=self.measure_list_rows(),
        )
        listing.set_growth(more=self._grow.more)
        return [listing, Static(Text(self._legend()), classes="legend", id="legend")]

    def _legend(self) -> str:
        return legend_text(self._filter, len(self._rows), self._grow.total, len(self._selected))

    # ---- growing ------------------------------------------------------------
    def on_cursor_list_more_requested(self, event: CursorList.MoreRequested) -> None:
        """`pgdn`: the next 10, appended under the rows in hand."""
        event.stop()
        self._grow.grow(self._read_page)

    def _reload_fresh(self) -> None:
        """After any write: the newest 10 again, the cursor on row 1.
        The old list stays up until the new one lands."""
        self._grow.reset()
        self._load()

    async def action_reload(self) -> None:
        self._grow.reset()
        await super().action_reload()

    def _viewport_resized(self) -> None:
        """The window re-slices the rows in hand; nothing is read."""
        try:
            listing = self.query_one(CursorList)
        except Exception:
            return  # loading / error state
        listing.set_page_size(self.measure_list_rows())

    def _append_loaded(self, items: list, more: bool) -> None:
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
        if action in ("delete", "split") and (self._selected or not self._rows or self._bulk_busy):
            # the cursor row only, never a selection: while rows are selected
            # `s` and `d` are off and leave the footer, and `esc` brings them
            # back. Off too while a bulk write runs, so neither overlaps its PUTs
            return False
        if action == "delete" and self._on_archived_row():
            # the engine deletes none of an archived account's transactions
            # (contract: POST /v1/accounts/{account_id}/archive); `s` stays, since
            # the Edit form it opens reads what is read-only from `edit_limits`
            return False
        return True

    def _on_archived_row(self) -> bool:
        """True while the cursor is on a row whose account is archived."""
        targets = [] if self._selected else self._targets()
        record = self._by_id.get(targets[0]) if targets else None
        return record is not None and record.get("account_id") in self._archived

    def on_cursor_list_highlighted(self, event: CursorList.Highlighted) -> None:
        self.refresh_bindings()  # re-check `d` for the row the cursor landed on

    def action_split(self) -> None:
        """`s` — the Edit form on the row under the cursor, as `⏎` opens it, an
        archived account's row included; a save reads the list fresh. Never a
        selection, nor while a bulk write runs (`check_action`)."""
        if self._selected or self._bulk_busy:
            return
        targets = self._targets()
        if not targets:
            return
        record = self._by_id[targets[0]]
        self.app.push_screen(EditFormScreen(record=record), self._after_detail)

    def action_delete(self) -> None:
        """`d` — delete the row under the cursor, after the question. Never a
        selection (`check_action` switches the key off while there is one),
        nor an archived account's row."""
        if self._selected or self._bulk_busy or self._on_archived_row():
            return
        targets = self._targets()
        if not targets:
            return
        record = self._by_id[targets[0]]
        if self._delete_reading:
            return  # one read at a time: the question is on its way
        self._delete_reading = True
        self._read_line_then_ask(record)

    @work(thread=True, exclusive=True, group="ledger-delete")
    def _read_line_then_ask(self, record: dict) -> None:
        """One `GET /bank-lines/{id}` for the row's bank line, which every
        transaction names (contract: "Transactions (Ledger)", "Bank lines"): its
        part count tells a split purchase from a row never split, and its parts
        and total word the question (contract: GET /v1/bank-lines/{bank_line_id}).
        The answer comes back only to a ledger still on the app."""
        from expense import config as config_module

        try:
            cfg = config_module.ensure_loaded()
            line = reads.fetch_bank_line(
                cfg, str(record.get("bank_line_id")), **screen_fetch_kwargs(self.app)
            )
        except Exception as exc:
            call_while_attached(self, self._delete_read_failed, list_refusal_text(exc))
            return
        call_while_attached(self, self._ask_delete, record, line)

    def _delete_read_failed(self, message: str) -> None:
        """The purchase could not be read: no question, nothing sent, the
        engine's words in the "Failed" note, and `d` again tries again."""
        self._delete_reading = False
        toast(self, message, title="Failed", severity="error")

    def _ask_delete(self, record: dict, line: dict) -> None:
        """The question, then the delete: a split purchase (`part_count` above
        1) goes whole, in one `DELETE /bank-lines/{id}`
        (contract: DELETE /v1/bank-lines/{bank_line_id}); a row never split goes
        alone, in `DELETE /transactions/{id}`. Nothing is asked once another
        screen is on top of the ledger: the key was pressed on a ledger no
        longer in front."""
        self._delete_reading = False
        if self.app.screen is not self:
            return
        if bank_line_part_count(line) > 1:
            account_id = line.get("account_id") or record.get("account_id")
            self.confirm_delete(
                "bank-lines",
                record.get("bank_line_id"),
                bank_line_delete_question(line),
                bank_line_delete_message(line, resolve_name(account_id, self._maps[0])),
                done="Transaction deleted.",
                after=self._reload_fresh,
            )
            return
        account = resolve_name(record.get("account_id"), self._maps[0])
        self.confirm_delete(
            "transactions",
            record.get("id"),
            "Delete this transaction?",
            transaction_delete_message(record, account),
            done="Transaction deleted.",
            after=self._reload_fresh,
        )

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

        From Home, `⏏` on a category then `esc` is Home again, not the whole
        ledger — the filter is the door you came in by, not a state to step out of."""
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
        toast(self, message, title="Could not load the pickers", severity="error")

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
            return list(refs.pickable_categories)
        if kind == "account":
            return [(i, n) for i, n, *_ in refs.accounts]
        return list(refs.hashtags)

    def _open_picker(self, kind: str) -> None:
        targets = self._targets()
        options = self._picker_options(kind)
        if not options:
            toast(self, f"There is nothing to pick — no {kind} exists yet.", severity="warning")
            return
        chosen = set(targets)
        rows = changed_rows([row for row in self._rows if row[0] in chosen])
        pick = BulkPickScreen(kind, len(targets), options, rows=rows, crumb=self.crumb)
        self.app.push_screen(pick, lambda picked: self._apply_pick(kind, targets, picked))

    def _apply_pick(self, kind: str, targets: list, picked: object) -> None:
        if picked is None or self._bulk_busy:
            return
        names = dict(self._picker_options(kind))
        if kind == "hashtags":
            ids = list(picked) if isinstance(picked, list) else [picked]
            ids = hashtags_to_send(ids, self._refs.pending_hashtag_id if self._refs else None)
            label = " ".join("#" + names.get(i, i) for i in ids) or "(no tags)"
            payload = {"hashtag_ids": ids}
        else:
            label = names.get(picked, str(picked))
            payload = {BULK_FIELDS[kind]: picked}
        self._bulk_busy = True
        self.refresh_bindings()
        self._bulk_write(bulk_writes(targets, payload, self._by_id), label, kind == "account")

    # ---- the bulk write -------------------------------------------------------
    @work(thread=True, group="engine-write")
    def _bulk_write(self, writes: list[tuple[object, dict]], label: str, move: bool) -> None:
        """One PUT per row, in order, on one client; a refused row is kept by
        number and the rest go through — unlike `run_write`'s queue, which
        drops the remainder on the first error, because here every row's
        intent is independent of its neighbours'. An account-wide refusal
        (`errors.refuses_every_write`) is the exception: every later row would
        draw it too, so the run stops there and the rows after it are never sent.

        The receipt counts what landed. A move (`move`) counts the parts the
        engine says it moved, and those that left their reconciliation, across
        the answers that came back (`moved_parts`); a category or hashtag pick
        reaches only the part it names
        (contract: PUT /v1/transactions/{transaction_id}, "Line fields"), so it
        counts the writes that landed."""
        from expense import config as config_module
        from expense.http import ExpenseClient

        numbers = {key: n for n, (key, *_) in enumerate(self._rows, start=1)}
        answers: list[dict] = []
        failed: list[RefusedRow] = []
        unsent: list[object] = []
        try:
            cfg = config_module.ensure_loaded()
            with ExpenseClient(cfg, verbose=self.app._verbose) as client:
                for sent, (key, body) in enumerate(writes, start=1):
                    try:
                        answers.append(client.put(f"/transactions/{key}", json_body=body))
                    except Exception as exc:
                        failed.append((key, numbers.get(key, 0), *refused_row(exc)))
                        if refuses_every_write(exc):
                            unsent = [later for later, _body in writes[sent:]]
                            break
        except Exception as exc:
            failed.append((None, 0, None, format_error(exc)))
        count, left = moved_parts(answers) if move else (len(answers), 0)
        self.app.call_from_thread(
            self._bulk_finished, len(answers), failed, label, left, unsent, count
        )

    def _bulk_finished(
        self,
        done: int,
        failed: list[RefusedRow],
        label: str,
        left: int = 0,
        unsent: tuple | list = (),
        count: int | None = None,
    ) -> None:
        """`done` writes landed; the receipt says `count` rows (`done` when
        not given) and `left` of them left their reconciliation. A move that
        changed nothing (`count` 0) shows no receipt; its refusals still show."""
        self._bulk_busy = False
        rows = done if count is None else count
        if rows:
            toast(self, bulk_receipt(rows, label, left))
        # One toast per kind of refusal, not per row — see `refusal_notes`. Its
        # colours are content markup, the engine's words escaped inside it.
        head = f"{len(failed)} of {done + len(failed)} refused" if len(failed) > 1 else "Refused"
        for note in refusal_notes(failed):
            self.notify(note, title=head, severity="error", timeout=10, markup=True)
        # the rows that went through no longer belong to a filtered list — they
        # leave at once. A refused row stays selected if the
        # fresh read brings it back, so once its lock is lifted the same key
        # retries exactly it; one past the newest 10 is dropped by `build`.
        # So does a row never sent because an account-wide refusal stopped the
        # run: the retry covers the refused row and every row after it.
        self._selected = {key for key, *_ in failed if key is not None} | set(unsent)
        self._reload_fresh()

    # ---- single-row doors ----------------------------------------------------
    def _after_log(self, _result=None) -> None:
        self._reload_fresh()  # a transaction written with `+` belongs in this list now

    def on_cursor_list_selected(self, event: CursorList.Selected) -> None:
        item = self._by_id.get(event.key)
        if item:
            self.app.push_screen(
                EditFormScreen(record=item),
                self._after_detail,
            )

    def _after_detail(self, saved: bool | None) -> None:
        """A save reloads fresh, like every write; `esc` leaves the list as it
        was — same rows loaded, cursor on the row it was on.
        The list underneath was never rebuilt, so doing nothing keeps it."""
        if saved:
            self._reload_fresh()


def _crumb_for(flt: LedgerFilter | None) -> tuple[str, ...]:
    return ("Ledger", flt.name) if flt is not None else ("Capture & ledger", "Transactions")
