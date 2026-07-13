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
    / "AZ-Colorflow.glyphsPalette"
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
    """Return the source of ``AZColorflow.start`` (the loader-bar class has its
    own ``start``, so scan from the palette class definition)."""
    class_start = PLUGIN_SOURCE.index("class AZColorflow(PalettePlugin):")
    start = PLUGIN_SOURCE.index("def start(", class_start)
    end = PLUGIN_SOURCE.index("\n\tdef ", start)
    return PLUGIN_SOURCE[start:end]


def _validate_menu_item_body() -> str:
    """Return the source of the palette's ``validateMenuItem_``.

    The dedicated ``AZColorflowRainbowMenuHandler`` also defines a
    ``validateMenuItem_`` (the Rainbow item's checkmark validator), so scan
    from the palette class definition to get the palette's own validator for
    the context-menu entries.
    """
    class_start = PLUGIN_SOURCE.index("class AZColorflow(PalettePlugin):")
    start = PLUGIN_SOURCE.index("def validateMenuItem_(", class_start)
    end = PLUGIN_SOURCE.index("\n\tdef ", start)
    return PLUGIN_SOURCE[start:end]


def _rainbow_handler_validate_body() -> str:
    """Return the source of ``AZColorflowRainbowMenuHandler.validateMenuItem_``
    (the singleton File-menu handler that owns the Rainbow checkmark)."""
    class_start = PLUGIN_SOURCE.index("class AZColorflowRainbowMenuHandler(NSObject):")
    start = PLUGIN_SOURCE.index("def validateMenuItem_(", class_start)
    end = PLUGIN_SOURCE.index("\n\tdef ", start)
    return PLUGIN_SOURCE[start:end]


def test_palette_validate_menu_item_has_no_rainbow_branch() -> None:
    body = _validate_menu_item_body()
    # The Rainbow File-menu item targets the module-level singleton handler,
    # so the palette's validator (context-menu entries) must not branch on —
    # or stamp — the Rainbow checkmark; it only gates on an open font. The
    # palette-side toggleRainbow_/Toggle_Rainbow pair is gone with it.
    assert "toggleRainbow:" not in body
    assert "setState_" not in body
    assert "return Glyphs.font is not None" in body
    assert "def Toggle_Rainbow(" not in PLUGIN_SOURCE


def test_rainbow_checkmark_lives_on_singleton_handler() -> None:
    body = _rainbow_handler_validate_body()
    # Original Rainbow semantics preserved on the handler: with no font the
    # item is unchecked and disabled; otherwise the checkmark reflects the
    # current font's grouping state.
    no_font = body.index("if font is None")
    tail = body[no_font:]
    assert "menuItem.setState_(NSOffState)" in tail
    assert "return font is not None" in tail
    assert "NSOnState if self._fontview.is_enabled(font) else NSOffState" in tail


def test_single_click_row_focus_removed() -> None:
    # Single-click row focus is gone: no handler, no gesture wiring.
    assert "def rowClicked_(" not in PLUGIN_SOURCE
    assert '"rowClicked:"' not in PLUGIN_SOURCE


def test_double_click_row_opens_step_tab() -> None:
    body = _method_body("rowDoubleClicked_")
    # Double-click on a row opens exactly that step's glyphs in a new Edit tab.
    assert "_open_step_tab" in body
    assert "_color_for_recognizer" in body


def test_row_overlay_has_open_tab_click_only_no_drag() -> None:
    body = _method_body("_attach_row_overlay")
    # The overlay keeps the two-click open-tab recognizer; the drag-reorder pan was
    # removed (reordering moved to the Settings pane).
    assert '"rowDoubleClicked:"' in body
    assert "setNumberOfClicksRequired_(2)" in body
    assert '"colorDragged:"' not in body
    assert "NSPanGestureRecognizer" not in body


def test_palette_drag_reorder_machinery_removed() -> None:
    # All the palette drag-reorder methods + their helpers are gone.
    for name in (
        "def colorDragged_(",
        "def _reorder_color_to(",
        "def _write_order(",
        "def _drop_index(",
        "def _begin_drag_feedback(",
        "def _update_drop_line(",
        "def _clear_drag_feedback(",
        "def _push_drag_cursor(",
        "def _pop_drag_cursor(",
        "def _row_index_at_point(",
        "def _row_top(",
    ):
        assert name not in PLUGIN_SOURCE, name
    # The double-click handler no longer needs the end-of-drag suppression guard.
    assert "_lastDragTime" not in PLUGIN_SOURCE


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


