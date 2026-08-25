from datetime import date, datetime, timezone

from sports_calendar.sources import nhl


def test_club_schedule(fake_fetch):
    fake_fetch([("club-schedule-season/COL/20252026", "nhl_col_2025_26.json")])
    games = nhl.club_schedule("COL", "20252026")
    assert {g.season_type for g in games} == {"pre", "regular", "post"}
    reg = [g for g in games if g.season_type == "regular"]
    assert reg[0].day == date(2025, 10, 7)
    assert reg[0].away.id == "COL" and reg[0].home.id == "LAK"
    assert reg[0].away.short == "Avalanche" and reg[0].away.name == "Colorado Avalanche"
    assert reg[0].sport == "hockey" and reg[0].competition == "nhl" and reg[0].competition_name == "NHL"
    post = [g for g in games if g.season_type == "post"]
    assert post[0].day == date(2026, 4, 19)
    assert post[0].start == datetime(2026, 4, 19, 19, 0, tzinfo=timezone.utc)
    assert post[0].series_round == 1 and post[0].series_game == 1 and post[0].series_title == "1st Round"
    assert post[0].round_slug == "R1"
    assert post[0].venue == "Ball Arena"
    assert "TNT" in post[0].broadcast


def test_stanley_cup_final(fake_fetch):
    calls = fake_fetch([
        ("playoff-bracket/2026", "nhl_bracket_2026.json"),
        ("schedule/playoff-series/20252026/o/", "nhl_series_scf_2026.json"),
    ])
    games = nhl.stanley_cup_final("20252026")
    assert len(calls) == 2
    assert len(games) >= 4
    g = games[0]
    assert g.start == datetime(2026, 6, 3, 0, 0, tzinfo=timezone.utc)
    assert g.away.id == "VGK" and g.home.id == "CAR"
    assert g.home.short == "Hurricanes"
    assert g.season_type == "post" and g.series_round == 4 and g.series_game == 1
    assert g.series_title == "Stanley Cup Final" and g.round_slug == "SCF"
    assert g.venue == "Lenovo Center"


def test_stanley_cup_final_before_playoffs(monkeypatch):
    from sports_calendar import http

    def not_found(*a, **k):
        raise http.NotFound("x")

    monkeypatch.setattr(http, "get_json", not_found)
    assert nhl.stanley_cup_final("20262027") == []


def test_stanley_cup_final_series_not_set(fake_fetch):
    fake_fetch([("playoff-bracket/2027", {"series": [{"playoffRound": 1, "seriesLetter": "A"}]})])
    assert nhl.stanley_cup_final("20262027") == []


def _game(**over):
    base = {
        "id": 2026020001, "gameType": 2, "gameDate": "2026-10-08", "startTimeUTC": "2026-10-09T01:00:00Z",
        "venue": {"default": "Ball Arena"}, "neutralSite": False, "gameScheduleState": "OK",
        "tvBroadcasts": [{"network": "ESPN", "countryCode": "US", "market": "N", "sequenceNumber": 1},
                         {"network": "ALT", "countryCode": "US", "market": "H", "sequenceNumber": 2},
                         {"network": "SN", "countryCode": "CA", "market": "N", "sequenceNumber": 3}],
        "awayTeam": {"abbrev": "DAL", "commonName": {"default": "Stars"}, "placeName": {"default": "Dallas"}},
        "homeTeam": {"abbrev": "COL", "commonName": {"default": "Avalanche"}, "placeName": {"default": "Colorado"}},
    }
    base.update(over)
    return base


def test_parse_game_broadcast_prefers_us_national():
    g = nhl.parse_game(_game())
    assert g.broadcast == "ESPN, ALT"
    assert g.day == date(2026, 10, 8)  # gameDate (local), not UTC date


def test_parse_game_tbd_and_postponed():
    assert nhl.parse_game(_game(gameScheduleState="TBD")).time_valid is False
    assert nhl.parse_game(_game(gameScheduleState="PPD")) is None
    assert nhl.parse_game(_game(gameScheduleState="CNCL")) is None
