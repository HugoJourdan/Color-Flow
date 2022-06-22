# encoding: utf-8
from __future__ import division, print_function, unicode_literals

###########################################################################################################
#
#	Font Dashboard Palette Plugin
#
#	Read the docs:
#	https://github.com/HugoJourdan/FontDashboard
#
###########################################################################################################

from vanilla import *
from vanilla import dialogs
import re
import os
import codecs
import AppKit
from datetime import datetime

from GlyphsApp.plugins import *
from GlyphsApp.UI import *
from GlyphsApp import *
from AppKit import NSColor


class ColorWorkflow(PalettePlugin):

	@objc.python_method
	def settings(self):
		self.name = 'ColorFlow'
		self.font = Glyphs.currentDocument.font
		self.export = [glyph.name for glyph in self.font.glyphs if glyph.export]	
		
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

		self.meaning = self.mapKeys(self.getKeyFile())
		self.init = 0
		self.width = 160
		self.rectHeight = 10
		self.lineSpacing = 20
		self.shift = 10
		self.barWidth = self.width+6
		self.barWidthDic = {}
		self.height = 22 * len([x for x in self.meaning.values() if x]) + 25
		self.xPos = 9

		self.paletteView = Window((self.width, self.height + 10))
		self.paletteView.frame = Group((0, 0, self.width, self.height))

		# Draw Action Button
		self.paletteView.frame.actionPopUpButton = ActionButton((self.width-22, 0, 34, 19), 
			[
			dict(title="Setup Color Flow based on Color Layers", callback=self.resetColorWorkflow),
			dict(title="Reset Color Flow", callback=self.hardreset),
			dict(title="Generate Color Flow Smart Filters", callback=self.generateColorFlow_SmartFilter),
			],
			sizeStyle='small')

		# Draw Master Name
		self.paletteView.frame.masterNameBox = Box((6, 4, 127, 10), fillColor=(AppKit.NSColor.colorWithRed_green_blue_alpha_(0, 0,0,0.1)), cornerRadius=4, borderWidth=0)

		# Draw Horitzontal Lines
		lineY = 25
		for k, v in self.meaning.items():
			setattr(self.paletteView.frame, str(k)+"line", HorizontalLine((0, lineY, 0, 1)))
			lineY += 22

		# Draw Color Tags
		y = 36
		for k, v in self.meaning.items():
			if v:
				setattr(self.paletteView.frame, str(k)+"colorTag", Box((0, y+1-self.shift, 3, 16), fillColor=(AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(k)])), cornerRadius=0, borderWidth=0))
				y += 22

		# Select a master if none is selected
		if not self.font.selectedFontMaster:
			self.font.selectedFontMaster = self.font.masters[0]

		# Add ColorFlow data in layers if missing, allow to initialize a .glyphs file
		for glyph in self.font.glyphs:
			for layer in glyph.layers:
				if layer.isMasterLayer and layer.userData["com.hugojourdan.ColorFlow"] == None :
					layer.userData["com.hugojourdan.ColorFlow"] = {}
					for color in self.meaning.keys():
						layer.userData["com.hugojourdan.ColorFlow"][str(color)] = False

		# Create fon.userData to update the plugin
		self.font.userData["com.hugojourdan.ColorFlow-export"] = None
		self.font.userData["com.hugojourdan.ColorFlow-selectedLayer"] = None
		self.font.userData["com.hugojourdan.ColorFlow-selectedLayer-data"] = None

		# Store data per Master
		self.font.userData["com.hugojourdan.ColorFlow-master-data"] = {}
		for master in self.font.masters:
			masterId = master.id
			self.font.userData["com.hugojourdan.ColorFlow-master-data"][master.name] = self.GetDicLayerColorLabel(masterId)
			
		# Needed to display the palette plugin
		self.dialog = self.paletteView.frame.getNSView()

	@objc.python_method
	def start(self):
		# Adding a callback for the 'GSUpdateInterface' event
		Glyphs.addCallback(self.update, UPDATEINTERFACE)


	# Build Dic with number of LayerColor
	@objc.python_method
	def GetDicLayerColorLabel(self ,masterId):
			
			self.LayerColorLabel = {k:False for k in self.meaning.keys()}
			for glyph in self.font.glyphs:
				colorFlowData = glyph.layers[masterId].userData["com.hugojourdan.ColorFlow"].copy()

				# colorFlowData = ["0":0, "1":0, "2":1, ..."]
				for k, v in colorFlowData.items():
					self.LayerColorLabel[k] += int(v)

			return self.LayerColorLabel

	@objc.python_method
	def updateView(self):

		if self.font.selectedLayers:
			for layer in self.font.selectedLayers:
				for k, v in layer.userData["com.hugojourdan.ColorFlow"].items():
					if v == True:
						layer.userData["com.hugojourdan.ColorFlow_Color_"+str(k)] = str(k)

		selectedMasterName = self.font.selectedFontMaster.name
		self.LayerColorLabel = self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterName]

		for color in self.LayerColorLabel:
			self.barWidthDic[color]= self.barWidth/len(self.font.glyphs)*self.LayerColorLabel[color]

		# Update Master Name
		if hasattr(self.paletteView.frame, "masterName"):
				delattr(self.paletteView.frame, "masterName")

		masterName = self.font.selectedFontMaster.name
		if len(masterName) > 16:
			masterName = masterName[0:16]+"…"
		setattr(self.paletteView.frame, "masterName", TextBox((6, 2.6, 140, 20), masterName, alignment="left", sizeStyle='small'))


		for k in self.meaning.keys():
			if hasattr(self.paletteView.frame, str(k)):
				delattr(self.paletteView.frame, str(k))
			if hasattr(self.paletteView.frame, str(k)+"box"):
				delattr(self.paletteView.frame, str(k)+"box")
			if hasattr(self.paletteView.frame, str(k)+"count"):
				delattr(self.paletteView.frame, str(k)+"count")
		
		y = 36
		for k, meaning in self.meaning.items():
			if meaning:
				
				try:
					self.selectedLayer = self.font.selectedLayers[0]
					check = self.selectedLayer.userData["com.hugojourdan.ColorFlow"][k]

					if len(self.font.selectedLayers) > 1:
						for layer in self.font.selectedLayers:
							check = layer.userData["com.hugojourdan.ColorFlow"][k]
							if check == False:
								break

					# Draw Gray Bar if ◻️, Colored Bar if ✅
					if check == False and k != None and self.barWidthDic[k] != 0:
						setattr(self.paletteView.frame, str(k)+"box", Box((self.xPos, y+1-self.shift, self.barWidthDic[k]+0.01, 16), fillColor=(AppKit.NSColor.colorWithRed_green_blue_alpha_(0,0,0,0.06)), cornerRadius=0, borderWidth=0))
					
					if check == True and k != None and self.barWidthDic[k] != 0 and self.font.selectedLayers[0].color != int(k):
						setattr(self.paletteView.frame, str(k)+"box", Box((self.xPos, y+1-self.shift, self.barWidthDic[k]+0.01, 16), fillColor=(AppKit.NSColor.colorWithRed_green_blue_alpha_(0,0,0,0.06)), cornerRadius=0, borderWidth=0))

					if check == True and k != None and self.barWidthDic[k] != 0 and self.font.selectedLayers[0].color == int(k) :
						setattr(self.paletteView.frame, str(k)+"box", Box((self.xPos, y+1-self.shift, self.barWidthDic[k]+0.01, 16), fillColor=(AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(k)])), cornerRadius=0, borderWidth=0))

					# Draw checkboxes
					#if len(meaning) > 16:
					#meaning = meaning[0:16]+"…"
					setattr(self.paletteView.frame, str(k), CheckBox((12, y-self.shift, -10, 20), meaning, value=check, callback=self.checkBoxCallback, sizeStyle='small'))
					
					# Replace Counter by ✅ if goal reached
					if self.LayerColorLabel[k] >= len(self.font.glyphs):
						setattr(self.paletteView.frame, str(k)+"count", TextBox((self.width-50, y+5-self.shift, -6, 20), "✅", alignment="right", sizeStyle='mini'))
					else:
						setattr(self.paletteView.frame, str(k)+"count", TextBox((self.width-50, y+3-self.shift, -6, 20), f"{self.LayerColorLabel[k]}/{len(self.font.glyphs)}", alignment="right", sizeStyle='small'))
					
					y += 22
				except:pass
		
	@objc.python_method
	def update(self, sender):
		# do not update in case the palette is collapsed
		if self.dialog.frame().origin.y == 0:
			trigger = False 

			# Need to start [NEED TO BE FIXED]
			if self.init != 3:
				self.updateView()
				self.init += 1

			# If number of exported Glyph change, update UI
			# self.export = [glyph.name for glyph in self.font.glyphs if glyph.export]
			# if self.font.userData["com.hugojourdan.ColorFlow-export"] != self.export:
			# 	self.font.userData["com.hugojourdan.ColorFlow-export"] = self.export
			# 	self.updateView()

			# If master added, add key
			for master in self.font.masters:
				if master.name not in self.font.userData["com.hugojourdan.ColorFlow-master-data"]:

					for glyph in self.font.glyphs:
						if not glyph.layers[master.id].userData["com.hugojourdan.ColorFlow"]: 
							glyph.layers[master.id].userData["com.hugojourdan.ColorFlow"] = {color:False for color in self.meaning.keys()}
					self.font.userData["com.hugojourdan.ColorFlow-master-data"][master.name] = self.GetDicLayerColorLabel(master.id)


			# If no data, create default data
			try:
				if not self.font.selectedLayers[0].userData["com.hugojourdan.ColorFlow"]: 
					print("data missing, so created")
					self.font.selectedLayers[0].userData["com.hugojourdan.ColorFlow"] = {color:False for color in self.meaning.keys()}
			except Exception as e: print(e)
			
			# If selectedMaster is changed, update UI
			try:
				if self.font.userData["com.hugojourdan.ColorFlow-selectedMaster"] != self.font.selectedFontMaster:
					self.font.userData["com.hugojourdan.ColorFlow-selectedMaster"] = self.font.selectedFontMaster
					self.updateView()
					trigger = True
			except Exception as e: print(e)

			#If ColorFlow data changed, trigger update
			try:
				if trigger == False:
					for selectedLayer in self.font.selectedLayers:
						if self.font.userData["com.hugojourdan.ColorFlow-selectedLayer-data"] != self.font.selectedLayers[0].userData["com.hugojourdan.ColorFlow"]:
							self.font.userData["com.hugojourdan.ColorFlow-selectedLayer-data"] = self.font.selectedLayers[0].userData["com.hugojourdan.ColorFlow"].copy()
							self.updateView()
							trigger = True
			except Exception as e: print(e)
		
	@objc.python_method
	def checkBoxCallback(self, sender):

		for master in self.font.masters:
			if master.name not in self.font.userData["com.hugojourdan.ColorFlow-master-data"]:

				for glyph in self.font.glyphs:
					if not glyph.layers[master.id].userData["com.hugojourdan.ColorFlow"]: 
						glyph.layers[master.id].userData["com.hugojourdan.ColorFlow"] = {color:False for color in self.meaning.keys()}
				self.font.userData["com.hugojourdan.ColorFlow-master-data"][master.name] = self.GetDicLayerColorLabel(master.id)

		
		selectedLayer = self.font.selectedLayers
		color = sender.getTitle()
		check = sender.get()

		for k, v in self.meaning.items():
			if color == v:
				color = k

		selectedMasterName = self.font.selectedFontMaster.name
		for layer in selectedLayer:
			if check == True and layer.userData["com.hugojourdan.ColorFlow"][color] == False:
				self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterName][color]+= 1
			if check == False and layer.userData["com.hugojourdan.ColorFlow"][color] == True:
			 	self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterName][color]-= 1

			# Change ColorFlow Layer Data
			layer.userData["com.hugojourdan.ColorFlow"][color]=check
			
			# Update LayerColor
			for COLOR in self.meaning.keys():
				
				if layer.userData["com.hugojourdan.ColorFlow"]["0"] == False:
					layer.color = None
					
				if layer.userData["com.hugojourdan.ColorFlow"][COLOR] == True:
					layer.color = int(COLOR)
				
				else:
					break
		
		self.updateView()
		#self.update(self)			
		
	# Setup ColorFlow based on Color Layers callback
	@objc.python_method
	def resetColorWorkflow(self, sender):

		print(f"✅ UPDATE > ColorFlow settings [{self.font.selectedFontMaster.name}]")

		selectedMasterName = self.font.selectedFontMaster.name
		self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterName] = {x:0 for x in self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterName]}

		selectedLayers = self.font.selectedLayers

		for glyph in self.font.glyphs:
			for layer in glyph.layers:
				if layer.isMasterLayer and layer.layerId == self.font.selectedFontMaster.id:
					if layer.color != None:	
						layer.userData["com.hugojourdan.ColorFlow"] = {x: False for x in layer.userData["com.hugojourdan.ColorFlow"]}
						for k, v in self.meaning.items():
							if int(k) != layer.color:
								layer.userData["com.hugojourdan.ColorFlow"][k]=True
								self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterName][k]+= 1
							else:
								layer.userData["com.hugojourdan.ColorFlow"][k]=True
								self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterName][k]+= 1
								break
					else:
						layer.userData["com.hugojourdan.ColorFlow"] = {x: False for x in layer.userData["com.hugojourdan.ColorFlow"]}


		self.updateView()
	
	# Reset ColorFlow callback
	@objc.python_method
	def hardreset(self,sender):
		print(f"✅ RESET > ColorFlow settings [{self.font.selectedFontMaster.name}]")

		
		for glyph in self.font.glyphs:
			for layer in glyph.layers:
				if layer.isMasterLayer and layer.layerId == self.font.selectedFontMaster.id:
					layer.userData["com.hugojourdan.ColorFlow"] = {x: False for x in layer.userData["com.hugojourdan.ColorFlow"]}
					layer.color = None
				else:
					pass


		for master in self.font.masters:
			self.font.userData["com.hugojourdan.ColorFlow-master-data"][master.name] = {x:0 for x in self.font.userData["com.hugojourdan.ColorFlow-master-data"][master.name]}

		self.updateView()

	# Generate Color Flow smart filter
	@objc.python_method
	def generateColorFlow_SmartFilter(self,sender):
		import plistlib
			
							
		with open("/Users/hugojourdan/Library/Application Support/Glyphs 3/CustomFilter.plist", 'rb') as fp:
			pl = plistlib.load(fp)
			
			trigger = True
			for item in pl:
				if item["name"]=="Color Flow":
					trigger = False
			
			layerColor = []
			for i in range (0,12):
				I = str(i)
				layerColor.append({'name': self.meaning[str(i)], 'predicate': f"'{I}' IN layer.userData"})
				
			pl.append({"name":"Color Flow", "subGroup": layerColor})
			

		if trigger == True:
			with open("~/Library/Application Support/Glyphs 3/CustomFilter.plist", 'wb') as fp:
				plistlib.dump(pl, fp)
			Message("Color Flow Smart Filters have been generated.\nRestart Glyph to see them", title='Alert', OKButton=None)
		else:

			if dialogs.askYesNo("Color Flow", "Color Flow filter already exist, do you want to overwrite them ?") == True:
				with open("/Users/hugojourdan/Library/Application Support/Glyphs 3/CustomFilter.plist", 'wb') as fp:
					pl.remove({"name":"Color Flow", "subGroup": layerColor})
					plistlib.dump(pl, fp)
				Message("Color Flow Smart Filters have been generated.\nRestart Glyph to update Filter UI", title='Alert', OKButton=None)

	# Find and read color.txt, if missing, create it
	@objc.python_method
	def getKeyFile(self):
		keyFile = None
		try:
			thisDirPath = os.path.dirname(self.font.filepath)
			localKeyFile = thisDirPath + '/color.txt'
			if os.path.exists(localKeyFile):
				keyFile = localKeyFile
		except:
			pass

		dirInfo = os.path.expanduser("~/Library/Application Support/Glyphs 3/info")
		if not os.path.exists(dirInfo):
			os.mkdir(dirInfo)

		if keyFile is None:
			keyFile = os.path.expanduser('~/Library/Application Support/Glyphs 3/info/color.txt')

		if not os.path.exists(keyFile):
			f = open(keyFile,"w+")
			f.write("red=Red\norange=Orange\nbrown=Brown\nyellow=Yellow\nlightGreen=Light green\ndarkGreen=Dark green\nlightBlue=Light blue\ndarkBlue=Dark blue\npurple=Purple\nmagenta=Magenta\nlightGray=Light Gray\ncharcoal=Charcoal") 
		else:
			pass
		return keyFile

	# Build Dic from color.txt content
	@objc.python_method
	def mapKeys(self, keyFile):

		self.colourLabels = {}
		if os.path.exists(keyFile):
			with codecs.open(keyFile, "r", "utf-8") as file:
				for line in file:
					colour = re.match(r".*?(?=\=)", line).group(0)
					label = re.search(r"(?<=\=).*", line).group(0)
					self.colourLabels[colour] = label
		switch = {}
		replace = {"red":"0", "orange":"1", "brown":"2", "yellow":"3", "lightGreen":"4", "darkGreen":"5", "lightBlue":"6", "darkBlue":"7", "purple":"8", "magenta":"9", "lightGray":"10", "charcoal":"11"}

		for k, v in self.colourLabels.items():
			switch[replace[k]] = v

		self.colourLabels = switch
		return self.colourLabels

	@objc.python_method
	def __del__(self):
		# Delete callbacks when Glyphs quits, otherwise it'll crash :( 
		Glyphs.removeCallback(self.update)

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__

