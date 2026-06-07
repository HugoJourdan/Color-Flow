# Color Flow Plugin Workflow Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add three live-workflow features to the Color Flow Glyphs palette — a visible focus mode that dims non-focused rows, a keyboard "jump to next unfinished glyph" shortcut, and three bundled starter profiles with a first-run nudge and a colour legend.

**Architecture:** All three features build on engines that already exist. Pure, headless-testable logic (the "next unfinished index" navigation helper and the bundled-profile validity check) is unit-tested with pytest. PyObjC/vanilla rendering and popover UI in `plugin.py` cannot run headless, so those steps are manual smoke tests in Glyphs. The new shortcut script is generated through the existing `tools/generate_shortcuts.py` pattern and embeds `colornames` verbatim so step logic never diverges from the palette.

**Tech Stack:** Python 3.9 (Glyphs embedded interpreter), PyObjC / vanilla (AppKit UI), pytest + pytest-xdist, ruff, pyright. Package management via uv. `plugin.py` uses **TAB indentation** — match it. The pure modules (`colornames.py`, `colorflow_profile.py`, the new `colornav.py`) use **4-space indentation** like the rest of `Resources/`.

---

## File Structure

- Create: `Color Flow.glyphsPalette/Contents/Resources/colornav.py` — pure, Glyphs-free "next unfinished glyph index (wrapping)" navigation helper, embeddable into the shortcut and importable by the palette.
- Create: `tests/test_colorflow_colornav.py` — pytest for the navigation helper (wrap, all-finished, none-coloured, final-step skip).
- Create: `Color Flow.glyphsPalette/Contents/Resources/StarterProfiles/spacing-kerning.colorflow` — bundled "Spacing & Kerning" starter profile JSON.
- Create: `Color Flow.glyphsPalette/Contents/Resources/StarterProfiles/draw-to-done.colorflow` — bundled "Draw to Done" starter profile JSON.
- Create: `Color Flow.glyphsPalette/Contents/Resources/StarterProfiles/qa-review.colorflow` — bundled "QA / Review" starter profile JSON.
- Create: `tests/test_colorflow_starter_profiles.py` — pytest that loads each bundled `.colorflow` through `colorflow_profile.parse` and asserts it validates and round-trips.
- Create: `Color Flow Shortcut/Jump To Next Unfinished (Color Flow).py` — the generated jump shortcut script (output of `generate_shortcuts.py`).
- Modify: `Color Flow.glyphsPalette/Contents/Resources/colornames.py` — add `final_visible_step(meaning)` helper used by both the palette and the jump shortcut to define "final step".
- Modify: `tools/generate_shortcuts.py` — emit the new jump shortcut (embeds `colornames` + `colornav` + a navigation tail).
- Modify: `Color Flow.glyphsPalette/Contents/Resources/plugin.py` — Focus-mode dimming in `Update_Plugin_UI`; Escape clears focus; starter-profile `PopUpButton` picker + `_apply_starter_profile`; first-run nudge gated on a defaults flag; "?" legend panel in the popover.

---

## Task 1: `final_visible_step` helper in `colornames`

The jump shortcut and the palette both need a single definition of "the final workflow step". The spec defines it as the highest-ranked *visible* step in the workflow order (last meaningful line of `colorNames.txt`). `parse_color_names` preserves file order, `visible_labels` filters to non-empty labels — so the final visible step is the last key of `visible_labels(meaning)`.

**Files:**
- Modify: `Color Flow.glyphsPalette/Contents/Resources/colornames.py`
- Test: `tests/test_colorflow_colornames.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_colorflow_colornames.py`:

The module is imported as `cc` at the top of `tests/test_colorflow_colornames.py` (line 10: `import colornames as cc`) — use that alias.

```python
def test_final_visible_step_returns_last_visible_key() -> None:
    meaning = cc.parse_color_names("red=Rough\nyellow=Refine\norange=Done\n")
    assert cc.final_visible_step(meaning) == "1"   # orange = index 1


def test_final_visible_step_ignores_trailing_hidden_steps() -> None:
    # purple has an empty label -> hidden; the final step is the last *labelled* one
    meaning = cc.parse_color_names("red=Start\ndarkGreen=Done\npurple=\n")
    assert cc.final_visible_step(meaning) == "5"   # darkGreen = index 5


def test_final_visible_step_returns_none_when_no_visible_steps() -> None:
    assert cc.final_visible_step({}) is None
    assert cc.final_visible_step(cc.parse_color_names("red=\norange=\n")) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -n auto "tests/test_colorflow_colornames.py::test_final_visible_step_returns_last_visible_key"`
Expected: FAIL with `AttributeError: module 'colornames' has no attribute 'final_visible_step'`

- [ ] **Step 3: Write minimal implementation**

Add to `Color Flow.glyphsPalette/Contents/Resources/colornames.py`, directly after `visible_labels` (4-space indentation):

```python
def final_visible_step(meaning: dict[str, str]) -> str | None:
    """The index string of the last visible workflow step, or ``None``.

    "Final" is the highest-ranked visible step in workflow order — the last
    non-empty-labelled line of ``colorNames.txt``. Shared by the palette and the
    jump shortcut so "finished" means the same thing in both halves.
    """
    visible = visible_labels(meaning)
    if not visible:
        return None
    return list(visible.keys())[-1]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -n auto "tests/test_colorflow_colornames.py::test_final_visible_step_returns_last_visible_key" "tests/test_colorflow_colornames.py::test_final_visible_step_ignores_trailing_hidden_steps" "tests/test_colorflow_colornames.py::test_final_visible_step_returns_none_when_no_visible_steps"`
