# Color Font Dashboard UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Color Font Dashboard's static table rendering with a contemporary, fully-interactive single-file HTML app (Direction A: dark pro-tool look), keeping the existing counting/snapshot data layer intact.

**Architecture:** Python computes a compact JSON **model** (reusing the shipped counting layer), embeds it in one self-contained `.html` with inline CSS + inline vanilla JS. The JS renders header, toolbar, overall hero, master tabs / compare matrix, step rows, per-glyph heatmap, and a changes panel, and drives all interaction (search, filters, sort, theme, copy). No network, no dependencies, no build step.

**Tech Stack:** Python 3.9 (stdlib `json`, `pathlib`, `datetime`), `colornames` (existing shared module), vanilla ES5-compatible JS, CSS custom properties. Tooling: uv, ruff, pyright, pytest (+ xdist).

---

## Background the implementer needs

Repo root (note the spaces): `/Users/hugojourdan/Dropbox (Personal)/02_Type-Design/02_Code/GitHub Repos/Color-Flow`. Run everything from there. Use `uv run …` for Python.

Spec: `docs/superpowers/specs/2026-06-05-color-font-dashboard-ui-redesign-design.md`.

The **data/counting layer already exists and is correct** in `Color Flow.glyphsPalette/Contents/Resources/colorflow_dashboard.py` and must be preserved unchanged:
- `free_mode() -> bool` — reads `Glyphs.defaults["com.hugojourdan.ColorFlow-FreeMode"]`.
- `_meaning_and_none(font) -> tuple[dict[str,str], str]` — `(meaning, none_label)` from `colorNames.txt`; `list(meaning.keys())` is the str counting order (includes hidden/empty-label slots — REQUIRED for cumulative parity; never use `visible_labels` for counting).
- `display_from_meaning(meaning, none_label) -> list[tuple[int,str]]` — visible `(int_key, label)` rows + None bucket last.
- `build_master_glyph_colors(font) -> dict[str,dict[str,int]]` — `{master_id:{glyph:key}}`, ALL glyphs, `layer.color` only, `-1` for none.
- `color_to_key`, `snapshot_to_colors`, `master_counts(colors, order, is_free)`, `uncolored_count(colors, order)`, `compute_changes`, `_coerce_snapshot`, `load_snapshot`, `save_snapshot`.
- `master_counts` is mode-aware: free → `colornames.single_counts_from_colors`, step → `colornames.counts_from_colors`. Str-keyed; never emits a `-1` key.

The following presentation functions/constants in `colorflow_dashboard.py` are **removed** by this plan (replaced by the JS app): `pct`, `hex_for`, `var_for`, `COLOR_HEX`, `HATCH`, `is_finished`, `label_map_from_display`, `display_colors`, `build_sidebar`, `_summary_bar`, `_count_row`, `_master_table`, `_change_log`, `build_heatmap_section`, `build_master_section`, `build_overall_totals`, `build_html`, `CSS`.

Colour hues now live ONLY in CSS (`--c0..--c11`, `--c-none`); Python no longer carries hexes.

## File Structure

- **Modify** `Color Flow.glyphsPalette/Contents/Resources/colorflow_dashboard.py`
  - Keep the data layer above. Add `build_model(font, now, current, previous) -> dict`. Rewrite `main()`. Delete the presentation functions/constants listed above. Import the new assets module.
- **Create** `Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py`
  - `DASHBOARD_CSS: str`, `DASHBOARD_JS: str` (the inline assets), `embed_model(model) -> str`, `build_html(model) -> str`. One responsibility: turn a model dict into the self-contained HTML page.
- **Rewrite** `tests/test_colorflow_dashboard.py` — keep the pure data/counting tests; drop the obsolete HTML-builder tests; add `build_model` tests.
- **Create** `tests/test_colorflow_assets.py` — `embed_model` + `build_html` tests.
- **Create** `tools/dashboard_sample.py` — dev harness that renders a sample model to HTML for in-browser checks.
- **Modify** `README.md` — refresh the dashboard section.

Each task is committed independently. Old and new code coexist until Task 7 deletes the dead builders, so the suite stays green throughout.

---

### Task 1: `build_model` — the JSON model from a font

**Files:**
- Modify: `Color Flow.glyphsPalette/Contents/Resources/colorflow_dashboard.py`
- Test: `tests/test_colorflow_dashboard.py`

- [ ] **Step 1: Add the failing tests**

Add to `tests/test_colorflow_dashboard.py` (the fakes `_FakeFont`, `_FakeMaster`, `_FakeGlyph`, `_FakeLayers`, `_FakeLayerColor`, and `_HIDDEN_REORDERED` already exist in that file from the current suite — reuse them):

