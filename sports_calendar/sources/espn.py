"""ESPN public site API → Game. Undocumented but stable; no key required."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sports_calendar import http
from sports_calendar.models import Game, Team

log = logging.getLogger(__name__)

BASE = "https://site.api.espn.com/apis/site/v2/sports"

LEAGUE_NAMES = {
    "nba": "NBA",
    "mens-college-hockey": "NCAA Hockey",
}


def parse_dt(value: str) -> datetime:
    """ESPN dates look like '2026-08-23T15:30Z'."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _team(competitor: dict) -> Team:
    t = competitor["team"]
    name = t.get("displayName") or t.get("name") or str(t["id"])
    return Team(id=str(t["id"]), name=name, short=t.get("shortDisplayName") or name)


def _broadcast(comp: dict) -> str | None:
    names: list[str] = []
    for b in comp.get("broadcasts", []) or []:
        if b.get("names"):
            names.extend(b["names"])
        elif isinstance(b.get("media"), dict) and b["media"].get("shortName"):
            names.append(b["media"]["shortName"])
    names = list(dict.fromkeys(n for n in names if n))
    return ", ".join(names) or None


_POST = re.compile(r"\bpost")            # "Postseason", "post-season"
_PRE = re.compile(r"\bpre(-?season)?\b")   # "Preseason" but NOT "Premier League"


def _season_type(event: dict) -> str:
    st = event.get("seasonType") or {}
    season = event.get("season") or {}
    if st.get("type") == 3 or season.get("type") == 3:
        return "post"
    if st.get("type") == 1:
        return "pre"
    text = f"{st.get('name', '')} {season.get('slug', '')}".lower()
    if _POST.search(text):
        return "post"
    if _PRE.search(text):
        return "pre"
    return "regular"


_GAME_NO = re.compile(r"Game (\d+)")


def parse_event(event: dict, sport: str, league_slug: str, league_name: str) -> Game | None:
    try:
        comp = event["competitions"][0]
        competitors = comp["competitors"]
        home = next(c for c in competitors if c.get("homeAway") == "home")
        away = next(c for c in competitors if c.get("homeAway") == "away")
        start = parse_dt(comp.get("date") or event["date"])
    except (KeyError, IndexError, StopIteration, ValueError) as exc:
        log.warning("skipping malformed ESPN event %s: %s", event.get("id"), exc)
        return None

    league = event.get("league") or {}
    slug = league.get("slug") or league_slug
    name = league.get("name") or league_name
    notes = None
    for n in comp.get("notes", []) or []:
        if n.get("headline"):
            notes = n["headline"]
            break
    m = _GAME_NO.search(notes or "")
    time_valid = comp.get("timeValid", event.get("timeValid", True))

    return Game(
        uid=f"espn-{event['id']}",
        sport=sport,
        competition=slug,
        competition_name=name,
        home=_team(home),
        away=_team(away),
        day=start.date(),
        start=start,
        time_valid=bool(time_valid),
        venue=(comp.get("venue") or {}).get("fullName"),
        neutral=bool(comp.get("neutralSite", False)),
        broadcast=_broadcast(comp),
        season_type=_season_type(event),
        round_slug=(event.get("season") or {}).get("slug"),
        notes=notes,
        series_game=int(m.group(1)) if m else None,
    )


def parse_schedule(data: dict, sport: str, league_slug: str, league_name: str) -> list[Game]:
    games = []
    for event in data.get("events", []) or []:
        g = parse_event(event, sport, league_slug, league_name)
        if g:
            games.append(g)
    return games


def _dedupe(games: list[Game]) -> list[Game]:
    seen: dict[str, Game] = {}
    for g in games:
        seen.setdefault(g.uid, g)
    return sorted(seen.values(), key=Game.sort_key)


def soccer_team_schedule(team_id: str) -> list[Game]:
    """Played matches + upcoming fixtures across every competition."""
    url = f"{BASE}/soccer/all/teams/{team_id}/schedule"
    results = http.get_json(url)
    fixtures = http.get_json(url, {"fixture": "true"})
    return _dedupe(parse_schedule(results, "soccer", "all", "Soccer")
                   + parse_schedule(fixtures, "soccer", "all", "Soccer"))


