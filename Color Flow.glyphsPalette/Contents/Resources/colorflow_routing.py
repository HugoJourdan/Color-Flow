"""Pure decision logic for Color Flow's "swap Option color routing" feature.

In stock Glyphs 3, clicking a colour swatch sets the GLYPH's colour label; holding
Option sets the active LAYER's colour instead. Color Flow can invert that: with the
swap toggle on, a plain click routes to the layer and Option-click routes to the
glyph. The actual swizzle of ``-[GSFontViewController setColorIndex:]`` lives in
plugin.py; this module holds only the two small decisions it makes, so they are
100% headless-unit-testable.

No AppKit / GlyphsApp imports — the NSEvent mouse-type raw values are hard-coded
from the documented ``NSEventType`` enum so this stays importable anywhere.
"""

from __future__ import annotations

from typing import Literal

# NSEventType raw integer values for the mouse interactions a real swatch click
# produces (down + up: left, right, other). Hard-coded so this module never has
# to import AppKit. Source: AppKit/NSEvent.h NSEventType.
_LEFT_MOUSE_DOWN = 1
_LEFT_MOUSE_UP = 2
_RIGHT_MOUSE_DOWN = 3
_RIGHT_MOUSE_UP = 4
_OTHER_MOUSE_DOWN = 25
_OTHER_MOUSE_UP = 26

MOUSE_EVENT_TYPES: frozenset[int] = frozenset(
	{
		_LEFT_MOUSE_DOWN,
		_LEFT_MOUSE_UP,
		_RIGHT_MOUSE_DOWN,
		_RIGHT_MOUSE_UP,
		_OTHER_MOUSE_DOWN,
		_OTHER_MOUSE_UP,
	}
)


def should_apply_swap(
	event_type: int | None, mouse_types: frozenset[int] = MOUSE_EVENT_TYPES
) -> bool:
	"""True only when the current event is a real mouse interaction.

	A non-mouse event type (e.g. a key event from a colour shortcut) or ``None``
	(no current event — a programmatic call) returns False, so the caller can fall
	back to stock glyph routing instead of misrouting a non-click.
	"""
	if event_type is None:
		return False
	return event_type in mouse_types


def resolve_color_target(option_pressed: bool, swap_enabled: bool) -> Literal["glyph", "layer"]:
	"""Decide whether the colour goes on the glyph or the active layer.

	Stock behaviour: Option-click -> layer, plain click -> glyph. With swap on, the
	two are inverted. Both reduce to XOR of the two booleans::

	    option | swap  | target
	    -------+-------+-------
	    False  | False | glyph
	    True   | False | layer
	    False  | True  | layer
	    True   | True  | glyph
	"""
	return "layer" if (option_pressed ^ swap_enabled) else "glyph"