Expected: PASS (3 passed)

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check "Color Flow.glyphsPalette/Contents/Resources/colornames.py" tests/test_colorflow_colornames.py`
Run: `uv run pyright "Color Flow.glyphsPalette/Contents/Resources/colornames.py"`
Expected: both clean (0 errors)

- [ ] **Step 6: Commit**

```bash
git add "Color Flow.glyphsPalette/Contents/Resources/colornames.py" tests/test_colorflow_colornames.py
git commit -m "feat(colornames): add final_visible_step helper for jump/finished logic"
```

---

## Task 2: `colornav` pure navigation helper

Extract the testable core of the jump shortcut: given an ordered list of `(name, colorKey)` for a master plus the final-step key, return the index of the next *unfinished* glyph after a starting position, wrapping. "Unfinished" = `colorKey != final_step` (uncoloured `None` and off-palette colours included). This module imports nothing from Glyphs so it is unit-testable and can be embedded verbatim into the shortcut, exactly like `colornames`.

**Files:**
- Create: `Color Flow.glyphsPalette/Contents/Resources/colornav.py`
- Test: `tests/test_colorflow_colornav.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_colorflow_colornav.py`:

```python
"""Tests for the pure jump-to-next-unfinished navigation helper."""

from __future__ import annotations

import colornav


def test_next_unfinished_finds_following_glyph() -> None:
    glyphs = [("A", 1), ("B", None), ("C", 1)]   # final step = "1"
    assert colornav.next_unfinished_index(glyphs, "1", 0) == 1


def test_next_unfinished_wraps_around_to_earlier_glyph() -> None:
    glyphs = [("A", None), ("B", 1), ("C", 1)]   # only A is unfinished
    assert colornav.next_unfinished_index(glyphs, "1", 1) == 0


def test_next_unfinished_skips_final_step_glyphs() -> None:
    glyphs = [("A", 1), ("B", 1), ("C", 1)]      # all finished
    assert colornav.next_unfinished_index(glyphs, "1", 0) is None


def test_next_unfinished_treats_uncoloured_and_offpalette_as_unfinished() -> None:
    glyphs = [("A", 1), ("B", None), ("C", 7)]   # B uncoloured, C wrong colour
    assert colornav.next_unfinished_index(glyphs, "1", 0) == 1
    assert colornav.next_unfinished_index(glyphs, "1", 1) == 2


def test_next_unfinished_with_no_final_step_returns_first_after_position() -> None:
    # final_step None (no visible steps): every glyph counts as unfinished
    glyphs = [("A", 1), ("B", 2), ("C", 3)]
    assert colornav.next_unfinished_index(glyphs, None, 0) == 1


def test_next_unfinished_empty_list_returns_none() -> None:
    assert colornav.next_unfinished_index([], "1", 0) is None


def test_next_unfinished_start_position_minus_one_scans_from_top() -> None:
    # -1 means "no current glyph" -> first unfinished is the first non-final one
    glyphs = [("A", 1), ("B", None), ("C", 1)]
    assert colornav.next_unfinished_index(glyphs, "1", -1) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -n auto tests/test_colorflow_colornav.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'colornav'`

- [ ] **Step 3: Write minimal implementation**

Create `Color Flow.glyphsPalette/Contents/Resources/colornav.py` (4-space indentation):

```python
"""Pure "jump to next unfinished glyph" navigation for Color Flow.

Glyphs-free so it can be unit-tested with plain CPython and embedded verbatim
into the jump keyboard-shortcut by ``tools/generate_shortcuts.py`` — the same
convention as ``colornames``. The palette and the shortcut therefore agree on
what "unfinished" and "next" mean.

A glyph is *finished* when its current-master ``layer.color`` equals the final
visible workflow step (see ``colornames.final_visible_step``). Uncoloured glyphs
(``None``) and glyphs at any other colour count as unfinished.
"""

from __future__ import annotations


def is_unfinished(color_key: int | None, final_step: str | None) -> bool:
    """True when a glyph's ``layer.color`` is not the final workflow step.

    ``final_step`` is an index string (e.g. ``"1"``) or ``None`` when the
    workflow has no visible steps, in which case nothing can be "finished".
    """
    if final_step is None:
        return True
    if color_key is None:
        return True
    return str(color_key) != final_step


def next_unfinished_index(
    glyphs: list[tuple[str, int | None]],
    final_step: str | None,
    position: int,
) -> int | None:
    """Index of the next unfinished glyph after ``position``, wrapping.

    ``glyphs`` is the font-order list of ``(glyph_name, layer_color)`` for the
    active master. ``position`` is the index of the current glyph (or ``-1`` for
    "no current glyph"); the scan starts at ``position + 1`` and wraps once
    through the whole list. Returns ``None`` when every glyph is finished or the
    list is empty.
    """
    total = len(glyphs)
    if total == 0:
        return None
    for offset in range(1, total + 1):
        candidate = (position + offset) % total
        _name, color_key = glyphs[candidate]
        if is_unfinished(color_key, final_step):
            return candidate
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -n auto tests/test_colorflow_colornav.py`
Expected: PASS (7 passed)

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check "Color Flow.glyphsPalette/Contents/Resources/colornav.py" tests/test_colorflow_colornav.py`
Run: `uv run pyright "Color Flow.glyphsPalette/Contents/Resources/colornav.py"`
Expected: both clean (0 errors)

