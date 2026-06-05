"""Tests for the Color Font Dashboard.

The pure data + HTML layer is exercised directly. The GlyphsApp-touching
helpers (mode pref, colorNames.txt resolution, per-glyph map, snapshot
persistence) are covered with lightweight fakes + a temp colorNames.txt, so the
only thing left to manual testing is the real ``from GlyphsApp import ...`` line.
"""

from __future__ import annotations

from datetime import datetime

import colornames as cc
import colorflow_dashboard as db


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #

class _FakeLayers(dict):
    """Glyphs returns ``None`` for a master with no layer, not KeyError."""

    def __getitem__(self, key) -> object:
        return self.get(key)


class _FakeGlyph:
    def __init__(self, name: str, layers: dict) -> None:
        self.name = name
        self.layers = _FakeLayers(layers)


class _FakeMaster:
    def __init__(self, id_: str, name: str) -> None:
        self.id = id_
        self.name = name


class _FakeFont:
    versionMajor = 2
    versionMinor = 5

    def __init__(self, masters: list, glyphs: list | None = None,
                 filepath: str = "/fonts/Acme.glyphs", family: str = "Acme Sans") -> None:
        self.masters = masters
        self.glyphs = glyphs if glyphs is not None else []
        self.filepath = filepath
        self.familyName = family


class _Defaults(dict):
    """Mimics ``Glyphs.defaults``: a missing key reads back as ``None``."""

    def __getitem__(self, key) -> object:
        return self.get(key)


class _FakeGlyphsApp:
    def __init__(self) -> None:
        self.defaults = _Defaults()


# --------------------------------------------------------------------------- #
# color_to_key
# --------------------------------------------------------------------------- #

def test_color_to_key_maps_none_to_no_color_sentinel() -> None:
    assert db.color_to_key(None) == cc.NO_COLOR


def test_color_to_key_passes_real_colours_through_as_int() -> None:
    assert db.color_to_key(3) == 3
    assert db.color_to_key(0) == 0
    assert db.color_to_key(11) == 11


# --------------------------------------------------------------------------- #
# snapshot_to_colors / master_counts parity / uncolored_count
# --------------------------------------------------------------------------- #

def test_snapshot_to_colors_inverts_color_to_key() -> None:
    per_glyph = {"A": 0, "B": cc.NO_COLOR, "C": 3}
    assert db.snapshot_to_colors(per_glyph) == [0, None, 3]


# A non-numeric file order with a hidden (empty-label) colour — the exact shape
# that breaks if the counting order is taken from visible_labels instead of
# load_meaning. Locks the load-bearing parity invariant.
_HIDDEN_REORDERED = (
    "purple=Outline\n"
    "lightGreen=Anchors\n"
    "red=\n"            # known but hidden -> still a slot in the counting order
    "yellow=Ready\n"
)


def _order_from(text: str) -> list[str]:
    return list(cc.parse_color_names(text).keys())


def test_master_counts_matches_palette_step_mode() -> None:
    order = _order_from(_HIDDEN_REORDERED)  # ["8", "4", "0", "3"]
    colors = [8, 4, None, 3, 0, 8]
    assert db.master_counts(colors, order, is_free=False) == cc.counts_from_colors(colors, order)


def test_master_counts_matches_palette_free_mode() -> None:
    order = _order_from(_HIDDEN_REORDERED)
    colors = [8, 4, None, 3, 0, 8]
    assert db.master_counts(colors, order, is_free=True) == cc.single_counts_from_colors(colors, order)


def test_step_counts_are_cumulative_over_file_order() -> None:
    order = _order_from(_HIDDEN_REORDERED)  # ["8", "4", "0", "3"]
    # one glyph at yellow (the final step) credits every earlier step in order
    counts = db.master_counts([3], order, is_free=False)
    assert counts == {"8": 1, "4": 1, "0": 1, "3": 1}


def test_uncolored_count_counts_none_and_out_of_order_colours() -> None:
    order = _order_from(_HIDDEN_REORDERED)  # {"8","4","0","3"}
    # None -> uncoloured; 5 (darkGreen) is not in the order -> uncoloured; 8 is.
    assert db.uncolored_count([8, None, 5, 4], order) == 2


