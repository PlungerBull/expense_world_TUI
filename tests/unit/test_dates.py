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


@pytest.mark.parametrize(
    "stamp",
    ["2026-04-25T16:30:00Z", "2026-04-25T16:30:00-05:00", "2026-04-25T16:30:00+02:00"],
)
def test_an_aware_datetime_passes_through(stamp):
    assert to_canonical_aware(stamp) == stamp


@pytest.mark.parametrize(
    ("text", "clock"),
    [
        ("2026-04-25T16:30:00", (16, 30, 0)),
        ("2026-04-25 16:30:00", (16, 30, 0)),
        ("2026-04-25T16:30", (16, 30, 0)),
        ("2026-04-25", (0, 0, 0)),  # a day alone is midnight local
    ],
)
def test_a_naive_datetime_gets_the_local_timezone(text, clock):
    parsed = datetime.fromisoformat(to_canonical_aware(text))
    assert parsed.tzinfo is not None
    assert (parsed.year, parsed.month, parsed.day) == (2026, 4, 25)
    assert (parsed.hour, parsed.minute, parsed.second) == clock


@pytest.mark.parametrize("text", ["not-a-date", "2026-04-25T25:99:00"])
def test_an_unreadable_date_raises_bad_parameter(text):
    with pytest.raises(typer.BadParameter):
        to_canonical_aware(text)


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
    TUI can catch it without importing typer."""
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


def test_is_readable_date_takes_what_the_save_reads():
    """`is_readable_date` answers with `to_canonical_aware`, the save's reader:
    a day with or without a time, or with an offset, and nothing else."""
    from expense.dates import is_readable_date

    for good in ["2026-10-23", "2026-10-23 14:30", "2026-10-23T14:30:00", "2026-10-23T14:30:00Z"]:
        assert is_readable_date(good), good
    for bad in ["abc", "18/8", "hoy", "2026-13-01", "2026-02-30"]:
        assert not is_readable_date(bad), bad
