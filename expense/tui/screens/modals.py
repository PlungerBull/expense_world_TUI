"""Reusable modal screens."""

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Static

from expense.tui.widgets.windowed import CURSOR_STYLE


class ConfirmModal(ModalScreen[bool]):
    """Yes/no confirmation. Only `y` confirms; `enter`/`n`/`esc` cancel — enter is
    the safe default so a reflexive keypress can never apply a write. Dismisses
    with the boolean result (use `push_screen(modal, callback)` to act on it)."""

    BINDINGS = [
        ("y", "confirm", "Yes"),
        ("n,escape,enter", "cancel", "No"),
    ]

    def __init__(self, title: str, message: str) -> None:
        super().__init__()
        self._title = title
        self._message = message

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(Text(self._title), classes="modal-title"),
            Static(Text(self._message)),
            Static(Text("[y] confirm    [enter / n / esc] cancel", style="dim")),
            id="modal",
        )
        yield Footer()

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class PromptModal(ModalScreen[str | None]):
    """Single-line text prompt. `enter` submits the value, `esc` cancels (None).
    `password=True` masks input (for the token). Dismisses with the string."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(
        self, title: str, message: str = "", *, value: str = "", password: bool = False
    ) -> None:
        super().__init__()
        self._title = title
        self._message = message
        self._value = value
        self._password = password

    def compose(self) -> ComposeResult:
        rows = [Static(Text(self._title), classes="modal-title")]
        if self._message:
            rows.append(Static(Text(self._message, style="dim")))
        rows.append(Input(value=self._value, password=self._password, id="prompt"))
        rows.append(Static(Text("[enter] save    [esc] cancel", style="dim")))
        yield Vertical(*rows, id="modal")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#prompt", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def action_cancel(self) -> None:
        self.dismiss(None)


class DiscardStagedModal(ModalScreen[str]):
    """`esc` with rows staged — the one confirmation on the LOG bar.

    `d` discards, `enter` (and `esc`) keep editing: the safe answer is the
    reflexive one, the same call `ConfirmModal` makes. It is **not** a y/n card,
    because "yes" to "5 rows are staged and not written" reads both ways.

    `ctrl+s save first` is the third answer. It writes the rows and then
    leaves — you pressed `esc`, so the
    intent was to go — but only if every row lands; a failed save keeps you on
    the screen where the error is readable.

    Returns the answer by name rather than a bool: three outcomes do not fit
    one, and `"keep"`/`"discard"`/`"save"` read at the call site.
    """

    BINDINGS = [
        ("d", "discard", "Discard"),
        ("ctrl+s", "save_first", "Save first"),
        ("enter,escape", "keep", "Keep editing"),
    ]

    def __init__(self, count: int) -> None:
        super().__init__()
        self._count = count

    def compose(self) -> ComposeResult:
        rows = "row is" if self._count == 1 else "rows are"
        yield Vertical(
            Static(
                Text(f"{self._count} {rows} staged and not written.", style="bold"),
                classes="modal-title",
            ),
            Static(Text("[enter] keep editing    [d] discard    [^s] save first", style="dim")),
            id="modal",
        )
        yield Footer()

    def action_discard(self) -> None:
        self.dismiss("discard")

    def action_save_first(self) -> None:
        self.dismiss("save")

    def action_keep(self) -> None:
        self.dismiss("keep")


class PickerModal(ModalScreen[object]):
    """Pick one reference row — or several hashtags — by typing part of a name.

    The bulk-edit picker: `c`, `b` and `h` on the ledger open it
    over the rows they will touch, headed by the count. Candidates are matched the way every other
    picker in the app matches (`quickadd.names.matches`: any substring, case-
    and accent-blind) and drawn on one line, the highlighted one in reverse.
    `↑↓` move the highlight, `↵` applies, `esc` cancels (None).

    Single mode dismisses with the highlighted candidate's id — an empty
    needle means the first option, so a two-keystroke pick is possible.

    Multi mode (`multi=True`, the hashtags) collects picks: `↵` on a needle
    adds the highlighted candidate to the picked line and clears the input;
    `↵` on an empty input applies the picks; `backspace` on an empty input
    drops the last one. Picks are ids, never re-parsed text, so a tag whose
    name has a space in it is one pick like any other. An empty apply is
    refused rather than taken as "clear every tag" — the edit form does that
    one row at a time, on purpose.

    Returns the picked id (str), the list of ids (multi), or None.
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("up", "move(-1)", "Up"),
        ("down", "move(1)", "Down"),
    ]

    def __init__(
        self,
        title: str,
        options: list[tuple[str, str]],
        *,
        note: str = "",
        multi: bool = False,
    ) -> None:
        super().__init__()
        self._title = title
        self._options = list(options)
        self._names = dict(options)
        self._note = note
        self._multi = multi
        self._pool: list[tuple[str, str]] = list(options)
        self._idx = 0
        self._picked: list[str] = []

    # ---- matching --------------------------------------------------------
    def _recompute(self, text: str) -> None:
        from expense.quickadd.names import matches

        needle = text.strip()
        taken = set(self._picked)
        self._pool = [(i, n) for i, n in self._options if matches(needle, n) and i not in taken]
        self._idx = 0
        self._refresh_candidates()

    def _refresh_candidates(self) -> None:
        line = Text("  ")
        if not self._pool:
            line.append("no matches — pick something that exists", style="dim")
        for k, (_id, name) in enumerate(self._pool[:12]):
            line.append(f" {name} ", style=CURSOR_STYLE if k == self._idx else "")
            line.append("  ")
        if len(self._pool) > 12:
            line.append(f"… {len(self._pool) - 12} more", style="dim")
        self.query_one("#candidates", Static).update(line)

    def _refresh_picked(self) -> None:
        if not self._multi:
            return
        names = " ".join("#" + self._names.get(i, i) for i in self._picked)
        text = Text("picked: ", style="dim")
        text.append(names if names else "(none yet)", style="" if names else "dim")
        self.query_one("#picked", Static).update(text)

    # ---- widgets ---------------------------------------------------------
    def compose(self) -> ComposeResult:
        keys = "↑↓ moves · ↵ applies · esc cancels"
        if self._multi:
            keys = "↑↓ moves · ↵ adds, ↵ on empty applies · ⌫ on empty drops the last · esc cancels"
        rows = [Static(Text(self._title), classes="modal-title")]
        if self._multi:
            rows.append(Static(Text(""), id="picked"))
        rows.append(Input(placeholder="type to narrow", id="picker"))
        rows.append(Static(Text(""), id="candidates"))
        rows.append(Static(Text(f"{self._note} · {keys}" if self._note else keys, style="dim")))
        yield Vertical(*rows, id="modal")
        yield Footer()

    def on_mount(self) -> None:
        self._recompute("")
        self._refresh_picked()
        self.query_one("#picker", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._recompute(event.value)

    def action_move(self, delta: int) -> None:
        if self._pool:
            self._idx = max(0, min(len(self._pool) - 1, self._idx + delta))
            self._refresh_candidates()

    def on_key(self, event) -> None:
        # `backspace` on an empty input un-picks the last tag. The Input's own
        # binding sees the key first and, with nothing to delete, lets it
        # bubble here.
        if self._multi and event.key == "backspace" and self._picked:
            box = self.query_one("#picker", Input)
            if not box.value:
                self._picked.pop()
                self._refresh_picked()
                self._recompute("")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        needle = event.value.strip()
        if not self._multi:
            if not self._pool:
                self.notify(f"Nothing matches “{needle}”.", severity="error")
                return
            self.dismiss(self._pool[self._idx][0])
            return
        if needle:
            if not self._pool:
                self.notify(f"No hashtag matches “{needle}”.", severity="error")
                return
            self._picked.append(self._pool[self._idx][0])
            self._refresh_picked()
            self.query_one("#picker", Input).value = ""  # Changed → _recompute("")
            return
        if not self._picked:
            self.notify(
                "Pick at least one tag, or esc to leave the rows as they are.", severity="warning"
            )
            return
        self.dismiss(list(self._picked))

    def action_cancel(self) -> None:
        self.dismiss(None)
