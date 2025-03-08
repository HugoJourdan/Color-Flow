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
from AppKit import NSColor
from GlyphsApp.plugins import PalettePlugin, Message
#from GlyphsApp.UI import
from GlyphsApp import Glyphs, UPDATEINTERFACE, DOCUMENTCLOSED



class ColorFlow(PalettePlugin):


	#####################################################################################################
	#																									#
	#	SETUP																							#
	#																									#
	#####################################################################################################
	#																									#
	#																									#

	@objc.python_method
	def settings(self):
		self.name = 'Color Flow'
		self.init = False
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
		self.height = 22 * len([x for x in self.meaning.values() if x]) + 25
		self.xPos = 9

		self.paletteView = Window((self.width, self.height + 10))
		self.paletteView.frame = Group((0, 0, self.width, self.height))
		if not Glyphs.defaults["com.hugojourdan.ColorFlow-Report"]:
			Glyphs.defaults["com.hugojourdan.ColorFlow-Report"] = "Enable Color Flow Report"
			self.report = False

		# Draw Action Button
		self.paletteView.frame.actionPopUpButton = ActionButton((self.width - 22, 0, 34, 19), [
			dict(title="Setup Color Flow based on Color Layers", callback=self.Setup_Color_Flow),
			dict(title="Reset Color Flow", callback=self.Color_Flow_Reset),
			dict(title="Generate Color Flow Smart Filters", callback=self.Generate_Color_Flow_Smart_Filter),
			dict(title="Copy Color Flow to Master", callback=self.Copy_Color_Flow_To_Master),
			dict(title=Glyphs.defaults["com.hugojourdan.ColorFlow-Report"], callback=self.Activate_Color_Flow_Report),
			"----",
			dict(title="Open Color Flow Documentation", callback=self.Open_Color_Flow_Documentation),
		],
			sizeStyle='small')

		#---------------------------------------------------------------------------#
		# Draw Master Name Field													#
		#---------------------------------------------------------------------------#
		self.paletteView.frame.masterNameBox = Box((6, 4, 127, 10), fillColor=(NSColor.colorWithRed_green_blue_alpha_(0, 0, 0, 0.1)), cornerRadius=4, borderWidth=0)

		#---------------------------------------------------------------------------#
		# Draw Horitzontal Lines													#
		#---------------------------------------------------------------------------#
		yPos = 25
		for k, v in self.meaning.items():
			setattr(self.paletteView.frame, str(k) + "line", HorizontalLine((0, yPos, 0, 1)))
			yPos += 22

		#---------------------------------------------------------------------------#
		# Draw Color Tags															#
		#---------------------------------------------------------------------------#
		yPos = 36
		for k, v in self.meaning.items():
			if v:
				color_value = self.colorKeys.get(str(k))
				color = NSColor.colorWithRed_green_blue_alpha_(*color_value) if color_value else None
				setattr(self.paletteView.frame, str(k) + "colorTag", Box((0, yPos + 1 - self.shift, 3, 16), fillColor=(color), cornerRadius=0, borderWidth=0))
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
		self.startSession = datetime.now().strftime('%m/%d/%Y - %H:%M')
		self.update(self._windowController)
		self.Color_Flow_Report(self._windowController)


		if Glyphs.defaults["com.hugojourdan.ColorFlow-Report"] == "Disable Color Flow Report":
			self.report = True
			Glyphs.addCallback(self.Color_Flow_Report_PRINT, DOCUMENTCLOSED)


	#####################################################################################################
	#																									#
	#	DATA + UI																						#
	#																									#
	#####################################################################################################
	#																									#
	#																									#

	# Build Dic with number of LayerColor


	@objc.python_method
	def Get_Dic_Layer_Color_Label(self, masterId):
		try:
			self.LayerColorLabel = {k: False for k in self.meaning.keys()}
			for glyph in self.font.glyphs:
				colorFlowData = glyph.layers[masterId].userData["com.hugojourdan.ColorFlow"].copy()

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
			yPos = 36


			#---------------------------------------------------------------------------#
			# Update data for sorting in CF Smart Filter								#
			#---------------------------------------------------------------------------#
			try:
				for layer in self.font.selectedLayers:
					for k, v in layer.userData["com.hugojourdan.ColorFlow"].items():
						if v is True:
							layer.userData["com.hugojourdan.ColorFlow_Color_" + str(k)] = str(k)
						else:
							del layer.userData["com.hugojourdan.ColorFlow_Color_" + str(k)]
			except:
				pass

			#---------------------------------------------------------------------------#
			# Access, build data to update UI											#
			#---------------------------------------------------------------------------#
			selectedMasterId = self.font.selectedFontMaster.id
			self.LayerColorLabel = self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterId]

			for color in self.LayerColorLabel:
				self.barWidthDic[color] = self.barWidth / len(self.font.glyphs) * self.LayerColorLabel[color]

			#---------------------------------------------------------------------------#
			# Updated element in UI														#
			#---------------------------------------------------------------------------#

			# Update Master Name
			if hasattr(self.paletteView.frame, "masterName"):
				delattr(self.paletteView.frame, "masterName")

			masterName = self.font.selectedFontMaster.name
			if len(masterName) > 16:
				masterName = masterName[0:16] + "…"
			setattr(self.paletteView.frame, "masterName", TextBox((6, 2.6, 140, 20), masterName, alignment="left", sizeStyle='small'))


			for color, meaning in self.meaning.items():

				if hasattr(self.paletteView.frame, str(color)):
					delattr(self.paletteView.frame, str(color))
				if hasattr(self.paletteView.frame, str(color) + "box"):
					delattr(self.paletteView.frame, str(color) + "box")
				if hasattr(self.paletteView.frame, str(color) + "count"):
					delattr(self.paletteView.frame, str(color) + "count")

				if meaning:

					if self.font.selectedLayers:
						check = self.font.selectedLayers[0].userData["com.hugojourdan.ColorFlow"][color]

						if len(self.font.selectedLayers) > 1:
							for layer in self.font.selectedLayers:
								check = layer.userData["com.hugojourdan.ColorFlow"][color]
								if not check:
									break

						# Draw Gray Bar if ◻️, Colored Bar if ✅
						if not check and color is not None and self.barWidthDic[color] != 0:
							setattr(self.paletteView.frame, str(color) + "box", Box((self.xPos, yPos + 1 - self.shift, self.barWidthDic[color] + 0.01, 16), fillColor=(NSColor.colorWithRed_green_blue_alpha_(0, 0, 0, 0.06)), cornerRadius=0, borderWidth=0))

						if check and not color and self.barWidthDic[color] != 0 and self.font.selectedLayers[0].color != int(color):
							setattr(self.paletteView.frame, str(color) + "box", Box((self.xPos, yPos + 1 - self.shift, self.barWidthDic[color] + 0.01, 16), fillColor=(NSColor.colorWithRed_green_blue_alpha_(0, 0, 0, 0.06)), cornerRadius=0, borderWidth=0))

						if check and not color and self.barWidthDic[color] != 0 and self.font.selectedLayers[0].color == int(color):
							setattr(self.paletteView.frame, str(color) + "box", Box((self.xPos, yPos + 1 - self.shift, self.barWidthDic[color] + 0.01, 16), fillColor=(NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(color)])), cornerRadius=0, borderWidth=0))

						## Draw checkboxes
						#if len(meaning) > 16:
							#meaning = meaning[0:16]+"…"
						setattr(self.paletteView.frame, str(color), CheckBox((12, yPos - self.shift, -10, 20), meaning, value=check, callback=self.CheckBox_Callback, sizeStyle='small'))

						# Replace Counter by ✅ if goal reached
						if self.LayerColorLabel[color] >= len(self.font.glyphs):
							setattr(self.paletteView.frame, str(color) + "count", TextBox((self.width - 50, yPos + 5 - self.shift, -6, 20), "✅", alignment="right", sizeStyle='mini'))
						else:
							setattr(self.paletteView.frame, str(color) + "count", TextBox((self.width - 50, yPos + 3 - self.shift, -6, 20), f"{self.LayerColorLabel[color]}/{len(self.font.glyphs)}", alignment="right", sizeStyle='small'))

						yPos += 22

					else:
						if self.barWidthDic[color] != 0:
							setattr(self.paletteView.frame, str(color) + "box", Box((self.xPos, yPos + 1 - self.shift, self.barWidthDic[color] + 0.01, 16), fillColor=(NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(color)])), cornerRadius=0, borderWidth=0))

						setattr(self.paletteView.frame, str(color), CheckBox((12, yPos - self.shift, -10, 20), meaning, value=False, callback=self.CheckBox_Callback, sizeStyle='small'))

						# Replace Counter by ✅ if goal reached
						if self.LayerColorLabel[color] >= len(self.font.glyphs):
							setattr(self.paletteView.frame, str(color) + "count", TextBox((self.width - 50, yPos + 5 - self.shift, -6, 20), "✅", alignment="right", sizeStyle='mini'))
						else:
							setattr(self.paletteView.frame, str(color) + "count", TextBox((self.width - 50, yPos + 3 - self.shift, -6, 20), f"{self.LayerColorLabel[color]}/{len(self.font.glyphs)}", alignment="right", sizeStyle='small'))

						yPos += 22
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
			if self.Glyphs.font:
				self.Update_Plugin_UI()
				self.init = True
				trigger = True
		except:
			pass

		#-------------------------------------------------------------------------------#
		# Add ColorFlow data in layers if missing, allow to initialize a .glyphs file	#
		#-------------------------------------------------------------------------------#
		try:
			masterId = self.font.selectedFontMaster.id
			for glyph in self.font.glyphs:
				if glyph.layers[masterId].userData["com.hugojourdan.ColorFlow"] is None:
					glyph.layers[masterId].userData["com.hugojourdan.ColorFlow"] = {}
					for color in self.meaning.keys():
						glyph.layers[masterId].userData["com.hugojourdan.ColorFlow"][str(color)] = False

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
		# If glyph is generated, create default Color Flow data						#
		#---------------------------------------------------------------------------#
		try:
			for layer in self.font.selectedLayers:
				if not layer.userData["com.hugojourdan.ColorFlow"]:
					layer.userData["com.hugojourdan.ColorFlow"] = {color: False for color in self.meaning.keys()}
		except:
			pass

		#---------------------------------------------------------------------------#
		# If master added, create default Color Flow data							#
		#---------------------------------------------------------------------------#
		try:
			for master in self.font.masters:
				if master.id not in self.font.userData["com.hugojourdan.ColorFlow-master-data"]:
					for glyph in self.font.glyphs:
						if not glyph.layers[master.id].userData["com.hugojourdan.ColorFlow"]:
							glyph.layers[master.id].userData["com.hugojourdan.ColorFlow"] = {color: False for color in self.meaning.keys()}
					self.font.userData["com.hugojourdan.ColorFlow-master-data"][master.id] = self.Get_Dic_Layer_Color_Label(master.id)
					self.Update_Plugin_UI()
		except:
			pass

		if not self.init:
			try:
				self.Update_Plugin_UI()
				self.init = True
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
							if self.font.userData["com.hugojourdan.ColorFlow-selectedLayer-data"] != self.font.selectedLayers[0].userData["com.hugojourdan.ColorFlow"]:
								self.font.userData["com.hugojourdan.ColorFlow-selectedLayer-data"] = self.font.selectedLayers[0].userData["com.hugojourdan.ColorFlow"].copy()
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
		selectedMasterID = self.font.selectedFontMaster.id
		firstMeaning = list(self.meaning.keys())[0]

		for master in self.font.masters:
			if master.id not in self.font.userData["com.hugojourdan.ColorFlow-master-data"]:

				for glyph in self.font.glyphs:
					if not glyph.layers[master.id].userData["com.hugojourdan.ColorFlow"]:
						glyph.layers[master.id].userData["com.hugojourdan.ColorFlow"] = {color: False for color in self.meaning.keys()}
				self.font.userData["com.hugojourdan.ColorFlow-master-data"][master.id] = self.Get_Dic_Layer_Color_Label(master.id)

		for k, v in self.meaning.items():
			if color == v:
				color = k


		for layer in self.font.selectedLayers:
			if check and not layer.userData["com.hugojourdan.ColorFlow"][color]:
				self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterID][color] += 1
				layer.userData["com.hugojourdan.ColorFlow"][color] = True
			if not check and layer.userData["com.hugojourdan.ColorFlow"][color]:
				self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterID][color] -= 1
				layer.userData["com.hugojourdan.ColorFlow"][color] = False


			# Update LayerColor
			for COLOR in self.meaning.keys():

				if not layer.userData["com.hugojourdan.ColorFlow"][firstMeaning]:
					layer.color = None

				if layer.userData["com.hugojourdan.ColorFlow"][COLOR]:
					layer.color = int(COLOR)

				else:
					break


	#####################################################################################################
	#																									#
	#	EXTRA FEATURES																					#
	#																									#
	#####################################################################################################
	#																									#
	#																									#


	@objc.python_method
	def Setup_Color_Flow(self, sender):
		"""Setup ColorFlow based on Color Layers callback"""

		print(f"✅ UPDATE > ColorFlow settings [{self.font.selectedFontMaster.name}]")

		selectedMasterId = self.font.selectedFontMaster.id
		self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterId] = {x: 0 for x in self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterId]}

		# selectedLayers = self.font.selectedLayers

		for glyph in self.font.glyphs:
			for layer in glyph.layers:
				if layer.isMasterLayer and layer.layerId == selectedMasterId:
					if not layer.color:
						layer.userData["com.hugojourdan.ColorFlow"] = {x: False for x in layer.userData["com.hugojourdan.ColorFlow"]}
						for k, v in self.meaning.items():
							if int(k) != layer.color:
								layer.userData["com.hugojourdan.ColorFlow"][k] = True
								self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterId][k] += 1
							else:
								layer.userData["com.hugojourdan.ColorFlow"][k] = True
								self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterId][k] += 1
								break
					else:
						layer.userData["com.hugojourdan.ColorFlow"] = {x: False for x in layer.userData["com.hugojourdan.ColorFlow"]}

		Glyphs.showMacroWindow()
		self.Update_Plugin_UI()


	@objc.python_method
	def Color_Flow_Reset(self, sender):
		"""Reset ColorFlow callback"""

		print(f"✅ RESET > ColorFlow settings [{self.font.selectedFontMaster.name}]")

		for glyph in self.font.glyphs:
			for layer in glyph.layers:
				if layer.isMasterLayer and layer.layerId == self.font.selectedFontMaster.id:

					for k in layer.userData.keys():
						if k != "com.hugojourdan.ColorFlow":
							del layer.userData[k]

					layer.userData["com.hugojourdan.ColorFlow"] = {x: False for x in layer.userData["com.hugojourdan.ColorFlow"]}
					layer.color = None
				else:
					pass

		selectedMasterId = self.font.selectedFontMaster.id
		# for master in self.font.masters:
		# 	self.font.userData["com.hugojourdan.ColorFlow-master-data"][master.name] = {x: 0 for x in self.font.userData["com.hugojourdan.ColorFlow-master-data"][master.name]}
		self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterId] = {x: 0 for x in self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterId]}

		Glyphs.showMacroWindow()
		self.Update_Plugin_UI()


	@objc.python_method
	def Generate_Color_Flow_Smart_Filter(self, sender):
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


	@objc.python_method
	def Copy_Color_Flow_To_Master(self, sender):
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
			glyph.layers[toMasterID].userData["com.hugojourdan.ColorFlow"] = glyph.layers[fromMasterID].userData["com.hugojourdan.ColorFlow"]

	@objc.python_method
	def Open_Color_Flow_Documentation(self, sender):

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

	@objc.python_method
	def Activate_Color_Flow_Report(self, sender):

		if Glyphs.defaults["com.hugojourdan.ColorFlow-Report"] == "Enable Color Flow Report":
			self.report = True
			Glyphs.addCallback(self.Color_Flow_Report_PRINT, DOCUMENTCLOSED)
			Glyphs.defaults["com.hugojourdan.ColorFlow-Report"] = "Disable Color Flow Report"
			print("Color Flow Report enabled.\nWhen you will close your document, a .txt file will be generated in 'Color Flow Reports' folder located next to your Glyphs file")

			Glyphs.showMacroWindow()

			if hasattr(self.paletteView.frame, "actionPopUpButton"):
				delattr(self.paletteView.frame, "actionPopUpButton")
			self.paletteView.frame.actionPopUpButton = ActionButton(
				(self.width - 22, 0, 34, 19),
				[
					dict(title="Setup Color Flow based on Color Layers", callback=self.Setup_Color_Flow),
					dict(title="Reset Color Flow", callback=self.Color_Flow_Reset),
					dict(title="Generate Color Flow Smart Filters", callback=self.Generate_Color_Flow_Smart_Filter),
					dict(title="Copy Color Flow to Master", callback=self.Copy_Color_Flow_To_Master),
					dict(title=Glyphs.defaults["com.hugojourdan.ColorFlow-Report"], callback=self.Activate_Color_Flow_Report),
					"----",
					dict(title="Open Color Flow Documentation", callback=self.Open_Color_Flow_Documentation),
				],
				sizeStyle='small'
			)

		else:
			self.report = False
			Glyphs.removeCallback(self.Color_Flow_Report_PRINT, DOCUMENTCLOSED)
			Glyphs.defaults["com.hugojourdan.ColorFlow-Report"] = "Enable Color Flow Report"
			print("Color Flow Report disabled")
			Glyphs.showMacroWindow()

			if hasattr(self.paletteView.frame, "actionPopUpButton"):
				delattr(self.paletteView.frame, "actionPopUpButton")
			self.paletteView.frame.actionPopUpButton = ActionButton(
				(self.width - 22, 0, 34, 19),
				[
					dict(title="Setup Color Flow based on Color Layers", callback=self.Setup_Color_Flow),
					dict(title="Reset Color Flow", callback=self.Color_Flow_Reset),
					dict(title="Generate Color Flow Smart Filters", callback=self.Generate_Color_Flow_Smart_Filter),
					dict(title="Copy Color Flow to Master", callback=self.Copy_Color_Flow_To_Master),
					dict(title=Glyphs.defaults["com.hugojourdan.ColorFlow-Report"], callback=self.Activate_Color_Flow_Report),
					"----",
					dict(title="Open Color Flow Documentation", callback=self.Open_Color_Flow_Documentation),
				],
				sizeStyle='small'
			)


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
