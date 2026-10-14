"""Date input normalization for the dates a person types.

The engine accepts only RFC 3339 datetimes with an explicit timezone offset
(naive datetimes return 422). This module accepts the user's natural shapes
(YYYY-MM-DD, naive datetimes with T or space separator, etc.) and emits the
engine-canonical form. Aware input passes through verbatim so the user's
exact wire format is preserved.

Also home to `detect_timezone` — the client-side IANA zone detection the
TUI's setup screen and its Bootstrap action share.
"""

import os
import re
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import typer
import tzlocal


def _local_tz() -> ZoneInfo:
    return ZoneInfo(tzlocal.get_localzone_name())


def now_local_iso() -> str:
    """Local wall-clock time with local timezone offset, ISO 8601."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today_local() -> date:
    """Today in the user's local zone — the `today` the quick-add grammar
    resolves `hoy` and a bare `18/8` against.

    Its own function so tests have a seam to freeze, exactly as they freeze
    `now_local_iso`. `date.today()` would answer in the *process* zone, which
    is the same thing here but says less about why it is being asked.
    """
    return datetime.now().astimezone().date()


class TimezoneDetectionError(RuntimeError):
    """System timezone could not be detected (no valid TZ env var, and
    /etc/localtime is not a zoneinfo symlink — some containers/WSL)."""


def detect_timezone(localtime: Path = Path("/etc/localtime")) -> str:
    """Best-effort IANA zone detection: $TZ if valid, else /etc/localtime.

    Neutral error on failure so each screen picks its own remedy: the setup
    screen asks for the zone, and Auth & profile notifies instead of crashing
    the app.
    """
    tz_env = os.environ.get("TZ")
    if tz_env:
        try:
            ZoneInfo(tz_env)
            return tz_env
        except ZoneInfoNotFoundError:
            pass

    if localtime.is_symlink():
        target = str(localtime.resolve())
        marker = "/zoneinfo/"
        if marker in target:
            zone = target.split(marker, 1)[1]
            try:
                ZoneInfo(zone)
                return zone
            except ZoneInfoNotFoundError:
                pass

    raise TimezoneDetectionError("Could not detect the system timezone from $TZ or /etc/localtime.")


def to_canonical_aware(user_input: str) -> str:
    """Normalize a user-typed date into RFC 3339 with a timezone offset.

    Accepted shapes:
      - 'YYYY-MM-DD'                     midnight in the user's local zone
      - 'YYYY-MM-DD HH:MM[:SS]'          local zone (space separator)
      - 'YYYY-MM-DDTHH:MM[:SS]'          local zone (T separator)
      - 'YYYY-MM-DDTHH:MM:SSZ'           UTC, passed through verbatim
      - 'YYYY-MM-DDTHH:MM:SS+HH:MM'      explicit offset, passed through verbatim

    Raises typer.BadParameter on unparseable input.
    """
    try:
        dt = datetime.fromisoformat(user_input)
    except ValueError:
        try:
            d = date.fromisoformat(user_input)
        except ValueError as exc:
            raise typer.BadParameter(
                f"Invalid date {user_input!r}. Use YYYY-MM-DD, "
                "'YYYY-MM-DD HH:MM[:SS]', or RFC 3339 with offset."
            ) from exc
        dt = datetime.combine(d, time())

    if dt.tzinfo is not None:
        return user_input
    return dt.replace(tzinfo=_local_tz()).isoformat(timespec="seconds")


_CALENDAR_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def is_calendar_day(text: str) -> bool:
    """True when `text` is exactly the day shape the engine accepts for a
    reconciliation's `date_start` / `date_end` (contract: "Date inputs"):
    zero-padded `YYYY-MM-DD`, and a real day.

    The regex is not redundant: 3.11's `date.fromisoformat` also takes
    `20260831`, which the engine refuses. The TUI form uses this to refuse a
    bad day at the field.
    """
    if not _CALENDAR_DAY.fullmatch(text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True
