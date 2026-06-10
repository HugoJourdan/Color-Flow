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


def test_row_click_focuses_without_opening_tab() -> None:
    body = _method_body("rowClicked_")
    # Row click is focus/dim only — no Edit-tab side-effect (tab spam fix).
    assert "_open_step_tab" not in body
    assert "_focusColor" in body
    assert "Update_Plugin_UI" in body


def test_row_click_keeps_drag_suppression_guard() -> None:
    body = _method_body("rowClicked_")
    # End-of-drag clicks must still be swallowed by the _lastDragTime guard.
    assert "_lastDragTime" in body
    guard = body.index("_lastDragTime")
    focus_toggle = body.index("_focusColor")
    assert guard < focus_toggle


def test_count_click_opens_step_tab() -> None:
    body = _method_body("countClicked_")
    # The count badge keeps the Review Queue behaviour: focus + open the
    # step's glyphs in a new Edit tab.
    assert "_open_step_tab" in body
    assert "_focusColor" in body


def test_escape_still_clears_focus() -> None:
    body = _method_body("cancelOperation_")
    assert "_clear_focus" in body


def test_action_popover_has_free_mode_checkbox() -> None:
    body = _method_body("Open_Action_Popover")
    # Free mode (previously only reachable via the never-imported
    # settings_panel.py) is a checkbox in the action popover, seeded from the
    # FreeMode default the palette already consumes.
    assert "popover.freeMode = CheckBox" in body
    assert "value=self._free_mode()" in body
    assert "callback=self._popover_free_mode" in body


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
    # 500 -> 540: two checkbox rows + separator appended below the legend.
    # 540 -> 568: the "Workflow recipes…" button appended below the checkboxes.
    # 568 -> 590: the "Count exporting glyphs only" checkbox row.
    assert "Popover((220, 590)" in body
    assert "Popover((220, 568)" not in body
    assert "Popover((220, 540)" not in body
    assert "Popover((220, 500)" not in body


def test_free_mode_handler_persists_default_and_invalidates_counts() -> None:
    body = _method_body("_popover_free_mode")
    assert 'Glyphs.defaults["com.hugojourdan.ColorFlow-FreeMode"]' in body
    # Free vs step changes the derived counts, so the per-master cache must be
    # dropped BEFORE the redraw or the bars repaint from stale data.
    invalidate = body.index("_invalidate_counts")
    redraw = body.index("Update_Plugin_UI")
    assert invalidate < redraw


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


def test_register_covers_all_13_commands_in_one_group() -> None:
    body = _module_function_body("_register_native_shortcuts")
    assert '_SHORTCUT_GROUP = "Color Flow"' in PLUGIN_SOURCE
    assert '_SHORTCUT_ID_PREFIX = "com.hugojourdan.ColorFlow."' in PLUGIN_SOURCE
    # 12 toggles driven by the display-name table + the explicit jump command.
    assert "for index, display in _SHORTCUT_DISPLAY_NAMES:" in body
    assert 'f"{_SHORTCUT_ID_PREFIX}toggleStep{index}"' in body
    assert 'f"toggleStepShortcut{index}:"' in body
    assert '_SHORTCUT_ID_PREFIX + "jumpNext"' in body
    assert '"jumpNextShortcut:"' in body
    # The display table covers exactly steps 0..11 with the script spellings.
    table_start = PLUGIN_SOURCE.index("_SHORTCUT_DISPLAY_NAMES = (")
    table = PLUGIN_SOURCE[table_start : PLUGIN_SOURCE.index(")\n", table_start)]
    for index, display in enumerate(
        [
            "Red", "Orange", "Brown", "Yellow", "Green", "DarkGreen",
            "Blue", "DarkBlue", "Purple", "Magenta", "Grey", "Charcoal",
        ]
    ):
        assert f'({index}, "{display}")' in table


def test_shortcut_handler_has_distinct_selectors_and_validate() -> None:
    # One ObjC selector per command on a long-lived NSObject target.
    assert "class ColorFlowShortcutHandler(NSObject):" in PLUGIN_SOURCE
    for index in range(12):
        assert f"def toggleStepShortcut{index}_(self, sender) -> None:" in PLUGIN_SOURCE
        assert f"self._toggle({index})" in PLUGIN_SOURCE
    assert "def jumpNextShortcut_(self, sender) -> None:" in PLUGIN_SOURCE
    # GSShortcutCommandProtocol conformance, typed as returning an ObjC BOOL.
    assert "def validateShortcutCommand_editViewController_(" in PLUGIN_SOURCE
    validate = PLUGIN_SOURCE.index("def validateShortcutCommand_editViewController_(")
    decorator = PLUGIN_SOURCE.rindex("@objc.typedSelector(objc._C_NSBOOL", 0, validate)
    assert decorator < validate
    # Both action paths are guarded — a shortcut can never raise into Glyphs.
    toggle_body = PLUGIN_SOURCE[
        PLUGIN_SOURCE.index("def _toggle(self, index: int)") : PLUGIN_SOURCE.index(
            "def jumpNextShortcut_"
        )
    ]
    assert "except Exception:" in toggle_body
    jump_body = PLUGIN_SOURCE[
        PLUGIN_SOURCE.index("def jumpNextShortcut_") : PLUGIN_SOURCE.index(
            "def toggleStepShortcut0_"
        )
    ]
    assert "except Exception:" in jump_body