# --------------------------------------------------------------------------- #
# Settings PANE migration (Glyphs > Settings > Color Flow)
# --------------------------------------------------------------------------- #


def test_action_popover_builder_is_gone() -> None:
    # The label/colour/store-in-font controls moved to the Settings pane, so the
    # per-palette action popover builder + its anchor helper no longer exist.
    assert "def Open_Action_Popover(" not in PLUGIN_SOURCE
    assert "def _popover_anchor_view(" not in PLUGIN_SOURCE
    # The report flow (its own helper) is SEPARATE and stays.
    assert "def _popover_dashboard(" in PLUGIN_SOURCE


def test_settings_pane_registered_once_via_app_delegate() -> None:
    body = _module_function_body("_register_preferences_pane")
    # The pane lands as a tab in the shared "AZ Toolkit" hub...
    assert "hub.addSettingsPane_(view_controller)" in body
    # ...with the verified GSAppDelegateProtocol API as the standalone fallback.
    assert "addViewToPreferences_(view_controller)" in body
    # Exactly once per app session, behind a module-level guard.
    assert "if _PREF_PANE_ADDED:" in body
    assert "return" in body
    assert "global _PREF_PANE_ADDED" in body
    assert "_PREF_PANE_ADDED = True" in body
    # Module-level guard flag + retained VC reference so AppKit can't deallocate it.
    assert "_PREF_PANE_ADDED = False" in PLUGIN_SOURCE
    assert "_PREF_PANE_VC = view_controller" in body


def test_az_toolkit_hub_protocol() -> None:
    # The shared AZ Toolkit hub: one Settings entry for the whole AZ suite,
    # rendezvous through the main thread's threadDictionary (protocol v1).
    assert '_HUB_KEY = "AZToolkit.SettingsHub.v1"' in PLUGIN_SOURCE
    assert '_HUB_TITLE = "AZ Toolkit"' in PLUGIN_SOURCE
    assert "class AZColorflowToolkitHub(AppKit.NSViewController):" in PLUGIN_SOURCE
    # The two selectors every AZ plugin relies on must keep these exact names.
    assert "def addSettingsPane_(self" in PLUGIN_SOURCE
    assert "def showSettingsPaneWithIdentifier_(self" in PLUGIN_SOURCE
    hub_finder = _module_function_body("_toolkit_hub")
    # First plugin to load creates + parks + registers the hub; others reuse it.
    assert "pool.objectForKey_(_HUB_KEY)" in hub_finder
    assert "pool.setObject_forKey_(hub, _HUB_KEY)" in hub_finder
    assert "delegate.addViewToPreferences_(hub)" in hub_finder
    # The jump opens Settings on the HUB identifier (our tab is selected first).
    opener = PLUGIN_SOURCE[
        PLUGIN_SOURCE.index("def showSettingsPaneWithIdentifier_(") :
        PLUGIN_SOURCE.index("def _recalc_preferred_size(")
    ]
    assert "showMainPreferencesWithIdentifier_(_HUB_TITLE)" in opener


def test_az_toolkit_hub_popup_and_license_badge() -> None:
    # The hub switches panes with a full-width popup over a tabless NSTabView.
    assert "NSPopUpButton.alloc().initWithFrame_pullsDown_(" in PLUGIN_SOURCE
    assert "setTabViewType_(AppKit.NSNoTabsNoBorder)" in PLUGIN_SOURCE
    assert "def azToolkitPopupChanged_(self" in PLUGIN_SOURCE
    # Licensed (bought, not trial) panes get a badge: a palette symbol image
    # (white checkmark in an accent seal) with the monochrome glyph as fallback.
    assert '"checkmark.seal.fill"' in PLUGIN_SOURCE
    assert "configurationWithPaletteColors_(" in PLUGIN_SOURCE
    assert "attributedStringWithAttachment_(" in PLUGIN_SOURCE
    assert '_HUB_BADGE = "\\U001001FB"' in PLUGIN_SOURCE
    assert "def azLicensed(self" in PLUGIN_SOURCE
    # Debug override: the AZToolkitFakeLicensed defaults key badges every pane.
    assert 'boolForKey_("AZToolkitFakeLicensed")' in PLUGIN_SOURCE
    badge_check = _method_body("azLicensed")
    assert '_SHARED_ENT.kind == "licensed"' in badge_check
    add_pane = PLUGIN_SOURCE[
        PLUGIN_SOURCE.index("def addSettingsPane_(") :
        PLUGIN_SOURCE.index("def _pane_licensed(")
    ]
    assert "self._pane_licensed(pane)" in add_pane
    assert "setAttributedTitle_(text)" in add_pane
    licensed_probe = _module_function_body("_toolkit_hub")  # hub finder unchanged
    assert "pool.objectForKey_(_HUB_KEY)" in licensed_probe


