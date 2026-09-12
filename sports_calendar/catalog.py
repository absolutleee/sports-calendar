"""Maps a rule's `source` to the right adapter call for today's date."""
from __future__ import annotations

import logging
from datetime import date

from sports_calendar import seasons
from sports_calendar.models import Game
from sports_calendar.sources import espn, mlb, nhl

log = logging.getLogger(__name__)


class Catalog:
    def __init__(self, today: date):
        self.today = today

    def team_games(self, rule: dict) -> list[Game]:
        source = rule["source"]
        team = str(rule["team"])
        if source == "espn_soccer":
            return espn.soccer_team_schedule(team)
        if source == "espn":
            season = seasons.nfl_season(self.today) if rule.get("sport") == "football" else seasons.espn_season(self.today)
            return espn.us_team_schedule(rule["sport"], rule["league"], team, season)
        if source == "mlb":
            games: list[Game] = []
            for season in seasons.mlb_seasons(self.today):
                games += mlb.team_schedule(team, season)
            return games
        if source == "nhl":
            return nhl.club_schedule(team, seasons.nhl_season_id(self.today))
        raise ValueError(f"unknown team source {source!r} in rule {rule.get('name')!r}")

    def competition_games(self, rule: dict) -> list[Game]:
        source = rule["source"]
        if source == "nhl":
            return nhl.stanley_cup_final(seasons.nhl_season_id(self.today))
        start, end = seasons.window(self.today, *rule["window"])
        if source == "espn_soccer":
            return espn.scoreboard("soccer", rule["league"], start, end)
        if source == "espn":
            return espn.scoreboard(rule["sport"], rule["league"], start, end)
        raise ValueError(f"unknown competition source {source!r} in rule {rule.get('name')!r}")

    def game_season_year(self, game: Game) -> int:
        """The season a game belongs to. Football seasons span into Jan/Feb, so a
        January game still belongs to the previous calendar year's season."""
        if game.sport == "football":
            return game.day.year if game.day.month >= 3 else game.day.year - 1
        return game.day.year

    def eliminated(self, rule: dict, season_year: int) -> bool:
        """Is the rule's team mathematically out of the `season_year` postseason?
        Only baseball (MLB) and football (ESPN/NFL) expose this today."""
        source = rule["source"]
        if source == "mlb":
            return mlb.eliminated(str(rule["team"]), season_year)
        if source == "espn" and rule.get("sport") == "football":
            return espn.us_eliminated(rule["sport"], rule["league"], str(rule["team"]), season_year)
        log.warning("until_eliminated is not supported for source %r (rule %r); ignoring it",
                    source, rule.get("name"))
        return False

    def golf_calendar(self, tour: str) -> list[dict]:
        return espn.golf_calendar(tour)

    def tennis_majors(self) -> list[espn.Major]:
        majors: list[espn.Major] = []
        for year in seasons.tennis_years(self.today):
            majors += espn.tennis_majors(year)
        return majors
