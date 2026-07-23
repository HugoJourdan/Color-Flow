"""Content + navigation logic for the first-run tutorial sheet.

The AppKit sheet that renders these slides lives in ``plugin.py`` (it needs Glyphs
and so can't be unit-tested); everything in this module is pure, so the slide data
and the navigation maths are fully testable.

Slides are plain ``(title, body)`` pairs; the sheet code only ever calls
:func:`slides`, so the content can be edited (or regenerated) without touching it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Slide:
    """One tutorial page: a short ``title`` and a longer wrapping ``body``."""

    title: str
    body: str


SLIDES: tuple[Slide, ...] = (
    Slide(
        "What AZ Colorflow does",
        "AZ Colorflow turns Glyphs' twelve colour labels into named workflow steps, "
        "so a layer's colour says exactly how far each glyph has come. The palette "
        "lists your steps with a live glyph count per step and highlights every step "
        "the selected glyphs have already reached.",
    ),
    Slide(
        "Make the steps yours",
        "Steps are defined in colorNames.txt — a copy next to the .glyphs file wins, "
        "otherwise the shared file in the Glyphs folder is used. Edit everything in "
        "Glyphs → Settings → AZ Colorflow: double-click a name to rename, click the "
        "swatch to recolour, the eye to show or hide, and drag rows to reorder.",
    ),
    Slide(
        "Work faster",
        "Right-click a selection and pick a step from the AZ Colorflow menu to "
        "colour it, or double-click a palette row to open exactly that step's glyphs "
        "in a new Edit tab. Assign a key to “Jump to next color glyph” in Glyphs → "
        "Settings → Shortcuts to step through unfinished glyphs.",
    ),
    Slide(
        "Track your progress",
        "Collapse the palette for a colour progress bar in its header; expand it and "
        "the header's report button builds the Color Font Dashboard — per-master "
        "progress, a per-glyph heatmap and a save-by-save timeline (git-tracked "
        "fonts read their history from commits). File → “AZ Colorflow: Font Glyph "
        "Order” groups the Font View by colour.",
    ),
)


def slides() -> list[Slide]:
    """The ordered list of tutorial slides to display."""
    return list(SLIDES)


def clamp_index(index: int, count: int) -> int:
    """``index`` constrained to ``[0, count - 1]`` (``0`` when there are no slides)."""
    if count <= 0:
        return 0
    return max(0, min(index, count - 1))


def is_first(index: int) -> bool:
    """Whether ``index`` is the first slide (so the Back arrow should be disabled)."""
    return index <= 0


def is_last(index: int, count: int) -> bool:
    """Whether ``index`` is the last slide (so Next becomes the Done button)."""
    return count > 0 and index >= count - 1


def page_indicator(index: int, count: int) -> str:
    """A simple dotted page indicator: a filled dot for the current slide, hollow
    dots for the rest (e.g. ``"● ○ ○ ○"``)."""
    return " ".join("●" if position == index else "○" for position in range(count))
