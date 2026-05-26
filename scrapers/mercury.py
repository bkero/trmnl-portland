"""
Portland Mercury "Do This, Do That" scraper.

Weekly event guide published every Monday covering Mon–Sun.
Index: https://www.portlandmercury.com/collections/47901508/do-this-do-that

Article structure (all unclassed <h2>):
  <h2>Wednesday, February 25</h2>   ← day heading (matches weekday + date)
  <h2>The Sun Ra Arkestra</h2>       ← event title (any other unclassed h2)
  <p>Prose description…</p>          ← prose; may contain venue mentions

Strategy:
  1. Fetch index page, grab the first article link (/do-this-do-that/…).
  2. Fetch article; find the unclassed <h2> matching today's date.
  3. Collect all unclassed <h2> event titles until the next day heading.
  4. Best-effort extract location from the first <p> description.
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag

from .base import BaseScraper, Event

INDEX_URL = "https://www.portlandmercury.com/category/do-this-do-that/"
BASE_URL = "https://www.portlandmercury.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}

# Matches "Monday, February 23", "Sunday, March 1", etc.
DAY_HEADING_RE = re.compile(
    r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+\w+\s+\d+$",
    re.IGNORECASE,
)

# Looks for "at Venue Name", "at the Venue", or "Venue, Address"
VENUE_RE = re.compile(
    r"\bat\s+(?:the\s+)?([A-Z][^\.,\n]{3,40}?)(?:\s+in\s+|\s+on\s+|\.|,|$)"
)


class MercuryScraper(BaseScraper):
    SOURCE_ID = "mercury"
    SOURCE_LABEL = "Portland Mercury"

    async def fetch(self) -> list[Event]:
        article_url = await asyncio.to_thread(self._find_current_article)
        if not article_url:
            return []
        return await asyncio.to_thread(self._parse_article, article_url)

    # ------------------------------------------------------------------
    # Step 1: find the current week's article URL from the index
    # ------------------------------------------------------------------
    def _find_current_article(self) -> Optional[str]:
        try:
            resp = requests.get(INDEX_URL, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception:
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        pattern = re.compile(r"/do-this-do-that/[a-z0-9][a-z0-9-]+/")
        seen = set()
        for a in soup.find_all("a", href=pattern):
            href = a["href"]
            if href in seen:
                continue
            seen.add(href)
            return f"{BASE_URL}{href}" if not href.startswith("http") else href

        return None

    # ------------------------------------------------------------------
    # Step 2: fetch article and extract today's events
    # ------------------------------------------------------------------
    def _parse_article(self, url: str) -> list[Event]:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        today_label = self.target_date.strftime("%A, %B %-d")

        # Find the <h2> that matches today's date label (case-insensitive)
        target_h2 = None
        today_label_upper = today_label.upper()
        for h2 in soup.find_all("h2"):
            if today_label_upper in h2.get_text(strip=True).upper():
                target_h2 = h2
                break

        if target_h2 is None:
            return []

        return self._extract_events(target_h2, url)

    def _extract_events(self, day_h2: Tag, article_url: str) -> list[Event]:
        """Collect event <h2>s between day_h2 and the next day heading."""
        results = []
        current = day_h2.find_next_sibling()

        while current:
            if current.name == "h2":
                title = current.get_text(strip=True)
                if not title:
                    current = current.find_next_sibling()
                    continue

                # Stop at next day heading
                if DAY_HEADING_RE.match(title):
                    break

                # Gather description from subsequent <p> and <div class="description">
                description_text = self._get_description(current)
                location = self._extract_location(title, description_text)

                results.append(
                    self._make_event(
                        title=title,
                        location=location,
                        url=article_url,
                    )
                )

            current = current.find_next_sibling()

        return results

    @staticmethod
    def _get_description(event_h2: Tag) -> Optional[str]:
        """Return the first meaningful text block after the event h2."""
        sib = event_h2.find_next_sibling()
        while sib:
            if sib.name == "h2":
                break
            if sib.name == "p":
                text = sib.get_text(separator=" ", strip=True)
                if len(text) > 20:
                    return text
            if sib.name == "div" and "description" in (sib.get("class") or []):
                text = sib.get_text(separator=" ", strip=True)
                if len(text) > 20:
                    return text
            sib = sib.find_next_sibling()
        return None

    @staticmethod
    def _extract_location(title: str, description: Optional[str]) -> Optional[str]:
        """
        Best-effort venue extraction. Strategies run in order:

        1. Leading proper-noun phrase before a verb in description —
           "Portland Center Stage has flung open its doors" → "Portland Center Stage"

        2. "at Venue" in description — "kicks off at OMSI" → "OMSI"

        3. Title colon pattern (last resort) —
           "History Pub: Big Medicine..." → "History Pub"
        """
        noise_starters = re.compile(
            r"^(If |When |As |While |In |After |Though |Although |Since |So |And |But |For )",
            re.I,
        )

        if description:
            # Strategy 0: parenthetical venue block at end of description —
            # "(Moda Center, 1 N Center Ct, 7 pm, more info, all ages)"
            # The first element before the first comma is the venue name.
            paren_match = re.search(
                r"\(([^,)]{3,50}),\s*[^,)]*,\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)",
                description,
                re.IGNORECASE,
            )
            if paren_match:
                venue = paren_match.group(1).strip()
                if len(venue) >= 3:
                    return venue

            # Strategy 1: proper-noun phrase + venue-specific verb at sentence start —
            # "In case…, Portland Center Stage has flung…" → "Portland Center Stage"
            # Only fires on verbs that uniquely signal a venue (not person-name verbs
            # like "is bringing"). Looks at sentence/clause boundaries.
            lead_match = re.search(
                r"(?:^|[.!?]\s+|,\s+)([A-Z][A-Za-z\s]{4,40}?)\s+(?:has |have |opens?|presents?|hosts?)",
                description[:300],
            )
            if lead_match:
                venue = lead_match.group(1).strip()
                if len(venue) >= 4 and not noise_starters.match(venue) and "'" not in venue:
                    return venue

            # Strategy 2: "at Venue" pattern — search first 500 chars but filter
            # out possessives ("at Montreal's…") and noise phrases.
            at_match = re.search(
                r"\bat\s+(?:the\s+)?([A-Z][^\.,\n']{2,40}?)(?:\s*(?:on|in|this|,|\.)|$)",
                description[:500],
            )
            if at_match:
                venue = at_match.group(1).strip().rstrip(".,")
                venue = re.sub(
                    r"\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)$",
                    "", venue,
                )
                noise = re.compile(r"^(one |their |this |that |least |most |first |last )", re.I)
                if len(venue) >= 3 and not noise.match(venue):
                    return venue

        # Strategy 3: colon in title (series/venue prefix)
        if ":" in title:
            candidate = title.split(":")[0].strip()
            if 3 <= len(candidate) < 40 and not re.search(r"\b(the|a|an|is|are|was)\b", candidate, re.I):
                return candidate

        return None
