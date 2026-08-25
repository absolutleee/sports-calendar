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
