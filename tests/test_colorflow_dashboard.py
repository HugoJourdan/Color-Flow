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
# color_to_key / pct / hex_for / var_for / xattr
# --------------------------------------------------------------------------- #

def test_color_to_key_maps_none_to_no_color_sentinel() -> None:
    assert db.color_to_key(None) == cc.NO_COLOR


def test_color_to_key_passes_real_colours_through_as_int() -> None:
    assert db.color_to_key(3) == 3
    assert db.color_to_key(0) == 0
    assert db.color_to_key(11) == 11


def test_pct_rounds_and_guards_zero_total() -> None:
    assert db.pct(1, 4) == 25
    assert db.pct(3, 3) == 100
    assert db.pct(0, 0) == 0
    assert db.pct(5, 0) == 0


def test_hex_for_known_colour_and_hatch_fallback() -> None:
    assert db.hex_for(0) == "#f97e55"
    assert db.hex_for(cc.NO_COLOR) == db.HATCH
    assert db.hex_for(999) == db.HATCH


def test_var_for_maps_keys_to_css_variables() -> None:
    assert db.var_for(0) == "--c0"
    assert db.var_for(11) == "--c11"
    assert db.var_for(cc.NO_COLOR) == "--c-none"


def test_xattr_escapes_quotes_and_angle_brackets() -> None:
    assert db.xattr('a"b') == "a&quot;b"
    assert db.xattr("a<b>&c") == "a&lt;b&gt;&amp;c"


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


def test_label_map_from_display() -> None:
    display = [(8, "Outline"), (cc.NO_COLOR, "None")]
    assert db.label_map_from_display(display) == {8: "Outline", cc.NO_COLOR: "None"}


def test_is_finished_step_mode_only_final_step() -> None:
    order = ["8", "4", "0", "3"]
    assert db.is_finished(3, order, is_free=False) is True   # final step
    assert db.is_finished(8, order, is_free=False) is False
    assert db.is_finished(cc.NO_COLOR, order, is_free=False) is False


def test_is_finished_free_mode_any_visible_colour() -> None:
    order = ["8", "4", "0", "3"]
    assert db.is_finished(8, order, is_free=True) is True
    assert db.is_finished(cc.NO_COLOR, order, is_free=True) is False
    assert db.is_finished(5, order, is_free=True) is False   # not in order


def test_is_finished_empty_order_never_finished() -> None:
    assert db.is_finished(0, [], is_free=False) is False


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
# build_overall_totals
# --------------------------------------------------------------------------- #

def test_build_overall_totals_step_mode_completion_and_started() -> None:
    order = ["0", "3"]
    display = [(0, "Red"), (3, "Yellow"), (cc.NO_COLOR, "None")]
    # master m1: one glyph at 3 (final), one uncoloured; total per master = 2.
    per_master = {"m1": (db.master_counts([3, None], order, False),
                         db.uncolored_count([3, None], order))}
    html = db.build_overall_totals(order, False, display, total=2, master_count=1,
                                   per_master=per_master)
    assert "Overall totals" in html
    assert "Complete : <b>1/2</b> (50%)" in html
    assert "Started : 1/2 (50%)" in html
    assert 'role="progressbar"' in html


def test_build_overall_totals_free_mode_headlines_labelled() -> None:
    order = ["0", "3"]
    display = [(0, "Red"), (3, "Yellow"), (cc.NO_COLOR, "None")]
    per_master = {"m1": (db.master_counts([0, 3], order, True),
                         db.uncolored_count([0, 3], order))}
    html = db.build_overall_totals(order, True, display, total=2, master_count=1,
                                   per_master=per_master)
    assert "Labelled across 1 master :" in html
    assert "<b>2/2</b> (100%)" in html


# --------------------------------------------------------------------------- #
# build_heatmap_section
# --------------------------------------------------------------------------- #