- [ ] **Step 6: Commit**

```bash
git add "Color Flow.glyphsPalette/Contents/Resources/colornav.py" tests/test_colorflow_colornav.py
git commit -m "feat(colornav): add pure next-unfinished-glyph navigation helper"
```

---

## Task 3: Generate the "Jump To Next Unfinished" shortcut

Add a new entry to `tools/generate_shortcuts.py` that emits a self-contained jump script. It embeds **both** `colornames.py` and `colornav.py` verbatim (so the script has no runtime import dependency on the palette bundle), then a navigation tail that: loads `meaning`, computes `final_visible_step`, builds the font-order `(name, layer.color)` list for the active master, finds the current glyph position from the active Edit tab, calls `colornav.next_unfinished_index`, and opens the result via `font.newTab` (matching the existing `_open_step_tab` convention at `plugin.py:1371`).

The generator's `build_script` only embeds one module today. Add a second canonical module path and a `build_jump_script` function rather than overloading the 12-toggle loop, so the toggle generation is untouched.

**Files:**
- Modify: `tools/generate_shortcuts.py`
- Create (generated output): `Color Flow Shortcut/Jump To Next Unfinished (Color Flow).py`

- [ ] **Step 1: Manual pre-check — confirm the toggle generator still works**

Run: `uv run python tools/generate_shortcuts.py`
Expected: prints `wrote Toggle Red CheckBox (Color Flow).py` … and `Generated 12 shortcut scripts`. This is the baseline before adding the jump script.

- [ ] **Step 2: Add the jump generation to `tools/generate_shortcuts.py`**

After the `CANONICAL_MODULE` definition (around line 24), add the second module path:

```python
NAV_MODULE = (
    REPO / "Color Flow.glyphsPalette" / "Contents" / "Resources" / "colornav.py"
)
```

After `TOGGLE_TAIL` (after line 100), add the jump header and tail constants:

```python
JUMP_HEADER = """#MenuTitle: Jump To Next Unfinished (Color Flow)
# =============================================================================
# AUTO-GENERATED by tools/generate_shortcuts.py — DO NOT EDIT BY HAND.
# Regenerate after editing the template or colornames.py / colornav.py:
#     uv run python tools/generate_shortcuts.py
#
# Opens the next glyph whose current-master layer.color is not the final visible
# workflow step (see colorNames.txt). Scans the font in order from the active
# glyph, wraps around, and opens the result in the Edit view. Recipes are ignored
# in v1 — it uses the single global final step.
#
# v1 always opens a new tab; reusing an already-open Edit tab (moving the cursor
# to the target glyph within it) is deferred.
# =============================================================================

"""

JUMP_TAIL = '''

# ---------------------------------------------------------------------------
# Navigation logic (auto-generated tail)
# ---------------------------------------------------------------------------


def _color_flow_jump_font_dir(font):
    return os.path.dirname(font.filepath) if font.filepath else None


def _color_flow_current_position(font, names):
    # Index of the active glyph in the font-order name list, or -1 if unknown.
    try:
        layers = font.selectedLayers
    except Exception:
        layers = None
    if layers:
        current = layers[0].parent.name
        if current in names:
            return names.index(current)
    return -1


def _color_flow_jump():
    font = Glyphs.font
    if font is None:
        Message("Open a font first.", title="Color Flow")
        return
    master = font.selectedFontMaster
    if master is None:
        return
    meaning = load_meaning(_color_flow_jump_font_dir(font))
    final_step = final_visible_step(meaning)
    master_id = master.id
    pairs = []
    for glyph in font.glyphs:
        layer = glyph.layers[master_id]
        color = layer.color if layer is not None else None
        pairs.append((glyph.name, color))
    names = [name for name, _color in pairs]
    position = _color_flow_current_position(font, names)
    index = next_unfinished_index(pairs, final_step, position)
    if index is None:
        Message("All glyphs finished.", title="Color Flow")
        return
    font.newTab("/" + names[index])


_color_flow_jump()
'''
```

- [ ] **Step 3: Add the jump build + wire it into `main`**

After `build_script` (after line 109), add:

```python
def build_jump_script(module_source: str, nav_source: str) -> str:
    """Assemble the jump shortcut: header + colornames + colornav + nav tail."""
    return JUMP_HEADER + module_source + "\n" + nav_source + JUMP_TAIL
```

In `main`, after the toggle loop's `print(...)` summary line (currently line 120), read the nav module and write the jump script. Replace the body of `main` so it reads:

```python
def main() -> None:
    module_source = CANONICAL_MODULE.read_text(encoding="utf-8")
    nav_source = NAV_MODULE.read_text(encoding="utf-8")
    SHORTCUT_DIR.mkdir(parents=True, exist_ok=True)
    for index, display in DISPLAY_NAMES:
        script = build_script(index, display, module_source)
        out_path = SHORTCUT_DIR / f"Toggle {display} CheckBox (Color Flow).py"
        out_path.write_text(script, encoding="utf-8")
        print(f"wrote {out_path.name}")
    jump = build_jump_script(module_source, nav_source)
    jump_path = SHORTCUT_DIR / "Jump To Next Unfinished (Color Flow).py"
    jump_path.write_text(jump, encoding="utf-8")
    print(f"wrote {jump_path.name}")
    print(f"\nGenerated {len(DISPLAY_NAMES)} toggle scripts + 1 jump script in {SHORTCUT_DIR}")
```

