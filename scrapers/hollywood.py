"""
Hollywood Theatre scraper.

The homepage at hollywoodtheatre.org embeds a 'gecko-show-list' component
whose data-props attribute contains structured JSON with today's showtimes.
We parse that JSON directly — no need to click any tabs or wait for JS.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from bs4 import BeautifulSoup

from .base import BaseScraper, Event

BASE_URL = "https://hollywoodtheatre.org/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}


class HollywoodScraper(BaseScraper):
    SOURCE_ID = "hollywood"
    SOURCE_LABEL = "Hollywood Theatre"

    async def fetch(self) -> list[Event]:
        from playwright.async_api import async_playwright

        html = None
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="en-US",
                timezone_id="America/Los_Angeles",
                extra_http_headers={
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;"
                        "q=0.9,image/avif,image/webp,*/*;q=0.8"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            page = await context.new_page()
            try:
                resp = await page.goto(BASE_URL, wait_until="load", timeout=30000)
                if resp and resp.status < 400:
                    html = await page.content()
            finally:
                await browser.close()

        if not html:
            return []

        return self._parse(html)

    def _parse(self, html: str) -> list[Event]:
        soup = BeautifulSoup(html, "lxml")
        date_str = self.target_date.strftime("%Y-%m-%d")

        # The showtime data lives in data-props on the .gecko-show-list section
        section = soup.select_one("section.gecko-show-list[data-props]")
        if not section:
            return []

        try:
            props = json.loads(section["data-props"])
        except (json.JSONDecodeError, KeyError):
            return []

        results = []
        for show in props.get("shows", []):
            if show.get("query_date") != date_str:
                continue

            title = show.get("title", "Untitled")
            permalink = show.get("permalink")
            series = show.get("series", "")
            fmt = show.get("format", "")

            # Each show may have multiple screenings (events)
            show_events = show.get("events", [])
            if not show_events:
                results.append(
                    self._make_event(
                        title=title,
                        url=permalink,
                        description=series or fmt or None,
                    )
                )
            else:
                for ev in show_events:
                    time_str = ev.get("start_time")
                    if time_str:
                        time_str = time_str.upper().replace("AM", " AM").replace("PM", " PM").strip()
                    results.append(
                        self._make_event(
                            title=title,
                            time=time_str,
                            description=series or fmt or None,
                            url=permalink,
                        )
                    )

        return results
