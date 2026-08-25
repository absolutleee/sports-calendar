from datetime import date, datetime, timezone

from sports_calendar.models import AllDayEvent, Game, Team

LIV = Team(id="364", name="Liverpool", short="Liverpool")
NEW = Team(id="361", name="Newcastle United", short="Newcastle")


def test_game_involves_and_opponent():
    g = Game(uid="espn-1", sport="soccer", competition="eng.1", competition_name="Premier League",
             home=NEW, away=LIV, day=date(2026, 8, 23),
             start=datetime(2026, 8, 23, 15, 30, tzinfo=timezone.utc))
    assert g.involves("364")
    assert g.involves(364)
    assert not g.involves("1")
    assert g.opponent_of("364") == NEW
    assert g.opponent_of("361") == LIV
    assert g.opponent_of("999") is None


def test_game_defaults():
    g = Game(uid="x", sport="hockey", competition="nhl", competition_name="NHL",
             home=LIV, away=NEW, day=date(2026, 1, 1))
    assert g.start is None and g.time_valid is True and g.season_type == "regular"
    assert g.matched_rules == [] and g.context is None


def test_sort_key_uses_start_or_day():
    timed = Game(uid="a", sport="soccer", competition="x", competition_name="X", home=LIV, away=NEW,
                 day=date(2026, 1, 2), start=datetime(2026, 1, 2, 20, 0, tzinfo=timezone.utc))
    dateonly = Game(uid="b", sport="soccer", competition="x", competition_name="X", home=LIV, away=NEW,
                    day=date(2026, 1, 2), start=None)
    assert dateonly.sort_key() < timed.sort_key()


def test_allday_event():
    e = AllDayEvent(uid="golf-1", title="The Masters", start=date(2026, 4, 9), end=date(2026, 4, 13))
    assert e.description == "" and e.matched_rules == []
