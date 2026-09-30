"""How a typed fragment matches a reference name. Pure, no I/O.

One copy for every picker in the app: the quick-add grammar
([parse.py](parse.py)) and the two TUI form pickers
(`edit_form.py`, `create_forms.py`) match case- and **accent-blind**, so
`#banos` finds `BAÑOS`. The typed side and the stored side go through the
same function, so `#baños` still matches itself.

Nothing else about matching lives here. "Contains anywhere", exact-name-wins
and longest-phrase-wins are the grammar's rules and stay in `parse.py`.
"""

import unicodedata


def fold(text: str) -> str:
    """Casefold and strip accents: `'BAÑOS'` and `'banos'` both → `'banos'`.

    NFKD splits an accented letter into its base plus a combining mark; the
    marks (Unicode category `Mn`) are then dropped. `ñ` → `n`, `á` → `a`.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.casefold()


def matches(needle: str, name: str) -> bool:
    """`needle` appears anywhere in `name`, ignoring case and accents."""
    return fold(needle) in fold(name)
