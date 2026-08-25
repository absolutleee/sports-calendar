from datetime import date

from sports_calendar.catalog import Catalog


def test_team_games_dispatch(fake_fetch):
    calls = fake_fetch([
        (("soccer/all/teams/364/schedule", "fixture=true"), "espn_liverpool_fixtures.json"),
        ("soccer/all/teams/364/schedule", "espn_liverpool_results.json"),
        (("basketball/nba/teams/7/schedule", "season=2027", "seasontype=2"), "espn_nuggets_2026_27_reg.json"),
        (("basketball/nba/teams/7/schedule", "season=2027", "seasontype=3"), {"events": []}),
        (("statsapi.mlb.com", "season=2026"), "mlb_mets_2026.json"),
        (("statsapi.mlb.com", "season=2027"), {"dates": []}),
        ("club-schedule-season/COL/20262027", "nhl_col_2026_27.json"),
    ])
    cat = Catalog(today=date(2026, 8, 25))
    assert len(cat.team_games({"source": "espn_soccer", "team": 364})) == 44
    assert len(cat.team_games({"source": "espn", "sport": "basketball", "league": "nba", "team": 7})) == 80
    assert len(cat.team_games({"source": "mlb", "team": 121})) == 162
    assert len(cat.team_games({"source": "nhl", "team": "COL"})) == 88
    assert len(calls) == 7


def test_competition_games_dispatch(fake_fetch):
    calls = fake_fetch([
        ("uefa.champions/scoreboard", "espn_ucl_2025_26.json"),
        ("nba/scoreboard", "espn_nba_june_2026.json"),
        ("playoff-bracket/2026", "nhl_bracket_2026.json"),
        ("playoff-series/20252026/o/", "nhl_series_scf_2026.json"),
    ])
    cat = Catalog(today=date(2026, 5, 15))
    ucl = cat.competition_games({"source": "espn_soccer", "league": "uefa.champions", "window": ["04-01", "06-15"]})
    assert len(ucl) == 189
    assert "dates=20260401-20260615" in calls[0]
    nba = cat.competition_games({"source": "espn", "sport": "basketball", "league": "nba", "window": ["05-25", "06-30"]})
    assert len(nba) == 5
    assert "dates=20260525-20260630" in calls[1]
    scf = cat.competition_games({"source": "nhl"})
    assert scf[0].series_title == "Stanley Cup Final"


def test_golf_and_tennis(fake_fetch):
    fake_fetch([
        ("golf/pga/scoreboard", "espn_pga_scoreboard.json"),
        (("tennis/atp/scoreboard", "dates=202607"), "espn_tennis_wimbledon_2026.json"),
        ("tennis/atp/scoreboard", {"events": []}),
    ])
    cat = Catalog(today=date(2026, 8, 25))
    assert any(e["label"] == "Masters Tournament" for e in cat.golf_calendar("pga"))
    assert [m.name for m in cat.tennis_majors()] == ["Wimbledon"]
