"""The machine's region gives the number format at launch (expense/region.py).

The conftest pins `region.read_region_format` for every test; this file imports the
real one by name before that patch and fakes only its OS calls.
"""

import subprocess
import types

import pytest

from expense import number_format, region
from expense.number_format import DEFAULT_FORMAT, NumberFormat, current_format
from expense.region import (
    apply_launch_format,
    launch_format,
    read_region_format,
    read_region_name,
)

COMMA = NumberFormat.COMMA_DECIMAL
DOT = NumberFormat.DOT_DECIMAL


def _macos(monkeypatch, stdout=None, failure=None):
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if failure is not None:
            raise failure
        return types.SimpleNamespace(stdout=stdout)

    monkeypatch.setattr(region.subprocess, "run", run)
    monkeypatch.setattr(region.sys, "platform", "darwin")
    return calls


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        (",\n", COMMA),
        (",", COMMA),
        (".\n", DOT),
        ("٫\n", DEFAULT_FORMAT),
        ("", DEFAULT_FORMAT),
    ],
)
def test_the_macos_separator_gives_the_format(monkeypatch, stdout, expected):
    _macos(monkeypatch, stdout)
    assert read_region_format() is expected


def test_the_macos_call_is_fixed_bounded_and_shell_free(monkeypatch):
    calls = _macos(monkeypatch, ".\n")
    read_region_format()
    [(cmd, kwargs)] = calls
    assert cmd == region._MACOS_SEPARATOR_ARGV
    assert cmd == [
        "osascript",
        "-l",
        "JavaScript",
        "-e",
        "ObjC.import('Foundation'); $.NSLocale.currentLocale.decimalSeparator.js",
    ]
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["check"] is True
    assert 0 < kwargs["timeout"] <= 5
    assert not kwargs.get("shell")


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.TimeoutExpired(cmd="osascript", timeout=2),
        subprocess.CalledProcessError(1, "osascript"),
        FileNotFoundError("osascript"),
        PermissionError("osascript"),
    ],
)
def test_a_failed_macos_read_is_the_default_and_never_raises(monkeypatch, failure):
    _macos(monkeypatch, failure=failure)
    assert read_region_format() is DEFAULT_FORMAT


def _locale(monkeypatch, point=None, failure=None):
    """A fake `locale` module surface; returns the list of setlocale calls."""
    calls = []

    def setlocale(category, value=None):
        calls.append(value)
        if value == "" and failure is not None:
            raise failure
        return "C"

    monkeypatch.setattr(region.locale, "setlocale", setlocale)
    monkeypatch.setattr(region.locale, "localeconv", lambda: {"decimal_point": point})
    monkeypatch.setattr(region.sys, "platform", "linux")
    return calls


@pytest.mark.parametrize(("point", "expected"), [(",", COMMA), (".", DOT), ("", DEFAULT_FORMAT)])
def test_elsewhere_the_locale_gives_the_mark(monkeypatch, point, expected):
    _locale(monkeypatch, point)
    assert read_region_format() is expected


def test_elsewhere_the_previous_locale_is_restored(monkeypatch):
    calls = _locale(monkeypatch, ",")
    read_region_format()
    assert calls == [None, "", "C"]


def test_elsewhere_an_unsupported_locale_is_the_default_and_restores(monkeypatch):
    calls = _locale(monkeypatch, failure=region.locale.Error("unsupported"))
    assert read_region_format() is DEFAULT_FORMAT
    assert calls[-1] == "C"


def test_the_launch_sets_the_session_format_from_the_region(monkeypatch):
    monkeypatch.setattr(region, "read_region_format", lambda: COMMA)
    apply_launch_format()
    assert current_format() is COMMA
    monkeypatch.setattr(region, "read_region_format", lambda: DOT)
    apply_launch_format()
    assert current_format() is DOT


def test_a_setting_wins_over_the_region(monkeypatch):
    monkeypatch.setattr(region, "read_region_format", lambda: COMMA)
    assert launch_format(DOT) is DOT
    assert launch_format(None) is COMMA
    apply_launch_format(DOT)
    assert current_format() is DOT


def test_the_unit_suite_never_reads_the_machine(monkeypatch):
    """With the conftest pin, resolving the launch format spawns nothing and touches no
    locale, so the answer cannot depend on the machine's region."""

    touched = []  # the reader swallows exceptions, so a trap must record, not raise

    def trap(*a, **k):
        touched.append(a)
        raise OSError("the region was read from the machine")

    monkeypatch.setattr(region.subprocess, "run", trap)
    monkeypatch.setattr(region.locale, "setlocale", trap)
    assert launch_format() is DEFAULT_FORMAT
    apply_launch_format()
    assert current_format() is DEFAULT_FORMAT
    assert touched == []


def test_expense_opens_with_the_regions_format(monkeypatch):
    """`launch` sets the format before the app runs, so the first screen draws in it."""
    from expense.tui import app as app_module

    seen = []

    class FakeApp:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            seen.append(number_format.current_format())

    monkeypatch.setattr(region, "read_region_format", lambda: COMMA)
    monkeypatch.setattr(app_module, "ExpenseApp", FakeApp)
    monkeypatch.setattr(app_module.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(app_module.sys.stdout, "isatty", lambda: True, raising=False)
    ctx = types.SimpleNamespace(obj=types.SimpleNamespace(verbose=False))
    app_module.launch(ctx)  # type: ignore[arg-type]
    assert seen == [COMMA]


def test_the_macos_region_is_named_as_the_os_spells_it(monkeypatch):
    calls = _macos(monkeypatch, "English (Peru)\n")
    assert read_region_name() == "English (Peru)"
    [(cmd, kwargs)] = calls
    assert cmd == region._MACOS_NAME_ARGV
    assert kwargs["check"] is True and not kwargs.get("shell") and 0 < kwargs["timeout"] <= 5


@pytest.mark.parametrize(
    "failure",
    [subprocess.TimeoutExpired(cmd="osascript", timeout=2), FileNotFoundError("osascript")],
)
def test_a_failed_or_empty_name_read_is_no_name(monkeypatch, failure):
    _macos(monkeypatch, failure=failure)
    assert read_region_name() is None
    _macos(monkeypatch, "\n")
    assert read_region_name() is None


def test_elsewhere_the_region_has_no_name(monkeypatch):
    calls = _locale(monkeypatch, ",")
    assert read_region_name() is None
    assert calls == []
