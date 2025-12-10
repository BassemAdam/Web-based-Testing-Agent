# agent/visualization/coverage_overlay.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image, ImageDraw  # pip install pillow

from ..models.page_snapshot import PageSnapshot
from ..utils.keys import key_from_descriptor, canonicalize_key


def create_page_coverage_overlay(
    page_id: str,
    snapshot: PageSnapshot,
    coverage: Dict[str, List[str]],
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    Create a shaded coverage overlay for a SINGLE page.

    - `page_id` is "page_0", "page_1", ...
    - `snapshot` contains the screenshot path and elements for that page.
    - `coverage` has keys like "page_0::a|Learn more" -> [test_ids...]

    Returns the path to the saved overlay image, or None if the screenshot
    file is missing.
    """
    screenshot_path = snapshot.screenshot_path
    if not screenshot_path:
        return None

    img_path = Path(screenshot_path)
    if not img_path.exists():
        # screenshot hasn't been written or path is wrong
        return None

    # Open base screenshot
    img = Image.open(img_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 1) Build a lookup from canonical element key -> bounding box
    key_to_box: Dict[str, tuple] = {}

    for e in snapshot.elements:
        if not e.bounding_box:
            continue

        dom_key = canonicalize_key(key_from_descriptor(e))

        try:
            x = int(e.bounding_box["x"])
            y = int(e.bounding_box["y"])
            w = int(e.bounding_box["width"])
            h = int(e.bounding_box["height"])
        except Exception:
            # malformed bbox, skip
            continue

        key_to_box[dom_key] = (x, y, x + w, y + h)

    # 2) For each coverage entry belonging to THIS page, draw highlight
    for full_key, tc_ids in coverage.items():
        prefix, sep, raw_key = full_key.partition("::")
        if not sep:
            # Old single-page style key (no pageId::); skip or treat as global
            continue

        if prefix != page_id:
            continue

        cov_key = canonicalize_key(raw_key)
        box = key_to_box.get(cov_key)
        if not box:
            continue

        # Green translucent rectangle for covered elements
        draw.rectangle(box, outline=(0, 255, 0, 255), width=2)
        draw.rectangle(box, fill=(0, 255, 0, 70))

    combined = Image.alpha_composite(img, overlay)

    # 3) Decide where to save
    if output_path is None:
        # default: same folder as screenshot, with suffix
        out_path = img_path.with_name(img_path.stem + f"_{page_id}_coverage.png")
    else:
        out_path = Path(output_path)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.save(out_path)

    return str(out_path)