def test_settings_pane_vc_title_is_color_flow() -> None:
    # Verified GlyphsCore mechanism: -addViewController: makes the Settings tab identifier
    # = vc.representedObject and the label = vc.title. So both title and representedObject
    # are "Color Flow" (the string showMainPreferencesWithIdentifier: matches).
    assert "class AZColorflowPreferencesController(AppKit.NSViewController):" in PLUGIN_SOURCE
    assert 'COLORFLOW_PREF_IDENTIFIER = "AZ Colorflow"' in PLUGIN_SOURCE
    reg = _module_function_body("_register_preferences_pane")
    assert "view_controller.setTitle_(COLORFLOW_PREF_IDENTIFIER)" in reg
    assert "view_controller.setRepresentedObject_(COLORFLOW_PREF_IDENTIFIER)" in reg
    init_body = PLUGIN_SOURCE[
        PLUGIN_SOURCE.index("def initWithSettingsView_(") :
        PLUGIN_SOURCE.index("def loadView(")
    ]
    assert "self.setTitle_(COLORFLOW_PREF_IDENTIFIER)" in init_body
    assert "self.setRepresentedObject_(COLORFLOW_PREF_IDENTIFIER)" in init_body
    # representedObject must be the identifier STRING, never an NSImage (that breaks the jump).
    assert "setRepresentedObject_(icon)" not in PLUGIN_SOURCE


def test_start_registers_pane_and_observes_broadcast() -> None:
    body = _palette_start_body()
    # Registration is at start(), guarded, so it can never break plugin load.
    reg = body.index("_register_preferences_pane()")
    guard_open = body.rindex("try:", 0, reg)
    guard_close = body.index("except Exception:", reg)
    assert guard_open < reg < guard_close
    # Each palette observes the broadcast so Settings-pane edits update it live.
    assert 'self, "colorFlowSettingsChanged:", COLORFLOW_SETTINGS_CHANGED, None' in body


def test_settings_changed_selector_reloads_palette() -> None:
    body = _method_body("colorFlowSettingsChanged_")
    # The observer rebuilds this palette from the freshly-written settings.
    assert "reload_after_settings" in body


def test_settings_entry_points_removed() -> None:
    # The settings gear and the Edit-menu "Color Flow settings…" / "Backfill timeline"
    # items are gone; the pane is reached only via Glyphs > Settings now.
    assert "def openSettings_(" not in PLUGIN_SOURCE
    assert "def _install_settings_menu(" not in PLUGIN_SOURCE
    assert '"openSettings:"' not in PLUGIN_SOURCE
    assert "def backfillTimeline_(" not in PLUGIN_SOURCE
    assert "def _install_backfill_menu(" not in PLUGIN_SOURCE
    assert "_BACKFILL_TITLE" not in PLUGIN_SOURCE
    assert "Open_Action_Popover" not in PLUGIN_SOURCE
    # The pane is still registered once at start() and reachable; the opener helper
    # (showMainPreferencesWithIdentifier:) remains available for any future entry point.
    opener = _module_function_body("_open_preferences_pane")
    assert "showMainPreferencesWithIdentifier_(COLORFLOW_PREF_IDENTIFIER)" in opener


def test_settings_pane_routes_through_shared_helpers_and_broadcasts() -> None:
    # The pane edits via the pure helpers and broadcasts to open palettes — it
    # never reaches into a single palette instance.
    colors = _module_function_body("_apply_label_colors")
    assert "labelcolors.write_label_colors(colors)" in colors
    assert "_broadcast_settings_changed()" in colors
    names = _module_function_body("_apply_label_names")
    assert "colornames.render_settings(" in names
    assert "_broadcast_settings_changed()" in names
    broadcast = _module_function_body("_broadcast_settings_changed")
    assert "postNotificationName_object_(" in broadcast
    assert "COLORFLOW_SETTINGS_CHANGED" in broadcast


