# Swap Option Color-Label Routing — Design

**Date:** 2026-06-10
**Branch:** `feature/report-and-plugin-features`
**Status:** approved (design), pending spec review

## Problem

In Glyphs 3, clicking a color swatch in the Font View sets the **glyph's** color label; holding **Option** while clicking sets the **active layer's** color instead. This fork is hard-coded in the compiled method `-[GSFontViewController setColorIndex:]`, which reads `[[NSApp currentEvent] modifierFlags]` and bit-tests bit 19 (`NSEventModifierFlagOption`) per selected layer. There is no preference, custom parameter, or hidden default that swaps it (confirmed by disassembly of the x86_64 slice + a live NSConnection runtime probe, 2026-06-10).

Hugo wants the routing **inverted**: plain click → layer color, Option-click → glyph color. Color Flow's entire model already treats `layer.color` as the single source of truth, so plain-click→layer matches the plugin's philosophy.

## Approach

**Method replacement (swizzle) of `-[GSFontViewController setColorIndex:]`**, installed when the Color Flow palette loads.

Why full replacement rather than IMP-preserving swizzle: the original IMP re-reads `modifierFlags` internally, so calling it from our wrapper cannot invert the decision — the original would just re-make the stock choice. We must reimplement the (small, self-contained) method body. The replacement reads a toggle at **call time**, so flipping the toggle needs no re-swizzle.

Rejected alternatives:
- **IMP-preserving swizzle** — original IMP useless for inversion (re-reads flags); only usable for the OFF path. Extra PyObjC IMP-call fragility for near-zero benefit.
- **NSEvent local monitor** mutating the Option flag during dispatch — timing-fragile, leaks into unrelated Option usage. Rejected.

## Components

### 1. `colorflow_routing.py` — pure, unit-tested

No AppKit imports. Holds the decision logic so it is 100% headless-testable.

```python
MOUSE_EVENT_TYPES: frozenset[int]  # NSEvent mouse type rawValues (down/up: left, right, other)

def should_apply_swap(event_type: int | None, mouse_types: frozenset[int] = MOUSE_EVENT_TYPES) -> bool:
    """True only when the current event is a real mouse interaction."""

def resolve_color_target(option_pressed: bool, swap_enabled: bool) -> Literal["glyph", "layer"]:
    """Stock: option->layer, none->glyph. With swap: XOR(option, swap)."""
```

Truth table (`resolve_color_target`):

| option_pressed | swap_enabled | target |
|---|---|---|
| False | False | glyph |
| True  | False | layer |
| False | True  | layer |
| True  | True  | glyph |

i.e. `target = "layer" if (option_pressed ^ swap_enabled) else "glyph"`.

### 2. plugin.py — install hook + replacement method

- **Module-level installer** `_install_color_routing_hook()`:
  - Idempotent via a class-level guard flag (`getattr(cls, "_cf_routing_installed", False)`), so reloading/multiple palettes don't double-install.
  - Resolves `objc.lookUpClass("GSFontViewController")`; on failure logs and no-ops.
  - Replaces `setColorIndex:` using PyObjC class method assignment for an existing ObjC selector. The replacement is a Python function decorated with the matching ObjC type signature `v@:C` (void, self, SEL, unsigned char) so dispatch works.
  - Whole body wrapped in `try/except` — matches the existing guarded-registration pattern; a missing SDK symbol or signature mismatch must never break palette load.
- **Replacement method** `_cf_setColorIndex_(self, color_index)`:
  1. `event = NSApp.currentEvent()`
  2. `swap = bool(Glyphs.defaults[SWAP_KEY])`
  3. `etype = event.type() if event else None`
  4. If `not should_apply_swap(etype)` → **stock glyph routing**: set `layer.glyph.colorIndex = color_index` for each selected layer (ignore Option; safe default for programmatic/keyboard callers).
  5. Else: `option = bool(event.modifierFlags() & NSEventModifierFlagOption)`; `target = resolve_color_target(option, swap)`; loop `self.selectedLayers()`, set `layer.colorIndex` (target=="layer") or `layer.glyph.colorIndex` (target=="glyph"), with `color_index` passed through unchanged (incl. `0xFF` NoColor reset).
  6. Wrap the mutation loop in the document's `disableUpdateInterface` / `enableUpdateInterface` (mirrors stock behavior so the UI updates once).
- `SWAP_KEY = "com.hugojourdan.ColorFlow-SwapColorRouting"` (matches existing `com.hugojourdan.ColorFlow-*` defaults convention).
- Call `_install_color_routing_hook()` once from the palette's `start()`.

### 3. Popover toggle

In `Open_Action_Popover`, add one `CheckBox` to the existing Settings section (alongside `freeMode` / `storeInFont` / `exportingOnly`):

- Label: **"Swap Option color routing (plain → layer)"**
- State initialised from `Glyphs.defaults[SWAP_KEY]`.
- Callback `_popover_swap_routing(self, sender)` writes the bool to `Glyphs.defaults[SWAP_KEY]`.
- Insert as a new stacked row; bump popover height and shift the rows below it (recipes button / legend) by the row pitch used in that section (~22px). No re-swizzle on toggle — the replacement reads the default at call time.

## Failure handling

- Hook install fully guarded; failure → log line, palette loads normally with stock routing intact.
- Guard against non-click callers: if `currentEvent` is not a mouse event, fall back to stock glyph routing (prevents misrouting if Glyphs ever calls `setColorIndex:` programmatically or from a key event while Option happens to be held).
- `0xFF` (NoColor / reset) flows through the same routing unchanged.

## Testing

- `tests/test_colorflow_routing.py` — 100% of `colorflow_routing.py`: full XOR truth table (4 rows) + `should_apply_swap` for each mouse type, a non-mouse type, and `None`.
- AppKit swizzle + popover wiring: `py_compile` only headless; **requires Hugo's one-time Glyphs smoke** (ObjC dispatch + NSPopover can't be headless-tested). Smoke checklist:
  1. Plain-click a swatch → layer color set, glyph color unchanged.
  2. Option-click → glyph color set.
  3. Toggle the checkbox OFF → behavior returns to stock (plain→glyph, Option→layer) with no restart.
  4. Reset (NoColor) routes the same way.
  5. Keyboard color shortcut (no mouse event) → glyph routing, no crash.

## Out of scope

- Configurable modes beyond invert (always-layer / always-glyph).
- Compiled-ObjC delivery (stays PyObjC in the existing palette bundle).
- Touching the ~4,900 lines of uncommitted work already in the tree — this feature is committed in isolation via explicit path adds.
