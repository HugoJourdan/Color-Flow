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


import re
import os
import codecs
import AppKit

from vanilla import *
from AppKit import NSColor
from GlyphsApp.plugins import *
from GlyphsApp.UI import *
from GlyphsApp import *



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
		self.meaning = self.Map_Keys(self.Get_Key_File())
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
			dict(title="Setup Color Flow based on Color Layers", callback=self.Setup_Color_Flow),
			dict(title="Reset Color Flow", callback=self.Color_Flow_Reset),
			dict(title="Generate Color Flow Smart Filters", callback=self.Generate_Color_Flow_Smart_Filter),
			dict(title="Copy Color Flow to Master", callback=self.Copy_Color_Flow_To_Master),
			"----",
			dict(title="Open Color Flow Documentation", callback=self.Open_Color_Flow_Documentation),
			],
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
		self.font.userData["com.hugojourdan.ColorFlow-selectedLayer"] = False
		self.font.userData["com.hugojourdan.ColorFlow-selectedLayer-data"] = None


		# Store data per Master
		self.font.userData["com.hugojourdan.ColorFlow-master-data"] = {}
		for master in self.font.masters:
			masterId = master.id
			self.font.userData["com.hugojourdan.ColorFlow-master-data"][master.name] = self.Get_Dic_Layer_Color_Label(masterId)
			
		# Needed to display the palette plugin
		self.dialog = self.paletteView.frame.getNSView()


	@objc.python_method
	def start(self):
		Glyphs.addCallback(self.update, UPDATEINTERFACE)


	########################################################################################################
	#																									   #
	#	DATA + UI 																				           #
	#																									   #
	########################################################################################################
	#																									   #
	#																									   #

	# Build Dic with number of LayerColor
	@objc.python_method
	def Get_Dic_Layer_Color_Label(self ,masterId):
			
			self.LayerColorLabel = {k:False for k in self.meaning.keys()}
			for glyph in self.font.glyphs:
				colorFlowData = glyph.layers[masterId].userData["com.hugojourdan.ColorFlow"].copy()

				# colorFlowData = ["0":0, "1":0, "2":1, ..."]
				for k, v in colorFlowData.items():
					self.LayerColorLabel[k] += int(v)

			return self.LayerColorLabel


	# Update Palette UI
	@objc.python_method
	def Update_Plugin_UI(self):

		yPos = 36

		#---------------------------------------------------------------------------#
		# Update data for sorting in CF Smart Filter								#
		#---------------------------------------------------------------------------#
		try:
			for layer in self.font.selectedLayers:
				for k, v in layer.userData["com.hugojourdan.ColorFlow"].items():
					if v == True:
						layer.userData["com.hugojourdan.ColorFlow_Color_"+str(k)] = str(k)
					else:
						del layer.userData["com.hugojourdan.ColorFlow_Color_"+str(k)]
		except:pass

		#---------------------------------------------------------------------------#
		# Access, build data to update UI											#
		#---------------------------------------------------------------------------#
		selectedMasterName = self.font.selectedFontMaster.name
		self.LayerColorLabel = self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterName]

		for color in self.LayerColorLabel:
			self.barWidthDic[color]= self.barWidth/len(self.font.glyphs)*self.LayerColorLabel[color]

		#---------------------------------------------------------------------------#
		# Updated element in UI														#
		#---------------------------------------------------------------------------#
		
		# Update Master Name
		if hasattr(self.paletteView.frame, "masterName"):
				delattr(self.paletteView.frame, "masterName")

		masterName = self.font.selectedFontMaster.name
		if len(masterName) > 16:
			masterName = masterName[0:16]+"…"
		setattr(self.paletteView.frame, "masterName", TextBox((6, 2.6, 140, 20), masterName, alignment="left", sizeStyle='small'))
			

		for color, meaning in self.meaning.items():

			if hasattr(self.paletteView.frame, str(color)):
				delattr(self.paletteView.frame, str(color))
			if hasattr(self.paletteView.frame, str(color)+"box"):
				delattr(self.paletteView.frame, str(color)+"box")
			if hasattr(self.paletteView.frame, str(color)+"count"):
				delattr(self.paletteView.frame, str(color)+"count")

			if meaning:
				
				if self.font.selectedLayers:
					check = self.font.selectedLayers[0].userData["com.hugojourdan.ColorFlow"][color]

					if len(self.font.selectedLayers) > 1:
						for layer in self.font.selectedLayers:
							check = layer.userData["com.hugojourdan.ColorFlow"][color]
							if check == False:
								break 

					# Draw Gray Bar if ◻️, Colored Bar if ✅
					if check == False and color != None and self.barWidthDic[color] != 0:
						setattr(self.paletteView.frame, str(color)+"box", Box((self.xPos, yPos+1-self.shift, self.barWidthDic[color]+0.01, 16), fillColor=(AppKit.NSColor.colorWithRed_green_blue_alpha_(0,0,0,0.06)), cornerRadius=0, borderWidth=0))
					
					if check == True and color != None and self.barWidthDic[color] != 0 and self.font.selectedLayers[0].color != int(color):
						setattr(self.paletteView.frame, str(color)+"box", Box((self.xPos, yPos+1-self.shift, self.barWidthDic[color]+0.01, 16), fillColor=(AppKit.NSColor.colorWithRed_green_blue_alpha_(0,0,0,0.06)), cornerRadius=0, borderWidth=0))

					if check == True and color != None and self.barWidthDic[color] != 0 and self.font.selectedLayers[0].color == int(color) :
						setattr(self.paletteView.frame, str(color)+"box", Box((self.xPos, yPos+1-self.shift, self.barWidthDic[color]+0.01, 16), fillColor=(AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(color)])), cornerRadius=0, borderWidth=0))

					## Draw checkboxes
					#if len(meaning) > 16:
						#meaning = meaning[0:16]+"…"
					setattr(self.paletteView.frame, str(color), CheckBox((12, yPos-self.shift, -10, 20), meaning, value=check, callback=self.CheckBox_Callback, sizeStyle='small'))
					
					# Replace Counter by ✅ if goal reached
					if self.LayerColorLabel[color] >= len(self.font.glyphs):
						setattr(self.paletteView.frame, str(color)+"count", TextBox((self.width-50, yPos+5-self.shift, -6, 20), "✅", alignment="right", sizeStyle='mini'))
					else:
						setattr(self.paletteView.frame, str(color)+"count", TextBox((self.width-50, yPos+3-self.shift, -6, 20), f"{self.LayerColorLabel[color]}/{len(self.font.glyphs)}", alignment="right", sizeStyle='small'))
					
					yPos += 22

				else:
					if self.barWidthDic[color] != 0:
						setattr(self.paletteView.frame, str(color)+"box", Box((self.xPos, yPos+1-self.shift, self.barWidthDic[color]+0.01, 16), fillColor=(AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(color)])), cornerRadius=0, borderWidth=0))

					setattr(self.paletteView.frame, str(color), CheckBox((12, yPos-self.shift, -10, 20), meaning, value=False, callback=self.CheckBox_Callback, sizeStyle='small'))
					
					# Replace Counter by ✅ if goal reached
					if self.LayerColorLabel[color] >= len(self.font.glyphs):
						setattr(self.paletteView.frame, str(color)+"count", TextBox((self.width-50, yPos+5-self.shift, -6, 20), "✅", alignment="right", sizeStyle='mini'))
					else:
						setattr(self.paletteView.frame, str(color)+"count", TextBox((self.width-50, yPos+3-self.shift, -6, 20), f"{self.LayerColorLabel[color]}/{len(self.font.glyphs)}", alignment="right", sizeStyle='small'))
					
					yPos += 22


	# Detect if UI need to be update
	@objc.python_method
	def update(self, sender):

		#---------------------------------------------------------------------------#
		# If Palette plugin is open, try update 									#
		#---------------------------------------------------------------------------#
		if self.dialog.frame().origin.y == 0:
			trigger = False 

			#---------------------------------------------------------------------------#
			# Run UI update at start to not show empty plugin 						   	#
			#---------------------------------------------------------------------------#
			try:
				if self.init == False :
					self.font.userData["com.hugojourdan.ColorFlow-selectedLayer"] = False
					self.Update_Plugin_UI()
					trigger = True
			except:pass

			#---------------------------------------------------------------------------#
			# If glyph is generated, create default Color Flow data						#
			#---------------------------------------------------------------------------#
			try:
				for layer in self.font.selectedLayers:
					if not layer.userData["com.hugojourdan.ColorFlow"]: 
						layer.userData["com.hugojourdan.ColorFlow"] = {color:False for color in self.meaning.keys()}
			except:pass

			#---------------------------------------------------------------------------#
			# If master added, create default Color Flow data  						   	#
			#---------------------------------------------------------------------------#
			if trigger == False:		
				self.font.userData["com.hugojourdan.ColorFlow-selectedLayer"] = True
				for master in self.font.masters:
					if master.name not in self.font.userData["com.hugojourdan.ColorFlow-master-data"]:
						for glyph in self.font.glyphs:
							if not glyph.layers[master.id].userData["com.hugojourdan.ColorFlow"]: 
								glyph.layers[master.id].userData["com.hugojourdan.ColorFlow"] = {color:False for color in self.meaning.keys()}
						self.font.userData["com.hugojourdan.ColorFlow-master-data"][master.name] = self.Get_Dic_Layer_Color_Label(master.id)

			#---------------------------------------------------------------------------#
			# If no layer selected, trigger UI update							    	#
			#---------------------------------------------------------------------------#
			try:
				if trigger == False and self.font.selectedLayers == None:
					self.font.userData["com.hugojourdan.ColorFlow-selectedLayer"] = False
					self.Update_Plugin_UI()
					trigger = True
			except:pass

			#---------------------------------------------------------------------------#
			# If layer selected, trigger UI update      						    	#
			#---------------------------------------------------------------------------#
			try:
				if trigger == False and self.font.userData["com.hugojourdan.ColorFlow-selectedLayer"] == False:
					self.Update_Plugin_UI()
					self.font.userData["com.hugojourdan.ColorFlow-selectedLayer"] = True
					trigger = True
			except:pass

			#---------------------------------------------------------------------------#
			# If selected master changed, trigger UI update   						   	#
			#---------------------------------------------------------------------------#
			try:
				if self.font.userData["com.hugojourdan.ColorFlow-selectedMaster"] != self.font.selectedFontMaster:
					self.font.userData["com.hugojourdan.ColorFlow-selectedMaster"] = self.font.selectedFontMaster
					self.Update_Plugin_UI()
					trigger = True
			except:pass

			#---------------------------------------------------------------------------#
			# If Color Flow Data changed, trigger UI update  						   	#
			#---------------------------------------------------------------------------#
			try:
				if trigger == False:
					if self.font.userData["com.hugojourdan.ColorFlow-selectedLayer-data"] != self.font.selectedLayers[0].userData["com.hugojourdan.ColorFlow"]:
						self.font.userData["com.hugojourdan.ColorFlow-selectedLayer-data"] = self.font.selectedLayers[0].userData["com.hugojourdan.ColorFlow"].copy()
						self.Update_Plugin_UI()
						trigger = True
			except:pass


	# Action when a checkbox is toogle
	@objc.python_method
	def CheckBox_Callback(self, sender):

		for master in self.font.masters:
			if master.name not in self.font.userData["com.hugojourdan.ColorFlow-master-data"]:

				for glyph in self.font.glyphs:
					if not glyph.layers[master.id].userData["com.hugojourdan.ColorFlow"]: 
						glyph.layers[master.id].userData["com.hugojourdan.ColorFlow"] = {color:False for color in self.meaning.keys()}
				self.font.userData["com.hugojourdan.ColorFlow-master-data"][master.name] = self.Get_Dic_Layer_Color_Label(master.id)
		
		color = sender.getTitle()
		check = sender.get()

		for k, v in self.meaning.items():
			if color == v:
				color = k
		selectedMasterName = self.font.selectedFontMaster.name

		for layer in self.font.selectedLayers:
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
		
			#self.update(self)			
		

	########################################################################################################
	#																									   #
	#	EXTRA FEATURES																					   #
	#																									   #
	########################################################################################################
	#																									   #
	#																									   #

	# Setup ColorFlow based on Color Layers callback
	@objc.python_method
	def Setup_Color_Flow(self, sender):

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

		Glyphs.showMacroWindow()
		self.Update_Plugin_UI()
	

	# Reset ColorFlow callback
	@objc.python_method
	def Color_Flow_Reset(self,sender):

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

		selectedMaster = self.font.selectedFontMaster.name
		#for master in self.font.masters:
			#self.font.userData["com.hugojourdan.ColorFlow-master-data"][master.name] = {x:0 for x in self.font.userData["com.hugojourdan.ColorFlow-master-data"][master.name]}
		self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMaster] = {x:0 for x in self.font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMaster]}

		Glyphs.showMacroWindow()
		self.Update_Plugin_UI()


	# Generate Color Flow smart filter
	@objc.python_method
	def Generate_Color_Flow_Smart_Filter(self,sender):

		import plistlib
			
		plistFile = os.path.expanduser("~/Library/Application Support/Glyphs 3/CustomFilter.plist")		

		try:	

			with open(plistFile, 'rb') as fp:

				pl = plistlib.load(fp)
				trigger = True
				layerColor = []
				notlayerColor = []

				for item in pl:
					if item["name"]=="Color Flow":
						trigger = False
				
				for i in range (0,12):
					layerColor.append({'name': self.meaning[str(i)], 'predicate': f"'{str(i)}' IN layer.userData"})
					notlayerColor.append({'name': self.meaning[str(i)], 'predicate': f"NOT '{str(i)}' IN layer.userData"})
					
				pl.append({'name': 'Color Flow', 'subGroup': [{'name': 'Has[...]', 'subGroup': layerColor}, {'name': 'Has not[...]', 'subGroup': notlayerColor}]})
				
			if trigger == True:
				with open(plistFile, 'wb') as fp:
					plistlib.dump(pl, fp)
				Message("Color Flow Smart Filters have been generated.\nRestart Glyph to see them", title='Alert', OKButton=None)
			else:

				if dialogs.askYesNo("Color Flow", "Color Flow filter already exist, do you want to overwrite them ?") == True:
					with open(plistFile, 'wb') as fp:
						pl.remove({'name': 'Color Flow', 'subGroup': [{'name': 'Has[...]', 'subGroup': layerColor}, {'name': 'Has not[...]', 'subGroup': notlayerColor}]})

						plistlib.dump(pl, fp)
					Message("Color Flow Smart Filters have been generated.\nRestart Glyph to update Filter UI", title='Alert', OKButton=None)
		except:
			Message("To Fix it, add an item in Filter Section and Restart Glyph. After that run again this function", title=".plist not writable", OKButton=None)
	

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
		self.font.userData["com.hugojourdan.ColorFlow-master-data"][toMaster] = self.font.userData["com.hugojourdan.ColorFlow-master-data"][fromMaster]
		
		fromMasterID, toMasterID = None, None
		for master in self.font.masters:
			if master.name == fromMaster:
				fromMasterID = master.id
			if master.name == toMaster:
				toMasterID = master.id
				
		for glyph in self.font.glyphs:
			glyph.layers[toMasterID].color = glyph.layers[fromMasterID].color
			glyph.layers[toMasterID].userData["com.hugojourdan.ColorFlow"] = glyph.layers[fromMasterID].userData["com.hugojourdan.ColorFlow"]

	@objc.python_method
	def Open_Color_Flow_Documentation( self, sender ):
		
		URL = "https://github.com/HugoJourdan/Color-Flow"
		
		import webbrowser
		webbrowser.open(URL)

	########################################################################################################
	#																									   #
	#	SETUP COLOR MEANING																			       #
	#																									   #
	########################################################################################################
	#																									   #
	#																									   #

	# Find and read color.txt, if missing, create it
	@objc.python_method
	def Get_Key_File(self):
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
	def Map_Keys(self, keyFile):

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


	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__

