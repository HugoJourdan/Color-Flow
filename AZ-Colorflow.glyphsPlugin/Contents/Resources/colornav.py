"""Pure "jump to next unfinished glyph" navigation for Color Flow.

Glyphs-free so it can be unit-tested with plain CPython and embedded verbatim
into the jump keyboard-shortcut by ``tools/generate_shortcuts.py`` — the same
convention as ``colornames``. The palette and the shortcut therefore agree on
what "unfinished" and "next" mean.

A glyph is *finished* when its current-master ``layer.color`` equals the final
visible workflow step (see ``colornames.final_visible_step``). Uncoloured glyphs
(``None``) and glyphs at any other colour count as unfinished.
"""

from __future__ import annotations


def is_unfinished(color_key: int | None, final_step: str | None) -> bool:
    """True when a glyph's ``layer.color`` is not the final workflow step.

    ``final_step`` is an index string (e.g. ``"1"``) or ``None`` when the
    workflow has no visible steps, in which case nothing can be "finished".
    """
    if final_step is None:
        return True
    if color_key is None:
        return True
    return str(color_key) != final_step


def next_unfinished_index(
    glyphs: list[tuple[str, int | None]],
    final_step: str | None,
    position: int,
) -> int | None:
    """Index of the next unfinished glyph after ``position``, wrapping.

    ``glyphs`` is the font-order list of ``(glyph_name, layer_color)`` for the
    active master. ``position`` is the index of the current glyph (or ``-1`` for
    "no current glyph"); the scan starts at ``position + 1`` and wraps once
    through the whole list. Returns ``None`` when every glyph is finished or the
    list is empty.
    """
    total = len(glyphs)
    if total == 0:
        return None
    for offset in range(1, total + 1):
        candidate = (position + offset) % total
        _name, color_key = glyphs[candidate]
        if is_unfinished(color_key, final_step):
            return candidate
    return None