```python
def test_build_model_shape_and_compact_glyph_names(tmp_path) -> None:
    (tmp_path / "colorNames.txt").write_text(
        "purple=Outline\nlightGreen=Anchors\nyellow=Ready\nNone=Nothing\n", encoding="utf-8")
    master = _FakeMaster("m1", "Regular")
    glyphs = [
        _FakeGlyph("A", {"m1": _FakeLayerColor(8)}),
        _FakeGlyph("B", {"m1": _FakeLayerColor(4)}),
        _FakeGlyph("C", {}),  # no layer -> none
    ]
    font = _FakeFont([master], glyphs, filepath=str(tmp_path / "Font.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)

    assert model["family"] == "Acme Sans"
    assert model["fileName"] == "Font.glyphs"
    assert model["version"] == "2.5"
    assert model["generated"] == "2026-06-05"
    assert model["mode"] == "step"
    assert model["glyphTotal"] == 3
    assert model["order"] == ["8", "4", "3"]
    assert model["steps"] == [{"key": 8, "label": "Outline"},
                              {"key": 4, "label": "Anchors"},
                              {"key": 3, "label": "Ready"}]
    assert model["noneLabel"] == "Nothing"
    assert model["glyphNames"] == ["A", "B", "C"]          # stored once
    assert model["masters"][0]["keys"] == [8, 4, -1]        # parallel to glyphNames
    assert model["changes"] == {"m1": {}}


def test_build_model_counts_match_palette_step_and_free(tmp_path) -> None:
    (tmp_path / "colorNames.txt").write_text(_HIDDEN_REORDERED, encoding="utf-8")
    glyphs = [
        _FakeGlyph("A", {"m1": _FakeLayerColor(8)}),
        _FakeGlyph("B", {"m1": _FakeLayerColor(4)}),
        _FakeGlyph("C", {"m1": _FakeLayerColor(3)}),
        _FakeGlyph("D", {}),  # none
    ]
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs, filepath=str(tmp_path / "F.glyphs"))
    current = db.build_master_glyph_colors(font)
    order = list(cc.parse_color_names(_HIDDEN_REORDERED).keys())
    colors = [8, 4, 3, None]

    step = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert step["mode"] == "step"
    assert step["masters"][0]["counts"] == cc.counts_from_colors(colors, order)
    assert step["masters"][0]["uncolored"] == db.uncolored_count(colors, order)


def test_build_model_free_mode(monkeypatch, tmp_path) -> None:
    fake = _FakeGlyphsApp()
    fake.defaults[db.FREE_KEY] = True
    monkeypatch.setattr(db, "Glyphs", fake)
    (tmp_path / "colorNames.txt").write_text(_HIDDEN_REORDERED, encoding="utf-8")
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(8)}), _FakeGlyph("B", {"m1": _FakeLayerColor(4)})]
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs, filepath=str(tmp_path / "F.glyphs"))
    current = db.build_master_glyph_colors(font)
    order = list(cc.parse_color_names(_HIDDEN_REORDERED).keys())
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["mode"] == "free"
    assert model["masters"][0]["counts"] == cc.single_counts_from_colors([8, 4], order)
```

- [ ] **Step 2: Run the tests; verify they fail**

Run: `uv run pytest tests/test_colorflow_dashboard.py -k build_model -q`
Expected: FAIL — `AttributeError: module 'colorflow_dashboard' has no attribute 'build_model'`.

- [ ] **Step 3: Implement `build_model`**

Add this function to `colorflow_dashboard.py` (place it just above the `main()` entry point):

```python
def build_model(font, now: datetime, current: dict, previous: dict) -> dict:
    """The full data model the JS app renders. Pure aside from reading the
    font's colorNames.txt (via _meaning_and_none) — the same source the palette
    uses, so counts stay in lockstep."""
    is_free = free_mode()
    meaning, none_label = _meaning_and_none(font)
    order = list(meaning.keys())
    steps = [{"key": key, "label": label}
             for key, label in display_from_meaning(meaning, none_label)
             if key != colornames.NO_COLOR]
    none_text = next((label for key, label in display_from_meaning(meaning, none_label)
                      if key == colornames.NO_COLOR), "")
    glyph_total = len(font.glyphs)
    glyph_names = list(current[font.masters[0].id].keys()) if font.masters else []

    masters = []
    for master in font.masters:
        per_glyph = current.get(master.id, {})
        colors = snapshot_to_colors(per_glyph)
        masters.append({
            "id": master.id,
            "name": master.name,
            "keys": [per_glyph[name] for name in glyph_names],
            "counts": master_counts(colors, order, is_free),
            "uncolored": uncolored_count(colors, order),
        })

    return {
        "family": font.familyName or "",
        "fileName": Path(font.filepath).name if font.filepath else (font.familyName or "Untitled"),
        "version": f"{font.versionMajor}.{font.versionMinor}",
        "generated": now.strftime("%Y-%m-%d"),
        "mode": "free" if is_free else "step",
        "glyphTotal": glyph_total,
        "order": order,
        "steps": steps,
        "noneLabel": none_text,
        "glyphNames": glyph_names,
        "masters": masters,
        "changes": compute_changes(current, previous),
    }
```

- [ ] **Step 4: Run the tests; verify they pass**

Run: `uv run pytest tests/test_colorflow_dashboard.py -k build_model -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add "Color Flow.glyphsPalette/Contents/Resources/colorflow_dashboard.py" tests/test_colorflow_dashboard.py
git commit -m "feat(dashboard): build JSON model from font for the JS app"
```

---

### Task 2: `embed_model` — safe JSON-in-HTML

**Files:**
- Create: `Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py`
- Test: `tests/test_colorflow_assets.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_colorflow_assets.py`:

```python
"""Tests for the inline-asset / HTML-shell layer of the Color Font Dashboard."""

from __future__ import annotations

import json

import colorflow_assets as assets


def _model() -> dict:
    return {
        "family": "Acme", "fileName": "Acme.glyphs", "version": "1.0",
        "generated": "2026-06-05", "mode": "step", "glyphTotal": 2,
        "order": ["0"], "steps": [{"key": 0, "label": "Red"}], "noneLabel": "None",
        "glyphNames": ["A", "B"],
        "masters": [{"id": "m1", "name": "Regular", "keys": [0, -1],
                     "counts": {"0": 1}, "uncolored": 1}],
        "changes": {"m1": {}},
    }


def test_embed_model_is_parseable_and_neutralises_script_breakout() -> None:
    model = _model()
    model["glyphNames"] = ["</script><b>x", "A"]  # hostile glyph name
    block = assets.embed_model(model)
    assert 'id="cfd-model"' in block
    assert "</script><b>" not in block          # the raw breakout never appears
    # the payload between the tags round-trips back to the original model
    payload = block.split(">", 1)[1].rsplit("<", 1)[0]
    assert json.loads(payload) == model
```

- [ ] **Step 2: Run it; verify it fails**

Run: `uv run pytest tests/test_colorflow_assets.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'colorflow_assets'`.

- [ ] **Step 3: Create `colorflow_assets.py` with `embed_model`**

```python
# encoding: utf-8
"""Inline assets + HTML shell for the Color Font Dashboard.

Turns the data model (see colorflow_dashboard.build_model) into one
self-contained, offline .html with inline CSS + inline vanilla JS. No network,
no dependencies. The model is the single source of truth the JS app renders.
"""

from __future__ import annotations

import json


def embed_model(model: dict) -> str:
    """Serialise the model into a ``<script type="application/json">`` block.
    ``<`` / ``>`` / ``&`` are escaped to their JSON ``\\uXXXX`` forms so no glyph
    name or label can terminate the script element (e.g. ``</script>``)."""
    payload = (json.dumps(model, ensure_ascii=False)
               .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))
    return f'<script type="application/json" id="cfd-model">{payload}</script>'
```

