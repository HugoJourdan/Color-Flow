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
from datetime import datetime
from typing import Any

import AppKit
import colorflow_filters
import colorflow_profile

# Shared, GlyphsApp-free colorNames logic (also embedded into the shortcut
# scripts by tools/generate_shortcuts.py). Glyphs puts this bundle's Resources/
# dir on sys.path, so a plain absolute import works.
import colornames

# Font-View colour grouping engine (the merged Rainbow FontView half).
import fontview
import labelcolors
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
		self._colors = [rgba_colors[i] for i in self._SPECTRUM if i < len(rgba_colors)]
		if not self._colors:
			self._colors = list(rgba_colors)
		self._value = 0.0    # displayed fraction (eased toward _target)
		self._target = 0.0   # latest real-progress milestone (monotonic, never decreases)
		self.start()

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
		bar_h = 16.0
		bar_y = height - bar_h
		radius = bar_h / 2.0
		bar_rect = AppKit.NSMakeRect(0.0, bar_y, width, bar_h)
		track = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(bar_rect, radius, radius)
		AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(0.137, 0.149, 0.180, 1.0).set()
		track.fill()
		if colors and prog > 0.0:
			context = AppKit.NSGraphicsContext.currentContext()
			context.saveGraphicsState()
			track.addClip()
			# Smooth blended rainbow across the FULL bar width — soft hue transitions
			# like the favicon's blurred ring, not hard segment seams — but revealed
			# only up to the filled fraction, so the colours stay anchored as it fills.
			filled = prog * width
			AppKit.NSBezierPath.bezierPathWithRect_(
				AppKit.NSMakeRect(0.0, bar_y, filled, bar_h)).addClip()
			nscolors = [
				AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(rgba[0], rgba[1], rgba[2], 1.0)
				for rgba in colors
			]
			blend = AppKit.NSGradient.alloc().initWithColors_(nscolors) if len(nscolors) >= 2 else None
			if blend is not None:
				blend.drawInRect_angle_(bar_rect, 0.0)
			else:
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

		try:
			if not Glyphs.defaults["com.hugojourdan.ColorFlow-FirstRunDone"]:
				Glyphs.defaults["com.hugojourdan.ColorFlow-FirstRunDone"] = True
				Message("Color Flow tracks glyph progress by colour. Open the action "
					"menu and pick a starter workflow to begin.", title="Welcome to Color Flow")
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
			self._rainbow_conflict_check()
		except Exception:
			import traceback
			print("Color Flow [Rainbow setup] error:\n" + traceback.format_exc())
		try:
			self.performSelector_withObject_afterDelay_("deferredHeaderSetup:", None, 2.0)
		except Exception:
			pass

		# Keep our grouping glyphOrder OUT of the saved .glyphs file: strip it
		# just before each save, restore it after. Glyphs has no DOCUMENTWILLSAVE
		# callback, so observe Cocoa's NSDocument save notifications.
		try:
			from Foundation import NSNotificationCenter
			center = NSNotificationCenter.defaultCenter()
			center.addObserver_selector_name_object_(self, "documentWillSave:", "NSDocumentWillSaveNotification", None)
			center.addObserver_selector_name_object_(self, "documentDidSave:", "NSDocumentDidSaveNotification", None)
		except Exception:
			pass


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
			button = self.dialog
			if sender is not None:
				if hasattr(sender, "_nsObject"):
					try:
						button = self._ns_button(sender)
					except Exception:
						button = self.dialog
				elif hasattr(sender, "superview"):
					button = sender
			self._popover = Popover((220, 500), parentView=button,
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
				settingsText = colornames.read_color_names(colornames.get_key_file(self._font_dir(Glyphs.font))) or colornames.DEFAULT_COLOR_NAMES
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
			self._starterFiles = self._starter_files()
			_starterTitles = ["Starter workflow…"] + [
				os.path.splitext(os.path.basename(path))[0] for path in self._starterFiles
			]
			starterY = reportY + 8 + 22 + 8
			popover.starter = PopUpButton((12, starterY, -40, 22), _starterTitles,
				callback=self._starter_selected, sizeStyle='small')
			popover.legend = Button((-32, starterY, 20, 22), "?",
				callback=self._open_legend, sizeStyle='small')
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
			text = colornames.read_color_names(path) or colornames.DEFAULT_COLOR_NAMES
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
			colornames.write_color_names(path, colornames.render_settings(newRows, noneLabel))
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
	def _starter_dir(self) -> str:
		# Bundled presets live beside this module, mirroring how report-loading.gif
		# is resolved (os.path.dirname(__file__)).
		return os.path.join(os.path.dirname(__file__), "StarterProfiles")

	@objc.python_method
	def _starter_files(self) -> list:
		try:
			directory = self._starter_dir()
			return sorted(
				os.path.join(directory, name)
				for name in os.listdir(directory)
				if name.endswith(".colorflow")
			)
		except OSError:
			return []

	@objc.python_method
	def _apply_starter_profile(self, path) -> None:
		# Same flow as _import_profile, but the source is a bundled file.
		try:
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
			print("Color Flow [starter profile] error:\n" + traceback.format_exc())

	@objc.python_method
	def _starter_selected(self, sender) -> None:
		# Index 0 is the "Starter workflow…" placeholder; real items start at 1.
		try:
			index = sender.get()
		except Exception:
			return
		files = getattr(self, "_starterFiles", [])
		if index <= 0 or index > len(files):
			return
		self._apply_starter_profile(files[index - 1])

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
			rect = AppKit.NSMakeRect(0, 0, 300, 104)
			panel = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
				rect, AppKit.NSWindowStyleMaskTitled, AppKit.NSBackingStoreBuffered, False)
			panel.setTitle_("Color Flow")
			content = panel.contentView()
			label = AppKit.NSTextField.labelWithString_("Generating Color Flow report\u2026")
			label.setFrame_(AppKit.NSMakeRect(20, 60, 260, 18))
			content.addSubview_(label)
			loader = _ColorFlowLoaderBar.alloc().initWithFrame_(AppKit.NSMakeRect(20, 22, 260, 34))
			loader.configure(labelcolors.read_label_colors())
			content.addSubview_(loader)
			self._reportLoader = loader
			self._reportPanel = panel
			parent.beginSheet_completionHandler_(panel, None)
			# Let the sheet paint once, then build on the next run-loop hop. The build
			# drives the bar with REAL progress (set_progress + run-loop pumping), so no
			# long pre-roll is needed — the bar tracks the actual work as it happens.
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

		try:
			self._run_dashboard(_on_progress)
		finally:
			if loader is not None:
				try:
					loader.set_progress(1.0)
				except Exception:
					pass
			# Build is done and the main thread is free again: let the bar visibly
			# reach 100% (a few timer ticks) before the sheet closes.
			self.performSelector_withObject_afterDelay_("dismissReportSheet:", None, 0.3)

	def dismissReportSheet_(self, sender) -> None:
		self._dismiss_report_sheet()

	@objc.python_method
	def _dismiss_report_sheet(self) -> None:
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
		font = Glyphs.font
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

	def documentWillSave_(self, notification) -> None:
		self._strippedForSave = False
		try:
			font = self._font_from_document(notification.object())
			if font is not None and getattr(self, "fontview", None) is not None:
				self._strippedForSave = bool(self.fontview.strip_for_save(font))
		except Exception:
			import traceback
			print("Color Flow [will-save] error:\n" + traceback.format_exc())

	def documentDidSave_(self, notification) -> None:
		try:
			document = notification.object()
			font = self._font_from_document(document)
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
		try:
			document = notification.object()
			self._record_dashboard_history(self._font_from_document(document))
		except Exception:
			import traceback
			print("Color Flow [history] error:\n" + traceback.format_exc())

	@objc.python_method
	def _record_dashboard_history(self, font) -> None:
		# Passively accrue a dated per-glyph snapshot on every save so the
		# dashboard's burndown / forecast / journey have a timeline to read,
		# whether or not the dashboard was ever opened. Stored in Glyphs.defaults.
		if font is None or not getattr(font, "filepath", None):
			return
		# build_master_glyph_colors scans every glyph in every master, so on a
		# large family this is a real per-save tax. record_history overwrites the
		# same day anyway, so throttle the rescan to at most once a minute per font.
		import time
		last = getattr(self, "_lastHistoryRecord", None) or {}
		key = str(font.filepath)
		now_mono = time.monotonic()
		if now_mono - last.get(key, 0.0) < 60.0:
			return
		last[key] = now_mono
		self._lastHistoryRecord = last
		import colorflow_dashboard
		snapshot = colorflow_dashboard.build_master_glyph_colors(font)
		colorflow_dashboard.record_history(font, snapshot, datetime.now())

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

	# A layer's checkbox state, derived from its colour. Free mode is single-
	# select (only the matching colour); step mode is the contiguous run.
	@objc.python_method
	def _layer_state(self, layer, order) -> dict:
		if self._free_mode():
			return colornames.exclusive_state_for_color(layer.color, order)
		return colornames.checked_state_for_color(layer.color, order)

	# Per-step counts for a master, derived from native layer colours. Nothing
	# Color Flow tracks is saved in the .glyphs file, in either mode.
	@objc.python_method
	def _derive_counts(self, masterId) -> dict:
		order = list(self.meaning.keys())
		colors = []
		for glyph in self.font.glyphs:
			layer = glyph.layers[masterId]
			colors.append(layer.color if layer is not None else None)
		if self._free_mode():
			return colornames.single_counts_from_colors(colors, order)
		return colornames.counts_from_colors(colors, order)

	@objc.python_method
	def _counts(self, masterId) -> dict:
		key = "com.hugojourdan.ColorFlow-counts-" + masterId
		counts = self.font.tempData[key]
		if not hasattr(counts, "keys"):
			counts = self._derive_counts(masterId)
			self.font.tempData[key] = counts
		return counts

	@objc.python_method
	def _invalidate_counts(self, masterId) -> None:
		self.font.tempData["com.hugojourdan.ColorFlow-counts-" + masterId] = None

	# Remember which colour a freshly built row checkbox belongs to (the widgets
	# rebuild on each refresh). Row interaction (open-tab click + drag-reorder)
	# lives on a full-width transparent overlay added after the count, so the
	# WHOLE row responds — see _attach_row_overlay.
	@objc.python_method
	def _register_row_checkbox(self, checkbox, color) -> None:
		self._rowChecks[color] = checkbox

	# A transparent, full-width overlay laid over each row (above the bar, label
	# and count) so a click anywhere on the row opens that step's tab and a drag
	# reorders it. The label/count underneath stay visible.
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
			glyphCount = len(self.font.glyphs)
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

	# Review Queue + Focus (#10, #11): single-click a step's count badge to
	# focus that step (row highlight) and open exactly its glyphs in a new Edit
	# tab to walk through them; click again to clear focus.
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
			self._focusColor = None if getattr(self, "_focusColor", None) == color else color
			self.Update_Plugin_UI()
			if self._focusColor is not None:
				self._open_step_tab(color)
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
			glyphCount = len(self.font.glyphs)
			if not glyphCount:
				return
			for sub in list(bar.subviews()):
				sub.removeFromSuperview()
			colors = []
			for glyph in self.font.glyphs:
				layer = glyph.layers[masterId]
				colors.append(layer.color if layer is not None else None)
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
	def _run_dashboard(self, progress=None) -> None:
		# ``progress`` (optional ``Callable[[float], None]``) is forwarded to
		# colorflow_dashboard.main so the report-sheet loader can track real build
		# progress; None when opened outside the sheet flow.
		try:
			import importlib

			import colorflow_dashboard
			importlib.reload(colorflow_dashboard)
			colorflow_dashboard.main(Glyphs.font, progress=progress)
		except Exception:
			import traceback
			print("Color Flow [dashboard] error:\n" + traceback.format_exc())

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

