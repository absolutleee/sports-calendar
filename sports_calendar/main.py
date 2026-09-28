"""CLI: load config → fetch → apply rules → write .ics (main + optional secondary)"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from sports_calendar.catalog import Catalog
from sports_calendar.curation import apply_excludes, build_extras, drop_past
from sports_calendar.ics import CALENDAR_NAME, build_calendar
from sports_calendar.rules import apply_rules

log = logging.getLogger("sports_calendar")

CALENDARS = ("main", "secondary")


def load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def split_rules(config: dict) -> dict[str, list[dict]]:
    """Group rules by their `calendar:` (default main). A typo fails the build."""
    groups: dict[str, list[dict]] = {c: [] for c in CALENDARS}
    for rule in config["rules"]:
        cal = rule.get("calendar", "main")
        if cal not in groups:
            raise ValueError(f"rule {rule.get('name')!r}: unknown calendar {cal!r} (use one of {', '.join(CALENDARS)})")
        groups[cal].append(rule)
    if groups["secondary"] and not config.get("secondary"):
        raise ValueError("rules use `calendar: secondary` but config has no `secondary:` section")
    return groups


def run(config_path: Path, out_path: Path, today: date) -> int:
    """Writes the main calendar to `out_path` and, if configured, the secondary
    calendar next to it (named by `secondary.output`). The secondary calendar
    never repeats an event the main one has, so both can be shown at once."""
    config = load_config(config_path)
    groups = split_rules(config)
    catalog = Catalog(today=today)
    display_names = config.get("display_names") or {}
    tz = ZoneInfo(config.get("timezone") or "America/Denver")
    cutoff = today - timedelta(days=int(config.get("keep_past_days", 7)))

    built: dict[str, tuple] = {}
    for cal in CALENDARS:
        if cal == "secondary" and not config.get("secondary"):
            continue
        games, alldays, failures = apply_rules(groups[cal], catalog)
        if failures:
            log.warning("%s: built with %d failed source(s): %s", cal, len(failures), ", ".join(failures))
            if not games and not alldays:
                log.error("aborting, every %s calendar source failed", cal)
                return 1
        built[cal] = (games, alldays)

    if "secondary" in built:
        # Dedupe against what the main rules matched (before trimming/excludes),
        # so an excluded main-calendar game doesn't resurface on the secondary.
        taken = {x.uid for x in built["main"][0] + built["main"][1]}
        games, alldays = built["secondary"]
        built["secondary"] = ([g for g in games if g.uid not in taken], [e for e in alldays if e.uid not in taken])

    for cal, (games, alldays) in built.items():
        if cal == "main":
            path, name = out_path, CALENDAR_NAME
        else:
            path = out_path.parent / Path(config["secondary"]["output"]).name
            name = config["secondary"].get("name", "More Sports")
        total = len(games) + len(alldays)
        games, alldays = drop_past(games, alldays, cutoff, tz)
        dropped_past = total - len(games) - len(alldays)
        games, alldays = apply_excludes(games, alldays, config.get("exclude") or [], display_names, tz)
        extras = build_extras(config.get("extra") or [], tz) if cal == "main" else []
        excluded = total - dropped_past - len(games) - len(alldays)
        log.info("%s: dropped %d past (before %s); excluded %d; added %d extra(s)",
                 cal, dropped_past, cutoff, excluded, len(extras))
        data = build_calendar(games, alldays + extras, display_names, name=name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        log.info("wrote %s: %d games, %d all-day events", path, len(games), len(alldays))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the sports .ics calendar")
    parser.add_argument("--config", default="config.yaml", type=Path)
    parser.add_argument("--out", type=Path,
                        help="main calendar path; defaults to `output` in config. "
                             "The secondary calendar is written alongside it.")
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
