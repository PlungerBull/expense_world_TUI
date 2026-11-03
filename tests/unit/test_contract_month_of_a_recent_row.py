"""A recent row and the month a report reads for it come from one moment, so a row logged in
the first minute of a month, in the display timezone, is read in the month it is dated in, and
the first minute after a daylight-saving jump gives a minute that exists."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from tests.contract.conftest import minute_before, month_of

LIMA = ZoneInfo("America/Lima")  # UTC-5, no daylight saving
AUCKLAND = ZoneInfo("Pacific/Auckland")


def test_the_first_minute_of_a_month_reads_the_month_before_it():
    now = datetime(2026, 3, 1, 0, 0, 30, tzinfo=LIMA)

    moment = minute_before(now, LIMA)

    assert moment.isoformat() == "2026-02-28T23:59:30-05:00"
    assert month_of(moment) == {"year": "2026", "month": "2"}


def test_the_year_turns_with_the_month():
    moment = minute_before(datetime(2027, 1, 1, 0, 0, 30, tzinfo=LIMA), LIMA)

    assert month_of(moment) == {"year": "2026", "month": "12"}


def test_a_zone_that_disagrees_with_utc_is_read_in_its_own_zone():
    # 05:00:30 UTC on 1 March is 00:00:30 in Lima: UTC is in March, Lima's minute back in February
    now = datetime(2026, 3, 1, 5, 0, 30, tzinfo=UTC)

    moment = minute_before(now, LIMA)

    assert (moment.astimezone(UTC).month, month_of(moment)["month"]) == (3, "2")
    assert month_of(minute_before(now, AUCKLAND)) == {"year": "2026", "month": "3"}


def test_a_minute_that_stays_in_the_month_reads_that_month():
    moment = minute_before(datetime(2026, 3, 1, 0, 1, 30, tzinfo=LIMA), LIMA)

    assert month_of(moment) == {"year": "2026", "month": "3"}


def test_the_first_minute_after_a_daylight_saving_jump_gives_a_minute_that_exists():
    new_york = ZoneInfo("America/New_York")
    # 03:00:30 EDT: 30 s into the first minute after the jump
    now = datetime(2026, 3, 8, 7, 0, 30, tzinfo=UTC)

    moment = minute_before(now, new_york)

    assert moment.astimezone(UTC).astimezone(new_york).isoformat() == moment.isoformat()
    assert (now.astimezone(UTC) - moment.astimezone(UTC)).total_seconds() == 60
