"""Accounts screen — banks & people.

Built on SectionScreen + the shared CursorList. One row per account and currency
it holds, named "<account> · <code>" (`reads.held_currencies` is the walk), the
Cur and Balance cells that currency's and the Type, Code, Color and Status cells
the account's, in the engine's order. Includes people and archived accounts
(archived rows dimmed); the Code column shows the account's statement code, a dim
`—` when it has none (a person always); the Color column renders the account's hex
color as a swatch. Balances are native currency — no surface converts an account
balance to the home currency. `n` creates; `e` edits the cursor row's account
(prefilled EditAccountScreen); `a` toggles its archive immediately — a second `a`
undoes; `t` turns a bank account into a person (`t Make person`) or a person into a
bank account (`t Make bank`) immediately, the footer naming the one the cursor row
takes, and is off on an archived row; `d` deletes the cursor row's account after a
question (`a` puts an account away, `d` is for one made by mistake). Each acts on
the whole account, every currency at once, through one call with the account's id.
After `a` or `t` the list reloads with the cursor on the same row, so a second press
undoes it. `enter` does nothing.
"""

from collections.abc import Callable

from textual.binding import Binding

from expense import reads
from expense.errors import format_error
from expense.formatting import currency_label, format_cents
from expense.tui.screens._base import DELETE_KEY, ResourceListScreen, list_refusal_text
from expense.tui.theme import AMOUNT_RULE, PALETTE, Palette
from expense.tui.widgets.cells import amount_cell, code_cell, swatch
from expense.tui.widgets.refusal import toast

_HEADERS = ["Name", "Type", "Cur", "Code", "Color", "Balance", "Status"]


def _row_entries(items: list[dict]) -> list[tuple[dict, str, dict | None]]:
    """`(account, name, currency entry)` per list row, in the engine's order: one per
    currency an account holds (`reads.held_currencies`), and one with no entry for an
    account that holds none, so it stays reachable."""
    entries: list[tuple[dict, str, dict | None]] = []
    for account in items:
        if not account.get("id"):
            continue
        held = reads.held_currencies([account])
        entries.extend(held or [(account, account.get("name") or "(unnamed)", None)])
    return entries


def account_rows(items: list[dict], palette: Palette | None = None) -> list:
    """Pure (key, cells, base_style) rows for a CursorList, one per account and
    currency, the key `(account id, currency code)`; an account holding no currency
    has one row, its name alone, a dim `—` for Cur and Balance, and the key
    `(account id, None)`. Unit-testable."""
    rows = []
    for account, name, held in _row_entries(items):
        archived = bool(account.get("is_archived"))
        code = held["currency_code"] if held else None
        cells = [
            currency_label(name, code) if code else name,
            "person" if account.get("is_person") else "bank",
            code_cell(code),
            code_cell(account.get("statement_code")),
            swatch(account.get("color")),
            amount_cell(held.get("current_balance_cents"), palette, AMOUNT_RULE)
            if held
            else code_cell(None),
            "archived" if archived else "active",
        ]
        rows.append(((account["id"], code), cells, "dim" if archived else ""))
    return rows


class AccountsScreen(ResourceListScreen):
    crumb = ("Manage", "Accounts")
    CARD_WIDTH = 86
    TITLE = "Accounts — banks & people"
    HEADERS = _HEADERS
    EMPTY = "(no accounts)"
    LEGEND = "balances are native currency"
    ALIGN_RIGHT = {5}
    RESOURCE = "accounts"
    # Accounts are the only archivable resource, so the `a` toggle lives here,
    # not on the shared scaffold. `t` is two bindings of one key, one per
    # direction: `check_action` keeps the one the cursor row takes, so the footer
    # label follows the row and the other binding never fires.
    BINDINGS = [
        *ResourceListScreen.BINDINGS,
        Binding("a", "archive", "Archive", tooltip="Archive / unarchive"),
        Binding("t", "make_person", "Make person"),
        Binding("t", "make_bank", "Make bank"),
        DELETE_KEY,
    ]

    def fetch_items(self, cfg, **kw):
        return reads.fetch_accounts(cfg, include_archived=True, include_people=True, **kw)

    def index_items(self, items: list) -> dict:
        return {
            (account["id"], held["currency_code"] if held else None): account
            for account, _, held in _row_entries(items)
        }

    def delete_question(self, item: dict) -> tuple[str, str, str]:
        """The whole account, whichever of its rows the cursor is on: its name, its
        kind, then each currency it holds with that currency's balance."""
        kind = "person" if item.get("is_person") else "bank"
        held = [
            f"{h['currency_code']} {format_cents(h.get('current_balance_cents'))}"
            for _, _, h in reads.held_currencies([item])
        ]
        row = " · ".join([item.get("name") or "(unnamed)", kind, *held])
        return (
            "Delete this account?",
            f"{row}\nIt is for an account made by mistake: no screen can bring it back.",
            "Account deleted.",
        )

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action not in ("make_person", "make_bank"):
            return super().check_action(action, parameters)
        item = self.selected_record()
        if item is None:
            return None  # empty list → nothing to turn
        if item.get("is_archived"):
            return False  # an archived account keeps its kind: `t` leaves the footer
        return bool(item.get("is_person")) == (action == "make_bank")

    def action_archive(self) -> None:
        item = self.selected_record()
        if not item:
            return
        verb, msg = (
            ("unarchive", "Unarchived.") if item.get("is_archived") else ("archive", "Archived.")
        )
        self._toggle(item, verb, msg)

    def action_make_person(self) -> None:
        # No body (contract: POST /v1/accounts/{account_id}/make-person).
        if self.check_action("make_person", ()):
            self._turn("make-person", "Now a person.")

    def action_make_bank(self) -> None:
        # No body (contract: POST /v1/accounts/{account_id}/make-account).
        if self.check_action("make_bank", ()):
            self._turn("make-account", "Now a bank account.")

    def _turn(self, verb: str, note: str) -> None:
        """`t`: a refusal is met on a list, so it reads in the list's words."""
        item = self.selected_record()
        if item:
            self._toggle(item, verb, note, error_text=list_refusal_text)

    def _toggle(
        self,
        item: dict,
        verb: str,
        note: str,
        error_text: Callable[[Exception], str] = format_error,
    ) -> None:
        """Send `POST /accounts/{id}/{verb}` at once, with no question; the list
        reloads with the cursor on the same account. One toggle at a time: a
        second press while one is in flight does nothing until the reload lands
        or the engine refuses."""
        if self._toggle_busy:
            return
        self._toggle_busy = True
        self._restore_key = self.selected_key()
        self.run_write(
            "POST",
            f"/{self.RESOURCE}/{item['id']}/{verb}",
            success=note,
            on_error=self._toggle_failed,
            error_text=error_text,
        )

    def _toggle_failed(self, message: str) -> None:
        self._toggle_busy = False
        toast(self, message, title="Failed", severity="error")

    def rows(self, items: list) -> list:
        return account_rows(items, palette=PALETTE)

    def edit_screen(self, item: dict):
        from expense.tui.screens.create_forms import EditAccountScreen

        key = self.selected_key()
        code = key[1] if isinstance(key, tuple) else None
        return EditAccountScreen(item, code)

    def new_screen(self):
        from expense.tui.screens.create_forms import NewAccountScreen

        return NewAccountScreen()
