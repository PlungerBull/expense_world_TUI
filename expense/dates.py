"""Date input normalization for commands that accept --date.

The engine accepts only RFC 3339 datetimes with an explicit timezone offset
(naive datetimes return 422). This module accepts the user's natural shapes
(YYYY-MM-DD, naive datetimes with T or space separator, etc.) and emits the
engine-canonical form. Aware input passes through verbatim so the user's
exact wire format is preserved.

Also home to `detect_timezone` — the client-side IANA zone detection shared
by `auth bootstrap` and the TUI Bootstrap action.
"""

import os
import re
from datetime import date, datetime, time, timedelta
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

    Neutral error on failure so each surface picks its own remedy: the CLI
    wraps it into BadParameter ("pass --timezone"), the TUI notifies with the
    TZ-env hint instead of crashing the app (backlog 6.2d).
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
                "'YYYY-MM-DD HH:MM[:SS]', or RFC 3339 with offset.",
                param_hint="--date",
            ) from exc
        dt = datetime.combine(d, time())

    if dt.tzinfo is not None:
        return user_input
    return dt.replace(tzinfo=_local_tz()).isoformat(timespec="seconds")


_CALENDAR_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def is_calendar_day(text: str) -> bool:
    """True when `text` is exactly the day shape the engine accepts for a
    reconciliation's `date_start` / `date_end` (engine-spec *Date inputs*):
    zero-padded `YYYY-MM-DD`, and a real day.

    The regex is not redundant: 3.11's `date.fromisoformat` also takes
    `20260831`, which the engine refuses. The TUI form uses this to refuse a
    bad day at the field; the flat commands send what was typed and let the
    engine's 422 speak.
    """
    if not _CALENDAR_DAY.fullmatch(text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def calendar_day_bound(text: str, zone: str, *, end: bool = False) -> str:
    """A bare day as an instant in `zone`, for a filter that takes only instants.

    `GET /activity` refuses a bare date and a naive time (engine debrief
    2026-09-23 part 2, §2.1), and stays on exact times by the engine owner's
    choice, so `activity list --from 2026-09-01` becomes the start of that day
    in the user's `display_timezone`. With `end=True` it becomes the start of
    the *next* day, so `--to 2026-09-25` covers the whole of the 25th.

    Only a bare `YYYY-MM-DD` is converted. Anything else — a time with an
    offset, a naive time, a typo — is sent as typed: the first is already what
    the engine wants, and the others get the engine's own `422`.
    """
    if not is_calendar_day(text):
        return text
    day = date.fromisoformat(text)
    if end:
        day += timedelta(days=1)
    return datetime.combine(day, time(), tzinfo=ZoneInfo(zone)).isoformat(timespec="seconds")


def parse_year_month(user_input: str, *, param_hint: str = "--date") -> tuple[int, int]:
    """Parse a YYYY-MM string into (year, month) integers.

    Used by `expense reports monthly` for --date / --from / --to. Strict shape:
    exactly four-digit year, dash, two-digit month. Value ranges (month 1..12,
    year bounds) are the engine's rules — out-of-range values are sent as-is so
    its 422 surfaces.

    Raises typer.BadParameter on bad shape only.
    """
    parts = user_input.split("-")
    if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
        raise typer.BadParameter(
            f"Invalid month {user_input!r}. Use YYYY-MM (e.g. 2026-04).",
            param_hint=param_hint,
        )
    try:
        year = int(parts[0])
        month = int(parts[1])
    except ValueError as exc:
        raise typer.BadParameter(
            f"Invalid month {user_input!r}. Use YYYY-MM (e.g. 2026-04).",
            param_hint=param_hint,
        ) from exc
    return year, month
