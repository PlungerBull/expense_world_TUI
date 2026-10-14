"""GrowingRead — the reads behind a list that grows. One copy, two lists.

The shape of a long list (docs/decisions.md "Long lists grow, they do not
page"): it opens with `GROW_STEP` rows,
`pgdn` appends the next `GROW_STEP` under them, and `↑`/`↓` scroll across
everything loaded. The engine hands out "the rows after this one", never
"row 41", so a list that only grows at its end is the shape that fits it.

Two lists grow: the ledger ([transactions.py](transactions.py), a whole
screen) and the "no batch" pane on Reconciliations (one panel inside a larger
screen). They share this reader, not a screen mixin — the pane is no screen of
its own. Each host keeps its own widgets and failure display; what lives here
is what must not drift between them:

- **Rows and count come together**: `read_first` raises
  when the count cannot be read, and the host fails its list rather than show
  rows beside a missing or guessed number. `pgdn` does not recount.
- **Any write starts the list over**: after `+`, `⏎`,
  `c`/`b`/`h` or `d` the host calls `reset()` and reads fresh, the first
  `GROW_STEP` with the cursor on row 1, like any app's list.
- **A `pgdn` read never lands on a list it was not for.** `reset()` drops the
  cursor, so a `pgdn` on the old list — still on screen while the fresh read
  runs — reads nothing, and a read already in flight is dropped on arrival by
  its generation number — otherwise a filtered ledger whose re-read ends one
  row further along repeats a row.
"""

from collections.abc import Callable
from typing import Any

from expense.errors import format_error
from expense.reads import items_of
from expense.tui.widgets.cursor_list import GROW_STEP

#: `(limit, after) -> the engine's body`, run on a worker thread.
FetchPage = Callable[[int, str | None], Any]


def read_first(fetch_page: FetchPage, count: Callable[[], int]) -> tuple[list, str | None, int]:
    """Worker thread: the first `GROW_STEP` rows, then the count.

    Returns (items, next_cursor, total). A count that cannot be read raises."""
    body = fetch_page(GROW_STEP, None)
    next_cursor = body.get("next_cursor") if isinstance(body, dict) else None
    return items_of(body), next_cursor, count()


class GrowingRead:
    """One growing list's cursor, count and `pgdn` read.

    `host` is the screen the list lives on (it runs the worker and shows a
    failed read); `on_more(items, more)` appends rows on the UI thread.
    """

    def __init__(self, host, *, on_more: Callable[[list, bool], None]) -> None:
        self._host = host
        self._on_more = on_more
        self._generation = 0
        self.next_cursor: str | None = None
        self.total: int | None = None
        self.busy = False  # a `pgdn` read is in flight

    @property
    def more(self) -> bool:
        """The engine said there are rows past the ones loaded."""
        return self.next_cursor is not None

    def took(self, next_cursor: str | None, total: int) -> None:
        """A fresh read landed: its cursor and count (UI thread)."""
        self.next_cursor = next_cursor
        self.total = total

    def reset(self) -> None:
        """A fresh read is coming: forget the cursor and orphan any `pgdn`
        read still in flight."""
        self._generation += 1
        self.next_cursor = None
        self.busy = False

    def grow(self, fetch_page: FetchPage) -> None:
        """`pgdn`: read the next `GROW_STEP` after the cursor. Nothing when
        there are no more, or a read is already in flight."""
        if self.busy or self.next_cursor is None:
            return
        self.busy = True
        after, generation = self.next_cursor, self._generation
        self._host.run_worker(
            lambda: self._read(fetch_page, after, generation), thread=True, group="grow"
        )

    def _read(self, fetch_page: FetchPage, after: str, generation: int) -> None:
        call = self._host.app.call_from_thread
        try:
            body = fetch_page(GROW_STEP, after)
        except Exception as exc:
            call(self._failed, format_error(exc), generation)
            return
        call(self._arrived, items_of(body), body.get("next_cursor"), generation)

    def _arrived(self, items: list, next_cursor: str | None, generation: int) -> None:
        if generation != self._generation:
            return  # a fresh read replaced the list this was for
        self.busy = False
        self.next_cursor = next_cursor
        self._on_more(items, next_cursor is not None)

    def _failed(self, message: str, generation: int) -> None:
        """The rows already loaded stay; only the next ones did not arrive."""
        if generation != self._generation:
            return
        self.busy = False
        self._host.notify(message, title="Failed", severity="error")