# --------------------------------------------------------------------------- #
# display_from_meaning / label_map / is_finished
# --------------------------------------------------------------------------- #

def test_display_from_meaning_keeps_visible_then_none_last() -> None:
    meaning = cc.parse_color_names(_HIDDEN_REORDERED)
    display = db.display_from_meaning(meaning, none_label="Nothing")
    assert display == [(8, "Outline"), (4, "Anchors"), (3, "Ready"), (cc.NO_COLOR, "Nothing")]


def test_display_from_meaning_falls_back_to_default_none_label() -> None:
    display = db.display_from_meaning({"0": "Red"}, none_label="")
    assert display[-1] == (cc.NO_COLOR, cc.DEFAULT_LABELS[cc.NO_COLOR])


# --------------------------------------------------------------------------- #
# compute_changes
# --------------------------------------------------------------------------- #

def test_compute_changes_reports_only_changed_glyphs() -> None:
    current = {"m1": {"A": 0, "B": 3, "C": cc.NO_COLOR}}
    previous = {"m1": {"A": 0, "B": 2, "C": cc.NO_COLOR}}
    assert db.compute_changes(current, previous) == {"m1": {"B": (2, 3)}}


def test_compute_changes_ignores_newly_added_glyphs() -> None:
    current = {"m1": {"A": 0, "NEW": 5}}
    previous = {"m1": {"A": 0}}
    assert db.compute_changes(current, previous) == {"m1": {}}


def test_compute_changes_handles_missing_master_in_previous() -> None:
    current = {"m1": {"A": 0}, "m2": {"A": 3}}
    previous = {"m1": {"A": 1}}
    assert db.compute_changes(current, previous) == {"m1": {"A": (1, 0)}, "m2": {}}


# --------------------------------------------------------------------------- #
# GlyphsApp-touching helpers (fakes)
# --------------------------------------------------------------------------- #

def test_build_master_glyph_colors_all_glyphs_layer_color_only() -> None:
    master = _FakeMaster("m1", "Regular")
    glyphs = [
        _FakeGlyph("A", {"m1": _FakeLayerColor(0)}),
        _FakeGlyph("B", {}),                       # no layer for m1 -> uncoloured
        _FakeGlyph("C", {"m1": _FakeLayerColor(3)}),
    ]
    font = _FakeFont([master], glyphs)
    assert db.build_master_glyph_colors(font) == {"m1": {"A": 0, "B": cc.NO_COLOR, "C": 3}}


def test_free_mode_reads_global_pref(monkeypatch) -> None:
    fake = _FakeGlyphsApp()
    fake.defaults[db.FREE_KEY] = True
    monkeypatch.setattr(db, "Glyphs", fake)
    assert db.free_mode() is True
    fake.defaults[db.FREE_KEY] = False
    assert db.free_mode() is False


def test_free_mode_defaults_to_step_without_glyphs(monkeypatch) -> None:
    monkeypatch.setattr(db, "Glyphs", None)
    assert db.free_mode() is False


def test_meaning_and_none_reads_font_dir_color_names(tmp_path) -> None:
    (tmp_path / "colorNames.txt").write_text(_HIDDEN_REORDERED + "None=Nothing\n",
                                             encoding="utf-8")
    font = _FakeFont([_FakeMaster("m1", "R")], filepath=str(tmp_path / "Font.glyphs"))
    meaning, none_label = db._meaning_and_none(font)
    assert list(meaning.keys()) == ["8", "4", "0", "3"]
    assert none_label == "Nothing"
    assert db.display_from_meaning(meaning, none_label)[-1] == (cc.NO_COLOR, "Nothing")


def test_snapshot_round_trip_through_defaults(monkeypatch) -> None:
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    assert db.load_snapshot(font) == {}            # nothing stored yet
    db.save_snapshot(font, {"m1": {"A": 0, "B": cc.NO_COLOR}})
    assert db.load_snapshot(font) == {"m1": {"A": 0, "B": cc.NO_COLOR}}


def test_coerce_snapshot_stringifies_and_ints() -> None:
    raw = {"m1": {"A": "0", "B": 3}}  # NSDictionary-ish: mixed value types
    assert db._coerce_snapshot(raw) == {"m1": {"A": 0, "B": 3}}
    assert db._coerce_snapshot(None) == {}


