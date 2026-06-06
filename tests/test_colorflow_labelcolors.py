"""Tests for the pure parts of the label-colour reader/writer.

The NSArchiver/NSUnarchiver + Glyphs.defaults paths only run inside Glyphs; here
we cover the hex conversion and the no-Glyphs fallbacks.
"""

from __future__ import annotations

import labelcolors as lc


def test_defaults_are_twelve_rgba_tuples() -> None:
    assert len(lc.DEFAULTS) == 12
    assert all(len(rgba) == 4 for rgba in lc.DEFAULTS)


def test_hex_for_converts_and_ignores_alpha() -> None:
    assert lc.hex_for((1.0, 0.0, 0.0, 1.0)) == "#ff0000"
    assert lc.hex_for((0.0, 0.0, 0.0)) == "#000000"
    assert lc.hex_for((1.0, 1.0, 1.0, 0.3)) == "#ffffff"  # alpha ignored


def test_hex_for_clamps_out_of_range() -> None:
    assert lc.hex_for((-1.0, 2.0, 0.5, 1.0)) == "#00ff80"


def test_read_label_colors_falls_back_to_defaults_without_glyphs(monkeypatch) -> None:
    monkeypatch.setattr(lc, "Glyphs", None)
    assert lc.read_label_colors() == lc.DEFAULTS


def test_hex_list_matches_defaults_without_glyphs(monkeypatch) -> None:
    monkeypatch.setattr(lc, "Glyphs", None)
    assert lc.hex_list() == [lc.hex_for(rgba) for rgba in lc.DEFAULTS]


def test_write_and_reset_are_no_ops_without_glyphs(monkeypatch) -> None:
    monkeypatch.setattr(lc, "Glyphs", None)
    assert lc.write_label_colors(lc.DEFAULTS) is False
    lc.reset_label_colors()  # must not raise
