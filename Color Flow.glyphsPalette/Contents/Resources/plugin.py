# pyright: reportUndefinedVariable=false
# `from vanilla import *` / `from GlyphsApp import *` pull in runtime-only names
# that Glyphs injects; pyright can't see them, so the undefined-name rule is off
# for this file (ruff likewise ignores F403/F405 here via pyproject).


#######################################################
#													  #
#	Color Flow Palette plugins						  #
#													  #
#	Read the docs: 									  #
#	https://github.com/HugoJourdan/Color-Flow         #
#													  #
#######################################################


from __future__ import annotations

import os
import webbrowser
from datetime import datetime
from typing import Any

import AppKit
import colorflow_filters
import colorflow_profile
import colorflow_recipes

# Shared, GlyphsApp-free colorNames logic (also embedded into the shortcut
# scripts by tools/generate_shortcuts.py). Glyphs puts this bundle's Resources/
# dir on sys.path, so a plain absolute import works.
import colornames

# Shared "jump to next unfinished" navigation (also embedded into the jump
# shortcut by tools/generate_shortcuts.py).
import colornav

# Font-View colour grouping engine (the merged Rainbow FontView half).
import fontview
import labelcolors
import objc
from AppKit import (
	NSClickGestureRecognizer,
	NSCursor,
	NSGestureRecognizerStateBegan,
	NSGestureRecognizerStateChanged,
	NSGestureRecognizerStateEnded,
	NSMenuItem,
	NSOffState,
	NSOnState,
	NSPanGestureRecognizer,
)
from Foundation import NSDate, NSObject, NSRunLoop, NSRunLoopCommonModes

# Star imports are runtime-only Glyphs globals. Order is significant: vanilla
# first so its widgets lose any name collision to the GlyphsApp UI helpers, and
# GlyphsApp last so its names win. Import sorting is disabled for this file
# (I001 in pyproject) to keep that precedence — do not reorder.
from vanilla import *
from GlyphsApp.plugins import *
from GlyphsApp.UI import *
from GlyphsApp import *


_PUMP_STATE = {"last": 0.0}
_PUMP_INTERVAL = 1.0 / 60.0
_MAX_EVENTS_PER_PUMP = 20


def _pump_runloop() -> None:
	"""Drain queued events + run the run loop once so the report loader bar
	repaints while the synchronous build holds the main thread. Throttled to
	~60 Hz, bounded event count, fully fail-safe. Mirrors the Argus audit pump:
	without explicit pumping the OS shows the beachball within ~2 s of unbroken
	main-thread work and the determinate bar would freeze instead of tracking
	real progress."""
	import time
	now = time.monotonic()
	if now - _PUMP_STATE["last"] < _PUMP_INTERVAL:
		return
	_PUMP_STATE["last"] = now
	try:
		app = AppKit.NSApplication.sharedApplication()
		for _ in range(_MAX_EVENTS_PER_PUMP):
			event = app.nextEventMatchingMask_untilDate_inMode_dequeue_(
				AppKit.NSEventMaskAny, NSDate.distantPast(), "kCFRunLoopDefaultMode", True)
			if event is None:
				break
			app.sendEvent_(event)
		NSRunLoop.currentRunLoop().runUntilDate_(NSDate.distantPast())
	except Exception:
		pass


class _ColorFlowLoaderBar(AppKit.NSView):
	# A self-contained "rainbow fill" loading bar for the report-generation sheet:
	# the workflow colours fill a rounded track 0->100% with a live percentage.
	# Progress is REAL: the build calls set_progress() at each phase (and every few
	# glyphs of the heavy outline pass) while _pump_runloop() keeps this view
	# repainting through the otherwise-blocking main-thread build, so the bar tracks
	# actual work instead of racing ahead on a timer. The 30 Hz NSTimer (added to the
	# common run-loop modes) eases the displayed value toward the latest milestone so
	# motion stays smooth between callbacks.
	_SPECTRUM = (0, 1, 3, 4, 5, 6, 8, 9)   # red->green->blue->purple->pink (skip browns/greys)

	@objc.python_method
	def configure(self, rgba_colors: list) -> None:
		raw = [rgba_colors[i] for i in self._SPECTRUM if i < len(rgba_colors)]
		if not raw:
			raw = list(rgba_colors)
		self._colors = [self._saturate(rgba, 1.6) for rgba in raw]   # vivid, punchy hues
		self._value = 0.0    # displayed fraction (eased toward _target)
		self._target = 0.0   # latest real-progress milestone (monotonic, never decreases)
		self._fillImage = None   # cached blurred gradient fill (rebuilt on size change)
		self._fillKey = None
		self.start()

	@objc.python_method
	def _saturate(self, rgba: tuple, factor: float) -> tuple:
		import colorsys
		hue, sat, val = colorsys.rgb_to_hsv(rgba[0], rgba[1], rgba[2])
		red, green, blue = colorsys.hsv_to_rgb(hue, min(1.0, sat * factor), val)
		return (red, green, blue, rgba[3] if len(rgba) > 3 else 1.0)

	@objc.python_method
	def _blurred_fill(self, gradient: Any, width: float, bar_h: float, radius: float) -> Any:
		# Render the full-width gradient offscreen and Gaussian-blur it so the colours
		# read soft/dreamy like the favicon. Returns an NSImage sized to the bar, or
		# None when Core Image is unavailable (caller falls back to the crisp gradient).
		try:
			import Quartz
			source = AppKit.NSImage.alloc().initWithSize_(AppKit.NSMakeSize(width, bar_h))
			source.lockFocus()
			gradient.drawInRect_angle_(AppKit.NSMakeRect(0.0, 0.0, width, bar_h), 0.0)
			source.unlockFocus()
			image = Quartz.CIImage.alloc().initWithData_(source.TIFFRepresentation())
			blur = Quartz.CIFilter.filterWithName_("CIGaussianBlur")
			if image is None or blur is None:
				return None
			blur.setValue_forKey_(image, "inputImage")
			blur.setValue_forKey_(radius, "inputRadius")
			output = blur.valueForKey_("outputImage")
			if output is None:
				return None
			# Push saturation back up — the blur averages neighbouring hues and dulls them,
			# so re-boost so the bar reads vivid/colourful even while soft.
			controls = Quartz.CIFilter.filterWithName_("CIColorControls")
			if controls is not None:
				controls.setValue_forKey_(output, "inputImage")
				controls.setValue_forKey_(1.5, "inputSaturation")
				boosted = controls.valueForKey_("outputImage")
				if boosted is not None:
					output = boosted
			output = output.imageByCroppingToRect_(image.extent())   # blur expands extent; crop back
			rep = AppKit.NSCIImageRep.alloc().initWithCIImage_(output)
			if rep is None:
				return None
			result = AppKit.NSImage.alloc().initWithSize_(AppKit.NSMakeSize(width, bar_h))
			result.addRepresentation_(rep)
			return result
		except Exception:
			return None

	@objc.python_method
	def start(self) -> None:
		self.stop()
		self._timer = AppKit.NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
			1.0 / 30.0, self, "tick:", None, True)
		NSRunLoop.currentRunLoop().addTimer_forMode_(self._timer, NSRunLoopCommonModes)

	@objc.python_method
	def stop(self) -> None:
		timer = getattr(self, "_timer", None)
		if timer is not None:
			try:
				timer.invalidate()
			except Exception:
				pass
		self._timer = None

	def tick_(self, timer: Any) -> None:
		self.setNeedsDisplay_(True)

	def viewDidMoveToWindow(self) -> None:
		if self.window() is None:
			self.stop()

	@objc.python_method
	def set_progress(self, frac: float) -> None:
		# Real-progress milestone from the build. Monotonic: only ever advances so
		# the bar can't jump backward if a later phase reports a smaller fraction.
		frac = 0.0 if frac < 0.0 else (1.0 if frac > 1.0 else float(frac))
		if frac > getattr(self, "_target", 0.0):
			self._target = frac
		self.setNeedsDisplay_(True)

	@objc.python_method
	def _progress(self) -> float:
		# Ease the displayed value toward the latest milestone (~25% of the gap per
		# tick) so the bar glides between callbacks rather than stepping.
		target = getattr(self, "_target", 0.0)
		value = getattr(self, "_value", 0.0)
		value += (target - value) * 0.25
		if target - value < 0.002:
			value = target
		self._value = value
		return value

	def drawRect_(self, dirtyRect: Any) -> None:
		colors = getattr(self, "_colors", None) or []
		prog = self._progress()
		bounds = self.bounds()
		width = bounds.size.width
		height = bounds.size.height
		bar_h = 16.0 / 1.5   # thinner bar
		bar_y = height - bar_h
		radius = bar_h / 2.0
		bar_rect = AppKit.NSMakeRect(0.0, bar_y, width, bar_h)
		filled = prog * width
		# Build (and cache once per size) the soft, saturated, Gaussian-blurred rainbow
		# fill — both the glow and the bar itself draw from it.
		nscolors = [
			AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(rgba[0], rgba[1], rgba[2], 1.0)
			for rgba in colors
		]
		blend = AppKit.NSGradient.alloc().initWithColors_(nscolors) if len(nscolors) >= 2 else None
		key = (int(round(width)), int(round(bar_h)))
		if blend is not None and getattr(self, "_fillKey", None) != key:
			self._fillImage = self._blurred_fill(blend, width, bar_h, bar_h * 1.2)
			self._fillKey = key
		fill_image = getattr(self, "_fillImage", None)
		# Coloured glow: the blurred fill drawn a little larger + faint BEHIND the track,
		# CLIPPED to a rounded pill so it reads as a soft halo hugging the bar — not a
		# rectangular ghost peeking out behind the rounded track (the "second bar").
		if colors and prog > 0.0 and fill_image is not None:
			grow = bar_h * 0.4
			glow_rect = AppKit.NSMakeRect(-grow, bar_y - grow, filled + grow * 2.0, bar_h + grow * 2.0)
			src_rect = AppKit.NSMakeRect(0.0, 0.0, max(filled, 1.0), bar_h)
			glow_radius = (bar_h + grow * 2.0) / 2.0
			context = AppKit.NSGraphicsContext.currentContext()
			context.saveGraphicsState()
			AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
				glow_rect, glow_radius, glow_radius).addClip()
			fill_image.drawInRect_fromRect_operation_fraction_(
				glow_rect, src_rect, AppKit.NSCompositingOperationSourceOver, 0.5)
			context.restoreGraphicsState()
		track = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(bar_rect, radius, radius)
		AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(0.137, 0.149, 0.180, 1.0).set()
		track.fill()
		if colors and prog > 0.0:
			context = AppKit.NSGraphicsContext.currentContext()
			context.saveGraphicsState()
			track.addClip()
			# reveal the fill only up to the filled fraction (colours stay anchored)
			AppKit.NSBezierPath.bezierPathWithRect_(
				AppKit.NSMakeRect(0.0, bar_y, filled, bar_h)).addClip()
			if fill_image is not None:
				fill_image.drawInRect_fromRect_operation_fraction_(
					bar_rect, AppKit.NSZeroRect, AppKit.NSCompositingOperationSourceOver, 1.0)
			elif blend is not None:
				blend.drawInRect_angle_(bar_rect, 0.0)
			elif nscolors:
				nscolors[0].set()
				AppKit.NSRectFill(AppKit.NSMakeRect(0.0, bar_y, filled, bar_h))
			top = AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(1.0, 1.0, 1.0, 0.22)
			bottom = AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(0.0, 0.0, 0.0, 0.16)
			sheen = AppKit.NSGradient.alloc().initWithStartingColor_endingColor_(top, bottom)
			if sheen is not None:
				sheen.drawInRect_angle_(bar_rect, -90.0)
			context.restoreGraphicsState()
		paragraph = AppKit.NSMutableParagraphStyle.alloc().init()
		paragraph.setAlignment_(AppKit.NSTextAlignmentCenter)
		attributes = {
			AppKit.NSForegroundColorAttributeName: AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(0.60, 0.63, 0.67, 1.0),
			AppKit.NSFontAttributeName: AppKit.NSFont.systemFontOfSize_(11.0),
			AppKit.NSParagraphStyleAttributeName: paragraph,
		}
		label = AppKit.NSAttributedString.alloc().initWithString_attributes_(
			f"{int(round(prog * 100))}%", attributes)
		label.drawInRect_(AppKit.NSMakeRect(0.0, 0.0, width, bar_y - 2.0))


########################################################################################################
#																									   #
#	NATIVE SHORTCUTS (Glyphs > Settings > Shortcuts)												   #
#																									   #
########################################################################################################

# Display spellings match tools/generate_shortcuts.py (Green/Blue/Grey rather than
# lightGreen/lightBlue/lightGray) so the native command titles line up with the
# external shortcut-script names users already know.
_SHORTCUT_DISPLAY_NAMES = (
	(0, "Red"), (1, "Orange"), (2, "Brown"), (3, "Yellow"),
	(4, "Green"), (5, "DarkGreen"), (6, "Blue"), (7, "DarkBlue"),
	(8, "Purple"), (9, "Magenta"), (10, "Grey"), (11, "Charcoal"),
)
_SHORTCUT_GROUP = "Color Flow"
_SHORTCUT_ID_PREFIX = "com.hugojourdan.ColorFlow."
_SHORTCUT_COUNTS_KEY = "com.hugojourdan.ColorFlow-counts-"
# Opt-in "count exporting glyphs only" mode (default OFF): when set, glyphs
# marked non-exporting in Glyphs drop out of every completion percentage —
# palette counts/bars here, and the report's displayed percentages (the same
# pref is read by colorflow_dashboard.exporting_only()).
_EXPORTING_ONLY_KEY = "com.hugojourdan.ColorFlow-ExportingOnly"

# Strong module-level reference to the registered target. GSShortcutItem holds its
# target WEAK and Glyphs builds one palette instance per document window, so the
# commands target this retained singleton (registered once per session) instead of
# a per-window palette instance that may be deallocated when its window closes.
_SHORTCUT_HANDLER = None


def _shortcut_font_dir(font) -> str | None:
	return os.path.dirname(font.filepath) if font.filepath else None


def _toggle_step_for_selection(index: int) -> None:
	"""Toggle workflow step ``index`` on the selected layers.

	Mirrors the generated "Toggle <Color> CheckBox (Color Flow)" scripts
	(tools/generate_shortcuts.py, TOGGLE_TAIL) so the native shortcut and the
	external script can never disagree: free mode toggles the colour exclusively,
	step mode flips the checkbox within the contiguous run, and the palette's
	cached per-master counts are invalidated.
	"""
	font = Glyphs.font
	if font is None:
		return
	master = font.selectedFontMaster
	layers = font.selectedLayers
	if master is None or not layers:
		return
	meaning = colornames.load_meaning(_shortcut_font_dir(font))
	order = list(meaning.keys())
	key = str(index)
	if key not in meaning:
		return  # this color is hidden in the current colorNames.txt
	free = bool(Glyphs.defaults["com.hugojourdan.ColorFlow-FreeMode"])
	for layer in layers:
		if free:
			# single-select: toggle this colour exclusively (clear if re-pressed)
			layer.color = None if layer.color == index else index
		else:
			# contiguous steps: derive from layer.color, nothing saved in the file
			state = colornames.checked_state_for_color(layer.color, order)
			state[key] = not state.get(key, False)
			layer.color = colornames.layer_color_for_state(state, order)
	# Invalidate the palette's cached counts (volatile tempData) — both the plain
	# variant and the exporting-only one (see ColorFlow._counts_cache_key).
	font.tempData[_SHORTCUT_COUNTS_KEY + master.id] = None
	font.tempData[_SHORTCUT_COUNTS_KEY + master.id + "-exporting"] = None


def _jump_to_next_unfinished() -> None:
	"""Open the next glyph whose layer.color is not the final visible step.

	Mirrors the generated "Jump To Next Unfinished (Color Flow)" script
	(tools/generate_shortcuts.py, JUMP_TAIL) via the shared colornav module, so
	"next" and "unfinished" mean the same thing in both halves.
	"""
	font = Glyphs.font
	if font is None:
		Message("Open a font first.", title="Color Flow")
		return
	master = font.selectedFontMaster
	if master is None:
		return
	meaning = colornames.load_meaning(_shortcut_font_dir(font))
	final_step = colornames.final_visible_step(meaning)
	master_id = master.id
	pairs = []
	for glyph in font.glyphs:
		layer = glyph.layers[master_id]
		color = layer.color if layer is not None else None
		pairs.append((glyph.name, color))
	names = [name for name, _color in pairs]
	position = -1
	try:
		layers = font.selectedLayers
	except Exception:
		layers = None
	if layers:
		parent = layers[0].parent
		current = parent.name if parent is not None else None
		if current in names:
			position = names.index(current)
	index = colornav.next_unfinished_index(pairs, final_step, position)
	if index is None:
		Message("All glyphs finished.", title="Color Flow")
		return
	font.newTab("/" + names[index])


