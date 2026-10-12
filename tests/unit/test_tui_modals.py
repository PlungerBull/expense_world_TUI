"""Guard: every modal's #modal box must actually render (non-zero size).

Regression armor for the Textual 8.x collapse — `width: auto` on #modal inside
`align: center middle` measured to 0, so the box shrank to an empty border and
every modal (the archive/delete confirm, the bulk-edit picker) went
invisible. app.tcss now sets a definite width; this test fails loudly if a
future Textual bump (or a stray edit) reintroduces the collapse. Asserting the
*screen* was pushed is not enough — the old tests did that and still passed
while the box rendered empty; we assert it has size.
"""

import pytest

from expense.tui.screens.modals import (
    ConfirmModal,
    PickerModal,
    PromptModal,
)
from tests.unit.helpers import run_app, wait_for

_MODALS = [
    lambda: ConfirmModal("Archive account?", "Archive BCP USD."),
    lambda: PromptModal("Rename", "New name"),
    lambda: PickerModal("CATEGORY for 3 rows", [("c1", "KORAKUEN")]),
]


def test_every_modal_box_renders_with_size():
    async def scenario(pilot, app):
        for make_modal in _MODALS:
            modal = make_modal()
            await app.push_screen(modal)
            await wait_for(pilot, lambda: app.screen.query("#modal"))
            box = app.screen.query_one("#modal")
            name = type(app.screen).__name__
            # A collapsed box is an empty border — the exact failure we guard.
            assert box.size.width > 10, f"{name} #modal collapsed: {box.size}"
            assert box.size.height > 2, f"{name} #modal collapsed: {box.size}"
            app.pop_screen()
            await wait_for(pilot, lambda: not app.screen.query("#modal"))

    run_app(scenario, size=(100, 40))


@pytest.mark.parametrize(
    ("kwargs", "typed", "expected"),
    [
        ({}, "  Groceries  ", "Groceries"),
        ({}, "   ", ""),
        (dict(verbatim=True), "  Groceries  ", "  Groceries  "),
        (dict(verbatim=True), "   ", "   "),
        (dict(verbatim=True), "", ""),
    ],
    ids=["default-trims", "default-blank", "verbatim-padded", "verbatim-spaces", "verbatim-empty"],
)
def test_prompt_trims_by_default_and_only_verbatim_keeps_whitespace(kwargs, typed, expected):
    async def scenario(pilot, app):
        results: list = []
        await app.push_screen(PromptModal("Rename", "New name", **kwargs), results.append)
        await wait_for(pilot, lambda: app.screen.query("#prompt"))
        app.screen.query_one("#prompt").value = typed
        await pilot.press("enter")
        await wait_for(pilot, lambda: results)
        assert results == [expected]

    run_app(scenario)


@pytest.mark.parametrize("kwargs", [{}, dict(verbatim=True)], ids=["default", "verbatim"])
def test_prompt_esc_cancels_with_none(kwargs):
    async def scenario(pilot, app):
        results: list = []
        await app.push_screen(PromptModal("Rename", "New name", **kwargs), results.append)
        await wait_for(pilot, lambda: app.screen.query("#prompt"))
        app.screen.query_one("#prompt").value = "typed"
        await pilot.press("escape")
        await wait_for(pilot, lambda: results)
        assert results == [None]

    run_app(scenario)