- [ ] **Step 4: Run it; verify it passes**

Run: `uv run pytest tests/test_colorflow_assets.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add "Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py" tests/test_colorflow_assets.py
git commit -m "feat(dashboard): add colorflow_assets with safe JSON embedding"
```

---

### Task 3: `DASHBOARD_CSS` + `DASHBOARD_JS` constants

No unit test (static assets — verified in-browser in Task 6). Paste the constants verbatim.

**Files:**
- Modify: `Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py`

- [ ] **Step 1: Append `DASHBOARD_CSS`**

Append to `colorflow_assets.py`:

```python
DASHBOARD_CSS = """
:root{
  --bg:#0a0b0e;--surface:#0e1014;--surface-2:#101217;--border:#1c1f26;--border-2:#23262e;
  --text:#e6e8ec;--muted:#9aa0ab;--muted-2:#6b7280;--accent:#6e7bff;--ok:#3fb950;
  --track:#15171c;--swatch-outline:rgba(255,255,255,.10);
  --c-none-a:#0e1116;--c-none-b:#3a3f4a;
  --c0:#f97e55;--c1:#ffbe68;--c2:#ba9d6d;--c3:#fff157;--c4:#c1ec8a;--c5:#6bab59;
  --c6:#64a5ef;--c7:#576ef1;--c8:#a962e7;--c9:#e77eb4;--c10:#c5c5c5;--c11:#5f5f5f;
  --c-none:repeating-linear-gradient(135deg,var(--c-none-a) 0,var(--c-none-a) 5px,var(--c-none-b) 5px,var(--c-none-b) 6px);
  --r:10px;--r-sm:7px;color-scheme:dark;
}
html[data-theme=light]{
  --bg:#f6f7f9;--surface:#ffffff;--surface-2:#f1f3f6;--border:#e3e6ea;--border-2:#d6dae0;
  --text:#15171c;--muted:#5b6270;--muted-2:#8b919c;--accent:#5b62ff;--ok:#1a7f37;
  --track:#eceef2;--swatch-outline:rgba(20,24,33,.18);
  --c-none-a:#dfe3e9;--c-none-b:#aab2bf;color-scheme:light;
}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--text);font:14px/1.5 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif,"Apple Color Emoji";
  font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased;opacity:0}
body.ready{opacity:1;transition:opacity .35s ease}
@media (prefers-reduced-motion:reduce){body,body.ready{opacity:1;transition:none}}
#cfd-app{max-width:980px;margin:0 auto;padding:0 20px 60px}
.hd{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:10px;padding:14px 0;background:var(--bg);border-bottom:1px solid var(--border)}
.hd .brand{width:10px;height:10px;border-radius:3px;background:var(--accent)}
.hd .fam{font-weight:600}
.hd .meta{font-size:12px;color:var(--muted-2)}
.hd .sp{flex:1}
.hd .mode{font-size:11px;color:var(--muted);border:1px solid var(--border-2);border-radius:var(--r-sm);padding:4px 9px}
.icon{width:30px;height:28px;border:1px solid var(--border-2);border-radius:var(--r-sm);background:transparent;color:var(--muted);cursor:pointer}
.icon:hover{color:var(--text)}
.tb{position:sticky;top:57px;z-index:4;display:flex;align-items:center;gap:8px;padding:12px 0;background:var(--bg);border-bottom:1px solid var(--border);flex-wrap:wrap}
.search{flex:1;min-width:180px;display:flex;align-items:center;gap:8px;background:var(--surface-2);border:1px solid var(--border-2);border-radius:var(--r-sm);padding:6px 10px;color:var(--muted-2)}
.search input{flex:1;background:transparent;border:0;outline:0;color:var(--text);font:inherit}
.search input::placeholder{color:var(--muted-2)}
.search kbd{border:1px solid var(--border-2);border-radius:4px;padding:0 5px;font:11px/1.4 inherit;color:var(--muted-2)}
.chip{font-size:11px;border:1px solid var(--border-2);border-radius:var(--r-sm);padding:6px 10px;background:var(--surface-2);color:var(--muted);cursor:pointer}
.chip:hover{color:var(--text)}
.chip[aria-pressed=true]{border-color:var(--accent);color:var(--text);background:color-mix(in srgb,var(--accent) 16%,transparent)}
.overall{display:flex;align-items:center;gap:22px;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 18px;margin:16px 0}
.ov-num{display:flex;flex-direction:column}
.ov-num .big{font-size:38px;font-weight:650;letter-spacing:-.02em;line-height:1}
.ov-num .big small{font-size:20px;color:var(--muted-2)}
.ov-sub{font-size:11px;color:var(--muted-2);text-transform:uppercase;letter-spacing:.06em}
.ov-main{flex:1}
.ov-head{font-size:12px;color:var(--muted);margin-bottom:8px}
.ov-head b{color:var(--text)}
.seg{display:flex;height:8px;border-radius:5px;overflow:hidden;background:var(--track)}
.seg>span{background:var(--accent)}
.seg .soft{background:color-mix(in srgb,var(--accent) 35%,transparent)}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;font-size:10.5px;color:var(--muted)}
.legend .lg{display:inline-flex;align-items:center;gap:5px}
.legend i{width:8px;height:8px;border-radius:50%;display:inline-block;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.tabs{display:flex;gap:18px;border-bottom:1px solid var(--border);margin-bottom:6px;overflow-x:auto}
.tab{font:12px inherit;background:transparent;border:0;border-bottom:2px solid transparent;color:var(--muted-2);padding:8px 0;cursor:pointer;white-space:nowrap}
.tab:hover{color:var(--text)}
.tab.on{color:var(--text);border-bottom-color:var(--accent)}
.rows{margin:6px 0 4px}
.row{display:flex;align-items:center;gap:12px;font-size:12.5px;padding:9px 0;border-top:1px solid var(--track)}
.row .dot{width:9px;height:9px;border-radius:50%;flex:none;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.row .rl{flex:1}
.row .chk{color:var(--ok)}
.row.done .rl{color:var(--muted)}
.bar{width:200px;height:5px;background:var(--track);border-radius:3px;overflow:hidden;flex:none}
.bar>span{display:block;height:100%;border-radius:3px}
.row .num{width:54px;text-align:right;color:var(--muted)}
.row .pc{width:40px;text-align:right}
.heat{margin-top:14px;border-top:1px solid var(--border);padding-top:12px}
.heat-h{font-size:11px;color:var(--muted);margin-bottom:8px}
.heat-h .hint{color:var(--muted-2)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(15px,1fr));gap:4px}
.cell{aspect-ratio:1;border:0;padding:0;border-radius:3px;cursor:pointer;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.cell:hover{outline:2px solid var(--accent);outline-offset:1px}
.cell.copied{outline:2px solid var(--ok);outline-offset:1px}
.more{display:inline-block;margin-top:8px;font-size:11px;color:var(--muted-2)}
.empty{font-size:12px;color:var(--muted-2)}
.changes{margin-top:14px}
.changes>summary{cursor:pointer;font-size:12px;color:var(--muted)}
.chgwrap{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.chg{display:flex;align-items:center;gap:6px;background:var(--surface-2);border:1px solid var(--border);border-radius:var(--r-sm);padding:5px 9px;font-size:11px}
.chg .cn{max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chg .sw{width:11px;height:11px;border-radius:3px;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.chg .arr{color:var(--muted-2)}
.cmp-wrap{overflow-x:auto;margin-top:8px}
.cmp{border-collapse:collapse;width:100%;font-size:12.5px}
.cmp caption{text-align:left;color:var(--muted-2);font-size:11px;padding-bottom:8px}
.cmp th,.cmp td{border:1px solid var(--border);padding:7px 10px;text-align:left}
.cmp thead th{color:var(--muted);font-weight:600}
.cmp tbody th{font-weight:500}
.cmp tbody th .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.cmp td{position:relative}
.cmp .cmpbar{position:absolute;left:0;top:0;bottom:0;border-radius:0;opacity:.28}
.cmp .cmpn{position:relative}
.ft{margin-top:30px;padding-top:16px;border-top:1px solid var(--border);font-size:10.5px;color:var(--muted-2);line-height:1.6}
.toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%) translateY(10px);background:var(--surface);border:1px solid var(--border-2);color:var(--text);border-radius:var(--r-sm);padding:8px 14px;font-size:12px;opacity:0;pointer-events:none;transition:opacity .15s,transform .15s}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
button:focus-visible,input:focus-visible,summary:focus-visible,.cell:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
"""
```

