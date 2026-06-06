"""Tests for the pure geometry/colour helpers of the SceneKit Color Tower.

Only the AppKit/SceneKit-free helpers are exercised here; the module imports
cleanly outside Glyphs (``_SCENEKIT_AVAILABLE`` is False) so these run anywhere."""

from __future__ import annotations

import colorflow_tower_scene as scene


def test_proportional_wedges_empty() -> None:
    assert scene.proportional_wedges([0] * 12) == []


def test_proportional_wedges_spans_full_circle_in_proportion() -> None:
    counts = [3, 0, 1] + [0] * 9          # total 4 -> 270 deg + 90 deg
    wedges = scene.proportional_wedges(counts)
    assert wedges == [(0.0, 270.0, 0), (270.0, 360.0, 2)]
    assert wedges[-1][1] == 360.0          # no gap at the wrap
    assert [w[2] for w in wedges] == [0, 2]  # only present slots


def test_hue_rgb_slot0_is_red_and_in_range() -> None:
    red, green, blue = scene.hue_rgb(0)
    assert red > 0.9 and green < 0.2 and blue < 0.2
    for channel in scene.hue_rgb(7):
        assert 0.0 <= channel <= 1.0


def test_average_rgb_neutral_when_uncolored() -> None:
    assert scene.average_rgb([0] * 12) == (0.78, 0.78, 0.80)


def test_average_rgb_single_slot_equals_its_hue() -> None:
    counts = [0, 0, 0, 5] + [0] * 8
    assert scene.average_rgb(counts) == scene.hue_rgb(3)


def test_average_rgb_channels_in_range() -> None:
    counts = [2, 1, 0, 3, 1, 0, 1, 0, 0, 0, 5, 2]
    for channel in scene.average_rgb(counts):
        assert 0.0 <= channel <= 1.0
