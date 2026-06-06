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
