"""Tests for the pure glyph-outline -> SVG path conversion."""

from __future__ import annotations

import glyphsvg


def test_svg_path_d_flips_y_and_builds_commands() -> None:
    elements = [("move", [(0, 100)]), ("line", [(50, 100)]),
                ("curve", [(60, 90), (60, 10), (50, 0)]), ("close", [])]
    assert glyphsvg.svg_path_d(elements) == "M0 -100L50 -100C60 -90 60 -10 50 0Z"


def test_svg_path_d_skips_malformed_and_rounds() -> None:
    assert glyphsvg.svg_path_d([("move", []), ("curve", [(1, 1)])]) == ""
    assert glyphsvg.svg_path_d([("close", [])]) == "Z"
    assert glyphsvg.svg_path_d([("line", [(10.4, -2.6)])]) == "L10 3"


class _FakePoint:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class _FakeBezier:
    def __init__(self, elements: list) -> None:
        self._elements = elements  # list of (element_type, [(x, y), ...])

    def elementCount(self) -> int:
        return len(self._elements)

    def elementAtIndex_associatedPoints_(self, index: int):
        element_type, points = self._elements[index]
        return element_type, [_FakePoint(x, y) for x, y in points]


class _FakeLayer:
    def __init__(self, bezier: object) -> None:
        self.drawBezierPath = bezier


def test_layer_svg_path_from_bezier_elements() -> None:
    bezier = _FakeBezier([(0, [(0, 0)]), (1, [(100, 0)]),
                          (2, [(110, 10), (110, 90), (100, 100)]), (3, [])])
    assert glyphsvg.layer_svg_path(_FakeLayer(bezier)) == "M0 0L100 0C110 -10 110 -90 100 -100Z"


def test_layer_svg_path_empty_without_path() -> None:
    class _NoPath:
        drawBezierPath = None
        bezierPath = None

    assert glyphsvg.layer_svg_path(_NoPath()) == ""


def test_view_box_is_tight_with_padding() -> None:
    elements = [("move", [(100, 0)]), ("line", [(500, 700)]), ("close", [])]
    assert glyphsvg.view_box(elements, pad=40) == "60 -740 480 780"


def test_view_box_empty_for_no_points() -> None:
    assert glyphsvg.view_box([("close", [])]) == ""


def test_layer_outline_returns_d_and_view_box() -> None:
    bezier = _FakeBezier([(0, [(100, 0)]), (1, [(500, 0)]), (1, [(500, 700)]), (3, [])])
    outline = glyphsvg.layer_outline(_FakeLayer(bezier))
    assert outline["d"] == "M100 0L500 0L500 -700Z"
    assert outline["vb"] == "60 -740 480 780"


def test_layer_outline_empty_without_path() -> None:
    class _NoPath:
        drawBezierPath = None
        bezierPath = None

    assert glyphsvg.layer_outline(_NoPath()) == {}


def test_layers_outline_offsets_and_combines() -> None:
    a = _FakeLayer(_FakeBezier([(0, [(0, 0)]), (1, [(100, 0)]), (3, [])]))
    b = _FakeLayer(_FakeBezier([(0, [(0, 0)]), (1, [(100, 0)]), (3, [])]))
    outline = glyphsvg.layers_outline([(a, 0.0), (b, 100.0)])
    # second glyph is shifted right by 100 units; both share the one viewBox
    assert outline["d"] == "M0 0L100 0ZM100 0L200 0Z"
    assert outline["vb"] == "-40 -40 280 80"


def test_layers_outline_empty_when_no_outline() -> None:
    class _NoPath:
        drawBezierPath = None
        bezierPath = None

    assert glyphsvg.layers_outline([(_NoPath(), 0.0)]) == {}
