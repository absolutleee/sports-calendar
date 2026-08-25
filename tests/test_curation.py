from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from sports_calendar import curation
from sports_calendar.models import AllDayEvent, Team
from tests.test_rules import COL, DAL, LIV, METS, NEW, ROX, mk

DEN = ZoneInfo("America/Denver")
DODGERS = Team("119", "Los Angeles Dodgers", "Dodgers")
NAMES = {"hockey": {"Avalanche": "Avs"}}


def _mets_at_la(uid, day_utc):
    # 01:30Z = 7:30pm the previous evening in Denver
    g = mk(uid, DODGERS, METS, day_utc, sport="baseball", comp="mlb", comp_name="MLB")
    g.start = datetime(day_utc.year, day_utc.month, day_utc.day, 1, 30, tzinfo=timezone.utc)
    return g


def test_exclude_by_title_and_between_uses_local_day():
    games = [_mets_at_la("g1", date(2026, 9, 5)), _mets_at_la("g2", date(2026, 9, 6)), _mets_at_la("g3", date(2026, 9, 8))]
    excludes = [{"title": "Mets Dodgers", "between": [date(2026, 9, 4), date(2026, 9, 5)]}]
    kept, _ = curation.apply_excludes(games, [], excludes, NAMES, DEN)
    assert [g.uid for g in kept] == ["g3"]  # g1 → Sep 4 Denver, g2 → Sep 5 Denver


def test_exclude_title_ignores_suffix():
    g = _mets_at_la("g1", date(2026, 3, 27))
    g.context = "Opening Day"
    kept, _ = curation.apply_excludes([g], [], [{"title": "Mets Dodgers"}], NAMES, DEN)
    assert kept == []
    kept, _ = curation.apply_excludes([g], [], [{"title": "Mets Dodgers · Opening Day"}], NAMES, DEN)
    assert kept == []


def test_exclude_by_sports_window_leaves_other_sports_and_events():
    games = [_mets_at_la("mlb", date(2026, 9, 5)),
             mk("nhl", COL, DAL, date(2026, 9, 5), sport="hockey", comp="nhl", comp_name="NHL"),
             mk("soc", LIV, NEW, date(2026, 9, 5))]
    events = [AllDayEvent(uid="t", title="US Open Men's Final", start=date(2026, 9, 5), end=date(2026, 9, 6))]
    excludes = [{"between": ["2026-09-01", "2026-09-14"], "sports": ["baseball", "hockey"]}]
    kept, kept_events = curation.apply_excludes(games, events, excludes, NAMES, DEN)
    assert [g.uid for g in kept] == ["soc"] and len(kept_events) == 1


def test_exclude_by_id_and_rules():
    games = [mk("a", LIV, NEW, date(2026, 9, 5), matched_rules=["Liverpool"]),
             mk("b", LIV, NEW, date(2026, 9, 12), matched_rules=["Liverpool", "Premier League big four"])]
    kept, _ = curation.apply_excludes(games, [], [{"id": "a"}], NAMES, DEN)
    assert [g.uid for g in kept] == ["b"]
    kept, _ = curation.apply_excludes(games, [], [{"rules": ["Premier League big four"]}], NAMES, DEN)
    assert [g.uid for g in kept] == ["a"]


def test_exclude_event_by_title_and_between():
    events = [AllDayEvent(uid="w", title="Wimbledon Day 1", start=date(2026, 6, 29), end=date(2026, 6, 30)),
              AllDayEvent(uid="m", title="The Masters", start=date(2026, 4, 9), end=date(2026, 4, 13))]
    _, kept = curation.apply_excludes([], events, [{"title": "Wimbledon Day 1", "between": ["2026-06-01", "2026-07-31"]}], NAMES, DEN)
    assert [e.uid for e in kept] == ["m"]


def test_invalid_exclude_entries():
    with pytest.raises(ValueError):
        curation.apply_excludes([], [], [{}], NAMES, DEN)
    with pytest.raises(ValueError):
        curation.apply_excludes([], [], [{"titel": "typo"}], NAMES, DEN)


def test_extras_all_day_single_and_multi_day():
    out = curation.build_extras([{"title": "Ryder Cup", "start": date(2027, 9, 24), "end": date(2027, 9, 26)},
                                 {"title": "Derby Day", "start": "2027-05-01", "notes": "Churchill Downs"}], DEN)
    ryder, derby = out
    assert ryder.uid == "extra-ryder-cup-2027-09-24"
    assert ryder.start == date(2027, 9, 24) and ryder.end == date(2027, 9, 27)
    assert derby.start == date(2027, 5, 1) and derby.end == date(2027, 5, 2) and derby.description == "Churchill Downs"


def test_extras_timed_with_hours_and_naive_localized():
    aware = datetime(2026, 12, 19, 21, 0, tzinfo=timezone.utc)
    out = curation.build_extras([{"title": "Fury Usyk", "start": aware, "hours": 3},
                                 {"title": "Watch party", "start": datetime(2026, 12, 20, 18, 0)},
                                 {"title": "String", "start": "2026-12-21T19:00Z"}], DEN)
    fury, party, string = out
    assert fury.start == aware and fury.end == aware + timedelta(hours=3)
    assert party.start == datetime(2026, 12, 20, 18, 0, tzinfo=DEN) and party.end - party.start == timedelta(hours=2)
    assert string.start == datetime(2026, 12, 21, 19, 0, tzinfo=timezone.utc)
    assert fury.uid == "extra-fury-usyk-2026-12-19"


def test_extras_require_title_and_start():
    with pytest.raises(ValueError):
        curation.build_extras([{"title": "No start"}], DEN)
    with pytest.raises(ValueError):
        curation.build_extras([{"title": "x", "start": "2026-01-01", "colour": "red"}], DEN)
