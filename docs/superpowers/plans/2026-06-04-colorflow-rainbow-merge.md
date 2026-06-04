# Color Flow + Rainbow FontView Merge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge Rainbow FontView's color-section grouping and inline label renaming into the Color Flow palette, behind one shared colorNames module, as a single `.glyphsPalette` bundle.

**Architecture:** Grow the existing `Color Flow.glyphsPalette`. One pure, unit-tested `colornames.py` is the single source of truth (palette + Font-View + the 12 shortcuts). A `fontview.py` holds the ported Rainbow grouping engine. `plugin.py` is the palette: checkbox/progress UI + inline rename + a Font-View on/off toggle, all driven by one dirty-checked `UPDATEINTERFACE` handler.

**Tech Stack:** Python 3 (Glyphs embedded interpreter), PyObjC/AppKit, vanilla, GlyphsApp API. Dev: `uv` + `pytest` for the pure logic; manual testing inside Glyphs for GUI.

**Spec:** `docs/superpowers/specs/2026-06-04-colorflow-rainbow-merge-design.md`

**Testing reality:** Only `colornames.py` (and the pure parts ported from `rainbow_core`) are unit-testable. GUI behavior (palette rendering, gestures, Font-View reorder) is verified manually in Glyphs after each task via `Plugin → Reload Plugins`. Each task lists its manual check.

**Branch:** `feature/colorflow-rainbow-merge` (already created; P0 below is committed).

---

## File Structure (target)

```
Color Flow.glyphsPalette/Contents/Resources/
├── plugin.py        # PalettePlugin: palette UI, inline rename, menu item, both update jobs
├── colornames.py    # single source of truth (renamed/expanded from colorflow_colornames.py)
├── fontview.py      # Font-View grouping engine (ported from Rainbow's plugin.py + rainbow_core)
tools/generate_shortcuts.py   # embeds colornames.py into the 12 toggle scripts
tests/                        # pytest for colornames.py
docs/superpowers/{specs,plans}/
```

## P0 — Foundation (DONE, committed)

- [x] Shared `colorflow_colornames.py` (parse, layer_color_for_state, count_states, default_state, key-file resolve/ensure, defaults fallback, broken-symlink guard) + tests.
- [x] `tools/generate_shortcuts.py` + 12 regenerated self-contained shortcuts (master.id key, colorNames.txt, self-healing counts).
- [x] `plugin.py`: wired to the module; settings() crash-guard; self-healing `Get_Master_Counts`; callback-leak fix; copy-by-value; zero-glyph guard; Info.plist typo.
- [x] Spec + this plan.

> Note: `plugin.py` still contains a temporary debug `print("Color Flow [Update_Plugin_UI] error:" …)` and the legacy `print("Freeze ?")` / `print("master.name")` and dead `self.Glyphs.font` block — all removed in P1.

---

## P1 — Stabilize the palette

**Outcome:** the palette refreshes by *mutating* reused widgets behind a cheap dirty-check (no per-fire teardown), no dead/debug code, Smart Filters actually match, Setup handles hidden colors. Prerequisite for the P4 row redesign (stable widgets can host the rename field + gesture).

**Files:** Modify `Color Flow.glyphsPalette/Contents/Resources/plugin.py`. Pure helpers added to `colorflow_colornames.py` get tests in `tests/test_colorflow_colornames.py`.

### Task 1.1 — Dirty-signature helper (pure, TDD)

**Files:** Modify `colorflow_colornames.py`; Test `tests/test_colorflow_colornames.py`.

- [ ] **Step 1 — failing test.** Add:

```python
def test_selection_signature_changes_with_master_layer_or_state():
    base = cc.selection_signature("m1", [("a", {"0": True})])
    assert cc.selection_signature("m1", [("a", {"0": True})]) == base
    assert cc.selection_signature("m2", [("a", {"0": True})]) != base      # master change
    assert cc.selection_signature("m1", [("a", {"0": False})]) != base     # state change
    assert cc.selection_signature("m1", [("b", {"0": True})]) != base      # selection change
    assert cc.selection_signature("m1", []) != base                        # empty selection
```