class _FakeLayerColor:
    def __init__(self, color: int | None) -> None:
        self.color = color


# --------------------------------------------------------------------------- #
# build_model
# --------------------------------------------------------------------------- #

def test_build_model_shape_and_compact_glyph_names(tmp_path) -> None:
    (tmp_path / "colorNames.txt").write_text(
        "purple=Outline\nlightGreen=Anchors\nyellow=Ready\nNone=Nothing\n", encoding="utf-8")
    master = _FakeMaster("m1", "Regular")
    glyphs = [
        _FakeGlyph("A", {"m1": _FakeLayerColor(8)}),
        _FakeGlyph("B", {"m1": _FakeLayerColor(4)}),
        _FakeGlyph("C", {}),  # no layer -> none
    ]
    font = _FakeFont([master], glyphs, filepath=str(tmp_path / "Font.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)

    assert model["family"] == "Acme Sans"
    assert model["fileName"] == "Font.glyphs"
    assert model["version"] == "2.5"
    assert model["generated"] == "2026-06-05"
    assert model["mode"] == "step"
    assert model["glyphTotal"] == 3
    assert model["order"] == ["8", "4", "3"]
    assert model["steps"] == [{"key": 8, "label": "Outline"},
                              {"key": 4, "label": "Anchors"},
                              {"key": 3, "label": "Ready"}]
    assert model["noneLabel"] == "Nothing"
    assert model["glyphNames"] == ["A", "B", "C"]          # stored once
    assert model["masters"][0]["keys"] == [8, 4, -1]        # parallel to glyphNames
    assert model["changes"] == {"m1": {}}


def test_build_model_counts_match_palette_step_and_free(tmp_path) -> None:
    (tmp_path / "colorNames.txt").write_text(_HIDDEN_REORDERED, encoding="utf-8")
    glyphs = [
        _FakeGlyph("A", {"m1": _FakeLayerColor(8)}),
        _FakeGlyph("B", {"m1": _FakeLayerColor(4)}),
        _FakeGlyph("C", {"m1": _FakeLayerColor(3)}),
        _FakeGlyph("D", {}),  # none
    ]
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs, filepath=str(tmp_path / "F.glyphs"))
    current = db.build_master_glyph_colors(font)
    order = list(cc.parse_color_names(_HIDDEN_REORDERED).keys())
    colors = [8, 4, 3, None]

    step = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert step["mode"] == "step"
    assert step["masters"][0]["counts"] == cc.counts_from_colors(colors, order)
    assert step["masters"][0]["uncolored"] == db.uncolored_count(colors, order)


def test_build_model_free_mode(monkeypatch, tmp_path) -> None:
    fake = _FakeGlyphsApp()
    fake.defaults[db.FREE_KEY] = True
    monkeypatch.setattr(db, "Glyphs", fake)
    (tmp_path / "colorNames.txt").write_text(_HIDDEN_REORDERED, encoding="utf-8")
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(8)}), _FakeGlyph("B", {"m1": _FakeLayerColor(4)})]
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs, filepath=str(tmp_path / "F.glyphs"))
    current = db.build_master_glyph_colors(font)
    order = list(cc.parse_color_names(_HIDDEN_REORDERED).keys())
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["mode"] == "free"
    assert model["masters"][0]["counts"] == cc.single_counts_from_colors([8, 4], order)


def test_build_model_multi_master_keys_align_to_glyph_names(tmp_path) -> None:
    (tmp_path / "colorNames.txt").write_text("purple=Outline\nyellow=Ready\n", encoding="utf-8")
    glyphs = [
        _FakeGlyph("A", {"m1": _FakeLayerColor(8), "m2": _FakeLayerColor(3)}),
        _FakeGlyph("B", {"m1": _FakeLayerColor(3), "m2": _FakeLayerColor(8)}),
    ]
    font = _FakeFont([_FakeMaster("m1", "Regular"), _FakeMaster("m2", "Bold")],
                     glyphs, filepath=str(tmp_path / "F.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)

    assert model["glyphNames"] == ["A", "B"]
    by_id = {m["id"]: m for m in model["masters"]}
    assert by_id["m1"]["keys"] == [8, 3]   # keys[i] aligns with glyphNames[i]
    assert by_id["m2"]["keys"] == [3, 8]
