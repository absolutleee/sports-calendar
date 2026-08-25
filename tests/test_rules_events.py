from datetime import date

from sports_calendar import rules
from sports_calendar.sources.espn import Major
from tests.test_rules import ARS, COL, DAL, DU, AF, FakeCatalog, LIV, METS, NEW, RMA, ROX, mk


def test_golf_event():
    cat = FakeCatalog(golf=[{"id": "1", "label": "Valero Texas Open", "start": date(2026, 4, 2), "end": date(2026, 4, 5)},
                            {"id": "401811941", "label": "Masters Tournament", "start": date(2026, 4, 9), "end": date(2026, 4, 12)}])
    out = rules.evaluate({"name": "Masters", "type": "golf_event", "tour": "pga", "label": "Masters Tournament",
                          "title": "The Masters"}, cat)
    assert len(out) == 1
    e = out[0]
    assert e.uid == "espn-golf-401811941" and e.title == "The Masters"
    assert e.start == date(2026, 4, 9) and e.end == date(2026, 4, 13)


def test_grand_slams_with_draw_and_fallback():
    wim = Major(id="w", name="Wimbledon", start=date(2026, 6, 22), end=date(2026, 7, 12),
                round_dates={"Round 1": [date(2026, 6, 29), date(2026, 6, 30)],
                             "Semifinal": [date(2026, 7, 10)], "Final": [date(2026, 7, 12)]})
    ao = Major(id="a", name="Australian Open", start=date(2026, 1, 11), end=date(2026, 2, 1),
               round_dates={"Round 1": [date(2026, 1, 18), date(2026, 1, 19)],
                            "Semifinal": [date(2026, 1, 29), date(2026, 1, 30)], "Final": [date(2026, 2, 1)]})
    uso = Major(id="u", name="US Open", start=date(2026, 8, 24), end=date(2026, 9, 13), round_dates={})
    cat = FakeCatalog(majors=[ao, wim, uso])
    out = rules.evaluate({"name": "Slams", "type": "grand_slams"}, cat)
    by_title = {e.title: e for e in out}
    assert by_title["Wimbledon Day 1"].start == date(2026, 6, 29)
    assert by_title["Wimbledon Men's Semifinals"].start == date(2026, 7, 10)
    assert by_title["Wimbledon Men's Final"].start == date(2026, 7, 12)
    assert by_title["Wimbledon Men's Final"].end == date(2026, 7, 13)
    # AO Round 1 begins Sunday → Day 1 is the Monday; two semifinal days → two events
    assert by_title["Australian Open Day 1"].start == date(2026, 1, 19)
    ao_sf = sorted(e.start for e in out if e.title == "Australian Open Men's Semifinals")
    assert ao_sf == [date(2026, 1, 29), date(2026, 1, 30)]
    # US Open has no draw yet → derived from end date
    assert by_title["US Open Men's Final"].start == date(2026, 9, 13)
    assert by_title["US Open Men's Semifinals"].start == date(2026, 9, 11)
    assert by_title["US Open Day 1"].start == date(2026, 8, 31)
    assert len({e.uid for e in out}) == len(out)


