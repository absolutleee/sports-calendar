# Sports Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Python script that pulls schedules from free key-less sports APIs, applies Lee's watch-list rules from `config.yaml`, and writes `docs/sports.ics`, run daily by GitHub Actions for Apple Calendar to subscribe to.

**Architecture:** Three source adapters (ESPN, MLB Stats API, NHL API) normalize raw JSON into one `Game` dataclass. `catalog.py` decides which season/date windows to fetch for today's date. `rules.py` turns each config rule into a filter over those games (plus all-day events for golf/tennis), dedupes, and computes a short title suffix. `ics.py` serializes. All network I/O goes through one function, `http.get_json`, which tests replace with fixture files.

**Tech Stack:** Python 3.12+, `requests`, `icalendar`, `PyYAML`, `pytest`. Spec: `docs/superpowers/specs/2026-08-25-sports-calendar-design.md`.

**Conventions for every task:**
- Run tests with `.venv/bin/pytest` from the repo root (venv already exists with all deps installed).
- Source modules must call `http.get_json(...)` via the module (`from sports_calendar import http` then `http.get_json`), never `from .http import get_json` — tests monkeypatch the module attribute.
- Fixture JSON files already exist in `fixtures/` (recorded from the real APIs on 2026-08-25). Do not edit them.
- Commit after each task with the message given.

---

## File structure

| Path | Responsibility |
|---|---|
| `sports_calendar/__init__.py` | package marker |
| `sports_calendar/models.py` | `Team`, `Game`, `AllDayEvent` dataclasses |
| `sports_calendar/http.py` | `get_json` with retries, cache, `FetchError`/`NotFound` |
| `sports_calendar/seasons.py` | date math: season-end year, NHL season id, windows |
| `sports_calendar/sources/__init__.py` | package marker |
| `sports_calendar/sources/espn.py` | ESPN team schedules, scoreboards, golf calendar, tennis majors → `Game`/`Major` |
| `sports_calendar/sources/mlb.py` | MLB Stats API → `Game` |
| `sports_calendar/sources/nhl.py` | NHL API club schedule + Stanley Cup Final → `Game` |
| `sports_calendar/catalog.py` | `Catalog`: maps a rule's `source` to the right adapter call for today's date |
| `sports_calendar/rules.py` | rule evaluation, dedupe, context suffix |
| `sports_calendar/ics.py` | titles, descriptions, `.ics` bytes |
| `sports_calendar/main.py` / `__main__.py` | CLI entry: config → fetch → filter → write |
| `config.yaml` | rules, team ids, display names |
| `tests/conftest.py` | fixture loader + `fake_fetch` |
| `tests/test_*.py` | one test file per module |
| `.github/workflows/build.yml` | daily build + commit |
| `README.md` | setup & subscribe instructions |

---

### Task 1: Scaffold, test harness, fixtures check

**Files:**
- Create: `requirements.txt`, `.gitignore`, `pytest.ini`, `sports_calendar/__init__.py`, `sports_calendar/sources/__init__.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_conftest.py`

- [ ] **Step 1: Create project files**

`requirements.txt`:
```
requests>=2.31
icalendar>=6.0
PyYAML>=6.0
pytest>=8.0
```

`.gitignore`:
```
.venv/
__pycache__/
.pytest_cache/
*.pyc
.DS_Store
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests
```

Empty files: `sports_calendar/__init__.py`, `sports_calendar/sources/__init__.py`, `tests/__init__.py`.

- [ ] **Step 2: Write conftest with fixture loader and fake fetch**

`tests/conftest.py`:
```python
import json
from pathlib import Path
from urllib.parse import urlencode

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def fixture():
    return load_fixture


@pytest.fixture
def fake_fetch(monkeypatch):
    """Replace http.get_json with a lookup table.

    mapping: list of (needles, payload). needles is a str or tuple of str; every
    needle must appear in the full URL (url + '?' + encoded params). payload is a
    fixture filename (str) or a dict. First match wins. Unmatched URLs raise.
    """
    from sports_calendar import http

    def install(mapping):
        calls = []

        def _get(url, params=None, **kwargs):
            full = url + ("?" + urlencode(params) if params else "")
            calls.append(full)
            for needles, payload in mapping:
                if isinstance(needles, str):
                    needles = (needles,)
                if all(n in full for n in needles):
                    return load_fixture(payload) if isinstance(payload, str) else payload
            raise AssertionError(f"unexpected fetch: {full}")

        monkeypatch.setattr(http, "get_json", _get)
        return calls

    return install
```

- [ ] **Step 3: Write a smoke test that fixtures are present**

`tests/test_conftest.py`:
```python
from tests.conftest import FIXTURES

EXPECTED = [
    "espn_liverpool_fixtures.json", "espn_liverpool_results.json",
    "espn_barcelona_fixtures.json", "espn_arsenal_fixtures.json",
    "espn_ucl_2025_26.json", "espn_uel_may_2026.json", "espn_eng2_playoffs_2026.json",
    "espn_worldcup_2026.json", "espn_nuggets_2026_27_reg.json", "espn_nuggets_2025_26_post.json",
    "espn_nba_june_2026.json", "espn_denver_hockey_2025_26.json",
    "nhl_col_2025_26.json", "nhl_col_2026_27.json", "nhl_nyr_2026_27.json",
    "nhl_bracket_2026.json", "nhl_series_scf_2026.json",
    "mlb_mets_2026.json", "espn_pga_scoreboard.json",
    "espn_tennis_wimbledon_2026.json", "espn_tennis_ao_2026.json", "espn_tennis_usopen_2026.json",
]


def test_fixtures_present():
    missing = [f for f in EXPECTED if not (FIXTURES / f).exists()]
    assert missing == []


def test_fixture_loader(fixture):
    data = fixture("espn_liverpool_fixtures.json")
    assert len(data["events"]) == 37
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest -q`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .gitignore pytest.ini sports_calendar tests fixtures
git commit -m "chore: scaffold package, test harness and recorded API fixtures"
```

---

### Task 2: Models

**Files:**
- Create: `sports_calendar/models.py`, `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
from datetime import date, datetime, timezone

from sports_calendar.models import AllDayEvent, Game, Team

LIV = Team(id="364", name="Liverpool", short="Liverpool")
NEW = Team(id="361", name="Newcastle United", short="Newcastle")


def test_game_involves_and_opponent():
    g = Game(uid="espn-1", sport="soccer", competition="eng.1", competition_name="Premier League",
             home=NEW, away=LIV, day=date(2026, 8, 23),
             start=datetime(2026, 8, 23, 15, 30, tzinfo=timezone.utc))
    assert g.involves("364")
    assert g.involves(364)
    assert not g.involves("1")
    assert g.opponent_of("364") == NEW
    assert g.opponent_of("361") == LIV
    assert g.opponent_of("999") is None


def test_game_defaults():
    g = Game(uid="x", sport="hockey", competition="nhl", competition_name="NHL",
             home=LIV, away=NEW, day=date(2026, 1, 1))
    assert g.start is None and g.time_valid is True and g.season_type == "regular"
    assert g.matched_rules == [] and g.context is None


def test_sort_key_uses_start_or_day():
    timed = Game(uid="a", sport="soccer", competition="x", competition_name="X", home=LIV, away=NEW,
                 day=date(2026, 1, 2), start=datetime(2026, 1, 2, 20, 0, tzinfo=timezone.utc))
    dateonly = Game(uid="b", sport="soccer", competition="x", competition_name="X", home=LIV, away=NEW,
                    day=date(2026, 1, 2), start=None)
    assert dateonly.sort_key() < timed.sort_key()


def test_allday_event():
    e = AllDayEvent(uid="golf-1", title="The Masters", start=date(2026, 4, 9), end=date(2026, 4, 13))
    assert e.description == "" and e.matched_rules == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_models.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sports_calendar.models'`

- [ ] **Step 3: Implement models**

`sports_calendar/models.py`:
```python
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
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_models.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add sports_calendar/models.py tests/test_models.py
git commit -m "feat: add Game, Team and AllDayEvent models"
```

---

### Task 3: HTTP layer

**Files:**
- Create: `sports_calendar/http.py`, `tests/test_http.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_http.py`:
```python
import pytest
import requests

from sports_calendar import http


class FakeResponse:
    def __init__(self, status, payload=None, bad_json=False):
        self.status_code = status
        self._payload = payload
        self._bad_json = bad_json

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError(f"{self.status_code}")
            err.response = self
            raise err

    def json(self):
        if self._bad_json:
            raise ValueError("bad json")
        return self._payload


@pytest.fixture(autouse=True)
def no_sleep_and_clear_cache(monkeypatch):
    monkeypatch.setattr(http, "_sleep", lambda s: None)
    http.clear_cache()


def test_returns_json(monkeypatch):
    monkeypatch.setattr(http.requests, "get", lambda *a, **k: FakeResponse(200, {"ok": 1}))
    assert http.get_json("https://x/y", {"a": 1}) == {"ok": 1}


def test_caches_by_url_and_params(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, tuple(sorted((kwargs.get("params") or {}).items()))))
        return FakeResponse(200, {"n": len(calls)})

    monkeypatch.setattr(http.requests, "get", fake_get)
    assert http.get_json("https://x/y", {"a": 1}) == {"n": 1}
    assert http.get_json("https://x/y", {"a": 1}) == {"n": 1}
    assert http.get_json("https://x/y", {"a": 2}) == {"n": 2}
    assert len(calls) == 2


def test_retries_then_succeeds(monkeypatch):
    responses = [FakeResponse(500), FakeResponse(200, bad_json=True), FakeResponse(200, {"ok": 1})]
    monkeypatch.setattr(http.requests, "get", lambda *a, **k: responses.pop(0))
    assert http.get_json("https://x/y") == {"ok": 1}


def test_raises_fetch_error_after_attempts(monkeypatch):
    monkeypatch.setattr(http.requests, "get", lambda *a, **k: FakeResponse(500))
    with pytest.raises(http.FetchError):
        http.get_json("https://x/y")


def test_404_raises_not_found_without_retry(monkeypatch):
    calls = []

    def fake_get(*a, **k):
        calls.append(1)
        return FakeResponse(404)

    monkeypatch.setattr(http.requests, "get", fake_get)
    with pytest.raises(http.NotFound):
        http.get_json("https://x/missing")
    assert len(calls) == 1


def test_connection_error_retries(monkeypatch):
    attempts = []

    def fake_get(*a, **k):
        attempts.append(1)
        if len(attempts) < 3:
            raise requests.ConnectionError("boom")
        return FakeResponse(200, {"ok": 1})

    monkeypatch.setattr(http.requests, "get", fake_get)
    assert http.get_json("https://x/y") == {"ok": 1}
    assert len(attempts) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_http.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sports_calendar.http'`

