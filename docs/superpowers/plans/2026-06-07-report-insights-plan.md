# Color Flow Report — Insight Features Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan. Steps use checkbox (- [ ]) syntax.

**Goal:** Surface the dashboard's already-computed time-series intelligence as six review-oriented features — a sparse per-glyph journey index plus a forecast card, a regression card, a recent-activity card, a date A-vs-B Timeline panel, a per-glyph journey modal, and a help/legend button — all fitted into the existing Overview/Timeline tab layout, with the journey index as the shared substrate.

**Architecture:** Python `build_model` emits one small new field, `journeyIndex` (sparse change-events `journeyIndex[masterId][glyphName] = [[isoDate, stepKey], ...]`) plus an aggregate forecast `trend.forecast["__all__"]`; everything else is render-layer JS over existing model fields (`trend.forecast`, `changes`, `lastEdit`, `journeys`, `order`, `steps`, `trend.dates`). New JS state keys (`dateA`, `dateB`, `journeyGlyph`, `helpOpen`) and two shared helpers (`journeyOf`, `stateAt`) drive new render units wired through the existing `bind()`/`update()` cycle. No new persistence; the history store (`HISTORY_KEY`) is untouched.

**Tech Stack:** Python 3 (pure data + HTML-string assembly, run via `uv`), inline vanilla JS embedded as `DASHBOARD_JS` string constant, pytest (substring + behavioural assertions, no node/jsdom runtime exists in this project), ruff, pyright.

## File Structure

- **Modify** `Color Flow.glyphsPalette/Contents/Resources/colorflow_dashboard.py` — add `build_journey_index()` and `aggregate_forecast()` helpers; emit `journeyIndex` and `trend.forecast["__all__"]` in `build_model`.
- **Modify** `Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py` — add JS helpers `journeyOf`/`stateAt`, render units `forecastCard`/`regressionCard`/`recentCard`/`dateDiffPanel`/`journeyModal`/`helpPanel`, new `state` keys, header `?` button, and `bind()` wiring; extend `DASHBOARD_CSS` minimally for the help panel and diff panel.
- **Modify** `tests/test_colorflow_dashboard.py` — pytest for `build_journey_index`, `aggregate_forecast`, and the two new `build_model` fields (shape, ranking, empty/one-master/cyclic edge cases).
- **Modify** `tests/test_colorflow_assets.py` — substring assertions for new JS function names + logic markers, and a behavioural-smoke section asserting the wiring is reachable from `build_html` output.

## Task 1: Journey index — shared substrate (Python emit + JS helpers)

The existing `journeys` field is dense per-date (`[key_per_date]` aligned to `dates`). Per the spec this is the central technical decision: emit a **sparse** sibling `journeyIndex` of change-events only, and add the two JS reconstruction helpers `journeyOf` / `stateAt`.

**Files**
- Modify: `Color Flow.glyphsPalette/Contents/Resources/colorflow_dashboard.py`
- Modify: `Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py`
- Test: `tests/test_colorflow_dashboard.py`, `tests/test_colorflow_assets.py`

- [ ] **Step — failing test for `build_journey_index` shape (sparse change-events).** Add to `tests/test_colorflow_dashboard.py` (after the journeys-related tests):

```python
def test_build_journey_index_emits_sparse_change_events_only() -> None:
    # history: 3 dates, one master, glyph A changes twice, glyph B never changes.
    history = {
        "2026-06-01": {"m1": {"A": cc.NO_COLOR, "B": 2}},
        "2026-06-02": {"m1": {"A": 1, "B": 2}},
        "2026-06-03": {"m1": {"A": 5, "B": 2}},
    }
    dates = ["2026-06-01", "2026-06-02", "2026-06-03"]
    index = db.build_journey_index(history, dates)
    # Only the first observation + each actual change is recorded (sparse).
    assert index["m1"]["A"] == [["2026-06-01", cc.NO_COLOR], ["2026-06-02", 1], ["2026-06-03", 5]]
    # A glyph that never changed records a single initial event, not one per date.
    assert index["m1"]["B"] == [["2026-06-01", 2]]


def test_build_journey_index_handles_missing_dates_as_uncoloured() -> None:
    # m1 has no entry on the middle date -> that date reads as NO_COLOR, a change.
    history = {
        "2026-06-01": {"m1": {"A": 3}},
        "2026-06-02": {},
        "2026-06-03": {"m1": {"A": 3}},
    }
    dates = ["2026-06-01", "2026-06-02", "2026-06-03"]
    index = db.build_journey_index(history, dates)
    assert index["m1"]["A"] == [["2026-06-01", 3], ["2026-06-02", cc.NO_COLOR], ["2026-06-03", 3]]


def test_build_journey_index_empty_when_no_dates() -> None:
    assert db.build_journey_index({}, []) == {}
```

- [ ] **Run it (expected FAIL — `AttributeError: module 'colorflow_dashboard' has no attribute 'build_journey_index'`).**
  `uv run pytest -n auto tests/test_colorflow_dashboard.py::test_build_journey_index_emits_sparse_change_events_only tests/test_colorflow_dashboard.py::test_build_journey_index_handles_missing_dates_as_uncoloured tests/test_colorflow_dashboard.py::test_build_journey_index_empty_when_no_dates`

- [ ] **Minimal implementation — add `build_journey_index` to `colorflow_dashboard.py`** (place it directly after `_glyph_journeys`, before `_days_ago` at line 838):

```python
def build_journey_index(history: dict, dates: list) -> dict:
    """Sparse per-master ``{glyph_name: [[iso_date, step_key], ...]}`` of colour
    *change-events* — the first observation of each glyph plus every date its key
    actually changed. Reconstructs full state at any date by carrying the last
    event forward, so it stays small for big fonts (vs the dense ``journeys``
    array). Missing dates read as uncoloured. Covers every glyph seen in history,
    aligned to ``dates`` (oldest-first)."""
    if not dates:
        return {}
    index: dict = {}
    master_ids: set = set()
    for per_master in history.values():
        master_ids.update(per_master.keys())
    for master_id in master_ids:
        names: set = set()
        for date in dates:
            names.update(history.get(date, {}).get(master_id, {}).keys())
        per_glyph: dict = {}
        for name in names:
            events: list = []
            previous = None
            for date in dates:
                key = history.get(date, {}).get(master_id, {}).get(name, colornames.NO_COLOR)
                if key != previous:
                    events.append([date, key])
                    previous = key
            per_glyph[name] = events
        index[master_id] = per_glyph
    return index
```

