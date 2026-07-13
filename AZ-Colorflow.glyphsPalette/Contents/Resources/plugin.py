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
import shutil
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

import AppKit

# WebKit hosts the report in a native window; if it's unavailable the report
# falls back to opening in the default browser (the pre-4.x behaviour).
try:
	import WebKit
except Exception:
	WebKit = None
import azcolorflow_filters

# Shared, GlyphsApp-free colorNames logic (also embedded into the jump
# shortcut script by tools/generate_shortcuts.py). Glyphs puts this bundle's
# Resources/ dir on sys.path, so a plain absolute import works.
import colornames

# Shared "jump to next unfinished" navigation (also embedded into the jump
# shortcut by tools/generate_shortcuts.py).
import colornav

# Pure swap-Option-color-routing decision logic (no AppKit); the swizzled
# setColorIndex: replacement below delegates its two decisions here.
import azcolorflow_routing

# Font-View colour grouping engine (the merged Rainbow FontView half).
import fontview
import labelcolors
import objc
from AppKit import (
	NSClickGestureRecognizer,
	NSMenuItem,
	NSOffState,
	NSOnState,
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

# Glyphs 4 added Window/Button/PopUpButton/ComboBox to GlyphsApp.UI with a
# title-first signature (Window(title="", frame=None, ...)). The star imports
# above let those shadow vanilla's posSize-first widgets that this palette is
# written against, so e.g. Window((w, h)) passed the size tuple as the title and
# crashed in setTitle_ (-[OC_BuiltinPythonArray length]). Pin the overlapping
# names back to vanilla; every other GlyphsApp precedence above is unchanged.
from vanilla import Window, Button, PopUpButton, ComboBox  # noqa: E402,F401,F811


_PUMP_STATE = {"last": 0.0}
_PUMP_INTERVAL = 1.0 / 60.0


def _pump_runloop() -> None:
	"""Run the run loop once so the report loader bar repaints while the
	synchronous build holds the main thread. Throttled to ~60 Hz, fully
	fail-safe. Deliberately does NOT dequeue/dispatch user input events:
	sending clicks/keys mid-build would let the user mutate the font while the
	report is being generated. runUntilDate_ alone services timers + display
	updates, which is all the loader bar needs to keep tracking real progress
	instead of beachballing."""
	import time
	now = time.monotonic()
	if now - _PUMP_STATE["last"] < _PUMP_INTERVAL:
		return
	_PUMP_STATE["last"] = now
	try:
		NSRunLoop.currentRunLoop().runUntilDate_(NSDate.distantPast())
	except Exception:
		pass


class _AZColorflowLoaderBar(AppKit.NSView):
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
		self.start()

	@objc.python_method
	def _saturate(self, rgba: tuple, factor: float) -> tuple:
		import colorsys
		hue, sat, val = colorsys.rgb_to_hsv(rgba[0], rgba[1], rgba[2])
		# Vivid AND bright: lift value toward full so each hue reads luminous (the loader
		# rainbow should glow, not sit muted).
		val = min(1.0, val * 1.15 + 0.12)
		red, green, blue = colorsys.hsv_to_rgb(hue, min(1.0, sat * factor), val)
		return (red, green, blue, rgba[3] if len(rgba) > 3 else 1.0)

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
		bar_h = 7.0    # thin bar; the % label now sits to its RIGHT (was below)
		pct_w = 46.0   # right-hand column reserved for the percentage label
		gap = 10.0     # space between the bar and the % label
		bar_w = max(10.0, width - pct_w - gap)
		bar_y = (height - bar_h) / 2.0   # vertically centre the bar in the view
		radius = bar_h / 2.0
		bar_rect = AppKit.NSMakeRect(0.0, bar_y, bar_w, bar_h)
		filled = prog * bar_w
		# The crisp rainbow gradient drawn as the bar's fill (single-colour fallback
		# when fewer than two workflow colours are available).
		nscolors = [
			AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(rgba[0], rgba[1], rgba[2], 1.0)
			for rgba in colors
		]
		blend = AppKit.NSGradient.alloc().initWithColors_(nscolors) if len(nscolors) >= 2 else None
		# Soft colour glow that HUGS the rounded bar: a shadow bloom cast by the filled pill,
		# drawn behind the track and then covered by it — not a
		# rectangular ghost peeking out behind the rounded track (the "second bar").
		if colors and prog > 0.0:
			mid = colors[len(colors) // 2]
			context = AppKit.NSGraphicsContext.currentContext()
			context.saveGraphicsState()
			glow = AppKit.NSShadow.alloc().init()
			glow.setShadowColor_(AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(mid[0], mid[1], mid[2], 0.55))
			glow.setShadowBlurRadius_(bar_h * 0.9)   # fits the now-shorter loader view without clipping
			glow.setShadowOffset_(AppKit.NSMakeSize(0.0, 0.0))
			glow.set()
			pill = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
				AppKit.NSMakeRect(0.0, bar_y, filled, bar_h), radius, radius)
			AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(mid[0], mid[1], mid[2], 1.0).set()
			pill.fill()
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
			if blend is not None:
				blend.drawInRect_angle_(bar_rect, 0.0)
			elif nscolors:
				nscolors[0].set()
				AppKit.NSRectFill(AppKit.NSMakeRect(0.0, bar_y, filled, bar_h))
			top = AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(1.0, 1.0, 1.0, 0.30)
			bottom = AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(0.0, 0.0, 0.0, 0.16)
			sheen = AppKit.NSGradient.alloc().initWithStartingColor_endingColor_(top, bottom)
			if sheen is not None:
				sheen.drawInRect_angle_(bar_rect, -90.0)
			context.restoreGraphicsState()
		paragraph = AppKit.NSMutableParagraphStyle.alloc().init()
		paragraph.setAlignment_(AppKit.NSTextAlignmentRight)
		attributes = {
			AppKit.NSForegroundColorAttributeName: AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(0.60, 0.63, 0.67, 1.0),
			AppKit.NSFontAttributeName: AppKit.NSFont.systemFontOfSize_(11.0),
			AppKit.NSParagraphStyleAttributeName: paragraph,
		}
		label = AppKit.NSAttributedString.alloc().initWithString_attributes_(
			f"{int(round(prog * 100))}%", attributes)
		# % sits to the RIGHT of the bar, vertically centred on it (was below the bar).
		text_h = label.size().height
		label.drawInRect_(AppKit.NSMakeRect(bar_w + gap, (height - text_h) / 2.0, pct_w, text_h))


########################################################################################################
#																									   #
#	NATIVE SHORTCUTS (Glyphs > Settings > Shortcuts)												   #
#																									   #
########################################################################################################

_SHORTCUT_GROUP = "AZ Colorflow"
_SHORTCUT_ID_PREFIX = "com.hugojourdan.AZColorflow."
_SHORTCUT_COUNTS_KEY = "com.hugojourdan.AZColorflow-counts-"

# Boolean default backing the "Swap Option color routing" toggle (Settings pane).
# Read at call time by the swizzled setColorIndex: replacement, so flipping it
# takes effect with no re-swizzle. Matches the com.hugojourdan.AZColorflow-* convention.
SWAP_KEY = "com.hugojourdan.AZColorflow-SwapColorRouting"
# Glyphs marked non-exporting in Glyphs are ALWAYS excluded from every
# completion percentage — palette counts/bars here, and the report's displayed
# percentages (azcolorflow_dashboard ships the same exclusion set client-side).

# Strong module-level reference to the registered target. GSShortcutItem holds its
# target WEAK and Glyphs builds one palette instance per document window, so the
# commands target this retained singleton (registered once per session) instead of
# a per-window palette instance that may be deallocated when its window closes.
_SHORTCUT_HANDLER = None

# Strong module-level reference to the singleton target for the Rainbow File-menu
# item. The shared File menu holds ONE item, and Glyphs builds one palette instance
# per document window — targeting a per-window instance means closing that window
# leaves the other windows' menu entry pointing at a deallocated target (or removes
# it entirely on that instance's __del__). So the item is installed ONCE per session
# (module-level guard) targeting this retained singleton, which acts on Glyphs.font.
_RAINBOW_MENU_HANDLER = None

# Strong module-level reference to the native report window (one per session,
# torn down on close). Module-level for the same weak-target reasons as above.
_REPORT_WINDOW = None

# WKNavigationActionPolicy raw values, with named constants when WebKit has them.
_WK_CANCEL = getattr(WebKit, "WKNavigationActionPolicyCancel", 0) if WebKit else 0
_WK_ALLOW = getattr(WebKit, "WKNavigationActionPolicyAllow", 1) if WebKit else 1
_WK_DOWNLOAD = getattr(WebKit, "WKNavigationActionPolicyDownload", 2) if WebKit else 2

# The report's own PDF export calls window.print(), which is a no-op inside a bare
# WKWebView — rebind it to a script message the native side turns into an
# NSPrintOperation. Injected at document start so it wins before any JS runs.
_REPORT_PRINT_SCRIPT = (
	"window.print = function(){"
	" try { window.webkit.messageHandlers.azcfPrint.postMessage('print'); } catch(e){} };"
)


class _AZColorflowReportWindow(AppKit.NSObject):
	"""Native window hosting the HTML report in a WKWebView.

	Keeps the report byte-identical to the browser version while feeling like part
	of Glyphs: titlebar buttons for "Save…" / "Open in Browser", glyphsapp:// heatmap
	links routed to the app, the report's CSV/JSON blob downloads landing in
	~/Downloads (revealed in Finder), and its PDF export (window.print) mapped to a
	real print panel. The WKUserContentController retains its message handler (us),
	so windowWillClose_ breaks the cycle by removing the handler and the delegates —
	the window is rebuilt fresh on the next report."""

	def showPath_(self, path) -> bool:
		self._path = str(path)
		if self._ensure_window() is None:
			return False
		try:
			file_url = AppKit.NSURL.fileURLWithPath_(self._path)
			read_access = AppKit.NSURL.fileURLWithPath_(str(Path(self._path).parent))
			self._webview.loadFileURL_allowingReadAccessToURL_(file_url, read_access)
			family = Path(self._path).stem.replace(" — AZ Colorflow", "")
			self._window.setTitle_(f"AZ Colorflow — {family}")
			self._window.makeKeyAndOrderFront_(None)
			return True
		except Exception:
			import traceback
			print("AZ Colorflow [report window] error:\n" + traceback.format_exc())
			return False

	@objc.python_method
	def _ensure_window(self):
		if getattr(self, "_window", None) is not None:
			return self._window
		try:
			config = WebKit.WKWebViewConfiguration.alloc().init()
			controller = config.userContentController()
			script = WebKit.WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(
				_REPORT_PRINT_SCRIPT, 0, True)   # 0 = WKUserScriptInjectionTimeAtDocumentStart
			controller.addUserScript_(script)
			controller.addScriptMessageHandler_name_(self, "azcfPrint")

			rect = AppKit.NSMakeRect(0, 0, 1180, 840)
			mask = (AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable
				| AppKit.NSWindowStyleMaskMiniaturizable | AppKit.NSWindowStyleMaskResizable)
			window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
				rect, mask, AppKit.NSBackingStoreBuffered, False)
			window.setReleasedWhenClosed_(False)
			window.setMinSize_(AppKit.NSMakeSize(800, 600))
			window.setFrameAutosaveName_("AZColorflowReportWindow")
			window.setDelegate_(self)

			webview = WebKit.WKWebView.alloc().initWithFrame_configuration_(rect, config)
			webview.setNavigationDelegate_(self)
			window.setContentView_(webview)

			# Titlebar accessory sizing is frame-driven: an auto-layout NSStackView with
			# nothing pinning it collapses to zero and the buttons never appear. Use a
			# plain container with explicit frames instead.
			save = AppKit.NSButton.buttonWithTitle_target_action_("Save…", self, "saveReport:")
			browser = AppKit.NSButton.buttonWithTitle_target_action_("Open in Browser", self, "openInBrowser:")
			for button in (save, browser):
				button.setControlSize_(AppKit.NSControlSizeSmall)
				button.setFont_(AppKit.NSFont.systemFontOfSize_(AppKit.NSFont.smallSystemFontSize()))
				button.setTranslatesAutoresizingMaskIntoConstraints_(True)
				button.sizeToFit()
			gap, margin, height = 8.0, 10.0, 24.0
			save_size = save.frame().size
			browser_size = browser.frame().size
			container = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(
				0, 0, save_size.width + gap + browser_size.width + margin, height))
			save.setFrameOrigin_((0.0, (height - save_size.height) / 2.0))
			browser.setFrameOrigin_((save_size.width + gap, (height - browser_size.height) / 2.0))
			container.addSubview_(save)
			container.addSubview_(browser)
			accessory = AppKit.NSTitlebarAccessoryViewController.alloc().init()
			accessory.setView_(container)
			accessory.setLayoutAttribute_(getattr(AppKit, "NSLayoutAttributeTrailing", AppKit.NSLayoutAttributeRight))
			window.addTitlebarAccessoryViewController_(accessory)

			self._window = window
			self._webview = webview
			self._controller = controller
			return window
		except Exception:
			import traceback
			print("AZ Colorflow [report window build] error:\n" + traceback.format_exc())
			self._window = None
			return None

	# ---- titlebar buttons -------------------------------------------------- #

	def saveReport_(self, sender) -> None:
		try:
			panel = AppKit.NSSavePanel.savePanel()
			panel.setNameFieldStringValue_(Path(self._path).name)
			if panel.runModal() == AppKit.NSModalResponseOK:
				shutil.copyfile(self._path, panel.URL().path())
		except Exception:
			import traceback
			print("AZ Colorflow [report save] error:\n" + traceback.format_exc())

	def openInBrowser_(self, sender) -> None:
		try:
			webbrowser.open(Path(self._path).as_uri())
		except Exception:
			import traceback
			print("AZ Colorflow [report browser] error:\n" + traceback.format_exc())

	# ---- window.print() → native print panel ------------------------------- #

	def userContentController_didReceiveScriptMessage_(self, controller, message) -> None:
		try:
			info = AppKit.NSPrintInfo.sharedPrintInfo().copy()
			operation = self._webview.printOperationWithPrintInfo_(info)
			operation.setShowsPrintPanel_(True)
			operation.setShowsProgressPanel_(True)
			operation.runOperationModalForWindow_delegate_didRunSelector_contextInfo_(
				self._window, None, None, None)
		except Exception:
			import traceback
			print("AZ Colorflow [report print] error:\n" + traceback.format_exc())

	# ---- navigation policy -------------------------------------------------- #

	def webView_decidePolicyForNavigationAction_decisionHandler_(self, webview, action, handler) -> None:
		try:
			url = action.request().URL()
			scheme = (url.scheme() or "").lower() if url is not None else ""
			if scheme == "glyphsapp":                     # heatmap deep links → Glyphs itself
				AppKit.NSWorkspace.sharedWorkspace().openURL_(url)
				handler(_WK_CANCEL)
				return
			wants_download = (action.respondsToSelector_(b"shouldPerformDownload")
				and action.shouldPerformDownload())
			if wants_download:                            # CSV/JSON export (<a download> blob)
				handler(_WK_DOWNLOAD)
				return
			if scheme in ("http", "https"):               # anything external → default browser
				AppKit.NSWorkspace.sharedWorkspace().openURL_(url)
				handler(_WK_CANCEL)
				return
			if scheme == "blob":                          # no download support (pre-11.3): don't navigate away
				handler(_WK_CANCEL)
				return
			handler(_WK_ALLOW)
		except Exception:
			handler(_WK_ALLOW)

	# ---- WKDownload → ~/Downloads, revealed in Finder ----------------------- #

	def webView_navigationAction_didBecomeDownload_(self, webview, action, download) -> None:
		download.setDelegate_(self)

	def download_decideDestinationUsingResponse_suggestedFilename_completionHandler_(
			self, download, response, filename, handler) -> None:
		try:
			downloads = Path.home() / "Downloads"
			base = downloads / (filename or "AZ Colorflow export")
			destination = base
			counter = 2
			while destination.exists():
				destination = downloads / f"{base.stem} ({counter}){base.suffix}"
				counter += 1
			self._lastDownload = str(destination)
			handler(AppKit.NSURL.fileURLWithPath_(str(destination)))
		except Exception:
			handler(None)

	def downloadDidFinish_(self, download) -> None:
		try:
			target = AppKit.NSURL.fileURLWithPath_(self._lastDownload)
			AppKit.NSWorkspace.sharedWorkspace().activateFileViewerSelectingURLs_([target])
		except Exception:
			pass

	def download_didFailWithError_resumeData_(self, download, error, data) -> None:
		print(f"AZ Colorflow [report export] download failed: {error}")

	# ---- teardown ------------------------------------------------------------ #

	def windowWillClose_(self, notification) -> None:
		# Break the WKUserContentController→handler(self)→webview retain cycle and drop
		# the module reference; the next report rebuilds the window from scratch.
		global _REPORT_WINDOW
		try:
			self._controller.removeScriptMessageHandlerForName_("azcfPrint")
		except Exception:
			pass
		try:
			self._webview.setNavigationDelegate_(None)
			self._window.setDelegate_(None)
		except Exception:
			pass
		self._window = None
		self._webview = None
		self._controller = None
		_REPORT_WINDOW = None


