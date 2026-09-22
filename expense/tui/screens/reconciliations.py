"""Reconciliations — list, new batch, and the working/detail screen (Phase 2).

Per-account bank-statement batches. The browse is account-first (two panes):
the account selector on top, the selected account's batches below in the
engine's order (`date_start ASC NULLS LAST, created_at ASC` when account-scoped
— a batch is a statement period, so its date is its position). `↑↓` in account
focus swaps the account (the batch list follows); `enter` drops into batch
focus, where `enter` opens the working screen and `esc` returns to the accounts.
`n` creates a batch for the selected account.

New batch: name › account › date start › date end › begin › end. Both balances
are typed off the paper statement — the engine deleted derived (chained) begins
on 2026-08-06, so there is nothing to inherit and `beginning_balance_cents` is
required. `date_start` is required too: it is what orders the batch.
POST /reconciliations.

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
    account_choices,
    fetch_all_pages,
    format_cents,
    items_of,
    load_account_name_map,
    load_category_name_map,
    load_hashtag_name_map,
    resolve_name,
)
from expense.dates import to_canonical_aware
from expense.errors import EngineError, format_error
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
from expense.tui.theme import AMOUNT_RULE, BALANCE_RULE, PALETTE, Palette
from expense.tui.widgets.cells import amount_cell, difference_cell
from expense.tui.widgets.checklist import CheckList
from expense.tui.widgets.cursor_list import CursorList
from expense.tui.widgets.header import Breadcrumb

# Status labels + period formatting are owned by the commands layer
# (reconcile_cmd.format_status / format_period) — one copy, per the §5 rule.
_period = reconcile_cmd.format_period

_BATCH_HEADERS = ["Name", "Period", "Begin", "End", "Diff", "Status"]
_UNFILED_HEADERS = ["", "Date", "Title", "Amount", "Category"]

#: How many unfiled rows the pane asks for. It lands on the OLDEST rows, which
#: is the whole point of the view, and the engine has no sort parameter — so the
#: page is fetched from the tail by offset and reversed for display. One page is
#: deliberate: the pane is a work queue (fix these, press `r`, the next oldest
#: arrive), not a browser over a ledger that can hold thousands of unfiled rows.
UNFILED_PAGE = 40


def unfiled_offset(total: int, limit: int) -> int:
    """Offset of the last page of `total` rows — the oldest ones, since
    `GET /transactions` is always `date DESC` and takes no sort parameter."""
    return max(0, total - limit)


def blocking_windows(recons: list[dict], account_id) -> list[tuple[str, str, str]]:
    """`(first_day, last_day, name)` for every dated batch on this account.

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
        start, end = (r.get("date_start") or "")[:10], (r.get("date_end") or "")[:10]
        if start and end:
            windows.append((start, end, r.get("name") or "—"))
    return windows


def unfiled_rows(items: list[dict], cat_names: dict, windows, palette=None) -> list:
    """Rows for the unfiled pane, oldest first, `!` on the ones inside a window.

    **The flag is a hint, not a ruling.** It compares each row's date against
    windows this screen already holds, so it costs no request — but the engine
    is the authority at close time (it resolves a window in the user's
    timezone), so an edge day may differ. Nothing downstream reads the flag: it
    only tells you which rows are worth opening first.
    """
    rows = []
    for it in reversed(items):  # the page arrives date DESC; the pane reads oldest first
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


def _batch_sort_key(r: dict):
    """The engine's account-scoped order, mirrored for a client-side slice.

    `fetch()` pulls every account's batches in one unscoped read so that moving
    the account cursor stays instant — and the unscoped list is `created_at
    DESC`, not statement order (only account-scoped reads sort by date — engine
    contract, unchained since 2026-08-06). So the per-account slice re-applies
    the documented server key: `date_start ASC NULLS LAST, created_at ASC`.
    ISO-8601 strings sort chronologically as text.
    """
    ds = r.get("date_start")
    return (ds is None, ds or "", r.get("created_at") or "", r.get("id") or "")


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