def test_store_labels_and_profile_controls_removed_from_pane() -> None:
    # The store-in-font checkbox and the import/export/reset icon buttons were
    # removed from the pane, along with their handlers + now-orphaned helpers.
    assert "group.storeInFont" not in PLUGIN_SOURCE
    assert "def _store_changed(" not in PLUGIN_SOURCE
    assert "def _apply_store_in_font(" not in PLUGIN_SOURCE
    assert "group.lcImport" not in PLUGIN_SOURCE
    assert "group.lcExport" not in PLUGIN_SOURCE
    assert "group.lcReset" not in PLUGIN_SOURCE
    assert "def _import_profile(" not in PLUGIN_SOURCE
    assert "def _export_profile(" not in PLUGIN_SOURCE
    assert "import azcolorflow_profile" not in PLUGIN_SOURCE


def test_settings_pane_build_order_labels_then_font_glyph_order() -> None:
    build = PLUGIN_SOURCE[
        PLUGIN_SOURCE.index("def _build(self) -> None:") :
        PLUGIN_SOURCE.index("def _slot_list_items(")
    ]
    # Top-to-bottom: Color Labels title, the help line, the combined list, then Font Glyph
    # Order (the inline legend was removed; the header now reads "Color Labels").
    labels = build.index('"Color Labels"')
    fgo = build.index('"Font Glyph Order"')
    assert labels < fgo
    assert '"Labels & Colours"' not in PLUGIN_SOURCE
    # A help line under the title explains how to edit a row (rename = double-click).
    help_index = build.index("group.lcHelp = TextBox")
    assert labels < help_index < build.index("group.lcList = List2")
    assert "Double-click a name to rename it." in build
    # The inline legend is gone.
    assert "group.legend = TextBox" not in PLUGIN_SOURCE
    assert "def _legend_text(" not in PLUGIN_SOURCE
    # Pane base width 340 (narrow); the view + full-width controls stretch to fill the tab.
    assert "WIDTH = 340" in PLUGIN_SOURCE
    assert "AppKit.NSViewWidthSizable | AppKit.NSViewMinYMargin" in PLUGIN_SOURCE


def test_color_glyph_order_is_a_checkbox_not_a_segmented_button() -> None:
    build = PLUGIN_SOURCE[
        PLUGIN_SOURCE.index("def _build(self) -> None:") :
        PLUGIN_SOURCE.index("def _slot_list_items(")
    ]
    # Font Glyph Order is now a single CheckBox "Color Glyph Order" (ON = Layer order,
    # OFF = Default), replacing the old 3-way Default/Layer/Glyph SegmentedButton.
    assert "SegmentedButton" not in PLUGIN_SOURCE
    assert "group.colorOrder = CheckBox(" in build
    assert '"Color Glyph Order"' in build
    assert "callback=self._color_order_changed" in build
    # ON -> Layer (segment 1), OFF -> Default (segment 0).
    cb = _method_body("_color_order_changed")
    assert "_apply_rainbow_source(Glyphs.font, 1 if sender.get() else 0)" in cb


def test_hidden_slot_rows_are_dimmed() -> None:
    assert "def _dim_hidden_rows(self) -> None:" in PLUGIN_SOURCE
    body = _method_body("_dim_hidden_rows")
    # Force each row view to exist, then full alpha for visible / faded for hidden rows.
    assert "rowViewAtRow_makeIfNecessary_(row, True)" in body
    assert "setAlphaValue_(1.0 if self._slot_is_visible(item) else 0.4)" in body
    # Re-applied after the list builds and after every reload/edit/drop.
    assert PLUGIN_SOURCE.count("self._dim_hidden_rows()") >= 4


def test_default_glyph_order_pokes_a_resort_via_store_sort_name() -> None:
    # Switching to Default restores the font order AND nudges Glyphs to re-sort the Font
    # View by toggling storeSortName on the first glyph (True then False, no persistence).
    apply = _module_function_body("_apply_rainbow_source")
    assert "_poke_default_sort(font)" in apply
    poke = _module_function_body("_poke_default_sort")
    assert "glyph.storeSortName = True" in poke
    assert "glyph.storeSortName = False" in poke
    # Guarded against an empty font.
    assert "len(font.glyphs) == 0" in poke


def test_settings_panel_module_deleted() -> None:
    # The dead settings_panel.py module is gone.
    assert not (RESOURCES / "settings_panel.py").exists()


