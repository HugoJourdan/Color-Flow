"""Tests for the Font-View grouping engine's ``is_dirty`` change detection.

``is_dirty`` is the cheap gate the debounced timer uses before paying for a full
``rebuild``. It must flag: a missing snapshot, a master change, a selected
glyph's colour change, and — the behaviour added here — glyph-membership drift
(a glyph added or deleted while nothing relevant is selected). Off-selection
recolours of EXISTING glyphs are deliberately not detected and are not asserted
to flag.

The GlyphsApp/AppKit-touching code is never reached by these tests: ``is_dirty``
only reads ``font.tempData``, ``font.glyphs``, ``font.selectedLayers`` and the
selected master, all modelled by the fakes below.
"""

from __future__ import annotations

from collections.abc import Iterator

import colornames
import fontview

# --------------------------------------------------------------------------- #
# Fakes — a GSFont-like object just rich enough for ``is_dirty``.
# --------------------------------------------------------------------------- #


class _FakeProxy(dict):
    """Mimics a Glyphs userData/tempData proxy: a missing key yields ``None``
    rather than raising, but ``del`` on a missing key still raises KeyError
    (which the engine's ``_clear`` suppresses)."""

    def __getitem__(self, key: str) -> object:
        return self.get(key)


class _FakeLayers(dict):
    """Glyphs returns ``None`` for a master with no layer, not KeyError."""

    def __getitem__(self, key: str) -> _FakeLayer | None:
        return self.get(key)


class _FakeLayer:
    def __init__(self, color: int | None, parent: _FakeGlyph) -> None:
        self.color = color
        self.parent = parent


class _FakeGlyph:
    def __init__(self, name: str, color: int | None = None) -> None:
        self.name = name
        self.color = color
        self.layers: _FakeLayers = _FakeLayers()

    def add_layer(self, master_id: str, color: int | None) -> _FakeLayer:
        layer = _FakeLayer(color, self)
        self.layers[master_id] = layer
        return layer


class _FakeGlyphs(list):
    """Mirrors ``GSFont.glyphs``: iteration like a list plus name indexing."""

    def by_name(self, name: str) -> _FakeGlyph | None:
        return next((glyph for glyph in self if glyph.name == name), None)


class _FakeMaster:
    def __init__(self, id_: str, name: str = "Regular") -> None:
        self.id = id_
        self.name = name


class _FakeParam:
    def __init__(self, name: str, value: object) -> None:
        self.name = name
        self.value = value
        self.active = True


class _FakeCustomParameters:
    """Mimics ``GSFont.customParameters``: name-keyed get/set/del (a missing name
    reads as ``None``) plus iteration over parameter OBJECTS, which is what the
    engine's ``_glyph_order_param`` fallback relies on."""

    def __init__(self) -> None:
        self._params: list[_FakeParam] = []

    def _find(self, name: str) -> _FakeParam | None:
        return next((param for param in self._params if param.name == name), None)

    def __getitem__(self, name: str) -> object | None:
        param = self._find(name)
        return param.value if param is not None else None

    def __setitem__(self, name: str, value: object) -> None:
        param = self._find(name)
        if param is not None:
            param.value = value
        else:
            self._params.append(_FakeParam(name, value))

    def __delitem__(self, name: str) -> None:
        param = self._find(name)
        if param is None:
            raise KeyError(name)
        self._params.remove(param)

    def __iter__(self) -> Iterator[_FakeParam]:
        return iter(self._params)


class _FakeFont:
    def __init__(self, masters: list[_FakeMaster], glyphs: list[_FakeGlyph]) -> None:
        self.masters = masters
        self.glyphs: _FakeGlyphs = _FakeGlyphs(glyphs)
        self.parent = object()  # truthy -> selectedFontMaster is honoured
        self.selectedFontMaster: _FakeMaster | None = masters[0] if masters else None
        self.selectedLayers: list[_FakeLayer] = []
        self.userData: _FakeProxy = _FakeProxy()
        self.tempData: _FakeProxy = _FakeProxy()
        self.customParameters: _FakeCustomParameters = _FakeCustomParameters()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

MASTER_ID = "m1"
OTHER_MASTER_ID = "m2"


def _make_font(mode: str = "Layer") -> tuple[_FakeFont, fontview.FontViewGrouping]:
    """Build a font with two coloured glyphs and prime the engine's snapshot to
    a freshly-rebuilt, clean state."""
    master = _FakeMaster(MASTER_ID)
    glyph_a = _FakeGlyph("A", color=2)
    glyph_a.add_layer(MASTER_ID, color=2)
    glyph_b = _FakeGlyph("B", color=5)
    glyph_b.add_layer(MASTER_ID, color=5)
    font = _FakeFont([master], [glyph_a, glyph_b])
    font.userData[fontview.MODE_KEY] = mode

    grouping = fontview.FontViewGrouping()
    _prime_snapshot(font, grouping, MASTER_ID)
    return font, grouping


def _prime_snapshot(font: _FakeFont, grouping: fontview.FontViewGrouping, master_id: str) -> None:
    """Populate ``tempData`` the way ``rebuild`` would, without touching the
    AppKit/customParameters path."""
    mode = grouping.mode(font)
    snapshot: dict[str, int] = {}
    for glyph in font.glyphs:
        color = glyph.color if mode == "Glyph" else grouping._layer_color(glyph, master_id)
        snapshot[glyph.name] = colornames.NO_COLOR if color is None else color
    font.tempData[fontview.SNAPSHOT_KEY] = snapshot
    font.tempData[fontview.MASTER_KEY] = master_id


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_clean_state_is_not_dirty() -> None:
    font, grouping = _make_font()
    assert grouping.is_dirty(font) is False