- [ ] **Step 2: Append `DASHBOARD_JS`**

Append the app to `colorflow_assets.py` as a **raw** string literal (`r"""…"""`) — it contains backslashes in the HTML-escape map that must be preserved:

```python
DASHBOARD_JS = r"""
(function(){
  "use strict";
  var node = document.getElementById("cfd-model");
  var H = JSON.parse(node.textContent);
  var lastOrder = H.order.length ? H.order[H.order.length-1] : null;

  var savedTheme = null;
  try { savedTheme = localStorage.getItem("cfd-theme"); } catch(e){}
  var prefersLight = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
  var state = {
    master: H.masters.length ? H.masters[0].id : null,
    view: "tabs", q: "", unfinishedOnly: true, sort: "workflow",
    theme: savedTheme || (prefersLight ? "light" : "dark")
  };

  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]; }); }
  function pct(n,t){ return t ? Math.round(n/t*100) : 0; }
  function varFor(k){ return k===-1 ? "--c-none" : "--c"+k; }
  function labelFor(k){
    if (k===-1) return H.noneLabel;
    for (var i=0;i<H.steps.length;i++){ if (H.steps[i].key===k) return H.steps[i].label; }
    return "Color "+k;
  }
  function masterById(id){
    for (var i=0;i<H.masters.length;i++){ if (H.masters[i].id===id) return H.masters[i]; }
    return H.masters[0];
  }
  function countFor(m,k){ return k===-1 ? m.uncolored : (m.counts[String(k)]||0); }
  function startedOf(m){ return H.glyphTotal - m.uncolored; }
  function finished(k){
    if (!H.order.length) return false;
    if (H.mode==="free") return H.order.indexOf(String(k))!==-1;
    return String(k)===lastOrder;
  }
  function matchQ(name){ return !state.q || name.toLowerCase().indexOf(state.q.toLowerCase())!==-1; }
  function stepsSorted(m){
    var s = H.steps.slice();
    if (state.sort==="progress"){ s.sort(function(a,b){ return countFor(m,b.key)-countFor(m,a.key); }); }
    return s;
  }
  function bar(value,total,cssVar,label){
    return '<div class="bar" role="progressbar" aria-valuenow="'+value+'" aria-valuemin="0" aria-valuemax="'+total+'" aria-label="'+esc(label)+'">'
      + '<span style="width:'+pct(value,total)+'%;background:var('+cssVar+')"></span></div>';
  }

  function aggregate(){
    var grand = H.glyphTotal * H.masters.length;
    var agg = {}; H.order.forEach(function(o){ agg[o]=0; });
    var aggUn = 0;
    H.masters.forEach(function(m){ H.order.forEach(function(o){ agg[o]+=(m.counts[o]||0); }); aggUn+=m.uncolored; });
    var started = grand - aggUn;
    var completion = (H.mode==="free" || !lastOrder) ? started : (agg[lastOrder]||0);
    return { grand:grand, agg:agg, started:started, completion:completion };
  }

  function header(){
    return '<header class="hd"><span class="brand"></span>'
      + '<span class="fam">'+esc(H.family)+'</span>'
      + '<span class="meta">'+esc(H.fileName)+' · v'+esc(H.version)+'</span>'
      + '<span class="sp"></span>'
      + '<span class="mode">Mode · '+(H.mode==="free"?"Free":"Step")+'</span>'
      + '<button type="button" id="cfd-theme" class="icon" aria-label="Toggle light or dark theme">◐</button></header>';
  }
  function toolbar(){
    return '<div class="tb">'
      + '<label class="search"><span aria-hidden="true">⌕</span>'
      + '<input id="cfd-search" type="search" placeholder="Search glyphs…" aria-label="Search glyphs" autocomplete="off"><kbd>/</kbd></label>'
      + '<button type="button" id="cfd-unfinished" class="chip" aria-pressed="'+state.unfinishedOnly+'">◦ Unfinished only</button>'
      + '<button type="button" id="cfd-sort" class="chip">↕ Sort: workflow</button>'
      + '<button type="button" id="cfd-compare" class="chip" aria-pressed="false">▤ Compare</button></div>';
  }
  function overall(){
    var a = aggregate(), compP = pct(a.completion,a.grand), startP = pct(a.started,a.grand);
    var legend = H.steps.map(function(s){
      return '<span class="lg"><i style="background:var('+varFor(s.key)+')"></i>'+esc(s.label)+' '+pct(a.agg[String(s.key)]||0,a.grand)+'%</span>';
    }).join("");
    var head = (H.mode==="free" || !lastOrder)
      ? '<b>'+a.started+'/'+a.grand+'</b> labelled ('+startP+'%)'
      : '<b>'+a.completion+'/'+a.grand+'</b> complete ('+compP+'%) · '+a.started+'/'+a.grand+' started ('+startP+'%)';
    return '<section class="overall" aria-label="Overall totals">'
      + '<div class="ov-num"><span class="big">'+compP+'<small>%</small></span><span class="ov-sub">'+(H.mode==="free"?"labelled":"complete")+'</span></div>'
      + '<div class="ov-main"><div class="ov-head">'+head+'</div>'
      + '<div class="seg" role="img" aria-label="Overall '+compP+'% complete, '+startP+'% started">'
      + '<span style="width:'+compP+'%"></span><span class="soft" style="width:'+Math.max(0,startP-compP)+'%"></span></div>'
      + '<div class="legend">'+legend+'</div></div></section>';
  }

  function rows(m){
    var html = stepsSorted(m).map(function(s){
      var c = countFor(m,s.key), p = pct(c,H.glyphTotal), done = H.glyphTotal>0 && c>=H.glyphTotal;
      return '<div class="row'+(done?' done':'')+'"><span class="dot" style="background:var('+varFor(s.key)+')"></span>'
        + '<span class="rl">'+esc(s.label)+(done?' <span class="chk" aria-label="complete">✓</span>':'')+'</span>'
        + bar(c,H.glyphTotal,varFor(s.key),s.label+': '+c+' of '+H.glyphTotal+' ('+p+'%)')
        + '<span class="num">'+c+'/'+H.glyphTotal+'</span><span class="pc">'+p+'%</span></div>';
    }).join("");
    var un = m.uncolored, up = pct(un,H.glyphTotal);
    html += '<div class="row none"><span class="dot" style="background:var(--c-none)"></span>'
      + '<span class="rl">'+esc(H.noneLabel)+'</span>'
      + bar(un,H.glyphTotal,"--c-none",H.noneLabel+': '+un+' of '+H.glyphTotal+' ('+up+'%)')
      + '<span class="num">'+un+'/'+H.glyphTotal+'</span><span class="pc">'+up+'%</span></div>';
    return '<div class="rows">'+html+'</div>';
  }
  function heatmap(m){
    var items = [];
    for (var i=0;i<H.glyphNames.length;i++){
      var name = H.glyphNames[i], k = m.keys[i];
      if (state.unfinishedOnly && finished(k)) continue;
      if (!matchQ(name)) continue;
      items.push([name,k]);
    }
    var cap = 500, shown = items.slice(0,cap);
    var cells = shown.map(function(it){
      var lab = labelFor(it[1]);
      return '<button type="button" class="cell" style="background:var('+varFor(it[1])+')" '
        + 'title="'+esc(it[0]+" — "+lab)+'" aria-label="'+esc(it[0]+", "+lab+" (copy name)")+'" data-g="'+esc(it[0])+'"></button>';
    }).join("");
    var more = items.length>cap ? '<span class="more">… +'+(items.length-cap)+' more</span>' : "";
    var empty = items.length===0 ? '<p class="empty">No glyphs match.</p>' : "";
    return '<section class="heat"><div class="heat-h">Per-glyph · '+items.length+(state.unfinishedOnly?" unfinished":"")
      + ' <span class="hint">hover for name · click to copy</span></div>'
      + '<div class="grid" aria-label="Per-glyph colours">'+cells+'</div>'+more+empty+'</section>';
  }
  function changes(m){
    var ch = (H.changes && H.changes[m.id]) || {}, names = Object.keys(ch);
    if (!names.length) return "";
    var blocks = names.map(function(n){
      var ok = ch[n][0], nk = ch[n][1];
      return '<div class="chg"><span class="cn">'+esc(n)+'</span>'
        + '<span class="sw" style="background:var('+varFor(ok)+')" title="'+esc("was "+labelFor(ok))+'" aria-label="'+esc("was "+labelFor(ok))+'"></span>'
        + '<span class="arr" aria-hidden="true">▶</span>'
        + '<span class="sw" style="background:var('+varFor(nk)+')" title="'+esc("now "+labelFor(nk))+'" aria-label="'+esc("now "+labelFor(nk))+'"></span></div>';
    }).join("");
    return '<details class="changes"><summary>Changed since last run ('+names.length+')</summary><div class="chgwrap">'+blocks+'</div></details>';
  }
  function tabsView(){
    var tabs = H.masters.map(function(m){
      var on = m.id===state.master;
      return '<button type="button" role="tab" aria-selected="'+on+'" class="tab'+(on?" on":"")+'" data-m="'+esc(m.id)+'">'+esc(m.name)+'</button>';
    }).join("");
    var m = masterById(state.master);
    return '<div class="tabs" role="tablist">'+tabs+'</div><div class="panel" role="tabpanel">'+rows(m)+heatmap(m)+changes(m)+'</div>';
  }
  function compareView(){
    var head = '<th scope="col">Step</th>'+H.masters.map(function(m){ return '<th scope="col">'+esc(m.name)+'</th>'; }).join("");
    var body = H.steps.map(function(s){
      var tds = H.masters.map(function(m){
        var p = pct(countFor(m,s.key),H.glyphTotal);
        return '<td><span class="cmpbar" style="width:'+p+'%;background:var('+varFor(s.key)+')"></span><span class="cmpn">'+p+'%</span></td>';
      }).join("");
      return '<tr><th scope="row"><span class="dot" style="background:var('+varFor(s.key)+')"></span>'+esc(s.label)+'</th>'+tds+'</tr>';
    }).join("");
    var noneTds = H.masters.map(function(m){ return '<td><span class="cmpn">'+pct(m.uncolored,H.glyphTotal)+'%</span></td>'; }).join("");
    body += '<tr class="none"><th scope="row"><span class="dot" style="background:var(--c-none)"></span>'+esc(H.noneLabel)+'</th>'+noneTds+'</tr>';
    return '<div class="cmp-wrap"><table class="cmp"><caption>Step completion by master</caption><thead><tr>'+head+'</tr></thead><tbody>'+body+'</tbody></table></div>';
  }
  function renderBody(){ return state.view==="compare" ? compareView() : tabsView(); }

  function update(){
    document.getElementById("cfd-body").innerHTML = renderBody();
    document.documentElement.setAttribute("data-theme", state.theme);
    var cmp = document.getElementById("cfd-compare"); if (cmp) cmp.setAttribute("aria-pressed", state.view==="compare");
    var uf = document.getElementById("cfd-unfinished"); if (uf) uf.setAttribute("aria-pressed", state.unfinishedOnly);
    var sb = document.getElementById("cfd-sort"); if (sb) sb.textContent = "↕ Sort: "+(state.sort==="progress"?"progress":"workflow");
  }

  var toastTimer;
  function toast(msg){
    var t = document.getElementById("cfd-toast");
    if (!t){ t = document.createElement("div"); t.id = "cfd-toast"; t.className = "toast"; document.body.appendChild(t); }
    t.textContent = msg; t.classList.add("show");
    clearTimeout(toastTimer); toastTimer = setTimeout(function(){ t.classList.remove("show"); }, 1400);
  }
  function copy(name, el){
    function done(){ toast('Copied "'+name+'"'); el.classList.add("copied"); setTimeout(function(){ el.classList.remove("copied"); }, 600); }
    function fallback(){ var t = document.createElement("textarea"); t.value = name; document.body.appendChild(t); t.select();
      try { document.execCommand("copy"); } catch(e){} document.body.removeChild(t); done(); }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(name).then(done, fallback);
    else fallback();
  }

  function bind(){
    document.getElementById("cfd-theme").addEventListener("click", function(){
      state.theme = state.theme==="dark" ? "light" : "dark";
      try { localStorage.setItem("cfd-theme", state.theme); } catch(e){}
      document.documentElement.setAttribute("data-theme", state.theme);
    });
    document.getElementById("cfd-unfinished").addEventListener("click", function(){ state.unfinishedOnly = !state.unfinishedOnly; update(); });
    document.getElementById("cfd-sort").addEventListener("click", function(){ state.sort = state.sort==="workflow" ? "progress" : "workflow"; update(); });
    document.getElementById("cfd-compare").addEventListener("click", function(){ state.view = state.view==="compare" ? "tabs" : "compare"; update(); });
    var s = document.getElementById("cfd-search");
    s.addEventListener("input", function(){ state.q = s.value; update(); });
    document.addEventListener("keydown", function(e){
      if (e.key==="/" && document.activeElement!==s){ e.preventDefault(); s.focus(); }
    });
    document.getElementById("cfd-body").addEventListener("click", function(e){
      var tab = e.target.closest(".tab"); if (tab){ state.master = tab.getAttribute("data-m"); update(); return; }
      var cell = e.target.closest(".cell"); if (cell){ copy(cell.getAttribute("data-g"), cell); }
    });
  }
  function init(){
    document.getElementById("cfd-app").innerHTML =
      header() + toolbar() + overall() + '<div id="cfd-body"></div>'
      + '<footer class="ft">Color Font Dashboard · Color Flow — Hugo Jourdan<br>'+esc(H.generated)+'</footer>';
    bind(); update();
    requestAnimationFrame(function(){ document.body.classList.add("ready"); });
  }
  if (document.readyState!=="loading") init();
  else document.addEventListener("DOMContentLoaded", init);
})();
"""
```

