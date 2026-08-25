from datetime import date

from sports_calendar import seasons


def test_season_end_year():
    assert seasons.season_end_year(date(2026, 8, 25)) == 2027
    assert seasons.season_end_year(date(2026, 7, 1)) == 2027
    assert seasons.season_end_year(date(2026, 6, 30)) == 2026
    assert seasons.season_end_year(date(2027, 1, 15)) == 2027


def test_nhl_season_id():
    assert seasons.nhl_season_id(date(2026, 8, 25)) == "20262027"
    assert seasons.nhl_season_id(date(2026, 5, 15)) == "20252026"


def test_mlb_seasons():
    assert seasons.mlb_seasons(date(2026, 8, 25)) == [2026, 2027]


def test_espn_season():
    assert seasons.espn_season(date(2026, 8, 25)) == 2027
    assert seasons.espn_season(date(2026, 4, 1)) == 2026


def test_window_resolves_in_season_end_year():
    assert seasons.window(date(2026, 8, 25), "04-01", "06-15") == (date(2027, 4, 1), date(2027, 6, 15))
    assert seasons.window(date(2026, 5, 15), "04-01", "06-15") == (date(2026, 4, 1), date(2026, 6, 15))


def test_tennis_years():
    assert seasons.tennis_years(date(2026, 8, 25)) == [2026]
    assert seasons.tennis_years(date(2026, 11, 2)) == [2026, 2027]