- [ ] **Step 2 — run, expect fail.** `uv run pytest -q -k selection_signature` → FAIL (no attribute `selection_signature`).
- [ ] **Step 3 — implement.** Add to `colorflow_colornames.py`:

```python
def selection_signature(master_id, layer_states):
    """Cheap, hashable fingerprint of what the palette renders.

    layer_states: list of (glyph_name, state_dict). Returns a tuple so update()
    can early-return when nothing the UI depends on has changed.
    """
    items = tuple(
        (name, tuple(sorted((str(k), bool(v)) for k, v in (state or {}).items())))
        for name, state in layer_states
    )
    return (master_id, items)
```

- [ ] **Step 4 — run, expect pass.** `uv run pytest -q -k selection_signature` → PASS. Then `uv run pytest -q` (all green) and `uvx ruff check "Color Flow.glyphsPalette/Contents/Resources/colorflow_colornames.py"`.
- [ ] **Step 5 — commit.** `git commit -am "feat(colornames): selection signature for palette dirty-check"` (+ Co-Authored-By trailer).

### Task 1.2 — Build palette rows once in settings()

**Files:** Modify `plugin.py` (`settings`, new `_build_rows`).

- [ ] **Step 1 — implement.** In `settings()`, after `self.meaning` is loaded, create per-color widgets **once** and store handles in `self.rows = {}`: for each `color, label` in `self.meaning.items()` build a label-less `CheckBox` (the box), a clickable label `TextBox`, a bar `Box`, a count `TextBox`, positioned by row index; keep them on `self.paletteView.frame` and in `self.rows[color]`. Remove the colorTag/line creation duplication by doing it in the same loop. Leave `Update_Plugin_UI` in place for now (next task rewires it).
- [ ] **Step 2 — manual check.** Reload in Glyphs: palette still draws all rows (values may be stale until 1.3). No Macro errors.
- [ ] **Step 3 — commit.** `git commit -am "refactor(plugin): build palette rows once in settings()"`.

### Task 1.3 — Rewrite update()/Update_Plugin_UI to mutate, dirty-checked

**Files:** Modify `plugin.py` (`update`, `Update_Plugin_UI`).

- [ ] **Step 1 — implement.** Replace the teardown/rebuild body of `Update_Plugin_UI` with mutation of `self.rows`: `checkbox.set(value)`, `label.set(text)`, `count.set("✅" or f"{n}/{glyphCount}")`, `bar.setPosSize(...)`/show-hide. Compute counts via `self.Get_Master_Counts`. At the top of `update()`: `if not self.font: return`; build `selection_signature` from selected layers + master; early-return if unchanged since `self._lastSig`. Delete the dead `if self.Glyphs.font:` block (fixes the `self.Glyphs` typo, M5) and the temporary debug `print`. Remove the `print("Freeze ?")` / `print("master.name")` lines.
- [ ] **Step 2 — manual check.** Reload: rows show correct checks/counts; arrow-key through glyphs (no flicker, no lag on the big font); toggle a box (count updates, layer color sets); switch master (counts update). No Macro errors.
- [ ] **Step 3 — commit.** `git commit -am "perf(plugin): reuse widgets + dirty-check update(), drop dead/debug code"`.

### Task 1.4 — CheckBox_Callback uses shared derivation + self-healing counts

**Files:** Modify `plugin.py` (`CheckBox_Callback`).

- [ ] **Step 1 — implement.** Rewrite `CheckBox_Callback`: resolve color key from the row (store the key on each row, not by matching label text — removes the label-collision bug). For each selected layer: flip the bit; set `layer.color = colornames.layer_color_for_state(state, order)`; then set the master counts via `self.Get_Master_Counts` recompute (authoritative) rather than ad-hoc +=. Wrap in `font.disableUpdateInterface()/enableUpdateInterface()` + an undo group.
- [ ] **Step 2 — manual check.** Toggle single + multi-selection; Cmd-Z restores both checkbox and color; counts stay correct.
- [ ] **Step 3 — commit.** `git commit -am "fix(plugin): robust checkbox callback with shared color derivation + undo"`.

