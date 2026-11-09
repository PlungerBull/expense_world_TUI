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
account (`t Make bank`) immediately, the footer naming the one the cursor row
takes, and is off on an archived row; `d` deletes the cursor row's account after a
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

from rich.text import Text
from textual.binding import Binding

from expense import reads
from expense.formatting import format_cents, name_or_unnamed
from expense.tui.screens._base import (
    DELETE_KEY,
    LeftBehind,
    ResourceListScreen,
    list_refusal_text,
    not_done_line,
)
from expense.tui.screens.modals import ConfirmModal, PickModal
from expense.tui.theme import AMOUNT_RULE, PALETTE, Palette
from expense.tui.widgets.cells import amount_cell, code_cell, swatch
from expense.tui.widgets.cursor_list import waits_for_a_row
from expense.tui.widgets.refusal import toast

_FIXED_HEADS = ["Name", "Type", "Code", "Color"]


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


def account_line(account: dict, *, only: str | None = None) -> str:
    """The account on one line: its name, its kind, then each currency it holds
    with that currency's balance — `Efectivo · bank · PEN 350.00`; with `only`,
    that one currency alone. The line a delete question and the currency picks
    name the account by, and a currency's removal names the currency by."""
    kind = "person" if account.get("kind") == "person" else "bank"
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
            "person" if account.get("kind") == "person" else "bank",
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
        if action not in ("make_person", "make_bank", "add_currency", "remove_currency"):
            return super().check_action(action, parameters)
        if waits_for_a_row(self, action):
            return False  # empty list → nothing to act on; the keys leave the footer
        item = self.selected_record()
        if action in ("add_currency", "remove_currency"):
            return True  # any account, a person's and an archived one's too: the engine judges
        if item.get("is_archived"):
            return False  # an archived account keeps its kind: `t` leaves the footer
        return (item.get("kind") == "person") == (action == "make_bank")

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
        # No body (contract: POST /v1/accounts/{account_id}/make-person).
        if self.check_action("make_person", ()):
            self._turn("make-person", "Now a person.", "Not made a person")

    def action_make_bank(self) -> None:
        # No body (contract: POST /v1/accounts/{account_id}/make-account).
        if self.check_action("make_bank", ()):
            self._turn("make-account", "Now a bank account.", "Not made a bank account")

    def _turn(self, verb: str, note: str, not_done: str) -> None:
        """`t`: turn the cursor account into a person or a bank."""
        item = self.selected_record()
        if item:
            self._toggle(item, verb, note, not_done)

    def _toggle(self, item: dict, verb: str, note: str, not_done: str) -> None:
        """`a`'s and `t`'s write: `POST /accounts/{id}/{verb}` at once, with no
        question, a refusal read in the list's words; the list reloads with the
        cursor on the same account. One toggle at a time: a second press while
        one is in flight does nothing until the engine refuses it or the list
        builds from a read that began after it was answered
        (`run_guarded_write`)."""
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
