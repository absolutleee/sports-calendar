from datetime import date, datetime, timezone

from sports_calendar.sources import mlb


def test_team_schedule(fake_fetch):
    calls = fake_fetch([(("statsapi.mlb.com", "teamId=121", "season=2026"), "mlb_mets_2026.json")])
    games = mlb.team_schedule("121", 2026)
    assert "gameType=R%2CF%2CD%2CL%2CW" in calls[0] and "hydrate=team" in calls[0]
    assert len(games) == 162  # 166 in the feed, 4 postponed games skipped
    g = games[0]
    assert g.uid.startswith("mlb-")
    assert g.sport == "baseball" and g.competition == "mlb" and g.competition_name == "MLB"
    assert g.start == datetime(2026, 3, 26, 17, 15, tzinfo=timezone.utc)
    assert g.day == date(2026, 3, 26)
    assert g.home.short == "Mets" and g.home.name == "New York Mets" and g.home.id == "121"
    assert g.away.short == "Pirates"
    assert g.season_type == "regular" and g.round_slug == "R"
    assert g.broadcast == "NBC/Peacock"
    assert g.time_valid is True


def test_unpublished_season_is_empty(fake_fetch):
    fake_fetch([("season=2027", {"dates": []})])
    assert mlb.team_schedule("121", 2027) == []


def test_not_found_is_empty(monkeypatch):
    from sports_calendar import http

    def boom(*a, **k):
        raise http.NotFound("x")

    monkeypatch.setattr(http, "get_json", boom)
    assert mlb.team_schedule("121", 2027) == []


def _game(**over):
    base = {
        "gamePk": 1, "gameType": "W", "gameDate": "2026-10-24T00:08:00Z", "officialDate": "2026-10-23",
        "status": {"detailedState": "Scheduled", "startTimeTBD": False},
        "teams": {"home": {"team": {"id": 121, "name": "New York Mets", "teamName": "Mets"}},
                  "away": {"team": {"id": 147, "name": "New York Yankees", "teamName": "Yankees"}}},
        "venue": {"name": "Citi Field"}, "seriesDescription": "World Series", "seriesGameNumber": 1,
        "broadcasts": [{"name": "FOX", "type": "TV"}, {"name": "WFAN", "type": "AM"}],
    }
    base.update(over)
    return base


def test_parse_postseason_game():
    g = mlb.parse_game(_game())
    assert g.season_type == "post" and g.series_title == "World Series" and g.series_game == 1
    assert g.day == date(2026, 10, 23)  # officialDate, not UTC date
    assert g.broadcast == "FOX"


def test_parse_tbd_and_postponed():
    tbd = mlb.parse_game(_game(status={"detailedState": "Scheduled", "startTimeTBD": True}))
    assert tbd.time_valid is False
    assert mlb.parse_game(_game(status={"detailedState": "Postponed", "startTimeTBD": False})) is None
    assert mlb.parse_game(_game(status={"detailedState": "Cancelled", "startTimeTBD": False})) is None
