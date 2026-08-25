from datetime import date

from sports_calendar.sources import espn


def test_golf_calendar(fake_fetch):
    fake_fetch([("golf/pga/scoreboard", "espn_pga_scoreboard.json")])
    entries = espn.golf_calendar("pga")
    masters = [e for e in entries if e["label"] == "Masters Tournament"]
    assert masters == [{"id": "401811941", "label": "Masters Tournament",
                        "start": date(2026, 4, 9), "end": date(2026, 4, 12)}]


def test_tennis_majors_dedupes_and_extracts_rounds(fake_fetch):
    calls = fake_fetch([
        (("tennis/atp/scoreboard", "dates=202601"), "espn_tennis_ao_2026.json"),
        (("tennis/atp/scoreboard", "dates=202607"), "espn_tennis_wimbledon_2026.json"),
        (("tennis/atp/scoreboard", "dates=202609"), "espn_tennis_usopen_2026.json"),
        ("tennis/atp/scoreboard", {"events": []}),
    ])
    majors = espn.tennis_majors(2026)
    assert len(calls) == len(espn.TENNIS_PROBE_DATES)
    names = [m.name for m in majors]
    assert names == ["Australian Open", "Wimbledon", "US Open"]

    ao = majors[0]
    assert ao.start == date(2026, 1, 11)
    assert ao.end == date(2026, 2, 1)
    assert min(ao.round_dates["Round 1"]) == date(2026, 1, 18)
    assert set(ao.round_dates["Semifinal"]) == {date(2026, 1, 30)}
    assert ao.round_dates["Final"] == [date(2026, 2, 1)]

    wim = majors[1]
    assert wim.end == date(2026, 7, 12)
    assert min(wim.round_dates["Round 1"]) == date(2026, 6, 29)
    assert wim.round_dates["Final"] == [date(2026, 7, 12)]

    uso = majors[2]
    assert uso.end == date(2026, 9, 13)
    # ESPN publishes provisional round dates before the draw: Round 1 on the Sunday
    assert min(uso.round_dates["Round 1"]) == date(2026, 8, 30)
    assert uso.round_dates["Final"] == [date(2026, 9, 13)]
