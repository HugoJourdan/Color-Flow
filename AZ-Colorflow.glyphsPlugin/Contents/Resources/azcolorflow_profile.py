"""Portable Color Flow workflow profiles — export / import / diff.

A ``.azcolorflow`` file is a small JSON bundle of everything that defines a Color
Flow workflow: the ``colorNames.txt`` text (colour order, labels, visibility,
None label), the Rainbow Font View source, and the 12 Glyphs label colours
(RGBA). Sharing one lets a team standardise their workflow.

This module is pure (no GlyphsApp): it builds, (de)serialises and *diffs*
profiles. The plugin gathers the live values, calls :func:`build_profile`, and on
import applies a parsed profile by writing colorNames.txt + the defaults. The diff
is what makes import conflict-surfacing rather than a silent overwrite.
"""

from __future__ import annotations

import json

import colornames

PROFILE_VERSION = 1
RAINBOW_SOURCES = ("Layer", "Glyph")
_COLOR_EPSILON = 1e-3


def build_profile(
    color_names: str, rainbow_source: str, label_colors: list, name: str = ""
) -> dict:
    """Assemble a portable profile dict from the live Color Flow config values."""
    source = rainbow_source if rainbow_source in RAINBOW_SOURCES else "Layer"
    return {
        "version": PROFILE_VERSION,
        "name": name or "Color Flow profile",
        "colorNames": color_names or "",
        "rainbowSource": source,
        "labelColors": [list(rgba) for rgba in label_colors],
    }


def serialize(profile: dict) -> str:
    """The profile as pretty JSON, ready to write to a ``.azcolorflow`` file."""
    return json.dumps(profile, ensure_ascii=False, indent=2)


def _coerce_label_colors(raw_colors: object) -> list[tuple]:
    """Validate the ``labelColors`` field into a list of RGBA tuples of floats.
    Raises ``ValueError`` if the field or any entry is not a list/tuple, or if
    any component is not a number — so a malformed profile surfaces as a caught
    ``ValueError`` rather than a bare ``TypeError`` raised later (e.g. by
    :func:`diff_profile` comparing components arithmetically)."""
    if not isinstance(raw_colors, list):
        raise ValueError(f"labelColors must be a list, got {type(raw_colors).__name__}.")
    coerced: list[tuple] = []
    for rgba in raw_colors:
        if not isinstance(rgba, (list, tuple)):
            raise ValueError(f"Each labelColors entry must be a list, got {type(rgba).__name__}.")
        try:
            coerced.append(tuple(float(component) for component in rgba))
        except (TypeError, ValueError) as error:
            raise ValueError(f"Each labelColors component must be a number: {error}") from error
    return coerced


def parse(text: str) -> dict:
    """Parse + normalise a ``.azcolorflow`` file into a profile dict. Raises
    ``ValueError`` on malformed JSON, a non-object, an unsupported version, or a
    malformed ``labelColors`` field."""
    try:
        raw = json.loads(text)
    except (ValueError, TypeError) as error:
        raise ValueError(f"Not a valid .azcolorflow file: {error}") from error
    if not isinstance(raw, dict):
        raise ValueError("Not a valid .azcolorflow file: expected a JSON object.")
    if raw.get("version") != PROFILE_VERSION:
        raise ValueError(f"Unsupported .azcolorflow version: {raw.get('version')!r}")
    # Tolerant parsing: unknown keys in the raw JSON (e.g. retired fields
    # written by older plugin versions) are simply ignored.
    return build_profile(
        color_names=str(raw.get("colorNames") or ""),
        rainbow_source=str(raw.get("rainbowSource") or "Layer"),
        label_colors=_coerce_label_colors(raw.get("labelColors") or []),
        name=str(raw.get("name") or ""),
    )


def _label_color_changes(current: list, incoming: list) -> int:
    """How many of the 12 label-colour slots differ (beyond rounding noise)."""
    changed = 0
    for index in range(max(len(current), len(incoming))):
        a = current[index] if index < len(current) else ()
        b = incoming[index] if index < len(incoming) else ()
        # (zip only evaluates when the length check above passed, so strict is a no-op)
        if len(a) != len(b) or any(abs(x - y) > _COLOR_EPSILON for x, y in zip(a, b, strict=True)):
            changed += 1
    return changed


def _color_names_diff(current_text: str, incoming_text: str) -> list[tuple[str, str]]:
    """Human-readable differences between two colorNames.txt texts: colour order,
    per-colour label and visibility, and the None label."""
    current_rows, current_none = colornames.parse_settings(current_text)
    incoming_rows, incoming_none = colornames.parse_settings(incoming_text)
    current_by = {index: (label, visible) for index, label, visible in current_rows}
    diffs: list[tuple[str, str]] = []
    if [index for index, _l, _v in current_rows] != [index for index, _l, _v in incoming_rows]:
        diffs.append(("Order", "colour order differs"))
    for index, label, visible in incoming_rows:
        previous_label, previous_visible = current_by.get(index, ("", False))
        name = colornames.COLOR_NAMES.get(index, str(index))
        if previous_label != label:
            diffs.append(("Label", f"{name}: {previous_label!r} -> {label!r}"))
        if previous_visible != visible:
            shown = "shown" if previous_visible else "hidden"
            now = "shown" if visible else "hidden"
            diffs.append(("Visibility", f"{name}: {shown} -> {now}"))
    if current_none != incoming_none:
        diffs.append(("None label", f"{current_none!r} -> {incoming_none!r}"))
    return diffs


def diff_profile(current: dict, incoming: dict) -> list[dict]:
    """Field-level differences ``[{field, detail}]`` between the live profile and
    an incoming one — surfaced to the user before applying an import so a shared
    profile never silently overwrites local choices. Empty when identical."""
    diffs: list[dict] = []
    if current.get("rainbowSource") != incoming.get("rainbowSource"):
        diffs.append(
            {
                "field": "Rainbow source",
                "detail": f"{current.get('rainbowSource')} -> {incoming.get('rainbowSource')}",
            }
        )
    changed = _label_color_changes(
        current.get("labelColors") or [], incoming.get("labelColors") or []
    )
    if changed:
        diffs.append({"field": "Label colours", "detail": f"{changed} of 12 differ"})
    diffs.extend(
        {"field": field, "detail": detail}
        for field, detail in _color_names_diff(
            current.get("colorNames") or "", incoming.get("colorNames") or ""
        )
    )
    return diffs
