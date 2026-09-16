# encoding: utf-8
from __future__ import division, print_function, unicode_literals


#########################################################
#														#
#	Color Flow Palette plugins							#
#														#
#	Read the docs:										#
#	https://github.com/HugoJourdan/Color-Flow			#
#														#
#########################################################


import re
import os
import codecs
import objc
from datetime import datetime
from vanilla import Window, FloatingWindow, Group, Box, Button, PopUpButton, ActionButton, HorizontalLine, TextBox, CheckBox, dialogs
from AppKit import NSColor, NSMenu, NSMenuItem, NSLineBreakByTruncatingTail
from GlyphsApp import Message
from GlyphsApp.plugins import PalettePlugin
#from GlyphsApp.UI import
from GlyphsApp import Glyphs, UPDATEINTERFACE, DOCUMENTCLOSED


SHORTCUT_COMMANDS = (
	("Toggle Red Checkbox", "red", "0", b"toggleRedShortcut:"),
	("Toggle Orange Checkbox", "orange", "1", b"toggleOrangeShortcut:"),
	("Toggle Brown Checkbox", "brown", "2", b"toggleBrownShortcut:"),
	("Toggle Yellow Checkbox", "yellow", "3", b"toggleYellowShortcut:"),
	("Toggle Green Checkbox", "green", "4", b"toggleGreenShortcut:"),
	("Toggle DarkGreen Checkbox", "dark-green", "5", b"toggleDarkGreenShortcut:"),
	("Toggle Blue Checkbox", "blue", "6", b"toggleBlueShortcut:"),
	("Toggle DarkBlue Checkbox", "dark-blue", "7", b"toggleDarkBlueShortcut:"),
	("Toggle Purple Checkbox", "purple", "8", b"togglePurpleShortcut:"),
	("Toggle Magenta Checkbox", "magenta", "9", b"toggleMagentaShortcut:"),
	("Toggle Grey Checkbox", "grey", "10", b"toggleGreyShortcut:"),
	("Toggle Charcoal Checkbox", "charcoal", "11", b"toggleCharcoalShortcut:"),
)

shortcutTarget = None


