"""Regression: ColorFlow framework-override methods must be @objc.python_method.

These methods either share a name with an inherited ObjC selector (e.g.
``update``, a 0-arg PalettePlugin/NSObject selector) or are PalettePlugin
lifecycle hooks. If the ``@objc.python_method`` decorator is missing, PyObjC
tries to bridge the Python method as the inherited selector and raises
``objc.BadPrototypeError`` at class creation -- the whole plugin then fails to
load ("'update' expects 0 arguments, <function ColorFlow.update> has 1
positional arguments"). The ``update`` decorator was dropped once during the
licensing work and shipped a crash on load; this guard prevents a repeat.

The module cannot be imported outside Glyphs (it pulls in GlyphsApp/AppKit at
import time), so we assert on the source text, like test_plugin_source.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

RESOURCES = (
    Path(__file__).resolve().parent.parent
    / "Color Flow.glyphsPalette"
    / "Contents"
    / "Resources"
)
PLUGIN_SOURCE = (RESOURCES / "plugin.py").read_text(encoding="utf-8")

# ColorFlow methods that MUST carry @objc.python_method.
FRAMEWORK_OVERRIDES = ("settings", "start", "update", "__del__")


@pytest.mark.parametrize("method", FRAMEWORK_OVERRIDES)
def test_framework_override_is_objc_python_method(method: str) -> None:
    marker = f"\n\tdef {method}("
    assert marker in PLUGIN_SOURCE, f"method {method} not found in plugin.py"
    idx = PLUGIN_SOURCE.index(marker)
    preceding = PLUGIN_SOURCE[:idx].rstrip()
    assert preceding.endswith("@objc.python_method"), (
        f"ColorFlow.{method} must be decorated @objc.python_method "
        "or PyObjC raises BadPrototypeError at class creation"
    )
