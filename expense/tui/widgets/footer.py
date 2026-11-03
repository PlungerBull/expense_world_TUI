"""A footer that gives up its spacing before it gives up a key."""

from textual.app import ComposeResult
from textual.widgets import Footer


class FittingFooter(Footer):
    """The footer, drawn in Textual's compact style (less whitespace between its keys)
    when its keys, spaced as usual, are wider than the screen, so the last one (`? Keys`)
    is never cut. Spaced as usual otherwise: only a screen whose footer can grow past a
    line uses it.

    A key costs its glyph and a space on each side, then its words and a space: the
    width the usual style draws (`Footer`'s own CSS)."""

    def compose(self) -> ComposeResult:
        if self._bindings_ready:
            self.compact = self._spaced_width() > self.screen.size.width
        yield from super().compose()

    def _spaced_width(self) -> int:
        """Width of the keys as `Footer.compose` lists them: one entry per action (the
        first binding shown for it wins). The app has no binding groups and turns the
        command palette off (`ENABLE_COMMAND_PALETTE`), the two other entries `Footer`
        can add."""
        first: dict[str, tuple[str, str]] = {}
        for _node, binding, _enabled, _tooltip in self.screen.active_bindings.values():
            if binding.show:
                first.setdefault(
                    binding.action, (self.app.get_key_display(binding), binding.description)
                )
        return sum(len(key) + 2 + len(words) + 1 for key, words in first.values())

    def on_resize(self) -> None:
        self.call_after_refresh(self.recompose)
