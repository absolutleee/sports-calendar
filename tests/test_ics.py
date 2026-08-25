from datetime import date, datetime, timedelta, timezone

from icalendar import Calendar

from sports_calendar import ics
from sports_calendar.models import AllDayEvent, Game, ManualEvent, Team

LIV = Team("364", "Liverpool", "Liverpool")
FOR = Team("393", "Nottingham Forest", "Nottm Forest")
MUN = Team("360", "Manchester United", "Man United")
COL = Team("COL", "Colorado Avalanche", "Avalanche")
DAL = Team("DAL", "Dallas Stars", "Stars")
NAMES = {"soccer": {"Man United": "United", "Man City": "City"}, "hockey": {"Avalanche": "Avs"}}


def game(**over):
    g = Game(uid="espn-1", sport="soccer", competition="eng.1", competition_name="Premier League",
             home=LIV, away=FOR, day=date(2026, 8, 29),
             start=datetime(2026, 8, 29, 11, 30, tzinfo=timezone.utc), venue="Anfield", broadcast="NBC")
    for k, v in over.items():
        setattr(g, k, v)
    return g


def test_title_soccer_home_first_and_short_names():
    assert ics.title_for(game(), NAMES) == "Liverpool Nottm Forest"
    assert ics.title_for(game(home=MUN, away=LIV), NAMES) == "United Liverpool"
    assert ics.title_for(game(context="UCL Final"), NAMES) == "Liverpool Nottm Forest · UCL Final"


def test_title_us_sports_away_first():
    g = game(sport="hockey", competition="nhl", competition_name="NHL", home=COL, away=DAL)
    assert ics.title_for(g, NAMES) == "Stars Avs"
    g.context = "1st Round G3"
    assert ics.title_for(g, NAMES) == "Stars Avs · 1st Round G3"


def test_display_names_are_scoped_per_sport():
    spurs = Team("24", "San Antonio Spurs", "Spurs")
    knicks = Team("18", "New York Knicks", "Knicks")
    g = game(sport="basketball", competition="nba", competition_name="NBA", home=spurs, away=knicks)
    assert ics.title_for(g, {"soccer": {"Spurs": "Tottenham"}}) == "Knicks Spurs"


def test_title_time_tbd():
    assert ics.title_for(game(time_valid=False), NAMES) == "Liverpool Nottm Forest · time TBD"
    assert ics.title_for(game(time_valid=False, context="UCL Final"), NAMES) == "Liverpool Nottm Forest · UCL Final · time TBD"


def test_build_calendar_timed_event():
    g = game(matched_rules=["Liverpool"])
    data = ics.build_calendar([g], [], NAMES)
    cal = Calendar.from_ical(data)
    assert cal["X-WR-CALNAME"] == "Sports"
    assert str(cal["X-PUBLISHED-TTL"]) == "PT12H"
    ev = [c for c in cal.walk("VEVENT")][0]
    assert str(ev["UID"]) == "espn-1@sports-calendar"
    assert str(ev["SUMMARY"]) == "Liverpool Nottm Forest"
    assert ev["DTSTART"].dt == datetime(2026, 8, 29, 11, 30, tzinfo=timezone.utc)
    assert ev["DTEND"].dt == datetime(2026, 8, 29, 13, 30, tzinfo=timezone.utc)
    assert str(ev["LOCATION"]) == "Anfield"
    desc = str(ev["DESCRIPTION"])
    assert "Premier League" in desc and "TV: NBC" in desc and "Matched: Liverpool" in desc
    assert desc.splitlines()[-1] == "id: espn-1"
    assert "VALARM" not in data.decode()


def test_durations_by_sport():
    for sport, hours in [("baseball", 3), ("hockey", 2.5), ("basketball", 2.5), ("soccer", 2)]:
        g = game(sport=sport)
        ev = Calendar.from_ical(ics.build_calendar([g], [], {})).walk("VEVENT")[0]
        assert ev["DTEND"].dt - ev["DTSTART"].dt == timedelta(hours=hours)


def test_tbd_game_is_all_day():
    g = game(time_valid=False)
    ev = Calendar.from_ical(ics.build_calendar([g], [], {})).walk("VEVENT")[0]
    assert ev["DTSTART"].dt == date(2026, 8, 29)
    assert ev["DTEND"].dt == date(2026, 8, 30)


def test_all_day_event():
    e = AllDayEvent(uid="espn-golf-1", title="The Masters", start=date(2026, 4, 9), end=date(2026, 4, 13),
                    description="Masters Tournament", matched_rules=["Masters"])
    ev = Calendar.from_ical(ics.build_calendar([], [e], {})).walk("VEVENT")[0]
    assert str(ev["SUMMARY"]) == "The Masters"
    assert ev["DTSTART"].dt == date(2026, 4, 9) and ev["DTEND"].dt == date(2026, 4, 13)
    assert str(ev["UID"]) == "espn-golf-1@sports-calendar"


def test_all_day_event_has_id_line():
    e = AllDayEvent(uid="espn-golf-1", title="The Masters", start=date(2026, 4, 9), end=date(2026, 4, 13))
    ev = Calendar.from_ical(ics.build_calendar([], [e], {})).walk("VEVENT")[0]
    assert str(ev["DESCRIPTION"]) == "id: espn-golf-1"


def test_manual_timed_event():
    start = datetime(2026, 12, 19, 21, 0, tzinfo=timezone.utc)
    e = ManualEvent(uid="extra-fury-usyk-2026-12-19", title="Fury Usyk", start=start, end=start + timedelta(hours=3),
                    description="Riyadh")
    ev = Calendar.from_ical(ics.build_calendar([], [e], {})).walk("VEVENT")[0]
    assert str(ev["SUMMARY"]) == "Fury Usyk"
    assert ev["DTSTART"].dt == start and ev["DTEND"].dt == start + timedelta(hours=3)
    assert str(ev["DESCRIPTION"]) == "Riyadh\nid: extra-fury-usyk-2026-12-19"


def test_output_is_deterministic_and_sorted():
    a = game(uid="a", start=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc), day=date(2026, 9, 1))
    b = game(uid="b", start=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc), day=date(2026, 8, 1))
    out1 = ics.build_calendar([a, b], [], {})
    out2 = ics.build_calendar([b, a], [], {})
    assert out1 == out2
    uids = [str(e["UID"]) for e in Calendar.from_ical(out1).walk("VEVENT")]
    assert uids == ["b@sports-calendar", "a@sports-calendar"]