class ColorFlowShortcutHandler(NSObject):
	"""Long-lived target for the native shortcut commands (one per session)."""

	# GSShortcutCommandProtocol: Glyphs asks right before performing the action.
	# Typed selector because the protocol method returns an ObjC BOOL, which
	# PyObjC cannot infer for a Python-defined method.
	@objc.typedSelector(objc._C_NSBOOL + b"@:" + objc._C_SEL + objc._C_ID)
	def validateShortcutCommand_editViewController_(self, action, editViewController) -> bool:
		return True

	@objc.python_method
	def _toggle(self, index: int) -> None:
		try:
			_toggle_step_for_selection(index)
		except Exception:
			import traceback
			print("Color Flow [toggle shortcut] error:\n" + traceback.format_exc())

	def jumpNextShortcut_(self, sender) -> None:
		try:
			_jump_to_next_unfinished()
		except Exception:
			import traceback
			print("Color Flow [jump shortcut] error:\n" + traceback.format_exc())

	# One tiny selector per step so each command is individually remappable in
	# Glyphs > Settings > Shortcuts.
	def toggleStepShortcut0_(self, sender) -> None:
		self._toggle(0)

	def toggleStepShortcut1_(self, sender) -> None:
		self._toggle(1)

	def toggleStepShortcut2_(self, sender) -> None:
		self._toggle(2)

	def toggleStepShortcut3_(self, sender) -> None:
		self._toggle(3)

	def toggleStepShortcut4_(self, sender) -> None:
		self._toggle(4)

	def toggleStepShortcut5_(self, sender) -> None:
		self._toggle(5)

	def toggleStepShortcut6_(self, sender) -> None:
		self._toggle(6)

	def toggleStepShortcut7_(self, sender) -> None:
		self._toggle(7)

	def toggleStepShortcut8_(self, sender) -> None:
		self._toggle(8)

	def toggleStepShortcut9_(self, sender) -> None:
		self._toggle(9)

	def toggleStepShortcut10_(self, sender) -> None:
		self._toggle(10)

	def toggleStepShortcut11_(self, sender) -> None:
		self._toggle(11)


def _register_native_shortcuts() -> None:
	"""Register the 12 step toggles + jump in Glyphs > Settings > Shortcuts.

	Uses GSCallbackHandler +registerShortcutCommand:group:identifier:action:
	target:character:modifierFlags: (GlyphsCore.framework, GSCallbackHandler.h).
	Commands ship UNASSIGNED (character "") so users map their own keys natively
	— no Scripts-folder copying. Registers once per session: Glyphs builds one
	palette instance per document window, so later windows must not re-register.
	"""
	global _SHORTCUT_HANDLER
	if _SHORTCUT_HANDLER is not None:
		return
	callback_handler = objc.lookUpClass("GSCallbackHandler")
	register = callback_handler.registerShortcutCommand_group_identifier_action_target_character_modifierFlags_
	target = ColorFlowShortcutHandler.alloc().init()
	# Mark registered BEFORE the calls: a partial failure must not re-register
	# the earlier commands when the next window opens (it would only fail again).
	_SHORTCUT_HANDLER = target
	for index, display in _SHORTCUT_DISPLAY_NAMES:
		register(
			f"Toggle {display} Checkbox",
			_SHORTCUT_GROUP,
			f"{_SHORTCUT_ID_PREFIX}toggleStep{index}",
			f"toggleStepShortcut{index}:",
			target,
			"",  # unassigned — the user picks a key in Settings > Shortcuts
			0,
		)
	register(
		"Jump to Next Unfinished",
		_SHORTCUT_GROUP,
		_SHORTCUT_ID_PREFIX + "jumpNext",
		"jumpNextShortcut:",
		target,
		"",
		0,
	)


