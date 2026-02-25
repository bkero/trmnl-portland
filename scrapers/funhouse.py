"""
FunHouse Lounge scraper.

Uses the public Google Calendar iCal feed embedded on their /calendar/ page.
Calendar ID discovered from the iframe src on the page.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Optional

import requests

from .base import BaseScraper, Event

ICAL_URL = (
    "https://calendar.google.com/calendar/ical/"
    "1d9rstj8str8khfubp6ckohvik%40group.calendar.google.com"
    "/public/basic.ics"
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}
TIMEZONE = "America/Los_Angeles"


class FunhouseScraper(BaseScraper):
    SOURCE_ID = "funhouse"
    SOURCE_LABEL = "FunHouse Lounge"

    async def fetch(self) -> list[Event]:
        import asyncio

        try:
            resp = await asyncio.to_thread(
                requests.get, ICAL_URL, headers=HEADERS, timeout=15
            )
            resp.raise_for_status()
        except Exception as exc:
            print(f"[WARN] FunHouse iCal fetch failed: {exc}")
            return []

        return self._parse_ical(resp.text)

    def _parse_ical(self, ical_text: str) -> list[Event]:
        """Parse VEVENT blocks from raw iCal text, returning today's events."""
        events = []
        for block in re.split(r"BEGIN:VEVENT", ical_text)[1:]:
            block = "BEGIN:VEVENT" + block.split("END:VEVENT")[0] + "END:VEVENT"
            ev = self._parse_vevent(block)
            if ev:
                events.append(ev)
        return events

    def _parse_vevent(self, block: str) -> Optional[Event]:
        """Parse a single VEVENT block and return an Event if it's today."""
        def field(name: str) -> str:
            m = re.search(rf"^{name}[^:]*:(.*)", block, re.MULTILINE)
            return m.group(1).strip() if m else ""

        summary = field("SUMMARY")
        if not summary:
            return None

        dtstart_raw = field("DTSTART")
        if not dtstart_raw:
            return None

        try:
            event_date, time_str = self._parse_dtstart(dtstart_raw, block)
        except ValueError:
            return None

        if event_date != self.target_date:
            return None

        url_val = field("URL")
        description = field("DESCRIPTION")[:120] or None

        return self._make_event(
            title=summary,
            time=time_str,
            description=description or None,
            url=url_val or None,
        )

    def _parse_dtstart(self, dtstart_raw: str, block: str) -> tuple[date, Optional[str]]:
        """
        Parse DTSTART into (date, time_string).
        Handles:
          - DATE-only: DTSTART;VALUE=DATE:20260225
          - UTC: DTSTART:20260225T020000Z
          - Local with TZID: DTSTART;TZID=America/Los_Angeles:20260225T190000
        """
        # Check for TZID in the property name line
        tzid_match = re.search(r"DTSTART;TZID=([^:]+):(.*)", block, re.MULTILINE)
        if tzid_match:
            tz_name, dt_str = tzid_match.group(1).strip(), tzid_match.group(2).strip()
            dt = datetime.strptime(dt_str, "%Y%m%dT%H%M%S")
            return dt.date(), self._fmt_time(dt.hour, dt.minute)

        if dtstart_raw.endswith("Z"):
            # UTC — convert to Pacific
            dt_utc = datetime.strptime(dtstart_raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            import zoneinfo
            dt_local = dt_utc.astimezone(zoneinfo.ZoneInfo(TIMEZONE))
            return dt_local.date(), self._fmt_time(dt_local.hour, dt_local.minute)

        if "T" in dtstart_raw:
            dt = datetime.strptime(dtstart_raw, "%Y%m%dT%H%M%S")
            return dt.date(), self._fmt_time(dt.hour, dt.minute)

        # Date-only
        d = datetime.strptime(dtstart_raw[:8], "%Y%m%d").date()
        return d, None

    @staticmethod
    def _fmt_time(hour: int, minute: int) -> str:
        period = "AM" if hour < 12 else "PM"
        h12 = hour % 12 or 12
        return f"{h12}:{minute:02d} {period}"
