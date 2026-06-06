# encoding: utf-8
from __future__ import division, print_function, unicode_literals


#######################################################
#													  #
#	Color Flow Palette plugins						  #
#													  #
#	Read the docs: 									  #
#	https://github.com/HugoJourdan/Color-Flow         #
#													  #
#######################################################


import os
import AppKit

from datetime import datetime
from vanilla import *
from AppKit import NSMenuItem, NSOnState, NSOffState, NSCursor, NSClickGestureRecognizer, NSPanGestureRecognizer, NSGestureRecognizerStateBegan, NSGestureRecognizerStateChanged, NSGestureRecognizerStateEnded
from Foundation import NSObject
from GlyphsApp.plugins import *
from GlyphsApp.UI import *
from GlyphsApp import *

# Shared, GlyphsApp-free colorNames logic (also embedded into the shortcut
# scripts by tools/generate_shortcuts.py). Glyphs puts this bundle's Resources/
# dir on sys.path, so a plain absolute import works.
import colornames
import labelcolors
import colorflow_profile
import colorflow_filters
# Font-View colour grouping engine (the merged Rainbow FontView half).
import fontview



class ColorFlow(PalettePlugin):


	########################################################################################################
	#																									   #
	#	SETUP																					           #
	#																									   #
	########################################################################################################
	#																									   #
	#																									   #

	@objc.python_method
	def settings(self):
		self.name = 'Color Flow'
		self.init = False
		self.colorKeys = {
						"0":(0.85, 0.26, 0.06, 0.5),
						"1":(0.99, 0.62, 0.11, 0.5),
						"2":(0.65, 0.48, 0.20, 0.5),
						"3":(0.97, 0.90, 0.00, 0.5),
						"4":(0.67, 0.95, 0.38, 0.5),
						"5":(0.04, 0.57, 0.04, 0.5),
						"6":(0.06, 0.60, 0.98, 0.5),
						"7":(0.00, 0.20, 0.88, 0.5),
						"8":(0.50, 0.09, 0.79, 0.5),
						"9":(0.98, 0.36, 0.67, 0.5),
						"10":(0.50, 0.50, 0.50, 0.5),
						"11":(0.25, 0.25, 0.25, 0.5)
						}
		# Override the hardcoded defaults with the user's Glyphs label colours
		# (read live; the dict above is the fallback). Alpha stays at the palette's
		# 0.5 convention so only the hue follows the label colour.
		try:
			self.colorKeys = self._label_color_keys()
		except Exception:
			pass
		# A colorNames.txt problem must never crash plugin load — degrade to an
		# empty palette instead of taking the whole plugin down.
		try:
			self.meaning = self.Load_Meaning()
		except Exception as error:
			print(f"Color Flow: could not load colorNames.txt ({error}); starting empty.")
			self.meaning = {}
		self.width = 160
		self.rectHeight = 10
		self.lineSpacing = 20
		self.shift = 10
		self.barWidth = self.width+6
		self.height = 19 * len([x for x in self.meaning.values() if x]) + 8
		self.xPos = 0  # progress bar flush to the left edge (no margin)

		self.paletteView = Window((self.width, self.height + 10))
		self.paletteView.frame = Group((0, 0, self.width, self.height))

		# Eye toggle: enter an inline visibility-edit mode (show every colour; click
		# a row to stage show/hide; press again to apply + collapse to visible-only).
		self._eye_mode = False
		self._eye_rows = None
		self._eye_none = ""
		self._eyeRowViews = {}

		# Separator lines + colour tags (depend on the meaning order/visibility).
		# Per-row widgets (label / bar / count) are built by Update_Plugin_UI.
		self._rowChecks = {}
		self._focusColor = None
		self._countBoxes = {}
		self._build_static_rows()

		# # Select a master if none is selected
		# if not self.font.selectedFontMaster:
		# 	self.font.selectedFontMaster = self.font.masters[0]

		# Needed to display the palette plugin
		self.dialog = self.paletteView.frame.getNSView()

		# Drive the palette height with an animatable height constraint so growing /
		# shrinking (e.g. entering/leaving eye mode) slides instead of snapping.
		# Glyphs pins the view's width + position; we own the height.
		try:
			self.dialog.setTranslatesAutoresizingMaskIntoConstraints_(False)
			self._heightConstraint = AppKit.NSLayoutConstraint.constraintWithItem_attribute_relatedBy_toItem_attribute_multiplier_constant_(
				self.dialog, AppKit.NSLayoutAttributeHeight, AppKit.NSLayoutRelationEqual, None, 0, 1.0, self.height)
			self.dialog.addConstraint_(self._heightConstraint)
		except Exception:
			self._heightConstraint = None

	# Separator lines + colour tags from the current meaning (order + visibility).
	# {"0".."11": (r, g, b, 0.5)} from the user's Glyphs label colours, keeping the
	# palette's 0.5 alpha so only the hue follows the label colour.
	@objc.python_method
	def _label_color_keys(self):
		colors = labelcolors.read_label_colors()
		return {str(index): (rgba[0], rgba[1], rgba[2], 0.5) for index, rgba in enumerate(colors)}

	@objc.python_method
	def _build_static_rows(self):
		yPos = 6
		for k in self.meaning.keys():
			setattr(self.paletteView.frame, str(k)+"line", HorizontalLine((0, yPos, 0, 1)))
			yPos += 19
		yPos = 17
		for k, v in self.meaning.items():
			if v:
				setattr(self.paletteView.frame, str(k)+"colorTag", Box((0, yPos-self.shift-1, 6, 19), fillColor=(AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(k)])), cornerRadius=0, borderWidth=0))
				yPos += 19

	# Open the Settings panel (reorder colours + choose which show).
	@objc.python_method
	def Open_Settings(self, sender):
		try:
			import importlib
			import settings_panel
			importlib.reload(settings_panel)
			self._settingsWindow = settings_panel.ColorFlowSettings(self, Glyphs.font)
		except Exception:
			import traceback
			print("Color Flow [settings] error:\n" + traceback.format_exc())

	# Re-read colorNames.txt and rebuild the palette after a Settings-panel save.
	@objc.python_method
	def reload_after_settings(self):
		self.meaning = self.Load_Meaning()
		for i in range(12):
			for suffix in ("line", "colorTag", "", "box", "count", "hl", "focus", "eye", "eyeTag", "eyeLine"):
				attr = str(i) + suffix
				if hasattr(self.paletteView.frame, attr):
					delattr(self.paletteView.frame, attr)
		self.height = 19 * len([x for x in self.meaning.values() if x]) + 8
		self._build_static_rows()
		try:
			self._set_palette_height(self.height, animated=True)
		except Exception:
			pass
		self._lastSignature = None
		self.Update_Plugin_UI()
		try:
			font = Glyphs.font
			if getattr(self, "fontview", None) is not None and font is not None and self.fontview.is_enabled(font):
				self.fontview.maybe_rebuild(font)
		except Exception:
			pass


	@objc.python_method
	def start(self):
		Glyphs.addCallback(self.update, UPDATEINTERFACE)
		try:
			Glyphs.addCallback(self.contextMenuHandler, CONTEXTMENUCALLBACK)
		except Exception:
			pass
		self.font = Glyphs.font
		self.init = False
		self.update(self._windowController)

		# Font-View colour grouping (the merged Rainbow FontView half). Opt-in and
		# fully wrapped so a problem here can never stop the palette from loading.
		self.fontview = fontview.FontViewGrouping()
		self._pendingFont = None
		self._strippedForSave = False
		try:
			self._install_rainbow_menu()
			self._install_settings_menu()
			self._rainbow_conflict_check()
		except Exception:
			import traceback
			print("Color Flow [Rainbow setup] error:\n" + traceback.format_exc())
		try:
			self.performSelector_withObject_afterDelay_("deferredHeaderSetup:", None, 2.0)
		except Exception:
			pass

		# Keep our grouping glyphOrder OUT of the saved .glyphs file: strip it
		# just before each save, restore it after. Glyphs has no DOCUMENTWILLSAVE
		# callback, so observe Cocoa's NSDocument save notifications.
		try:
			from Foundation import NSNotificationCenter
			center = NSNotificationCenter.defaultCenter()
			center.addObserver_selector_name_object_(self, "documentWillSave:", "NSDocumentWillSaveNotification", None)
			center.addObserver_selector_name_object_(self, "documentDidSave:", "NSDocumentDidSaveNotification", None)
		except Exception:
			pass


	########################################################################################################
	#																									   #
	#	RAINBOW FONT VIEW																			       #
	#																									   #
	########################################################################################################

	@objc.python_method
	def _rainbow_menu_title(self):
		return "Color Flow: Font Glyph Order"

	# Action popover: the Dashboard and a Disable/Glyph/Layer segmented control
	# for the Font Glyph Order grouping. Replaces the old ⋯ menu.
	@objc.python_method
	def Open_Action_Popover(self, sender):
		try:
			self._popover = FloatingWindow((220, 516), "Color Flow Settings")
			popover = self._popover
			popover.dashboard = Button((12, 12, -12, 22), "Open Color Font Dashboard",
				callback=self._popover_dashboard, sizeStyle='small')
			popover.fgoLabel = TextBox((12, 46, -12, 16), "Font Glyph Order",
				sizeStyle='small')
			popover.rainbow = SegmentedButton((12, 66, -12, 22),
				[dict(title="Disable"), dict(title="Glyph"), dict(title="Layer")],
				callback=self._popover_rainbow, sizeStyle='small')
			popover.rainbow.set(self._rainbow_segment_index())
			popover.lcSep = HorizontalLine((12, 96, -12, 1))
			self._labelColorsEdited = False
			popover.lcLabel = TextBox((12, 104, -90, 16), "Labels & Colours", sizeStyle='small')
			popover.lcReset = Button((-82, 102, 70, 18), "Reset", callback=self._label_colors_reset, sizeStyle='mini')
			self._labelWells = []
			self._labelFields = {}
			rgbaList = labelcolors.read_label_colors()
			try:
				settingsText = colornames.read_color_names(colornames.get_key_file(self._font_dir(Glyphs.font))) or colornames.DEFAULT_COLOR_NAMES
			except Exception:
				settingsText = colornames.DEFAULT_COLOR_NAMES
			labelRows, _noneLabel = colornames.parse_settings(settingsText)
			labelByIndex = {index: label for index, label, _visible in labelRows}
			for index in range(12):
				rowY = 128 + index * 26
				wellColor = AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(*rgbaList[index])
				well = ColorWell((12, rowY, 26, 22), callback=self._label_color_changed, color=wellColor)
				setattr(popover, "lcWell%d" % index, well)
				self._labelWells.append(well)
				field = EditText((44, rowY, -12, 22), labelByIndex.get(index, ""),
					callback=self._label_name_changed, continuous=False, sizeStyle='small')
				setattr(popover, "lcField%d" % index, field)
				self._labelFields[index] = field
			profileY = 128 + 12 * 26 + 6
			popover.profileSep = HorizontalLine((12, profileY, -12, 1))
			popover.profileExport = Button((12, profileY + 8, 98, 22), "Export Profile…",
				callback=self._export_profile, sizeStyle='small')
			popover.profileImport = Button((114, profileY + 8, -12, 22), "Import Profile…",
				callback=self._import_profile, sizeStyle='small')
			popover.smartFilters = Button((12, profileY + 36, -12, 22), "Generate Smart Filters",
				callback=self._generate_smart_filters, sizeStyle='small')
			try:
				popover.bind("close", self._popover_did_close)
			except Exception:
				pass
			popover.open()
		except Exception:
			import traceback
			print("Color Flow [popover] error:\n" + traceback.format_exc())

	# Current grouping state -> segment index (0 Disable / 1 Glyph / 2 Layer).
	@objc.python_method
	def _rainbow_segment_index(self):
		font = Glyphs.font
		if font is None or not self.fontview.is_enabled(font):
			return 0
		return 1 if self.fontview.mode(font) == "Glyph" else 2

	# Popover closed and the user edited at least one label colour: prompt for the
	# Glyphs restart its own views need (Color Flow already updated live).
	@objc.python_method
	def _popover_did_close(self, sender):
		if getattr(self, "_labelColorsEdited", False):
			self._labelColorsEdited = False
			Message("Restart Glyphs for the new label colours to take effect in its "
				"own Font and Edit views. Color Flow already updated.", title="Color Flow")

	@objc.python_method
	def _close_popover(self):
		popover = getattr(self, "_popover", None)
		if popover is not None:
			try:
				popover.close()
			except Exception:
				pass
			self._popover = None

	# Gather all twelve wells -> write LabelColors, best-effort live-refresh the
	# app, and refresh Color Flow's own swatches immediately.
	@objc.python_method
	def _label_color_changed(self, sender):
		try:
			colors = []
			for well in getattr(self, "_labelWells", []):
				native = well.get()
				rgb = native.colorUsingColorSpaceName_("NSCalibratedRGBColorSpace") or native
				colors.append((rgb.redComponent(), rgb.greenComponent(),
					rgb.blueComponent(), rgb.alphaComponent()))
			if len(colors) == 12:
				labelcolors.write_label_colors(colors)
				labelcolors.refresh_app_label_colors(colors)
				self._labelColorsEdited = True
				self.colorKeys = self._label_color_keys()
				self.reload_after_settings()
		except Exception:
			import traceback
			print("Color Flow [label colour] error:\n" + traceback.format_exc())

	# Rename workflow labels from the settings window: gather all 12 fields and
	# rewrite colorNames.txt (a non-empty field = visible, empty = hidden),
	# preserving the colour order + the None label.
	@objc.python_method
	def _label_name_changed(self, sender):
		try:
			font = Glyphs.font
			path = colornames.get_key_file(self._font_dir(font))
			text = colornames.read_color_names(path) or colornames.DEFAULT_COLOR_NAMES
			rows, noneLabel = colornames.parse_settings(text)
			fields = getattr(self, "_labelFields", {})
			newRows = []
			for index, label, visible in rows:
				field = fields.get(index)
				if field is not None:
					newLabel = field.get().strip()
					newRows.append((index, newLabel, bool(newLabel)))
				else:
					newRows.append((index, label, visible))
			colornames.write_color_names(path, colornames.render_settings(newRows, noneLabel))
			self.meaning = self.Load_Meaning()
			self._lastSignature = None
			self.Update_Plugin_UI()
			try:
				if getattr(self, "fontview", None) and font is not None and self.fontview.is_enabled(font):
					self.fontview.maybe_rebuild(font)
			except Exception:
				pass
		except Exception:
			import traceback
			print("Color Flow [rename label] error:\n" + traceback.format_exc())

	@objc.python_method
	def _label_colors_reset(self, sender):
		try:
			labelcolors.reset_label_colors()
			rgbaList = labelcolors.read_label_colors()
			for index, well in enumerate(getattr(self, "_labelWells", [])):
				well.set(AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(*rgbaList[index]))
			labelcolors.refresh_app_label_colors(rgbaList)
			self.colorKeys = self._label_color_keys()
			self.reload_after_settings()
		except Exception:
			import traceback
			print("Color Flow [label reset] error:\n" + traceback.format_exc())

	# ------------------------------------------------------------------ workflow profiles (.colorflow)

	@objc.python_method
	def _live_profile(self, font, font_dir, name=""):
		# Gather the current Color Flow config into a portable profile dict.
		color_names = colornames.read_color_names(colornames.get_key_file(font_dir))
		source = self.fontview.mode(font) if font is not None else "Layer"
		return colorflow_profile.build_profile(
			color_names=color_names, free_mode=self._free_mode(), rainbow_source=source,
			label_colors=labelcolors.read_label_colors(), name=name)

	@objc.python_method
	def _font_dir(self, font):
		return os.path.dirname(font.filepath) if (font is not None and font.filepath) else None

	@objc.python_method
	def _export_profile(self, sender):
		try:
			font = Glyphs.font
			family = (font.familyName if font is not None else "") or "Color Flow profile"
			profile = self._live_profile(font, self._font_dir(font), name=family)
			path = GetSaveFile("Export Color Flow profile", "Color-Flow-Profile.json", ["json"])
			if not path:
				return
			with open(path, "w", encoding="utf-8") as handle:
				handle.write(colorflow_profile.serialize(profile))
			Message("Saved Color Flow profile.", title="Color Flow")
		except Exception:
			import traceback
			print("Color Flow [export profile] error:\n" + traceback.format_exc())

	@objc.python_method
	def _import_profile(self, sender):
		try:
			path = GetOpenFile("Import Color Flow profile", False, ["json", "colorflow"])
			if not path:
				return
			with open(path, "r", encoding="utf-8") as handle:
				incoming = colorflow_profile.parse(handle.read())
			font = Glyphs.font
			font_dir = self._font_dir(font)
			diffs = colorflow_profile.diff_profile(self._live_profile(font, font_dir), incoming)
			if not self._confirm_import(incoming, diffs):
				return
			self._apply_profile(incoming, font, font_dir)
		except ValueError as error:
			Message(str(error), title="Color Flow")
		except Exception:
			import traceback
			print("Color Flow [import profile] error:\n" + traceback.format_exc())

	@objc.python_method
	def _confirm_import(self, incoming, diffs):
		# Surface what will change before applying, so a shared profile never
		# silently overwrites local choices.
		if diffs:
			shown = diffs[:12]
			summary = "\n".join("• %s: %s" % (d["field"], d["detail"]) for d in shown)
			if len(diffs) > len(shown):
				summary += "\n• …and %d more" % (len(diffs) - len(shown))
			info = "Importing “%s” will change:\n\n%s" % (incoming.get("name", "profile"), summary)
		else:
			info = "This profile matches your current settings."
		alert = AppKit.NSAlert.alloc().init()
		alert.setMessageText_("Import Color Flow profile?")
		alert.setInformativeText_(info)
		alert.addButtonWithTitle_("Apply")
		alert.addButtonWithTitle_("Cancel")
		return alert.runModal() == AppKit.NSAlertFirstButtonReturn

	@objc.python_method
	def _apply_profile(self, incoming, font, font_dir):
		colornames.write_color_names(colornames.get_key_file(font_dir), incoming.get("colorNames", ""))
		Glyphs.defaults["com.hugojourdan.ColorFlow-FreeMode"] = bool(incoming.get("freeMode"))
		if font is not None:
			self.fontview.set_mode(font, incoming.get("rainbowSource", "Layer"))
		colors = [tuple(rgba) for rgba in incoming.get("labelColors", [])]
		if len(colors) == 12:
			labelcolors.write_label_colors(colors)
			labelcolors.refresh_app_label_colors(colors)
		self.colorKeys = self._label_color_keys()
		self.reload_after_settings()
		Message("Imported Color Flow profile. Restart Glyphs if the label colours do not "
			"update in its own Font and Edit views.", title="Color Flow")

	@objc.python_method
	def _generate_smart_filters(self, sender):
		# Build a "Color Flow" smart-filter group (one filter per visible step +
		# None) and merge it into the font's Filters parameter. Filters match the
		# GLYPH colour — Glyphs has no per-master layer-colour predicate.
		try:
			font = Glyphs.font
			if font is None:
				Message("Open a font first.", title="Color Flow")
				return
			meaning = self.Load_Meaning()
			steps = [(int(index), label)
				for index, label in colornames.visible_labels(meaning).items()]
			text = colornames.read_color_names(colornames.get_key_file(self._font_dir(font)))
			none_label = colornames.parse_settings(text)[1] or "None"
			group = colorflow_filters.build_filter_group(steps, none_label)
			existing = [dict(entry) for entry in (font.customParameters["Filters"] or [])]
			font.customParameters["Filters"] = colorflow_filters.merge_into_filters(existing, group)
			Message("Added the “Color Flow” smart-filter group to the sidebar "
				"(filters by glyph colour).", title="Color Flow")
		except Exception:
			import traceback
			print("Color Flow [smart filters] error:\n" + traceback.format_exc())

	@objc.python_method
	def _popover_dashboard(self, sender):
		self._close_popover()
		self.Open_Color_Font_Dashboard(sender)

	# Disable / Glyph / Layer for the Font Glyph Order grouping (popover stays open
	# so the source can be switched without reopening).
	@objc.python_method
	def _popover_rainbow(self, sender):
		font = Glyphs.font
		if font is None:
			return
		segment = sender.get()
		try:
			if segment == 0:
				if self.fontview.is_enabled(font):
					self.fontview.disable(font)
			else:
				self.fontview.set_mode(font, "Glyph" if segment == 1 else "Layer")
				if not self.fontview.is_enabled(font):
					self.fontview.enable(font)
		except Exception:
			import traceback
			print("Color Flow [rainbow] error:\n" + traceback.format_exc())

	@objc.python_method
	def _install_rainbow_menu(self):
		# Add a File-menu toggle, removing any stale copy from a previous load.
		title = self._rainbow_menu_title()
		self._rainbowMenuItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
			title, self.toggleRainbow_, "")
		self._rainbowMenuItem.setTarget_(self)
		barItem = Glyphs.menu[FILE_MENU]
		submenu = barItem.submenu() if hasattr(barItem, "submenu") else None
		if submenu is not None:
			for item in list(submenu.itemArray()):
				if item.title() == title:
					submenu.removeItem_(item)
			submenu.addItem_(self._rainbowMenuItem)
		else:
			barItem.append(self._rainbowMenuItem)

	@objc.python_method
	def _teardown_rainbow_menu(self):
		try:
			title = self._rainbow_menu_title()
			barItem = Glyphs.menu[FILE_MENU]
			submenu = barItem.submenu() if hasattr(barItem, "submenu") else None
			if submenu is not None:
				for item in list(submenu.itemArray()):
					if item.title() == title:
						submenu.removeItem_(item)
		except Exception:
			pass

	@objc.python_method
	def _install_settings_menu(self):
		title = "Color Flow settings\u2026"
		self._settingsMenuItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, self.openSettings_, "")
		self._settingsMenuItem.setTarget_(self)
		barItem = Glyphs.menu[EDIT_MENU]
		submenu = barItem.submenu() if hasattr(barItem, "submenu") else None
		if submenu is not None:
			for item in list(submenu.itemArray()):
				if item.title() == title:
					submenu.removeItem_(item)
			submenu.addItem_(self._settingsMenuItem)
		else:
			barItem.append(self._settingsMenuItem)

	@objc.python_method
	def _teardown_settings_menu(self):
		try:
			barItem = Glyphs.menu[EDIT_MENU]
			submenu = barItem.submenu() if hasattr(barItem, "submenu") else None
			if submenu is not None:
				for item in list(submenu.itemArray()):
					if item.title() == "Color Flow settings\u2026":
						submenu.removeItem_(item)
		except Exception:
			pass

	def openSettings_(self, sender):
		try:
			self.Open_Action_Popover(None)
		except Exception:
			import traceback
			print("Color Flow [settings menu] error:\n" + traceback.format_exc())

	@objc.python_method
	def _rainbow_conflict_check(self):
		# Warn once if the standalone Rainbow FontView is still installed (two
		# plugins fighting over glyphOrder would conflict).
		if Glyphs.defaults["com.hugojourdan.ColorFlow-RainbowConflictWarned"]:
			return
		barItem = Glyphs.menu[FILE_MENU]
		submenu = barItem.submenu() if hasattr(barItem, "submenu") else None
		if submenu is None:
			return
		for item in list(submenu.itemArray()):
			if item.title() == "Rainbow FontView":
				Message(
					"The standalone Rainbow FontView plugin is still installed.\n\n"
					"Color Flow now includes Font-View grouping, so please disable or "
					"remove Rainbow FontView to avoid them conflicting.",
					title="Color Flow", OKButton=None)
				Glyphs.defaults["com.hugojourdan.ColorFlow-RainbowConflictWarned"] = True
				return

	# --- ObjC selectors (no python_method decorator: called by menu / timer) ---

	def validateMenuItem_(self, menuItem):
		font = Glyphs.font
		if font is None:
			menuItem.setState_(NSOffState)
			return False
		try:
			menuItem.setState_(NSOnState if self.fontview.is_enabled(font) else NSOffState)
		except Exception:
			menuItem.setState_(NSOffState)
		return True

	def toggleRainbow_(self, sender):
		self.Toggle_Rainbow(sender)

	def rainbowDebouncedRebuild_(self, sender):
		font = self._pendingFont or Glyphs.font
		self._pendingFont = None
		if font is None:
			return
		try:
			if self.fontview.is_enabled(font):
				self.fontview.maybe_rebuild(font)
		except Exception:
			import traceback
			print("Color Flow [Rainbow rebuild] error:\n" + traceback.format_exc())

	# --- keep our grouping order out of saved files (Cocoa save notifications) ---

	def documentWillSave_(self, notification):
		self._strippedForSave = False
		try:
			font = self._font_from_document(notification.object())
			if font is not None and getattr(self, "fontview", None) is not None:
				self._strippedForSave = bool(self.fontview.strip_for_save(font))
		except Exception:
			import traceback
			print("Color Flow [will-save] error:\n" + traceback.format_exc())

	def documentDidSave_(self, notification):
		try:
			document = notification.object()
			font = self._font_from_document(document)
			if (font is not None and getattr(self, "fontview", None) is not None
					and getattr(self, "_strippedForSave", False)):
				self.fontview.restore_after_save(font)
				try:
					document.updateChangeCount_(2)  # NSChangeCleared: re-add is transient
				except Exception:
					pass
		except Exception:
			import traceback
			print("Color Flow [did-save] error:\n" + traceback.format_exc())
		self._strippedForSave = False
		try:
			document = notification.object()
			self._record_dashboard_history(self._font_from_document(document))
		except Exception:
			import traceback
			print("Color Flow [history] error:\n" + traceback.format_exc())

	@objc.python_method
	def _record_dashboard_history(self, font):
		# Passively accrue a dated per-glyph snapshot on every save so the
		# dashboard's burndown / forecast / journey have a timeline to read,
		# whether or not the dashboard was ever opened. Stored in Glyphs.defaults.
		if font is None or not getattr(font, "filepath", None):
			return
		import colorflow_dashboard
		snapshot = colorflow_dashboard.build_master_glyph_colors(font)
		colorflow_dashboard.record_history(font, snapshot, datetime.now())

	@objc.python_method
	def _font_from_document(self, document):
		if document is None:
			return None
		font = getattr(document, "font", None)
		if callable(font):
			try:
				font = document.font()
			except Exception:
				font = None
		if font is None and hasattr(document, "glyphs") and hasattr(document, "userData"):
			font = document  # the notification object is already a GSFont
		return font

	# --- python callbacks (action menu + the ObjC toggle target) ---

	@objc.python_method
	def Toggle_Rainbow(self, sender):
		font = Glyphs.font
		if font is None:
			return
		try:
			self.fontview.toggle(font)
		except Exception:
			import traceback
			print("Color Flow [Rainbow toggle] error:\n" + traceback.format_exc())

	# ------------------------------------------------------------------ inline label rename

	@objc.python_method
	def _ns_button(self, check):
		if hasattr(check, "getNSButton"):
			return check.getNSButton()
		return check._nsObject

	# ObjC selector fired by the per-row double-click gesture recognizer.
	def labelDoubleClicked_(self, sender):
		try:
			view = sender.view()
			for color, checkbox in getattr(self, "_rowChecks", {}).items():
				if self._ns_button(checkbox) == view:
					self._begin_rename(color)
					return
		except Exception:
			import traceback
			print("Color Flow [rename] error:\n" + traceback.format_exc())

	@objc.python_method
	def _begin_rename(self, color):
		self._cancel_rename()
		self.Update_Plugin_UI()  # rebuild a clean row before overlaying the editor
		checkbox = getattr(self, "_rowChecks", {}).get(color)
		if checkbox is None:
			return
		try:
			rowY = checkbox.getPosSize()[1]
		except Exception:
			return
		# Hide the label text + count so they don't show through the editor.
		try:
			checkbox.set("")
		except Exception:
			pass
		countAttr = str(color) + "count"
		if hasattr(self.paletteView.frame, countAttr):
			delattr(self.paletteView.frame, countAttr)
		editor = EditText((32, rowY, -8, 20), self.meaning.get(color, ""),
			callback=self._commit_rename, continuous=False, sizeStyle='small')
		setattr(self.paletteView.frame, "renameEditor", editor)
		self._renameColor = color
		try:
			field = editor.getNSTextField()
			field.window().makeFirstResponder_(field)
		except Exception:
			pass

	@objc.python_method
	def _commit_rename(self, sender):
		color = getattr(self, "_renameColor", None)
		self._renameColor = None
		if color is None:
			self._cancel_rename()
			return
		newLabel = sender.get().strip()

		font = Glyphs.font
		fontDir = None
		if font is not None and font.filepath:
			fontDir = os.path.dirname(font.filepath)
		path = colornames.resolve_key_file(fontDir)
		text = colornames.read_color_names(path) or colornames.DEFAULT_COLOR_NAMES
		meaningInt, orderInt, _ = colornames.parse_key_file(text)
		intColor = int(color)
		if newLabel:
			meaningInt[intColor] = newLabel
			if intColor not in orderInt:
				orderInt.append(intColor)
		colornames.write_color_names(path, colornames.render_key_file(meaningInt, orderInt))

		self._cancel_rename()
		self.meaning = self.Load_Meaning()
		self._lastSignature = None
		self.Update_Plugin_UI()
		try:
			if getattr(self, "fontview", None) and font is not None and self.fontview.is_enabled(font):
				self.fontview.maybe_rebuild(font)
		except Exception:
			pass

	@objc.python_method
	def _cancel_rename(self):
		if hasattr(self.paletteView.frame, "renameEditor"):
			try:
				delattr(self.paletteView.frame, "renameEditor")
			except Exception:
				pass


	########################################################################################################
	#																									   #
	#	DATA + UI 																				           #
	#																									   #
	########################################################################################################
	#																									   #
	#																									   #

	# ------------------------------------------------------------------ derived data (tempData)

	# --- mode: contiguous "step" (default, nothing saved in the file) vs "free"
	# (independent checkboxes, stored per-layer in userData). ---
	@objc.python_method
	def _free_mode(self):
		return bool(Glyphs.defaults["com.hugojourdan.ColorFlow-FreeMode"])

	# A layer's checkbox state, derived from its colour. Free mode is single-
	# select (only the matching colour); step mode is the contiguous run.
	@objc.python_method
	def _layer_state(self, layer, order):
		if self._free_mode():
			return colornames.exclusive_state_for_color(layer.color, order)
		return colornames.checked_state_for_color(layer.color, order)

	# Per-step counts for a master, derived from native layer colours. Nothing
	# Color Flow tracks is saved in the .glyphs file, in either mode.
	@objc.python_method
	def _derive_counts(self, masterId):
		order = list(self.meaning.keys())
		colors = []
		for glyph in self.font.glyphs:
			layer = glyph.layers[masterId]
			colors.append(layer.color if layer is not None else None)
		if self._free_mode():
			return colornames.single_counts_from_colors(colors, order)
		return colornames.counts_from_colors(colors, order)

	@objc.python_method
	def _counts(self, masterId):
		key = "com.hugojourdan.ColorFlow-counts-" + masterId
		counts = self.font.tempData[key]
		if not hasattr(counts, "keys"):
			counts = self._derive_counts(masterId)
			self.font.tempData[key] = counts
		return counts

	@objc.python_method
	def _invalidate_counts(self, masterId):
		self.font.tempData["com.hugojourdan.ColorFlow-counts-" + masterId] = None

	# Attach the double-click-to-rename and drag-to-reorder gestures to a freshly
	# built checkbox and remember which colour it is (widgets rebuild each refresh).
	@objc.python_method
	def _attach_rename(self, checkbox, color):
		self._rowChecks[color] = checkbox
		button = self._ns_button(checkbox)
		# Single-click a row opens that step's glyphs (rename now lives in
		# Edit ▸ Color Flow settings, not on the palette).
		try:
			singleClick = NSClickGestureRecognizer.alloc().initWithTarget_action_(self, "rowClicked:")
			singleClick.setNumberOfClicksRequired_(1)
			button.addGestureRecognizer_(singleClick)
		except Exception:
			pass
		# NOTE: do NOT set a Python attribute on the recognizer (e.g.
		# pan._cf_color) — PyObjC framework objects have no __dict__, so it
		# raises AttributeError and (when wrapped in try/except) silently
		# prevents the gesture from ever being attached. The colour is resolved
		# in colorDragged_ by matching the recognizer's view, exactly like the
		# double-click handler does.
		try:
			pan = NSPanGestureRecognizer.alloc().initWithTarget_action_(self, "colorDragged:")
			button.addGestureRecognizer_(pan)
		except Exception:
			import traceback
			print("Color Flow [attach pan] error:\n" + traceback.format_exc())

	# Resolve which colour-row a gesture recognizer is attached to (its view is
	# the row's checkbox NSButton).
	@objc.python_method
	def _color_for_recognizer(self, recognizer):
		view = recognizer.view()
		for color, checkbox in getattr(self, "_rowChecks", {}).items():
			if self._ns_button(checkbox) == view:
				return color
		return None

	# Drag a row to reorder the colours: the dragged colour is dropped onto the
	# row currently under the pointer (cursor-position targeting, so it always
	# follows the mouse regardless of the view's coordinate flip). A grabbing-hand
	# cursor shows while dragging. Reorder + persist on release.
	def colorDragged_(self, recognizer):
		try:
			state = recognizer.state()
			if state == NSGestureRecognizerStateBegan:
				self._push_drag_cursor()
				self._begin_drag_feedback(self._color_for_recognizer(recognizer))
				return
			if state == NSGestureRecognizerStateChanged:
				self._lastDragTime = datetime.now()  # suppress the end-of-drag toggle
				try:
					NSCursor.closedHandCursor().set()
				except Exception:
					pass
				color = self._color_for_recognizer(recognizer)
				dst = self._drop_index(recognizer)
				if color is not None and dst is not None:
					self._update_drop_line(color, dst)
				return
			# Ended / Cancelled / Failed (state >= Ended): restore cursor + clear feedback.
			self._pop_drag_cursor()
			self._clear_drag_feedback()
			if state != NSGestureRecognizerStateEnded:
				return
			color = self._color_for_recognizer(recognizer)
			if color is None:
				return
			dst = self._drop_index(recognizer)
			if dst is not None:
				self._reorder_color_to(color, dst)
		except Exception:
			import traceback
			self._pop_drag_cursor()
			self._clear_drag_feedback()
			print("Color Flow [drag] error:\n" + traceback.format_exc())

	# The visible-row index under the pointer right now (flip-safe).
	@objc.python_method
	def _drop_index(self, recognizer):
		frameView = self.paletteView.frame.getNSView()
		point = recognizer.locationInView_(frameView)
		y = point.y
		try:
			if not frameView.isFlipped():
				y = frameView.bounds().size.height - y
		except Exception:
			pass
		return self._row_index_at_point(y)

	# Top y (flipped coords) of a visible row band, matching the colour-bar offset.
	@objc.python_method
	def _row_top(self, index):
		visible = list(self.meaning.keys())
		if not (0 <= index < len(visible)):
			return None
		checkbox = self._rowChecks.get(visible[index])
		if checkbox is None:
			return None
		try:
			return checkbox.getPosSize()[1] - 1
		except Exception:
			return None

	# Live drag highlight: tint the dragged row blue + show a blue insertion line.
	@objc.python_method
	def _begin_drag_feedback(self, color):
		self._clear_drag_feedback()
		if color is None:
			return
		visible = list(self.meaning.keys())
		key = str(color)
		if key not in visible:
			return
		top = self._row_top(visible.index(key))
		if top is None:
			return
		tint = AppKit.NSColor.colorWithRed_green_blue_alpha_(0.16, 0.5, 0.96, 0.22)
		line = AppKit.NSColor.colorWithRed_green_blue_alpha_(0.13, 0.45, 0.96, 1.0)
		self.paletteView.frame.dragHighlight = Box((0, top, self.width, 19), fillColor=tint, cornerRadius=0, borderWidth=0)
		self.paletteView.frame.dropLine = Box((0, top, self.width, 2), fillColor=line, cornerRadius=0, borderWidth=0)

	# Move the insertion line to the slot the dragged colour would drop into.
	@objc.python_method
	def _update_drop_line(self, color, dst):
		if not hasattr(self.paletteView.frame, "dropLine"):
			return
		visible = list(self.meaning.keys())
		key = str(color)
		if key not in visible:
			return
		src = visible.index(key)
		top = self._row_top(dst)
		if top is None:
			return
		lineY = top + 22 if dst > src else top
		try:
			self.paletteView.frame.dropLine.setPosSize((0, lineY, self.width, 2))
		except Exception:
			pass

	@objc.python_method
	def _clear_drag_feedback(self):
		for attr in ("dragHighlight", "dropLine"):
			if hasattr(self.paletteView.frame, attr):
				try:
					delattr(self.paletteView.frame, attr)
				except Exception:
					pass

	# Grabbing-hand cursor while dragging (push once, pop once — flag-balanced).
	@objc.python_method
	def _push_drag_cursor(self):
		if getattr(self, "_cursorPushed", False):
			return
		try:
			NSCursor.closedHandCursor().push()
			self._cursorPushed = True
		except Exception:
			pass

	@objc.python_method
	def _pop_drag_cursor(self):
		if not getattr(self, "_cursorPushed", False):
			return
		try:
			NSCursor.pop()
		except Exception:
			pass
		self._cursorPushed = False

	# Which visible row sits under a y-coordinate (in the frame view's flipped
	# coords, top-down): the row whose checkbox vertical centre is nearest.
	@objc.python_method
	def _row_index_at_point(self, y):
		visible = list(self.meaning.keys())
		bestIndex = None
		bestDist = None
		for index, key in enumerate(visible):
			checkbox = self._rowChecks.get(key)
			if checkbox is None:
				continue
			try:
				_, top, _, height = checkbox.getPosSize()
			except Exception:
				continue
			center = top + (height / 2.0)
			dist = abs(center - y)
			if bestDist is None or dist < bestDist:
				bestIndex, bestDist = index, dist
		return bestIndex

	# Move `color` to absolute position `dst` among the visible colours; persist.
	@objc.python_method
	def _reorder_color_to(self, color, dst):
		visible = list(self.meaning.keys())
		key = str(color)
		if key not in visible:
			return
		src = visible.index(key)
		dst = max(0, min(len(visible) - 1, dst))
		if dst == src:
			return
		visible.insert(dst, visible.pop(src))
		self._write_order(visible)
		self.reload_after_settings()

	# Write colorNames.txt with the visible colours in `new_order`, preserving
	# each colour's label + the hidden colours.
	@objc.python_method
	def _write_order(self, new_order):
		fontDir = None
		font = Glyphs.font
		if font is not None and font.filepath:
			fontDir = os.path.dirname(font.filepath)
		path = colornames.resolve_key_file(fontDir)
		text = colornames.read_color_names(path) or colornames.DEFAULT_COLOR_NAMES
		rows, noneLabel = colornames.parse_settings(text)
		info = {index: (label, visible) for index, label, visible in rows}
		newRows = []
		seen = set()
		for key in new_order:
			index = int(key)
			label = info.get(index, ("", True))[0]
			newRows.append((index, label, True))
			seen.add(index)
		for index, label, visible in rows:
			if index not in seen:
				newRows.append((index, label, visible))
		colornames.write_color_names(path, colornames.render_settings(newRows, noneLabel))

	# Update Palette UI (original look; checkbox state + counts derived from colour).
	@objc.python_method
	def Update_Plugin_UI(self):
		try:
			for attr in getattr(self, "_metaAttrs", []) + getattr(self, "_bodyAttrs", []):
				if hasattr(self.paletteView.frame, attr):
					delattr(self.paletteView.frame, attr)
			self._metaAttrs = []
			self._bodyAttrs = []
			if not self.font or not self.meaning or getattr(self, "_eye_mode", False):
				return
			self._rowChecks = {}
			yPos = 17
			masterId = self.font.selectedFontMaster.id
			counts = self._counts(masterId)
			glyphCount = len(self.font.glyphs)
			order = list(self.meaning.keys())

			selectedLayers = self.font.selectedLayers or []
			selStates = [self._layer_state(layer, order) for layer in selectedLayers]
			firstColor = selectedLayers[0].color if selectedLayers else None

			for color, meaning in self.meaning.items():
				for suffix in ("", "box", "count", "hl", "focus"):
					attr = str(color) + suffix
					if hasattr(self.paletteView.frame, attr):
						delattr(self.paletteView.frame, attr)
				if not meaning:
					continue
				count = counts[color] if color in counts else 0
				barWidth = (self.barWidth / glyphCount * count) if glyphCount else 0
				if getattr(self, "_focusColor", None) == color:
					rgb = self.colorKeys[str(color)]
					setattr(self.paletteView.frame, str(color)+"focus", Box((0, yPos-self.shift-1, self.width, 19), fillColor=AppKit.NSColor.colorWithRed_green_blue_alpha_(rgb[0], rgb[1], rgb[2], 0.22), cornerRadius=0, borderWidth=0))

				if selectedLayers:
					check = all(state.get(color, False) for state in selStates)
					if check:
						rgb = self.colorKeys[str(color)]
						setattr(self.paletteView.frame, str(color)+"hl", Box((0, yPos-self.shift-1, self.width, 19), fillColor=AppKit.NSColor.colorWithRed_green_blue_alpha_(rgb[0], rgb[1], rgb[2], 0.16), cornerRadius=0, borderWidth=0))
					if barWidth:
						if check and firstColor == int(color):
							fill = AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(color)])
						else:
							fill = AppKit.NSColor.colorWithRed_green_blue_alpha_(0, 0, 0, 0.06)
						setattr(self.paletteView.frame, str(color)+"box", Box((self.xPos, yPos-self.shift-1, barWidth+0.01, 19), fillColor=fill, cornerRadius=0, borderWidth=0))
					checkbox = TextBox((12, yPos-self.shift+2, -10, 20), meaning, sizeStyle='small')
					setattr(self.paletteView.frame, str(color), checkbox)
					self._attach_rename(checkbox, color)
					self._make_count(color, count, yPos)
					yPos += 19
				else:
					if barWidth:
						fill = AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(color)])
						setattr(self.paletteView.frame, str(color)+"box", Box((self.xPos, yPos-self.shift-1, barWidth+0.01, 19), fillColor=fill, cornerRadius=0, borderWidth=0))
					checkbox = TextBox((12, yPos-self.shift+2, -10, 20), meaning, sizeStyle='small')
					setattr(self.paletteView.frame, str(color), checkbox)
					self._attach_rename(checkbox, color)
					self._make_count(color, count, yPos)
					yPos += 19
			self._countBoxes = {}
			for reviewColor in list(self._rowChecks.keys()):
				countBox = getattr(self.paletteView.frame, str(reviewColor)+"count", None)
				if countBox is None:
					continue
				self._countBoxes[reviewColor] = countBox
				try:
					recognizer = NSClickGestureRecognizer.alloc().initWithTarget_action_(self, "countClicked:")
					recognizer.setNumberOfClicksRequired_(1)
					view = self._ns_button(countBox)
					view.addGestureRecognizer_(recognizer)
					area = AppKit.NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
						view.bounds(),
						AppKit.NSTrackingCursorUpdate | AppKit.NSTrackingActiveInKeyWindow | AppKit.NSTrackingMouseEnteredAndExited,
						self, None)
					view.addTrackingArea_(area)
				except Exception:
					pass
			self._build_meta_strip(order, glyphCount, masterId)
			self._update_title_bar()
		except Exception:
			import traceback
			print("Color Flow [Update_Plugin_UI] error:\n" + traceback.format_exc())

	# Right-click “Set workflow step” on the Font/Edit-View selection (#6).
	# The callback signature for a palette is not firmly documented, so the handler
	# finds the NSMenu among whatever args Glyphs passes and is fully guarded.
	@objc.python_method
	def contextMenuHandler(self, *args):
		try:
			if not self.meaning:
				return
			menu = None
			for candidate in args:
				if candidate is not None and hasattr(candidate, "addItem_"):
					menu = candidate
					break
			if menu is None:
				return
			submenu = AppKit.NSMenu.alloc().initWithTitle_("Color Flow")
			for color, label in self.meaning.items():
				if not label:
					continue
				item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(label, "setStepFromMenu:", "")
				item.setTarget_(self)
				item.setRepresentedObject_(str(color))
				submenu.addItem_(item)
			submenu.addItem_(NSMenuItem.separatorItem())
			clearItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Clear colour", "setStepFromMenu:", "")
			clearItem.setTarget_(self)
			clearItem.setRepresentedObject_("none")
			submenu.addItem_(clearItem)
			parent = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Color Flow", None, "")
			parent.setSubmenu_(submenu)
			menu.addItem_(parent)
		except Exception:
			import traceback
			print("Color Flow [context menu] error:\n" + traceback.format_exc())

	def setStepFromMenu_(self, sender):
		try:
			raw = sender.representedObject()
			self._apply_step_to_selection(None if raw == "none" else int(raw))
		except Exception:
			import traceback
			print("Color Flow [set step] error:\n" + traceback.format_exc())

	@objc.python_method
	def _apply_step_to_selection(self, color):
		font = Glyphs.font
		if font is None:
			return
		layers = font.selectedLayers or []
		try:
			font.disableUpdateInterface()
		except Exception:
			pass
		try:
			for layer in layers:
				layer.color = color
		finally:
			try:
				font.enableUpdateInterface()
			except Exception:
				pass

	# Review Queue + Focus (#10, #11): single-click a step's count badge to
	# focus that step (row highlight) and open exactly its glyphs in a new Edit
	# tab to walk through them; click again to clear focus.
	# Pointing-hand cursor while hovering a clickable count badge (#10/#11).
	def cursorUpdate_(self, event):
		try:
			AppKit.NSCursor.pointingHandCursor().set()
		except Exception:
			pass

	def rowClicked_(self, sender):
		try:
			color = self._color_for_recognizer(sender)
			if color is None:
				return
			self._focusColor = None if getattr(self, "_focusColor", None) == color else color
			self.Update_Plugin_UI()
			if self._focusColor is not None:
				self._open_step_tab(color)
		except Exception:
			import traceback
			print("Color Flow [row click] error:\n" + traceback.format_exc())

	def countClicked_(self, sender):
		try:
			color = self._color_for_count(sender)
			if color is None:
				return
			self._focusColor = None if getattr(self, "_focusColor", None) == color else color
			self.Update_Plugin_UI()
			if self._focusColor is not None:
				self._open_step_tab(color)
		except Exception:
			import traceback
			print("Color Flow [review] error:\n" + traceback.format_exc())

	@objc.python_method
	def _color_for_count(self, recognizer):
		view = recognizer.view()
		for color, box in getattr(self, "_countBoxes", {}).items():
			try:
				if self._ns_button(box) == view:
					return color
			except Exception:
				continue
		return None

	@objc.python_method
	def _glyphs_for_step(self, color, masterId, order):
		names = []
		for glyph in self.font.glyphs:
			layer = glyph.layers[masterId]
			state = self._layer_state(layer, order) if layer is not None else {}
			if state.get(color):
				names.append(glyph.name)
		return names

	@objc.python_method
	def _open_step_tab(self, color):
		font = self.font
		if font is None:
			return
		try:
			masterId = font.selectedFontMaster.id
		except Exception:
			return
		order = list(self.meaning.keys())
		names = self._glyphs_for_step(color, masterId, order)
		if not names:
			Message("No glyphs at \u201c%s\u201d." % self.meaning.get(color, str(color)), title="Color Flow")
			return
		try:
			font.newTab("/" + "/".join(names))
		except Exception:
			import traceback
			print("Color Flow [open tab] error:\n" + traceback.format_exc())

	@objc.python_method
	def _make_count(self, color, count, yPos):
		textbox = TextBox((self.width-50, yPos+3-self.shift, -6, 20), str(count), alignment="right", sizeStyle='small')
		try:
			size = AppKit.NSFont.smallSystemFontSize()
			label = getattr(self, "_rowChecks", {}).get(color)
			if label is not None:
				size = self._ns_button(label).font().pointSize()
			size = max(8.0, size - 1.0)
			textbox.getNSTextField().setFont_(AppKit.NSFont.monospacedDigitSystemFontOfSize_weight_(size, AppKit.NSFontWeightRegular))
		except Exception:
			pass
		setattr(self.paletteView.frame, str(color)+"count", textbox)

	def headerEyeClicked_(self, sender):
		try:
			self._toggle_eye_mode(sender)
		except Exception:
			import traceback
			print("Color Flow [header eye] error:\n" + traceback.format_exc())

	@objc.python_method
	def _is_collapsed(self):
		try:
			view = self.dialog
			if view is None or view.window() is None:
				return True
			if view.isHiddenOrHasHiddenAncestor():
				return True
			return view.visibleRect().size.height < 2.0
		except Exception:
			return False

	@objc.python_method
	def _sync_header(self):
		bar = getattr(self, "_titleBar", None)
		if bar is None:
			return
		try:
			collapsed = self._is_collapsed()
			bar.setHidden_(not collapsed)
			eye = getattr(self, "_titleEye", None)
			if eye is not None:
				eye.setHidden_(collapsed)
			gear = getattr(self, "_titleGear", None)
			if gear is not None:
				gear.setHidden_(collapsed)
		except Exception:
			pass

	def headerTick_(self, sender):
		self._sync_header()

	# Inject a colour bar into the palette SECTION HEADER (#23). Done deferred so
	# the palette is docked first, then the whole window is searched for the title.
	def deferredHeaderSetup_(self, sender):
		try:
			self._inject_title_bar()
			self._update_title_bar()
			if getattr(self, "_headerTimer", None) is None:
				from Foundation import NSTimer
				self._headerTimer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(0.5, self, "headerTick:", None, True)
		except Exception:
			import traceback
			print("Color Flow [header setup] error:\n" + traceback.format_exc())

	@objc.python_method
	def _window_root(self):
		view = getattr(self, "dialog", None)
		top = view
		for _ in range(25):
			if view is None:
				break
			sup = view.superview()
			if sup is None:
				break
			top = sup
			view = sup
		return top

	@objc.python_method
	def _dump_view_hierarchy(self):
		if getattr(self, "_dumpedHierarchy", False):
			return
		self._dumpedHierarchy = True
		try:
			lines = ["Color Flow [header dump v2] window tree (class ='text' frame):"]
			count = [0]
			def walk(v, depth):
				if v is None or count[0] > 90 or depth > 12:
					return
				count[0] += 1
				text = ""
				try:
					if v.isKindOfClass_(AppKit.NSTextField):
						text = " ='%s'" % str(v.stringValue())
				except Exception:
					pass
				try:
					fr = v.frame()
					rect = " (%d,%d,%d,%d)" % (fr.origin.x, fr.origin.y, fr.size.width, fr.size.height)
				except Exception:
					rect = ""
				lines.append("  " * depth + v.className() + text + rect)
				try:
					for sub in v.subviews():
						walk(sub, depth + 1)
				except Exception:
					pass
			walk(self._window_root(), 0)
			print("\n".join(lines))
		except Exception:
			import traceback
			print("Color Flow [header dump] error:\n" + traceback.format_exc())

	@objc.python_method
	def _search_title(self, view, depth):
		if view is None or depth > 12:
			return None
		try:
			if view.isKindOfClass_(AppKit.NSTextField):
				value = str(view.stringValue() or "")
				if "Color Flow" in value:
					return view
		except Exception:
			pass
		try:
			for sub in view.subviews():
				found = self._search_title(sub, depth + 1)
				if found is not None:
					return found
		except Exception:
			pass
		return None

	@objc.python_method
	def _inject_title_bar(self):
		if getattr(self, "_titleBar", None) is not None:
			return
		try:
			field = self._search_title(self._window_root(), 0)
			if field is None:
				return
			header = field.superview()
			if header is None:
				return
			bounds = header.bounds()
			btn = 14.0
			pad = 8.0
			gap = 4.0
			ctrlY = (bounds.size.height - btn) / 2.0
			gearX = bounds.size.width - pad - btn
			eyeX = gearX - gap - btn
			barWidth, barHeight = 52.0, 6.0
			barX = bounds.size.width - pad - barWidth
			barY = (bounds.size.height - barHeight) / 2.0
			bar = AppKit.NSView.alloc().initWithFrame_(((barX, barY), (barWidth, barHeight)))
			bar.setAutoresizingMask_(AppKit.NSViewMinXMargin)
			bar.setWantsLayer_(True)
			try:
				bar.layer().setCornerRadius_(3.0)
				bar.layer().setMasksToBounds_(True)
				bar.layer().setBackgroundColor_(AppKit.NSColor.colorWithRed_green_blue_alpha_(0.5, 0.5, 0.5, 0.18).CGColor())
			except Exception:
				pass
			header.addSubview_(bar)
			self._titleBar = bar
			eye = AppKit.NSButton.alloc().initWithFrame_(((eyeX, ctrlY), (btn, btn)))
			eye.setBordered_(False)
			eye.setAutoresizingMask_(AppKit.NSViewMinXMargin)
			eye.setTarget_(self)
			eye.setAction_("headerEyeClicked:")
			try:
				eyeImg = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_("eye", None)
				if eyeImg is not None:
					eye.setImage_(eyeImg)
				else:
					eye.setTitle_("\U0001F441")
			except Exception:
				pass
			header.addSubview_(eye)
			self._titleEye = eye
			gear = AppKit.NSButton.alloc().initWithFrame_(((gearX, ctrlY), (btn, btn)))
			gear.setBordered_(False)
			gear.setAutoresizingMask_(AppKit.NSViewMinXMargin)
			gear.setTarget_(self)
			gear.setAction_("openSettings:")
			try:
				gearImg = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_("gearshape", None)
				if gearImg is not None:
					gear.setImage_(gearImg)
				else:
					gear.setTitle_("\u2699")
			except Exception:
				pass
			header.addSubview_(gear)
			self._titleGear = gear
			self._sync_header()
		except Exception:
			import traceback
			print("Color Flow [title bar] error:\n" + traceback.format_exc())

	@objc.python_method
	def _update_title_bar(self):
		bar = getattr(self, "_titleBar", None)
		if bar is None or not self.font or not self.meaning:
			return
		try:
			order = list(self.meaning.keys())
			for sub in list(bar.subviews()):
				sub.removeFromSuperview()
			colors = []
			for master in self.font.masters:
				mid = master.id
				for glyph in self.font.glyphs:
					layer = glyph.layers[mid]
					colors.append(layer.color if layer is not None else None)
			total = len(colors)
			if not total:
				return
			exclusive = colornames.single_counts_from_colors(colors, order)
			width = bar.bounds().size.width
			height = bar.bounds().size.height
			xPos = 0.0
			for key in order:
				count = exclusive.get(key, 0)
				if not count:
					continue
				segWidth = width / total * count
				rgb = self.colorKeys.get(str(key), (0.5, 0.5, 0.5, 0.5))
				seg = AppKit.NSView.alloc().initWithFrame_(((xPos, 0.0), (segWidth, height)))
				seg.setWantsLayer_(True)
				try:
					seg.layer().setBackgroundColor_(AppKit.NSColor.colorWithRed_green_blue_alpha_(rgb[0], rgb[1], rgb[2], 0.95).CGColor())
				except Exception:
					pass
				bar.addSubview_(seg)
				xPos += segWidth
		except Exception:
			pass

	# Palette body: a single stacked colour bar for the SELECTED master (replaces
	# the per-step rows). Each segment is one step, sized by its glyph count, with
	# a label-and-count tooltip. Per-step detail lives in eye mode + the dashboard.
	@objc.python_method
	def _build_body_bar(self, order, glyphCount, masterId):
		frame = self.paletteView.frame
		attrs = []
		if not glyphCount:
			self._bodyAttrs = attrs
			return
		try:
			masterName = self.font.selectedFontMaster.name or ""
		except Exception:
			masterName = ""
		frame.cfBodyLabel = TextBox((4, 4, -4, 14), masterName, sizeStyle='small')
		attrs.append("cfBodyLabel")
		colors = []
		for glyph in self.font.glyphs:
			layer = glyph.layers[masterId]
			colors.append(layer.color if layer is not None else None)
		exclusive = colornames.single_counts_from_colors(colors, order)
		barY, barH = 24, 16
		usable = self.width - 8
		setattr(frame, "cfBodyTrack", Box((4, barY, usable, barH),
			fillColor=AppKit.NSColor.colorWithRed_green_blue_alpha_(0.5, 0.5, 0.5, 0.14),
			cornerRadius=4, borderWidth=0))
		attrs.append("cfBodyTrack")
		xPos = 4.0
		for key in order:
			count = exclusive.get(key, 0)
			if not count:
				continue
			segWidth = usable / glyphCount * count
			rgb = self.colorKeys.get(str(key), (0.5, 0.5, 0.5, 0.5))
			name = "cfBody" + str(key)
			box = Box((xPos, barY, segWidth + 0.01, barH),
				fillColor=AppKit.NSColor.colorWithRed_green_blue_alpha_(rgb[0], rgb[1], rgb[2], 0.9),
				cornerRadius=0, borderWidth=0)
			setattr(frame, name, box)
			try:
				self._ns_button(box).setToolTip_("%s \u00b7 %d" % (self.meaning.get(str(key), str(key)), count))
			except Exception:
				pass
			attrs.append(name)
			xPos += segWidth
		self._bodyAttrs = attrs

	# Top strip: a fire progress-streak badge (#17) and a thin 100%-stacked
	# whole-master progress ribbon (#23), drawn in the top band above the rows so
	# the palette height is unchanged. Torn down each rebuild via self._metaAttrs.
	@objc.python_method
	def _build_meta_strip(self, order, glyphCount, masterId):
		frame = self.paletteView.frame
		attrs = []
		self._metaAttrs = attrs

	# UPDATEINTERFACE handler: cheap dirty-check on selection + layer colours.
	@objc.python_method
	def update(self, sender):
		if self._windowController:
			self.font = self._windowController.documentFont()
		if not self.font:
			return
		try:
			self._sync_header()
		except Exception:
			pass

		try:
			grouping = getattr(self, "fontview", None)
			if grouping is not None and grouping.is_enabled(self.font) and grouping.is_dirty(self.font):
				self._pendingFont = self.font
				NSObject.cancelPreviousPerformRequestsWithTarget_selector_object_(self, "rainbowDebouncedRebuild:", None)
				self.performSelector_withObject_afterDelay_("rainbowDebouncedRebuild:", None, 0.15)
		except Exception:
			pass

		try:
			masterId = self.font.selectedFontMaster.id
		except Exception:
			return
		if not masterId:
			return

		selectedLayers = self.font.selectedLayers or []
		signature = (masterId, tuple(
			((layer.parent.name if layer.parent is not None else ""), layer.color)
			for layer in selectedLayers))
		if signature == getattr(self, "_lastSignature", None):
			return
		self._lastSignature = signature
		# A layer colour changed (or selection moved) — the cached per-step counts
		# are derived from layer colours, so drop them and let Update_Plugin_UI
		# recompute. (Nothing else invalidates them now the palette is display-only.)
		self._invalidate_counts(masterId)
		self.Update_Plugin_UI()

	# Toggle a step: recompute the native layer colour (the saved source of truth).
	@objc.python_method
	def CheckBox_Callback(self, sender):
		if not self.font:
			return
		# An NSButton can still fire its action at the end of a drag-to-reorder
		# gesture. Ignore that spurious toggle (within ~250ms of real drag motion)
		# so reordering never accidentally recolours the selected glyphs.
		lastDrag = getattr(self, "_lastDragTime", None)
		if lastDrag is not None and (datetime.now() - lastDrag).total_seconds() < 0.25:
			return
		color = None
		for candidate, checkbox in getattr(self, "_rowChecks", {}).items():
			if checkbox is sender:
				color = candidate
				break
		if color is None:
			return
		checked = bool(sender.get())
		order = list(self.meaning.keys())
		master = self.font.selectedFontMaster
		selectedLayers = self.font.selectedLayers
		if master is None or not selectedLayers:
			# No glyph/layer selected (e.g. clicked from Font View with nothing
			# selected): nothing to toggle. Rebuild so the box snaps back to its
			# derived (unchecked) state instead of looking toggled.
			self._lastSignature = None
			self.Update_Plugin_UI()
			return
		masterId = master.id
		self.font.disableUpdateInterface()
		try:
			for layer in selectedLayers:
				if self._free_mode():
					# single-select: this colour exclusively, or clear if re-clicked
					layer.color = int(color) if checked else None
				else:
					state = colornames.checked_state_for_color(layer.color, order)
					state[color] = checked
					layer.color = colornames.layer_color_for_state(state, order)
			self._invalidate_counts(masterId)
		finally:
			self.font.enableUpdateInterface()
		self._lastSignature = None
		self.Update_Plugin_UI()

	########################################################################################################
	#																									   #
	#	EXTRA FEATURES																					   #
	#																									   #
	########################################################################################################
	#																									   #
	#																									   #

	# Open the HTML Color Font Dashboard for the current font (per-master colour
	# distribution + what changed since last run). Reloaded each time so edits to
	# dashboard.py take effect without restarting Glyphs.
	@objc.python_method
	def Open_Color_Font_Dashboard(self, sender):
		try:
			import importlib
			import colorflow_dashboard
			importlib.reload(colorflow_dashboard)
			colorflow_dashboard.main(Glyphs.font)
		except Exception:
			import traceback
			print("Color Flow [dashboard] error:\n" + traceback.format_exc())


	########################################################################################################
	#																									   #
	#	SETUP COLOR MEANING																			       #
	#																									   #
	########################################################################################################
	#																									   #
	#																									   #

	# Resolve colorNames.txt (per-font dir, else the shared info dir) and parse it
	# into {"0".."11": label}. All parsing/key-file logic lives in the shared
	# colornames module so the palette and the shortcut scripts can
	# never diverge (see tools/generate_shortcuts.py).
	@objc.python_method
	def Load_Meaning(self):
		fontDir = None
		font = Glyphs.font
		if font is not None and font.filepath:
			fontDir = os.path.dirname(font.filepath)
		return colornames.load_meaning(fontDir)


	########################################################################################################
	#																									   #
	#	DON'T MODIFY																			           #
	#																									   #
	########################################################################################################
	#																									   #

	@objc.python_method
	def __del__(self):
		# Delete callbacks when Glyphs quits, otherwise it'll crash :(
		Glyphs.removeCallback(self.update)
		try:
			if getattr(self, "_headerTimer", None) is not None:
				self._headerTimer.invalidate()
		except Exception:
			pass
		# Remove the Rainbow Font View menu item this instance added.
		self._teardown_rainbow_menu()
		self._teardown_settings_menu()
		# Remove the Cocoa save-notification observers.
		try:
			from Foundation import NSNotificationCenter
			NSNotificationCenter.defaultCenter().removeObserver_(self)
		except Exception:
			pass


	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__

	# ------------------------------------------------------------------ eye visibility mode

	# ObjC selector: a single click on a colour row in eye mode toggles whether
	# that colour is staged visible or hidden.
	def eyeRowClicked_(self, sender):
		try:
			view = sender.view()
			for key, label in getattr(self, "_eyeRowViews", {}).items():
				if label._nsObject == view:
					index = int(key)
					for row in self._eye_rows:
						if row[0] == index:
							row[2] = not row[2]
							break
					self._build_eye_mode_ui()
					return
		except Exception:
			import traceback
			print("Color Flow [eye click] error:\n" + traceback.format_exc())

	# Animate the palette height via the height constraint's animator proxy (the
	# technique the Glyphs team documents for smooth palette resizing). Falls back
	# to a direct, un-animated resize if the constraint could not be created.
	@objc.python_method
	def _set_palette_height(self, height, animated=True):
		self.height = height
		constraint = getattr(self, "_heightConstraint", None)
		if constraint is None:
			try:
				self.paletteView.frame.setPosSize((0, 0, self.width, height))
				self.paletteView.setPosSize((0, 0, self.width, height + 10))
			except Exception:
				pass
			return
		if animated:
			AppKit.NSAnimationContext.beginGrouping()
			AppKit.NSAnimationContext.currentContext().setDuration_(0.22)
			constraint.animator().setConstant_(height)
			AppKit.NSAnimationContext.endGrouping()
		else:
			constraint.setConstant_(height)

	@objc.python_method
	def _toggle_eye_mode(self, sender):
		try:
			if self._eye_mode:
				self._exit_eye_mode()
			else:
				self._enter_eye_mode()
		except Exception:
			import traceback
			print("Color Flow [eye toggle] error:\n" + traceback.format_exc())

	@objc.python_method
	def _set_eye_button(self, on):
		try:
			name = "eye.slash" if on else "eye"
			image = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
			nsbutton = getattr(self, "_titleEye", None)
			if nsbutton is None:
				return
			nsbutton.setBordered_(False)
			if image is not None:
				nsbutton.setImage_(image)
				nsbutton.setTitle_("")
			else:
				nsbutton.setTitle_("🙈" if on else "👁")
		except Exception:
			pass

	@objc.python_method
	def _eye_key_path(self):
		font = Glyphs.font
		fontDir = os.path.dirname(font.filepath) if (font is not None and font.filepath) else None
		return colornames.resolve_key_file(fontDir)

	@objc.python_method
	def _enter_eye_mode(self):
		path = self._eye_key_path()
		text = colornames.read_color_names(path) or colornames.DEFAULT_COLOR_NAMES
		rows, none_label = colornames.parse_settings(text)
		self._eye_rows = [[index, label, visible] for index, label, visible in rows]
		self._eye_none = none_label
		self._eye_mode = True
		self._set_eye_button(True)
		self.height = 19 * len(self._eye_rows) + 8
		try:
			self._set_palette_height(self.height, animated=True)
		except Exception:
			pass
		self._build_eye_mode_ui()

	@objc.python_method
	def _exit_eye_mode(self):
		self._eye_mode = False
		self._set_eye_button(False)
		rows = [(index, label, visible) for index, label, visible in (self._eye_rows or [])]
		if rows:
			path = self._eye_key_path()
			colornames.write_color_names(path, colornames.render_settings(rows, self._eye_none))
		self._teardown_eye_rows()
		self.reload_after_settings()

	@objc.python_method
	def _teardown_eye_rows(self):
		for index in range(12):
			for suffix in ("eye", "eyeTag", "eyeLine"):
				attr = str(index) + suffix
				if hasattr(self.paletteView.frame, attr):
					delattr(self.paletteView.frame, attr)
		self._eyeRowViews = {}

	# Render every colour (visible + hidden) as a click-to-toggle row; hidden rows
	# are dimmed. A 1-click gesture per label flips its staged visibility.
	@objc.python_method
	def _build_eye_mode_ui(self):
		for index in range(12):
			for suffix in ("", "box", "count", "hl", "colorTag", "line", "eye", "eyeTag", "eyeLine"):
				attr = str(index) + suffix
				if hasattr(self.paletteView.frame, attr):
					delattr(self.paletteView.frame, attr)
		self._eyeRowViews = {}
		yPos = 17
		for index, label, visible in (self._eye_rows or []):
			key = str(index)
			rgb = self.colorKeys.get(key, (0.5, 0.5, 0.5, 0.5))
			alpha = 0.5 if visible else 0.12
			setattr(self.paletteView.frame, key+"eyeTag", Box((0, yPos-self.shift-1, 6, 19), fillColor=AppKit.NSColor.colorWithRed_green_blue_alpha_(rgb[0], rgb[1], rgb[2], alpha), cornerRadius=0, borderWidth=0))
			shown = label or colornames.DEFAULT_LABELS.get(index, key)
			textbox = TextBox((12, yPos-self.shift+2, -10, 20), shown, sizeStyle='small')
			setattr(self.paletteView.frame, key+"eye", textbox)
			try:
				field = textbox.getNSTextField()
				field.setTextColor_(AppKit.NSColor.labelColor() if visible else AppKit.NSColor.tertiaryLabelColor())
			except Exception:
				pass
			self._eyeRowViews[key] = textbox
			try:
				recognizer = NSClickGestureRecognizer.alloc().initWithTarget_action_(self, "eyeRowClicked:")
				recognizer.setNumberOfClicksRequired_(1)
				textbox._nsObject.addGestureRecognizer_(recognizer)
			except Exception:
				pass
			yPos += 19

