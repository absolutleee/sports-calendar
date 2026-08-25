from datetime import date, datetime, timezone

import pytest

from sports_calendar import rules
from sports_calendar.models import Game, Team

LIV = Team("364", "Liverpool", "Liverpool")
NEW = Team("361", "Newcastle United", "Newcastle")
RMA = Team("86", "Real Madrid", "Real Madrid")
BAR = Team("83", "Barcelona", "Barcelona")
ARS = Team("359", "Arsenal", "Arsenal")
CHE = Team("363", "Chelsea", "Chelsea")
MCI = Team("382", "Manchester City", "Man City")
DU = Team("2172", "Denver Pioneers", "Denver")
AF = Team("2160", "Air Force Falcons", "Air Force")
METS = Team("121", "New York Mets", "Mets")
ROX = Team("115", "Colorado Rockies", "Rockies")
COL = Team("COL", "Colorado Avalanche", "Avalanche")
DAL = Team("DAL", "Dallas Stars", "Stars")


def mk(uid, home, away, day, *, sport="soccer", comp="eng.1", comp_name="Premier League", **over):
    g = Game(uid=uid, sport=sport, competition=comp, competition_name=comp_name, home=home, away=away,
             day=day, start=datetime(day.year, day.month, day.day, 19, 0, tzinfo=timezone.utc))
    for k, v in over.items():
        setattr(g, k, v)
    return g


class FakeCatalog:
    def __init__(self, team_games=None, competition_games=None, golf=None, majors=None):
        self._team = team_games or {}
        self._comp = competition_games or []
        self._golf = golf or []
        self._majors = majors or []
        self.team_calls = []

    def team_games(self, rule):
        self.team_calls.append(str(rule["team"]))
        return self._team.get(str(rule["team"]), [])

    def competition_games(self, rule):
        return self._comp

    def golf_calendar(self, tour):
        return self._golf

    def tennis_majors(self):
        return self._majors


def test_team_all_with_competition_filter():
    games = [mk("a", LIV, NEW, date(2026, 8, 29)), mk("b", NEW, LIV, date(2026, 9, 5), comp="uefa.champions")]
    cat = FakeCatalog({"364": games})
    assert [g.uid for g in rules.evaluate({"name": "LFC", "type": "team_all", "source": "espn_soccer", "team": 364}, cat)] == ["a", "b"]
    out = rules.evaluate({"name": "LFC UCL", "type": "team_all", "source": "espn_soccer", "team": 364,
                          "competitions": ["uefa.champions"]}, cat)
    assert [g.uid for g in out] == ["b"]


def test_head_to_head_filters_opponents_competition_and_only_away():
    games = [
        mk("liga", BAR, RMA, date(2026, 10, 25), comp="esp.1"),
        mk("copa", RMA, BAR, date(2027, 1, 20), comp="esp.copa_del_rey"),
        mk("other", BAR, NEW, date(2026, 11, 1), comp="esp.1"),
    ]
    cat = FakeCatalog({"83": games})
    rule = {"name": "Clasico", "type": "head_to_head", "source": "espn_soccer", "team": 83,
            "opponents": [86], "competitions": ["esp.1"]}
    assert [g.uid for g in rules.evaluate(rule, cat)] == ["liga"]
    rule.pop("competitions")
    assert [g.uid for g in rules.evaluate(rule, cat)] == ["liga", "copa"]

    mets = [mk("home", METS, ROX, date(2026, 5, 1), sport="baseball", comp="mlb", comp_name="MLB"),
            mk("away", ROX, METS, date(2026, 6, 1), sport="baseball", comp="mlb", comp_name="MLB")]
    cat = FakeCatalog({"121": mets})
    rule = {"name": "Coors", "type": "head_to_head", "source": "mlb", "team": 121, "opponents": [115], "only_away": True}
    assert [g.uid for g in rules.evaluate(rule, cat)] == ["away"]


def test_group_h2h_fetches_each_team_and_dedupes():
    ars_che = mk("ac", ARS, CHE, date(2026, 9, 1))
    che_mci = mk("cm", CHE, MCI, date(2026, 10, 1))
    ars_new = mk("an", ARS, NEW, date(2026, 9, 8))
    che_cup = mk("cup", CHE, ARS, date(2026, 12, 1), comp="eng.league_cup")
    cat = FakeCatalog({"359": [ars_che, ars_new, che_cup], "363": [ars_che, che_mci, che_cup], "382": [che_mci]})
    rule = {"name": "Big four", "type": "group_h2h", "source": "espn_soccer", "teams": [359, 363, 382],
            "competitions": ["eng.1"]}
    out = rules.evaluate(rule, cat)
    assert sorted(g.uid for g in out) == ["ac", "cm"]
    assert sorted(cat.team_calls) == ["359", "363", "382"]


