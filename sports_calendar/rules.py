"""Turn config rules into lists of matched games / all-day events."""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from sports_calendar.models import AllDayEvent, Game

log = logging.getLogger(__name__)


def _ids(values) -> set[str]:
    return {str(v) for v in values or []}


def _in_competitions(rule: dict, game: Game) -> bool:
    comps = rule.get("competitions")
    return not comps or game.competition in comps


# --- Game rules --------------------------------------------------------------

def _team_all(rule, catalog) -> list[Game]:
    team = str(rule["team"])
    return [g for g in catalog.team_games(rule) if g.involves(team) and _in_competitions(rule, g)]


def _head_to_head(rule, catalog) -> list[Game]:
    team = str(rule["team"])
    opponents = _ids(rule["opponents"])
    out = []
    for g in catalog.team_games(rule):
        opp = g.opponent_of(team)
        if opp is None or opp.id not in opponents or not _in_competitions(rule, g):
            continue
        if rule.get("only_away") and g.away.id != team:
            continue
        out.append(g)
    return out


def _group_h2h(rule, catalog) -> list[Game]:
    teams = _ids(rule["teams"])
    seen: dict[str, Game] = {}
    for team in rule["teams"]:
        for g in catalog.team_games({**rule, "team": team}):
            if g.home.id in teams and g.away.id in teams and _in_competitions(rule, g):
                seen.setdefault(g.uid, g)
    return list(seen.values())


def _opener(rule, catalog) -> list[Game]:
    team = str(rule["team"])
    regular = sorted((g for g in catalog.team_games(rule) if g.involves(team) and g.season_type == "regular"),
                     key=Game.sort_key)
    if not regular:
        return []
    if regular[0].sport == "baseball":
        firsts: dict[int, Game] = {}
        for g in regular:
            firsts.setdefault(g.day.year, g)
        openers = list(firsts.values())
    else:
        openers = [regular[0]]
    for g in openers:
        g.context = "Opening Day" if g.sport == "baseball" else "Season Opener"
    return openers


def _home_games(rule, catalog) -> list[Game]:
    team = str(rule["team"])
    return [g for g in catalog.team_games(rule) if g.home.id == team and not g.neutral]


def _postseason(rule, catalog) -> list[Game]:
    team = str(rule["team"])
    return [g for g in catalog.team_games(rule) if g.involves(team) and g.season_type == "post"]


def _round(rule, catalog) -> list[Game]:
    rounds = set(rule["rounds"])
    return [g for g in catalog.competition_games(rule) if g.round_slug in rounds]


def _tournament_all(rule, catalog) -> list[Game]:
    return list(catalog.competition_games(rule))


def _finals(rule, catalog) -> list[Game]:
    games = catalog.competition_games(rule)
    prefix = rule.get("notes_prefix")
    if prefix:
        games = [g for g in games if (g.notes or "").startswith(prefix)]
    return list(games)


GAME_RULES = {
    "team_all": _team_all,
    "head_to_head": _head_to_head,
    "group_h2h": _group_h2h,
    "opener": _opener,
    "home_games": _home_games,
    "postseason": _postseason,
    "round": _round,
    "tournament_all": _tournament_all,
    "finals": _finals,
}


# --- All-day event rules -----------------------------------------------------

def _golf_event(rule, catalog) -> list[AllDayEvent]:
    out = []
    for entry in catalog.golf_calendar(rule["tour"]):
        if entry["label"] == rule["label"]:
            out.append(AllDayEvent(
                uid=f"espn-golf-{entry['id']}",
                title=rule.get("title", entry["label"]),
                start=entry["start"],
                end=entry["end"] + timedelta(days=1),
                description=f"{entry['label']} · {entry['start']:%b %-d}–{entry['end']:%b %-d}",
            ))
    return out


def slam_dates(major) -> tuple[date, list[date], date]:
    """(Day 1 Monday, men's semifinal days, men's final day) — from the draw if
    present, else derived from the tournament's last day (always a Sunday)."""
    rd = major.round_dates
    final = min(rd["Final"]) if rd.get("Final") else major.end
    semis = sorted(set(rd["Semifinal"])) if rd.get("Semifinal") else [final - timedelta(days=2)]
    day1 = min(rd["Round 1"]) if rd.get("Round 1") else final - timedelta(days=13)
    if day1.weekday() == 6:  # main draw opened on a Sunday → first Monday
        day1 += timedelta(days=1)
    return day1, semis, final


