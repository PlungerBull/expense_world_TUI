"""The machine's region gives the number format until a setting is picked.

Read once at launch (`apply_launch_format`), never stored. On macOS the OS is asked
for the current locale's decimal separator, which honours a custom decimal set in
System Settings; elsewhere the environment's `LC_NUMERIC` locale is asked through
Python's `locale`. A comma gives `1.234,56`, a dot `1,234.56`; any other answer or a
failed read is `DEFAULT_FORMAT`. The read never raises or hangs; it is bounded at 2 s.
"""

import locale
import subprocess
import sys

from expense.number_format import (
    DEFAULT_FORMAT,
    NumberFormat,
    set_current_format,
)

_READ_TIMEOUT_SECONDS = 2

#: Asks macOS for the current locale's decimal separator (about 0.04 s).
_MACOS_SEPARATOR_ARGV = [
    "osascript",
    "-l",
    "JavaScript",
    "-e",
    "ObjC.import('Foundation'); $.NSLocale.currentLocale.decimalSeparator.js",
]


#: Asks macOS for the current region's name, as System Settings spells it.
_MACOS_NAME_ARGV = [
    "osascript",
    "-l",
    "JavaScript",
    "-e",
    "ObjC.import('Foundation'); var l = $.NSLocale.currentLocale; "
    "l.localizedStringForLocaleIdentifier(l.localeIdentifier).js",
]


def _format_for_decimal_mark(mark: str) -> NumberFormat | None:
    if mark == ",":
        return NumberFormat.COMMA_DECIMAL
    if mark == ".":
        return NumberFormat.DOT_DECIMAL
    return None


def _from_macos() -> NumberFormat | None:
    out = subprocess.run(
        _MACOS_SEPARATOR_ARGV,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=_READ_TIMEOUT_SECONDS,
        check=True,
    ).stdout
    return _format_for_decimal_mark(out.strip())


def _from_locale() -> NumberFormat | None:
    """The `LC_NUMERIC` locale's mark (`LC_ALL`, `LC_NUMERIC`, `LANG` decide); the
    process's previous locale is restored whatever happens."""
    previous = locale.setlocale(locale.LC_NUMERIC)
    try:
        locale.setlocale(locale.LC_NUMERIC, "")
        return _format_for_decimal_mark(locale.localeconv()["decimal_point"])
    finally:
        locale.setlocale(locale.LC_NUMERIC, previous)


def read_region_format() -> NumberFormat:
    """The machine's format; `DEFAULT_FORMAT` when it cannot be read."""
    try:
        found = _from_macos() if sys.platform == "darwin" else _from_locale()
    except Exception:  # missing binary, timeout, bad exit, unsupported locale: default stands
        return DEFAULT_FORMAT
    return found or DEFAULT_FORMAT


def read_region_name() -> str | None:
    """The machine's region as named on macOS (`English (Peru)`); `None` elsewhere or
    when it cannot be read. Never raises or hangs (2 s)."""
    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.run(
            _MACOS_NAME_ARGV,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=_READ_TIMEOUT_SECONDS,
            check=True,
        ).stdout
    except Exception:  # missing binary, timeout, bad exit: the row goes without a name
        return None
    return out.strip() or None


def launch_format(setting: NumberFormat | None = None) -> NumberFormat:
    """The session's format at launch: the account's setting when there is one, else
    the machine's region. The setting is the engine's `number_format`, `None` for no pick."""
    return setting if setting is not None else read_region_format()


def apply_launch_format(setting: NumberFormat | None = None) -> None:
    """Set the session format; called once, before the first screen draws an amount."""
    set_current_format(launch_format(setting))
