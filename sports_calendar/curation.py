"""Manual curation from config: `exclude` filters and `extra` events."""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sports_calendar.ics import title_for
from sports_calendar.models import AllDayEvent, Game, ManualEvent

log = logging.getLogger(__name__)

EXCLUDE_KEYS = {"id", "title", "between", "sports", "rules"}
EXTRA_KEYS = {"title", "start", "end", "hours", "notes"}


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _as_when(value, tz: ZoneInfo) -> date | datetime:
    """YAML gives date / datetime objects; strings are accepted too. Naive datetimes are in tz."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00")) if "T" in value else date.fromisoformat(value)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=tz)
    return value


def local_day(item: Game | AllDayEvent | ManualEvent, tz: ZoneInfo) -> date:
    if isinstance(item, Game):
        if item.start is not None and item.time_valid:
            return item.start.astimezone(tz).date()
        return item.day
    if isinstance(item.start, datetime):
        return item.start.astimezone(tz).date()
    return item.start


def base_title(title: str) -> str:
    return title.split(" · ")[0]


def matches(entry: dict, item, title: str, tz: ZoneInfo) -> bool:
    if "id" in entry and item.uid != entry["id"]:
        return False
    if "title" in entry and entry["title"] not in (title, base_title(title)):
        return False
    if "between" in entry:
        lo, hi = (_as_date(v) for v in entry["between"])
        if not lo <= local_day(item, tz) <= hi:
            return False
    if "sports" in entry and (not isinstance(item, Game) or item.sport not in entry["sports"]):
        return False
    if "rules" in entry and not set(entry["rules"]) & set(item.matched_rules):
        return False
    return True


def _validate(entries: list[dict], allowed: set[str], section: str) -> None:
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict) or not entry:
            raise ValueError(f"{section}[{i}] must be a mapping with at least one field")
        unknown = set(entry) - allowed
        if unknown:
            raise ValueError(f"{section}[{i}] has unknown field(s) {sorted(unknown)}; allowed: {sorted(allowed)}")


def apply_excludes(games: list[Game], events: list, excludes: list[dict], display_names: dict, tz: ZoneInfo):
    _validate(excludes, EXCLUDE_KEYS, "exclude")
    if not excludes:
        return games, events

    def keep(item, title):
        hit = next((e for e in excludes if matches(e, item, title, tz)), None)
        if hit is not None:
            log.info("excluded %-40s (%s) by %s", title, local_day(item, tz), hit)
        return hit is None

    kept_games = [g for g in games if keep(g, title_for(g, display_names))]
    kept_events = [e for e in events if keep(e, e.title)]
    return kept_games, kept_events


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "event"


def build_extras(entries: list[dict], tz: ZoneInfo) -> list[ManualEvent]:
    _validate(entries, EXTRA_KEYS, "extra")
    out = []
    for entry in entries:
        if "title" not in entry or "start" not in entry:
            raise ValueError(f"extra entry needs title and start: {entry}")
        start = _as_when(entry["start"], tz)
        if isinstance(start, datetime):
            end = start + timedelta(hours=float(entry.get("hours", 2)))
            uid_day = start.astimezone(tz).date()
        else:
            end = _as_date(entry.get("end", start)) + timedelta(days=1)
            uid_day = start
        out.append(ManualEvent(
            uid=f"extra-{_slug(entry['title'])}-{uid_day.isoformat()}",
            title=str(entry["title"]),
            start=start,
            end=end,
            description=str(entry.get("notes", "")),
        ))
    return out
