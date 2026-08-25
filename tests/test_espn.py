from datetime import date, datetime, timezone

from sports_calendar.sources import espn


def test_parse_soccer_fixture(fixture):
    data = fixture("espn_liverpool_fixtures.json")
    games = espn.parse_schedule(data, sport="soccer", league_slug="all", league_name="Soccer")
    assert len(games) == 37
    g = games[0]
    assert g.uid.startswith("espn-")
    assert g.sport == "soccer"
    assert g.competition == "eng.1"
    assert g.competition_name == "English Premier League"
    assert g.home.short == "Liverpool" and g.away.short == "Nottm Forest"
    assert g.away.name == "Nottingham Forest"
    assert g.start == datetime(2026, 8, 29, 11, 30, tzinfo=timezone.utc)
    assert g.day == date(2026, 8, 29)
    assert g.time_valid is True
    assert g.season_type == "regular"
    assert g.neutral is False


def test_parse_soccer_results_include_friendlies(fixture):
    games = espn.parse_schedule(fixture("espn_liverpool_results.json"), "soccer", "all", "Soccer")
    assert {g.competition for g in games} == {"eng.1", "club.friendly"}


def test_soccer_team_schedule_merges_results_and_fixtures(fake_fetch):
    calls = fake_fetch([
        (("teams/364/schedule", "fixture=true"), "espn_liverpool_fixtures.json"),
        ("teams/364/schedule", "espn_liverpool_results.json"),
    ])
    games = espn.soccer_team_schedule("364")
    assert len(games) == 44
    assert len(calls) == 2
    assert len({g.uid for g in games}) == 44


def test_us_team_schedule_fetches_regular_and_post(fake_fetch):
    fake_fetch([
        (("teams/7/schedule", "seasontype=2"), "espn_nuggets_2026_27_reg.json"),
        (("teams/7/schedule", "seasontype=3"), "espn_nuggets_2025_26_post.json"),
    ])
    games = espn.us_team_schedule("basketball", "nba", "7", 2027)
    assert len(games) == 86
    post = [g for g in games if g.season_type == "post"]
    assert len(post) == 6
    assert post[0].notes == "West 1st Round - Game 1"
    assert post[0].series_game == 1
    reg = [g for g in games if g.season_type == "regular"]
    assert reg[0].competition == "nba" and reg[0].competition_name == "NBA"
    assert reg[0].home.short == "Thunder" and reg[0].away.short == "Nuggets"
    assert reg[0].broadcast == "ESPN"


def test_us_team_schedule_tolerates_missing_events(fake_fetch):
    fake_fetch([
        (("teams/7/schedule", "seasontype=2"), "espn_nuggets_2026_27_reg.json"),
        (("teams/7/schedule", "seasontype=3"), {"events": []}),
    ])
    assert len(espn.us_team_schedule("basketball", "nba", "7", 2027)) == 80


def test_ncaa_postseason_notes(fixture):
    games = espn.parse_schedule(fixture("espn_denver_hockey_2025_26.json"), "hockey",
                                "mens-college-hockey", "NCAA Hockey")
    assert len(games) == 43
    first = games[0]
    assert first.away.short == "Denver" and first.home.short == "Air Force"
    assert first.venue == "Cadet Ice Arena"
    post = [g for g in games if g.season_type == "post"]
    assert len(post) == 4
    assert post[-1].notes == "NCAA Men's Hockey National Championship"


def test_scoreboard_round_slugs_and_notes(fake_fetch):
    calls = fake_fetch([("uefa.champions/scoreboard", "espn_ucl_2025_26.json")])
    games = espn.scoreboard("soccer", "uefa.champions", date(2025, 8, 1), date(2026, 6, 1))
    assert "dates=20250801-20260601" in calls[0] and "limit=1000" in calls[0]
    assert len(games) == 189
    final = [g for g in games if g.round_slug == "final"]
    assert len(final) == 1
    assert final[0].home.short == "PSG" and final[0].away.short == "Arsenal"
    assert final[0].competition == "uefa.champions"
    assert final[0].competition_name == "UEFA Champions League"
    semis = [g for g in games if g.round_slug == "semifinals"]
    assert len(semis) == 4
    assert any(g.notes.startswith("2nd Leg") for g in semis if g.notes)


def test_scoreboard_nba_finals(fake_fetch):
    fake_fetch([("nba/scoreboard", "espn_nba_june_2026.json")])
    games = espn.scoreboard("basketball", "nba", date(2026, 6, 1), date(2026, 6, 25))
    assert [g.notes for g in games][:2] == ["NBA Finals - Game 1", "NBA Finals - Game 2"]
    assert games[0].season_type == "post"
    assert games[0].series_game == 1


def test_season_type_detection():
    ev = {"id": "1", "date": "2026-08-23T15:30Z", "competitions": [{"competitors": [
        {"homeAway": "home", "team": {"id": "1", "displayName": "A"}},
        {"homeAway": "away", "team": {"id": "2", "displayName": "B"}}]}]}
    assert espn.parse_event({**ev, "seasonType": {"type": 14308, "name": "2026-27 English Premier League"}},
                            "soccer", "eng.1", "PL").season_type == "regular"
    assert espn.parse_event({**ev, "seasonType": {"type": 1, "name": "Preseason"}}, "basketball", "nba", "NBA").season_type == "pre"
    assert espn.parse_event({**ev, "seasonType": {"type": 3, "name": "Postseason"}}, "hockey", "x", "X").season_type == "post"
    assert espn.parse_event({**ev, "season": {"year": 2026, "type": 3, "slug": "post-season"}}, "basketball", "nba", "NBA").season_type == "post"
    assert espn.parse_event({**ev, "season": {"year": 2025, "type": 13530, "slug": "promotion-semifinals"}}, "soccer", "eng.2", "C").season_type == "regular"


def test_parse_event_skips_malformed():
    assert espn.parse_event({"id": "1", "date": "2026-01-01T00:00Z", "competitions": [{}]},
                            "soccer", "eng.1", "PL") is None
