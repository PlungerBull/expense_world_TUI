"""Reusable modal screens."""

from collections.abc import Callable, Sequence
from typing import TypeVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Footer, Input, Static

from expense.quickadd.money import parse_amount
from expense.tui.widgets.picker import suggestion_list
from expense.tui.widgets.refusal import toast


class UnderHead:
    """A box drawn under the screen's head, the head still in sight above it, as the
    Statements pane 6 draws `c`'s boxes (docs/mockups/expense-world-statements-
    screens.html). The card covers the screen from its top line to the footer, in the
    terminal's own background, so nothing of the list shows beside or below it. `under`
    says the line the card starts on, asked each time the box is placed (when it
    opens, once it is laid out, on a resize), so the box follows a head that grew. The
    box is never cut: where the space under the head is too short it rises over the
    head's last lines. With `under` None the box stays where every modal is, centred
    under the scrim."""

    _under: Callable[[], int] | None = None

    def _place_under_head(self) -> None:
        if self._under is None:
            return
        self.add_class("under-head")  # type: ignore[attr-defined]
        # the box follows every layout of the screen under it (its head grew, a note
        # above its list came or went); the signal drops the box once it is gone
        below = self.app.screen_stack[-2]  # type: ignore[attr-defined]
        below.screen_layout_refresh_signal.subscribe(self, lambda _screen: self._place())
        self._place()
        self.call_after_refresh(self._place)  # type: ignore[attr-defined]

    def _place(self) -> None:
        if self._under is None:
            return
        screen: ModalScreen = self  # type: ignore[assignment]
        try:
            card = screen.query_one("#modal")
        except Exception:  # not composed yet, or already gone
            return
        top = self._under()
        if card.size.width:  # laid out: the card's own height, not what is left it
            need = sum(
                child.outer_size.height + child.styles.margin.height
                for child in card.children
                if child.display
            )
            top = min(top, screen.size.height - 1 - need)
        card.styles.margin = (max(0, top), 0, 0, 0)

    def _lead(self) -> list[Widget]:
        """What opens the card: the blank line, then the rule. Nothing for a centred
        box."""
        return [Widget(classes="under-rule under-first")] if self._under is not None else []

    def _tail(self) -> list[Widget]:
        """What closes the card: the rule under the blank line. Nothing for a centred
        box."""
        return [Widget(classes="under-rule under-last")] if self._under is not None else []

    def on_resize(self, _event) -> None:
        self._place()


class ConfirmModal(UnderHead, ModalScreen[bool]):
    """Yes/no confirmation. Only `y` confirms; `enter`/`n`/`esc` cancel — enter is
    the safe default so a reflexive keypress can never apply a write. Dismisses
    with the boolean result (use `push_screen(modal, callback)` to act on it)."""

    BINDINGS = [
        ("y", "confirm", "Yes"),
        ("n,escape,enter", "cancel", "No"),
    ]

    def __init__(self, title: str, message: str, *, under: Callable[[], int] | None = None) -> None:
        """`under`, when given, draws the question under the screen's head instead
        of centred: see `UnderHead`."""
        super().__init__()
        self._title = title
        self._message = message
        self._under = under

    def on_mount(self) -> None:
        self._place_under_head()

    def compose(self) -> ComposeResult:
        yield Vertical(
            *self._lead(),
            Static(Text(self._title), classes="modal-title"),
            Static(Text(self._message)),
            Static(Text("[y] confirm    [enter / n / esc] cancel", style="dim")),
            *self._tail(),
            id="modal",
        )
        yield Footer()

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class PickModal(ModalScreen[str | None]):
    """One of a few choices, picked from a list: the title, the line naming what
    the pick acts on, the choices in the order given (the shared
    `suggestion_list`, the highlight on the first), then `[enter] <verb>    [esc]
    cancel`. `↑↓` move the highlight, `⏎` dismisses with the highlighted choice,
    `esc` with None. It writes nothing: the caller acts on what it dismisses
    with. Manage ▸ Accounts' `c` picks the currency to add through it, and `x`
    the currency to remove."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "pick", "Pick", show=False),
        Binding("up", "move(-1)", "Highlight up", show=False),
        Binding("down", "move(1)", "Highlight down", show=False),
    ]

    def __init__(self, title: str, message: str, choices: Sequence[str], *, verb: str) -> None:
        super().__init__()
        self._title = title
        self._message = message
        self._choices = list(choices)
        self._verb = verb
        self._idx = 0

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(Text(self._title), classes="modal-title"),
            Static(Text(self._message)),
            Static(self._list(), id="pick-choices"),
            Static(Text(f"[enter] {self._verb}    [esc] cancel", style="dim")),
            id="modal",
        )
        yield Footer()

    def _list(self):
        return suggestion_list(self._choices, self._idx)

    def action_move(self, delta: int) -> None:
        if self._choices:
            self._idx = max(0, min(self._idx + delta, len(self._choices) - 1))
            self.query_one("#pick-choices", Static).update(self._list())

    def action_pick(self) -> None:
        if self._choices:
            self.dismiss(self._choices[self._idx])

    def action_cancel(self) -> None:
        self.dismiss(None)


_T = TypeVar("_T")


class _TouchedInput(Input):
    """The box's input, telling `touched` of every key before it does what it does."""

    def __init__(self, *args, touched: Callable[[], None] | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._touched = touched

    def on_key(self, _event) -> None:
        if self._touched is not None:
            self._touched()


class PromptBox(UnderHead, ModalScreen[_T]):
    """One line typed in a box: the title, an optional dim message, the input
    and `[enter] save    [esc] cancel`. `esc` cancels (None). Each subclass
    says what `enter` dismisses with, and so its result type."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(
        self,
        title: str,
        message: str = "",
        *,
        value: str = "",
        password: bool = False,
        under: Callable[[], int] | None = None,
        touched: Callable[[], None] | None = None,
    ) -> None:
        """`under`: see `UnderHead`. `touched` is called on every key typed in the box."""
        super().__init__()
        self._title = title
        self._touched = touched
        self._message = message
        self._value = value
        self._password = password
        self._under = under

    def compose(self) -> ComposeResult:
        rows = [*self._lead(), Static(Text(self._title), classes="modal-title")]
        if self._message:
            rows.append(Static(Text(self._message, style="dim")))
        rows.append(
            _TouchedInput(
                value=self._value, password=self._password, id="prompt", touched=self._touched
            )
        )
        rows.append(Static(Text("[enter] save    [esc] cancel", style="dim")))
        yield Vertical(*rows, *self._tail(), id="modal")
        yield Footer()

    def on_mount(self) -> None:
        self._place_under_head()
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

    def __init__(
        self,
        title: str,
        message: str = "",
        *,
        unreadable: str,
        under: Callable[[], int] | None = None,
        touched: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(title, message, under=under, touched=touched)
        self._unreadable = unreadable

    def on_input_submitted(self, event: Input.Submitted) -> None:
        cents = parse_amount(event.value)
        if cents is None:
            toast(self, self._unreadable, severity="error")
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
