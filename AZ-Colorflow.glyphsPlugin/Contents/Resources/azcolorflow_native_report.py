"""Native AppKit replica of the HTML Color Flow report.

Renders the SAME model dict ``azcolorflow_dashboard.build_model`` produces (no
second data pipeline) in a chromeless NSWindow that mirrors the HTML report's
look: dark JetBrains Mono dashboard, Overview / Timeline toolbar, the master
tower on the left, cards, stacked colour bars, the glyph heatmap, charts, the
month calendar.

Rendering is immediate-mode: each ``update()`` re-lays the page out into draw
ops + hit regions on flipped ``_Canvas`` views (the JS rebuilds innerHTML the
same way), so there is no per-widget NSView zoo to keep in sync. All maths lives
in ``azcolorflow_native_model`` (pure Python, unit-tested); this file is only
geometry + paint + events.

ponytail: no CSS animations (bar intros, ring sweep, disc spin, crossfades) —
static paint. Add a 60Hz NSTimer on the tower if the spin is missed.
"""

from __future__ import annotations

import calendar as _calendar
import colorsys
import json
import math
import random
import re
from typing import Any

import AppKit
import objc
from azcolorflow_native_model import (
    MONTHS_LONG,
    NO_COLOR,
    TL_SPANS,
    ReportModel,
    date_label,
    pct,
    pretty_script,
    rank_arrow,
    smooth_segments,
)
from Foundation import NSObject

try:  # CoreImage drives the disc / script-tile blur; without it they render crisp
    import Quartz
except ImportError:  # pragma: no cover
    Quartz = None

# --------------------------------------------------------------------------- #
# Design tokens (the report's :root / html[data-theme=light] blocks)
# --------------------------------------------------------------------------- #

DARK = {
    "bg": "#0a0b0e",
    "surface": "#0e1014",
    "surface2": "#101217",
    "border": "#1c1f26",
    "border2": "#23262e",
    "text": "#e6e8ec",
    "muted": "#9aa0ab",
    "muted2": "#6b7280",
    "accent": "#9f75ff",
    "ok": "#3fb950",
    "track": "#15171c",
    "swatch_outline": (1.0, 1.0, 1.0, 0.10),
    "tl_dot": "#ffffff",
    "tl_vgrid": (1.0, 1.0, 1.0, 0.10),
    "none_a": "#0e1116",
    "none_b": "#3a3f4a",
}
LIGHT = {
    "bg": "#f6f7f9",
    "surface": "#ffffff",
    "surface2": "#f1f3f6",
    "border": "#e3e6ea",
    "border2": "#d6dae0",
    "text": "#15171c",
    "muted": "#5b6270",
    "muted2": "#8b919c",
    "accent": "#9f75ff",
    "ok": "#1a7f37",
    "track": "#eceef2",
    "swatch_outline": (20 / 255, 24 / 255, 33 / 255, 0.18),
    "tl_dot": "#15171c",
    "tl_vgrid": (20 / 255, 24 / 255, 33 / 255, 0.10),
    "none_a": "#dfe3e9",
    "none_b": "#aab2bf",
}
STEP_COLORS = [
    "#f97e55",
    "#ffbe68",
    "#ba9d6d",
    "#fff157",
    "#c1ec8a",
    "#6bab59",
    "#64a5ef",
    "#576ef1",
    "#a962e7",
    "#e77eb4",
    "#c5c5c5",
    "#5f5f5f",
]
FS_BASE, FS_ROW, FS_SM, FS_XS, FS_2XS, FS_BIG, FS_BIG_SM = 15.0, 14.0, 13.0, 12.0, 11.5, 46.0, 24.0
PAGE_MAX_W = 1180.0
PAGE_PAD = 20.0
TOWER_W = 240.0
MAIN_GAP = 24.0
BODY_PAD_R = 6.0
WINDOW_TITLE_BAND = 40.0  # the chromeless titlebar/traffic-light band the HTML host pads for

_FONT_CACHE: dict = {}
_COLOR_CACHE: dict = {}


def _hex_rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return tuple(int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def rgba(spec: Any, alpha: float | None = None) -> Any:
    """NSColor from "#hex" / (r,g,b[,a]) tuples, sRGB, cached. NSColors pass through."""
    if isinstance(spec, AppKit.NSColor):
        return spec if alpha is None else spec.colorWithAlphaComponent_(alpha)
    key = (spec, alpha)
    cached = _COLOR_CACHE.get(key)
    if cached is not None:
        return cached
    if isinstance(spec, str):
        r, g, b = _hex_rgb(spec)
        a = 1.0
    else:
        r, g, b = spec[0], spec[1], spec[2]
        a = spec[3] if len(spec) > 3 else 1.0
    if alpha is not None:
        a = alpha
    color = AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, a)
    _COLOR_CACHE[key] = color
    return color


def _comps(spec: Any) -> tuple[float, float, float, float]:
    if isinstance(spec, str):
        r, g, b = _hex_rgb(spec)
        return r, g, b, 1.0
    return spec[0], spec[1], spec[2], (spec[3] if len(spec) > 3 else 1.0)


def mix(a: Any, b: Any, t: float) -> tuple[float, float, float, float]:
    """CSS color-mix(in srgb, a t, b 1-t) — ``t`` is the share of ``a``."""
    ar, ag, ab, aa = _comps(a)
    br, bg, bb, ba = _comps(b)
    return (
        ar * t + br * (1 - t),
        ag * t + bg * (1 - t),
        ab * t + bb * (1 - t),
        aa * t + ba * (1 - t),
    )


def saturate(spec: Any, factor: float, bright: float = 1.0) -> tuple[float, float, float, float]:
    r, g, b, a = _comps(spec)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    r2, g2, b2 = colorsys.hsv_to_rgb(h, min(1.0, s * factor), min(1.0, v * bright))
    return (r2, g2, b2, a)


def font(size: float, weight: int = 400) -> Any:
    """JetBrains Mono at the CSS weight (falls back to the system monospace)."""
    key = (size, weight)
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    face = "JetBrainsMono-Regular"
    if weight >= 600:
        face = "JetBrainsMono-Bold"
    elif weight >= 500:
        face = "JetBrainsMono-Medium"
    result = AppKit.NSFont.fontWithName_size_(face, size)
    if result is None:
        ns_weight = 0.0
        if weight >= 600:
            ns_weight = getattr(AppKit, "NSFontWeightSemibold", 0.3)
        elif weight >= 500:
            ns_weight = getattr(AppKit, "NSFontWeightMedium", 0.23)
        ctor = getattr(AppKit.NSFont, "monospacedSystemFontOfSize_weight_", None)
        result = ctor(size, ns_weight) if ctor else AppKit.NSFont.userFixedPitchFontOfSize_(size)
    _FONT_CACHE[key] = result
    return result


class Theme:
    """The active token set + the 12 step colours (model overrides win)."""

    def __init__(self, tokens: dict, colors: dict | None = None) -> None:
        self.t = tokens
        self.steps = list(STEP_COLORS)
        for key, value in (colors or {}).items():
            try:
                index = int(key)
            except (TypeError, ValueError):
                continue
            if 0 <= index < 12 and isinstance(value, str) and value.startswith("#"):
                self.steps[index] = value

    def __getitem__(self, name: str) -> Any:
        return rgba(self.t[name])

    def raw(self, name: str) -> Any:
        return self.t[name]

    def step(self, key: Any) -> Any:
        """Colour spec for a step key (-1 -> the solid none-b grey)."""
        try:
            index = int(key)
        except (TypeError, ValueError):
            return self.t["none_b"]
        if 0 <= index < 12:
            return self.steps[index]
        return self.t["none_b"]

    def is_dark(self) -> bool:
        return self.t is DARK


# --------------------------------------------------------------------------- #
# Paint helpers (run inside drawRect_ of a flipped view)
# --------------------------------------------------------------------------- #


def rrect(x: float, y: float, w: float, h: float, r: float = 0.0) -> Any:
    rect = AppKit.NSMakeRect(x, y, max(0.0, w), max(0.0, h))
    if r <= 0:
        return AppKit.NSBezierPath.bezierPathWithRect_(rect)
    r = min(r, w / 2.0, h / 2.0)
    return AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, r, r)


def fill(path: Any, color: Any, shadow: tuple | None = None) -> None:
    """Fill a path; ``shadow=(spec, blur)`` adds a CSS-style 0 0 blur box-shadow."""
    if shadow is not None:
        AppKit.NSGraphicsContext.saveGraphicsState()
        ns_shadow = AppKit.NSShadow.alloc().init()
        ns_shadow.setShadowColor_(rgba(shadow[0]))
        ns_shadow.setShadowBlurRadius_(shadow[1])
        ns_shadow.setShadowOffset_((0.0, 0.0))
        ns_shadow.set()
        rgba(color).set()
        path.fill()
        AppKit.NSGraphicsContext.restoreGraphicsState()
        return
    rgba(color).set()
    path.fill()


def stroke(path: Any, color: Any, width: float = 1.0) -> None:
    rgba(color).set()
    path.setLineWidth_(width)
    path.stroke()


def box(
    x: float, y: float, w: float, h: float, color: Any, r: float = 0.0, shadow: tuple | None = None
) -> None:
    fill(rrect(x, y, w, h, r), color, shadow)


def frame(
    x: float, y: float, w: float, h: float, color: Any, r: float = 0.0, width: float = 1.0
) -> None:
    # inset by half the line so a 1px border sits crisp inside the box
    inset = width / 2.0
    stroke(rrect(x + inset, y + inset, w - width, h - width, max(0.0, r - inset)), color, width)


def hline(x0: float, x1: float, y: float, color: Any, width: float = 1.0) -> None:
    box(min(x0, x1), y, abs(x1 - x0), width, color)


def circle(cx: float, cy: float, r: float) -> Any:
    return AppKit.NSBezierPath.bezierPathWithOvalInRect_(
        AppKit.NSMakeRect(cx - r, cy - r, 2 * r, 2 * r)
    )


def hatch(x: float, y: float, w: float, h: float, theme: Theme, path: Any | None = None) -> None:
    """The ``--c-none`` remainder: 135deg stripes, 5px none-a / 1px none-b."""
    AppKit.NSGraphicsContext.saveGraphicsState()
    (path or rrect(x, y, w, h)).addClip()
    box(x, y, w, h, theme.raw("none_a"))
    lines = AppKit.NSBezierPath.bezierPath()
    lines.setLineWidth_(1.0)
    offset = -h
    while offset < w + h:
        lines.moveToPoint_((x + offset, y + h))
        lines.lineToPoint_((x + offset + h, y))
        offset += 6.0
    rgba(theme.raw("none_b")).set()
    lines.stroke()
    AppKit.NSGraphicsContext.restoreGraphicsState()


def measure(text: str, fnt: Any) -> tuple[float, float]:
    attributed = AppKit.NSAttributedString.alloc().initWithString_attributes_(
        text, {AppKit.NSFontAttributeName: fnt}
    )
    size = attributed.size()
    return float(size.width), float(size.height)


def text(
    value: str,
    x: float,
    y: float,
    fnt: Any,
    color: Any,
    align: str = "left",
    width: float | None = None,
    kern: float = 0.0,
    truncate: bool = False,
) -> float:
    """Draw one line at (x, y) top-left (flipped view). ``width`` enables right /
    center alignment and tail truncation. Returns the drawn width."""
    style = AppKit.NSMutableParagraphStyle.alloc().init()
    style.setAlignment_({"left": 0, "center": 1, "right": 2}[align])
    style.setLineBreakMode_(
        AppKit.NSLineBreakByTruncatingTail if truncate else AppKit.NSLineBreakByClipping
    )
    attrs = {
        AppKit.NSFontAttributeName: fnt,
        AppKit.NSForegroundColorAttributeName: rgba(color),
        AppKit.NSParagraphStyleAttributeName: style,
    }
    if kern:
        attrs[AppKit.NSKernAttributeName] = kern
    attributed = AppKit.NSAttributedString.alloc().initWithString_attributes_(value, attrs)
    size = attributed.size()
    box_w = width if width is not None else float(size.width) + 2.0
    attributed.drawInRect_(AppKit.NSMakeRect(x, y, box_w, float(size.height) + 2.0))
    return float(size.width)


def line_height(fnt: Any) -> float:
    return float(measure("Ag", fnt)[1])


_PATH_CACHE: dict = {}


def svg_path(
    d: str, vb: str, x: float, y: float, w: float, h: float, pad: float = 0.0
) -> Any | None:
    """NSBezierPath for one of the model's outline SVGs (M/L/C/Z, absolute ints),
    fitted into (x, y, w, h) like ``preserveAspectRatio="xMidYMid meet"``. Parsed
    once per (outline, box) and translated per call, so a 1000-cell heatmap
    re-layout costs copies, not parses."""
    key = (d, vb, w, h, pad)
    base = _PATH_CACHE.get(key)
    if base is None:
        base = _parse_svg_path(d, vb, w, h, pad)
        if base is None:
            return None
        if len(_PATH_CACHE) > 20000:
            _PATH_CACHE.clear()
        _PATH_CACHE[key] = base
    path = base.copy()
    transform = AppKit.NSAffineTransform.transform()
    transform.translateXBy_yBy_(x, y)
    path.transformUsingAffineTransform_(transform)
    return path


def _parse_svg_path(d: str, vb: str, w: float, h: float, pad: float) -> Any | None:
    try:
        vx, vy, vw, vh = (float(part) for part in vb.split())
    except (ValueError, AttributeError):
        return None
    if vw <= 0 or vh <= 0:
        return None
    scale = min((w - 2 * pad) / vw, (h - 2 * pad) / vh)
    ox = (w - vw * scale) / 2.0 - vx * scale
    oy = (h - vh * scale) / 2.0 - vy * scale
    path = AppKit.NSBezierPath.bezierPath()
    for cmd, args in re.findall(r"([MLCZ])([^MLCZ]*)", d):
        nums = [float(n) for n in args.split()]
        if cmd == "M" and len(nums) >= 2:
            path.moveToPoint_((ox + nums[0] * scale, oy + nums[1] * scale))
        elif cmd == "L" and len(nums) >= 2:
            path.lineToPoint_((ox + nums[0] * scale, oy + nums[1] * scale))
        elif cmd == "C" and len(nums) >= 6:
            path.curveToPoint_controlPoint1_controlPoint2_(
                (ox + nums[4] * scale, oy + nums[5] * scale),
                (ox + nums[0] * scale, oy + nums[1] * scale),
                (ox + nums[2] * scale, oy + nums[3] * scale),
            )
        elif cmd == "Z":
            path.closePath()
    path.setWindingRule_(AppKit.NSNonZeroWindingRule)
    return path


def _union_vb(a: Any, b: Any) -> str:
    def parse(value: Any) -> list[float] | None:
        try:
            parts = [float(p) for p in str(value or "").split()]
        except ValueError:
            return None
        return parts if len(parts) == 4 else None

    pa, pb = parse(a), parse(b)
    if pa is None and pb is None:
        return "0 0 1000 1000"
    if pa is None:
        return str(b)
    if pb is None:
        return str(a)
    x0, y0 = min(pa[0], pb[0]), min(pa[1], pb[1])
    x1, y1 = max(pa[0] + pa[2], pb[0] + pb[2]), max(pa[1] + pa[3], pb[1] + pb[3])
    return f"{x0} {y0} {x1 - x0} {y1 - y0}"


def arc_path(cx: float, cy: float, r: float, start_deg: float, span_deg: float) -> Any:
    """Arc from ``start_deg`` (0 = 3 o'clock, clockwise-positive on screen) over ``span_deg``."""
    path = AppKit.NSBezierPath.bezierPath()
    path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
        (cx, cy), r, start_deg, start_deg + span_deg, False
    )
    return path


def smooth_bezier(points: list[tuple[float, float]]) -> Any:
    path = AppKit.NSBezierPath.bezierPath()
    if not points:
        return path
    path.moveToPoint_(points[0])
    for c1, c2, end in smooth_segments(points):
        path.curveToPoint_controlPoint1_controlPoint2_(end, c1, c2)
    return path


def gradient(*stops: tuple) -> Any:
    """NSGradient from (color, location) stops (the variadic ObjC initialiser can't bridge)."""
    colors = [rgba(color) for color, _ in stops]
    locations = [float(loc) for _, loc in stops]
    return AppKit.NSGradient.alloc().initWithColors_atLocations_colorSpace_(
        colors, locations, AppKit.NSColorSpace.sRGBColorSpace()
    )


def seg_path(x: float, y: float, w: float, h: float, r_left: float, r_right: float) -> Any:
    """A bar segment: rounded on the sides that touch the bar's ends only."""
    path = AppKit.NSBezierPath.bezierPath()
    rl, rr = min(r_left, w / 2.0, h / 2.0), min(r_right, w / 2.0, h / 2.0)
    path.moveToPoint_((x + rl, y))
    path.lineToPoint_((x + w - rr, y))
    if rr:
        path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
            (x + w - rr, y + rr), rr, -90.0, 0.0, False
        )
    path.lineToPoint_((x + w, y + h - rr))
    if rr:
        path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
            (x + w - rr, y + h - rr), rr, 0.0, 90.0, False
        )
    path.lineToPoint_((x + rl, y + h))
    if rl:
        path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
            (x + rl, y + h - rl), rl, 90.0, 180.0, False
        )
    path.lineToPoint_((x, y + rl))
    if rl:
        path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
            (x + rl, y + rl), rl, 180.0, 270.0, False
        )
    path.closePath()
    return path


