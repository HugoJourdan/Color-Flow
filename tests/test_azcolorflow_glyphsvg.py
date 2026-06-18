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

    def elementAtIndex_associatedPoints_(self, index: int) -> tuple[int, list[_FakePoint]]:
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


def test_layer_outline_em_uses_baseline_aligned_box() -> None:
    bezier = _FakeBezier([(0, [(100, 0)]), (1, [(500, 0)]), (1, [(500, 700)]), (3, [])])
    # ascender 800, descender -200 -> span 1000; top_pad 0.20 -> 200, bot_pad 0.10 -> 100;
    # box = 1300. x-centre 300 -> box_x 300-650 = -350. baseline-framed: box_y = -(800+200) = -1000.
    outline = glyphsvg.layer_outline_em(_FakeLayer(bezier), 800.0, -200.0)
    assert outline["d"] == "M100 0L500 0L500 -700Z"
    assert outline["vb"] == "-350 -1000 1300 1300"


def test_layer_outline_em_shares_baseline_regardless_of_ink_height() -> None:
    # Two glyphs of very different ink height get the SAME vertical frame (box_y/box),
    # so font y=0 (the baseline) lands at the same place in every cell.
    short = _FakeBezier([(0, [(0, 0)]), (1, [(400, 0)]), (1, [(400, 400)]), (3, [])])
    tall = _FakeBezier([(0, [(0, 0)]), (1, [(400, 0)]), (1, [(400, 900)]), (3, [])])
    vb_short = glyphsvg.layer_outline_em(_FakeLayer(short), 800.0, -200.0)["vb"].split()
    vb_tall = glyphsvg.layer_outline_em(_FakeLayer(tall), 800.0, -200.0)["vb"].split()
    assert vb_short[1] == vb_tall[1]          # same box_y (vertical frame) -> shared baseline
    assert vb_short[2:] == vb_tall[2:]        # same box side (uniform scale)


def test_layer_outline_em_empty_without_path() -> None:
    class _NoPath:
        drawBezierPath = None
        bezierPath = None

    assert glyphsvg.layer_outline_em(_NoPath(), 800.0, -200.0) == {}


class _BadPoint:
    """A point whose coordinate access raises, to model a malformed element."""

    @property
    def x(self) -> float:
        raise ValueError("malformed point")

    @property
    def y(self) -> float:
        raise ValueError("malformed point")


class _BezierWithBadElement:
    """Like ``_FakeBezier`` but one element index yields a point that raises, so we
    can assert a single bad element is skipped without losing the rest."""

    def __init__(self, elements: list, bad_index: int) -> None:
        self._elements = elements
        self._bad_index = bad_index

    def elementCount(self) -> int:
        return len(self._elements)

    def elementAtIndex_associatedPoints_(self, index: int) -> tuple[int, list[object]]:
        element_type, points = self._elements[index]
        if index == self._bad_index:
            return element_type, [_BadPoint()]
        return element_type, [_FakePoint(x, y) for x, y in points]


def test_one_bad_element_is_skipped_not_whole_glyph() -> None:
    # move, (bad line at index 1), line, close — the good segments must survive.
    bezier = _BezierWithBadElement(
        [(0, [(0, 0)]), (1, [(50, 0)]), (1, [(100, 0)]), (3, [])], bad_index=1
    )
    # Only the malformed line is dropped; the rest of the contour remains.
    assert glyphsvg.layer_svg_path(_FakeLayer(bezier)) == "M0 0L100 0Z"


def test_quadratic_element_is_converted_to_cubic() -> None:
    # quad from (0, 0) via control (60, 60) to (120, 0): elevate to a cubic.
    bezier = _FakeBezier([(0, [(0, 0)]), (4, [(60, 60), (120, 0)]), (3, [])])
    d = glyphsvg.layer_svg_path(_FakeLayer(bezier))
    # control_1 = (0,0)+2/3*((60,60)-(0,0)) = (40, 40)
    # control_2 = (120,0)+2/3*((60,60)-(120,0)) = (80, 40)
    assert d == "M0 0C40 -40 80 -40 120 0Z"


def test_quadratic_keeps_contour_continuous() -> None:
    # A quad element must not blank the path nor leave a gap before the close.
    bezier = _FakeBezier([(0, [(0, 0)]), (1, [(100, 0)]),
                          (4, [(150, 50), (100, 100)]), (3, [])])
    d = glyphsvg.layer_svg_path(_FakeLayer(bezier))
    assert d.startswith("M0 0L100 0C")
    assert d.endswith("100 -100Z")


def test_unknown_element_falls_back_to_line_to_endpoint() -> None:
    # Unknown element type 7 must degrade to a line-to its endpoint, not a hole.
    bezier = _FakeBezier([(0, [(0, 0)]), (7, [(40, 40), (80, 0)]), (3, [])])
    # endpoint is the last associated point (80, 0); flipped Y keeps it on 0.
    assert glyphsvg.layer_svg_path(_FakeLayer(bezier)) == "M0 0L80 0Z"


def test_view_box_uses_on_curve_bounds_not_control_points() -> None:
    # A curve whose control points bulge far outside the on-curve endpoints.
    # On-curve points: (0, 0) and (100, 0); controls (50, 999)/(50, -999) ignored.
    elements = [("move", [(0, 0)]),
                ("curve", [(50, 999), (50, -999), (100, 0)]), ("close", [])]
    # Tight box on on-curve bounds [0..100] x [0..0] with pad 40.
    assert glyphsvg.view_box(elements, pad=40) == "-40 -40 180 80"


def test_layer_outline_em_centres_x_on_on_curve_bounds() -> None:
    # Control points bulge far off-curve; horizontal centring must ignore them, and
    # the vertical frame is baseline-based (independent of ink height).
    bezier = _FakeBezier([(0, [(0, 0)]), (1, [(200, 0)]),
                          (2, [(100, 5000), (100, 5000), (200, 400)]), (3, [])])
    outline = glyphsvg.layer_outline_em(_FakeLayer(bezier), 800.0, -200.0)
    # On-curve xs: 0, 200, 200 -> centre 100; box 1300 -> box_x = 100 - 650 = -550.
    # box_y baseline-framed = -(800+200) = -1000.
    assert outline["vb"] == "-550 -1000 1300 1300"
