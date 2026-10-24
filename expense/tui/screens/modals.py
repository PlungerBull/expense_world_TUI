"""Reusable modal screens."""

from typing import TypeVar

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Static

from expense.quickadd.money import parse_amount


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


_T = TypeVar("_T")


class PromptBox(ModalScreen[_T]):
    """One line typed in a box: the title, an optional dim message, the input
    and `[enter] save    [esc] cancel`. `esc` cancels (None). Each subclass
    says what `enter` dismisses with, and so its result type."""

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

    def action_cancel(self) -> None:
        self.dismiss(None)


class PromptModal(PromptBox[str | None]):
    """Single-line text prompt. `enter` submits the value, `esc` cancels (None).
    `password=True` masks input (for the token). Dismisses with the string,
    trimmed — or exactly as typed with `verbatim=True`, for a value whose
    whitespace is the engine's to judge."""

    def __init__(
        self,
        title: str,
        message: str = "",
        *,
        value: str = "",
        password: bool = False,
        verbatim: bool = False,
    ) -> None:
        super().__init__(title, message, value=value, password=password)
        self._verbatim = verbatim

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value if self._verbatim else event.value.strip())


class AmountPromptModal(PromptBox[int | None]):
    """A signed amount typed in a box. `enter` dismisses with its cents, read by
    the shared money parser exactly as typed — the sign is the one typed, never
    added or flipped. Text the parser cannot read keeps the box open with what
    was typed and notes `unreadable`: a well-formedness check only."""

    def __init__(self, title: str, message: str = "", *, unreadable: str) -> None:
        super().__init__(title, message)
        self._unreadable = unreadable

    def on_input_submitted(self, event: Input.Submitted) -> None:
        cents = parse_amount(event.value)
        if cents is None:
            self.notify(self._unreadable, severity="error")
            return
        self.dismiss(cents)


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
