"""Categories screen — spending buckets.

Color swatch + system-lock marker. `n` creates; `e` edits the cursor row
(prefilled EditCategoryScreen). `enter` does nothing. System categories
can be renamed/recolored (the engine keys them by `system_key`, not name)
but cannot be deleted; the legend is the CLI's delete hint,
`formatting.SYSTEM_HINT`. Only accounts archive.
"""

from expense import formatting, reads
from expense.tui.screens._base import ResourceListScreen
from expense.tui.widgets.cells import swatch

_HEADERS = ["Color", "Name", "System"]


def category_rows(items: list[dict]) -> list:
    """Pure (id, cells, base_style) rows for a CursorList. Unit-testable."""
    rows = []
    for it in items:
        cells = [
            swatch(it.get("color")),
            it.get("name") or "(unnamed)",
            "system 🔒" if it.get("is_system") else "—",
        ]
        rows.append((it.get("id"), cells, ""))
    return rows


class CategoriesScreen(ResourceListScreen):
    crumb = ("Manage", "Categories")
    CARD_WIDTH = 60
    TITLE = "Categories — buckets for every transaction"
    HEADERS = _HEADERS
    EMPTY = "(no categories)"
    LEGEND = formatting.SYSTEM_HINT
    RESOURCE = "categories"

    def fetch_items(self, cfg, **kw):
        # The engine returns every row; the 20-row window pages
        # over the full set locally, so "page 2 of N" stays honest.
        return reads.fetch_categories(cfg, **kw)

    def rows(self, items: list) -> list:
        return category_rows(items)

    def edit_screen(self, item: dict):
        from expense.tui.screens.create_forms import EditCategoryScreen

        return EditCategoryScreen(item)

    def new_screen(self):
        from expense.tui.screens.create_forms import NewCategoryScreen

        return NewCategoryScreen()