def test_heatmap_shows_only_unfinished_cells() -> None:
    order = ["0", "3"]
    label_map = {0: "Red", 3: "Yellow", cc.NO_COLOR: "None"}
    per_glyph = {"A": 3, "B": 0, "C": cc.NO_COLOR}  # A finished (final), B & C not
    html = db.build_heatmap_section("Regular", per_glyph, label_map, order, is_free=False)
    assert "2 unfinished" in html
    assert html.count('class="cell"') == 2


def test_heatmap_empty_when_all_finished() -> None:
    order = ["0"]
    per_glyph = {"A": 0, "B": 0}
    assert db.build_heatmap_section("Regular", per_glyph, {0: "Red"}, order, False) == ""


def test_heatmap_caps_cells_and_reports_remainder() -> None:
    order = ["0"]
    per_glyph = {f"g{i}": cc.NO_COLOR for i in range(7)}
    html = db.build_heatmap_section("Regular", per_glyph, {cc.NO_COLOR: "None"}, order,
                                    is_free=False, cap=5)
    assert html.count('class="cell"') == 5
    assert "+2 more" in html


def test_heatmap_escapes_glyph_name_in_attribute() -> None:
    order = ["0"]
    html = db.build_heatmap_section("Reg", {'a"b': cc.NO_COLOR}, {cc.NO_COLOR: "None"},
                                    order, is_free=False)
    assert "a&quot;b" in html
    assert 'a"b —' not in html  # the raw quote never lands in the title


# --------------------------------------------------------------------------- #
# build_html (smoke + a11y + theming + escaping)
# --------------------------------------------------------------------------- #

def _one_master_font() -> _FakeFont:
    return _FakeFont([_FakeMaster("m1", "Regular")])


def test_build_html_renders_overall_master_and_percentages() -> None:
    font = _one_master_font()
    order = ["0"]
    display = [(0, "🚨 Red"), (cc.NO_COLOR, "🫥 None")]
    current = {"m1": {"A": 0, "B": cc.NO_COLOR}}
    html = db.build_html(font, 2, order, False, display, current, current,
                         {"m1": {}}, datetime(2026, 6, 5))

    assert html.startswith("<!DOCTYPE html>")
    assert 'lang="en"' in html
    assert "Overall totals" in html
    assert "Regular" in html
    assert "🚨 Red" in html
    assert "Acme Sans" in html
    assert "50%" in html  # 1 of 2 glyphs is Red


def test_build_html_includes_accessibility_and_both_themes() -> None:
    font = _one_master_font()
    html = db.build_html(font, 1, ["0"], False, [(0, "Red"), (cc.NO_COLOR, "None")],
                         {"m1": {"A": 0}}, {"m1": {"A": 0}}, {"m1": {}},
                         datetime(2026, 6, 5))
    assert 'role="progressbar"' in html
    assert 'scope="col"' in html
    assert 'scope="row"' in html
    assert ":root{" in html
    assert "prefers-color-scheme:light" in html
    assert "prefers-reduced-motion:reduce" in html


def test_build_html_escapes_glyph_names_in_change_report() -> None:
    font = _one_master_font()
    display = [(0, "Red"), (cc.NO_COLOR, "None")]
    current = {"m1": {"a<b>": 0}}
    previous = {"m1": {"a<b>": cc.NO_COLOR}}
    changes = db.compute_changes(current, previous)
    html = db.build_html(font, 1, ["0"], False, display, current, previous, changes,
                         datetime(2026, 6, 5))
    assert "a&lt;b&gt;" in html
    assert "<th scope=\"row\">a<b></th>" not in html  # never raw


def test_build_html_free_mode_sidebar_label() -> None:
    font = _one_master_font()
    html = db.build_html(font, 1, ["0"], True, [(0, "Red"), (cc.NO_COLOR, "None")],
                         {"m1": {"A": 0}}, {"m1": {"A": 0}}, {"m1": {}},
                         datetime(2026, 6, 5))
    assert "Mode : Free" in html


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
    assert db.display_colors(font)[-1] == (cc.NO_COLOR, "Nothing")


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