class ColorFlow(PalettePlugin):


	########################################################################################################
	#																									   #
	#	SETUP																					           #
	#																									   #
	########################################################################################################
	#																									   #
	#																									   #

	@objc.python_method
	def settings(self) -> None:
		self.name = 'Color Flow'
		self.init = False
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
		# Override the hardcoded defaults with the user's Glyphs label colours
		# (read live; the dict above is the fallback). Alpha stays at the palette's
		# 0.5 convention so only the hue follows the label colour.
		try:
			self.colorKeys = self._label_color_keys()
		except Exception:
			pass
		# A colorNames.txt problem must never crash plugin load — degrade to an
		# empty palette instead of taking the whole plugin down.
		try:
			self.meaning = self.Load_Meaning()
		except Exception as error:
			print(f"Color Flow: could not load colorNames.txt ({error}); starting empty.")
			self.meaning = {}
		self.width = 160
		self.rectHeight = 10
		self.lineSpacing = 20
		self.shift = 10
		self.barWidth = self.width+6
		self.height = 19 * len([x for x in self.meaning.values() if x]) + 4
		self.xPos = 0  # progress bar flush to the left edge (no margin)

		self.paletteView = Window((self.width, self.height + 10))
		self.paletteView.frame = Group((0, 0, self.width, self.height))

		# Eye toggle: enter an inline visibility-edit mode (show every colour; click
		# a row to stage show/hide; press again to apply + collapse to visible-only).
		self._eye_mode = False
		self._eye_rows = None
		self._eye_none = ""
		self._eyeRowViews = {}

		# Separator lines + colour tags (depend on the meaning order/visibility).
		# Per-row widgets (label / bar / count) are built by Update_Plugin_UI.
		self._rowChecks = {}
		self._rowOverlays = {}
		self._focusColor = None
		self._countBoxes = {}
		self._build_static_rows()

		# # Select a master if none is selected
		# if not self.font.selectedFontMaster:
		# 	self.font.selectedFontMaster = self.font.masters[0]

		# Needed to display the palette plugin
		self.dialog = self.paletteView.frame.getNSView()

		# Drive the palette height with an animatable height constraint so growing /
		# shrinking (e.g. entering/leaving eye mode) slides instead of snapping.
		# Glyphs pins the view's width + position; we own the height.
		try:
			self.dialog.setTranslatesAutoresizingMaskIntoConstraints_(False)
			self._heightConstraint = AppKit.NSLayoutConstraint.constraintWithItem_attribute_relatedBy_toItem_attribute_multiplier_constant_(
				self.dialog, AppKit.NSLayoutAttributeHeight, AppKit.NSLayoutRelationEqual, None, 0, 1.0, self.height)
			self.dialog.addConstraint_(self._heightConstraint)
		except Exception:
			self._heightConstraint = None

	# Separator lines + colour tags from the current meaning (order + visibility).
	# {"0".."11": (r, g, b, 0.5)} from the user's Glyphs label colours, keeping the
	# palette's 0.5 alpha so only the hue follows the label colour.
	@objc.python_method
	def _label_color_keys(self) -> dict:
		colors = labelcolors.read_label_colors()
		return {str(index): (rgba[0], rgba[1], rgba[2], 0.5) for index, rgba in enumerate(colors)}

	@objc.python_method
	def _build_static_rows(self) -> None:
		yPos = 2
		for k in self.meaning.keys():
			setattr(self.paletteView.frame, str(k)+"line", HorizontalLine((0, yPos, 0, 1)))
			yPos += 19
		yPos = 13
		for k, v in self.meaning.items():
			if v:
				setattr(self.paletteView.frame, str(k)+"colorTag", Box((0, yPos-self.shift-1, 6, 19), fillColor=(AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(k)])), cornerRadius=0, borderWidth=0))
				yPos += 19

	# Re-read colorNames.txt and rebuild the palette after a Settings-panel save.
	@objc.python_method
	def reload_after_settings(self) -> None:
		self.meaning = self.Load_Meaning()
		for i in range(12):
			for suffix in ("line", "colorTag", "", "box", "count", "hl", "focus", "click", "eye", "eyeTag", "eyeLine"):
				attr = str(i) + suffix
				if hasattr(self.paletteView.frame, attr):
					delattr(self.paletteView.frame, attr)
		self.height = 19 * len([x for x in self.meaning.values() if x]) + 4
		self._build_static_rows()
		try:
			self._set_palette_height(self.height, animated=True)
		except Exception:
			pass
		self._lastSignature = None
		self.Update_Plugin_UI()
		try:
			font = Glyphs.font
			if getattr(self, "fontview", None) is not None and font is not None and self.fontview.is_enabled(font):
				self.fontview.maybe_rebuild(font)
		except Exception:
			pass


	@objc.python_method
	def start(self) -> None:
		Glyphs.addCallback(self.update, UPDATEINTERFACE)
		try:
			Glyphs.addCallback(self.contextMenuHandler, CONTEXTMENUCALLBACK)
		except Exception:
			pass
		self.font = Glyphs.font
		self.init = False
		self.update(self._windowController)

		# First run: show the multi-slide tutorial sheet once the document window
		# exists. The method self-gates on a one-time flag, so this fires at most once
		# ever (across all windows). Replaces the old one-line welcome message.
		try:
			self.performSelector_withObject_afterDelay_("showTutorialIfFirstRun:", None, 1.0)
		except Exception:
			pass

		# Font-View colour grouping (the merged Rainbow FontView half). Opt-in and
		# fully wrapped so a problem here can never stop the palette from loading.
		self.fontview = fontview.FontViewGrouping()
		self._pendingFont = None
		self._strippedForSave = False
		try:
			self._install_rainbow_menu()
			self._install_settings_menu()
			self._install_backfill_menu()
			self._rainbow_conflict_check()
		except Exception:
			import traceback
			print("Color Flow [Rainbow setup] error:\n" + traceback.format_exc())

		# Native shortcut commands in Glyphs > Settings > Shortcuts (remappable,
		# no Scripts-folder copying). Guarded like the Rainbow setup: a missing
		# GSCallbackHandler symbol on an older Glyphs, or any registration
		# failure, only prints to the Macro panel and never breaks plugin load.
		try:
			_register_native_shortcuts()
		except Exception:
			import traceback
			print("Color Flow [shortcuts] error:\n" + traceback.format_exc())
		try:
			self.performSelector_withObject_afterDelay_("deferredHeaderSetup:", None, 2.0)
		except Exception:
			pass

		# Glyphs has NO will-save / pre-save hook. It posts exactly one save
		# notification — GSDocumentWasSavedSuccessfully — AFTER a successful save (the
		# value of GlyphsApp.DOCUMENTWASSAVED). The old code observed Cocoa names
		# (NSDocumentWillSave/DidSaveNotification) that Glyphs never posts, so the save
		# hooks never fired and the timeline was never recorded. Observe the real name.
		try:
			from Foundation import NSNotificationCenter
			center = NSNotificationCenter.defaultCenter()
			center.addObserver_selector_name_object_(
				self, "documentDidSave:", "GSDocumentWasSavedSuccessfully", None)
		except Exception:
			import traceback
			print("Color Flow [save-observer] error:\n" + traceback.format_exc())


	########################################################################################################
	#																									   #
	#	RAINBOW FONT VIEW																			       #
	#																									   #
	########################################################################################################

	@objc.python_method
	def _rainbow_menu_title(self) -> str:
		return "Color Flow: Font Glyph Order"

	# Action popover: a Default/Layer/Glyph segmented control + label/colour
	# for the Font Glyph Order grouping. Replaces the old ⋯ menu.
	@objc.python_method
	def Open_Action_Popover(self, sender) -> None:
		try:
			button = self._popover_anchor_view(sender)
			if button is None:
				# Nothing on screen can host the popover (no palette, no window) —
				# bail gracefully instead of letting NSPopover throw.
				print("Color Flow: no visible view to anchor the settings popover to.")
				return
			self._popover = Popover((220, 590), parentView=button,
				preferredEdge='left', behavior='semitransient')
			popover = self._popover
			popover.fgoLabel = TextBox((12, 12, -12, 16), "Font Glyph Order",
				sizeStyle='small')
			popover.rainbow = SegmentedButton((12, 32, -12, 22),
				[dict(title="Default"), dict(title="Layer"), dict(title="Glyph")],
				callback=self._popover_rainbow, sizeStyle='small')
			popover.rainbow.set(self._rainbow_segment_index())
			popover.lcSep = HorizontalLine((12, 62, -12, 1))
			self._labelColorsEdited = False
			popover.lcLabel = TextBox((12, 71, -84, 14), "Labels & Colours", sizeStyle='small')
			popover.lcImport = Button((-78, 68, 20, 20), "", callback=self._import_profile, sizeStyle='small')
			popover.lcExport = Button((-55, 68, 20, 20), "", callback=self._export_profile, sizeStyle='small')
			popover.lcReset = Button((-32, 68, 20, 20), "", callback=self._label_colors_reset, sizeStyle='small')
			# Borderless SF-Symbol icons via NSImage (NOT the symbol font as a title);
			# the literal glyph is only a fallback if the named image is unavailable.
			for _name, _sym, _fallback in (("lcImport", "square.and.arrow.down", "􀈄"),
					("lcExport", "square.and.arrow.up", "􀈂"),
					("lcReset", "arrow.counterclockwise", "􀎀")):
				try:
					_b = self._ns_button(getattr(popover, _name))
					_b.setBordered_(False)
					_img = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(_sym, None)
					if _img is not None:
						_b.setImage_(_img)
						_b.setImageScaling_(AppKit.NSImageScaleProportionallyDown)
					else:
						_b.setTitle_(_fallback)
						_b.setFont_(AppKit.NSFont.systemFontOfSize_(11.0))
				except Exception:
					pass
			self._labelWells = []
			self._labelFields = {}
			rgbaList = labelcolors.read_label_colors()
			try:
				# in-font labels (userData) win over the sidecar key file so a shared font
				# shows the labels its author saved.
				_keyText = colornames.read_color_names(colornames.get_key_file(self._font_dir(Glyphs.font)))
				settingsText = colornames.pick_settings_text(
					colornames.font_labels_text(Glyphs.font), _keyText)
			except Exception:
				settingsText = colornames.DEFAULT_COLOR_NAMES
			labelRows, _noneLabel = colornames.parse_settings(settingsText)
			labelByIndex = {index: label for index, label, _visible in labelRows}
			for index in range(12):
				rowY = 94 + index * 26
				wellColor = AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(*rgbaList[index])
				well = ColorWell((12, rowY, 26, 22), callback=self._label_color_changed, color=wellColor)
				setattr(popover, f"lcWell{index}", well)
				self._labelWells.append(well)
				field = EditText((44, rowY, -12, 22), labelByIndex.get(index, ""),
					callback=self._label_name_changed, continuous=False, sizeStyle='small')
				setattr(popover, f"lcField{index}", field)
				self._labelFields[index] = field
			reportY = 94 + 12 * 26 + 6
			popover.reportSep = HorizontalLine((12, reportY, -12, 1))
			popover.dashboard = Button((12, reportY + 8, -12, 22), "Generate Colorflow Report",
				callback=self._popover_dashboard, sizeStyle='small')
			legendY = reportY + 8 + 22 + 8
			popover.legend = Button((12, legendY, 20, 22), "?",
				callback=self._open_legend, sizeStyle='small')
			# Settings ported from the never-reachable settings_panel.py: the app-wide
			# free mode (independent steps) and storing the labels inside this .glyphs
			# file (userData) so they travel when the font is shared.
			settingsY = legendY + 22 + 8
			popover.settingsSep = HorizontalLine((12, settingsY, -12, 1))
			popover.freeMode = CheckBox((12, settingsY + 8, -12, 18),
				"Free mode (independent steps)", value=self._free_mode(),
				callback=self._popover_free_mode, sizeStyle='small')
			popover.storeInFont = CheckBox((12, settingsY + 30, -12, 18),
				"Store labels in this font",
				value=colornames.font_labels_text(Glyphs.font) is not None,
				callback=self._popover_store_in_font, sizeStyle='small')
			if Glyphs.font is None:
				popover.storeInFont.enable(False)
			# Opt-in: drop the glyphs marked non-exporting in Glyphs from every
			# completion percentage (palette counts/bars + the report's displayed
			# percentages). Honest default OFF — everything counts.
			popover.exportingOnly = CheckBox((12, settingsY + 52, -12, 18),
				"Count exporting glyphs only", value=self._exporting_only(),
				callback=self._popover_exporting_only, sizeStyle='small')
			# Workflow recipes (#5): a small editor for the per-category/per-script
			# step recipes — previously only settable as raw JSON in the Macro panel.
			popover.recipes = Button((12, settingsY + 76, -12, 22), "Workflow recipes…",
				callback=self._open_recipes_editor, sizeStyle='small')
			# The button has no background or border of its own; the animated GIF
			# (which bakes in its own button shape) provides the entire visual. The
			# native bezel is removed and an NSImageView the exact size of the button
			# sits just behind it, playing the GIF unclipped at its own aspect ratio.
			# The borderless button on top draws only the label (white, 100%, for
			# contrast on the bright gradient) and stays the click target.
			try:
				_gif = os.path.join(os.path.dirname(__file__), "report-loading.gif")
				_img = AppKit.NSImage.alloc().initWithContentsOfFile_(_gif)
				if _img is not None:
					_btn = self._ns_button(popover.dashboard)
					_btn.setBordered_(False)
					_titleAttrs = {AppKit.NSForegroundColorAttributeName: AppKit.NSColor.whiteColor()}
					if _btn.font() is not None:
						_titleAttrs[AppKit.NSFontAttributeName] = _btn.font()
					_btn.setAttributedTitle_(AppKit.NSAttributedString.alloc().initWithString_attributes_(
						_btn.title(), _titleAttrs))
					_f = _btn.frame()
					_iv = AppKit.NSImageView.alloc().initWithFrame_(_f)
					_iv.setImage_(_img)
					_iv.setAnimates_(True)
					_iv.setImageScaling_(AppKit.NSImageScaleProportionallyUpOrDown)
					_iv.setAutoresizingMask_(AppKit.NSViewWidthSizable)
					_btn.superview().addSubview_positioned_relativeTo_(_iv, AppKit.NSWindowBelow, _btn)
					self._reportGifView = _iv
			except Exception:
				import traceback
				print("Color Flow [report gif] error:\n" + traceback.format_exc())
			# Strip the blue AppKit focus ring (halo) from every control in the popover.
			try:
				self._strip_focus_rings(self._ns_button(popover.dashboard).superview())
			except Exception:
				pass
			try:
				popover.bind("did close", self._popover_did_close)
			except Exception:
				pass
			popover.open()
		except Exception:
			import traceback
			print("Color Flow [popover] error:\n" + traceback.format_exc())

	# Resolve the view the action popover anchors to. The Edit-menu item passes an
	# NSMenuItem (no view), and a collapsed palette section leaves self.dialog
	# hidden / without a window — anchoring NSPopover to either throws inside
	# AppKit. Try the sender's own view, then the palette view, then the key/main
	# window's content view; None when nothing on screen can host the popover
	# (the caller bails gracefully, no crash).
	@objc.python_method
	def _popover_anchor_view(self, sender) -> Any:
		candidates = []
		if sender is not None:
			if hasattr(sender, "_nsObject"):
				try:
					candidates.append(self._ns_button(sender))
				except Exception:
					pass
			elif hasattr(sender, "superview"):
				candidates.append(sender)
		candidates.append(getattr(self, "dialog", None))
		try:
			app = AppKit.NSApplication.sharedApplication()
			window = app.keyWindow() or app.mainWindow()
			if window is not None:
				candidates.append(window.contentView())
		except Exception:
			pass
		for view in candidates:
			try:
				if (view is not None and view.window() is not None
						and not view.isHiddenOrHasHiddenAncestor()):
					return view
			except Exception:
				continue
		return None

	# Current grouping state -> segment index (0 Default / 1 Layer / 2 Glyph).
	@objc.python_method
	def _rainbow_segment_index(self) -> int:
		font = Glyphs.font
		if font is None or not self.fontview.is_enabled(font):
			return 0
		return 2 if self.fontview.mode(font) == "Glyph" else 1

	# Popover closed and the user edited at least one label colour: prompt for the
	# Glyphs restart its own views need (Color Flow already updated live).
	@objc.python_method
	def _popover_did_close(self, sender) -> None:
		if getattr(self, "_labelColorsEdited", False):
			self._labelColorsEdited = False
			Message("Restart Glyphs for the new label colours to take effect in its "
				"own Font and Edit views. Color Flow already updated.", title="Color Flow")

	@objc.python_method
	def _close_popover(self) -> None:
		popover = getattr(self, "_popover", None)
		if popover is not None:
			try:
				popover.close()
			except Exception:
				pass
			self._popover = None

	# Gather all twelve wells -> write LabelColors, best-effort live-refresh the
	# app, and refresh Color Flow's own swatches immediately.
	@objc.python_method
	def _label_color_changed(self, sender) -> None:
		try:
			colors = []
			for well in getattr(self, "_labelWells", []):
				native = well.get()
				rgb = native.colorUsingColorSpaceName_("NSCalibratedRGBColorSpace") or native
				colors.append((rgb.redComponent(), rgb.greenComponent(),
					rgb.blueComponent(), rgb.alphaComponent()))
			if len(colors) == 12:
				labelcolors.write_label_colors(colors)
				labelcolors.refresh_app_label_colors(colors)
				self._labelColorsEdited = True
				self.colorKeys = self._label_color_keys()
				self.reload_after_settings()
		except Exception:
			import traceback
			print("Color Flow [label colour] error:\n" + traceback.format_exc())

	# Rename workflow labels from the settings window: gather all 12 fields and
	# rewrite colorNames.txt (a non-empty field = visible, empty = hidden),
	# preserving the colour order + the None label.
	@objc.python_method
	def _label_name_changed(self, sender) -> None:
		try:
			font = Glyphs.font
			path = colornames.get_key_file(self._font_dir(font))
			text = colornames.pick_settings_text(
				colornames.font_labels_text(font), colornames.read_color_names(path))
			rows, noneLabel = colornames.parse_settings(text)
			fields = getattr(self, "_labelFields", {})
			newRows = []
			for index, label, visible in rows:
				field = fields.get(index)
				if field is not None:
					newLabel = field.get().strip()
					newRows.append((index, newLabel, bool(newLabel)))
				else:
					newRows.append((index, label, visible))
			newText = colornames.render_settings(newRows, noneLabel)
			colornames.write_color_names(path, newText)
			# keep the in-font copy in sync when this font stores its labels in-file
			if font is not None and colornames.font_labels_text(font) is not None:
				font.userData[colornames.FONT_LABELS_KEY] = newText
			self.meaning = self.Load_Meaning()
			self._lastSignature = None
			self.Update_Plugin_UI()
			try:
				if getattr(self, "fontview", None) and font is not None and self.fontview.is_enabled(font):
					self.fontview.maybe_rebuild(font)
			except Exception:
				pass
		except Exception:
			import traceback
			print("Color Flow [rename label] error:\n" + traceback.format_exc())

	@objc.python_method
	def _label_colors_reset(self, sender) -> None:
		try:
			labelcolors.reset_label_colors()
			rgbaList = labelcolors.read_label_colors()
			for index, well in enumerate(getattr(self, "_labelWells", [])):
				well.set(AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(*rgbaList[index]))
			labelcolors.refresh_app_label_colors(rgbaList)
			self.colorKeys = self._label_color_keys()
			self.reload_after_settings()
		except Exception:
			import traceback
			print("Color Flow [label reset] error:\n" + traceback.format_exc())

	# ------------------------------------------------------------------ workflow profiles (.colorflow)

	@objc.python_method
	def _live_profile(self, font, font_dir, name="") -> dict:
		# Gather the current Color Flow config into a portable profile dict.
		color_names = colornames.read_color_names(colornames.get_key_file(font_dir))
		source = self.fontview.mode(font) if font is not None else "Layer"
		return colorflow_profile.build_profile(
			color_names=color_names, free_mode=self._free_mode(), rainbow_source=source,
			label_colors=labelcolors.read_label_colors(), name=name)

	@objc.python_method
	def _font_dir(self, font) -> str | None:
		return os.path.dirname(font.filepath) if (font is not None and font.filepath) else None

	@objc.python_method
	def _export_profile(self, sender) -> None:
		try:
			font = Glyphs.font
			family = (font.familyName if font is not None else "") or "Color Flow profile"
			profile = self._live_profile(font, self._font_dir(font), name=family)
			path = GetSaveFile("Export Color Flow profile", "Color-Flow-Profile.json", ["json"])
			if not path:
				return
			with open(path, "w", encoding="utf-8") as handle:
				handle.write(colorflow_profile.serialize(profile))
			Message("Saved Color Flow profile.", title="Color Flow")
		except Exception:
			import traceback
			print("Color Flow [export profile] error:\n" + traceback.format_exc())

	@objc.python_method
	def _import_profile(self, sender) -> None:
		try:
			path = GetOpenFile("Import Color Flow profile", False, ["json", "colorflow"])
			if not path:
				return
			with open(path, encoding="utf-8") as handle:
				incoming = colorflow_profile.parse(handle.read())
			font = Glyphs.font
			font_dir = self._font_dir(font)
			diffs = colorflow_profile.diff_profile(self._live_profile(font, font_dir), incoming)
			if not self._confirm_import(incoming, diffs):
				return
			self._apply_profile(incoming, font, font_dir)
		except ValueError as error:
			Message(str(error), title="Color Flow")
		except Exception:
			import traceback
			print("Color Flow [import profile] error:\n" + traceback.format_exc())

	@objc.python_method
	def _confirm_import(self, incoming, diffs) -> bool:
		# Surface what will change before applying, so a shared profile never
		# silently overwrites local choices.
		if diffs:
			shown = diffs[:12]
			summary = "\n".join(f"• {d['field']}: {d['detail']}" for d in shown)
			if len(diffs) > len(shown):
				summary += f"\n• …and {len(diffs) - len(shown)} more"
			info = f"Importing “{incoming.get('name', 'profile')}” will change:\n\n{summary}"
		else:
			info = "This profile matches your current settings."
		alert = AppKit.NSAlert.alloc().init()
		alert.setMessageText_("Import Color Flow profile?")
		alert.setInformativeText_(info)
		alert.addButtonWithTitle_("Apply")
		alert.addButtonWithTitle_("Cancel")
		return alert.runModal() == AppKit.NSAlertFirstButtonReturn

	@objc.python_method
	def _apply_profile(self, incoming, font, font_dir) -> None:
		# Never overwrite the user's colorNames with an empty file: parse()
		# normalises a missing/null colorNames to "", so a profile built from a
		# font that had no key file would otherwise wipe local labels/order.
		incoming_names = incoming.get("colorNames", "")
		if incoming_names.strip():
			colornames.write_color_names(colornames.get_key_file(font_dir), incoming_names)
		Glyphs.defaults["com.hugojourdan.ColorFlow-FreeMode"] = bool(incoming.get("freeMode"))
		if font is not None:
			self.fontview.set_mode(font, incoming.get("rainbowSource", "Layer"))
		colors = [tuple(rgba) for rgba in incoming.get("labelColors", [])]
		if len(colors) == 12:
			labelcolors.write_label_colors(colors)
			labelcolors.refresh_app_label_colors(colors)
		self.colorKeys = self._label_color_keys()
		self.reload_after_settings()
		Message("Imported Color Flow profile. Restart Glyphs if the label colours do not "
			"update in its own Font and Edit views.", title="Color Flow")

	@objc.python_method
	def _open_legend(self, sender) -> None:
		try:
			meaning = getattr(self, "meaning", {}) or {}
			visible = colornames.visible_labels(meaning)
			free = bool(Glyphs.defaults["com.hugojourdan.ColorFlow-FreeMode"])
			mode_line = ("Free mode: each colour is independent."
				if free else
				"Step mode: a colour means every step up to it is done.")
			lines = [mode_line, ""]
			for position, (color, label) in enumerate(visible.items(), start=1):
				name = colornames.COLOR_NAMES.get(int(color), str(color))
				lines.append(f"{position}. {label}  ({name})")
			Message("\n".join(lines), title="Color Flow — Legend")
		except Exception:
			import traceback
			print("Color Flow [legend] error:\n" + traceback.format_exc())

	# Free-mode checkbox in the action popover (ported from the unreachable
	# settings_panel.py): persist the app-wide default, then redraw. Free vs step
	# changes both the derived per-step counts and the row checkbox states, so the
	# cached per-master counts must be dropped first — a plain redraw would repaint
	# from the stale cache until the next interface update.
	@objc.python_method
	def _popover_free_mode(self, sender) -> None:
		try:
			Glyphs.defaults["com.hugojourdan.ColorFlow-FreeMode"] = bool(sender.get())
			try:
				if self.font is not None:
					self._invalidate_counts(self.font.selectedFontMaster.id)
			except Exception:
				pass
			self._lastSignature = None
			self.Update_Plugin_UI()
		except Exception:
			import traceback
			print("Color Flow [free mode] error:\n" + traceback.format_exc())

	# Exporting-only checkbox in the action popover: persist the app-wide pref,
	# then redraw. The counts cache key includes the pref (_counts_cache_key) so
	# the two modes can never read each other's cache, but the freshly selected
	# mode's entry may itself be stale from an earlier toggle — drop it before
	# the redraw, same discipline as the free-mode handler.
	@objc.python_method
	def _popover_exporting_only(self, sender) -> None:
		try:
			Glyphs.defaults[_EXPORTING_ONLY_KEY] = bool(sender.get())
			try:
				if self.font is not None:
					self._invalidate_counts(self.font.selectedFontMaster.id)
			except Exception:
				pass
			self._lastSignature = None
			self.Update_Plugin_UI()
		except Exception:
			import traceback
			print("Color Flow [exporting only] error:\n" + traceback.format_exc())

	# Store-labels checkbox (ported from settings_panel._save): ticking mirrors the
	# current effective label text into font.userData[FONT_LABELS_KEY] so the
	# labels travel with the shared .glyphs file; unticking clears the key so the
	# external colorNames.txt takes over again.
	@objc.python_method
	def _popover_store_in_font(self, sender) -> None:
		try:
			font = Glyphs.font
			if font is None:
				return
			if bool(sender.get()):
				path = colornames.get_key_file(self._font_dir(font))
				text = colornames.pick_settings_text(
					colornames.font_labels_text(font), colornames.read_color_names(path))
				font.userData[colornames.FONT_LABELS_KEY] = text
			elif font.userData[colornames.FONT_LABELS_KEY] is not None:
				del font.userData[colornames.FONT_LABELS_KEY]
			# Unticking can swap which source wins, so re-resolve the popover's
			# name fields and rebuild the palette from the effective text.
			self._refresh_popover_label_fields(font)
			self.reload_after_settings()
		except Exception:
			import traceback
			print("Color Flow [store labels] error:\n" + traceback.format_exc())

	@objc.python_method
	def _refresh_popover_label_fields(self, font) -> None:
		# Push the re-resolved effective label text into the open popover's fields.
		try:
			text = colornames.pick_settings_text(
				colornames.font_labels_text(font),
				colornames.read_color_names(colornames.get_key_file(self._font_dir(font))))
			rows, _noneLabel = colornames.parse_settings(text)
			labels = {index: label for index, label, _visible in rows}
			for index, field in getattr(self, "_labelFields", {}).items():
				field.set(labels.get(index, ""))
		except Exception:
			pass

	# ------------------------------------------------------------------ workflow recipes editor
	# A vanilla FloatingWindow editing the opt-in workflow recipes (#5) that the
	# report's recipe-adjusted completion reads from Glyphs.defaults — previously
	# only definable by hand-typing JSON in the Macro panel. All parsing /
	# validation / persistence goes through the pure colorflow_recipes helpers so
	# the logic stays unit-tested; this layer is only widgets.

	# The visible workflow steps (key -> label) in workflow order, one checkbox
	# per step in every editor row. Reloaded each open so label renames show up.
	@objc.python_method
	def _recipe_steps(self) -> list:
		meaning = getattr(self, "meaning", None) or self.Load_Meaning()
		return list(colornames.visible_labels(meaning).items())

	# Match-field values actually present in the open font, stringified exactly
	# like the report's glyph_meta stringifies them so popup values and recipe
	# matching compare equal. Empty lists with no font: match_options then falls
	# back to its static vocabulary.
	@objc.python_method
	def _recipe_field_values(self) -> dict:
		values: dict = {field: [] for field, _label in colorflow_recipes.MATCH_FIELDS}
		font = Glyphs.font
		if font is not None:
			try:
				for glyph in font.glyphs:
					for field in values:
						value = getattr(glyph, field, None)
						if value:
							values[field].append(str(value))
			except Exception:
				pass
		return values

	@objc.python_method
	def _open_recipes_editor(self, sender) -> None:
		try:
			self._close_popover()
			import colorflow_dashboard
			draft = colorflow_recipes.parse_recipes(
				Glyphs.defaults[colorflow_dashboard.RECIPES_KEY])
			self._build_recipes_window(draft)
		except Exception:
			import traceback
			print("Color Flow [recipes editor] error:\n" + traceback.format_exc())

	# (Re)build the whole editor window from a draft list — add/remove rebuild the
	# window instead of reflowing it, which keeps the vanilla layout trivial. Note:
	# steps a recipe lists beyond the currently visible workflow are dropped on
	# save (the editor edits THIS workflow; serialize_recipes normalises anyway).
	@objc.python_method
	def _build_recipes_window(self, draft: list, position: tuple | None = None) -> None:
		self._close_recipes_editor()
		steps = self._recipe_steps()
		field_values = self._recipe_field_values()
		step_lines = -(-len(steps) // 4) if steps else 0
		row_height = 28 + step_lines * 22 + 12
		rows_top = 36
		body_height = len(draft) * row_height if draft else 24
		window = FloatingWindow((660, rows_top + body_height + 46),
			"Color Flow — Workflow Recipes")
		self._recipesWindow = window
		self._recipesRows = []
		for text, x, width in (("Name", 12, 188), ("Category", 208, 106),
				("Script", 318, 106), ("Subcategory", 428, 110), ("Case", 542, 106)):
			setattr(window, f"head{text}", TextBox((x, 14, width, 14), text, sizeStyle='mini'))
		if not draft:
			window.empty = TextBox((12, rows_top + 4, -12, 16),
				"No recipes yet — click + to add one.", sizeStyle='small')
		for row_index, recipe in enumerate(draft):
			self._build_recipe_row(window, row_index, recipe,
				rows_top + row_index * row_height, steps, field_values)
		window.addRecipe = Button((12, -34, 32, 22), "+",
			callback=self._recipes_add, sizeStyle='small')
		window.removeRecipe = Button((50, -34, 32, 22), "−",
			callback=self._recipes_remove, sizeStyle='small')
		window.cancel = Button((-188, -34, 80, 22), "Cancel",
			callback=self._recipes_cancel, sizeStyle='small')
		window.save = Button((-100, -34, 88, 22), "Save",
			callback=self._recipes_save, sizeStyle='small')
		window.setDefaultButton(window.save)
		if position is not None:
			try:
				_x, _y, current_w, current_h = window.getPosSize()
				window.setPosSize((position[0], position[1], current_w, current_h))
			except Exception:
				pass
		window.open()

	# One editor row: name field, an "Any"-defaulting popup per match criterion
	# (so multi-criteria recipes round-trip without loss), one checkbox per
	# visible workflow step, and a separator.
	@objc.python_method
	def _build_recipe_row(self, window, row_index: int, recipe: dict, top: int,
			steps: list, field_values: dict) -> None:
		match = recipe.get("match", {})
		row: dict = {"popups": {}, "options": {}, "steps": {}}
		row["name"] = EditText((12, top, 188, 22), recipe.get("name", ""),
			continuous=False, sizeStyle='small')
		setattr(window, f"recipeName{row_index}", row["name"])
		layout = {"category": (208, 106), "script": (318, 106),
			"subCategory": (428, 110), "case": (542, 106)}
		for field, _label in colorflow_recipes.MATCH_FIELDS:
			x, width = layout[field]
			selected = match.get(field) or None
			options = colorflow_recipes.match_options(field, field_values.get(field), selected)
			values = [""] + [value for value, _optionLabel in options]
			popup = PopUpButton((x, top, width, 22),
				["Any"] + [optionLabel for _value, optionLabel in options], sizeStyle='small')
			popup.set(values.index(selected) if selected in values else 0)
			setattr(window, f"recipe{field.capitalize()}{row_index}", popup)
			row["popups"][field] = popup
			row["options"][field] = values
		wanted = set(recipe.get("steps") or [])
		for position, (key, label) in enumerate(steps):
			checkbox = CheckBox(
				(12 + (position % 4) * 160, top + 28 + (position // 4) * 22, 156, 18),
				label, value=(key in wanted), sizeStyle='small')
			setattr(window, f"recipeStep{row_index}_{key}", checkbox)
			row["steps"][key] = checkbox
		step_lines = -(-len(steps) // 4) if steps else 0
		setattr(window, f"recipeSep{row_index}",
			HorizontalLine((12, top + 28 + step_lines * 22 + 4, -12, 1)))
		self._recipesRows.append(row)

	# Read every editor row back into raw recipe dicts. serialize_recipes /
	# parse_recipes do all the validation, so this stays dumb on purpose.
	@objc.python_method
	def _recipes_draft_from_ui(self) -> list:
		draft = []
		for row in getattr(self, "_recipesRows", []):
			match = {}
			for field, popup in row["popups"].items():
				values = row["options"][field]
				index = popup.get()
				value = values[index] if 0 <= index < len(values) else ""
				if value:
					match[field] = value
			checked = [key for key, checkbox in row["steps"].items() if checkbox.get()]
			draft.append({"name": row["name"].get().strip(), "match": match, "steps": checked})
		return draft

	@objc.python_method
	def _recipes_window_position(self) -> tuple | None:
		window = getattr(self, "_recipesWindow", None)
		if window is None:
			return None
		try:
			x, y, _width, _height = window.getPosSize()
			return (x, y)
		except Exception:
			return None

	@objc.python_method
	def _recipes_add(self, sender) -> None:
		try:
			position = self._recipes_window_position()
			draft = self._recipes_draft_from_ui()
			# a fresh recipe starts with every visible step checked (= full order,
			# the engine's no-op), so saving it unedited changes nothing.
			draft.append({"name": "", "match": {},
				"steps": [key for key, _label in self._recipe_steps()]})
			self._build_recipes_window(draft, position=position)
		except Exception:
			import traceback
			print("Color Flow [recipes add] error:\n" + traceback.format_exc())

	@objc.python_method
	def _recipes_remove(self, sender) -> None:
		try:
			position = self._recipes_window_position()
			draft = self._recipes_draft_from_ui()
			if draft:
				draft.pop()
			self._build_recipes_window(draft, position=position)
		except Exception:
			import traceback
			print("Color Flow [recipes remove] error:\n" + traceback.format_exc())

	@objc.python_method
	def _recipes_save(self, sender) -> None:
		# Persist through the pure helpers: serialize_recipes normalises and
		# validates the round-trip, so the report engine reads back exactly what
		# the editor saved.
		try:
			import colorflow_dashboard
			Glyphs.defaults[colorflow_dashboard.RECIPES_KEY] = (
				colorflow_recipes.serialize_recipes(self._recipes_draft_from_ui()))
			self._close_recipes_editor()
		except Exception:
			import traceback
			print("Color Flow [recipes save] error:\n" + traceback.format_exc())

	@objc.python_method
	def _recipes_cancel(self, sender) -> None:
		self._close_recipes_editor()

	@objc.python_method
	def _close_recipes_editor(self) -> None:
		window = getattr(self, "_recipesWindow", None)
		if window is not None:
			try:
				window.close()
			except Exception:
				pass
		self._recipesWindow = None
		self._recipesRows = []

	@objc.python_method
	def _generate_smart_filters(self, sender) -> None:
		# Build a "Color Flow" smart-filter group (one filter per visible step +
		# None) and merge it into the font's Filters parameter. Filters match the
		# GLYPH colour — Glyphs has no per-master layer-colour predicate.
		try:
			font = Glyphs.font
			if font is None:
				Message("Open a font first.", title="Color Flow")
				return
			meaning = self.Load_Meaning()
			steps = [(int(index), label)
				for index, label in colornames.visible_labels(meaning).items()]
			text = colornames.read_color_names(colornames.get_key_file(self._font_dir(font)))
			none_label = colornames.parse_settings(text)[1] or "None"
			group = colorflow_filters.build_filter_group(steps, none_label)
			existing = [dict(entry) for entry in (font.customParameters["Filters"] or [])]
			font.customParameters["Filters"] = colorflow_filters.merge_into_filters(existing, group)
			Message("Added the “Color Flow” smart-filter group to the sidebar "
				"(filters by glyph colour).", title="Color Flow")
		except Exception:
			import traceback
			print("Color Flow [smart filters] error:\n" + traceback.format_exc())

	@objc.python_method
	def _popover_dashboard(self, sender) -> None:
		# The timeline records itself to the font's userData on every save (non-git
		# fonts) — no git commits, no opt-in. So generating a report just builds it.
		self._close_popover()
		self._present_report_sheet()

	# Present a titled panel as a sheet on the palette window with an
	# indeterminate progress bar, then build the report on the next runloop tick
	# (so the sheet has painted) and dismiss the sheet when it opens.
	@objc.python_method
	def _present_report_sheet(self) -> None:
		try:
			parent = self.dialog.window() if self.dialog is not None else None
			if parent is None:
				self.Open_Color_Font_Dashboard(None)
				return
			rect = AppKit.NSMakeRect(0, 0, 256, 84)
			panel = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
				rect, AppKit.NSWindowStyleMaskTitled, AppKit.NSBackingStoreBuffered, False)
			panel.setTitle_("Color Flow")
			content = panel.contentView()
			label = AppKit.NSTextField.labelWithString_("Generating Color Flow report\u2026")
			label.setFrame_(AppKit.NSMakeRect(16, 52, 224, 16))
			content.addSubview_(label)
			loader = _ColorFlowLoaderBar.alloc().initWithFrame_(AppKit.NSMakeRect(16, 16, 224, 30))
			loader.configure(labelcolors.read_label_colors())
			content.addSubview_(loader)
			# Open / Save buttons, hidden until the build finishes — they replace the
			# loader so the report is no longer opened automatically.
			open_btn = AppKit.NSButton.buttonWithTitle_target_action_("Open", self, "openReport:")
			open_btn.setFrame_(AppKit.NSMakeRect(54, 18, 70, 24))
			open_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
			open_btn.setKeyEquivalent_("\r")   # Open = default button (Return)
			open_btn.setHidden_(True)
			content.addSubview_(open_btn)
			save_btn = AppKit.NSButton.buttonWithTitle_target_action_("Save", self, "saveReport:")
			save_btn.setFrame_(AppKit.NSMakeRect(132, 18, 70, 24))
			save_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
			save_btn.setHidden_(True)
			content.addSubview_(save_btn)
			self._reportLoader = loader
			self._reportPanel = panel
			self._reportLabel = label
			self._openBtn = open_btn
			self._saveBtn = save_btn
			self._reportPath = None
			parent.beginSheet_completionHandler_(panel, None)
			# Let the sheet paint once, then build on the next run-loop hop. The build
			# drives the bar with REAL progress (set_progress + run-loop pumping); when it
			# finishes we reveal Open / Save instead of auto-opening the report.
			self.performSelector_withObject_afterDelay_("runReportGeneration:", None, 0.08)
		except Exception:
			import traceback
			print("Color Flow [report sheet] error:\n" + traceback.format_exc())
			self.Open_Color_Font_Dashboard(None)

	def runReportGeneration_(self, sender) -> None:
		loader = getattr(self, "_reportLoader", None)

		def _on_progress(frac: float) -> None:
			if loader is not None:
				loader.set_progress(frac)
			_pump_runloop()

		path = None
		try:
			path = self._run_dashboard(_on_progress, open_when_done=False)
		finally:
			if loader is not None:
				try:
					loader.set_progress(1.0)
				except Exception:
					pass
			self._reportPath = path
			# Build is done and the main thread is free again: let the bar visibly reach
			# 100% (a few timer ticks), then reveal the Open / Save buttons.
			self.performSelector_withObject_afterDelay_("showReportActions:", None, 0.3)

	def showReportActions_(self, sender) -> None:
		self._show_report_actions()

	@objc.python_method
	def _show_report_actions(self) -> None:
		# Build finished: stop + hide the loader, swap the label, and reveal Open / Save.
		# If nothing was produced, just close the sheet.
		loader = getattr(self, "_reportLoader", None)
		if loader is not None:
			try:
				loader.stop()
			except Exception:
				pass
			loader.setHidden_(True)
		path = getattr(self, "_reportPath", None)
		if path is None:
			self._dismiss_report_sheet()
			return
		label = getattr(self, "_reportLabel", None)
		if label is not None:
			label.setStringValue_("Color Flow report ready")
		for button in (getattr(self, "_openBtn", None), getattr(self, "_saveBtn", None)):
			if button is not None:
				button.setHidden_(False)

	def openReport_(self, sender) -> None:
		path = getattr(self, "_reportPath", None)
		if path is not None:
			try:
				webbrowser.open(path.as_uri())
			except Exception:
				import traceback
				print("Color Flow [open report] error:\n" + traceback.format_exc())
		self._dismiss_report_sheet()

	def saveReport_(self, sender) -> None:
		self._save_report_path(getattr(self, "_reportPath", None))
		self._dismiss_report_sheet()

	@objc.python_method
	def _save_report_path(self, path) -> None:
		# Shared "save a copy of the .html" via NSSavePanel — used by the sheet's Save
		# button and the inline web view's Save… button. No-op when there's no report.
		if path is None:
			return
		try:
			save_panel = AppKit.NSSavePanel.savePanel()
			save_panel.setNameFieldStringValue_(path.name)
			try:
				save_panel.setAllowedFileTypes_(["html"])
			except Exception:
				pass
			if save_panel.runModal() == AppKit.NSModalResponseOK:
				url = save_panel.URL()
				dest = url.path() if url is not None else None
				if dest:
					with open(dest, "wb") as handle:
						handle.write(path.read_bytes())
		except Exception:
			import traceback
			print("Color Flow [save report] error:\n" + traceback.format_exc())

	# ----- View here: the report inside an embedded WKWebView -------------------
	def viewReportInline_(self, sender) -> None:
		path = getattr(self, "_reportPath", None)
		self._dismiss_report_sheet()                 # close the small action sheet first
		if path is not None:
			self._present_report_webview(path)

	@objc.python_method
	def _present_report_webview(self, path) -> None:
		# Embed the self-contained report in a WKWebView and present it as a sheet on the
		# document window (the docked palette is too narrow to host it). glyphsapp:// glyph
		# links route to Glyphs via a block-free JS message handler; the file:// report
		# loads in place. Falls back to a floating window with no doc window; browser on error.
		try:
			import WebKit
			style = (AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable
				| AppKit.NSWindowStyleMaskResizable | AppKit.NSWindowStyleMaskMiniaturizable)
			window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
				AppKit.NSMakeRect(0, 0, 1040, 740), style, AppKit.NSBackingStoreBuffered, False)
			window.setTitle_("Color Flow — " + path.name)
			window.setReleasedWhenClosed_(False)
			window.setDelegate_(self)
			content = window.contentView()
			bar_h = 40
			size = content.bounds().size
			config = WebKit.WKWebViewConfiguration.alloc().init()
			# Route clicks on glyphsapp:// glyph links to Glyphs through a JS message
			# handler — block-free, unlike a navigation-policy completion handler (whose
			# block crashes PyObjC). The file:// report itself just loads normally.
			controller = config.userContentController()
			controller.addScriptMessageHandler_name_(self, "cfGlyph")
			click_js = (
				"document.addEventListener('click',function(e){"
				"var a=e.target.closest&&e.target.closest('a[href^=\"glyphsapp:\"]');"
				"if(a){e.preventDefault();try{"
				"window.webkit.messageHandlers.cfGlyph.postMessage(a.getAttribute('href'));"
				"}catch(err){}}},true);"
			)
			controller.addUserScript_(
				WebKit.WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(
					click_js, WebKit.WKUserScriptInjectionTimeAtDocumentEnd, True))
			web = WebKit.WKWebView.alloc().initWithFrame_configuration_(
				AppKit.NSMakeRect(0, bar_h, size.width, size.height - bar_h), config)
			web.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
			web.loadFileURL_allowingReadAccessToURL_(
				AppKit.NSURL.fileURLWithPath_(str(path)),
				AppKit.NSURL.fileURLWithPath_(str(path.parent)))
			content.addSubview_(web)
			save_btn = AppKit.NSButton.buttonWithTitle_target_action_("Save…", self, "saveReportFile:")
			save_btn.setFrame_(AppKit.NSMakeRect(12, 8, 90, 24))
			save_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
			save_btn.setAutoresizingMask_(AppKit.NSViewMaxXMargin)
			content.addSubview_(save_btn)
			browser_btn = AppKit.NSButton.buttonWithTitle_target_action_("Open in Browser", self, "openReportBrowser:")
			browser_btn.setFrame_(AppKit.NSMakeRect(108, 8, 130, 24))
			browser_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
			browser_btn.setAutoresizingMask_(AppKit.NSViewMaxXMargin)
			content.addSubview_(browser_btn)
			done_btn = AppKit.NSButton.buttonWithTitle_target_action_("Done", self, "dismissReportWindow:")
			done_btn.setFrame_(AppKit.NSMakeRect(size.width - 92, 8, 80, 24))
			done_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
			done_btn.setKeyEquivalent_("\r")
			done_btn.setAutoresizingMask_(AppKit.NSViewMinXMargin)
			content.addSubview_(done_btn)
			self._reportWindow = window
			self._reportWeb = web
			self._reportController = controller
			self._reportWebPath = path
			parent = None
			try:
				doc = Glyphs.font.parent if (Glyphs.font is not None) else None
				wc = doc.windowController() if doc is not None else None
				parent = wc.window() if wc is not None else None
			except Exception:
				parent = None
			if parent is None:
				try:
					parent = AppKit.NSApp.mainWindow() or AppKit.NSApp.keyWindow()
				except Exception:
					parent = None
			if parent is not None:
				parent.beginSheet_completionHandler_(window, None)
			else:
				window.center()
				window.makeKeyAndOrderFront_(None)
		except Exception:
			import traceback
			print("Color Flow [inline report] error:\n" + traceback.format_exc())
			try:
				webbrowser.open(path.as_uri())
			except Exception:
				pass

	def saveReportFile_(self, sender) -> None:
		self._save_report_path(getattr(self, "_reportWebPath", None))

	def openReportBrowser_(self, sender) -> None:
		path = getattr(self, "_reportWebPath", None)
		if path is not None:
			try:
				webbrowser.open(path.as_uri())
			except Exception:
				pass

	def dismissReportWindow_(self, sender) -> None:
		self._dismiss_report_window()

	@objc.python_method
	def _dismiss_report_window(self) -> None:
		# End the report sheet (or close the floating fallback window) and drop refs,
		# removing the script-message handler to break the controller -> self cycle.
		window = getattr(self, "_reportWindow", None)
		controller = getattr(self, "_reportController", None)
		if controller is not None:
			try:
				controller.removeScriptMessageHandlerForName_("cfGlyph")
			except Exception:
				pass
		if window is not None:
			try:
				parent = window.sheetParent()
				if parent is not None:
					parent.endSheet_(window)
				window.orderOut_(None)
			except Exception:
				pass
		self._reportController = None
		self._reportWeb = None
		self._reportWindow = None
		self._reportWebPath = None

	# ------------------------------------------------------------------ #
	#  First-run tutorial sheet (multi-slide, arrow navigation)
	# ------------------------------------------------------------------ #

	def showTutorialIfFirstRun_(self, sender) -> None:
		# Deferred from start(). Shows the tutorial once ever (global flag), attaching a
		# sheet to the document window; falls back to a floating panel if none is found.
		try:
			if Glyphs.defaults["com.hugojourdan.ColorFlow-TutorialShown"]:
				return
			if getattr(self, "_tutorialPanel", None) is not None:
				return                                  # already on screen
			self._present_tutorial()
		except Exception:
			import traceback
			print("Color Flow [tutorial] error:\n" + traceback.format_exc())

	@objc.python_method
	def _tutorial_parent_window(self):
		# Prefer the frontmost document's window (the sheet drops from the app window),
		# then the app's main / key window; None -> caller shows a floating fallback.
		try:
			doc = Glyphs.font.parent if Glyphs.font is not None else None
			wc = doc.windowController() if doc is not None else None
			window = wc.window() if wc is not None else None
			if window is not None:
				return window
		except Exception:
			pass
		try:
			return AppKit.NSApp.mainWindow() or AppKit.NSApp.keyWindow()
		except Exception:
			return None

	@objc.python_method
	def _present_tutorial(self) -> None:
		import colorflow_tutorial
		self._tutorialSlides = colorflow_tutorial.slides()
		count = len(self._tutorialSlides)
		if count == 0:
			return
		self._tutorialIndex = 0
		width, height = 540, 360
		rect = AppKit.NSMakeRect(0, 0, width, height)
		panel = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
			rect, AppKit.NSWindowStyleMaskTitled, AppKit.NSBackingStoreBuffered, False)
		panel.setTitle_("Welcome to Color Flow")
		content = panel.contentView()

		title = AppKit.NSTextField.labelWithString_("")
		title.setFrame_(AppKit.NSMakeRect(32, height - 80, width - 64, 30))
		title.setFont_(AppKit.NSFont.boldSystemFontOfSize_(20.0))
		content.addSubview_(title)

		body = AppKit.NSTextField.wrappingLabelWithString_("")
		body.setFrame_(AppKit.NSMakeRect(32, 72, width - 64, height - 168))
		body.setFont_(AppKit.NSFont.systemFontOfSize_(13.0))
		body.setSelectable_(False)
		content.addSubview_(body)

		# Clickable page bubbles: one borderless button per slide, centered, each
		# carrying its index as the button tag. Click jumps straight to that slide.
		dot_size, gap = 26, 4
		row_width = count * dot_size + (count - 1) * gap
		start_x = (width - row_width) / 2.0
		dot_buttons = []
		for position in range(count):
			dot = AppKit.NSButton.buttonWithTitle_target_action_("", self, "tutorialDot:")
			dot.setFrame_(AppKit.NSMakeRect(
				start_x + position * (dot_size + gap), 26, dot_size, dot_size))
			dot.setBordered_(False)
			dot.setTag_(position)
			content.addSubview_(dot)
			dot_buttons.append(dot)

		# Red close bubble, top-right (the sheet has no title bar of its own to close it).
		close_size = 16
		close = AppKit.NSButton.buttonWithTitle_target_action_("", self, "tutorialClose:")
		close.setFrame_(AppKit.NSMakeRect(
			width - close_size - 14, height - close_size - 14, close_size, close_size))
		close.setBordered_(False)
		close.setWantsLayer_(True)
		try:
			layer = close.layer()
			if layer is not None:
				layer.setBackgroundColor_(AppKit.NSColor.systemRedColor().CGColor())
				layer.setCornerRadius_(close_size / 2.0)
			attrs = {
				AppKit.NSForegroundColorAttributeName: AppKit.NSColor.whiteColor(),
				AppKit.NSFontAttributeName: AppKit.NSFont.boldSystemFontOfSize_(10.0),
			}
			close.setAttributedTitle_(
				AppKit.NSAttributedString.alloc().initWithString_attributes_("✕", attrs))
		except Exception:
			close.setTitle_("✕")
		content.addSubview_(close)

		self._tutorialPanel = panel
		self._tutorialTitle = title
		self._tutorialBody = body
		self._tutorialDotButtons = dot_buttons
		self._tutorial_render()
		self._install_tutorial_key_monitor()

		Glyphs.defaults["com.hugojourdan.ColorFlow-TutorialShown"] = True
		# Present as a sheet attached to the document window; floating fallback if none.
		parent = self._tutorial_parent_window()
		if parent is not None:
			parent.beginSheet_completionHandler_(panel, None)
		else:
			panel.center()
			panel.makeKeyAndOrderFront_(None)

	@objc.python_method
	def _install_tutorial_key_monitor(self) -> None:
		# Left / right arrow keys step between slides while the tutorial is up.
		def _handler(event):
			try:
				if getattr(self, "_tutorialPanel", None) is None:
					return event
				code = event.keyCode()
				if code == 123:               # left arrow
					self._tutorial_step(-1)
					return None
				if code == 124:               # right arrow
					self._tutorial_step(1)
					return None
			except Exception:
				pass
			return event
		try:
			self._tutorialKeyMonitor = (
				AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
					AppKit.NSEventMaskKeyDown, _handler))
		except Exception:
			self._tutorialKeyMonitor = None

	@objc.python_method
	def _tutorial_set_dot(self, button, filled: bool) -> None:
		glyph = "\u25CF" if filled else "\u25CB"     # \u25CF filled / \u25CB hollow
		try:
			color = (AppKit.NSColor.controlAccentColor() if filled
				else AppKit.NSColor.tertiaryLabelColor())
			attrs = {
				AppKit.NSForegroundColorAttributeName: color,
				AppKit.NSFontAttributeName: AppKit.NSFont.systemFontOfSize_(15.0),
			}
			button.setAttributedTitle_(
				AppKit.NSAttributedString.alloc().initWithString_attributes_(glyph, attrs))
		except Exception:
			button.setTitle_(glyph)

	@objc.python_method
	def _tutorial_render(self) -> None:
		import colorflow_tutorial
		slides = getattr(self, "_tutorialSlides", [])
		count = len(slides)
		title = self._tutorialTitle
		body = self._tutorialBody
		dot_buttons = getattr(self, "_tutorialDotButtons", [])
		if count == 0 or title is None or body is None:
			return
		index = colorflow_tutorial.clamp_index(getattr(self, "_tutorialIndex", 0), count)
		self._tutorialIndex = index
		slide = slides[index]
		title.setStringValue_(slide.title)
		body.setStringValue_(slide.body)
		for position, dot in enumerate(dot_buttons):
			self._tutorial_set_dot(dot, position == index)

	@objc.python_method
	def _tutorial_step(self, delta: int) -> None:
		import colorflow_tutorial
		count = len(getattr(self, "_tutorialSlides", []))
		self._tutorialIndex = colorflow_tutorial.clamp_index(
			getattr(self, "_tutorialIndex", 0) + delta, count)
		self._tutorial_render()

	def tutorialDot_(self, sender) -> None:
		try:
			self._tutorialIndex = int(sender.tag())
		except Exception:
			return
		self._tutorial_render()

	def tutorialClose_(self, sender) -> None:
		self._dismiss_tutorial()

	@objc.python_method
	def _dismiss_tutorial(self) -> None:
		monitor = getattr(self, "_tutorialKeyMonitor", None)
		if monitor is not None:
			try:
				AppKit.NSEvent.removeMonitor_(monitor)
			except Exception:
				pass
		self._tutorialKeyMonitor = None
		panel = getattr(self, "_tutorialPanel", None)
		if panel is not None:
			try:
				sheet_parent = panel.sheetParent()
				if sheet_parent is not None:
					sheet_parent.endSheet_(panel)
				panel.orderOut_(None)
			except Exception:
				pass
		self._tutorialPanel = None
		self._tutorialTitle = None
		self._tutorialBody = None
		self._tutorialDotButtons = []


	def userContentController_didReceiveScriptMessage_(self, controller, message) -> None:
		# A glyphsapp:// glyph link was clicked in the embedded report — hand the URL to
		# the system so Glyphs opens the glyph, instead of navigating the web view.
		try:
			href = message.body()
			url = AppKit.NSURL.URLWithString_(str(href)) if href else None
			if url is not None:
				AppKit.NSWorkspace.sharedWorkspace().openURL_(url)
		except Exception:
			pass

	def windowWillClose_(self, notification) -> None:
		# Drop our strong refs when the inline report window closes (avoids a leak; the
		# guard keeps this safe even though self may be the delegate of other windows).
		try:
			closing = notification.object() if notification is not None else None
		except Exception:
			closing = None
		if closing is not None and closing == getattr(self, "_reportWindow", None):
			controller = getattr(self, "_reportController", None)
			if controller is not None:
				try:
					controller.removeScriptMessageHandlerForName_("cfGlyph")
				except Exception:
					pass
			self._reportController = None
			self._reportWeb = None
			self._reportWindow = None
			self._reportWebPath = None

	def dismissReportSheet_(self, sender) -> None:
		self._dismiss_report_sheet()

	@objc.python_method
	def _dismiss_report_sheet(self) -> None:
		self._reportPath = None
		loader = getattr(self, "_reportLoader", None)
		if loader is not None:
			try:
				loader.stop()
			except Exception:
				pass
			self._reportLoader = None
		panel = getattr(self, "_reportPanel", None)
		if panel is None:
			return
		try:
			parent = panel.sheetParent()
			if parent is None and self.dialog is not None:
				parent = self.dialog.window()
			if parent is not None:
				parent.endSheet_(panel)
			panel.orderOut_(None)
		except Exception:
			pass
		self._reportPanel = None

	# Default / Layer / Glyph for the Font Glyph Order grouping (popover stays open
	# so the source can be switched without reopening).
	@objc.python_method
	def _popover_rainbow(self, sender) -> None:
		font = Glyphs.font
		if font is None:
			return
		segment = sender.get()
		try:
			if segment == 0:
				if self.fontview.is_enabled(font):
					self.fontview.disable(font)
			else:
				self.fontview.set_mode(font, "Layer" if segment == 1 else "Glyph")
				if not self.fontview.is_enabled(font):
					self.fontview.enable(font)
		except Exception:
			import traceback
			print("Color Flow [rainbow] error:\n" + traceback.format_exc())

	@objc.python_method
	def _install_rainbow_menu(self) -> None:
		# Add a File-menu toggle, removing any stale copy from a previous load.
		title = self._rainbow_menu_title()
		self._rainbowMenuItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
			title, self.toggleRainbow_, "")
		self._rainbowMenuItem.setTarget_(self)
		barItem = Glyphs.menu[FILE_MENU]
		submenu = barItem.submenu() if hasattr(barItem, "submenu") else None
		if submenu is not None:
			for item in list(submenu.itemArray()):
				if item.title() == title:
					submenu.removeItem_(item)
			submenu.addItem_(self._rainbowMenuItem)
		else:
			barItem.append(self._rainbowMenuItem)

	@objc.python_method
	def _teardown_rainbow_menu(self) -> None:
		try:
			title = self._rainbow_menu_title()
			barItem = Glyphs.menu[FILE_MENU]
			submenu = barItem.submenu() if hasattr(barItem, "submenu") else None
			if submenu is not None:
				for item in list(submenu.itemArray()):
					if item.title() == title:
						submenu.removeItem_(item)
		except Exception:
			pass

	@objc.python_method
	def _install_settings_menu(self) -> None:
		title = "Color Flow settings\u2026"
		self._settingsMenuItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, self.openSettings_, "")
		self._settingsMenuItem.setTarget_(self)
		barItem = Glyphs.menu[EDIT_MENU]
		submenu = barItem.submenu() if hasattr(barItem, "submenu") else None
		if submenu is not None:
			for item in list(submenu.itemArray()):
				if item.title() == title:
					submenu.removeItem_(item)
			submenu.addItem_(self._settingsMenuItem)
		else:
			barItem.append(self._settingsMenuItem)

	@objc.python_method
	def _teardown_settings_menu(self) -> None:
		try:
			barItem = Glyphs.menu[EDIT_MENU]
			submenu = barItem.submenu() if hasattr(barItem, "submenu") else None
			if submenu is not None:
				for item in list(submenu.itemArray()):
					if item.title() == "Color Flow settings\u2026":
						submenu.removeItem_(item)
		except Exception:
			pass

	def openSettings_(self, sender) -> None:
		try:
			self.Open_Action_Popover(sender)
		except Exception:
			import traceback
			print("Color Flow [settings menu] error:\n" + traceback.format_exc())

	_BACKFILL_TITLE = "Color Flow: Backfill timeline into font…"

	@objc.python_method
	def _install_backfill_menu(self) -> None:
		# An on-demand "record the timeline into userData now" action, so users can
		# populate the in-font history without waiting for (or relying on) a save.
		self._backfillMenuItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
			self._BACKFILL_TITLE, self.backfillTimeline_, "")
		self._backfillMenuItem.setTarget_(self)
		barItem = Glyphs.menu[EDIT_MENU]
		submenu = barItem.submenu() if hasattr(barItem, "submenu") else None
		if submenu is not None:
			for item in list(submenu.itemArray()):
				if item.title() == self._BACKFILL_TITLE:
					submenu.removeItem_(item)
			submenu.addItem_(self._backfillMenuItem)
		else:
			barItem.append(self._backfillMenuItem)

	@objc.python_method
	def _teardown_backfill_menu(self) -> None:
		try:
			barItem = Glyphs.menu[EDIT_MENU]
			submenu = barItem.submenu() if hasattr(barItem, "submenu") else None
			if submenu is not None:
				for item in list(submenu.itemArray()):
					if item.title() == self._BACKFILL_TITLE:
						submenu.removeItem_(item)
		except Exception:
			pass

	def backfillTimeline_(self, sender) -> None:
		try:
			font = Glyphs.font
			if font is None:
				Message("Open a font first.", title="Color Flow")
				return
			import colorflow_dashboard
			snapshot = colorflow_dashboard.build_master_glyph_colors(font)
			colorflow_dashboard.record_history(font, snapshot, datetime.now())
			imported = 0
			try:
				imported = colorflow_dashboard.backfill_from_git(font)
			except Exception:
				imported = 0
			entries = len(colorflow_dashboard.load_history(font))
			extra = ""
			if imported:
				extra = f" (imported {imported} commit{'' if imported == 1 else 's'} from git history)"
			tail = ("Save the font to keep it." if getattr(font, "filepath", None)
				else "Save the font (give it a file) to keep it.")
			entry_word = "snapshot" if entries == 1 else "snapshots"
			print(f"Color Flow: backfilled timeline into userData — {entries} {entry_word}{extra}.")
			Message(
				f"Color Flow wrote the timeline into this font: {entries} {entry_word} of history{extra}.\n\n{tail}",
				title="Color Flow")
		except Exception:
			import traceback
			print("Color Flow [backfill] error:\n" + traceback.format_exc())

	@objc.python_method
	def _rainbow_conflict_check(self) -> None:
		# Warn once if the standalone Rainbow FontView is still installed (two
		# plugins fighting over glyphOrder would conflict).
		if Glyphs.defaults["com.hugojourdan.ColorFlow-RainbowConflictWarned"]:
			return
		barItem = Glyphs.menu[FILE_MENU]
		submenu = barItem.submenu() if hasattr(barItem, "submenu") else None
		if submenu is None:
			return
		for item in list(submenu.itemArray()):
			if item.title() == "Rainbow FontView":
				Message(
					"The standalone Rainbow FontView plugin is still installed.\n\n"
					"Color Flow now includes Font-View grouping, so please disable or "
					"remove Rainbow FontView to avoid them conflicting.",
					title="Color Flow", OKButton=None)
				Glyphs.defaults["com.hugojourdan.ColorFlow-RainbowConflictWarned"] = True
				return

	# --- ObjC selectors (no python_method decorator: called by menu / timer) ---

	def validateMenuItem_(self, menuItem) -> bool:
		# This validates EVERY menu item targeting the plugin (Rainbow toggle,
		# settings, backfill, context-menu entries) — only the Rainbow toggle
		# carries an on/off checkmark, so branch on the action selector.
		try:
			action = str(menuItem.action()) if menuItem.action() else ""
		except Exception:
			action = ""
		font = Glyphs.font
		if action != "toggleRainbow:":
			if action == "openSettings:":
				return True  # settings popover works without a font
			return font is not None
		if font is None:
			menuItem.setState_(NSOffState)
			return False
		try:
			menuItem.setState_(NSOnState if self.fontview.is_enabled(font) else NSOffState)
		except Exception:
			menuItem.setState_(NSOffState)
		return True

	def toggleRainbow_(self, sender) -> None:
		self.Toggle_Rainbow(sender)

	def rainbowDebouncedRebuild_(self, sender) -> None:
		font = self._pendingFont or Glyphs.font
		self._pendingFont = None
		if font is None:
			return
		try:
			if self.fontview.is_enabled(font):
				self.fontview.maybe_rebuild(font)
		except Exception:
			import traceback
			print("Color Flow [Rainbow rebuild] error:\n" + traceback.format_exc())

	# --- keep our grouping order out of saved files (Cocoa save notifications) ---

	def documentDidSave_(self, notification) -> None:
		# Glyphs posts this (GSDocumentWasSavedSuccessfully) after a successful save —
		# the only save hook it offers.
		document = notification.object()
		# Re-entrancy guard: this fire is our OWN follow-up save (below), made only to
		# flush the just-written userData to disk. Don't record or re-save again.
		if getattr(self, "_resaving", False):
			self._resaving = False
			print("Color Flow: timeline persisted to disk (follow-up save).")
			return
		print("Color Flow [save]: GSDocumentWasSavedSuccessfully fired.")
		font = None
		try:
			font = self._font_from_document(document)
		except Exception:
			font = None
		if font is None:
			try:
				font = Glyphs.font
			except Exception:
				font = None
		# Record the per-save timeline snapshot into userData. Glyphs has no pre-save
		# hook, so this runs just AFTER the write; if it records something new we then do
		# one follow-up save (below) to persist it on disk in this same user action.
		recorded = False
		try:
			recorded = bool(self._record_dashboard_history(font))
		except Exception:
			import traceback
			print("Color Flow [history] error:\n" + traceback.format_exc())
		# Font-View glyphOrder restore (only relevant if a strip happened — currently
		# inert because Glyphs has no pre-save hook to strip in; kept harmless).
		try:
			if (font is not None and getattr(self, "fontview", None) is not None
					and getattr(self, "_strippedForSave", False)):
				self.fontview.restore_after_save(font)
				try:
					document.updateChangeCount_(2)  # NSChangeCleared: re-add is transient
				except Exception:
					pass
		except Exception:
			import traceback
			print("Color Flow [did-save] error:\n" + traceback.format_exc())
		self._strippedForSave = False
		# Flush the freshly-written userData to disk NOW (no "save twice" needed): mark the
		# doc dirty for the userData change and trigger one guarded follow-up save. Only
		# when a new snapshot was actually recorded AND the font has a file on disk (an
		# untitled doc would pop a Save As dialog). A 2s fallback clears the guard if the
		# follow-up save never reports back, so a future real save is never skipped.
		if recorded and document is not None and getattr(font, "filepath", None):
			try:
				document.updateChangeCount_(0)   # NSChangeDone: the userData change is unsaved
				self._resaving = True
				document.performSelector_withObject_afterDelay_("saveDocument:", None, 0.0)
				self.performSelector_withObject_afterDelay_("_clearResaving:", None, 2.0)
			except Exception:
				self._resaving = False
				import traceback
				print("Color Flow [resave] error:\n" + traceback.format_exc())

	def _clearResaving_(self, _arg) -> None:
		# Fallback: if the follow-up save's notification never arrived, don't leave the
		# guard stuck on (which would skip the next real save).
		self._resaving = False

	@objc.python_method
	def _record_dashboard_history(self, font) -> bool:
		# Accrue a per-SAVE per-glyph snapshot so the dashboard's timeline has data to
		# read, whether or not the dashboard was ever opened. Stored in the font's
		# userData (gzip+base64) so it travels with the file. No throttle: record_history
		# itself skips a save that changed no colour (content-dedup), so rapid or no-op
		# saves don't add junk while genuine colour changes are all captured. Returns True
		# when it actually wrote a new snapshot (so the caller can flush it to disk).
		if font is None:
			print("Color Flow: no font on save — nothing recorded.")
			return False
		if not getattr(font, "filepath", None):
			print("Color Flow: font has no file path yet — timeline kept in memory, "
				"persists once the file is saved to disk.")
		import colorflow_dashboard
		# Storage rule: git-tracked fonts keep their history in git commits, so we don't
		# *also* accrue userData snapshots (that would double-store the same timeline).
		# The report merges the frozen pre-git userData past with git going forward.
		# Untracked fonts (no repo, or not yet committed) keep writing userData so the
		# timeline still accrues for users who don't use git.
		if colorflow_dashboard.is_git_tracked(font):
			print("Color Flow: font is git-tracked — timeline reads from git, "
				"skipping userData snapshot.")
			return False
		key = colorflow_dashboard.TIMELINE_USERDATA_KEY
		# Compare the encoded userData string before/after: it changes iff a new entry was
		# written (count alone is unreliable — capping can drop an old day as one is added).
		before = colorflow_dashboard._read_user_data(font, key)
		snapshot = colorflow_dashboard.build_master_glyph_colors(font)
		colorflow_dashboard.record_history(font, snapshot, datetime.now())
		recorded = colorflow_dashboard._read_user_data(font, key) != before
		try:
			saves = len(colorflow_dashboard.load_history(font))
			save_word = "save" if saves == 1 else "saves"
			if recorded:
				print(f"Color Flow: timeline snapshot recorded to userData "
					f"({saves} {save_word} logged; flushing to disk).")
			else:
				print(f"Color Flow: no colour change since last save — timeline unchanged "
					f"({saves} {save_word} logged).")
		except Exception:
			pass
		return recorded

	@objc.python_method
	def _font_from_document(self, document) -> Any:
		if document is None:
			return None
		font = getattr(document, "font", None)
		if callable(font):
			try:
				font = document.font()
			except Exception:
				font = None
		if font is None and hasattr(document, "glyphs") and hasattr(document, "userData"):
			font = document  # the notification object is already a GSFont
		return font

	# --- python callbacks (action menu + the ObjC toggle target) ---

	@objc.python_method
	def Toggle_Rainbow(self, sender) -> None:
		font = Glyphs.font
		if font is None:
			return
		try:
			self.fontview.toggle(font)
		except Exception:
			import traceback
			print("Color Flow [Rainbow toggle] error:\n" + traceback.format_exc())

	# ------------------------------------------------------------------ inline label rename

	@objc.python_method
	def _ns_button(self, check) -> Any:
		if hasattr(check, "getNSButton"):
			return check.getNSButton()
		return check._nsObject

	@objc.python_method
	def _strip_focus_rings(self, view) -> None:
		# Remove the blue AppKit focus ring (halo) from a view and every descendant.
		# NSFocusRingTypeNone == 1.
		try:
			view.setFocusRingType_(1)
		except Exception:
			pass
		try:
			subviews = view.subviews()
		except Exception:
			return
		for sub in subviews:
			self._strip_focus_rings(sub)

	########################################################################################################
	#																									   #
	#	DATA + UI 																				           #
	#																									   #
	########################################################################################################
	#																									   #
	#																									   #

	# ------------------------------------------------------------------ derived data (tempData)

	# --- mode: contiguous "step" (default, nothing saved in the file) vs "free"
	# (independent checkboxes, stored per-layer in userData). ---
	@objc.python_method
	def _free_mode(self) -> bool:
		return bool(Glyphs.defaults["com.hugojourdan.ColorFlow-FreeMode"])

	# --- opt-in "count exporting glyphs only" (default OFF): non-exporting glyphs
	# drop out of the per-master counts AND the bar denominators. ---
	@objc.python_method
	def _exporting_only(self) -> bool:
		return bool(Glyphs.defaults[_EXPORTING_ONLY_KEY])

	# The exclusion set the counting threads through colornames: the names of the
	# font's non-exporting glyphs when the pref is ON, else empty (all count).
	@objc.python_method
	def _excluded_glyph_names(self) -> set:
		if not self._exporting_only():
			return set()
		try:
			return colornames.non_exporting_names(self.font.glyphs)
		except Exception:
			return set()

	# A layer's checkbox state, derived from its colour. Free mode is single-
	# select (only the matching colour); step mode is the contiguous run.
	@objc.python_method
	def _layer_state(self, layer, order) -> dict:
		if self._free_mode():
			return colornames.exclusive_state_for_color(layer.color, order)
		return colornames.checked_state_for_color(layer.color, order)

	# Per-step counts for a master, derived from native layer colours. Nothing
	# Color Flow tracks is saved in the .glyphs file, in either mode. In
	# exporting-only mode the non-exporting glyphs' colours are excluded before
	# counting (the exclusion set is threaded through colornames).
	@objc.python_method
	def _derive_counts(self, masterId) -> dict:
		order = list(self.meaning.keys())
		named_colors = []
		for glyph in self.font.glyphs:
			layer = glyph.layers[masterId]
			named_colors.append((glyph.name, layer.color if layer is not None else None))
		colors = colornames.exclude_named_colors(named_colors, self._excluded_glyph_names())
		if self._free_mode():
			return colornames.single_counts_from_colors(colors, order)
		return colornames.counts_from_colors(colors, order)

	# Cache signature: the key includes the exporting-only pref, so counts derived
	# under one mode can never be repainted after toggling into the other.
	@objc.python_method
	def _counts_cache_key(self, masterId) -> str:
		return _SHORTCUT_COUNTS_KEY + masterId + ("-exporting" if self._exporting_only() else "")

	@objc.python_method
	def _counts(self, masterId) -> dict:
		key = self._counts_cache_key(masterId)
		counts = self.font.tempData[key]
		if not hasattr(counts, "keys"):
			counts = self._derive_counts(masterId)
			self.font.tempData[key] = counts
		return counts

	@objc.python_method
	def _invalidate_counts(self, masterId) -> None:
		# Drop BOTH variants (plain + exporting-only) — see _counts_cache_key.
		self.font.tempData[_SHORTCUT_COUNTS_KEY + masterId] = None
		self.font.tempData[_SHORTCUT_COUNTS_KEY + masterId + "-exporting"] = None

	# Remember which colour a freshly built row checkbox belongs to (the widgets
	# rebuild on each refresh). Row interaction (open-tab click + drag-reorder)
	# lives on a full-width transparent overlay added after the count, so the
	# WHOLE row responds — see _attach_row_overlay.
	@objc.python_method
	def _register_row_checkbox(self, checkbox, color) -> None:
		self._rowChecks[color] = checkbox

	# A transparent, full-width overlay laid over each row (above the bar, label
	# and count) so a click anywhere on the row toggles focus on that step and a
	# drag reorders it. The label/count underneath stay visible.
	@objc.python_method
	def _attach_row_overlay(self, color, yPos) -> None:
		overlay = Group((0, yPos - self.shift - 1, self.width, 19))
		setattr(self.paletteView.frame, str(color) + "click", overlay)
		self._rowOverlays[color] = overlay
		view = overlay._nsObject
		try:
			click = NSClickGestureRecognizer.alloc().initWithTarget_action_(self, "rowClicked:")
			click.setNumberOfClicksRequired_(1)
			view.addGestureRecognizer_(click)
		except Exception:
			pass
		try:
			pan = NSPanGestureRecognizer.alloc().initWithTarget_action_(self, "colorDragged:")
			view.addGestureRecognizer_(pan)
		except Exception:
			pass
		try:
			area = AppKit.NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
				view.bounds(),
				AppKit.NSTrackingCursorUpdate | AppKit.NSTrackingActiveInKeyWindow,
				self, None)
			view.addTrackingArea_(area)
		except Exception:
			pass

	# Resolve which colour-row a gesture recognizer is attached to (its view is
	# the row's checkbox NSButton).
	@objc.python_method
	def _color_for_recognizer(self, recognizer) -> str | None:
		view = recognizer.view()
		for color, overlay in getattr(self, "_rowOverlays", {}).items():
			try:
				if overlay._nsObject == view:
					return color
			except Exception:
				pass
		for color, checkbox in getattr(self, "_rowChecks", {}).items():
			if self._ns_button(checkbox) == view:
				return color
		return None

	# Drag a row to reorder the colours: the dragged colour is dropped onto the
	# row currently under the pointer (cursor-position targeting, so it always
	# follows the mouse regardless of the view's coordinate flip). A grabbing-hand
	# cursor shows while dragging. Reorder + persist on release.
	def colorDragged_(self, recognizer) -> None:
		try:
			state = recognizer.state()
			if state == NSGestureRecognizerStateBegan:
				self._push_drag_cursor()
				self._begin_drag_feedback(self._color_for_recognizer(recognizer))
				return
			if state == NSGestureRecognizerStateChanged:
				self._lastDragTime = datetime.now()  # suppress the end-of-drag toggle
				try:
					NSCursor.closedHandCursor().set()
				except Exception:
					pass
				color = self._color_for_recognizer(recognizer)
				dst = self._drop_index(recognizer)
				if color is not None and dst is not None:
					self._update_drop_line(color, dst)
				return
			# Ended / Cancelled / Failed (state >= Ended): restore cursor + clear feedback.
			self._pop_drag_cursor()
			self._clear_drag_feedback()
			if state != NSGestureRecognizerStateEnded:
				return
			color = self._color_for_recognizer(recognizer)
			if color is None:
				return
			dst = self._drop_index(recognizer)
			if dst is not None:
				self._reorder_color_to(color, dst)
		except Exception:
			import traceback
			self._pop_drag_cursor()
			self._clear_drag_feedback()
			print("Color Flow [drag] error:\n" + traceback.format_exc())

	# The visible-row index under the pointer right now (flip-safe).
	@objc.python_method
	def _drop_index(self, recognizer) -> int | None:
		frameView = self.paletteView.frame.getNSView()
		point = recognizer.locationInView_(frameView)
		y = point.y
		try:
			if not frameView.isFlipped():
				y = frameView.bounds().size.height - y
		except Exception:
			pass
		return self._row_index_at_point(y)

	# Top y (flipped coords) of a visible row band, matching the colour-bar offset.
	@objc.python_method
	def _row_top(self, index) -> float | None:
		visible = list(self.meaning.keys())
		if not (0 <= index < len(visible)):
			return None
		checkbox = self._rowChecks.get(visible[index])
		if checkbox is None:
			return None
		try:
			return checkbox.getPosSize()[1] - 3
		except Exception:
			return None

	# Live drag highlight: tint the dragged row blue + show a blue insertion line.
	@objc.python_method
	def _begin_drag_feedback(self, color) -> None:
		self._clear_drag_feedback()
		if color is None:
			return
		visible = list(self.meaning.keys())
		key = str(color)
		if key not in visible:
			return
		top = self._row_top(visible.index(key))
		if top is None:
			return
		tint = AppKit.NSColor.colorWithRed_green_blue_alpha_(0.16, 0.5, 0.96, 0.22)
		line = AppKit.NSColor.colorWithRed_green_blue_alpha_(0.13, 0.45, 0.96, 1.0)
		self.paletteView.frame.dragHighlight = Box((0, top, self.width, 19), fillColor=tint, cornerRadius=0, borderWidth=0)
		self.paletteView.frame.dropLine = Box((0, top, self.width, 2), fillColor=line, cornerRadius=0, borderWidth=0)

	# Move the insertion line to the slot the dragged colour would drop into.
	@objc.python_method
	def _update_drop_line(self, color, dst) -> None:
		if not hasattr(self.paletteView.frame, "dropLine"):
			return
		visible = list(self.meaning.keys())
		key = str(color)
		if key not in visible:
			return
		src = visible.index(key)
		top = self._row_top(dst)
		if top is None:
			return
		lineY = top + 19 if dst > src else top
		try:
			self.paletteView.frame.dropLine.setPosSize((0, lineY, self.width, 2))
		except Exception:
			pass

	@objc.python_method
	def _clear_drag_feedback(self) -> None:
		for attr in ("dragHighlight", "dropLine"):
			if hasattr(self.paletteView.frame, attr):
				try:
					delattr(self.paletteView.frame, attr)
				except Exception:
					pass

	# Grabbing-hand cursor while dragging (push once, pop once — flag-balanced).
	@objc.python_method
	def _push_drag_cursor(self) -> None:
		if getattr(self, "_cursorPushed", False):
			return
		try:
			NSCursor.closedHandCursor().push()
			self._cursorPushed = True
		except Exception:
			pass

	@objc.python_method
	def _pop_drag_cursor(self) -> None:
		if not getattr(self, "_cursorPushed", False):
			return
		try:
			NSCursor.pop()
		except Exception:
			pass
		self._cursorPushed = False

	# Which visible row sits under a y-coordinate (in the frame view's flipped
	# coords, top-down): the row whose checkbox vertical centre is nearest.
	@objc.python_method
	def _row_index_at_point(self, y) -> int | None:
		visible = list(self.meaning.keys())
		bestIndex = None
		bestDist = None
		for index, key in enumerate(visible):
			checkbox = self._rowChecks.get(key)
			if checkbox is None:
				continue
			try:
				_, top, _, height = checkbox.getPosSize()
			except Exception:
				continue
			center = top + (height / 2.0)
			dist = abs(center - y)
			if bestDist is None or dist < bestDist:
				bestIndex, bestDist = index, dist
		return bestIndex

	# Move `color` to absolute position `dst` among the visible colours; persist.
	@objc.python_method
	def _reorder_color_to(self, color, dst) -> None:
		visible = list(self.meaning.keys())
		key = str(color)
		if key not in visible:
			return
		src = visible.index(key)
		dst = max(0, min(len(visible) - 1, dst))
		if dst == src:
			return
		visible.insert(dst, visible.pop(src))
		self._write_order(visible)
		self.reload_after_settings()

	# Write colorNames.txt with the visible colours in `new_order`, preserving
	# each colour's label + the hidden colours.
	@objc.python_method
	def _write_order(self, new_order) -> None:
		fontDir = None
		font = Glyphs.font
		if font is not None and font.filepath:
			fontDir = os.path.dirname(font.filepath)
		path = colornames.resolve_key_file(fontDir)
		text = colornames.read_color_names(path) or colornames.DEFAULT_COLOR_NAMES
		rows, noneLabel = colornames.parse_settings(text)
		info = {index: (label, visible) for index, label, visible in rows}
		newRows = []
		seen = set()
		for key in new_order:
			index = int(key)
			label = info.get(index, ("", True))[0]
			newRows.append((index, label, True))
			seen.add(index)
		for index, label, visible in rows:
			if index not in seen:
				newRows.append((index, label, visible))
		colornames.write_color_names(path, colornames.render_settings(newRows, noneLabel))

	# Update Palette UI (original look; checkbox state + counts derived from colour).
	@objc.python_method
	def Update_Plugin_UI(self) -> None:
		try:
			for attr in getattr(self, "_metaAttrs", []) + getattr(self, "_bodyAttrs", []):
				if hasattr(self.paletteView.frame, attr):
					delattr(self.paletteView.frame, attr)
			self._metaAttrs = []
			self._bodyAttrs = []
			if not self.font or not self.meaning or getattr(self, "_eye_mode", False):
				return
			self._rowChecks = {}
			self._rowOverlays = {}
			yPos = 13
			masterId = self.font.selectedFontMaster.id
			counts = self._counts(masterId)
			# Exporting-only mode shrinks the bar denominator with the counts, so
			# a fully-finished exporting set still reads as a full bar.
			glyphCount = len(self.font.glyphs) - len(self._excluded_glyph_names())
			order = list(self.meaning.keys())

			selectedLayers = self.font.selectedLayers or []
			selStates = [self._layer_state(layer, order) for layer in selectedLayers]
			firstColor = selectedLayers[0].color if selectedLayers else None

			for color, meaning in self.meaning.items():
				focusColor = getattr(self, "_focusColor", None)
				focused = focusColor is not None
				isFocusRow = focused and str(color) == str(focusColor)
				rowAlpha = 1.0 if (not focused or isFocusRow) else 0.28
				for suffix in ("", "box", "count", "hl", "focus", "click"):
					attr = str(color) + suffix
					if hasattr(self.paletteView.frame, attr):
						delattr(self.paletteView.frame, attr)
				if not meaning:
					continue
				count = counts[color] if color in counts else 0
				barWidth = (self.barWidth / glyphCount * count) if glyphCount else 0

				if selectedLayers:
					check = all(state.get(color, False) for state in selStates)
					if check:
						rgb = self.colorKeys[str(color)]
						setattr(self.paletteView.frame, str(color)+"hl", Box((0, yPos-self.shift-1, self.width, 19), fillColor=AppKit.NSColor.colorWithRed_green_blue_alpha_(rgb[0], rgb[1], rgb[2], 0.16), cornerRadius=0, borderWidth=0))
					if barWidth:
						if check and firstColor == int(color):
							fill = AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(color)])
						else:
							fill = AppKit.NSColor.colorWithRed_green_blue_alpha_(0, 0, 0, 0.06)
						setattr(self.paletteView.frame, str(color)+"box", Box((self.xPos, yPos-self.shift-1, barWidth+0.01, 19), fillColor=fill, cornerRadius=0, borderWidth=0))
					checkbox = TextBox((12, yPos-self.shift+2, -10, 20), meaning, sizeStyle='small')
					setattr(self.paletteView.frame, str(color), checkbox)
					try:
						_tv = checkbox._nsObject
						_tc = _tv.textColor() or AppKit.NSColor.labelColor()
						_tv.setTextColor_(_tc.colorWithAlphaComponent_(rowAlpha))
					except Exception:
						pass
					self._register_row_checkbox(checkbox, color)
					self._make_count(color, count, yPos)
					self._attach_row_overlay(color, yPos)
					yPos += 19
				else:
					if barWidth:
						_rgba = self.colorKeys[str(color)]
						fill = AppKit.NSColor.colorWithRed_green_blue_alpha_(_rgba[0], _rgba[1], _rgba[2], _rgba[3] * rowAlpha)
						setattr(self.paletteView.frame, str(color)+"box", Box((self.xPos, yPos-self.shift-1, barWidth+0.01, 19), fillColor=fill, cornerRadius=0, borderWidth=0))
					checkbox = TextBox((12, yPos-self.shift+2, -10, 20), meaning, sizeStyle='small')
					setattr(self.paletteView.frame, str(color), checkbox)
					try:
						_tv = checkbox._nsObject
						_tc = _tv.textColor() or AppKit.NSColor.labelColor()
						_tv.setTextColor_(_tc.colorWithAlphaComponent_(rowAlpha))
					except Exception:
						pass
					self._register_row_checkbox(checkbox, color)
					self._make_count(color, count, yPos)
					self._attach_row_overlay(color, yPos)
					yPos += 19
			self._countBoxes = {}
			for reviewColor in list(self._rowChecks.keys()):
				countBox = getattr(self.paletteView.frame, str(reviewColor)+"count", None)
				if countBox is None:
					continue
				self._countBoxes[reviewColor] = countBox
				try:
					recognizer = NSClickGestureRecognizer.alloc().initWithTarget_action_(self, "countClicked:")
					recognizer.setNumberOfClicksRequired_(1)
					view = self._ns_button(countBox)
					view.addGestureRecognizer_(recognizer)
					area = AppKit.NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
						view.bounds(),
						AppKit.NSTrackingCursorUpdate | AppKit.NSTrackingActiveInKeyWindow | AppKit.NSTrackingMouseEnteredAndExited,
						self, None)
					view.addTrackingArea_(area)
				except Exception:
					pass
			self._update_title_bar()
		except Exception:
			import traceback
			print("Color Flow [Update_Plugin_UI] error:\n" + traceback.format_exc())

	# Right-click “Set workflow step” on the Font/Edit-View selection (#6).
	# The callback signature for a palette is not firmly documented, so the handler
	# finds the NSMenu among whatever args Glyphs passes and is fully guarded.
	@objc.python_method
	def contextMenuHandler(self, *args) -> None:
		try:
			if not self.meaning:
				return
			menu = None
			for candidate in args:
				if candidate is not None and hasattr(candidate, "addItem_"):
					menu = candidate
					break
			if menu is None:
				return
			submenu = AppKit.NSMenu.alloc().initWithTitle_("Color Flow")
			for color, label in self.meaning.items():
				if not label:
					continue
				item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(label, "setStepFromMenu:", "")
				item.setTarget_(self)
				item.setRepresentedObject_(str(color))
				submenu.addItem_(item)
			submenu.addItem_(NSMenuItem.separatorItem())
			clearItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Clear colour", "setStepFromMenu:", "")
			clearItem.setTarget_(self)
			clearItem.setRepresentedObject_("none")
			submenu.addItem_(clearItem)
			parent = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Color Flow", None, "")
			parent.setSubmenu_(submenu)
			menu.addItem_(parent)
		except Exception:
			import traceback
			print("Color Flow [context menu] error:\n" + traceback.format_exc())

	def setStepFromMenu_(self, sender) -> None:
		try:
			raw = sender.representedObject()
			self._apply_step_to_selection(None if raw == "none" else int(raw))
		except Exception:
			import traceback
			print("Color Flow [set step] error:\n" + traceback.format_exc())

	@objc.python_method
	def _apply_step_to_selection(self, color) -> None:
		font = Glyphs.font
		if font is None:
			return
		layers = font.selectedLayers or []
		try:
			font.disableUpdateInterface()
		except Exception:
			pass
		try:
			for layer in layers:
				layer.color = color
		finally:
			try:
				font.enableUpdateInterface()
			except Exception:
				pass

	# Review Queue + Focus (#10, #11): single-click a row to toggle focus on
	# that step (row highlight / dimming) with no other side-effect; single-click
	# the step's count badge to focus AND open exactly its glyphs in a new Edit
	# tab to walk through them. Click again to clear focus.
	# Pointing-hand cursor while hovering a clickable count badge (#10/#11).
	def cursorUpdate_(self, event) -> None:
		try:
			AppKit.NSCursor.pointingHandCursor().set()
		except Exception:
			pass

	def rowClicked_(self, sender) -> None:
		try:
			lastDrag = getattr(self, "_lastDragTime", None)
			if lastDrag is not None and (datetime.now() - lastDrag).total_seconds() < 0.25:
				return
			color = self._color_for_recognizer(sender)
			if color is None:
				return
			# Focus/dim toggle only — opening an Edit tab is the count badge's
			# job (countClicked_), so casual row clicks don't spam new tabs.
			self._focusColor = None if getattr(self, "_focusColor", None) == color else color
			self.Update_Plugin_UI()
		except Exception:
			import traceback
			print("Color Flow [row click] error:\n" + traceback.format_exc())

	def countClicked_(self, sender) -> None:
		try:
			color = self._color_for_count(sender)
			if color is None:
				return
			self._focusColor = None if getattr(self, "_focusColor", None) == color else color
			self.Update_Plugin_UI()
			if self._focusColor is not None:
				self._open_step_tab(color)
		except Exception:
			import traceback
			print("Color Flow [review] error:\n" + traceback.format_exc())

	@objc.python_method
	def _clear_focus(self) -> None:
		# Escape (or a programmatic clear) drops focus mode and repaints. Safe to
		# call when nothing is focused — it is then a no-op repaint.
		if getattr(self, "_focusColor", None) is None:
			return
		self._focusColor = None
		try:
			self.Update_Plugin_UI()
		except Exception:
			pass

	def cancelOperation_(self, sender) -> None:
		# AppKit routes the Escape key to cancelOperation_ up the responder chain.
		self._clear_focus()

	@objc.python_method
	def _color_for_count(self, recognizer) -> str | None:
		view = recognizer.view()
		for color, box in getattr(self, "_countBoxes", {}).items():
			try:
				if self._ns_button(box) == view:
					return color
			except Exception:
				continue
		return None

	@objc.python_method
	def _glyphs_for_step(self, color, masterId, order) -> list:
		names = []
		for glyph in self.font.glyphs:
			layer = glyph.layers[masterId]
			state = self._layer_state(layer, order) if layer is not None else {}
			if state.get(color):
				names.append(glyph.name)
		return names

	@objc.python_method
	def _open_step_tab(self, color) -> None:
		font = self.font
		if font is None:
			return
		try:
			masterId = font.selectedFontMaster.id
		except Exception:
			return
		order = list(self.meaning.keys())
		names = self._glyphs_for_step(color, masterId, order)
		if not names:
			Message(f"No glyphs at \u201c{self.meaning.get(color, str(color))}\u201d.", title="Color Flow")
			return
		try:
			font.newTab("/" + "/".join(names))
		except Exception:
			import traceback
			print("Color Flow [open tab] error:\n" + traceback.format_exc())

	@objc.python_method
	def _make_count(self, color, count, yPos) -> None:
		textbox = TextBox((self.width-50, yPos+3-self.shift, -6, 20), str(count), alignment="right", sizeStyle='small')
		try:
			size = AppKit.NSFont.smallSystemFontSize()
			label = getattr(self, "_rowChecks", {}).get(color)
			if label is not None:
				size = self._ns_button(label).font().pointSize()
			size = max(8.0, size - 1.0)
			textbox.getNSTextField().setFont_(AppKit.NSFont.monospacedDigitSystemFontOfSize_weight_(size, AppKit.NSFontWeightRegular))
		except Exception:
			pass
		setattr(self.paletteView.frame, str(color)+"count", textbox)

	def headerEyeClicked_(self, sender) -> None:
		try:
			self._toggle_eye_mode(sender)
		except Exception:
			import traceback
			print("Color Flow [header eye] error:\n" + traceback.format_exc())

	@objc.python_method
	def _is_collapsed(self) -> bool:
		try:
			view = self.dialog
			if view is None or view.window() is None:
				return True
			if view.isHiddenOrHasHiddenAncestor():
				return True
			return view.visibleRect().size.height < 2.0
		except Exception:
			return False

	@objc.python_method
	def _sync_header(self) -> None:
		bar = getattr(self, "_titleBar", None)
		if bar is None:
			return
		try:
			collapsed = self._is_collapsed()
			bar.setHidden_(not collapsed)
			eye = getattr(self, "_titleEye", None)
			if eye is not None:
				eye.setHidden_(collapsed)
			gear = getattr(self, "_titleGear", None)
			if gear is not None:
				gear.setHidden_(collapsed)
		except Exception:
			pass

	# Inject a colour bar into the palette SECTION HEADER (#23). Done deferred so
	# the palette is docked first, then the whole window is searched for the title.
	# The header is kept in sync by update() -> _sync_header on every
	# UPDATEINTERFACE; we deliberately avoid a repeating NSTimer here because a
	# scheduled timer with target=self retains the instance, which would prevent
	# __del__ from ever running and leak every callback/observer on reload.
	def deferredHeaderSetup_(self, sender) -> None:
		try:
			self._inject_title_bar()
			self._update_title_bar()
		except Exception:
			import traceback
			print("Color Flow [header setup] error:\n" + traceback.format_exc())

	@objc.python_method
	def _window_root(self) -> Any:
		view = getattr(self, "dialog", None)
		top = view
		for _ in range(25):
			if view is None:
				break
			sup = view.superview()
			if sup is None:
				break
			top = sup
			view = sup
		return top

	@objc.python_method
	def _search_title(self, view, depth) -> Any:
		if view is None or depth > 12:
			return None
		try:
			if view.isKindOfClass_(AppKit.NSTextField):
				value = str(view.stringValue() or "")
				if "Color Flow" in value:
					return view
		except Exception:
			pass
		try:
			for sub in view.subviews():
				found = self._search_title(sub, depth + 1)
				if found is not None:
					return found
		except Exception:
			pass
		return None

	@objc.python_method
	def _inject_title_bar(self) -> None:
		if getattr(self, "_titleBar", None) is not None:
			return
		try:
			field = self._search_title(self._window_root(), 0)
			if field is None:
				return
			header = field.superview()
			if header is None:
				return
			bounds = header.bounds()
			btn = 14.0
			pad = 8.0
			gap = 4.0
			ctrlY = (bounds.size.height - btn) / 2.0
			gearX = bounds.size.width - pad - btn
			eyeX = gearX - gap - btn
			barWidth, barHeight = 84.0, 6.0
			barX = bounds.size.width - pad - barWidth
			barY = (bounds.size.height - barHeight) / 2.0
			bar = AppKit.NSView.alloc().initWithFrame_(((barX, barY), (barWidth, barHeight)))
			bar.setAutoresizingMask_(AppKit.NSViewMinXMargin)
			bar.setWantsLayer_(True)
			try:
				bar.layer().setCornerRadius_(3.0)
				bar.layer().setMasksToBounds_(True)
				bar.layer().setBackgroundColor_(AppKit.NSColor.colorWithRed_green_blue_alpha_(0.5, 0.5, 0.5, 0.18).CGColor())
			except Exception:
				pass
			header.addSubview_(bar)
			self._titleBar = bar
			eye = AppKit.NSButton.alloc().initWithFrame_(((eyeX, ctrlY), (btn, btn)))
			eye.setBordered_(False)
			eye.setAutoresizingMask_(AppKit.NSViewMinXMargin)
			eye.setTarget_(self)
			eye.setAction_("headerEyeClicked:")
			eye.setImageScaling_(AppKit.NSImageScaleProportionallyDown)
			try:
				eyeImg = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_("eye", None)
				if eyeImg is not None:
					eye.setImage_(eyeImg)
				else:
					eye.setTitle_("\U0001F441")
			except Exception:
				pass
			header.addSubview_(eye)
			self._titleEye = eye
			gear = AppKit.NSButton.alloc().initWithFrame_(((gearX, ctrlY), (btn, btn)))
			gear.setBordered_(False)
			gear.setAutoresizingMask_(AppKit.NSViewMinXMargin)
			gear.setTarget_(self)
			gear.setAction_("openSettings:")
			gear.setImageScaling_(AppKit.NSImageScaleProportionallyDown)
			try:
				gearImg = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_("gearshape", None)
				if gearImg is not None:
					gear.setImage_(gearImg)
				else:
					gear.setTitle_("\u2699")
			except Exception:
				pass
			header.addSubview_(gear)
			self._titleGear = gear
			self._sync_header()
		except Exception:
			import traceback
			print("Color Flow [title bar] error:\n" + traceback.format_exc())

	@objc.python_method
	def _update_title_bar(self) -> None:
		bar = getattr(self, "_titleBar", None)
		if bar is None or not self.font or not self.meaning:
			return
		try:
			masterId = self.font.selectedFontMaster.id
			order = list(self.meaning.keys())
			excluded = self._excluded_glyph_names()
			glyphCount = len(self.font.glyphs) - len(excluded)
			if not glyphCount:
				return
			for sub in list(bar.subviews()):
				sub.removeFromSuperview()
			named_colors = []
			for glyph in self.font.glyphs:
				layer = glyph.layers[masterId]
				named_colors.append((glyph.name, layer.color if layer is not None else None))
			colors = colornames.exclude_named_colors(named_colors, excluded)
			exclusive = colornames.single_counts_from_colors(colors, order)
			width = bar.bounds().size.width
			height = bar.bounds().size.height
			xPos = 0.0
			for key in order:
				count = exclusive.get(key, 0)
				if not count:
					continue
				segWidth = width / glyphCount * count
				rgb = self.colorKeys.get(str(key), (0.5, 0.5, 0.5, 0.5))
				seg = AppKit.NSView.alloc().initWithFrame_(((xPos, 0.0), (segWidth, height)))
				seg.setWantsLayer_(True)
				try:
					seg.layer().setBackgroundColor_(AppKit.NSColor.colorWithRed_green_blue_alpha_(rgb[0], rgb[1], rgb[2], 0.95).CGColor())
				except Exception:
					pass
				bar.addSubview_(seg)
				xPos += segWidth
		except Exception:
			pass

	# UPDATEINTERFACE handler: cheap dirty-check on selection + layer colours.
	@objc.python_method
	def update(self, sender) -> None:
		if self._windowController:
			self.font = self._windowController.documentFont()
		if not self.font:
			return
		try:
			self._sync_header()
		except Exception:
			pass

		try:
			grouping = getattr(self, "fontview", None)
			if grouping is not None and grouping.is_enabled(self.font) and grouping.is_dirty(self.font):
				self._pendingFont = self.font
				NSObject.cancelPreviousPerformRequestsWithTarget_selector_object_(self, "rainbowDebouncedRebuild:", None)
				self.performSelector_withObject_afterDelay_("rainbowDebouncedRebuild:", None, 0.15)
		except Exception:
			pass

		try:
			masterId = self.font.selectedFontMaster.id
		except Exception:
			return
		if not masterId:
			return

		selectedLayers = self.font.selectedLayers or []
		signature = (masterId, tuple(
			((layer.parent.name if layer.parent is not None else ""), layer.color)
			for layer in selectedLayers))
		if signature == getattr(self, "_lastSignature", None):
			return
		self._lastSignature = signature
		# A layer colour changed (or selection moved) — the cached per-step counts
		# are derived from layer colours, so drop them and let Update_Plugin_UI
		# recompute. (Nothing else invalidates them now the palette is display-only.)
		self._invalidate_counts(masterId)
		self.Update_Plugin_UI()

	########################################################################################################
	#																									   #
	#	EXTRA FEATURES																					   #
	#																									   #
	########################################################################################################
	#																									   #
	#																									   #

	# Open the HTML Color Font Dashboard for the current font (per-master colour
	# distribution + what changed since last run). Reloaded each time so edits to
	# dashboard.py take effect without restarting Glyphs.
	@objc.python_method
	def Open_Color_Font_Dashboard(self, sender) -> None:
		self._run_dashboard(None)

	@objc.python_method
	def _run_dashboard(self, progress=None, open_when_done: bool = True) -> Any:
		# ``progress`` (optional ``Callable[[float], None]``) is forwarded to
		# colorflow_dashboard.main so the report-sheet loader can track real build
		# progress; None when opened outside the sheet flow. Returns the written report
		# Path (or None) so the sheet flow can offer Open / Save instead of auto-opening.
		try:
			import importlib

			import colorflow_dashboard
			importlib.reload(colorflow_dashboard)
			return colorflow_dashboard.main(Glyphs.font, progress=progress, open_when_done=open_when_done)
		except Exception:
			import traceback
			print("Color Flow [dashboard] error:\n" + traceback.format_exc())
			return None

	########################################################################################################
	#																									   #
	#	SETUP COLOR MEANING																			       #
	#																									   #
	########################################################################################################
	#																									   #
	#																									   #

	# Resolve colorNames.txt (per-font dir, else the shared info dir) and parse it
	# into {"0".."11": label}. All parsing/key-file logic lives in the shared
	# colornames module so the palette and the shortcut scripts can
	# never diverge (see tools/generate_shortcuts.py).
	@objc.python_method
	def Load_Meaning(self) -> dict:
		fontDir = None
		font = Glyphs.font
		if font is not None and font.filepath:
			fontDir = os.path.dirname(font.filepath)
		return colornames.load_meaning(fontDir)


	########################################################################################################
	#																									   #
	#	DON'T MODIFY																			           #
	#																									   #
	########################################################################################################
	#																									   #

	@objc.python_method
	def __del__(self) -> None:
		# Delete callbacks when Glyphs quits, otherwise it'll crash :(
		Glyphs.removeCallback(self.update)
		# start() also registers contextMenuHandler on CONTEXTMENUCALLBACK; mirror
		# its removal here or right-click submenus stack up on every reload.
		try:
			Glyphs.removeCallback(self.contextMenuHandler)
		except Exception:
			pass
		# Remove the Rainbow Font View menu item this instance added.
		self._teardown_rainbow_menu()
		self._teardown_settings_menu()
		self._teardown_backfill_menu()
		# Remove the Cocoa save-notification observers.
		try:
			from Foundation import NSNotificationCenter
			NSNotificationCenter.defaultCenter().removeObserver_(self)
		except Exception:
			pass


	@objc.python_method
	def __file__(self) -> str:
		"""Please leave this method unchanged"""
		return __file__

	# ------------------------------------------------------------------ eye visibility mode

	# ObjC selector: a single click on a colour row in eye mode toggles whether
	# that colour is staged visible or hidden.
	def eyeRowClicked_(self, sender) -> None:
		try:
			view = sender.view()
			for key, label in getattr(self, "_eyeRowViews", {}).items():
				if label._nsObject == view:
					index = int(key)
					for row in (self._eye_rows or []):
						if row[0] == index:
							row[2] = not row[2]
							break
					self._build_eye_mode_ui()
					return
		except Exception:
			import traceback
			print("Color Flow [eye click] error:\n" + traceback.format_exc())

	# Animate the palette height via the height constraint's animator proxy (the
	# technique the Glyphs team documents for smooth palette resizing). Falls back
	# to a direct, un-animated resize if the constraint could not be created.
	@objc.python_method
	def _set_palette_height(self, height, animated=True) -> None:
		self.height = height
		constraint = getattr(self, "_heightConstraint", None)
		if constraint is None:
			try:
				self.paletteView.frame.setPosSize((0, 0, self.width, height))
				self.paletteView.setPosSize((0, 0, self.width, height + 10))
			except Exception:
				pass
			return
		if animated:
			AppKit.NSAnimationContext.beginGrouping()
			AppKit.NSAnimationContext.currentContext().setDuration_(0.22)
			constraint.animator().setConstant_(height)
			AppKit.NSAnimationContext.endGrouping()
		else:
			constraint.setConstant_(height)

	@objc.python_method
	def _toggle_eye_mode(self, sender) -> None:
		try:
			if self._eye_mode:
				self._exit_eye_mode()
			else:
				self._enter_eye_mode()
		except Exception:
			import traceback
			print("Color Flow [eye toggle] error:\n" + traceback.format_exc())

	@objc.python_method
	def _set_eye_button(self, on) -> None:
		try:
			name = "eye.slash" if on else "eye"
			image = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
			nsbutton = getattr(self, "_titleEye", None)
			if nsbutton is None:
				return
			nsbutton.setBordered_(False)
			if image is not None:
				nsbutton.setImage_(image)
				nsbutton.setTitle_("")
			else:
				nsbutton.setTitle_("🙈" if on else "👁")
		except Exception:
			pass

	@objc.python_method
	def _eye_key_path(self) -> str:
		font = Glyphs.font
		fontDir = os.path.dirname(font.filepath) if (font is not None and font.filepath) else None
		return colornames.resolve_key_file(fontDir)

	@objc.python_method
	def _enter_eye_mode(self) -> None:
		path = self._eye_key_path()
		text = colornames.read_color_names(path) or colornames.DEFAULT_COLOR_NAMES
		rows, none_label = colornames.parse_settings(text)
		self._eye_rows = [[index, label, visible] for index, label, visible in rows]
		self._eye_none = none_label
		self._eye_mode = True
		self._set_eye_button(True)
		self.height = 19 * len(self._eye_rows) + 4
		try:
			self._set_palette_height(self.height, animated=True)
		except Exception:
			pass
		self._build_eye_mode_ui()

	@objc.python_method
	def _exit_eye_mode(self) -> None:
		self._eye_mode = False
		self._set_eye_button(False)
		rows = [(index, label, visible) for index, label, visible in (self._eye_rows or [])]
		if rows:
			path = self._eye_key_path()
			colornames.write_color_names(path, colornames.render_settings(rows, self._eye_none))
		self._teardown_eye_rows()
		self.reload_after_settings()

	@objc.python_method
	def _teardown_eye_rows(self) -> None:
		for index in range(12):
			for suffix in ("eye", "eyeTag", "eyeLine"):
				attr = str(index) + suffix
				if hasattr(self.paletteView.frame, attr):
					delattr(self.paletteView.frame, attr)
		self._eyeRowViews = {}

	# Render every colour (visible + hidden) as a click-to-toggle row; hidden rows
	# are dimmed. A 1-click gesture per label flips its staged visibility.
	@objc.python_method
	def _build_eye_mode_ui(self) -> None:
		for index in range(12):
			for suffix in ("", "box", "count", "hl", "colorTag", "line", "eye", "eyeTag", "eyeLine"):
				attr = str(index) + suffix
				if hasattr(self.paletteView.frame, attr):
					delattr(self.paletteView.frame, attr)
		self._eyeRowViews = {}
		yPos = 13
		for index, label, visible in (self._eye_rows or []):
			key = str(index)
			rgb = self.colorKeys.get(key, (0.5, 0.5, 0.5, 0.5))
			alpha = 0.5 if visible else 0.12
			setattr(self.paletteView.frame, key+"eyeTag", Box((0, yPos-self.shift-1, 6, 19), fillColor=AppKit.NSColor.colorWithRed_green_blue_alpha_(rgb[0], rgb[1], rgb[2], alpha), cornerRadius=0, borderWidth=0))
			setattr(self.paletteView.frame, key+"eyeLine", HorizontalLine((0, yPos-self.shift-1, 0, 1)))
			shown = label or colornames.DEFAULT_LABELS.get(index, key)
			textbox = TextBox((12, yPos-self.shift+2, -10, 20), shown, sizeStyle='small')
			setattr(self.paletteView.frame, key+"eye", textbox)
			try:
				field = textbox.getNSTextField()
				field.setTextColor_(AppKit.NSColor.labelColor() if visible else AppKit.NSColor.tertiaryLabelColor())
			except Exception:
				pass
			self._eyeRowViews[key] = textbox
			try:
				recognizer = NSClickGestureRecognizer.alloc().initWithTarget_action_(self, "eyeRowClicked:")
				recognizer.setNumberOfClicksRequired_(1)
				textbox._nsObject.addGestureRecognizer_(recognizer)
			except Exception:
				pass
			yPos += 19