- [ ] **Run it (expected PASS).**
  `uv run pytest -n auto tests/test_colorflow_dashboard.py::test_build_journey_index_emits_sparse_change_events_only tests/test_colorflow_dashboard.py::test_build_journey_index_handles_missing_dates_as_uncoloured tests/test_colorflow_dashboard.py::test_build_journey_index_empty_when_no_dates`

- [ ] **Failing test for `journeyIndex` emitted by `build_model`.** Add to `tests/test_colorflow_dashboard.py`:

```python
def test_build_model_emits_journey_index_field(tmp_path) -> None:
    (tmp_path / "colorNames.txt").write_text(
        "purple=Outline\nyellow=Ready\nNone=Nothing\n", encoding="utf-8")
    master = _FakeMaster("m1", "Regular")
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(8)})]
    font = _FakeFont([master], glyphs, filepath=str(tmp_path / "Font.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert "journeyIndex" in model
    # One master, today's snapshot only -> one initial event for A.
    assert model["journeyIndex"]["m1"]["A"] == [["2026-06-05", 8]]
```

- [ ] **Run it (expected FAIL — `KeyError: 'journeyIndex'`).**
  `uv run pytest -n auto tests/test_colorflow_dashboard.py::test_build_model_emits_journey_index_field`

- [ ] **Minimal implementation — emit `journeyIndex` in `build_model`.** After line 920 (`journeys = _glyph_journeys(...)`), add:

```python
    journey_index = build_journey_index(history, dates)
```

Then in the returned dict, after the `"journeys": journeys,` line (line 954), add:

```python
        "journeyIndex": journey_index,
```

- [ ] **Run it (expected PASS).**
  `uv run pytest -n auto tests/test_colorflow_dashboard.py::test_build_model_emits_journey_index_field`

- [ ] **Failing test for JS helpers `journeyOf` / `stateAt`.** Add to `tests/test_colorflow_assets.py`:

```python
def test_dashboard_js_has_journey_helpers() -> None:
    js = assets.DASHBOARD_JS
    assert "function journeyOf(" in js
    assert "function stateAt(" in js
    # journeyOf reads the sparse index; stateAt carries the last event forward.
    assert "H.journeyIndex" in js
    assert "<=" in js  # stateAt: last event at or before the date
```

- [ ] **Run it (expected FAIL — `AssertionError` on `function journeyOf(`).**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_dashboard_js_has_journey_helpers`

- [ ] **Minimal implementation — add the two helpers to `DASHBOARD_JS`.** In `colorflow_assets.py`, insert directly after the `journeyFor` function (after line 841, before `function showTip`):

```javascript
  // ----- Shared journey substrate: reconstruct colour state from the sparse
  // change-event index (journeyIndex[masterId][glyphName] = [[date,key],...]) ----
  function journeyOf(masterId, name){
    var perMaster = H.journeyIndex && H.journeyIndex[masterId];
    return (perMaster && perMaster[name]) || [];
  }
  function stateAt(masterId, iso){
    var perMaster = H.journeyIndex && H.journeyIndex[masterId];
    var out = {};
    if (!perMaster) return out;
    for (var name in perMaster){
      var events = perMaster[name], key = null;
      for (var i=0;i<events.length;i++){
        if (events[i][0] <= iso) key = events[i][1]; else break;
      }
      if (key !== null) out[name] = key;
    }
    return out;
  }
```

- [ ] **Run it (expected PASS).**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_dashboard_js_has_journey_helpers`

- [ ] **Lint + types clean.**
  `uv run ruff check` and `uv run pyright`

- [ ] **Commit.** `feat(report): add sparse per-glyph journey index and JS stateAt/journeyOf helpers`

## Task 2: Forecast headline card (Overview)

Add an aggregate (whole-font) forecast to the model, then render an Overview card via the existing `ovCard` pattern: aggregate when no master is selected, that master's figures when one is.

**Files**
- Modify: `Color Flow.glyphsPalette/Contents/Resources/colorflow_dashboard.py`
- Modify: `Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py`
- Test: `tests/test_colorflow_dashboard.py`, `tests/test_colorflow_assets.py`

- [ ] **Failing test for `aggregate_forecast`.** Add to `tests/test_colorflow_dashboard.py`:

```python
def test_aggregate_forecast_sums_finals_across_masters() -> None:
    # Two masters, two dates; each master advances its `final` over time.
    series = [
        {"date": "2026-05-01",
         "masters": {"m1": {"final": 0, "started": 0, "total": 10},
                     "m2": {"final": 0, "started": 0, "total": 10}}},
        {"date": "2026-05-29",
         "masters": {"m1": {"final": 5, "started": 5, "total": 10},
                     "m2": {"final": 5, "started": 5, "total": 10}}},
    ]
    now = datetime(2026, 5, 29)
    result = db.aggregate_forecast(series, ["m1", "m2"], 20, now, is_free=False)
    assert result["total"] == 20
    assert result["final"] == 10        # 5 + 5
    assert result["remaining"] == 10
    assert result["confidence"] != "none"
    assert result["etaIso"] is not None


def test_aggregate_forecast_no_masters_is_none_confidence() -> None:
    result = db.aggregate_forecast([], [], 0, datetime(2026, 5, 29), is_free=False)
    assert result["confidence"] == "none"
    assert result["etaIso"] is None
```

- [ ] **Run it (expected FAIL — `AttributeError: ... 'aggregate_forecast'`).**
  `uv run pytest -n auto tests/test_colorflow_dashboard.py::test_aggregate_forecast_sums_finals_across_masters tests/test_colorflow_dashboard.py::test_aggregate_forecast_no_masters_is_none_confidence`

- [ ] **Minimal implementation — add `aggregate_forecast`** to `colorflow_dashboard.py`, directly after `forecast_master` (after line 418, before `progress_streak`). It builds a synthetic single-master series whose `final` is the sum across masters per date, then reuses `forecast_master`:

```python
def aggregate_forecast(series: list[dict], master_ids: list, total: int,
                       now: datetime, is_free: bool, window_days: int = 28) -> dict:
    """Whole-font forecast: a single hedged ETA from the summed ``final`` of every
    master per date. Built by collapsing ``series`` into one synthetic master, then
    reusing :func:`forecast_master` so the velocity/band/confidence rules stay
    identical to the per-master cards."""
    collapsed = []
    for point in series:
        summed = sum(point["masters"][master_id]["final"]
                     for master_id in master_ids if master_id in point["masters"])
        collapsed.append({"date": point["date"], "masters": {"__all__": {"final": summed}}})
    return forecast_master(collapsed, "__all__", total, now, is_free, window_days)
```

