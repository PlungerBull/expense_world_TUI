"""The bulk pick — what `c`, `b` and `h` on the ledger open.

Drawn in docs/mockups/expense-world-wording-picks.html, Question 6. A full pushed
screen, not a pop-up: it carries rows. The crumb adds `Category for 3 rows`
(`Account for …`, `Hashtags for …`) to the ledger's. On top, `the 3 rows it
changes` and those rows in the ledger's own columns, at most five and then
`+ N more` (the ledger draws them: `changed_rows` in transactions.py). Under
them one bar, CATEGORY, ACCOUNT or HASHTAGS, its hint, and the shared
suggestion list and its name filter ([picker.py](../widgets/picker.py):
`suggestion_list`, `matching`), as the Edit form's entity lines look.

Typing narrows the list (any part of a name, case- and accent-blind) and
highlights its first match, `↑↓` move the highlight, `esc` leaves with nothing
picked (None).

On CATEGORY and ACCOUNT, `⏎` dismisses with the highlighted id; with nothing
typed that is the first name, so two keys pick. A bar that matches nothing
says so and stays.

On HASHTAGS, `⏎` on a typed name adds the highlighted tag to the `picked` line
under the list and empties the bar; `⏎` on an empty bar dismisses with the
picked ids; `⌫` on an empty bar drops the last pick. Picks are ids, never
re-read text, so a tag whose name has a space in it is one pick like any
other. An empty apply is refused rather than taken as "clear every tag": the
Edit form does that, one row at a time.

The screen writes nothing: the ledger sends its `PUT`s with what it dismisses
with.
"""

from rich.console import RenderableType
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Footer, Input, Label, Static

from expense.tui.widgets.header import Breadcrumb
from expense.tui.widgets.picker import matching, suggestion_list
from expense.tui.widgets.refusal import toast

#: The bar's label for each bulk key's kind.
LABELS = {"category": "CATEGORY", "account": "ACCOUNT", "hashtags": "HASHTAGS"}


def rows_word(count: int) -> str:
    """`1 row`, `3 rows`."""
    return f"{count} {'row' if count == 1 else 'rows'}"


def pick_hint(kind: str, count: int) -> str:
    """The hint under the bar, as the mockup words it."""
    rows = rows_word(count)
    if kind == "hashtags":
        return (
            f"replaces every tag on the {rows} · enter adds · empty enter applies"
            " · ⌫ drops the last"
        )
    return f"type to narrow · ↑↓ highlight · enter picks it for the {rows} · esc cancels"


class BulkPickScreen(Screen[object]):
    """Pick a category or an account, or several hashtags, for `count` rows.

    `options` are `(id, name)` pairs in the order to offer them; `rows` is
    what the screen shows over the bar, under `the N rows it changes`.
    Dismisses with the picked id, the list of picked ids (hashtags) or None.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", tooltip="Leave with nothing changed"),
        Binding("up", "move(-1)", "Highlight up", show=False),
        Binding("down", "move(1)", "Highlight down", show=False),
    ]

    def __init__(
        self,
        kind: str,
        count: int,
        options: list[tuple[str, str]],
        *,
        rows: RenderableType,
        crumb: tuple[str, ...] = (),
    ) -> None:
        super().__init__()
        self._kind = kind
        self._count = count
        self._options = list(options)
        self._names = dict(options)
        self._rows = rows
        self._multi = kind == "hashtags"
        self._pool: list[tuple] = list(options)
        self._idx = 0
        self._picked: list[str] = []
        self.crumb = (*crumb, f"{kind.capitalize()} for {rows_word(count)}")

    # ---- widgets ---------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Breadcrumb(self.crumb, id="crumb")
        head = Text(f"the {rows_word(self._count)} it changes", style="dim")
        yield Static(head, id="pick-caption")
        yield Static(self._rows, id="pick-rows")
        yield Horizontal(Label(LABELS[self._kind], id="field"), Input(id="bar"), id="inputbar")
        yield Static(Text(pick_hint(self._kind, self._count), style="dim"), id="hint")
        yield Static("", id="suggest")
        if self._multi:
            yield Static("", id="summary")
        yield Footer()

    def on_mount(self) -> None:
        self._recompute("")
        self._refresh_picked()
        self.query_one("#bar", Input).focus()

    # ---- the list --------------------------------------------------------
    def _recompute(self, text: str) -> None:
        self._pool = matching(self._options, text.strip(), chosen=set(self._picked))
        self._idx = 0
        self._refresh_suggest()

    def _refresh_suggest(self) -> None:
        labels = [name for _id, name, *_ in self._pool]
        self.query_one("#suggest", Static).update(suggestion_list(labels, self._idx))

    def _refresh_picked(self) -> None:
        if not self._multi:
            return
        line = Text("picked    ")
        names = " ".join("#" + self._names.get(i, i) for i in self._picked)
        line.append(names or "(none yet)", style="" if names else "dim")
        self.query_one("#summary", Static).update(line)

    # ---- keys ------------------------------------------------------------
    def on_input_changed(self, event: Input.Changed) -> None:
        self._recompute(event.value)

    def action_move(self, delta: int) -> None:
        if self._pool:
            self._idx = max(0, min(len(self._pool) - 1, self._idx + delta))
            self._refresh_suggest()

    def on_key(self, event: Key) -> None:
        # `⌫` on an empty bar drops the last pick. The Input's own binding sees
        # the key first and, with nothing to delete, lets it bubble here.
        if self._multi and event.key == "backspace" and self._picked:
            if not self.query_one("#bar", Input).value:
                self._picked.pop()
                self._refresh_picked()
                self._recompute("")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        needle = event.value.strip()
        if not self._multi:
            if not self._pool:
                toast(self, f"Nothing matches “{needle}”.", severity="error")
                return
            self.dismiss(self._pool[self._idx][0])
            return
        if needle:
            if not self._pool:
                toast(self, f"No hashtag matches “{needle}”.", severity="error")
                return
            self._picked.append(self._pool[self._idx][0])
            self._refresh_picked()
            self.query_one("#bar", Input).value = ""  # Changed → _recompute("")
            return
        if not self._picked:
            self.notify(
                "Pick at least one tag, or esc to leave the rows as they are.", severity="warning"
            )
            return
        self.dismiss(list(self._picked))

    def action_cancel(self) -> None:
        self.dismiss(None)
