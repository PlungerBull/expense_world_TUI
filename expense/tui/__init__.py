"""The interactive app — what `expense` opens when run alone.

A retained-mode Textual app over the engine reads and write plumbing (zero
business logic here). The entry point is kept light: `open_app` imports Textual
lazily so `expense import sheet` doesn't pay the cost.
See [docs/tui.md](../../docs/tui.md).
"""

from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from expense.import_.engine import SheetReview


def open_app(ctx: typer.Context, review: "SheetReview | None" = None) -> None:
    """Open the interactive app, on the import's review when `review` is given."""
    from expense.tui.app import launch

    launch(ctx, review)


__all__ = ["open_app"]
