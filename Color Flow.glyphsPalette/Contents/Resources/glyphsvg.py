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
# AppKit import and stays testable: moveTo / lineTo / curveTo (cubic) / closePath
# / quadraticCurveTo (NSBezierPathElementQuadraticCurveTo == 4).
_MOVE, _LINE, _CURVE, _CLOSE, _QUAD = 0, 1, 2, 3, 4


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


def _on_curve_points(elements: list) -> list[tuple[float, float]]:
    """The on-curve (endpoint) coordinates of an ``[(kind, points)]`` outline.

    For ``move``/``line`` the single point is on-curve; for ``curve`` only the
    last of the three points (the segment end) is on-curve — the first two are
    off-curve control points. ``close`` carries no point. Using these instead of
    every control point gives a good ink-bounds approximation (without flattening)
    for centring/viewBox maths, so glyphs sit tight and centred."""
    on_curve: list[tuple[float, float]] = []
    for kind, points in elements:
        if not points:
            continue
        if kind == "curve":
            on_curve.append(points[-1])
        else:
            on_curve.append(points[0])
    return on_curve


def view_box(elements: list, pad: float = 40.0) -> str:
    """A tight SVG ``viewBox`` ("x y w h") around the outline (flipped Y), with a
    little padding, so each glyph fills its cell instead of floating in the em.

    The bounds come from on-curve points (a practical ink-bounds approximation)
    so off-curve control points don't loosen the box."""
    xs: list = []
    ys: list = []
    for x, y in _on_curve_points(elements):
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


def _quad_to_cubic(
    start: tuple[float, float],
    control: tuple[float, float],
    end: tuple[float, float],
) -> list[tuple[float, float]]:
    """Elevate a quadratic curve (start, one control, end) to a cubic's two control
    points + end, so quad segments survive the cubic-only ``svg_path_d``."""
    control_1 = (
        start[0] + 2.0 / 3.0 * (control[0] - start[0]),
        start[1] + 2.0 / 3.0 * (control[1] - start[1]),
    )
    control_2 = (
        end[0] + 2.0 / 3.0 * (control[0] - end[0]),
        end[1] + 2.0 / 3.0 * (control[1] - end[1]),
    )
    return [control_1, control_2, end]


def _layer_elements(layer) -> list:
    """``[(kind, points)]`` for a layer's outline, or ``[]`` when it has none.

    Each element is parsed in its own ``try``/``except`` so one malformed segment
    is skipped without discarding the rest of the glyph. Quadratic segments are
    elevated to cubics; any other unknown non-close element falls back to a
    line-to its endpoint so the contour stays continuous instead of gaining a
    hole."""
    path = _bezier_path(layer)
    if path is None:
        return []
    elements: list = []
    current_point: tuple[float, float] = (0.0, 0.0)
    try:
        count = path.elementCount()
    except Exception:
        return []
    for index in range(count):
        try:
            element_type, points = path.elementAtIndex_associatedPoints_(index)
            if element_type == _MOVE:
                current_point = (points[0].x, points[0].y)
                elements.append(("move", [current_point]))
            elif element_type == _LINE:
                current_point = (points[0].x, points[0].y)
                elements.append(("line", [current_point]))
            elif element_type == _CURVE:
                curve_points = [(point.x, point.y) for point in points[:3]]
                current_point = curve_points[-1]
                elements.append(("curve", curve_points))
            elif element_type == _QUAD:
                control = (points[0].x, points[0].y)
                end = (points[1].x, points[1].y)
                curve_points = _quad_to_cubic(current_point, control, end)
                current_point = end
                elements.append(("curve", curve_points))
            elif element_type == _CLOSE:
                elements.append(("close", []))
            else:
                # Unknown non-close element: keep the contour continuous with a
                # line-to its (last) endpoint rather than dropping the segment.
                endpoint = (points[-1].x, points[-1].y)
                current_point = endpoint
                elements.append(("line", [endpoint]))
        except Exception:
            continue
    return elements


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


def layer_outline_em(layer, em_height: float) -> dict:
    """``{"d", "vb"}`` for a cell glyph using a SHARED square viewBox (side
    ``em_height``) centred on the glyph's ink in BOTH axes, so every cell scales
    identically (glyphs keep their real relative sizes — "a" is shorter than "A")
    while each glyph sits perfectly centred in its cell.

    ``em_height`` is the ascender-to-descender span (the constant scale). ``{}``
    when the layer has no outline."""
    elements = _layer_elements(layer)
    d = svg_path_d(elements)
    if not d:
        return {}
    on_curve = _on_curve_points(elements)
    xs = [x for x, _y in on_curve]
    ys = [y for _x, y in on_curve]
    center_x = (min(xs) + max(xs)) / 2.0 if xs else 0.0
    center_y = (min(ys) + max(ys)) / 2.0 if ys else 0.0
    box_x = center_x - em_height / 2.0
    box_y = -center_y - em_height / 2.0  # flipped Y: SVG y = -font y
    return {"d": d, "vb": f"{_num(box_x)} {_num(box_y)} {_num(em_height)} {_num(em_height)}"}


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