def _show_report_window(path) -> bool:
	"""Open the report in the native window; False = caller should fall back to the browser."""
	global _REPORT_WINDOW
	if WebKit is None:
		return False
	try:
		if _REPORT_WINDOW is None:
			_REPORT_WINDOW = _AZColorflowReportWindow.alloc().init()
		return bool(_REPORT_WINDOW.showPath_(path))
	except Exception:
		import traceback
		print("AZ Colorflow [report window] error:\n" + traceback.format_exc())
		return False

# Shared bootstrap entitlement (Gate). The native "Jump to next" shortcut fires
# the module-level handler, which has no palette instance, so the licence gate is
# consulted here. settings()/_onLicenseChanged publish the live Gate so the
# shortcut blocks (and nags once) exactly like the in-palette features.
_SHARED_ENT = None


def _shared_gate_blocked() -> bool:
	"""True when the shared licence entitlement is blocked; nags once if so."""
	ent = _SHARED_ENT
	blocked = bool(ent and getattr(ent, "blocked", False))
	if blocked:
		try:
			ent.nag()
		except Exception:
			pass
	return blocked


def _shortcut_font_dir(font) -> str | None:
	return os.path.dirname(font.filepath) if font.filepath else None


def _jump_to_next_unfinished() -> None:
	"""Open the next glyph whose layer.color is not the final visible step.

	Mirrors the generated "Jump To Next Unfinished (Color Flow)" script
	(tools/generate_shortcuts.py, JUMP_TAIL) via the shared colornav module, so
	"next" and "unfinished" mean the same thing in both halves.
	"""
	if _shared_gate_blocked():
		return
	font = Glyphs.font
	if font is None:
		Message("Open a font first.", title="AZ Colorflow")
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
		Message("All glyphs finished.", title="AZ Colorflow")
		return
	font.newTab("/" + names[index])


class AZColorflowShortcutHandler(NSObject):
	"""Long-lived target for the native shortcut command (one per session)."""

	# GSShortcutCommandProtocol: Glyphs asks right before performing the action.
	# Typed selector because the protocol method returns an ObjC BOOL, which
	# PyObjC cannot infer for a Python-defined method.
	@objc.typedSelector(objc._C_NSBOOL + b"@:" + objc._C_SEL + objc._C_ID)
	def validateShortcutCommand_editViewController_(self, action, editViewController) -> bool:
		return True

	def jumpNextShortcut_(self, sender) -> None:
		try:
			_jump_to_next_unfinished()
		except Exception:
			import traceback
			print("AZ Colorflow [jump shortcut] error:\n" + traceback.format_exc())


def _register_native_shortcuts() -> None:
	"""Register the jump command in Glyphs > Settings > Shortcuts.

	Uses GSCallbackHandler +registerShortcutCommand:group:identifier:action:
	target:character:modifierFlags: (GlyphsCore.framework, GSCallbackHandler.h).
	The command ships UNASSIGNED (character "") so users map their own key
	natively — no Scripts-folder copying. Registers once per session: Glyphs
	builds one palette instance per document window, so later windows must not
	re-register.
	"""
	global _SHORTCUT_HANDLER
	if _SHORTCUT_HANDLER is not None:
		return
	callback_handler = objc.lookUpClass("GSCallbackHandler")
	register = callback_handler.registerShortcutCommand_group_identifier_action_target_character_modifierFlags_
	target = AZColorflowShortcutHandler.alloc().init()
	# Mark registered BEFORE the call: a partial failure must not re-register
	# when the next window opens (it would only fail again).
	_SHORTCUT_HANDLER = target
	register(
		"Jump to next color glyph",
		_SHORTCUT_GROUP,
		_SHORTCUT_ID_PREFIX + "jumpNext",
		"jumpNextShortcut:",
		target,
		"",  # unassigned — the user picks a key in Settings > Shortcuts
		0,
	)


_RAINBOW_MENU_TITLE = "AZ Colorflow: Font Glyph Order"


class AZColorflowRainbowMenuHandler(NSObject):
	"""Long-lived target for the Rainbow File-menu item (one per session).

	The shared File menu holds a single item; targeting a per-window palette
	instance breaks once that window closes (dead target or removed entry for the
	other open windows). This singleton acts on ``Glyphs.font`` and owns its own
	``FontViewGrouping`` so the toggle works regardless of which window is frontmost.
	"""

	def init(self) -> Any:
		self = objc.super(AZColorflowRainbowMenuHandler, self).init()
		if self is None:
			return None
		try:
			self._fontview = fontview.FontViewGrouping()
		except Exception:
			self._fontview = None
		return self

	def validateMenuItem_(self, menuItem) -> bool:
		# Reflect the current font's grouping state as the checkmark.
		font = Glyphs.font
		if font is None or self._fontview is None:
			menuItem.setState_(NSOffState)
			return font is not None
		try:
			menuItem.setState_(NSOnState if self._fontview.is_enabled(font) else NSOffState)
		except Exception:
			menuItem.setState_(NSOffState)
		return True

	def toggleRainbow_(self, sender) -> None:
		# Gate via the shared session entitlement (same path the native shortcut uses).
		if _shared_gate_blocked():
			return
		font = Glyphs.font
		if font is None or self._fontview is None:
			return
		try:
			self._fontview.toggle(font)
		except Exception:
			import traceback
			print("AZ Colorflow [Rainbow toggle] error:\n" + traceback.format_exc())


def _install_rainbow_menu() -> None:
	"""Add the Rainbow File-menu item once per session, targeting a retained singleton.

	Glyphs builds one palette instance per document window; registering the item
	per instance means the last window wins and closing it strands the others. The
	module-level ``_RAINBOW_MENU_HANDLER`` guard ensures the item is created exactly
	once and outlives any individual window. Removes any stale copy (e.g. from a
	previous load of this module) before adding.
	"""
	global _RAINBOW_MENU_HANDLER
	if _RAINBOW_MENU_HANDLER is not None:
		return
	title = _RAINBOW_MENU_TITLE
	# Mark installed BEFORE wiring the menu: a partial failure must not let the next
	# window re-attempt (it would only fail again, and could stack a second item).
	handler = AZColorflowRainbowMenuHandler.alloc().init()
	_RAINBOW_MENU_HANDLER = handler
	menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
		title, "toggleRainbow:", "")
	menu_item.setTarget_(handler)
	bar_item = Glyphs.menu[FILE_MENU]
	# respondsToSelector_, not hasattr: hasattr on a PyObjC-bridged object scans
	# the entire ObjC selector table when the attribute is missing.
	submenu = bar_item.submenu() if bar_item.respondsToSelector_(b"submenu") else None
	if submenu is not None:
		for item in list(submenu.itemArray()):
			if item.title() == title:
				submenu.removeItem_(item)
		submenu.addItem_(menu_item)
	else:
		bar_item.append(menu_item)


########################################################################################################
#																									   #
#	SWAP OPTION COLOR ROUTING (swizzle of -[GSFontViewController setColorIndex:])				   #
#																									   #
########################################################################################################
#
# Stock Glyphs: click a swatch -> glyph colour; Option-click -> active layer colour. This fork is
# baked into the compiled -[GSFontViewController setColorIndex:], which re-reads modifierFlags
# internally, so an IMP-preserving swizzle cannot invert it (the original would just re-make the
# stock choice). We FULLY REPLACE the (small, self-contained) method body. The replacement reads the
# SWAP_KEY default at CALL TIME, so flipping the Settings toggle needs no re-swizzle. The decision
# logic lives in the pure, unit-tested azcolorflow_routing module.

# Idempotency guard: Glyphs builds one palette instance per document window; the installer must run
# its class-method replacement exactly once per app session.
_CF_ROUTING_INSTALLED = False


def _cf_setColorIndex_(self, color_index) -> None:
	"""Replacement for -[GSFontViewController setColorIndex:] implementing swap routing.

	Signed ``v@:C`` (void, self, _cmd, unsigned char) so it matches the GSLabelColors
	(uint8_t) argument — 0xFF (NoColor / reset) flows through unchanged. Fully guarded:
	any failure prints to the Macro panel and the routing is simply skipped, never crashes
	the Font View. Non-mouse callers (keyboard shortcut, programmatic) fall back to stock
	glyph routing so a held Option key during a key event can't misroute.
	"""
	try:
		event = AppKit.NSApp.currentEvent() if AppKit.NSApp is not None else None
		swap = bool(Glyphs.defaults[SWAP_KEY])
		event_type = event.type() if event is not None else None

		try:
			layers = list(self.selectedLayers() or [])
		except Exception:
			layers = []

		if event is None or not azcolorflow_routing.should_apply_swap(event_type):
			# Non-mouse / no event: stock GLYPH routing, ignore Option (safe default).
			# (The `event is None` test is redundant with should_apply_swap — a None
			# event_type already returns False — but it lets the type checker narrow
			# `event` to non-None in the else branch where modifierFlags() is read.)
			target = "glyph"
		else:
			option = bool(event.modifierFlags() & AppKit.NSEventModifierFlagOption)
			target = azcolorflow_routing.resolve_color_target(option, swap)

		# Wrap the mutation in the font's disable/enableUpdateInterface so the UI
		# updates once (mirrors stock). The accessor lives on GSFont; reach it via a
		# selected layer's glyph.parent (== the font). Best-effort: if we can't find
		# it, just mutate without the batching.
		font = None
		if layers:
			try:
				glyph = layers[0].glyph
				font = glyph.parent if glyph is not None else None
			except Exception:
				font = None

		if font is not None:
			try:
				font.disableUpdateInterface()
			except Exception:
				font = None  # don't try to re-enable something we couldn't disable
		# Coalesce the per-layer/per-glyph colorIndex assignments into ONE undo step,
		# so Cmd-Z after a multi-glyph swatch click reverts the whole batch in one go
		# (the stock IMP we replaced did its own single-step registration; this restores
		# that grouping). Best-effort + null-safe: any missing undoManager just skips
		# grouping and the mutation still applies. End the group symmetrically in finally.
		undo_manager = None
		if font is not None:
			try:
				get_undo = getattr(font, "undoManager", None)
				undo_manager = get_undo() if callable(get_undo) else None
			except Exception:
				undo_manager = None
		if undo_manager is not None:
			try:
				undo_manager.beginUndoGrouping()
				undo_manager.setActionName_("Set Color")
			except Exception:
				undo_manager = None  # don't end a group we never began
		try:
			for layer in layers:
				if target == "layer":
					layer.colorIndex = color_index
				else:
					glyph = layer.glyph
					if glyph is not None:
						glyph.colorIndex = color_index
		finally:
			if undo_manager is not None:
				try:
					undo_manager.endUndoGrouping()
				except Exception:
					pass
			if font is not None:
				try:
					font.enableUpdateInterface()
				except Exception:
					pass
	except Exception:
		import traceback
		print("AZ Colorflow [setColorIndex swap] error:\n" + traceback.format_exc())


def _install_color_routing_hook() -> None:
	"""Replace -[GSFontViewController setColorIndex:] with the swap-aware version.

	Idempotent (module-level _CF_ROUTING_INSTALLED guard) so reloading or multiple
	document windows never double-install. Whole body guarded: a missing GSFontViewController
	symbol on a future Glyphs, or any PyObjC signature/dispatch failure, only prints to the
	Macro panel and leaves stock routing intact — palette load is never broken.
	"""
	global _CF_ROUTING_INSTALLED
	if _CF_ROUTING_INSTALLED:
		return
	try:
		try:
			font_view_controller = objc.lookUpClass("GSFontViewController")
		except Exception:
			import traceback
			print("AZ Colorflow [routing hook] GSFontViewController not found:\n"
				+ traceback.format_exc())
			return
		# Mark installed BEFORE the swap: a partial failure must not let the next window
		# re-attempt (it would only fail again).
		_CF_ROUTING_INSTALLED = True
		# REPLACE the EXISTING -[GSFontViewController setColorIndex:] IMP. Both PyObjC's
		# classAddMethods AND objc.Category only ADD new selectors (Category internally calls
		# classAddMethods too) — neither overrides an already-implemented selector, so they
		# leave the stock IMP in place. We therefore: (1) add our Python impl under a NEW
		# private selector (classAddMethods works for a new name), then (2) copy that IMP onto
		# the existing setColorIndex: via the Objective-C runtime's class_replaceMethod (ctypes).
		# The IMP is a PyObjC trampoline bound to our callable, so it dispatches correctly under
		# either selector. Signature v@:C matches the verified encoding (v20@0:8C16, uint8_t arg).
		private = objc.selector(
			_cf_setColorIndex_, selector=b"cf_swapSetColorIndex:", signature=b"v@:C")
		objc.classAddMethods(font_view_controller, [private])
		if _runtime_copy_imp("GSFontViewController", b"cf_swapSetColorIndex:",
				b"setColorIndex:", b"v@:C"):
			print("AZ Colorflow: swap-routing hook installed on "
				"-[GSFontViewController setColorIndex:].")
		else:
			print("AZ Colorflow [routing hook] could not replace setColorIndex: IMP; "
				"stock routing left intact.")
	except Exception:
		import traceback
		print("AZ Colorflow [routing hook] error:\n" + traceback.format_exc())


def _runtime_copy_imp(
	class_name: str, source_selector: bytes, target_selector: bytes, type_encoding: bytes
) -> bool:
	"""Copy ``class_name``'s ``source_selector`` IMP onto its ``target_selector`` via the
	Objective-C runtime (method_setImplementation), using ctypes/libobjc — the only reliable
	way to OVERRIDE an already-implemented COMPILED method from PyObjC (both classAddMethods
	and objc.Category only ADD new selectors). ``target_selector`` is a compiled GlyphsCore
	method, so it dispatches purely through its IMP slot and the swap takes effect. Returns
	True on success; any failure prints and returns False so stock routing is left intact.

	(Verified against a compiled method in isolation: copying a private PyObjC selector's IMP
	onto -[__NSArrayM count] made count() return the patched value.)"""
	try:
		import ctypes

		libobjc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
		libobjc.objc_getClass.restype = ctypes.c_void_p
		libobjc.objc_getClass.argtypes = [ctypes.c_char_p]
		libobjc.sel_registerName.restype = ctypes.c_void_p
		libobjc.sel_registerName.argtypes = [ctypes.c_char_p]
		libobjc.class_getInstanceMethod.restype = ctypes.c_void_p
		libobjc.class_getInstanceMethod.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
		libobjc.method_getImplementation.restype = ctypes.c_void_p
		libobjc.method_getImplementation.argtypes = [ctypes.c_void_p]
		libobjc.method_setImplementation.restype = ctypes.c_void_p
		libobjc.method_setImplementation.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

		_ = type_encoding   # the target method already carries its encoding; kept for the API
		cls = libobjc.objc_getClass(class_name.encode())
		if not cls:
			return False
		source_method = libobjc.class_getInstanceMethod(cls, libobjc.sel_registerName(source_selector))
		target_method = libobjc.class_getInstanceMethod(cls, libobjc.sel_registerName(target_selector))
		if not source_method or not target_method:
			return False
		imp = libobjc.method_getImplementation(source_method)
		if not imp:
			return False
		libobjc.method_setImplementation(target_method, imp)
		return True
	except Exception:
		import traceback
		print("AZ Colorflow [routing hook] runtime IMP copy failed:\n" + traceback.format_exc())
		return False


