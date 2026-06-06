# encoding: utf-8
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
    (0.85, 0.26, 0.06, 1.0), (0.99, 0.62, 0.11, 1.0), (0.65, 0.48, 0.20, 1.0),
    (0.97, 0.90, 0.00, 1.0), (0.67, 0.95, 0.38, 1.0), (0.04, 0.57, 0.04, 1.0),
    (0.06, 0.60, 0.98, 1.0), (0.00, 0.20, 0.88, 1.0), (0.50, 0.09, 0.79, 1.0),
    (0.98, 0.36, 0.67, 1.0), (0.75, 0.75, 0.75, 1.0), (0.25, 0.25, 0.25, 1.0),
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
    return "#{:02x}{:02x}{:02x}".format(
        round(_clamp(rgba[0]) * 255),
        round(_clamp(rgba[1]) * 255),
        round(_clamp(rgba[2]) * 255),
    )


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
            rgb = color.colorUsingColorSpaceName_("NSCalibratedRGBColorSpace") or color
            colors.append((rgb.redComponent(), rgb.greenComponent(),
                           rgb.blueComponent(), rgb.alphaComponent()))
        except Exception:
            colors.append(DEFAULTS[index])
    return colors


def hex_list() -> list[str]:
    """The twelve current label colours as ``#rrggbb`` strings."""
    return [hex_for(rgba) for rgba in read_label_colors()]


def write_label_colors(colors: list) -> bool:
    """Persist twelve ``(r, g, b, a)`` tuples to ``Glyphs.defaults['LabelColors']``
    as NSArchiver-archived ``NSColor`` objects (how Glyphs stores them). Returns
    ``False`` (a no-op) outside Glyphs."""
    if Glyphs is None or NSColor is None or NSArchiver is None or NSMutableArray is None:
        return False
    archived = NSMutableArray.new()
    for rgba in colors:
        values = (tuple(rgba) + (1.0,))[:4]
        color = NSColor.colorWithDeviceRed_green_blue_alpha_(*(_clamp(v) for v in values))
        archived.addObject_(NSArchiver.archivedDataWithRootObject_(color))
    Glyphs.defaults[DEFAULTS_KEY] = archived
    return True


def reset_label_colors() -> None:
    """Clear the override so Glyphs' built-in label colours apply again."""
    if Glyphs is not None:
        Glyphs.defaults[DEFAULTS_KEY] = None
