"""Tests for the pure first-run tutorial content + navigation logic.

The AppKit sheet that displays these slides lives in plugin.py and is manual-smoke
only; here we exercise the slide data and the navigation maths the sheet drives.
"""

from __future__ import annotations

import azcolorflow_tutorial as tut


def test_slides_are_nonempty_with_title_and_body() -> None:
    items = tut.slides()
    assert items, "at least one slide must ship"
    for slide in items:
        assert slide.title.strip()
        assert slide.body.strip()


def test_slides_returns_a_fresh_list() -> None:
    # callers can mutate the returned list without corrupting the shared content
    first = tut.slides()
    first.append(tut.Slide("x", "y"))
    assert len(tut.slides()) == len(tut.PLACEHOLDER_SLIDES)


def test_clamp_index_constrains_to_bounds() -> None:
    assert tut.clamp_index(-3, 4) == 0
    assert tut.clamp_index(0, 4) == 0
    assert tut.clamp_index(2, 4) == 2
    assert tut.clamp_index(9, 4) == 3
    assert tut.clamp_index(1, 0) == 0          # no slides -> 0


def test_is_first_and_is_last() -> None:
    assert tut.is_first(0) is True
    assert tut.is_first(1) is False
    assert tut.is_last(3, 4) is True
    assert tut.is_last(2, 4) is False
    assert tut.is_last(0, 0) is False          # no slides -> never "last"


def test_page_indicator_marks_current_slide() -> None:
    assert tut.page_indicator(0, 4) == "● ○ ○ ○"
    assert tut.page_indicator(2, 4) == "○ ○ ● ○"
    assert tut.page_indicator(0, 1) == "●"
    assert tut.page_indicator(0, 0) == ""
