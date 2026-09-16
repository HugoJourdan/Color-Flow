#MenuTitle: Toggle Yellow Checkbox (Color Flow)
# -*- coding: utf-8 -*-
import os
import sys

script_directory = os.path.dirname(__file__)
if script_directory not in sys.path:
	sys.path.insert(0, script_directory)

from color_flow_shortcut import toggle_color

toggle_color(Glyphs.font, "3")
