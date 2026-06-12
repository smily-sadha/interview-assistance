"""
capture.py
==========
Takes a screenshot and returns it as JPEG image bytes, ready for the LLM.

For low latency we:
- capture ONE monitor (the primary) instead of the whole multi-monitor desktop,
- downscale so the longest side is at most `screenshot_max_px`,
- encode as JPEG (much smaller than PNG → faster upload + faster model).

`mss` grabs the pixels; `Pillow` resizes and encodes.
"""

import io

import mss
from PIL import Image

from ..config import settings

# Mime type of what grab_screenshot() returns (used by llm.py).
SCREENSHOT_MIME = "image/jpeg"


def grab_screenshot(monitor_index: int = None) -> bytes:
    """Capture the screen and return JPEG bytes (downscaled for speed)."""
    idx = settings.screenshot_monitor if monitor_index is None else monitor_index

    with mss.mss() as sct:
        monitors = sct.monitors          # [0] = all, [1] = primary, [2]=second…
        if idx >= len(monitors):
            idx = 0
        raw = sct.grab(monitors[idx])
        image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    # Shrink large screens so we send far fewer pixels (thumbnail only shrinks,
    # never enlarges, and keeps the aspect ratio).
    max_px = settings.screenshot_max_px
    image.thumbnail((max_px, max_px))

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=settings.screenshot_jpeg_quality)
    return buffer.getvalue()
