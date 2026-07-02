"""Content + navigation logic for the first-run tutorial sheet.

The AppKit sheet that renders these slides lives in ``plugin.py`` (it needs Glyphs
and so can't be unit-tested); everything in this module is pure, so the slide data
and the navigation maths are fully testable.

The slides below are placeholder/fake content for now. They are deliberately shaped
as ``(title, body)`` pairs so they can later be generated from ``README.md`` without
touching the sheet code — only :func:`slides` would change.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Slide:
    """One tutorial page: a short ``title`` and a longer wrapping ``body``."""

    title: str
    body: str


# TODO: replace with content extracted from README.md. Fake content for testing.
PLACEHOLDER_SLIDES: tuple[Slide, ...] = (
    Slide(
        "Welcome to AZ Colorflow",
        "AZ Colorflow turns the colour labels you already use in Glyphs into a live "
        "picture of how far along your font is. This quick tour shows the basics — "
        "use the arrows to move between pages.",
    ),
    Slide(
        "Colour your glyphs",
        "Give each glyph (or layer) a colour label as you work: one colour per stage "
        "of your process, for example Drawn, Spaced, Kerned, Done. AZ Colorflow reads "
        "those labels — you don't have to change how you work.",
    ),
    Slide(
        "Read the palette",
        "The palette groups your glyphs by colour and shows how many are at each "
        "stage, so you can see at a glance what's finished and what still needs "
        "attention. Drag to reorder colours and double-click to rename a label.",
    ),
    Slide(
        "Generate a report",
        "Open the ⋯ menu and choose “Open Color Font Dashboard” for a shareable "
        "HTML snapshot of your progress. Keep the project in git (or turn on "
        "auto-commit) and the report also charts how your colours progressed over "
        "time. That's it — happy colouring!",
    ),
)


def slides() -> list[Slide]:
    """The ordered list of tutorial slides to display."""
    return list(PLACEHOLDER_SLIDES)


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