- [ ] **Step 3: Sanity-check the module imports**

Run: `cd "Color Flow.glyphsPalette/Contents/Resources" && uv run python -c "import colorflow_assets as a; print(len(a.DASHBOARD_CSS), len(a.DASHBOARD_JS))"`
Expected: two non-zero integers, no exception. (Return to repo root afterward.)

- [ ] **Step 4: Commit**

```bash
git add "Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py"
git commit -m "feat(dashboard): add inline CSS + JS app constants"
```

---

### Task 4: `build_html` — assemble the self-contained page

**Files:**
- Modify: `Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py`
- Test: `tests/test_colorflow_assets.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_colorflow_assets.py`:

```python
def test_build_html_is_self_contained_and_accessible() -> None:
    html = assets.build_html(_model())
    assert html.startswith("<!DOCTYPE html>")
    assert 'lang="en"' in html
    assert '<style>' in html and assets.DASHBOARD_CSS[:20].strip() in html
    assert 'id="cfd-model"' in html            # model embedded
    assert "JSON.parse" in html                # app script inlined
    assert "<noscript>" in html
    assert ":root{" in html                     # dark default tokens
    assert "html[data-theme=light]" in html     # light theme
    assert "http://" not in html and "https://" not in html  # no network


def test_build_html_title_from_model_is_escaped() -> None:
    model = _model(); model["family"] = "a<b>"
    html = assets.build_html(model)
    assert "a&lt;b&gt;" in html
    assert "<title>" in html
```

