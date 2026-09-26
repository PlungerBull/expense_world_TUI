from datetime import datetime

import pytest
import typer

from expense.dates import (
    TimezoneDetectionError,
    calendar_day_bound,
    detect_timezone,
    is_calendar_day,
    to_canonical_aware,
)


@pytest.fixture(autouse=True)
def pin_local_tz(monkeypatch):
    """Pin the local timezone so output strings are deterministic across machines."""
    monkeypatch.setattr("tzlocal.get_localzone_name", lambda: "America/New_York")


def test_aware_utc_passthrough():
    assert to_canonical_aware("2026-04-25T16:30:00Z") == "2026-04-25T16:30:00Z"


def test_aware_offset_passthrough():
    assert to_canonical_aware("2026-04-25T16:30:00-05:00") == "2026-04-25T16:30:00-05:00"


def test_aware_plus_offset_passthrough():
    assert to_canonical_aware("2026-04-25T16:30:00+02:00") == "2026-04-25T16:30:00+02:00"


def test_naive_datetime_t_separator_attaches_local_tz():
    result = to_canonical_aware("2026-04-25T16:30:00")
    parsed = datetime.fromisoformat(result)
    assert parsed.tzinfo is not None
    assert parsed.year == 2026 and parsed.month == 4 and parsed.day == 25
    assert parsed.hour == 16 and parsed.minute == 30 and parsed.second == 0


def test_naive_datetime_space_separator_attaches_local_tz():
    result = to_canonical_aware("2026-04-25 16:30:00")
    parsed = datetime.fromisoformat(result)
    assert parsed.tzinfo is not None
    assert parsed.hour == 16 and parsed.minute == 30


def test_naive_datetime_no_seconds():
    result = to_canonical_aware("2026-04-25T16:30")
    parsed = datetime.fromisoformat(result)
    assert parsed.tzinfo is not None
    assert parsed.hour == 16 and parsed.minute == 30


def test_date_only_midnight_local():
    result = to_canonical_aware("2026-04-25")
    parsed = datetime.fromisoformat(result)
    assert parsed.tzinfo is not None
    assert parsed.year == 2026 and parsed.month == 4 and parsed.day == 25
    assert parsed.hour == 0 and parsed.minute == 0


def test_garbage_raises_bad_parameter():
    with pytest.raises(typer.BadParameter):
        to_canonical_aware("not-a-date")


def test_invalid_time_raises_bad_parameter():
    with pytest.raises(typer.BadParameter):
        to_canonical_aware("2026-04-25T25:99:00")


def test_detect_timezone_from_tz_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TZ", "America/Lima")
    assert detect_timezone(localtime=tmp_path / "missing") == "America/Lima"


def test_detect_timezone_ignores_invalid_tz_env(monkeypatch, tmp_path):
    """A garbage $TZ falls through to /etc/localtime, then errors neutrally."""
    monkeypatch.setenv("TZ", "Not/AZone")
    with pytest.raises(TimezoneDetectionError):
        detect_timezone(localtime=tmp_path / "missing")


def test_detect_timezone_from_localtime_symlink(monkeypatch, tmp_path):
    monkeypatch.delenv("TZ", raising=False)
    zoneinfo_dir = tmp_path / "zoneinfo" / "America"
    zoneinfo_dir.mkdir(parents=True)
    zone_file = zoneinfo_dir / "Lima"
    zone_file.write_bytes(b"")
    localtime = tmp_path / "localtime"
    localtime.symlink_to(zone_file)
    assert detect_timezone(localtime=localtime) == "America/Lima"


def test_detect_timezone_failure_raises_neutral_error(monkeypatch, tmp_path):
    """No $TZ and no symlink → TimezoneDetectionError (not typer/click), so the
    TUI can catch it without importing the CLI layer (backlog 6.2d)."""
    monkeypatch.delenv("TZ", raising=False)
    with pytest.raises(TimezoneDetectionError):
        detect_timezone(localtime=tmp_path / "missing")


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("2026-08-31", True),
        ("2024-02-29", True),
        ("2026-8-31", False),  # unpadded — the engine refuses it
        ("20260831", False),  # compact — 3.11's fromisoformat takes it, the engine does not
        ("31/08/2026", False),
        ("2026-02-30", False),  # the right shape, not a day
        ("2026-08-31T00:00:00-05:00", False),  # any datetime is a 422 on a period
        (" 2026-08-31", False),
        ("", False),
    ],
)
def test_is_calendar_day_is_the_engines_day_shape(text, ok):
    assert is_calendar_day(text) is ok


# --- calendar_day_bound (activity list --from / --to) ---------------------


def test_calendar_day_bound_start_is_midnight_in_the_zone():
    assert calendar_day_bound("2026-09-01", "America/Lima") == "2026-09-01T00:00:00-05:00"


def test_calendar_day_bound_end_is_the_next_midnight():
    assert calendar_day_bound("2026-09-30", "America/Lima", end=True) == (
        "2026-10-01T00:00:00-05:00"
    )


def test_calendar_day_bound_takes_the_offset_of_that_day_not_today():
    """New York is -04:00 on 2026-11-01 and -05:00 by the next midnight."""
    assert calendar_day_bound("2026-11-01", "America/New_York") == "2026-11-01T00:00:00-04:00"
    assert calendar_day_bound("2026-11-01", "America/New_York", end=True) == (
        "2026-11-02T00:00:00-05:00"
    )


@pytest.mark.parametrize(
    "typed", ["2026-09-01T00:00:00Z", "2026-09-01T08:00:00-05:00", "2026-09-01T00:00", "20260901"]
)
def test_calendar_day_bound_passes_anything_but_a_bare_day_through(typed):
    """An aware time is already right; the rest is the engine's to refuse."""
    assert calendar_day_bound(typed, "America/Lima") == typed
    assert calendar_day_bound(typed, "America/Lima", end=True) == typed
