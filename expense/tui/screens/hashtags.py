"""Hashtags screen — cross-cutting tags.

A plain name list, consistent with the other list screens, rather than the
chip mockup — usage counts would need engine support the list endpoint
doesn't provide. `n` creates; `e` renames the cursor row (prefilled
EditHashtagScreen). `enter` does nothing. Hashtag archive was removed
engine-side (2026-08-06 schema slimming) — only accounts archive now.
"""

from expense.commands import hashtags_cmd
from expense.tui.screens._base import ResourceListScreen

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

    def fetch_items(self, cfg, **kw):
        # The engine returns every row (2026-09-23); the 20-row window pages
        # over the full set locally, so "page 2 of N" stays honest.
        return hashtags_cmd.fetch_hashtags(cfg, **kw)

    def rows(self, items: list) -> list:
        return hashtag_rows(items)

    def edit_screen(self, item: dict):
        from expense.tui.screens.create_forms import EditHashtagScreen

        return EditHashtagScreen(item)

    def new_screen(self):
        from expense.tui.screens.create_forms import NewHashtagScreen

        return NewHashtagScreen()