- [ ] **Step 3: Implement http.py**

`sports_calendar/http.py`:
```python
"""Single network seam. Everything that talks to the internet goes through get_json."""
from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode

import requests

log = logging.getLogger(__name__)

USER_AGENT = "sports-calendar/1.0 (+https://github.com)"
_cache: dict[str, Any] = {}
_sleep = time.sleep  # patched in tests


class FetchError(Exception):
    """A request failed after all retries."""


class NotFound(FetchError):
    """The server returned 404 (not retried; callers may treat as 'no data yet')."""


def clear_cache() -> None:
    _cache.clear()


def get_json(url: str, params: dict | None = None, *, attempts: int = 3, timeout: int = 20) -> Any:
    key = url + ("?" + urlencode(params) if params else "")
    if key in _cache:
        return _cache[key]

    delay = 1.0
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT})
            if resp.status_code == 404:
                raise NotFound(key)
            resp.raise_for_status()
            data = resp.json()
        except NotFound:
            raise
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            log.warning("fetch failed (attempt %d/%d) %s: %s", attempt, attempts, key, exc)
            if attempt < attempts:
                _sleep(delay)
                delay *= 2
            continue
        _cache[key] = data
        return data

    raise FetchError(f"{key}: {last_error}")
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_http.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add sports_calendar/http.py tests/test_http.py
git commit -m "feat: add retrying, cached get_json network seam"
```

---

### Task 4: Season/date math

**Files:**
- Create: `sports_calendar/seasons.py`, `tests/test_seasons.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_seasons.py`:
```python
from datetime import date

from sports_calendar import seasons


def test_season_end_year():
    assert seasons.season_end_year(date(2026, 8, 25)) == 2027
    assert seasons.season_end_year(date(2026, 7, 1)) == 2027
    assert seasons.season_end_year(date(2026, 6, 30)) == 2026
    assert seasons.season_end_year(date(2027, 1, 15)) == 2027


def test_nhl_season_id():
    assert seasons.nhl_season_id(date(2026, 8, 25)) == "20262027"
    assert seasons.nhl_season_id(date(2026, 5, 15)) == "20252026"


def test_mlb_seasons():
    assert seasons.mlb_seasons(date(2026, 8, 25)) == [2026, 2027]


def test_espn_season():
    assert seasons.espn_season(date(2026, 8, 25)) == 2027
    assert seasons.espn_season(date(2026, 4, 1)) == 2026


def test_window_resolves_in_season_end_year():
    assert seasons.window(date(2026, 8, 25), "04-01", "06-15") == (date(2027, 4, 1), date(2027, 6, 15))
    assert seasons.window(date(2026, 5, 15), "04-01", "06-15") == (date(2026, 4, 1), date(2026, 6, 15))


def test_tennis_years():
    assert seasons.tennis_years(date(2026, 8, 25)) == [2026]
    assert seasons.tennis_years(date(2026, 11, 2)) == [2026, 2027]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_seasons.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement seasons.py**

`sports_calendar/seasons.py`:
```python
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
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_seasons.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add sports_calendar/seasons.py tests/test_seasons.py
git commit -m "feat: add season and date-window helpers"
```

---

### Task 5: ESPN adapter — events, team schedules, scoreboard

**Files:**
- Create: `sports_calendar/sources/espn.py`, `tests/test_espn.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_espn.py`:
```python
from datetime import date, datetime, timezone

from sports_calendar.sources import espn


def test_parse_soccer_fixture(fixture):
    data = fixture("espn_liverpool_fixtures.json")
    games = espn.parse_schedule(data, sport="soccer", league_slug="all", league_name="Soccer")
    assert len(games) == 37
    g = games[0]
    assert g.uid.startswith("espn-")
    assert g.sport == "soccer"
    assert g.competition == "eng.1"
    assert g.competition_name == "English Premier League"
    assert g.home.short == "Liverpool" and g.away.short == "Nottm Forest"
    assert g.away.name == "Nottingham Forest"
    assert g.start == datetime(2026, 8, 29, 11, 30, tzinfo=timezone.utc)
    assert g.day == date(2026, 8, 29)
    assert g.time_valid is True
    assert g.season_type == "regular"
    assert g.neutral is False


def test_parse_soccer_results_include_friendlies(fixture):
    games = espn.parse_schedule(fixture("espn_liverpool_results.json"), "soccer", "all", "Soccer")
    assert {g.competition for g in games} == {"eng.1", "club.friendly"}


def test_soccer_team_schedule_merges_results_and_fixtures(fake_fetch):
    calls = fake_fetch([
        (("teams/364/schedule", "fixture=true"), "espn_liverpool_fixtures.json"),
        ("teams/364/schedule", "espn_liverpool_results.json"),
    ])
    games = espn.soccer_team_schedule("364")
    assert len(games) == 44
    assert len(calls) == 2
    assert len({g.uid for g in games}) == 44


def test_us_team_schedule_fetches_regular_and_post(fake_fetch):
    fake_fetch([
        (("teams/7/schedule", "seasontype=2"), "espn_nuggets_2026_27_reg.json"),
        (("teams/7/schedule", "seasontype=3"), "espn_nuggets_2025_26_post.json"),
    ])
    games = espn.us_team_schedule("basketball", "nba", "7", 2027)
    assert len(games) == 86
    post = [g for g in games if g.season_type == "post"]
    assert len(post) == 6
    assert post[0].notes == "West 1st Round - Game 1"
    assert post[0].series_game == 1
    reg = [g for g in games if g.season_type == "regular"]
    assert reg[0].competition == "nba" and reg[0].competition_name == "NBA"
    assert reg[0].home.short == "Thunder" and reg[0].away.short == "Nuggets"
    assert reg[0].broadcast == "ESPN"


def test_us_team_schedule_tolerates_missing_events(fake_fetch):
    fake_fetch([
        (("teams/7/schedule", "seasontype=2"), "espn_nuggets_2026_27_reg.json"),
        (("teams/7/schedule", "seasontype=3"), {"events": []}),
    ])
    assert len(espn.us_team_schedule("basketball", "nba", "7", 2027)) == 80


def test_ncaa_postseason_notes(fixture):
    games = espn.parse_schedule(fixture("espn_denver_hockey_2025_26.json"), "hockey",
                                "mens-college-hockey", "NCAA Hockey")
    assert len(games) == 43
    first = games[0]
    assert first.away.short == "Denver" and first.home.short == "Air Force"
    assert first.venue == "Cadet Ice Arena"
    post = [g for g in games if g.season_type == "post"]
    assert len(post) == 4
    assert post[-1].notes == "NCAA Men's Hockey National Championship"


def test_scoreboard_round_slugs_and_notes(fake_fetch):
    calls = fake_fetch([("uefa.champions/scoreboard", "espn_ucl_2025_26.json")])
    games = espn.scoreboard("soccer", "uefa.champions", date(2025, 8, 1), date(2026, 6, 1))
    assert "dates=20250801-20260601" in calls[0] and "limit=1000" in calls[0]
    assert len(games) == 189
    final = [g for g in games if g.round_slug == "final"]
    assert len(final) == 1
    assert final[0].home.short == "PSG" and final[0].away.short == "Arsenal"
    assert final[0].competition == "uefa.champions"
    assert final[0].competition_name == "UEFA Champions League"
    semis = [g for g in games if g.round_slug == "semifinals"]
    assert len(semis) == 4
    assert any(g.notes.startswith("2nd Leg") for g in semis if g.notes)


def test_scoreboard_nba_finals(fake_fetch):
    fake_fetch([("nba/scoreboard", "espn_nba_june_2026.json")])
    games = espn.scoreboard("basketball", "nba", date(2026, 6, 1), date(2026, 6, 25))
    assert [g.notes for g in games][:2] == ["NBA Finals - Game 1", "NBA Finals - Game 2"]
    assert games[0].season_type == "post"
    assert games[0].series_game == 1


def test_season_type_detection():
    ev = {"id": "1", "date": "2026-08-23T15:30Z", "competitions": [{"competitors": [
        {"homeAway": "home", "team": {"id": "1", "displayName": "A"}},
        {"homeAway": "away", "team": {"id": "2", "displayName": "B"}}]}]}
    assert espn.parse_event({**ev, "seasonType": {"type": 14308, "name": "2026-27 English Premier League"}},
                            "soccer", "eng.1", "PL").season_type == "regular"
    assert espn.parse_event({**ev, "seasonType": {"type": 1, "name": "Preseason"}}, "basketball", "nba", "NBA").season_type == "pre"
    assert espn.parse_event({**ev, "seasonType": {"type": 3, "name": "Postseason"}}, "hockey", "x", "X").season_type == "post"
    assert espn.parse_event({**ev, "season": {"year": 2026, "type": 3, "slug": "post-season"}}, "basketball", "nba", "NBA").season_type == "post"
    assert espn.parse_event({**ev, "season": {"year": 2025, "type": 13530, "slug": "promotion-semifinals"}}, "soccer", "eng.2", "C").season_type == "regular"


def test_parse_event_skips_malformed():
    assert espn.parse_event({"id": "1", "date": "2026-01-01T00:00Z", "competitions": [{}]},
                            "soccer", "eng.1", "PL") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_espn.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement espn.py (events, schedules, scoreboard)**

