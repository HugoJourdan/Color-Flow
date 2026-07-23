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
    / "AZ-Colorflow.glyphsPlugin"
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
    init_start = PLUGIN_SOURCE.index("def initWithSettingsView_(")
    init_body = PLUGIN_SOURCE[
        init_start : PLUGIN_SOURCE.index("def loadView(", init_start)
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
    # The Edit-menu "Color Flow settings…" / "Backfill timeline" items and the old
    # palette-header gear stay gone; settings are reached via Glyphs > Settings or the
    # sidebar gear (see test_sidebar_has_settings_gear).
    assert "def _install_settings_menu(" not in PLUGIN_SOURCE
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


def test_report_window_top_band_is_draggable_and_padded() -> None:
    # WKWebView swallows mouse events, so the chromeless window needs a native
    # drag strip over the top band — and the page is padded (screen-only) so the
    # floating traffic lights / buttons never overlap report UI.
    assert "class _AZColorflowReportDragStrip(AppKit.NSView):" in PLUGIN_SOURCE
    strip = _method_body("mouseDown_")
    assert "performWindowDragWithEvent_" in strip
    assert "@media screen" in PLUGIN_SOURCE
    assert "padding-top" in PLUGIN_SOURCE
    build = _method_body("_ensure_window")
    assert "_AZColorflowReportDragStrip.alloc()" in build
    assert "NSViewMinYMargin" in build


def _sidebar_block() -> str:
    start = PLUGIN_SOURCE.index("class AZColorflowCoverageSidebar")
    return PLUGIN_SOURCE[start : PLUGIN_SOURCE.index("\nexcept Exception:", start)]


def test_coverage_sidebar_is_g4_gated_and_native() -> None:
    # The Edit-view left-sidebar tab must declare protocol conformance at class
    # creation (Glyphs' registration check is conformsToProtocol:), register the
    # CLASS via GSCallbackHandler, and be a no-op on Glyphs 3.
    assert 'objc.protocolNamed("GSEditViewSidebarControllerProtocol")' in PLUGIN_SOURCE
    assert "protocols=[_SIDEBAR_PROTOCOL]" in PLUGIN_SOURCE
    register = _module_function_body("_register_coverage_sidebar")
    assert 'respondsToSelector_(b"addEditViewLeftSidebarController:")' in register
    assert "addEditViewLeftSidebarController_(AZColorflowCoverageSidebar)" in register
    # Native, no WebView: a custom-drawn NSView + an NSScrollView, no WebKit.
    block = _sidebar_block()
    assert "class _AZCoverageBarsView(AppKit.NSView)" in PLUGIN_SOURCE
    assert "def drawRect_(self, dirtyRect" in PLUGIN_SOURCE
    assert "NSScrollView" in block
    assert "WebKit" not in block and "WKWebView" not in block
    # Each section is an AZ-Dock-style card (rounded fill + border + darker band),
    # with white + monospaced counts and a dark hairline stroke around every bar.
    assert "def _draw_card(self" in PLUGIN_SOURCE
    assert "_COV_CARD_RADIUS" in PLUGIN_SOURCE
    assert "NSColor.blackColor().colorWithAlphaComponent_(0.15)" in PLUGIN_SOURCE   # darker header band
    assert "NSColor.whiteColor(), align=_NS_ALIGN_LEFT, mono=True" in PLUGIN_SOURCE
    assert "monospacedSystemFontOfSize_weight_" in PLUGIN_SOURCE
    assert "NSColor.blackColor().colorWithAlphaComponent_(0.35)" in PLUGIN_SOURCE   # darker bar stroke
    assert "track.setLineWidth_(0.75)" in PLUGIN_SOURCE and "track.stroke()" in PLUGIN_SOURCE


def test_coverage_sidebar_follows_selected_master_live() -> None:
    # Bars track the selected master: rebuild on UPDATEINTERFACE, master read from
    # selectedFontMaster, data from the lean per-master helper; teardown removes
    # the callback so a closed Edit view stops walking glyphs.
    block = _sidebar_block()
    assert "Glyphs.addCallback(self.refreshInterface, UPDATEINTERFACE)" in block
    assert "Glyphs.removeCallback(self.refreshInterface, UPDATEINTERFACE)" in block
    assert "selectedFontMaster.id" in block
    assert "coverage_rows_for_master(font)" in block
    # A master switch skips the debounce (instant); other churn coalesces.
    assert 'performSelector_withObject_afterDelay_("coverageRebuild:", None' in block


def test_coverage_sidebar_categories_collapse_to_subcategories() -> None:
    # Category rows carry a sub-category breakdown (with_subs) and toggle open on
    # click; a disclosure chevron marks expandable rows, the view reflows height.
    assert "with_subs" in _sidebar_block()                          # controller attaches subRows
    assert "def mouseDown_(self, event" in PLUGIN_SOURCE
    assert "self._expanded" in PLUGIN_SOURCE
    assert "def _draw_disclosure(self" in PLUGIN_SOURCE and "is_open" in PLUGIN_SOURCE
    assert "def _reflow(self" in PLUGIN_SOURCE and "self.setFrameSize_" in PLUGIN_SOURCE


def test_coverage_sidebar_collapse_is_animated() -> None:
    # Expand/collapse animates: a per-key progress fraction driven by a 60fps timer,
    # sub-rows revealed by clipping to the animated height, after a short pre-delay.
    assert "self._anim" in PLUGIN_SOURCE
    assert "def animTick_(self, timer" in PLUGIN_SOURCE
    assert "def _start_anim(self" in PLUGIN_SOURCE and "def _stop_anim(self" in PLUGIN_SOURCE
    assert "def _progress(self, key" in PLUGIN_SOURCE
    assert "_COV_SUB_ROW_H * len(subs) * open_frac" in PLUGIN_SOURCE   # clip height follows progress
    assert "step = 1.0 / 15.0" in PLUGIN_SOURCE                        # ~0.25s open/close
    assert 'performSelector_withObject_afterDelay_("animStart:", None, 0.1)' in PLUGIN_SOURCE  # 0.1s beat


def test_coverage_sidebar_scripts_are_flat() -> None:
    # Scripts do NOT collapse — flat rows only (with_subs False); no subscript filter.
    assert 'build(data.get("byScript", []), True, "script", False)' in PLUGIN_SOURCE
    assert "subscript" not in PLUGIN_SOURCE


def test_coverage_sidebar_value_percent_toggle() -> None:
    # Total/% toggle is a small switch drawn in the Overall card header (on the master's
    # line), hit-tested via _pct_hit — no stray NSSwitch machinery remains.
    assert "self._pct_hit" in PLUGIN_SOURCE
    assert "controlAccentColor" in PLUGIN_SOURCE            # the ON track colour
    assert "self._show_percent" in PLUGIN_SOURCE
    assert "def _count_label(self" in PLUGIN_SOURCE
    assert "NSSwitch" not in PLUGIN_SOURCE
    assert "toggleValueMode" not in PLUGIN_SOURCE


def test_coverage_sidebar_double_click_shows_layers() -> None:
    # Double-clicking a colour segment opens that group+colour's glyphs into the
    # current tab; single click (left of the bar) still toggles the collapse.
    assert "def _show_group_color_layers(" in PLUGIN_SOURCE
    assert "tab.layers = layers" in PLUGIN_SOURCE
    assert "event.clickCount() >= 2" in PLUGIN_SOURCE
    assert "self._seg_hits" in PLUGIN_SOURCE
    assert "_show_group_color_layers(Glyphs.font" in PLUGIN_SOURCE


def test_coverage_sidebar_has_global_progress_bar() -> None:
    # A whole-master card (its header the master name) sits above the cards;
    # double-click on its bar opens every glyph of that colour (kind "all").
    assert "def _draw_global(self" in PLUGIN_SOURCE
    assert 'self._draw_global(_COV_TOP, width)' in PLUGIN_SOURCE
    assert '(title or "Overall").upper()' in PLUGIN_SOURCE          # master-named card header
    assert "font.selectedFontMaster.name" in PLUGIN_SOURCE          # title = the master
    assert '"all", None, None, color_key' in PLUGIN_SOURCE          # global seg hit meta
    assert 'if kind == "all":' in PLUGIN_SOURCE                     # matches every glyph


def test_coverage_sidebar_scripts_use_glyphs_icons() -> None:
    # Script rows show Glyphs' own sidebar icon (a "*Template.pdf" via imageNamed_).
    assert 'NSImage.imageNamed_(name)' in PLUGIN_SOURCE
    assert '"latin": "CapitalGTemplate"' in PLUGIN_SOURCE
    assert "def _script_icon(script_id" in PLUGIN_SOURCE
    assert "def _draw_icon(self" in PLUGIN_SOURCE
    assert 'elif kind == "script":' in PLUGIN_SOURCE and "_script_icon(key)" in PLUGIN_SOURCE


def test_coverage_sidebar_bars_show_hand_cursor() -> None:
    assert "def resetCursorRects(self" in PLUGIN_SOURCE
    assert "NSCursor.pointingHandCursor()" in PLUGIN_SOURCE
    assert "addCursorRect_cursor_" in PLUGIN_SOURCE
    assert "invalidateCursorRectsForView_(self)" in PLUGIN_SOURCE


def test_coverage_sidebar_subcategories_align_with_categories() -> None:
    # Sub-rows share the top-level name size + x, only lighter grey distinguishes them.
    marker = "# Same size + x as top-level names"
    tail = PLUGIN_SOURCE[PLUGIN_SOURCE.index(marker):][:260]
    assert "_COV_NAME_INDENT, 11.5, AppKit.NSColor.secondaryLabelColor()" in tail


def test_settings_pane_icon_uses_chosen_sf_symbol() -> None:
    # The Settings-pane icon renders Hugo's SF Symbol glyph (U+101082).
    assert "def _glyph_symbol_image(codepoint" in PLUGIN_SOURCE
    assert "_glyph_symbol_image(0x101082)" in PLUGIN_SOURCE


def test_coverage_sidebar_tab_icon_uses_sf_symbol() -> None:
    # Tab icon = Hugo's SF Symbol glyph (U+101082), rendered to a template image;
    # a drawn ring template is the fallback.
    block = _sidebar_block()
    assert "def tabBarImage(cls" in block
    assert "_glyph_symbol_image(0x101082)" in block
    assert "def _drawn_ring_icon(cls" in PLUGIN_SOURCE      # fallback
    assert "bezierPathWithOvalInRect_" in PLUGIN_SOURCE


def test_coverage_sidebar_has_color_legend() -> None:
    # A bottom-pinned, titleless 2-column legend grid of pill swatches, with a bottom margin.
    assert "class _AZLegendView(AppKit.NSView)" in PLUGIN_SOURCE
    assert "_COV_LEGEND_COLS = 2" in PLUGIN_SOURCE
    assert "_COV_LEGEND_BOTTOM" in PLUGIN_SOURCE            # margin below the legend card
    assert "swatch, sw_h / 2.0, sw_h / 2.0" in PLUGIN_SOURCE   # pill swatch
    assert "def heightForWidth_(self" in PLUGIN_SOURCE
    assert "NSViewMaxYMargin" in _sidebar_block()          # legend pinned to the bottom
    assert '"COLORS"' not in PLUGIN_SOURCE                 # no title on the legend card


def test_coverage_sidebar_color_focus_dims_others() -> None:
    # Clicking a legend swatch focuses that colour; the bars fade every other colour.
    assert "def focusColor_(self, color_key" in PLUGIN_SOURCE
    assert "owner.focusColor_(str(color_key))" in PLUGIN_SOURCE          # legend click -> controller
    assert "focus is not None and color_key != focus" in PLUGIN_SOURCE   # per-segment dim in _draw_bar


def test_sidebar_has_settings_gear() -> None:
    # The Edit-view sidebar has a gear button opening the Color Flow settings pane
    # (wired through the shared _icon_button helper's setAction_(action)).
    block = _sidebar_block()
    assert "btn.setAction_(action)" in block
    assert '"openSettings:"' in block
    assert "def openSettings_(self, sender" in block
    assert "_open_preferences_pane()" in block
    # The opener actually opens the window (selecting the tab alone won't front it).
    assert "def _open_settings_window(" in PLUGIN_SOURCE
    assert "performActionForItemAtIndex_" in PLUGIN_SOURCE


def test_sidebar_loadview_has_no_undefined_addsubview() -> None:
    # Regression guard: a refactor once left `container.addSubview_(gear)` after the
    # `gear` local was folded into a helper — a NameError crash on sidebar load that
    # neither ruff (blind to it behind `from ... import *`) nor the string tests caught.
    # Every name added to the container must be assigned somewhere in loadView.
    import ast
    load_view = next(
        node for node in ast.walk(ast.parse(PLUGIN_SOURCE))
        if isinstance(node, ast.FunctionDef) and node.name == "loadView"
        and any(getattr(call.func, "attr", "") == "setDocumentView_"
                for call in ast.walk(node) if isinstance(call, ast.Call))
    )
    assigned = {
        node.id for node in ast.walk(load_view)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    added = [
        call.args[0].id for call in ast.walk(load_view)
        if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "addSubview_"
        and call.args and isinstance(call.args[0], ast.Name)
    ]
    undefined = sorted(name for name in added if name not in assigned)
    assert not undefined, f"container.addSubview_ of undefined local(s): {undefined}"


def test_palette_archived_general_plugin_is_principal() -> None:
    # The docked palette is archived: a lightweight GeneralPlugin loader is the
    # principal class and runs the registrations; the palette class stays defined
    # (its code + tests intact) but Glyphs never instantiates it.
    assert "class AZColorflowLoader(GeneralPlugin):" in PLUGIN_SOURCE
    assert "class AZColorflow(PalettePlugin):" in PLUGIN_SOURCE
    loader = PLUGIN_SOURCE[
        PLUGIN_SOURCE.index("class AZColorflowLoader(GeneralPlugin):"):
        PLUGIN_SOURCE.index("class AZColorflow(PalettePlugin):")
    ]
    for register in ("_install_rainbow_menu", "_install_color_routing_hook",
                     "_register_native_shortcuts", "_register_preferences_pane",
                     "_register_coverage_sidebar"):
        assert register in loader, register
    # Info.plist points at the loader, and the bundle is a general plugin.
    info = (RESOURCES.parent / "Info.plist").read_text(encoding="utf-8")
    assert "<string>AZColorflowLoader</string>" in info
    assert RESOURCES.parent.parent.name == "AZ-Colorflow.glyphsPlugin"


def test_sidebar_has_global_report_button() -> None:
    # A sidebar report button builds the global report behind the rainbow loading
    # sheet (the same _AZColorflowLoaderBar the palette used), reusing the palette's
    # report icon (list.clipboard.fill) and the shared dashboard entry point.
    block = _sidebar_block()
    assert '"openReport:"' in block
    assert "def openReport_(self, sender" in block
    assert '"list.clipboard.fill"' in block
    assert "_AZColorflowLoaderBar.alloc()" in block                 # the loading window
    assert "beginSheet_completionHandler_" in block
    assert "def sidebarRunReport_(self, sender" in block
    assert "def sidebarFinishReport_(self, sender" in block
    assert "progress=_on_progress, open_when_done=False" in block   # bar tracks real build progress


def test_settings_pane_has_no_behaviour_section() -> None:
    # The "Behaviour" section (the swap-routing toggle) is gone from the settings pane.
    assert "Behaviour" not in PLUGIN_SOURCE
    assert "group.swapRouting" not in PLUGIN_SOURCE
    assert "group.behLabel" not in PLUGIN_SOURCE


def test_coverage_sidebar_disclosure_is_a_chevron() -> None:
    # Collapse marker is a thin stroked chevron (Hugo's icon), not a filled triangle.
    marker = PLUGIN_SOURCE[PLUGIN_SOURCE.index("def _draw_disclosure(self"):][:1000]
    assert "setLineCapStyle_" in marker and "path.stroke()" in marker
    assert "path.fill()" not in marker


def test_hosted_report_never_spins_the_host_main_thread_needlessly() -> None:
    # Report window: spin paused whenever the window is not key or occluded.
    sync = _method_body("_sync_spin_state")
    assert "occlusionState" in sync
    assert "isKeyWindow" in sync
    for selector in ("windowDidBecomeKey_", "windowDidResignKey_", "windowDidChangeOcclusionState_"):
        assert f"def {selector}(self, notification)" in PLUGIN_SOURCE
    assert "window.__cfdSpinPause && window.__cfdSpinPause(" in PLUGIN_SOURCE
