"""Find glyphs whose OUTLINES changed between dated font versions.

Color Flow already reconstructs a font's dated history from git (``azcolorflow_git``)
to drive the timeline. This module is the pure, Glyphs-free companion that turns a
sequence of per-day *outline* snapshots into "what shape changed, and when".

A per-day snapshot is a path map — the same ``{"d", "vb"}`` SVG shape
``glyphsvg.layer_outline_em`` already produces — keyed by master then glyph:

    {master_id: {glyph_name: {"d": "M0 0 ...", "vb": "x y w h"}}}

The diff compares a glyph's ``d`` string between two days; equality of ``d`` means
the outline is unchanged (same nodes, same order). Only glyphs present with a
non-empty outline in BOTH days of the SAME master are compared — added or removed
glyphs are out of scope for this view (the timeline covers coverage growth already).
"""

from __future__ import annotations

from collections.abc import Mapping

# {master_id: {glyph_name: {"d": str, "vb": str}}}
PathMap = Mapping[str, Mapping[str, Mapping[str, str]]]


def diff_path_maps(prev: PathMap, cur: PathMap) -> list[dict]:
    """Glyphs whose outline ``d`` differs between ``prev`` and ``cur``, per master.

    Returns a list of ``{"glyph", "master", "old": {"d","vb"}, "new": {"d","vb"}}``
    sorted by ``(master, glyph)``. A glyph is reported only when it has a non-empty
    ``d`` in both versions of the same master and the two ``d`` strings differ."""
    changes: list[dict] = []
    for master_id, cur_glyphs in cur.items():
        prev_glyphs = prev.get(master_id) or {}
        for glyph_name, new_path in cur_glyphs.items():
            old_path = prev_glyphs.get(glyph_name)
            if not old_path or not new_path:
                continue
            old_d = old_path.get("d") or ""
            new_d = new_path.get("d") or ""
            if not old_d or not new_d or old_d == new_d:
                continue
            changes.append({
                "glyph": glyph_name,
                "master": master_id,
                "old": {"d": old_d, "vb": old_path.get("vb") or ""},
                "new": {"d": new_d, "vb": new_path.get("vb") or ""},
            })
    changes.sort(key=lambda change: (str(change["master"]), str(change["glyph"])))
    return changes


def outline_changes(
    day_maps: Mapping[str, PathMap], limit_per_day: int | None = None
) -> dict[str, list[dict]]:
    """Per-date outline changes from ``{iso_date: path_map}``.

    Each date is diffed against the chronologically previous date, so the result is
    ``{iso_date: [change, ...]}`` for every date that changed at least one glyph
    versus the day before. The earliest date has no predecessor and never appears.
    ``limit_per_day`` (when set) caps the changes kept for a date, in the stable
    ``(master, glyph)`` order ``diff_path_maps`` returns."""
    result: dict[str, list[dict]] = {}
    dates = sorted(day_maps)
    for position in range(1, len(dates)):
        previous = day_maps[dates[position - 1]]
        current = day_maps[dates[position]]
        changes = diff_path_maps(previous, current)
        if limit_per_day is not None and len(changes) > limit_per_day:
            changes = changes[:limit_per_day]
        if changes:
            result[dates[position]] = changes
    return result