### Task 1.5 — Smart Filter predicate fix (verify syntax first)

**Files:** Modify `plugin.py` (`Generate_Color_Flow_Smart_Filter`).

- [ ] **Step 1 — verify.** In the Macro panel, create a Smart Filter by hand that matches "layer has userData key X", inspect `CustomFilter.plist` to learn the exact predicate Glyphs writes for a userData-key test. (Current code writes `'<i>' IN layer.userData`, but the plugin stores keys named `com.hugojourdan.ColorFlow_Color_<i>`.)
- [ ] **Step 2 — implement.** Rewrite the predicate to match the keys actually written (or change what is written) so generated filters select the right layers. Narrow the broad `except:` to `OSError`/`PermissionError` for the not-writable message; surface other errors. Fix the overwrite path (`pl.remove` of a freshly-built dict never matches the stale entry).
- [ ] **Step 3 — manual check.** Generate filters, restart Glyphs, confirm each filter selects the expected layers.
- [ ] **Step 4 — commit.** `git commit -am "fix(plugin): correct Smart Filter predicate + error reporting"`.

### Task 1.6 — Setup hidden-color edge + cleanup

**Files:** Modify `plugin.py` (`Setup_Color_Flow`), `Info.plist`.

- [ ] **Step 1 — implement.** In `Setup_Color_Flow`, derive checked steps from `layer.color` using the shared order; when `layer.color` is not a visible step, leave it unchecked rather than marking all steps done. Remove the dead `selectedLayers` local. Remove remaining commented-out blocks / debug prints flagged in P0 note. Confirm Info.plist has no leftover issues.
- [ ] **Step 2 — manual check.** Run Setup on a master with mixed colors; checks reflect each glyph's color; no over-marking.
- [ ] **Step 3 — commit.** `git commit -am "fix(plugin): Setup handles hidden colors; remove dead code"`.

**P1 done when:** palette renders by mutation, no flicker/lag on the 1147-glyph font, toggles + undo correct, Smart Filters work, no debug prints, all pytest green.

---

## P2 — Unify `colornames.py`

**Outcome:** one module replaces both `colorflow_colornames.py` and Rainbow's `rainbow_core.py`; adopts the robust `GSGlyphsInfo` support path.

### Task 2.1 — Rename module + add int/None canonical layer (TDD)
- [ ] Rename `colorflow_colornames.py` → `colornames.py`; update the `import` in `plugin.py`, `tools/generate_shortcuts.py`, and `tests/`.
- [ ] Add `NO_COLOR=-1`, `NONE_TOKEN`, `COLOR_NAMES` reverse map, and a `parse(text)` returning a `KeyFile`-style result (meaning by int index + `None` bucket + order + rejected). Keep `parse_color_names`/`meaning_str` string-key adapter for the palette/shortcuts. Tests for int/None/order/rejected semantics (port Rainbow's `parse_key_file` tests).
- [ ] Swap the default content to Rainbow's emoji `DEFAULT_COLOR_NAMES` (matches what's on disk).
- [ ] Commit.

### Task 2.2 — Port font-view pure helpers (TDD)
- [ ] Add `label_for`, `section_order`, `build_glyph_order`, `render_key_file` from `rainbow_core` (adapted to the unified types). Port their tests.
- [ ] Commit.

### Task 2.3 — Robust support path
- [ ] Add a `_support_info_dir()` that uses `GSGlyphsInfo.applicationSupportPath()` inside Glyphs, falling back to `expanduser`+`$HOME` for tests (inject the resolver). Replace `default_info_dir()` internals. Tests for the fallback.
- [ ] Regenerate shortcuts; `uv run pytest`; manual reload check. Commit.

