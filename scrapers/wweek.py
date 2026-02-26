"""
Willamette Week calendar scraper.

API: https://www.wweek.com/calendar/willamette/search.json
     ?page=1&ongoing=true&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD

Each event has:
  _source.name        — event title
  _source.starttime   — ISO datetime with tz offset (e.g. "2026-02-25T17:00:00.000-08:00")
  _source.venue.name  — venue name
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from .base import BaseScraper, Event

API_URL = "https://www.wweek.com/calendar/willamette/search.json"
PACIFIC = ZoneInfo("America/Los_Angeles")


class WWeekScraper(BaseScraper):
    SOURCE_ID = "wweek"
    SOURCE_LABEL = "Willamette Week"

    async def fetch(self) -> list[Event]:
        return await asyncio.to_thread(self._fetch_sync)

    def _fetch_sync(self) -> list[Event]:
        date_str = self.target_date.strftime("%Y-%m-%d")
        try:
            resp = requests.get(
                API_URL,
                params={"page": 1, "ongoing": "true", "start_date": date_str, "end_date": date_str},
                timeout=15,
            )
            resp.raise_for_status()
        except Exception:
            return []

        results = []
        for ev_wrapper in resp.json().get("events", []):
            ev = ev_wrapper.get("_source", {})
            event = self._parse_event(ev)
            if event:
                results.append(event)

        return results

    def _parse_event(self, ev: dict) -> Optional[Event]:
        starttime = ev.get("starttime")
        if not starttime:
            return None

        dt = datetime.fromisoformat(starttime).astimezone(PACIFIC)
        if dt.date() != self.target_date:
            return None

        name = (ev.get("name") or "").strip()
        if not name:
            return None

        time_str = None if ev.get("allday") else dt.strftime("%-I:%M %p")

        venue = ev.get("venue") or {}
        location = (venue.get("name") or "").strip() or None

        return self._make_event(
            title=name,
            time=time_str,
            location=location,
        )
