"""Official NHL web API → Game. No key required."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sports_calendar import http
from sports_calendar.models import Game, Team

log = logging.getLogger(__name__)

BASE = "https://api-web.nhle.com/v1"
SEASON_TYPES = {1: "pre", 2: "regular", 3: "post"}
SKIP_STATES = ("PPD", "CNCL")


def _team(t: dict) -> Team:
    common = (t.get("commonName") or {}).get("default") or t["abbrev"]
    place = (t.get("placeName") or {}).get("default")
    return Team(id=t["abbrev"], name=f"{place} {common}" if place else common, short=common)


def _broadcast(g: dict) -> str | None:
    us = [b for b in g.get("tvBroadcasts", []) or [] if b.get("countryCode") == "US" and b.get("network")]
    us.sort(key=lambda b: (0 if b.get("market") == "N" else 1, b.get("sequenceNumber", 0)))
    return ", ".join(dict.fromkeys(b["network"] for b in us)) or None


def parse_game(g: dict, *, default_round: int | None = None, default_title: str | None = None) -> Game | None:
    try:
        if g.get("gameScheduleState") in SKIP_STATES:
            return None
        start = datetime.fromisoformat(g["startTimeUTC"].replace("Z", "+00:00")).astimezone(timezone.utc)
        day = date.fromisoformat(g["gameDate"]) if g.get("gameDate") else start.date()
        home = _team(g["homeTeam"])
        away = _team(g["awayTeam"])
    except (KeyError, ValueError) as exc:
        log.warning("skipping malformed NHL game %s: %s", g.get("id"), exc)
        return None

    series = g.get("seriesStatus") or {}
    season_type = SEASON_TYPES.get(g.get("gameType"), "regular")
    series_round = series.get("round") or default_round
    series_title = series.get("seriesTitle") or default_title
    round_slug = series.get("seriesAbbrev") or ("SCF" if series_round == 4 else None)
    return Game(
        uid=f"nhl-{g['id']}",
        sport="hockey",
        competition="nhl",
        competition_name="NHL",
        home=home,
        away=away,
        day=day,
        start=start,
        time_valid=g.get("gameScheduleState") != "TBD",
        venue=(g.get("venue") or {}).get("default"),
        neutral=bool(g.get("neutralSite", False)),
        broadcast=_broadcast(g),
        season_type=season_type,
        round_slug=round_slug if season_type == "post" else None,
        series_round=series_round if season_type == "post" else None,
        series_game=(series.get("gameNumberOfSeries") or g.get("gameNumber")) if season_type == "post" else None,
        series_title=series_title if season_type == "post" else None,
    )


def club_schedule(abbrev: str, season_id: str) -> list[Game]:
    data = http.get_json(f"{BASE}/club-schedule-season/{abbrev}/{season_id}")
    games = [parse_game(g) for g in data.get("games", []) or []]
    return sorted((g for g in games if g), key=Game.sort_key)


def stanley_cup_final(season_id: str) -> list[Game]:
    """All Stanley Cup Final games for a season, or [] if the final is not set yet."""
    end_year = int(season_id[4:])
    try:
        bracket = http.get_json(f"{BASE}/playoff-bracket/{end_year}")
    except http.NotFound:
        return []
    final = [s for s in bracket.get("series", []) or [] if s.get("playoffRound") == 4 and s.get("seriesLetter")]
    if not final:
        return []
    letter = final[0]["seriesLetter"].lower()
    try:
        data = http.get_json(f"{BASE}/schedule/playoff-series/{season_id}/{letter}/")
    except http.NotFound:
        return []
    games = [parse_game(g, default_round=4, default_title="Stanley Cup Final")
             for g in data.get("games", []) or []]
    return sorted((g for g in games if g), key=Game.sort_key)
