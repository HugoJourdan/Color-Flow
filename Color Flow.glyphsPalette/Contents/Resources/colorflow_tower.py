"""Color Tower — build the in-Glyphs WKWebView page for the disc-stack visualizer.

The visual (an isometric stack of discs, one per master, each disc a blurred
blend of that master's label-colour distribution) lives in the self-contained
``tower.html`` template next to this module. This module only:

* turns a font into the small data model the page needs — per-master 12-slot
  colour counts plus an uncolored tally — and
* injects that model into the template as ``window.TOWER_MODEL`` so the page
  renders the real font instead of its built-in sample.

Kept free of any GlyphsApp import at module load so it stays unit-testable; the
font-reading helpers import the dashboard lazily.
"""

from __future__ import annotations

import json
from pathlib import Path

LABEL_SLOTS = 12

TEMPLATE_PATH = Path(__file__).with_name("tower.html")


def master_color_array(colors: list[int | None]) -> tuple[list[int], int]:
    """Tally a master's per-glyph colours into 12 label slots + an uncolored count.

    ``colors`` is the list the dashboard's ``snapshot_to_colors`` produces: a
    native label index (0..11) per glyph, or ``None`` for an uncoloured glyph.
    Indices outside 0..11 are ignored (defensive; Glyphs only has 12 labels)."""
    counts = [0] * LABEL_SLOTS
    uncolored = 0
    for color in colors:
        if color is None:
            uncolored += 1
        elif 0 <= color < LABEL_SLOTS:
            counts[color] += 1
    return counts, uncolored


def tower_model(font) -> dict:
    """Build the Tower data model from a GSFont: one entry per master with its
    12-slot colour counts and uncolored tally. Reuses the dashboard's colour
    snapshot so the numbers stay in lockstep with the report and the palette."""
    import colorflow_dashboard

    current = colorflow_dashboard.build_master_glyph_colors(font)
    masters: list[dict] = []
    for master in font.masters:
        per_glyph = current.get(master.id, {})
        colors = colorflow_dashboard.snapshot_to_colors(per_glyph)
        counts, uncolored = master_color_array(colors)
        masters.append({"name": master.name, "counts": counts, "uncolored": uncolored})
    return {"total": len(font.glyphs), "masters": masters}


def build_html(model: dict, template: str | None = None) -> str:
    """Inject ``model`` into the Tower template as ``window.TOWER_MODEL`` so the
    page renders the real font. ``template`` defaults to the bundled tower.html.

    The payload is JSON with ``</`` neutralised so a master name can never break
    out of the injected ``<script>`` tag."""
    if template is None:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
    payload = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
    injection = f"<script>window.TOWER_MODEL = {payload};</script>\n"
    marker = "</head>"
    if marker in template:
        return template.replace(marker, injection + marker, 1)
    return injection + template


def build_html_for_font(font) -> str:
    """Convenience: build the model from the font and inject it into the template."""
    return build_html(tower_model(font))
