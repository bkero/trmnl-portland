"""
Portland City Cast newsletter scraper.

The newsletter is an HTML email with a table-based layout.
Structure:
  1. "What To Do" h2 section header
  2. "Wednesday, Feb. 25" h2 (day heading)
  3. <ul> with <li> items: emoji <a href>Title</a> | Venue (Neighborhood)
  4. "Thursday, Feb. 26" h2 (next day — stop here)

Strategy:
  1. Find today's newsletter URL from the archive page
     (URL pattern: /newsletter/YYYY-MM-DD?id=portland.<uuid>)
  2. Fetch newsletter and extract events only for today's date heading
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag

from .base import BaseScraper, Event

ARCHIVE_URL = "https://portland.citycast.fm/newsletter"
NEWSLETTER_BASE = "https://portland.citycast.fm"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}


class CityCastScraper(BaseScraper):
    SOURCE_ID = "citycast"
    SOURCE_LABEL = "City Cast PDX"

    async def fetch(self) -> list[Event]:
        import asyncio

        newsletter_url = await asyncio.to_thread(self._find_todays_newsletter)
        if not newsletter_url:
            return []
        return await asyncio.to_thread(self._parse_newsletter, newsletter_url)

    # ------------------------------------------------------------------
    # Step 1: find today's newsletter URL from the archive page
    # ------------------------------------------------------------------
    def _find_todays_newsletter(self) -> Optional[str]:
        date_str = self.target_date.strftime("%Y-%m-%d")
        try:
            resp = requests.get(ARCHIVE_URL, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception:
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        import re as _re
        newsletter_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "newsletter" in href and _re.search(r"\d{4}-\d{2}-\d{2}", href):
                newsletter_links.append(href)

        # Prefer today's newsletter; fall back to the most recent one.
        # City Cast publishes Mon–Fri; the Friday issue covers the coming weekend,
        # so the most recent newsletter will contain events for Saturday/Sunday.
        for href in newsletter_links:
            if date_str in href:
                return href if href.startswith("http") else f"{NEWSLETTER_BASE}{href}"

        if newsletter_links:
            href = newsletter_links[0]
            return href if href.startswith("http") else f"{NEWSLETTER_BASE}{href}"

        return None

    # ------------------------------------------------------------------
    # Step 2: fetch newsletter and extract today's events
    # ------------------------------------------------------------------
    def _parse_newsletter(self, url: str) -> list[Event]:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        return self._extract_todays_events(soup)

    def _extract_todays_events(self, soup: BeautifulSoup) -> list[Event]:
        """
        Find the h2 matching today's date (e.g. "Wednesday, Feb. 25"),
        then collect all <li> items until the next day's h2.
        """
        today_label = self._date_label(self.target_date)

        # Find all h3s to locate today's section and the next day boundary
        # (City Cast switched from h2 to h3 for day headings)
        all_h3s = soup.find_all("h3")
        today_h2 = None
        next_day_h2 = None

        for i, h3 in enumerate(all_h3s):
            text = h3.get_text(strip=True)
            if today_label in text:
                today_h2 = h3
                # Next day heading is the next h3 that looks like a date
                for j in range(i + 1, len(all_h3s)):
                    if re.search(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*,", all_h3s[j].get_text()):
                        next_day_h2 = all_h3s[j]
                        break
                break

        if today_h2 is None:
            return []

        # The events <ul> is NOT a direct sibling (it's in a different table cell).
        # Strategy: walk all <li> elements in document order, keeping only those
        # that appear AFTER today_h2 and BEFORE next_day_h2.
        all_lis = soup.find_all("li")
        today_h2_pos = self._element_position(soup, today_h2)
        next_pos = self._element_position(soup, next_day_h2) if next_day_h2 else float("inf")

        results = []
        for li in all_lis:
            pos = self._element_position(soup, li)
            if pos <= today_h2_pos:
                continue
            if pos >= next_pos:
                break
            ev = self._parse_li(li)
            if ev:
                results.append(ev)

        return results

    def _parse_li(self, li: Tag) -> Optional[Event]:
        """Parse a single <li> event item."""
        link = li.find("a", href=True)
        if not link:
            return None

        title = link.get_text(strip=True)
        if not title:
            return None

        # Text after the link is "| Venue (Neighborhood)"
        full_text = li.get_text(separator=" ", strip=True)
        location = None
        pipe_match = re.search(r"\|\s*(.+)", full_text)
        if pipe_match:
            location = pipe_match.group(1).strip()

        href = link.get("href", "")

        return self._make_event(
            title=title,
            location=location or None,
            url=href if href.startswith("http") else None,
        )

    @staticmethod
    def _date_label(d: date) -> str:
        """Return a label like 'Wednesday, Feb. 25' matching the newsletter format.

        City Cast follows AP style: months with 5 or fewer letters (March, April,
        May, June, July) are spelled out in full; others are abbreviated with a
        trailing period (Jan., Feb., Aug., Sept., Oct., Nov., Dec.).
        """
        AP_ABBREVS = {
            1: "Jan.", 2: "Feb.", 3: "March", 4: "April", 5: "May",
            6: "June", 7: "July", 8: "Aug.", 9: "Sept.",
            10: "Oct.", 11: "Nov.", 12: "Dec.",
        }
        month_str = AP_ABBREVS[d.month]
        return f"{d.strftime('%A')}, {month_str} {d.day}"

    @staticmethod
    def _element_position(soup: BeautifulSoup, el) -> int:
        """Return the index of el among all tags in the document."""
        if el is None:
            return -1
        all_tags = list(soup.descendants)
        try:
            return all_tags.index(el)
        except ValueError:
            return -1
