# encoding: utf-8

###########################################################################################################
#
#
#	Reporter Plugin
#
#	Read the docs:
#	https://github.com/schriftgestalt/GlyphsSDK/tree/master/Python%20Templates/Reporter
#
#
###########################################################################################################


from __future__ import division, print_function, unicode_literals
import objc
from GlyphsApp import *
from GlyphsApp.plugins import *
from vanilla import Window, TextBox

class ShowMasterDashboard(ReporterPlugin):

	@objc.python_method
	def settings(self):
		self.menuName = "Master FontDashboard"

		if not Glyphs.defaults["com.HugoJourdan.ShowMasterDashboard"]:
			Glyphs.defaults["com.HugoJourdan.ShowMasterDashboard"] = "fullwidth"
	
	@objc.python_method
	def DrawProgressBar(self):

			self.colorKeys = {
						"0":(0.85, 0.26, 0.06, 0.8),
						"1":(0.99, 0.62, 0.11, 0.8),
						"2":(0.65, 0.48, 0.20, 0.8),
						"3":(0.97, 0.90, 0.00, 0.8),
						"4":(0.67, 0.95, 0.38, 0.8),
						"5":(0.04, 0.57, 0.04, 0.8),
						"6":(0.06, 0.60, 0.98, 0.8),
						"7":(0.00, 0.20, 0.88, 0.8),
						"8":(0.50, 0.09, 0.79, 0.8),
						"9":(0.98, 0.36, 0.67, 0.8),
						"10":(0.75, 0.75, 0.75, 1),
						"11":(0.25, 0.25, 0.25, 0.8)
						}

			rectHeight = 6
	
			LayerColorLabel = {"0":0,"1":0,"2":0,"3":0,"4":0,"5":0,"6":0,"7":0,"8":0,"9":0,"10":0,"11":0,"None":0}
			masterId = self.font.selectedFontMaster.id

			for glyph in self.font.glyphs:
				color = glyph.layers[masterId].color
				LayerColorLabel[str(color)] += 1

			if Glyphs.defaults["com.HugoJourdan.ShowMasterDashboard"] == "fullwidth":
				rectHeight = 6
				wWidth = self.font.currentTab.viewPort.size.width
				xOffSet = self.font.currentTab.viewPort.origin.x
				y = self.font.currentTab.viewPort.origin.y + self.font.currentTab.viewPort.size.height-rectHeight

			if Glyphs.defaults["com.HugoJourdan.ShowMasterDashboard"] == "small":
				rectHeight = 10
				wWidth = 200
				xOffSet = self.font.currentTab.viewPort.origin.x+20
				y = self.font.currentTab.viewPort.origin.y + self.font.currentTab.viewPort.size.height-rectHeight-18

			
			percent = wWidth/100

			barWidth = {}
			for k, v in LayerColorLabel.items():
				barWidth[k]= wWidth/100*(LayerColorLabel[k]/len(self.font.glyphs)*100)

			
			

			for k, v in barWidth.items():
				if k != "None" and v != 0:
					rect = NSMakeRect(xOffSet,y, v, rectHeight)
					NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(k)]).set()
					path = NSBezierPath.bezierPathWithRect_(rect)
					path.fill()

					if Glyphs.defaults["com.HugoJourdan.ShowMasterDashboard"] == "small":
						NSColor.colorWithRed_green_blue_alpha_(0.6, 0.6, 0.6, 1).set()
						path.stroke()
					xOffSet += v


			#xOffSet = self.font.currentTab.viewPort.origin.x + 10
			#rect = NSMakeRect(xOffSet,y, wWidth, rectHeight)
			#NSColor.colorWithRed_green_blue_alpha_(0.6, 0.6, 0.6, 1).set()
			#path = NSBezierPath.bezierPathWithRect_(rect)
			#path.stroke()

		
	@objc.python_method
	def foregroundInViewCoords(self):

		self.font = Glyphs.font
		currentTab = self.font.currentTab

		y = self.font.currentTab.viewPort.origin.y + self.font.currentTab.viewPort.size.height -26
		xOffSet = self.font.currentTab.viewPort.origin.x + 10
		fontSize = 14

		#masterName = self.font.selectedFontMaster.name
		#pos = NSPoint(xOffSet, y)
		#self.drawTextAtPoint(masterName, pos, fontSize * currentTab.scale)
		
		self.DrawProgressBar()

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__
