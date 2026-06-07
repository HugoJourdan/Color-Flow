"""Tests for the pure jump-to-next-unfinished navigation helper."""

from __future__ import annotations

import colornav


def test_next_unfinished_finds_following_glyph() -> None:
    glyphs = [("A", 1), ("B", None), ("C", 1)]   # final step = "1"
    assert colornav.next_unfinished_index(glyphs, "1", 0) == 1


def test_next_unfinished_wraps_around_to_earlier_glyph() -> None:
    glyphs = [("A", None), ("B", 1), ("C", 1)]   # only A is unfinished
    assert colornav.next_unfinished_index(glyphs, "1", 1) == 0


def test_next_unfinished_skips_final_step_glyphs() -> None:
    glyphs = [("A", 1), ("B", 1), ("C", 1)]      # all finished
    assert colornav.next_unfinished_index(glyphs, "1", 0) is None


def test_next_unfinished_treats_uncoloured_and_offpalette_as_unfinished() -> None:
    glyphs = [("A", 1), ("B", None), ("C", 7)]   # B uncoloured, C wrong colour
    assert colornav.next_unfinished_index(glyphs, "1", 0) == 1
    assert colornav.next_unfinished_index(glyphs, "1", 1) == 2


def test_next_unfinished_with_no_final_step_returns_first_after_position() -> None:
    # final_step None (no visible steps): every glyph counts as unfinished
    glyphs = [("A", 1), ("B", 2), ("C", 3)]
    assert colornav.next_unfinished_index(glyphs, None, 0) == 1


def test_next_unfinished_empty_list_returns_none() -> None:
    assert colornav.next_unfinished_index([], "1", 0) is None


def test_next_unfinished_start_position_minus_one_scans_from_top() -> None:
    # -1 means "no current glyph" -> first unfinished is the first non-final one
    glyphs = [("A", 1), ("B", None), ("C", 1)]
    assert colornav.next_unfinished_index(glyphs, "1", -1) == 1
