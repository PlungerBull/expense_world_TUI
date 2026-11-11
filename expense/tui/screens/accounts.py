"""Accounts screen — banks & people.

Built on SectionScreen + the shared CursorList. One row per account, in the
engine's order, keyed by the account's id: Name, Type, Code, Color, a column per
currency the engine lists (`GET /currencies`, in its order; read with the accounts
in the screen's worker) and Status. Each
currency column holds the account's balance in that currency, never summed with
another, or a dim `—` when the account does not hold it. Includes people and
archived accounts (archived rows dimmed whole); the Code column shows the account's
statement code, a dim `—` when it has none; a person's is its statement code like any account's
(contract: "What an account is", "A person carries a code like a bank account"); the Color column
renders the account's hex color as a swatch. Balances are native currency — no
surface converts an account balance to the home currency. `n` creates; `e` edits
the cursor row's account (prefilled EditAccountScreen, an opening balance's
pair of lines per currency); `a` toggles its archive immediately — a second `a` undoes; `t`
turns a bank account into a person (`t Make person`) or a person into a bank
account (`t Make bank`) after a short question (`QuestionModal`), the footer naming the one the
cursor row takes, and is off on an archived row; `d` deletes the cursor row's account after a
question (`a` puts an account away, `d` is for one made by mistake). Each acts on
the whole account, every currency at once, through one call with the account's id.
After `a` or `t` the list reloads with the cursor on the same account, so a second
press undoes it. `c` (`c Currency`) lists the engine's currencies the cursor row's
account does not hold (`PickModal`) and `⏎` adds the picked one at once with
`POST /accounts/{id}/currencies`; on an account holding every one it writes nothing
and says so. `x` (`x Remove currency`) lists the currencies the account holds, and
the picked one goes with `DELETE /accounts/{id}/currencies/{code}` after a question
only `y` answers. After either the list reloads with the cursor on the same account;
one currency write at a time, as for `a` and `t`. `enter` on the list does nothing.
"""

from collections.abc import Callable

from rich.text import Text
from textual.binding import Binding

from expense import reads
from expense.errors import EngineError, format_error
from expense.formatting import format_cents, name_or_unnamed
from expense.tui.screens._base import (
    DELETE_KEY,
    LeftBehind,
    ResourceListScreen,
    list_refusal_text,
    not_done_line,
)
from expense.tui.screens.modals import ConfirmModal, PickModal, QuestionLine, QuestionModal
from expense.tui.theme import AMOUNT_RULE, PALETTE, Palette
from expense.tui.widgets.cells import amount_cell, code_cell, swatch
from expense.tui.widgets.cursor_list import waits_for_a_row
from expense.tui.widgets.refusal import toast

_FIXED_HEADS = ["Name", "Type", "Code", "Color"]


def _bank_body(values: dict[str, str]) -> dict:
    """`make-account`'s body: the bank and the last 4, each only when the line holds text,
    as typed, never `null`, and no `name` (contract: POST
    /v1/accounts/{account_id}/make-account, "Body"). With no bank listed none is sent: the
    engine answers `REQUIRED` on `bank_code`."""
    return {key: values[key] for key in ("bank_code", "last4") if values[key]}


def _refused_line(failure: Exception, lines: list[str]) -> str | None:
    """The first of the question's `lines` (engine field names) a refusal names, or None."""
    if not isinstance(failure, EngineError):
        return None
    named = {*(failure.reasons or {}), *(failure.fields or {})}
    return next((key for key in lines if key in named), None)


def account_headers(currencies: list[str]) -> list[str]:
    """Name, Type, Code, Color, a balance column per engine currency, then Status."""
    return [*_FIXED_HEADS, *currencies, "Status"]


def _balance_cells(
    account: dict, currencies: list[str], palette: Palette | None
) -> list[str | Text]:
    """One cell per engine currency, in the engine's order: the account's balance
    in it, or a dim `—` when the account does not hold it."""
    held = {h["currency_code"]: h for _, _, h in reads.held_currencies([account])}
    return [
        amount_cell(held[code].get("current_balance_cents"), palette, AMOUNT_RULE)
        if code in held
        else code_cell(None)
        for code in currencies
    ]


def _kind_word(account: dict) -> str:
    """The Type column's word: `person` and `cash` as the engine's `kind` says, any other
    account `bank`."""
    kind = account.get("kind")
    return kind if kind in ("person", "cash") else "bank"