- [ ] **Step 2: Run; verify fail**

Run: `uv run pytest tests/test_colorflow_assets.py -k build_html -q`
Expected: FAIL — `AttributeError: module 'colorflow_assets' has no attribute 'build_html'`.

- [ ] **Step 3: Implement `build_html`**

Add to `colorflow_assets.py` (import `escape` at the top of the file: `from xml.sax.saxutils import escape as xesc`):

```python
def build_html(model: dict) -> str:
    """Assemble the complete, self-contained dashboard page from a model."""
    title = xesc(f'{model["generated"]}_{model.get("family") or ""}_Color-Flow-Dashboard')
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title><style>{DASHBOARD_CSS}</style></head>"
        '<body><div id="cfd-app"></div>'
        '<noscript>This report needs JavaScript — please open it in a modern browser.</noscript>'
        f"{embed_model(model)}"
        f"<script>{DASHBOARD_JS}</script>"
        "</body></html>"
    )
```

- [ ] **Step 4: Run; verify pass**

Run: `uv run pytest tests/test_colorflow_assets.py -q`
Expected: PASS (all assets tests).

- [ ] **Step 5: Commit**

```bash
git add "Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py" tests/test_colorflow_assets.py
git commit -m "feat(dashboard): assemble self-contained HTML shell from model"
```

