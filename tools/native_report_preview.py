"""Render the native (AppKit) report offscreen to PNGs for visual checks.

Needs a Python with PyObjC (the uv venv has none):
    /opt/homebrew/bin/python3 tools/native_report_preview.py [out_dir]

Writes window snapshots (overview, master, timeline, calendar, light theme,
sparse history with the Timeline chip disabled, funnel) plus *_body.png (the full scrolled body) using the sample
model from dashboard_sample (colour overrides dropped so the default palette
shows).
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "AZ-Colorflow.glyphsPlugin" / "Contents" / "Resources"))
sys.path.insert(0, str(ROOT / "tools"))

import AppKit  # noqa: E402
import dashboard_sample  # noqa: E402
from azcolorflow_native_report import AZColorflowNativeReport  # noqa: E402


def _snapshot(view, path: Path) -> None:
    bounds = view.bounds()
    rep = view.bitmapImageRepForCachingDisplayInRect_(bounds)
    view.cacheDisplayInRect_toBitmapImageRep_(bounds, rep)
    data = rep.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, {})
    data.writeToFile_atomically_(str(path), True)


def _sample(keep_dates: int | None = None) -> dict:
    model = dashboard_sample._model()
    model.pop("colors", None)
    if keep_dates is not None:
        # a sparse history (1 or 2 snapshots) disables the Timeline chip
        dates = model["trend"]["dates"][:keep_dates]
        model["trend"]["dates"] = dates
        model["trend"]["series"] = model["trend"]["series"][:keep_dates]
        last = dates[-1]
        for per_master in model["journeyIndex"].values():
            for name, events in list(per_master.items()):
                per_master[name] = [event for event in events if event[0] <= last]
    return model


def _controller(model: dict, out: Path):
    controller = AZColorflowNativeReport.alloc().initWithModel_(copy.deepcopy(model))
    window = controller._ensure_window()
    window.setFrame_display_(AppKit.NSMakeRect(0, 0, 1180, 840), False)
    controller._layout_frames()

    def shot(name: str) -> None:
        controller.update()
        window.contentView().layoutSubtreeIfNeeded()
        _snapshot(window.contentView(), out / f"{name}.png")
        _snapshot(controller.body, out / f"{name}_body.png")
        print("wrote", out / f"{name}.png")

    return controller, shot


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tmp"
    out.mkdir(parents=True, exist_ok=True)
    AppKit.NSApplication.sharedApplication()
    model = _sample()
    controller, shot = _controller(model, out)
    shot("overview")
    controller.state["master"] = model["masters"][0]["id"]
    shot("master")
    controller.state["funnelOpen"] = True
    controller.state["focus"] = 4
    shot("master_funnel_focus")
    controller.state["funnelOpen"] = False
    controller.state["focus"] = None
    controller.state["view"] = "timeline"
    shot("timeline_master")
    controller.state["master"] = None
    shot("timeline")
    controller.state["tlScrub"] = 1
    shot("timeline_scrubbed")
    controller.state["tlScrub"] = None
    controller.state["tlPane"] = "calendar"
    shot("calendar")
    controller.state["tlPane"] = "graph"
    controller.state["view"] = "tabs"
    controller._toggle_theme()
    shot("overview_light")
    for n in (1, 2):
        sparse_controller, sparse_shot = _controller(_sample(keep_dates=n), out)
        sparse_controller.toggle_view("timeline")  # disabled below 3 snapshots: stays on Overview
        assert sparse_controller.state["view"] == "tabs", sparse_controller.model.timeline_lock()
        sparse_shot(f"sparse_{n}")


if __name__ == "__main__":
    main()