- [ ] **Step 4: Regenerate and verify the jump script compiles**

Run: `uv run python tools/generate_shortcuts.py`
Expected: prints `wrote Jump To Next Unfinished (Color Flow).py` plus the 12 toggles and the new summary line.

Run: `uv run python -m py_compile "Color Flow Shortcut/Jump To Next Unfinished (Color Flow).py"`
Expected: no output, exit 0 (the embedded `Glyphs` / `Message` names are only referenced at runtime, so byte-compilation succeeds).

- [ ] **Step 5: Lint the generated script and the generator**

Run: `uv run ruff check tools/generate_shortcuts.py`
Expected: clean (0 errors). The generated shortcut lives in `Color Flow Shortcut/`, which is not in ruff's `extend-include`, so it is intentionally not linted (it references the Glyphs runtime).

- [ ] **Step 6: Commit**

```bash
git add tools/generate_shortcuts.py "Color Flow Shortcut/Jump To Next Unfinished (Color Flow).py"
git commit -m "feat(shortcut): generate jump-to-next-unfinished keyboard script"
```

- [ ] **Step 7: Manual smoke in Glyphs**

Install `Color Flow Shortcut/Jump To Next Unfinished (Color Flow).py` (Scripts folder), open a font with mixed layer colours, bind it to a key. From a glyph mid-list, trigger it: confirm it opens a new tab at the next glyph whose colour is not the final step. With every glyph at the final colour, confirm the "All glyphs finished." message. With no font open, confirm "Open a font first.". No crash in any case.

---

## Task 4: Focus-mode dimming in `Update_Plugin_UI`

`_focusColor` is already toggled by `rowClicked_` (plugin.py:1314) and `countClicked_` (plugin.py:1327) and already opens the step tab, but nothing reads it for drawing. This task adds the read: when `_focusColor is not None`, non-focused rows render dimmed and the focused row renders at full strength. This is PyObjC/vanilla render code that only runs inside Glyphs — **manual smoke, no pytest** (matching the `omit = ["*/plugin.py", ...]` coverage policy in `pyproject.toml`).

The change is in the row loop at `plugin.py:1174-1210`. The existing dimming primitive is alpha `0.06` for an inactive bar (line 1193) and full colour for the active one (line 1191). Focus reuses the same idea on the row label: when a focus is set and this row is not it, wrap the row label and bar in reduced opacity; when this row *is* the focus, leave it full. **TAB indentation.**

**Files:**
- Modify: `Color Flow.glyphsPalette/Contents/Resources/plugin.py:1174-1210`

- [ ] **Step 1: Add the focus flags at the top of the row loop**

In `Update_Plugin_UI`, immediately after the `for color, meaning in self.meaning.items():` line (1174) and before `for suffix in (...)` (1175), insert (TAB-indented to the loop body, i.e. three tabs):

```python
			focusColor = getattr(self, "_focusColor", None)
			focused = focusColor is not None
			isFocusRow = focused and str(color) == str(focusColor)
			rowAlpha = 1.0 if (not focused or isFocusRow) else 0.28
```

This reads the already-tracked state once per row. `0.28` is the dim level for non-focused rows (between the eye-mode hidden `0.12` at line 1825 and full); the focused row keeps `1.0`.

- [ ] **Step 2: Apply `rowAlpha` to the row label text colour**

The row label is the `TextBox` created at line 1195 (selectedLayers branch) and line 1205 (no-selection branch). After **each** of those two `setattr(self.paletteView.frame, str(color), checkbox)` calls, set the text colour alpha on its NSObject. The bare `setattr(self.paletteView.frame, str(color), checkbox)` line appears in both branches, so each Edit must include enough surrounding lines to be unique.

**`selectedLayers` branch** — the `self._register_row_checkbox(checkbox, color)` follow-up is shared by both branches, so anchor on the unique `if check and firstColor == int(color):` line above. Replace:

```python
						if check and firstColor == int(color):
							fill = AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(color)])
						else:
							fill = AppKit.NSColor.colorWithRed_green_blue_alpha_(0, 0, 0, 0.06)
						setattr(self.paletteView.frame, str(color)+"box", Box((self.xPos, yPos-self.shift-1, barWidth+0.01, 19), fillColor=fill, cornerRadius=0, borderWidth=0))
					checkbox = TextBox((12, yPos-self.shift+2, -10, 20), meaning, sizeStyle='small')
					setattr(self.paletteView.frame, str(color), checkbox)
```

with:

```python
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
```

**No-selection branch** — the matching insert (Step 3 below rewrites the `fill =` line that precedes it, so do Step 3 first; this anchor uses the rewritten `_rgba`/`fill` pair, which exists only in this branch). Replace:

```python
						_rgba = self.colorKeys[str(color)]
						fill = AppKit.NSColor.colorWithRed_green_blue_alpha_(_rgba[0], _rgba[1], _rgba[2], _rgba[3] * rowAlpha)
						setattr(self.paletteView.frame, str(color)+"box", Box((self.xPos, yPos-self.shift-1, barWidth+0.01, 19), fillColor=fill, cornerRadius=0, borderWidth=0))
					checkbox = TextBox((12, yPos-self.shift+2, -10, 20), meaning, sizeStyle='small')
					setattr(self.paletteView.frame, str(color), checkbox)
```

