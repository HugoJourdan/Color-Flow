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
from AppKit import NSColor, NSMenuItem, NSOnState, NSOffState
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
		self.xPos = 9

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

		#---------------------------------------------------------------------------#
		# Draw Horitzontal Lines 													#
		#---------------------------------------------------------------------------#
		yPos = 25
		for k, v in self.meaning.items():
			setattr(self.paletteView.frame, str(k)+"line", HorizontalLine((0, yPos, 0, 1)))
			yPos += 22

		#---------------------------------------------------------------------------#
		# Draw Color Tags															#
		#---------------------------------------------------------------------------#
		yPos = 36
		for k, v in self.meaning.items():
			if v:
				setattr(self.paletteView.frame, str(k)+"colorTag", Box((0, yPos+1-self.shift, 3, 16), fillColor=(AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(k)])), cornerRadius=0, borderWidth=0))
				yPos += 22

		#---------------------------------------------------------------------------#
		# Build interactive rows ONCE; update() mutates their values (no teardown). #
		# Two pre-positioned bars per row (gray + colored) sit behind the checkbox;  #
		# only their width is mutated, since vanilla Box fill colour is immutable.   #
		#---------------------------------------------------------------------------#
		self.paletteView.frame.masterName = TextBox((6, 2.6, 140, 20), "", alignment="left", sizeStyle='small')
		self.masterName = self.paletteView.frame.masterName

		self.rows = {}
		yPos = 36
		for color, label in self.meaning.items():
			if not label:
				continue
			barY = yPos + 1 - self.shift
			grayBar = Box((self.xPos, barY, 0, 16), fillColor=(AppKit.NSColor.colorWithRed_green_blue_alpha_(0, 0, 0, 0.06)), cornerRadius=0, borderWidth=0)
			setattr(self.paletteView.frame, str(color)+"graybar", grayBar)
			colorBar = Box((self.xPos, barY, 0, 16), fillColor=(AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(color)])), cornerRadius=0, borderWidth=0)
			setattr(self.paletteView.frame, str(color)+"colorbar", colorBar)
			check = CheckBox((12, yPos-self.shift, -10, 20), label, value=False, callback=self.CheckBox_Callback, sizeStyle='small')
			setattr(self.paletteView.frame, str(color)+"check", check)
			count = TextBox((self.width-50, yPos+3-self.shift, -6, 20), "", alignment="right", sizeStyle='small')
			setattr(self.paletteView.frame, str(color)+"count", count)
			self.rows[color] = {"gray": grayBar, "color": colorBar, "check": check, "count": count, "barY": barY}
			yPos += 22

		# # Select a master if none is selected
		# if not self.font.selectedFontMaster:
		# 	self.font.selectedFontMaster = self.font.masters[0]

		# Needed to display the palette plugin
		self.dialog = self.paletteView.frame.getNSView()


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
		try:
			self._install_rainbow_menu()
			self._rainbow_conflict_check()
		except Exception:
			import traceback
			print("Color Flow [Rainbow setup] error:\n" + traceback.format_exc())


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
			dict(title="Setup Color Flow based on Color Layers", callback=self.Setup_Color_Flow),
			dict(title="Reset Color Flow", callback=self.Color_Flow_Reset),
			dict(title="Generate Color Flow Smart Filters", callback=self.Generate_Color_Flow_Smart_Filter),
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


	########################################################################################################
	#																									   #
	#	DATA + UI 																				           #
	#																									   #
	########################################################################################################
	#																									   #
	#																									   #

	# Aggregate per-step counts for a master, derived from the real layer state.
	@objc.python_method
	def Recompute_Master_Counts(self, masterId):
		order = list(self.meaning.keys())
		states = []
		for glyph in self.font.glyphs:
			try:
				state = glyph.layers[masterId].userData["com.hugojourdan.ColorFlow"]
			except Exception:
				state = None
			states.append(state if state else {})
		return colornames.count_states(states, order)

	# Return a valid counts dict for the master, repairing it in place when the
	# persisted value is missing, corrupt (e.g. a serialized None "<null>"), or
	# has drifted from the current colorNames keys.
	@objc.python_method
	def Get_Master_Counts(self, masterId):
		userData = self.font.userData
		allCounts = userData["com.hugojourdan.ColorFlow-master-data"]
		if not hasattr(allCounts, "keys"):
			userData["com.hugojourdan.ColorFlow-master-data"] = {}
			allCounts = userData["com.hugojourdan.ColorFlow-master-data"]
		counts = allCounts[masterId] if masterId in allCounts else None
		needsRecompute = not hasattr(counts, "keys")
		if not needsRecompute:
			for key in self.meaning.keys():
				if key not in counts:
					needsRecompute = True
					break
		if needsRecompute:
			counts = self.Recompute_Master_Counts(masterId)
			allCounts[masterId] = counts
		return counts

	# Store a counts dict for a master, repairing the container if corrupt.
	@objc.python_method
	def _store_master_counts(self, masterId, counts):
		allCounts = self.font.userData["com.hugojourdan.ColorFlow-master-data"]
		if not hasattr(allCounts, "keys"):
			self.font.userData["com.hugojourdan.ColorFlow-master-data"] = {}
			allCounts = self.font.userData["com.hugojourdan.ColorFlow-master-data"]
		allCounts[masterId] = counts

	# Mirror the checked steps into top-level userData keys that the generated
	# Smart Filters query (Has / Has-not a given step).
	@objc.python_method
	def _sync_shadow_keys(self, layer, state):
		for index in self.meaning.keys():
			shadowKey = "com.hugojourdan.ColorFlow_Color_" + index
			if index in state and state[index]:
				layer.userData[shadowKey] = index
			else:
				del layer.userData[shadowKey]  # UserDataProxy: no-throw if absent

	# Update Palette UI by mutating the widgets built once in settings().
	@objc.python_method
	def Update_Plugin_UI(self):
		try:
			if not self.font or not self.meaning:
				return
			selectedMasterId = self.font.selectedFontMaster.id
			counts = self.Get_Master_Counts(selectedMasterId)
			glyphCount = len(self.font.glyphs)

			masterName = self.font.selectedFontMaster.name
			if len(masterName) > 16:
				masterName = masterName[0:16] + "…"
			self.masterName.set(masterName)

			selectedLayers = self.font.selectedLayers or []
			firstColor = selectedLayers[0].color if selectedLayers else None

			for color, row in self.rows.items():
				count = counts[color] if color in counts else 0
				barWidth = (self.barWidth / glyphCount * count) if glyphCount else 0

				if selectedLayers:
					checked = all(self._layer_step(layer, color) for layer in selectedLayers)
					colored = checked and firstColor == int(color)
				else:
					checked = False
					colored = True

				row["check"].set(checked)
				if glyphCount and count >= glyphCount:
					row["count"].set("✅")
				else:
					row["count"].set(f"{count}/{glyphCount}")

				activeWidth = (barWidth + 0.01) if barWidth else 0
				if colored:
					row["color"].setPosSize((self.xPos, row["barY"], activeWidth, 16))
					row["gray"].setPosSize((self.xPos, row["barY"], 0, 16))
				else:
					row["gray"].setPosSize((self.xPos, row["barY"], activeWidth, 16))
					row["color"].setPosSize((self.xPos, row["barY"], 0, 16))
		except Exception:
			import traceback
			print("Color Flow [Update_Plugin_UI] error:\n" + traceback.format_exc())

	# True if the `color` step is checked on this layer (missing state == off).
	@objc.python_method
	def _layer_step(self, layer, color):
		state = layer.userData["com.hugojourdan.ColorFlow"]
		return bool(state) and color in state and bool(state[color])

	# UPDATEINTERFACE handler: cheap dirty-check, then refresh only when needed.
	@objc.python_method
	def update(self, sender):
		if self._windowController:
			self.font = self._windowController.documentFont()
		if not self.font:
			return

		# Font-View grouping: cheap dirty-check, then debounce the (expensive)
		# glyphOrder rebuild. Independent of the palette refresh below, and fully
		# guarded so it can never break the palette.
		try:
			grouping = getattr(self, "fontview", None)
			if grouping is not None and grouping.is_enabled(self.font) and grouping.is_dirty(self.font):
				self._pendingFont = self.font
				NSObject.cancelPreviousPerformRequestsWithTarget_selector_object_(
					self, "rainbowDebouncedRebuild:", None)
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
		layerStates = []
		for layer in selectedLayers:
			glyph = layer.parent
			name = glyph.name if glyph is not None else ""
			layerStates.append((name, layer.userData["com.hugojourdan.ColorFlow"]))
		signature = colornames.selection_signature(masterId, layerStates)
		if signature == getattr(self, "_lastSignature", None):
			return
		self._lastSignature = signature
		self.Update_Plugin_UI()

	# Action when a checkbox is toggled
	@objc.python_method
	def CheckBox_Callback(self, sender):
		if not self.font:
			return
		color = None
		for candidate, row in self.rows.items():
			if row["check"] is sender:
				color = candidate
				break
		if color is None:
			return

		checked = bool(sender.get())
		masterId = self.font.selectedFontMaster.id
		order = list(self.meaning.keys())
		key = "com.hugojourdan.ColorFlow"

		self.font.disableUpdateInterface()
		try:
			for layer in self.font.selectedLayers:
				state = layer.userData[key]
				if not state:
					layer.userData[key] = colornames.default_state(order)
					state = layer.userData[key]
				state[color] = checked
				layer.color = colornames.layer_color_for_state(state, order)
				self._sync_shadow_keys(layer, state)
			self._store_master_counts(masterId, self.Recompute_Master_Counts(masterId))
		finally:
			self.font.enableUpdateInterface()

		self._lastSignature = None  # force the next refresh
		self.Update_Plugin_UI()


	########################################################################################################
	#																									   #
	#	EXTRA FEATURES																					   #
	#																									   #
	########################################################################################################
	#																									   #
	#																									   #

	# Setup Color Flow from each layer's existing native color.
	@objc.python_method
	def Setup_Color_Flow(self, sender):
		if not self.font:
			return
		masterId = self.font.selectedFontMaster.id
		order = list(self.meaning.keys())
		key = "com.hugojourdan.ColorFlow"
		self.font.disableUpdateInterface()
		try:
			for glyph in self.font.glyphs:
				layer = glyph.layers[masterId]
				if layer is None:
					continue
				state = colornames.checked_state_for_color(layer.color, order)
				layer.userData[key] = state
				self._sync_shadow_keys(layer, state)
			self._store_master_counts(masterId, self.Recompute_Master_Counts(masterId))
		finally:
			self.font.enableUpdateInterface()
		print(f"✅ Color Flow set up from layer colors [{self.font.selectedFontMaster.name}]")
		Glyphs.showMacroWindow()
		self._lastSignature = None
		self.Update_Plugin_UI()


	# Reset Color Flow for the selected master (state, color, shadow keys, counts).
	@objc.python_method
	def Color_Flow_Reset(self, sender):
		if not self.font:
			return
		masterId = self.font.selectedFontMaster.id
		order = list(self.meaning.keys())
		key = "com.hugojourdan.ColorFlow"
		self.font.disableUpdateInterface()
		try:
			for glyph in self.font.glyphs:
				layer = glyph.layers[masterId]
				if layer is None:
					continue
				# Only drop our own shadow keys — never other plugins' userData.
				for existing in list(layer.userData.keys()):
					if str(existing).startswith("com.hugojourdan.ColorFlow_Color_"):
						del layer.userData[existing]
				layer.userData[key] = colornames.default_state(order)
				layer.color = None
			self._store_master_counts(masterId, {index: 0 for index in order})
		finally:
			self.font.enableUpdateInterface()
		print(f"✅ Color Flow reset [{self.font.selectedFontMaster.name}]")
		Glyphs.showMacroWindow()
		self._lastSignature = None
		self.Update_Plugin_UI()


	# Generate Color Flow smart filters in the Filter sidebar.
	@objc.python_method
	def Generate_Color_Flow_Smart_Filter(self, sender):
		import plistlib

		plistFile = os.path.expanduser("~/Library/Application Support/Glyphs 3/CustomFilter.plist")
		shadowPrefix = "com.hugojourdan.ColorFlow_Color_"

		try:
			with open(plistFile, "rb") as fp:
				pl = plistlib.load(fp)
		except OSError:
			Message(
				"Could not read CustomFilter.plist.\nAdd any item in the Filter "
				"section, restart Glyphs, then run this again.",
				title="Color Flow", OKButton=None)
			return

		layerColor = []
		notLayerColor = []
		for index, label in self.meaning.items():
			if not label:
				continue
			# The shadow keys are written by toggling / Setup; the predicate tests
			# for their presence on a layer.
			layerColor.append({"name": label, "predicate": f"'{shadowPrefix}{index}' IN layer.userData"})
			notLayerColor.append({"name": label, "predicate": f"NOT '{shadowPrefix}{index}' IN layer.userData"})

		group = {"name": "Color Flow", "subGroup": [
			{"name": "Has[...]", "subGroup": layerColor},
			{"name": "Has not[...]", "subGroup": notLayerColor},
		]}

		# Replace any existing Color Flow group rather than appending duplicates.
		pl = [item for item in pl if item.get("name") != "Color Flow"]
		pl.append(group)

		try:
			with open(plistFile, "wb") as fp:
				plistlib.dump(pl, fp)
		except OSError as error:
			Message(f"Could not write CustomFilter.plist:\n{error}", title="Color Flow", OKButton=None)
			return

		Message(
			"Color Flow Smart Filters generated.\nRestart Glyphs to see them in the Filter list.",
			title="Color Flow", OKButton=None)


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

		# Copy by value, never by reference: each master must own an independent
		# dict, otherwise editing one master's checkboxes mutates the other's.
		masterData = self.font.userData["com.hugojourdan.ColorFlow-master-data"]
		if masterData is not None and fromMasterID in masterData:
			masterData[toMasterID] = dict(masterData[fromMasterID])

		for glyph in self.font.glyphs:
			glyph.layers[toMasterID].color = glyph.layers[fromMasterID].color
			fromState = glyph.layers[fromMasterID].userData["com.hugojourdan.ColorFlow"]
			if fromState:
				glyph.layers[toMasterID].userData["com.hugojourdan.ColorFlow"] = dict(fromState)

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


	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__