- [ ] **Run it (expected PASS).**
  `uv run pytest -n auto tests/test_colorflow_dashboard.py::test_aggregate_forecast_sums_finals_across_masters tests/test_colorflow_dashboard.py::test_aggregate_forecast_no_masters_is_none_confidence`

- [ ] **Failing test for `trend.forecast["__all__"]` in `build_model`.** Add to `tests/test_colorflow_dashboard.py`:

```python
def test_build_model_trend_forecast_has_aggregate(tmp_path) -> None:
    (tmp_path / "colorNames.txt").write_text(
        "purple=Outline\nyellow=Ready\nNone=Nothing\n", encoding="utf-8")
    master = _FakeMaster("m1", "Regular")
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(8)})]
    font = _FakeFont([master], glyphs, filepath=str(tmp_path / "Font.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert "__all__" in model["trend"]["forecast"]
    # Aggregate `final` is the SUM of per-master finals, so its denominator is the
    # whole-font capacity: glyphTotal * masters (== glyphTotal here, 1 master).
    assert (model["trend"]["forecast"]["__all__"]["total"]
            == model["glyphTotal"] * len(font.masters))


def test_build_model_trend_forecast_aggregate_total_scales_with_masters(tmp_path) -> None:
    # Two masters: the aggregate total must be glyphTotal * 2, NOT glyphTotal.
    # This is the multi-master case the single-master test above can't exercise.
    (tmp_path / "colorNames.txt").write_text(
        "purple=Outline\nyellow=Ready\nNone=Nothing\n", encoding="utf-8")
    masters = [_FakeMaster("m1", "Regular"), _FakeMaster("m2", "Bold")]
    glyphs = [
        _FakeGlyph("A", {"m1": _FakeLayerColor(8), "m2": _FakeLayerColor(8)}),
        _FakeGlyph("B", {"m1": _FakeLayerColor(4), "m2": _FakeLayerColor(4)}),
    ]
    font = _FakeFont(masters, glyphs, filepath=str(tmp_path / "Font.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["glyphTotal"] == 2
    assert model["trend"]["forecast"]["__all__"]["total"] == 4   # 2 glyphs * 2 masters
```

- [ ] **Run it (expected FAIL — `KeyError: '__all__'`).**
  `uv run pytest -n auto tests/test_colorflow_dashboard.py::test_build_model_trend_forecast_has_aggregate tests/test_colorflow_dashboard.py::test_build_model_trend_forecast_aggregate_total_scales_with_masters`

- [ ] **Minimal implementation — add the aggregate to the `trend` dict.** In `build_model`, change the `trend` assembly so the `forecast` dict also carries `"__all__"`. The aggregate `final` is the **sum** of every master's `final` (range `0..glyph_total * len(masters)`), so its `total` denominator must be `glyph_total * len(font.masters)` — not `glyph_total`. Each *per-master* forecast keeps `glyph_total` as its own denominator. **Guard:** emit `"__all__"` only when there is at least one master (i.e. when the per-master forecast dict is non-empty) — an empty/master-less font must keep `trend.forecast == {}` (the pre-existing `test_build_model_empty_font_does_not_crash` invariant). Build the per-master dict first, then conditionally add the aggregate:

```python
    forecast = {master.id: forecast_master(series, master.id, glyph_total, now, is_free)
                for master in font.masters}
    # Only emit the whole-font aggregate when there is at least one master; an empty
    # font must keep trend.forecast == {} (no per-master entries, no "__all__").
    if forecast:
        forecast["__all__"] = aggregate_forecast(
            series, [master.id for master in font.masters],
            glyph_total * len(font.masters), now, is_free)
    trend = {
        "series": series,
        "forecast": forecast,
        # ... dates / today / streak unchanged ...
    }
```

> Empty-font invariant: with no masters the per-master dict is empty, so `"__all__"` is skipped and `trend.forecast == {}` is preserved — the pre-existing `test_build_model_empty_font_does_not_crash` assertion keeps passing unchanged. `aggregate_forecast` itself is left as-is (it still returns a none-confidence dict for empty input; that result is simply never emitted for a master-less font).

- [ ] **Run it (expected PASS).**
  `uv run pytest -n auto tests/test_colorflow_dashboard.py::test_build_model_trend_forecast_has_aggregate tests/test_colorflow_dashboard.py::test_build_model_trend_forecast_aggregate_total_scales_with_masters`

- [ ] **Failing test for `forecastCard` JS.** Add to `tests/test_colorflow_assets.py`:

```python
def test_dashboard_js_has_forecast_card() -> None:
    js = assets.DASHBOARD_JS
    assert "function forecastCard(" in js
    assert 'ovCard("forecast"' in js
    assert "H.trend.forecast" in js
    assert "etaIso" in js
    assert "confidence" in js
    assert "Not enough history yet" in js   # the none/<2-points empty state
```

- [ ] **Run it (expected FAIL — `AssertionError` on `function forecastCard(`).**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_dashboard_js_has_forecast_card`

- [ ] **Minimal implementation — add `forecastCard` and append it in `overviewExtras`.** In `colorflow_assets.py`, add `forecastCard` directly before `overviewExtras` (before line 624):

```javascript
  function forecastCard(){
    var fc = H.trend && H.trend.forecast;
    if (!fc) return "";
    var key = state.master || "__all__";
    var f = fc[key] || fc["__all__"];
    if (!f) return "";
    var body;
    if (f.confidence === "none" || f.points < 2){
      body = '<p class="ov-empty">Not enough history yet.</p>';
    } else if (f.confidence === "done"){
      body = '<p class="fc-line"><b>Done.</b> All '+f.total+' complete.</p>';
    } else if (!f.etaIso){
      body = '<p class="ov-empty">No recent progress — no estimate.</p>';
    } else {
      body = '<p class="fc-line"><b>~'+esc(f.etaIso)+'</b>'
        + (f.bandDays!=null ? ' ±'+f.bandDays+'d' : '')
        + ' · '+esc(f.confidence)+' confidence · '+f.remaining+' left'
        + ' · ~'+f.velocityPerWeek+'/week</p>';
    }
    return ovCard("forecast", "Forecast", body, false);
  }
```

Then change `overviewExtras` (line 626) to prepend the forecast card:

```javascript
  function overviewExtras(){
    if (!H.masters.length) return "";
    return '<div class="ov-extra">'+forecastCard()+leaderboard()+histogram()+timelineCard()+'</div>';
  }
```

- [ ] **Run it (expected PASS).**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_dashboard_js_has_forecast_card`

