
# Color Flow


**Color Flow** is a Palette Plugin, to organize your workflow and track easier your project.  
This helps you not to forget anything when working on a font.

<img src="https://user-images.githubusercontent.com/76793951/174275455-665033a1-334e-492a-86ab-a85d5b1a4140.jpg" width="500">

GlyphsApp propose two different kind of Color Labels.

* `Glyph Color Label` , assigned to glyphs with Right-Click
* `Layer Color Label` , assigned to layers with Right-Click + Option


<img src="https://user-images.githubusercontent.com/76793951/174276486-13d2ae58-0ca4-464b-a9c6-a996c38059ac.png" width="400">

A glyph can have only one Glyph Color Label, but many Layer Color Labels (as many as the number of layers of the glyph). A useful use of layer color labels is to set them to indicate the state of a layer. For example, you could decide to use the ![Capture d’écran 2022-06-15 à 20.43.33|32x32, 50%](upload://ePMsUmXa7nwz0qOEOCqHk5jrha4.jpeg) Red layer color for layers that need outline corrected.



This Plugin is a alternative way to use Layer Color Labels. Instead of setting Layer Color Labels with ⌥ + Right-Click,

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

# How to customize color meanings

You can customise color order by changing line order, and you can also hide a color by deleting the line associated with it.
Here is an example :

```
red=Step 1
yellow=Step 2
magenta=Step 3
purple=Step 4
lightGreen=Step 5
```
