"""Hashtags screen — cross-cutting tags.

A table of Name and System, like Categories without the colour (a hashtag has
none), in the order `GET /hashtags` lists them. The built-in pending hashtag is
the row with a `system_key` (`reads.is_system_row`, never its name): it reads
`system 🔒` and every other row `—`. It keeps its name and is never deleted
(contract: PUT /v1/hashtags/{hashtag_id}, "The pending hashtag keeps its name")
(contract: DELETE /v1/hashtags/{hashtag_id}), and a hashtag has nothing to edit
but its name, so neither `e` nor `d` is offered on it; the legend says so.
`n` creates; `e` renames the cursor row (prefilled EditHashtagScreen); `d`
deletes the cursor row after a question that says it is also taken off every
transaction carrying it, and where a transaction left with no hashtag goes.
`enter` does nothing. Only accounts archive.
"""

from expense import reads
from expense.reads import is_system_row, pending_hashtag_of
from expense.tui.screens._base import DELETE_KEY, ResourceListScreen

_HEADERS = ["Name", "System"]

#: The legend under the list.
LEGEND = "System hashtags cannot be renamed or deleted."


def _tag(name: object) -> str:
    return "#" + (str(name) if name else "(unnamed)").lstrip("#")


def hashtag_rows(items: list[dict]) -> list:
    """Pure (id, cells, base_style) rows for a CursorList. Unit-testable."""
    return [
        (it.get("id"), [_tag(it.get("name")), "system 🔒" if is_system_row(it) else "—"], "")
        for it in items
    ]


class HashtagsScreen(ResourceListScreen):
    crumb = ("Manage", "Hashtags")
    CARD_WIDTH = 60
    TITLE = "Hashtags — tag across categories & accounts"
    HEADERS = _HEADERS
    EMPTY = "(no hashtags)"
    LEGEND = LEGEND
    RESOURCE = "hashtags"
    BINDINGS = [DELETE_KEY]

    def fetch_items(self, cfg, **kw):
        # The engine returns every row; the 20-row window pages
        # over the full set locally, so "page 2 of N" stays honest.
        return reads.fetch_hashtags(cfg, **kw)

    def rows(self, items: list) -> list:
        return hashtag_rows(items)

    def is_fixed(self, item: dict) -> bool:
        return is_system_row(item)

    def delete_question(self, item: dict) -> tuple[str, str, str]:
        # The engine never refuses this delete for being in use: it takes the
        # tag off every transaction carrying it, and one left with no hashtag
        # carries the pending hashtag (contract: DELETE /v1/hashtags/{hashtag_id}),
        # so the question says both. The pending hashtag is named as the list
        # gives it; with none in the list yet, the question says what it is.
        pending = pending_hashtag_of(list(self._by_id.values()))
        goes_to = _tag(pending[1]) if pending else "the pending hashtag"
        return (
            "Delete this hashtag?",
            f"{_tag(item.get('name'))}\nIt is also taken off every transaction that carries "
            f"it; one with no other hashtag goes to {goes_to}. No screen can bring it back.",
            "Hashtag deleted.",
        )

    def edit_screen(self, item: dict):
        from expense.tui.screens.create_forms import EditHashtagScreen

        return EditHashtagScreen(item)

    def new_screen(self):
        from expense.tui.screens.create_forms import NewHashtagScreen

        return NewHashtagScreen()
