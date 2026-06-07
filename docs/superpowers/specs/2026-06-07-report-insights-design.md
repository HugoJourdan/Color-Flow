# Color Flow Report — Insight Features Design

**Date:** 2026-06-07
**Scope:** The self-contained offline HTML dashboard (`colorflow_dashboard.py` model + `colorflow_assets.py` front-end).
**Status:** Approved design, ready for implementation planning.

## Goal

Surface the dashboard's already-computed time-series intelligence as six review-oriented features, fitted into the existing tab layout, with the per-glyph **journey** as the shared data substrate.

## Why this is cheap

The Python model builder already computes and embeds: per-glyph journeys, per-master forecast (ETA / confidence / velocity / remaining), last-edit ages, and since-last-run changes. The front-end renders almost none of it. So four of the six features are render-layer work over existing model fields; the other two add a small amount of model plumbing. **No new persistence** — the history store is untouched.

## Architecture

```
colorflow_dashboard.py  →  JSON model (gzip+base64 embedded)  →  DASHBOARD_JS (loadModel → state → render)
        │                                                                │
        ├─ existing: journeys, forecast_master, lastEdit, changes        ├─ new render units (cards / panel / modal / help)
        └─ small additions: aggregate forecast, compact journey index    └─ new state keys + a shared time helper
```

The six features sit on one shared substrate (the journey index). Three render as Overview cards, one as a Timeline-tab panel, one as a click-through modal, one as a header help panel.

## Components

### 0. Journey index — shared substrate

- **Purpose:** give the front-end a per-master, per-glyph, time-ordered list of `(date, stepKey)` change-events so any feature can reconstruct the colour state at any date and diff two dates.
- **Source:** the model already carries `journeys` per master (per the inventory). Confirm its exact shape during planning. If it is sparkline-shaped rather than event-shaped, emit a compact sibling: `journeys[masterId][glyphName] = [[isoDate, stepKey], ...]`, **change-events only** (sparse), not dense per-date snapshots.
- **Interface (JS helpers):**
  - `journeyOf(masterId, glyphName) → [[date, stepKey], ...]`
  - `stateAt(masterId, isoDate) → { glyphName: stepKey }` (last event at or before the date)
- **Depends on:** `model.history` date list, `model.order` (step ranking).
- **Why sparse:** dense snapshots (glyphs × dates × masters) would bloat the embedded file for large fonts. Reconstructing from change-events keeps it small. **This is the central technical decision of the spec.**

### 1. Forecast card (Overview)

- **Purpose:** headline ETA. "At current pace, ~Aug 12 ±5d · medium confidence · 312 left · ~28/week."
- **Data:** `forecast_master` already exists per master (`etaIso`, `bandDays`, `confidence`, velocity, `remaining`). Add an **aggregate** forecast (whole font) to the model if not already emitted.
- **Render:** an Overview card via the existing `ovCard` pattern. Aggregate when no master is selected; that master's figures when one is.
- **States:** `confidence == none` (or < 2 history points) → "Not enough history yet."

### 2. Regression card (Overview)

- **Purpose:** flag glyphs that moved **backward** since the last run (e.g. finished → reopened).
- **Data:** `model.changes` (before/after step per glyph) + `model.order` for rank. Regression = `rank(after) < rank(before)`, with explicit handling for "→ uncoloured/none" (counts as backward) and off-palette steps.
- **Render:** Overview card; **hidden when zero**. Lists glyph name + before→after swatches. Clicking a row opens the journey modal (#6).

### 3. Recent activity card (Overview)

- **Purpose:** a "what moved lately" feed.
- **Data:** most recent N change-events across all glyphs (from the journey index), or `model.changes` + `lastEdit` ages.
- **Render:** Overview card; each row = glyph · before→after swatches · when ("today" / "Nd ago" / date). Row click → journey modal.

### 4. Date A vs Date B (Timeline tab)

- **Purpose:** diff two snapshots for weekly review.
- **Data:** two date `<select>`s populated from `model.history` dates; compute `stateAt(A)` vs `stateAt(B)` → counts of advanced / regressed / unchanged, net graded-% delta, and an optional per-glyph list.
- **Render:** a panel inside the existing Timeline view (not a new top-level tab). Defaults: A = earliest available, B = latest.
- **States:** < 2 distinct history dates → panel shows "Need at least two snapshots."

### 5. Per-glyph journey modal

- **Purpose:** click any heatmap glyph cell → see that glyph's full colour history over time.
- **Data:** `journeyOf(masterId, glyphName)`; render dates → step swatches (current master; optionally a row per master).
- **Render:** reuse the **existing export modal shell** (`.cfd-modal`) rather than a new dialog. Opened from a cell click handler; new state key `state.journeyGlyph`.
- **States:** glyph with no recorded history → "No history yet for this glyph."

### 6. Help / colour legend ("?" button)

- **Purpose:** onboarding key for people the report is shared with.
- **Data:** `model.steps` / `model.order` / colour overrides.
- **Render:** a button in the header/toolbar → panel listing each step (swatch + name + position in the flow) plus a short glossary (what "% complete", "forecast", "regression" mean). Static content; new state key `state.helpOpen`.

## Data flow

`model` (Python) → gzip+base64 embed → `loadModel()` → `state`. New `state` keys: `dateA`, `dateB`, `journeyGlyph`, `helpOpen`. New render entry points: three cards in the Overview extras builder, a panel in the Timeline view builder, a modal opened from the heatmap cell click handler, a panel opened from a new header button. All wired through the existing `bind()` / `update()` cycle.

## Error handling & invariants

- Every feature degrades gracefully when history < 2 dates (cards show empty states; date-diff disabled with a note).
- Journey modal handles glyphs with no history.
- Preserve the existing hard invariants the test-suite asserts: **fully self-contained, no network** (`http://`/`https://` absent), gzipped model embedded, `<noscript>` present, dark/light themes intact, `prefers-reduced-motion` respected.

## Testing

- **Model:** extend `tests/test_colorflow_dashboard.py` for any new fields (aggregate forecast; compact journey index) — shape, ranking, and empty/cyclic/one-master edge cases.
- **Front-end:** extend `tests/test_colorflow_assets.py` in its existing style (assert new JS function names + key logic markers: `stateAt(`, `journeyOf(`, `forecastCard(`, regression rank compare, date-select wiring, journey modal, legend panel).
- **Behavioural smoke:** regenerate the sample via `tools/dashboard_sample.py` and run the jsdom/node smoke harness — assert: forecast text renders; a regressed glyph appears in the regression card and is absent when none; date A/B diff counts advanced/regressed; clicking a cell opens the journey modal; legend button toggles the panel.
- Keep `ruff` + `pyright` clean on any touched Python.

## Risks / open implementation details (confirm at plan time)

- Exact shape of the existing `journeys` field (event-list vs sparkline) — determines whether the compact index is reuse or a small new emit.
- Whether an **aggregate** forecast helper needs adding (per-master exists).
- Embedded-model size for large fonts — mitigated by the sparse change-event design; verify on a real multi-master font.
- Modal reuse: confirm the export modal shell is generic enough to host journey content.

## Build order

Build the journey index first (unblocks 2/3/4/5), then the three Overview cards, then the Timeline date-diff, the journey modal, and the legend.
