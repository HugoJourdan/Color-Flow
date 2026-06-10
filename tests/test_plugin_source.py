"""Source-level assertions on ``plugin.py``.

The plugin module itself cannot be imported outside Glyphs (it pulls in
GlyphsApp/AppKit at import time), so these tests assert structural properties
of its source text instead — mirroring how the asset tests source-assert the
inline JS/CSS strings.
"""

from __future__ import annotations

from pathlib import Path

RESOURCES = (
    Path(__file__).resolve().parent.parent
    / "Color Flow.glyphsPalette"
    / "Contents"
    / "Resources"
)

PLUGIN_SOURCE = (RESOURCES / "plugin.py").read_text(encoding="utf-8")


def _method_body(name: str) -> str:
    """Return the source of method ``name`` (up to the next method def)."""
    start = PLUGIN_SOURCE.index(f"def {name}(")
    end = PLUGIN_SOURCE.index("\n\tdef ", start)
    return PLUGIN_SOURCE[start:end]


def _module_function_body(name: str) -> str:
    """Return the source of module-level function ``name`` (up to the next
    top-level def/class)."""
    start = PLUGIN_SOURCE.index(f"\ndef {name}(") + 1
    next_def = PLUGIN_SOURCE.find("\ndef ", start)
    next_class = PLUGIN_SOURCE.find("\nclass ", start)
    candidates = [position for position in (next_def, next_class) if position != -1]
    return PLUGIN_SOURCE[start : min(candidates)] if candidates else PLUGIN_SOURCE[start:]


def _palette_start_body() -> str:
    """Return the source of ``ColorFlow.start`` (the loader-bar class has its
    own ``start``, so scan from the palette class definition)."""
    class_start = PLUGIN_SOURCE.index("class ColorFlow(PalettePlugin):")
    start = PLUGIN_SOURCE.index("def start(", class_start)
    end = PLUGIN_SOURCE.index("\n\tdef ", start)
    return PLUGIN_SOURCE[start:end]


def _validate_menu_item_body() -> str:
    """Return the source of ``validateMenuItem_`` (up to the next method def)."""
    return _method_body("validateMenuItem_")


def test_validate_menu_item_branches_on_action_selector() -> None:
    body = _validate_menu_item_body()
    # Must inspect the menu item's action selector, not stamp every item.
    assert "menuItem.action()" in body
    assert '"toggleRainbow:"' in body
    # Non-rainbow items bail out BEFORE any setState_ call, so the Rainbow
    # checkmark never leaks onto settings / backfill / context-menu items.
    branch = body.index('!= "toggleRainbow:"')
    first_set_state = body.index("setState_")
    assert branch < first_set_state


def test_validate_menu_item_keeps_settings_enabled_without_font() -> None:
    body = _validate_menu_item_body()
    settings_branch = body.index('"openSettings:"')
    settings_tail = body[settings_branch:body.index("\n", body.index("return", settings_branch))]
    assert "return True" in settings_tail
    # Settings is enabled unconditionally — no setState_ between the action
    # check and its return.
    assert "setState_" not in settings_tail


def test_validate_menu_item_rainbow_disabled_without_font() -> None:
    body = _validate_menu_item_body()
    # Original semantics preserved for the Rainbow toggle: with no font the
    # item is unchecked and disabled.
    no_font = body.index("if font is None:")
    tail = body[no_font:]
    assert "menuItem.setState_(NSOffState)" in tail
    assert "return False" in tail
    assert "NSOnState if self.fontview.is_enabled(font) else NSOffState" in tail


def test_single_click_row_focus_removed() -> None:
    # Single-click row focus is gone: no handler, no gesture wiring.
    assert "def rowClicked_(" not in PLUGIN_SOURCE
    assert '"rowClicked:"' not in PLUGIN_SOURCE


