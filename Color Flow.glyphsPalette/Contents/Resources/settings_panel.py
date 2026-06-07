"""Vanilla Settings panel for Color Flow.

Lets the user reorder the colours and choose which ones show in the palette
(e.g. keep only Red / Magenta / Blue), plus the Rainbow Font-View colour source.
Order + visibility persist to colorNames.txt (visible = ``name=label``, hidden =
``#name=label`` so the label is remembered). Labels themselves are edited by
double-clicking in the palette.

Imported lazily from plugin.py (vanilla only exists inside Glyphs' interpreter).
"""

import os
from typing import Any, Optional

import colornames
from vanilla import Button, CheckBox, HorizontalLine, RadioGroup, TextBox, Window

try:
    from GlyphsApp import Glyphs, Message
except Exception:  # pragma: no cover - only importable inside Glyphs
    Glyphs = None
    def Message(*args: Any, **kwargs: Any) -> None:
        pass

MODE_KEY = "hugojourdan.RainbowFontView.labelUsed"
FREE_KEY = "com.hugojourdan.ColorFlow-FreeMode"
MODES = ("Layer", "Glyph")

MARGIN = 15
ROW_HEIGHT = 26
TOP = 84  # first colour row sits below the source radio, free-mode box + separator


class ColorFlowSettings:
    """A small window editing colour order + visibility for the active font."""

    def __init__(self, plugin: Any, font: Any) -> None:
        self.plugin = plugin
        self.font = font
        rows, self.none_label = colornames.parse_settings(self._read_key_file())
        # [index, label, visible], mutable so reorder/toggle callbacks can edit in place
        self.rows: list[list[Any]] = [list(row) for row in rows]
        self._checks: dict[int, CheckBox] = {}
        self._names: dict[int, TextBox] = {}
        self._build()

    # ------------------------------------------------------------------ data
    def _read_key_file(self) -> str:
        font_dir = None
        if self.font is not None and self.font.filepath:
            font_dir = os.path.dirname(self.font.filepath)
        path = colornames.resolve_key_file(font_dir)
        return colornames.read_color_names(path) or colornames.DEFAULT_COLOR_NAMES

    def _row_text(self, index: int, label: str) -> str:
        return label or colornames.DEFAULT_LABELS.get(index, str(index))

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        width = 300
        height = TOP + len(self.rows) * ROW_HEIGHT + 18 + MARGIN
        self.w = Window((width, height), "Color Flow Settings")

        y = MARGIN
        self.w.sourceLabel = TextBox((MARGIN, y + 2, 130, 20), "Rainbow source:")
        current = self.font.userData[MODE_KEY] if self.font is not None else "Layer"
        current = current if current in MODES else "Layer"
        self.w.source = RadioGroup(
            (135, y, -MARGIN, 20), ["Layer color", "Glyph color"], isVertical=False
        )
        self.w.source.set(MODES.index(current))
        y += 28
        free = bool(Glyphs.defaults[FREE_KEY]) if Glyphs is not None else False
        self.w.freeMode = CheckBox((MARGIN, y, -MARGIN, 20),
                                   "Free mode (independent steps)", value=free)
        y += 26
        self.w.separator = HorizontalLine((MARGIN, y, -MARGIN, 1))

        for position in range(len(self.rows)):
            index, label, visible = self.rows[position]
            rowY = TOP + position * ROW_HEIGHT
            check = CheckBox((MARGIN, rowY, 22, 20), "", value=visible,
                             callback=self._toggle_visible)
            up = Button((MARGIN + 24, rowY, 26, 20), "↑", callback=self._move_up)
            down = Button((MARGIN + 52, rowY, 26, 20), "↓", callback=self._move_down)
            name = TextBox((MARGIN + 86, rowY + 2, -MARGIN, 18),
                           self._row_text(index, label))
            for widget in (check, up, down):
                widget._cf_row = position
            setattr(self.w, f"check{position}", check)
            setattr(self.w, f"up{position}", up)
            setattr(self.w, f"down{position}", down)
            setattr(self.w, f"name{position}", name)
            self._checks[position] = check
            self._names[position] = name

        self.w.reset = Button((MARGIN, -MARGIN - 22, 110, 22), "Reset defaults",
                              callback=self._reset)
        self.w.cancel = Button((-185, -MARGIN - 22, 80, 22), "Cancel",
                               callback=self._cancel)
        self.w.save = Button((-95, -MARGIN - 22, 80, 22), "Save", callback=self._save)
        self.w.setDefaultButton(self.w.save)
        self.w.open()

    # ------------------------------------------------------------------ helpers
    def _row_of(self, sender: Any) -> Optional[int]:
        return getattr(sender, "_cf_row", None)

    def _refresh(self) -> None:
        for position in range(len(self.rows)):
            index, label, visible = self.rows[position]
            self._checks[position].set(visible)
            self._names[position].set(self._row_text(index, label))

    # ------------------------------------------------------------------ callbacks
    def _toggle_visible(self, sender: Any) -> None:
        position = self._row_of(sender)
        if position is not None:
            self.rows[position][2] = bool(sender.get())

    def _move_up(self, sender: Any) -> None:
        position = self._row_of(sender)
        if position is not None and position > 0:
            self.rows[position - 1], self.rows[position] = (
                self.rows[position], self.rows[position - 1])
            self._refresh()

    def _move_down(self, sender: Any) -> None:
        position = self._row_of(sender)
        if position is not None and position < len(self.rows) - 1:
            self.rows[position + 1], self.rows[position] = (
                self.rows[position], self.rows[position + 1])
            self._refresh()

    def _reset(self, sender: Any) -> None:
        rows, self.none_label = colornames.parse_settings(colornames.DEFAULT_COLOR_NAMES)
        self.rows = [list(row) for row in rows]
        self._refresh()

    def _cancel(self, sender: Any) -> None:
        self.w.close()

    def _save(self, sender: Any) -> None:
        rows: list[tuple[int, str, bool]] = [
            (int(index), str(label), bool(visible))
            for index, label, visible in self.rows
        ]
        text = colornames.render_settings(rows, self.none_label)
        font_dir = None
        if self.font is not None and self.font.filepath:
            font_dir = os.path.dirname(self.font.filepath)
        path = colornames.resolve_key_file(font_dir)
        if not colornames.write_color_names(path, text):
            Message(f"Could not write colorNames.txt:\n{path}",
                    title="Color Flow", OKButton=None)
            return
        if self.font is not None:
            self.font.userData[MODE_KEY] = MODES[self.w.source.get()]
        if Glyphs is not None:
            Glyphs.defaults[FREE_KEY] = bool(self.w.freeMode.get())
        self.w.close()
        try:
            self.plugin.reload_after_settings()
        except Exception:
            pass