########################################################################################################
#																									   #
#	COLOR FLOW SETTINGS PANE (Glyphs > Settings > Color Flow)									       #
#																									   #
########################################################################################################
#
# The label/colour controls used to live in a per-palette popover. They now live in a single GLOBAL
# preferences pane added to Glyphs > Settings via the app delegate's addViewToPreferences:. Because
# the pane is shared across every document window, edits there are routed through the same pure
# helpers the palette uses (labelcolors / colornames) and then broadcast with an NSNotification so
# every open palette instance refreshes live.

# The notification name every palette instance observes; the pane posts it after any edit.
COLORFLOW_SETTINGS_CHANGED = "AZColorflowSettingsChanged"

# The pane's Settings tab identifier AND its visible label. Verified against GlyphsCore:
# -addViewController: makes the tab identifier = vc.representedObject and the label =
# vc.title, and showMainPreferencesWithIdentifier: selects the tab by that identifier. So
# we set representedObject = title = this string, and jump to the same string.
COLORFLOW_PREF_IDENTIFIER = "AZ Colorflow"

# Registered exactly once per app session (palettes instantiate once per document window). The VC is
# held module-globally so AppKit does not deallocate it out from under the Settings window.
_PREF_PANE_ADDED = False
_PREF_PANE_VC = None
_PREF_PANE_CONTROLLER = None


def _app_delegate() -> Any:
	"""The Glyphs app delegate (it implements addViewToPreferences: / showMainPreferencesWithIdentifier:).
	Prefer Glyphs.delegate(); fall back to the shared application's delegate."""
	try:
		delegate = Glyphs.delegate()
		if delegate is not None:
			return delegate
	except Exception:
		pass
	try:
		return AppKit.NSApplication.sharedApplication().delegate()
	except Exception:
		return None


def _font_dir_for(font) -> str | None:
	return os.path.dirname(font.filepath) if (font is not None and font.filepath) else None


def _broadcast_settings_changed() -> None:
	"""Tell every open palette instance to re-read its settings and rebuild."""
	try:
		from Foundation import NSNotificationCenter
		NSNotificationCenter.defaultCenter().postNotificationName_object_(
			COLORFLOW_SETTINGS_CHANGED, None)
	except Exception:
		import traceback
		print("AZ Colorflow [settings broadcast] error:\n" + traceback.format_exc())


def _rgba_close(first, second, tol: float = 1e-4) -> bool:
	"""True when two ``(r, g, b, a)`` tuples match within ``tol`` per channel. Used to
	decide whether a colour well ACTUALLY changed before rewriting the twelve label
	colours — an unchanged well must compare equal so editing a name / visibility never
	churns (and colour-space-drifts) the colours."""
	try:
		return len(first) == len(second) and all(
			abs(float(left) - float(right)) <= tol for left, right in zip(first, second, strict=True)
		)
	except Exception:
		return False


def _apply_label_colors(colors: list) -> None:
	"""Persist the twelve label colours, live-refresh the app, and broadcast."""
	if len(colors) != 12:
		return
	labelcolors.write_label_colors(colors)
	labelcolors.refresh_app_label_colors(colors)
	_broadcast_settings_changed()


def _apply_label_names(font, labels_by_index: dict) -> None:
	"""Rewrite colorNames.txt from the edited name fields, PRESERVING each slot's current
	visibility flag (visibility is now the eye/checkbox's job — renaming never shows/hides a
	slot), keep the in-font copy in sync when this font stores its labels in-file, then
	broadcast."""
	path = colornames.get_key_file(_font_dir_for(font))
	text = colornames.pick_settings_text(
		colornames.font_labels_text(font), colornames.read_color_names(path))
	rows, none_label = colornames.parse_settings(text)
	new_rows = []
	for index, label, visible in rows:
		if index in labels_by_index:
			new_rows.append((index, labels_by_index[index].strip(), visible))
		else:
			new_rows.append((index, label, visible))
	new_text = colornames.render_settings(new_rows, none_label)
	colornames.write_color_names(path, new_text)
	if font is not None and colornames.font_labels_text(font) is not None:
		font.userData[colornames.FONT_LABELS_KEY] = new_text
	_broadcast_settings_changed()


def _apply_color_order(font, new_visible_order: list[int]) -> None:
	"""Persist a new visible-colour order to colorNames.txt (and the in-font copy when this
	font stores its labels in-file), then broadcast so every palette rebuilds. The reorder
	math lives in the pure, unit-tested colornames.reorder_visible_rows."""
	path = colornames.get_key_file(_font_dir_for(font))
	text = colornames.pick_settings_text(
		colornames.font_labels_text(font), colornames.read_color_names(path))
	rows, none_label = colornames.parse_settings(text)
	new_rows = colornames.reorder_visible_rows(rows, new_visible_order)
	new_text = colornames.render_settings(new_rows, none_label)
	colornames.write_color_names(path, new_text)
	if font is not None and colornames.font_labels_text(font) is not None:
		font.userData[colornames.FONT_LABELS_KEY] = new_text
	_broadcast_settings_changed()


def _apply_label_visibility(font, visibility_by_index: dict) -> None:
	"""Persist each slot's explicit show/hide flag to colorNames.txt (and the in-font copy
	when this font stores its labels in-file) WITHOUT touching its label or colour order,
	then broadcast so every palette rebuilds. A named slot can therefore be hidden and keep
	its name. The flip math lives in the pure, unit-tested colornames.set_label_visibility."""
	path = colornames.get_key_file(_font_dir_for(font))
	text = colornames.pick_settings_text(
		colornames.font_labels_text(font), colornames.read_color_names(path))
	rows, none_label = colornames.parse_settings(text)
	for index, visible in visibility_by_index.items():
		rows = colornames.set_label_visibility(rows, int(index), bool(visible))
	new_text = colornames.render_settings(rows, none_label)
	colornames.write_color_names(path, new_text)
	if font is not None and colornames.font_labels_text(font) is not None:
		font.userData[colornames.FONT_LABELS_KEY] = new_text
	_broadcast_settings_changed()


def _reset_colors_and_order(font) -> None:
	"""Reset the twelve label colours to the Glyphs defaults AND the workflow
	names/order/visibility to the Color Flow default sequence, keep the in-font copy in sync
	when this font stores its labels in-file, then broadcast so every palette rebuilds."""
	labelcolors.write_label_colors(labelcolors.DEFAULTS)
	labelcolors.refresh_app_label_colors(labelcolors.DEFAULTS)
	path = colornames.get_key_file(_font_dir_for(font))
	colornames.write_color_names(path, colornames.DEFAULT_COLOR_NAMES)
	if font is not None and colornames.font_labels_text(font) is not None:
		font.userData[colornames.FONT_LABELS_KEY] = colornames.DEFAULT_COLOR_NAMES
	_broadcast_settings_changed()


def _poke_default_sort(font) -> None:
	"""Nudge Glyphs to refresh the Font View to the default glyph order. Toggling
	``storeSortName`` True then False on a glyph triggers a re-sort without persisting
	any custom sort name (the Macro-panel idiom ``font.glyphs[0].storeSortName = True/False``)."""
	try:
		if font is None or len(font.glyphs) == 0:
			return
		glyph = font.glyphs[0]
		glyph.storeSortName = True
		glyph.storeSortName = False
	except Exception:
		import traceback
		print("AZ Colorflow [default sort poke] error:\n" + traceback.format_exc())


def _apply_rainbow_source(font, segment: int) -> None:
	"""Mirror the popover's Default/Layer/Glyph segmented control: 0 disables Font Glyph
	Order grouping, 1 = Layer colour, 2 = Glyph colour. Best-effort; broadcasts."""
	if font is None:
		return
	grouping = fontview.FontViewGrouping()
	try:
		if segment == 0:
			if grouping.is_enabled(font):
				grouping.disable(font)
			# Default order restored — poke Glyphs to re-sort the Font View to it.
			_poke_default_sort(font)
		else:
			grouping.set_mode(font, "Layer" if segment == 1 else "Glyph")
			if not grouping.is_enabled(font):
				grouping.enable(font)
	except Exception:
		import traceback
		print("AZ Colorflow [rainbow source] error:\n" + traceback.format_exc())


def _rainbow_segment_for_font(font) -> int:
	"""Current grouping state -> segment index (0 Default / 1 Layer / 2 Glyph)."""
	if font is None:
		return 0
	grouping = fontview.FontViewGrouping()
	try:
		if not grouping.is_enabled(font):
			return 0
		return 2 if grouping.mode(font) == "Glyph" else 1
	except Exception:
		return 0


def _eye_symbol(name: str):
	"""SF Symbol ``NSImage`` for an eye glyph (``eye.fill`` / ``eye.slash``), or ``None`` on a
	macOS too old for symbol images (the cell then falls back to a plain checkbox)."""
	try:
		return AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
	except Exception:
		return None


class EyeToggleList2Cell(CheckBoxList2Cell):
	"""The visibility column drawn as an eye icon instead of a checkbox: ``eye.fill`` when the
	colour is SHOWN, ``eye.slash`` when HIDDEN. It is still a CheckBox underneath, so clicking
	toggles the state, writes the bool back into the row dict and fires the list editCallback —
	exactly like the checkbox it replaces. We just restyle the NSButton as a borderless
	push-on/push-off toggle whose normal image is the OFF (hidden) eye and whose alternate image
	is the ON (shown) eye."""

	def __init__(self, title=None, editable=False, callback=None) -> None:
		super().__init__(title=None, editable=editable, callback=callback)
		try:
			button = self.getNSButton()
			toggle_type = getattr(AppKit, "NSButtonTypeToggle", None)
			if toggle_type is None:                              # pre-10.12 constant name
				toggle_type = getattr(AppKit, "NSToggleButton", 2)
			button.setButtonType_(toggle_type)
			button.setBordered_(False)
			button.setImagePosition_(getattr(AppKit, "NSImageOnly", 5))
			button.setImageScaling_(AppKit.NSImageScaleProportionallyDown)
			button.setTitle_("")
			off_eye = _eye_symbol("eye.slash")                   # state OFF = hidden
			on_eye = _eye_symbol("eye.fill")                     # state ON  = shown
			if off_eye is not None:
				button.setImage_(off_eye)
			if on_eye is not None:
				button.setAlternateImage_(on_eye)
		except Exception:
			import traceback
			print("AZ Colorflow [eye cell] error:\n" + traceback.format_exc())