def gradient_rect(
    x: float, y: float, w: float, h: float, top: Any, bottom: Any, clip: Any | None = None
) -> None:
    AppKit.NSGraphicsContext.saveGraphicsState()
    (clip or rrect(x, y, w, h)).addClip()
    grad = AppKit.NSGradient.alloc().initWithStartingColor_endingColor_(rgba(top), rgba(bottom))
    grad.drawFromPoint_toPoint_options_((x, y), (x, y + h), 0)
    AppKit.NSGraphicsContext.restoreGraphicsState()


def radial(cx: float, cy: float, r: float, inner: Any, outer: Any, clip: Any | None = None) -> None:
    AppKit.NSGraphicsContext.saveGraphicsState()
    (clip or circle(cx, cy, r)).addClip()
    grad = AppKit.NSGradient.alloc().initWithStartingColor_endingColor_(rgba(inner), rgba(outer))
    grad.drawFromCenter_radius_toCenter_radius_options_((cx, cy), 0.0, (cx, cy), r, 0)
    AppKit.NSGraphicsContext.restoreGraphicsState()


# --------------------------------------------------------------------------- #
# Immediate-mode canvas
# --------------------------------------------------------------------------- #


class AZColorflowNativeCanvas(AppKit.NSView):
    """Flipped view that replays a list of draw closures and hit-tests a list of
    (rect, handler) regions. ``owner`` gets key events and scroll (tower)."""

    def initWithFrame_(self, frame):  # noqa: N802
        self = objc.super(AZColorflowNativeCanvas, self).initWithFrame_(frame)
        if self is None:
            return None
        self._ops: list = []
        self._hits: list = []
        self._tips: dict = {}
        self._bg = None
        self._owner = None
        self._wheel = None
        self._hover = None
        return self

    def isFlipped(self):  # noqa: N802
        return True

    def acceptsFirstResponder(self):  # noqa: N802
        return True

    def isOpaque(self):  # noqa: N802
        return self._bg is not None

    @objc.python_method
    def reset(self, bg: Any) -> None:
        self._ops = []
        self._hits = []
        self._bg = bg
        self.removeAllToolTips()
        self._tips = {}

    @objc.python_method
    def op(self, fn) -> None:
        self._ops.append(fn)

    @objc.python_method
    def hit(self, x: float, y: float, w: float, h: float, fn, cursor: bool = True) -> None:
        self._hits.append((AppKit.NSMakeRect(x, y, w, h), fn))

    @objc.python_method
    def tip(self, x: float, y: float, w: float, h: float, value: str) -> None:
        tag = self.addToolTipRect_owner_userData_(AppKit.NSMakeRect(x, y, w, h), self, None)
        self._tips[tag] = value

    @objc.typedSelector(b"@@:@q{CGPoint=dd}^v")
    def view_stringForToolTip_point_userData_(self, view, tag, point, data):  # noqa: N802
        return self._tips.get(tag, "")

    def drawRect_(self, rect):  # noqa: N802
        if self._bg is not None:
            rgba(self._bg).set()
            AppKit.NSRectFill(self.bounds())
        for op in self._ops:
            try:
                op()
            except Exception:
                import traceback

                print("AZ Colorflow [native report draw] error:\n" + traceback.format_exc())

    def mouseDown_(self, event):  # noqa: N802
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        for rect, fn in reversed(self._hits):
            if AppKit.NSPointInRect(point, rect):
                try:
                    fn(event)
                except Exception:
                    import traceback

                    print("AZ Colorflow [native report click] error:\n" + traceback.format_exc())
                return
        window = self.window()
        if window is not None and self._wheel is None:
            window.makeFirstResponder_(self)

    def scrollWheel_(self, event):  # noqa: N802
        if self._wheel is not None:
            self._wheel(event)
        else:
            objc.super(AZColorflowNativeCanvas, self).scrollWheel_(event)

    def keyDown_(self, event):  # noqa: N802
        owner = self._owner
        if owner is not None and owner.handle_key(event):
            return
        objc.super(AZColorflowNativeCanvas, self).keyDown_(event)


_Canvas = AZColorflowNativeCanvas


class AZColorflowNativeDragStrip(AppKit.NSView):
    """Transparent top band: drags the chromeless window (same trick as the HTML host)."""

    def mouseDown_(self, event):  # noqa: N802
        window = self.window()
        if window is not None:
            window.performWindowDragWithEvent_(event)


# --------------------------------------------------------------------------- #
# The report controller
# --------------------------------------------------------------------------- #


