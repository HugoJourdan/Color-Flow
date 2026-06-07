# Color Flow Plugin — Workflow Features Design

**Date:** 2026-06-07
**Scope:** The live Glyphs palette (`plugin.py`) plus the shortcut-generation and profile-apply engines.
**Status:** Approved design, ready for implementation planning.

## Goal

Three live-workflow features for the palette: a keyboard **jump to next unfinished glyph**, a visible **focus mode**, and bundled **starter profiles** with a one-time first-run nudge and a colour legend.

## Architecture

All three live in `plugin.py` and lean on engines that already exist:

```
Jump          → new auto-generated shortcut script (matches the existing 12 toggles); shared step logic via embedded colornames
Focus mode    → render change in Update_Plugin_UI reading the already-tracked _focusColor
Starter       → bundled .colorflow JSON in Resources → colorflow_profile.parse → existing import-diff → _apply_profile
+ first-run   → a Glyphs.defaults flag gating a one-time message
+ legend      → a "?" panel in the action popover
```

No new storage formats; no changes to how colours map to steps. Each feature is independent.

## Components

### 1. Jump to next unfinished glyph (shortcut script)

- **Purpose:** bind a key that advances editing to the next glyph not yet at the final workflow step.
- **Definitions:**
  - **Final step** = the highest-ranked *visible* step in the workflow order (last meaningful line of `colorNames.txt`).
  - **Unfinished** = current master `layer.color` is not the final step key. Uncoloured and off-palette glyphs count as unfinished.
  - **Recipes ignored for v1** — uses the single global final step, not per-glyph recipe order. (Noted as a future refinement.)
- **Navigation:** from the current glyph in the active Edit tab, scan `font.glyphs` in font order for the next unfinished glyph (wrap around), then open it in the Edit view. If an Edit tab is open, move the cursor to that glyph; otherwise open a new tab at it. If none are unfinished, show an "All glyphs finished" message.
- **Build:** generated through the `tools/generate_shortcuts.py` pattern (a new template entry or a sibling script in `Color Flow Shortcut/`). Embeds the `colornames` module so step logic never diverges from the palette — same convention as the 12 toggle scripts.
- **Testable core:** extract the "given a list of (name, colorKey) and the order, return the index of the next unfinished after position P (wrapping)" logic into a pure helper (in `colornames` or a small sibling module) so it can be unit-tested without Glyphs.

### 2. Focus mode (render)

- **Purpose:** when a step is focused, dim the other palette rows so the focused colour pops. Palette-only; does not touch the Font View.
- **State:** `_focusColor` is **already** toggled by `rowClicked_` / `countClicked_` and already opens the step's tab — but nothing reads it for drawing. This feature adds the read.
- **Change:** in the row-rendering loop of `Update_Plugin_UI`, when `_focusColor is not None`, render non-focused rows at reduced opacity; the focused row stays full (optionally a subtle accent). Keep the existing tab-opening behaviour on click.
- **Clear:** re-clicking the focused row already sets `_focusColor` back to `None`; add `Escape` handling if not already present.

### 3. Starter profiles + first-run nudge + legend

- **Starter profiles:**
  - Ship the three workflows below as valid `.colorflow` JSON files under `Resources/` (e.g. `Resources/StarterProfiles/`).
  - Add a picker to the action popover (a `PopUpButton`, "Starter workflow…"). On select: load the bundled file via `colorflow_profile.parse`, show the **existing import diff/confirm** dialog, then apply via `_apply_profile` (writes `colorNames.txt` + label colours).
- **First-run nudge:**
  - Gate on a `Glyphs.defaults` flag (e.g. `com.hugojourdan.ColorFlow-FirstRunDone`).
  - On plugin start, if the flag is unset, show a one-time message/popover: "Color Flow tracks glyph progress by colour. Pick a starter workflow to begin." pointing at the picker. Set the flag afterward. Wrap so any failure never blocks plugin load.
- **Legend (plugin side):**
  - A "?" affordance in the popover opening a small list: each colour swatch + name + order position, plus one line on step vs free mode.

#### Proposed starter workflows (each a profile dict: `version`, `name`, `colorNames`, `freeMode`, `rainbowSource`, `labelColors`)

| Workflow | Steps (in order) → Glyphs label colour |
|---|---|
| **Spacing & Kerning** (3) | Spacing → Orange · Kerning → Blue · Review → Green |
| **Draw → Done** (5) | Rough → Red · Refine → Yellow · Spacing → Orange · Kerning → Blue · Approved → Green |
| **QA / Review** (4) | To-check → Red · Needs fix → Purple · Fixed → Yellow · Signed-off → Green |

Colour assignments use the standard Glyphs label palette (red = problem/start, green = done). Exact label indices and emoji are finalised when authoring the JSON.

## Data flow

- **Jump:** shortcut reads `colorNames` + current selection/tab → finds next unfinished → sets the active glyph in the Edit view.
- **Focus:** `_focusColor` → consumed by `Update_Plugin_UI` render.
- **Starter:** bundled JSON → `colorflow_profile.parse` → diff/confirm → `_apply_profile` → `colorNames.txt` + label colours.

## Error handling

- Jump handles: no font open, no Edit tab, all glyphs finished — each with a clear message, never a crash.
- Starter apply reuses profile validation (raises `ValueError` on malformed JSON) and the existing confirm dialog.
- First-run nudge is fully wrapped; failure is swallowed so it can never block load.

## Testing

- **Pure logic:** unit-test the "next unfinished index" helper (font-order wrap, all-finished, none-coloured, final-step glyph skipped).
- **Starter profiles:** a test that loads each bundled `.colorflow` file through `colorflow_profile.parse` and asserts it validates and round-trips — guarantees shipped presets are never broken.
- **Shortcut:** regenerate via `tools/generate_shortcuts.py`; `py_compile` + `ruff` on the new script.
- **Focus-mode render** is PyObjC/vanilla (excluded from coverage like the rest of `plugin.py`) → manual smoke in Glyphs.
- Keep `ruff` + `pyright` clean on touched Python; every function gets a return type hint.

## Risks / open implementation details (confirm at plan time)

- "Open the glyph in the Edit view" — confirm the right Glyphs API for setting the active glyph (move cursor in the current tab vs `newTab`); pick the least disruptive.
- Final-step definition interaction with recipes — v1 deliberately ignores recipes; document the limitation.
- Bundled-asset path resolution inside the `.glyphsPalette` bundle (how `Resources/` is located at runtime) — mirror how `colorNames.txt` / `report-loading.gif` are already resolved.

## Build order

Focus mode first (smallest, completes existing skeleton), then jump-to-next, then starter profiles + first-run + legend.