def test_double_click_row_opens_step_tab() -> None:
    body = _method_body("rowDoubleClicked_")
    # Double-click on a row opens exactly that step's glyphs in a new Edit tab.
    assert "_open_step_tab" in body
    assert "_color_for_recognizer" in body


def test_double_click_wired_with_two_clicks_alongside_pan() -> None:
    body = _method_body("_attach_row_overlay")
    # The overlay carries BOTH recognizers: a two-click NSClickGestureRecognizer
    # for open-tab and the pan recognizer for drag-reorder.
    assert '"rowDoubleClicked:"' in body
    assert "setNumberOfClicksRequired_(2)" in body
    assert '"colorDragged:"' in body
    assert "setNumberOfClicksRequired_(1)" not in body


def test_double_click_keeps_drag_suppression_guard() -> None:
    body = _method_body("rowDoubleClicked_")
    # End-of-drag clicks must still be swallowed by the _lastDragTime guard
    # BEFORE any tab opens.
    assert "_lastDragTime" in body
    guard = body.index("_lastDragTime")
    open_tab = body.index("_open_step_tab")
    assert guard < open_tab


def test_count_badge_is_passive() -> None:
    # The count badge no longer opens tabs: handler, wiring and the badge
    # registry that resolved a recognizer back to its colour are all gone.
    assert "countClicked_" not in PLUGIN_SOURCE
    assert '"countClicked:"' not in PLUGIN_SOURCE
    assert "_color_for_count" not in PLUGIN_SOURCE
    assert "_countBoxes" not in PLUGIN_SOURCE


def test_step_tab_membership_matches_exact_badge_count() -> None:
    body = _method_body("_glyphs_for_step")
    # The badge shows the exact census, so the tab it opens holds exactly those
    # glyphs: layers with EXACTLY this colour, non-exporting glyphs excluded —
    # not the cumulative "reached this step or beyond" set.
    assert "self._excluded_glyph_names()" in body
    assert "str(layerColor) == str(color)" in body
    assert "_layer_state" not in body


def test_focus_mode_machinery_removed() -> None:
    # With no setter left the focus/dim machinery is dead — state, Escape path
    # and the Update_Plugin_UI dimming branch are all gone.
    assert "_focusColor" not in PLUGIN_SOURCE
    assert "_clear_focus" not in PLUGIN_SOURCE
    assert "cancelOperation_" not in PLUGIN_SOURCE
    assert "rowAlpha" not in PLUGIN_SOURCE
    assert '"focus"' not in PLUGIN_SOURCE


def test_action_popover_has_store_labels_checkbox() -> None:
    body = _method_body("Open_Action_Popover")
    # Checked iff the font already carries its labels in userData; disabled
    # when no font is open.
    assert "popover.storeInFont = CheckBox" in body
    assert "value=colornames.font_labels_text(Glyphs.font) is not None" in body
    assert "callback=self._popover_store_in_font" in body
    assert "popover.storeInFont.enable(False)" in body


def test_action_popover_height_fits_settings_rows() -> None:
    body = _method_body("Open_Action_Popover")
    # 590 -> 518: the retired settings rows (two checkboxes + one button) below
    # the legend were removed, leaving only the store-in-font checkbox.
    assert "Popover((220, 518)" in body
    assert "Popover((220, 546)" not in body
    assert "Popover((220, 568)" not in body
    assert "Popover((220, 590)" not in body
    assert "Popover((220, 500)" not in body


def test_store_labels_handler_mirrors_settings_panel_save() -> None:
    body = _method_body("_popover_store_in_font")
    # Tick: write the effective label text into the font's userData (same
    # resolution as settings_panel._save: in-font text wins, then key file).
    assert "colornames.pick_settings_text(" in body
    assert "font.userData[colornames.FONT_LABELS_KEY] = text" in body
    # Untick: clear the key, guarded like settings_panel was.
    assert "del font.userData[colornames.FONT_LABELS_KEY]" in body
    assert "is not None" in body
    # No font -> no-op, and the palette rebuilds from the effective text.
    assert "if font is None:" in body
    assert "reload_after_settings" in body