def us_team_schedule(sport: str, league: str, team_id: str, season: int) -> list[Game]:
    """Regular season + postseason for NBA / NCAA style leagues."""
    url = f"{BASE}/{sport}/{league}/teams/{team_id}/schedule"
    name = LEAGUE_NAMES.get(league, league)
    games: list[Game] = []
    for seasontype in (2, 3):
        data = http.get_json(url, {"season": season, "seasontype": seasontype})
        games += parse_schedule(data, sport, league, name)
    return _dedupe(games)


def scoreboard(sport: str, league: str, start: date, end: date) -> list[Game]:
    """Every event of a competition in a date range (inclusive)."""
    url = f"{BASE}/{sport}/{league}/scoreboard"
    data = http.get_json(url, {"dates": f"{start:%Y%m%d}-{end:%Y%m%d}", "limit": 1000})
    leagues = data.get("leagues") or [{}]
    slug = leagues[0].get("slug") or league
    name = LEAGUE_NAMES.get(league) or leagues[0].get("name") or league
    return _dedupe(parse_schedule(data, sport, slug, name))


# --- Golf -------------------------------------------------------------------

def golf_calendar(tour: str) -> list[dict]:
    """Season calendar: [{'id', 'label', 'start': date, 'end': date}] (dates inclusive)."""
    data = http.get_json(f"{BASE}/golf/{tour}/scoreboard")
    leagues = data.get("leagues") or [{}]
    out = []
    for entry in leagues[0].get("calendar", []) or []:
        try:
            out.append({
                "id": str(entry["id"]),
                "label": entry["label"],
                "start": parse_dt(entry["startDate"]).date(),
                "end": parse_dt(entry["endDate"]).date(),
            })
        except (KeyError, ValueError) as exc:
            log.warning("skipping golf calendar entry %s: %s", entry.get("label"), exc)
    return out


# --- Tennis -----------------------------------------------------------------

# One or two probe dates inside each Grand Slam's window.
TENNIS_PROBE_DATES = ["01-20", "01-27", "05-28", "06-03", "07-01", "07-07", "08-28", "09-05"]
_NY = ZoneInfo("America/New_York")


@dataclass
class Major:
    id: str
    name: str
    start: date
    end: date                                   # last day of play (inclusive)
    round_dates: dict[str, list[date]] = field(default_factory=dict)  # Men's Singles round → UTC dates


def _major_from_event(event: dict) -> Major | None:
    try:
        tz = ZoneInfo((event.get("calendar") or {}).get("timeZone") or "America/New_York")
    except Exception:  # unknown zone string
        tz = _NY
    try:
        start = parse_dt(event["date"]).astimezone(tz).date()
        end = parse_dt(event["endDate"]).astimezone(tz).date()
    except (KeyError, ValueError) as exc:
        log.warning("skipping tennis event %s: %s", event.get("name"), exc)
        return None
    rounds: dict[str, list[date]] = {}
    for grouping in event.get("groupings", []) or []:
        label = (grouping.get("grouping") or {}).get("displayName")
        if label != "Men's Singles":
            continue
        for comp in grouping.get("competitions", []) or []:
            rname = (comp.get("round") or {}).get("displayName")
            if not rname or not comp.get("date"):
                continue
            rounds.setdefault(rname, []).append(parse_dt(comp["date"]).date())
    for k in rounds:
        rounds[k] = sorted(set(rounds[k]))
    return Major(id=str(event["id"]), name=event["name"], start=start, end=end, round_dates=rounds)


def tennis_majors(year: int) -> list[Major]:
    """The Grand Slams ESPN knows about for `year`, in date order."""
    found: dict[str, Major] = {}
    for md in TENNIS_PROBE_DATES:
        data = http.get_json(f"{BASE}/tennis/atp/scoreboard", {"dates": f"{year}{md.replace('-', '')}"})
        for event in data.get("events", []) or []:
            if not event.get("major"):
                continue
            major = _major_from_event(event)
            if major and major.id not in found:
                found[major.id] = major
    return sorted(found.values(), key=lambda m: m.start)