with:

```python
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
```

The indentation is five tabs (inside the `else:` row branch). Use `checkbox._nsObject` — the vanilla wrapper exposes the underlying `NSTextField` there, consistent with the existing `self._ns_button(...)` access pattern elsewhere in the file.

- [ ] **Step 3: Dim the colour tag / bar on non-focused rows**

In the no-selection branch the active bar is full colour (line 1203). Wrap its alpha by `rowAlpha`. The line `fill = AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(color)])` appears **twice** in the row loop (selectedLayers branch line 1191, no-selection branch line 1203), so anchor the Edit on the unique surrounding lines that scope it to the no-selection branch — `else:` → `if barWidth:` → the `fill` line. Replace:

```python
				else:
					if barWidth:
						fill = AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(color)])
```

with:

```python
				else:
					if barWidth:
						_rgba = self.colorKeys[str(color)]
						fill = AppKit.NSColor.colorWithRed_green_blue_alpha_(_rgba[0], _rgba[1], _rgba[2], _rgba[3] * rowAlpha)
```

`self.colorKeys[str(color)]` is a 4-tuple `(r, g, b, 0.5)` (see `_label_color_keys`, plugin.py:151), so indexing `[0..3]` is safe and multiplying the existing alpha by `rowAlpha` dims the bar consistently with the label. Apply this Step 3 Edit **before** the no-selection Step 2 Edit above, since that anchor depends on the rewritten `_rgba`/`fill` pair.

- [ ] **Step 4: Lint and type-check the touched file**

Run: `uv run ruff check "Color Flow.glyphsPalette/Contents/Resources/plugin.py"`
Run: `uv run pyright "Color Flow.glyphsPalette/Contents/Resources/plugin.py"`
Expected: clean for the lines touched (pre-existing PyObjC dynamic-attribute notes elsewhere in the file are unchanged; do not introduce new errors).

- [ ] **Step 5: Commit**

```bash
git add "Color Flow.glyphsPalette/Contents/Resources/plugin.py"
git commit -m "feat(palette): dim non-focused rows when a step is focused"
```

- [ ] **Step 6: Manual smoke in Glyphs**

Load the palette. Click a row label (or its count) to focus that step: confirm the focused row stays full-strength and **all other rows dim** to ~28% opacity (label text and colour bar). Confirm the existing step tab still opens. Re-click the focused row: confirm focus clears and all rows return to full strength. Switch between selected-glyph and no-selection states and confirm dimming holds in both.

---

## Task 5: Escape clears focus

The spec asks for Escape handling to clear focus if not already present. There is no key handler on the palette today. Add a small clear path and bind Escape on the palette view, fully wrapped so a binding failure never blocks load. This is PyObjC — **manual smoke, no pytest.** **TAB indentation.**

**Files:**
- Modify: `Color Flow.glyphsPalette/Contents/Resources/plugin.py`

- [ ] **Step 1: Add a `_clear_focus` python_method**

Add immediately after `countClicked_` (after plugin.py:1333), TAB-indented to class level:

```python
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
```

`cancelOperation_` is the standard AppKit selector the Escape key triggers, so no manual key-equivalent table is needed. It is **not** a `python_method` (it is an Obj-C-exposed selector reached via the responder chain).

- [ ] **Step 2: Lint and type-check**