class AZColorflowSettingsView:
	"""Builds + owns the vanilla controls for the Color Flow preferences pane and routes
	every edit through the module-level shared helpers (which broadcast to open palettes).

	Held module-globally (not per palette instance) because the pane is GLOBAL: it is added
	to Glyphs > Settings once per session and shared across all document windows."""

	WIDTH = 340          # base width; the view + controls stretch to fill the Settings tab
	MARGIN = 12          # slim margins so the controls take the full pane width

	def __init__(self) -> None:
		# One combined List2 of all 12 label slots: each row = colour well + editable name.
		# ``_slot_items`` is the parallel list of row dicts (slot/color/name) so callbacks can
		# map an edited/dragged row back to its colour index.
		self._slot_list = None
		self._slot_items: list[dict] = []
		self._color_order = None
		self._swap_checkbox = None
		self._license_btn = None
		self._height = 0
		self._build()

	@property
	def view(self) -> Any:
		# Pin the backing view to its built size and let Glyphs' tab view position (not
		# deform) it. Vanilla resolves negative/zero widths against the LIVE parent frame,
		# which is ~0 the moment Glyphs first lays the pane out — collapsing every full-width
		# control to the top-left. We avoid that two ways: every control below uses POSITIVE
		# absolute coords, and we fix the view's frame + min size here.
		ns_view = self.group.getNSView()
		try:
			ns_view.setFrame_(AppKit.NSMakeRect(0, 0, self.WIDTH, self._height))
			# Fill the Settings tab's width (the window itself is sized by Glyphs / other
			# panes — we can't narrow it, only fill it); pin to the top, keep our height.
			ns_view.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewMinYMargin)
		except Exception:
			pass
		return ns_view

	# ------------------------------------------------------------------ build
	def _effective_label_text(self, font) -> str:
		try:
			key_text = colornames.read_color_names(
				colornames.get_key_file(_font_dir_for(font)))
			return colornames.pick_settings_text(
				colornames.font_labels_text(font), key_text)
		except Exception:
			return colornames.DEFAULT_COLOR_NAMES

	def _build(self) -> None:
		# EVERY control uses POSITIVE, absolute coords (no -margin / -100 right anchors):
		# vanilla resolves negatives against the live parent frame, which collapses inside
		# Glyphs' tab view. ``inner`` is the full content width between the margins.
		# Top-to-bottom: Color Labels title (+ reload-reset icon), a help line, ONE combined
		# 12-row list (colour well + editable name, visible rows draggable to reorder), then
		# Font Glyph Order.
		font = Glyphs.font
		margin = self.MARGIN
		inner = self.WIDTH - 2 * margin

		# Color Labels (title + reload-reset icon, help line, combined editor) ---
		lc_label_y = 12
		# One help line under the title explaining how to edit a row.
		lc_help_y = lc_label_y + 20
		lc_help_h = 36
		lc_list_y = lc_help_y + lc_help_h + 6
		# 12 rows; List2 row height is ~24pt on modern macOS, plus a little chrome.
		lc_list_h = 12 * 26 + 8
		# Font Glyph Order (below the list — reset is now the title's reload icon) ---
		fgo_sep_y = lc_list_y + lc_list_h + 10
		fgo_label_y = fgo_sep_y + 10
		fgo_seg_y = fgo_label_y + 20
		# Behaviour (below Font Glyph Order) ------------------------------------
		beh_sep_y = fgo_seg_y + 24 + 10
		beh_label_y = beh_sep_y + 10
		beh_check_y = beh_label_y + 20
		beh_lic_y = beh_check_y + 24
		height = beh_lic_y + 22 + margin
		self._height = height

		self.group = Group((0, 0, self.WIDTH, height))
		group = self.group
		# Vanilla creates the Group's NSView with a ZERO frame and only applies the posSize
		# when a PARENT lays it out. Here the Group has no vanilla parent (its view becomes an
		# NSViewController.view), so we set the frame ourselves BEFORE adding children — every
		# child's frame is computed against the Group's CURRENT frame (vanilla flips top-origin
		# posSize using the parent height), and a zero height would push every row off-view.
		try:
			group.getNSView().setFrame_(AppKit.NSMakeRect(0, 0, self.WIDTH, height))
		except Exception:
			pass

		group.lcLabel = TextBox((margin, lc_label_y, 96, 18), "Color Labels")

		# Reset icon (a "reload" arrow) sits next to the title; it confirms, then restores the
		# twelve label colours + the names/order/visibility to their defaults. Replaces the old
		# full-width reset button.
		reload_image = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(
			"arrow.clockwise", "Reset colours and order")
		if reload_image is None:                                  # pre-SF-Symbols fallback
			reload_image = AppKit.NSImage.imageNamed_(AppKit.NSImageNameRefreshTemplate)
		group.resetButton = ImageButton((margin + 98, lc_label_y - 2, 20, 20),
			imageObject=reload_image, bordered=False, callback=self._reset_clicked)
		try:
			group.resetButton.getNSButton().setToolTip_("Reset colours and order")
		except Exception:
			pass

		# Help line: how to edit a row. Renaming is a double-click (not obvious), so spell it out.
		group.lcHelp = TextBox((margin, lc_help_y, inner, lc_help_h),
			"Double-click a name to rename it. Click the swatch to recolour, the "
			"eye to hide, and drag to reorder.",
			sizeStyle="small")

		# ONE combined control: a List2 of all 12 label slots. Each row carries an EYE
		# checkbox (show/hide the slot), a colour well (recolour) and an editable name
		# (rename). Shown rows are draggable to reorder the workflow sequence; hidden rows
		# are pinned below and are NOT draggable. A row can stay NAMED yet hidden. The drop
		# persists via the shared _apply_color_order -> colornames.reorder_visible_rows path
		# and broadcasts.
		drag_type = "dev.azcolorflow.slotRow"
		try:
			group.lcList = List2(
				(margin, lc_list_y, inner, lc_list_h),
				self._slot_list_items(font),
				columnDescriptions=[
					# Eye toggle = "shown" (eye.fill) / "hidden" (eye.slash). Editable so a
					# click flips visibility (the bool is written back into the row dict,
					# then editCallback fires).
					dict(identifier="visible", title="", cellClass=EyeToggleList2Cell,
						editable=True, width=24),
					dict(identifier="color", title="", cellClass=ColorWellList2Cell,
						editable=True, width=44),
					dict(identifier="name", title="", cellClass=EditTextList2Cell,
						editable=True),
				],
				showColumnTitles=False,
				allowsSorting=False,
				allowsMultipleSelection=False,
				allowsEmptySelection=True,
				drawFocusRing=False,
				editCallback=self._slot_edited,
				dragSettings=dict(
					dragCandidateCallback=self._slot_drag_candidate,
					makeDragDataCallback=self._slot_make_drag_data),
				dropSettings=dict(
					pasteboardTypes=[drag_type],
					dropCandidateCallback=self._slot_drop_candidate,
					performDropCallback=self._slot_perform_drop),
			)
			self._slot_list = group.lcList
		except Exception:
			import traceback
			print("AZ Colorflow [pane slot list build] error:\n" + traceback.format_exc())
			self._slot_list = None

		# Font Glyph Order (bottom) ---------------------------------------------
		group.fgoSep = HorizontalLine((margin, fgo_sep_y, inner, 1))
		group.fgoLabel = TextBox((margin, fgo_label_y, inner, 18), "Font Glyph Order")
		# Single checkbox: ON = Layer colour glyph order, OFF = Default font order.
		group.colorOrder = CheckBox((margin, fgo_seg_y, inner, 18),
			"Color Glyph Order",
			value=bool(_rainbow_segment_for_font(font)),
			callback=self._color_order_changed)
		self._color_order = group.colorOrder

		# Behaviour (bottom) ----------------------------------------------------
		group.behSep = HorizontalLine((margin, beh_sep_y, inner, 1))
		group.behLabel = TextBox((margin, beh_label_y, inner, 18), "Behaviour")
		group.swapRouting = CheckBox((margin, beh_check_y, inner, 18),
			"Swap Option color routing (plain → layer)",
			value=bool(Glyphs.defaults[SWAP_KEY]),
			callback=self._swap_routing_changed)
		self._swap_checkbox = group.swapRouting

		# License recovery button — always-enabled, opens the license sheet.
		group.licenseBtn = Button((margin, beh_lic_y, inner, 22), "License…",
			callback=lambda sender: __import__("_azcolorflow_lic", fromlist=["bootstrap"]).bootstrap.show_license_ui(__import__("_azcolorflow_lic_config").CONFIG))
		self._license_btn = group.licenseBtn

		# Make the full-width controls grow with the Settings tab. Each is pinned to the top,
		# width flexible. The title + its reload-reset icon keep a fixed width/position
		# (top-left), so the icon stays next to the title rather than drifting right.
		for _name in ("lcHelp", "lcList", "fgoSep", "fgoLabel", "colorOrder",
				"behSep", "behLabel", "swapRouting", "licenseBtn"):
			try:
				getattr(group, _name).getNSView().setAutoresizingMask_(
					AppKit.NSViewWidthSizable | AppKit.NSViewMinYMargin)
			except Exception:
				pass
		for _name in ("lcLabel", "resetButton"):
			try:
				getattr(group, _name).getNSView().setAutoresizingMask_(AppKit.NSViewMinYMargin)
			except Exception:
				pass
		# Fade hidden rows so they read as inactive.
		self._dim_hidden_rows()

	# ------------------------------------------------------------------ slot list
	def _slot_list_items(self, font) -> list[dict]:
		"""All 12 label slots as List2 row dicts, VISIBLE (shown) first in their current
		workflow order, then HIDDEN pinned below. Each dict carries the colour index
		(``slot``), the live NSColor (``color``), the editable label (``name``) and the
		explicit show/hide flag (``visible``, from the parsed rows — NOT name-blankness, so
		a named row can be hidden and keep its name). Also caches the list in
		``self._slot_items`` so callbacks can map rows back to colours and recompute the
		visible order on drag/edit."""
		items: list[dict] = []
		try:
			rgba_list = labelcolors.read_label_colors()
			rows, _none = colornames.parse_settings(self._effective_label_text(font))
			visible_rows = [(index, label) for index, label, visible in rows if visible]
			hidden_rows = [(index, label) for index, label, visible in rows if not visible]
			for index, label in visible_rows + hidden_rows:
				color = AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(*rgba_list[index])
				items.append(dict(slot=int(index), color=color, name=label,
					visible=any(index == r[0] and r[2] for r in rows)))
		except Exception:
			import traceback
			print("AZ Colorflow [pane slot items] error:\n" + traceback.format_exc())
			items = []
		self._slot_items = items
		return items

	@staticmethod
	def _slot_is_visible(item: dict) -> bool:
		"""A slot row is VISIBLE (shown, draggable, part of the workflow order) when its
		EXPLICIT ``visible`` flag is set — the eye/checkbox column, NOT name-blankness. A
		named row can therefore be unchecked (hidden) and keep its name."""
		return bool(item.get("visible"))

	def _visible_slot_count(self) -> int:
		"""Number of leading VISIBLE rows (the draggable block, pinned above the hidden ones)."""
		return sum(1 for item in self._slot_items if self._slot_is_visible(item))

	def _dim_hidden_rows(self) -> None:
		"""Fade hidden (unchecked) slot rows so they read as inactive. Row index maps to
		self._slot_items (visible first, hidden pinned below); makeIfNecessary forces each row
		view to exist so the dim holds right after a reload. Best-effort/guarded."""
		if self._slot_list is None:
			return
		try:
			table = self._slot_list.getNSTableView()
			for row, item in enumerate(self._slot_items):
				row_view = table.rowViewAtRow_makeIfNecessary_(row, True)
				if row_view is not None:
					row_view.setAlphaValue_(1.0 if self._slot_is_visible(item) else 0.4)
		except Exception:
			import traceback
			print("AZ Colorflow [dim hidden rows] error:\n" + traceback.format_exc())

	def _slot_drag_candidate(self, indexes) -> bool:
		"""Allow a drag only when every picked row is VISIBLE (named). Hidden rows are fixed."""
		try:
			return bool(indexes) and all(
				0 <= int(i) < len(self._slot_items)
				and self._slot_is_visible(self._slot_items[int(i)])
				for i in indexes
			)
		except Exception:
			return False

	def _slot_make_drag_data(self, index) -> dict:
		"""Pack the dragged source row index onto the pasteboard for the self-reorder."""
		return {"dev.azcolorflow.slotRow": int(index)}

	def _slot_drop_candidate(self, info) -> str:
		"""Accept a self-move drop (rejects external drags, which carry no source)."""
		try:
			return "move" if info.get("source") is self._slot_list else "none"
		except Exception:
			return "none"

	def _slot_perform_drop(self, info) -> bool:
		"""Self-drop reorder: move the dragged VISIBLE rows to the drop position (clamped to
		stay within the visible block, above the pinned hidden rows), refresh the list, then
		persist the new visible-colour order via the shared _apply_color_order helper."""
		try:
			sender = info.get("sender")
			source_indexes = sorted(
				int(i) for i in sender.getDropItemValues(
					info.get("items") or [], "dev.azcolorflow.slotRow"))
			items = list(self._slot_items)
			moved = [items[i] for i in source_indexes if 0 <= i < len(items)]
			if not moved or not all(self._slot_is_visible(item) for item in moved):
				return False
			source_set = set(source_indexes)
			remaining = [item for pos, item in enumerate(items) if pos not in source_set]
			drop_index = info.get("index")
			visible_remaining = sum(1 for item in remaining if self._slot_is_visible(item))
			if drop_index is None:
				insert_at = visible_remaining
			else:
				insert_at = int(drop_index) - sum(1 for i in source_indexes if i < int(drop_index))
			# Keep the moved (visible) rows inside the visible block, above hidden rows.
			insert_at = max(0, min(visible_remaining, insert_at))
			new_items = remaining[:insert_at] + moved + remaining[insert_at:]
			self._slot_items = new_items
			if self._slot_list is not None:
				self._slot_list.set(new_items)
				self._dim_hidden_rows()
			new_order = [item["slot"] for item in new_items if self._slot_is_visible(item)]
			_apply_color_order(Glyphs.font, new_order)
			return True
		except Exception:
			import traceback
			print("AZ Colorflow [pane slot drop] error:\n" + traceback.format_exc())
			return False

	# ------------------------------------------------------------------ refresh
	def reload(self) -> None:
		"""Re-read settings into the pane's controls (e.g. after the active font changes)."""
		try:
			font = Glyphs.font
			if self._slot_list is not None:
				self._slot_list.set(self._slot_list_items(font))
				self._dim_hidden_rows()
			if self._color_order is not None:
				self._color_order.set(bool(_rainbow_segment_for_font(font)))
			if self._swap_checkbox is not None:
				self._swap_checkbox.set(bool(Glyphs.defaults[SWAP_KEY]))
		except Exception:
			import traceback
			print("AZ Colorflow [pane reload] error:\n" + traceback.format_exc())

	# ------------------------------------------------------------------ callbacks
	def _color_order_changed(self, sender) -> None:
		try:
			# Checkbox ON = Layer colour order, OFF = Default (restores order + pokes re-sort).
			_apply_rainbow_source(Glyphs.font, 1 if sender.get() else 0)
		except Exception:
			import traceback
			print("AZ Colorflow [pane rainbow] error:\n" + traceback.format_exc())

	def _swap_routing_changed(self, sender) -> None:
		"""Persist the swap toggle. The swizzled setColorIndex: reads SWAP_KEY at call
		time, so no re-swizzle is needed; routing doesn't change palette display, so no
		broadcast either."""
		try:
			Glyphs.defaults[SWAP_KEY] = bool(sender.get())
		except Exception:
			import traceback
			print("AZ Colorflow [pane swap routing] error:\n" + traceback.format_exc())

	def _reset_clicked(self, sender) -> None:
		"""Confirm, then reset the 12 label colours + the names/order/visibility to defaults
		(via the shared _reset_colors_and_order helper) and refresh the pane's own list."""
		try:
			alert = AppKit.NSAlert.alloc().init()
			alert.setMessageText_("Reset colours and order?")
			alert.setInformativeText_(
				"This restores the twelve label colours and the workflow "
				"names, order and visibility to their defaults.")
			alert.addButtonWithTitle_("Reset")
			alert.addButtonWithTitle_("Cancel")
			if alert.runModal() != AppKit.NSAlertFirstButtonReturn:
				return
			_reset_colors_and_order(Glyphs.font)
			self.reload()
		except Exception:
			import traceback
			print("AZ Colorflow [pane reset] error:\n" + traceback.format_exc())

	def _slot_edited(self, sender) -> None:
		"""Fires after the user edits ANY cell (eye/checkbox, colour well or name) in the
		combined list. List2 has already written the new value into the edited row dict, but a
		single editCallback can't say WHICH column changed — so we DIFF the live rows against
		the currently-persisted state and apply ONLY the store that actually moved:

		- colours: rewritten only when a well differs from the saved colour. The well is read
		  in DEVICE RGB (symmetric with how it was built and how write_label_colors stores it),
		  so an untouched well compares equal and the twelve colours are NOT rewritten — this is
		  what stops a hide/rename from colour-space-drifting every colour.
		- names: rewritten only when a label differs (PRESERVING visibility).
		- visibility: rewritten only when a show/hide flag flipped; that case also re-sets the
		  list to re-pin the toggled row into the visible or hidden block.

		Each apply broadcasts so open palettes refresh live. Applying only the changed store
		also keeps the colour-panel refresh/redraw out of a plain rename, so renaming commits
		cleanly."""
		try:
			font = Glyphs.font
			by_slot: dict[int, dict] = {}
			for item in list(self._slot_items):
				slot = int(item.get("slot", -1))
				if 0 <= slot < 12:
					by_slot[slot] = item

			# --- colours: only rewrite when a well genuinely changed (device-space read) ---
			baseline_colors = labelcolors.read_label_colors()
			new_colors = list(baseline_colors)
			colors_changed = False
			for slot, item in by_slot.items():
				native = item.get("color")
				if native is None:
					continue
				rgb = native.colorUsingColorSpaceName_("NSDeviceRGBColorSpace") or native
				comps = (rgb.redComponent(), rgb.greenComponent(),
					rgb.blueComponent(), rgb.alphaComponent())
				new_colors[slot] = comps
				if not _rgba_close(comps, baseline_colors[slot]):
					colors_changed = True
			if colors_changed:
				_apply_label_colors(new_colors)

			# --- names + visibility: diff against the persisted colorNames settings ---
			persisted_rows, _none = colornames.parse_settings(self._effective_label_text(font))
			persisted_names = {index: label for index, label, _vis in persisted_rows}
			persisted_visible = {index: vis for index, _label, vis in persisted_rows}
			labels_by_index = {slot: str(item.get("name", "")).strip()
				for slot, item in by_slot.items()}
			visibility_by_index = {slot: bool(item.get("visible"))
				for slot, item in by_slot.items()}

			if any(labels_by_index[slot] != persisted_names.get(slot)
					for slot in labels_by_index):
				_apply_label_names(font, labels_by_index)
			if any(visibility_by_index[slot] != persisted_visible.get(slot)
					for slot in visibility_by_index):
				_apply_label_visibility(font, visibility_by_index)
				# A flag flipped: re-set so the toggled row re-pins into the visible block or
				# the hidden block below. (A pure name/colour edit leaves the partition intact,
				# so we skip the re-set to avoid stealing focus mid-type.)
				if self._slot_list is not None:
					self._slot_list.set(self._slot_list_items(font))
				self._dim_hidden_rows()
		except Exception:
			import traceback
			print("AZ Colorflow [pane slot edit] error:\n" + traceback.format_exc())


class AZColorflowPreferencesController(AppKit.NSViewController):
	"""NSViewController whose view is the Color Flow settings pane. Glyphs' Settings
	window holds it via addViewToPreferences:. The heavy lifting lives on the
	module-level AZColorflowSettingsView so the title-only VC stays thin."""

	def initWithSettingsView_(self, settings_view) -> Any:
		self = objc.super(AZColorflowPreferencesController, self).init()
		if self is None:
			return None
		self._settingsView = settings_view
		# Glyphs' GSPreferencesController -addViewController: builds the Settings tab as:
		#     item = [[NSTabViewItem alloc] initWithIdentifier: vc.representedObject];
		#     item.view  = vc.view;  item.label = vc.title;
		# and -showPrefpaneWithIdentifier: selects the tab by that identifier. So the tab
		# IDENTIFIER comes from representedObject (must be the string we jump to) and the
		# visible toolbar LABEL comes from title. Both are "Color Flow".
		try:
			self.setTitle_(COLORFLOW_PREF_IDENTIFIER)
		except Exception:
			pass
		try:
			self.setRepresentedObject_(COLORFLOW_PREF_IDENTIFIER)
		except Exception:
			pass
		# Declare how big this pane wants to be. Glyphs' Settings window switches panes inside
		# an NSTabView (item.view = vc.view); a pane-switching prefs window sizes the content
		# area to the selected controller's preferredContentSize. NSTabView stretches our view's
		# FRAME to fill, so the frame can't carry the request — preferredContentSize can, and the
		# window (sidebar + pane) shrinks to fit. Set here AND in loadView so it's present
		# whenever Glyphs queries.
		self._apply_preferred_size()
		return self

	@objc.python_method
	def _apply_preferred_size(self) -> None:
		try:
			view = self._settingsView
			size = AppKit.NSMakeSize(float(view.WIDTH), float(getattr(view, "_height", 0) or view.WIDTH))
			self.setPreferredContentSize_(size)
		except Exception:
			pass

	def loadView(self) -> None:
		try:
			self.setView_(self._settingsView.view)
			self._apply_preferred_size()
		except Exception:
			import traceback
			print("AZ Colorflow [pref loadView] error:\n" + traceback.format_exc())

	# Glyphs 4's Settings sidebar reads GSPreferenceViewControllerProtocol off each
	# registered pane: required -imageName, optional -image. Both are respondsToSelector-
	# guarded (that's why the pane showed with no icon before). We supply an SF Symbol so
	# the tab gets a glyph in the native blue line-icon style. -imageName covers the path
	# where Glyphs builds the image itself (imageWithSystemSymbolName:); -image covers the
	# path where it wants a ready NSImage. Fallback chain keeps an icon across macOS
	# versions (swatchpalette is macOS 14+). Both return objects, so the default PyObjC
	# selector signatures are correct.
	def imageName(self) -> str:
		return "swatchpalette"

	def image(self) -> Any:
		symbol_ctor = getattr(
			AppKit.NSImage, "imageWithSystemSymbolName_accessibilityDescription_", None
		)
		if symbol_ctor is None:   # pre-macOS 11: no SF Symbols
			return None
		for name in ("swatchpalette", "paintpalette", "circle.hexagongrid", "drop.halffull"):
			image = symbol_ctor(name, "AZ Colorflow")
			if image is not None:
				image.setTemplate_(True)   # tint to match the native sidebar icons
				return image
		return None

	def azLicensed(self) -> bool:
		# Protocol v1.1: the AZ Toolkit hub reads this (respondsToSelector + valueForKey)
		# to badge our popup item when the plugin is BOUGHT — an active trial is not a
		# licence, so it gets no badge. _SHARED_ENT is the live Gate settings() publishes.
		try:
			return bool(_SHARED_ENT is not None and _SHARED_ENT.kind == "licensed")
		except Exception:
			return False


