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
from AppKit import NSColor, NSMenuItem, NSOnState, NSOffState, NSClickGestureRecognizer, NSPanGestureRecognizer, NSGestureRecognizerStateEnded
from Foundation import NSObject
from GlyphsApp.plugins import *
from GlyphsApp.UI import *
from GlyphsApp import *

# Shared, GlyphsApp-free colorNames logic (also embedded into the shortcut
# scripts by tools/generate_shortcuts.py). Glyphs puts this bundle's Resources/
# dir on sys.path, so a plain absolute import works.
import colornames
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
		self.height = 22 * len([x for x in self.meaning.values() if x]) + 25
		self.xPos = 0  # progress bar flush to the left edge (no margin)

		self.paletteView = Window((self.width, self.height + 10))
		self.paletteView.frame = Group((0, 0, self.width, self.height))
		if not Glyphs.defaults["com.hugojourdan.ColorFlow-Report"]:
			Glyphs.defaults["com.hugojourdan.ColorFlow-Report"] = "Enable Color Flow Report"
			self.report = False

		# Draw Action Button
		self.paletteView.frame.actionPopUpButton = ActionButton((self.width-22, 0, 34, 19),
			self._action_menu_items(),
			sizeStyle='small')

		#---------------------------------------------------------------------------#
		# Draw Master Name Field 												    #
		#---------------------------------------------------------------------------#
		self.paletteView.frame.masterNameBox = Box((6, 4, 127, 10), fillColor=(AppKit.NSColor.colorWithRed_green_blue_alpha_(0, 0,0,0.1)), cornerRadius=4, borderWidth=0)

		# Separator lines + colour tags (depend on the meaning order/visibility).
		# Per-row widgets (checkbox / bar / count) are built by Update_Plugin_UI.
		self._rowChecks = {}
		self._build_static_rows()

		# # Select a master if none is selected
		# if not self.font.selectedFontMaster:
		# 	self.font.selectedFontMaster = self.font.masters[0]

		# Needed to display the palette plugin
		self.dialog = self.paletteView.frame.getNSView()

	# Separator lines + colour tags from the current meaning (order + visibility).
	@objc.python_method
	def _build_static_rows(self):
		yPos = 25
		for k in self.meaning.keys():
			setattr(self.paletteView.frame, str(k)+"line", HorizontalLine((0, yPos, 0, 1)))
			yPos += 22
		yPos = 36
		for k, v in self.meaning.items():
			if v:
				setattr(self.paletteView.frame, str(k)+"colorTag", Box((0, yPos-self.shift-1, 3, 22), fillColor=(AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(k)])), cornerRadius=0, borderWidth=0))
				yPos += 22

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
			for suffix in ("line", "colorTag", "", "box", "count"):
				attr = str(i) + suffix
				if hasattr(self.paletteView.frame, attr):
					delattr(self.paletteView.frame, attr)
		self.height = 22 * len([x for x in self.meaning.values() if x]) + 25
		self._build_static_rows()
		try:
			self.paletteView.frame.setPosSize((0, 0, self.width, self.height))
			self.paletteView.setPosSize((0, 0, self.width, self.height + 10))
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
		self.font = Glyphs.font
		self.init = False
		self.reportCallbackRegistered = False
		self.startSession = datetime.now().strftime('%m/%d/%Y - %H:%M')
		self.update(self._windowController)
		self.Color_Flow_Report(self._windowController)


		if Glyphs.defaults["com.hugojourdan.ColorFlow-Report"] == "Disable Color Flow Report":
			self.report = True
			Glyphs.addCallback(self.Color_Flow_Report_PRINT, DOCUMENTCLOSED)
			self.reportCallbackRegistered = True

		# Font-View colour grouping (the merged Rainbow FontView half). Opt-in and
		# fully wrapped so a problem here can never stop the palette from loading.
		self.fontview = fontview.FontViewGrouping()
		self._pendingFont = None
		self._strippedForSave = False
		try:
			self._install_rainbow_menu()
			self._rainbow_conflict_check()
		except Exception:
			import traceback
			print("Color Flow [Rainbow setup] error:\n" + traceback.format_exc())

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
		return "Color Flow: Rainbow Font View"

	# Shared action-menu definition (used by settings() and the report toggle
	# rebuild) so the items never drift between the two.
	@objc.python_method
	def _action_menu_items(self):
		return [
			dict(title="Settings…", callback=self.Open_Settings),
			"----",
			dict(title="Refresh from Layer Colors", callback=self.Setup_Color_Flow),
			dict(title="Reset Color Flow (clear colours)", callback=self.Color_Flow_Reset),
			dict(title="Copy Color Flow to Master", callback=self.Copy_Color_Flow_To_Master),
			dict(title=Glyphs.defaults["com.hugojourdan.ColorFlow-Report"], callback=self.Activate_Color_Flow_Report),
			"----",
			dict(title="Toggle Rainbow Font View", callback=self.Toggle_Rainbow),
			dict(title="Rainbow Source: Layer Color", callback=self.Set_Rainbow_Layer_Source),
			dict(title="Rainbow Source: Glyph Color", callback=self.Set_Rainbow_Glyph_Source),
			"----",
			dict(title="Open Color Flow Documentation", callback=self.Open_Color_Flow_Documentation),
		]

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

	@objc.python_method
	def Set_Rainbow_Layer_Source(self, sender):
		font = Glyphs.font
		if font is not None:
			self.fontview.set_mode(font, "Layer")

	@objc.python_method
	def Set_Rainbow_Glyph_Source(self, sender):
		font = Glyphs.font
		if font is not None:
			self.fontview.set_mode(font, "Glyph")

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
			checkbox.setTitle("")
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
		try:
			recognizer = NSClickGestureRecognizer.alloc().initWithTarget_action_(self, "labelDoubleClicked:")
			recognizer.setNumberOfClicksRequired_(2)
			button.addGestureRecognizer_(recognizer)
		except Exception:
			pass
		try:
			pan = NSPanGestureRecognizer.alloc().initWithTarget_action_(self, "colorDragged:")
			pan._cf_color = color
			button.addGestureRecognizer_(pan)
		except Exception:
			pass

	# Drag a row up/down to reorder the colours; reorder + persist on release.
	def colorDragged_(self, recognizer):
		try:
			if recognizer.state() != NSGestureRecognizerStateEnded:
				return
			color = getattr(recognizer, "_cf_color", None)
			if color is None:
				return
			view = recognizer.view()
			translation = recognizer.translationInView_(view.superview() if view is not None else None)
			steps = int(round(translation.y / 22.0))  # palette y increases downward
			if steps:
				self._reorder_color(color, steps)
		except Exception:
			import traceback
			print("Color Flow [drag] error:\n" + traceback.format_exc())

	# Move `color` by `delta` positions among the visible colours and persist.
	@objc.python_method
	def _reorder_color(self, color, delta):
		visible = list(self.meaning.keys())
		key = str(color)
		if key not in visible:
			return
		src = visible.index(key)
		dst = max(0, min(len(visible) - 1, src + delta))
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
			if not self.font or not self.meaning:
				return
			self._rowChecks = {}
			yPos = 36
			masterId = self.font.selectedFontMaster.id
			counts = self._counts(masterId)
			glyphCount = len(self.font.glyphs)
			order = list(self.meaning.keys())

			if hasattr(self.paletteView.frame, "masterName"):
				delattr(self.paletteView.frame, "masterName")
			masterName = self.font.selectedFontMaster.name
			if len(masterName) > 16:
				masterName = masterName[0:16] + "…"
			setattr(self.paletteView.frame, "masterName", TextBox((6, 2.6, 140, 20), masterName, alignment="left", sizeStyle='small'))

			selectedLayers = self.font.selectedLayers or []
			selStates = [self._layer_state(layer, order) for layer in selectedLayers]
			firstColor = selectedLayers[0].color if selectedLayers else None

			for color, meaning in self.meaning.items():
				for suffix in ("", "box", "count"):
					attr = str(color) + suffix
					if hasattr(self.paletteView.frame, attr):
						delattr(self.paletteView.frame, attr)
				if not meaning:
					continue
				count = counts[color] if color in counts else 0
				barWidth = (self.barWidth / glyphCount * count) if glyphCount else 0

				if selectedLayers:
					check = all(state.get(color, False) for state in selStates)
					if barWidth:
						if check and firstColor == int(color):
							fill = AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(color)])
						else:
							fill = AppKit.NSColor.colorWithRed_green_blue_alpha_(0, 0, 0, 0.06)
						setattr(self.paletteView.frame, str(color)+"box", Box((self.xPos, yPos-self.shift-1, barWidth+0.01, 22), fillColor=fill, cornerRadius=0, borderWidth=0))
					checkbox = CheckBox((12, yPos-self.shift, -10, 20), meaning, value=check, callback=self.CheckBox_Callback, sizeStyle='small')
					setattr(self.paletteView.frame, str(color), checkbox)
					self._attach_rename(checkbox, color)
					if glyphCount and count >= glyphCount:
						setattr(self.paletteView.frame, str(color)+"count", TextBox((self.width-50, yPos+5-self.shift, -6, 20), "✅", alignment="right", sizeStyle='mini'))
					else:
						setattr(self.paletteView.frame, str(color)+"count", TextBox((self.width-50, yPos+3-self.shift, -6, 20), f"{count}/{glyphCount}", alignment="right", sizeStyle='small'))
					yPos += 22
				else:
					if barWidth:
						fill = AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(color)])
						setattr(self.paletteView.frame, str(color)+"box", Box((self.xPos, yPos-self.shift-1, barWidth+0.01, 22), fillColor=fill, cornerRadius=0, borderWidth=0))
					checkbox = CheckBox((12, yPos-self.shift, -10, 20), meaning, value=False, callback=self.CheckBox_Callback, sizeStyle='small')
					setattr(self.paletteView.frame, str(color), checkbox)
					self._attach_rename(checkbox, color)
					if glyphCount and count >= glyphCount:
						setattr(self.paletteView.frame, str(color)+"count", TextBox((self.width-50, yPos+5-self.shift, -6, 20), "✅", alignment="right", sizeStyle='mini'))
					else:
						setattr(self.paletteView.frame, str(color)+"count", TextBox((self.width-50, yPos+3-self.shift, -6, 20), f"{count}/{glyphCount}", alignment="right", sizeStyle='small'))
					yPos += 22
		except Exception:
			import traceback
			print("Color Flow [Update_Plugin_UI] error:\n" + traceback.format_exc())

	# UPDATEINTERFACE handler: cheap dirty-check on selection + layer colours.
	@objc.python_method
	def update(self, sender):
		if self._windowController:
			self.font = self._windowController.documentFont()
		if not self.font:
			return

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
		self.Update_Plugin_UI()

	# Toggle a step: recompute the native layer colour (the saved source of truth).
	@objc.python_method
	def CheckBox_Callback(self, sender):
		if not self.font:
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
		masterId = self.font.selectedFontMaster.id
		self.font.disableUpdateInterface()
		try:
			for layer in self.font.selectedLayers:
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

	# Refresh the palette from current layer colours (state is always derived
	# from layer.color, so this just rebuilds the cached counts).
	@objc.python_method
	def Setup_Color_Flow(self, sender):
		if not self.font:
			return
		self._invalidate_counts(self.font.selectedFontMaster.id)
		self._lastSignature = None
		self.Update_Plugin_UI()

	# Reset Color Flow for the selected master: clear every layer colour.
	@objc.python_method
	def Color_Flow_Reset(self, sender):
		if not self.font:
			return
		masterId = self.font.selectedFontMaster.id
		self.font.disableUpdateInterface()
		try:
			for glyph in self.font.glyphs:
				layer = glyph.layers[masterId]
				if layer is not None:
					layer.color = None
			self._invalidate_counts(masterId)
		finally:
			self.font.enableUpdateInterface()
		self._lastSignature = None
		self.Update_Plugin_UI()


	# Copy Color Flow Data to Master
	@objc.python_method
	def Copy_Color_Flow_To_Master(self, sender):

		MASTER = []
		for master in self.font.masters:
			MASTER.append(master.name)

		self.w = FloatingWindow((200, 110), "Copy Color Flow Data")
		self.w.textFrom = TextBox((10, 10, -10, 17), "From")
		self.w.fromMaster = PopUpButton((55, 10, -10, 20),MASTER)
		self.w.line = HorizontalLine((10, 37, -10, 1))
		self.w.line2 = HorizontalLine((10, 37, -10, 1))
		self.w.textTo = TextBox((10, 46, -10, 17), "To")
		self.w.toMaster = PopUpButton((55, 46, -10, 20),MASTER)
		self.w.button = Button((10, 76, -10, 20), "Run", callback=self.Copy_Color_Flow_To_Master_Callback)
		self.w.center()
		self.w.open()


	@objc.python_method
	def Copy_Color_Flow_To_Master_Callback(self, sender):
		fromMaster = self.w.fromMaster.getTitle()
		toMaster = self.w.toMaster.getTitle()

		fromMasterID, toMasterID = None, None
		for master in self.font.masters:
			if master.name == fromMaster:
				fromMasterID = master.id
			if master.name == toMaster:
				toMasterID = master.id

		if fromMasterID is None or toMasterID is None or fromMasterID == toMasterID:
			return

		# State is derived from layer.color, so copying the colours is enough.
		self.font.disableUpdateInterface()
		try:
			for glyph in self.font.glyphs:
				glyph.layers[toMasterID].color = glyph.layers[fromMasterID].color
			self._invalidate_counts(toMasterID)
		finally:
			self.font.enableUpdateInterface()
		self._lastSignature = None
		self.Update_Plugin_UI()

	@objc.python_method
	def Open_Color_Flow_Documentation( self, sender ):

		URL = "https://github.com/HugoJourdan/Color-Flow"

		import webbrowser
		webbrowser.open(URL)

	@objc.python_method
	def Color_Flow_Report(self, sender):
		layerColorData = {}
		for master in self.font.masters:
			layerColorData[master.id] = {}
			for glyph in self.font.glyphs:
				try:
					colorMeaning = self.meaning[str(glyph.layers[master.id].color)]
				except:
					colorMeaning = "None"
				layerColorData[master.id][glyph.name] = colorMeaning

		if not self.font.userData["com.hugojourdan.ColorFlow-Report_Data"]:
			self.font.userData["com.hugojourdan.ColorFlow-Report_Data"] = layerColorData

		#self.dataSaveLocation = f"{os.path.dirname(self.font.filepath)}/ColorFlow-Data.json"
		#with open(self.dataSaveLocation, 'w') as outfile:
			#json.dump(layerColorData, outfile)

	@objc.python_method
	def Color_Flow_Report_PRINT(self, sender):


		try :
			layerColorData = {}
			for master in self.font.masters:
				layerColorData[master.id] = {}
				for glyph in self.font.glyphs:
					try:
						colorMeaning = self.meaning[str(glyph.layers[master.id].color)]
					except:
						colorMeaning = "None"
					layerColorData[master.id][glyph.name] = colorMeaning

			#layerColorData = json.dumps(layerColorData)

			DATA = self.font.userData["com.hugojourdan.ColorFlow-Report_Data"]

			LayerColorChanged = {}
			for master, data in DATA.items():
				LayerColorChanged[master] = {}
				for glyph in data:
					if glyph in layerColorData[master] and DATA[master][glyph] != layerColorData[master][glyph]:
						LayerColorChanged[master][glyph] = f"{DATA[master][glyph]} → {layerColorData[master][glyph]}"

			if not os.path.exists(f"{os.path.dirname(self.font.filepath)}/Color Flow Reports"):
				os.mkdir(f"{os.path.dirname(self.font.filepath)}/Color Flow Reports")

			dateNow = datetime.now()
			saveLocation = f"{os.path.dirname(self.font.filepath)}/Color Flow Reports"
			fileName = f"{self.font.familyName} – {dateNow.strftime('%m%d%Y-%H%M%S')}.txt"

			with open(saveLocation+"/"+fileName, 'w') as f:
				f.write(f"Session start : {self.startSession}\nSession stop : {dateNow.strftime('%m/%d/%Y - %H:%M')}\n\n")
				for master, data in LayerColorChanged.items():
					f.write(f"Master : {self.font.masters[master].name}\n-----------------------------------------------------\n")
					for k, v in data.items():
						f.write(f"{k} : {v}\n- - - - - - - - - - - - - - - - - - - - - - - - - - -\n")
					f.write("\n=====================================================\n\n")

		except:pass

		# with open('/Users/hugojourdan/Desktop/POUBELLE/DATA.json', 'w') as outfile:
			# json.dump(layerColorData, outfile)

	@objc.python_method
	def Activate_Color_Flow_Report(self, sender):
		if Glyphs.defaults["com.hugojourdan.ColorFlow-Report"] == "Enable Color Flow Report":
			self.report = True
			Glyphs.addCallback(self.Color_Flow_Report_PRINT, DOCUMENTCLOSED)
			self.reportCallbackRegistered = True
			Glyphs.defaults["com.hugojourdan.ColorFlow-Report"] = "Disable Color Flow Report"
			print("Color Flow Report enabled. A .txt report will be written to a 'Color Flow Reports' folder next to your .glyphs file when you close the document.")
		else:
			self.report = False
			Glyphs.removeCallback(self.Color_Flow_Report_PRINT, DOCUMENTCLOSED)
			self.reportCallbackRegistered = False
			Glyphs.defaults["com.hugojourdan.ColorFlow-Report"] = "Enable Color Flow Report"
			print("Color Flow Report disabled.")
		Glyphs.showMacroWindow()
		self._rebuild_action_button()

	# Rebuild the action button (its Report item title reflects Glyphs.defaults).
	@objc.python_method
	def _rebuild_action_button(self):
		if hasattr(self.paletteView.frame, "actionPopUpButton"):
			delattr(self.paletteView.frame, "actionPopUpButton")
		self.paletteView.frame.actionPopUpButton = ActionButton(
			(self.width-22, 0, 34, 19), self._action_menu_items(), sizeStyle='small')


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
		# The report callback (DOCUMENTCLOSED) is registered conditionally, so it
		# must be removed here too or it leaks and can crash on close/quit.
		if getattr(self, "reportCallbackRegistered", False):
			Glyphs.removeCallback(self.Color_Flow_Report_PRINT, DOCUMENTCLOSED)
			self.reportCallbackRegistered = False
		# Remove the Rainbow Font View menu item this instance added.
		self._teardown_rainbow_menu()
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