---

### Task 5: Rewire `main()` and delete the old builders

**Files:**
- Modify: `Color Flow.glyphsPalette/Contents/Resources/colorflow_dashboard.py`

- [ ] **Step 1: Rewrite `main()`**

Replace the existing `main()` body in `colorflow_dashboard.py` with:

```python
def main(font=None) -> None:
    if font is None and Glyphs is not None:
        font = Glyphs.font
    if font is None:
        Message("Open a font first.", "Color Font Dashboard")
        return
    total = len(font.glyphs)
    if total == 0:
        Message("No glyphs to report on.", "Color Font Dashboard")
        return

    now = datetime.now()
    current = build_master_glyph_colors(font)
    previous = load_snapshot(font) or current
    model = build_model(font, now, current, previous)
    html = colorflow_assets.build_html(model)
    save_snapshot(font, current)

    base = Path(font.filepath).stem if font.filepath else (font.familyName or "font")
    out_path = Path(tempfile.gettempdir()) / f"{now.strftime('%Y%m%d')} {base} — Color Flow.html"
    try:
        out_path.write_text(html, encoding="utf-8")
    except OSError as error:
        Message(f"Could not write the dashboard:\n{error}", "Color Font Dashboard")
        return
    webbrowser.open(out_path.as_uri())
```

- [ ] **Step 2: Add the assets import and delete dead presentation code**

At the top of `colorflow_dashboard.py`, add `import colorflow_assets` next to `import colornames`. Then **delete** these now-unused definitions and the `# Page styling` / `# HTML building` section comments: `pct`, `hex_for`, `var_for`, `COLOR_HEX`, `HATCH`, `is_finished`, `label_map_from_display`, `display_colors`, `build_sidebar`, `_summary_bar`, `_count_row`, `_master_table`, `_change_log`, `build_heatmap_section`, `build_master_section`, `build_overall_totals`, `build_html`, `CSS`. Keep the data-layer functions and `build_model`. Leave `from xml.sax.saxutils import escape as xesc` only if still referenced — it is not, so remove that import too. Keep `tempfile`, `webbrowser`, `datetime`, `Path`, `colornames`, `colorflow_assets`, and the `Glyphs`/`Message` guard.

- [ ] **Step 3: Verify the module imports and lints**

Run: `cd "Color Flow.glyphsPalette/Contents/Resources" && uv run python -c "import colorflow_dashboard"` (return to repo root after).
Then: `uv run ruff check "Color Flow.glyphsPalette/Contents/Resources/colorflow_dashboard.py"`
Expected: no import error; ruff reports no unused imports / no errors. Fix any `F401` by removing the flagged import.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -n auto -q`
Expected: collection error or failures ONLY in `tests/test_colorflow_dashboard.py` referencing deleted functions (fixed in Task 6). The `colornames` and `colorflow_assets` tests must pass.

- [ ] **Step 5: Commit**

```bash
git add "Color Flow.glyphsPalette/Contents/Resources/colorflow_dashboard.py"
git commit -m "refactor(dashboard): render via JSON model + assets, drop static builders"
```

---

### Task 6: Prune obsolete dashboard tests

**Files:**
- Modify: `tests/test_colorflow_dashboard.py`

- [ ] **Step 1: Delete tests of removed functions**

Remove every test that references a deleted symbol: `test_hex_for_*`, `test_var_for_*`, `test_is_finished_*`, `test_label_map_from_display`, `test_pct_*`, and all `test_build_html_*`, `test_build_overall_totals_*`, `test_heatmap_*` tests (heatmap/overall/HTML rendering now lives in JS). Also delete the now-unused `xattr` test if present. **Keep**: `test_color_to_key_*`, `test_snapshot_to_colors_*`, `test_master_counts_matches_palette_*`, `test_step_counts_are_cumulative_*`, `test_uncolored_count_*`, `test_display_from_meaning_*`, `test_compute_changes_*`, the GlyphsApp-touching tests (`test_build_master_glyph_colors_*`, `test_free_mode_*`, `test_meaning_and_none_*`, `test_snapshot_round_trip_*`, `test_coerce_snapshot_*`), and the new `test_build_model_*` from Task 1. Keep all fakes.

- [ ] **Step 2: Run the suite**

Run: `uv run pytest -n auto -q`
Expected: PASS (no references to removed symbols remain).

- [ ] **Step 3: Type-check**

Run: `uv run pyright "Color Flow.glyphsPalette/Contents/Resources/colorflow_dashboard.py" "Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py" tests/test_colorflow_dashboard.py tests/test_colorflow_assets.py`
Expected: `0 errors`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_colorflow_dashboard.py
git commit -m "test(dashboard): drop tests for removed static builders"
```

---

### Task 7: Sample harness + in-browser verification

**Files:**
- Create: `tools/dashboard_sample.py`

- [ ] **Step 1: Write the sample harness**

Create `tools/dashboard_sample.py`:

