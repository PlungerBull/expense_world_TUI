"""The suggestion list under the quick-add input, shared by both surfaces.

The LOG bar and the bar-cycle edit form each wrote this scroll arithmetic out;
these pin the window behaviour that used to exist twice.
"""

from expense.tui.widgets.picker import PICKER_WINDOW, suggestion_list
from expense.tui.widgets.windowed import CURSOR_STYLE
from tests.unit.helpers import render_text


def _text(renderable, *, ansi: bool = False) -> str:
    return render_text(renderable, width=60, ansi=ansi)


def _labels(n: int) -> list[str]:
    return [f"name {i:02d}" for i in range(n)]


def test_an_empty_pool_says_what_to_do_about_it():
    assert "pick something that exists" in _text(suggestion_list([], 0))


def test_a_short_pool_shows_every_name_and_no_arrows():
    out = _text(suggestion_list(_labels(3), 0))
    assert "name 00" in out and "name 02" in out
    assert "more" not in out


def test_a_long_pool_windows_and_says_how_much_is_hidden():
    out = _text(suggestion_list(_labels(30), 0))
    assert out.count("name") == PICKER_WINDOW
    assert "↓ 22 more" in out and "↑" not in out


def test_the_window_centres_on_the_cursor_then_clamps_to_the_ends():
    middle = _text(suggestion_list(_labels(30), 15))
    assert "↑ 11 more" in middle and "↓ 11 more" in middle
    # the last page is full, not half-empty
    end = _text(suggestion_list(_labels(30), 29))
    assert "name 29" in end and "↓" not in end
    assert end.count("name") == PICKER_WINDOW


def test_the_cursor_row_is_drawn_with_the_shared_style():
    assert CURSOR_STYLE == "reverse"
    out = _text(suggestion_list(_labels(3), 1), ansi=True)
    lines = [ln for ln in out.splitlines() if "name" in ln]
    assert "\x1b[7m" in lines[1] and "\x1b[7m" not in lines[0]
