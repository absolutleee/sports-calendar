from tests.conftest import FIXTURES

EXPECTED = [
    "espn_liverpool_fixtures.json", "espn_liverpool_results.json",
    "espn_barcelona_fixtures.json", "espn_arsenal_fixtures.json",
    "espn_ucl_2025_26.json", "espn_uel_may_2026.json", "espn_eng2_playoffs_2026.json",
    "espn_worldcup_2026.json", "espn_nuggets_2026_27_reg.json", "espn_nuggets_2025_26_post.json",
    "espn_nba_june_2026.json", "espn_denver_hockey_2025_26.json",
    "nhl_col_2025_26.json", "nhl_col_2026_27.json", "nhl_nyr_2026_27.json",
    "nhl_bracket_2026.json", "nhl_series_scf_2026.json",
    "mlb_mets_2026.json", "espn_pga_scoreboard.json",
    "espn_tennis_wimbledon_2026.json", "espn_tennis_ao_2026.json", "espn_tennis_usopen_2026.json",
]


def test_fixtures_present():
    missing = [f for f in EXPECTED if not (FIXTURES / f).exists()]
    assert missing == []


def test_fixture_loader(fixture):
    data = fixture("espn_liverpool_fixtures.json")
    assert len(data["events"]) == 37