```python
"""Render sample dashboards (step + free) to HTML for in-browser checks.

Usage: uv run python tools/dashboard_sample.py [out_dir]
Writes dashboard_step.html and dashboard_free.html. No Glyphs required.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

RESOURCES = Path(__file__).resolve().parent.parent / "Color Flow.glyphsPalette" / "Contents" / "Resources"
sys.path.insert(0, str(RESOURCES))

import colorflow_assets as assets  # noqa: E402

STEPS = [
    {"key": 8, "label": "Outline corrected"},
    {"key": 4, "label": "Anchors placed"},
    {"key": 6, "label": "Spacing set"},
    {"key": 3, "label": "Ready to Export"},
]
ORDER = ["8", "4", "6", "3"]
SEQ = [8, 8, 4, 4, 4, 6, 6, 3, 3, 3, 3, -1, -1, 8, 4, 6, 3, -1, 8, 4, -1, 6]
NAMES = [chr(c) for c in range(ord("A"), ord("A") + len(SEQ))]


def _counts(keys: list[int], is_free: bool) -> dict[str, int]:
    counts = {o: 0 for o in ORDER}
    for key in keys:
        if key == -1:
            continue
        target = str(key)
        if is_free:
            if target in counts:
                counts[target] += 1
        else:
            for step in ORDER:
                counts[step] += 1
                if step == target:
                    break
    return counts


def _model(is_free: bool) -> dict:
    masters = []
    for offset, name in ((0, "Regular"), (5, "Bold")):
        keys = [SEQ[(i + offset) % len(SEQ)] for i in range(len(SEQ))]
        uncolored = sum(1 for k in keys if k == -1)
        masters.append({"id": name.lower(), "name": name, "keys": keys,
                        "counts": _counts(keys, is_free), "uncolored": uncolored})
    return {
        "family": "Acme Sans", "fileName": "Acme.glyphs", "version": "2.5",
        "generated": datetime(2026, 6, 5).strftime("%Y-%m-%d"),
        "mode": "free" if is_free else "step", "glyphTotal": len(SEQ),
        "order": ORDER, "steps": STEPS, "noneLabel": "🫥 None",
        "glyphNames": NAMES, "masters": masters,
        "changes": {"regular": {"A": [4, 8], "H": [6, 3]}},
    }


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    for is_free in (False, True):
        path = out_dir / f"dashboard_{'free' if is_free else 'step'}.html"
        path.write_text(assets.build_html(_model(is_free)), encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Generate the samples**

Run: `uv run python tools/dashboard_sample.py "$TMPDIR"`
Expected: prints two paths; both files exist.

- [ ] **Step 3: Open and verify in a browser**

Run: `open "$TMPDIR/dashboard_step.html"`
Manually confirm each (this is the JS acceptance test — there is no automated JS test):
  - Loads with the dark Direction-A look; content fades in once.
  - **Theme toggle** (◐) flips dark↔light and persists on reload.
  - **Search**: typing filters the heatmap; pressing `/` focuses the search box.
  - **Unfinished only** chip toggles the heatmap set; **Sort** flips workflow↔progress and reorders step rows.
  - **Tabs** switch master; **Compare** shows the steps×masters matrix and back.
  - **Heatmap**: hovering a cell shows `glyph — colour`; clicking copies the name (toast appears).
  - **Changed since last run** lists the seeded changes.
  - Open `dashboard_free.html`: header shows `Mode · Free`, overall headline reads "labelled".

- [ ] **Step 4: Commit**

```bash
git add tools/dashboard_sample.py
git commit -m "chore(dashboard): add sample-render harness for in-browser checks"
```

---

### Task 8: Refresh the README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the COLOR FONT DASHBOARD section**

In `README.md`, in the `# COLOR FONT DASHBOARD` section, update the bullet list to describe the new interactive UI. Replace the existing bullets with:

```markdown
A contemporary, interactive progress report for the whole font, opened in your
browser from the palette's **Action Button (⋯) → Open Color Font Dashboard**. It is
a single self-contained HTML file — no internet, no install — that you can keep or share.

* **Search & filter** — find glyphs by name (press `/`), show only unfinished glyphs.
* **Master tabs + Compare** — focus one master, or switch to a steps × masters matrix
  to see which master lags on which step.
* **Sort** — order steps by your workflow (`colorNames.txt`) or by progress.
* **Per-glyph heatmap** — hover a cell for the glyph name + colour; click to copy the name.
* **Light & dark** — follows your system, with a one-click toggle that remembers your choice.
* **Matches the palette** — counts are exactly what the sidebar shows (same glyphs, same
  Layer Color source, same step/free mode). Overall shows **completion** and **started**.
* **Changed since last run** — lists glyphs whose colour changed since the previous open;
  the snapshot lives in Glyphs' preferences, not in your `.glyphs` file.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(dashboard): describe the new interactive dashboard UI"
```

---

### Task 9: Final verification

- [ ] **Step 1: Lint, type-check, test**

Run:
```bash
uv run ruff check "Color Flow.glyphsPalette/Contents/Resources/colorflow_dashboard.py" "Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py" tests tools
uv run pyright "Color Flow.glyphsPalette/Contents/Resources/colorflow_dashboard.py" "Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py" tests
uv run pytest -n auto -q
```
Expected: ruff "All checks passed!"; pyright `0 errors`; pytest all green.

- [ ] **Step 2: Regenerate and re-open the sample for a final look**

Run: `uv run python tools/dashboard_sample.py "$TMPDIR" && open "$TMPDIR/dashboard_step.html"`
Expected: the redesigned dashboard renders and all interactions work.

- [ ] **Step 3: In Glyphs (manual, if available)**

Open a multi-master font with a `colorNames.txt`, open the dashboard from the palette Action popover in both **step** and **free** mode; confirm each step row's count equals the palette sidebar's count for the focused master, and that search/filter/sort/compare/heatmap-copy all work.

---

## Self-Review (completed by plan author)

- **Spec coverage:** aesthetic/tokens → Task 3 CSS; single self-contained file + JS render → Tasks 3–4; model schema → Task 1; embedding safety → Task 2; views/interactions → Task 3 JS + Task 7 checklist; counting parity preserved → Task 1 tests reuse `colornames` oracle; testing strategy → Tasks 1–4, 6, 9; README → Task 8; migration/remove-dead-code → Task 5. All spec sections map to a task.
- **Placeholders:** none — every code step contains complete code; the JS/CSS are pasted in full.
- **Type/name consistency:** `build_model(font, now, current, previous)` defined in Task 1 and called identically in Task 5; `embed_model`/`build_html` defined in Tasks 2/4 and used in Task 5's `main` via `colorflow_assets.build_html`; model keys (`glyphNames`, `keys`, `counts`, `uncolored`, `order`, `steps`, `noneLabel`, `mode`, `glyphTotal`, `changes`) are identical across the Python builder, the embedding tests, the JS app, and the sample harness.
```
