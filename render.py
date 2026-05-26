"""
Render the Jinja2 dashboard template to an 800x480 1-bit PNG for TRMNL.

Steps:
  1. Render template → HTML string
  2. Screenshot with Playwright at 800x480
  3. Convert to 1-bit monochrome with ImageMagick
"""
from __future__ import annotations

import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


async def render_to_png(context: dict[str, Any], output_path: Path | None = None) -> Path:
    """Render dashboard to a 1-bit PNG. Returns the path to the output file."""
    output_path = output_path or OUTPUT_DIR / "display.png"
    raw_path = OUTPUT_DIR / "raw.png"

    html = _render_html(context)

    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp_html = Path(f.name)

    try:
        await _screenshot(tmp_html, raw_path)
        _convert_to_2bit(raw_path, output_path)
    finally:
        tmp_html.unlink(missing_ok=True)

    return output_path


def _render_html(context: dict[str, Any]) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    tpl = env.get_template("dashboard.html")
    return tpl.render(**context)


async def _screenshot(html_path: Path, out_png: Path) -> None:
    """
    Screenshot at 1× (800×480) — pixel fonts must render at their native size;
    supersampling destroys bitmap glyphs.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": 800, "height": 480},
            device_scale_factor=1,
        )
        await page.goto(f"file://{html_path.resolve()}", wait_until="load")
        # If a column overflows its height, hide the time/location meta lines so
        # more event titles fit within the fixed 480px display.
        await page.evaluate("""
            document.querySelectorAll('.source-col').forEach(col => {
                if (col.scrollHeight > col.clientHeight) {
                    col.querySelectorAll('.event-meta').forEach(m => m.style.display = 'none');
                }
            });
        """)
        await page.screenshot(path=str(out_png), clip={"x": 0, "y": 0, "width": 800, "height": 480})
        await browser.close()


def _imagemagick_cmd() -> str:
    """Return 'magick' (IM7+) if available, else fall back to 'convert' (IM6)."""
    try:
        result = subprocess.run(["magick", "--version"], capture_output=True)
        if result.returncode == 0:
            return "magick"
    except FileNotFoundError:
        pass
    return "convert"


def _convert_to_2bit(src: Path, dst: Path) -> None:
    """Convert to 2-bit (4-gray) PNG matching the TRMNL display's color depth."""
    cmd = _imagemagick_cmd()
    result = subprocess.run(
        [
            cmd,
            str(src),
            "-colorspace", "Gray",
            "-posterize", "4",
            "-depth", "2",
            "-strip",
            f"png:{dst}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ImageMagick failed: {result.stderr}")


def build_template_context(grouped_events: list[dict], target_date) -> dict[str, Any]:
    """Build the Jinja2 context dict from grouped event data."""
    return {
        "date_label": target_date.strftime("%A, %B %-d"),
        "updated_at": datetime.now().strftime("%-I:%M %p"),
        "columns": grouped_events,
        "static_dir": STATIC_DIR.resolve().as_uri(),
    }
