# Color Flow Report — Timeline Tab Enhancements Design

**Date:** 2026-06-07
**Scope:** The Timeline tab of the self-contained offline HTML dashboard
(`colorflow_dashboard.py` model + `colorflow_assets.py` front-end).
**Status:** Approved feature set (Hugo picked 13 of 20 R&D ideas), ready to build.

## Goal

Turn the Timeline tab from two static widgets (a multi-master % line chart + a
date A/B compare panel) into an interrogable, story-telling progress surface,
using data already embedded in the report. Thirteen features, twelve of them
pure front-end; one (`#18`) needs a ~2-line Python model addition.

## Selected features (R&D numbering)

| # | Name | Group | Data | Effort |
|---|------|-------|------|--------|
| 7 | Real calendar X axis + week bands | chart | client-derivable | S |
| 10 | Smooth filled hero area (selected master) | chart | already-computed | S |
| 6 | Snapping crosshair read-out | chart | already-computed | S |
| 8 | Brush-to-compare on the chart | chart | client-derivable | M |
| 5 | Colour streamgraph over time (Line/Flow toggle) | chart | client-derivable | L |
| 14 | This-week digest card | story | client-derivable | S |
| 15 | Regression log + chart flags | review | client-derivable | M |
| 17 | Per-category progress lanes | review | client-derivable | M |
| 18 | Per-script progress lanes | review | **needs model change** | M |
| 19 | Deadline marker + on-track verdict | review | client-derivable | M |
| 11 | Time Machine scrubber (+play) | replay | client-derivable | L |
| 12 | Scrub-locked heatmap diff rings | replay | client-derivable | M |
| 20 | Rich empty / day-2 seed state | onboarding | client-derivable | M |

Skipped this round: 1–4, 9, 13, 16 (the forecast-surfacing set + stalled-glyphs).

## Existing substrate (reuse, do not reinvent)

- `trendParts(W, Ht)` — builds the line chart SVG; inline `X(off)`/`Y(pct)` scale
  closures, per-master polylines + `tl-dot` circles, `dayOff(date)` from real ISO
  dates, `selLine` (selected master kept on top). `timelineView()` wraps it +
  `dateDiffPanel()`. `hasTrend()` gates at ≥2 snapshots.
- `dateDiffPanel()` + `diffCounts(masterId, isoA, isoB)` — A/B compare; returns
  `{advanced, regressed, unchanged, deltaPct}`. Driven by `state.dateA/dateB`.
- `stateAt(masterId, isoDate) → {glyphName: stepKey}` and `journeyOf(...)` —
  reconstruct any glyph's colour at any date from the sparse `H.journeyIndex`.
- `rankOf(key)`, `varFor(key)`, `labelFor(key)`, `openJourney(name)`, `esc()`,
  `pct()`, `stepWeights()`, the `cfd-tip` floating-tooltip pattern, the
  `setFocus`/`__cfdNoAnim`/`matchMedia` reduced-motion pattern, and
  `applyBeforeAfter()` (recolours `.heat .cell` backgrounds in place).
- Model fields: `H.trend.series` (per-date `{date, masters:{id:{started,final,total}}}`),
  `H.trend.forecast[id]`, `H.trend.streak`, `H.trend.dates`, `H.trend.today`,
  `H.journeyIndex`, `H.masters`, `H.steps`, `H.order`, `H.glyphNames`,
  `H.categories` (array parallel to glyphNames), `H.glyphTotal`, `H.paths`,
  `H.changes`, `H.coverage.scriptMeta`.

## Locked design decisions

- **D1 — Timeline layout (top → bottom):** seed/empty state (`#20`, when <2
  snapshots) · This-week digest (`#14`) · main chart block (axis `#7`, hero fill
  `#10`, Line/Flow toggle → streamgraph `#5`, crosshair `#6`, brush `#8`, deadline
  rule `#19`, regression ticks `#15`) · Compare panel (existing, now brush-driven) ·
  Deadline control + verdict chips (`#19`) · Time Machine (`#11` + rings `#12`) ·
  Per-category lanes (`#17`) · Per-script lanes (`#18`) · Regression log (`#15`).
- **D2 — Streamgraph is opt-in:** a "Line / Flow" toggle on the chart, default
  **Line** (current behaviour stays the default; Flow is one tap away).
- **D3 — Scrubber owns its heatmap:** the main heatmap lives in the Overview tab,
  not the Timeline tab, so `#11` renders its **own compact heatmap** inside the
  Timeline tab and recolours cells via `stateAt(master, dateAtIndex) → varFor(key)`.
- **D4 — Deadline persists in `localStorage`** keyed by family name (offline-safe).
  Empty by default → the feature stays dormant until a date is entered.
- **D5 — Model change (`#18` only):** add a `scripts` list parallel to `glyphNames`
  in `build_model` (mirror `categories = [...]` at ~line 998), emit `"scripts"`.
  `stateAt` cannot map glyph→script otherwise (`scriptMeta` is keyed by script).
