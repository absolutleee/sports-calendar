from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone


@dataclass(frozen=True)
class Team:
    id: str        # source-specific id: ESPN numeric string, MLB numeric string, NHL abbrev
    name: str      # full name, e.g. "Manchester United"
    short: str     # source's short name, e.g. "Man United"


@dataclass
class Game:
    uid: str                     # "{source}-{id}", stable across runs
    sport: str                   # soccer | baseball | hockey | basketball
    competition: str             # ESPN league slug, or "mlb" / "nhl"
    competition_name: str        # human-readable competition
    home: Team
    away: Team
    day: date                    # calendar date of the game (UTC date when start is known)
    start: datetime | None = None  # aware UTC datetime, None when unknown
    time_valid: bool = True      # False when the league has not set a start time yet
    venue: str | None = None
    neutral: bool = False
    broadcast: str | None = None
    season_type: str = "regular"  # pre | regular | post
    round_slug: str | None = None  # ESPN season.slug ("semifinals"), NHL series abbrev ("SCF"), MLB gameType
    notes: str | None = None       # ESPN notes headline, e.g. "1st Leg", "NBA Finals - Game 1"
    series_round: int | None = None
    series_game: int | None = None
    series_title: str | None = None  # "Stanley Cup Final", "World Series"
    matched_rules: list[str] = field(default_factory=list)
    context: str | None = None     # title suffix, set by rules.annotate

    def involves(self, team_id) -> bool:
        return str(team_id) in (self.home.id, self.away.id)

    def opponent_of(self, team_id) -> Team | None:
        team_id = str(team_id)
        if self.home.id == team_id:
            return self.away
        if self.away.id == team_id:
            return self.home
        return None

    def sort_key(self) -> datetime:
        if self.start is not None:
            return self.start
        return datetime.combine(self.day, time(0, 0), tzinfo=timezone.utc)


@dataclass
class AllDayEvent:
    uid: str
    title: str
    start: date
    end: date                    # exclusive, per RFC 5545
    description: str = ""
    matched_rules: list[str] = field(default_factory=list)
