# pyright: reportOptionalMemberAccess=false, reportOptionalCall=false
# SceneKit/AppKit/Quartz names are imported in a guarded try/except (they only
# resolve inside Glyphs) and bound to None otherwise; every use site is gated on
# _SCENEKIT_AVAILABLE so the None placeholders are never touched. Suppress the
# Optional-access diagnostics that pairing produces rather than narrowing each
# class reference by hand in the Glyphs-only builders.
"""Color Tower — native SceneKit (Apple 3D) build of the disc-stack visualizer.

A SceneKit alternative to the WebView ``tower.html`` page: one thin disc per
master, stacked, each disc's top face textured with that master's label-colour
distribution (a blurred proportional wheel — same idea as the canvas version).
SceneKit lights give the front/back shading for free and ``allowsCameraControl``
handles drag/orbit/zoom.

Mirrors the hosting pattern proven in the Argus plugin's design-space cube:

* SceneKit/AppKit imports are guarded — the module imports cleanly outside Glyphs
  (``_SCENEKIT_AVAILABLE`` is then ``False``) so the pure geometry helpers stay
  unit-testable.
* Auto-rotation is a native ``SCNAction`` on a rig node — NEVER a Python
  ``renderer:updateAtTime:`` delegate, which deadlocks the GIL against the
  SceneKit transaction lock (see Argus' notes).
* Materials stay opaque (no ``setTransparency_`` near 1.0, which SceneKit rounds
  to the opaque pass and breaks render ordering).

The per-disc face image and the scene build are wrapped so any failure degrades
gracefully (image -> flat average colour; no SceneKit -> caller uses WebView).
"""

from __future__ import annotations

import math

LABEL_SLOTS = 12

try:  # only resolves inside Glyphs' embedded Python
    from AppKit import (
        NSBezierPath,
        NSColor,
        NSGradient,
        NSImage,
        NSMakeRect,
    )
    from Quartz import CIFilter, CIImage
    from AppKit import NSCIImageRep
    from SceneKit import (
        SCNAction,
        SCNCamera,
        SCNCylinder,
        SCNLight,
        SCNMaterial,
        SCNNode,
        SCNScene,
        SCNVector3Make,
    )

    _SCENEKIT_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only outside Glyphs
    NSBezierPath = NSColor = NSGradient = NSImage = NSMakeRect = None
    CIFilter = CIImage = NSCIImageRep = None
    SCNAction = SCNCamera = SCNCylinder = SCNLight = None
    SCNMaterial = SCNNode = SCNScene = SCNVector3Make = None
    _SCENEKIT_AVAILABLE = False


# --------------------------------------------------------------------------- #
# Pure geometry / colour helpers (unit-tested; no AppKit/SceneKit needed)
# --------------------------------------------------------------------------- #

def proportional_wedges(counts: list[int]) -> list[tuple[float, float, int]]:
    """Map a master's 12-slot counts to proportional pie wedges.

    Returns ``[(start_deg, end_deg, slot), ...]`` for each present colour, the
    arc width proportional to that colour's share of the master's coloured
    glyphs. Spans 0..360 with no gaps. Empty when nothing is coloured."""
    total = sum(counts)
    if total <= 0:
        return []
    wedges: list[tuple[float, float, int]] = []
    accumulated = 0
    for slot, count in enumerate(counts):
        if count <= 0:
            continue
        start = accumulated / total * 360.0
        accumulated += count
        end = accumulated / total * 360.0
        wedges.append((start, end, slot))
    return wedges


def hue_rgb(slot: int) -> tuple[float, float, float]:
    """RGB (0..1) for a label slot — the vivid favicon/button-GIF rainbow hue,
    ``hsl((slot/12)*360, 100%, 55%)``, matching the canvas ``hueHsl()``."""
    return _hsl_to_rgb((slot / float(LABEL_SLOTS)) % 1.0, 1.0, 0.55)


