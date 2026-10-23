"""FormScreen — the shared bar-cycle form core.

One input bar cycles through a field sequence; a suggestion list under it
offers picks; a summary table mirrors progress; `ctrl+s` (or enter when no
field ahead can change) submits via `run_write`. Subclasses supply the field
sequence, labels/hints, suggestion pools, commit handlers, and the submit request:
BarFormScreen (static Field list), EditFormScreen (dynamic sequence,
locked fields, edit mode), NewReconciliationScreen (dynamic sequence),
SetupScreen (first-time setup: the engine address and key, then a profile),
SplitScreen (a part's fields, or the title's one field, under the table of
parts, its own layout and send).
"""

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Footer, Input, Label, Static

from expense.tui.screens._base import EngineWriteMixin
from expense.tui.widgets.header import Breadcrumb

#: What `⏎` on an empty title says, on every form that edits one.
TITLE_REQUIRED = "Title is required."


def form_bindings(
    submit_desc: str, *, cancel_desc: str = "Cancel"
) -> list[Binding | tuple[str, str, str]]:
    """The shared bar-form keymap; only the esc and ctrl+s descriptions vary.

    The footer reads `esc Cancel  ^s Save  ⇥ Field` — `⇥ Field` is the form's
    one navigation slot. The setup screen, which has no screen under it to go
    back to, reads `esc Quit`:

    · `tab` moves to the next field and `shift+tab` to the previous, on every
      field, list open or not. FormScreen does not inherit Textual's Screen
      bindings (whose `tab`/`shift+tab` cycle focus), so the bar keeps focus and
      the footer reads in this list's order; Screen's hidden `ctrl+c` copy is
      declared again here so nothing is lost.
    · `↑` / `↓` walk the suggestion list when the field has a non-empty one,
      and move to the previous / next field when it has none.
    · `^↑` / `^↓` also move between fields. macOS claims `⌃↑` (Mission
      Control) and `⌃↓` (Application Windows) before the terminal sees them,
      so they are never advertised; they work wherever those system shortcuts
      are off.

    Every field move skips read-only fields and stops at either end. On a
    read-only field (only when every field is), the bar takes nothing (`FormBar`).
    Guarded by `test_form_navigation_keys_are_not_advertised`.
    """
    return [
        ("escape", "cancel", cancel_desc),
        ("ctrl+s", "submit", submit_desc),
        Binding("tab", "field(1)", "Field", key_display="⇥"),
        Binding("shift+tab", "field(-1)", "Prev field", show=False),
        Binding("up", "arrow(-1)", "Highlight up or prev field", show=False),
        Binding("down", "arrow(1)", "Highlight down or next field", show=False),
        Binding("ctrl+up", "field(-1)", "Prev field", show=False),
        Binding("ctrl+down", "field(1)", "Next field", show=False),
        Binding("ctrl+c,super+c", "screen.copy_text", "Copy selected text", show=False),
    ]


class FormBar(Input):
    """The bar forms' one input bar. While the field under it is read-only
    (`read_only()`, asked at each key), nothing typed, pasted or deleted
    changes the bar, and `⏎` posts `Passed` in place of `Submitted`: no
    field's commit runs, so nothing lands on a read-only line, and the form
    moves on as from any line (`FormScreen.on_form_bar_passed`)."""

    class Passed(Message):
        """`⏎` on a read-only field."""

    def __init__(self, *, read_only, **kwargs) -> None:
        super().__init__(**kwargs)
        self._read_only = read_only

    def replace(self, text: str, start: int, end: int) -> None:
        # every edit of the bar's text (typing, paste, delete, cut) goes through here
        if not self._read_only():
            super().replace(text, start, end)

    async def action_submit(self) -> None:
        if self._read_only():
            self.post_message(self.Passed())
        else:
            await super().action_submit()