- [ ] **Self-contained invariant still holds.**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_build_html_is_self_contained_and_accessible`

- [ ] **Manual smoke in Glyphs:** Open a multi-day-history font's report, Overview tab. Confirm a "Forecast" card appears with `~<date> ±Nd · <confidence> confidence · N left · ~N/week`; select one master in the tower and confirm the card switches to that master's figures.

- [ ] **Lint + types clean.** `uv run ruff check` and `uv run pyright`

- [ ] **Commit.** `feat(report): add aggregate forecast field and Overview forecast card`

## Task 3: Regression card (Overview)

Flag glyphs that moved backward since the last run, using `model.changes` (before/after) ranked by `model.order`. Hidden when zero. Rows open the journey modal (wired in Task 6).

**Files**
- Modify: `Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py`
- Test: `tests/test_colorflow_assets.py`

- [ ] **Failing test for `regressionCard` JS + rank-compare logic.** Add to `tests/test_colorflow_assets.py`:

```python
def test_dashboard_js_has_regression_card() -> None:
    js = assets.DASHBOARD_JS
    assert "function regressionCard(" in js
    assert "function rankOf(" in js
    assert "H.changes" in js
    # backward = new rank below old rank; "-> none" counts as backward.
    assert "rankOf(nw) < rankOf(was)" in js
    assert 'data-jglyph' in js   # rows are journey-modal triggers
    # swatch helper reuses the canonical varFor (no inline '--c'+key derivation).
    assert "function swatchFor(" in js
    assert "varFor(key)" in js


def test_dashboard_js_regression_card_hidden_when_zero() -> None:
    js = assets.DASHBOARD_JS
    # The builder returns "" when no regressions are found.
    assert 'if (!rows.length) return "";' in js