def test_context_soccer():
    assert rules.context_for(mk("a", LIV, NEW, date(2026, 8, 29))) is None
    assert rules.context_for(mk("a", LIV, NEW, date(2026, 8, 29), comp="club.friendly", comp_name="Club Friendly")) == "Friendly"
    assert rules.context_for(mk("a", LIV, NEW, date(2026, 8, 29), comp="eng.fa", comp_name="English FA Cup")) == "FA Cup"
    assert rules.context_for(mk("a", LIV, NEW, date(2026, 8, 29), comp="uefa.champions", round_slug="league-phase")) == "UCL"
    assert rules.context_for(mk("a", ARS, RMA, date(2026, 5, 5), comp="uefa.champions", round_slug="semifinals",
                                notes="2nd Leg - Arsenal advance 2-1 on aggregate")) == "UCL Semifinal 2nd Leg"
    assert rules.context_for(mk("a", ARS, RMA, date(2026, 5, 30), comp="uefa.champions", round_slug="final")) == "UCL Final"
    assert rules.context_for(mk("a", ARS, RMA, date(2026, 5, 23), comp="eng.2", round_slug="promotion-final")) == "Championship Play-off Final"
    assert rules.context_for(mk("a", ARS, RMA, date(2026, 5, 9), comp="eng.2", round_slug="promotion-semifinals", notes="1st Leg")) == "Championship Play-off Semifinal 1st Leg"
    assert rules.context_for(mk("a", ARS, RMA, date(2026, 6, 11), comp="fifa.world", round_slug="group-stage")) == "World Cup"
    assert rules.context_for(mk("a", ARS, RMA, date(2026, 7, 19), comp="fifa.world", round_slug="final")) == "World Cup Final"
    # unknown non-domestic competition falls back to ESPN's name
    assert rules.context_for(mk("a", LIV, NEW, date(2026, 8, 29), comp="xyz.cup", comp_name="Mystery Cup")) == "Mystery Cup"


def test_context_us_sports():
    nhl = mk("a", COL, DAL, date(2027, 4, 20), sport="hockey", comp="nhl", comp_name="NHL", season_type="post",
             series_title="1st Round", series_game=3)
    assert rules.context_for(nhl) == "1st Round G3"
    scf = mk("a", COL, DAL, date(2027, 6, 5), sport="hockey", comp="nhl", comp_name="NHL", season_type="post",
             series_title="Stanley Cup Final", series_game=2)
    assert rules.context_for(scf) == "Stanley Cup Final G2"
    nba = mk("a", COL, DAL, date(2027, 6, 5), sport="basketball", comp="nba", comp_name="NBA", season_type="post",
             notes="NBA Finals - Game 4")
    assert rules.context_for(nba) == "NBA Finals G4"
    nba1 = mk("a", COL, DAL, date(2027, 4, 20), sport="basketball", comp="nba", comp_name="NBA", season_type="post",
              notes="West 1st Round - Game 1")
    assert rules.context_for(nba1) == "West 1st Round G1"
    mlb = mk("a", METS, ROX, date(2026, 10, 24), sport="baseball", comp="mlb", comp_name="MLB", season_type="post",
             series_title="World Series", series_game=1)
    assert rules.context_for(mlb) == "World Series G1"
    ncaa = mk("a", DU, AF, date(2026, 3, 27), sport="hockey", comp="mens-college-hockey", comp_name="NCAA Hockey",
              season_type="post", notes="NCAA Men's Hockey Championship - Loveland Regional Semifinal")
    assert rules.context_for(ncaa) == "NCAA Loveland Regional Semifinal"
    natty = mk("a", DU, AF, date(2026, 4, 11), sport="hockey", comp="mens-college-hockey", comp_name="NCAA Hockey",
               season_type="post", notes="NCAA Men's Hockey National Championship")
    assert rules.context_for(natty) == "NCAA Championship"
    bare = mk("a", DU, AF, date(2026, 3, 20), sport="hockey", comp="mens-college-hockey", comp_name="NCAA Hockey",
              season_type="post")
    assert rules.context_for(bare) == "Playoffs"
    regular = mk("a", COL, DAL, date(2026, 10, 8), sport="hockey", comp="nhl", comp_name="NHL")
    assert rules.context_for(regular) is None
    regular.context = "Season Opener"
    assert rules.context_for(regular) == "Season Opener"


def test_apply_rules_annotates_context():
    g = mk("a", ARS, RMA, date(2026, 5, 30), comp="uefa.champions", round_slug="final")
    cat = FakeCatalog(competition_games=[g])
    games, _ = rules.apply_rules([{"name": "UCL", "type": "round", "source": "espn_soccer", "league": "uefa.champions",
                                   "window": ["04-01", "06-15"], "rounds": ["final"]}], cat)
    assert games[0].context == "UCL Final"
