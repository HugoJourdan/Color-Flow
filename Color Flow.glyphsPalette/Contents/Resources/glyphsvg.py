# encoding: utf-8
"""Turn a Glyphs layer into an SVG path so the dashboard can draw real glyphs.

``layer_svg_path`` reads a ``GSLayer``'s ``drawBezierPath`` (outlines + decomposed
components) and converts the ``NSBezierPath`` elements into an SVG ``d`` string,
flipping the Y axis (font coordinates are y-up, SVG is y-down). The element ->
``d`` conversion (:func:`svg_path_d`) is pure and unit-tested; the layer reader is
duck-typed so it works against a real ``GSLayer`` inside Glyphs and a fake in tests.
"""

from __future__ import annotations

from typing import Any

# NSBezierPath element types (AppKit), kept as literals so this module needs no
# AppKit import and stays testable: moveTo / lineTo / curveTo (cubic) / closePath.
_MOVE, _LINE, _CURVE, _CLOSE = 0, 1, 2, 3


def _num(value: float) -> str:
    """Compact integer coordinate (glyph units round fine at swatch size)."""
    return str(int(round(value)))


def svg_path_d(elements: list) -> str:
    """``[(kind, points)]`` -> an SVG path ``d`` string, with Y flipped.

    ``kind`` is ``"move" | "line" | "curve" | "close"``; ``points`` is a list of
    ``(x, y)`` in font coordinates (y up). ``curve`` carries three points (two
    control points + the on-curve end), matching a cubic ``C``."""
    parts: list[str] = []
    for kind, points in elements:
        if kind == "move" and points:
            parts.append(f"M{_num(points[0][0])} {_num(-points[0][1])}")
        elif kind == "line" and points:
            parts.append(f"L{_num(points[0][0])} {_num(-points[0][1])}")
        elif kind == "curve" and len(points) >= 3:
            parts.append("C" + " ".join(f"{_num(x)} {_num(-y)}" for x, y in points[:3]))
        elif kind == "close":
            parts.append("Z")
    return "".join(parts)


def view_box(elements: list, pad: float = 40.0) -> str:
    """A tight SVG ``viewBox`` ("x y w h") around the outline (flipped Y), with a
    little padding, so each glyph fills its cell instead of floating in the em."""
    xs: list = []
    ys: list = []
    for _kind, points in elements:
        for x, y in points:
            xs.append(x)
            ys.append(y)
    if not xs:
        return ""
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    width = max(1.0, (max_x - min_x) + 2 * pad)
    height = max(1.0, (max_y - min_y) + 2 * pad)
    return f"{_num(min_x - pad)} {_num(-max_y - pad)} {_num(width)} {_num(height)}"


def _bezier_path(layer) -> Any:
    """The layer's drawing path (outlines + components), tolerant of property vs
    method and of layers that have none."""
    getter = getattr(layer, "drawBezierPath", None)
    try:
        path = getter() if callable(getter) else getter
    except Exception:
        path = None
    if path is None:
        path = getattr(layer, "bezierPath", None)
    return path


def _layer_elements(layer) -> list:
    """``[(kind, points)]`` for a layer's outline, or ``[]`` when it has none."""
    path = _bezier_path(layer)
    if path is None:
        return []
    try:
        elements = []
        for index in range(path.elementCount()):
            element_type, points = path.elementAtIndex_associatedPoints_(index)
            if element_type == _MOVE:
                elements.append(("move", [(points[0].x, points[0].y)]))
            elif element_type == _LINE:
                elements.append(("line", [(points[0].x, points[0].y)]))
            elif element_type == _CURVE:
                elements.append(("curve", [(point.x, point.y) for point in points[:3]]))
            elif element_type == _CLOSE:
                elements.append(("close", []))
        return elements
    except Exception:
        return []


def layer_svg_path(layer) -> str:
    """SVG ``d`` for one ``GSLayer`` (empty string when it has no outline)."""
    return svg_path_d(_layer_elements(layer))


def layer_outline(layer) -> dict:
    """``{"d": <path>, "vb": <viewBox>}`` for a layer's glyph, or ``{}`` when it has
    no outline. The viewBox is tight to the glyph so it fills the dashboard cell."""
    elements = _layer_elements(layer)
    d = svg_path_d(elements)
    if not d:
        return {}
    return {"d": d, "vb": view_box(elements)}


def layer_outline_em(layer, em_top: float, em_height: float) -> dict:
    """``{"d", "vb"}`` for a cell glyph using a SHARED square viewBox (side
    ``em_height``) centred horizontally on the glyph and aligned to the font
    baseline, so every cell scales identically and glyphs keep their real relative
    sizes ("a" is shorter than "A") instead of each filling its cell.

    ``em_top`` is the flipped-Y top of the box (``-ascender``); ``em_height`` is the
    ascender-to-descender span. ``{}`` when the layer has no outline."""
    elements = _layer_elements(layer)
    d = svg_path_d(elements)
    if not d:
        return {}
    xs = [x for _kind, points in elements for x, _y in points]
    center_x = (min(xs) + max(xs)) / 2.0 if xs else 0.0
    box_x = center_x - em_height / 2.0
    return {"d": d, "vb": f"{_num(box_x)} {_num(em_top)} {_num(em_height)} {_num(em_height)}"}


def layers_outline(layers_with_offsets: list) -> dict:
    """Combine several layers, each shifted by an x advance, into one
    ``{"d", "vb"}`` — e.g. an "Aa" preview for a master tab. ``layers_with_offsets``
    is ``[(layer, dx), ...]``; ``dx`` is added to every x so glyphs sit side by
    side. Returns ``{}`` when none of the layers has an outline."""
    combined: list = []
    for layer, dx in layers_with_offsets:
        for kind, points in _layer_elements(layer):
            combined.append((kind, [(x + dx, y) for x, y in points]))
    d = svg_path_d(combined)
    if not d:
        return {}
    return {"d": d, "vb": view_box(combined)}