class ColorFlow(PalettePlugin):
	COLOR_FLOW_LAYER_KEY = "com.hugojourdan.ColorFlow"


	#####################################################################################################
	#																									#
	#	SETUP																							#
	#																									#
	#####################################################################################################
	#																									#
	#																									#

	@objc.python_method
	def settings(self):
		global shortcutTarget
		if shortcutTarget is None:
			shortcutTarget = self
			self.Register_Shortcuts()

		self.name = 'Color Flow'
		self._init = False
		self.compactedFonts = set()
		self.colorKeys = {
			"0": (0.85, 0.26, 0.06, 0.5),
			"1": (0.99, 0.62, 0.11, 0.5),
			"2": (0.65, 0.48, 0.20, 0.5),
			"3": (0.97, 0.90, 0.00, 0.5),
			"4": (0.67, 0.95, 0.38, 0.5),
			"5": (0.04, 0.57, 0.04, 0.5),
			"6": (0.06, 0.60, 0.98, 0.5),
			"7": (0.00, 0.20, 0.88, 0.5),
			"8": (0.50, 0.09, 0.79, 0.5),
			"9": (0.98, 0.36, 0.67, 0.5),
			"10": (0.50, 0.50, 0.50, 0.5),
			"11": (0.25, 0.25, 0.25, 0.5)
		}
		self.meaning = self.Map_Keys(self.Get_Key_File())
		self.width = 160
		self.rectHeight = 10
		self.lineSpacing = 20
		self.shift = 10
		self.barWidth = self.width + 6
		self.barWidthDic = {}
		self.height = 20 * len([x for x in self.meaning.values() if x]) + 21
		self.xPos = 9

		self.paletteView = Window((self.width, self.height + 10))
		self.paletteView.frame = Group((0, 0, self.width, self.height))
		if not Glyphs.defaults["com.hugojourdan.ColorFlow-Report"]:
			Glyphs.defaults["com.hugojourdan.ColorFlow-Report"] = "Enable Color Flow Report"
			self.report = False

		# Draw Action Button
		self.Update_Settings_Button()

		#---------------------------------------------------------------------------#
		# Draw Master Name Field													#
		#---------------------------------------------------------------------------#

		if Glyphs.versionNumber >= 4:
			self.paletteView.frame.masterNameBox = Box((6, 0, -8, 15), fillColor=(NSColor.colorWithRed_green_blue_alpha_(0, 0, 0, 0.1)), cornerRadius=4, borderWidth=0)
			self.paletteView.frame.masterName = TextBox((8, 0, -9, 20), "", alignment="left", sizeStyle='small')
		else:
			self.paletteView.frame.masterNameBox = Box((6, 0, 127, 10), fillColor=(NSColor.colorWithRed_green_blue_alpha_(0, 0, 0, 0.1)), cornerRadius=4, borderWidth=0)
			self.paletteView.frame.masterName = TextBox((8, 0, 140, 20), "", alignment="left", sizeStyle='small')

		cell = self.paletteView.frame.masterName.getNSTextField().cell()
		cell.setLineBreakMode_(NSLineBreakByTruncatingTail)
		cell.setWraps_(False)
		cell.setScrollable_(False)

		#---------------------------------------------------------------------------#
		# Set up color rows															#
		#---------------------------------------------------------------------------#
		self.Build_Color_Rows()

		# # Select a master if none is selected
		# if not self.font.selectedFontMaster:
		# 	self.font.selectedFontMaster = self.font.masters[0]

		# Needed to display the palette plugin
		self.dialog = self.paletteView.frame.getNSView()

	@objc.python_method
	def Build_Color_Rows(self):
		"""Create the controls for every visible color row once."""
		self.colorRows = {}
		yPos = 32
		gray = NSColor.colorWithRed_green_blue_alpha_(0, 0, 0, 0.06)

		for color, meaning in self.meaning.items():
			if not meaning:
				continue

			colorValue = self.colorKeys.get(str(color))
			fillColor = NSColor.colorWithRed_green_blue_alpha_(*colorValue) if colorValue else None
			barPosition = (self.xPos, yPos + 1 - self.shift, 0.01, 16)

			line = HorizontalLine((0, yPos - 11, 0, 1))
			colorTag = Box((0, yPos + 1 - self.shift, 3, 16), fillColor=fillColor, cornerRadius=0, borderWidth=0)
			grayBar = Box(barPosition, fillColor=gray, cornerRadius=0, borderWidth=0)
			colorBar = Box(barPosition, fillColor=fillColor, cornerRadius=0, borderWidth=0)
			checkbox = CheckBox((12, yPos - 1 - self.shift, -10, 20), meaning, value=False, callback=self.CheckBox_Callback, sizeStyle='small')
			countLabel = TextBox((self.width - 50, yPos + 2 - self.shift, -6, 20), "0/0", alignment="right", sizeStyle='small')

			grayBar.show(False)
			colorBar.show(False)

			setattr(self.paletteView.frame, str(color) + "line", line)
			setattr(self.paletteView.frame, str(color) + "colorTag", colorTag)
			setattr(self.paletteView.frame, str(color) + "box", grayBar)
			setattr(self.paletteView.frame, str(color) + "colorBox", colorBar)
			setattr(self.paletteView.frame, str(color), checkbox)
			setattr(self.paletteView.frame, str(color) + "count", countLabel)

			self.colorRows[color] = {
				"grayBar": grayBar,
				"colorBar": colorBar,
				"checkbox": checkbox,
				"countLabel": countLabel,
				"barY": yPos + 1 - self.shift,
			}
			yPos += 20

	def settingsMenu(self):
		self._settingsMenu = NSMenu()
		self._settingsMenu.addItem_(NSMenuItem("Setup Color Flow based on Color Layers", callback="SetupColorFlow:", target=self))
		self._settingsMenu.addItem_(NSMenuItem(title="Reset Color Flow", callback="ColorFlowReset:", target=self))
		self._settingsMenu.addItem_(NSMenuItem(title="Generate Color Flow Smart Filters", callback="GenerateColorFlowSmartFilter:", target=self))
		self._settingsMenu.addItem_(NSMenuItem(title="Copy Color Flow to Master", callback="CopyColorFlowToMaster:", target=self))
		self._settingsMenu.addItem_(NSMenuItem(title=Glyphs.defaults["com.hugojourdan.ColorFlow-Report"], callback="ActivateColorFlowReport:", target=self))
		self._settingsMenu.addItem_(NSMenuItem.separatorItem())
		self._settingsMenu.addItem_(NSMenuItem(title="Open Color Flow Documentation", callback="OpenColorFlowDocumentation:", target=self))
		return self._settingsMenu

	def Update_Settings_Button(self):
		if Glyphs.versionNumber <= 3:
			if hasattr(self.paletteView.frame, "actionPopUpButton"):
				delattr(self.paletteView.frame, "actionPopUpButton")

			self.paletteView.frame.actionPopUpButton = ActionButton((self.width - 22, 0, 34, 19), [
					dict(title="Setup Color Flow based on Color Layers", callback=self.SetupColorFlow_),
					dict(title="Reset Color Flow", callback=self.ColorFlowReset_),
					dict(title="Generate Color Flow Smart Filters", callback=self.GenerateColorFlowSmartFilter_),
					dict(title="Copy Color Flow to Master", callback=self.CopyColorFlowToMaster_),
					dict(title=Glyphs.defaults["com.hugojourdan.ColorFlow-Report"], callback=self.ActivateColorFlowReport_),
					"----",
					dict(title="Open Color Flow Documentation", callback=self.OpenColorFlowDocumentation_),
			],
				sizeStyle='small')

	@objc.python_method
	def start(self):
		Glyphs.addCallback(self.update, UPDATEINTERFACE)
		self.font = Glyphs.font
		self._init = False
		self.startSession = datetime.now().strftime('%m/%d/%Y - %H:%M')
		self.update(self._windowController)
		self.Color_Flow_Report(self._windowController)


		if Glyphs.defaults["com.hugojourdan.ColorFlow-Report"] == "Disable Color Flow Report":
			self.report = True
			Glyphs.addCallback(self.Color_Flow_Report_PRINT, DOCUMENTCLOSED)


	@objc.python_method
	def Register_Shortcuts(self):
		"""Register assignable Color Flow commands when the Glyphs 4 API exists."""

		try:
			shortcutHandler = objc.lookUpClass("GSShortcutHandler")
		except:
			return

		for title, identifier, color, action in SHORTCUT_COMMANDS:
			shortcutHandler.registerShortcutCommand_group_identifier_action_target_character_modifierFlags_(
				title,
				"Color Flow",
				"com.hugojourdan.ColorFlow." + identifier,
				action,
				shortcutTarget,
				None,
				0,
			)

	@objc.python_method
	def Toggle_Color_From_Shortcut(self, color):
		"""Apply the same sparse data toggle as the Glyphs 3 scripts."""
		font = Glyphs.font
		if font is None:
			return
		self.font = font
		for layer in font.selectedLayers or []:
			colorFlowData = self.Get_Layer_Color_Flow_Data(layer, clean=True)
			self.Set_Layer_Color_Flow_Value(layer, color, not colorFlowData.get(color, False))
		self.Update_Plugin_UI()
		Glyphs.redraw()

	def toggleRedShortcut_(self, sender):
		self.Toggle_Color_From_Shortcut("0")

	def toggleOrangeShortcut_(self, sender):
		self.Toggle_Color_From_Shortcut("1")

	def toggleBrownShortcut_(self, sender):
		self.Toggle_Color_From_Shortcut("2")

	def toggleYellowShortcut_(self, sender):
		self.Toggle_Color_From_Shortcut("3")

	def toggleGreenShortcut_(self, sender):
		self.Toggle_Color_From_Shortcut("4")

	def toggleDarkGreenShortcut_(self, sender):
		self.Toggle_Color_From_Shortcut("5")

	def toggleBlueShortcut_(self, sender):
		self.Toggle_Color_From_Shortcut("6")

	def toggleDarkBlueShortcut_(self, sender):
		self.Toggle_Color_From_Shortcut("7")

	def togglePurpleShortcut_(self, sender):
		self.Toggle_Color_From_Shortcut("8")

	def toggleMagentaShortcut_(self, sender):
		self.Toggle_Color_From_Shortcut("9")

	def toggleGreyShortcut_(self, sender):
		self.Toggle_Color_From_Shortcut("10")

	def toggleCharcoalShortcut_(self, sender):
		self.Toggle_Color_From_Shortcut("11")


	#####################################################################################################
	#																									#
	#	DATA + UI																						#
	#																									#
	#####################################################################################################
	#																									#
	#																									#

	# Build Dic with number of LayerColor
	@objc.python_method
	def Get_Layer_Color_Flow_Data(self, layer, clean=False):
		"""Return only enabled Color Flow values for a layer.

		Missing values represent unchecked colors.  When ``clean`` is true,
		legacy dictionaries containing false values are rewritten sparsely.
		"""
		storedData = layer.userData[self.COLOR_FLOW_LAYER_KEY]
		colorFlowData = {}

		if storedData:
			for color, value in storedData.items():
				if value:
					colorFlowData[str(color)] = True

		if clean:
			if colorFlowData:
				if dict(storedData.items()) != colorFlowData:
					layer.userData[self.COLOR_FLOW_LAYER_KEY] = colorFlowData
			elif storedData is not None:
				del layer.userData[self.COLOR_FLOW_LAYER_KEY]

		return colorFlowData

	@objc.python_method
	def Set_Layer_Color_Flow_Value(self, layer, color, value):
		"""Store an enabled value, or remove it (and an empty layer dictionary)."""
		colorFlowData = self.Get_Layer_Color_Flow_Data(layer)
		color = str(color)

		if value:
			colorFlowData[color] = True
		else:
			colorFlowData.pop(color, None)

		if colorFlowData:
			layer.userData[self.COLOR_FLOW_LAYER_KEY] = colorFlowData
		elif layer.userData[self.COLOR_FLOW_LAYER_KEY] is not None:
			del layer.userData[self.COLOR_FLOW_LAYER_KEY]

	@objc.python_method
	def Set_Layer_Color_Flow_Data(self, layer, colorFlowData):
		"""Replace a layer's Color Flow data using the sparse representation."""
		colorFlowData = {
			str(color): True
			for color, value in colorFlowData.items()
			if value
		}
		if colorFlowData:
			layer.userData[self.COLOR_FLOW_LAYER_KEY] = colorFlowData
		elif layer.userData[self.COLOR_FLOW_LAYER_KEY] is not None:
			del layer.userData[self.COLOR_FLOW_LAYER_KEY]

	@objc.python_method
	def Update_Layer_Color(self, layer):
		"""Update the native layer color using the configured workflow order."""
		colorFlowData = self.Get_Layer_Color_Flow_Data(layer, clean=True)
		layerColor = None
		for color in self.meaning.keys():
			if not colorFlowData.get(color, False):
				break
			layerColor = int(color)
		if layer.color != layerColor:
			layer.color = layerColor


	@objc.python_method
	def Get_Dic_Layer_Color_Label(self, masterId):
		try:
			self.LayerColorLabel = {k: 0 for k in self.meaning.keys()}
			for glyph in self.font.glyphs:
				colorFlowData = self.Get_Layer_Color_Flow_Data(glyph.layers[masterId], clean=True)

				# colorFlowData = ["0":0, "1":0, "2":1, ..."]
				for k, v in colorFlowData.items():
					self.LayerColorLabel[k] += int(v)

			return self.LayerColorLabel
		except:
			pass

	# Update Palette UI
	@objc.python_method
	def Update_Plugin_UI(self):
		try:
			selectedMasterId = self.font.selectedFontMaster.id

			for layer in self.font.selectedLayers or []:
				self.Update_Layer_Color(layer)

			self.LayerColorLabel = self.Get_Dic_Layer_Color_Label(selectedMasterId)
			masterData = self.font.userData["com.hugojourdan.ColorFlow-master-data"] or {}
			if selectedMasterId not in masterData or masterData[selectedMasterId] != self.LayerColorLabel:
				masterData[selectedMasterId] = self.LayerColorLabel
				self.font.userData["com.hugojourdan.ColorFlow-master-data"] = masterData


			#---------------------------------------------------------------------------#
			# Update data for sorting in CF Smart Filter								#
			#---------------------------------------------------------------------------#
			try:
				for layer in self.font.selectedLayers:
					colorFlowData = self.Get_Layer_Color_Flow_Data(layer, clean=True)
					for k in self.meaning.keys():
						filterKey = "com.hugojourdan.ColorFlow_Color_" + str(k)
						if colorFlowData.get(k, False):
							layer.userData[filterKey] = str(k)
						elif layer.userData[filterKey] is not None:
							del layer.userData[filterKey]
			except:
				pass

			#---------------------------------------------------------------------------#
			# Access, build data to update UI											#
			#---------------------------------------------------------------------------#
			glyphCount = len(self.font.glyphs)
			for color in self.LayerColorLabel:
				self.barWidthDic[color] = self.barWidth / glyphCount * self.LayerColorLabel[color] if glyphCount else 0

			#---------------------------------------------------------------------------#
			# Updated element in UI														#
			#---------------------------------------------------------------------------#

			# Update Master Name
			masterName = self.font.selectedFontMaster.name
			self.paletteView.frame.masterName.set(masterName)

			selectedLayers = list(self.font.selectedLayers or [])
			selectedLayerData = [
				self.Get_Layer_Color_Flow_Data(layer, clean=True)
				for layer in selectedLayers
			]

			for color, row in self.colorRows.items():
				check = bool(selectedLayerData) and all(
					colorFlowData.get(color, False)
					for colorFlowData in selectedLayerData
				)
				row["checkbox"].set(check)

				count = self.LayerColorLabel[color]
				row["countLabel"].set("✅" if count >= glyphCount else f"{count}/{glyphCount}")

				barWidth = self.barWidthDic[color]
				barPosition = (self.xPos, row["barY"], barWidth + 0.01, 16)
				row["grayBar"].setPosSize(barPosition)
				row["colorBar"].setPosSize(barPosition)
				row["grayBar"].show(bool(selectedLayers) and not check and barWidth > 0)
				row["colorBar"].show(not selectedLayers and barWidth > 0)
		except:
			pass

	# Detect if UI need to be update
	@objc.python_method
	def update(self, sender):

		if self._windowController:
			self.font = self._windowController.documentFont()
			self.selectedLayers = self._windowController.selectedLayers()

		#-------------------------------------------------------------------------------#
		# Draw Color Flow UI when														#
		#-------------------------------------------------------------------------------#

		try:
			if self.font:
				self.Update_Plugin_UI()
				self._init = True
				trigger = True
		except:
			pass

		#-------------------------------------------------------------------------------#
		# Compact legacy layer data to the sparse representation once per open font      #
		#-------------------------------------------------------------------------------#
		try:
			fontIdentity = id(self.font)
			if fontIdentity not in self.compactedFonts:
				for glyph in self.font.glyphs:
					for layer in glyph.layers:
						self.Get_Layer_Color_Flow_Data(layer, clean=True)
				self.compactedFonts.add(fontIdentity)

		except:
			pass

		#---------------------------------------------------------------------------#
		# Create data is no															#
		#---------------------------------------------------------------------------#
		if not self.font.userData["com.hugojourdan.ColorFlow-export"]:
			self.font.userData["com.hugojourdan.ColorFlow-export"] = None
		if not self.font.userData["com.hugojourdan.ColorFlow-selectedLayer"]:
			self.font.userData["com.hugojourdan.ColorFlow-selectedLayer"] = False
		if not self.font.userData["com.hugojourdan.ColorFlow-selectedLayer-data"]:
			self.font.userData["com.hugojourdan.ColorFlow-selectedLayer-data"] = None
		if not self.font.userData["com.hugojourdan.ColorFlow-currentFont"]:
			self.font.userData["com.hugojourdan.ColorFlow-currentFont"] = None

		if not self.font.userData["com.hugojourdan.ColorFlow-master-data"]:
			self.font.userData["com.hugojourdan.ColorFlow-master-data"] = {}

		# for master in self.font.masters:
		# 	masterId = master.id
		# 	if masterId not in self.font.userData["com.hugojourdan.ColorFlow-master-data"].keys():
		# 		self.font.userData["com.hugojourdan.ColorFlow-master-data"][masterId] = self.Get_Dic_Layer_Color_Label(masterId)


		#---------------------------------------------------------------------------#
		# If master added, create its aggregate Color Flow data                     #
		#---------------------------------------------------------------------------#
		try:
			for master in self.font.masters:
				if master.id not in self.font.userData["com.hugojourdan.ColorFlow-master-data"]:
					self.font.userData["com.hugojourdan.ColorFlow-master-data"][master.id] = self.Get_Dic_Layer_Color_Label(master.id)
					self.Update_Plugin_UI()
		except:
			pass

		if not self._init:
			try:
				self.Update_Plugin_UI()
				self._init = True
				trigger = True
			except:
				pass

		try:
			if self._windowController:

				self.font = self._windowController.documentFont()
				self.selectedLayers = self._windowController.selectedLayers()

				#-------------------------------------------------------------------------------#
				# If Palette plugin is open, try update											#
				#-------------------------------------------------------------------------------#
				if self.dialog.frame().origin.y == 0:
					trigger = False

					#---------------------------------------------------------------------------#
					# If no layer selected, trigger UI update									#
					#---------------------------------------------------------------------------#
					try:
						if not trigger and self.font.selectedLayers is None:
							self.font.userData["com.hugojourdan.ColorFlow-selectedLayer"] = False
							self.Update_Plugin_UI()
							trigger = True
					except:
						pass

					#---------------------------------------------------------------------------#
					# If layer selected, trigger UI update										#
					#---------------------------------------------------------------------------#
					try:
						if not trigger and not self.font.userData["com.hugojourdan.ColorFlow-selectedLayer"]:
							self.Update_Plugin_UI()
							self.font.userData["com.hugojourdan.ColorFlow-selectedLayer"] = True
							trigger = True
					except:
						pass

					#---------------------------------------------------------------------------#
					# If selected master changed, trigger UI update								#
					#---------------------------------------------------------------------------#
					try:
						if self.font.userData["com.hugojourdan.ColorFlow-selectedMaster"] != self.font.selectedFontMaster:
							self.font.userData["com.hugojourdan.ColorFlow-selectedMaster"] = self.font.selectedFontMaster
							self.Update_Plugin_UI()
							trigger = True
					except:
						pass

					#---------------------------------------------------------------------------#
					# If Color Flow Data changed, trigger UI update								#
					#---------------------------------------------------------------------------#
					try:
						if not trigger:
							selectedLayerData = self.Get_Layer_Color_Flow_Data(self.font.selectedLayers[0], clean=True)
							if self.font.userData["com.hugojourdan.ColorFlow-selectedLayer-data"] != selectedLayerData:
								self.font.userData["com.hugojourdan.ColorFlow-selectedLayer-data"] = selectedLayerData.copy()
								self.Update_Plugin_UI()
								trigger = True

					except:
						pass
		except:
			pass

	# Action when a checkbox is toogle
	@objc.python_method
	def CheckBox_Callback(self, sender):

		color = sender.getTitle()
		check = sender.get()

		for k, v in self.meaning.items():
			if color == v:
				color = k

		for layer in self.font.selectedLayers:
			self.Set_Layer_Color_Flow_Value(layer, color, check)

		self.Update_Plugin_UI()


	#####################################################################################################
	#																									#
	#	EXTRA FEATURES																					#
	#																									#
	#####################################################################################################
	#																									#
	#																									#


	def SetupColorFlow_(self, sender):
		"""Setup ColorFlow based on Color Layers callback"""

		print(f"✅ UPDATE > ColorFlow settings [{self.font.selectedFontMaster.name}]")

		selectedMasterId = self.font.selectedFontMaster.id
		self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterId] = {x: 0 for x in self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterId]}

		# selectedLayers = self.font.selectedLayers

		for glyph in self.font.glyphs:
			for layer in glyph.layers:
				if layer.isMasterLayer and layer.layerId == selectedMasterId:
					colorFlowData = {}
					if layer.color is not None:
						for k, v in self.meaning.items():
							colorFlowData[k] = True
							self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterId][k] += 1
							if int(k) == layer.color:
								break
					self.Set_Layer_Color_Flow_Data(layer, colorFlowData)

		Glyphs.showMacroWindow()
		self.Update_Plugin_UI()

	def ColorFlowReset_(self, sender):
		"""Reset ColorFlow callback"""

		print(f"✅ RESET > ColorFlow settings [{self.font.selectedFontMaster.name}]")

		for glyph in self.font.glyphs:
			for layer in glyph.layers:
				if layer.isMasterLayer and layer.layerId == self.font.selectedFontMaster.id:
					self.Set_Layer_Color_Flow_Data(layer, {})
					layer.color = None
				else:
					pass

		selectedMasterId = self.font.selectedFontMaster.id
		# for master in self.font.masters:
		# 	self.font.userData["com.hugojourdan.ColorFlow-master-data"][master.name] = {x: 0 for x in self.font.userData["com.hugojourdan.ColorFlow-master-data"][master.name]}
		self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterId] = {x: 0 for x in self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterId]}

		Glyphs.showMacroWindow()
		self.Update_Plugin_UI()


	def GenerateColorFlowSmartFilter_(self, sender):
		"""Generate Color Flow smart filter"""

		import plistlib

		plistFile = os.path.expanduser("~/Library/Application Support/Glyphs 3/CustomFilter.plist")

		try:

			with open(plistFile, 'rb') as fp:

				pl = plistlib.load(fp)
				trigger = True
				layerColor = []
				notlayerColor = []

				for item in pl:
					if item["name"] == "Color Flow":
						trigger = False

				for i in range(0, 12):
					layerColor.append({'name': self.meaning[str(i)], 'predicate': f"'{str(i)}' IN layer.userData"})
					notlayerColor.append({'name': self.meaning[str(i)], 'predicate': f"NOT '{str(i)}' IN layer.userData"})

				pl.append({'name': 'Color Flow', 'subGroup': [{'name': 'Has[...]', 'subGroup': layerColor}, {'name': 'Has not[...]', 'subGroup': notlayerColor}]})

			if trigger:
				with open(plistFile, 'wb') as fp:
					plistlib.dump(pl, fp)
				Message("Color Flow Smart Filters have been generated.\nRestart Glyph to see them", title='Alert', OKButton=None)
			else:

				if dialogs.askYesNo("Color Flow", "Color Flow filter already exist, do you want to overwrite them ?"):
					with open(plistFile, 'wb') as fp:
						pl.remove({'name': 'Color Flow', 'subGroup': [{'name': 'Has[...]', 'subGroup': layerColor}, {'name': 'Has not[...]', 'subGroup': notlayerColor}]})

						plistlib.dump(pl, fp)
					Message("Color Flow Smart Filters have been generated.\nRestart Glyph to update Filter UI", title='Alert', OKButton=None)
		except:
			Message("To Fix it, add an item in Filter Section and Restart Glyph. After that run again this function", title=".plist not writable", OKButton=None)


	def CopyColorFlowToMaster_(self, sender):
		"""Copy Color Flow Data to Master"""

		MASTER = []
		for master in self.font.masters:
			MASTER.append(master.name)

		self.w = FloatingWindow((200, 110), "Copy Color Flow Data")
		self.w.textFrom = TextBox((10, 10, -10, 17), "From")
		self.w.fromMaster = PopUpButton((55, 10, -10, 20), MASTER)
		self.w.line = HorizontalLine((10, 37, -10, 1))
		self.w.line2 = HorizontalLine((10, 37, -10, 1))
		self.w.textTo = TextBox((10, 46, -10, 17), "To")
		self.w.toMaster = PopUpButton((55, 46, -10, 20), MASTER)
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

		self.font.userData["com.hugojourdan.ColorFlow-master-data"][toMasterID] = self.font.userData["com.hugojourdan.ColorFlow-master-data"][fromMasterID]

		for glyph in self.font.glyphs:
			glyph.layers[toMasterID].color = glyph.layers[fromMasterID].color
			colorFlowData = self.Get_Layer_Color_Flow_Data(glyph.layers[fromMasterID], clean=True)
			self.Set_Layer_Color_Flow_Data(glyph.layers[toMasterID], colorFlowData)

	def OpenColorFlowDocumentation_(self, sender):

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

		try:
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

			with open(saveLocation + "/" + fileName, 'w') as f:
				f.write(f"Session start : {self.startSession}\nSession stop : {dateNow.strftime('%m/%d/%Y - %H:%M')}\n\n")
				for master, data in LayerColorChanged.items():
					f.write(f"Master : {self.font.masters[master].name}\n-----------------------------------------------------\n")
					for k, v in data.items():
						f.write(f"{k} : {v}\n- - - - - - - - - - - - - - - - - - - - - - - - - - -\n")
					f.write("\n=====================================================\n\n")
			f.close()

		except:
			pass

		# with open('/Users/hugojourdan/Desktop/POUBELLE/DATA.json', 'w') as outfile:
		# 	json.dump(layerColorData, outfile)


	def ActivateColorFlowReport_(self, sender):

		if Glyphs.defaults["com.hugojourdan.ColorFlow-Report"] == "Enable Color Flow Report":
			self.report = True
			Glyphs.addCallback(self.Color_Flow_Report_PRINT, DOCUMENTCLOSED)
			Glyphs.defaults["com.hugojourdan.ColorFlow-Report"] = "Disable Color Flow Report"
			print("Color Flow Report enabled.\nWhen you will close your document, a .txt file will be generated in 'Color Flow Reports' folder located next to your Glyphs file")

			Glyphs.showMacroWindow()

		else:
			self.report = False
			Glyphs.removeCallback(self.Color_Flow_Report_PRINT, DOCUMENTCLOSED)
			Glyphs.defaults["com.hugojourdan.ColorFlow-Report"] = "Enable Color Flow Report"
			print("Color Flow Report disabled")
			Glyphs.showMacroWindow()

		self.Update_Settings_Button()


	#####################################################################################################
	#																									#
	#	SETUP COLOR MEANING																				#
	#																									#
	#####################################################################################################
	#																									#
	#																									#


	@objc.python_method
	def Get_Key_File(self):
		"""Find and read ColorNames.txt, if missing, create it"""
		keyFile = None
		try:
			thisDirPath = os.path.dirname(Glyphs.font.filepath)
			localKeyFile = thisDirPath + '/colorNames.txt'
			if os.path.exists(localKeyFile):
				keyFile = localKeyFile
		except:
			pass

		dirInfo = os.path.expanduser("~/Library/Application Support/Glyphs 3/info")
		if not os.path.exists(dirInfo):
			os.mkdir(dirInfo)

		if keyFile is None:
			keyFile = os.path.expanduser('~/Library/Application Support/Glyphs 3/info/colorNames.txt')

		if not os.path.exists(keyFile):
			f = open(keyFile, "w+")
			f.write("red=Red\norange=Orange\nbrown=Brown\nyellow=Yellow\nlightGreen=Light green\ndarkGreen=Dark green\nlightBlue=Light blue\ndarkBlue=Dark blue\npurple=Purple\nmagenta=Magenta\nlightGray=Light Gray\ncharcoal=Charcoal")
		else:
			pass
		return keyFile


	@objc.python_method
	def Map_Keys(self, keyFile):
		"""Build Dic from ColorNames.txt content"""
		self.colourLabels = {}
		if not os.path.exists(keyFile):
			return self.colourLabels

		replace = {"red": "0", "orange": "1", "brown": "2", "yellow": "3", "lightGreen": "4", "darkGreen": "5", "lightBlue": "6", "darkBlue": "7", "purple": "8", "magenta": "9", "lightGray": "10", "charcoal": "11"}

		with codecs.open(keyFile, "r", "utf-8") as file:
			for line in file:
				colour = re.match(r".*?(?=\=)", line).group(0)
				label = re.search(r"(?<=\=).*", line).group(0)
				if colour in replace:
					colour = replace[colour]
				self.colourLabels[colour] = label

		return self.colourLabels


	#####################################################################################################
	#																									#
	#	DON'T MODIFY																					#
	#																									#
	#####################################################################################################
	#																									#


	@objc.python_method
	def __del__(self):
		# Delete callbacks when Glyphs quits, otherwise it'll crash :(
		Glyphs.removeCallback(self.update)


	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__
