# Sports Calendar — Design

**Date:** 2026-08-25
**Status:** Approved by Lee (pending spec review)

## Goal

Stop hand-creating calendar events for sports. A Python script pulls schedules
from free, key-less JSON APIs (no AI/LLM calls), applies a fixed set of rules
describing which games Lee wants to watch, and writes a single iCalendar file.
GitHub Actions runs it daily and commits the result; Apple Calendar subscribes
to the raw file URL once and stays current on Mac and iPhone.

## Non-goals

- No AI API calls of any kind.
- No server, database, or paid service.
- No write access to Apple Calendar, iCloud, Google Calendar, or any account.
- No credentials handled inside the Claude Code session (see Security).

## Data sources

All public, free, no API key:

| Source | Base URL | Used for |
|---|---|---|
| ESPN public API | `https://site.api.espn.com/apis/site/v2/sports/…` | All soccer, NBA, NCAA men's hockey, golf, tennis |
| MLB Stats API (official) | `https://statsapi.mlb.com/api/v1/schedule` | Mets |
| NHL API (official) | `https://api-web.nhle.com/v1/…` | Avalanche, Rangers, Stanley Cup Final |

Verified on 2026-08-25 that these return: full 2026-27 schedules for
Avalanche, Rangers, Nuggets and Mets (2026); Liverpool/Barcelona fixtures across
all competitions (`?fixture=true`); UCL/UEL events with round slugs
(`quarterfinals`, `semifinals`, `final`); Championship play-off legs (notes
`1st Leg` / `2nd Leg`); Denver Pioneers schedule with `Postseason` season type;
Masters with start/end dates in the PGA calendar; Grand Slam events with
`major: true` and per-round competition dates.

Endpoints:

- ESPN team schedule: `sports/{sport}/{league}/teams/{id}/schedule`
  (soccer uses league `all` and both the default call and `?fixture=true`
  to get played + upcoming; NBA/NCAA use `?season=YYYY&seasontype=N`).
- ESPN scoreboard by date range: `sports/{sport}/{league}/scoreboard?dates=YYYYMMDD-YYYYMMDD`
  for competition-wide rules (UCL rounds, UEL final, Championship play-offs,
  World Cup, NBA Finals).
- ESPN golf: `sports/golf/pga/scoreboard` → `leagues[0].calendar[]` (label,
  startDate, endDate).
- ESPN tennis: `sports/tennis/atp/scoreboard?dates=YYYYMMDD` → `events[]` with
  `major`, `date`, `endDate`, `groupings[]` (Men's Singles) → `competitions[]`
  with `round.displayName` and `date`.
- MLB: `schedule?teamId=121&season=YYYY&sportId=1&gameType=R,F,D,L,W`.
- NHL: `club-schedule-season/{TEAM}/{season}` (gameType 1 pre, 2 regular,
  3 playoffs; `seriesStatus.round` 1–4) and `schedule/{YYYY-MM-DD}` for
  league-wide Stanley Cup Final lookup.

ESPN team IDs: Liverpool 364, Barcelona 83, Real Madrid 86, Atlético 1068,
Juventus 111, Inter 110, AC Milan 103, Bayern 132, Dortmund 124, Arsenal 359,
Chelsea 363, Man City 382, Man United 360, Tottenham 367, Nuggets 7, OKC 25,
Denver Pioneers (NCAA hockey) 2172. MLB: Mets 121, Yankees 147, Dodgers 119,
Phillies 143, Rockies 115. NHL: COL, NYR, DAL. IDs are confirmed against the
API during implementation and live in `config.yaml`, not code.

## Rules

Season = whatever the source currently returns (current season, plus next
season once published). Playoff games appear the day the league schedules them.

### Soccer
1. **Liverpool** — every match in every competition ESPN lists, including
   pre-season friendlies.
2. **Barcelona** — La Liga matches vs Real Madrid and Atlético Madrid; every
   Champions League match.
3. **Champions League** — all quarterfinal, semifinal and final matches (both legs).
4. **Europa League** — final.
5. **EFL Championship** — play-off semifinals (both legs) and final.
6. **Juventus vs Inter**, **Inter vs AC Milan**, **Bayern vs Dortmund** — any competition.
7. **Tottenham vs Chelsea**, **Tottenham vs Arsenal** — any competition.
8. **Premier League** — any match where both teams are in
   {Arsenal, Chelsea, Manchester City, Manchester United}.
9. **Denver Pioneers (NCAA men's hockey)** — all home games (Denver is the
   `home` competitor and venue is not neutral) + all postseason games.
10. **FIFA World Cup** — all matches of the tournament proper (`fifa.world`).
    Qualifying is a different ESPN league and is not included.

### Baseball — New York Mets
11. Opening Day (first regular-season game of the season).
12. All games vs Yankees, Dodgers, Phillies.
13. Games vs Rockies **only when the Mets are the away team** (i.e. at Coors Field).
14. Every postseason game (MLB gameType F, D, L, W).

### Hockey
15. **Avalanche** — season opener (first gameType 2), all games vs Dallas, all
    playoff games (gameType 3).
16. **Rangers** — season opener, all playoff games.
17. **Stanley Cup Final** — all games (gameType 3, `seriesStatus.round == 4`).

### Basketball
18. **Nuggets** — all games vs Oklahoma City; all playoff games (`seasontype=3`).
19. **NBA Finals** — all games (ESPN NBA scoreboard, playoff season type,
    identified by the event's Finals round metadata / notes headline
    containing "NBA Finals").

### Golf
20. **The Masters** — one all-day event spanning Thursday through Sunday
    (inclusive), from the PGA calendar entry labelled "Masters Tournament".

### Tennis — each Grand Slam (Australian Open, Roland Garros, Wimbledon, US Open)
21. All-day event on the first Monday of main-draw play: `"{Slam} Day 1"`.
22. All-day event on the Men's Singles semifinal day: `"{Slam} Men's Semifinals"`.
23. All-day event on the Men's Singles final day: `"{Slam} Men's Final"`.

Dates come from the Men's Singles draw when ESPN has it (earliest `Round 1`
date → its Monday; `Semifinal` date; `Final` date). Before the draw exists,
they are derived from the event `endDate`: Final = last day (a Sunday),
Semifinals = Final − 2 days, Day 1 = Final − 13 days. This holds for all four
majors.

