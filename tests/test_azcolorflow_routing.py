"""Tests for the pure swap-color-routing decision logic (azcolorflow_routing)."""

from __future__ import annotations

import azcolorflow_routing as routing
import pytest


# -------------------------------------------------------------- resolve_color_target
@pytest.mark.parametrize(
    ("option_pressed", "swap_enabled", "expected"),
    [
        (False, False, "glyph"),
        (True, False, "layer"),
        (False, True, "layer"),
        (True, True, "glyph"),
    ],
)
def test_resolve_color_target_xor_truth_table(
    option_pressed: bool, swap_enabled: bool, expected: str
) -> None:
    assert routing.resolve_color_target(option_pressed, swap_enabled) == expected


# -------------------------------------------------------------- should_apply_swap
@pytest.mark.parametrize("event_type", sorted(routing.MOUSE_EVENT_TYPES))
def test_should_apply_swap_true_for_every_mouse_type(event_type: int) -> None:
    assert routing.should_apply_swap(event_type) is True


def test_should_apply_swap_covers_all_documented_mouse_types() -> None:
    # Guard the hard-coded raw values against silent drift from the NSEventType enum:
    # left/right/other mouse down+up.
    assert routing.MOUSE_EVENT_TYPES == frozenset({1, 2, 3, 4, 25, 26})


def test_should_apply_swap_false_for_non_mouse_type() -> None:
    # 10 == NSEventTypeKeyDown — a colour keyboard shortcut, not a click.
    assert routing.should_apply_swap(10) is False


def test_should_apply_swap_false_for_none() -> None:
    # No current event (programmatic caller).
    assert routing.should_apply_swap(None) is False


def test_should_apply_swap_honours_custom_mouse_type_set() -> None:
    assert routing.should_apply_swap(99, mouse_types=frozenset({99})) is True
    assert routing.should_apply_swap(1, mouse_types=frozenset({99})) is False
