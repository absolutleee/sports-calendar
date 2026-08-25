"""Official MLB Stats API → Game. No key required."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sports_calendar import http
from sports_calendar.models import Game, Team

log = logging.getLogger(__name__)

BASE = "https://statsapi.mlb.com/api/v1/schedule"
GAME_TYPES = "R,F,D,L,W"  # regular, wild card, division, league championship, world series
SEASON_TYPES = {"S": "pre", "R": "regular", "F": "post", "D": "post", "L": "post", "W": "post"}
SKIP_STATES = ("Postponed", "Cancelled", "Canceled")


def _team(entry: dict) -> Team:
    t = entry["team"]
    name = t.get("name") or str(t["id"])
    return Team(id=str(t["id"]), name=name, short=t.get("teamName") or name)


def parse_game(g: dict) -> Game | None:
    try:
        status = g.get("status") or {}
        if any(status.get("detailedState", "").startswith(s) for s in SKIP_STATES):
            return None
        start = datetime.fromisoformat(g["gameDate"].replace("Z", "+00:00")).astimezone(timezone.utc)
        day = date.fromisoformat(g["officialDate"]) if g.get("officialDate") else start.date()
        home = _team(g["teams"]["home"])
        away = _team(g["teams"]["away"])
    except (KeyError, ValueError) as exc:
        log.warning("skipping malformed MLB game %s: %s", g.get("gamePk"), exc)
        return None

    tv = [b.get("name") for b in g.get("broadcasts", []) or [] if b.get("type") == "TV" and b.get("name")]
    season_type = SEASON_TYPES.get(g.get("gameType", "R"), "regular")
    return Game(
        uid=f"mlb-{g['gamePk']}",
        sport="baseball",
        competition="mlb",
        competition_name="MLB",
        home=home,
        away=away,
        day=day,
        start=start,
        time_valid=not status.get("startTimeTBD", False),
        venue=(g.get("venue") or {}).get("name"),
        broadcast=", ".join(dict.fromkeys(tv)) or None,
        season_type=season_type,
        round_slug=g.get("gameType"),
        series_title=g.get("seriesDescription") if season_type == "post" else None,
        series_game=g.get("seriesGameNumber") if season_type == "post" else None,
    )


def team_schedule(team_id: str, season: int) -> list[Game]:
    params = {"teamId": team_id, "season": season, "sportId": 1, "gameType": GAME_TYPES,
              "hydrate": "team,broadcasts(all)"}
    try:
        data = http.get_json(BASE, params)
    except http.NotFound:
        return []
    games = []
    for d in data.get("dates", []) or []:
        for g in d.get("games", []) or []:
            parsed = parse_game(g)
            if parsed:
                games.append(parsed)
    return sorted(games, key=Game.sort_key)