def test_settings_pane_reset_is_a_reload_icon_next_to_the_title() -> None:
    # Reset is now a borderless "reload" (arrow.clockwise) icon button next to the title,
    # NOT the old full-width "Reset colours & order" button.
    assert "group.resetButton = ImageButton(" in PLUGIN_SOURCE
    assert 'imageWithSystemSymbolName_accessibilityDescription_(\n\t\t\t"arrow.clockwise"' in PLUGIN_SOURCE
    assert "callback=self._reset_clicked" in PLUGIN_SOURCE
    assert "Reset colours & order" not in PLUGIN_SOURCE
    assert "group.resetButton = Button(" not in PLUGIN_SOURCE
    assert "def _reset_clicked(" in PLUGIN_SOURCE
    # It routes through the shared module helper, which writes the defaults and broadcasts.
    body = _module_function_body("_reset_colors_and_order")
    assert "labelcolors.DEFAULTS" in body
    assert "colornames.DEFAULT_COLOR_NAMES" in body
    assert "_broadcast_settings_changed()" in body


# --------------------------------------------------------------------------- #
# Combined Labels & Colours control: ONE List2 (colour well + name, drag visible)
# --------------------------------------------------------------------------- #


def test_settings_pane_has_single_combined_slot_list() -> None:
    build = PLUGIN_SOURCE[
        PLUGIN_SOURCE.index("def _build(self) -> None:") :
        PLUGIN_SOURCE.index("def _slot_list_items(")
    ]
    # ONE List2 holds all label slots: an eye-toggle visibility column + a colour-well
    # column + an editable name column (eye FIRST so it reads left-to-right).
    assert "group.lcList = List2(" in build
    assert "self._slot_list_items(font)" in build
    assert 'identifier="visible"' in build
    assert "cellClass=EyeToggleList2Cell" in build
    assert "cellClass=ColorWellList2Cell" in build
    assert "cellClass=EditTextList2Cell" in build
    # The visible eye column comes BEFORE the colour well.
    assert build.index('identifier="visible"') < build.index('identifier="color"')
    # All three columns are editable so any slot can be shown/hidden, recoloured, renamed.
    assert build.count("editable=True") >= 3
    # The eye column is narrow (24) and the colour well is 44; name fills the rest.
    assert "width=24" in build
    # Edits route through one combined handler; drag-reorder + self-drop are wired.
    assert "editCallback=self._slot_edited" in build
    assert "dragCandidateCallback=self._slot_drag_candidate" in build
    assert "makeDragDataCallback=self._slot_make_drag_data" in build
    assert "performDropCallback=self._slot_perform_drop" in build


def test_visibility_cell_is_an_eye_toggle() -> None:
    # The visibility cell is a CheckBox restyled as an eye toggle: eye.fill (shown) /
    # eye.slash (hidden), driven by the on/off state of a borderless toggle button.
    assert "class EyeToggleList2Cell(CheckBoxList2Cell):" in PLUGIN_SOURCE
    cell = PLUGIN_SOURCE[
        PLUGIN_SOURCE.index("class EyeToggleList2Cell(CheckBoxList2Cell):") :
        PLUGIN_SOURCE.index("class AZColorflowSettingsView:")
    ]
    assert '_eye_symbol("eye.slash")' in cell      # state OFF = hidden
    assert '_eye_symbol("eye.fill")' in cell        # state ON  = shown
    assert "button.setImage_(off_eye)" in cell
    assert "button.setAlternateImage_(on_eye)" in cell
    assert "NSButtonTypeToggle" in cell
    assert "button.setBordered_(False)" in cell
    helper = _module_function_body("_eye_symbol")
    assert "imageWithSystemSymbolName_accessibilityDescription_(name, None)" in helper


def test_old_separate_order_list_removed() -> None:
    # The redundant standalone "Order (drag to reorder)" section is gone: its label,
    # its List, and the now-unused per-row drag/drop handlers must not survive.
    assert "Order (drag to reorder)" not in PLUGIN_SOURCE
    assert "group.orderList" not in PLUGIN_SOURCE
    assert "group.orderLabel" not in PLUGIN_SOURCE
    assert "def _order_drag(" not in PLUGIN_SOURCE
    assert "def _order_drop(" not in PLUGIN_SOURCE
    assert "def _order_list_items(" not in PLUGIN_SOURCE
    # The old separate 12-row well/field editor is gone too (merged into the list).
    assert "group.lcWell" not in PLUGIN_SOURCE
    assert "group.lcField" not in PLUGIN_SOURCE


