"""The session clock. Everything the desk claims rests on this being right."""
import datetime

import pytest


def at(kit, ny, y, mo, d, h, mi):
    return kit.session_state(
        datetime.datetime(y, mo, d, h, mi, tzinfo=ny).astimezone(datetime.timezone.utc))


@pytest.mark.parametrize("when,expected", [
    ((2026, 9, 2, 9, 29), False),   # a minute before the open
    ((2026, 9, 2, 9, 30), True),    # the open itself is inclusive
    ((2026, 9, 2, 15, 59), True),
    ((2026, 9, 2, 16, 0), False),   # the close itself is exclusive
    ((2026, 9, 5, 12, 0), False),   # Saturday
    ((2026, 9, 6, 12, 0), False),   # Sunday
    ((2026, 9, 7, 9, 30), False),   # Labor Day — a Monday, still shut
    ((2026, 9, 8, 9, 30), True),    # the Tuesday after it
])
def test_open_state(kit, ny, when, expected):
    assert at(kit, ny, *when)["open"] is expected


def test_holiday_is_named(kit, ny):
    s = at(kit, ny, 2026, 12, 25, 12, 0)
    assert s["open"] is False
    assert s["closed_because"] == "Christmas Day"


def test_weekend_is_named(kit, ny):
    assert at(kit, ny, 2026, 9, 5, 12, 0)["closed_because"] == "Weekend"


def test_early_close_shuts_at_one(kit, ny):
    assert at(kit, ny, 2026, 11, 27, 12, 0)["open"] is True
    assert at(kit, ny, 2026, 11, 27, 13, 0)["open"] is False
    assert at(kit, ny, 2026, 11, 27, 12, 0)["early_close"] is True


def test_ordinary_day_is_not_flagged_early(kit, ny):
    assert at(kit, ny, 2026, 12, 3, 12, 0)["early_close"] is False


@pytest.mark.parametrize("frm,to", [
    ((2026, 12, 25, 12, 0), (2026, 12, 28, 9, 30)),   # Christmas Fri -> Mon
    ((2026, 11, 25, 16, 30), (2026, 11, 27, 9, 30)),  # over Thanksgiving
    ((2026, 4, 3, 10, 0), (2026, 4, 6, 9, 30)),       # Good Friday -> Mon
    ((2026, 9, 4, 16, 1), (2026, 9, 8, 9, 30)),       # Fri close -> Labor Day -> Tue
])
def test_gap_to_next_open_is_exact(kit, ny, frm, to):
    start = datetime.datetime(*frm, tzinfo=ny)
    target = datetime.datetime(*to, tzinfo=ny)
    truth = round((target - start).total_seconds() / 60)
    got = kit.session_state(start.astimezone(datetime.timezone.utc))["minutes_until_change"]
    assert got == truth


def test_countdown_never_negative_or_absurd(kit, ny):
    """Sample a year: the clock must always point somewhere sane."""
    t = datetime.datetime(2026, 1, 1, tzinfo=ny)
    end = datetime.datetime(2027, 1, 1, tzinfo=ny)
    while t < end:
        s = kit.session_state(t.astimezone(datetime.timezone.utc))
        assert 0 < s["minutes_until_change"] <= 6 * 1440, t
        t += datetime.timedelta(hours=7)


def test_dst_transition_does_not_break_the_clock(kit, ny):
    # US DST starts 2026-03-08 and ends 2026-11-01, both Sundays.
    for d in ((2026, 3, 8), (2026, 11, 1), (2026, 3, 9), (2026, 11, 2)):
        s = at(kit, ny, *d, 12, 0)
        assert isinstance(s["open"], bool)
        assert s["minutes_until_change"] > 0
