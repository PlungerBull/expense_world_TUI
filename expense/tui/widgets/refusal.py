"""What the engine said, as a screen shows it: its words as text, never as styling.

One copy for every screen that lays a refusal out line by line (`hanging`: the
bank import's preview and result, and the Edit form's parts), for words that
wrap under themselves after a head of the app's own (`under_itself`: the Edit
form's read-only lines and their sentences), for every toast whose words
the app did not write itself (`toast`), or that holds them, line by line,
inside the app's own styling (`as_markup`), and for the note of a refusal that
stopped a run of writes (`run_stopped`), which the LOG bar and the ledger's
bulk edit both show.
"""

from collections.abc import Iterable
from typing import Any

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text
from textual.app import App
from textual.widget import Widget

from expense.errors import format_error


def under_itself(head: Text, words: Text) -> RenderableType:
    """`head`, then `words` beside it, a long `words` wrapping under its own
    first word, never under `head`."""
    grid = Table.grid()
    grid.add_column(no_wrap=True)
    grid.add_column()
    grid.add_row(head, words)
    return grid


def hanging(line: Text) -> RenderableType:
    """A `! …` line wraps under its own words, not under the `!`; any other
    line is itself."""
    if not line.plain.startswith("! "):
        return line
    return under_itself(line[:2], line[2:])


def as_markup(lines: Iterable[tuple[str, str]]) -> str:
    """`lines` of words, each with the app's style it shows in (`"$error"`,
    `"dim"`, or `""` for none), as one string of content markup that reads
    back as exactly those lines, one under the other, each in its style: for a
    toast that styles words the app did not write, since a toast's message is
    a string Textual reads either as plain text or as markup.

    Each `[` in the words gets one backslash in front, which Textual takes away
    again as it reads, so `[like this]`, `[/]`, a lone `[` and a backslash
    before a `[` all show as sent; Textual's own `escape` leaves some of them
    to be read as styling. Textual's markup has no way to escape a backslash,
    so one at the end of the words would escape a tag written straight after
    them; none is: a line's style opens before its words and closes after the
    line break that ends them (a line break shows no colour), and the last
    line's style runs to the end of the note. So words ending in `\\` show
    whole too."""
    given = list(lines)
    marked = []
    for n, (words, style) in enumerate(given, 1):
        text = words.replace("[", "\\[")
        if style:
            text = f"[{style}]{text}"
        if n < len(given):
            text += "\n[/]" if style else "\n"
        marked.append(text)
    return "".join(marked)


def toast(host: App | Widget, message: str, **options: Any) -> None:
    """Show `message` in a toast as the words it holds, `[` and all.

    Textual reads a toast's message as content markup unless told otherwise, so
    a `[like this]` in the engine's words would vanish, read as a style. Every
    toast whose message is not a fixed sentence written in the app (the
    engine's words, a name, what was typed) goes through here; `options` are
    `notify`'s own (`title`, `severity`, `timeout`), and the title is always
    drawn as text. The guard in tests/unit/test_toast_words.py holds every
    other `notify` to a fixed sentence."""
    host.notify(message, markup=False, **options)


def run_stopped(host: App | Widget, err: Exception) -> None:
    """The one note for a refusal that stopped a run of writes
    (`errors.refuses_every_write`: `SETTINGS_MISSING`, or `LIMIT_REACHED` with
    `LINE_CODES_EXHAUSTED`), the same on every screen that runs several: titled
    `Failed`, the engine's words whole, then, after a blank line, the app's
    line saying what to do (`format_error`). The LOG bar's save and the
    ledger's bulk edit both say their stop here, once, on no row."""
    toast(host, format_error(err), title="Failed", severity="error")