def test_combined_list_covers_all_twelve_slots() -> None:
    body = _method_body("_slot_list_items")
    # The combined list is built from ALL 12 label slots (visible first, hidden pinned below).
    assert "labelcolors.read_label_colors()" in body
    assert "colornames.parse_settings(self._effective_label_text(font))" in body
    assert "if visible" in body and "if not visible" in body
    assert "visible_rows + hidden_rows" in body
    # Each row carries its EXPLICIT visibility flag from the parsed rows (not name-blankness).
    assert "dict(slot=int(index), color=color, name=label," in body
    assert "visible=any(index == r[0] and r[2] for r in rows)" in body


def test_only_visible_rows_are_draggable() -> None:
    candidate = _method_body("_slot_drag_candidate")
    # A drag is allowed only when every picked row is VISIBLE (shown); hidden rows are fixed.
    assert "self._slot_is_visible(self._slot_items[int(i)])" in candidate
    visible = _method_body("_slot_is_visible")
    # Visibility is the EXPLICIT flag now (the eye/checkbox), NOT name-blankness.
    assert 'bool(item.get("visible"))' in visible
    assert 'str(item.get("name", "")).strip()' not in visible


def test_slot_drop_persists_via_shared_helper() -> None:
    body = _method_body("_slot_perform_drop")
    # The drop builds the new VISIBLE order and routes it through the shared order helper
    # (which writes colorNames + broadcasts); hidden rows stay pinned via reorder_visible_rows.
    assert 'new_order = [item["slot"] for item in new_items if self._slot_is_visible(item)]' in body
    assert "_apply_color_order(Glyphs.font, new_order)" in body
    helper = _module_function_body("_apply_color_order")
    assert "colornames.reorder_visible_rows(rows, new_visible_order)" in helper
    assert "_broadcast_settings_changed()" in helper


def test_slot_edit_applies_only_the_changed_field() -> None:
    body = _method_body("_slot_edited")
    # A single editCallback can't say which column changed, so the handler DIFFS the live
    # rows against the persisted state and applies ONLY the store that moved. This is the
    # fix for "hiding/renaming silently changes the colours": an untouched well must NOT
    # trigger a colour rewrite.
    assert "_apply_label_colors(new_colors)" in body
    assert "if colors_changed:" in body
    # Wells are read in DEVICE RGB (symmetric with how they're built + stored), so an
    # unchanged well compares equal and never colour-space-drifts.
    assert 'native.colorUsingColorSpaceName_("NSDeviceRGBColorSpace")' in body
    assert "_rgba_close(comps, baseline_colors[slot])" in body
    # Names + visibility are each diffed against the persisted colorNames settings.
    assert "colornames.parse_settings(self._effective_label_text(font))" in body
    assert "_apply_label_names(font, labels_by_index)" in body
    assert "_apply_label_visibility(font, visibility_by_index)" in body
    # A visibility flip (and only that) re-pins the list.
    assert "self._slot_list.set(self._slot_list_items(font))" in body
    colors_helper = _module_function_body("_apply_label_colors")
    assert "_broadcast_settings_changed()" in colors_helper
    names_helper = _module_function_body("_apply_label_names")
    assert "_broadcast_settings_changed()" in names_helper


def test_label_colours_read_and_write_use_the_same_colourspace() -> None:
    # read_label_colors must read in the SAME RGB space write_label_colors stores in
    # (device), so a save/load round-trip is the identity and colours don't drift.
    source = (RESOURCES / "labelcolors.py").read_text(encoding="utf-8")
    assert 'colorUsingColorSpaceName_("NSDeviceRGBColorSpace")' in source
    assert "NSCalibratedRGBColorSpace" not in source
    assert "colorWithDeviceRed_green_blue_alpha_" in source


def test_visibility_persists_via_set_label_visibility_and_broadcast() -> None:
    # The eye/checkbox routes through a shared helper that writes colorNames.txt via
    # render_settings (keeping the name) + the in-font copy + broadcasts.
    helper = _module_function_body("_apply_label_visibility")
    assert "colornames.set_label_visibility(rows, int(index), bool(visible))" in helper
    assert "colornames.render_settings(rows, none_label)" in helper
    assert "font.userData[colornames.FONT_LABELS_KEY] = new_text" in helper
    assert "_broadcast_settings_changed()" in helper


def test_renaming_preserves_visibility() -> None:
    # _apply_label_names must NOT derive visibility from name-blankness anymore — it
    # keeps each slot's existing visible flag so a rename never shows/hides a slot.
    helper = _module_function_body("_apply_label_names")
    assert "new_rows.append((index, labels_by_index[index].strip(), visible))" in helper
    assert "bool(new_label)" not in helper