- **D6 — Honesty + a11y:** every new motion respects `prefers-reduced-motion`
  (reuse `__cfdNoAnim`/`matchMedia`); everything theme-safe via CSS vars; no
  network; hedged/empty states never invent data (e.g. regression log renders
  nothing when clean, digest falls back to "since you started" when <7 days).

## Feature notes

- **#7 calendar axis:** label the X axis with real dates, zebra week bands (3–4%
  `--text` tint, theme-safe), weekend tint, a dashed `--accent` "today" rule from
  `H.trend.today`; thin tick labels so they never overlap on long spans.
- **#10 hero fill:** SVG `linearGradient` (master hue ~22% → transparent) under the
  selected master's polyline + monotone smoothing that never overshoots real
  points; keep `tl-dot`s visible so exact values stay honest.
- **#6 crosshair:** hover → vertical guide snaps to the nearest snapshot X; a
  floating `cfd-tip` card lists every master's exact % + the date. Chart focusable,
  Left/Right step snapshots. No interpolation (series is discrete).
- **#8 brush:** drag a range across the chart (pointer events on an SVG overlay) →
  feeds `diffCounts` two snapped dates; the `<select>`s stay synced as the a11y
  fallback. Inverse X→date from the forward `X()` math.
- **#5 streamgraph:** stacked area of all step counts per date, bands bottom→top by
  `H.order`, fills `--c0..--cN`, an "uncoloured" bucket hatched on top; per-date
  counts tallied client-side from `stateAt` over `H.trend.dates`; hover crosshair →
  per-step counts. Degrades to a 2–3 band view on sparse history.
- **#14 digest:** `diffCounts(master, ~7-days-ago, today)` with auto-snapped dates
  (labelled honestly) → big net number + advanced/regressed micro-stats + a single
  arrow vs the prior week (a second `diffCounts`). All-masters roll-up when no
  master is selected.
- **#15 regression log:** walk consecutive `H.trend.dates` with `stateAt` + `rankOf`
  for rank drops → newest-first from→to swatch table (top 8 + "show all"), red ticks
  on the chart days where any regression happened, row click → `openJourney`. Renders
  nothing when clean.
- **#17 / #18 lanes:** per date, sum `stateAt` keys per category (`#17`, from
  `H.categories`) / per script (`#18`, from the new `H.scripts`); render a small
  sparkline per group (reuse the `sparkline()` idiom), laggard-first, current % +
  a delta arrow vs a week ago.
- **#19 deadline:** an `<input type="date">` (persisted via D4) → a dashed red rule
  on the chart (reusing #7's date→X math) + per-master verdict chips
  (green/amber/red vs forecast ETA) with the required catch-up pace
  (`remaining / daysUntilTarget`).
- **#11 Time Machine:** a notched range slider (one notch per snapshot) over a
  compact heatmap (D3); dragging recolours cells from `stateAt`; a play button
  auto-advances (throttled to rAF). Keyboard Left/Right ±1 day, Home/End. Play
  disabled <3 snapshots; reduced-motion disables autoplay (drag still snaps).
- **#12 diff rings:** while scrubbing, glyphs that changed since the previous day
  flash a ring (green advanced / amber regressed) + a live "+12, −1 today" chip;
  `stateAt(prev)` vs `stateAt(this)`. Additive on #11; reduced-motion → static
  border, chip still updates.
- **#20 seed state:** replace the bland "not enough history" line. <2 snapshots →
  skeleton preview (dashed placeholder line + ghost dots + one real "today" dot) +
  locked preview chips ("unlocks at 2 days") + a "History: N of 60 days" meter.
  ==2 snapshots → compact "in 1 day you advanced N (+X%)" layout (A/B hidden).

## Error handling & invariants

Preserve the test-asserted invariants: fully self-contained (no `http://`/`https://`),
gzipped model embedded, `<noscript>` present, dark/light themes, reduced-motion
respected. Every feature degrades gracefully on <2 / ==2 / sparse history. The model
change (`#18`) must not break the empty-font invariant (`scripts == []` when no glyphs).

## Testing

- **Front-end:** extend `tests/test_colorflow_assets.py` in its existing style —
  assert new JS function names + key logic markers (calendar axis labels, gradient
  id, crosshair handler, brush handler, streamgraph builder + Line/Flow toggle,
  digest builder, regression-log walk, category/script lane builders, deadline
  input + verdict, scrubber + `stateAt` recolour, diff-ring class, seed-state markup)
  and the reduced-motion gates.
- **Model (`#18`):** extend `tests/test_colorflow_dashboard.py` for the `scripts`
  array — parallel to `glyphNames`, `[]` for an empty font.
- **Behavioural smoke:** regenerate via `tools/dashboard_sample.py` and run the
  node/jsdom harness — Line/Flow toggle swaps views; crosshair snaps; brush updates
  diff counts; scrubber recolours the mini heatmap; seed state shows at <2 snapshots.
- Keep `ruff` + `pyright` clean on any touched Python.

## Build order (dependency-sorted)

`#7` → `#10` → `#6` → `#8` → `#5` → `#14` → `#15` → `#17` → `#18` → `#19` → `#11`
→ `#12` → `#20`. Chart foundations first (axis/scale before overlays), then cards,
then the scrubber (and its rings), then the onboarding gate last.
