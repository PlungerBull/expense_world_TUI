"""Backlog 4.4 — the #field label column must fit every form label.

The bar-cycle forms (edit form, create forms, new reconciliation, setup) share
app.tcss's `#field { width: N; padding: 0 1 0 0 }`. Textual's box model puts
the padding INSIDE the width and Static hard-crops with no ellipsis, so a
label longer than (width − right padding) silently loses its tail
("BEGIN BALANCE" → "BEGIN BALA"). This guard computes the longest label
straight from the forms' own definitions and pins the tcss value against it —
a future longer label fails here by name instead of shipping clipped.
"""

import re
from pathlib import Path

import expense.tui as tui_pkg
from expense.tui.screens.create_forms import (
    NewAccountScreen,
    NewCategoryScreen,
    NewHashtagScreen,
)
from expense.tui.screens.edit_form import _LABELS
from expense.tui.screens.reconciliations import _R_LABELS, NewCardStatementScreen
from expense.tui.screens.setup import LABELS as SETUP_LABELS


def _field_rule(scope: str = "") -> tuple[int, int]:
    """(width, right_padding) parsed from app.tcss's #field rule, or from the
    rule a screen's `scope` puts on it, whose padding is the shared rule's."""
    tcss = (Path(tui_pkg.__file__).parent / "app.tcss").read_text()
    block = re.search(r"(?m)^#field\s*\{([^}]*)\}", tcss).group(1)
    width = int(re.search(r"width:\s*(\d+)", block).group(1))
    padding = re.search(r"padding:\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", block)
    right_pad = int(padding.group(2)) if padding else 0
    if scope:
        scoped = re.search(rf"(?m)^{scope} #field\s*\{{([^}}]*)\}}", tcss).group(1)
        width = int(re.search(r"width:\s*(\d+)", scoped).group(1))
    return width, right_pad


def _all_form_labels() -> dict[str, str]:
    """Every string that can appear in the #field label, keyed by origin."""
    labels = {f"edit_form:{key}": text for key, text in _LABELS.items()}
    labels |= {f"reconciliations:{key}": text for key, text in _R_LABELS.items()}
    labels |= {f"setup:{key}": text for key, text in SETUP_LABELS.items()}
    for screen in (NewHashtagScreen, NewCategoryScreen, NewAccountScreen):
        labels |= {f"{screen.__name__}:{f.key}": f.label for f in screen.FIELDS}
    return labels


def test_field_column_fits_every_label():
    width, right_pad = _field_rule()
    content = width - right_pad
    clipped = {k: v for k, v in _all_form_labels().items() if len(v) > content}
    assert not clipped, (
        f"#field width {width} leaves {content} content cells and clips: "
        + ", ".join(f"{k} {v!r} ({len(v)})" for k, v in clipped.items())
    )


def test_the_card_statement_form_fits_a_balance_and_its_currency():
    """A card statement's form names each balance's currency, `BEGIN BALANCE
    USD`, so it widens the column on its own screen alone; a currency code is
    always three letters."""
    width, right_pad = _field_rule("NewCardStatementScreen")
    form = NewCardStatementScreen(
        account=("acc1", "Signature PEN", "PEN"),
        partner=("acc2", "Signature USD", "USD"),
        code="SIG",
        holder_id="h1",
    )
    labels = {key: form._label(key) for key in form._sequence()}
    clipped = {k: v for k, v in labels.items() if len(v) > width - right_pad}
    assert not clipped
    assert max(len(v) for v in labels.values()) == width - right_pad


def test_the_edit_form_fits_each_parts_longest_label_up_to_part_99():
    """The Edit form names each part's field, `PART 2 CATEGORY`, so it widens
    the column on its own screen alone, to fit part 99's longest label."""
    from expense.tui.screens.edit_form import EditFormScreen
    from expense.tui.widgets.parts_table import FIELDS

    width, right_pad = _field_rule("EditFormScreen")
    form = EditFormScreen(record={"id": "t1", "bank_line_id": "bl1"})
    labels = {f"{i}.{field}": form._label(f"{i}.{field}") for i in range(99) for field in FIELDS}
    labels |= {key: form._label(key) for key in ("date", "title", "operation", "account")}
    assert labels["98.category"] == "PART 99 CATEGORY"
    clipped = {k: v for k, v in labels.items() if len(v) > width - right_pad}
    assert not clipped
    assert max(len(v) for v in labels.values()) == width - right_pad