A game matched by several rules appears once; the notes list every rule that matched.

## Event format

Designed for scanning without opening the event.

- **Title**: two team names separated by a single space, no emoji, no "vs"/"@".
  - Soccer: home team first — `Liverpool Newcastle`.
  - MLB/NHL/NBA/NCAA: away team first, home second — `Stars Avs`.
  - Suffix ` · {context}` only when it adds information: playoff round and game
    (`Avs Stars · Playoffs R1 G3`), knockout stage (`Arsenal PSG · UCL Semifinal
    2nd Leg`), `· Opening Day`, `· Play-off Final`, `· World Cup Final`,
    `· Stanley Cup Final G2`, `· NBA Finals G5`. Regular-season and group-stage
    games get no suffix.
  - Short names from a `display_names` map in `config.yaml`, applied to every
    title: Manchester United → `United`, Manchester City → `City`,
    Colorado Avalanche → `Avs`, plus ESPN's already-short names (e.g.
    `Newcastle United` → `Newcastle`, `Dallas Stars` → `Stars`). Adding one is a
    one-line edit.
- **Description**: competition, round, venue, TV broadcast when the feed has it,
  and the rule name(s) that matched.
- **Time**: `DTSTART` in UTC; Apple renders in the viewer's zone.
  Durations: soccer 2h, MLB 3h, NHL 2h30, NBA 2h30, NCAA hockey 2h30.
- **Time TBD** (ESPN `timeValid: false`, or NHL/MLB `TBD` status): all-day
  event on the game date with suffix ` · time TBD`; becomes a timed event
  automatically once the time is set.
- **All-day events** (golf, tennis): `DTSTART;VALUE=DATE`, `DTEND` exclusive
  per RFC 5545.
- **UID**: `{source}-{event_id}@sports-calendar` — stable, so a reschedule
  updates the existing event instead of duplicating it. Tennis/golf derived
  events use `{source}-{event_id}-{kind}`.
- **Calendar properties**: `X-WR-CALNAME: Sports`, `X-PUBLISHED-TTL: PT12H`,
  `REFRESH-INTERVAL;VALUE=DURATION:PT12H`. No `VALARM`s.
- Past games in the current season stay in the file (useful record; small).

## Architecture

