# Color Tower View — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Tower" view to the Color Flow HTML report — a stacked-disc 3D visualizer where each master is a blurred colour disc (its label-colour distribution), viewed isometrically, drag-to-rotate.

**Architecture:** Pure front-end inside the existing self-contained report (`colorflow_assets.py`). A new `state.view === "tower"` branch renders a `<canvas>` into `#cfd-body`; an isometric painter draws one disc per master from the already-embedded model (`H.masters[].counts`, `H.masters[].uncolored`, `H.steps`, `H.colors`), with interpolated sub-slices between masters. No Python model change, no new dependency, fully offline. The working prototype is `tools/disc_tower_draft.html`.

**Tech Stack:** Canvas 2D (`ctx.filter='blur()'`, radial gradients, painter's algorithm), inline JS/CSS in the report. Same data model the report already embeds.

---

## Context

The user wants a colour-driven "tower" visualizer: each master = a disc tinted by its label-colour mix (the favicon's soft-blur look), stacked into an isometric cylinder so completion across the design space reads at a glance (sparse Thin → saturated Black, with the uncoloured share as a centre bore). A standalone canvas prototype already exists and matches the desired look; this plan wires that renderer into the report as a first-class view next to Overview / Coverage / Timeline / Compare.

Feasibility for the native Glyphs palette is also high (WKWebView reuse of this same renderer, or SceneKit/CALayer native) — **out of scope here**; this plan covers the HTML report only. Doing it in-report first gives the reusable renderer that a future WKWebView palette panel can embed unchanged.

## Files to modify

- `Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py` — `DASHBOARD_CSS` (tower styles) + `DASHBOARD_JS` (toolbar button, `state.view` branch, `towerView()`, `startTower()`).
- `tests/test_colorflow_assets.py` — assert the new CSS/JS markers.
- `$CLAUDE_JOB_DIR/tmp/smoke.js` — Tower button toggles + injects a canvas, with a null-2d-context guard so jsdom (no real canvas) doesn't throw.
- **No change** to `colorflow_dashboard.py` (model already carries everything) or `tools/dashboard_sample.py`.

Repo root: `/Users/hugojourdan/Dropbox (Personal)/02_Type-Design/02_Code/GitHub Repos/Color-Flow/`

## Reuse (do not re-implement)

- Toolbar pattern: `toolbar()` (`colorflow_assets.py:~336`) — chips `#cfd-overview/coverage/timeline/compare/export`; their click handlers in `bind()` (`:~789`) flip `state.view` and call `update()`; `update()` (`:~628`) syncs `aria-pressed`.
- `renderBody()` (`:~570`) dispatches on `state.view` (`compare|coverage|timeline|tabs`). Add `"tower"`.
- Model fields (already embedded, mirrored by `tools/dashboard_sample.py`): `H.masters[]` each `{id, name, counts:{ "0".."11":n }, uncolored, ...}`; `H.steps[]` `{key,label}`; `H.glyphTotal`; `H.colors` (`{str:hex}`, may be absent → fall back to CSS vars). `masterOverall()` (`:~379`) already builds a per-master `dist` from `m.counts` + `m.uncolored` — copy that mapping.
- The drawing logic (buildField/drawDisc/iso loop) is in `tools/disc_tower_draft.html` — port it, swapping the fake model for `H`.

## Key integration wrinkle (must handle)

`update()` re-renders `#cfd-body` via `innerHTML` on **every** state change, which destroys & recreates the canvas. The tower's `requestAnimationFrame` loop must:
1. be (re)started after each render while `state.view==="tower"`, and
2. self-cancel when its canvas leaves the DOM (guard each frame with `document.body.contains(cv)`), and a module-level `towerRAF` id cancelled before starting a new loop — so switching views never leaks loops.
Also: `canvas.getContext("2d")` returns `null` under jsdom — `startTower()` must no-op if the context or canvas is missing, so the report never throws headless.

## Work breakdown

### Task 1: Toolbar button + view branch

**Files:**
- Modify: `Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py` (`toolbar()`, `renderBody()`, `bind()`, `update()`)

- [ ] **Step 1: Add the Tower chip to `toolbar()`** (after the Compare chip, before Export)

```js
+ '<button type="button" id="cfd-tower" class="chip" aria-pressed="false">◉ Tower</button>'
```

- [ ] **Step 2: Branch `renderBody()`**

```js
function renderBody(){
  return state.view==="compare" ? compareView()
    : state.view==="coverage" ? coverageView()
    : state.view==="timeline" ? timelineView()
    : state.view==="tower" ? towerView()
    : tabsView();
}
```

- [ ] **Step 3: Wire the button in `bind()`** (next to the other view toggles, ~`:760`)

```js
document.getElementById("cfd-tower").addEventListener("click", function(){
  state.view = state.view==="tower" ? "tabs" : "tower"; update();
});
```

- [ ] **Step 4: Sync aria + start/stop the loop in `update()`** (after the existing `aria-pressed` lines, before the global-bar re-render)

```js
var tw = document.getElementById("cfd-tower"); if (tw) tw.setAttribute("aria-pressed", state.view==="tower");
if (state.view==="tower") startTower(); else stopTower();
```

- [ ] **Step 5: Commit**

```bash
git add "Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py"
git commit -m "feat(dashboard): add Tower view toggle scaffold"
```

### Task 2: `towerView()` markup + CSS

**Files:**
- Modify: `colorflow_assets.py` (`DASHBOARD_JS` add `towerView()`; `DASHBOARD_CSS` add styles)

- [ ] **Step 1: Add `towerView()`** — returns the canvas + controls (real model drives it later in `startTower`)

```js
function towerView(){
  return '<section class="tower-wrap" aria-label="Master colour tower">'
    + '<canvas id="cfd-tower-cv" width="900" height="640" role="img"'
    + ' aria-label="Each master as a colour disc, stacked by design-space order"></canvas>'
    + '<div class="tower-ctl">'
    +   '<label>tilt <input id="tw-tilt" type="range" min="20" max="70" value="42"></label>'
    +   '<label>blend <input id="tw-slices" type="range" min="1" max="20" value="12"></label>'
    +   '<label><input id="tw-spin" type="checkbox" checked> spin</label>'
    +   '<label><input id="tw-hole" type="checkbox" checked> uncoloured core</label>'
    + '</div>'
    + '<p class="tower-cap">One disc per master · disc colour = that master’s label-colour mix · bore = uncoloured share. Drag to rotate.</p>'
    + '</section>';
}
```

- [ ] **Step 2: Add CSS to `DASHBOARD_CSS`**

```css
.tower-wrap{display:flex;flex-direction:column;align-items:center;gap:10px;padding-top:8px}
.tower-wrap canvas{max-width:100%;height:auto;cursor:grab}
.tower-wrap canvas:active{cursor:grabbing}
.tower-ctl{display:flex;gap:16px;flex-wrap:wrap;justify-content:center;color:var(--muted);font-size:var(--fs-xs)}
.tower-ctl label{display:inline-flex;gap:6px;align-items:center}
.tower-cap{color:var(--muted-2);font-size:var(--fs-xs);text-align:center;margin:0}
@media (prefers-reduced-motion:reduce){.tower-wrap canvas{}} /* spin already opt-out via JS */
```

- [ ] **Step 3: Commit**

```bash
git add "Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py"
git commit -m "feat(dashboard): tower view markup and styles"
```

### Task 3: The renderer — `startTower()` / `stopTower()`

**Files:**
- Modify: `colorflow_assets.py` (`DASHBOARD_JS`: module-level `towerRAF`, `towerFields` cache; helpers)

- [ ] **Step 1: Add module-scope state** (near `var introDone`)

```js
var towerRAF = 0, towerState = {rot:-0.5, tilt:0.42, perGap:12, spin:true, hole:true, drag:false, lastX:0};
```

- [ ] **Step 2: Add colour + field helpers** (port from the prototype; resolve hex from model or CSS var)

```js
function hexForKey(k){
  if (H.colors && H.colors[String(k)]) return H.colors[String(k)];
  var v = getComputedStyle(document.documentElement).getPropertyValue("--c"+k).trim();
  return v || "#888";
}
function rgbaFromHex(hex,a){
  var s = hex.replace("#",""); if (s.length===3) s = s.replace(/(.)/g,"$1$1");
  var n = parseInt(s,16); return "rgba("+((n>>16)&255)+","+((n>>8)&255)+","+(n&255)+","+a+")";
}
// master -> blurred colour disc canvas (favicon look)
function towerField(m){
  var FSz = 320, off = document.createElement("canvas"); off.width = off.height = FSz;
  var g = off.getContext("2d"); if (!g) return null;
  var cx = FSz/2, cy = FSz/2, R = FSz*0.46;
  var keys = H.steps.map(function(s){ return s.key; });
  var counts = keys.map(function(k){ return (m.counts && m.counts[String(k)]) || 0; });
  var sum = counts.reduce(function(a,b){ return a+b; }, 0) || 1;
  counts.forEach(function(cnt,i){
    if (!cnt) return;
    var share = cnt/sum, ang = (i/keys.length)*Math.PI*2 - Math.PI/2;
    var bx = cx+Math.cos(ang)*R*0.5, by = cy+Math.sin(ang)*R*0.5;
    var rad = R*(0.42+0.8*share), hex = hexForKey(keys[i]);
    var grd = g.createRadialGradient(bx,by,0,bx,by,rad);
    grd.addColorStop(0, hex); grd.addColorStop(1, rgbaFromHex(hex,0));
    g.globalAlpha = 0.5+0.5*share; g.fillStyle = grd;
    g.beginPath(); g.arc(bx,by,rad,0,7); g.fill();
  });
  g.globalAlpha = 1;
  var base = document.createElement("canvas"); base.width = base.height = FSz;
  var cg = base.getContext("2d");
  cg.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--surface").trim() || "#fbfbfd";
  cg.beginPath(); cg.arc(FSz/2,FSz/2,FSz/2,0,7); cg.fill();
  cg.filter = "blur(26px)"; cg.drawImage(off,0,0);
  return base;
}
```

- [ ] **Step 3: Add `stopTower()` + `startTower()`** (port the iso loop; guard null ctx + DOM presence; bind controls)

```js
function stopTower(){ if (towerRAF){ cancelAnimationFrame(towerRAF); towerRAF = 0; } }
function startTower(){
  stopTower();
  var cv = document.getElementById("cfd-tower-cv");
  var ctx = cv && cv.getContext && cv.getContext("2d");
  if (!ctx || !H.masters.length) return;                 // jsdom / no masters: no-op
  var W = cv.width, Hh = cv.height;
  var fields = H.masters.map(towerField);
  var holes = H.masters.map(function(m){ return H.glyphTotal ? (m.uncolored||0)/H.glyphTotal : 0; });
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion:reduce)").matches;
  var s = towerState; s.rot = -0.5;
  function disc(fA,fB,t,cx,cy,rx,ry,rot,hf){
    ctx.save(); ctx.translate(cx,cy); ctx.scale(1,ry/rx); ctx.rotate(rot);
    ctx.beginPath(); ctx.arc(0,0,rx,0,7); ctx.clip();
    ctx.globalAlpha = 1; ctx.drawImage(fA,-rx,-rx,rx*2,rx*2);
    if (fB && t>0){ ctx.globalAlpha = t; ctx.drawImage(fB,-rx,-rx,rx*2,rx*2); }
    ctx.globalAlpha = 1;
    if (hf>0){ var hr = rx*0.55*Math.sqrt(hf), hg = ctx.createRadialGradient(0,0,0,0,0,hr);
      hg.addColorStop(0,"rgba(15,17,21,.85)"); hg.addColorStop(.7,"rgba(15,17,21,.45)"); hg.addColorStop(1,"rgba(15,17,21,0)");
      ctx.fillStyle = hg; ctx.beginPath(); ctx.arc(0,0,hr,0,7); ctx.fill(); }
    ctx.restore();
    ctx.save(); ctx.translate(cx,cy); ctx.scale(1,ry/rx);
    ctx.beginPath(); ctx.arc(0,0,rx,0.05*Math.PI,0.95*Math.PI);
    ctx.strokeStyle = "rgba(0,0,0,.10)"; ctx.lineWidth = 3; ctx.stroke(); ctx.restore();
  }
  function frame(){
    if (!document.body.contains(cv)){ stopTower(); return; }   // canvas gone -> stop
    if (s.spin && !s.drag && !reduce) s.rot += 0.004;
    ctx.clearRect(0,0,W,Hh);
    var M = H.masters.length, rx = W*0.205, ry = rx*s.tilt;
    var N = (M-1)*s.perGap + 1, towerH = Hh*0.42, dz = N>1 ? towerH/(N-1) : 0;
    var cx = W/2, topY = (Hh-towerH)/2 + 10;
    for (var n=0; n<N; n++){
      var cy = topY + n*dz, p = (M-1) - n/s.perGap, lo = Math.max(0,Math.floor(p)), t = p-lo;
      var hf = s.hole ? (holes[lo]*(1-t) + holes[Math.min(M-1,lo+1)]*t) : 0;
      disc(fields[lo], fields[Math.min(M-1,lo+1)], t, cx, cy, rx, ry, s.rot, n===0 ? hf : 0);
    }
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--muted").trim() || "#888";
    ctx.textAlign = "left";
    for (var i=0;i<M;i++){ var yy = topY + (M-1-i)*s.perGap*dz;
      ctx.fillText(H.masters[i].name, cx+rx+14, yy+4); }
    towerRAF = requestAnimationFrame(frame);
  }
  // controls (recreated each time the view opens)
  cv.onpointerdown = function(e){ s.drag = true; s.lastX = e.clientX; cv.setPointerCapture(e.pointerId); };
  cv.onpointermove = function(e){ if (s.drag){ s.rot += (e.clientX-s.lastX)*0.01; s.lastX = e.clientX; } };
  cv.onpointerup   = function(){ s.drag = false; };
  var bind = function(id,fn){ var el = document.getElementById(id); if (el) el.addEventListener("input", fn); };
  bind("tw-tilt", function(e){ s.tilt = +e.target.value/100; });
  bind("tw-slices", function(e){ s.perGap = +e.target.value; });
  var spin = document.getElementById("tw-spin"); if (spin) spin.addEventListener("change", function(e){ s.spin = e.target.checked; });
  var hole = document.getElementById("tw-hole"); if (hole) hole.addEventListener("change", function(e){ s.hole = e.target.checked; });
  frame();
}
```

- [ ] **Step 4: Manual check** — `uv run python tools/dashboard_sample.py "$CLAUDE_JOB_DIR/tmp"`, open `dashboard_step.html`, click **Tower**: stacked discs render, drag rotates, controls work, switching to another view stops the loop (no console errors).

- [ ] **Step 5: Commit**

```bash
git add "Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py"
git commit -m "feat(dashboard): render the master colour tower (canvas)"
```

### Task 4: Tests + smoke

**Files:**
- Modify: `tests/test_colorflow_assets.py`, `$CLAUDE_JOB_DIR/tmp/smoke.js`

- [ ] **Step 1: Asset markers test** (append to `test_colorflow_assets.py`)

```python
def test_dashboard_has_tower_view() -> None:
    css, js = assets.DASHBOARD_CSS, assets.DASHBOARD_JS
    assert ".tower-wrap" in css
    assert 'id="cfd-tower"' in js                 # toolbar chip
    assert "function towerView(" in js
    assert "function startTower(" in js and "function stopTower(" in js
    assert "cancelAnimationFrame" in js           # loop is cancellable (no leak)
    assert "document.body.contains(cv)" in js     # self-stops when canvas leaves DOM
```

- [ ] **Step 2: Run it** — `uv run pytest -n auto tests/test_colorflow_assets.py -q` → PASS.

- [ ] **Step 3: Smoke behavioural check** (in `smoke.js`, after the focus block; jsdom has no real canvas so guard on no-throw + DOM)

```js
// Tower view: button toggles it, injects a canvas, and does not throw under jsdom
const towerBtn = app.querySelector('#cfd-tower');
assert(towerBtn, 'toolbar has a Tower button');
towerBtn.click();
assert(app.querySelector('#cfd-tower-cv'), 'Tower view injects its canvas');
assert(towerBtn.getAttribute('aria-pressed') === 'true', 'Tower button reports pressed');
towerBtn.click(); // back to tabs
assert(!app.querySelector('#cfd-tower-cv'), 'leaving Tower removes the canvas');
assert(app.querySelector('.heat'), 'returning to Overview restores the heatmap');
```

- [ ] **Step 4: Run smoke** — `uv run python tools/dashboard_sample.py "$CLAUDE_JOB_DIR/tmp"` then `node "$CLAUDE_JOB_DIR/tmp/smoke.js" "$CLAUDE_JOB_DIR/tmp/dashboard_step.html"` → SMOKE PASSED, no `JSDOM JS ERROR`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_colorflow_assets.py
git commit -m "test(dashboard): cover the Tower view markup + toggle"
```

## Verification

1. `cd` repo root.
2. `uv run pytest -n auto` — all pass (existing + Tower marker test).
3. Regenerate + smoke: `uv run python tools/dashboard_sample.py "$CLAUDE_JOB_DIR/tmp"` then `node "$CLAUDE_JOB_DIR/tmp/smoke.js" "$CLAUDE_JOB_DIR/tmp/dashboard_step.html"` — SMOKE PASSED, **no** `JSDOM JS ERROR` (proves the null-canvas guard).
4. Manual: open `dashboard_step.html`, click **Tower** — discs stack and rotate (drag), tilt/blend/spin/core controls work, switching views stops the loop cleanly. Toggle OS reduced-motion → no auto-spin. Compare against `tools/disc_tower_draft.html`.

## Risks / decisions (defaults chosen; flip at review)

- **Blob placement** = colour-wheel angle by step index (draft default). Alt: by workflow-step order around the circle. Cosmetic.
- **Smooth interpolated tower** (sub-slices between masters, `blend` slider) vs literal one-disc-per-master (`blend=1`). Default smooth=12.
- **Core/hole = uncoloured share** (default). Can disable per the toggle.
- **Single-master fonts**: `N=1`, one disc, no interpolation — handled (`dz=0` guard).
- **Performance**: fields built once per `startTower` (not per frame); ~5 masters × 320² offscreen = trivial. Many masters (20+) still cheap.
- **jsdom**: no 2d context → `startTower()` no-ops; smoke only checks DOM wiring, not pixels.
- **Native Glyphs palette**: deferred. This renderer is WKWebView-ready for a future palette panel; SceneKit/CALayer remain options if true rotatable 3D is wanted later.