Run: `uv run ruff check "Color Flow.glyphsPalette/Contents/Resources/plugin.py"`
Run: `uv run pyright "Color Flow.glyphsPalette/Contents/Resources/plugin.py"`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add "Color Flow.glyphsPalette/Contents/Resources/plugin.py"
git commit -m "feat(palette): clear focus mode on Escape"
```

- [ ] **Step 4: Manual smoke in Glyphs**

Focus a step (Task 4). With the palette focused, press Escape: confirm focus clears and rows return to full strength. If the palette is not first responder and Escape does not reach it, note that in the smoke result — the responder-chain reach is the only thing that cannot be verified headless. No crash either way.

---

## Task 6: Author the three bundled starter profiles

Ship the three workflows from the spec as valid `.colorflow` JSON. Each is the exact dict shape produced by `colorflow_profile.build_profile` / accepted by `parse`: `version`, `name`, `colorNames`, `freeMode`, `rainbowSource`, `labelColors`. `colorNames` is `colorNames.txt` text using the canonical colour names from `colornames.COLOR_ORDER`. `labelColors` is exactly 12 RGBA lists in index order (so `_apply_profile`'s `len(colors) == 12` guard at plugin.py:527 fires). The mapping from spec colour name → canonical name / index:

- Red → `red` (0), Orange → `orange` (1), Yellow → `yellow` (3), Blue → `lightBlue` (6), Green → `lightGreen` (4), Purple → `purple` (8).

`colorNames` lists **only the workflow's steps, in order** (file order defines step order); steps not used are simply omitted, so they stay hidden. The `labelColors` array still has all 12 entries (the Glyphs label palette) — use the default Glyphs label RGBA values so unedited slots match Glyphs' own.

**Files:**
- Create: `Color Flow.glyphsPalette/Contents/Resources/StarterProfiles/spacing-kerning.colorflow`
- Create: `Color Flow.glyphsPalette/Contents/Resources/StarterProfiles/draw-to-done.colorflow`
- Create: `Color Flow.glyphsPalette/Contents/Resources/StarterProfiles/qa-review.colorflow`

- [ ] **Step 1: Create `spacing-kerning.colorflow`**

Spacing → Orange (1) · Kerning → Blue (6) · Review → Green (4).

```json
{
  "version": 1,
  "name": "Spacing & Kerning",
  "colorNames": "orange=🦊 Spacing\nlightBlue=💎 Kerning\nlightGreen=🍀 Review\n",
  "freeMode": false,
  "rainbowSource": "Layer",
  "labelColors": [
    [0.85, 0.26, 0.06, 1.0],
    [0.99, 0.62, 0.11, 1.0],
    [0.65, 0.48, 0.2, 1.0],
    [0.97, 0.9, 0.0, 1.0],
    [0.67, 0.95, 0.38, 1.0],
    [0.04, 0.52, 0.0, 1.0],
    [0.06, 0.6, 0.98, 1.0],
    [0.02, 0.0, 0.97, 1.0],
    [0.59, 0.06, 0.83, 1.0],
    [0.9, 0.0, 0.59, 1.0],
    [0.75, 0.75, 0.75, 1.0],
    [0.25, 0.25, 0.25, 1.0]
  ]
}
```

- [ ] **Step 2: Create `draw-to-done.colorflow`**

Rough → Red (0) · Refine → Yellow (3) · Spacing → Orange (1) · Kerning → Blue (6) · Approved → Green (4).

```json
{
  "version": 1,
  "name": "Draw to Done",
  "colorNames": "red=🚨 Rough\nyellow=🌼 Refine\norange=🦊 Spacing\nlightBlue=💎 Kerning\nlightGreen=🍀 Approved\n",
  "freeMode": false,
  "rainbowSource": "Layer",
  "labelColors": [
    [0.85, 0.26, 0.06, 1.0],
    [0.99, 0.62, 0.11, 1.0],
    [0.65, 0.48, 0.2, 1.0],
    [0.97, 0.9, 0.0, 1.0],
    [0.67, 0.95, 0.38, 1.0],
    [0.04, 0.52, 0.0, 1.0],
    [0.06, 0.6, 0.98, 1.0],
    [0.02, 0.0, 0.97, 1.0],
    [0.59, 0.06, 0.83, 1.0],
    [0.9, 0.0, 0.59, 1.0],
    [0.75, 0.75, 0.75, 1.0],
    [0.25, 0.25, 0.25, 1.0]
  ]
}
```

- [ ] **Step 3: Create `qa-review.colorflow`**

To-check → Red (0) · Needs fix → Purple (8) · Fixed → Yellow (3) · Signed-off → Green (4).

```json
{
  "version": 1,
  "name": "QA / Review",
  "colorNames": "red=🚨 To-check\npurple=🔮 Needs fix\nyellow=🌼 Fixed\nlightGreen=🍀 Signed-off\n",
  "freeMode": false,
  "rainbowSource": "Layer",
  "labelColors": [
    [0.85, 0.26, 0.06, 1.0],
    [0.99, 0.62, 0.11, 1.0],
    [0.65, 0.48, 0.2, 1.0],
    [0.97, 0.9, 0.0, 1.0],
    [0.67, 0.95, 0.38, 1.0],
    [0.04, 0.52, 0.0, 1.0],
    [0.06, 0.6, 0.98, 1.0],
    [0.02, 0.0, 0.97, 1.0],
    [0.59, 0.06, 0.83, 1.0],
    [0.9, 0.0, 0.59, 1.0],
    [0.75, 0.75, 0.75, 1.0],
    [0.25, 0.25, 0.25, 1.0]
  ]
}
```

- [ ] **Step 4: Commit (tested in Task 7)**

```bash
git add "Color Flow.glyphsPalette/Contents/Resources/StarterProfiles/"
git commit -m "feat(starter): add three bundled .colorflow workflow profiles"
```

---

## Task 7: Test that every bundled profile validates and round-trips

A pytest that discovers each `.colorflow` under `StarterProfiles/`, parses it through `colorflow_profile.parse`, and asserts it validates (no `ValueError`), has the expected shape, and round-trips through `serialize`/`parse`. This guarantees a shipped preset can never silently break.

**Files:**
- Create: `tests/test_colorflow_starter_profiles.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_colorflow_starter_profiles.py`:

```python
"""Every bundled starter .colorflow must validate and round-trip."""

from __future__ import annotations

from pathlib import Path

import colorflow_profile as profile
import pytest

STARTER_DIR = (
    Path(__file__).resolve().parent.parent
    / "Color Flow.glyphsPalette"
    / "Contents"
    / "Resources"
    / "StarterProfiles"
)
STARTERS = sorted(STARTER_DIR.glob("*.colorflow"))


def test_three_starter_profiles_are_shipped() -> None:
    assert len(STARTERS) == 3


