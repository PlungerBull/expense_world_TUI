"""A footer that gives up its spacing, then its last keys, before it cuts a key."""

from rich.cells import cell_len
from textual.app import ComposeResult
from textual.widgets import Footer


class FittingFooter(Footer):
    """The footer, drawn in Textual's compact style (less whitespace between its keys)
    when its keys, spaced as usual, are wider than the screen. Keys still too wide then
    leave the footer from its end, whole, so none is ever drawn cut. A key left out still
    works, and the `?` card lists it on a screen that has one. Spaced as usual when it fits.

    A key costs its glyph and a space on each side, then its words and a space, spaced
    as usual; compact, its glyph, a space, its words and a space before the next key
    (`Footer`'s own CSS)."""

    def compose(self) -> ComposeResult:
        if not self._bindings_ready:
            return
        entries = self._entries()
        width = self.screen.size.width
        self.compact = sum(self._cost(e, compact=False) for e in entries) > width
        keys = list(super().compose())
        if self.compact:
            keys = keys[: self._fitting(entries, width)]
        yield from keys

    def _entries(self) -> list[tuple[int, int]]:
        """The (glyph, words) lengths of the keys as `Footer.compose` lists them: one
        entry per action (the first binding shown for it wins). The app has no binding
        groups and turns the command palette off (`ENABLE_COMMAND_PALETTE`), the two
        other entries `Footer` can add."""
        first: dict[str, tuple[int, int]] = {}
        for _node, binding, _enabled, _tooltip in self.screen.active_bindings.values():
            if binding.show:
                first.setdefault(
                    binding.action,
                    (cell_len(self.app.get_key_display(binding)), cell_len(binding.description)),
                )
        return list(first.values())

    @staticmethod
    def _cost(entry: tuple[int, int], *, compact: bool) -> int:
        """Columns a key takes, with its space before the next key: the glyph and its
        words as `FooterKey` draws them. With no words only the glyph is drawn."""
        key, words = entry
        if not words:
            return key + compact
        return key + 1 + words + 1 if compact else key + 2 + words + 1

    @classmethod
    def _fitting(cls, entries: list[tuple[int, int]], width: int) -> int:
        """How many of the first keys fit `width` in the compact style (the last one
        draws no space after it)."""
        used = -1
        for count, entry in enumerate(entries):
            used += cls._cost(entry, compact=True)
            if used > width:
                return count
        return len(entries)

    def on_resize(self) -> None:
        self.call_after_refresh(self.recompose)