# ---- AZ Toolkit shared Settings hub (protocol v1) ----------------------------------------------
# All AZ plugins share ONE "AZ Toolkit" entry in Glyphs > Settings; each plugin's pane is a tab
# inside it. Rendezvous: the hub NSViewController is parked in the main thread's threadDictionary
# under _HUB_KEY — whichever AZ plugin loads first creates the hub (its own uniquely-named copy of
# this class) and registers it via addViewToPreferences:; everyone else finds it there. UI: a
# full-width NSPopUpButton switches between the panes hosted in a tabless NSTabView below it; a
# pane whose plugin is licensed (bought, not trial) gets an accent-colored 􀇻 after its name.
# Keep the selectors stable across ALL AZ plugins (protocol v1.1):
#   addSettingsPane:(NSViewController*)   pane.title = the popup item ("AZ X"),
#                                         pane.representedObject = jump identifier;
#                                         pane MAY expose azLicensed (BOOL)
#   showSettingsPaneWithIdentifier:(NSString*)
_HUB_KEY = "AZToolkit.SettingsHub.v1"
_HUB_TITLE = "AZ Toolkit"
_HUB_BADGE = "\U001001FB"   # SF Symbol checkmark seal, one astral codepoint
_POPUP_BAR_H = 41.0   # 10 top + 25 popup + 6 gap


class AZColorflowToolkitHub(AppKit.NSViewController):
	def init(self) -> Any:
		self = objc.super(AZColorflowToolkitHub, self).init()
		if self is None:
			return None
		self._panes = []
		self.setTitle_(_HUB_TITLE)
		self.setRepresentedObject_(_HUB_TITLE)
		self.setPreferredContentSize_(AppKit.NSMakeSize(360.0, 240.0))
		return self

	def loadView(self) -> None:
		root = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 360, 240))
		popup = AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(
			AppKit.NSMakeRect(12, 240 - 35, 360 - 24, 25), False)
		popup.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewMinYMargin)
		popup.setTarget_(self)
		popup.setAction_("azToolkitPopupChanged:")
		tabs = AppKit.NSTabView.alloc().initWithFrame_(
			AppKit.NSMakeRect(0, 0, 360, 240 - _POPUP_BAR_H))
		tabs.setTabViewType_(AppKit.NSNoTabsNoBorder)
		tabs.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
		root.addSubview_(popup)
		root.addSubview_(tabs)
		self._popup = popup
		self._tabs = tabs
		self.setView_(root)

	def azToolkitPopupChanged_(self, sender: Any) -> None:
		try:
			self._tabs.selectTabViewItemAtIndex_(sender.indexOfSelectedItem())
		except Exception:
			pass

	# Glyphs 4's Settings sidebar reads GSPreferenceViewControllerProtocol off each pane:
	# required -imageName, optional -image (both respondsToSelector-guarded).
	def imageName(self) -> str:
		return "wrench.and.screwdriver"

	def image(self) -> Any:
		symbol_ctor = getattr(
			AppKit.NSImage, "imageWithSystemSymbolName_accessibilityDescription_", None
		)
		if symbol_ctor is None:   # pre-macOS 11: no SF Symbols
			return None
		for name in ("wrench.and.screwdriver", "gearshape.2", "hammer"):
			image = symbol_ctor(name, _HUB_TITLE)
			if image is not None:
				image.setTemplate_(True)
				return image
		return None

	def addSettingsPane_(self, pane: Any) -> None:
		try:
			self.view()   # force loadView so _popup/_tabs exist
			tabs = self._tabs
			ident = pane.representedObject() or pane.title() or ""
			for index in range(tabs.numberOfTabViewItems()):
				if tabs.tabViewItemAtIndex_(index).identifier() == ident:
					return   # already registered (e.g. two document windows)
			title = pane.title() or str(ident)
			label = title[3:] if title.startswith("AZ ") else title
			size = pane.preferredContentSize()
			view = pane.view()
			if size.width < 1 or size.height < 1:
				size = view.frame().size
			# Pin the pane at its designed size, top-left; the flexible right/bottom
			# margins absorb the stretch NSTabView applies to item views.
			container = AppKit.NSView.alloc().initWithFrame_(
				AppKit.NSMakeRect(0, 0, size.width, size.height))
			view.setFrame_(AppKit.NSMakeRect(0, 0, size.width, size.height))
			view.setAutoresizingMask_(AppKit.NSViewMaxXMargin | AppKit.NSViewMinYMargin)
			container.addSubview_(view)
			item = AppKit.NSTabViewItem.alloc().initWithIdentifier_(ident)
			item.setLabel_(label)
			item.setView_(container)
			insert_at = tabs.numberOfTabViewItems()
			for index in range(tabs.numberOfTabViewItems()):
				if label < str(tabs.tabViewItemAtIndex_(index).label()):
					insert_at = index
					break
			tabs.insertTabViewItem_atIndex_(item, insert_at)
			# Popup shows the FULL plugin name ("AZ Colorflow"), not the stripped
			# tab label — the sort above still uses the label.
			self._popup.insertItemWithTitle_atIndex_(title, insert_at)
			if self._pane_licensed(pane):
				text = AppKit.NSMutableAttributedString.alloc().initWithString_attributes_(
					title + "  ",
					{AppKit.NSFontAttributeName: AppKit.NSFont.menuFontOfSize_(0)})
				text.appendAttributedString_(self._badge_string())
				self._popup.itemAtIndex_(insert_at).setAttributedTitle_(text)
			self._panes.append(pane)   # retain: AppKit must not dealloc the pane
			self._popup.selectItemAtIndex_(
				tabs.indexOfTabViewItem_(tabs.selectedTabViewItem()))
			self._recalc_preferred_size()
		except Exception:
			import traceback
			print("AZ Colorflow [toolkit hub addPane] error:\n" + traceback.format_exc())

	@objc.python_method
	def _badge_string(self) -> Any:
		"""The licensed badge, appended after the plugin name.

		Preferred: checkmark.seal.fill as a PALETTE symbol image (white checkmark
		inside an accent-colored seal, macOS 12+) attached inline via
		NSTextAttachment — plain text runs render SF symbols monochrome, so the
		checkmark can't be white there. Fallback: the accent-colored 􀇻 glyph as
		text (checkmark = knocked out)."""
		accent = getattr(AppKit.NSColor, "controlAccentColor", None)
		color = accent() if accent is not None else AppKit.NSColor.systemBlueColor()
		try:
			image = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(
				"checkmark.seal.fill", "licensed")
			size_conf = AppKit.NSImageSymbolConfiguration.configurationWithPointSize_weight_(
				12.0, AppKit.NSFontWeightRegular)
			palette = AppKit.NSImageSymbolConfiguration.configurationWithPaletteColors_(
				[AppKit.NSColor.whiteColor(), color])
			image = image.imageWithSymbolConfiguration_(
				size_conf.configurationByApplyingConfiguration_(palette))
			attachment = AppKit.NSTextAttachment.alloc().init()
			attachment.setImage_(image)
			size = image.size()
			font = AppKit.NSFont.menuFontOfSize_(0)
			# center the seal on the cap height of the menu font
			offset_y = round((font.capHeight() - size.height) / 2.0)
			attachment.setBounds_(AppKit.NSMakeRect(0, offset_y, size.width, size.height))
			return AppKit.NSAttributedString.attributedStringWithAttachment_(attachment)
		except Exception:
			pass
		text = AppKit.NSMutableAttributedString.alloc().initWithString_attributes_(
			_HUB_BADGE, {AppKit.NSFontAttributeName: AppKit.NSFont.menuFontOfSize_(0)})
		text.addAttribute_value_range_(
			AppKit.NSForegroundColorAttributeName, color,
			AppKit.NSMakeRange(0, text.length()))
		return text

	@objc.python_method
	def _pane_licensed(self, pane: Any) -> bool:
		"""Protocol v1.1: a pane MAY expose azLicensed (bought, not trial).
		Debug: the AZToolkitFakeLicensed defaults key badges EVERY pane."""
		try:
			if AppKit.NSUserDefaults.standardUserDefaults().boolForKey_("AZToolkitFakeLicensed"):
				return True
			if pane.respondsToSelector_(b"azLicensed"):
				return bool(pane.valueForKey_("azLicensed"))
		except Exception:
			pass
		return False

	def showSettingsPaneWithIdentifier_(self, identifier: Any) -> None:
		try:
			self.view()
			tabs = self._tabs
			for index in range(tabs.numberOfTabViewItems()):
				if tabs.tabViewItemAtIndex_(index).identifier() == identifier:
					tabs.selectTabViewItemAtIndex_(index)
					self._popup.selectItemAtIndex_(index)
					break
		except Exception:
			pass
		delegate = _app_delegate()
		if delegate is not None and delegate.respondsToSelector_(b"showMainPreferencesWithIdentifier:"):
			try:
				delegate.showMainPreferencesWithIdentifier_(_HUB_TITLE)
			except Exception:
				pass

	@objc.python_method
	def _recalc_preferred_size(self) -> None:
		try:
			max_width, max_height = 300.0, 200.0
			for pane in self._panes:
				size = pane.preferredContentSize()
				if size.width < 1 or size.height < 1:
					size = pane.view().frame().size
				max_width = max(max_width, size.width)
				max_height = max(max_height, size.height)
			self.setPreferredContentSize_(
				AppKit.NSMakeSize(max_width, max_height + _POPUP_BAR_H))
		except Exception:
			import traceback
			print("AZ Colorflow [toolkit hub size] error:\n" + traceback.format_exc())


def _toolkit_hub() -> Any:
	"""Find-or-create the shared AZ Toolkit hub (None if it can't be hosted)."""
	try:
		pool = AppKit.NSThread.mainThread().threadDictionary()
		hub = pool.objectForKey_(_HUB_KEY)
		if hub is not None:
			return hub
		delegate = _app_delegate()
		# respondsToSelector_, not hasattr: hasattr on the bridged delegate scans
		# the entire ObjC selector table when the method is missing.
		if delegate is None or not delegate.respondsToSelector_(b"addViewToPreferences:"):
			return None
		hub = AZColorflowToolkitHub.alloc().init()
		if hub is None:
			return None
		pool.setObject_forKey_(hub, _HUB_KEY)   # retained here for the app's lifetime
		delegate.addViewToPreferences_(hub)
		return hub
	except Exception:
		import traceback
		print("AZ Colorflow [toolkit hub] error:\n" + traceback.format_exc())
		return None


def _register_preferences_pane() -> None:
	"""Add the Color Flow pane to Glyphs > Settings exactly once per app session.

	Glyphs builds one palette instance per document window, so the module-level
	_PREF_PANE_ADDED guard prevents duplicate panes. The VC + its backing view are
	retained module-globally so AppKit cannot deallocate them. Fully guarded: any
	failure only prints to the Macro panel and never breaks plugin load.
	"""
	global _PREF_PANE_ADDED, _PREF_PANE_VC, _PREF_PANE_CONTROLLER
	if _PREF_PANE_ADDED:
		return
	delegate = _app_delegate()
	# respondsToSelector_, not hasattr: hasattr on the bridged app delegate scans
	# the entire ObjC selector table when the method is missing.
	if delegate is None or not delegate.respondsToSelector_(b"addViewToPreferences:"):
		return
	controller = AZColorflowSettingsView()
	view_controller = AZColorflowPreferencesController.alloc().initWithSettingsView_(controller)
	if view_controller is None:
		return
	# title -> the Settings tab's visible label; representedObject -> the tab IDENTIFIER
	# that showMainPreferencesWithIdentifier: matches (see initWithSettingsView_). Set both
	# again here defensively in case a subclass init path skipped them.
	try:
		view_controller.setTitle_(COLORFLOW_PREF_IDENTIFIER)
	except Exception:
		pass
	try:
		view_controller.setRepresentedObject_(COLORFLOW_PREF_IDENTIFIER)
	except Exception:
		pass
	# NOTE: Glyphs builds the Settings pane toolbar entry as a TEXT button (its
	# mapTabsToToolbar reads only label + identifier), so the pane has no custom icon —
	# it shows the "Color Flow" label. Do not set representedObject to an NSImage: that
	# would become the tab identifier and break the jump.
	# Mark added BEFORE the call so a partial failure cannot re-register on the next window.
	_PREF_PANE_ADDED = True
	_PREF_PANE_CONTROLLER = controller
	_PREF_PANE_VC = view_controller
	# The pane lands as a tab in the shared "AZ Toolkit" entry; standalone fallback
	# only if the hub can't be built.
	hub = _toolkit_hub()
	if hub is not None and hub.respondsToSelector_(b"addSettingsPane:"):
		hub.addSettingsPane_(view_controller)
	else:
		delegate.addViewToPreferences_(view_controller)   # solo fallback


def _open_preferences_pane() -> None:
	"""Open Glyphs > Settings to the Color Flow pane (registering it first if needed).

	showMainPreferencesWithIdentifier: -> GSPreferencesController -showPrefpaneWithIdentifier:
	-> [mainTabView selectTabViewItemWithIdentifier: ident]. Our tab's identifier is the VC's
	representedObject, which we set to COLORFLOW_PREF_IDENTIFIER — so the jump matches. If it
	ever throws (older Glyphs / no such item), fall back to just opening Settings so the user
	still lands in the window and can click the Color Flow pane manually."""
	_register_preferences_pane()
	# Preferred path: the shared AZ Toolkit hub selects our tab and opens Settings.
	hub = _toolkit_hub()
	if hub is not None and hub.respondsToSelector_(b"showSettingsPaneWithIdentifier:"):
		try:
			hub.showSettingsPaneWithIdentifier_(COLORFLOW_PREF_IDENTIFIER)
			return
		except Exception:
			pass  # fall through to the direct jump
	delegate = _app_delegate()
	if delegate is None:
		return
	# Solo-registered pane (no hub): its top-level identifier is our own.
	# respondsToSelector_, not hasattr/getattr: those scan the entire ObjC
	# selector table on the bridged delegate when the method is missing.
	if delegate.respondsToSelector_(b"showMainPreferencesWithIdentifier:"):
		try:
			delegate.showMainPreferencesWithIdentifier_(COLORFLOW_PREF_IDENTIFIER)
			return
		except Exception:
			pass  # fall through to a plain Settings open
	for selector in (b"showMainPreferences:", b"showPreferencesPanel:",
			b"showPreferences:", b"openPreferences:"):
		try:
			if delegate.respondsToSelector_(selector):
				delegate.performSelector_withObject_(selector, None)
				return
		except Exception:
			continue


