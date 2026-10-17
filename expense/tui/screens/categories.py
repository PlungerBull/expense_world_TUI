"""Categories screen — spending buckets.

Color swatch + system-lock marker. `n` creates; `e` edits the cursor row
(prefilled EditCategoryScreen); `d` deletes the cursor row after a question.
`enter` does nothing. The system categories, `@Pendiente` and `@Opening`, are
the rows with a `system_key` (`reads.is_system_row`, never their names): they
keep their names and stay, so neither `e` nor `d` is offered on them, and the
legend says so (`errors.SYSTEM_HINT`, also the line under the engine's
`SYSTEM_CATEGORY` refusal). Only accounts archive.
"""

from expense import reads
from expense.errors import SYSTEM_HINT
from expense.reads import is_system_row
from expense.tui.screens._base import DELETE_KEY, ResourceListScreen
from expense.tui.widgets.cells import swatch

_HEADERS = ["Color", "Name", "System"]


def category_rows(items: list[dict]) -> list:
    """Pure (id, cells, base_style) rows for a CursorList. Unit-testable."""
    rows = []
    for it in items:
        cells = [
            swatch(it.get("color")),
            it.get("name") or "(unnamed)",
            "system 🔒" if is_system_row(it) else "—",
        ]
        rows.append((it.get("id"), cells, ""))
    return rows


class CategoriesScreen(ResourceListScreen):
    crumb = ("Manage", "Categories")
    CARD_WIDTH = 60
    TITLE = "Categories — buckets for every transaction"
    HEADERS = _HEADERS
    EMPTY = "(no categories)"
    LEGEND = SYSTEM_HINT
    RESOURCE = "categories"
    BINDINGS = [DELETE_KEY]

    def fetch_items(self, cfg, **kw):
        # The engine returns every row; the 20-row window pages
        # over the full set locally, so "page 2 of N" stays honest.
        return reads.fetch_categories(cfg, **kw)

    def rows(self, items: list) -> list:
        return category_rows(items)

    def is_fixed(self, item: dict) -> bool:
        return is_system_row(item)

    def delete_question(self, item: dict) -> tuple[str, str, str]:
        return (
            "Delete this category?",
            f"{item.get('name') or '(unnamed)'}\n"
            "It is for a category made by mistake: no screen can bring it back.",
            "Category deleted.",
        )

    def edit_screen(self, item: dict):
        from expense.tui.screens.create_forms import EditCategoryScreen

        return EditCategoryScreen(item)

    def new_screen(self):
        from expense.tui.screens.create_forms import NewCategoryScreen

        return NewCategoryScreen()
