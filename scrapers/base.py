from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Event:
    title: str
    source: str                        # scraper identifier, e.g. "funhouse"
    source_label: str                  # human-readable label, e.g. "FunHouse Lounge"
    time: Optional[str] = None         # display string, e.g. "7:30 PM"
    location: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    # Sort key: 24h time string "HH:MM" or "" (sorts to end)
    sort_key: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.sort_key = self._parse_sort_key(self.time)

    @staticmethod
    def _parse_sort_key(time_str: Optional[str]) -> str:
        """Convert a display time string to 24h 'HH:MM' for sorting."""
        if not time_str:
            return ""
        m = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)?", time_str, re.IGNORECASE)
        if not m:
            return ""
        h, mn, meridiem = int(m.group(1)), int(m.group(2)), (m.group(3) or "").upper()
        if meridiem == "PM" and h != 12:
            h += 12
        elif meridiem == "AM" and h == 12:
            h = 0
        return f"{h:02d}:{mn:02d}"


class BaseScraper(ABC):
    """All event scrapers implement this interface."""

    SOURCE_ID: str = ""       # machine identifier
    SOURCE_LABEL: str = ""    # human-readable name shown on display

    def __init__(self, target_date: Optional[date] = None) -> None:
        if target_date is None:
            # All sources are Portland, OR venues — use Pacific time so that
            # "today" matches the local date even when the server runs in UTC.
            import zoneinfo
            from datetime import datetime as _dt
            target_date = _dt.now(zoneinfo.ZoneInfo("America/Los_Angeles")).date()
        self.target_date = target_date

    @abstractmethod
    async def fetch(self) -> list[Event]:
        """Return today's events. Must be implemented by subclasses."""
        ...

    def _make_event(self, **kwargs) -> Event:
        """Convenience factory that injects source fields."""
        return Event(
            source=self.SOURCE_ID,
            source_label=self.SOURCE_LABEL,
            **kwargs,
        )
