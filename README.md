# ABOUT

**Color Flow** is a Palette Plugin to help organize and gamify your workflow by tracking progress through visual feedback. It works by assigning meaning to Layer Color Labels which are sorted into a series of customizable catogories and made directly accessable through the sidebar. Checkboxes and color-coded progress bars help to easily identify and update which step you are on in a workflow. 


<img src="https://github.com/HugoJourdan/Color-Flow/blob/main/img/ColorFlow_thumbnail.jpg?raw=true" width="900">

<br>

_________________
# GLYPH COLOR 🆚 LAYER COLOR

In Glyphs App, color labels can be defined on two levels, Glyph and Layer, and applied in one of twelve predefined colors.

Set Glyph Color is accessed by control-click or right-click on a glyph. 

Set Layer Color is accessed by right-click on a glyph and holding the Option key.

Glyph Color spans across the entire glyph cell. Layer Color is drawn on the right half of the cell if a Glyph Color is set, or across the entire cell with a cut-out in the top left if no glyph
color is set.

| Glyph Color | Layer Color | Glyph+Layer Color |
| :---: | :---: | :---: |
| <img src="https://github.com/HugoJourdan/Color-Flow/blob/main/img/Glyph-Color-Label.png" width="100"> | <img src="https://github.com/HugoJourdan/Color-Flow/blob/main/img/Layer-Color-Label.png" width="100"> | <img src="https://github.com/HugoJourdan/Color-Flow/blob/main/img/Glyph+Layer-Color-Label.png" width="100"> |
 
Convenient use of `Layer Color Label` is to indicate progress status of a layer, as the following example.

* 🟣 → Outline corrected
* 🟢 → Anchors placed
* 🔵 → Spacing set
* 🟡 → Ready to Export
<br>

_________________
# REQUIREMENTS

Color Flow requires a `color.txt` file stored in either `~/Library/Application Support/Glyphs 3/info` or the same directory as the current Glyphs source file. Preference is given to the latter allowing for the sharing of the `color.txt` file with glyphs source files to retain labelling information between project collaborators. 

The `color.txt` file requires the formatting `colorName=meaning`, with each key on a newline and with no space surrounding the '='.  
An example, with the defined colorNames is given below. 

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

<br>

_________________
# CUSTOMIZE

The whole point of Color Flow is that meaning and order of colors can be customized, so that each designer can build their own workflow.  
Color order can be modified by changing line order and color can be hidden by removing it's meaning. An example, with a customize `color.txt` is given below. 

```
red=
orange=
brown=
purple=Outline corrected
lightGreen=Anchors placed
darkGreen=
lightBlue=Spacing set
darkBlue=
yellow=Ready to Export
magenta=
lightGray=
charcoal=
```

Display in Color Flow UI:
* 🟣 → Outline corrected
* 🟢 → Anchors placed
* 🔵 → Spacing set
* 🟡 → Ready to Export


<br>

_________________
# HOW IT WORK

Each layer has is own Color Flow data, shown in the panel.  
Layers Color Labels are set automaticaly depending on the status and order of each category checkbox.  
The Color set is the precedent color of the first uncheck checkbox. 

In the following example Layer Color is set to `Orange` because even if `Light Green` and `Yellow` are ✅ , `Brown` is uncheck, so the color set is the color that precedes it.

<img src="https://github.com/HugoJourdan/Color-Flow/blob/main/img/howcolorsetup1.jpg" width="300"> <img src="https://github.com/HugoJourdan/Color-Flow/blob/main/img/howcolorsetup2.jpg" width="300"> 

Shortcuts can be used to toggle checkboxes. To assign shortcuts, follow these steps:

1. Download "Color Flow Shortcut" from Window > Plugin Manager.
2. Reload script folder by pressing [ Option + MAJ + Command + Y ].
3. In Glyph Preferences > Shortcuts, search "Color Flow" and assign a shortcut for each item. (I personnaly use Control+Number as shortcuts)


_________________
# EXTRA FEATURES

Some extra features are accessible from the Action Button.

* **Setup Color Flow based on Color Layers** : Set for all layer, Color Flow data based on its Layer Color (useful when you open for the first time a .glyph file with Layer Color already set)
* **Reset Color Flow** : Reset for all layers, Color Flow data and Layer Color.
* **Generate Color Flow Smart Filters** : Generate in the Filters UI section, a "Color Flow" folder containing filters to sort which layer has or has not a specific step checked.

<br>

*Thanks to Gor Jihanian (@gorjious) for his contribution.*

