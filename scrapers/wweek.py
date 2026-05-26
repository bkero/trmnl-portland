"""
Willamette Week calendar scraper.

WWeek's calendar is now powered by CitySpark. The portal JS at
  https://portal.cityspark.com/PortalScripts/WillametteWeek
embeds all of today's events in a `cSparkLocals` JS variable with
an `Events` array. Each event has:
  Name        — title
  Venue       — venue name
  StartUTC    — ISO UTC datetime (e.g. "2026-05-26T15:30:00Z")
  AllDay      — bool
  HasTime     — bool
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from .base import BaseScraper, Event

CITYSPARK_URL = "https://portal.cityspark.com/PortalScripts/WillametteWeek"
PACIFIC = ZoneInfo("America/Los_Angeles")


class WWeekScraper(BaseScraper):
    SOURCE_ID = "wweek"
    SOURCE_LABEL = "Willamette Week"

    async def fetch(self) -> list[Event]:
        return await asyncio.to_thread(self._fetch_sync)

    def _fetch_sync(self) -> list[Event]:
        try:
            resp = requests.get(CITYSPARK_URL, timeout=15)
            resp.raise_for_status()
        except Exception:
            return []

        data = self._extract_json(resp.text)
        if data is None:
            return []

        results = []
        for ev in data.get("Events", []):
            event = self._parse_event(ev)
            if event:
                results.append(event)

        return results

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        """Pull the cSparkLocals {...} object out of the JS file."""
        idx = text.find("cSparkLocals")
        if idx < 0:
            return None
        try:
            start = text.index("{", idx)
        except ValueError:
            return None

        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        return None
        return None

    def _parse_event(self, ev: dict) -> Optional[Event]:
        start_utc = ev.get("StartUTC")
        if not start_utc:
            return None

        dt = datetime.fromisoformat(start_utc.replace("Z", "+00:00")).astimezone(PACIFIC)
        if dt.date() != self.target_date:
            return None

        name = (ev.get("Name") or "").strip()
        if not name:
            return None

        time_str = None
        if ev.get("HasTime") and not ev.get("AllDay"):
            time_str = dt.strftime("%-I:%M %p")

        venue = (ev.get("Venue") or "").strip() or None

        return self._make_event(
            title=name,
            time=time_str,
            location=venue,
        )
