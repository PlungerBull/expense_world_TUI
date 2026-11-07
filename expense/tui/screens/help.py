"""The `?` overlay — one curated inventory of what the current screen can do.

Why this exists rather than Textual's own `action_show_help_panel`: that panel
lists every *active* binding, which means everything we never authored (Scroll
Left/Right, Page Left/Right, Focus Next/Previous, Copy selected text), renders
`show=False` aliases as rows with a blank description, groups nothing, and docks
right — squeezing the content to a third of the width.

The inventory is **derived, never hand-listed**. It walks the screen's — and the
focused widget's — MRO and keeps only the BINDINGS declared by classes in this
package, so a binding added or removed anywhere shows up here with no edit. The
two hand-written blocks are the ones no walk can produce: `CONVENTIONS` (true
across screens, so no single screen declares them) and `EVERYWHERE` (Textual's
own keys). tests/unit/test_tui_help.py is the guard — it fails if a binding we
declare has no description for this card to show.
"""

from dataclasses import dataclass, field

from rich.console import Console, ConsoleOptions
from rich.console import Group as RichGroup
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.events import Resize
from textual.keys import format_key, key_to_character
from textual.screen import ModalScreen
from textual.widgets import Static

from expense.tui.theme import ACCENT
from expense.tui.widgets.footer import FittingFooter
from expense.tui.widgets.refusal import under_itself

#: Only BINDINGS declared by classes under this package reach the card. Textual's
#: own widget keys are not ours to document — see the module docstring.
PACKAGE = "expense.tui"

#: A `show=False` binding whose action is the inverse of a shown one needs no row
#: of its own: it renders as a dim parenthetical on its partner's row
#: (`↓   Down   (↑ up)`). Textual's panel prints it as a row with a blank
#: description instead — the `↑ k` row in the §1.2 capture. Maps folded action →
#: the action whose row it joins.
FOLD_INTO = {"move(-1)": "move(1)"}

#: Cross-screen rules from docs/tui.md §4. No screen declares them, so no
#: walk can find them — and they are the one thing a generated key list can never
#: say. Rendered inline (key immediately before the text), not in a key column.
CONVENTIONS = (
    ("r", "refreshes, everywhere"),
    ("y", "alone confirms"),
    ("⏎", "never changes data, except on a currency pick"),
)

#: Textual's own keys — all that is app-wide.
#: Why: docs/decisions.md "The command palette is removed".
EVERYWHERE = (("^q", "Quit"), ("?", "This help"))

#: `?` is declared on every screen root (Textual does not merge BINDINGS from a
#: plain mixin, so `HelpBindingMixin.BINDINGS` has to be splatted in), which means
#: the walk finds it as a screen binding. It belongs in EVERYWHERE, not in the
#: screen's own block — drop it there rather than print it twice.
EXCLUDED_ACTIONS = frozenset({"help"})

#: Widget bindings that only do something when the *screen* handles the message
#: they post. `CursorList`'s `enter` posts `Selected`; on the Manage lists no
#: screen handles it, because the keymap contract makes `enter` a literal no-op
#: there (docs/tui.md §4). Advertising `⏎ Open` on those screens would be
#: the card lying — so the row is dropped when the handler is absent.
NEEDS_SCREEN_HANDLER = {
    "select": ("on_cursor_list_selected",),
    # `CursorList` posts its `Toggled`, a statement's `CheckList` its own
    "toggle": ("on_cursor_list_toggled", "on_check_list_toggled"),
    "more": ("on_cursor_list_more_requested",),
}

#: A widget or a screen may name, in a `CARD_FOLLOWS_CHECK` frozenset, the
#: actions whose card row follows its `check_action`: listed only while it
#: allows them, as the footer does. For a key that is off in some states (the
#: statements panel's `⏎`: `Edit` in the "no statement" list, `Open` on the
#: statements; a statement's `f`, only while a complete's flagged lines
#: are left); every other row of the card lists what the classes declare.
CARD_FOLLOWS_CHECK = "CARD_FOLLOWS_CHECK"

#: Card geometry. `#modal` is 72 wide with `padding: 1 2` and a border, leaving 66
#: interior columns.
LEFT_WIDTH = 34
RIGHT_WIDTH = 32


@dataclass(frozen=True)
class KeyRow:
    """One line of the card: the keys, what they do, and an optional fold."""

    keys: str
    description: str
    note: str = ""