def test_opener_per_sport():
    avs = [mk("pre", DAL, COL, date(2026, 9, 25), sport="hockey", comp="nhl", comp_name="NHL", season_type="pre"),
           mk("op", COL, DAL, date(2026, 10, 8), sport="hockey", comp="nhl", comp_name="NHL"),
           mk("g2", DAL, COL, date(2026, 10, 10), sport="hockey", comp="nhl", comp_name="NHL")]
    cat = FakeCatalog({"COL": avs})
    out = rules.evaluate({"name": "Avs opener", "type": "opener", "source": "nhl", "team": "COL"}, cat)
    assert [g.uid for g in out] == ["op"] and out[0].context == "Season Opener"

    mets = [mk("26", METS, ROX, date(2026, 3, 26), sport="baseball", comp="mlb", comp_name="MLB"),
            mk("26b", METS, ROX, date(2026, 3, 27), sport="baseball", comp="mlb", comp_name="MLB"),
            mk("27", ROX, METS, date(2027, 3, 30), sport="baseball", comp="mlb", comp_name="MLB")]
    cat = FakeCatalog({"121": mets})
    out = rules.evaluate({"name": "Mets opener", "type": "opener", "source": "mlb", "team": 121}, cat)
    assert [g.uid for g in out] == ["26", "27"] and out[0].context == "Opening Day"


def test_home_games_excludes_away_and_neutral():
    games = [mk("home", DU, AF, date(2025, 10, 11), sport="hockey", comp="mens-college-hockey", comp_name="NCAA Hockey"),
             mk("away", AF, DU, date(2025, 10, 12), sport="hockey", comp="mens-college-hockey", comp_name="NCAA Hockey"),
             mk("neutral", DU, AF, date(2025, 12, 1), sport="hockey", comp="mens-college-hockey", comp_name="NCAA Hockey", neutral=True)]
    cat = FakeCatalog({"2172": games})
    out = rules.evaluate({"name": "DU home", "type": "home_games", "source": "espn", "sport": "hockey",
                          "league": "mens-college-hockey", "team": 2172}, cat)
    assert [g.uid for g in out] == ["home"]


def test_postseason():
    games = [mk("r", COL, DAL, date(2027, 4, 1), sport="hockey", comp="nhl", comp_name="NHL"),
             mk("p", COL, DAL, date(2027, 4, 20), sport="hockey", comp="nhl", comp_name="NHL", season_type="post")]
    cat = FakeCatalog({"COL": games})
    out = rules.evaluate({"name": "Avs playoffs", "type": "postseason", "source": "nhl", "team": "COL"}, cat)
    assert [g.uid for g in out] == ["p"]


def test_round_tournament_all_and_finals():
    comp = [mk("qf", ARS, RMA, date(2026, 4, 8), comp="uefa.champions", round_slug="quarterfinals"),
            mk("lp", ARS, RMA, date(2026, 1, 8), comp="uefa.champions", round_slug="league-phase"),
            mk("f", ARS, RMA, date(2026, 5, 30), comp="uefa.champions", round_slug="final")]
    cat = FakeCatalog(competition_games=comp)
    out = rules.evaluate({"name": "UCL KO", "type": "round", "source": "espn_soccer", "league": "uefa.champions",
                          "window": ["04-01", "06-15"], "rounds": ["quarterfinals", "semifinals", "final"]}, cat)
    assert sorted(g.uid for g in out) == ["f", "qf"]
    out = rules.evaluate({"name": "WC", "type": "tournament_all", "source": "espn_soccer", "league": "fifa.world",
                          "window": ["06-01", "07-31"]}, cat)
    assert len(out) == 3

    nba = [mk("wcf", ARS, RMA, date(2026, 5, 20), sport="basketball", comp="nba", comp_name="NBA",
              season_type="post", notes="West Finals - Game 1"),
           mk("fin", ARS, RMA, date(2026, 6, 4), sport="basketball", comp="nba", comp_name="NBA",
              season_type="post", notes="NBA Finals - Game 1")]
    cat = FakeCatalog(competition_games=nba)
    out = rules.evaluate({"name": "NBA Finals", "type": "finals", "source": "espn", "sport": "basketball",
                          "league": "nba", "window": ["05-25", "06-30"], "notes_prefix": "NBA Finals"}, cat)
    assert [g.uid for g in out] == ["fin"]
    cat = FakeCatalog(competition_games=nba)
    out = rules.evaluate({"name": "SCF", "type": "finals", "source": "nhl"}, cat)
    assert len(out) == 2  # nhl source already returns only final games


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        rules.evaluate({"name": "x", "type": "nope", "source": "nhl"}, FakeCatalog())


def test_apply_rules_dedupes_and_merges_rule_names():
    g = mk("a", LIV, NEW, date(2026, 8, 29))
    cat = FakeCatalog({"364": [g], "361": [g]})
    games, alldays = rules.apply_rules([
        {"name": "LFC", "type": "team_all", "source": "espn_soccer", "team": 364},
        {"name": "NUFC", "type": "team_all", "source": "espn_soccer", "team": 361},
    ], cat)
    assert len(games) == 1 and games[0].matched_rules == ["LFC", "NUFC"]
    assert alldays == []