# --------------------------------------------------------------------------- #
# Swap Option color routing — swizzle install
# --------------------------------------------------------------------------- #


def test_routing_hook_replaces_existing_method_via_runtime() -> None:
    body = _module_function_body("_install_color_routing_hook")
    # setColorIndex: already exists on GSFontViewController; classAddMethods/Category only
    # ADD new selectors, so our impl is added under a PRIVATE selector and its IMP is then
    # copied onto setColorIndex: via the Objective-C runtime.
    assert 'objc.lookUpClass("GSFontViewController")' in body
    assert 'selector=b"cf_swapSetColorIndex:"' in body
    assert "objc.classAddMethods(font_view_controller, [private])" in body
    assert '_runtime_copy_imp("GSFontViewController", b"cf_swapSetColorIndex:"' in body
    assert 'signature=b"v@:C"' in body
    # Idempotent + guarded.
    assert "if _CF_ROUTING_INSTALLED:" in body
    assert "_CF_ROUTING_INSTALLED = True" in body
    # The runtime copy uses method_setImplementation (the verified override path).
    copier = _module_function_body("_runtime_copy_imp")
    assert "method_setImplementation" in copier
    assert "objc_getClass" in copier


def test_routing_replacement_reads_swap_default_at_call_time() -> None:
    body = _method_body("_cf_setColorIndex_")
    # Reads SWAP_KEY each call (no re-swizzle on toggle) and uses the pure decision module.
    assert "Glyphs.defaults[SWAP_KEY]" in body
    assert "azcolorflow_routing.should_apply_swap(event_type)" in body
    assert "azcolorflow_routing.resolve_color_target(option, swap)" in body
    # Routes to layer.colorIndex or glyph.colorIndex.
    assert "layer.colorIndex = color_index" in body
    assert "glyph.colorIndex = color_index" in body


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
    assert "AZ Colorflow [shortcuts] error" in body


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
    assert '_SHORTCUT_GROUP = "AZ Colorflow"' in PLUGIN_SOURCE
    assert '_SHORTCUT_ID_PREFIX = "com.hugojourdan.AZColorflow."' in PLUGIN_SOURCE
    # Exactly one command: the jump (Hugo's wording), no step toggles.
    assert '"Jump to next color glyph"' in body
    assert '_SHORTCUT_ID_PREFIX + "jumpNext"' in body
    assert '"jumpNextShortcut:"' in body
    assert "toggleStepShortcut" not in PLUGIN_SOURCE
    assert "_SHORTCUT_DISPLAY_NAMES" not in PLUGIN_SOURCE
    assert "_toggle_step_for_selection" not in PLUGIN_SOURCE


def test_shortcut_handler_has_jump_selector_and_validate() -> None:
    # One ObjC selector for the jump command on a long-lived NSObject target.
    assert "class AZColorflowShortcutHandler(NSObject):" in PLUGIN_SOURCE
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


def test_no_exporting_only_checkbox_anywhere() -> None:
    # The exclusion is always on — no opt-in checkbox, no pref key anywhere.
    assert "Count exporting glyphs only" not in PLUGIN_SOURCE
    assert "popover.exporting" not in PLUGIN_SOURCE
    assert "AZColorflow-Exporting" not in PLUGIN_SOURCE
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
    assert '_SHORTCUT_COUNTS_KEY = "com.hugojourdan.AZColorflow-counts-"' in PLUGIN_SOURCE
    counts_body = _method_body("_counts")
    assert "key = _SHORTCUT_COUNTS_KEY + masterId" in counts_body
    invalidate = _method_body("_invalidate_counts")
    assert "_SHORTCUT_COUNTS_KEY + masterId] = None" in invalidate


def test_palette_row_has_no_coloured_bar() -> None:
    body = _method_body("Update_Plugin_UI")
    # The per-row coloured progress bar was removed (it sat over the label text). The
    # colour cue is now the 6px colorTag strip + the count number, so no "box" Box and
    # no bar denominator remain in the row builder.
    assert '+"box"' not in body and "barWidth" not in body
    # the non-exporting exclusion still drives the title-bar census, which now
    # reuses the cached per-step counts (same derivation, same exclusion set)
    # instead of recounting the whole font on every header sync
    title = _method_body("_update_title_bar")
    assert "self._excluded_glyph_names()" in title
    assert "self._counts(masterId)" in title
    assert "colornames.exclude_named_colors(" not in title