class FormScreen(EngineWriteMixin, Screen, inherit_bindings=False):
    BINDINGS = form_bindings("Create")
    RESOURCE = ""  # engine collection for the default POST submit

    def __init__(self) -> None:
        super().__init__()
        self._current = 0
        self._values: dict = {}
        self._display: dict = {}
        self._suggestions: list = []
        self._suggest_idx = 0
        self._submitting = False
        self._locked: set[str] = set()

    # ---- subclass hooks ----------------------------------------------------
    def _sequence(self) -> list[str]:
        """The ordered field keys — may vary with form state."""
        raise NotImplementedError

    def _label(self, key: str) -> str:
        """The bar label for a field key (e.g. `AMOUNT`)."""
        raise NotImplementedError

    def _hint_for(self, key: str) -> str:
        return ""

    def _hint_line(self, key: str) -> Text:
        """The hint line under the bar: `_hint_for`'s words, dimmed."""
        return Text(self._hint_for(key), style="dim")

    def _required(self) -> tuple[str, ...]:
        return ()

    def _suggests(self, key: str) -> bool:
        """Whether this field drives the suggestion list."""
        return False

    def _bar_value(self, key: str) -> str:
        """The bar prefill when landing on a field."""
        return str(self._values.get(key, "") or "")

    def _recompute(self, text: str) -> None:
        """Rebuild `_suggestions` for the current field from the bar text."""
        self._suggestions = []
        self._suggest_idx = 0

    def _after_mount(self) -> None:
        """Post-mount hook — e.g. kick off entity loading."""

    def _heading(self) -> RenderableType | None:
        """A line over the bar naming what the form edits; None (the default)
        draws none."""
        return None

    def _payload(self) -> dict:
        raise NotImplementedError

    def _submit_request(self) -> tuple[str, str, dict, str] | None:
        """(method, path, payload, busy-hint) for the write; None aborts."""
        return ("POST", f"/{self.RESOURCE}", self._payload(), "Creating…")

    def _done(self) -> None:
        """Success callback (UI thread) — toast + dismiss."""
        raise NotImplementedError

    # ---- layout ------------------------------------------------------------
    @property
    def _key(self) -> str:
        seq = self._sequence()
        return seq[min(self._current, len(seq) - 1)]

    def compose(self) -> ComposeResult:
        yield Breadcrumb(self.crumb, id="crumb")
        heading = self._heading()
        if heading is not None:
            yield Static(heading, id="form-head")
        bar = FormBar(id="bar", read_only=lambda: self._key in self._locked)
        yield Horizontal(Label("", id="field"), bar, id="inputbar")
        yield Static("", id="hint")
        yield Static("", id="suggest")
        yield Static("", id="summary")
        yield Footer()

    def on_mount(self) -> None:
        self._current = self._first_editable()
        self._refresh_bar()
        self._refresh_view()
        self.query_one("#bar", Input).focus()
        self._after_mount()

    # ---- bar / nav -----------------------------------------------------------
    def _first_editable(self) -> int:
        for i, key in enumerate(self._sequence()):
            if key not in self._locked:
                return i
        return 0

    def _step(self, delta: int) -> int:
        """The next editable field index in `delta`'s direction, skipping locks."""
        seq = self._sequence()
        step = 1 if delta > 0 else -1
        j = self._current
        while 0 <= j + step < len(seq):
            j += step
            if seq[j] not in self._locked:
                return j
        return self._current  # no editable field that way

    def _refresh_bar(self) -> None:
        key = self._key
        self.query_one("#field", Label).update(self._label(key))
        bar = self.query_one("#bar", Input)
        bar.value = self._bar_value(key)
        self._recompute(bar.value)

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._suggests(self._key):
            self._recompute(event.value)
            self._refresh_view()

    def action_suggest(self, delta: int) -> None:
        if self._suggestions:
            self._suggest_idx = max(0, min(len(self._suggestions) - 1, self._suggest_idx + delta))
            self._refresh_view()

    def action_arrow(self, delta: int) -> None:
        """Plain `↑`/`↓`: walk a non-empty suggestion list, else move fields."""
        if self._suggestions:
            self.action_suggest(delta)
        else:
            self.action_field(delta)

    def action_field(self, delta: int) -> None:
        self._current = self._step(delta)
        self._refresh_bar()
        self._refresh_view()

    def on_form_bar_passed(self, event: FormBar.Passed) -> None:
        """`⏎` on a read-only field keeps nothing and moves on."""
        event.stop()
        self._advance()

    def _advance(self) -> None:
        """`⏎`'s move: on to the next field that can change, or, when no field
        ahead can (the last field, or only read-only ones after it), the save
        `ctrl+s` runs."""
        following = self._step(1)
        if following == self._current:
            self.action_submit()
        else:
            self._current = following
            self._refresh_bar()
            self._refresh_view()

    # ---- render --------------------------------------------------------------
    def _refresh_view(self) -> None:
        self.query_one("#hint", Static).update(self._hint_line(self._key))
        self.query_one("#suggest", Static).update(self._suggest_renderable())
        self.query_one("#summary", Static).update(self._summary_renderable())

    def _suggest_renderable(self) -> RenderableType:
        if not self._suggests(self._key):
            return Text("")
        if not self._suggestions:
            return Text("  no matches", style="dim")
        rows = []
        for i, ent in enumerate(self._suggestions):
            extra = f"  {ent[2]}" if len(ent) > 2 else ""
            line = Text(f"  {ent[1]}{extra}")
            if i == self._suggest_idx:
                line.stylize("reverse")
            rows.append(line)
        return Group(*rows)

    def _summary_renderable(self) -> RenderableType:
        seq = self._sequence()
        required = self._required()
        current_key = self._key
        t = Table(box=None, pad_edge=False, show_header=False, expand=False)
        t.add_column("k")
        t.add_column("v")
        for key in seq:
            shown = self._display.get(key)
            locked = key in self._locked
            if locked:
                value = Text(f"{shown or '—'}  read-only", style="dim")
            elif shown:
                value = Text(str(shown))
            else:
                tag = "  *" if key in required else "  (optional)"
                value = Text("—" + tag, style="dim")
            label = Text(self._label(key).lower(), style="dim" if locked else "")
            if key == current_key and not locked:
                label.stylize("bold")
            t.add_row(label, value)
        return t

    # ---- submit ----------------------------------------------------------------
    def action_cancel(self) -> None:
        self.dismiss()

    def _title_given(self, text: str) -> bool:
        """False, with `Title is required.` as an error toast, when the title
        typed (already stripped) is empty: a title is never kept empty."""
        if not text:
            self.notify(TITLE_REQUIRED, severity="error")
            return False
        return True

    def _required_met(self) -> bool:
        """True when every required field has a value; otherwise notes the first
        missing one. Every form's save goes through this one check."""
        for key in self._required():
            if key not in self._values:
                self.notify(f"{self._label(key).title()} is required.", severity="error")
                return False
        return True

    def action_submit(self) -> None:
        if self._submitting:
            return
        if not self._required_met():
            return
        request = self._submit_request()
        if request is None:
            return
        method, path, payload, busy = request
        self._submitting = True
        self.query_one("#hint", Static).update(Text(busy, style="dim"))
        self.run_write(
            method, path, json_body=payload, on_success=self._done, on_error=self._failed
        )

    def _failed(self, message: str) -> None:
        self._submitting = False
        self.notify(message, title="Failed", severity="error")
        self._refresh_view()
