"""Tests for the pure data + HTML layer of the Color Font Dashboard.

The dashboard's GlyphsApp-touching code (snapshot persistence, building the
per-glyph map from a live font) is not exercised here; everything that decides
*what* the report says is pure and lives below.
"""

from datetime import datetime

import colornames as cc
import colorflow_dashboard as db


# --------------------------------------------------------------------------- #
# color_to_key / pct / hex_for
# --------------------------------------------------------------------------- #

def test_color_to_key_maps_none_to_no_color_sentinel():
    assert db.color_to_key(None) == cc.NO_COLOR


def test_color_to_key_passes_real_colours_through_as_int():
    assert db.color_to_key(3) == 3
    assert db.color_to_key(0) == 0
    assert db.color_to_key(11) == 11


def test_pct_rounds_and_guards_zero_total():
    assert db.pct(1, 4) == 25
    assert db.pct(3, 3) == 100
    assert db.pct(0, 0) == 0
    assert db.pct(5, 0) == 0


def test_hex_for_known_colour_and_hatch_fallback():
    assert db.hex_for(0) == "#f97e55"
    assert db.hex_for(cc.NO_COLOR) == db.HATCH
    assert db.hex_for(999) == db.HATCH  # unknown key -> hatch, never KeyError


# --------------------------------------------------------------------------- #
# counts_for_master
# --------------------------------------------------------------------------- #

def test_counts_for_master_counts_each_display_key():
    glyph_colors = {"A": 0, "B": 0, "C": 3, "D": cc.NO_COLOR}
    counts = db.counts_for_master(glyph_colors, [0, 3, cc.NO_COLOR])
    assert counts == {0: 2, 3: 1, cc.NO_COLOR: 1}


def test_counts_for_master_includes_zero_rows_for_unused_display_keys():
    counts = db.counts_for_master({"A": 0}, [0, 5, cc.NO_COLOR])
    assert counts == {0: 1, 5: 0, cc.NO_COLOR: 0}


def test_counts_for_master_ignores_colours_not_in_display_set():
    # 7 is used on a layer but hidden from the display set -> not counted.
    counts = db.counts_for_master({"A": 0, "B": 7}, [0, cc.NO_COLOR])
    assert counts == {0: 1, cc.NO_COLOR: 0}


# --------------------------------------------------------------------------- #
# compute_changes
# --------------------------------------------------------------------------- #

def test_compute_changes_reports_only_changed_glyphs():
    current = {"m1": {"A": 0, "B": 3, "C": cc.NO_COLOR}}
    previous = {"m1": {"A": 0, "B": 2, "C": cc.NO_COLOR}}
    assert db.compute_changes(current, previous) == {"m1": {"B": (2, 3)}}


def test_compute_changes_ignores_newly_added_glyphs():
    current = {"m1": {"A": 0, "NEW": 5}}
    previous = {"m1": {"A": 0}}
    assert db.compute_changes(current, previous) == {"m1": {}}


def test_compute_changes_handles_missing_master_in_previous():
    current = {"m1": {"A": 0}, "m2": {"A": 3}}
    previous = {"m1": {"A": 1}}
    assert db.compute_changes(current, previous) == {"m1": {"A": (1, 0)}, "m2": {}}


# --------------------------------------------------------------------------- #
# build_html (smoke, with a fake font)
# --------------------------------------------------------------------------- #

class _FakeMaster:
    def __init__(self, id_, name):
        self.id = id_
        self.name = name


class _FakeFont:
    familyName = "Acme Sans"
    filepath = "/fonts/Acme.glyphs"
    versionMajor = 2
    versionMinor = 5

    def __init__(self, masters):
        self.masters = masters


def test_build_html_renders_master_labels_and_percentages():
    font = _FakeFont([_FakeMaster("m1", "Regular")])
    display = [(0, "🚨 Red"), (cc.NO_COLOR, "🫥 None")]
    current = {"m1": {"A": 0, "B": cc.NO_COLOR}}
    html = db.build_html(font, 2, display, current, current, {"m1": {}}, datetime(2026, 6, 5))

    assert html.startswith("<!DOCTYPE html>")
    assert "Regular" in html
    assert "🚨 Red" in html
    assert "Acme Sans" in html
    assert "50%" in html          # 1 of 2 glyphs is Red
    assert "Labelled : <b>1/2</b>" in html


def test_build_html_escapes_glyph_names_in_change_report():
    font = _FakeFont([_FakeMaster("m1", "Regular")])
    display = [(0, "Red"), (cc.NO_COLOR, "None")]
    current = {"m1": {"a<b>": 0}}
    previous = {"m1": {"a<b>": cc.NO_COLOR}}
    changes = db.compute_changes(current, previous)
    html = db.build_html(font, 1, display, current, previous, changes, datetime(2026, 6, 5))

    assert "a&lt;b&gt;" in html      # escaped
    assert "<td>a<b></td>" not in html  # never raw
