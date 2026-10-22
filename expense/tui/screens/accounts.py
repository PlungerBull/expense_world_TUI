"""Accounts screen — banks & people.

Built on SectionScreen + the shared CursorList. Includes people and archived
accounts (archived rows dimmed); the Color column renders the account's hex
color as a swatch. Balances are native currency — no surface converts an
account balance to the home currency: a single-currency user sees one
meaningful number, and a multi-currency user gets the value in the unit they
think in for that account. `n` creates; `e` edits the cursor row (prefilled
EditAccountScreen); `a` toggles archive immediately — a second `a` undoes;
`t` turns a bank account into a person (`t Make person`) or a person into a bank
account (`t Make bank`) immediately, the footer naming the one the cursor row
takes, and is off on an archived row; `d` deletes the cursor row after a
question (`a` puts an account away, `d` is for one made by mistake). After `a`
or `t` the list reloads with the cursor on the same account, so a second press
undoes it. `enter` does nothing.
"""

from collections.abc import Callable

from textual.binding import Binding

from expense import reads
from expense.errors import format_error
from expense.formatting import format_cents
from expense.tui.screens._base import DELETE_KEY, ResourceListScreen, list_refusal_text
from expense.tui.theme import AMOUNT_RULE, PALETTE, Palette
from expense.tui.widgets.cells import amount_cell, swatch

_HEADERS = ["Name", "Type", "Cur", "Color", "Balance", "Status"]


def account_rows(items: list[dict], palette: Palette | None = None) -> list:
    """Pure (id, cells, base_style) rows for a CursorList. Unit-testable."""
    rows = []
    for it in items:
        archived = bool(it.get("is_archived"))
        cells = [
            it.get("name") or "(unnamed)",
            "person" if it.get("is_person") else "bank",
            it.get("currency_code") or "?",
            swatch(it.get("color")),
            amount_cell(it.get("current_balance_cents"), palette, AMOUNT_RULE),
            "archived" if archived else "active",
        ]
        rows.append((it.get("id"), cells, "dim" if archived else ""))
    return rows


class AccountsScreen(ResourceListScreen):
    crumb = ("Manage", "Accounts")
    CARD_WIDTH = 80
    TITLE = "Accounts — banks & people"
    HEADERS = _HEADERS
    EMPTY = "(no accounts)"
    LEGEND = "balances are native currency"
    ALIGN_RIGHT = {4}
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

    def delete_question(self, item: dict) -> tuple[str, str, str]:
        kind = "person" if item.get("is_person") else "bank"
        row = " · ".join(
            [
                item.get("name") or "(unnamed)",
                kind,
                item.get("currency_code") or "?",
                format_cents(item.get("current_balance_cents")),
            ]
        )
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
        self._restore_key = item.get("id")
        self.run_write(
            "POST",
            f"/{self.RESOURCE}/{item['id']}/{verb}",
            success=note,
            on_error=self._toggle_failed,
            error_text=error_text,
        )

    def _toggle_failed(self, message: str) -> None:
        self._toggle_busy = False
        self.notify(message, title="Failed", severity="error")

    def rows(self, items: list) -> list:
        return account_rows(items, palette=PALETTE)

    def edit_screen(self, item: dict):
        from expense.tui.screens.create_forms import EditAccountScreen

        return EditAccountScreen(item)

    def new_screen(self):
        from expense.tui.screens.create_forms import NewAccountScreen

        return NewAccountScreen()
