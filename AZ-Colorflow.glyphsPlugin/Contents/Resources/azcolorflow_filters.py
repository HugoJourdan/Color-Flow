"""Build the "Color Flow" smart-filter group for the Glyphs sidebar.

Generates a folder of smart filters — one per workflow step, plus a "None"
bucket — as the structure Glyphs stores in a font's ``Filters`` custom
parameter. Each leaf is a predicate filter on ``colorIndex``; the folder nests
its children under ``subGroup``. Glyphs' ``colorIndex`` predicate matches the
GLYPH colour (there is no per-master layer-colour predicate), so these filters
track glyph colour — exact per step, never a cumulative ``colorIndex <= N``
(which would be wrong whenever the workflow order is not ascending colour
index).

Pure: it only assembles/merges plain dicts. The plugin reads the visible steps,
calls :func:`build_filter_group`, merges it into the existing ``Filters`` value
and writes it back.
"""

from __future__ import annotations

GROUP_NAME = "AZ Colorflow"
# Glyphs' sentinel for "no colour label" in a colorIndex predicate.
NO_COLOR_INDEX = 255


def step_filter(label: str, color_index: int) -> dict:
    """One leaf smart filter: glyphs whose colour is exactly ``color_index``."""
    return {"name": label, "predicate": f"colorIndex == {int(color_index)}"}


def build_filter_group(steps: list, none_label: str = "None", group_name: str = GROUP_NAME) -> dict:
    """A ``{"name", "subGroup": [...]}`` folder: one exact filter per step plus a
    trailing "no colour" filter. ``steps`` is ordered ``[(color_index, label)]``
    in workflow order; blank labels fall back to the colour index."""
    items = [step_filter(label or f"Colour {index}", index) for index, label in steps]
    items.append({"name": none_label or "None", "predicate": f"colorIndex == {NO_COLOR_INDEX}"})
    return {"name": group_name, "subGroup": items}


def merge_into_filters(
    existing: list[dict] | None, group: dict, group_name: str = GROUP_NAME
) -> list[dict]:
    """Return the ``Filters`` list with any previous group of the same name
    replaced by ``group`` (so regenerating updates in place, never duplicates).
    ``existing`` may be ``None`` (treated as an empty list)."""
    kept = [entry for entry in (existing or []) if entry.get("name") != group_name]
    kept.append(group)
    return kept