def test_shortcut_toggle_mirrors_generated_script() -> None:
    body = _module_function_body("_toggle_step_for_selection")
    # Same semantics as the generated TOGGLE_TAIL in tools/generate_shortcuts.py.
    assert "if key not in meaning:" in body  # hidden colour -> no-op
    assert 'bool(Glyphs.defaults["com.hugojourdan.ColorFlow-FreeMode"])' in body
    assert "None if layer.color == index else index" in body  # free mode
    assert "colornames.checked_state_for_color(layer.color, order)" in body
    assert "colornames.layer_color_for_state(state, order)" in body
    # Invalidates the palette's cached per-master counts, same tempData key.
    assert '_SHORTCUT_COUNTS_KEY = "com.hugojourdan.ColorFlow-counts-"' in PLUGIN_SOURCE
    assert "font.tempData[_SHORTCUT_COUNTS_KEY + master.id] = None" in body


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
# Exporting-only mode (count exporting glyphs only)
# --------------------------------------------------------------------------- #


def test_action_popover_has_exporting_only_checkbox() -> None:
    body = _method_body("Open_Action_Popover")
    # Opt-in pref (default OFF), seeded from the same key the dashboard reads.
    assert "popover.exportingOnly = CheckBox" in body
    assert '"Count exporting glyphs only"' in body
    assert "value=self._exporting_only()" in body
    assert "callback=self._popover_exporting_only" in body
    assert (
        '_EXPORTING_ONLY_KEY = "com.hugojourdan.ColorFlow-ExportingOnly"' in PLUGIN_SOURCE
    )


def test_exporting_only_handler_persists_pref_and_invalidates_counts() -> None:
    body = _method_body("_popover_exporting_only")
    assert "Glyphs.defaults[_EXPORTING_ONLY_KEY]" in body
    # The stale cache for the newly selected mode must be dropped BEFORE the
    # redraw, same discipline as the free-mode handler.
    invalidate = body.index("_invalidate_counts")
    redraw = body.index("Update_Plugin_UI")
    assert invalidate < redraw


def test_derive_counts_threads_exclusion_set_through_colornames() -> None:
    body = _method_body("_derive_counts")
    # (glyph_name, color) pairs filtered by the exclusion set via the shared
    # pure helper — palette and report counting can never disagree.
    assert "colornames.exclude_named_colors(named_colors, self._excluded_glyph_names())" in body
    excluded = _method_body("_excluded_glyph_names")
    assert "colornames.non_exporting_names(self.font.glyphs)" in excluded
    assert "if not self._exporting_only():" in excluded     # OFF -> empty set, all count


def test_counts_cache_key_includes_exporting_only_pref() -> None:
    # Toggling the pref must invalidate: the cache signature embeds the mode, and
    # the invalidator drops BOTH variants.
    key_body = _method_body("_counts_cache_key")
    assert '"-exporting" if self._exporting_only() else ""' in key_body
    counts_body = _method_body("_counts")
    assert "self._counts_cache_key(masterId)" in counts_body
    invalidate = _method_body("_invalidate_counts")
    assert "_SHORTCUT_COUNTS_KEY + masterId] = None" in invalidate
    assert '_SHORTCUT_COUNTS_KEY + masterId + "-exporting"] = None' in invalidate
    # the module-level shortcut toggle clears both variants too
    toggle = _module_function_body("_toggle_step_for_selection")
    assert 'font.tempData[_SHORTCUT_COUNTS_KEY + master.id + "-exporting"] = None' in toggle


def test_palette_bar_denominator_excludes_non_exporting() -> None:
    body = _method_body("Update_Plugin_UI")
    # Counts AND the bar denominator shrink together, so a fully finished
    # exporting set reads as a full bar.
    assert "len(self.font.glyphs) - len(self._excluded_glyph_names())" in body
    title = _method_body("_update_title_bar")
    assert "self._excluded_glyph_names()" in title
    assert "colornames.exclude_named_colors(named_colors, excluded)" in title