`sports_calendar/sources/espn.py`:
```python
"""ESPN public site API → Game. Undocumented but stable; no key required."""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone

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
    name = t.get("displayName") or t.get("name") or t["id"]
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
    if st.get("type") == 3 or (season.get("type") == 3 and not isinstance(season.get("type"), dict)):
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
    name = leagues[0].get("name") or LEAGUE_NAMES.get(league, league)
    if league == "nba":
        name = "NBA"
    return _dedupe(parse_schedule(data, sport, slug, name))
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_espn.py -q`
Expected: `10 passed`. If `test_parse_soccer_fixture` fails on `competition_name`, print `games[0].competition_name` and adjust the assertion to the actual ESPN league name (the fixture's `league.name` field).

- [ ] **Step 5: Commit**

```bash
git add sports_calendar/sources/espn.py tests/test_espn.py
git commit -m "feat: ESPN adapter for team schedules and scoreboards"
```

---

### Task 6: ESPN adapter — golf calendar and tennis majors

**Files:**
- Modify: `sports_calendar/sources/espn.py` (append)
- Create: `tests/test_espn_events.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_espn_events.py`:
```python
from datetime import date

from sports_calendar.sources import espn


def test_golf_calendar(fake_fetch):
    fake_fetch([("golf/pga/scoreboard", "espn_pga_scoreboard.json")])
    entries = espn.golf_calendar("pga")
    masters = [e for e in entries if e["label"] == "Masters Tournament"]
    assert masters == [{"id": "401811941", "label": "Masters Tournament",
                        "start": date(2026, 4, 9), "end": date(2026, 4, 12)}]


def test_tennis_majors_dedupes_and_extracts_rounds(fake_fetch):
    calls = fake_fetch([
        (("tennis/atp/scoreboard", "dates=202601"), "espn_tennis_ao_2026.json"),
        (("tennis/atp/scoreboard", "dates=202607"), "espn_tennis_wimbledon_2026.json"),
        (("tennis/atp/scoreboard", "dates=202609"), "espn_tennis_usopen_2026.json"),
        ("tennis/atp/scoreboard", {"events": []}),
    ])
    majors = espn.tennis_majors(2026)
    assert len(calls) == len(espn.TENNIS_PROBE_DATES)
    names = [m.name for m in majors]
    assert names == ["Australian Open", "Wimbledon", "US Open"]

    ao = majors[0]
    assert ao.start == date(2026, 1, 11)
    assert ao.end == date(2026, 2, 1)
    assert min(ao.round_dates["Round 1"]) == date(2026, 1, 18)
    assert set(ao.round_dates["Semifinal"]) == {date(2026, 1, 30)}
    assert ao.round_dates["Final"] == [date(2026, 2, 1)]

    wim = majors[1]
    assert wim.end == date(2026, 7, 12)
    assert min(wim.round_dates["Round 1"]) == date(2026, 6, 29)
    assert wim.round_dates["Final"] == [date(2026, 7, 12)]

    uso = majors[2]
    assert uso.end == date(2026, 9, 13)
    # ESPN publishes provisional round dates before the draw: Round 1 on the Sunday
    assert min(uso.round_dates["Round 1"]) == date(2026, 8, 30)
    assert uso.round_dates["Final"] == [date(2026, 9, 13)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_espn_events.py -q`
Expected: FAIL with `AttributeError: module ... has no attribute 'golf_calendar'`

- [ ] **Step 3: Append golf + tennis to espn.py**

Append to `sports_calendar/sources/espn.py`:
```python
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

from dataclasses import dataclass, field as _field  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

# One probe date inside each Grand Slam's window (two per slam for safety).
TENNIS_PROBE_DATES = ["01-20", "01-27", "05-28", "06-03", "07-01", "07-07", "08-28", "09-05"]
_NY = ZoneInfo("America/New_York")


@dataclass
class Major:
    id: str
    name: str
    start: date
    end: date                                   # last day of play (inclusive)
    round_dates: dict[str, list[date]] = _field(default_factory=dict)  # Men's Singles round → UTC dates


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
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_espn_events.py -q`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add sports_calendar/sources/espn.py tests/test_espn_events.py
git commit -m "feat: ESPN golf calendar and Grand Slam extraction"
```

---

### Task 7: MLB adapter

**Files:**
- Create: `sports_calendar/sources/mlb.py`, `tests/test_mlb.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_mlb.py`:
```python
from datetime import date, datetime, timezone

from sports_calendar.sources import mlb


def test_team_schedule(fake_fetch):
    calls = fake_fetch([(("statsapi.mlb.com", "teamId=121", "season=2026"), "mlb_mets_2026.json")])
    games = mlb.team_schedule("121", 2026)
    assert "gameType=R%2CF%2CD%2CL%2CW" in calls[0] and "hydrate=team" in calls[0]
    assert len(games) == 166
    g = games[0]
    assert g.uid.startswith("mlb-")
    assert g.sport == "baseball" and g.competition == "mlb" and g.competition_name == "MLB"
    assert g.start == datetime(2026, 3, 26, 17, 15, tzinfo=timezone.utc)
    assert g.day == date(2026, 3, 26)
    assert g.home.short == "Mets" and g.home.name == "New York Mets" and g.home.id == "121"
    assert g.away.short == "Pirates"
    assert g.season_type == "regular" and g.round_slug == "R"
    assert g.broadcast == "NBC/Peacock"
    assert g.time_valid is True


def test_unpublished_season_is_empty(fake_fetch):
    fake_fetch([("season=2027", {"dates": []})])
    assert mlb.team_schedule("121", 2027) == []


def test_not_found_is_empty(monkeypatch):
    from sports_calendar import http

    def boom(*a, **k):
        raise http.NotFound("x")

    monkeypatch.setattr(http, "get_json", boom)
    assert mlb.team_schedule("121", 2027) == []


def _game(**over):
    base = {
        "gamePk": 1, "gameType": "W", "gameDate": "2026-10-24T00:08:00Z", "officialDate": "2026-10-23",
        "status": {"detailedState": "Scheduled", "startTimeTBD": False},
        "teams": {"home": {"team": {"id": 121, "name": "New York Mets", "teamName": "Mets"}},
                  "away": {"team": {"id": 147, "name": "New York Yankees", "teamName": "Yankees"}}},
        "venue": {"name": "Citi Field"}, "seriesDescription": "World Series", "seriesGameNumber": 1,
        "broadcasts": [{"name": "FOX", "type": "TV"}, {"name": "WFAN", "type": "AM"}],
    }
    base.update(over)
    return base


def test_parse_postseason_game():
    g = mlb.parse_game(_game())
    assert g.season_type == "post" and g.series_title == "World Series" and g.series_game == 1
    assert g.day == date(2026, 10, 23)  # officialDate, not UTC date
    assert g.broadcast == "FOX"


def test_parse_tbd_and_postponed():
    tbd = mlb.parse_game(_game(status={"detailedState": "Scheduled", "startTimeTBD": True}))
    assert tbd.time_valid is False
    assert mlb.parse_game(_game(status={"detailedState": "Postponed", "startTimeTBD": False})) is None
    assert mlb.parse_game(_game(status={"detailedState": "Cancelled", "startTimeTBD": False})) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_mlb.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement mlb.py**

`sports_calendar/sources/mlb.py`:
```python
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
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_mlb.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add sports_calendar/sources/mlb.py tests/test_mlb.py
git commit -m "feat: MLB Stats API adapter"
```

---

### Task 8: NHL adapter

**Files:**
- Create: `sports_calendar/sources/nhl.py`, `tests/test_nhl.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_nhl.py`:
```python
from datetime import date, datetime, timezone

from sports_calendar.sources import nhl


def test_club_schedule(fake_fetch):
    fake_fetch([("club-schedule-season/COL/20252026", "nhl_col_2025_26.json")])
    games = nhl.club_schedule("COL", "20252026")
    assert {g.season_type for g in games} == {"pre", "regular", "post"}
    reg = [g for g in games if g.season_type == "regular"]
    assert reg[0].day == date(2025, 10, 7)
    assert reg[0].away.id == "COL" and reg[0].home.id == "LAK"
    assert reg[0].away.short == "Avalanche" and reg[0].away.name == "Colorado Avalanche"
    assert reg[0].sport == "hockey" and reg[0].competition == "nhl" and reg[0].competition_name == "NHL"
    post = [g for g in games if g.season_type == "post"]
    assert post[0].day == date(2026, 4, 19)
    assert post[0].start == datetime(2026, 4, 19, 19, 0, tzinfo=timezone.utc)
    assert post[0].series_round == 1 and post[0].series_game == 1 and post[0].series_title == "1st Round"
    assert post[0].round_slug == "R1"
    assert post[0].venue == "Ball Arena"
    assert "TNT" in post[0].broadcast


def test_stanley_cup_final(fake_fetch):
    calls = fake_fetch([
        ("playoff-bracket/2026", "nhl_bracket_2026.json"),
        ("schedule/playoff-series/20252026/o/", "nhl_series_scf_2026.json"),
    ])
    games = nhl.stanley_cup_final("20252026")
    assert len(calls) == 2
    assert len(games) >= 4
    g = games[0]
    assert g.start == datetime(2026, 6, 3, 0, 0, tzinfo=timezone.utc)
    assert g.away.id == "VGK" and g.home.id == "CAR"
    assert g.home.short == "Hurricanes"
    assert g.season_type == "post" and g.series_round == 4 and g.series_game == 1
    assert g.series_title == "Stanley Cup Final" and g.round_slug == "SCF"
    assert g.venue == "Lenovo Center"


def test_stanley_cup_final_before_playoffs(monkeypatch):
    from sports_calendar import http

    def not_found(*a, **k):
        raise http.NotFound("x")

    monkeypatch.setattr(http, "get_json", not_found)
    assert nhl.stanley_cup_final("20262027") == []


def test_stanley_cup_final_series_not_set(fake_fetch):
    fake_fetch([("playoff-bracket/2027", {"series": [{"playoffRound": 1, "seriesLetter": "A"}]})])
    assert nhl.stanley_cup_final("20262027") == []


def _game(**over):
    base = {
        "id": 2026020001, "gameType": 2, "gameDate": "2026-10-08", "startTimeUTC": "2026-10-09T01:00:00Z",
        "venue": {"default": "Ball Arena"}, "neutralSite": False, "gameScheduleState": "OK",
        "tvBroadcasts": [{"network": "ESPN", "countryCode": "US", "market": "N", "sequenceNumber": 1},
                         {"network": "ALT", "countryCode": "US", "market": "H", "sequenceNumber": 2},
                         {"network": "SN", "countryCode": "CA", "market": "N", "sequenceNumber": 3}],
        "awayTeam": {"abbrev": "DAL", "commonName": {"default": "Stars"}, "placeName": {"default": "Dallas"}},
        "homeTeam": {"abbrev": "COL", "commonName": {"default": "Avalanche"}, "placeName": {"default": "Colorado"}},
    }
    base.update(over)
    return base


def test_parse_game_broadcast_prefers_us_national():
    g = nhl.parse_game(_game())
    assert g.broadcast == "ESPN, ALT"
    assert g.day == date(2026, 10, 8)  # gameDate (local), not UTC date


def test_parse_game_tbd_and_postponed():
    assert nhl.parse_game(_game(gameScheduleState="TBD")).time_valid is False
    assert nhl.parse_game(_game(gameScheduleState="PPD")) is None
    assert nhl.parse_game(_game(gameScheduleState="CNCL")) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_nhl.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement nhl.py**

`sports_calendar/sources/nhl.py`:
```python
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
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_nhl.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add sports_calendar/sources/nhl.py tests/test_nhl.py
git commit -m "feat: NHL API adapter incl. Stanley Cup Final lookup"
```

---

### Task 9: Catalog (rule source → adapter call)

**Files:**
- Create: `sports_calendar/catalog.py`, `tests/test_catalog.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_catalog.py`:
```python
from datetime import date

from sports_calendar.catalog import Catalog


def test_team_games_dispatch(fake_fetch):
    calls = fake_fetch([
        (("soccer/all/teams/364/schedule", "fixture=true"), "espn_liverpool_fixtures.json"),
        ("soccer/all/teams/364/schedule", "espn_liverpool_results.json"),
        (("basketball/nba/teams/7/schedule", "season=2027", "seasontype=2"), "espn_nuggets_2026_27_reg.json"),
        (("basketball/nba/teams/7/schedule", "season=2027", "seasontype=3"), {"events": []}),
        (("statsapi.mlb.com", "season=2026"), "mlb_mets_2026.json"),
        (("statsapi.mlb.com", "season=2027"), {"dates": []}),
        ("club-schedule-season/COL/20262027", "nhl_col_2026_27.json"),
    ])
    cat = Catalog(today=date(2026, 8, 25))
    assert len(cat.team_games({"source": "espn_soccer", "team": 364})) == 44
    assert len(cat.team_games({"source": "espn", "sport": "basketball", "league": "nba", "team": 7})) == 80
    assert len(cat.team_games({"source": "mlb", "team": 121})) == 166
    assert len(cat.team_games({"source": "nhl", "team": "COL"})) == 88
    assert len(calls) == 7


def test_competition_games_dispatch(fake_fetch):
    calls = fake_fetch([
        ("uefa.champions/scoreboard", "espn_ucl_2025_26.json"),
        ("nba/scoreboard", "espn_nba_june_2026.json"),
        ("playoff-bracket/2026", "nhl_bracket_2026.json"),
        ("playoff-series/20252026/o/", "nhl_series_scf_2026.json"),
    ])
    cat = Catalog(today=date(2026, 5, 15))
    ucl = cat.competition_games({"source": "espn_soccer", "league": "uefa.champions", "window": ["04-01", "06-15"]})
    assert len(ucl) == 189
    assert "dates=20260401-20260615" in calls[0]
    nba = cat.competition_games({"source": "espn", "sport": "basketball", "league": "nba", "window": ["05-25", "06-30"]})
    assert len(nba) == 5
    assert "dates=20260525-20260630" in calls[1]
    scf = cat.competition_games({"source": "nhl"})
    assert scf[0].series_title == "Stanley Cup Final"


def test_golf_and_tennis(fake_fetch):
    fake_fetch([
        ("golf/pga/scoreboard", "espn_pga_scoreboard.json"),
        (("tennis/atp/scoreboard", "dates=202607"), "espn_tennis_wimbledon_2026.json"),
        ("tennis/atp/scoreboard", {"events": []}),
    ])
    cat = Catalog(today=date(2026, 8, 25))
    assert any(e["label"] == "Masters Tournament" for e in cat.golf_calendar("pga"))
    assert [m.name for m in cat.tennis_majors()] == ["Wimbledon"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_catalog.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement catalog.py**

`sports_calendar/catalog.py`:
```python
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
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_catalog.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add sports_calendar/catalog.py tests/test_catalog.py
git commit -m "feat: catalog dispatches rule sources to adapters by season"
```

---

### Task 10: Rules — team filters, competition filters, dedupe

**Files:**
- Create: `sports_calendar/rules.py`, `tests/test_rules.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_rules.py`:
```python
from datetime import date, datetime, timezone

import pytest

from sports_calendar import rules
from sports_calendar.models import Game, Team

LIV = Team("364", "Liverpool", "Liverpool")
NEW = Team("361", "Newcastle United", "Newcastle")
RMA = Team("86", "Real Madrid", "Real Madrid")
BAR = Team("83", "Barcelona", "Barcelona")
ARS = Team("359", "Arsenal", "Arsenal")
CHE = Team("363", "Chelsea", "Chelsea")
MCI = Team("382", "Manchester City", "Man City")
DU = Team("2172", "Denver Pioneers", "Denver")
AF = Team("2160", "Air Force Falcons", "Air Force")
METS = Team("121", "New York Mets", "Mets")
ROX = Team("115", "Colorado Rockies", "Rockies")
COL = Team("COL", "Colorado Avalanche", "Avalanche")
DAL = Team("DAL", "Dallas Stars", "Stars")


def mk(uid, home, away, day, *, sport="soccer", comp="eng.1", comp_name="Premier League", **over):
    g = Game(uid=uid, sport=sport, competition=comp, competition_name=comp_name, home=home, away=away,
             day=day, start=datetime(day.year, day.month, day.day, 19, 0, tzinfo=timezone.utc))
    for k, v in over.items():
        setattr(g, k, v)
    return g


class FakeCatalog:
    def __init__(self, team_games=None, competition_games=None, golf=None, majors=None):
        self._team = team_games or {}
        self._comp = competition_games or []
        self._golf = golf or []
        self._majors = majors or []
        self.team_calls = []

    def team_games(self, rule):
        self.team_calls.append(str(rule["team"]))
        return self._team.get(str(rule["team"]), [])

    def competition_games(self, rule):
        return self._comp

    def golf_calendar(self, tour):
        return self._golf

    def tennis_majors(self):
        return self._majors


def test_team_all_with_competition_filter():
    games = [mk("a", LIV, NEW, date(2026, 8, 29)), mk("b", NEW, LIV, date(2026, 9, 5), comp="uefa.champions")]
    cat = FakeCatalog({"364": games})
    assert [g.uid for g in rules.evaluate({"name": "LFC", "type": "team_all", "source": "espn_soccer", "team": 364}, cat)] == ["a", "b"]
    out = rules.evaluate({"name": "LFC UCL", "type": "team_all", "source": "espn_soccer", "team": 364,
                          "competitions": ["uefa.champions"]}, cat)
    assert [g.uid for g in out] == ["b"]


def test_head_to_head_filters_opponents_competition_and_only_away():
    games = [
        mk("liga", BAR, RMA, date(2026, 10, 25), comp="esp.1"),
        mk("copa", RMA, BAR, date(2027, 1, 20), comp="esp.copa_del_rey"),
        mk("other", BAR, NEW, date(2026, 11, 1), comp="esp.1"),
    ]
    cat = FakeCatalog({"83": games})
    rule = {"name": "Clasico", "type": "head_to_head", "source": "espn_soccer", "team": 83,
            "opponents": [86], "competitions": ["esp.1"]}
    assert [g.uid for g in rules.evaluate(rule, cat)] == ["liga"]
    rule.pop("competitions")
    assert [g.uid for g in rules.evaluate(rule, cat)] == ["liga", "copa"]

    mets = [mk("home", METS, ROX, date(2026, 5, 1), sport="baseball", comp="mlb", comp_name="MLB"),
            mk("away", ROX, METS, date(2026, 6, 1), sport="baseball", comp="mlb", comp_name="MLB")]
    cat = FakeCatalog({"121": mets})
    rule = {"name": "Coors", "type": "head_to_head", "source": "mlb", "team": 121, "opponents": [115], "only_away": True}
    assert [g.uid for g in rules.evaluate(rule, cat)] == ["away"]


def test_group_h2h_fetches_each_team_and_dedupes():
    ars_che = mk("ac", ARS, CHE, date(2026, 9, 1))
    che_mci = mk("cm", CHE, MCI, date(2026, 10, 1))
    ars_new = mk("an", ARS, NEW, date(2026, 9, 8))
    che_cup = mk("cup", CHE, ARS, date(2026, 12, 1), comp="eng.league_cup")
    cat = FakeCatalog({"359": [ars_che, ars_new, che_cup], "363": [ars_che, che_mci, che_cup], "382": [che_mci]})
    rule = {"name": "Big four", "type": "group_h2h", "source": "espn_soccer", "teams": [359, 363, 382],
            "competitions": ["eng.1"]}
    out = rules.evaluate(rule, cat)
    assert sorted(g.uid for g in out) == ["ac", "cm"]
    assert sorted(cat.team_calls) == ["359", "363", "382"]


def test_opener_per_sport():
    avs = [mk("pre", DAL, COL, date(2026, 9, 25), sport="hockey", comp="nhl", comp_name="NHL", season_type="pre"),
           mk("op", COL, DAL, date(2026, 10, 8), sport="hockey", comp="nhl", comp_name="NHL"),
           mk("g2", DAL, COL, date(2026, 10, 10), sport="hockey", comp="nhl", comp_name="NHL")]
    cat = FakeCatalog({"COL": avs})
    out = rules.evaluate({"name": "Avs opener", "type": "opener", "source": "nhl", "team": "COL"}, cat)
    assert [g.uid for g in out] == ["op"] and out[0].context == "Season Opener"

    mets = [mk("26", METS, ROX, date(2026, 3, 26), sport="baseball", comp="mlb", comp_name="MLB"),
            mk("26b", METS, ROX, date(2026, 3, 27), sport="baseball", comp="mlb", comp_name="MLB"),
            mk("27", ROX, METS, date(2027, 3, 30), sport="baseball", comp="mlb", comp_name="MLB")]
    cat = FakeCatalog({"121": mets})
    out = rules.evaluate({"name": "Mets opener", "type": "opener", "source": "mlb", "team": 121}, cat)
    assert [g.uid for g in out] == ["26", "27"] and out[0].context == "Opening Day"


def test_home_games_excludes_away_and_neutral():
    games = [mk("home", DU, AF, date(2025, 10, 11), sport="hockey", comp="mens-college-hockey", comp_name="NCAA Hockey"),
             mk("away", AF, DU, date(2025, 10, 12), sport="hockey", comp="mens-college-hockey", comp_name="NCAA Hockey"),
             mk("neutral", DU, AF, date(2025, 12, 1), sport="hockey", comp="mens-college-hockey", comp_name="NCAA Hockey", neutral=True)]
    cat = FakeCatalog({"2172": games})
    out = rules.evaluate({"name": "DU home", "type": "home_games", "source": "espn", "sport": "hockey",
                          "league": "mens-college-hockey", "team": 2172}, cat)
    assert [g.uid for g in out] == ["home"]


def test_postseason():
    games = [mk("r", COL, DAL, date(2027, 4, 1), sport="hockey", comp="nhl", comp_name="NHL"),
             mk("p", COL, DAL, date(2027, 4, 20), sport="hockey", comp="nhl", comp_name="NHL", season_type="post")]
    cat = FakeCatalog({"COL": games})
    out = rules.evaluate({"name": "Avs playoffs", "type": "postseason", "source": "nhl", "team": "COL"}, cat)
    assert [g.uid for g in out] == ["p"]


def test_round_tournament_all_and_finals():
    comp = [mk("qf", ARS, RMA, date(2026, 4, 8), comp="uefa.champions", round_slug="quarterfinals"),
            mk("lp", ARS, RMA, date(2026, 1, 8), comp="uefa.champions", round_slug="league-phase"),
            mk("f", ARS, RMA, date(2026, 5, 30), comp="uefa.champions", round_slug="final")]
    cat = FakeCatalog(competition_games=comp)
    out = rules.evaluate({"name": "UCL KO", "type": "round", "source": "espn_soccer", "league": "uefa.champions",
                          "window": ["04-01", "06-15"], "rounds": ["quarterfinals", "semifinals", "final"]}, cat)
    assert sorted(g.uid for g in out) == ["f", "qf"]
    out = rules.evaluate({"name": "WC", "type": "tournament_all", "source": "espn_soccer", "league": "fifa.world",
                          "window": ["06-01", "07-31"]}, cat)
    assert len(out) == 3

    nba = [mk("wcf", ARS, RMA, date(2026, 5, 20), sport="basketball", comp="nba", comp_name="NBA",
              season_type="post", notes="West Finals - Game 1"),
           mk("fin", ARS, RMA, date(2026, 6, 4), sport="basketball", comp="nba", comp_name="NBA",
              season_type="post", notes="NBA Finals - Game 1")]
    cat = FakeCatalog(competition_games=nba)
    out = rules.evaluate({"name": "NBA Finals", "type": "finals", "source": "espn", "sport": "basketball",
                          "league": "nba", "window": ["05-25", "06-30"], "notes_prefix": "NBA Finals"}, cat)
    assert [g.uid for g in out] == ["fin"]
    cat = FakeCatalog(competition_games=nba)
    out = rules.evaluate({"name": "SCF", "type": "finals", "source": "nhl"}, cat)
    assert len(out) == 2  # nhl source already returns only final games


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        rules.evaluate({"name": "x", "type": "nope", "source": "nhl"}, FakeCatalog())


def test_apply_rules_dedupes_and_merges_rule_names():
    g = mk("a", LIV, NEW, date(2026, 8, 29))
    cat = FakeCatalog({"364": [g], "361": [g]})
    games, alldays = rules.apply_rules([
        {"name": "LFC", "type": "team_all", "source": "espn_soccer", "team": 364},
        {"name": "NUFC", "type": "team_all", "source": "espn_soccer", "team": 361},
    ], cat)
    assert len(games) == 1 and games[0].matched_rules == ["LFC", "NUFC"]
    assert alldays == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_rules.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement rules.py (game rules; golf/tennis/annotate come in Task 11)**

`sports_calendar/rules.py`:
```python
"""Turn config rules into lists of matched games / all-day events."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sports_calendar.models import AllDayEvent, Game

log = logging.getLogger(__name__)


def _ids(values) -> set[str]:
    return {str(v) for v in values or []}


def _in_competitions(rule: dict, game: Game) -> bool:
    comps = rule.get("competitions")
    return not comps or game.competition in comps


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

EVENT_RULES: dict = {}  # filled in Task 11


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
        log.info("rule %-28s → %d", rule.get("name"), len(matched))
        for item in matched:
            store = games if isinstance(item, Game) else events
            kept = store.setdefault(item.uid, item)
            if rule["name"] not in kept.matched_rules:
                kept.matched_rules.append(rule["name"])
            if kept is not item and item.context and not kept.context:
                kept.context = item.context
    return (sorted(games.values(), key=Game.sort_key), sorted(events.values(), key=lambda e: e.start))
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_rules.py -q`
Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add sports_calendar/rules.py tests/test_rules.py
git commit -m "feat: rule evaluation for team and competition rules"
```

---

### Task 11: Rules — golf, Grand Slams, context suffix

**Files:**
- Modify: `sports_calendar/rules.py`
- Create: `tests/test_rules_events.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_rules_events.py`:
```python
from datetime import date

from sports_calendar import rules
from sports_calendar.sources.espn import Major
from tests.test_rules import ARS, COL, DAL, DU, AF, FakeCatalog, LIV, METS, NEW, RMA, ROX, mk


def test_golf_event():
    cat = FakeCatalog(golf=[{"id": "1", "label": "Valero Texas Open", "start": date(2026, 4, 2), "end": date(2026, 4, 5)},
                            {"id": "401811941", "label": "Masters Tournament", "start": date(2026, 4, 9), "end": date(2026, 4, 12)}])
    out = rules.evaluate({"name": "Masters", "type": "golf_event", "tour": "pga", "label": "Masters Tournament",
                          "title": "The Masters"}, cat)
    assert len(out) == 1
    e = out[0]
    assert e.uid == "espn-golf-401811941" and e.title == "The Masters"
    assert e.start == date(2026, 4, 9) and e.end == date(2026, 4, 13)


def test_grand_slams_with_draw_and_fallback():
    wim = Major(id="w", name="Wimbledon", start=date(2026, 6, 22), end=date(2026, 7, 12),
                round_dates={"Round 1": [date(2026, 6, 29), date(2026, 6, 30)],
                             "Semifinal": [date(2026, 7, 10)], "Final": [date(2026, 7, 12)]})
    ao = Major(id="a", name="Australian Open", start=date(2026, 1, 11), end=date(2026, 2, 1),
               round_dates={"Round 1": [date(2026, 1, 18), date(2026, 1, 19)],
                            "Semifinal": [date(2026, 1, 29), date(2026, 1, 30)], "Final": [date(2026, 2, 1)]})
    uso = Major(id="u", name="US Open", start=date(2026, 8, 24), end=date(2026, 9, 13), round_dates={})
    cat = FakeCatalog(majors=[ao, wim, uso])
    out = rules.evaluate({"name": "Slams", "type": "grand_slams"}, cat)
    by_title = {e.title: e for e in out}
    assert by_title["Wimbledon Day 1"].start == date(2026, 6, 29)
    assert by_title["Wimbledon Men's Semifinals"].start == date(2026, 7, 10)
    assert by_title["Wimbledon Men's Final"].start == date(2026, 7, 12)
    assert by_title["Wimbledon Men's Final"].end == date(2026, 7, 13)
    # AO Round 1 begins Sunday → Day 1 is the Monday; two semifinal days → two events
    assert by_title["Australian Open Day 1"].start == date(2026, 1, 19)
    ao_sf = sorted(e.start for e in out if e.title == "Australian Open Men's Semifinals")
    assert ao_sf == [date(2026, 1, 29), date(2026, 1, 30)]
    # US Open has no draw yet → derived from end date
    assert by_title["US Open Men's Final"].start == date(2026, 9, 13)
    assert by_title["US Open Men's Semifinals"].start == date(2026, 9, 11)
    assert by_title["US Open Day 1"].start == date(2026, 8, 31)
    assert len({e.uid for e in out}) == len(out)


def test_context_soccer():
    assert rules.context_for(mk("a", LIV, NEW, date(2026, 8, 29))) is None
    assert rules.context_for(mk("a", LIV, NEW, date(2026, 8, 29), comp="club.friendly", comp_name="Club Friendly")) == "Friendly"
    assert rules.context_for(mk("a", LIV, NEW, date(2026, 8, 29), comp="eng.fa", comp_name="English FA Cup")) == "FA Cup"
    assert rules.context_for(mk("a", LIV, NEW, date(2026, 8, 29), comp="uefa.champions", round_slug="league-phase")) == "UCL"
    assert rules.context_for(mk("a", ARS, RMA, date(2026, 5, 5), comp="uefa.champions", round_slug="semifinals",
                                notes="2nd Leg - Arsenal advance 2-1 on aggregate")) == "UCL Semifinal 2nd Leg"
    assert rules.context_for(mk("a", ARS, RMA, date(2026, 5, 30), comp="uefa.champions", round_slug="final")) == "UCL Final"
    assert rules.context_for(mk("a", ARS, RMA, date(2026, 5, 23), comp="eng.2", round_slug="promotion-final")) == "Championship Play-off Final"
    assert rules.context_for(mk("a", ARS, RMA, date(2026, 5, 9), comp="eng.2", round_slug="promotion-semifinals", notes="1st Leg")) == "Championship Play-off Semifinal 1st Leg"
    assert rules.context_for(mk("a", ARS, RMA, date(2026, 6, 11), comp="fifa.world", round_slug="group-stage")) == "World Cup"
    assert rules.context_for(mk("a", ARS, RMA, date(2026, 7, 19), comp="fifa.world", round_slug="final")) == "World Cup Final"
    # unknown non-domestic competition falls back to ESPN's name
    assert rules.context_for(mk("a", LIV, NEW, date(2026, 8, 29), comp="xyz.cup", comp_name="Mystery Cup")) == "Mystery Cup"


def test_context_us_sports():
    nhl = mk("a", COL, DAL, date(2027, 4, 20), sport="hockey", comp="nhl", comp_name="NHL", season_type="post",
             series_title="1st Round", series_game=3)
    assert rules.context_for(nhl) == "1st Round G3"
    scf = mk("a", COL, DAL, date(2027, 6, 5), sport="hockey", comp="nhl", comp_name="NHL", season_type="post",
             series_title="Stanley Cup Final", series_game=2)
    assert rules.context_for(scf) == "Stanley Cup Final G2"
    nba = mk("a", COL, DAL, date(2027, 6, 5), sport="basketball", comp="nba", comp_name="NBA", season_type="post",
             notes="NBA Finals - Game 4")
    assert rules.context_for(nba) == "NBA Finals G4"
    nba1 = mk("a", COL, DAL, date(2027, 4, 20), sport="basketball", comp="nba", comp_name="NBA", season_type="post",
              notes="West 1st Round - Game 1")
    assert rules.context_for(nba1) == "West 1st Round G1"
    mlb = mk("a", METS, ROX, date(2026, 10, 24), sport="baseball", comp="mlb", comp_name="MLB", season_type="post",
             series_title="World Series", series_game=1)
    assert rules.context_for(mlb) == "World Series G1"
    ncaa = mk("a", DU, AF, date(2026, 3, 27), sport="hockey", comp="mens-college-hockey", comp_name="NCAA Hockey",
              season_type="post", notes="NCAA Men's Hockey Championship - Loveland Regional Semifinal")
    assert rules.context_for(ncaa) == "NCAA Loveland Regional Semifinal"
    natty = mk("a", DU, AF, date(2026, 4, 11), sport="hockey", comp="mens-college-hockey", comp_name="NCAA Hockey",
               season_type="post", notes="NCAA Men's Hockey National Championship")
    assert rules.context_for(natty) == "NCAA Championship"
    bare = mk("a", DU, AF, date(2026, 3, 20), sport="hockey", comp="mens-college-hockey", comp_name="NCAA Hockey",
              season_type="post")
    assert rules.context_for(bare) == "Playoffs"
    regular = mk("a", COL, DAL, date(2026, 10, 8), sport="hockey", comp="nhl", comp_name="NHL")
    assert rules.context_for(regular) is None
    regular.context = "Season Opener"
    assert rules.context_for(regular) == "Season Opener"


def test_apply_rules_annotates_context():
    g = mk("a", ARS, RMA, date(2026, 5, 30), comp="uefa.champions", round_slug="final")
    cat = FakeCatalog(competition_games=[g])
    games, _ = rules.apply_rules([{"name": "UCL", "type": "round", "source": "espn_soccer", "league": "uefa.champions",
                                   "window": ["04-01", "06-15"], "rounds": ["final"]}], cat)
    assert games[0].context == "UCL Final"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_rules_events.py -q`
Expected: FAIL (`KeyError`/`ValueError: unknown rule type 'golf_event'`, `AttributeError: context_for`)

- [ ] **Step 3: Add golf, grand slams and context to rules.py**

Replace the line `EVENT_RULES: dict = {}  # filled in Task 11` in `sports_calendar/rules.py` with:
```python
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

import re  # noqa: E402

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
```

Then in `apply_rules`, change the final `return` to:
```python
    result = sorted(games.values(), key=Game.sort_key)
    annotate(result)
    return result, sorted(events.values(), key=lambda e: e.start)
```

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/pytest -q`
Expected: all pass (`test_rules_events.py`: 5 passed; earlier suites unchanged)

- [ ] **Step 5: Commit**

```bash
git add sports_calendar/rules.py tests/test_rules_events.py
git commit -m "feat: golf/tennis all-day rules and title context"
```

---

### Task 12: ICS output

**Files:**
- Create: `sports_calendar/ics.py`, `tests/test_ics.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_ics.py`:
```python
from datetime import date, datetime, timedelta, timezone

from icalendar import Calendar

from sports_calendar import ics
from sports_calendar.models import AllDayEvent, Game, Team

LIV = Team("364", "Liverpool", "Liverpool")
FOR = Team("393", "Nottingham Forest", "Nottm Forest")
MUN = Team("360", "Manchester United", "Man United")
COL = Team("COL", "Colorado Avalanche", "Avalanche")
DAL = Team("DAL", "Dallas Stars", "Stars")
NAMES = {"Man United": "United", "Man City": "City", "Avalanche": "Avs"}


def game(**over):
    g = Game(uid="espn-1", sport="soccer", competition="eng.1", competition_name="Premier League",
             home=LIV, away=FOR, day=date(2026, 8, 29),
             start=datetime(2026, 8, 29, 11, 30, tzinfo=timezone.utc), venue="Anfield", broadcast="NBC")
    for k, v in over.items():
        setattr(g, k, v)
    return g


def test_title_soccer_home_first_and_short_names():
    assert ics.title_for(game(), NAMES) == "Liverpool Nottm Forest"
    assert ics.title_for(game(home=MUN, away=LIV), NAMES) == "United Liverpool"
    assert ics.title_for(game(context="UCL Final"), NAMES) == "Liverpool Nottm Forest · UCL Final"


def test_title_us_sports_away_first():
    g = game(sport="hockey", competition="nhl", competition_name="NHL", home=COL, away=DAL)
    assert ics.title_for(g, NAMES) == "Stars Avs"
    g.context = "1st Round G3"
    assert ics.title_for(g, NAMES) == "Stars Avs · 1st Round G3"


def test_title_time_tbd():
    assert ics.title_for(game(time_valid=False), NAMES) == "Liverpool Nottm Forest · time TBD"
    assert ics.title_for(game(time_valid=False, context="UCL Final"), NAMES) == "Liverpool Nottm Forest · UCL Final · time TBD"


def test_build_calendar_timed_event():
    g = game(matched_rules=["Liverpool"])
    data = ics.build_calendar([g], [], NAMES)
    cal = Calendar.from_ical(data)
    assert cal["X-WR-CALNAME"] == "Sports"
    assert str(cal["X-PUBLISHED-TTL"]) == "PT12H"
    ev = [c for c in cal.walk("VEVENT")][0]
    assert str(ev["UID"]) == "espn-1@sports-calendar"
    assert str(ev["SUMMARY"]) == "Liverpool Nottm Forest"
    assert ev["DTSTART"].dt == datetime(2026, 8, 29, 11, 30, tzinfo=timezone.utc)
    assert ev["DTEND"].dt == datetime(2026, 8, 29, 13, 30, tzinfo=timezone.utc)
    assert str(ev["LOCATION"]) == "Anfield"
    desc = str(ev["DESCRIPTION"])
    assert "Premier League" in desc and "TV: NBC" in desc and "Matched: Liverpool" in desc
    assert "VALARM" not in data.decode()


def test_durations_by_sport():
    for sport, hours in [("baseball", 3), ("hockey", 2.5), ("basketball", 2.5), ("soccer", 2)]:
        g = game(sport=sport)
        ev = Calendar.from_ical(ics.build_calendar([g], [], {})).walk("VEVENT")[0]
        assert ev["DTEND"].dt - ev["DTSTART"].dt == timedelta(hours=hours)


def test_tbd_game_is_all_day():
    g = game(time_valid=False)
    ev = Calendar.from_ical(ics.build_calendar([g], [], {})).walk("VEVENT")[0]
    assert ev["DTSTART"].dt == date(2026, 8, 29)
    assert ev["DTEND"].dt == date(2026, 8, 30)


def test_all_day_event():
    e = AllDayEvent(uid="espn-golf-1", title="The Masters", start=date(2026, 4, 9), end=date(2026, 4, 13),
                    description="Masters Tournament", matched_rules=["Masters"])
    ev = Calendar.from_ical(ics.build_calendar([], [e], {})).walk("VEVENT")[0]
    assert str(ev["SUMMARY"]) == "The Masters"
    assert ev["DTSTART"].dt == date(2026, 4, 9) and ev["DTEND"].dt == date(2026, 4, 13)
    assert str(ev["UID"]) == "espn-golf-1@sports-calendar"


def test_output_is_deterministic_and_sorted():
    a = game(uid="a", start=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc), day=date(2026, 9, 1))
    b = game(uid="b", start=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc), day=date(2026, 8, 1))
    out1 = ics.build_calendar([a, b], [], {})
    out2 = ics.build_calendar([b, a], [], {})
    assert out1 == out2
    uids = [str(e["UID"]) for e in Calendar.from_ical(out1).walk("VEVENT")]
    assert uids == ["b@sports-calendar", "a@sports-calendar"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_ics.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement ics.py**

`sports_calendar/ics.py`:
```python
"""Game / AllDayEvent → iCalendar bytes."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from icalendar import Calendar, Event

from sports_calendar.models import AllDayEvent, Game

DURATIONS = {
    "soccer": timedelta(hours=2),
    "baseball": timedelta(hours=3),
    "hockey": timedelta(hours=2, minutes=30),
    "basketball": timedelta(hours=2, minutes=30),
}
UID_DOMAIN = "sports-calendar"
CALENDAR_NAME = "Sports"


def shorten(name: str, display_names: dict[str, str]) -> str:
    return display_names.get(name, name)


def title_for(game: Game, display_names: dict[str, str]) -> str:
    if game.sport == "soccer":
        first, second = game.home, game.away
    else:
        first, second = game.away, game.home
    title = f"{shorten(first.short, display_names)} {shorten(second.short, display_names)}"
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
    return "\n".join(lines)


def _stamp(dt: datetime) -> datetime:
    # Deterministic DTSTAMP so unchanged schedules produce byte-identical files.
    return dt.astimezone(timezone.utc)


def _game_event(game: Game, display_names: dict[str, str]) -> Event:
    ev = Event()
    ev.add("uid", f"{game.uid}@{UID_DOMAIN}")
    ev.add("summary", title_for(game, display_names))
    ev.add("description", description_for(game))
    if game.venue:
        ev.add("location", game.venue)
    if game.time_valid and game.start is not None:
        ev.add("dtstart", game.start)
        ev.add("dtend", game.start + DURATIONS.get(game.sport, timedelta(hours=2)))
        ev.add("dtstamp", _stamp(game.start))
    else:
        ev.add("dtstart", game.day)
        ev.add("dtend", game.day + timedelta(days=1))
        ev.add("dtstamp", datetime.combine(game.day, time(0, 0), tzinfo=timezone.utc))
    ev.add("transp", "TRANSPARENT")
    return ev


def _allday_event(e: AllDayEvent) -> Event:
    ev = Event()
    ev.add("uid", f"{e.uid}@{UID_DOMAIN}")
    ev.add("summary", e.title)
    desc = e.description
    if e.matched_rules:
        desc = (desc + "\n" if desc else "") + "Matched: " + ", ".join(e.matched_rules)
    if desc:
        ev.add("description", desc)
    ev.add("dtstart", e.start)
    ev.add("dtend", e.end)
    ev.add("dtstamp", datetime.combine(e.start, time(0, 0), tzinfo=timezone.utc))
    ev.add("transp", "TRANSPARENT")
    return ev


def build_calendar(games: list[Game], alldays: list[AllDayEvent], display_names: dict[str, str]) -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//sports-calendar//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", CALENDAR_NAME)
    cal.add("x-published-ttl", "PT12H")
    cal.add("refresh-interval", "PT12H", parameters={"VALUE": "DURATION"})

    for g in sorted(games, key=lambda g: (g.sort_key(), g.uid)):
        cal.add_component(_game_event(g, display_names))
    for e in sorted(alldays, key=lambda e: (e.start, e.uid)):
        cal.add_component(_allday_event(e))
    return cal.to_ical()
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_ics.py -q`
Expected: `8 passed`. If `X-PUBLISHED-TTL` comparison fails because icalendar wraps it in a `vText`, compare with `str(...)` (already done) — if the `refresh-interval` `parameters=` kwarg is rejected by the installed icalendar version, use `cal.add("refresh-interval", vDuration(timedelta(hours=12)), parameters={"VALUE": "DURATION"})` importing `vDuration` from `icalendar`.

- [ ] **Step 5: Commit**

```bash
git add sports_calendar/ics.py tests/test_ics.py
git commit -m "feat: iCalendar serialization with scan-friendly titles"
```

---

### Task 13: Config, CLI entry point, end-to-end test

**Files:**
- Create: `config.yaml`, `sports_calendar/main.py`, `sports_calendar/__main__.py`, `tests/test_main.py`

- [ ] **Step 1: Write config.yaml**

`config.yaml`:
```yaml
# Sports calendar rules. Edit this file to change what lands on the calendar.
#
# Sources:   espn_soccer (ESPN, all competitions for a club)
#            espn        (ESPN US sports: needs sport + league)
#            mlb         (official MLB Stats API; team = MLB team id)
#            nhl         (official NHL API; team = 3-letter abbrev)
# Windows:   ["MM-DD", "MM-DD"] resolved in the season-end year
#            (July 1 onward counts as next year's season).

output: docs/sports.ics

# Short names used in event titles. Left side = the source's short name.
display_names:
  Man United: United
  Man City: City
  Avalanche: Avs
  Inter Milan: Inter
  Spurs: Tottenham

rules:
  # ---------------------------------------------------------------- Soccer
  - name: Liverpool
    type: team_all
    source: espn_soccer
    team: 364

  - name: Barcelona v Real Madrid / Atlético
    type: head_to_head
    source: espn_soccer
    team: 83
    opponents: [86, 1068]
    competitions: [esp.1]

  - name: Barcelona Champions League
    type: team_all
    source: espn_soccer
    team: 83
    competitions: [uefa.champions]

  - name: Champions League knockouts
    type: round
    source: espn_soccer
    league: uefa.champions
    window: ["04-01", "06-15"]
    rounds: [quarterfinals, semifinals, final]

  - name: Europa League final
    type: round
    source: espn_soccer
    league: uefa.europa
    window: ["05-01", "06-15"]
    rounds: [final]

  - name: Championship play-offs
    type: round
    source: espn_soccer
    league: eng.2
    window: ["05-01", "06-10"]
    rounds: [promotion-semifinals, promotion-final]

  - name: Juventus v Inter
    type: head_to_head
    source: espn_soccer
    team: 111
    opponents: [110]

  - name: Inter v Milan
    type: head_to_head
    source: espn_soccer
    team: 110
    opponents: [103]

  - name: Bayern v Dortmund
    type: head_to_head
    source: espn_soccer
    team: 132
    opponents: [124]

  - name: Tottenham v Chelsea / Arsenal
    type: head_to_head
    source: espn_soccer
    team: 367
    opponents: [363, 359]

  - name: Premier League big four
    type: group_h2h
    source: espn_soccer
    teams: [359, 363, 382, 360]     # Arsenal, Chelsea, Man City, Man United
    competitions: [eng.1]

  - name: Denver Pioneers home
    type: home_games
    source: espn
    sport: hockey
    league: mens-college-hockey
    team: 2172

  - name: Denver Pioneers postseason
    type: postseason
    source: espn
    sport: hockey
    league: mens-college-hockey
    team: 2172

  - name: World Cup
    type: tournament_all
    source: espn_soccer
    league: fifa.world
    window: ["06-01", "07-31"]

  # -------------------------------------------------------------- Baseball
  - name: Mets Opening Day
    type: opener
    source: mlb
    team: 121

  - name: Mets v Yankees / Dodgers / Phillies
    type: head_to_head
    source: mlb
    team: 121
    opponents: [147, 119, 143]

  - name: Mets at Coors Field
    type: head_to_head
    source: mlb
    team: 121
    opponents: [115]
    only_away: true

  - name: Mets postseason
    type: postseason
    source: mlb
    team: 121

  # ---------------------------------------------------------------- Hockey
  - name: Avs opener
    type: opener
    source: nhl
    team: COL

  - name: Avs v Stars
    type: head_to_head
    source: nhl
    team: COL
    opponents: [DAL]

  - name: Avs playoffs
    type: postseason
    source: nhl
    team: COL

  - name: Rangers opener
    type: opener
    source: nhl
    team: NYR

  - name: Rangers playoffs
    type: postseason
    source: nhl
    team: NYR

  - name: Stanley Cup Final
    type: finals
    source: nhl

  # ------------------------------------------------------------ Basketball
  - name: Nuggets v Thunder
    type: head_to_head
    source: espn
    sport: basketball
    league: nba
    team: 7
    opponents: [25]

  - name: Nuggets playoffs
    type: postseason
    source: espn
    sport: basketball
    league: nba
    team: 7

  - name: NBA Finals
    type: finals
    source: espn
    sport: basketball
    league: nba
    window: ["05-25", "06-30"]
    notes_prefix: NBA Finals

  # ------------------------------------------------------------------ Golf
  - name: The Masters
    type: golf_event
    tour: pga
    label: Masters Tournament
    title: The Masters

  # ---------------------------------------------------------------- Tennis
  - name: Grand Slams
    type: grand_slams
```

- [ ] **Step 2: Write the failing end-to-end test**

`tests/test_main.py`:
```python
from datetime import date
from pathlib import Path

from icalendar import Calendar

from sports_calendar import main

E2E_MAPPING = [
    (("soccer/all/teams/364/schedule", "fixture=true"), "espn_liverpool_fixtures.json"),
    ("soccer/all/teams/364/schedule", "espn_liverpool_results.json"),
    (("soccer/all/teams/83/schedule", "fixture=true"), "espn_barcelona_fixtures.json"),
    (("soccer/all/teams/359/schedule", "fixture=true"), "espn_arsenal_fixtures.json"),
    ("uefa.champions/scoreboard", "espn_ucl_2025_26.json"),
    ("uefa.europa/scoreboard", "espn_uel_may_2026.json"),
    ("eng.2/scoreboard", "espn_eng2_playoffs_2026.json"),
    ("fifa.world/scoreboard", "espn_worldcup_2026.json"),
    (("mens-college-hockey/teams/2172/schedule", "seasontype=2"), "espn_denver_hockey_2025_26.json"),
    (("basketball/nba/teams/7/schedule", "seasontype=2"), "espn_nuggets_2026_27_reg.json"),
    (("basketball/nba/teams/7/schedule", "seasontype=3"), "espn_nuggets_2025_26_post.json"),
    ("basketball/nba/scoreboard", "espn_nba_june_2026.json"),
    (("statsapi.mlb.com", "season=2026"), "mlb_mets_2026.json"),
    ("statsapi.mlb.com", {"dates": []}),
    ("club-schedule-season/COL/", "nhl_col_2025_26.json"),
    ("club-schedule-season/NYR/", "nhl_nyr_2026_27.json"),
    ("playoff-bracket/2026", "nhl_bracket_2026.json"),
    ("playoff-series/20252026/o/", "nhl_series_scf_2026.json"),
    ("golf/pga/scoreboard", "espn_pga_scoreboard.json"),
    (("tennis/atp/scoreboard", "dates=202601"), "espn_tennis_ao_2026.json"),
    (("tennis/atp/scoreboard", "dates=202607"), "espn_tennis_wimbledon_2026.json"),
    (("tennis/atp/scoreboard", "dates=202609"), "espn_tennis_usopen_2026.json"),
    ("tennis/atp/scoreboard", {"events": []}),
    ("/schedule", {"events": []}),  # any other team: no games
]


def test_end_to_end(fake_fetch, tmp_path):
    fake_fetch(E2E_MAPPING)
    out = tmp_path / "sports.ics"
    code = main.run(Path("config.yaml"), out, today=date(2026, 5, 15))
    assert code == 0
    cal = Calendar.from_ical(out.read_bytes())
    events = {str(e["SUMMARY"]): e for e in cal.walk("VEVENT")}
    summaries = list(events)

    assert sum(s.startswith("Liverpool ") or " Liverpool" in s for s in summaries) >= 40
    assert "Liverpool Nottm Forest" in events
    assert "PSG Arsenal · UCL Final" in events
    assert "Hull City Middlesbrough · Championship Play-off Final" in events or any(
        "Championship Play-off Final" in s for s in summaries)
    assert "Pirates Mets · Opening Day" in events
    assert "Golden Knights Hurricanes · Stanley Cup Final G1" in events
    assert "Knicks Spurs · NBA Finals G1" in events
    assert any(s.endswith("· Season Opener") and "Avs" in s for s in summaries)
    assert any("Avs" in s and "1st Round G1" in s for s in summaries)
    assert any(s.startswith("Air Force Denver") or s.endswith(" Denver") for s in summaries)

    masters = events["The Masters"]
    assert masters["DTSTART"].dt == date(2026, 4, 9) and masters["DTEND"].dt == date(2026, 4, 13)
    assert events["Wimbledon Men's Final"]["DTSTART"].dt == date(2026, 7, 12)
    assert events["Wimbledon Day 1"]["DTSTART"].dt == date(2026, 6, 29)
    assert events["Australian Open Day 1"]["DTSTART"].dt == date(2026, 1, 19)
    assert events["US Open Men's Final"]["DTSTART"].dt == date(2026, 9, 13)
    assert events["US Open Day 1"]["DTSTART"].dt == date(2026, 8, 31)  # Sunday start → first Monday

    for s in summaries:
        assert " vs " not in s and " @ " not in s
        assert "Manchester" not in s and "Avalanche" not in s
    assert "VALARM" not in out.read_text()


def test_run_fails_cleanly_on_fetch_error(monkeypatch, tmp_path):
    from sports_calendar import http

    def boom(*a, **k):
        raise http.FetchError("down")

    monkeypatch.setattr(http, "get_json", boom)
    out = tmp_path / "sports.ics"
    assert main.run(Path("config.yaml"), out, today=date(2026, 5, 15)) == 1
    assert not out.exists()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_main.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sports_calendar.main'`

- [ ] **Step 4: Implement main.py and __main__.py**

`sports_calendar/main.py`:
```python
"""CLI: load config → fetch → apply rules → write .ics"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import yaml

from sports_calendar import http
from sports_calendar.catalog import Catalog
from sports_calendar.ics import build_calendar
from sports_calendar.rules import apply_rules

log = logging.getLogger("sports_calendar")


def load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def run(config_path: Path, out_path: Path, today: date) -> int:
    config = load_config(config_path)
    catalog = Catalog(today=today)
    try:
        games, alldays = apply_rules(config["rules"], catalog)
    except http.FetchError as exc:
        log.error("aborting, a source failed: %s", exc)
        return 1
    data = build_calendar(games, alldays, config.get("display_names") or {})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    log.info("wrote %s: %d games, %d all-day events", out_path, len(games), len(alldays))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the sports .ics calendar")
    parser.add_argument("--config", default="config.yaml", type=Path)
    parser.add_argument("--out", type=Path, help="defaults to `output` in config")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today(),
                        help="override today's date (YYYY-MM-DD)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    config = load_config(args.config)
    out = args.out or Path(config.get("output", "docs/sports.ics"))
    return run(args.config, out, args.today)


if __name__ == "__main__":
    sys.exit(main())
```

`sports_calendar/__main__.py`:
```python
import sys

from sports_calendar.main import main

sys.exit(main())
```

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: all pass. If an e2e title assertion fails, print `sorted(summaries)` and check whether the *code* or the *expected string* is wrong before changing either — the fixture data is authoritative (e.g. ESPN may short-name a club differently than assumed).

- [ ] **Step 6: Run against the live APIs once**

Run: `.venv/bin/python -m sports_calendar -v`
Expected: INFO lines with a count per rule and `wrote docs/sports.ics: N games, M all-day events`. Then:

```bash
grep -c "BEGIN:VEVENT" docs/sports.ics
grep "^SUMMARY" docs/sports.ics | head -40
```
Sanity check the titles read the way the spec describes (home-first soccer, away-first US, `United`/`City`/`Avs`, no `vs`/`@`).

- [ ] **Step 7: Commit**

```bash
git add config.yaml sports_calendar/main.py sports_calendar/__main__.py tests/test_main.py docs/sports.ics
git commit -m "feat: config, CLI entry point and first generated calendar"
```

---

### Task 14: GitHub Actions workflow and README

**Files:**
- Create: `.github/workflows/build.yml`, `README.md`

- [ ] **Step 1: Write the workflow**

`.github/workflows/build.yml`:
```yaml
name: Build sports calendar

on:
  schedule:
    - cron: "0 10 * * *"      # daily 10:00 UTC = 04:00 Denver (MDT) / 03:00 (MST)
  workflow_dispatch:
  push:
    paths: ["config.yaml", "sports_calendar/**", ".github/workflows/build.yml"]

permissions:
  contents: write

concurrency:
  group: build-calendar
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - run: pip install -r requirements.txt

      - name: Test
        run: pytest -q

      - name: Build calendar
        run: python -m sports_calendar -v

      - name: Commit if changed
        run: |
          git config user.name "sports-calendar bot"
          git config user.email "actions@users.noreply.github.com"
          git add docs/sports.ics
          if git diff --cached --quiet; then
            echo "No changes"
          else
            git commit -m "Update sports.ics ($(date -u +%Y-%m-%d))"
            git push
          fi
```

- [ ] **Step 2: Write the README**

`README.md`:
```markdown
# Sports Calendar

Generates `docs/sports.ics` — every game I want to watch — from free, key-less
sports APIs (ESPN, MLB Stats API, NHL API). GitHub Actions rebuilds it daily;
Apple Calendar subscribes to the file.

## Subscribe in Apple Calendar

URL (replace `USER`):

    https://raw.githubusercontent.com/USER/sports-calendar/main/docs/sports.ics

Mac: Calendar → File → New Calendar Subscription… → paste URL → set
**Location: iCloud** (so it syncs to iPhone) and **Auto-refresh: Every day**.
Alerts are intentionally off; titles are built for scanning:

    Liverpool Newcastle              soccer: home team first
    Stars Avs                        US sports: away team first
    Avs Stars · 1st Round G3         suffix only when it adds information
    PSG Arsenal · UCL Final
    Pirates Mets · Opening Day
    The Masters                      all-day, Thu–Sun
    Wimbledon Men's Final            all-day

## Changing what's on the calendar

Edit `config.yaml` and push. Rule types:

| type | what it matches | fields |
|---|---|---|
| `team_all` | every game of a team | `team`, optional `competitions` |
| `head_to_head` | games vs listed opponents | `team`, `opponents`, optional `competitions`, `only_away` |
| `group_h2h` | games where both sides are in a set | `teams`, optional `competitions` |
| `opener` | first regular-season game | `team` |
| `home_games` | non-neutral home games | `team` |
| `postseason` | all playoff games | `team` |
| `round` | competition games in given rounds | `league`, `window`, `rounds` |
| `tournament_all` | every game of a competition | `league`, `window` |
| `finals` | championship series | `source: nhl`, or `league`+`window`+`notes_prefix` for ESPN |
| `golf_event` | all-day block for a tournament | `tour`, `label`, `title` |
| `grand_slams` | Day 1 / Men's SF / Men's Final of each major | — |

Sources: `espn_soccer` (club id), `espn` (needs `sport` + `league`, team id),
`mlb` (team id), `nhl` (abbrev). Find ESPN ids in the URL of a team page on
espn.com; MLB ids at `statsapi.mlb.com/api/v1/teams?sportId=1`.

`display_names` maps a source's short name to what you want in the title
(`Man United: United`).

## Run locally

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/pytest -q
    .venv/bin/python -m sports_calendar -v            # writes docs/sports.ics
    .venv/bin/python -m sports_calendar --today 2026-05-15 --out /tmp/test.ics

## First-time GitHub setup (done from a normal Terminal, not from Claude)

1. On github.com create an empty **public** repo named `sports-calendar` (no README).
2. In this folder:

       git remote add origin https://github.com/USER/sports-calendar.git
       git push -u origin main

   Use your normal GitHub login when prompted (browser / token / SSH — whatever
   you already use). Nothing needs to be stored in the repo.
3. On GitHub: Actions tab → "Build sports calendar" → Run workflow. The first
   run commits `docs/sports.ics`. After that it runs daily on its own.
4. Subscribe in Apple Calendar with the URL above.

## Notes

- If any source fails, the run aborts and the previous calendar stays
  published; GitHub emails you about the failed workflow.
- GitHub pauses scheduled workflows in repos with no commits for 60 days. If
  the calendar stops updating, open the Actions tab and re-enable it.
- `fixtures/` holds recorded API responses used by the tests; they are not
  used by the daily build.
```

- [ ] **Step 3: Validate the workflow YAML parses**

Run: `.venv/bin/python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/build.yml')); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Full test run**

Run: `.venv/bin/pytest -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/build.yml README.md
git commit -m "ci: daily GitHub Actions build; README with setup and rule reference"
```

---

## Hand-off to Lee (not a code task)

After Task 14 the repo is complete locally on `main`. Lee then, in a separate Terminal:

1. Creates the public repo `sports-calendar` on GitHub.
2. `git remote add origin …` and `git push -u origin main`.
3. Triggers the workflow once from the Actions tab and subscribes in Apple Calendar.