def account_line(account: dict, *, only: str | None = None) -> str:
    """The account on one line: its name, its kind, then each currency it holds
    with that currency's balance — `Efectivo · bank · PEN 350.00`; with `only`,
    that one currency alone. The line a delete question and the currency picks
    name the account by, and a currency's removal names the currency by."""
    kind = _kind_word(account)
    held = [
        f"{h['currency_code']} {format_cents(h.get('current_balance_cents'))}"
        for _, _, h in reads.held_currencies([account])
        if only is None or h["currency_code"] == only
    ]
    return " · ".join([name_or_unnamed(account.get("name")), kind, *held])


def _who(not_done: str, account: dict) -> str:
    """A refused write on an account, left behind: `Account <name>`, `Person <name>`
    for a person (`not_done_line`)."""
    kind = "Person" if account.get("kind") == "person" else "Account"
    return not_done_line(not_done, kind, account.get("name"))


def currencies_held(account: dict) -> list[str]:
    """The currencies the account holds, in the engine's order: what `x`
    offers. Unit-testable."""
    return [h["currency_code"] for _, _, h in reads.held_currencies([account])]


def currencies_to_add(account: dict, currencies: list[str]) -> list[str]:
    """The engine's currencies the account does not hold, in the engine's order:
    what `c` offers. Unit-testable."""
    held = {h["currency_code"] for _, _, h in reads.held_currencies([account])}
    return [code for code in currencies if code not in held]


def removal_question(account: dict, code: str) -> tuple[str, str]:
    """`(title, body)` of the question before `code` leaves the account: the
    account with that currency's balance, then what the account keeps."""
    name = name_or_unnamed(account.get("name"))
    kept = [held for held in currencies_held(account) if held != code]
    after = f"{name} keeps {' and '.join(kept)}." if kept else "It is the account's only currency."
    return f"Remove {code} from {name}?", f"{account_line(account, only=code)}\n{after}"


def account_rows(items: list[dict], currencies: list[str], palette: Palette | None = None) -> list:
    """Pure (key, cells, base_style) rows for a CursorList, one per account in the
    order given, a balance cell per engine currency, the key the account's id; id-less
    records are skipped. An archived account's row is dimmed whole. Unit-testable."""
    rows = []
    for account in items:
        if not account.get("id"):
            continue
        archived = bool(account.get("is_archived"))
        cells = [
            name_or_unnamed(account.get("name")),
            _kind_word(account),
            code_cell(account.get("statement_code")),
            swatch(account.get("color")),
            *_balance_cells(account, currencies, palette),
            "archived" if archived else "active",
        ]
        rows.append((account["id"], cells, "dim" if archived else ""))
    return rows