class AZColorflowNativeReport(NSObject):
    """Owns the window and the four canvases (header, toolbar, body, footer) plus
    the tower; ``update()`` re-lays everything out from ``state`` + ``model``."""

    def initWithModel_(self, model: dict):  # noqa: N802
        self = objc.super(AZColorflowNativeReport, self).init()
        if self is None:
            return None
        self.model = ReportModel(model)
        self.theme = Theme(DARK, self.model.colors)
        self.state: dict = {
            "master": None,
            "view": "tabs",
            "before": False,
            "focus": None,
            "ovExpand": {},
            "heatSort": "category",
            "heatRecent": False,
            "cellSize": 40,
            "tlPane": "graph",
            "tlScrub": None,
            "viewLo": None,
            "viewHi": None,
            "tlSpan": None,
            "calY": None,
            "calM": None,
            "ocOpen": {},
            "funnelOpen": False,
        }
        self._window = None
        self._disc_cache: dict = {}
        self._frost = None
        self._tower_vt = 0.0
        self._tower_geo: dict = {}
        self._rot = -0.5
        self._spin_timer = None
        self._spin_t = 0.0
        self._overlay_cache: dict = {}
        return self

    # ----- window ----------------------------------------------------------------------
    @objc.python_method
    def show(self, title: str | None = None) -> Any:
        window = self._ensure_window()
        if title:
            window.setTitle_(title)
        window.makeKeyAndOrderFront_(None)
        self.update()
        self._start_spin()
        return window

    @objc.python_method
    def _ensure_window(self) -> Any:
        if self._window is not None:
            return self._window
        rect = AppKit.NSMakeRect(0, 0, PAGE_MAX_W, 840)
        mask = (
            AppKit.NSWindowStyleMaskTitled
            | AppKit.NSWindowStyleMaskClosable
            | AppKit.NSWindowStyleMaskMiniaturizable
            | AppKit.NSWindowStyleMaskResizable
            | AppKit.NSWindowStyleMaskFullSizeContentView
        )
        window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, mask, AppKit.NSBackingStoreBuffered, False
        )
        window.setReleasedWhenClosed_(False)
        window.setMinSize_(AppKit.NSMakeSize(800, 600))
        window.setFrameAutosaveName_("AZColorflowNativeReportWindow")
        window.setTitlebarAppearsTransparent_(True)
        window.setTitleVisibility_(AppKit.NSWindowTitleHidden)
        window.setTitle_("AZ Colorflow")
        self._apply_appearance(window)

        root = _Canvas.alloc().initWithFrame_(rect)
        root.reset(self.theme.raw("bg"))
        self.header = _Canvas.alloc().initWithFrame_(rect)
        self.toolbar = _Canvas.alloc().initWithFrame_(rect)
        self.footer = _Canvas.alloc().initWithFrame_(rect)
        self.tower = _Canvas.alloc().initWithFrame_(rect)
        self.body = _Canvas.alloc().initWithFrame_(rect)
        for canvas in (self.header, self.toolbar, self.footer, self.tower, self.body):
            canvas._owner = self
        self.tower._wheel = self._tower_wheel
        scroll = AppKit.NSScrollView.alloc().initWithFrame_(rect)
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(False)
        scroll.setAutohidesScrollers_(True)
        scroll.setBorderType_(AppKit.NSNoBorder)
        scroll.setDrawsBackground_(False)
        scroll.setScrollerStyle_(AppKit.NSScrollerStyleOverlay)
        scroll.setDocumentView_(self.body)
        self.scroll = scroll
        for view in (self.header, self.toolbar, self.tower, scroll, self.footer):
            root.addSubview_(view)
        strip = AZColorflowNativeDragStrip.alloc().initWithFrame_(rect)
        root.addSubview_(strip)
        self._strip = strip
        window.setContentView_(root)
        self._root = root
        window.setDelegate_(self)
        AppKit.NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self, "windowResized:", AppKit.NSWindowDidResizeNotification, window
        )
        self._window = window
        self._layout_frames()
        return window

    @objc.python_method
    def _apply_appearance(self, window: Any) -> None:
        name = (
            AppKit.NSAppearanceNameDarkAqua if self.theme.is_dark() else AppKit.NSAppearanceNameAqua
        )
        try:
            window.setAppearance_(AppKit.NSAppearance.appearanceNamed_(name))
            window.setBackgroundColor_(self.theme["bg"])
        except Exception:
            pass

    def windowResized_(self, note):  # noqa: N802
        self._layout_frames()
        self.update()

    # ----- disc spin ---------------------------------------------------------------------
    # The JS auto-spins the tower at ~60fps with a 1.5s smoothstep ease-in, and the
    # Glyphs host pauses it while the report is not the key window: a spinning canvas
    # forces a repaint through the host's main thread every frame. Same etiquette here:
    # the timer runs only while the window is key + visible, never under Reduce Motion.
    SPIN_SPEED = 0.00768
    SPIN_RAMP = 1.0 / 90.0

    @objc.python_method
    def _motion_ok(self) -> bool:
        try:
            reduce = AppKit.NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceMotion()
        except Exception:
            reduce = False
        return not reduce

    @objc.python_method
    def _start_spin(self) -> None:
        window = self._window
        if self._spin_timer is not None or window is None or not self._motion_ok():
            return
        if not window.isKeyWindow():
            return
        timer = AppKit.NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / 60.0, self, "spinTick:", None, True
        )
        AppKit.NSRunLoop.currentRunLoop().addTimer_forMode_(timer, AppKit.NSRunLoopCommonModes)
        self._spin_timer = timer

    @objc.python_method
    def _stop_spin(self) -> None:
        if self._spin_timer is not None:
            self._spin_timer.invalidate()
            self._spin_timer = None

    def spinTick_(self, timer):  # noqa: N802
        if self._spin_t < 1.0:
            self._spin_t = min(1.0, self._spin_t + self.SPIN_RAMP)
        ramp = self._spin_t * self._spin_t * (3.0 - 2.0 * self._spin_t)
        self._rot += self.SPIN_SPEED * ramp
        self.tower.setNeedsDisplay_(True)

    def windowDidBecomeKey_(self, note):  # noqa: N802
        self._start_spin()

    def windowDidResignKey_(self, note):  # noqa: N802
        self._stop_spin()

    def windowDidChangeOcclusionState_(self, note):  # noqa: N802
        window = self._window
        visible = window is not None and bool(
            window.occlusionState() & AppKit.NSWindowOcclusionStateVisible
        )
        if visible:
            self._start_spin()
        else:
            self._stop_spin()

    def windowWillClose_(self, note):  # noqa: N802
        self._stop_spin()

    @objc.python_method
    def _page_metrics(self) -> tuple[float, float, float]:
        """(page x, page width, content height) — the HTML #cfd-app box."""
        bounds = self._root.bounds()
        total_w = float(bounds.size.width)
        page_w = min(PAGE_MAX_W, total_w)
        page_x = (total_w - page_w) / 2.0 + PAGE_PAD
        return page_x, page_w - 2 * PAGE_PAD, float(bounds.size.height)

    @objc.python_method
    def _layout_frames(self) -> None:
        if self._window is None:
            return
        page_x, page_w, total_h = self._page_metrics()
        root_w = float(self._root.bounds().size.width)
        header_h = 57.0
        toolbar_h = 56.0
        footer_h = 66.0
        top = WINDOW_TITLE_BAND

        # the root canvas is flipped, so subview frames are top-down like the page
        def place(
            view: Any, y_top: float, h: float, x: float = 0.0, w: float | None = None
        ) -> None:
            width = root_w if w is None else w
            view.setFrame_(AppKit.NSMakeRect(x, y_top, width, h))

        place(self._strip, 0.0, top)
        place(self.header, top, header_h)
        place(self.toolbar, top + header_h, toolbar_h)
        main_top = top + header_h + toolbar_h
        main_h = max(100.0, total_h - main_top - footer_h)
        place(self.tower, main_top, main_h, page_x, TOWER_W)
        body_x = page_x + TOWER_W + MAIN_GAP
        place(self.scroll, main_top, main_h, body_x, page_w - TOWER_W - MAIN_GAP)
        place(self.footer, main_top + main_h, footer_h)

    # ----- state helpers ---------------------------------------------------------------------
    @objc.python_method
    def scrub_index(self) -> int:
        return self.model.scrub_index(self.state["tlScrub"])

    @objc.python_method
    def scrub_set(self, index: int) -> None:
        dates = self.model.dates
        if not dates:
            return
        clamped = max(0, min(len(dates) - 1, index))
        self.state["tlScrub"] = None if clamped == len(dates) - 1 else clamped
        self._disc_cache = {}
        self.update()

    @objc.python_method
    def set_focus(self, key) -> None:
        self.state["focus"] = key
        self._disc_cache = {}
        self.update()

    @objc.python_method
    def set_master(self, master_id) -> None:
        self.state["master"] = None if self.state["master"] == master_id else master_id
        self.state["focus"] = None
        self.update()

    @objc.python_method
    def toggle_view(self, name: str) -> None:
        if name == "timeline" and self.model.timeline_lock():
            return
        self.state["view"] = "tabs" if self.state["view"] == name else name
        self.update()

    @objc.python_method
    def set_span(self, span: str) -> None:
        self.state["tlSpan"] = span
        lo, hi = self.model.span_bounds(span)
        self.state["viewLo"], self.state["viewHi"] = lo, hi
        self.update()

    @objc.python_method
    def reset_timeline_window(self) -> None:
        self.state["tlScrub"] = None
        self.state["viewLo"] = self.state["viewHi"] = None
        self.state["tlSpan"] = None

    @objc.python_method
    def handle_key(self, event: Any) -> bool:
        chars = event.charactersIgnoringModifiers() or ""
        code = event.keyCode()
        if code == 53:  # Escape
            if self.state["focus"] is not None:
                self.set_focus(None)
            return True
        if code in (125, 126):  # down / up: switch the focused master
            masters = self.model.masters
            if not masters:
                return True
            cur = self.model.master_index(self.state["master"])
            step = 1 if code == 125 else -1
            if cur < 0:
                nxt = 0 if step > 0 else len(masters) - 1
            else:
                nxt = max(0, min(len(masters) - 1, cur + step))
            self.state["master"] = masters[nxt]["id"]
            self.state["focus"] = None
            self.update()
            return True
        if code in (123, 124) and self.state["view"] == "timeline":  # left / right: step the moment
            self.scrub_set(self.scrub_index() + (1 if code == 124 else -1))
            return True
        return bool(chars) and False

    # ----- update ------------------------------------------------------------------------------
    @objc.python_method
    def update(self) -> None:
        if self._window is None:
            return
        self._root.reset(self.theme.raw("bg"))
        self._root.setNeedsDisplay_(True)
        self._layout_header()
        self._layout_toolbar()
        self._layout_body()
        self._layout_footer()
        self._layout_tower()
        for canvas in (self.header, self.toolbar, self.body, self.footer, self.tower):
            canvas.setNeedsDisplay_(True)

    # ----- header ------------------------------------------------------------------------------
    @objc.python_method
    def _layout_header(self) -> None:
        th = self.theme
        canvas = self.header
        canvas.reset(th.raw("bg"))
        page_x, page_w, _ = self._page_metrics()
        h = float(canvas.bounds().size.height)
        cy = h / 2.0
        model = self.model.h
        logo = model.get("logo") or {}
        if logo.get("d"):
            try:
                vx, vy, vw, vh = (float(p) for p in str(logo.get("vb", "")).split())
                logo_w = 22.0 * vw / vh if vh else 60.0
            except ValueError:
                logo_w = 60.0
            path = svg_path(logo["d"], logo.get("vb", ""), page_x, cy - 11, logo_w, 22.0)
            if path is not None:
                canvas.op(lambda p=path: fill(p, th.raw("text")))
        else:
            fam = str(model.get("family") or "")
            fnt = font(FS_BASE, 600)
            lh = line_height(fnt)
            canvas.op(lambda: text(fam, page_x, cy - lh / 2.0, fnt, th.raw("text")))
        # right cluster: streak badge, export, theme
        x_right = page_x + page_w
        icon_w, icon_h = 30.0, 28.0
        for label, action in (("◐", self._toggle_theme), ("􀈂", self._export_menu)):
            x_right -= icon_w
            xi, yi = x_right, cy - icon_h / 2.0
            canvas.op(lambda xi=xi, yi=yi: frame(xi, yi, icon_w, icon_h, th.raw("border2"), 7.0))
            fnt = font(13.0)
            lh = line_height(fnt)
            canvas.op(
                lambda xi=xi, yi=yi, label=label, fnt=fnt, lh=lh: text(
                    label, xi, yi + (icon_h - lh) / 2.0, fnt, th.raw("muted"), "center", icon_w
                )
            )
            canvas.hit(xi, yi, icon_w, icon_h, lambda e, action=action: action())
            x_right -= 10.0
        streak = (self.model.trend.get("streak") or {}).get("current") if self.model.trend else None
        if streak:
            fnt = font(FS_XS)
            label = f"🔥 {streak}"
            tw, lh = measure(label, fnt)
            bw, bh = tw + 18.0, lh + 8.0
            x_right -= bw
            xb, yb = x_right, cy - bh / 2.0
            canvas.op(
                lambda xb=xb, yb=yb, bw=bw, bh=bh: frame(xb, yb, bw, bh, th.raw("border2"), 7.0)
            )
            canvas.op(
                lambda xb=xb, yb=yb, bw=bw, lh=lh, fnt=fnt, label=label, bh=bh: text(
                    label, xb, yb + (bh - lh) / 2.0, fnt, th.raw("text"), "center", bw
                )
            )
            best = (self.model.trend.get("streak") or {}).get("best") or 0
            tip = f"Progress streak: {streak} day{'s' if streak != 1 else ''} in a row"
            if best > streak:
                tip += f" · best {best}"
            canvas.tip(xb, yb, bw, bh, tip)
        canvas.op(lambda: hline(0, float(canvas.bounds().size.width), h - 1, th.raw("border")))

    @objc.python_method
    def _toggle_theme(self) -> None:
        self.theme = Theme(LIGHT if self.theme.is_dark() else DARK, self.model.colors)
        self._disc_cache = {}
        self._frost = None
        self._overlay_cache = {}
        _COLOR_CACHE.clear()
        if self._window is not None:
            self._apply_appearance(self._window)
        self.update()

    @objc.python_method
    def _export_menu(self) -> None:
        menu = AppKit.NSMenu.alloc().initWithTitle_("Export")
        for title, action in (("Export CSV…", "exportCSV:"), ("Export JSON…", "exportJSON:")):
            item = menu.addItemWithTitle_action_keyEquivalent_(title, action, "")
            item.setTarget_(self)
        event = AppKit.NSApp().currentEvent()
        if event is not None:
            AppKit.NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self.header)

    @objc.python_method
    def _export_rows(self) -> list[dict]:
        model = self.model
        total = model.counted_total()
        rows = []
        for master in model.masters:
            for step in model.steps:
                count = model.count_for(master, step["key"])
                rows.append(
                    {
                        "master": master["name"],
                        "step": step["key"],
                        "label": step["label"],
                        "count": count,
                        "total": total,
                        "pct": pct(count, total),
                    }
                )
            un = model.uncolored_for(master)
            rows.append(
                {
                    "master": master["name"],
                    "step": "None",
                    "label": model.none_label,
                    "count": un,
                    "total": total,
                    "pct": pct(un, total),
                }
            )
        return rows

    @objc.python_method
    def _save_export(self, ext: str, content: str) -> None:
        h = self.model.h
        family = re.sub(r"[^\w.-]+", "-", str(h.get("family") or "font"))
        panel = AppKit.NSSavePanel.savePanel()
        panel.setNameFieldStringValue_(f"{h.get('generated', '')}_{family}_Color-Flow.{ext}")
        if panel.runModal() != AppKit.NSModalResponseOK:
            return
        url = panel.URL()
        if url is not None:
            with open(url.path(), "w", encoding="utf-8") as handle:
                handle.write(content)

    def exportCSV_(self, sender):  # noqa: N802
        h = self.model.h

        def cell(value: Any) -> str:
            s = "" if value is None else str(value)
            return '"' + s.replace('"', '""') + '"' if re.search(r'[",\n]', s) else s

        lines = [
            f"{cell(k)},{cell(v)}"
            for k, v in (
                ("Family", h.get("family")),
                ("File", h.get("fileName")),
                ("Version", h.get("version")),
                ("Generated", h.get("generated")),
                ("Glyphs", h.get("glyphTotal")),
            )
        ]
        lines += ["", "Master,Step,Label,Count,Total,Percent"]
        for row in self._export_rows():
            lines.append(
                ",".join(cell(row[k]) for k in ("master", "step", "label", "count", "total", "pct"))
            )
        self._save_export("csv", "\n".join(lines))

    def exportJSON_(self, sender):  # noqa: N802
        h, model = self.model.h, self.model
        payload = {
            "family": h.get("family"),
            "fileName": h.get("fileName"),
            "version": h.get("version"),
            "generated": h.get("generated"),
            "glyphTotal": h.get("glyphTotal"),
            "steps": model.steps,
            "nonExporting": model.non_exporting,
            "masters": [
                {
                    "id": m["id"],
                    "name": m["name"],
                    "counts": {k: model.count_for(m, k) for k in model.order},
                    "uncolored": model.uncolored_for(m),
                    "started": model.started_of(m),
                    "total": model.counted_total(),
                }
                for m in model.masters
            ],
        }
        self._save_export("json", json.dumps(payload, indent=2))

    # ----- toolbar ---------------------------------------------------------------------------------
    @objc.python_method
    def _chip(
        self,
        canvas: _Canvas,
        x: float,
        y: float,
        label: str,
        pressed: bool,
        action,
        small: bool = False,
        disabled: bool = False,
        tip: str | None = None,
    ) -> float:
        th = self.theme
        size = FS_2XS if small else FS_XS
        fnt = font(size)
        tw, lh = measure(label, fnt)
        pad_x, pad_y = (8.0, 4.0) if small else (10.0, 6.0)
        box_h = max(lh, size * 1.5)
        w, h = tw + 2 * pad_x + 2, box_h + 2 * pad_y
        pad_y += (box_h - lh) / 2.0
        if pressed:
            canvas.op(lambda: box(x, y, w, h, mix(th.raw("accent"), (0, 0, 0, 0), 0.16), 7.0))
            canvas.op(lambda: frame(x, y, w, h, th.raw("accent"), 7.0))
            color = th.raw("text")
        else:
            alpha = 0.45 if disabled else 1.0  # .chip[aria-disabled=true]{opacity:.45}
            canvas.op(lambda: box(x, y, w, h, rgba(th.raw("surface2"), alpha), 7.0))
            canvas.op(lambda: frame(x, y, w, h, rgba(th.raw("border2"), alpha), 7.0))
            color = rgba(th.raw("muted"), alpha)
        canvas.op(lambda: text(label, x, y + pad_y, fnt, color, "center", w))
        if not disabled:
            canvas.hit(x, y, w, h, lambda e: action())
        if tip:
            canvas.tip(x, y, w, h, tip)
        return w

    @objc.python_method
    def _segsw(
        self,
        canvas: _Canvas,
        x: float,
        y: float,
        items: list[tuple[str, Any]],
        active: int,
        small_pad: float = 12.0,
    ) -> tuple[float, float]:
        """The sliding-pill segmented switch (.segsw). Returns (width, height)."""
        th = self.theme
        fnt = font(FS_2XS)
        fnt_b = font(FS_2XS, 600)
        lh = max(line_height(fnt), FS_2XS * 1.5)
        widths = [
            max(measure(label, fnt_b)[0], measure(label, fnt)[0]) + 2 * small_pad
            for label, _ in items
        ]
        seg_w = max(widths) if widths else 0.0
        h = lh + 6.0 + 4.0
        w = seg_w * len(items) + 4.0
        canvas.op(lambda: box(x, y, w, h, th.raw("track"), 7.0))
        if 0 <= active < len(items):
            hx = x + 2.0 + active * seg_w
            canvas.op(
                lambda hx=hx: box(
                    hx,
                    y + 2.0,
                    seg_w,
                    h - 4.0,
                    mix(th.raw("accent"), "#15131c", 0.52),
                    5.0,
                    shadow=(mix(th.raw("accent"), (0, 0, 0, 0), 0.16), 3.0),
                )
            )
        for index, (label, action) in enumerate(items):
            bx = x + 2.0 + index * seg_w
            on = index == active
            ty = y + 5.0 + (lh - line_height(fnt)) / 2.0
            canvas.op(
                lambda bx=bx, label=label, on=on, ty=ty: text(
                    label,
                    bx,
                    ty,
                    fnt_b if on else fnt,
                    "#ffffff" if on else th.raw("muted"),
                    "center",
                    seg_w,
                )
            )
            canvas.hit(bx, y, seg_w, h, lambda e, action=action: action())
        return w, h

    @objc.python_method
    def _layout_toolbar(self) -> None:
        th = self.theme
        canvas = self.toolbar
        canvas.reset(th.raw("bg"))
        page_x, page_w, _ = self._page_metrics()
        h = float(canvas.bounds().size.height)
        x = page_x
        y = 12.0
        w = self._chip(canvas, x, y, "⌂ Overview", self.state["view"] == "tabs", self._go_overview)
        x += w + 8.0
        lock = self.model.timeline_lock()
        self._chip(
            canvas,
            x,
            y,
            "📈 Timeline",
            self.state["view"] == "timeline",
            lambda: self.toggle_view("timeline"),
            disabled=bool(lock),
            tip=lock or None,
        )
        canvas.op(lambda: hline(0, float(canvas.bounds().size.width), h - 1, th.raw("border")))

    @objc.python_method
    def _go_overview(self) -> None:
        self.state["view"] = "tabs"
        self.state["master"] = None
        self.update()

    # ----- footer ----------------------------------------------------------------------------------
    @objc.python_method
    def _layout_footer(self) -> None:
        th = self.theme
        canvas = self.footer
        canvas.reset(th.raw("bg"))
        page_x, page_w, _ = self._page_metrics()
        h = self.model.h
        fnt = font(10.0)
        canvas.op(lambda: hline(page_x, page_x + page_w, 24.0, th.raw("border")))
        left = f"{h.get('fileName', '')} · v{h.get('version', '')}"
        right = f"AZ Colorflow Report — {h.get('generated', '')}"
        canvas.op(lambda: text(left, page_x, 37.0, fnt, th.raw("muted2")))
        canvas.op(lambda: text(right, page_x, 37.0, fnt, th.raw("muted2"), "right", page_w))

    # ----- body ------------------------------------------------------------------------------------
    @objc.python_method
    def _layout_body(self) -> None:
        canvas = self.body
        canvas.reset(None)
        width = float(self.scroll.contentSize().width) - BODY_PAD_R
        x = 0.0
        y = 0.0
        if self.state["view"] == "timeline":
            y = self._timeline_view(canvas, x, y, width)
        else:
            y = self._tabs_view(canvas, x, y, width)
        height = max(y + 8.0, float(self.scroll.contentSize().height))
        canvas.setFrameSize_(AppKit.NSMakeSize(width + BODY_PAD_R, height))

    @objc.python_method
    def _tabs_view(self, canvas: _Canvas, x: float, y: float, w: float) -> float:
        if self.state["master"] is None:
            y = self._overall(canvas, x, y, w)
            return self._overview_extras(canvas, x, y, w)
        master = self.model.master_by_id(self.state["master"])
        if master is None:
            return y
        y = self._version_card(canvas, x, y, w)
        y = self._master_overall(canvas, master, x, y, w)
        y = self._category_coverage(canvas, x, y, w)
        y = self._script_coverage(canvas, x, y, w)
        return self._heatmap(canvas, master, x, y, w)

    # ----- Overview: ring + legend ---------------------------------------------------------------
    @objc.python_method
    def _ring(
        self, canvas: _Canvas, x: float, y: float, p: int, segs: list[dict], big: bool, select: bool
    ) -> float:
        th = self.theme
        sz = 78.0 if big else 52.0
        cc = sz / 2.0
        sw = 10.0 if big else 5.0
        r = cc - sw / 2.0 - 2.0
        cx, cy = x + cc, y + cc
        focus = self.state["focus"]
        canvas.op(lambda: stroke(circle(cx, cy, r), th.raw("track"), sw))
        if segs:
            acc = -90.0
            for seg in segs:
                span = max(0.0, min(1.0, seg.get("frac") or 0.0)) * 360.0
                if span <= 0.01:
                    continue
                on = select and focus == seg["key"]
                off = select and focus is not None and not on
                color = th.step(seg["key"])
                alpha = 0.28 if off else 1.0

                def draw(acc=acc, span=span, color=color, alpha=alpha) -> None:
                    AppKit.NSGraphicsContext.saveGraphicsState()
                    path = arc_path(cx, cy, r, acc, span)
                    path.setLineWidth_(sw)
                    rgba(color, alpha).set()
                    path.stroke()
                    AppKit.NSGraphicsContext.restoreGraphicsState()

                canvas.op(draw)
                acc += span
        else:
            span = 360.0 * max(0, min(100, p)) / 100.0
            canvas.op(
                lambda span=span: stroke(arc_path(cx, cy, r, -90.0, span), th.raw("accent"), sw)
            )
        fnt = font(18.0, 500) if big else font(12.5, 600)
        lh = line_height(fnt)
        label = f"{p}%"
        canvas.op(lambda: text(label, x, cy - lh / 2.0, fnt, th.raw("text"), "center", sz))
        return sz

    @objc.python_method
    def _overall(self, canvas: _Canvas, x: float, y: float, w: float) -> float:
        th, model = self.theme, self.model
        agg = model.aggregate()
        comp = model.graded_overall_pct()
        ex = model.agg_exclusive()
        grand = agg["grand"] or 1
        segs = [
            {
                "key": s["key"],
                "label": s["label"],
                "frac": (ex["dist"].get(str(s["key"])) or 0) / grand,
            }
            for s in model.steps
        ]
        y += 16.0  # .overall margin
        top = y
        pad_x, pad_y = 16.0, 12.0
        ring_sz = 78.0
        # legend: 3-column grid, gap 4 x 44, items 12px, padding 2 7
        fnt = font(FS_XS)
        lh = line_height(fnt)
        item_h = lh + 4.0
        cols = 3
        legend_x = x + pad_x + ring_sz + 40.0
        legend_w = w - (legend_x - x) - pad_x
        col_ws = [0.0] * cols
        for index, step in enumerate(model.steps):
            count = ex["dist"].get(str(step["key"])) or 0
            need = (
                7.0
                + 11.0
                + 8.0
                + measure(str(step["label"]), fnt)[0]
                + 44.0
                + measure(f"{round(count / grand * 100)}%", fnt)[0]
                + 7.0
            )
            col_ws[index % cols] = max(col_ws[index % cols], need)
        scale = min(1.0, (legend_w - 44.0 * (cols - 1)) / max(1.0, sum(col_ws)))
        col_ws = [cw * scale for cw in col_ws]
        col_xs = [legend_x + sum(col_ws[:c]) + 44.0 * c for c in range(cols)]
        rows = math.ceil(len(model.steps) / cols) if model.steps else 0
        legend_h = rows * item_h + max(0, rows - 1) * 4.0
        content_h = max(ring_sz, legend_h)
        card_h = content_h + 2 * pad_y
        canvas.op(lambda: box(x, top, w, card_h, th.raw("surface"), 12.0))
        canvas.op(lambda: frame(x, top, w, card_h, th.raw("border"), 12.0))
        ring_y = top + pad_y + (content_h - ring_sz) / 2.0
        self._ring(canvas, x + pad_x, ring_y, comp, segs, True, True)
        # ring arcs are clickable colour selectors: one hit rect per step wedge is overkill,
        # so the ring toggles focus via the legend (same data-fkey), matching the JS labels.
        legend_y = top + pad_y + (content_h - legend_h) / 2.0
        focus = self.state["focus"]
        for index, step in enumerate(model.steps):
            key = step["key"]
            count = ex["dist"].get(str(key)) or 0
            p = round(count / grand * 100)
            col, row = index % cols, index // cols
            col_w = col_ws[col]
            ix = col_xs[col]
            iy = legend_y + row * (item_h + 4.0)
            on = focus == key
            off = focus is not None and not on
            band = (index % 6) in (3, 4, 5)
            if on:
                canvas.op(
                    lambda ix=ix, iy=iy, col_w=col_w: box(
                        ix, iy, col_w, item_h, th.raw("surface2"), 6.0
                    )
                )
            elif band:
                canvas.op(
                    lambda ix=ix, iy=iy, col_w=col_w: box(
                        ix, iy, col_w, item_h, mix(th.raw("text"), (0, 0, 0, 0), 0.05), 6.0
                    )
                )
            alpha = 0.4 if off else 1.0
            sw_y = iy + (item_h - 11.0) / 2.0
            color = th.step(key)
            canvas.op(
                lambda ix=ix, sw_y=sw_y, color=color, alpha=alpha: fill(
                    rrect(ix + 7.0, sw_y, 11.0, 11.0, 3.0), rgba(color, alpha)
                )
            )
            canvas.op(
                lambda ix=ix, sw_y=sw_y, alpha=alpha: stroke(
                    rrect(ix + 7.5, sw_y + 0.5, 10.0, 10.0, 2.5),
                    rgba(th.raw("swatch_outline"), 0.10 * alpha),
                )
            )
            label = str(step["label"])
            text_color = rgba(th.raw("text"), alpha)
            pct_color = rgba(th.raw("muted"), alpha)
            canvas.op(
                lambda ix=ix, iy=iy, label=label, text_color=text_color, col_w=col_w: text(
                    label,
                    ix + 7.0 + 11.0 + 8.0,
                    iy + 2.0,
                    fnt,
                    text_color,
                    "left",
                    col_w - 26.0 - 44.0,
                    truncate=True,
                )
            )
            canvas.op(
                lambda ix=ix, iy=iy, p=p, pct_color=pct_color, col_w=col_w: text(
                    f"{p}%", ix, iy + 2.0, fnt, pct_color, "right", col_w - 7.0
                )
            )
            canvas.hit(
                ix,
                iy,
                col_w,
                item_h,
                lambda e, key=key: self.set_focus(None if self.state["focus"] == key else key),
            )
            canvas.tip(ix, iy, col_w, item_h, f"{label} — {count} glyphs ({p}%)")
        return top + card_h

    # ----- Overview: This week + Furthest along --------------------------------------------------
    @objc.python_method
    def _card_header(
        self, canvas: _Canvas, x: float, y: float, w: float, title: str, expand: str | None = None
    ) -> float:
        th = self.theme
        fnt = font(FS_2XS, 600)
        lh = line_height(fnt)
        canvas.op(lambda: text(title.upper(), x, y, fnt, th.raw("muted"), kern=FS_2XS * 0.05))
        if expand:
            canvas.op(lambda: text(expand, x, y, fnt, th.raw("accent"), "right", w))
        return lh + 10.0

    @objc.python_method
    def _leaderboard(self, canvas: _Canvas, x: float, y: float, w: float) -> float:
        th, model = self.theme, self.model
        rows = model.leaderboard_rows()
        top = y
        pad_x, pad_y = 16.0, 14.0
        start = len(canvas._ops)
        cx, cy = x + pad_x, y + pad_y
        cw = w - 2 * pad_x
        cy += self._card_header(canvas, cx, cy, cw, "Furthest along")
        cols = 2
        col_gap = 30.0
        col_w = (cw - col_gap) / cols
        fnt = font(FS_XS)
        lh = line_height(fnt)
        row_h = lh + 6.0
        per_col = math.ceil(len(rows) / cols) if rows else 0
        for index, row in enumerate(rows):
            col, r = index % cols, index // cols
            rx = cx + col * (col_w + col_gap)
            ry = cy + r * row_h
            # nth-child(4n+3)/(4n+4) stripes: every second visual row across both columns
            if (index % 4) in (2, 3):
                canvas.op(
                    lambda rx=rx, ry=ry: box(
                        rx, ry, col_w, row_h, mix(th.raw("text"), (0, 0, 0, 0), 0.05), 5.0
                    )
                )
            selected = row["id"] == self.state["master"]
            name_w = col_w - 6.0 - 9.0 - 104.0 - 9.0 - 36.0 - 6.0
            canvas.op(
                lambda rx=rx, ry=ry, name=row["name"], name_w=name_w: text(
                    name, rx + 6.0, ry + 3.0, fnt, th.raw("text"), width=name_w, truncate=True
                )
            )
            bx = rx + 6.0 + name_w + 9.0
            byy = ry + (row_h - 7.0) / 2.0
            canvas.op(lambda bx=bx, byy=byy: box(bx, byy, 104.0, 7.0, th.raw("track"), 4.0))
            fill_w = 104.0 * row["p"] / 100.0
            canvas.op(
                lambda bx=bx, byy=byy, fill_w=fill_w, selected=selected: box(
                    bx,
                    byy,
                    fill_w,
                    7.0,
                    saturate(th.raw("accent"), 1.0, 1.18) if selected else th.raw("accent"),
                    4.0,
                )
            )
            canvas.op(
                lambda rx=rx, ry=ry, p=row["p"]: text(
                    f"{p}%", rx, ry + 3.0, fnt, th.raw("muted"), "right", col_w - 6.0
                )
            )
            canvas.hit(rx, ry, col_w, row_h, lambda e, mid=row["id"]: self.set_master(mid))
            canvas.tip(rx, ry, col_w, row_h, f"Focus {row['name']}")
        cy += per_col * row_h
        card_h = cy - top + pad_y
        canvas._ops.insert(start, lambda: box(x, top, w, card_h, th.raw("surface"), 12.0))
        canvas._ops.insert(start + 1, lambda: frame(x, top, w, card_h, th.raw("border"), 12.0))
        return top + card_h

    @objc.python_method
    def _overview_extras(self, canvas: _Canvas, x: float, y: float, w: float) -> float:
        if not self.model.masters:
            return y
        y += 16.0
        y2 = self._week_card_safe(canvas, x, y, w)
        if y2 > y:
            y = y2 + 14.0
        return self._leaderboard(canvas, x, y, w)

    @objc.python_method
    def _week_card_safe(self, canvas: _Canvas, x: float, y: float, w: float) -> float:
        """The week card with its chrome inserted under its content (op-order fix)."""
        th, model = self.theme, self.model
        digest = model.week_digest()
        if digest is None:
            return y
        start = len(canvas._ops)
        end_y = self._week_body(canvas, x, y, w, digest)
        card_h = end_y - y
        canvas._ops.insert(start, lambda: box(x, y, w, card_h, th.raw("surface"), 12.0))
        canvas._ops.insert(start + 1, lambda: frame(x, y, w, card_h, th.raw("border"), 12.0))
        return end_y

    @objc.python_method
    def _week_body(self, canvas: _Canvas, x: float, y: float, w: float, digest: dict) -> float:
        th, model = self.theme, self.model
        pad_x, pad_y = 16.0, 14.0
        cx, cy = x + pad_x, y + pad_y
        cw = w - 2 * pad_x
        cy += self._card_header(canvas, cx, cy, cw, "This week")
        big = font(22.0, 700)
        sub = font(FS_2XS)
        big_h = line_height(big)
        sub_h = line_height(sub)

        def stat(value: int, label: str, sx: float, sy: float) -> float:
            glyph, kind = rank_arrow(value)
            color = {"up": th.raw("ok"), "down": th.step(0), "flat": th.raw("muted2")}[kind]
            label_text = f"{glyph} {'+' if value > 0 else ''}{value}%"
            tw = measure(label_text, big)[0]
            canvas.op(lambda: text(label_text, sx, sy, big, color))
            lw = measure(label.upper(), sub)[0]
            canvas.op(
                lambda: text(
                    label.upper(),
                    sx + tw + 7.0,
                    sy + big_h - sub_h - 3.0,
                    sub,
                    th.raw("muted"),
                    kern=FS_2XS * 0.05,
                )
            )
            return tw + 7.0 + lw + 24.0

        sx = cx + stat(digest["delta"], "past 7 days", cx, cy)
        if digest["monthDelta"] is not None:
            stat(digest["monthDelta"], "past 30 days", sx, cy)
        cy += big_h + 4.0
        best, colors = digest["topMasters"], digest["topColors"]
        if best or colors:
            cy += 10.0
            line_y = cy
            canvas.op(lambda: hline(cx, cx + cw, line_y, th.raw("track")))
            cy += 10.0
            col_gap = 28.0
            col_w = (cw - col_gap) / 2.0
            key_font = font(FS_2XS)
            row_font = font(FS_SM)
            bold_font = font(FS_SM, 600)
            tail_font = font(FS_SM, 500)
            row_h = line_height(row_font) + 5.0
            heights = []
            for index, (title, items) in enumerate(
                (("Most improved masters", best), ("Focus of the week", colors))
            ):
                if not items:
                    heights.append(0.0)
                    continue
                bx = cx + index * (col_w + col_gap)
                by = cy
                canvas.op(
                    lambda bx=bx, by=by, title=title: text(
                        title.upper(), bx, by, key_font, th.raw("muted2"), kern=FS_2XS * 0.04
                    )
                )
                by += line_height(key_font) + 3.0 + 5.0
                for item in items:
                    if "master" in item:
                        name, value = item["master"]["name"], f"+{item['d']}%"
                        canvas.op(
                            lambda bx=bx, by=by, name=name: text(
                                name,
                                bx,
                                by,
                                row_font,
                                th.raw("text"),
                                width=col_w - 60.0,
                                truncate=True,
                            )
                        )
                        canvas.op(
                            lambda bx=bx, by=by, value=value: text(
                                value, bx, by, bold_font, th.raw("accent"), "right", col_w
                            )
                        )
                    else:
                        share = (
                            round(item["n"] / digest["moveTotal"] * 100)
                            if digest["moveTotal"]
                            else 0
                        )
                        color = th.step(item["k"])
                        label = model.label_for(item["k"])
                        value, tail = f"+{item['n']}", f"(+{share}%)"
                        tail_w = measure(tail, tail_font)[0]
                        canvas.op(
                            lambda bx=bx, by=by, color=color: fill(
                                rrect(bx, by + 3.0, 11.0, 11.0, 3.0), color
                            )
                        )
                        canvas.op(
                            lambda bx=bx, by=by, label=label: text(
                                label,
                                bx + 18.0,
                                by,
                                row_font,
                                th.raw("text"),
                                width=col_w - 90.0,
                                truncate=True,
                            )
                        )
                        canvas.op(
                            lambda bx=bx, by=by, tail=tail: text(
                                tail, bx, by, tail_font, rgba(th.raw("muted"), 0.6), "right", col_w
                            )
                        )
                        canvas.op(
                            lambda bx=bx, by=by, value=value, tail_w=tail_w: text(
                                value,
                                bx,
                                by,
                                bold_font,
                                th.raw("accent"),
                                "right",
                                col_w - tail_w - 5.0,
                            )
                        )
                    by += row_h
                heights.append(by - cy)
            cy += max(heights)
        return cy + pad_y

    # ----- master panel ---------------------------------------------------------------------------
    @objc.python_method
    def _version_card(self, canvas: _Canvas, x: float, y: float, w: float) -> float:
        th, model = self.theme, self.model
        dates = model.dates
        vidx = model.version_indices(self.state["master"])
        if len(dates) < 2 or len(vidx) < 1:
            return y
        y += 16.0
        top = y
        start = len(canvas._ops)
        pad_x, pad_y = 16.0, 12.0
        cx, cy = x + pad_x, y + pad_y
        cw = w - 2 * pad_x
        fnt = font(FS_XS)
        lh = line_height(fnt)
        cur = self.scrub_index()
        active = 0
        for pos, di in enumerate(vidx):
            if di <= cur:
                active = pos
            else:
                break
        when = date_label(dates[cur]) if 0 <= cur < len(dates) else ""
        canvas.op(lambda cy=cy: text("VERSIONS", cx, cy, fnt, th.raw("muted"), kern=FS_XS * 0.04))
        canvas.op(lambda cy=cy: text(when, cx, cy, fnt, th.raw("muted2"), "right", cw))
        cy += lh + 12.0
        # the dot line: track + accent fill to the active node + 10px dots
        nav_y = cy + 5.0
        nav_x0, nav_x1 = cx + 2.0 + 5.0, cx + cw - 2.0 - 5.0
        canvas.op(lambda: box(nav_x0, nav_y + 4.0, nav_x1 - nav_x0, 2.0, th.raw("track"), 2.0))
        n = len(vidx)
        frac = active / (n - 1) if n > 1 else 0.0
        canvas.op(
            lambda: box(nav_x0, nav_y + 4.0, (nav_x1 - nav_x0) * frac, 2.0, th.raw("accent"), 2.0)
        )
        for pos, di in enumerate(vidx):
            dx = nav_x0 + ((nav_x1 - nav_x0) * pos / (n - 1) if n > 1 else 0.0)
            past = pos <= active
            on = pos == active
            radius = 5.0 * (1.4 if on else 1.0)
            if on:
                canvas.op(
                    lambda dx=dx, radius=radius: fill(
                        circle(dx, nav_y + 5.0, radius + 3.0),
                        mix(th.raw("accent"), (0, 0, 0, 0), 0.28),
                    )
                )
            canvas.op(
                lambda dx=dx, radius=radius, past=past: fill(
                    circle(dx, nav_y + 5.0, radius),
                    th.raw("accent") if past else th.raw("surface2"),
                )
            )
            canvas.op(
                lambda dx=dx, radius=radius, past=past: stroke(
                    circle(dx, nav_y + 5.0, radius - 0.75),
                    th.raw("accent") if past else th.raw("muted2"),
                    1.5,
                )
            )
            canvas.hit(dx - 10.0, nav_y - 6.0, 20.0, 22.0, lambda e, di=di: self.scrub_set(di))
            canvas.tip(dx - 8.0, nav_y - 4.0, 16.0, 18.0, dates[di] + (" · showing" if on else ""))
        cy += 10.0 + 4.0 + 2.0
        card_h = cy - top + pad_y
        canvas._ops.insert(start, lambda: box(x, top, w, card_h, th.raw("surface"), 12.0))
        canvas._ops.insert(start + 1, lambda: frame(x, top, w, card_h, th.raw("border"), 12.0))
        return top + card_h

    @objc.python_method
    def _seg_bar(
        self,
        canvas: _Canvas,
        x: float,
        y: float,
        w: float,
        parts: list[tuple[Any, float, str]],
        height: float = 10.0,
        clickable: bool = False,
    ) -> None:
        """Stacked colour bar (.seg / .cov-bar): parts = [(key, share 0..1, tooltip)]."""
        th = self.theme
        focus = self.state["focus"]
        radius = height / 2.0
        canvas.op(lambda: box(x, y, w, height, th.raw("track"), radius))
        live = [(key, w * share, tip) for key, share, tip in parts if w * share > 0]
        cursor = x
        for index, (key, seg_w, tip) in enumerate(live):
            sx = cursor
            cursor += seg_w
            first, last = index == 0, index == len(live) - 1
            path = seg_path(sx, y, seg_w, height, radius if first else 0.0, radius if last else 0.0)
            on = clickable and focus == key
            off = clickable and focus is not None and not on
            alpha = 0.28 if off else 1.0
            if key == NO_COLOR:
                glow = th.raw("none_b")
                canvas.op(
                    lambda path=path, glow=glow, alpha=alpha: fill(
                        path, rgba(glow, alpha), shadow=(mix(glow, (0, 0, 0, 0), 0.22 * alpha), 9.0)
                    )
                )
                canvas.op(
                    lambda sx=sx, seg_w=seg_w, path=path: hatch(sx, y, seg_w, height, th, path)
                )
            else:
                color = saturate(th.step(key), 1.2, 1.08)
                canvas.op(
                    lambda path=path, color=color, alpha=alpha: fill(
                        path,
                        rgba(color, alpha),
                        shadow=(mix(color, (0, 0, 0, 0), 0.22 * alpha), 9.0),
                    )
                )
            if tip:
                canvas.tip(sx, y, seg_w, height, tip)
            if clickable:
                canvas.hit(
                    sx,
                    y - 3.0,
                    seg_w,
                    height + 6.0,
                    lambda e, key=key: self.set_focus(None if self.state["focus"] == key else key),
                )

    @objc.python_method
    def _master_overall(self, canvas: _Canvas, master: dict, x: float, y: float, w: float) -> float:
        th, model = self.theme, self.model
        dist = model.master_distribution(master, self.state["tlScrub"])
        total = dist["total"] or 1
        y += 8.0 if model.version_indices(self.state["master"]) and len(model.dates) >= 2 else 16.0
        top = y
        start = len(canvas._ops)
        pad_x, pad_y = 16.0, 12.0
        cx, cy = x + pad_x, y + pad_y
        cw = w - 2 * pad_x
        name_font = font(17.0, 700)
        head_font = font(FS_SM)
        head_bold = font(FS_SM, 700)
        name_h = line_height(name_font)
        head_h = line_height(head_font)
        name_w = measure(master["name"], name_font)[0]
        canvas.op(lambda cy=cy: text(master["name"], cx, cy, name_font, th.raw("text")))
        dot_x = cx + name_w + 9.0
        canvas.op(
            lambda cy=cy: text("·", dot_x, cy + name_h - head_h - 2.0, head_font, th.raw("muted2"))
        )
        pct_x = dot_x + measure("·", head_font)[0] + 9.0
        head = f"{dist['headPct']}% complete"
        canvas.op(
            lambda cy=cy: text(head, pct_x, cy + name_h - head_h - 2.0, head_bold, th.raw("text"))
        )
        start_p = pct(dist["started"], total)
        canvas.tip(
            pct_x,
            cy,
            measure(head, head_bold)[0],
            name_h,
            f"{dist['started']}/{total} glyphs started ({start_p}%)",
        )
        cy += name_h + 8.0
        parts = [
            (
                s["key"],
                (dist["dist"].get(str(s["key"])) or 0) / total,
                f"{s['label']} — click to focus these glyphs",
            )
            for s in model.steps
        ]
        parts.append(
            (NO_COLOR, dist["none"] / total, f"{model.none_label} — click to focus these glyphs")
        )
        canvas.hit(
            pct_x,
            cy - name_h - 8.0,
            measure(head, head_bold)[0],
            name_h,
            lambda e: self._toggle_funnel(),
        )
        self._seg_bar(canvas, cx, cy, cw, parts, 10.0, clickable=True)
        cy += 10.0
        if self.state["funnelOpen"]:
            cy = self._funnel(canvas, master, cx, cy + 12.0, cw, dist, total)
        card_h = cy - top + pad_y
        canvas._ops.insert(start, lambda: box(x, top, w, card_h, th.raw("surface"), 12.0))
        canvas._ops.insert(start + 1, lambda: frame(x, top, w, card_h, th.raw("border"), 12.0))
        return top + card_h

    @objc.python_method
    def _cov_row(
        self, canvas: _Canvas, x: float, y: float, w: float, row: dict, border: bool
    ) -> float:
        th, model = self.theme, self.model
        fnt = font(FS_XS)
        lh = line_height(fnt)
        row_h = lh + 10.0
        if border:
            canvas.op(lambda: hline(x, x + w, y, th.raw("track")))
        canvas.op(
            lambda: text(
                str(row["key"]), x, y + 5.0, fnt, th.raw("text"), width=120.0, truncate=True
            )
        )
        count = row.get("glyphs") if row.get("glyphs") is not None else row.get("total")
        num_w = max(48.0, measure(str(count), fnt)[0])
        bar_x = x + 120.0 + 12.0
        bar_w = w - 120.0 - 12.0 - 12.0 - num_w
        total = row.get("total") or 0
        parts = []
        for key in model.order:
            c = (row.get("dist") or {}).get(key) or 0
            if c and total:
                parts.append(
                    (int(key), c / total, f"{model.label_for(key)} — {round(c / total * 100)}%")
                )
        unc = row.get("uncolored") or 0
        if unc and total:
            parts.append(
                (NO_COLOR, unc / total, f"{model.none_label} — {round(unc / total * 100)}%")
            )
        self._seg_bar(canvas, bar_x, y + (row_h - 10.0) / 2.0, bar_w, parts, 10.0)
        canvas.op(lambda: text(str(count), x, y + 5.0, fnt, th.raw("muted"), "right", w))
        return row_h

    @objc.python_method
    def _category_coverage(self, canvas: _Canvas, x: float, y: float, w: float) -> float:
        rows = self.model.cov_rows("byCategory", self.state["master"])
        y += 16.0
        if not rows:
            fnt = font(FS_SM)
            canvas.op(lambda: text("No glyphs.", x, y, fnt, self.theme.raw("muted2")))
            return y + line_height(fnt) + 16.0
        gap = 28.0
        col_w = (w - gap) / 2.0
        col_y = [y + 6.0, y + 6.0]
        for index, row in enumerate(rows):
            col = index % 2
            rx = x + col * (col_w + gap)
            h = self._cov_row(canvas, rx, col_y[col], col_w, row, border=index >= 2)
            col_y[col] += h
        return max(col_y) + 4.0 + 16.0

    @objc.python_method
    def _script_tile_image(self, row: dict, size: float) -> Any:
        """The blurred proportional colour blend behind a script card (paintBlend)."""
        th = self.theme
        key = (
            row["key"],
            size,
            json.dumps(row.get("dist") or {}, sort_keys=True),
            row.get("uncolored"),
            th.is_dark(),
        )
        cached = self._disc_cache.get(("tile", key))
        if cached is not None:
            return cached
        segs = []
        total = 0.0
        for k, c in (row.get("dist") or {}).items():
            if c:
                segs.append((float(c), th.step(k)))
                total += c
        unc = row.get("uncolored") or 0
        grey = th.raw("track")
        if unc:
            segs.append((float(unc), grey))
            total += unc
        base = segs[0][1] if segs else grey
        image = _wedge_image(
            segs, total, size, base, blur=size * 0.085, saturation=1.2, square=True
        )
        self._disc_cache[("tile", key)] = image
        return image

    @objc.python_method
    def _script_coverage(self, canvas: _Canvas, x: float, y: float, w: float) -> float:
        th, model = self.theme, self.model
        rows = model.script_rows(self.state["master"])
        if len(rows) <= 1:
            return y
        title_font = font(FS_SM)
        canvas.op(
            lambda y=y: text("Colours set by script", x, y + 10.0, title_font, th.raw("muted"))
        )
        y += 10.0 + line_height(title_font) + 4.0 + 12.0
        gap = 12.0
        cols = max(1, int((w + gap) // (148.0 + gap)))
        tile = (w - gap * (cols - 1)) / cols
        name_font = font(13.0, 600)
        count_font = font(11.0)
        for index, row in enumerate(rows):
            col, r = index % cols, index // cols
            tx = x + col * (tile + gap)
            ty = y + r * (tile + gap)
            meta = model.script_meta(row["key"])
            raw_name = meta.get("name") or pretty_script(row["key"])
            name = raw_name[:1].upper() + raw_name[1:] if raw_name else raw_name
            count = row.get("glyphs") if row.get("glyphs") is not None else row.get("total")
            image = self._script_tile_image(row, 320.0)

            def draw_tile(tx=tx, ty=ty, image=image) -> None:
                AppKit.NSGraphicsContext.saveGraphicsState()
                rrect(tx, ty, tile, tile, 16.0).addClip()
                image.drawInRect_fromRect_operation_fraction_(
                    AppKit.NSMakeRect(tx, ty, tile, tile),
                    AppKit.NSZeroRect,
                    AppKit.NSCompositingOperationSourceOver,
                    1.0,
                )
                AppKit.NSGraphicsContext.restoreGraphicsState()

            canvas.op(draw_tile)
            canvas.op(
                lambda tx=tx, ty=ty, name=name: text(
                    name,
                    tx + 11.0,
                    ty + 13.0,
                    name_font,
                    "#ffffff",
                    "center",
                    tile - 22.0,
                    truncate=True,
                )
            )
            outline = model.script_glyph_path(meta, self.state["master"])
            if outline:
                gw = tile * 0.46
                gh = tile * 0.5
                path = svg_path(
                    outline.get("d", ""),
                    outline.get("vb", ""),
                    tx + (tile - gw) / 2.0,
                    ty + (tile - gh) / 2.0,
                    gw,
                    gh,
                )
                if path is not None:
                    canvas.op(
                        lambda path=path: fill(
                            path, (1.0, 1.0, 1.0, 0.96), shadow=((0, 0, 0, 0.5), 4.0)
                        )
                    )
            canvas.op(
                lambda tx=tx, ty=ty, count=count: text(
                    str(count),
                    tx,
                    ty + tile - 13.0 - line_height(count_font),
                    count_font,
                    (1.0, 1.0, 1.0, 0.82),
                    "center",
                    tile,
                )
            )
            canvas.tip(tx, ty, tile, tile, f"{name} — {count} glyphs")
        rows_n = math.ceil(len(rows) / cols)
        return y + rows_n * tile + (rows_n - 1) * gap + 4.0

    @objc.python_method
    def _heatmap(self, canvas: _Canvas, master: dict, x: float, y: float, w: float) -> float:
        th, model, state = self.theme, self.model, self.state
        items, changes = model.heatmap_items(master, state["tlScrub"])
        focus = state["focus"]
        if focus is not None:

            def matches(item: tuple) -> bool:
                key = item[1]
                fk = NO_COLOR if (key == NO_COLOR or str(key) not in model.order) else key
                return fk == focus

            shown = [item for item in items if matches(item)]
        else:
            shown = items
        if state["heatRecent"] and changes:
            shown = [item for item in shown if item[0] in changes]
        y += 14.0
        canvas.op(lambda y=y: hline(x, x + w, y, th.raw("border")))
        y += 12.0
        # header controls: focus chip · before/after · recently modified · sort switch
        hx = x
        row_h = 0.0
        if focus is not None:
            cw = self._chip(
                canvas,
                hx,
                y,
                f"Focus: {model.label_for(focus)} ✕",
                True,
                lambda: self.set_focus(None),
                small=True,
            )
            hx += cw + 8.0
        if changes:
            items_ba = [
                ("Before", lambda: self._set_before(True)),
                ("After", lambda: self._set_before(False)),
            ]
            sw_w, sw_h = self._segsw(canvas, hx, y, items_ba, 0 if state["before"] else 1, 10.0)
            hx += sw_w + 8.0
            row_h = max(row_h, sw_h)
            cw = self._chip(
                canvas,
                hx,
                y,
                "Recently modified",
                state["heatRecent"],
                self._toggle_recent,
                small=True,
            )
            hx += cw + 8.0
        sort_items = [
            ("Category", lambda: self._set_sort("category")),
            ("By colour", lambda: self._set_sort("color")),
        ]
        sw_w, sw_h = self._segsw(
            canvas, hx, y, sort_items, 1 if state["heatSort"] == "color" else 0
        )
        hx += sw_w + 8.0
        row_h = max(row_h, sw_h)
        # cell size: − / + chips stand in for the range slider
        for label, delta in (("−", -6), ("+", 6)):
            cw = self._chip(
                canvas,
                hx,
                y,
                label,
                False,
                lambda delta=delta: self._resize_cells(delta),
                small=True,
            )
            hx += cw + 4.0
        y += row_h + 8.0
        cell_min = float(state["cellSize"])
        gap = 3.0
        col_gap = 24.0  # .heat-cats{column-count:2;column-gap:24px}
        col_w = (w - col_gap) / 2.0
        cols = max(1, int((col_w + gap) // (cell_min + gap)))
        cell = (col_w - gap * (cols - 1)) / cols
        cat_font = font(FS_XS)
        cat_h = line_height(cat_font)
        if state["heatSort"] == "color":
            sections = [
                (model.label_for(key), key, group) for key, group in model.group_by_color(shown)
            ]
        else:
            sections = [(cat, None, group) for cat, group in model.group_by_category(shown)]
        if not sections:
            fnt = font(FS_SM)
            msg = "No glyphs changed since the last run." if state["heatRecent"] else "No glyphs."
            canvas.op(lambda y=y: text(msg, x, y, fnt, th.raw("muted2")))
            return y + line_height(fnt)
        paths = model.paths.get(master["id"]) or {}
        file_path = model.h.get("filePath")

        def draw_section(title: str, key: Any, group: list, x: float, y: float) -> float:
            tx = x
            if key is not None:
                color = th.step(key) if key != NO_COLOR else th.raw("none_b")
                canvas.op(
                    lambda tx=tx, y=y, color=color: fill(
                        rrect(tx, y + (cat_h - 12.0) / 2.0, 12.0, 12.0, 3.0), color
                    )
                )
                tx += 12.0 + 6.0
            tw = measure(title, cat_font)[0]
            canvas.op(lambda tx=tx, y=y, title=title: text(title, tx, y, cat_font, th.raw("muted")))
            count = len(group)
            canvas.op(
                lambda tx=tx, y=y, n=count, tw=tw: text(
                    str(n), tx + tw + 6.0, y, cat_font, th.raw("muted2")
                )
            )
            y += cat_h + 6.0
            for index, (name, gkey, _gi) in enumerate(group):
                col, r = index % cols, index // cols
                cx = x + col * (cell + gap)
                cy = y + r * (cell + gap)
                dim = not model.is_counted(name)
                was_key = changes[name][0] if name in changes else gkey
                show_key = was_key if state["before"] else gkey
                color = th.step(show_key) if show_key != NO_COLOR else th.raw("none_b")
                alpha = 0.35 * (0.35 if dim else 1.0)
                canvas.op(
                    lambda cx=cx, cy=cy, color=color, alpha=alpha: fill(
                        rrect(cx, cy, cell, cell, 5.0), rgba(color, alpha)
                    )
                )
                outline = paths.get(name)
                if outline:
                    inner = cell * 0.9
                    path = svg_path(
                        outline.get("d", ""),
                        outline.get("vb", ""),
                        cx + (cell - inner) / 2.0,
                        cy + (cell - inner) / 2.0,
                        inner,
                        inner,
                        pad=3.0 * 0.9,
                    )
                    if path is not None:
                        canvas.op(
                            lambda path=path, dim=dim: fill(
                                path, rgba(th.raw("text"), 0.35 if dim else 1.0)
                            )
                        )
                label = model.label_for(gkey) + (" — not counted" if dim else "")
                edited = model.last_edit.get(name)
                tip = f"{name} — {label}" + (
                    f" · edited {edited}d ago" if edited is not None else ""
                )
                canvas.tip(cx, cy, cell, cell, tip)
                if file_path:
                    canvas.hit(
                        cx,
                        cy,
                        cell,
                        cell,
                        lambda e, name=name: self._open_glyph(name, master["id"]),
                    )
            rows_n = math.ceil(len(group) / cols)
            return y + rows_n * cell + max(0, rows_n - 1) * gap

        def section_h(group: list) -> float:
            rows_n = math.ceil(len(group) / cols)
            return cat_h + 6.0 + rows_n * cell + max(0, rows_n - 1) * gap

        def stack_h(heights: list[float]) -> float:
            return sum(heights) + 14.0 * max(0, len(heights) - 1)

        # CSS column balancing with unbreakable .cat blocks: sections keep their order and
        # the split is the one that keeps the taller column shortest (ties fill the left).
        heights = [section_h(group) for _, _, group in sections]
        split = min(
            range(len(sections) + 1),
            key=lambda k: (max(stack_h(heights[:k]), stack_h(heights[k:])), -k),
        )
        bottom = y
        for col_index, chunk in enumerate((sections[:split], sections[split:])):
            sy = y
            for s_index, (title, key, group) in enumerate(chunk):
                if s_index > 0:
                    sy += 14.0
                sy = draw_section(title, key, group, x + col_index * (col_w + col_gap), sy)
            bottom = max(bottom, sy)
        return bottom + 8.0

    @objc.python_method
    def _set_before(self, before: bool) -> None:
        self.state["before"] = before
        self.update()

    @objc.python_method
    def _toggle_recent(self) -> None:
        self.state["heatRecent"] = not self.state["heatRecent"]
        self.update()

    @objc.python_method
    def _set_sort(self, mode: str) -> None:
        self.state["heatSort"] = mode
        self.update()

    @objc.python_method
    def _resize_cells(self, delta: int) -> None:
        self.state["cellSize"] = max(20, min(40, int(self.state["cellSize"]) + delta))
        self.update()

    @objc.python_method
    def _open_glyph(self, name: str, master_id: str) -> None:
        from urllib.parse import quote

        path = self.model.h.get("filePath")
        if not path:
            return
        url = f"glyphsapp://show/?path={quote(str(path), safe='')}&glyph={quote(name, safe='')}&layer={quote(str(master_id), safe='')}"
        AppKit.NSWorkspace.sharedWorkspace().openURL_(AppKit.NSURL.URLWithString_(url))

    # ----- Timeline ---------------------------------------------------------------------------------
    @objc.python_method
    def _axis(self, w: float, h: float) -> dict:
        """calendarAxis: plot geometry over the (zoom-windowed) series."""
        model, state = self.model, self.state
        series = model.series
        if state["viewLo"] is not None or state["viewHi"] is not None:
            lo, hi = model.view_bounds(state["viewLo"], state["viewHi"])
            series = series[lo : hi + 1]
            base = lo
        else:
            base = 0
        pl, pr, ptop, pb = 30.0, 12.0, 12.0, 16.0
        iw, ih = w - pl - pr, h - ptop - pb
        last = max(1, len(series) - 1)

        def X(i: int) -> float:
            return pl + i / last * iw

        def Y(p: float) -> float:
            return ptop + ih - p / 100.0 * ih

        return {
            "series": series,
            "base": base,
            "pl": pl,
            "pr": pr,
            "ptop": ptop,
            "pb": pb,
            "iw": iw,
            "ih": ih,
            "X": X,
            "Y": Y,
        }

    @objc.python_method
    def _chart_frame(
        self, canvas: _Canvas, x: float, y: float, w: float, ax: dict, sx: float, sy: float
    ) -> None:
        """Grid, column rules, tick labels and the scrub marker shared by both charts."""
        th = self.theme
        series = ax["series"]
        X, Y = ax["X"], ax["Y"]
        pl, pr, ptop, ih, pb = ax["pl"], ax["pr"], ax["ptop"], ax["ih"], ax["pb"]
        axis_font = font(10.0 * sy)
        tick_font = font(9.0 * sy)
        for index in range(len(series)):
            gx = x + X(index) * sx
            canvas.op(lambda gx=gx: box(gx, y + ptop * sy, 1.0, ih * sy, th.raw("tl_vgrid")))
        for g in (0, 25, 50, 75, 100):
            gy = y + Y(g) * sy
            canvas.op(
                lambda gy=gy: box(x + pl * sx, gy, (w / sx - pl - pr) * sx, 1.0, th.raw("track"))
            )
            canvas.op(
                lambda gy=gy, g=g: text(
                    str(g),
                    x,
                    gy - line_height(axis_font) / 2.0,
                    axis_font,
                    th.raw("muted2"),
                    "right",
                    (pl - 5.0) * sx,
                )
            )
        step = max(1, math.ceil(len(series) / 6))
        for index, point in enumerate(series):
            if index % step != 0 and index != len(series) - 1:
                continue
            tx = x + X(index) * sx
            label = self._tick_label(point["date"])
            align = "start" if index == 0 else ("end" if index == len(series) - 1 else "middle")
            tw = measure(label, tick_font)[0]
            lx = tx if align == "start" else (tx - tw if align == "end" else tx - tw / 2.0)
            canvas.op(
                lambda lx=lx, label=label: text(
                    label,
                    lx,
                    y + (ptop + ih + pb) * sy - line_height(tick_font) + 2.0,
                    tick_font,
                    th.raw("muted2"),
                )
            )
        scrub = self.state["tlScrub"]
        if scrub is not None:
            swi = scrub - ax["base"]
            if 0 <= swi < len(series):
                srx = x + X(swi) * sx

                def scrub_rule(srx=srx) -> None:
                    path = AppKit.NSBezierPath.bezierPath()
                    path.moveToPoint_((srx, y + ptop * sy))
                    path.lineToPoint_((srx, y + (ptop + ih) * sy))
                    path.setLineDash_count_phase_([3.0, 3.0], 2, 0.0)
                    stroke(path, rgba(th.raw("accent"), 0.85), 1.5)
                    fill(circle(srx, y + (ptop + ih) * sy, 3.5), th.raw("accent"))

                canvas.op(scrub_rule)

        # click-to-pick-a-moment over the plot
        def pick(event: Any) -> None:
            point = canvas.convertPoint_fromView_(event.locationInWindow(), None)
            px = (float(point.x) - x) / sx
            best, best_d = 0, float("inf")
            for index in range(len(series)):
                d = abs(X(index) - px)
                if d < best_d:
                    best, best_d = index, d
            self.scrub_set(ax["base"] + best)

        canvas.hit(x + pl * sx, y + ptop * sy, (w / sx - pl - pr) * sx, ih * sy, pick)

    @objc.python_method
    def _tick_label(self, iso: str) -> str:
        model = self.model
        if model.gran == "time":
            if model.bucket == "month":
                s = str(iso)
                try:
                    year, mo = int(s[:4]), int(s[5:7]) - 1
                    return f"{MONTHS_LONG[mo][:3]} {str(year)[2:]}"
                except ValueError:
                    return s[:7]
            if model.bucket == "day":
                return date_label(str(iso)[:10])
        return date_label(iso)

    @objc.python_method
    def _band_chart(self, canvas: _Canvas, x: float, y: float, w: float) -> float:
        """Global timeline: median line + min-max band across all masters."""
        th, model = self.theme, self.model
        vw, vh = 680.0, 200.0
        sx = w / vw
        sy = sx
        h = vh * sy
        canvas.op(lambda: box(x, y, w, h, th.raw("surface"), 12.0))
        canvas.op(lambda: frame(x, y, w, h, th.raw("border"), 12.0))
        ax = self._axis(vw, vh)
        series = ax["series"]
        X, Y = ax["X"], ax["Y"]
        dates = [p["date"] for p in series]
        matrix = model.pct_matrix(dates)
        up, lo, md = [], [], []
        for j in range(len(dates)):
            col = sorted(matrix[i][j] for i in range(len(matrix))) if matrix else []
            mn, mx = (col[0], col[-1]) if col else (0.0, 0.0)
            if not col:
                mid = 0.0
            elif len(col) % 2:
                mid = col[(len(col) - 1) // 2]
            else:
                mid = (col[len(col) // 2 - 1] + col[len(col) // 2]) / 2.0
            px = x + X(j) * sx
            up.append((px, y + Y(mx) * sy))
            lo.append((px, y + Y(mn) * sy))
            md.append((px, y + Y(mid) * sy, mid, mn, mx))
        self._chart_frame(canvas, x, y, w, ax, sx, sy)
        if len(up) >= 2:

            def band() -> None:
                path = smooth_bezier(up)
                lower = list(reversed(lo))
                path.lineToPoint_(lower[0])
                for c1, c2, end in smooth_segments(lower):
                    path.curveToPoint_controlPoint1_controlPoint2_(end, c1, c2)
                path.closePath()
                fill(path, rgba(th.raw("accent"), 0.16))

            canvas.op(band)
            canvas.op(
                lambda: stroke(smooth_bezier([(p[0], p[1]) for p in md]), th.raw("accent"), 1.8)
            )
            for p in md:
                canvas.op(lambda p=p: fill(circle(p[0], p[1], 2.0), th.raw("tl_dot")))
                canvas.tip(
                    p[0] - 4.0,
                    p[1] - 4.0,
                    8.0,
                    8.0,
                    f"Median {round(p[2])}% · range {round(p[3])}–{round(p[4])}%",
                )
        # (i) info bubble at the top-right
        info_font = font(11.0, 600)
        ix, iy = x + w - 9.0 - 18.0, y + 9.0
        canvas.op(lambda: fill(circle(ix + 9.0, iy + 9.0, 9.0), th.raw("surface")))
        canvas.op(lambda: stroke(circle(ix + 9.0, iy + 9.0, 8.5), th.raw("border2")))
        canvas.op(
            lambda: text(
                "i",
                ix,
                iy + (18.0 - line_height(info_font)) / 2.0,
                info_font,
                th.raw("muted"),
                "center",
                18.0,
            )
        )
        canvas.tip(
            ix,
            iy,
            18.0,
            18.0,
            f"Median completion over time · shaded band spans min–max across {len(model.masters)} masters",
        )
        return h

    @objc.python_method
    def _stream_chart(self, canvas: _Canvas, x: float, y: float, w: float) -> float:
        """Focused master: stacked weighted colour bands whose top traces the graded %."""
        th, model = self.theme, self.model
        vw, vh = 680.0, 200.0
        sx = w / vw
        sy = sx
        h = vh * sy
        canvas.op(lambda: box(x, y, w, h, th.raw("surface"), 12.0))
        canvas.op(lambda: frame(x, y, w, h, th.raw("border"), 12.0))
        ax = self._axis(vw, vh)
        series = ax["series"]
        X, Y = ax["X"], ax["Y"]
        master_id = self.state["master"]
        scope = [master_id] if master_id is not None else [m["id"] for m in model.masters]
        tally = []
        for point in series:
            by_key = {key: 0 for key in model.order}
            none = 0
            for mid in scope:
                t = model.col_tally(mid, point["date"])
                for key in model.order:
                    by_key[key] += t["byKey"][key]
                none += t["none"]
            tally.append({"date": point["date"], "byKey": by_key, "none": none})
        weight = model.step_weights()["weight"]
        denom = len(scope) * (model.counted_total() or 1) or 1
        self._chart_frame(canvas, x, y, w, ax, sx, sy)
        cum = [0.0] * len(tally)
        for key in model.order:
            lower = list(cum)
            upper = [
                cum[i] + (weight.get(key, 0.0) * (t["byKey"].get(key) or 0) / denom * 100)
                for i, t in enumerate(tally)
            ]
            cum = list(upper)
            if not any(upper[i] - lower[i] > 0.0001 for i in range(len(tally))):
                continue
            up_pts = [(x + X(i) * sx, y + Y(upper[i]) * sy) for i in range(len(tally))]
            lo_pts = [(x + X(i) * sx, y + Y(lower[i]) * sy) for i in range(len(tally))]
            if len(up_pts) < 2:
                continue
            color = th.step(key)

            def band(up_pts=up_pts, lo_pts=lo_pts, color=color) -> None:
                path = smooth_bezier(up_pts)
                lower_rev = list(reversed(lo_pts))
                path.lineToPoint_(lower_rev[0])
                for c1, c2, end in smooth_segments(lower_rev):
                    path.curveToPoint_controlPoint1_controlPoint2_(end, c1, c2)
                path.closePath()
                fill(path, rgba(color, 0.4))
                stroke(smooth_bezier(up_pts), rgba(color, 0.92), 1.4)

            canvas.op(band)
        scope_name = "Overall"
        if master_id is not None:
            master = model.master_by_id(master_id)
            scope_name = master["name"] if master else ""
        for i in range(len(tally)):
            px, py = x + X(i) * sx, y + Y(cum[i]) * sy
            canvas.op(lambda px=px, py=py: fill(circle(px, py, 1.8), th.raw("tl_dot")))
            canvas.tip(
                px - 4.0,
                py - 4.0,
                8.0,
                8.0,
                f"{scope_name} · {tally[i]['date']} · {round(cum[i])}%",
            )
        return h

    @objc.python_method
    def _range_nav(self, canvas: _Canvas, x: float, y: float, w: float) -> float:
        th, model, state = self.theme, self.model, self.state
        series = model.series
        if len(series) < 5:
            return 0.0
        y += 6.0
        vw, vh = 680.0, 54.0
        sx = w / vw
        sy = sx
        h = vh * sy
        pl, pr, ptop, pb = 8.0, 8.0, 9.0, 15.0
        iw, ih = vw - pl - pr, vh - ptop - pb
        canvas.op(lambda: box(x, y, w, h, th.raw("surface"), 12.0))
        canvas.op(lambda: frame(x, y, w, h, th.raw("border"), 12.0))
        n = len(series)

        def X(i: int) -> float:
            return x + (pl + (i / (n - 1) if n > 1 else 0.0) * iw) * sx

        def Y(p: float) -> float:
            return y + (ptop + ih - p / 100.0 * ih) * sy

        overall = model.nav_overall_series()
        pts = [(X(i), Y(overall[i])) for i in range(n)]
        base_y = y + (ptop + ih) * sy

        def area() -> None:
            path = smooth_bezier(pts)
            path.lineToPoint_((pts[-1][0], base_y))
            path.lineToPoint_((pts[0][0], base_y))
            path.closePath()
            fill(path, rgba(th.raw("accent"), 0.13))
            stroke(smooth_bezier(pts), rgba(th.raw("accent"), 0.6), 1.2)

        canvas.op(area)
        lo, hi = model.view_bounds(state["viewLo"], state["viewHi"])
        x_lo, x_hi = X(lo), X(hi)
        canvas.op(
            lambda: box(
                x + pl * sx,
                y + ptop * sy,
                max(0.0, x_lo - x - pl * sx),
                ih * sy,
                rgba(th.raw("bg"), 0.58),
            )
        )
        canvas.op(
            lambda: box(
                x_hi,
                y + ptop * sy,
                max(0.0, x + (vw - pr) * sx - x_hi),
                ih * sy,
                rgba(th.raw("bg"), 0.58),
            )
        )
        canvas.op(
            lambda: box(
                x_lo, y + ptop * sy, max(0.0, x_hi - x_lo), ih * sy, rgba(th.raw("accent"), 0.10)
            )
        )
        gy = y + (ptop + ih / 2.0) * sy
        for hx in (x_lo, x_hi):
            canvas.op(
                lambda hx=hx: box(hx - 3.0, gy - 9.0, 6.0, 18.0, rgba(th.raw("accent"), 0.95), 3.0)
            )
            for gx in (hx - 1.3, hx + 1.3):
                canvas.op(lambda gx=gx: box(gx - 0.5, gy - 4.0, 1.0, 8.0, rgba(th.raw("bg"), 0.85)))
        tick_font = font(9.0 * sy)
        step = max(1, math.ceil(n / 5))
        for i, point in enumerate(series):
            if i % step != 0 and i != n - 1:
                continue
            label = self._tick_label(point["date"])
            tw = measure(label, tick_font)[0]
            tx = X(i)
            lx = tx if i == 0 else (tx - tw if i == n - 1 else tx - tw / 2.0)
            canvas.op(
                lambda lx=lx, label=label: text(
                    label,
                    lx,
                    y + (ptop + ih + 11.0) * sy - line_height(tick_font) + 2.0,
                    tick_font,
                    th.raw("muted2"),
                )
            )

        # click: nearest handle jumps to the clicked snapshot; double-click resets
        def nav_click(event: Any) -> None:
            if event.clickCount() >= 2:
                state["viewLo"] = state["viewHi"] = None
                state["tlSpan"] = "all"
                self.update()
                return
            point = canvas.convertPoint_fromView_(event.locationInWindow(), None)
            px = float(point.x)
            idx = min(range(n), key=lambda i: abs(X(i) - px))
            lo2, hi2 = model.view_bounds(state["viewLo"], state["viewHi"])
            if abs(idx - lo2) <= abs(idx - hi2):
                state["viewLo"], state["viewHi"] = min(idx, hi2 - 1), hi2
            else:
                state["viewLo"], state["viewHi"] = lo2, max(idx, lo2 + 1)
            state["tlSpan"] = None
            self.update()

        canvas.hit(x, y, w, h, nav_click)
        return h + 6.0

    @objc.python_method
    def _lanes_block(
        self, canvas: _Canvas, x: float, y: float, w: float, lanes: list[dict], script: bool
    ) -> float:
        th = self.theme
        if not lanes:
            return y
        y += 14.0
        canvas.op(lambda y=y: hline(x, x + w, y, th.raw("border")))
        y += 12.0
        fnt = font(FS_XS)
        small = font(FS_XS)
        lh = line_height(fnt)
        row_h = lh + 8.0
        for index, lane in enumerate(lanes):
            ry = y + index * row_h
            if index > 0:
                canvas.op(lambda ry=ry: hline(x, x + w, ry, th.raw("track")))
            name = pretty_script(lane["key"]) if script else str(lane["key"])
            done = lane["cur"] >= 100
            line_color = th.raw("ok") if done else th.raw("accent")
            pct_w = 34.0
            arrow_w = 14.0
            spark_w, spark_h = 64.0, 16.0
            name_w = w - 10.0 - spark_w - 10.0 - pct_w - 10.0 - arrow_w
            label = f"{name} ({lane['count']})"
            nw = measure(name, fnt)[0]
            canvas.op(
                lambda ry=ry, name=name, name_w=name_w: text(
                    name, x, ry + 4.0, fnt, th.raw("text"), width=name_w, truncate=True
                )
            )
            canvas.op(
                lambda ry=ry, nw=nw, count=lane["count"]: text(
                    f"({count})", x + nw + 4.0, ry + 4.0, small, th.raw("muted2")
                )
            )
            spx = x + name_w + 10.0
            spy = ry + (row_h - spark_h) / 2.0
            values = lane["values"]
            pad = 1.5
            if values:
                if len(values) == 1:
                    yy = (
                        spy
                        + pad
                        + (spark_h - 2 * pad)
                        - max(0, min(100, values[0])) / 100.0 * (spark_h - 2 * pad)
                    )
                    pts = [(spx + pad, yy), (spx + spark_w - pad, yy)]
                else:
                    pts = [
                        (
                            spx + pad + i / (len(values) - 1) * (spark_w - 2 * pad),
                            spy
                            + pad
                            + (spark_h - 2 * pad)
                            - max(0, min(100, v)) / 100.0 * (spark_h - 2 * pad),
                        )
                        for i, v in enumerate(values)
                    ]

                def spark(pts=pts, line_color=line_color) -> None:
                    path = AppKit.NSBezierPath.bezierPath()
                    path.moveToPoint_(pts[0])
                    for p in pts[1:]:
                        path.lineToPoint_(p)
                    path.setLineJoinStyle_(1)  # round
                    path.setLineCapStyle_(1)
                    stroke(path, line_color, 1.5)

                canvas.op(spark)
            canvas.op(
                lambda ry=ry, cur=lane["cur"], spx=spx, spark_w=spark_w, pct_w=pct_w: text(
                    f"{cur}%", spx + spark_w + 10.0, ry + 4.0, fnt, th.raw("text"), "right", pct_w
                )
            )
            glyph, kind = rank_arrow(lane["delta"])
            color = {"up": th.raw("ok"), "down": th.step(0), "flat": th.raw("muted2")}[kind]
            canvas.op(
                lambda ry=ry, glyph=glyph, color=color, arrow_w=arrow_w: text(
                    glyph, x + w - arrow_w, ry + 4.0, fnt, color, "right", arrow_w
                )
            )
            prev = lane.get("prev")
            delta_txt = (
                f"{'+' if lane['delta'] > 0 else ''}{lane['delta']}% vs {date_label(prev)}"
                if prev
                else "first snapshot"
            )
            canvas.tip(x + w - arrow_w, ry, arrow_w, row_h, delta_txt)
            canvas.tip(x, ry, name_w, row_h, label)
        return y + len(lanes) * row_h

    @objc.python_method
    def _calendar(self, canvas: _Canvas, x: float, y: float, w: float, stretch: bool) -> float:
        th, model, state = self.theme, self.model, self.state
        dates = model.dates
        if len(dates) < 2:
            return y
        counts = model.cal_activity_scoped(state["master"])
        level = model.cal_level(counts)
        date_idx = {date: index for index, date in enumerate(dates)}
        if state["calY"] is None or state["calM"] is None:
            last = dates[-1]
            state["calY"], state["calM"] = int(last[:4]), int(last[5:7]) - 1
        year, month = state["calY"], state["calM"]
        title_font = font(FS_SM, 600)
        # nav: ‹ Month Year ›
        title = f"{MONTHS_LONG[month]} {year}"
        tw = max(150.0, measure(title, title_font)[0])
        nav_w = 30.0 + 14.0 + tw + 14.0 + 30.0
        nx = x + (w - nav_w) / 2.0
        chip_font = font(FS_SM)
        chip_h = line_height(chip_font) + 4.0
        for label, delta, cx in (("‹", -1, nx), ("›", 1, nx + nav_w - 30.0)):
            canvas.op(lambda cx=cx, y=y: box(cx, y, 30.0, chip_h, th.raw("surface2"), 7.0))
            canvas.op(lambda cx=cx, y=y: frame(cx, y, 30.0, chip_h, th.raw("border2"), 7.0))
            canvas.op(
                lambda cx=cx, y=y, label=label: text(
                    label, cx, y + 2.0, chip_font, th.raw("muted"), "center", 30.0
                )
            )
            canvas.hit(cx, y, 30.0, chip_h, lambda e, delta=delta: self._cal_nav(delta))
        canvas.op(
            lambda y=y: text(
                title,
                nx + 44.0,
                y + (chip_h - line_height(title_font)) / 2.0,
                title_font,
                th.raw("text"),
                "center",
                tw,
            )
        )
        y += chip_h + 10.0
        gap = 5.0
        if stretch:
            cell_w = (w - 6 * gap) / 7.0
            cell_h = cell_w / 2.0
            gx = x
        else:
            cell_w = cell_h = 28.0
            gx = x + (w - (7 * 28.0 + 6 * gap)) / 2.0
        dow_font = font(FS_2XS)
        for i, d in enumerate("SMTWTFS"):
            canvas.op(
                lambda i=i, d=d, y=y: text(
                    d, gx + i * (cell_w + gap), y, dow_font, th.raw("muted2"), "center", cell_w
                )
            )
        y += line_height(dow_font) + 2.0 + gap
        first_dow, days = _calendar.monthrange(year, month + 1)
        first_dow = (first_dow + 1) % 7  # monthrange is Monday=0; the grid starts on Sunday
        first_snap, last_snap = dates[0], dates[-1]
        num_font = font(FS_2XS)
        slot = first_dow
        rows_used = 0
        for day in range(1, days + 1):
            col, r = slot % 7, slot // 7
            slot += 1
            rows_used = r + 1
            cx = gx + col * (cell_w + gap)
            cy = y + r * (cell_h + gap)
            iso = f"{year:04d}-{month + 1:02d}-{day:02d}"
            snap_i = date_idx.get(iso)
            in_range = first_snap <= iso <= last_snap
            count = counts.get(iso, 0)
            bg = None
            color = th.raw("muted2")
            if snap_i is not None:
                lv = level(count)
                bg = {
                    1: mix(th.raw("accent"), th.raw("track"), 0.12),
                    2: mix(th.raw("accent"), th.raw("track"), 0.40),
                    3: mix(th.raw("accent"), th.raw("track"), 0.70),
                    4: th.raw("accent"),
                }[lv]
                color = "#ffffff" if lv == 4 else th.raw("text")
                canvas.hit(cx, cy, cell_w, cell_h, lambda e, snap_i=snap_i: self._cal_pick(snap_i))
                canvas.tip(
                    cx,
                    cy,
                    cell_w,
                    cell_h,
                    iso + (f" · {count} changed" if count else " · snapshot"),
                )
            elif in_range:
                bg = mix(th.raw("text"), (0, 0, 0, 0), 0.05)
            if bg is not None:
                canvas.op(lambda cx=cx, cy=cy, bg=bg: box(cx, cy, cell_w, cell_h, bg, 5.0))
            canvas.op(
                lambda cx=cx, cy=cy, day=day, color=color: text(
                    str(day), cx, cy + 2.0, num_font, color, "right", cell_w - 4.0
                )
            )
        return y + rows_used * cell_h + (rows_used - 1) * gap

    @objc.python_method
    def _cal_nav(self, delta: int) -> None:
        state = self.state
        state["calM"] += delta
        while state["calM"] < 0:
            state["calM"] += 12
            state["calY"] -= 1
        while state["calM"] > 11:
            state["calM"] -= 12
            state["calY"] += 1
        self.update()

    @objc.python_method
    def _cal_pick(self, index: int) -> None:
        if self.state["view"] != "timeline":
            self.state["view"] = "timeline"
            self.state["focus"] = None
        self.scrub_set(index)

    @objc.python_method
    def _timeline_view(self, canvas: _Canvas, x: float, y: float, w: float) -> float:
        model, state = self.model, self.state
        y += 2.0
        y = self._gran_bar(canvas, x, y, w)
        # card header: Graph/Calendar switch (left) · duration presets (right)
        cal = state["tlPane"] == "calendar"
        sw_w, sw_h = self._segsw(
            canvas,
            x,
            y,
            [
                ("Graph", lambda: self._set_pane("graph")),
                ("Calendar", lambda: self._set_pane("calendar")),
            ],
            1 if cal else 0,
        )
        if not cal and len(model.series) >= 3:
            active = state["tlSpan"] or (
                "" if (state["viewLo"] is not None or state["viewHi"] is not None) else "all"
            )
            items = [(label, (lambda key=key: self.set_span(key))) for key, label, _ in TL_SPANS]
            idx = next((i for i, entry in enumerate(TL_SPANS) if entry[0] == active), -1)
            widths = [measure(label, font(FS_2XS, 600))[0] + 18.0 for _, label, _ in TL_SPANS]
            total_w = max(widths) * len(TL_SPANS) + 4.0
            self._segsw(canvas, x + w - total_w, y, items, idx, 9.0)
        y += sw_h + 8.0
        if cal:
            y = self._calendar(canvas, x, y, w, stretch=True)
        else:
            if state["master"] is not None:
                y += self._stream_chart(canvas, x, y, w)
            else:
                y += self._band_chart(canvas, x, y, w)
            y += self._range_nav(canvas, x, y, w)
            gap = 28.0
            cat_lanes = model.lanes("category", state["master"], state["tlScrub"])
            scr_lanes = model.lanes("script", state["master"], state["tlScrub"])
            if scr_lanes:
                col_w = (w - gap) / 2.0
                y1 = self._lanes_block(canvas, x, y, col_w, cat_lanes, False)
                y2 = self._lanes_block(canvas, x + col_w + gap, y, col_w, scr_lanes, True)
                y = max(y1, y2)
            else:
                # no script lanes: category lanes flow two-up
                col_w = (w - gap) / 2.0
                half = math.ceil(len(cat_lanes) / 2)
                y1 = self._lanes_block(canvas, x, y, col_w, cat_lanes[:half], False)
                y2 = self._lanes_block(canvas, x + col_w + gap, y, col_w, cat_lanes[half:], False)
                y = max(y1, y2)
        y = self._outline_changes(canvas, x, y, w)
        y = self._touched_after_done(canvas, x, y, w)
        return y + 14.0

    @objc.python_method
    def _toggle_funnel(self) -> None:
        self.state["funnelOpen"] = not self.state["funnelOpen"]
        self.update()

    @objc.python_method
    def _funnel(
        self, canvas: _Canvas, master: dict, x: float, y: float, w: float, dist: dict, total: int
    ) -> float:
        """Cumulative "reached step k or beyond" bars (funnelHTML), one per step."""
        th, model = self.theme, self.model
        fnt = font(FS_XS)
        lh = line_height(fnt)
        row_h = lh + 2.0
        scrubbing = self.state["tlScrub"] is not None and len(model.dates) > 1
        if scrubbing:
            cum: dict = {}
            run = 0
            for key in reversed(model.order):
                run += dist["dist"].get(key, 0)
                cum[key] = run
            counts = {step["key"]: cum.get(str(step["key"]), 0) for step in model.steps}
        else:
            counts = {step["key"]: model.count_for(master, step["key"]) for step in model.steps}
        rows = [(step, pct(counts[step["key"]], total)) for step in model.steps]
        rows = [(step, p) for step, p in rows if p]
        if not rows:
            canvas.op(lambda y=y: text("Not started yet", x + 5.0, y + 4.0, fnt, th.raw("muted2")))
            return y + row_h + 4.0
        lab_w = max(84.0, min(130.0, max(measure(str(s["label"]), fnt)[0] for s, _ in rows)))
        for index, (step, p) in enumerate(rows):
            ry = y + index * (row_h + 5.0)
            color = th.step(step["key"])
            canvas.op(
                lambda ry=ry, color=color: fill(
                    circle(x + 4.0 + 4.0, ry + row_h / 2.0, 4.0),
                    color,
                    shadow=(mix(color, (0, 0, 0, 0), 0.26), 7.0),
                )
            )
            canvas.op(
                lambda ry=ry, label=str(step["label"]): text(
                    label,
                    x + 4.0 + 8.0 + 9.0,
                    ry + 1.0,
                    fnt,
                    th.raw("muted"),
                    width=lab_w,
                    truncate=True,
                )
            )
            bx = x + 4.0 + 8.0 + 9.0 + lab_w + 9.0
            bw = w - (bx - x) - 9.0 - 38.0 - 4.0
            canvas.op(
                lambda ry=ry, bx=bx, bw=bw: box(
                    bx, ry + (row_h - 9.0) / 2.0, bw, 9.0, th.raw("track"), 5.0
                )
            )
            canvas.op(
                lambda ry=ry, bx=bx, bw=bw, p=p, color=color: box(
                    bx,
                    ry + (row_h - 9.0) / 2.0,
                    bw * p / 100.0,
                    9.0,
                    saturate(color, 1.2, 1.08),
                    5.0,
                )
            )
            canvas.op(
                lambda ry=ry, p=p: text(f"{p}%", x, ry + 1.0, fnt, th.raw("text"), "right", w - 4.0)
            )
            canvas.tip(x, ry, w, row_h, f"{step['label']} — {p}% reached this step or beyond")
        return y + len(rows) * (row_h + 5.0)

    @objc.python_method
    def _gran_bar(self, canvas: _Canvas, x: float, y: float, w: float) -> float:
        """tlGranToggle: Time (grouped) vs Save (per checkpoint) + Days/Months buckets."""
        model = self.model
        if not model.h.get("hasCommits"):
            return y
        th = self.theme
        label_font = font(FS_XS)
        lh = line_height(label_font)
        cx = x
        canvas.op(
            lambda: text("TIMELINE", cx, y + 8.0, label_font, th.raw("muted2"), kern=FS_XS * 0.04)
        )
        cx += measure("TIMELINE", label_font)[0] + 10.0
        time_mode = model.gran == "time"
        cw = self._chip(
            canvas,
            cx,
            y,
            "Time",
            time_mode,
            lambda: self._set_gran("save" if time_mode else "time"),
            small=True,
        )
        cx += cw + 4.0
        row_h = lh + 8.0 + 8.0
        if time_mode:
            cx += 8.0
            canvas.op(lambda cx=cx: box(cx - 4.0, y + 2.0, 1.0, row_h - 4.0, th.raw("border")))
            for unit, label in (("day", "Days"), ("month", "Months")):
                cw = self._chip(
                    canvas,
                    cx,
                    y,
                    label,
                    model.bucket == unit,
                    lambda unit=unit: self._set_bucket(unit),
                    small=True,
                )
                cx += cw + 4.0
        return y + row_h + 12.0 - 8.0

    @objc.python_method
    def _set_gran(self, gran: str) -> None:
        if self.model.set_granularity(gran):
            self.reset_timeline_window()
            self._disc_cache = {}
            self.update()

    @objc.python_method
    def _set_bucket(self, unit: str) -> None:
        if self.model.set_bucket(unit):
            self.reset_timeline_window()
            self._disc_cache = {}
            self.update()

    @objc.python_method
    def _onion(self, canvas: _Canvas, change: dict, x: float, y: float, size: float) -> None:
        """ocOnionSVG: the old outline ghosted under the new, in their union viewBox."""
        th = self.theme
        old, new = change.get("old") or {}, change.get("new") or {}
        vb = _union_vb(old.get("vb"), new.get("vb"))
        canvas.op(lambda: box(x, y, size, size, th.raw("track"), 6.0))
        canvas.op(lambda: frame(x, y, size, size, th.raw("border"), 6.0))
        if old.get("d"):
            path = svg_path(old["d"], vb, x, y, size, size)
            if path is not None:
                canvas.op(lambda path=path: fill(path, rgba(th.raw("muted2"), 0.32)))
        if new.get("d"):
            path = svg_path(new["d"], vb, x, y, size, size)
            if path is not None:
                canvas.op(lambda path=path: fill(path, th.raw("text")))

    @objc.python_method
    def _outline_changes(self, canvas: _Canvas, x: float, y: float, w: float) -> float:
        th, model, state = self.theme, self.model, self.state
        days = model.outline_changes(state["master"])
        if not days:
            return y
        y += 14.0
        canvas.op(lambda y=y: hline(x, x + w, y, th.raw("border")))
        y += 12.0
        head_font = font(FS_XS)
        canvas.op(lambda y=y: text("Shape changes", x, y, head_font, th.raw("muted")))
        y += line_height(head_font) + 8.0
        row_font = font(FS_SM, 600)
        count_font = font(FS_XS)
        name_font = font(FS_2XS)
        row_h = line_height(row_font) + 10.0
        for date, items in days:
            open_ = bool(state["ocOpen"].get(date))
            day_label = date_label(date)
            ry = y
            canvas.op(
                lambda ry=ry, open_=open_: text(
                    "▾" if open_ else "▸", x + 6.0, ry + 5.0, count_font, th.raw("muted2")
                )
            )
            canvas.op(
                lambda ry=ry, label=day_label: text(
                    label, x + 6.0 + 10.0 + 8.0, ry + 5.0, row_font, th.raw("text")
                )
            )
            n = len(items)
            canvas.op(
                lambda ry=ry, n=n: text(
                    f"{n} glyph{'' if n == 1 else 's'}",
                    x,
                    ry + 5.0,
                    count_font,
                    th.raw("muted2"),
                    "right",
                    w - 6.0,
                )
            )
            canvas.hit(x, ry, w, row_h, lambda e, date=date: self._toggle_oc(date))
            y += row_h + 4.0
            if open_:
                cell, gap, size = 60.0, 10.0, 48.0
                cols = max(1, int((w - 12.0 + gap) // (cell + gap)))
                for index, change in enumerate(items):
                    col, r = index % cols, index // cols
                    cx = x + 6.0 + col * (cell + gap)
                    gname = str(change.get("glyph", ""))
                    cy = y + 8.0 + r * (size + 3.0 + line_height(name_font) + 10.0)
                    self._onion(canvas, change, cx + (cell - size) / 2.0, cy, size)
                    canvas.op(
                        lambda cx=cx, cy=cy, g=gname, size=size, cell=cell: text(
                            g,
                            cx,
                            cy + size + 3.0,
                            name_font,
                            th.raw("muted"),
                            "center",
                            cell,
                            truncate=True,
                        )
                    )
                    sub = (
                        f" · {change.get('master')}"
                        if (state["master"] is None and change.get("master"))
                        else ""
                    )
                    canvas.tip(
                        cx, cy, cell, size, f"{change.get('glyph', '')}{sub} — outline changed"
                    )
                rows_n = math.ceil(len(items) / cols)
                y += 8.0 + rows_n * (size + 3.0 + line_height(name_font) + 10.0) + 2.0
        return y

    @objc.python_method
    def _toggle_oc(self, date: str) -> None:
        self.state["ocOpen"][date] = not self.state["ocOpen"].get(date)
        self.update()

    @objc.python_method
    def _touched_after_done(self, canvas: _Canvas, x: float, y: float, w: float) -> float:
        th, model, state = self.theme, self.model, self.state
        rows = model.touched_after_done(state["master"])
        if not rows:
            return y
        y += 14.0
        canvas.op(lambda y=y: hline(x, x + w, y, th.raw("border")))
        y += 12.0
        head_font = font(FS_XS)
        canvas.op(lambda y=y: text("Touched after done", x, y, head_font, th.raw("muted")))
        hw = measure("Touched after done", head_font)[0]
        canvas.op(
            lambda y=y: text(
                "outline edits to glyphs already on the final step",
                x + hw + 6.0,
                y,
                head_font,
                th.raw("muted2"),
            )
        )
        y += line_height(head_font) + 8.0
        glyph_font = font(FS_SM, 600)
        small = font(FS_XS)
        small_b = font(FS_XS, 600)
        row_h = 34.0 + 10.0
        for row in rows:
            ry = y
            self._onion(canvas, row["change"], x + 6.0, ry + 5.0, 34.0)
            tx = x + 6.0 + 34.0 + 10.0
            canvas.op(
                lambda ry=ry, g=str(row["glyph"]), tx=tx: text(
                    g, tx, ry + (row_h - line_height(glyph_font)) / 2.0, glyph_font, th.raw("text")
                )
            )
            gw = measure(str(row["glyph"]), glyph_font)[0]
            if state["master"] is None:
                master = model.master_by_id(row["master"])
                mname = master["name"] if master else str(row["master"])
                canvas.op(
                    lambda ry=ry, mname=mname, gw=gw, tx=tx: text(
                        mname,
                        tx + gw + 8.0,
                        ry + (row_h - line_height(small)) / 2.0,
                        small,
                        th.raw("muted"),
                    )
                )
            gap_txt = f"({row['gapDays']} day{'' if row['gapDays'] == 1 else 's'} later)"
            when = (
                f"done {date_label(row['doneDate'])} → outline changed {date_label(row['date'])} "
            )
            gap_w = measure(gap_txt, small_b)[0]
            canvas.op(
                lambda ry=ry, gap_txt=gap_txt: text(
                    gap_txt,
                    x,
                    ry + (row_h - line_height(small)) / 2.0,
                    small_b,
                    th.raw("text"),
                    "right",
                    w - 6.0,
                )
            )
            canvas.op(
                lambda ry=ry, when=when, gap_w=gap_w: text(
                    when,
                    x,
                    ry + (row_h - line_height(small)) / 2.0,
                    small,
                    th.raw("muted"),
                    "right",
                    w - 6.0 - gap_w,
                )
            )
            y += row_h
        return y

    @objc.python_method
    def _set_pane(self, pane: str) -> None:
        self.state["tlPane"] = pane
        self.state["tlScrub"] = None
        self.update()

    # ----- tower -------------------------------------------------------------------------------------
    @objc.python_method
    def _tower_wheel(self, event: Any) -> None:
        masters = self.model.masters
        visible = self._tower_geo.get("visible", len(masters))
        self._tower_vt = max(
            0.0, min(max(0, len(masters) - visible), self._tower_vt + float(event.deltaY()) * 0.02)
        )
        self._layout_tower()
        self.tower.setNeedsDisplay_(True)

    @objc.python_method
    def _counts_of(self, master: dict) -> tuple[list[int], int]:
        model, state = self.model, self.state
        counts = [0] * 12
        if state["tlScrub"] is not None and model.dates:
            date = model.dates[self.scrub_index()]
            for key in model.state_at(master["id"], date).values():
                if 0 <= key < 12:
                    counts[key] += 1
            return counts, max(0, model.glyph_total - sum(counts))
        for key in master.get("keys") or []:
            if 0 <= key < 12:
                counts[key] += 1
        return counts, int(master.get("uncolored") or 0)

    @objc.python_method
    def _focused_counts(self, master: dict) -> tuple[list[int], int]:
        counts, unc = self._counts_of(master)
        fk = self.state["focus"]
        if fk is None:
            return counts, unc
        if fk < 0 or fk > 11:
            return [0] * 12, unc
        only = [0] * 12
        only[fk] = counts[fk]
        return only, self.model.glyph_total - counts[fk]

    @objc.python_method
    def _disc_field(self, master: dict, grey: bool) -> Any | None:
        """The blurred colour wheel (buildField) for a master, cached per state."""
        counts, unc = self._focused_counts(master)
        key = ("field", master["id"], tuple(counts), unc, grey, self.theme.is_dark())
        cached = self._disc_cache.get(key)
        if cached is not None:
            return cached
        total = sum(counts) + unc
        if not total:
            self._disc_cache[key] = None
            return None
        segs = []
        for index, count in enumerate(counts):
            if count > 0:
                segs.append((float(count), self.theme.step(index)))
        if unc > 0:
            segs.append((float(unc), (0.0392, 0.0402, 0.0455)))
        image = _wedge_image(
            segs,
            float(total),
            320.0,
            None,
            blur=320.0 * 0.125,
            saturation=0.0 if grey else 1.6,
            square=False,
            vignette=True,
        )
        self._disc_cache[key] = image
        return image

    @objc.python_method
    def _overlay(self, rx: float, ry: float, dimmed: bool, trim: float, frost: Any) -> Any:
        """The disc's static finish (white fill, frost, sheen, hot-spot, rim — or the
        dark trim when dimmed) with the hole left clear, rendered once per geometry
        so the per-frame spin only draws the rotating field underneath."""
        key = (round(rx, 2), round(ry, 2), dimmed, self.theme.is_dark())
        cached = self._overlay_cache.get(key)
        if cached is not None:
            return cached
        image = _disc_overlay(rx, ry, dimmed, trim, frost)
        self._overlay_cache[key] = image
        return image

    @objc.python_method
    def _frost_image(self) -> Any:
        if self._frost is not None:
            return self._frost
        size = 320.0
        image = AppKit.NSImage.alloc().initWithSize_((size, size))
        image.lockFocus()
        rng = random.Random(7)
        for _ in range(1600):
            r = rng.random() * 1.6 + 0.3
            fill(
                circle(rng.random() * size, rng.random() * size, r),
                (1.0, 1.0, 1.0, rng.random() * 0.07),
            )
        for _ in range(1100):
            r = rng.random() * 0.9 + 0.2
            fill(
                circle(rng.random() * size, rng.random() * size, r),
                (0.0, 0.0, 0.0, rng.random() * 0.05 + 0.008),
            )
        image.unlockFocus()
        self._frost = image
        return image

    @objc.python_method
    def _layout_tower(self) -> None:
        th, model, state = self.theme, self.model, self.state
        canvas = self.tower
        canvas.reset(None)
        masters = model.masters
        if not masters:
            return
        W = float(canvas.bounds().size.width)
        Hc = float(canvas.bounds().size.height)
        tilt = 0.5
        rx = min(92.0, W * 0.42)
        ry = rx * tilt
        top_y = ry + 16.0
        bot_pad = ry + 12.0
        visible = max(4, min(len(masters), int((Hc - top_y - bot_pad) // 29) + 1))
        vt = max(0.0, min(max(0, len(masters) - visible), self._tower_vt))
        self._tower_vt = vt
        dz = min(51.0, (Hc - top_y - bot_pad) / (visible - 1)) if visible > 1 else 0.0
        cx = W / 2.0
        sel = model.master_index(state["master"])
        win_bot = top_y + (visible - 1) * dz
        self._tower_geo = {
            "rx": rx,
            "ry": ry,
            "cx": cx,
            "topY": top_y,
            "dz": dz,
            "vt": vt,
            "visible": visible,
        }

        def cy_of(i: int) -> float:
            return top_y + (i - vt) * dz

        def vis(i: int) -> bool:
            c = cy_of(i)
            return top_y - dz * 1.6 <= c <= win_bot + dz * 1.6

        frost = self._frost_image()
        empty_fill = th.raw("track")
        trim, opacity = 0.5, 0.37
        for i in range(len(masters) - 1, -1, -1):
            if not vis(i):
                continue
            master = masters[i]
            cy = cy_of(i)
            dimmed = sel >= 0 and i != sel
            focused = sel >= 0 and i == sel
            field = self._disc_field(master, dimmed)
            if field is None:
                canvas.op(lambda cx=cx, cy=cy: _paint_empty(cx, cy, rx, ry, empty_fill))
                continue
            canvas.op(lambda cx=cx, cy=cy: _paint_shadow(cx, cy, rx, ry))
            overlay = self._overlay(rx, ry, dimmed, trim, frost)
            canvas.op(
                lambda cx=cx, cy=cy, field=field, overlay=overlay, dimmed=dimmed, focused=focused: (
                    _paint_disc(field, overlay, cx, cy, rx, ry, self._rot, dimmed, focused, opacity)
                )
            )
            canvas.hit(
                cx - rx, cy - ry, 2 * rx, 2 * ry, lambda e, mid=master["id"]: self.set_master(mid)
            )
            canvas.tip(cx - rx, cy - ry, 2 * rx, 2 * ry, master["name"])
        # the top disc shows the page background through its hole
        top_i = next((i for i in range(len(masters)) if vis(i)), -1)
        if top_i >= 0 and self._disc_field(masters[top_i], sel >= 0 and top_i != sel) is not None:
            cy = cy_of(top_i)
            canvas.op(lambda cy=cy: _paint_hole(cx, cy, rx, ry, th.raw("bg"), 0.7))


# --------------------------------------------------------------------------- #
# Disc painting (Color Tower) — module-level so ops stay small closures
# --------------------------------------------------------------------------- #


def _wedge_image(
    segs: list[tuple[float, Any]],
    total: float,
    size: float,
    base: Any | None,
    blur: float,
    saturation: float,
    square: bool,
    vignette: bool = False,
) -> Any:
    """Proportional colour wedges (a conic gradient) blurred with CoreImage, optionally
    vignetted at the centre and masked to a circle. Returns an NSImage ``size``²."""
    src = AppKit.NSImage.alloc().initWithSize_((size, size))
    src.lockFocus()
    cx = cy = size / 2.0
    if base is not None:
        rgba(base).set()
        AppKit.NSRectFill(AppKit.NSMakeRect(0, 0, size, size))
    if segs and total > 0:
        angle = -90.0
        radius = size * (0.72 if square else 0.46 * 1.25)
        for share, color in segs:
            span = share / total * 360.0
            path = AppKit.NSBezierPath.bezierPath()
            path.moveToPoint_((cx, cy))
            path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
                (cx, cy), radius, angle, angle + span, False
            )
            path.closePath()
            fill(path, color)
            angle += span
        if vignette:
            radial(cx, cy, size * 0.46 * 0.72, (0, 0, 0, 0.58), (0, 0, 0, 0))
    src.unlockFocus()
    image = _blurred(src, blur, saturation)
    if square:
        return image
    # mask to a circle (clip; compositing ops are unreliable inside lockFocus)
    out = AppKit.NSImage.alloc().initWithSize_((size, size))
    out.lockFocus()
    circle(cx, cy, size * 0.5).addClip()
    image.drawInRect_fromRect_operation_fraction_(
        AppKit.NSMakeRect(0, 0, size, size),
        AppKit.NSZeroRect,
        AppKit.NSCompositingOperationSourceOver,
        1.0,
    )
    out.unlockFocus()
    return out


def _blurred(image: Any, radius: float, saturation: float) -> Any:
    """CIGaussianBlur (+ CIColorControls saturation) of an NSImage, cropped to size."""
    if Quartz is None:
        return image
    try:
        size = image.size()
        tiff = image.TIFFRepresentation()
        ci = Quartz.CIImage.imageWithData_(tiff)
        if ci is None:
            return image
        extent = ci.extent()
        clamp = Quartz.CIFilter.filterWithName_("CIAffineClamp")
        clamp.setDefaults()
        clamp.setValue_forKey_(ci, "inputImage")
        clamped = clamp.valueForKey_("outputImage")
        blur = Quartz.CIFilter.filterWithName_("CIGaussianBlur")
        blur.setValue_forKey_(clamped, "inputImage")
        px_scale = float(extent.size.width) / float(size.width) if size.width else 1.0
        blur.setValue_forKey_(radius * px_scale, "inputRadius")
        blurred = blur.valueForKey_("outputImage")
        if saturation != 1.0:
            controls = Quartz.CIFilter.filterWithName_("CIColorControls")
            controls.setDefaults()
            controls.setValue_forKey_(blurred, "inputImage")
            controls.setValue_forKey_(saturation, "inputSaturation")
            blurred = controls.valueForKey_("outputImage")
        cropped = blurred.imageByCroppingToRect_(extent)
        rep = AppKit.NSCIImageRep.imageRepWithCIImage_(cropped)
        out = AppKit.NSImage.alloc().initWithSize_(size)
        out.addRepresentation_(rep)
        # flatten to a bitmap so later draws don't re-run the filter chain
        flat = AppKit.NSImage.alloc().initWithSize_(size)
        flat.lockFocus()
        out.drawInRect_fromRect_operation_fraction_(
            AppKit.NSMakeRect(0, 0, size.width, size.height),
            AppKit.NSZeroRect,
            AppKit.NSCompositingOperationSourceOver,
            1.0,
        )
        flat.unlockFocus()
        return flat
    except Exception:
        return image


def _ellipse_transform(cx: float, cy: float, rx: float, ry: float, rot: float = 0.0) -> Any:
    transform = AppKit.NSAffineTransform.transform()
    transform.translateXBy_yBy_(cx, cy)
    transform.scaleXBy_yBy_(1.0, ry / rx)
    if rot:
        transform.rotateByRadians_(rot)
    return transform


def _paint_empty(cx: float, cy: float, rx: float, ry: float, color: Any) -> None:
    AppKit.NSGraphicsContext.saveGraphicsState()
    _ellipse_transform(cx, cy, rx, ry).concat()
    fill(circle(0, 0, rx), rgba(color, 0.6))
    AppKit.NSGraphicsContext.restoreGraphicsState()


def _paint_shadow(cx: float, cy: float, rx: float, ry: float) -> None:
    AppKit.NSGraphicsContext.saveGraphicsState()
    _ellipse_transform(cx, cy + ry * 0.62, rx, ry).concat()
    grad = gradient(((0, 0, 0, 0.28), 0.0), ((0, 0, 0, 0.14), 0.6), ((0, 0, 0, 0.0), 1.0))
    grad.drawFromCenter_radius_toCenter_radius_options_((0, 0), 0.0, (0, 0), rx * 1.12, 0)
    AppKit.NSGraphicsContext.restoreGraphicsState()


def _disc_hole_clip(rx: float, hr: float) -> Any:
    """Even-odd clip: the disc minus its centre hole (the JS destination-out hole)."""
    clip = AppKit.NSBezierPath.bezierPath()
    clip.appendBezierPath_(circle(0, 0, rx))
    clip.appendBezierPath_(circle(0, 0, hr))
    clip.setWindingRule_(AppKit.NSEvenOddWindingRule)
    return clip


def _disc_overlay(rx: float, ry: float, dimmed: bool, trim: float, frost: Any) -> Any:
    """paintDisc's non-rotating layers as one image: white fill, frost, sheen, hot-spot
    and the rim (a dimmed disc gets the dark trim instead), hole left transparent."""
    margin = 1.05
    bw, bh = 2 * rx * margin, 2 * ry * margin
    image = AppKit.NSImage.alloc().initWithSize_((bw, bh))
    image.lockFocusFlipped_(True)
    AppKit.NSGraphicsContext.saveGraphicsState()
    _ellipse_transform(bw / 2.0, bh / 2.0, rx, ry).concat()
    hr = rx * 0.26
    _disc_hole_clip(rx, hr).addClip()
    disc = circle(0, 0, rx)
    if dimmed:
        fill(disc, (0, 0, 0, trim))
    else:
        fill(disc, (1, 1, 1, 0.05))
        frost.drawInRect_fromRect_operation_fraction_(
            AppKit.NSMakeRect(-rx, -rx, rx * 2, rx * 2),
            AppKit.NSZeroRect,
            AppKit.NSCompositingOperationSourceOver,
            0.45,
        )
        sheen = gradient(
            ((0, 0, 0, 0.11), 0.0),
            ((1, 1, 1, 0.01), 0.34),
            ((1, 1, 1, 0.02), 0.66),
            ((1, 1, 1, 0.09), 1.0),
        )
        sheen.drawFromPoint_toPoint_options_((0, -rx), (0, rx), 0)
        hot = gradient(((1, 1, 1, 0.075), 0.0), ((1, 1, 1, 0.0), 1.0))
        hot.drawFromCenter_radius_toCenter_radius_options_(
            (0, rx * 0.42), 0.0, (0, rx * 0.42), rx * 0.8, 0
        )
    # rim: a 2px ring lit from below (even-odd ring clip, vertical gradient)
    ring_clip = AppKit.NSBezierPath.bezierPath()
    ring_clip.appendBezierPath_(circle(0, 0, rx * 0.992 + 1.0))
    ring_clip.appendBezierPath_(circle(0, 0, rx * 0.992 - 1.0))
    ring_clip.setWindingRule_(AppKit.NSEvenOddWindingRule)
    ring_clip.addClip()
    rim = gradient(((0, 0, 0, 0.12), 0.0), ((1, 1, 1, 0.025), 0.5), ((1, 1, 1, 0.16), 1.0))
    rim.drawFromPoint_toPoint_options_((0, -rx), (0, rx), 0)
    AppKit.NSGraphicsContext.restoreGraphicsState()
    image.unlockFocus()
    return image


def _paint_disc(
    field: Any,
    overlay: Any,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    rot: float,
    dimmed: bool,
    focused: bool,
    opacity: float,
) -> None:
    """Per-frame disc paint: the halo + blurred colour field rotate (``rot``) inside
    an ellipse-minus-hole clip, then the cached static overlay lands on top. No
    offscreen buffer per frame, so the spin timer stays cheap. A dimmed disc is
    the grey field, trimmed dark (overlay) and translucent."""
    o = rx * 1.14
    alpha = opacity if dimmed else 1.0
    glow = 1.4 if focused else (0.0 if dimmed else 1.0)
    hr = rx * 0.26
    if glow > 0:  # halo: the field drawn slightly larger and faint (pure blur in the JS)
        AppKit.NSGraphicsContext.saveGraphicsState()
        _ellipse_transform(cx, cy, rx, ry, rot).concat()
        _disc_hole_clip(rx * 1.07, hr).addClip()
        for scale, a in ((1.006, 0.11), (1.025, 0.07), (1.06, 0.04)):
            hh = rx * scale
            field.drawInRect_fromRect_operation_fraction_(
                AppKit.NSMakeRect(-hh, -hh, hh * 2, hh * 2),
                AppKit.NSZeroRect,
                AppKit.NSCompositingOperationSourceOver,
                a * glow * alpha,
            )
        AppKit.NSGraphicsContext.restoreGraphicsState()
    AppKit.NSGraphicsContext.saveGraphicsState()
    _ellipse_transform(cx, cy, rx, ry, rot).concat()
    _disc_hole_clip(rx, hr).addClip()
    field.drawInRect_fromRect_operation_fraction_(
        AppKit.NSMakeRect(-o, -o, o * 2, o * 2),
        AppKit.NSZeroRect,
        AppKit.NSCompositingOperationSourceOver,
        0.95 * alpha,
    )
    AppKit.NSGraphicsContext.restoreGraphicsState()
    size = overlay.size()
    overlay.drawInRect_fromRect_operation_fraction_(
        AppKit.NSMakeRect(cx - size.width / 2.0, cy - size.height / 2.0, size.width, size.height),
        AppKit.NSZeroRect,
        AppKit.NSCompositingOperationSourceOver,
        alpha,
    )


def _paint_hole(cx: float, cy: float, rx: float, ry: float, bg: Any, alpha: float) -> None:
    """The top disc's hole reads the page background (JS destination-out at 70%)."""
    AppKit.NSGraphicsContext.saveGraphicsState()
    _ellipse_transform(cx, cy, rx, ry).concat()
    hr = rx * 0.26
    grad = gradient((rgba(bg, alpha), 0.0), (rgba(bg, alpha), 0.94), (rgba(bg, 0.0), 1.0))
    grad.drawFromCenter_radius_toCenter_radius_options_((0, 0), 0.0, (0, 0), hr, 0)
    AppKit.NSGraphicsContext.restoreGraphicsState()


# --------------------------------------------------------------------------- #
# Entry points
# --------------------------------------------------------------------------- #

_REPORTS: list = []  # keep controllers alive (PyObjC drops them otherwise)


def show_report(model: dict, title: str | None = None) -> Any:
    """Open (or reopen) the native report window for a built model dict."""
    for old in _REPORTS:
        try:
            if old._window is not None:
                old._window.close()
        except Exception:
            pass
    controller = AZColorflowNativeReport.alloc().initWithModel_(model)
    _REPORTS[:] = [controller]
    return controller.show(title)
