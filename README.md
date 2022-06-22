
# Color Flow


**Color Flow** is a Palette Plugin, to organize your workflow and make it more visual.  
It allows to define for each layer work steps done, and update automaticaly Layer Color Label.

<img src="https://github.com/HugoJourdan/Color-Flow/blob/main/img/ColorFlow_thumbnail.jpg" width="900">

# Glyph Color vs Layer Color
GlyphsApp propose two different kind of Color Labels.

* `Glyph Color Label` , assigned to glyph with `Right-Click`
* `Layer Color Label` , assigned to layer with `Right-Click + Option`

| Glyph Color | Layer Color | Glyph+Layer Color |
| :---: | :---: | :---: |
| <img src="https://github.com/HugoJourdan/Color-Flow/blob/main/img/Glyph-Color-Label.png" width="100"> | <img src="https://github.com/HugoJourdan/Color-Flow/blob/main/img/Layer-Color-Label.png" width="100"> | <img src="https://github.com/HugoJourdan/Color-Flow/blob/main/img/Glyph+Layer-Color-Label.png" width="100"> |

A glyph can have only one `Glyph Color Label`, but many `Layer Color Label` (as many layers of the glyph). 


# Use of Layer Color
Convenient use of `Layer Color Label` is to set them to indicate progress status of a layer.  

For example:
* Yellow → Outline corrected
* Green → Anchors placed
* Blue → Spacing set



# How to customize color meanings

The plugin requires a **coolorWorkflow.txt** file stored in either ~/Library/Application Support/Glyphs 3/info/ or the same directory as the current Glyphs source file. Preference is given to the latter allowing for the sharing of the **fontdashboard.txt** file with glyphs source files to retain labelling information between project contributors. 

The **coolorWorkflow.txt** file requires the formatting `colorName=meaning`, with each key on a newline and with no space surrounding the '='. An example, with the defined colorNames is given below. 

```
red=Step 1
orange=Step 2
brown=Step 3
yellow=Step 4
lightGreen=Step 5
darkGreen=Step 6
lightBlue=Step7
darkBlue=Step 8
purple=Step 9
magenta=Step 10
lightGray=Step 11
charcoal=Step 12
```


Layers Color are set automaticaly set according to checkboxes. Layer Color set is precedent color of the first uncheck checkbox.  
In the following example Layer Color is set to`Orange` because even if `Light Green` and `Yellow` are ✅, `Brown` is uncheck, so color set is the color that precedes it.

<img src="https://github.com/HugoJourdan/Color-Flow/blob/main/img/howcolorsetup1.jpg" width="300"> <img src="https://github.com/HugoJourdan/Color-Flow/blob/main/img/howcolorsetup2.jpg" width="300"> 



You can customise color order by changing line order, and you can also hide a color by deleting the line associated with it.
Here is an example :

```
red=Step 1
yellow=Step 2
magenta=Step 3
purple=Step 4
lightGreen=Step 5
```

# Additionnal features
Some extra feature are accesible from the Action Button in the UI.

* `Setup Color Flow based on Color Layers` : Set for all layer, Color Flow data based on it Layer Color (Useful when you open for the first time a .glyph file with Layer Color already set)
* `Reset Color Flow` : Reset for all layers, Color Flow data and Layer Color.
* `Generate Color Flow Smart Filters` : Generate in the Filters UI section, a `Color Flow` folder containing two sub-folder. 
  *  `Has [...]` : filters to sort all layer with a specific step checked.
  *  `Has not [...]` : filters to sort all layer with a specific step not checked.