def average_rgb(counts: list[int]) -> tuple[float, float, float]:
    """Count-weighted average of the present slots' hues — the flat fallback
    colour when a disc's distribution image can't be built. Neutral grey when
    nothing is coloured."""
    total = sum(counts)
    if total <= 0:
        return (0.78, 0.78, 0.80)
    red = green = blue = 0.0
    for slot, count in enumerate(counts):
        if count <= 0:
            continue
        r, g, b = hue_rgb(slot)
        red += r * count
        green += g * count
        blue += b * count
    return (red / total, green / total, blue / total)


def _hsl_to_rgb(hue: float, sat: float, light: float) -> tuple[float, float, float]:
    if sat == 0:
        return (light, light, light)
    q = light * (1.0 + sat) if light < 0.5 else light + sat - light * sat
    p = 2.0 * light - q
    return (_hue_to_channel(p, q, hue + 1.0 / 3.0),
            _hue_to_channel(p, q, hue),
            _hue_to_channel(p, q, hue - 1.0 / 3.0))


def _hue_to_channel(p: float, q: float, t: float) -> float:
    if t < 0.0:
        t += 1.0
    if t > 1.0:
        t -= 1.0
    if t < 1.0 / 6.0:
        return p + (q - p) * 6.0 * t
    if t < 1.0 / 2.0:
        return q
    if t < 2.0 / 3.0:
        return p + (q - p) * (2.0 / 3.0 - t) * 6.0
    return p


# --------------------------------------------------------------------------- #
# Disc face image (AppKit) — proportional wheel, centre-darkened, blurred
# --------------------------------------------------------------------------- #

def disc_face_image(counts: list[int], size: int = 512):
    """Render a master's distribution as a blurred proportional colour wheel
    (NSImage) for the disc's top face. Returns ``None`` on any failure so the
    caller falls back to a flat colour."""
    if not _SCENEKIT_AVAILABLE:
        return None
    try:
        wedges = proportional_wedges(counts)
        base = NSImage.alloc().initWithSize_((size, size))
        base.lockFocus()
        center = (size / 2.0, size / 2.0)
        radius = size  # overscan past the corners so the whole square is opaque
        if not wedges:
            NSColor.colorWithCalibratedWhite_alpha_(0.82, 1.0).set()
            NSBezierPath.bezierPathWithRect_(NSMakeRect(0, 0, size, size)).fill()
        else:
            for start_deg, end_deg, slot in wedges:
                red, green, blue = hue_rgb(slot)
                NSColor.colorWithCalibratedRed_green_blue_alpha_(red, green, blue, 1.0).set()
                path = NSBezierPath.bezierPath()
                path.moveToPoint_(center)
                # offset by -90 so slot 0 starts at 12 o'clock, like the canvas
                path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(
                    center, radius, 90.0 - start_deg, 90.0 - end_deg, True)
                path.closePath()
                path.fill()
            # darken toward the centre for depth around the bore
            inner = size / 2.0 * 0.72
            dark = NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.58)
            clear = NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.0)
            gradient = NSGradient.alloc().initWithStartingColor_endingColor_(dark, clear)
            circle = NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(center[0] - inner, center[1] - inner, inner * 2.0, inner * 2.0))
            gradient.drawInBezierPath_relativeCenterPosition_(circle, (0.0, 0.0))
        base.unlockFocus()
        return _blurred(base, radius=size * 0.04) or base
    except Exception:
        return None


def _blurred(image, radius: float):
    """Gaussian-blur an NSImage via Core Image; returns None on failure."""
    try:
        ci = CIImage.imageWithData_(image.TIFFRepresentation())
        flt = CIFilter.filterWithName_("CIGaussianBlur")
        flt.setValue_forKey_(ci, "inputImage")
        flt.setValue_forKey_(radius, "inputRadius")
        out = flt.valueForKey_("outputImage")
        if out is None:
            return None
        rep = NSCIImageRep.imageRepWithCIImage_(out)
        result = NSImage.alloc().initWithSize_(image.size())
        result.addRepresentation_(rep)
        return result
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Scene (SceneKit)
# --------------------------------------------------------------------------- #

