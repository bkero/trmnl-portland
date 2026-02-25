"""Upload a PNG image to TRMNL via the Webhook Image plugin API."""
from __future__ import annotations

import os
from pathlib import Path

import requests


def upload(image_path: Path, webhook_url: str | None = None) -> dict:
    """
    Upload image_path to TRMNL.

    webhook_url is the full URL from the Webhook Image plugin settings page.
    Defaults to the TRMNL_WEBHOOK_URL environment variable.
    Returns the parsed JSON response on success, raises on failure.
    """
    url = webhook_url or os.environ.get("TRMNL_WEBHOOK_URL")
    if not url:
        raise ValueError(
            "TRMNL webhook URL required. Set TRMNL_WEBHOOK_URL env var or pass webhook_url."
        )

    with open(image_path, "rb") as f:
        resp = requests.post(
            url,
            data=f.read(),
            headers={"Content-Type": "image/png"},
            timeout=30,
        )

    resp.raise_for_status()
    return resp.json()