@dataclass(frozen=True)
class HelpGroup:
    """A titled block. `inline` renders the key against the text rather than in
    its own column — used by the conventions block, whose entries read as
    sentences (`r refreshes, everywhere`) instead of key/description pairs."""

    title: str
    rows: tuple[KeyRow, ...] = field(default_factory=tuple)
    inline: bool = False


# ---------------------------------------------------------------------------
# deriving the inventory
# ---------------------------------------------------------------------------


def _is_typed_character(key: str) -> bool:
    """True for keys the user produces by typing a visible character.

    Drives display order — `j / ↓` and `. / pgdn` read better than the reverse,
    because the letter is what you actually press. `escape` is excluded here on
    purpose: it maps to \\x1b, a character but not a visible one.
    """
    char = key_to_character(key)
    return bool(char) and char.isprintable() and not char.isspace()


def _display(key: str) -> str:
    """Textual's own key formatting, with `ctrl+x` shortened to `^x`."""
    return format_key(key).replace("ctrl+", "^")


def declared_bindings(klass: type) -> list[Binding]:
    """Every Binding declared by `klass` or a base of it **in this package**.

    Walks the MRO rather than reading `_bindings`, because the merged runtime
    table cannot say which class declared what — and that distinction is the
    whole filter: it is how Textual's `home`/`end`/`tab` bindings stay out
    without a suppression list that would rot.

    Bindings arrive already split per key (`"n,escape,enter"` → three Bindings), which is
    what `_grouped_rows` re-joins into one row.
    """
    seen: set[tuple[str, str]] = set()
    found: list[Binding] = []
    for base in klass.__mro__:
        if not base.__module__.startswith(PACKAGE):
            continue
        for item in base.__dict__.get("BINDINGS", ()):
            for binding in Binding.make_bindings([item]):
                ident = (binding.key, binding.action)
                if ident in seen:
                    continue
                seen.add(ident)
                found.append(binding)
    return found


def _tail_rank(action: str) -> int:
    """Refresh, then Back, sort to the end of a screen's own block — they are
    the two every screen has, so leading with them would bury what is specific
    to this one."""
    if action == "reload":
        return 1
    if action in ("app.pop_screen", "back"):
        return 2
    return 0


def key_rows(bindings: list[Binding], drop: frozenset[str] = frozenset()) -> list[KeyRow]:
    """Bindings → card rows: keys re-joined, inverses folded, tail keys last."""
    order: list[str] = []
    keys_by_action: dict[str, list[str]] = {}
    described: dict[str, str] = {}
    for binding in bindings:
        if binding.action not in keys_by_action:
            keys_by_action[binding.action] = []
            order.append(binding.action)
        keys_by_action[binding.action].append(binding.key)
        # `tooltip` wins over `description`: the description is the FOOTER label
        # and is terse because footer width is scarce ("New", "Prev"), while this
        # card has room to say what the key actually does ("Next page",
        # "Archive / unarchive"). Setting a tooltip never changes the footer, so
        # the two stay independently tunable from one declaration.
        text = binding.tooltip or binding.description
        if text:
            described[binding.action] = text

    def joined(action: str) -> str:
        keys = keys_by_action[action]
        typed = [k for k in keys if _is_typed_character(k)]
        rest = [k for k in keys if k not in typed]
        return " / ".join(_display(k) for k in (*typed, *rest))

    rows: list[KeyRow] = []
    for action in sorted(order, key=_tail_rank):
        if action in EXCLUDED_ACTIONS or action in drop:
            continue
        folded_into = FOLD_INTO.get(action)
        if folded_into and folded_into in keys_by_action:
            continue  # rendered as a parenthetical on its partner's row
        note = ""
        for other, target in FOLD_INTO.items():
            if target == action and other in keys_by_action:
                note = f"({joined(other)} {described.get(other, '').lower()})".replace(" )", ")")
        rows.append(KeyRow(joined(action), described.get(action, ""), note))
    return rows


