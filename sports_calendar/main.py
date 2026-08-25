"""CLI: load config → fetch → apply rules → write .ics"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from sports_calendar import http
from sports_calendar.catalog import Catalog
from sports_calendar.curation import apply_excludes, build_extras, drop_past
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
    display_names = config.get("display_names") or {}
    tz = ZoneInfo(config.get("timezone") or "America/Denver")
    total = len(games) + len(alldays)
    cutoff = today - timedelta(days=int(config.get("keep_past_days", 7)))
    games, alldays = drop_past(games, alldays, cutoff, tz)
    dropped_past = total - len(games) - len(alldays)
    games, alldays = apply_excludes(games, alldays, config.get("exclude") or [], display_names, tz)
    extras = build_extras(config.get("extra") or [], tz)
    excluded = total - dropped_past - len(games) - len(alldays)
    log.info("dropped %d past (before %s); excluded %d; added %d extra(s)", dropped_past, cutoff, excluded, len(extras))
    data = build_calendar(games, alldays + extras, display_names)
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
