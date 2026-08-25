from datetime import date
from pathlib import Path

from icalendar import Calendar

from sports_calendar import main

E2E_MAPPING = [
    (("soccer/all/teams/364/schedule", "fixture=true"), "espn_liverpool_fixtures.json"),
    ("soccer/all/teams/364/schedule", "espn_liverpool_results.json"),
    (("soccer/all/teams/83/schedule", "fixture=true"), "espn_barcelona_fixtures.json"),
    (("soccer/all/teams/359/schedule", "fixture=true"), "espn_arsenal_fixtures.json"),
    ("uefa.champions/scoreboard", "espn_ucl_2025_26.json"),
    ("uefa.europa/scoreboard", "espn_uel_may_2026.json"),
    ("eng.2/scoreboard", "espn_eng2_playoffs_2026.json"),
    ("fifa.world/scoreboard", "espn_worldcup_2026.json"),
    (("mens-college-hockey/teams/2172/schedule", "seasontype=2"), "espn_denver_hockey_2025_26.json"),
    (("basketball/nba/teams/7/schedule", "seasontype=2"), "espn_nuggets_2026_27_reg.json"),
    (("basketball/nba/teams/7/schedule", "seasontype=3"), "espn_nuggets_2025_26_post.json"),
    ("basketball/nba/scoreboard", "espn_nba_june_2026.json"),
    (("statsapi.mlb.com", "season=2026"), "mlb_mets_2026.json"),
    ("statsapi.mlb.com", {"dates": []}),
    ("club-schedule-season/COL/", "nhl_col_2025_26.json"),
    ("club-schedule-season/NYR/", "nhl_nyr_2026_27.json"),
    ("playoff-bracket/2026", "nhl_bracket_2026.json"),
    ("playoff-series/20252026/o/", "nhl_series_scf_2026.json"),
    ("golf/pga/scoreboard", "espn_pga_scoreboard.json"),
    (("tennis/atp/scoreboard", "dates=202601"), "espn_tennis_ao_2026.json"),
    (("tennis/atp/scoreboard", "dates=202607"), "espn_tennis_wimbledon_2026.json"),
    (("tennis/atp/scoreboard", "dates=202609"), "espn_tennis_usopen_2026.json"),
    ("tennis/atp/scoreboard", {"events": []}),
    ("/schedule", {"events": []}),  # any other team: no games
]


def test_end_to_end(fake_fetch, tmp_path):
    fake_fetch(E2E_MAPPING)
    out = tmp_path / "sports.ics"
    code = main.run(Path("config.yaml"), out, today=date(2026, 5, 15))
    assert code == 0
    cal = Calendar.from_ical(out.read_bytes())
    events = {str(e["SUMMARY"]): e for e in cal.walk("VEVENT")}
    summaries = list(events)

    assert sum(s.startswith("Liverpool ") or " Liverpool" in s for s in summaries) >= 40
    assert "Liverpool Nottm Forest" in events
    assert "PSG Arsenal · UCL Final" in events
    assert any("Championship Play-off Final" in s for s in summaries)
    assert "Pirates Mets · Opening Day" in events
    assert "Golden Knights Hurricanes · Stanley Cup Final G1" in events
    assert "Knicks Spurs · NBA Finals G1" in events
    assert any(s.endswith("· Season Opener") and "Avs" in s for s in summaries)
    assert any("Avs" in s and "1st Round G1" in s for s in summaries)
    assert any(s.endswith(" Denver") for s in summaries)

    masters = events["The Masters"]
    assert masters["DTSTART"].dt == date(2026, 4, 9) and masters["DTEND"].dt == date(2026, 4, 13)
    assert events["Wimbledon Men's Final"]["DTSTART"].dt == date(2026, 7, 12)
    assert events["Wimbledon Day 1"]["DTSTART"].dt == date(2026, 6, 29)
    assert events["Australian Open Day 1"]["DTSTART"].dt == date(2026, 1, 19)
    assert events["US Open Men's Final"]["DTSTART"].dt == date(2026, 9, 13)
    assert events["US Open Day 1"]["DTSTART"].dt == date(2026, 8, 31)  # Sunday start → first Monday

    for s in summaries:
        assert " vs " not in s and " @ " not in s
        assert "Manchester" not in s and "Avalanche" not in s
    assert "VALARM" not in out.read_text()


def test_run_fails_cleanly_on_fetch_error(monkeypatch, tmp_path):
    from sports_calendar import http

    def boom(*a, **k):
        raise http.FetchError("down")

    monkeypatch.setattr(http, "get_json", boom)
    out = tmp_path / "sports.ics"
    assert main.run(Path("config.yaml"), out, today=date(2026, 5, 15)) == 1
    assert not out.exists()
