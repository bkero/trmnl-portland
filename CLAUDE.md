# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Python script that scrapes Portland event sources daily, renders an 800×480 monochrome dashboard, and uploads it to a TRMNL e-ink device.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # then fill in TRMNL_PLUGIN_UUID
```

ImageMagick (`magick` CLI) must be installed separately.

## Running

```bash
# Scrape, render, upload
python main.py

# Render only (no upload) — good for testing
python main.py --render-only

# Test against a specific date
python main.py --date 2026-03-01 --render-only
```

Output image lands at `output/display.png`.

## Architecture

```
main.py          Orchestrator — runs all scrapers concurrently, calls render + upload
scrapers/
  base.py        Event dataclass + BaseScraper ABC (implement fetch() → list[Event])
  funhouse.py    FunHouse Lounge: tries Tribe Events REST API → FooEvents API → Playwright
  hollywood.py   Hollywood Theatre: Playwright (site blocks plain HTTP)
  citycast.py    City Cast PDX newsletter: find today's link from archive, extract events
render.py        Jinja2 → HTML → Playwright screenshot → ImageMagick 1-bit PNG
upload.py        POST image to TRMNL plugin API
templates/
  dashboard.html Jinja2 template, 800×480, one column per source
```

## Adding a New Scraper

1. Create `scrapers/yourname.py` subclassing `BaseScraper`; set `SOURCE_ID` and `SOURCE_LABEL`; implement `async def fetch(self) -> list[Event]`
2. Import and add the class to `SCRAPER_CLASSES` in `main.py`
3. Import it in `scrapers/__init__.py`

The display automatically adds a new column per source — keep the total number of sources to 3–4 to avoid crowding the 800px-wide layout.

## Key Design Details

- All scrapers receive `self.target_date` (a `datetime.date`); use it rather than `date.today()` so `--date` overrides work
- `Event.sort_key` is auto-computed from `time` for chronological sorting; no manual sorting needed
- Scrapers should return `[]` (not raise) on network failure — the display will show "No events found"
- Playwright is used for sites that block plain HTTP (Hollywood Theatre). FunHouse tries REST APIs first and falls back to Playwright
- City Cast: newsletter URL pattern is `https://portland.citycast.fm/newsletter/YYYY-MM-DD?id=portland.<uuid>` — the UUID changes per issue, so we scrape the archive page to find it

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `TRMNL_PLUGIN_UUID` | Yes (for upload) | Found in TRMNL dashboard URL |
| `OVERRIDE_DATE` | No | Force a specific date (YYYY-MM-DD) |
