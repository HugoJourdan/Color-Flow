#MenuTitle: Toggle Red Checkbox (Color Flow)
# -*- coding: utf-8 -*-
import os
import re
import codecs

font = Glyphs.font

# Find and read color.txt, if missing, create it
def getKeyFile():

	keyFile = None

	try:
		thisDirPath = os.path.dirname(font.filepath)
		localKeyFile = thisDirPath + '/color.txt'
		if os.path.exists(localKeyFile):
			keyFile = localKeyFile
	except:
		pass

	dirInfo = os.path.expanduser("~/Library/Application Support/Glyphs 3/info")

	if keyFile is None:
		keyFile = os.path.expanduser('~/Library/Application Support/Glyphs 3/info/color.txt')

	if not os.path.exists(keyFile):
		f = open(keyFile,"w+")
		f.write("red=Red\norange=Orange\nbrown=Brown\nyellow=Yellow\nlightGreen=Light green\ndarkGreen=Dark green\nlightBlue=Light blue\ndarkBlue=Dark blue\npurple=Purple\nmagenta=Magenta\nlightGray=Light Gray\ncharcoal=Charcoal") 
	else:
		pass
	return keyFile

# Build Dic from color.txt content
def mapKeys(keyFile):

	colourLabels = {}
	if os.path.exists(keyFile):
		with codecs.open(keyFile, "r", "utf-8") as file:
			for line in file:
				colour = re.match(r".*?(?=\=)", line).group(0)
				label = re.search(r"(?<=\=).*", line).group(0)
				colourLabels[colour] = label
	switch = {}
	replace = {"red":"0", "orange":"1", "brown":"2", "yellow":"3", "lightGreen":"4", "darkGreen":"5", "lightBlue":"6", "darkBlue":"7", "purple":"8", "magenta":"9", "lightGray":"10", "charcoal":"11"}

	for k, v in colourLabels.items():
		switch[replace[k]] = v

	colourLabels = switch
	return colourLabels

meaning = mapKeys(getKeyFile())
selectedMasterName = font.selectedFontMaster.name
selectedLayers = font.selectedLayers

colorCheck = "0"
for layer in selectedLayers:
	layer.color = layer.color

	layer.userData["com.hugojourdan.ColorFlow"][colorCheck] = not layer.userData["com.hugojourdan.ColorFlow"][colorCheck]

	if layer.userData["com.hugojourdan.ColorFlow"][colorCheck] == True:
		font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterName][colorCheck]+= 1
	else:
		font.userData["com.hugojourdan.ColorFlow-master-data"][selectedMasterName][colorCheck]-= 1

	for COLOR in meaning.keys():
				
		if layer.userData["com.hugojourdan.ColorFlow"][colorCheck] == False:
			layer.color = None
					
		if layer.userData["com.hugojourdan.ColorFlow"][COLOR] == True:
			layer.color = int(COLOR)
				
		else:
			break