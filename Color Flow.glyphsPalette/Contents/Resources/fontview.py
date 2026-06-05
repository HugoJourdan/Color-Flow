# encoding: utf-8
"""Font-View grouping engine for Color Flow (ported from Rainbow FontView).

Groups the Font View into labelled colour sections by rewriting the font's
``glyphOrder`` custom parameter. Non-destructive: the original glyphOrder is
snapshotted on enable and restored on disable.

This module is free of any AppKit/menu/timer code — the palette plugin owns the
UPDATEINTERFACE debounce and the menu item, and simply calls into this engine.
It operates on the GSFont passed to it; the only Glyphs dependency at import time
is the sibling ``colornames`` module (pure Python), so it stays importable for
tests. Rainbow's userData/tempData keys are kept verbatim so a font already
grouped by the standalone Rainbow FontView stays consistent after the merge.
"""

from __future__ import annotations

import contextlib
import os

import colornames

# Persistent state (saved in the .glyphs file via userData) — kept compatible
# with the standalone Rainbow FontView plugin.
ENABLED_KEY = "hugojourdan.RainbowFontView.enabled"
SAVED_ORDER_KEY = "hugojourdan.RainbowFontView.savedGlyphOrder"
HAD_ORDER_KEY = "hugojourdan.RainbowFontView.hadGlyphOrder"
MODE_KEY = "hugojourdan.RainbowFontView.labelUsed"  # "Layer" | "Glyph"

# Volatile cache (font.tempData; not saved).
SNAPSHOT_KEY = "colorFlowRainbowSnapshot"
MASTER_KEY = "colorFlowRainbowMaster"

GLYPH_ORDER = "glyphOrder"
HEADER = "#Color Flow Rainbow"


