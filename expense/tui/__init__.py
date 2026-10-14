"""The interactive app — what `expense` opens when run alone.

A retained-mode Textual app over the engine reads and write plumbing (zero
business logic here). The entry point is kept light: `open_app` imports Textual
lazily so `expense import sheet` doesn't pay the cost.
See [docs/tui.md](../../docs/tui.md).
"""

import typer


def open_app(ctx: typer.Context) -> None:
    """Open the interactive app."""
    from expense.tui.app import launch

    launch(ctx)


__all__ = ["open_app"]
