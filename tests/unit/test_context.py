"""Direct tests for expense/context.py — AppContext + get_verbose."""

from types import SimpleNamespace

import pytest

from expense.context import AppContext, get_verbose


@pytest.mark.parametrize(
    ("ctx", "verbose"),
    [
        (None, False),
        (SimpleNamespace(obj=None), False),
        (SimpleNamespace(obj={"verbose": True}), False),  # not an AppContext
        (SimpleNamespace(obj=AppContext(verbose=True)), True),
        (SimpleNamespace(obj=AppContext()), False),
    ],
)
def test_get_verbose_is_true_only_for_an_app_context_set_verbose(ctx, verbose):
    assert get_verbose(ctx) is verbose  # type: ignore[arg-type]
