"""Game / AllDayEvent → iCalendar bytes."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from icalendar import Calendar, Event

from sports_calendar.models import AllDayEvent, Game, ManualEvent

DURATIONS = {
    "soccer": timedelta(hours=2),
    "baseball": timedelta(hours=3),
    "hockey": timedelta(hours=2, minutes=30),
    "basketball": timedelta(hours=2, minutes=30),
}
UID_DOMAIN = "sports-calendar"
CALENDAR_NAME = "Sports"


def shorten(name: str, sport: str, display_names: dict[str, dict[str, str]]) -> str:
    """display_names is scoped per sport so e.g. soccer's 'Spurs' can't rename the NBA Spurs."""
    return (display_names.get(sport) or {}).get(name, name)


def title_for(game: Game, display_names: dict[str, dict[str, str]]) -> str:
    if game.sport == "soccer":
        first, second = game.home, game.away
    else:
        first, second = game.away, game.home
    title = f"{shorten(first.short, game.sport, display_names)} {shorten(second.short, game.sport, display_names)}"
    parts = [p for p in (game.context, None if game.time_valid else "time TBD") if p]
    if parts:
        title += " · " + " · ".join(parts)
    return title


def description_for(game: Game) -> str:
    lines = [game.competition_name]
    if game.context:
        lines[0] += f" · {game.context}"
    if game.venue:
        lines.append(game.venue)
    if game.broadcast:
        lines.append(f"TV: {game.broadcast}")
    if game.matched_rules:
        lines.append("Matched: " + ", ".join(game.matched_rules))
    lines.append(f"id: {game.uid}")
    return "\n".join(lines)


def _game_event(game: Game, display_names: dict[str, dict[str, str]]) -> Event:
    ev = Event()
    ev.add("uid", f"{game.uid}@{UID_DOMAIN}")
    ev.add("summary", title_for(game, display_names))
    ev.add("description", description_for(game))
    if game.venue:
        ev.add("location", game.venue)
    if game.time_valid and game.start is not None:
        ev.add("dtstart", game.start)
        ev.add("dtend", game.start + DURATIONS.get(game.sport, timedelta(hours=2)))
        # Deterministic DTSTAMP so unchanged schedules produce byte-identical files.
        ev.add("dtstamp", game.start.astimezone(timezone.utc))
    else:
        ev.add("dtstart", game.day)
        ev.add("dtend", game.day + timedelta(days=1))
        ev.add("dtstamp", datetime.combine(game.day, time(0, 0), tzinfo=timezone.utc))
    ev.add("transp", "TRANSPARENT")
    return ev


def _simple_event(e: AllDayEvent | ManualEvent) -> Event:
    ev = Event()
    ev.add("uid", f"{e.uid}@{UID_DOMAIN}")
    ev.add("summary", e.title)
    lines = [e.description] if e.description else []
    if e.matched_rules:
        lines.append("Matched: " + ", ".join(e.matched_rules))
    lines.append(f"id: {e.uid}")
    ev.add("description", "\n".join(lines))
    ev.add("dtstart", e.start)
    ev.add("dtend", e.end)
    if isinstance(e.start, datetime):
        ev.add("dtstamp", e.start.astimezone(timezone.utc))
    else:
        ev.add("dtstamp", datetime.combine(e.start, time(0, 0), tzinfo=timezone.utc))
    ev.add("transp", "TRANSPARENT")
    return ev


def _event_sort_key(e: AllDayEvent | ManualEvent):
    start = e.start
    if isinstance(start, datetime):
        start = start.astimezone(timezone.utc).date()
    return (start, e.uid)


def build_calendar(games: list[Game], alldays: list[AllDayEvent | ManualEvent],
                   display_names: dict[str, dict[str, str]]) -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//sports-calendar//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", CALENDAR_NAME)
    cal.add("x-published-ttl", "PT12H")
    cal.add("refresh-interval", timedelta(hours=12), parameters={"VALUE": "DURATION"})

    for g in sorted(games, key=lambda g: (g.sort_key(), g.uid)):
        cal.add_component(_game_event(g, display_names))
    for e in sorted(alldays, key=_event_sort_key):
        cal.add_component(_simple_event(e))
    return cal.to_ical()