def screen_inventory(screen) -> tuple[str, list[HelpGroup]]:
    """`(title, groups)` for the screen the user is looking at.

    Called on the screen *before* `HelpModal` is pushed — once the modal is up it
    owns the focus, and the focused widget is half the answer.
    """
    crumb = getattr(screen, "crumb", ()) or ()
    # Home builds its own header instead of a Breadcrumb, so it has no crumb —
    # fall back to the class name, which reads correctly for any future
    # crumbless screen too.
    name = crumb[-1] if crumb else type(screen).__name__.removesuffix("Screen")
    title = f"Keys — {name}"

    off = frozenset(
        action
        for action in getattr(screen, CARD_FOLLOWS_CHECK, ())
        if screen.check_action(action, ()) is False
    )
    groups = [HelpGroup("This screen", tuple(key_rows(declared_bindings(type(screen)), drop=off)))]

    focused = getattr(screen, "focused", None)
    if focused is not None and focused is not screen:
        inert = frozenset(
            action
            for action, handlers in NEEDS_SCREEN_HANDLER.items()
            if not any(hasattr(screen, handler) for handler in handlers)
        ) | frozenset(
            action
            for action in getattr(focused, CARD_FOLLOWS_CHECK, ())
            if focused.check_action(action, ()) is False
        )
        widget_rows = key_rows(declared_bindings(type(focused)), drop=inert)
        if widget_rows:
            groups.append(HelpGroup("Moving around", tuple(widget_rows)))

    groups.append(
        HelpGroup(
            "Always true",
            tuple(KeyRow(key, text) for key, text in CONVENTIONS),
            inline=True,
        )
    )
    groups.append(HelpGroup("Everywhere", tuple(KeyRow(key, text) for key, text in EVERYWHERE)))
    return title, groups


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------


def _render_group(group: HelpGroup, width: int, accent: str, pad_to: int) -> RichGroup:
    """One titled block, padded to `pad_to` rows so the block beneath it starts
    on the same line as its opposite number in the other column."""
    table = Table(box=None, show_header=False, pad_edge=False, padding=(0, 0), width=width)
    if group.inline:
        table.add_column("line", width=width)
        for row in group.rows:
            head = Text("  ")
            head.append(row.keys, style=accent)
            head.append(" ")
            # A long rule wraps under its own words, never under its key.
            table.add_row(under_itself(head, Text(row.description)))
    else:
        # Sized to the widest key string rather than a constant: `. / pgdn` is
        # three cells wider than `esc`, and a fixed column either clipped the
        # page keys or wasted a third of the narrow column on the screen block.
        key_width = max((len(row.keys) for row in group.rows), default=0) + 4
        table.add_column("keys", no_wrap=True, width=key_width)
        table.add_column("what", width=width - key_width)
        for row in group.rows:
            keys = Text("  ")
            keys.append(row.keys, style=accent)
            what = Text(row.description)
            if row.note:
                what.append(f"   {row.note}", style="dim")
            table.add_row(keys, what)
    for _ in range(pad_to - len(group.rows)):
        table.add_row(*([Text("")] * len(table.columns)))
    return RichGroup(Text(f" {group.title}", style=f"bold {accent}"), table, Text(""))


def render_card(groups: list[HelpGroup], accent: str) -> Table:
    """The two-column card. Left stack gets the screen's own keys and the
    conventions; right stack the focused widget's and the app-wide keys — the
    pairing approved as variant C."""
    left = [g for g in groups if g.title in ("This screen", "Always true")]
    right = [g for g in groups if g.title in ("Moving around", "Everywhere")]

    # Blocks are paired by position, so block 2 of each column starts on the same
    # line however many keys block 1 happened to have.
    heights = [
        max(len(stack[i].rows) if i < len(stack) else 0 for stack in (left, right))
        for i in range(max(len(left), len(right)))
    ]

    def stack(groups_: list[HelpGroup], width: int) -> RichGroup:
        return RichGroup(
            *[_render_group(g, width, accent, heights[i]) for i, g in enumerate(groups_)]
        )

    outer = Table(box=None, show_header=False, pad_edge=False, padding=(0, 0))
    outer.add_column("left", width=LEFT_WIDTH)
    outer.add_column("right", width=RIGHT_WIDTH)
    outer.add_row(stack(left, LEFT_WIDTH), stack(right, RIGHT_WIDTH))
    return outer


#: Rows the card's chrome takes while it fits: the two rules, the padding above and
#: below, the title with its blank line, and the closing hint.
FIT_CHROME = 7

#: A card taller than the room it has scrolls between its two rules; the rows inside
#: them are all window (the title is its first lines). The rules take these rows.
SCROLL_CHROME = 2

#: Rows the screen's head takes (its line and rule), left showing above a scrolling card.
HEAD_ROWS = 2


