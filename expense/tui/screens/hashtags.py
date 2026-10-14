"""Hashtags screen — cross-cutting tags.

A plain name list, consistent with the other list screens, rather than
chips with usage counts — those would need engine support the list endpoint
doesn't provide. `n` creates; `e` renames the cursor row (prefilled
EditHashtagScreen); `d` deletes the cursor row after a question that says
it is also taken off every transaction carrying it. `enter` does nothing. Only
accounts archive.
"""

from expense import reads
from expense.tui.screens._base import DELETE_KEY, ResourceListScreen

_HEADERS = ["Name"]


def hashtag_rows(items: list[dict]) -> list:
    """Pure (id, cells, base_style) rows for a CursorList. Unit-testable."""
    rows = []
    for it in items:
        name = it.get("name") or "(unnamed)"
        rows.append((it.get("id"), ["#" + name.lstrip("#")], ""))
    return rows


class HashtagsScreen(ResourceListScreen):
    crumb = ("Manage", "Hashtags")
    CARD_WIDTH = 48
    TITLE = "Hashtags — tag across categories & accounts"
    HEADERS = _HEADERS
    EMPTY = "(no hashtags)"
    RESOURCE = "hashtags"
    BINDINGS = [DELETE_KEY]

    def fetch_items(self, cfg, **kw):
        # The engine returns every row; the 20-row window pages
        # over the full set locally, so "page 2 of N" stays honest.
        return reads.fetch_hashtags(cfg, **kw)

    def rows(self, items: list) -> list:
        return hashtag_rows(items)

    def delete_question(self, item: dict) -> tuple[str, str, str]:
        # The engine never refuses this delete for being in use: it takes the
        # tag off every transaction carrying it (contract: DELETE /v1/hashtags/{hashtag_id}),
        # so the question says so.
        name = "#" + (item.get("name") or "(unnamed)").lstrip("#")
        return (
            "Delete this hashtag?",
            f"{name}\nIt is also taken off every transaction that carries it. "
            "No screen can bring it back.",
            "Hashtag deleted.",
        )

    def edit_screen(self, item: dict):
        from expense.tui.screens.create_forms import EditHashtagScreen

        return EditHashtagScreen(item)

    def new_screen(self):
        from expense.tui.screens.create_forms import NewHashtagScreen

        return NewHashtagScreen()