---

## P3 — Font-View grouping

**Outcome:** Font View can be grouped into color sections from within Color Flow, non-destructively.

### Tasks (expand to bite-size at execution)
- [ ] 3.1 Create `fontview.py`: port Rainbow's `_enable/_disable/_rebuild/_is_dirty/_force_refresh/backup-restore` as a class taking a font; reuse `colornames.build_glyph_order/section_order`; keep Rainbow's userData/tempData keys.
- [ ] 3.2 In `plugin.py start()`: install one File-menu toggle item ("Color Flow: Rainbow Font View") with checkmark via `validateMenuItem_`; teardown on reload (track active instance).
- [ ] 3.3 Wire grouping into the existing `UPDATEINTERFACE` handler: when enabled, run `fontview.is_dirty` → debounced `rebuild` (`performSelector:withObject:afterDelay:`), independent of the palette dirty-check.
- [ ] 3.4 Add action-menu items: "Rainbow Font View" on/off + "Color source: Layer/Glyph" (writes the mode userData).
- [ ] 3.5 Conflict guard: on `start()`, detect the standalone Rainbow bundle (menu titles / bundle id) and show a one-time "please disable Rainbow FontView" message.
- [ ] Manual checks: toggle on → font groups into sections in colorNames order; toggle off → original glyphOrder restored (and removed if none existed); recolor a glyph → section updates after debounce; switch master → re-groups.

---

## P4 — Inline rename + row redesign

**Outcome:** double-click a label to rename; writes `colorNames.txt`; palette + Font View relabel live.

### Tasks (expand to bite-size at execution)
- [ ] 4.1 Add a `NSClickGestureRecognizer` (numberOfClicksRequired=2) to each row's label view; single-click continues to toggle the checkbox.
- [ ] 4.2 On double-click: replace the label `TextBox` with an `EditText` prefilled with the current label; Enter/focus-loss → save, Escape → cancel.
- [ ] 4.3 Save path: update meaning → `colornames.render_key_file` → write to the resolved `colorNames.txt` (never through a broken symlink) → reload meaning → refresh palette rows → if grouping enabled, `fontview.rebuild`.
- [ ] 4.4 Tests for the pure rename round-trip (`render_key_file` after editing one label) already covered in P2; add one for label-with-emoji preserved.
- [ ] Manual checks: double-click "Orange" → edit to "🦊 Spacing" → Enter → palette relabels, colorNames.txt updated, Font-View section header relabels live; single-click still toggles.

---

## P5 — Finish

- [ ] 5.1 Migration polish: ensure a font already grouped by standalone Rainbow keeps working (adopt its enabled/saved-order keys); verify counts self-heal.
- [ ] 5.2 README rewrite covering both halves + the "disable standalone Rainbow FontView" step; update screenshots list.
- [ ] 5.3 Info.plist: bump `CFBundleShortVersionString`/`CFBundleVersion`, fill `productReleaseNotes`.
- [ ] 5.4 Final pass: `uv run pytest` green, `uvx ruff check` clean on `colornames.py`/`fontview.py`/`tools`, `pyright` clean on the pure modules; lint the bundle with the glyphs3 `lint_plugin.py` if applicable.
- [ ] 5.5 Tell the user to disable/remove the standalone Rainbow FontView bundle.

---

## Self-review notes
- Every spec section maps to a phase: shared module → P2; font-view → P3; inline rename → P4; migration/conflict → P3.5/P5; palette stabilization (prereq) → P1.
- Pure logic is TDD (P1.1, P2); GUI tasks specify manual Glyphs checks (no pytest placeholder).
- Names are consistent: `colornames.py`, `fontview.py`, `Get_Master_Counts`, `selection_signature`, `layer_color_for_state`, `count_states`, `build_glyph_order`.
- Open risk carried from spec: double-click gesture reliability (fallback: per-row ✎), palette-driven glyphOrder, single UPDATEINTERFACE doing both jobs.