def card_lines(renderable, width: int) -> list[Text]:
    """A Rich renderable as one `Text` per line, styles kept, so a window of the
    lines can be drawn with the card's own look."""
    console = Console(width=width)
    options: ConsoleOptions = console.options.update(width=width)
    lines = []
    for segments in console.render_lines(renderable, options, pad=False):
        line = Text()
        for segment in segments:
            line.append(segment.text, segment.style)
        lines.append(line)
    return lines


def scroll_window(lines: list[Text], offset: int, height: int) -> tuple[list[Text], int]:
    """`height` rows showing `lines` from `offset`: the lines that fit, with a dim
    `▲ N lines above · ↑ scrolls` first row while any are above and a dim
    `▼ N more lines · ↓ scrolls` last row while any are below; N counts the card
    lines hidden. Returns the rows and the offset kept inside the card (the last
    offset is the one that shows the end)."""
    total = len(lines)
    offset = max(0, min(offset, total - height + 1 if total > height else 0))
    up = offset > 0
    room = height - up
    down = offset + room < total
    shown = lines[offset : offset + room - down]
    rows: list[Text] = []
    if up:
        rows.append(Text(f" ▲ {_count(offset, 'line', 'lines')} above · ↑ scrolls", style="dim"))
    rows.extend(shown)
    if down:
        hidden = total - offset - len(shown)
        rows.append(
            Text(f" ▼ {_count(hidden, 'more line', 'more lines')} · ↓ scrolls", style="dim")
        )
    return rows, offset


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


class HelpModal(ModalScreen):
    """The `?` card. Dismissed by `?` as well as `esc` — the key that opens it
    is the key that closes it, so it works as a peek. A card taller than the screen
    above the footer scrolls on `↓` / `↑` (`scroll_window`)."""

    BINDINGS = [
        ("escape", "close", "Close"),
        ("question_mark", "close", "Close"),
        Binding("down", "scroll(1)", "Scroll down", show=False),
        Binding("up", "scroll(-1)", "Scroll up", show=False),
    ]

    def __init__(self, title: str, groups: list[HelpGroup]) -> None:
        super().__init__()
        self._title = title
        self._card = render_card(groups, ACCENT)
        self._lines = [
            Text(""),
            Text(title, style=f"bold {ACCENT}"),
            Text(""),
            *card_lines(self._card, LEFT_WIDTH + RIGHT_WIDTH),
        ]
        self._offset = 0

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(Text(self._title), classes="modal-title fit"),
            Static(self._card, classes="fit"),
            Static(Text("[?] or [esc] close", style="dim"), classes="fit"),
            Static("", id="help-scroll"),
            id="modal",
        )
        yield FittingFooter()

    def on_mount(self) -> None:
        self._layout()

    def on_resize(self, event: Resize) -> None:
        self._layout()

    @property
    def _room(self) -> int:
        """Rows between the screen's head and the footer."""
        return self.size.height - 1 - HEAD_ROWS

    def _layout(self) -> None:
        """A card that fits is drawn as its three parts; one that does not, as one
        window of lines the height of the room."""
        modal = self.query_one("#modal")
        scrolls = len(self._lines) - 3 + FIT_CHROME > self._room
        modal.set_class(scrolls, "scrolling")
        modal.styles.height = self._room if scrolls else "auto"
        self._draw()

    def _draw(self) -> None:
        modal = self.query_one("#modal")
        if not modal.has_class("scrolling"):
            self._offset = 0
            return
        rows, self._offset = scroll_window(self._lines, self._offset, self._room - SCROLL_CHROME)
        self.query_one("#help-scroll", Static).update(Text("\n").join(rows))

    def action_scroll(self, step: int) -> None:
        self._offset += step
        self._draw()  # kept inside the card by `scroll_window`

    def action_close(self) -> None:
        self.dismiss(None)


class HelpBindingMixin:
    """Adds `?` to a screen. Mixed into the three screen roots that are not
    forms or modals — `SectionScreen`, `HomeScreen`, `StatementScreen`.

    Deliberately not bound on the App: letters bubble up from lists, so an
    app-level `?` would fire from inside a ConfirmModal (the same reason there is
    no app-level `q` — see app.py). Deliberately not on `FormScreen` either: a
    focused `Input` swallows printable keys, so `?` there types a question mark,
    which is the wanted behaviour.
    """

    BINDINGS = [("question_mark", "help", "Keys")]

    def action_help(self) -> None:
        title, groups = screen_inventory(self)
        self.app.push_screen(HelpModal(title, groups))
