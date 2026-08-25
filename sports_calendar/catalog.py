"""Maps a rule's `source` to the right adapter call for today's date."""
from __future__ import annotations

from datetime import date

from sports_calendar import seasons
from sports_calendar.models import Game
from sports_calendar.sources import espn, mlb, nhl


class Catalog:
    def __init__(self, today: date):
        self.today = today

    def team_games(self, rule: dict) -> list[Game]:
        source = rule["source"]
        team = str(rule["team"])
        if source == "espn_soccer":
            return espn.soccer_team_schedule(team)
        if source == "espn":
            return espn.us_team_schedule(rule["sport"], rule["league"], team, seasons.espn_season(self.today))
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

    def golf_calendar(self, tour: str) -> list[dict]:
        return espn.golf_calendar(tour)

    def tennis_majors(self) -> list[espn.Major]:
        majors: list[espn.Major] = []
        for year in seasons.tennis_years(self.today):
            majors += espn.tennis_majors(year)
        return majors
