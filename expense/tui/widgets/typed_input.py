"""TypedInput — the one input whose typed and pasted text shows as a function gives it back.

Every edit of the text (typing, paste, delete, cut) goes through `replace`, so the transform
holds for all of them. The bar forms' bar (`FormBar`) and `QuestionModal`'s typed lines share it.
"""

from collections.abc import Callable

from textual.widgets import Input


class TypedInput(Input):
    """An input that shows what is typed or pasted as `typed(text)`, as typed by default."""

    def __init__(self, *, typed: Callable[[str], str] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._typed = typed or (lambda text: text)

    def replace(self, text: str, start: int, end: int) -> None:
        super().replace(self._typed(text), start, end)