# Borderless layer-backed button with a hover effect — brightens its fill while
# the mouse is inside. Guarded with lookUpClass so a plugin reload doesn't
# re-register the ObjC class name.
try:
	_CFBuyButton = objc.lookUpClass("CFBuyButton")
except objc.error:

	class CFBuyButton(AppKit.NSButton):
		def initWithFrame_(self, frame):
			self = objc.super(CFBuyButton, self).initWithFrame_(frame)
			if self is not None:
				self._normalBG = None
				self._hoverBG = None
				self._trackingArea = None
			return self

		@objc.python_method
		def configureBG(self, normal_cg, hover_cg) -> None:
			self._normalBG = normal_cg
			self._hoverBG = hover_cg
			if self.layer() is not None and normal_cg is not None:
				self.layer().setBackgroundColor_(normal_cg)

		def updateTrackingAreas(self):
			objc.super(CFBuyButton, self).updateTrackingAreas()
			existing = getattr(self, "_trackingArea", None)
			if existing is not None:
				self.removeTrackingArea_(existing)
			opts = (
				AppKit.NSTrackingMouseEnteredAndExited
				| AppKit.NSTrackingActiveAlways
				| AppKit.NSTrackingInVisibleRect
			)
			self._trackingArea = AppKit.NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
				self.bounds(), opts, self, None)
			self.addTrackingArea_(self._trackingArea)

		def resetCursorRects(self):
			# Canonical: AppKit shows the hand over the button's bounds + restores it.
			self.addCursorRect_cursor_(self.bounds(), AppKit.NSCursor.pointingHandCursor())

		def mouseEntered_(self, event):
			AppKit.NSCursor.pointingHandCursor().set()
			if self.layer() is not None and getattr(self, "_hoverBG", None) is not None:
				self.layer().setBackgroundColor_(self._hoverBG)

		def mouseExited_(self, event):
			AppKit.NSCursor.arrowCursor().set()
			if self.layer() is not None and getattr(self, "_normalBG", None) is not None:
				self.layer().setBackgroundColor_(self._normalBG)

	_CFBuyButton = CFBuyButton


# Transparent full-row companion view that shows the pointing hand while the
# mouse hovers an openable palette row. It owns its cursor rect itself
# (resetCursorRects — the canonical AppKit way), so no NSTrackingArea with
# owner=self is needed: a tracking area RETAINS its owner, and owning it from
# the palette instance kept every AZColorflow alive forever. hitTest_ returns
# None so clicks fall through to the overlay underneath (whose double-click
# gesture recognizer opens the step tab). Guarded with lookUpClass so a plugin
# reload doesn't re-register the ObjC class name.
try:
	_CFRowHoverView = objc.lookUpClass("CFRowHoverView")
except objc.error:

	class CFRowHoverView(AppKit.NSView):
		def resetCursorRects(self):
			self.addCursorRect_cursor_(self.bounds(), AppKit.NSCursor.pointingHandCursor())

		def hitTest_(self, point):
			return None   # cursor-only: never intercept clicks meant for the row overlay

	_CFRowHoverView = CFRowHoverView


