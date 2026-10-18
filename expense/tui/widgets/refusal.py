"""The `! …` line a screen keeps under what the engine refused.

One copy for every screen that lays a refusal out line by line: the bank
import's preview and result, and the split screen's parts.
"""

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text


def hanging(line: Text) -> RenderableType:
    """A `! …` line wraps under its own words, not under the `!`; any other
    line is itself."""
    if not line.plain.startswith("! "):
        return line
    grid = Table.grid()
    grid.add_column(no_wrap=True)
    grid.add_column()
    grid.add_row(line[:2], line[2:])
    return grid
