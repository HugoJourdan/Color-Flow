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
DATES = ["2026-06-01", "2026-06-03", "2026-06-05"]
# Glyphs that went backwards between the middle and latest snapshot, so the
# regression log + scrub diff-rings have something to show in the sample.
REGRESS_NAMES = {"C", "P"}


def _script_for(index: int) -> str:
    """A spread of writing systems so the per-script lanes show several groups
    (digits get an empty script -> the front-end buckets them as 'Other')."""
    if index < 10:
        return "latin"
    if index < 14:
        return "cyrillic"
    if index < 18:
        return ""
    return "greek"


def _step_sequence(name: str, final_key: int) -> list[int]:
    """A 3-point colour journey (aligned to ``DATES``) ending at ``final_key``.

    Normal glyphs walk forward through ``ORDER`` (uncoloured -> ... -> final).
    A ``REGRESS_NAMES`` glyph is shown as 'done' at the middle snapshot then
    dropped back to its current step, giving a real backward move."""
    final_str = str(final_key)
    rank = ORDER.index(final_str) if final_str in ORDER else len(ORDER) - 1
    done = int(ORDER[-1])
    if name in REGRESS_NAMES and final_key != done:
        start = int(ORDER[max(0, rank - 1)])
        return [start, done, final_key]
    return [int(ORDER[step]) if step >= 0 else -1 for step in (rank - 2, rank - 1, rank)]


def _journey_index(masters: list[dict]) -> dict:
    """Sparse per-master change-event index the Timeline features read via
    ``stateAt``: ``{masterId: {glyph: [[isoDate, key], ...]}}`` (events only)."""
    index: dict[str, dict[str, list[list]]] = {}
    for master in masters:
        per_glyph: dict[str, list[list]] = {}
        for name, final_key in zip(NAMES, master["keys"]):
            if final_key == -1:
                continue
            events: list[list] = []
            previous = None
            for date, key in zip(DATES, _step_sequence(name, final_key)):
                if key != previous:
                    events.append([date, key])
                    previous = key
            if events:
                per_glyph[name] = events
        index[master["id"]] = per_glyph
    return index


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
        "glyphNames": NAMES,
        "categories": [("Letter" if i < 14 else "Number" if i < 18 else "Punctuation")
                       for i in range(len(SEQ))],
        "scripts": [_script_for(i) for i in range(len(SEQ))],
        "masters": masters,
        "colors": {str(index): "#888888" for index in range(12)},
        "filePath": "/fonts/Acme.glyphs", "paths": paths,
        "favicon": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        "logo": {"d": "M0 0L100 0L100 -700L0 -700ZM200 0L360 0L360 -500L200 -500Z", "vb": "0 -740 360 780"},
        "trend": _trend(),
        "journeyIndex": _journey_index(masters),
        "journeys": {"regular": {"A": [-1, 4, 8], "C": [-1, -1, 4]}, "bold": {}},
        "lastEdit": {"A": 2, "C": 30, "E": 1},
        "recipes": [{"match": {"category": "Mark"}, "steps": ["6", "3"]}],
        "recipeCompletion": {"regular": {"complete": 14, "total": len(SEQ)},
                             "bold": {"complete": 11, "total": len(SEQ)}},
        "coverage": _coverage(),
        "changes": {"regular": {"A": [4, 8], "H": [6, 3]}},
    }


def _coverage() -> dict:
    def script_rows(bump: int) -> list:
        return [
            {"key": "latin", "total": 16, "final": 8 + bump, "started": 12, "uncolored": 4,
             "counts": {}, "dist": {"8": 6, "4": 3, "6": 3}},
            {"key": "punctuation", "total": 6, "final": 2, "started": 4, "uncolored": 2,
             "counts": {}, "dist": {"6": 2, "3": 2}},
        ]
    category_rows = [
        {"key": "Letter", "total": 18, "final": 10, "started": 15, "uncolored": 3,
         "counts": {}, "dist": {"8": 5, "4": 5, "6": 3, "3": 2}},
        {"key": "Punctuation", "total": 4, "final": 1, "started": 2, "uncolored": 2,
         "counts": {}, "dist": {"3": 1, "6": 1}},
    ]
    return {
        "byScript": {"regular": script_rows(2), "bold": script_rows(0)},
        "byCategory": {"regular": category_rows, "bold": category_rows},
    }


def _trend() -> dict:
    dates = DATES
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
    return {"series": series, "forecast": forecast, "today": "2026-06-05",
            "streak": {"current": 3, "best": 5, "days": 3}}


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    for is_free in (False, True):
        path = out_dir / f"dashboard_{'free' if is_free else 'step'}.html"
        path.write_text(assets.build_html(_model(is_free)), encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
