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


def layer_svg_path(layer) -> str:
    """SVG ``d`` for one ``GSLayer`` (empty string when it has no outline)."""
    path = _bezier_path(layer)
    if path is None:
        return ""
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
    except Exception:
        return ""
    return svg_path_d(elements)