class FontViewGrouping:
    """Owns the colour-section grouping for one running palette instance."""

    def __init__(self) -> None:
        self._meaning: dict[int, str] = {}
        self._order: list[int] = []

    # ----------------------------------------------------------- key file
    def load(self, font) -> None:
        """Re-read colorNames.txt so live edits to the labels/order take effect."""
        font_dir = None
        if font is not None and font.filepath:
            font_dir = os.path.dirname(font.filepath)
        path = colornames.resolve_key_file(font_dir)
        text = colornames.read_color_names(path) or colornames.DEFAULT_COLOR_NAMES
        meaning, order, _ = colornames.parse_key_file(text)
        self._meaning = meaning
        self._order = order

    # ----------------------------------------------------------- state
    def is_enabled(self, font) -> bool:
        return bool(font.userData[ENABLED_KEY])

    def mode(self, font) -> str:
        mode = font.userData[MODE_KEY]
        return mode if mode in ("Layer", "Glyph") else "Layer"

    def set_mode(self, font, mode: str) -> None:
        font.userData[MODE_KEY] = mode if mode in ("Layer", "Glyph") else "Layer"
        if self.is_enabled(font):
            self._clear(font.tempData, SNAPSHOT_KEY)
            self.rebuild(font)

    # ----------------------------------------------------------- enable/disable
    def toggle(self, font) -> None:
        if self.is_enabled(font):
            self.disable(font)
        else:
            self.enable(font)

    def enable(self, font) -> None:
        self.load(font)
        existing = font.customParameters[GLYPH_ORDER]
        if existing is not None:
            # Snapshot any existing glyphOrder so disable can restore it.
            font.userData[SAVED_ORDER_KEY] = (
                existing if isinstance(existing, str) else list(existing)
            )
            font.userData[HAD_ORDER_KEY] = True
        else:
            font.userData[HAD_ORDER_KEY] = False
        font.userData[ENABLED_KEY] = True
        self.rebuild(font)

    def disable(self, font) -> None:
        font.userData[ENABLED_KEY] = False
        if bool(font.userData[HAD_ORDER_KEY]):
            saved = font.userData[SAVED_ORDER_KEY]
            font.customParameters[GLYPH_ORDER] = saved if saved else []
        else:
            self._remove_glyph_order(font)
        self._clear(font.userData, SAVED_ORDER_KEY)
        self._clear(font.userData, HAD_ORDER_KEY)
        self._clear(font.tempData, SNAPSHOT_KEY)
        self._clear(font.tempData, MASTER_KEY)

    # ----------------------------------------------------------- rebuild
    def rebuild(self, font) -> None:
        """Recompute the glyphOrder parameter from current colours."""
        master_id = self._master_id(font)
        if master_id is None:
            return
        mode = self.mode(font)
        snapshot: dict[str, int] = {}
        glyph_colors: list[tuple[str, int | None]] = []
        for glyph in font.glyphs:
            color = glyph.color if mode == "Glyph" else self._layer_color(glyph, master_id)
            glyph_colors.append((glyph.name, color))
            snapshot[glyph.name] = colornames.NO_COLOR if color is None else color
        code = colornames.build_glyph_order(
            glyph_colors, self._meaning, self._order, header=f"{HEADER} ({mode})"
        )
        font.customParameters[GLYPH_ORDER] = code
        self._force_refresh(font)
        font.tempData[SNAPSHOT_KEY] = snapshot
        font.tempData[MASTER_KEY] = master_id

    def maybe_rebuild(self, font) -> None:
        """Re-read the key file then rebuild (called from the debounced timer)."""
        self.load(font)
        self.rebuild(font)

    # --------------------------------------------------- keep our order out of saves
    def _is_color_flow_order(self, value) -> bool:
        """True only for a glyphOrder value WE wrote (tagged with our header), so
        we never disturb a glyphOrder the user set themselves."""
        try:
            return bool(value) and not isinstance(value, str) and str(value[0]).startswith(HEADER)
        except Exception:
            return False

    def strip_for_save(self, font) -> bool:
        """Before a save: if our grouping order is the active glyphOrder, swap it
        back to the user's own order (or remove it) so it is not written to the
        file. Returns True if it changed anything (caller restores afterwards).
        Never touches a glyphOrder that isn't ours."""
        if font is None or not self.is_enabled(font):
            return False
        if not self._is_color_flow_order(font.customParameters[GLYPH_ORDER]):
            return False  # the active glyphOrder is the user's — leave it alone
        if bool(font.userData[HAD_ORDER_KEY]):
            saved = font.userData[SAVED_ORDER_KEY]
            font.customParameters[GLYPH_ORDER] = saved if saved else []
        else:
            self._remove_glyph_order(font)
        return True

    def restore_after_save(self, font) -> None:
        """After a save: re-apply our grouping order in memory."""
        if font is not None and self.is_enabled(font):
            self.rebuild(font)

    # ----------------------------------------------------------- dirty check
    def is_dirty(self, font) -> bool:
        """Cheap O(selection) test for whether a rebuild is warranted."""
        snapshot = font.tempData[SNAPSHOT_KEY]
        if snapshot is None:
            return True
        master_id = self._master_id(font)
        if master_id is None:
            return False
        if font.tempData[MASTER_KEY] != master_id:
            return True
        mode = self.mode(font)
        for layer in font.selectedLayers or []:
            glyph = layer.parent
            if glyph is None:
                continue
            color = glyph.color if mode == "Glyph" else self._layer_color(glyph, master_id)
            normalised = colornames.NO_COLOR if color is None else color
            if snapshot.get(glyph.name) != normalised:
                return True
        return False

    # ----------------------------------------------------------- helpers
    def _master_id(self, font):
        master = font.selectedFontMaster if font.parent is not None else None
        if master is None:
            master = font.masters[0] if font.masters else None
        return master.id if master is not None else None

    def _layer_color(self, glyph, master_id):
        layer = glyph.layers[master_id]
        return layer.color if layer is not None else None

    def _glyph_order_param(self, font):
        for param in font.customParameters:
            if param.name == GLYPH_ORDER:
                return param
        return None

    def _force_refresh(self, font) -> None:
        """Toggle the parameter off/on to force Font View to re-read the order."""
        param = self._glyph_order_param(font)
        if param is None:
            return
        param.active = False
        param.active = True

    def _remove_glyph_order(self, font) -> None:
        try:
            del font.customParameters[GLYPH_ORDER]
        except Exception:
            param = self._glyph_order_param(font)
            if param is not None:
                param.active = False

    def _clear(self, proxy, key) -> None:
        with contextlib.suppress(KeyError, TypeError):
            del proxy[key]
