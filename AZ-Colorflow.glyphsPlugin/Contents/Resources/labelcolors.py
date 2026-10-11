"""Read / write the twelve Glyphs label colours (``Glyphs.defaults['LabelColors']``).

These are the app-wide colours Glyphs draws for layer / glyph colour labels 0-11.
Glyphs stores them as an array of NSArchiver-archived ``NSColor`` objects (the same
format the mekkablue *Set Label Colors* script uses); when nothing is stored, the
built-in defaults apply. Color Flow reads them so its palette swatches and the
dashboard follow whatever the user has chosen, and writes them when the user edits
a colour in the palette's action popover.

The pure helpers (``DEFAULTS``, ``hex_for``, and the no-Glyphs fallbacks) import
nothing from AppKit / GlyphsApp so they stay unit-testable; the archive/unarchive
paths only run inside Glyphs.
"""

from __future__ import annotations

# Glyphs' built-in label colours as (r, g, b, a) in 0..1, index 0-11. Used when the
# user has not overridden them (matches the Set Label Colors defaults).
DEFAULTS: list[tuple[float, float, float, float]] = [
    (0.85, 0.26, 0.06, 1.0),
    (0.99, 0.62, 0.11, 1.0),
    (0.65, 0.48, 0.20, 1.0),
    (0.97, 0.90, 0.00, 1.0),
    (0.67, 0.95, 0.38, 1.0),
    (0.04, 0.57, 0.04, 1.0),
    (0.06, 0.60, 0.98, 1.0),
    (0.00, 0.20, 0.88, 1.0),
    (0.50, 0.09, 0.79, 1.0),
    (0.98, 0.36, 0.67, 1.0),
    (0.75, 0.75, 0.75, 1.0),
    (0.25, 0.25, 0.25, 1.0),
]

# The Glyphs preference key holding the archived label colours.
DEFAULTS_KEY = "LabelColors"

try:
    from AppKit import NSArchiver, NSColor, NSMutableArray, NSUnarchiver  # type: ignore[import]
    from GlyphsApp import Glyphs  # type: ignore[import]
except Exception:  # pragma: no cover - only importable inside Glyphs
    NSArchiver = NSColor = NSMutableArray = NSUnarchiver = None
    Glyphs = None


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def hex_for(rgba: tuple) -> str:
    """``(r, g, b[, a])`` floats in 0..1 -> a ``#rrggbb`` string (alpha ignored)."""
    return f"#{round(_clamp(rgba[0]) * 255):02x}{round(_clamp(rgba[1]) * 255):02x}{round(_clamp(rgba[2]) * 255):02x}"


def read_label_colors() -> list[tuple[float, float, float, float]]:
    """The twelve current label colours as ``(r, g, b, a)`` tuples, falling back to
    :data:`DEFAULTS` when nothing is stored or when running outside Glyphs."""
    if Glyphs is None or NSUnarchiver is None:
        return list(DEFAULTS)
    stored = Glyphs.defaults[DEFAULTS_KEY]
    if not stored:
        return list(DEFAULTS)
    colors: list[tuple[float, float, float, float]] = []
    for index in range(12):
        try:
            color = NSUnarchiver.unarchiveObjectWithData_(stored[index])
            # Read in DEVICE RGB — the same space write_label_colors stores them in
            # (``colorWithDeviceRed:``). A device->device round-trip is the identity, so a
            # colour written by Color Flow reads back byte-for-byte; converting to calibrated
            # here would shift every component and make each save/load cycle drift the colours.
            rgb = color.colorUsingColorSpaceName_("NSDeviceRGBColorSpace") or color
            colors.append(
                (
                    rgb.redComponent(),
                    rgb.greenComponent(),
                    rgb.blueComponent(),
                    rgb.alphaComponent(),
                )
            )
        except Exception:
            colors.append(DEFAULTS[index])
    return colors


def hex_list() -> list[str]:
    """The twelve current label colours as ``#rrggbb`` strings."""
    return [hex_for(rgba) for rgba in read_label_colors()]


def _ns_color(rgba: tuple) -> object:
    """``(r, g, b[, a])`` -> a clamped device ``NSColor`` (callers ensure Glyphs)."""
    assert NSColor is not None
    values = (tuple(rgba) + (1.0,))[:4]
    return NSColor.colorWithDeviceRed_green_blue_alpha_(*(_clamp(v) for v in values))


def write_label_colors(colors: list) -> bool:
    """Persist twelve ``(r, g, b, a)`` tuples to ``Glyphs.defaults['LabelColors']``
    as NSArchiver-archived ``NSColor`` objects (how Glyphs stores them). Returns
    ``False`` (a no-op) outside Glyphs."""
    if Glyphs is None or NSColor is None or NSArchiver is None or NSMutableArray is None:
        return False
    archived = NSMutableArray.new()
    for rgba in colors:
        archived.addObject_(NSArchiver.archivedDataWithRootObject_(_ns_color(rgba)))
    Glyphs.defaults[DEFAULTS_KEY] = archived
    return True


def refresh_app_label_colors(colors: list) -> None:
    """Best-effort: make the *running* Glyphs pick up new label colours without a
    restart, for its own Font / Edit views.

    Glyphs caches ``+[GSGlyphsInfo labelColors]`` with no public setter/reset, so
    this is undocumented and fully guarded. It tries, in order: a private reload
    selector (if any exists), mutating the cached colour array in place, then a
    redraw. It silently no-ops if none of that is supported — Color Flow's own
    palette + dashboard already read the colours directly, so they update either
    way; only Glyphs' native drawing depends on this working."""
    if Glyphs is None or NSColor is None:
        return
    try:
        import objc

        info = objc.lookUpClass("GSGlyphsInfo")
    except Exception:
        info = None
    if info is not None:
        for selector_name in ("reloadLabelColors", "resetLabelColors", "clearLabelColors"):
            method = getattr(info, selector_name, None)
            if method is not None:
                try:
                    method()
                except Exception:
                    pass
        try:
            cached = info.labelColors()
            if cached is not None and hasattr(cached, "replaceObjectAtIndex_withObject_"):
                for index in range(min(len(cached), len(colors))):
                    cached.replaceObjectAtIndex_withObject_(index, _ns_color(colors[index]))
        except Exception:
            pass
    try:
        Glyphs.redraw()
    except Exception:
        pass


def reset_label_colors() -> None:
    """Clear the override so Glyphs' built-in label colours apply again."""
    if Glyphs is not None:
        Glyphs.defaults[DEFAULTS_KEY] = None