def test_settings_popover_anchor_falls_back_when_collapsed() -> None:
    # The Edit-menu item passes an NSMenuItem (no view) and a collapsed palette
    # leaves self.dialog hidden — the anchor helper must skip unusable views and
    # fall back to the key/main window, returning None (graceful bail) last.
    body = _method_body("_popover_anchor_view")
    assert "keyWindow" in body
    assert "mainWindow" in body
    assert "isHiddenOrHasHiddenAncestor" in body
    assert "return None" in body
    popover_body = _method_body("Open_Action_Popover")
    assert "self._popover_anchor_view(sender)" in popover_body
    assert "if button is None" in popover_body


# --------------------------------------------------------------------------- #
# Native shortcut commands (Glyphs > Settings > Shortcuts)
# --------------------------------------------------------------------------- #


def test_start_registers_native_shortcuts_guarded() -> None:
    body = _palette_start_body()
    # Registration happens at plugin start() and is wrapped in try/except so a
    # missing GSCallbackHandler symbol can never break plugin load.
    call = body.index("_register_native_shortcuts()")
    guard_open = body.rindex("try:", 0, call)
    guard_close = body.index("except Exception:", call)
    assert guard_open < call < guard_close
    assert "Color Flow [shortcuts] error" in body


def test_register_uses_gscallbackhandler_api_unassigned() -> None:
    body = _module_function_body("_register_native_shortcuts")
    # The verified GlyphsCore API (GSCallbackHandler.h:94), reached via
    # objc.lookUpClass — never a hard import that could fail at module load.
    assert 'objc.lookUpClass("GSCallbackHandler")' in body
    assert (
        "registerShortcutCommand_group_identifier_action_target_character_modifierFlags_" in body
    )
    # Commands ship unassigned (character "") with no modifiers — users map
    # their own keys natively in Settings > Shortcuts.
    assert '"",  # unassigned' in body
    # Once-per-session guard: Glyphs builds one palette instance per window.
    assert "if _SHORTCUT_HANDLER is not None:" in body
    # The target is retained module-globally (GSShortcutItem.target is weak).
    assert "global _SHORTCUT_HANDLER" in body
    assert "_SHORTCUT_HANDLER = target" in body


def test_register_covers_only_jump_command_in_one_group() -> None:
    body = _module_function_body("_register_native_shortcuts")
    assert '_SHORTCUT_GROUP = "Color Flow"' in PLUGIN_SOURCE
    assert '_SHORTCUT_ID_PREFIX = "com.hugojourdan.ColorFlow."' in PLUGIN_SOURCE
    # Exactly one command: the jump (Hugo's wording), no step toggles.
    assert '"Jump to next color glyph"' in body
    assert '_SHORTCUT_ID_PREFIX + "jumpNext"' in body
    assert '"jumpNextShortcut:"' in body
    assert "toggleStepShortcut" not in PLUGIN_SOURCE
    assert "_SHORTCUT_DISPLAY_NAMES" not in PLUGIN_SOURCE
    assert "_toggle_step_for_selection" not in PLUGIN_SOURCE


def test_shortcut_handler_has_jump_selector_and_validate() -> None:
    # One ObjC selector for the jump command on a long-lived NSObject target.
    assert "class ColorFlowShortcutHandler(NSObject):" in PLUGIN_SOURCE
    assert "def jumpNextShortcut_(self, sender) -> None:" in PLUGIN_SOURCE
    # GSShortcutCommandProtocol conformance, typed as returning an ObjC BOOL.
    assert "def validateShortcutCommand_editViewController_(" in PLUGIN_SOURCE
    validate = PLUGIN_SOURCE.index("def validateShortcutCommand_editViewController_(")
    decorator = PLUGIN_SOURCE.rindex("@objc.typedSelector(objc._C_NSBOOL", 0, validate)
    assert decorator < validate
    # The action path is guarded — the shortcut can never raise into Glyphs.
    jump_body = PLUGIN_SOURCE[
        PLUGIN_SOURCE.index("def jumpNextShortcut_") : PLUGIN_SOURCE.index(
            "def _register_native_shortcuts"
        )
    ]
    assert "except Exception:" in jump_body