def test_missing_snapshot_is_dirty() -> None:
    font, grouping = _make_font()
    del font.tempData[fontview.SNAPSHOT_KEY]
    assert grouping.is_dirty(font) is True


def test_master_change_is_dirty() -> None:
    font, grouping = _make_font()
    # Selected master now differs from the one cached in the snapshot.
    font.masters.append(_FakeMaster(OTHER_MASTER_ID))
    font.selectedFontMaster = font.masters[1]
    assert grouping.is_dirty(font) is True


def test_selected_glyph_layer_colour_change_is_dirty() -> None:
    font, grouping = _make_font(mode="Layer")
    glyph_a = font.glyphs.by_name("A")
    assert glyph_a is not None
    layer = glyph_a.layers[MASTER_ID]
    assert layer is not None
    layer.color = 9  # recolour the selected layer
    font.selectedLayers = [layer]
    assert grouping.is_dirty(font) is True


def test_selected_glyph_colour_change_is_dirty_glyph_mode() -> None:
    font, grouping = _make_font(mode="Glyph")
    glyph_b = font.glyphs.by_name("B")
    assert glyph_b is not None
    glyph_b.color = 11
    layer = glyph_b.layers[MASTER_ID]
    assert layer is not None
    font.selectedLayers = [layer]
    assert grouping.is_dirty(font) is True


def test_glyph_added_while_nothing_selected_is_dirty() -> None:
    font, grouping = _make_font()
    new_glyph = _FakeGlyph("C", color=7)
    new_glyph.add_layer(MASTER_ID, color=7)
    font.glyphs.append(new_glyph)
    # Nothing relevant is selected — membership drift alone must flag it.
    assert font.selectedLayers == []
    assert grouping.is_dirty(font) is True


def test_glyph_deleted_while_nothing_selected_is_dirty() -> None:
    font, grouping = _make_font()
    del font.glyphs[1]  # drop "B"
    assert font.selectedLayers == []
    assert grouping.is_dirty(font) is True


def test_off_selection_recolour_of_existing_glyph_not_detected() -> None:
    """Documents the known limitation: recolouring an EXISTING, unselected glyph
    is not caught by ``is_dirty`` and relies on a later selection/master change."""
    font, grouping = _make_font(mode="Layer")
    glyph_a = font.glyphs.by_name("A")
    assert glyph_a is not None
    layer = glyph_a.layers[MASTER_ID]
    assert layer is not None
    layer.color = 9  # change colour but leave it UNselected
    assert font.selectedLayers == []
    assert grouping.is_dirty(font) is False


# --------------------------------------------------------------------------- #
# Restoring the user's glyphOrder (disable / strip_for_save)
# --------------------------------------------------------------------------- #


def _enable_with_our_order(font: _FakeFont) -> None:
    """Put the font in the enabled state with OUR grouping order active."""
    font.userData[fontview.ENABLED_KEY] = True
    font.customParameters[fontview.GLYPH_ORDER] = [f"{fontview.HEADER} (Layer)", "A", "B"]


def test_disable_restores_the_saved_order_when_present() -> None:
    font, grouping = _make_font()
    _enable_with_our_order(font)
    font.userData[fontview.HAD_ORDER_KEY] = True
    font.userData[fontview.SAVED_ORDER_KEY] = ["B", "A"]
    grouping.disable(font)
    assert font.customParameters[fontview.GLYPH_ORDER] == ["B", "A"]


def test_disable_with_lost_saved_order_removes_the_parameter() -> None:
    # HAD_ORDER_KEY says the user had their own glyphOrder, but the saved
    # snapshot was lost: restoring [] would leave an empty ACTIVE parameter
    # overriding the font's natural order — remove the parameter instead.
    font, grouping = _make_font()
    _enable_with_our_order(font)
    font.userData[fontview.HAD_ORDER_KEY] = True
    font.userData[fontview.SAVED_ORDER_KEY] = None
    grouping.disable(font)
    assert font.customParameters[fontview.GLYPH_ORDER] is None


def test_strip_for_save_restores_the_saved_order_when_present() -> None:
    font, grouping = _make_font()
    _enable_with_our_order(font)
    font.userData[fontview.HAD_ORDER_KEY] = True
    font.userData[fontview.SAVED_ORDER_KEY] = ["B", "A"]
    assert grouping.strip_for_save(font) is True
    assert font.customParameters[fontview.GLYPH_ORDER] == ["B", "A"]


def test_strip_for_save_with_lost_saved_order_removes_the_parameter() -> None:
    # Same falsy-saved-order guard on the save path: never write an empty
    # active glyphOrder into the file.
    font, grouping = _make_font()
    _enable_with_our_order(font)
    font.userData[fontview.HAD_ORDER_KEY] = True
    font.userData[fontview.SAVED_ORDER_KEY] = ""
    assert grouping.strip_for_save(font) is True
    assert font.customParameters[fontview.GLYPH_ORDER] is None


def test_strip_for_save_never_touches_a_user_glyph_order() -> None:
    # The active glyphOrder is NOT ours (no header tag) -> leave it alone.
    font, grouping = _make_font()
    font.userData[fontview.ENABLED_KEY] = True
    font.customParameters[fontview.GLYPH_ORDER] = ["B", "A"]
    assert grouping.strip_for_save(font) is False
    assert font.customParameters[fontview.GLYPH_ORDER] == ["B", "A"]