def build_scene(model: dict):
    """Build the SCNScene for the Color Tower from a tower model
    (``{"total", "masters":[{"name","counts","uncolored"}]}``). Returns the
    scene, or ``None`` if SceneKit is unavailable."""
    if not _SCENEKIT_AVAILABLE:
        return None
    masters = model.get("masters") or []
    scene = SCNScene.scene()
    root = scene.rootNode()
    try:
        scene.background().setContents_(NSColor.colorWithCalibratedWhite_alpha_(0.92, 1.0))
    except Exception:
        pass

    rig = SCNNode.node()
    root.addChildNode_(rig)

    disc_radius = 1.0
    disc_height = 0.10
    gap = 0.34
    count = len(masters)
    top = (count - 1) * gap / 2.0 if count else 0.0

    for index, master in enumerate(masters):
        counts = master.get("counts") or [0] * LABEL_SLOTS
        disc = SCNCylinder.cylinderWithRadius_height_(disc_radius, disc_height)
        cap = SCNMaterial.material()
        face = disc_face_image(counts)
        if face is not None:
            cap.diffuse().setContents_(face)
        else:
            red, green, blue = average_rgb(counts)
            cap.diffuse().setContents_(
                NSColor.colorWithCalibratedRed_green_blue_alpha_(red, green, blue, 1.0))
        side = SCNMaterial.material()
        side.diffuse().setContents_(NSColor.colorWithCalibratedWhite_alpha_(0.86, 1.0))
        # SCNCylinder material order: [side, top, bottom]; top carries the face.
        disc.setMaterials_([side, cap, cap])
        node = SCNNode.nodeWithGeometry_(disc)
        # first master at the base, last on top (matches the canvas tower)
        node.setPosition_(SCNVector3Make(0.0, -top + index * gap, 0.0))
        rig.addChildNode_(node)

    _add_lights(root)
    _add_camera(root, top)
    _autorotate(rig)
    return scene


def _add_lights(root) -> None:
    key_node = SCNNode.node()
    key = SCNLight.light()
    try:
        key.setType_("directional")
        key.setIntensity_(820)
    except Exception:
        pass
    key_node.setLight_(key)
    key_node.setPosition_(SCNVector3Make(-2.0, 4.0, 4.0))
    key_node.setEulerAngles_(SCNVector3Make(-0.7, -0.3, 0.0))
    root.addChildNode_(key_node)

    fill_node = SCNNode.node()
    fill = SCNLight.light()
    try:
        fill.setType_("directional")
        fill.setIntensity_(300)
    except Exception:
        pass
    fill_node.setLight_(fill)
    fill_node.setPosition_(SCNVector3Make(3.0, 1.5, 3.0))
    fill_node.setEulerAngles_(SCNVector3Make(-0.2, 0.6, 0.0))
    root.addChildNode_(fill_node)

    ambient_node = SCNNode.node()
    ambient = SCNLight.light()
    try:
        ambient.setType_("ambient")
        ambient.setColor_(NSColor.colorWithCalibratedWhite_alpha_(0.55, 1.0))
    except Exception:
        pass
    ambient_node.setLight_(ambient)
    root.addChildNode_(ambient_node)


def _add_camera(root, top: float) -> None:
    cam_node = SCNNode.node()
    cam = SCNCamera.camera()
    try:
        cam.setUsesOrthographicProjection_(True)
        cam.setOrthographicScale_(max(1.4, top + 1.3))
        cam.setZNear_(0.1)
        cam.setZFar_(100.0)
    except Exception:
        pass
    cam_node.setCamera_(cam)
    cam_node.setPosition_(SCNVector3Make(0.0, top + 2.4, 6.5))
    cam_node.setEulerAngles_(SCNVector3Make(-0.5, 0.0, 0.0))
    root.addChildNode_(cam_node)


def _autorotate(rig) -> None:
    # Native SCNAction only — a Python render delegate would deadlock the GIL
    # against SceneKit's transaction lock (see Argus' freeze notes).
    try:
        spin = SCNAction.rotateByX_y_z_duration_(0.0, math.pi * 2.0, 0.0, 18.0)
        rig.runAction_(SCNAction.repeatActionForever_(spin))
    except Exception:
        pass
