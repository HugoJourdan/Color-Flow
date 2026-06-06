"""Render sample dashboards (step + free) to HTML for in-browser checks.

Usage: uv run python tools/dashboard_sample.py [out_dir]
Writes dashboard_step.html and dashboard_free.html. No Glyphs required.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

RESOURCES = Path(__file__).resolve().parent.parent / "Color Flow.glyphsPalette" / "Contents" / "Resources"
sys.path.insert(0, str(RESOURCES))

import colorflow_assets as assets  # noqa: E402

STEPS = [
    {"key": 8, "label": "Outline corrected"},
    {"key": 4, "label": "Anchors placed"},
    {"key": 6, "label": "Spacing set"},
    {"key": 3, "label": "Ready to Export"},
]
ORDER = ["8", "4", "6", "3"]
SEQ = [8, 8, 4, 4, 4, 6, 6, 3, 3, 3, 3, -1, -1, 8, 4, 6, 3, -1, 8, 4, -1, 6]
NAMES = [chr(c) for c in range(ord("A"), ord("A") + len(SEQ))]


def _counts(keys: list[int], is_free: bool) -> dict[str, int]:
    counts = {o: 0 for o in ORDER}
    for key in keys:
        if key == -1:
            continue
        target = str(key)
        if is_free:
            if target in counts:
                counts[target] += 1
        else:
            for step in ORDER:
                counts[step] += 1
                if step == target:
                    break
    return counts


def _model(is_free: bool) -> dict:
    preview = {"d": "M40 -700L300 -700L300 -100L40 -100ZM360 -640L600 -640L600 -100L360 -100Z",
               "vb": "0 -740 640 680"}
    masters = []
    for offset, name in ((0, "Regular"), (5, "Bold")):
        keys = [SEQ[(i + offset) % len(SEQ)] for i in range(len(SEQ))]
        uncolored = sum(1 for k in keys if k == -1)
        masters.append({"id": name.lower(), "name": name, "keys": keys,
                        "counts": _counts(keys, is_free), "uncolored": uncolored,
                        "preview": preview})
    outline = {"d": "M120 -700L520 -700L520 -100L120 -100Z", "vb": "80 -740 480 680"}
    paths = {master["id"]: {name: outline for name, key in zip(NAMES, master["keys"])
                            if key != -1} for master in masters}
    return {
        "family": "Acme Sans", "fileName": "Acme.glyphs", "version": "2.5",
        "generated": datetime(2026, 6, 5).strftime("%Y-%m-%d"),
        "mode": "free" if is_free else "step", "glyphTotal": len(SEQ),
        "order": ORDER, "steps": STEPS, "noneLabel": "🫥 None",
        "glyphNames": NAMES, "masters": masters,
        "colors": {str(index): "#888888" for index in range(12)},
        "filePath": "/fonts/Acme.glyphs", "paths": paths,
        "favicon": outline,
        "trend": _trend(),
        "journeys": {"regular": {"A": [-1, 4, 8], "C": [-1, -1, 4]}, "bold": {}},
        "changes": {"regular": {"A": [4, 8], "H": [6, 3]}},
    }


def _trend() -> dict:
    dates = ["2026-06-01", "2026-06-03", "2026-06-05"]
    series = []
    for index, date in enumerate(dates):
        masters = {}
        for master in ("regular", "bold"):
            final = 4 + index * 3 if master == "regular" else 2 + index * 2
            masters[master] = {"final": final, "started": final + 2, "total": len(SEQ)}
        series.append({"date": date, "masters": masters})
    forecast = {
        "regular": {"velocityPerWeek": 10.5, "remaining": 6, "final": 10, "total": len(SEQ),
                    "etaIso": "2026-06-09", "bandDays": 2, "confidence": "high", "points": 3},
        "bold": {"velocityPerWeek": 7.0, "remaining": 12, "final": 6, "total": len(SEQ),
                 "etaIso": "2026-06-14", "bandDays": 4, "confidence": "med", "points": 3},
    }
    return {"series": series, "forecast": forecast, "today": "2026-06-05"}


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    for is_free in (False, True):
        path = out_dir / f"dashboard_{'free' if is_free else 'step'}.html"
        path.write_text(assets.build_html(_model(is_free)), encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
