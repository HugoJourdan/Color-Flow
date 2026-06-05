# encoding: utf-8
"""Inline assets + HTML shell for the Color Font Dashboard.

Turns the data model (see colorflow_dashboard.build_model) into one
self-contained, offline .html with inline CSS + inline vanilla JS. No network,
no dependencies. The model is the single source of truth the JS app renders.
"""

from __future__ import annotations

import json


def embed_model(model: dict) -> str:
    """Serialise the model into a ``<script type="application/json">`` block.
    ``<`` / ``>`` / ``&`` are escaped to their JSON ``\\uXXXX`` forms so no glyph
    name or label can terminate the script element (e.g. ``</script>``)."""
    payload = (json.dumps(model, ensure_ascii=False)
               .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))
    return f'<script type="application/json" id="cfd-model">{payload}</script>'