# --------------------------------------------------------------------------- #
# Section-header buttons: report ONLY (gear AND eye removed — visibility moved
# to the Settings pane)
# --------------------------------------------------------------------------- #


def test_header_has_report_only_no_gear_no_eye() -> None:
    body = _method_body("_inject_title_bar")
    # The report button is the rightmost (and only) header button now.
    assert "reportX = bounds.size.width - pad - btn" in body
    assert 'report.setAction_("openDashboard:")' in body
    assert "self._titleReport = report" in body
    # The settings gear is gone.
    assert "self._titleGear" not in PLUGIN_SOURCE
    assert 'setAction_("openSettings:")' not in body
    # The eye button is gone (visibility now lives in the Settings pane).
    assert "self._titleEye" not in PLUGIN_SOURCE
    assert "headerEyeClicked" not in PLUGIN_SOURCE
    assert "eyeX" not in body
    assert 'setAction_("headerEyeClicked:")' not in body


def test_report_button_triggers_report_flow() -> None:
    body = _method_body("openDashboard_")
    # The report header button drives the same loader-sheet report flow the old
    # popover button used.
    assert "self._popover_dashboard(sender)" in body


def test_sync_header_hides_report_no_eye() -> None:
    body = _method_body("_sync_header")
    # Collapsing the palette (or a blocked trial) hides the report button; no eye.
    assert "_titleReport" in body
    assert "report.setHidden_(collapsed or blocked)" in body
    assert "eye.setHidden_(collapsed)" not in body
    assert "gear.setHidden_(collapsed)" not in body


def test_palette_eye_visibility_mode_fully_removed() -> None:
    # The inline palette "eye" visibility-edit mode is gone end-to-end: no state,
    # no toggle/build/teardown helpers, no per-row click handler.
    for symbol in (
        "_eye_mode",
        "_eye_rows",
        "_eye_none",
        "_eyeRowViews",
        "_toggle_eye_mode",
        "_enter_eye_mode",
        "_exit_eye_mode",
        "_teardown_eye_rows",
        "_build_eye_mode_ui",
        "_set_eye_button",
        "_eye_key_path",
        "eyeRowClicked",
    ):
        assert symbol not in PLUGIN_SOURCE, symbol


# --------------------------------------------------------------------------- #
#  Native report window (WKWebView)
# --------------------------------------------------------------------------- #


def test_report_opens_in_native_window_with_browser_fallback() -> None:
    body = _method_body("_finish_report_sheet")
    # Native window first; webbrowser stays as the fallback when WebKit is out.
    assert "_show_report_window(path)" in body
    assert "webbrowser.open" in body
    assert body.index("_show_report_window") < body.index("webbrowser.open")


def test_report_window_gates_on_webkit_and_falls_back() -> None:
    body = _module_function_body("_show_report_window")
    assert "if WebKit is None:" in body
    assert "return False" in body


def test_report_window_routes_glyphsapp_links_to_the_app() -> None:
    body = _method_body("webView_decidePolicyForNavigationAction_decisionHandler_")
    assert '"glyphsapp"' in body
    assert "NSWorkspace" in body
    assert "_WK_CANCEL" in body
    # <a download> blob exports become WKDownloads instead of navigations.
    assert "shouldPerformDownload" in body
    assert "_WK_DOWNLOAD" in body


def test_report_window_breaks_message_handler_retain_cycle_on_close() -> None:
    # WKUserContentController retains its script-message handler (the window
    # controller). Closing the window must remove the handler and both delegates,
    # or every closed report window leaks a webview + controller.
    body = _method_body("windowWillClose_")
    assert 'removeScriptMessageHandlerForName_("azcfPrint")' in body
    assert "setNavigationDelegate_(None)" in body
    assert "setDelegate_(None)" in body
    assert "_REPORT_WINDOW = None" in body


def test_report_window_maps_window_print_to_native_print_panel() -> None:
    # The report's PDF export calls window.print(), a no-op in a bare WKWebView:
    # a document-start user script rebinds it to the azcfPrint message, and the
    # native side turns that into an NSPrintOperation.
    assert "window.print = function()" in PLUGIN_SOURCE
    assert "azcfPrint" in PLUGIN_SOURCE
    body = _method_body("userContentController_didReceiveScriptMessage_")
    assert "printOperationWithPrintInfo_" in body