class AZColorflow(PalettePlugin):

	# Body height in the license-blocked state. Not 0 — a literal-0 body strips the
	# padding Glyphs keeps under a collapsed section header, making the band read
	# shorter than sibling sections. Tune ±2 in Glyphs until it matches.
	_BLOCKED_BODY_HEIGHT = 14


	########################################################################################################
	#																									   #
	#	SETUP																					           #
	#																									   #
	########################################################################################################
	#																									   #
	#																									   #

	@objc.python_method
	def settings(self) -> None:
		from _azcolorflow_lic_config import CONFIG
		from _azcolorflow_lic import bootstrap
		self._ent = bootstrap.start(CONFIG)
		# Publish the live Gate so the module-level "Jump to next" shortcut handler
		# (no palette instance) can consult the same licence state.
		global _SHARED_ENT
		_SHARED_ENT = self._ent
		self.name = 'AZ Colorflow'
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
			print(f"AZ Colorflow: could not load colorNames.txt ({error}); starting empty.")
			self.meaning = {}
		self.width = 160
		self.rectHeight = 10
		self.lineSpacing = 20
		self.shift = 10
		self.height = 19 * len([x for x in self.meaning.values() if x]) + 4

		self.paletteView = Window((self.width, self.height + 10))
		self.paletteView.frame = Group((0, 0, self.width, self.height))

		# Separator lines + colour tags (depend on the meaning order/visibility).
		# Per-row widgets (label / bar / count) are built by Update_Plugin_UI.
		self._rowChecks = {}
		self._rowOverlays = {}
		self._build_static_rows()

		# # Select a master if none is selected
		# if not self.font.selectedFontMaster:
		# 	self.font.selectedFontMaster = self.font.masters[0]

		# Needed to display the palette plugin
		self.dialog = self.paletteView.frame.getNSView()

		# Drive the palette height with an animatable height constraint so growing /
		# shrinking (e.g. when the Settings pane shows/hides a colour) slides instead of
		# snapping. Glyphs pins the view's width + position; we own the height.
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

	# This palette's OWN document font. Glyphs builds one palette instance per
	# document window, so Glyphs.font (the FRONTMOST font) can belong to a
	# different document while this palette's window sits in the background.
	# Falls back to Glyphs.font when the window controller is not attached yet
	# (settings() runs before the palette is docked).
	@objc.python_method
	def _palette_font(self) -> Any:
		try:
			if self._windowController:
				font = self._windowController.documentFont()
				if font is not None:
					return font
		except Exception:
			pass
		return Glyphs.font

	# Re-read colorNames.txt and rebuild the palette after a Settings-panel save.
	@objc.python_method
	def reload_after_settings(self) -> None:
		self.meaning = self.Load_Meaning()
		for i in range(12):
			for suffix in ("line", "colorTag", "", "box", "count", "hl", "click"):
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
		# The step order/visibility changed, so the cached per-step counts (keyed
		# on the OLD order) are stale — drop them before the rebuild below.
		try:
			self._invalidate_counts(self.font.selectedFontMaster.id)
		except Exception:
			pass
		self.Update_Plugin_UI()
		try:
			font = self._palette_font()
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
			_install_rainbow_menu()
			self._rainbow_conflict_check()
		except Exception:
			import traceback
			print("AZ Colorflow [Rainbow setup] error:\n" + traceback.format_exc())

		# Swap Option color routing: replace -[GSFontViewController setColorIndex:]
		# once per session (idempotent installer). Guarded like the rest — any
		# failure only prints and leaves stock routing intact.
		try:
			_install_color_routing_hook()
		except Exception:
			import traceback
			print("AZ Colorflow [routing hook] error:\n" + traceback.format_exc())

		# Native shortcut command in Glyphs > Settings > Shortcuts (remappable,
		# no Scripts-folder copying). Guarded like the Rainbow setup: a missing
		# GSCallbackHandler symbol on an older Glyphs, or any registration
		# failure, only prints to the Macro panel and never breaks plugin load.
		try:
			_register_native_shortcuts()
		except Exception:
			import traceback
			print("AZ Colorflow [shortcuts] error:\n" + traceback.format_exc())

		# Add the Color Flow pane to Glyphs > Settings exactly once per app session
		# (module-level _PREF_PANE_ADDED guard). Guarded: a failure only prints.
		try:
			_register_preferences_pane()
		except Exception:
			import traceback
			print("AZ Colorflow [prefs pane] error:\n" + traceback.format_exc())

		# Observe edits made in the global Settings pane so THIS palette refreshes live.
		try:
			from Foundation import NSNotificationCenter
			NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
				self, "colorFlowSettingsChanged:", COLORFLOW_SETTINGS_CHANGED, None)
		except Exception:
			import traceback
			print("AZ Colorflow [settings observer] error:\n" + traceback.format_exc())
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
			print("AZ Colorflow [save-observer] error:\n" + traceback.format_exc())


	########################################################################################################
	#																									   #
	#	RAINBOW FONT VIEW																			       #
	#																									   #
	########################################################################################################

	@objc.python_method
	def _font_dir(self, font) -> str | None:
		return os.path.dirname(font.filepath) if (font is not None and font.filepath) else None

	@objc.python_method
	def _generate_smart_filters(self, sender) -> None:
		# Build a smart-filter group (named azcolorflow_filters.GROUP_NAME; one
		# filter per visible step + None) and merge it into the font's Filters
		# parameter. Filters match the GLYPH colour — Glyphs has no per-master
		# layer-colour predicate.
		if self._gate():
			return
		try:
			font = Glyphs.font
			if font is None:
				Message("Open a font first.", title="AZ Colorflow")
				return
			meaning = self.Load_Meaning()
			steps = [(int(index), label)
				for index, label in colornames.visible_labels(meaning).items()]
			text = colornames.read_color_names(colornames.get_key_file(self._font_dir(font)))
			none_label = colornames.parse_settings(text)[1] or "None"
			group = azcolorflow_filters.build_filter_group(steps, none_label)
			existing = [dict(entry) for entry in (font.customParameters["Filters"] or [])]
			font.customParameters["Filters"] = azcolorflow_filters.merge_into_filters(existing, group)
			Message(f"Added the “{azcolorflow_filters.GROUP_NAME}” smart-filter group "
				"to the sidebar (filters by glyph colour).", title="AZ Colorflow")
		except Exception:
			import traceback
			print("AZ Colorflow [smart filters] error:\n" + traceback.format_exc())

	@objc.python_method
	def _popover_dashboard(self, sender) -> None:
		# The timeline records itself to the font's userData on every save (non-git
		# fonts) — no git commits, no opt-in. So generating a report just builds it.
		self._present_report_sheet()

	# Present a titled panel as a sheet on the palette window with an
	# indeterminate progress bar, then build the report on the next runloop tick
	# (so the sheet has painted) and dismiss the sheet when it opens.
	@objc.python_method
	def _present_report_sheet(self) -> None:
		# Single choke point for the report/dashboard (openDashboard_ ->
		# _popover_dashboard -> here, and the header button). Gate here so a blocked
		# licence cannot generate a report by any path.
		if self._gate():
			return
		# Re-entry guard: a report build is already running (sheet up, 30 Hz
		# loader ticking). Presenting a second sheet would orphan the first
		# panel and leave its NSTimer loader running forever.
		if getattr(self, "_reportPanel", None) is not None:
			return
		try:
			parent = self.dialog.window() if self.dialog is not None else None
			if parent is None:
				self.Open_Color_Font_Dashboard(None)
				return
			rect = AppKit.NSMakeRect(0, 0, 256, 54)   # compact, with a little breathing room top/bottom
			panel = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
				rect, AppKit.NSWindowStyleMaskTitled, AppKit.NSBackingStoreBuffered, False)
			panel.setTitle_("AZ Colorflow")
			content = panel.contentView()
			label = AppKit.NSTextField.labelWithString_("Generating AZ Colorflow report\u2026")
			label.setFrame_(AppKit.NSMakeRect(16, 30, 224, 16))
			content.addSubview_(label)
			loader = _AZColorflowLoaderBar.alloc().initWithFrame_(AppKit.NSMakeRect(16, 5, 224, 22))
			loader.configure(labelcolors.read_label_colors())
			content.addSubview_(loader)
			self._reportLoader = loader
			self._reportPanel = panel
			self._reportLabel = label
			self._reportPath = None
			parent.beginSheet_completionHandler_(panel, None)
			# Let the sheet paint once, then build on the next run-loop hop. The build
			# drives the bar with REAL progress (set_progress + run-loop pumping); when it
			# finishes the report opens automatically and the sheet closes.
			self.performSelector_withObject_afterDelay_("runReportGeneration:", None, 0.08)
		except Exception:
			import traceback
			print("AZ Colorflow [report sheet] error:\n" + traceback.format_exc())
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
			# 100% (a few timer ticks), then open the report and close the sheet.
			self.performSelector_withObject_afterDelay_("finishReportSheet:", None, 0.3)

	def finishReportSheet_(self, sender) -> None:
		self._finish_report_sheet()

	@objc.python_method
	def _finish_report_sheet(self) -> None:
		# Build finished: stop the loader, close the sheet, then ALWAYS open the report
		# (no Open/Save prompt) — in the native window, or the browser if WebKit is out.
		loader = getattr(self, "_reportLoader", None)
		if loader is not None:
			try:
				loader.stop()
			except Exception:
				pass
		path = getattr(self, "_reportPath", None)
		self._dismiss_report_sheet()
		if path is not None:
			try:
				if not _show_report_window(path):
					webbrowser.open(path.as_uri())
			except Exception:
				import traceback
				print("AZ Colorflow [open report] error:\n" + traceback.format_exc())

	# ------------------------------------------------------------------ #
	#  First-run tutorial sheet (multi-slide, arrow navigation)
	# ------------------------------------------------------------------ #

	def showTutorialIfFirstRun_(self, sender) -> None:
		# Deferred from start(). Shows the tutorial once ever (global flag), attaching a
		# sheet to the document window; falls back to a floating panel if none is found.
		try:
			if Glyphs.defaults["com.hugojourdan.AZColorflow-TutorialShown"]:
				return
			if getattr(self, "_tutorialPanel", None) is not None:
				return                                  # already on screen
			self._present_tutorial()
		except Exception:
			import traceback
			print("AZ Colorflow [tutorial] error:\n" + traceback.format_exc())

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
		import azcolorflow_tutorial
		self._tutorialSlides = azcolorflow_tutorial.slides()
		count = len(self._tutorialSlides)
		if count == 0:
			return
		self._tutorialIndex = 0
		width, height = 540, 360
		rect = AppKit.NSMakeRect(0, 0, width, height)
		panel = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
			rect, AppKit.NSWindowStyleMaskTitled, AppKit.NSBackingStoreBuffered, False)
		panel.setTitle_("Welcome to AZ Colorflow")
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

		Glyphs.defaults["com.hugojourdan.AZColorflow-TutorialShown"] = True
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
		# The handler closure retains self (and the monitor retains the handler),
		# so it self-destructs: if the tutorial panel is gone or off screen —
		# closed by any path, not just the close bubble — it removes the monitor
		# and passes the event through, breaking the retain chain.
		def _handler(event):
			try:
				panel = getattr(self, "_tutorialPanel", None)
				if panel is None or not panel.isVisible():
					monitor = getattr(self, "_tutorialKeyMonitor", None)
					self._tutorialKeyMonitor = None
					if monitor is not None:
						try:
							AppKit.NSEvent.removeMonitor_(monitor)
						except Exception:
							pass
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
			# Color Flow brand accent (#9f75ff) for the filled tutorial dot, not the
			# system accent, so the onboarding matches the report's purple.
			color = (AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(0.624, 0.459, 1.0, 1.0) if filled
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
		import azcolorflow_tutorial
		slides = getattr(self, "_tutorialSlides", [])
		count = len(slides)
		title = self._tutorialTitle
		body = self._tutorialBody
		dot_buttons = getattr(self, "_tutorialDotButtons", [])
		if count == 0 or title is None or body is None:
			return
		index = azcolorflow_tutorial.clamp_index(getattr(self, "_tutorialIndex", 0), count)
		self._tutorialIndex = index
		slide = slides[index]
		title.setStringValue_(slide.title)
		body.setStringValue_(slide.body)
		for position, dot in enumerate(dot_buttons):
			self._tutorial_set_dot(dot, position == index)

	@objc.python_method
	def _tutorial_step(self, delta: int) -> None:
		import azcolorflow_tutorial
		count = len(getattr(self, "_tutorialSlides", []))
		self._tutorialIndex = azcolorflow_tutorial.clamp_index(
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

	def colorFlowSettingsChanged_(self, notification) -> None:
		# Posted by the global Settings pane after any edit; rebuild this palette live.
		try:
			self.colorKeys = self._label_color_keys()
		except Exception:
			pass
		try:
			self.reload_after_settings()
		except Exception:
			import traceback
			print("AZ Colorflow [settings changed] error:\n" + traceback.format_exc())

	@objc.python_method
	def _rainbow_conflict_check(self) -> None:
		# Warn once if the standalone Rainbow FontView is still installed (two
		# plugins fighting over glyphOrder would conflict).
		if Glyphs.defaults["com.hugojourdan.AZColorflow-RainbowConflictWarned"]:
			return
		barItem = Glyphs.menu[FILE_MENU]
		# respondsToSelector_, not hasattr (bridged object — see _install_rainbow_menu).
		submenu = barItem.submenu() if barItem.respondsToSelector_(b"submenu") else None
		if submenu is None:
			return
		for item in list(submenu.itemArray()):
			if item.title() == "Rainbow FontView":
				Message(
					"The standalone Rainbow FontView plugin is still installed.\n\n"
					"AZ Colorflow now includes Font-View grouping, so please disable or "
					"remove Rainbow FontView to avoid them conflicting.",
					title="AZ Colorflow", OKButton=None)
				Glyphs.defaults["com.hugojourdan.AZColorflow-RainbowConflictWarned"] = True
				return

	# --- ObjC selectors (no python_method decorator: called by menu / timer) ---

	def validateMenuItem_(self, menuItem) -> bool:
		# Validates the menu items targeting the plugin instance (the context-menu
		# entries): enabled whenever a font is open. The Rainbow File-menu item
		# targets the module-level _RAINBOW_MENU_HANDLER singleton, whose own
		# validateMenuItem_ handles the on/off checkmark.
		return Glyphs.font is not None

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
			print("AZ Colorflow [Rainbow rebuild] error:\n" + traceback.format_exc())

	# --- keep our grouping order out of saved files (Cocoa save notifications) ---

	def documentDidSave_(self, notification) -> None:
		# Glyphs posts this (GSDocumentWasSavedSuccessfully) after a successful save —
		# the only save hook it offers.
		document = notification.object()
		# Scope to THIS palette's own document. The observer is registered with
		# object=None (Glyphs needs the notification before its window controller
		# resolves), and Glyphs builds one AZColorflow instance per window — so every
		# instance is told about every document's save. Ignore saves that aren't this
		# instance's, so only the owning palette records/re-saves its timeline.
		# Best-effort + null-safe: if we can't resolve our own document, fall through
		# (don't drop the notification) so behaviour degrades to the prior all-instances
		# path rather than silently doing nothing.
		try:
			own_document = self._windowController.document() if self._windowController is not None else None
		except Exception:
			own_document = None
		if own_document is not None and document is not None and document != own_document:
			return
		# Re-entrancy guard: this fire is our OWN follow-up save (below), made only to
		# flush the just-written userData to disk. Don't record or re-save again.
		if getattr(self, "_resaving", False):
			self._resaving = False
			print("AZ Colorflow: timeline persisted to disk (follow-up save).")
			return
		print("AZ Colorflow [save]: GSDocumentWasSavedSuccessfully fired.")
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
			print("AZ Colorflow [history] error:\n" + traceback.format_exc())
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
			print("AZ Colorflow [did-save] error:\n" + traceback.format_exc())
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
				print("AZ Colorflow [resave] error:\n" + traceback.format_exc())

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
			print("AZ Colorflow: no font on save — nothing recorded.")
			return False
		if not getattr(font, "filepath", None):
			print("AZ Colorflow: font has no file path yet — timeline kept in memory, "
				"persists once the file is saved to disk.")
		import azcolorflow_dashboard
		# Storage rule: git-tracked fonts keep their history in git commits, so we don't
		# *also* accrue userData snapshots (that would double-store the same timeline).
		# The report merges the frozen pre-git userData past with git going forward.
		# Untracked fonts (no repo, or not yet committed) keep writing userData so the
		# timeline still accrues for users who don't use git.
		if azcolorflow_dashboard.is_git_tracked(font):
			print("AZ Colorflow: font is git-tracked — timeline reads from git, "
				"skipping userData snapshot.")
			return False
		key = azcolorflow_dashboard.TIMELINE_USERDATA_KEY
		# Compare the encoded userData string before/after: it changes iff a new entry was
		# written (count alone is unreliable — capping can drop an old day as one is added).
		before = azcolorflow_dashboard._read_user_data(font, key)
		snapshot = azcolorflow_dashboard.build_master_glyph_colors(font)
		azcolorflow_dashboard.record_history(font, snapshot, datetime.now())
		recorded = azcolorflow_dashboard._read_user_data(font, key) != before
		try:
			saves = len(azcolorflow_dashboard.load_history(font))
			save_word = "save" if saves == 1 else "saves"
			if recorded:
				print(f"AZ Colorflow: timeline snapshot recorded to userData "
					f"({saves} {save_word} logged; flushing to disk).")
			else:
				print(f"AZ Colorflow: no colour change since last save — timeline unchanged "
					f"({saves} {save_word} logged).")
		except Exception:
			pass
		return recorded

	@objc.python_method
	def _font_from_document(self, document) -> Any:
		if document is None:
			return None
		# respondsToSelector_, not hasattr/getattr: those scan the entire ObjC
		# selector table on the bridged object when the attribute is missing.
		font = None
		try:
			if document.respondsToSelector_(b"font"):
				font = document.font()
		except Exception:
			font = None
		if (font is None and document.respondsToSelector_(b"glyphs")
				and document.respondsToSelector_(b"userData")):
			font = document  # the notification object is already a GSFont
		return font

	# ------------------------------------------------------------------ inline label rename

	@objc.python_method
	def _ns_button(self, check) -> Any:
		if hasattr(check, "getNSButton"):
			return check.getNSButton()
		return check._nsObject

	########################################################################################################
	#																									   #
	#	DATA + UI 																				           #
	#																									   #
	########################################################################################################
	#																									   #
	#																									   #

	# ------------------------------------------------------------------ derived data (tempData)

	# The exclusion set the counting threads through colornames: the names of the
	# font's non-exporting glyphs — ALWAYS excluded, they never count.
	@objc.python_method
	def _excluded_glyph_names(self) -> set:
		try:
			return colornames.non_exporting_names(self.font.glyphs)
		except Exception:
			return set()

	# A layer's checkbox state, derived from its colour: the contiguous run of
	# steps up to and including the colour.
	@objc.python_method
	def _layer_state(self, layer, order) -> dict:
		return colornames.checked_state_for_color(layer.color, order)

	# Exact per-step census for a master, derived from native layer colours: a
	# layer counts ONLY for the colour it actually has (raw census, NOT the
	# cumulative "reached this step or beyond" sum). Nothing Color Flow tracks
	# is saved in the .glyphs file. The non-exporting glyphs' colours are always
	# excluded before counting (the exclusion set is threaded through colornames).
	@objc.python_method
	def _derive_counts(self, masterId) -> dict:
		order = list(self.meaning.keys())
		named_colors = []
		for glyph in self.font.glyphs:
			layer = glyph.layers[masterId]
			named_colors.append((glyph.name, layer.color if layer is not None else None))
		colors = colornames.exclude_named_colors(named_colors, self._excluded_glyph_names())
		return colornames.single_counts_from_colors(colors, order)

	@objc.python_method
	def _counts(self, masterId) -> dict:
		key = _SHORTCUT_COUNTS_KEY + masterId
		counts = self.font.tempData[key]
		if not hasattr(counts, "keys"):
			counts = self._derive_counts(masterId)
			self.font.tempData[key] = counts
		return counts

	@objc.python_method
	def _invalidate_counts(self, masterId) -> None:
		self.font.tempData[_SHORTCUT_COUNTS_KEY + masterId] = None

	# Remember which colour a freshly built row checkbox belongs to (the widgets
	# rebuild on each refresh). Row interaction (open-tab double-click + drag-reorder)
	# lives on a full-width transparent overlay added after the count, so the
	# WHOLE row responds — see _attach_row_overlay.
	@objc.python_method
	def _register_row_checkbox(self, checkbox, color) -> None:
		self._rowChecks[color] = checkbox

	# A transparent, full-width overlay laid over each row (above the bar, label
	# and count) so a DOUBLE-click anywhere on the row opens that step's glyphs in a
	# new Edit tab. (Drag-to-reorder moved to the Settings pane; the palette row now
	# only hosts the open-tab double-click + a pointer-cursor tracking area.)
	@objc.python_method
	def _attach_row_overlay(self, color, yPos) -> None:
		overlay = Group((0, yPos - self.shift - 1, self.width, 19))
		setattr(self.paletteView.frame, str(color) + "click", overlay)
		self._rowOverlays[color] = overlay
		view = overlay._nsObject
		try:
			click = NSClickGestureRecognizer.alloc().initWithTarget_action_(self, "rowDoubleClicked:")
			click.setNumberOfClicksRequired_(2)
			view.addGestureRecognizer_(click)
		except Exception:
			pass
		# Pointing-hand cursor while hovering the row: a dedicated subview owns
		# the cursor rect (see _CFRowHoverView) — an NSTrackingArea with
		# owner=self would retain this palette instance forever.
		try:
			hover = _CFRowHoverView.alloc().initWithFrame_(view.bounds())
			hover.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
			view.addSubview_(hover)
		except Exception:
			pass

	# Resolve which colour-row a gesture recognizer is attached to (its view is
	# the row's overlay / checkbox NSButton).
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

	# Update Palette UI (original look; checkbox state + counts derived from colour).
	@objc.python_method
	def Update_Plugin_UI(self) -> None:
		try:
			if not self.font or not self.meaning:
				return
			self._rowChecks = {}
			self._rowOverlays = {}
			yPos = 13
			masterId = self.font.selectedFontMaster.id
			counts = self._counts(masterId)
			order = list(self.meaning.keys())

			selectedLayers = self.font.selectedLayers or []
			selStates = [self._layer_state(layer, order) for layer in selectedLayers]

			for color, meaning in self.meaning.items():
				for suffix in ("", "box", "count", "hl", "click"):
					attr = str(color) + suffix
					if hasattr(self.paletteView.frame, attr):
						delattr(self.paletteView.frame, attr)
				if not meaning:
					continue
				count = counts[color] if color in counts else 0

				if selectedLayers:
					check = all(state.get(color, False) for state in selStates)
					if check:
						rgb = self.colorKeys[str(color)]
						setattr(self.paletteView.frame, str(color)+"hl", Box((0, yPos-self.shift-1, self.width, 19), fillColor=AppKit.NSColor.colorWithRed_green_blue_alpha_(rgb[0], rgb[1], rgb[2], 0.16), cornerRadius=0, borderWidth=0))
					checkbox = TextBox((12, yPos-self.shift+2, -10, 20), meaning, sizeStyle='small')
					setattr(self.paletteView.frame, str(color), checkbox)
					self._register_row_checkbox(checkbox, color)
					self._make_count(color, count, yPos)
					self._attach_row_overlay(color, yPos)
					yPos += 19
				else:
					checkbox = TextBox((12, yPos-self.shift+2, -10, 20), meaning, sizeStyle='small')
					setattr(self.paletteView.frame, str(color), checkbox)
					self._register_row_checkbox(checkbox, color)
					self._make_count(color, count, yPos)
					self._attach_row_overlay(color, yPos)
					yPos += 19
			self._update_title_bar()
		except Exception:
			import traceback
			print("AZ Colorflow [Update_Plugin_UI] error:\n" + traceback.format_exc())

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
			submenu = AppKit.NSMenu.alloc().initWithTitle_("AZ Colorflow")
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
			parent = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("AZ Colorflow", None, "")
			parent.setSubmenu_(submenu)
			menu.addItem_(parent)
		except Exception:
			import traceback
			print("AZ Colorflow [context menu] error:\n" + traceback.format_exc())

	def setStepFromMenu_(self, sender) -> None:
		if self._gate():
			return
		try:
			raw = sender.representedObject()
			self._apply_step_to_selection(None if raw == "none" else int(raw))
		except Exception:
			import traceback
			print("AZ Colorflow [set step] error:\n" + traceback.format_exc())

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

	# Review Queue: DOUBLE-click a row to open exactly that step's glyphs in a
	# new Edit tab to walk through them. The count badge is a passive display.
	# (The pointing-hand hover cursor lives on the row overlay's _CFRowHoverView.)
	def rowDoubleClicked_(self, sender) -> None:
		try:
			color = self._color_for_recognizer(sender)
			if color is None:
				return
			self._open_step_tab(color)
		except Exception:
			import traceback
			print("AZ Colorflow [row double-click] error:\n" + traceback.format_exc())

	# Exact census membership, matching the count badge: a glyph is "at" this
	# step only when its layer colour IS this step (not beyond it), and the
	# non-exporting glyphs are excluded — the opened tab holds exactly the
	# badge's count of glyphs.
	@objc.python_method
	def _glyphs_for_step(self, color, masterId) -> list:
		excluded = self._excluded_glyph_names()
		names = []
		for glyph in self.font.glyphs:
			if glyph.name in excluded:
				continue
			layer = glyph.layers[masterId]
			layerColor = layer.color if layer is not None else None
			if layerColor is not None and str(layerColor) == str(color):
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
		names = self._glyphs_for_step(color, masterId)
		if not names:
			Message(f"No glyphs at \u201c{self.meaning.get(color, str(color))}\u201d.", title="AZ Colorflow")
			return
		try:
			font.newTab("/" + "/".join(names))
		except Exception:
			import traceback
			print("AZ Colorflow [open tab] error:\n" + traceback.format_exc())

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

	def openDashboard_(self, sender) -> None:
		# Report header button: same flow the old popover's report button used —
		# the loader sheet that builds the report and then offers Open / Save.
		if self._gate():
			return
		try:
			self._popover_dashboard(sender)
		except Exception:
			import traceback
			print("AZ Colorflow [header report] error:\n" + traceback.format_exc())

	@objc.python_method
	def _is_collapsed(self) -> bool:
		try:
			view = self.dialog
			if view is None or view.window() is None:
				return True
			if view.isHiddenOrHasHiddenAncestor():
				return True
			# Glyphs 4 collapses a sidebar section by shrinking the section container
			# to the header height and sliding the body OUT of it (negative origin.y),
			# not by hiding it or zeroing its height — so the old
			# visibleRect().height < 2 test never fired (it reports the header height).
			# Detect collapse by how much of the body overlaps its container's bounds:
			# ~0 when collapsed, ~full body height when expanded.
			container = view.superview()
			if container is None:
				return view.visibleRect().size.height < 2.0
			frame = view.frame()
			container_h = container.bounds().size.height
			overlap = min(frame.origin.y + frame.size.height, container_h) - max(frame.origin.y, 0.0)
			return overlap < 2.0
		except Exception:
			return False

	@objc.python_method
	def _sync_header(self) -> None:
		bar = getattr(self, "_titleBar", None)
		if bar is None:
			# Retry injection here (idempotent: _inject_title_bar no-ops once
			# _titleBar is set). The one-shot 2s deferral in deferredHeaderSetup_
			# can fire before Glyphs 4 has docked the palette / built the header,
			# and there is no repeating timer — so drive it from UPDATEINTERFACE.
			# Capped: when the title field is never found (say, a future header
			# layout), give up after a few consecutive failures instead of
			# re-walking the whole window (depth-40) on every UPDATEINTERFACE
			# forever. The counter resets on success.
			tries = getattr(self, "_headerInjectTries", 0)
			if tries >= 8:
				return
			try:
				self._inject_title_bar()
			except Exception:
				pass
			bar = getattr(self, "_titleBar", None)
			if bar is None:
				self._headerInjectTries = tries + 1
				return
			self._headerInjectTries = 0
		try:
			collapsed = self._is_collapsed()
			blocked = bool(getattr(getattr(self, "_ent", None), "blocked", False))
			# Colour bar: only in the collapsed header AND not blocked.
			bar.setHidden_(not collapsed or blocked)
			report = getattr(self, "_titleReport", None)
			buy = getattr(self, "_titleBuy", None)
			if report is not None:
				# Report: only when expanded and not blocked.
				report.setHidden_(collapsed or blocked)
			if buy is not None:
				# Buy: whenever blocked — the only affordance while gated, and the
				# palette body is collapsed, so it must not depend on collapse state.
				buy.setHidden_(not blocked)
			lock = getattr(self, "_titleLock", None)
			if lock is not None:
				lock.setHidden_(not blocked)
			title_field = getattr(self, "_titleField", None)
			if title_field is not None:
				# Dim the plugin name to signal the disabled (trial-expired) state.
				title_field.setAlphaValue_(0.25 if blocked else 1.0)
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
			print("AZ Colorflow [header setup] error:\n" + traceback.format_exc())

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
		# Depth cap generous enough for Glyphs 4's deeper sidebar nesting
		# (GSSidebarStackView > NSView > GSSidebarHeaderView > NSStackView > title
		# NSTextField lands ~13 deep; G3's old cap of 12 silently missed it).
		if view is None or depth > 40:
			return None
		try:
			if view.isKindOfClass_(AppKit.NSTextField):
				value = str(view.stringValue() or "")
				# Match the live palette title (self.name), not a hardcoded string —
				# the rename to "AZ Colorflow" broke the old "Color Flow" literal, which
				# silently skipped the header injection (no report button, no colour bar).
				# Case-insensitive so a header that upper-cases the title still matches.
				if self.name and self.name.lower() in value.lower():
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
			# Glyphs 4's section header is a horizontal NSStackView (auto-layout), so
			# manual-frame addSubview_ children don't lay out there. Add our controls as
			# ARRANGED subviews with explicit size constraints; the stack positions them
			# and honours setHidden_ (which _sync_header already toggles) by reflowing.
			# Glyphs 3's plain-NSView header keeps the original absolute-frame path.
			is_stack = bool(header.isKindOfClass_(AppKit.NSStackView))
			def _add(view, width=None, height=None):
				if is_stack:
					view.setTranslatesAutoresizingMaskIntoConstraints_(False)
					# Insert right after the title (index 0), BEFORE Glyphs's own
					# disclosure chevron + "⋯" menu, so those stay to the right of our
					# bar/report. (Appending would put our controls rightmost instead.)
					header.insertArrangedSubview_atIndex_(view, 1)
					if width is not None:
						view.widthAnchor().constraintEqualToConstant_(width).setActive_(True)
					if height is not None:
						view.heightAnchor().constraintEqualToConstant_(height).setActive_(True)
				else:
					header.addSubview_(view)
			btn = 14.0
			pad = 8.0
			ctrlY = (bounds.size.height - btn) / 2.0
			# Eye button removed (visibility now lives in Settings); report is rightmost.
			reportX = bounds.size.width - pad - btn
			barWidth, barHeight = 48.0, 6.0   # narrow; leaves room for the native disclosure chevron on its right
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
			_add(bar, barWidth, barHeight)
			self._titleBar = bar
			# Remember the intended bar size. As an arranged subview the stack
			# collapses the bar's width to 0 while it is hidden (the expanded state),
			# so _update_title_bar can't trust bar.bounds() when it computes the fill.
			self._barSize = (barWidth, barHeight)
			report = AppKit.NSButton.alloc().initWithFrame_(((reportX, ctrlY), (btn, btn)))
			report.setBordered_(False)
			report.setAutoresizingMask_(AppKit.NSViewMinXMargin)
			report.setTarget_(self)
			report.setAction_("openDashboard:")
			report.setImageScaling_(AppKit.NSImageScaleProportionallyDown)
			try:
				reportImg = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_("list.clipboard.fill", None)
				if reportImg is None:
					reportImg = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_("doc.text", None)
				if reportImg is not None:
					# Render the list.clipboard.fill symbol at SEMIBOLD WEIGHT (Hugo's pick) so it reads heavier than
					# the default regular. Symbol weight needs a point size; tie it to the 14pt button.
					try:
						weight = getattr(AppKit, "NSFontWeightSemibold", 0.3)
						scale = getattr(AppKit, "NSImageSymbolScaleMedium", 2)
						cfg = AppKit.NSImageSymbolConfiguration.configurationWithPointSize_weight_scale_(
							float(btn) * 0.66, weight, scale)
						configured = reportImg.imageWithSymbolConfiguration_(cfg)
						if configured is not None:
							reportImg = configured
					except Exception:
						pass
					report.setImage_(reportImg)
				else:
					report.setTitle_("\U0001F4CA")
			except Exception:
				pass
			_add(report, btn, btn)
			self._titleReport = report
			# Buy button — an orange pill (filled, rounded, white text) so it clearly
			# reads as a button. Right-aligned in the header, shown only while blocked
			# (replaces the report button + colour bar).
			# Original 80×16 pill, narrowed in steps to 38 wide (64 -> 48 -> 38).
			buyW, buyH = 38.0, 13.0
			buyX = bounds.size.width - pad - buyW
			buyY = (bounds.size.height - buyH) / 2.0
			buy = _CFBuyButton.alloc().initWithFrame_(((buyX, buyY), (buyW, buyH)))
			buy.setBordered_(False)
			buy.setAutoresizingMask_(AppKit.NSViewMinXMargin)
			buy.setTarget_(self)
			buy.setAction_("buyLicense:")
			buy.setWantsLayer_(True)
			buyText = AppKit.NSColor.colorWithRed_green_blue_alpha_(0.91, 0.61, 0.24, 1.0)  # bright amber-orange
			try:
				# Solid dark-amber capsule + bright orange label; brightens on hover.
				buy.layer().setCornerRadius_(buyH / 2.0)
				buy.layer().setMasksToBounds_(True)
				buy.configureBG(
					AppKit.NSColor.colorWithRed_green_blue_alpha_(0.42, 0.31, 0.13, 1.0).CGColor(),
					AppKit.NSColor.colorWithRed_green_blue_alpha_(0.51, 0.38, 0.16, 1.0).CGColor())
			except Exception:
				pass
			try:
				attrs = {
					AppKit.NSForegroundColorAttributeName: buyText,
					AppKit.NSFontAttributeName: AppKit.NSFont.systemFontOfSize_weight_(
						10, getattr(AppKit, "NSFontWeightMedium", 0.23)),
				}
				buy.setAttributedTitle_(
					AppKit.NSAttributedString.alloc().initWithString_attributes_("Buy", attrs))
			except Exception:
				buy.setTitle_("Buy")
			buy.setHidden_(True)
			_add(buy, buyW, buyH)
			self._titleBuy = buy
			# Lock glyph after the plugin name; the name is dimmed when disabled.
			self._titleField = field
			try:
				fr = field.frame()
				try:
					text_w = field.attributedStringValue().size().width
				except Exception:
					text_w = 70.0
				try:
					title_pt = field.font().pointSize()
				except Exception:
					title_pt = 11.0
				lockX = fr.origin.x + text_w + 5.0
				# Match the plugin-name field's exact vertical box + point size so the
				# lock glyph centers on the same baseline as the name.
				lock = AppKit.NSTextField.alloc().initWithFrame_(((lockX, fr.origin.y), (18.0, fr.size.height)))
				lock.setEditable_(False)
				lock.setSelectable_(False)
				lock.setBordered_(False)
				lock.setDrawsBackground_(False)
				lock.setAutoresizingMask_(AppKit.NSViewMaxXMargin)
				lock.setFont_(AppKit.NSFont.systemFontOfSize_(title_pt))
				lock.setTextColor_(AppKit.NSColor.secondaryLabelColor())
				lock.setStringValue_("􀎡")  # SF Symbol lock (renders in the system font)
				lock.setHidden_(True)
				_add(lock, 18.0, fr.size.height)
				self._titleLock = lock
			except Exception:
				pass
			self._sync_header()
			# Draw the completion fill once now: injection can happen via the
			# _sync_header retry path (not just deferredHeaderSetup_), which would
			# otherwise leave the bar empty until the next counts-changing update.
			self._update_title_bar()
		except Exception:
			import traceback
			print("AZ Colorflow [title bar] error:\n" + traceback.format_exc())

	@objc.python_method
	def _teardown_title_bar(self) -> None:
		# Remove the subviews _inject_title_bar added into the long-lived, window-owned
		# section header. The header outlives this palette instance, so without this they
		# orphan and stack across reloads (the reinjection guard at _inject_title_bar
		# lives on the NEW instance, so a reload would inject a second control set over the
		# stale orphans whose buttons still target a dead instance). Null-safe + idempotent:
		# guards each attr and tolerates a double teardown / partial init.
		for attr in ("_titleBar", "_titleReport", "_titleBuy", "_titleLock"):
			view = getattr(self, attr, None)
			if view is not None:
				try:
					view.removeFromSuperview()
				except Exception:
					pass
			setattr(self, attr, None)
		field = getattr(self, "_titleField", None)
		if field is not None:
			try:
				field.setAlphaValue_(1.0)
			except Exception:
				pass
		self._titleField = None

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
			# Reuse the cached per-step census (same derivation, same exclusion
			# set) instead of recounting the whole font on every header sync.
			exclusive = self._counts(masterId)
			# Use the intended bar size, not bar.bounds(): while the bar is hidden
			# (expanded state) the stack collapses its width to 0, which would zero
			# every fill segment and leave the bar empty once collapsed.
			size = getattr(self, "_barSize", None)
			if size is not None:
				width, height = size
			else:
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

	@objc.python_method
	def _gate(self) -> bool:
		# True when the licence is blocked (trial expired / unlicensed). Nags once
		# per session via the bootstrap Gate, then returns True so callers early-out.
		# Wire every guarded feature through this so a blocked palette is inert, not
		# just visually collapsed.
		ent = getattr(self, "_ent", None)
		blocked = bool(ent and getattr(ent, "blocked", False))
		if blocked:
			try:
				ent.nag()
			except Exception:
				pass
		return blocked

	# UPDATEINTERFACE handler: cheap dirty-check on selection + layer colours.
	@objc.python_method
	def update(self, sender) -> None:
		ent = getattr(self, "_ent", None)
		if ent is not None and ent.blocked:
			self._showBlockedState_()
			return
		self._clearBlockedState_()
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
		# Two-part signature: WHICH layers are selected (names) and WHAT colours
		# they carry. The selection part only gates the UI rebuild; the cached
		# per-step counts are derived from layer COLOURS, so they are dropped only
		# when the colour part changed for the SAME selection (a swatch click /
		# undo) or the master switched — a pure selection move (arrow keys) keeps
		# the cache and skips the 3-4 full-font recounts per keystroke.
		selection = tuple(
			(layer.parent.name if layer.parent is not None else "")
			for layer in selectedLayers)
		colors = tuple(layer.color for layer in selectedLayers)
		signature = (masterId, selection, colors)
		last = getattr(self, "_lastSignature", None)
		if signature == last:
			return
		self._lastSignature = signature
		colors_changed = (
			last is None
			or last[0] != masterId
			or (last[1] == selection and last[2] != colors))
		if colors_changed:
			self._invalidate_counts(masterId)
		self.Update_Plugin_UI()

	@objc.python_method
	def _showBlockedState_(self) -> None:
		# Block the palette from opening: clear the rows and collapse the body to
		# nothing, leaving only the section header with the orange "Buy Licence →"
		# button. Idempotent (update() fires on every UPDATEINTERFACE).
		if getattr(self, "_blockedShown", False):
			return
		try:
			group = self.paletteView.frame
			# Clear per-row widgets (same idiom as Update_Plugin_UI).
			for color in list(getattr(self, "meaning", {}).keys()):
				for suffix in ("", "box", "count", "hl", "click"):
					attr = str(color) + suffix
					if hasattr(group, attr):
						delattr(group, attr)
			if hasattr(group, "_cfLockMsg"):
				delattr(group, "_cfLockMsg")
			self._blockedShown = True
			# Not 0: a literal-0 body strips the padding Glyphs keeps under a collapsed
			# section header, so the band reads shorter than sibling sections. Leave a
			# sliver matching the natural collapsed height. Tune ±2 in Glyphs to match.
			self._set_palette_height(self._BLOCKED_BODY_HEIGHT, animated=False)
			self._sync_header()
		except Exception:
			import traceback
			print("AZ Colorflow [blocked state] error:\n" + traceback.format_exc())

	@objc.python_method
	def _clearBlockedState_(self) -> None:
		# Restore the palette body after the block lifts so normal rows rebuild.
		# Idempotent.
		if not getattr(self, "_blockedShown", False):
			return
		try:
			group = self.paletteView.frame
			if hasattr(group, "_cfLockMsg"):
				delattr(group, "_cfLockMsg")
			self._blockedShown = False
			visible = len([x for x in getattr(self, "meaning", {}).values() if x])
			self._set_palette_height(19 * visible + 4, animated=False)
			self._sync_header()
		except Exception:
			import traceback
			print("AZ Colorflow [clear blocked] error:\n" + traceback.format_exc())

	@objc.python_method
	def _onLicenseChanged(self) -> None:
		try:
			from _azcolorflow_lic_config import CONFIG
			from _azcolorflow_lic import bootstrap
			self._ent = bootstrap.start(CONFIG)
			# Keep the shortcut handler's shared Gate in sync after activation.
			global _SHARED_ENT
			_SHARED_ENT = self._ent
			self._clearBlockedState_()
			self._update_title_bar()
			self.update(None)
		except Exception:
			import traceback
			print("AZ Colorflow [license refresh] error:\n" + traceback.format_exc())

	def buyLicense_(self, sender) -> None:
		# Title-bar affordance shown while blocked: offer Buy (de-branded LS
		# checkout sheet) OR Enter Key (activation sheet). The Enter-Key path
		# refreshes entitlement live via _onLicenseChanged so the palette
		# unlocks without a Glyphs reload.
		try:
			from _azcolorflow_lic_config import CONFIG
			from _azcolorflow_lic import bootstrap
			from AppKit import (
				NSAlert,
				NSAlertFirstButtonReturn,
				NSAlertSecondButtonReturn,
			)
			alert = NSAlert.alloc().init()
			alert.setMessageText_("AZ Colorflow")
			alert.setInformativeText_("Buy a license, or enter a key you already have.")
			alert.addButtonWithTitle_("Buy License")
			alert.addButtonWithTitle_("Enter Key…")
			alert.addButtonWithTitle_("Cancel")
			response = alert.runModal()
			if response == NSAlertFirstButtonReturn:
				bootstrap.show_buy_sheet(CONFIG)
			elif response == NSAlertSecondButtonReturn:
				bootstrap.show_license_ui(CONFIG, on_activated=self._onLicenseChanged)
		except Exception:
			import traceback
			print("AZ Colorflow [buy] error:\n" + traceback.format_exc())

	########################################################################################################
	#																									   #
	#	EXTRA FEATURES																					   #
	#																									   #
	########################################################################################################
	#																									   #
	#																									   #

	# Open the HTML Color Font Dashboard for the current font (per-master colour
	# distribution + what changed since last run).
	@objc.python_method
	def Open_Color_Font_Dashboard(self, sender) -> None:
		self._run_dashboard(None)

	@objc.python_method
	def _run_dashboard(self, progress=None, open_when_done: bool = True) -> Any:
		# ``progress`` (optional ``Callable[[float], None]``) is forwarded to
		# azcolorflow_dashboard.main so the report-sheet loader can track real build
		# progress; None when opened outside the sheet flow. Returns the written report
		# Path (or None) so the sheet flow can offer Open / Save instead of auto-opening.
		try:
			import azcolorflow_dashboard
			return azcolorflow_dashboard.main(Glyphs.font, progress=progress, open_when_done=open_when_done)
		except Exception:
			import traceback
			print("AZ Colorflow [dashboard] error:\n" + traceback.format_exc())
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
	# colornames module so the palette and the jump shortcut script can
	# never diverge (see tools/generate_shortcuts.py).
	@objc.python_method
	def Load_Meaning(self) -> dict:
		# Resolve against this palette's OWN font (not the frontmost one): a
		# background window's palette must keep reading its own per-font-dir
		# colorNames.txt, whatever document is frontmost.
		fontDir = None
		font = self._palette_font()
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
		# NOTE: the Rainbow File-menu item is now installed ONCE per session against a
		# retained module-level singleton (_RAINBOW_MENU_HANDLER), so it deliberately
		# OUTLIVES this instance — closing one window must not strip the entry the other
		# open windows still use. Hence no per-instance menu teardown here.
		# Remove the section-header subviews this instance injected into the long-lived,
		# window-owned header (else they orphan + stack dead-target controls on reload).
		try:
			self._teardown_title_bar()
		except Exception:
			pass
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

	# ------------------------------------------------------------------ palette height

	# Animate the palette height via the height constraint's animator proxy (the
	# technique the Glyphs team documents for smooth palette resizing). Falls back
	# to a direct, un-animated resize if the constraint could not be created. Driven
	# by reload_after_settings when a Settings-pane edit changes the visible count.
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

