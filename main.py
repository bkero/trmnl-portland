#!/usr/bin/env python3
"""
Portland events dashboard for TRMNL e-ink display.

Usage:
  python main.py                  # scrape, render, upload
  python main.py --render-only    # skip upload (for testing)
  python main.py --date 2026-03-01
"""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

from render import build_template_context, render_to_png
from scrapers import CityCastScraper, FunhouseScraper, HollywoodScraper
from scrapers.base import BaseScraper, Event

load_dotenv()

# ── Registry ─────────────────────────────────────────────────────────────────
# Add new scrapers here. Order controls column order on the display.
SCRAPER_CLASSES: list[type[BaseScraper]] = [
    FunhouseScraper,
    HollywoodScraper,
    CityCastScraper,
]

# Maximum events to show per source (display space is limited)
MAX_EVENTS_PER_SOURCE = 8


async def run(target_date: date, render_only: bool = False) -> Path:
    # Run all scrapers concurrently
    scrapers = [cls(target_date=target_date) for cls in SCRAPER_CLASSES]
    results: list[list[Event]] = await asyncio.gather(
        *[s.fetch() for s in scrapers], return_exceptions=True
    )

    grouped = []
    for scraper, events in zip(scrapers, results):
        if isinstance(events, Exception):
            print(f"[WARN] {scraper.SOURCE_LABEL} scraper failed: {events}")
            events = []

        # Sort by time, capping display count
        sorted_events = sorted(events, key=lambda e: (e.sort_key == "", e.sort_key))
        capped = sorted_events[:MAX_EVENTS_PER_SOURCE]

        grouped.append(
            {
                "label": scraper.SOURCE_LABEL,
                "source": scraper.SOURCE_ID,
                "events": [
                    {
                        "title": ev.title,
                        "time": ev.time,
                        "location": ev.location,
                        "description": ev.description,
                        "url": ev.url,
                    }
                    for ev in capped
                ],
            }
        )
        print(f"[INFO] {scraper.SOURCE_LABEL}: {len(capped)} event(s)")

    context = build_template_context(grouped, target_date)
    output_path = await render_to_png(context)
    print(f"[INFO] Rendered → {output_path}")

    if not render_only:
        from upload import upload

        response = upload(output_path)
        print(f"[INFO] Uploaded: {response}")

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Portland TRMNL events dashboard")
    parser.add_argument(
        "--date",
        help="Target date (YYYY-MM-DD). Defaults to today.",
        default=os.environ.get("OVERRIDE_DATE"),
    )
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="Render image but do not upload to TRMNL.",
    )
    args = parser.parse_args()

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = date.today()

    asyncio.run(run(target_date, render_only=args.render_only))


if __name__ == "__main__":
    main()
