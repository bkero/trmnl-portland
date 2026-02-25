"""Upload a PNG image to TRMNL via the plugin image API."""
from __future__ import annotations

import os
from pathlib import Path

import requests

TRMNL_API_BASE = "https://usetrmnl.com/api/plugin_settings"


def upload(image_path: Path, plugin_uuid: str | None = None) -> dict:
    """
    Upload image_path to TRMNL.

    plugin_uuid defaults to the TRMNL_PLUGIN_UUID environment variable.
    Returns the parsed JSON response on success, raises on failure.
    """
    uuid = plugin_uuid or os.environ.get("TRMNL_PLUGIN_UUID")
    if not uuid:
        raise ValueError(
            "TRMNL plugin UUID required. Set TRMNL_PLUGIN_UUID env var or pass plugin_uuid."
        )

    url = f"{TRMNL_API_BASE}/{uuid}/image"

    with open(image_path, "rb") as f:
        resp = requests.post(
            url,
            data=f.read(),
            headers={"Content-Type": "image/png"},
            timeout=30,
        )

    resp.raise_for_status()
    return resp.json()