```
sports-calendar/
  config.yaml                    # rules, team IDs, display names — the file to edit
  sports_calendar/
    __init__.py
    models.py                    # Game, AllDayEvent dataclasses (single internal shape)
    http.py                      # GET with 3 retries + backoff, JSON decode
    sources/
      espn.py                    # ESPN team schedule / scoreboard / golf / tennis → Game
      mlb.py                     # MLB Stats API → Game
      nhl.py                     # NHL API → Game
    rules.py                     # rule types → predicate over Game; dedupe; context suffix
    names.py                     # display-name shortening
    ics.py                       # Game/AllDayEvent list → .ics bytes
    main.py                      # load config → fetch → filter → write docs/sports.ics
  tests/                         # pytest; unit per rule type / adapter; e2e ics build
  fixtures/                      # recorded real API JSON (captured 2026-08-25)
  docs/sports.ics                # output, committed by Actions
  .github/workflows/build.yml    # cron 10:00 UTC daily (04:00 Denver) + workflow_dispatch
  requirements.txt               # requests, icalendar, pyyaml; pytest for dev
  README.md                      # setup, subscribe instructions, editing rules
```

**Data flow**: `main.py` reads `config.yaml` → for each rule, asks the relevant
source adapter for the raw schedule (adapters cache by URL so a team's schedule
is fetched once even if several rules use it) → adapters normalize to `Game`
(id, source, sport, competition, round/notes, start UTC or date, time_valid,
home, away, venue, neutral, broadcast, season_type, playoff round/game number)
→ `rules.py` evaluates each rule's predicate, collects matches, dedupes by UID,
attaches matched-rule names and context suffix → `ics.py` serializes → written
to `docs/sports.ics`.

**Rule vocabulary** (`config.yaml`), each rule has `name`, `type`, `source`, and
type-specific fields:

| type | meaning | fields |
|---|---|---|
| `team_all` | every game of a team | `team`, optional `competitions` filter |
| `head_to_head` | games between team and opponents | `team`, `opponents`, optional `competitions`, optional `only_away` |
| `group_h2h` | games where both teams are in a set | `league`, `teams` |
| `opener` | first regular-season game | `team` |
| `home_games` | team's non-neutral home games | `team` |
| `postseason` | all playoff/postseason games of a team | `team` |
| `round` | all games of a competition in given rounds | `league`, `rounds` |
| `tournament_all` | every game of a competition | `league` |
| `finals` | championship series of a league | `league` |
| `golf_event` | multi-day all-day block | `tour`, `label` |
| `grand_slams` | Day 1 / Men's SF / Men's Final per major | — |

## Error handling

- Every HTTP call: 3 attempts, exponential backoff (1s, 2s, 4s), 20s timeout.
- If any source still fails or returns unparseable JSON, `main.py` exits
  non-zero and writes nothing. The workflow fails, no commit happens, the
  previously published `.ics` stays live, and GitHub emails the failure.
  Never publish a partial calendar.
- A rule matching zero games is normal (off-season, playoffs not yet set) and
  is logged at INFO, not an error.
- Unexpected shape inside a single event (missing competitor, etc.) is logged
  at WARNING and that event skipped; the run continues.

## Testing

- `pytest`, no network: adapters and rules are tested against recorded JSON in
  `fixtures/` (Liverpool fixtures, Barcelona fixtures, UCL May 2026, UEL May
  2026, Championship May 2026, World Cup 2026, Nuggets 2026-27, DU 2025-26,
  Avalanche 2025-26 incl. playoffs, Mets 2026, Wimbledon 2026 draw, US Open
  2026 event, PGA calendar). `http.get_json` is the one seam that is mocked.
- One end-to-end test builds the `.ics` from fixtures and parses it back with
  `icalendar`, asserting a handful of expected events (e.g. `Liverpool Newcastle`,
  `Masters` all-day 4 days, `Wimbledon Men's Final` on 2026-07-12).
- CI runs `pytest` before building; a failing test blocks publishing.

## Deployment & security

- GitHub Actions workflow: checkout → Python 3.12 → `pip install -r
  requirements.txt` → `pytest` → `python -m sports_calendar` → commit
  `docs/sports.ics` if changed, using the workflow's built-in `GITHUB_TOKEN`
  with `permissions: contents: write`. No personal tokens or secrets required.
- Subscription URL: `https://raw.githubusercontent.com/<user>/sports-calendar/main/docs/sports.ics`
  (Apple Calendar: File → New Calendar Subscription; location iCloud so it
  syncs to iPhone; auto-refresh daily).
- **Session boundary**: this project is built under a work Claude account. No
  credentials are entered, printed, or stored inside the Claude Code session.
  Repo creation and the first `git push` are done by Lee in a separate
  Terminal; commands are provided in the README. Local commits use the personal
  identity `c.leepryor@gmail.com`.

## Open assumptions (confirm during spec review)

- Tottenham–Chelsea / Tottenham–Arsenal match in any competition (not PL only).
- Liverpool friendlies are included.
- Title separator is a single space; switching to ` – ` is a one-line change in `ics.py`.