class ReconciliationsScreen(SectionScreen):
    """Account-first two-pane browse. Top: bank accounts. Bottom: the selected
    account's batches in the engine's statement-date order. `↑↓` in account
    focus swaps the account (the batch list follows); `enter` drops into batch
    focus; there `enter` opens a batch, `esc` returns to accounts."""

    crumb = ("Capture & ledger", "Reconciliations")
    CARD_WIDTH = 100
    BINDINGS = [
        ("escape", "back", "Back"),  # not the inherited pop: three-stage unfiled/batches → accts
        ("n", "new", "New"),
        Binding("u", "unfiled", "No batch", tooltip="This account's rows that are in no batch"),
        Binding("d", "delete_row", "Delete", show=False),  # unfiled pane only
    ]

    def __init__(self) -> None:
        super().__init__()
        self._recons: list = []
        self._accounts: list = []  # (id, name, currency, balance_cents)
        self._acct_idx = 0
        self._mode = "accts"  # "accts" | "batches" | "unfiled"
        self._unfiled: list = []  # the fetched page of unfiled rows, newest first
        self._unfiled_total: int | None = None
        self._unfiled_busy = False
        self._batches: list = []  # recon dicts for the selected account (sorted)
        self._by_id: dict = {}
        self._resume_batch = False
        self._resume_key: object | None = None

    def fetch(self) -> dict:
        from expense import config as config_module

        cfg = config_module.ensure_loaded()
        kw = screen_fetch_kwargs(self.app)
        # page through everything: the default ~100-row page truncated the
        # account's batches, so the lower pane silently lost old ones (6.2b)
        recons = fetch_all_pages(
            lambda limit, offset: reconcile_cmd.fetch_reconciliations(
                cfg, limit=limit, offset=offset, **kw
            )
        )
        accts = items_of(accounts_cmd.fetch_accounts(cfg, **kw))
        accounts = account_choices(accts, include_people=False, with_balance=True)
        return {"recons": recons, "accounts": accounts}

    def _selected_account(self):
        return self._accounts[self._acct_idx] if self._accounts else None

    def _rebuild_batches(self) -> None:
        acct = self._selected_account()
        aid = acct[0] if acct else None
        self._batches = sorted(
            (r for r in self._recons if r.get("account_id") == aid), key=_batch_sort_key
        )
        self._by_id = {r.get("id"): r for r in self._batches}

    def _batch_caption(self) -> str:
        acct = self._selected_account()
        label = acct[1] if acct else "—"
        return f"Reconciliations · {label}   ·   by statement start date (oldest → newest)"

    # ---- adaptive window (2026-07-13): two stacked panes split #content ----
    def pane_rows(self) -> int:
        """Rows-per-pane = an equal split of what fits — auto-height panes give
        unused rows back when a pane has fewer rows than its share. Clamped by
        `AdaptiveRowsMixin`, which is what this used to do for itself against a
        hardcoded 20.

        The chrome is the section title (2) plus the two panes' frames, which
        are **not** the same size: the batches pane keeps a caption naming the
        account and the accounts pane does not, so it is `2 * LIST_FRAME_LINES
        + CAPTION_LINES` rather than an even doubling.
        """
        return self.fit_rows(
            chrome=2 + 2 * self.LIST_FRAME_LINES + self.CAPTION_LINES, lines_per_row=2
        )

    def _viewport_resized(self) -> None:
        for lst in (getattr(self, "_accts_list", None), getattr(self, "_batch_list", None)):
            if lst is not None and lst.is_attached:
                lst.set_page_size(self.pane_rows())

    def build(self, data: dict) -> list[Widget]:
        self._recons = data["recons"]
        self._accounts = data["accounts"]
        self._acct_idx = min(self._acct_idx, max(0, len(self._accounts) - 1))
        self._rebuild_batches()
        palette = PALETTE
        acct_rows = [
            (aid, [name, cur, amount_cell(bal, palette, AMOUNT_RULE)])
            for (aid, name, cur, bal) in self._accounts
        ]
        pane_size = self.pane_rows()
        self._accts_list = CursorList(
            ["Account", "Cur", "Balance"],
            acct_rows,
            align_right={2},
            empty="(no bank accounts)",
            page_size=pane_size,
        )
        self._accts_list.id = "accts"
        self._batch_list = CursorList(
            _BATCH_HEADERS,
            batch_rows(self._batches, palette=palette),
            align_right={2, 3, 4},
            empty="(no batches — press n to create one)",
            caption=self._batch_caption(),  # a content line; updated as the cursor moves
            page_size=pane_size,
        )
        self._batch_list.id = "batches"
        title = "Reconciliations — pick an account, then a batch"
        return [
            Static(Text(title), classes="section-title"),
            self._accts_list,
            self._batch_list,
        ]

    async def _show(self, data: object) -> None:
        await super()._show(data)
        if not self._accounts:
            return
        self._accts_list.set_cursor(self._acct_idx)
        if self._resume_batch:
            self._resume_batch = False
            self._mode = "batches"
            self._batch_list.set_cursor(self._batch_list.index_of(self._resume_key))
            self._batch_list.focus()
        else:
            self._mode = "accts"
            self._accts_list.focus()

    # ---- interaction -----------------------------------------------------
    def on_cursor_list_highlighted(self, event: CursorList.Highlighted) -> None:
        # Source guard (backlog 6.2c): a Highlighted from the batches pane
        # (reachable by Tab/click focus without a select) must not overwrite
        # the selected account — `n` would then create under the wrong one.
        if self._mode != "accts" or event.control is not getattr(self, "_accts_list", None):
            return
        self._acct_idx = event.index
        self._rebuild_batches()
        self._batch_list.set_rows(batch_rows(self._batches, palette=PALETTE))
        self._batch_list.set_caption(self._batch_caption())

    def on_cursor_list_selected(self, event: CursorList.Selected) -> None:
        if self._mode == "unfiled":
            # `⏎` opens the form that already edits date and account — the two
            # remedies for a row that is in no batch (owner, 2026-09-22).
            record = self._unfiled_record()
            if record is not None:
                acct = self._selected_account()
                from expense.tui.screens.quick_log import QuickAddLogScreen

                self.app.push_screen(
                    QuickAddLogScreen(record=record),
                    lambda _result: self._reload_unfiled(acct),
                )
            return
        if self._mode == "accts":
            if not self._batches:
                self.notify("No batches for this account — press n to create one.")
                return
            self._mode = "batches"
            self._batch_list.focus()
            return
        item = self._by_id.get(event.key)
        if item:
            self._resume_batch = True
            self._resume_key = event.key
            self.app.push_screen(ReconciliationDetailScreen(item), lambda _result: self._load())

    def action_back(self) -> None:
        if self._mode == "unfiled":
            # the pane swaps back; the screen and the account cursor stay put
            self._mode = "batches" if self._batches else "accts"
            self._unfiled, self._unfiled_total = [], None
            self._batch_list.set_headers(_BATCH_HEADERS, align_right={2, 3, 4})
            self._batch_list.set_caption(self._batch_caption())
            self._batch_list.set_rows(batch_rows(self._batches, palette=PALETTE))
            (self._batch_list if self._batches else self._accts_list).focus()
        elif self._mode == "batches":
            self._mode = "accts"
            self._accts_list.focus()
        else:
            self.app.pop_screen()

    def _reload_unfiled(self, acct) -> None:
        """Refetch the pane after an edit — a row whose date or account moved is
        no longer in this list, which is the point of editing it."""
        if acct and self._mode == "unfiled":
            self._unfiled_busy = True
            self._load_unfiled(acct[0])

    # ---- the unfiled pane (2026-09-22) -----------------------------------
    def action_unfiled(self) -> None:
        """`u` — swap the lower pane to this account's rows in no batch.

        The screen does not change and the account cursor does not move: only
        what the lower list is listing. `esc` swaps it back. Owner's shape,
        mockup expense-world-rows-in-no-batch.html — reconciliation work stays
        in the reconciliation view, so this is a pane, not a filtered ledger.
        """
        acct = self._selected_account()
        if not acct:
            self.notify("No account selected.", severity="error")
            return
        if self._unfiled_busy:
            return
        self._unfiled_busy = True
        self._mode = "unfiled"
        self._batch_list.set_headers(_UNFILED_HEADERS, align_right={3})
        self._batch_list.set_caption(f"In no batch · {acct[1]}   ·   loading…")
        self._batch_list.set_rows([])
        self._load_unfiled(acct[0])

    @work(thread=True, exclusive=True, group="recon-unfiled")
    def _load_unfiled(self, account_id: str) -> None:
        from expense import config as config_module

        worker = get_current_worker()
        try:
            cfg = config_module.ensure_loaded()
            kw = screen_fetch_kwargs(self.app)
            # Two reads, deliberately: the first says how many there are, the
            # second asks for the LAST page — the oldest rows, which is the
            # question this pane answers. `GET /transactions` is always
            # `date DESC` and takes no sort parameter (engine-spec), so the tail
            # is the only honest way to reach them without pulling everything.
            head = transactions_cmd.fetch_transactions(
                cfg, account=account_id, unreconciled=True, limit=1, **kw
            )
            total = head.get("total")
            if not isinstance(total, int):
                total = len(items_of(head))
            items = items_of(head)
            if total > 1:
                body = transactions_cmd.fetch_transactions(
                    cfg,
                    account=account_id,
                    unreconciled=True,
                    limit=UNFILED_PAGE,
                    offset=unfiled_offset(total, UNFILED_PAGE),
                    **kw,
                )
                items = items_of(body)
            cat_names = load_category_name_map()
        except Exception as exc:
            if not worker.is_cancelled:
                self.app.call_from_thread(self._unfiled_failed, format_error(exc))
            return
        if worker.is_cancelled:
            return
        self.app.call_from_thread(self._show_unfiled, account_id, items, total, cat_names)

    def _unfiled_failed(self, message: str) -> None:
        self._unfiled_busy = False
        self._mode = "batches" if self._batches else "accts"
        self._batch_list.set_headers(_BATCH_HEADERS, align_right={2, 3, 4})
        self._batch_list.set_caption(self._batch_caption())
        self._batch_list.set_rows(batch_rows(self._batches, palette=PALETTE))
        self.notify(message, title="Failed", severity="error")

    def _show_unfiled(self, account_id: str, items: list, total: int, cat_names: dict) -> None:
        self._unfiled_busy = False
        if self._mode != "unfiled":  # esc landed while the read was in flight
            return
        self._unfiled = items
        self._unfiled_total = total
        acct = self._selected_account()
        label = acct[1] if acct else "—"
        windows = blocking_windows(self._recons, account_id)
        rows = unfiled_rows(items, cat_names, windows, palette=PALETTE)
        shown = len(rows)
        head = f"In no batch · {label}   ·   {total} row{'' if total == 1 else 's'}"
        if shown < total:
            head += f" · the {shown} oldest"
        self._batch_list.set_caption(f"{head} · oldest first   ·   ! blocks a batch's close")
        self._batch_list.set_rows(rows)
        self._batch_list.set_cursor(0)
        self._batch_list.focus()

    def _unfiled_record(self) -> dict | None:
        key = self._batch_list.cursor_key if self._batch_list is not None else None
        return next((it for it in self._unfiled if it.get("id") == key), None)

    def action_delete_row(self) -> None:
        """`d` — delete the row under the cursor, in the unfiled pane only.

        The one destructive key in the TUI (owner, 2026-09-22). Cursor row only,
        never a selection: `a`-style page selects live on the ledger and this
        pane deliberately has none. The engine's delete is a soft delete, but no
        TUI door restores one — so the confirm says so.
        """
        if self._mode != "unfiled":
            return
        record = self._unfiled_record()
        if record is None:
            return
        title = record.get("title") or "—"
        amount = format_cents(record.get("amount_cents"))
        day = (record.get("date") or "")[:10]
        acct = self._selected_account()
        self._confirm_delete(
            record,
            f"{title} · {amount} · {day} · {acct[1] if acct else '—'}\n"
            "It leaves every balance and report. The engine keeps it recoverable, "
            "but nothing in the TUI can bring it back.",
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
        acct = self._selected_account()
        if acct and self._mode == "unfiled":
            self._unfiled_busy = True
            self._load_unfiled(acct[0])

    def action_new(self) -> None:
        acct = self._selected_account()
        if not acct:
            self.notify("No account selected.", severity="error")
            return
        self._resume_batch = True
        self._resume_key = None
        self.app.push_screen(
            NewReconciliationScreen(account_id=acct[0], account_name=acct[1]),
            lambda _result: self._load(),
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
    "date_end": "YYYY-MM-DD · optional · empty enter to skip",
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
        # statement. date_start: it is what orders the batch (undated sorts last).
        return ("name", "account", "date_start", "begin")

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
            if text:
                try:
                    to_canonical_aware(text)
                except Exception:
                    self.notify(f"{_R_LABELS[key].title()}: use YYYY-MM-DD.", severity="error")
                    return
                self._values[key] = self._display[key] = text
            elif key == "date_start":  # required — it orders the batch
                self.notify("Date start is required.", severity="error")
                return
            else:
                self._values.pop(key, None)
                self._display.pop(key, None)
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
        payload = {
            "id": str(uuid.uuid4()),
            "account_id": self._values["account"],
            "name": self._values["name"],
        }
        if self._values.get("date_start"):
            payload["date_start"] = to_canonical_aware(self._values["date_start"])
        if self._values.get("date_end"):
            payload["date_end"] = to_canonical_aware(self._values["date_end"])
        # never send beginning_balance_source — the engine's request schemas are
        # extra="forbid" since the 2026-08-06 de-chaining, so it would 422
        payload["beginning_balance_cents"] = self._values["begin"]
        if self._values.get("end") is not None:
            payload["ending_balance_cents"] = self._values["end"]
        return payload

    def _done(self) -> None:
        self.notify("Reconciliation created.")
        self.dismiss()


# --------------------------------------------------------------------------- #
# Working / detail screen — assign transactions, complete / revert / delete
# --------------------------------------------------------------------------- #
def _fetch_all_txns(cfg, **kw) -> list[dict]:
    """Every matching transaction, paged at the engine cap.

    A single limit=500 request 422s live (cap is 200) and silently truncates
    the checklist; page through instead (backlog 3.3 → 6.4a).
    """
    return fetch_all_pages(
        lambda limit, offset: transactions_cmd.fetch_transactions(
            cfg, limit=limit, offset=offset, **kw
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
        # keep _record list-row-shaped: drop the embedded window keys
        self._record = {k: v for k, v in fresh.items() if not k.startswith("transactions")}
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
                # misrepresent balances and the read-only gate. By id: scanning
                # the collection stops at one page and falsely reported later
                # records as deleted (backlog 6.2b).
                try:
                    fresh = reconcile_cmd.fetch_reconciliation(cfg, self._id, limit=1, **kw)
                except EngineError as err:
                    if err.status == 404:
                        if not worker.is_cancelled:
                            self.app.call_from_thread(self._record_gone)
                        return
                    raise
                if worker.is_cancelled:
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
                        date_from=self._record.get("date_start") or None,
                        date_to=self._record.get("date_end") or None,
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