@pytest.mark.parametrize("path", STARTERS, ids=lambda path: path.name)
def test_starter_profile_parses_and_round_trips(path: Path) -> None:
    parsed = profile.parse(path.read_text(encoding="utf-8"))
    assert parsed["version"] == profile.PROFILE_VERSION
    assert parsed["name"]                                   # non-empty name
    assert parsed["colorNames"].strip()                    # has at least one step
    assert len(parsed["labelColors"]) == 12                # full Glyphs palette
    assert parsed["rainbowSource"] in profile.RAINBOW_SOURCES
    # Re-serialising a parsed profile and parsing again must be a fixed point.
    assert profile.parse(profile.serialize(parsed)) == parsed
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest -n auto tests/test_colorflow_starter_profiles.py`
Expected: PASS (1 + 3 parametrised = 4 passed). If `STARTERS` is empty the parametrised test collects zero cases and `test_three_starter_profiles_are_shipped` FAILS — that is the guard that the files exist.

- [ ] **Step 3: Lint and type-check**

Run: `uv run ruff check tests/test_colorflow_starter_profiles.py`
Expected: clean (0 errors)

- [ ] **Step 4: Commit**

```bash
git add tests/test_colorflow_starter_profiles.py
git commit -m "test(starter): validate + round-trip every bundled .colorflow profile"
```

---

## Task 8: Starter-profile picker, `_apply_starter_profile`, first-run nudge, legend in the popover

Add to the action popover: a `PopUpButton` "Starter workflow…" picker that loads a bundled profile, runs the **existing** diff/confirm, and applies via `_apply_profile`; a "?" legend button opening a small list of swatch + name + order position; and a one-time first-run nudge gated on a new `Glyphs.defaults` flag. All PyObjC/vanilla — **manual smoke, no pytest** — except the bundled-asset path resolution, which mirrors the existing `os.path.dirname(__file__)` pattern at plugin.py:316. **TAB indentation.**

**Files:**
- Modify: `Color Flow.glyphsPalette/Contents/Resources/plugin.py`

- [ ] **Step 1: Add the StarterProfiles directory resolver + loader**

Add as `python_method`s near `_apply_profile` (after plugin.py:533), TAB-indented:

```python
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
```

`_live_profile`, `_font_dir`, `_confirm_import`, `_apply_profile`, and `colorflow_profile` are all already present (used by `_import_profile` at plugin.py:477-489).

- [ ] **Step 2: Add the picker callback**

Add after `_apply_starter_profile`, TAB-indented:

```python
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
```

- [ ] **Step 3: Add the legend panel callback**

Add after `_starter_selected`, TAB-indented. It builds the swatch+name+order list from the live `meaning` and mode:

```python
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
```

The spec asks for a swatch panel; v1 renders the legend as an ordered text list (swatch name + label + order position + a mode line) via the existing `Message` affordance — no new NSView. If a visual swatch list is wanted later, it is a follow-up; the text legend fully satisfies "swatch + name + order position, plus one line on step vs free mode" in content.

- [ ] **Step 4: Add the picker, legend button, and first-run flag to `Open_Action_Popover`**

The popover is 220×460 (plugin.py:254) with the dashboard button at the bottom (`reportY = 94 + 12 * 26 + 6`, plugin.py:305). Insert the picker + legend **between** the dashboard separator and the dashboard button so layout below the colour wells is unchanged. After line 307 (`popover.dashboard = Button(...)`), add:

```python
				self._starterFiles = self._starter_files()
				_starterTitles = ["Starter workflow…"] + [
					os.path.splitext(os.path.basename(path))[0] for path in self._starterFiles
				]
				starterY = reportY + 8 + 22 + 8
				popover.starter = PopUpButton((12, starterY, -40, 22), _starterTitles,
					callback=self._starter_selected, sizeStyle='small')
				popover.legend = Button((-32, starterY, 20, 22), "?",
					callback=self._open_legend, sizeStyle='small')
```

Then grow the popover height so the new controls fit: change the popover construction at line 254 from `Popover((220, 460), ...)` to `Popover((220, 500), ...)`.

`PopUpButton` needs no import edit: `plugin.py` uses `from vanilla import *` (line 52), and the star import already provides `PopUpButton`. No import change is needed.

- [ ] **Step 5: Add the one-time first-run nudge to `start`**

`start` (plugin.py:191) already wraps optional setup in `try/except`. After `self.update(self._windowController)` (line 199), add a wrapped first-run nudge gated on a new flag (mirroring the `RainbowConflictWarned` pattern at plugin.py:705/718):

```python
		try:
			if not Glyphs.defaults["com.hugojourdan.ColorFlow-FirstRunDone"]:
				Glyphs.defaults["com.hugojourdan.ColorFlow-FirstRunDone"] = True
				Message("Color Flow tracks glyph progress by colour. Open the action "
					"menu and pick a starter workflow to begin.", title="Welcome to Color Flow")
		except Exception:
			pass