class AccountsScreen(ResourceListScreen):
    crumb = ("Manage", "Accounts")
    CARD_WIDTH = 86
    TITLE = "Accounts — banks & people"
    HEADERS = account_headers([])  # set from the engine's currencies on each build
    EMPTY = "(no accounts)"
    LEGEND = "balances are native currency"
    RESOURCE = "accounts"
    # Accounts are the only archivable resource, so the `a` toggle lives here,
    # not on the shared scaffold. `t` is two bindings of one key, one per
    # direction: `check_action` keeps the one the cursor row takes, so the footer
    # label follows the row and the other binding never fires.
    BINDINGS = [
        *ResourceListScreen.BINDINGS,
        Binding("c", "add_currency", "Currency", tooltip="Add a currency"),
        Binding("x", "remove_currency", "Remove currency", tooltip="Remove a currency"),
        Binding("a", "archive", "Archive", tooltip="Archive / unarchive"),
        Binding("t", "make_person", "Make person"),
        Binding("t", "make_bank", "Make bank"),
        DELETE_KEY,
    ]
    CARD_FOLLOWS_CHECK = frozenset({"delete"})
    CARD_NEEDS_A_ROW = ResourceListScreen.CARD_NEEDS_A_ROW | {
        "add_currency",
        "remove_currency",
        "archive",
        "make_person",
        "make_bank",
    }

    def __init__(self) -> None:
        super().__init__()
        self._currencies: list[str] = []  # the engine's codes, read with the accounts
        self._banks: list[str] = []  # the engine's bank codes, read with them

    def fetch_items(self, cfg, **kw):
        """The accounts, and with them the engine's currencies and banks (worker thread); a
        refused or failed read of any shows the engine's words."""
        accounts = reads.fetch_accounts(cfg, include_archived=True, include_people=True, **kw)
        self._currencies = reads.fetch_currency_codes(cfg, **kw)
        self._banks = reads.fetch_bank_codes(cfg, **kw)
        return accounts

    def build(self, items: list):
        """The columns follow the engine's currencies, one per code."""
        self.HEADERS = account_headers(self._currencies)
        self.ALIGN_RIGHT = set(range(len(_FIXED_HEADS), len(_FIXED_HEADS) + len(self._currencies)))
        return super().build(items)

    def delete_question(self, item: dict) -> tuple[str, str, str]:
        """The whole account (`account_line`), then what a delete is for."""
        return (
            "Delete this account?",
            f"{account_line(item)}\n"
            "It is for an account made by mistake: no screen can bring it back.",
            "Account deleted.",
        )

    def not_deleted(self, item: dict) -> str:
        return _who("Not deleted", item)

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action == "delete" and self._on_cash():
            return False  # `d` leaves the footer and the card on the cash row
        if action not in ("make_person", "make_bank", "add_currency", "remove_currency"):
            return super().check_action(action, parameters)
        if waits_for_a_row(self, action):
            return False  # empty list → nothing to act on; the keys leave the footer
        item = self.selected_record()
        if action in ("add_currency", "remove_currency"):
            return True  # any account, a person's and an archived one's too: the engine judges
        if item.get("is_archived") or item.get("kind") == "cash":
            return False  # an archived or cash account keeps its kind: `t` leaves the footer
        return (item.get("kind") == "person") == (action == "make_bank")

    def _on_cash(self) -> bool:
        """Whether the cursor row is the cash account (its `kind` alone says so)."""
        item = self.selected_record()
        return item is not None and item.get("kind") == "cash"

    def action_delete(self) -> None:
        if self._on_cash():
            return  # the engine never deletes it (contract: DELETE /v1/accounts/{account_id})
        super().action_delete()

    def action_archive(self) -> None:
        item = self.selected_record()
        if not item:
            return
        verb, msg = (
            ("unarchive", "Unarchived.") if item.get("is_archived") else ("archive", "Archived.")
        )
        self._toggle(item, verb, msg, f"Not {verb}d")

    def action_add_currency(self) -> None:
        """`c`: pick a currency the account does not hold, and `⏎` adds it at
        once with no question, as `a` writes. On an account holding every
        currency the engine lists nothing is offered and nothing is sent."""
        item = self.selected_record()
        if not item or self._toggle_busy:
            return
        name = name_or_unnamed(item.get("name"))
        choices = currencies_to_add(item, self._currencies)
        if not choices:
            toast(self, f"{name} already holds every currency.")
            return
        ident = item["id"]

        def picked(code: str | None) -> None:
            if code is None:
                return
            # The body names the currency (contract: POST /v1/accounts/{account_id}/currencies).
            self._currency_write(
                "POST",
                f"/{self.RESOURCE}/{ident}/currencies",
                ident,
                f"Currency added: {code}.",
                f"Not added · {code} on {name}",
                json_body={"currency_code": code},
            )

        pick = PickModal(f"Add a currency · {name}", account_line(item), choices, verb="add")
        self.app.push_screen(pick, picked)

    def action_remove_currency(self) -> None:
        """`x`: pick a currency the account holds, then the question naming the
        account and the currency; only `y` sends the removal. The engine judges
        the rest: the account's last currency, one holding transactions, one in a
        live statement and an archived account are refused in its words alone."""
        item = self.selected_record()
        if not item or self._toggle_busy:
            return
        name = name_or_unnamed(item.get("name"))
        choices = currencies_held(item)
        ident = item["id"]

        def answered(code: str, ok: bool | None) -> None:
            if not ok:
                return
            # No body (contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}).
            self._currency_write(
                "DELETE",
                f"/{self.RESOURCE}/{ident}/currencies/{code}",
                ident,
                f"Currency removed: {code}.",
                f"Not removed · {code} on {name}",
            )

        def picked(code: str | None) -> None:
            if code is None:
                return
            title, body = removal_question(item, code)
            self.app.push_screen(ConfirmModal(title, body), lambda ok: answered(code, ok))

        pick = PickModal(f"Remove a currency · {name}", account_line(item), choices, verb="pick")
        self.app.push_screen(pick, picked)

    def _currency_write(
        self,
        method: str,
        path: str,
        ident: str,
        note: str,
        left_behind: str,
        *,
        json_body: dict | None = None,
    ) -> None:
        """Send `c`'s or `x`'s one write. Written, the note shows and the list
        reads again with the cursor on the same account; refused, the list
        stays as it was, the "Failed" note in the engine's words. One write at a
        time, sharing `a` and `t`'s guard: `c` and `x` do nothing until the
        engine refuses the write or the list builds from a read that began after it was
        answered (`run_guarded_write`)."""
        if self._toggle_busy:
            return

        def written() -> None:
            toast(self, note)
            self._restore_key = ident
            self._load()

        self.run_guarded_write(
            method,
            path,
            json_body=json_body,
            success=note,
            on_success=written,
            on_error=self._toggle_failed,
            error_text=list_refusal_text,
            left_behind=LeftBehind(left_behind),
        )

    def action_make_person(self) -> None:
        """`t` on a bank account: the question for the person's name."""
        if self.check_action("make_person", ()):
            self._ask_to_turn(
                "make-person",
                "a person",
                (QuestionLine("name", "name"),),
                lambda values: {"name": values["name"]},
                "Now a person.",
                "Not made a person",
            )

    def action_make_bank(self) -> None:
        """`t` on a person: the question for the bank and an optional last 4."""
        if self.check_action("make_bank", ()):
            self._ask_to_turn(
                "make-account",
                "a bank account",
                (
                    QuestionLine("bank_code", "bank", tuple(self._banks)),
                    QuestionLine("last4", "last 4", note="optional"),
                ),
                _bank_body,
                "Now a bank account.",
                "Not made a bank account",
            )

    def _ask_to_turn(
        self,
        verb: str,
        kind: str,
        lines: tuple[QuestionLine, ...],
        body_of: Callable[[dict[str, str]], dict],
        note: str,
        not_done: str,
    ) -> None:
        """`t`: ask what the engine needs to turn the cursor account into `kind`, then
        `⏎` sends `POST /accounts/{id}/{verb}` with the body `body_of` makes of the lines.
        The engine judges what was typed: a refusal keyed on one of the question's own
        lines (`name`, `bank_code`, `last4`) keeps the question open on that line, in the
        engine's words, what was typed kept; any other closes the question and reads in
        the list's words. Written, the note shows and the list reloads with the cursor on
        the same account. One at a time, as `a` is (`run_guarded_write`)."""
        item = self.selected_record()
        if not item or self._toggle_busy:
            return
        ident = item["id"]
        title = f"Make {name_or_unnamed(item.get('name'))} {kind}?"

        def written() -> None:
            toast(self, note)
            self._restore_key = ident
            if modal.is_attached:
                modal.dismiss()
            self._load()

        def failed(failure: Exception) -> None:
            line = _refused_line(failure, modal.keys())
            if line is not None and modal.is_attached:
                self.clear_guard()
                modal.refuse(line, format_error(failure))
                return
            if modal.is_attached:
                modal.dismiss()
            self._toggle_failed(list_refusal_text(failure))

        def send(values: dict[str, str]) -> None:
            self.run_guarded_write(
                "POST",
                f"/{self.RESOURCE}/{ident}/{verb}",
                json_body=body_of(values),
                success=note,
                on_success=written,
                on_failure=failed,
                error_text=list_refusal_text,
                left_behind=LeftBehind(_who(not_done, item)),
            )

        modal = QuestionModal(title, lines, "⏎ makes it · esc keeps it", send)
        self.app.push_screen(modal)

    def _toggle(self, item: dict, verb: str, note: str, not_done: str) -> None:
        """`a`'s write: `POST /accounts/{id}/{verb}` at once, with no question, a
        refusal read in the list's words; the list reloads with the cursor on the
        same account. One toggle at a time: a second press while one is in flight
        does nothing until the engine refuses it or the list builds from a read that
        began after it was answered (`run_guarded_write`)."""
        if self._toggle_busy:
            return
        self._restore_key = self.selected_key()
        self.run_guarded_write(
            "POST",
            f"/{self.RESOURCE}/{item['id']}/{verb}",
            success=note,
            on_error=self._toggle_failed,
            error_text=list_refusal_text,
            left_behind=LeftBehind(_who(not_done, item)),
        )

    def _toggle_failed(self, message: str) -> None:
        self.clear_guard()
        toast(self, message, title="Failed", severity="error")

    def rows(self, items: list) -> list:
        return account_rows(items, self._currencies, palette=PALETTE)

    def edit_screen(self, item: dict):
        from expense.tui.screens.create_forms import EditAccountScreen

        return EditAccountScreen(item, self._currencies, self._banks)

    def new_screen(self):
        from expense.tui.screens.create_forms import NewAccountScreen

        return NewAccountScreen(self._currencies, self._banks)
