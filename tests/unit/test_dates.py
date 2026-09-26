from datetime import datetime

import pytest
import typer

from expense.dates import (
    TimezoneDetectionError,
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
