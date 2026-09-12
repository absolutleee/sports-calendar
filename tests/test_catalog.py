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


def test_football_uses_nfl_start_year_and_elimination_dispatch(fake_fetch):
    calls = fake_fetch([
        (("football/nfl/teams/19/schedule", "season=2026", "seasontype=2"), {"events": []}),
        (("football/nfl/teams/19/schedule", "season=2026", "seasontype=3"), {"events": []}),
        (("football/nfl/standings", "season=2026"), "espn_nfl_standings_2024.json"),
    ])
    cat = Catalog(today=date(2026, 9, 11))
    rule = {"source": "espn", "sport": "football", "league": "nfl", "team": 19}
    cat.team_games(rule)                       # must request season=2026 (start year), not 2027
    assert any("season=2026" in c and "football/nfl/teams/19" in c for c in calls)
    assert not any("season=2027" in c for c in calls)
    assert cat.eliminated(rule, 2026) is True  # Giants clincher 'e' in fixture


def test_eliminated_dispatch_mlb(fake_fetch):
    fake_fetch([(("statsapi.mlb.com/api/v1/standings", "season=2026"), "mlb_standings_2026.json")])
    cat = Catalog(today=date(2026, 9, 11))
    assert cat.eliminated({"source": "mlb", "team": 121}, 2026) is True


def test_eliminated_unsupported_source_fails_open():
    cat = Catalog(today=date(2026, 9, 11))
    assert cat.eliminated({"source": "nhl", "team": "COL", "name": "Avs"}, 2026) is False


def test_game_season_year():
    from sports_calendar.models import Game, Team
    cat = Catalog(today=date(2026, 9, 11))

    def g(sport, day):
        return Game(uid="x", sport=sport, competition="c", competition_name="C",
                    home=Team("1", "H", "H"), away=Team("2", "A", "A"), day=day)

    assert cat.game_season_year(g("baseball", date(2026, 9, 20))) == 2026
    assert cat.game_season_year(g("football", date(2026, 11, 1))) == 2026
    assert cat.game_season_year(g("football", date(2027, 1, 4))) == 2026  # Week 18 in January