def _grand_slams(rule, catalog) -> list[AllDayEvent]:
    out = []
    for major in catalog.tennis_majors():
        day1, semis, final = slam_dates(major)
        note = f"{major.name} · {major.start:%b %-d}–{major.end:%b %-d}"
        out.append(AllDayEvent(uid=f"espn-tennis-{major.id}-day1", title=f"{major.name} Day 1",
                               start=day1, end=day1 + timedelta(days=1), description=note))
        for d in semis:
            out.append(AllDayEvent(uid=f"espn-tennis-{major.id}-sf-{d:%Y%m%d}", title=f"{major.name} Men's Semifinals",
                                   start=d, end=d + timedelta(days=1), description=note))
        out.append(AllDayEvent(uid=f"espn-tennis-{major.id}-final", title=f"{major.name} Men's Final",
                               start=final, end=final + timedelta(days=1), description=note))
    return out


EVENT_RULES = {
    "golf_event": _golf_event,
    "grand_slams": _grand_slams,
}


# --- Title context -----------------------------------------------------------

COMPETITION_LABELS = {
    "uefa.champions": "UCL", "uefa.europa": "UEL", "uefa.europa.conf": "Conference League",
    "uefa.super_cup": "Super Cup", "fifa.world": "World Cup", "fifa.cwc": "Club World Cup",
    "club.friendly": "Friendly", "eng.2": "Championship",
    "eng.fa": "FA Cup", "eng.league_cup": "EFL Cup", "eng.charity": "Community Shield",
    "esp.copa_del_rey": "Copa del Rey", "esp.super_cup": "Supercopa",
    "ita.coppa_italia": "Coppa Italia", "ita.super_cup": "Supercoppa",
    "ger.dfb_pokal": "DFB-Pokal", "ger.super_cup": "Supercup",
}
# Domestic leagues: no suffix for ordinary league games.
DOMESTIC_LEAGUES = {"eng.1", "esp.1", "ita.1", "ger.1", "fra.1", "eng.2"}
ROUND_LABELS = {
    "quarterfinals": "Quarterfinal", "semifinals": "Semifinal", "final": "Final",
    "round-of-16": "Round of 16", "round-of-32": "Round of 32", "knockout-round-playoffs": "Knockout Play-off",
    "promotion-semifinals": "Play-off Semifinal", "promotion-final": "Play-off Final",
    "third-place-playoff": "Third Place", "3rd-place-playoff": "Third Place",
}
_LEG = re.compile(r"^(1st|2nd) Leg")
_GAME_SUFFIX = re.compile(r"\s*-\s*Game (\d+)$")
NOTE_REPLACEMENTS = [
    ("NCAA Men's Hockey National Championship", "NCAA Championship"),
    ("NCAA Men's Hockey Championship - ", "NCAA "),
]


def context_for(game: Game) -> str | None:
    if game.sport == "soccer":
        round_label = ROUND_LABELS.get(game.round_slug or "")
        label = COMPETITION_LABELS.get(game.competition)
        if label is None and game.competition not in DOMESTIC_LEAGUES:
            label = game.competition_name
        if game.competition in DOMESTIC_LEAGUES and not round_label:
            label = None
        leg = _LEG.match(game.notes or "")
        parts = [p for p in (label, round_label, leg.group(0) if leg else None) if p]
        return " ".join(parts) or game.context
    if game.season_type == "post":
        if game.series_title:
            return f"{game.series_title} G{game.series_game}" if game.series_game else game.series_title
        if game.notes:
            text = game.notes
            for old, new in NOTE_REPLACEMENTS:
                text = text.replace(old, new)
            return _GAME_SUFFIX.sub(r" G\1", text)
        return "Playoffs"
    return game.context


def annotate(games: list[Game]) -> None:
    for g in games:
        g.context = context_for(g)


# --- Driver ------------------------------------------------------------------

def evaluate(rule: dict, catalog) -> list:
    kind = rule.get("type")
    if kind in GAME_RULES:
        return GAME_RULES[kind](rule, catalog)
    if kind in EVENT_RULES:
        return EVENT_RULES[kind](rule, catalog)
    raise ValueError(f"unknown rule type {kind!r} in rule {rule.get('name')!r}")


def apply_rules(rule_list: list[dict], catalog) -> tuple[list[Game], list[AllDayEvent]]:
    games: dict[str, Game] = {}
    events: dict[str, AllDayEvent] = {}
    for rule in rule_list:
        matched = evaluate(rule, catalog)
        log.info("rule %-32s → %d", rule.get("name"), len(matched))
        for item in matched:
            store = games if isinstance(item, Game) else events
            kept = store.setdefault(item.uid, item)
            if rule["name"] not in kept.matched_rules:
                kept.matched_rules.append(rule["name"])
            if kept is not item and item.context and not kept.context:
                kept.context = item.context
    result = sorted(games.values(), key=Game.sort_key)
    annotate(result)
    return result, sorted(events.values(), key=lambda e: e.start)
