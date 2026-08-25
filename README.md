# Sports Calendar

Generates `docs/sports.ics` — every game I want to watch — from free, key-less
sports APIs (ESPN, MLB Stats API, NHL API). No AI calls. GitHub Actions rebuilds
it daily; Apple Calendar subscribes to the file.

## Subscribe in Apple Calendar

URL (replace `USER` with your GitHub username):

    https://raw.githubusercontent.com/USER/sports-calendar/main/docs/sports.ics

Mac: Calendar → File → New Calendar Subscription… → paste URL → set
**Location: iCloud** (so it syncs to iPhone) and **Auto-refresh: Every day**.
Alerts are intentionally off; titles are built for scanning:

    Liverpool Newcastle              soccer: home team first
    Stars Avs                        US sports: away team first
    Avs Stars · 1st Round G3         suffix only when it adds information
    PSG Arsenal · UCL Final
    Pirates Mets · Opening Day
    Barcelona Real Madrid · time TBD kickoff not set yet → all-day until it is
    The Masters                      all-day, Thu–Sun
    Wimbledon Men's Final            all-day

## Changing what's on the calendar

Edit `config.yaml` and push — the workflow rebuilds on push. Rule types:

| type | what it matches | fields |
|---|---|---|
| `team_all` | every game of a team | `team`, optional `competitions` |
| `head_to_head` | games vs listed opponents (any competition unless filtered — includes pre-season friendlies) | `team`, `opponents`, optional `competitions`, `only_away` |
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

`display_names` maps a source's short name to what you want in the title, per
sport (`soccer: {Man United: United}`), so a soccer nickname can't rename a
US team that shares it.

ESPN competition slugs used in `competitions:` / `league:`: `eng.1` Premier
League, `eng.2` Championship, `esp.1` La Liga, `ita.1` Serie A, `ger.1`
Bundesliga, `uefa.champions`, `uefa.europa`, `fifa.world`, `club.friendly`.

## Run locally

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/pytest -q
    .venv/bin/python -m sports_calendar -v            # writes docs/sports.ics
    .venv/bin/python -m sports_calendar --today 2026-05-15 --out /tmp/test.ics

## First-time GitHub setup (from a normal Terminal)

1. On github.com create an empty **public** repo named `sports-calendar` (no README).
2. In this folder:

       git remote add origin https://github.com/USER/sports-calendar.git
       git push -u origin main

   Use your normal GitHub login when prompted (browser / token / SSH — whatever
   you already use). Nothing needs to be stored in the repo.
3. On GitHub: Actions tab → "Build sports calendar" → Run workflow. It runs the
   tests, rebuilds `docs/sports.ics`, and commits it if anything changed. After
   that it runs daily on its own.
4. Subscribe in Apple Calendar with the URL above.

## Notes

- Playoff games, cup draws and next season's fixtures appear the day the league
  publishes them; the calendar looks as far ahead as the sources do (MLB and NHL
  publish a full season; ESPN's PGA calendar rolls to the next season in January).
- If any source fails, the run aborts and the previous calendar stays
  published; GitHub emails you about the failed workflow.
- GitHub pauses scheduled workflows in repos with no commits for 60 days. If
  the calendar stops updating, open the Actions tab and re-enable it.
- `fixtures/` holds recorded API responses used by the tests; they are not
  used by the daily build.
