# -*- coding: utf-8 -*-
"""Shared implementation for the Color Flow shortcut scripts."""

LAYER_DATA_KEY = "com.hugojourdan.ColorFlow"


def _layer_data(layer):
	"""Read a layer's Color Flow data and discard unchecked values."""
	stored_data = layer.userData[LAYER_DATA_KEY]
	if not stored_data:
		return {}
	return {
		str(color): True
		for color, value in stored_data.items()
		if value
	}


def _store_layer_data(layer, color_flow_data):
	"""Persist enabled values only, removing the key when none remain."""
	color_flow_data = {
		str(color): True
		for color, value in color_flow_data.items()
		if value
	}
	if color_flow_data:
		layer.userData[LAYER_DATA_KEY] = color_flow_data
	elif layer.userData[LAYER_DATA_KEY] is not None:
		del layer.userData[LAYER_DATA_KEY]


def toggle_color(font, color):
	"""Toggle one Color Flow value on every selected layer."""
	color = str(color)
	for layer in font.selectedLayers:
		color_flow_data = _layer_data(layer)
		if color_flow_data.get(color, False):
			color_flow_data.pop(color)
		else:
			color_flow_data[color] = True
		_store_layer_data(layer, color_flow_data)