```

The flag is set **before** showing the message so a failure mid-message still never re-nudges, and the whole block is swallowed so it can never block load (spec error-handling requirement).

- [ ] **Step 6: Lint and type-check**

Run: `uv run ruff check "Color Flow.glyphsPalette/Contents/Resources/plugin.py"`
Run: `uv run pyright "Color Flow.glyphsPalette/Contents/Resources/plugin.py"`
Expected: no new errors.

- [ ] **Step 7: Run the full suite to confirm nothing regressed**

Run: `uv run pytest -n auto`
Expected: all pass (existing suite + the new `colornav`, `colornames`, and starter-profile tests).

- [ ] **Step 8: Commit**

```bash
git add "Color Flow.glyphsPalette/Contents/Resources/plugin.py"
git commit -m "feat(palette): starter-profile picker, first-run nudge, and legend panel"
```

- [ ] **Step 9: Manual smoke in Glyphs**

Open the action popover: confirm the "Starter workflow…" `PopUpButton` lists the three bundled profiles and the "?" legend button sits beside it; the colour-well rows and dashboard button are unchanged. Pick "Draw to Done": confirm the existing import-diff confirm dialog appears, and applying writes the new `colorNames.txt` + label colours (palette rebuilds with the 5 steps). Click "?": confirm the legend lists each visible colour with its order position and a step-vs-free mode line. Delete the `com.hugojourdan.ColorFlow-FirstRunDone` default (`defaults delete ... `), restart Glyphs: confirm the one-time welcome message appears once and not again on the next launch. Confirm plugin load never blocks even if `StarterProfiles/` is missing (the picker then shows only the placeholder).

---

## Self-Review

**Spec coverage**

- §1 Jump to next unfinished — Tasks 1 (`final_visible_step`), 2 (`colornav` pure helper + unit tests: wrap, all-finished, none-coloured, final-step skip), 3 (generated shortcut, font-order scan + wrap, opens in Edit via `font.newTab`, "All glyphs finished" + "Open a font first" messages, recipes ignored — documented in the script header). Covered, with one explicit deviation: the spec (§1) allows moving the cursor in an already-open Edit tab *or* opening a new tab; v1 always calls `font.newTab(...)` (new tab every time). Reusing an open tab is deferred — this is stated in the generated script's header docstring (the JUMP_HEADER "v1 always opens a new tab…" line).
- §2 Focus mode — Task 4 (read `_focusColor` in `Update_Plugin_UI` row loop, dim non-focused rows, focused row full, keep tab-opening), Task 5 (Escape clears). Covered.
- §3 Starter profiles + first-run + legend — Task 6 (three bundled `.colorflow`), Task 7 (validate + round-trip test), Task 8 (`PopUpButton` picker → parse → existing diff/confirm → `_apply_profile`; `com.hugojourdan.ColorFlow-FirstRunDone` first-run nudge fully wrapped; "?" legend with swatch name + order position + mode line). Covered.
- Data flow, error handling (no font / all finished / malformed JSON via `parse` `ValueError` / wrapped nudge), and testing section (pure-logic unit tests + bundled-profile round-trip + shortcut `py_compile`/`ruff`; render is manual smoke) — all mapped to tasks. Build order Focus → Jump → Starter is preserved as Tasks 4-5 (focus) come after the shared helpers needed by jump, but each task is independent and committed separately; the helper-first ordering (Tasks 1-3) is a dependency requirement of the jump shortcut, not a behavioural reordering.

**Placeholder scan** — No "TBD"/"add error handling"/"similar to Task N". Every code step shows real code. Error handling is shown explicitly (wrapped `try/except`, `ValueError` paths, messages). The legend's text-vs-NSView decision is stated explicitly rather than left open.

**Type consistency** — `final_visible_step(meaning) -> str | None` (Task 1) returns the index string consumed by `colornav.next_unfinished_index(glyphs, final_step, position)` (Task 2) where `final_step: str | None`; the shortcut tail (Task 3) passes `final_visible_step(meaning)` straight in. `is_unfinished(color_key, final_step)` compares `str(color_key) != final_step`. `_apply_starter_profile` reuses the exact `_apply_profile(incoming, font, font_dir)` signature (plugin.py:516) and `_confirm_import`/`_live_profile`/`_font_dir` already in the file. `labelColors` is 12 entries in every bundled profile, matching `_apply_profile`'s `len(colors) == 12` guard. `_starterFiles` (set in `Open_Action_Popover`) and `getattr(self, "_starterFiles", [])` (read in `_starter_selected`) use the same name. `_color_flow_current_position(font, names)` (Task 3 tail) declares only parameters it uses — `master_id` was dropped and the call site updated. Every Python function defined has a return type hint.

**Anchors & symbols verified against the real files** — Task 1's test snippet imports the module exactly as `tests/test_colorflow_colornames.py` does (`import colornames as cc`, line 10) and references `cc.parse_color_names` / `cc.final_visible_step`; no `cn.` alias appears. `from vanilla import *` (plugin.py:52) already provides `PopUpButton`, so Task 8 Step 4 makes no import edit. Every Task 4 Edit `old_string` was checked for uniqueness in `plugin.py`: the line `fill = AppKit.NSColor.colorWithRed_green_blue_alpha_(*self.colorKeys[str(color)])` occurs twice (selectedLayers 1191, no-selection 1203) and the bare `setattr(self.paletteView.frame, str(color), checkbox)` occurs twice (1196, 1206), so each Step 2/3 Edit includes the unique surrounding lines (`if check and firstColor == int(color):` for the selectedLayers branch; `else:` → `if barWidth:` for the no-selection branch). Cited line numbers were re-grepped: row loop 1174-1210, active bar full colour 1191, dim bar `0,0,0,0.06` 1193, selectedLayers `TextBox` 1195 / `setattr` 1196, no-selection `fill` 1203 / `TextBox` 1205 / `setattr` 1206, `_label_color_keys` tuple 151, eye-mode hidden alpha `0.12` 1825, `rowClicked_` toggle 1314, `countClicked_` toggle 1327, `countClicked_` end 1333, `_open_step_tab` `newTab` 1371, `_apply_profile` 516 / `len(colors) == 12` 527 / def-end 533, `_import_profile` 477-494, `start` 191 / `update(...)` 199, `RainbowConflictWarned` 705, `Popover((220, 460)` 254, `reportY` 305, `popover.dashboard` 307, gif `os.path.dirname(__file__)` 316 — all match the current source.