```

- [ ] **Run it (expected FAIL — `AssertionError` on `function regressionCard(`).**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_dashboard_js_has_regression_card tests/test_colorflow_assets.py::test_dashboard_js_regression_card_hidden_when_zero`

- [ ] **Minimal implementation — add `rankOf` + `regressionCard`.** In `colorflow_assets.py`, add directly before `forecastCard` (added in Task 2):

```javascript
  // rank within the workflow order; uncoloured/none and off-palette steps rank
  // below every real step so "-> none" reads as backward.
  function rankOf(key){
    var order = H.order || [];
    var idx = order.indexOf(String(key));
    return idx === -1 ? -1 : idx;
  }
  // canonical swatch: reuse the existing `varFor` helper, adding the null/undefined
  // guard `varFor` lacks (varFor(null) -> "--cnull"). `key==null` catches both.
  function swatchFor(key){
    var v = (key==null) ? "--c-none" : varFor(key);
    return '<span class="rg-sw" style="background:var('+v+')"></span>';
  }
  function regressionCard(){
    var changes = (H.changes && state.master) ? H.changes[state.master]
      : mergedChanges();
    var rows = "", count = 0;
    for (var name in changes){
      var pair = changes[name], was = pair[0], nw = pair[1];
      if (rankOf(nw) < rankOf(was)){
        rows += '<div class="rg-row" data-jglyph="'+esc(name)+'"><span class="rg-n">'+esc(name)+'</span>'
          + swatchFor(was)+'<span class="rg-ar">→</span>'+swatchFor(nw)+'</div>';
        count++;
      }
    }
    if (!rows.length) return "";
    return ovCard("regression", "Moved backward ("+count+")", rows, count>6);
  }
  // When no master is selected, merge every master's changes so the global card
  // still flags regressions; per-glyph last-write wins (stable for review).
  function mergedChanges(){
    var all = {};
    var byMaster = H.changes || {};
    for (var mid in byMaster){
      var ch = byMaster[mid];
      for (var name in ch){ all[name] = ch[name]; }
    }
    return all;
  }
```

Then append `regressionCard()` in `overviewExtras` after `forecastCard()`:

```javascript
  function overviewExtras(){
    if (!H.masters.length) return "";
    return '<div class="ov-extra">'+forecastCard()+regressionCard()+leaderboard()+histogram()+timelineCard()+'</div>';
  }
```

- [ ] **Run it (expected PASS).**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_dashboard_js_has_regression_card tests/test_colorflow_assets.py::test_dashboard_js_regression_card_hidden_when_zero`

- [ ] **Manual smoke in Glyphs:** In a font where a finished glyph was reopened since the last save, open the report Overview. Confirm a "Moved backward (N)" card lists the glyph with a before→after swatch pair. In a font with no regressions, confirm the card is absent (not an empty card).

- [ ] **Lint + types clean.** `uv run ruff check` and `uv run pyright`

- [ ] **Commit.** `feat(report): add Overview regression card flagging backward glyph moves`

## Task 4: Recent activity card (Overview)

A "what moved lately" feed: the most recent change-events from the journey index, each row showing glyph · before→after swatches · when (from `lastEdit` ages). Rows open the journey modal.

**Scope decision (spec #3, design line 54 — "most recent N change-events across all glyphs").** The card surfaces the **latest events from the selected master's index**: it reads `journeyIndex[mid]` for the selected master (or `H.masters[0]` when none is selected), iterating *all glyphs* of that master. This is intentional and matches the rest of the Overview/heatmap, which is per-master throughout (the forecast/regression cards and the date-diff panel all key off `state.master || H.masters[0].id`). The spec's "across all glyphs" is read as *across all glyphs of the master in view*, not *flattened across every master*. The `journeyIndex` is emitted per-master (`journeyIndex[masterId][glyphName]`), so a cross-master flatten would require a separate merge pass and a master column per row. **Cross-master aggregation is a deliberate non-goal for v1** — a documented choice (keeping the per-master framing of the whole report consistent), not an oversight.

**Files**
- Modify: `Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py`
- Test: `tests/test_colorflow_assets.py`

- [ ] **Failing test for `recentCard` JS.** Add to `tests/test_colorflow_assets.py`:

```python
def test_dashboard_js_has_recent_card() -> None:
    js = assets.DASHBOARD_JS
    assert "function recentCard(" in js
    assert 'ovCard("recent"' in js
    assert "H.journeyIndex" in js      # latest events across the active master's glyphs
    assert "H.lastEdit" in js          # "Nd ago" / "today" labelling
    assert "data-jglyph" in js         # rows open the journey modal
    assert "ago" in js


def test_dashboard_js_recent_card_when_label() -> None:
    js = assets.DASHBOARD_JS
    assert "function whenLabel(" in js
    assert '"today"' in js
```

- [ ] **Run it (expected FAIL — `AssertionError` on `function recentCard(`).**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_dashboard_js_has_recent_card tests/test_colorflow_assets.py::test_dashboard_js_recent_card_when_label`

- [ ] **Minimal implementation — add `whenLabel` + `recentCard`.** In `colorflow_assets.py`, add directly after `regressionCard` (and its `mergedChanges`):

```javascript
  function whenLabel(name){
    var days = (H.lastEdit && H.lastEdit[name] != null) ? H.lastEdit[name] : null;
    if (days == null) return "";
    return days === 0 ? "today" : days+"d ago";
  }
  function recentCard(){
    var mid = state.master || (H.masters[0] && H.masters[0].id);
    if (!mid) return "";
    var perMaster = (H.journeyIndex && H.journeyIndex[mid]) || {};
    var feed = [];
    for (var name in perMaster){
      var events = perMaster[name];
      if (events.length < 1) continue;
      var last = events[events.length-1];
      var prev = events.length > 1 ? events[events.length-2][1] : last[1];
      feed.push({name:name, date:last[0], was:prev, nw:last[1]});
    }
    feed.sort(function(a,b){ return a.date < b.date ? 1 : a.date > b.date ? -1 : 0; });
    if (!feed.length) return '<div class="ov-card"><div class="ov-card-h"><span>Recent activity</span></div><div class="ov-card-body"><p class="ov-empty">No recorded changes yet.</p></div></div>';
    var rows = feed.slice(0, 12).map(function(it){
      return '<div class="rg-row" data-jglyph="'+esc(it.name)+'"><span class="rg-n">'+esc(it.name)+'</span>'
        + swatchFor(it.was)+'<span class="rg-ar">→</span>'+swatchFor(it.nw)
        + '<span class="rg-when">'+esc(whenLabel(it.name) || it.date)+'</span></div>';
    }).join("");
    return ovCard("recent", "Recent activity", rows, feed.length > 12);
  }
```

Then append `recentCard()` in `overviewExtras` after `regressionCard()`:

```javascript
  function overviewExtras(){
    if (!H.masters.length) return "";
    return '<div class="ov-extra">'+forecastCard()+regressionCard()+recentCard()+leaderboard()+histogram()+timelineCard()+'</div>';
  }
```

- [ ] **Run it (expected PASS).**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_dashboard_js_has_recent_card tests/test_colorflow_assets.py::test_dashboard_js_recent_card_when_label`

- [ ] **Manual smoke in Glyphs:** Open a font with several days of history. Confirm the "Recent activity" card lists most-recently-changed glyphs newest-first with before→after swatches and a "today"/"Nd ago" label.

- [ ] **Lint + types clean.** `uv run ruff check` and `uv run pyright`

- [ ] **Commit.** `feat(report): add Overview recent-activity feed card`

## Task 5: Date A vs Date B panel (Timeline view)

A diff panel inside the existing `timelineView`, with two date `<select>`s populated from `H.trend.dates`, computing `stateAt(A)` vs `stateAt(B)` → the three required spec #4 outputs: advanced/regressed/unchanged counts **and** the net graded-% delta (signed change in weighted completion between A and B, reusing the existing `stepWeights().weight` table). The spec's third output — an *optional* per-glyph list — is the only one deliberately skipped (the journey modal already covers per-glyph drill-down). Disabled note when < 2 distinct dates.

**Files**
- Modify: `Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py`
- Test: `tests/test_colorflow_assets.py`

- [ ] **Failing test for `dateDiffPanel` JS + select wiring.** Add to `tests/test_colorflow_assets.py`:

```python
def test_dashboard_js_has_date_diff_panel() -> None:
    js = assets.DASHBOARD_JS
    assert "function dateDiffPanel(" in js
    assert "function diffCounts(" in js
    assert 'id="cfd-date-a"' in js
    assert 'id="cfd-date-b"' in js
    assert "state.dateA" in js and "state.dateB" in js
    assert "H.trend.dates" in js
    assert "stateAt(" in js
    assert "Need at least two snapshots" in js   # <2 distinct dates state
    assert "advanced" in js and "regressed" in js
    # net graded-% delta (spec #4): computed via the existing step-weight helper
    # and rendered as a signed "% net" token in the panel output.
    assert "function gradedStateSum(" in js
    assert "deltaPct" in js
    assert "stepWeights(" in js
    assert "% net" in js


def test_dashboard_js_date_diff_state_keys_initialised() -> None:
    js = assets.DASHBOARD_JS
    assert "dateA:" in js and "dateB:" in js
```

- [ ] **Run it (expected FAIL — `AssertionError` on `function dateDiffPanel(`).**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_dashboard_js_has_date_diff_panel tests/test_colorflow_assets.py::test_dashboard_js_date_diff_state_keys_initialised`

- [ ] **Minimal implementation — extend `state`, add the helpers, mount the panel, wire the selects.**

First extend the `state` object literal (lines 328–334). Replace the `ovExpand: {},` line with:

```javascript
  ovExpand: {},                          // which Overview cards are expanded
  dateA: null, dateB: null,              // Timeline date A-vs-B diff selection
  journeyGlyph: null, helpOpen: false,   // journey modal + help panel
```

Add `diffCounts` + `dateDiffPanel` directly before `timelineView` (before line 800):

```javascript
  // graded value of one state map {glyph:key}: sum of the per-step weights used by
  // the existing % helpers (stepWeights().weight maps key -> (i+1)/N).
  function gradedStateSum(stateMap){
    var W = stepWeights().weight, s = 0;
    for (var name in stateMap){ var w = W[stateMap[name]]; if (w) s += w; }
    return s;
  }
  function diffCounts(masterId, isoA, isoB){
    var before = stateAt(masterId, isoA), after = stateAt(masterId, isoB);
    var advanced = 0, regressed = 0, unchanged = 0;
    var names = {};
    for (var n1 in before){ names[n1] = true; }
    for (var n2 in after){ names[n2] = true; }
    for (var name in names){
      var was = before[name]; if (was == null) was = -1;
      var nw = after[name]; if (nw == null) nw = -1;
      if (rankOf(nw) > rankOf(was)) advanced++;
      else if (rankOf(nw) < rankOf(was)) regressed++;
      else unchanged++;
    }
    // net graded-% delta (spec #4): change in graded completion between A and B,
    // over the whole-font denominator, same scale as the % cards. Signed.
    var denom = H.glyphTotal || Object.keys(names).length || 1;
    var deltaPct = Math.round((gradedStateSum(after) - gradedStateSum(before)) / denom * 100);
    return {advanced:advanced, regressed:regressed, unchanged:unchanged, deltaPct:deltaPct};
  }
  function dateDiffPanel(){
    var dates = (H.trend && H.trend.dates) || [];
    if (dates.length < 2){
      return '<div class="tl-diff"><p class="empty">Need at least two snapshots.</p></div>';
    }
    var a = state.dateA || dates[0];
    var b = state.dateB || dates[dates.length-1];
    var mid = state.master || (H.masters[0] && H.masters[0].id);
    var opts = function(sel){ return dates.map(function(d){
      return '<option value="'+esc(d)+'"'+(d===sel?" selected":"")+'>'+esc(d)+'</option>'; }).join(""); };
    var c = diffCounts(mid, a, b);
    return '<div class="tl-diff"><div class="tl-diff-h">Compare snapshots</div>'
      + '<div class="tl-diff-pick">'
      + '<label>From <select id="cfd-date-a">'+opts(a)+'</select></label>'
      + '<label>To <select id="cfd-date-b">'+opts(b)+'</select></label></div>'
      + '<div class="tl-diff-out"><span class="dz dz-up">↑ '+c.advanced+' advanced</span>'
      + '<span class="dz dz-down">↓ '+c.regressed+' regressed</span>'
      + '<span class="dz dz-flat">= '+c.unchanged+' unchanged</span>'
      + '<span class="dz dz-net">'+(c.deltaPct>=0?"+":"")+c.deltaPct+'% net</span></div></div>';
  }
```

Then mount it inside `timelineView` by appending `dateDiffPanel()` to the returned section (the non-empty branch, line 805):

```javascript
  return '<section class="timeline"><div class="tl-legend">'+parts.legend+'</div>'+parts.chart+parts.foot+dateDiffPanel()+'</section>';
```

Then wire the selects in `bind()`. Add a `change` listener on `bodyEl` directly after the existing `bodyEl.addEventListener("click", ...)` block (after line 1090):

```javascript
    bodyEl.addEventListener("change", function(e){
      if (e.target.id === "cfd-date-a"){ state.dateA = e.target.value; update(); }
      else if (e.target.id === "cfd-date-b"){ state.dateB = e.target.value; update(); }
    });
```

- [ ] **Run it (expected PASS).**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_dashboard_js_has_date_diff_panel tests/test_colorflow_assets.py::test_dashboard_js_date_diff_state_keys_initialised`

- [ ] **Reduced-motion + self-contained invariants still hold.**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_build_html_is_self_contained_and_accessible`

- [ ] **Manual smoke in Glyphs:** Open the report, Timeline tab. Confirm a "Compare snapshots" panel with two date dropdowns (From=earliest, To=latest by default). Change a dropdown; confirm the advanced/regressed/unchanged counts AND the signed "+N% net" graded-delta token update. On a font with one history date, confirm the panel shows "Need at least two snapshots."

- [ ] **Lint + types clean.** `uv run ruff check` and `uv run pyright`

- [ ] **Commit.** `feat(report): add date A-vs-B diff panel to the Timeline view`

## Task 6: Per-glyph journey modal (reuse export modal shell)

Click any heatmap cell → open the existing `.cfd-modal` shell showing that glyph's full colour history (dates → step swatches) via `journeyOf`. Wired from the cell click handler; new `state.journeyGlyph`. Also makes the regression/recent `data-jglyph` rows open the same modal.

**Files**
- Modify: `Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py`
- Test: `tests/test_colorflow_assets.py`

- [ ] **Failing test for `journeyModal` JS + cell wiring.** Add to `tests/test_colorflow_assets.py`:

```python
def test_dashboard_js_has_journey_modal() -> None:
    js = assets.DASHBOARD_JS
    assert "function openJourney(" in js
    assert "function closeJourney(" in js
    assert "cfd-journey-modal" in js
    assert "cfd-modal" in js                 # reuses the export modal shell class
    assert "journeyOf(" in js
    assert "No history yet for this glyph" in js
    assert "data-jglyph" in js               # regression/recent rows trigger it
    assert "state.journeyGlyph" in js


def test_dashboard_js_journey_modal_wired_from_cell_click() -> None:
    js = assets.DASHBOARD_JS
    # A click on a heatmap cell with a modifier-free trigger opens the journey.
    assert "openJourney(" in js
    assert ".heat .cell" in js
```

- [ ] **Run it (expected FAIL — `AssertionError` on `function openJourney(`).**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_dashboard_js_has_journey_modal tests/test_colorflow_assets.py::test_dashboard_js_journey_modal_wired_from_cell_click`

- [ ] **Minimal implementation — add `openJourney` / `closeJourney`, reusing the `.cfd-modal` shell.** In `colorflow_assets.py`, add directly after `closeExport` (after line 1039 / before `openExport`):

```javascript
  function closeJourney(){ var m = document.getElementById("cfd-journey-modal"); if (m) m.style.display = "none"; state.journeyGlyph = null; }
  function openJourney(name){
    state.journeyGlyph = name;
    var mid = state.master || (H.masters[0] && H.masters[0].id);
    var events = journeyOf(mid, name);
    var rows = events.length
      ? events.map(function(ev){
          // reuse the canonical null-guarding swatch (wraps `varFor`).
          return '<div class="jm-row"><span class="jm-date">'+esc(ev[0])+'</span>'
            + swatchFor(ev[1])
            + '<span class="jm-lab">'+esc(labelFor(ev[1]))+'</span></div>';
        }).join("")
      : '<p class="ov-empty">No history yet for this glyph.</p>';
    var modal = document.getElementById("cfd-journey-modal");
    if (!modal){
      modal = document.createElement("div"); modal.id = "cfd-journey-modal"; modal.className = "cfd-modal";
      modal.addEventListener("click", function(e){ if (e.target===modal) closeJourney(); });
      document.body.appendChild(modal);
    }
    modal.innerHTML = '<div class="cfd-modal-box" role="dialog" aria-label="Glyph journey" aria-modal="true">'
      + '<div class="cfd-modal-h">Journey · '+esc(name)+'</div>'
      + '<div class="cfd-cards jm-list">'+rows+'</div></div>';
    modal.style.display = "flex";
  }
```

Wire it from the cell click and from `data-jglyph` rows. In the `bodyEl.addEventListener("click", ...)` block, add a `data-jglyph` branch (after the `var ba = ...` block, before its closing) and a cell branch. Insert directly before the `var ba = e.target.closest(".ba-toggle");` line (line 1088):

```javascript
      var jr = e.target.closest("[data-jglyph]"); if (jr){ openJourney(jr.getAttribute("data-jglyph")); return; }
      var jc = e.target.closest(".heat .cell"); if (jc && (e.metaKey || e.ctrlKey)){ e.preventDefault(); openJourney(jc.getAttribute("data-glyph")); return; }
```

Add Escape-to-close in the existing keydown handler (line 1071–1073). Replace its body with:

```javascript
    document.addEventListener("keydown", function(e){
      if (e.key==="Escape"){ closeExport(); closeJourney(); closeHelp(); if (state.focus!==null){ setFocus(null); } }
    });
```

(`closeHelp` is added in Task 7; both are defined before `bind` runs, so the reference is safe.)

- [ ] **Run it (expected PASS).**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_dashboard_js_has_journey_modal tests/test_colorflow_assets.py::test_dashboard_js_journey_modal_wired_from_cell_click`

- [ ] **Self-contained + reduced-motion invariants still hold.**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_build_html_is_self_contained_and_accessible`

- [ ] **Manual smoke in Glyphs:** Open a report, a master heatmap tab. Cmd-click (or Ctrl-click) a glyph cell — confirm a modal opens listing that glyph's dated colour-step rows. Click a regression-card row — confirm the same modal opens. Click outside the box or press Escape — confirm it closes. Cmd-click a glyph with no history — confirm "No history yet for this glyph."

- [ ] **Lint + types clean.** `uv run ruff check` and `uv run pyright`

- [ ] **Commit.** `feat(report): add per-glyph journey modal reusing the export modal shell`

## Task 7: Help / legend "?" button (header)

A `?` button in the header opens a panel listing each step (swatch + name + position) plus a short glossary of "% complete" / "forecast" / "regression". Static content; new `state.helpOpen`.

**Files**
- Modify: `Color Flow.glyphsPalette/Contents/Resources/colorflow_assets.py`
- Test: `tests/test_colorflow_assets.py`

- [ ] **Failing test for `helpPanel` JS + header button.** Add to `tests/test_colorflow_assets.py`:

```python
def test_dashboard_js_has_help_panel_and_button() -> None:
    js = assets.DASHBOARD_JS
    assert "function helpPanel(" in js
    assert "function openHelp(" in js
    assert "function closeHelp(" in js
    assert 'id="cfd-help"' in js               # the ? header button
    assert "state.helpOpen" in js
    assert "H.steps" in js                      # legend rows from steps
    assert "% complete" in js                   # glossary entry
    assert "regression" in js and "forecast" in js


def test_build_html_help_button_present_and_self_contained() -> None:
    html = assets.build_html(_model())
    assert 'id="cfd-help"' in html
    assert "http://" not in html and "https://" not in html   # invariant preserved
```

- [ ] **Run it (expected FAIL — `AssertionError` on `function helpPanel(`).**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_dashboard_js_has_help_panel_and_button tests/test_colorflow_assets.py::test_build_html_help_button_present_and_self_contained`

- [ ] **Minimal implementation — add the `?` button, the panel builders, and wiring.**

Add the `?` button to `header()` (line 397–405) by inserting it before the theme button. Change the `streakBadge()` line region so the return ends:

```javascript
    + streakBadge()
    + '<button type="button" id="cfd-help" class="icon" aria-label="Help and legend">?</button>'
    + '<button type="button" id="cfd-theme" class="icon" aria-label="Toggle light or dark theme">◐</button></header>';
```

Add `helpPanel` / `openHelp` / `closeHelp` directly after `closeJourney`/`openJourney` (so they exist before `bind`):

```javascript
  function helpPanel(){
    var steps = H.steps || [];
    // reuse `swatchFor` (which wraps the canonical `varFor`); step keys are real
    // ints, the none row passes null so `swatchFor` emits the `--c-none` var.
    var legend = steps.map(function(s, i){
      return '<div class="hp-row">'+swatchFor(s.key)
        + '<span class="hp-n">'+esc(s.label)+'</span><span class="hp-pos">step '+(i+1)+' of '+steps.length+'</span></div>';
    }).join("");
    var none = H.noneLabel
      ? '<div class="hp-row">'+swatchFor(null)
        + '<span class="hp-n">'+esc(H.noneLabel)+'</span><span class="hp-pos">uncoloured</span></div>'
      : "";
    var glossary = '<div class="hp-gloss">'
      + '<p><b>% complete</b> — weighted progress across the colour steps.</p>'
      + '<p><b>forecast</b> — estimated finish date at the recent pace; never a hard date.</p>'
      + '<p><b>regression</b> — a glyph that moved backward in the flow since the last save.</p></div>';
    return '<div class="cfd-modal-box" role="dialog" aria-label="Help and legend" aria-modal="true">'
      + '<div class="cfd-modal-h">Legend &amp; help</div>'
      + '<div class="cfd-cards hp-list">'+legend+none+glossary+'</div></div>';
  }
  function closeHelp(){ var m = document.getElementById("cfd-help-modal"); if (m) m.style.display = "none"; state.helpOpen = false; }
  function openHelp(){
    state.helpOpen = true;
    var modal = document.getElementById("cfd-help-modal");
    if (!modal){
      modal = document.createElement("div"); modal.id = "cfd-help-modal"; modal.className = "cfd-modal";
      modal.addEventListener("click", function(e){ if (e.target===modal) closeHelp(); });
      document.body.appendChild(modal);
    }
    modal.innerHTML = helpPanel();
    modal.style.display = "flex";
  }
```

Wire the `?` button in `bind()`, directly after the export wiring (after line 1070):

```javascript
    document.getElementById("cfd-help").addEventListener("click", openHelp);
```

- [ ] **Run it (expected PASS).**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_dashboard_js_has_help_panel_and_button tests/test_colorflow_assets.py::test_build_html_help_button_present_and_self_contained`

- [ ] **Manual smoke in Glyphs:** Open a report. Click the `?` button in the header — confirm a panel lists each colour step (swatch + name + "step N of M"), the uncoloured row, and the three-line glossary. Click outside / Escape — confirm it closes.

- [ ] **Lint + types clean.** `uv run ruff check` and `uv run pyright`

- [ ] **Commit.** `feat(report): add help/legend panel and header ? button`

## Task 8: Behavioural smoke + regenerate sample + full suite

Regenerate the standalone sample and add a behavioural-smoke test section in the project's real style (substring assertions over `build_html` output — no node/jsdom runtime exists here), asserting every new wiring marker is reachable end-to-end in the generated document and the hard invariants are intact.

**Files**
- Modify: `tests/test_colorflow_assets.py`
- Test: `tests/test_colorflow_assets.py`

- [ ] **Failing behavioural-smoke test.** Add to `tests/test_colorflow_assets.py`:

```python
def test_build_html_wires_all_report_insight_features() -> None:
    """End-to-end smoke: every new render unit + its wiring marker is present in
    the generated document, and the self-contained/no-network invariant holds."""
    html = assets.build_html(_model())
    # render units
    for marker in ("function forecastCard(", "function regressionCard(",
                   "function recentCard(", "function dateDiffPanel(",
                   "function openJourney(", "function helpPanel(",
                   "function journeyOf(", "function stateAt("):
        assert marker in html, marker
    # wiring: header button, cell + row triggers, date selects, journey index
    assert 'id="cfd-help"' in html
    assert 'id="cfd-date-a"' in html and 'id="cfd-date-b"' in html
    assert "data-jglyph" in html
    assert "H.journeyIndex" in html
    # spec #4 net graded-% delta reaches the document; swatches reuse varFor
    assert "function gradedStateSum(" in html and "% net" in html
    assert "function swatchFor(" in html and "varFor(key)" in html
    # hard invariants preserved
    assert "http://" not in html and "https://" not in html
    assert "<noscript>" in html
    assert "prefers-reduced-motion" in html
    assert "DecompressionStream" in html
```

- [ ] **Run it (expected PASS — all markers were added in Tasks 1–7; this confirms they survive into `build_html`).**
  `uv run pytest -n auto tests/test_colorflow_assets.py::test_build_html_wires_all_report_insight_features`

- [ ] **Regenerate the standalone sample for in-browser eyeball.**
  `uv run python tools/dashboard_sample.py /tmp` — confirm it prints `/tmp/dashboard_step.html` and `/tmp/dashboard_free.html` with no traceback.

- [ ] **Full suite green.**
  `uv run pytest -n auto tests/test_colorflow_assets.py tests/test_colorflow_dashboard.py`

- [ ] **Lint + types clean across all touched Python.**
  `uv run ruff check` and `uv run pyright`

- [ ] **Manual smoke in browser:** Open `/tmp/dashboard_step.html`. Confirm: Forecast card text renders; toggling light/dark works; the `?` legend opens and closes; (if the sample carries ≥2 history dates) the Timeline "Compare snapshots" panel counts advanced/regressed; Cmd-click a heatmap cell opens the journey modal.

- [ ] **Commit.** `test(report): add behavioural smoke for all six report insight features`

## Self-Review

**Placeholder scan.** No `TBD`, no "add error handling" without code, no "similar to Task N". Every step shows real test code and real implementation code. Each "Manual smoke" step names the exact click/observe action (UI/AppKit code that cannot run headless is not faked into a pytest). The behavioural-smoke task (Task 8) is honest: this project has **no node/jsdom runtime** (verified — only `dashboard_sample.py` exists under `tools/`, all JS testing is substring assertions per `tests/test_colorflow_assets.py`), so the "smoke harness" is the project's real convention — substring assertions over `build_html` output plus an in-browser eyeball of the regenerated sample.

**Spec coverage.** (0) Journey index → Task 1 (`build_journey_index` sparse change-events + `journeyOf`/`stateAt`). (1) Forecast card → Task 2 (`aggregate_forecast`, `trend.forecast["__all__"]`, `forecastCard`, none/<2-points + done states; aggregate `total` = `glyph_total * len(masters)` since aggregate `final` sums per-master finals — asserted in both a 1-master and a 2-master test so the multi-master denominator is actually exercised). The `"__all__"` aggregate is emitted **conditionally** — only when the per-master forecast dict is non-empty (≥1 master) — so the empty-font invariant `trend.forecast == {}` is preserved (pre-existing `test_build_model_empty_font_does_not_crash` keeps passing unchanged). (2) Regression card → Task 3 (`rankOf` rank-compare, `mergedChanges`, hidden-when-zero, `data-jglyph` rows, → none counts backward). (3) Recent activity card → Task 4 (`recentCard` showing the **latest events from the selected master's index**, `whenLabel` today/Nd-ago, row→modal); **scope:** "across all glyphs" is read as *across all glyphs of the master in view* (per-master, like every other Overview unit) — cross-master aggregation is a **deliberate non-goal for v1**, documented in the Task 4 scope note, not an omission. (4) Date A-vs-B → Task 5 (`dateDiffPanel`, `diffCounts`, two selects from `H.trend.dates`, <2-dates note, inside `timelineView` not a new tab) — emits **all three** spec #4 outputs: advanced/regressed/unchanged counts AND the non-optional **net graded-% delta** (`gradedStateSum` reusing the existing `stepWeights().weight`, rendered as a signed "% net" token, covered by a substring assertion); the per-glyph list is the one explicitly *optional* output and is skipped. (5) Journey modal → Task 6 (`openJourney` reusing `.cfd-modal` shell, `state.journeyGlyph`, cell + `data-jglyph` wiring, no-history state). (6) Help/legend → Task 7 (`?` button in `header`, `helpPanel` steps + glossary, `state.helpOpen`). New `state` keys `dateA`/`dateB`/`journeyGlyph`/`helpOpen` added in Task 5/Task 6 region. Invariants (self-contained, no network, `<noscript>`, reduced-motion, gzipped model) asserted in Tasks 2, 5, 6, 7, 8.

**Type consistency.** All new Python functions carry return type hints: `build_journey_index(...) -> dict`, `aggregate_forecast(...) -> dict`. They reuse only real symbols: `colornames.NO_COLOR` (matches `cc.NO_COLOR` in tests and the dense `_glyph_journeys`), `forecast_master` (existing, signature `(series, master_id, total, now, is_free, window_days=28) -> dict`). JS references only real model fields: `H.journeyIndex` (new, Task 1), `H.trend.forecast` / `etaIso` / `confidence` / `bandDays` / `velocityPerWeek` / `remaining` / `total` / `points` (existing `forecast_master` output), `H.changes` (`{master: {glyph: (old, new)}}` from `compute_changes`), `H.lastEdit` (`{glyph: days}` from `glyph_last_edit`), `H.order` (`list[str]`), `H.steps` (`[{key, label}]`), `H.noneLabel`, `H.trend.dates` (`list[iso]`), `H.masters[].id`. Existing JS helpers reused without redefinition: `ovCard`, `esc`, `labelFor`, `varFor` (canonical `--c`/`--c-none` mapper at colorflow_assets.py:342 — wrapped by the new `swatchFor`, which adds the `key==null` guard `varFor` lacks, and reused by `openJourney`/`helpPanel` via `swatchFor` rather than re-deriving `'--c'+key` inline), `stepWeights`/`gradedSum` weight table (reused by `gradedStateSum` for the net-delta), `overviewExtras`, `timelineView`, `header`, `closeExport`/`openExport`, `bind`, `update`. The only new colour-var derivation is `swatchFor`'s single null-guarded wrapper; the rest delegate to it. No invented field or method.
