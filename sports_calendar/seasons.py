"""Which season / date range to fetch, given today's date.

Convention: the "season-end year" is the calendar year in which the current
European/US winter season ends. From July 1 onward we are in the season that
ends next year.
"""
from __future__ import annotations

from datetime import date


def season_end_year(today: date) -> int:
    return today.year + 1 if today.month >= 7 else today.year


def nhl_season_id(today: date) -> str:
    end = season_end_year(today)
    return f"{end - 1}{end}"


def mlb_seasons(today: date) -> list[int]:
    # MLB seasons are calendar years; next year's schedule appears in late summer.
    return [today.year, today.year + 1]


def espn_season(today: date) -> int:
    # ESPN's `season` param for NBA / NCAA is the season-end year.
    return season_end_year(today)


def window(today: date, start_md: str, end_md: str) -> tuple[date, date]:
    """Resolve 'MM-DD' bounds into dates in the season-end year."""
    year = season_end_year(today)
    sm, sd = (int(x) for x in start_md.split("-"))
    em, ed = (int(x) for x in end_md.split("-"))
    return date(year, sm, sd), date(year, em, ed)


def tennis_years(today: date) -> list[int]:
    return [today.year] + ([today.year + 1] if today.month >= 10 else [])
