"""The calendar is data, and data rots quietly. These tests make it rot loudly."""
import datetime


def test_verified_through_has_not_passed(calendar):
    through = datetime.date.fromisoformat(calendar["verified_through"])
    assert through >= datetime.date.today(), (
        f"calendar expired on {through} — closures after it are unmodelled")


def test_all_dates_are_observed_not_nominal(calendar):
    """A holiday landing on a weekend means someone wrote the nominal date."""
    for kind in ("holidays", "early_closes"):
        for e in calendar[kind]:
            d = datetime.date.fromisoformat(e["date"])
            assert d.weekday() < 5, f"{e['date']} ({e['name']}) falls on a weekend"


def test_no_duplicate_dates(calendar):
    for kind in ("holidays", "early_closes"):
        dates = [e["date"] for e in calendar[kind]]
        assert len(dates) == len(set(dates))


def test_a_date_is_never_both_closed_and_early(calendar):
    holidays = {e["date"] for e in calendar["holidays"]}
    early = {e["date"] for e in calendar["early_closes"]}
    assert not (holidays & early)


def test_every_entry_is_named(calendar):
    for kind in ("holidays", "early_closes"):
        for e in calendar[kind]:
            assert e.get("name", "").strip()


def test_kit_copy_matches_the_served_file(kit, calendar):
    """The kit embeds the calendar for offline use; drift would be silent."""
    assert set(kit.HOLIDAYS) == {e["date"] for e in calendar["holidays"]}
    assert set(kit.EARLY_CLOSES) == {e["date"] for e in calendar["early_closes"]}
    assert kit.CALENDAR_VERIFIED_THROUGH == calendar["verified_through"]
    assert kit.EARLY_CLOSE_HOUR == calendar["early_close_hour"]


def test_each_year_has_a_plausible_holiday_count(calendar):
    years = {}
    for e in calendar["holidays"]:
        years.setdefault(e["date"][:4], []).append(e)
    for year, entries in years.items():
        assert 8 <= len(entries) <= 11, f"{year} has {len(entries)} holidays"