def test_shortcut_jump_mirrors_generated_script() -> None:
    body = _module_function_body("_jump_to_next_unfinished")
    # Same semantics as the generated JUMP_TAIL: shared colornav navigation,
    # final visible step from colorNames.txt, wrap-around scan, new Edit tab.
    assert "colornames.final_visible_step(meaning)" in body
    assert "colornav.next_unfinished_index(pairs, final_step, position)" in body
    assert '"All glyphs finished."' in body
    assert 'font.newTab("/" + names[index])' in body
    assert "import colornav" in PLUGIN_SOURCE


# --------------------------------------------------------------------------- #
# Non-exporting glyphs are ALWAYS excluded from every count and percentage
# --------------------------------------------------------------------------- #


def test_action_popover_has_no_exporting_only_checkbox() -> None:
    # The exclusion is always on — no opt-in checkbox, no pref key anywhere.
    body = _method_body("Open_Action_Popover")
    assert "Count exporting glyphs only" not in body
    assert "popover.exporting" not in body
    assert "ColorFlow-Exporting" not in PLUGIN_SOURCE
    assert "_popover_exporting" not in PLUGIN_SOURCE
    assert "def _exporting" not in PLUGIN_SOURCE


def test_derive_counts_threads_exclusion_set_through_colornames() -> None:
    body = _method_body("_derive_counts")
    # (glyph_name, color) pairs filtered by the exclusion set via the shared
    # pure helper — palette and report counting can never disagree.
    assert "colornames.exclude_named_colors(named_colors, self._excluded_glyph_names())" in body
    excluded = _method_body("_excluded_glyph_names")
    # UNCONDITIONAL: the exclusion set is always the non-exporting names.
    assert "colornames.non_exporting_names(self.font.glyphs)" in excluded
    assert "return set()" in excluded                       # only the exception fallback
    assert "Glyphs.defaults" not in excluded


def test_derive_counts_is_exact_census_not_cumulative() -> None:
    # Each count badge = layers with EXACTLY that colour (raw census), NOT the
    # cumulative "reached this step or beyond" suffix-sum. 358 glyphs all on
    # the final step -> final row 358, every other row 0.
    body = _method_body("_derive_counts")
    assert "return colornames.single_counts_from_colors(colors, order)" in body
    assert "colornames.counts_from_colors(" not in PLUGIN_SOURCE


def test_counts_cache_single_variant() -> None:
    # Always-on exclusion -> one cache variant again; no mode suffix anywhere.
    assert '"-exporting"' not in PLUGIN_SOURCE
    assert '_SHORTCUT_COUNTS_KEY = "com.hugojourdan.ColorFlow-counts-"' in PLUGIN_SOURCE
    counts_body = _method_body("_counts")
    assert "key = _SHORTCUT_COUNTS_KEY + masterId" in counts_body
    invalidate = _method_body("_invalidate_counts")
    assert "_SHORTCUT_COUNTS_KEY + masterId] = None" in invalidate


def test_palette_bar_denominator_excludes_non_exporting() -> None:
    body = _method_body("Update_Plugin_UI")
    # Counts AND the bar denominator shrink together, so a fully finished
    # exporting set reads as a full bar on the final step (counts are the
    # exact census, so the other rows stay empty).
    assert "len(self.font.glyphs) - len(self._excluded_glyph_names())" in body
    title = _method_body("_update_title_bar")
    assert "self._excluded_glyph_names()" in title
    assert "colornames.exclude_named_colors(named_colors, excluded)" in title
