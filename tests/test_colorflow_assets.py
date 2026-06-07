"""Tests for the inline-asset / HTML-shell layer of the Color Font Dashboard."""

from __future__ import annotations

import base64
import gzip
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


def test_build_html_is_self_contained_and_accessible() -> None:
    html = assets.build_html(_model())
    assert html.startswith("<!DOCTYPE html>")
    assert 'lang="en"' in html
    assert '<style>' in html and assets.DASHBOARD_CSS[:20].strip() in html
    assert 'id="cfd-model-gz"' in html         # gzipped model embedded
    assert "JSON.parse" in html                # app script inlined (parses the decompressed model)
    assert "DecompressionStream" in html       # client gunzips the model
    assert "<noscript>" in html
    assert ":root{" in html                     # dark default tokens
    assert "html[data-theme=light]" in html     # light theme
    assert "http://" not in html and "https://" not in html  # no network


def test_build_html_title_from_model_is_escaped() -> None:
    model = _model()
    model["family"] = "a<b>"
    html = assets.build_html(model)
    assert "a&lt;b&gt;" in html
    assert "<title>CF - a&lt;b&gt;</title>" in html


def test_embed_model_gzips_and_neutralises_script_breakout() -> None:
    model = _model()
    model["glyphNames"] = ["</script><b>x", "A"]  # hostile glyph name
    block = assets.embed_model(model)
    assert 'id="cfd-model-gz"' in block
    assert "</script><b>" not in block          # base64 cannot reproduce the breakout
    # the base64 payload between the tags gunzips back to the original model
    payload = block.split(">", 1)[1].rsplit("<", 1)[0]
    assert json.loads(gzip.decompress(base64.b64decode(payload))) == model


def test_color_overrides_injected_after_base_css() -> None:
    model = _model()
    model["colors"] = {"0": "#abcdef", "11": "#123456"}
    html = assets.build_html(model)
    assert "--c0:#abcdef;" in html
    assert "--c11:#123456;" in html
    # the override must come AFTER the base stylesheet so it wins
    assert html.index("--c0:#abcdef") > html.index(assets.DASHBOARD_CSS[:20].strip())


def test_color_overrides_absent_without_colors() -> None:
    assert assets._color_overrides({}) == ""
    assert assets._color_overrides({"colors": {}}) == ""


def test_favicon_link_embeds_model_data_uri() -> None:
    uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAA="
    link = assets._favicon_link({"favicon": uri})
    assert link == f'<link rel="icon" href="{uri}">'


def test_favicon_link_empty_without_favicon() -> None:
    assert assets._favicon_link({}) == ""
    assert assets._favicon_link({"favicon": ""}) == ""


def test_favicon_link_accepts_well_formed_data_image_uris() -> None:
    # base64 PNG and percent-encoded SVG are both legitimate self-contained icons
    png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAA="
    svg = "data:image/svg+xml,%3Csvg%20xmlns%3D%22...%22%3E%3C%2Fsvg%3E"
    ico = "data:image/x-icon;base64,AAABAAEAEBA="
    for uri in (png, svg, ico):
        assert assets._favicon_link({"favicon": uri}) == f'<link rel="icon" href="{uri}">'


def test_favicon_link_rejects_attribute_breakout() -> None:
    # A hostile favicon value must not be able to escape the href="..." attribute
    # context. Each of these contains a character that would close the attribute or
    # add new ones; _favicon_link must emit nothing rather than the raw value.
    hostile = [
        'data:image/png;base64," onload="alert(1)',     # double-quote closes href
        'data:image/svg+xml,"><script>alert(1)</script>',  # quote + tag breakout
        "data:image/png;base64,AA onload=alert(1)",      # bare space lets attrs follow
        "data:text/html,<script>alert(1)</script>",       # not an image subtype
        "javascript:alert(1)",                            # not a data: URI at all
        "https://evil.example/x.png",                     # remote URL (breaks offline)
        "data:image/png;base64,AA&x=1",                   # '&' starts an entity
        "data:image/png;base64,",                         # empty payload
        "data:image/png;base64,AA\n onload=x",            # newline / control char
    ]
    for uri in hostile:
        link = assets._favicon_link({"favicon": uri})
        assert link == "", uri
        # and the breakout never reaches a generated page either
        html = assets.build_html({**_model(), "favicon": uri})
        assert "<script>alert" not in html
        assert 'onload="alert' not in html and "onload=alert" not in html
        assert 'href="' + uri not in html


def test_favicon_link_rejects_non_string_favicon() -> None:
    assert assets._favicon_link({"favicon": 123}) == ""
    assert assets._favicon_link({"favicon": ["data:image/png;base64,AA"]}) == ""


def test_build_html_embeds_favicon_and_glyph_ink_token() -> None:
    model = _model()
    model["favicon"] = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAA="
    html = assets.build_html(model)
    assert 'rel="icon"' in html                 # favicon link present in <head>
    assert "--glyph-ink:" in html               # constant ink for glyph fills
    assert ".tabsvg" in html                    # master-tab Aa preview styling


def test_dashboard_css_has_fill_on_load_and_focus_styles() -> None:
    css = assets.DASHBOARD_CSS
    assert "@keyframes segGrow" in css                          # bars fill on load
    assert ".seg.intro{" in css                                 # whole bar grows as one block
    assert "animation-delay:calc(var(--i" not in css            # NOT per-segment staggered
    assert ".seg>span.off" in css                               # dim the OTHER segments
    assert "box-shadow:inset 0 0 0 2px var(--text)" not in css  # white border removed
    assert ".cell.dim" not in css                               # glyph dim removed
    assert ".heat.fading" in css                                # crossfade recompose


def test_build_html_has_tower_master_navigator() -> None:
    html = assets.build_html(_model())
    assert 'id="cfd-tower"' in html              # persistent sidebar nav container
    assert 'id="cfd-tower-cv"' in html           # the tower canvas
    assert "function initTower(" in html         # tower bootstrap
    assert "#cfd-main{display:flex" in html      # sidebar + body layout
    assert "bind(); update(); initTower();" in html
    assert "Math.min(16, H.masters.length)" in html   # windowed: up to 16 discs shown
    assert '"wheel"' in html                          # scroll reveals the rest


def test_dashboard_js_tower_is_hidpi_aware() -> None:
    js = assets.DASHBOARD_JS
    assert "devicePixelRatio" in js                       # supersample by the display's DPR
    assert "Math.min(window.devicePixelRatio || 1, 3)" in js  # capped at 3x
    assert "setTransform(dpr,0,0,dpr,0,0)" in js          # draw in CSS units at physical resolution
    assert "cv.width=Math.round(availW*dpr)" in js        # #cfd-tower-cv backing store scaled to physical px
    assert "cv.height=Math.round(availH*dpr)" in js
    assert 'cv.style.width=availW+"px"' in js             # CSS size stays logical (hit-test unaffected)
    assert "buf.width=Math.round(W*dpr)" in js            # composite buffer scaled too


def test_build_html_has_script_coverage_grid() -> None:
    html = assets.build_html(_model())
    assert "function scriptGrid(" in html              # grid builder
    assert "function paintBlend(" in html              # label-colour blend painter
    assert "function paintScriptCards(" in html        # post-render canvas paint
    assert "paintScriptCards();" in html               # called from update()
    assert ".sgrid{" in html and 'class="scard"' in html
    assert 'state.coverGroup==="byScript"' in html and "scriptGrid()" in html  # Script tab -> grid
    assert "function scriptRows(" in html              # per-master / aggregated rows


def test_dashboard_js_has_expandable_overview_cards_and_timeline_card() -> None:
    js = assets.DASHBOARD_JS
    assert "function ovCard(" in js                       # shared expandable card
    assert "function timelineCard(" in js                 # timeline shown in the Overview
    assert "function trendParts(" in js                   # chart shared by view + card
    assert "data-ovexpand" in js                          # header toggles expansion
    assert "ovExpand" in js                               # per-card expanded state
    assert "leaderboard\", \"Furthest along\"" in js or 'ovCard("leaderboard"' in js


def test_dashboard_js_uses_graded_step_progress() -> None:
    js = assets.DASHBOARD_JS
    assert "function stepWeights(" in js                 # palette-order step ranking
    assert "function gradedMasterPct(" in js
    assert "function gradedOverallPct(" in js
    assert "(i+1)/N" in js                                # first step = 1/N, final = 100%
    assert "% complete" in js                             # graded % shown in the headline
    assert "function masterPct(m){ return gradedMasterPct(m); }" in js  # leaderboard/histogram use it


def test_dashboard_js_routes_focus_through_setfocus() -> None:
    js = assets.DASHBOARD_JS
    assert "function setFocus(" in js
    assert "__cfdNoAnim" in js
    assert "items.filter(matchesFocus)" in js                   # recompose to selected colour
    assert "barsAnim = (state.master !== barMaster)" in js       # one-shot fill flag


def test_dashboard_js_has_journey_helpers() -> None:
    js = assets.DASHBOARD_JS
    assert "function journeyOf(" in js
    assert "function stateAt(" in js
    # journeyOf reads the sparse index; stateAt carries the last event forward.
    assert "H.journeyIndex" in js
    assert "<=" in js  # stateAt: last event at or before the date


def test_dashboard_js_has_calendar_x_axis() -> None:
    """#7: trendParts draws real calendar date ticks, zebra ISO week bands and a
    dashed 'today' rule, instead of an unlabelled day-offset axis."""
    js = assets.DASHBOARD_JS
    # short "D Mon" date->label helper for the X ticks
    assert "function dateLabel(" in js
    # the today rule reads the real today date from the model
    assert "H.trend.today" in js
    # the three new visual layers each get a class
    assert "tl-weekband" in js
    assert "tl-xtick" in js
    assert "tl-today" in js
    # the today rule keeps the existing grid/polyline/dots layers (still present)
    assert "tl-grid" in js
    assert "tl-dot" in js


def test_dashboard_css_styles_calendar_axis_classes() -> None:
    """#7: the week bands, x-axis tick labels and today rule each carry a
    theme-safe CSS rule built from --text / --accent vars (no hard-coded colour)."""
    css = assets.DASHBOARD_CSS
    for selector in (".tl-weekband", ".tl-xtick", ".tl-today", ".tl-today-pill"):
        assert selector in css, selector
    # week bands are a faint --text tint (theme-safe), not a baked colour
    band_rule = css.split(".tl-weekband")[1].split("}")[0]
    assert "var(--text)" in band_rule
    # today rule uses the accent var and is dashed
    today_rule = css.split(".tl-today{")[1].split("}")[0]
    assert "var(--accent)" in today_rule
    assert "dasharray" in today_rule


def test_dashboard_js_fills_hero_area_under_selected_master() -> None:
    """#10: for the selected master only, trendParts draws a soft gradient area
    fill under its line — a <linearGradient> (unique id from the master hue) from
    the hue at ~22% alpha down to transparent, plus a filled .tl-area path that
    closes down to the baseline Y(0). The tl-dot circles stay at exact values."""
    js = assets.DASHBOARD_JS
    # unique gradient id + the gradient element itself, with two stops
    assert "tl-area-grad" in js
    assert "<linearGradient" in js
    assert "<stop" in js
    # the filled area carries the .tl-area class and references the gradient
    assert "tl-area" in js
    assert "url(#" in js
    # the fill closes to the baseline Y(0) and only the selected master gets it
    assert "Y(0)" in js
    # dots remain rendered (exact values stay honest)
    assert "tl-dot" in js


def test_dashboard_css_styles_hero_area_class() -> None:
    """#10: the hero area fill carries a theme-safe .tl-area rule (no stroke,
    so the polyline still draws the crisp line on top)."""
    css = assets.DASHBOARD_CSS
    assert ".tl-area" in css
    area_rule = css.split(".tl-area{")[1].split("}")[0]
    assert "stroke:none" in area_rule


def test_dashboard_js_has_snapping_crosshair() -> None:
    """#6: trendParts adds a transparent overlay rect capturing pointer X plus a
    hidden vertical guide + nearest-snapshot marker; a dedicated crosshair handler
    snaps to the nearest discrete snapshot X (no interpolation) and shows a floating
    readout. The chart is focusable so Left/Right arrows step snapshots."""
    js = assets.DASHBOARD_JS
    # the named crosshair handler that wires pointer + keyboard interaction
    assert "function crosshairMove(" in js
    # transparent overlay rect that captures pointer X over the plot
    assert "tl-crossarea" in js
    # the 1px vertical guide + the nearest-snapshot marker dot
    assert "tl-cross" in js
    assert "tl-cross-mark" in js
    # snapping picks the nearest discrete snapshot, never interpolates
    assert "nearest" in js
    # the readout reuses the existing cfd-tip floating pattern
    assert "cfd-tip" in js
    # the chart is focusable and steps snapshots on Left/Right
    assert "tabindex" in js
    assert "ArrowLeft" in js and "ArrowRight" in js
    # reduced-motion: guide updates instantly (no transition) via the shared gate
    assert "tl-cross" in assets.DASHBOARD_CSS


def test_dashboard_css_styles_crosshair_class() -> None:
    """#6: the crosshair guide is a 1px --muted-2 vertical rule; the overlay rect
    is transparent so it only captures the pointer."""
    css = assets.DASHBOARD_CSS
    assert ".tl-cross" in css
    cross_rule = css.split(".tl-cross{")[1].split("}")[0]
    assert "var(--muted-2)" in cross_rule
    # the capture overlay is transparent and never paints
    assert ".tl-crossarea" in css


def test_dashboard_js_has_brush_to_compare() -> None:
    """#8: a pointerdown+drag across the chart overlay paints a translucent band
    between two snapped snapshot dates and, on release, drives the A/B compare by
    setting state.dateA / state.dateB. The handler derives an inverse X->date from
    the forward X() scale, keeps the <select> a11y fallback synced, and exposes two
    draggable handles nudged by the arrow keys."""
    js = assets.DASHBOARD_JS
    # the named brush handler that wires the drag interaction
    assert "function brushMove(" in js
    # the translucent band + the two draggable handles draw as .tl-brush elements
    assert "tl-brush" in js
    # the band snaps to discrete snapshots (same data as the crosshair) and inverts
    # the forward X scale to recover the date under the pointer
    assert "data-snaps" in js
    # on release the brush sets BOTH compare endpoints, then re-renders
    assert "state.dateA" in js and "state.dateB" in js
    # the existing <select> a11y fallback stays the source of truth markup
    assert 'id="cfd-date-a"' in js and 'id="cfd-date-b"' in js
    # pointer drag + keyboard nudge on a focused handle
    assert "pointerdown" in js
    assert "ArrowLeft" in js and "ArrowRight" in js
    # reduced-motion: numbers settle on release (no live anim) via the shared gate
    assert "__cfdNoAnim" in js or "prefers-reduced-motion" in js
    # the brush band carries a CSS rule
    assert ".tl-brush" in assets.DASHBOARD_CSS


def test_dashboard_css_styles_brush_class() -> None:
    """#8: the brush band is a translucent --accent fill so it reads as a range
    selection over the plot without hiding the lines underneath."""
    css = assets.DASHBOARD_CSS
    assert ".tl-brush" in css
    brush_rule = css.split(".tl-brush{")[1].split("}")[0]
    assert "var(--accent)" in brush_rule


def test_dashboard_css_hides_brush_handles_until_painted() -> None:
    """#8: the two draggable handles must stay hidden until brushPaint() sets
    display:block — same as the band. Without display:none the handle rects render
    stacked at x=0 in the left axis gutter on the very first chart paint, before any
    brush interaction."""
    css = assets.DASHBOARD_CSS
    assert ".tl-brush-h{" in css
    handle_rule = css.split(".tl-brush-h{")[1].split("}")[0]
    assert "display:none" in handle_rule


def test_dashboard_js_has_streamgraph_builder() -> None:
    """#5: a Line/Flow toggle (default Line) swaps the per-master line chart for a
    stacked-area colour streamgraph. The streamgraph builder tallies per-step counts
    per date by calling stateAt over H.trend.dates, stacks bands bottom->top by
    H.order, fills each band with its step var, and hatches the uncoloured bucket on
    top. Reuses the calendar X axis (#7) and a snapping crosshair read-out."""
    js = assets.DASHBOARD_JS
    # the named streamgraph builder
    assert "function streamParts(" in js
    # the Line/Flow toggle button drives state.tlMode (default "line"); aria-pressed
    assert "tlMode" in js
    assert 'state.tlMode === "flow"' in js or "state.tlMode==='flow'" in js or 'state.tlMode==="flow"' in js
    assert "tl-mode" in js                                  # the toggle control class
    assert "Line" in js and "Flow" in js                   # the two toggle labels
    assert "aria-pressed" in js
    # per-step tally per date via stateAt over the trend dates
    assert "stateAt(" in js
    assert "H.trend.dates" in js or "H.trend && H.trend.dates" in js
    # bands stack by palette order and fill with the per-step var
    assert "H.order" in js
    assert "varFor(" in js
    # the uncoloured ("none") bucket is hatched on top via an SVG pattern
    assert "stream-hatch" in js or "tl-stream-none" in js
    # reuses the calendar X axis day-offset math from #7
    assert "dayOff(" in js
    # reduced-motion: no draw-in animation via the shared gate
    assert "__cfdNoAnim" in js or "prefers-reduced-motion" in js


def test_dashboard_js_streamgraph_state_and_toggle_wired() -> None:
    """#5: state.tlMode is initialised to 'line' and a Line/Flow toggle click flips
    it then re-renders. timelineView routes to the streamgraph when state.tlMode is
    'flow'."""
    js = assets.DASHBOARD_JS
    assert "tlMode:" in js                                 # initialised in the state object
    assert 'state.tlMode = ' in js or "state.tlMode=" in js  # the toggle mutates it
    # the timeline view picks the builder by mode
    assert "streamParts(" in js


def test_dashboard_css_styles_streamgraph_classes() -> None:
    """#5: the Line/Flow toggle and the stacked-area band classes each carry a
    theme-safe rule; the toggle marks the active mode with aria-pressed."""
    css = assets.DASHBOARD_CSS
    assert ".tl-mode" in css
    assert ".tl-band" in css
    # the active toggle button is highlighted with the accent var (theme-safe)
    active_rule = css.split(".tl-mode-btn[aria-pressed=true]")[1].split("}")[0]
    assert "var(--accent)" in active_rule


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


def test_dashboard_js_regression_and_recent_are_per_master_only() -> None:
    js = assets.DASHBOARD_JS
    # The global Overview extras must NOT call the per-master change feeds.
    extras = js.split("function overviewExtras(")[1].split("}")[0]
    assert "regressionCard(" not in extras
    assert "recentCard(" not in extras
    # They live in the per-master panel instead, scoped to state.master.
    assert "function masterExtras(" in js
    master_extras = js.split("function masterExtras(")[1].split("}")[0]
    assert "regressionCard()" in master_extras and "recentCard()" in master_extras
    assert "masterExtras()" in js.split("function tabsView(")[1].split("}")[0]


def test_dashboard_js_regression_card_hidden_when_zero() -> None:
    js = assets.DASHBOARD_JS
    # The builder returns "" when no regressions are found.
    assert 'if (!rows.length) return "";' in js


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


def test_dashboard_js_has_cross_master_card() -> None:
    js = assets.DASHBOARD_JS
    assert "function crossMasterCard(" in js
    assert "H.crossMaster" in js
    # headline + progress bar, the identical/differ/byStep lines
    assert "done everywhere" in js
    assert "identical in all masters" in js
    assert "differ between masters" in js
    assert "by step:" in js
    assert "(single master)" in js          # masterCount < 2 note
    # the differ list rows open the existing per-glyph journey modal
    assert "data-jglyph" in js
    assert "cm.differGlyphs" in js
    # byStep swatches reuse the shared swatchFor helper (parseInt -> int key)
    assert "swatchFor(key)" in js
    # wired into the global Overview where forecastCard used to lead
    extras = js.split("function overviewExtras(")[1].split("}")[0]
    assert "crossMasterCard()" in extras


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


def test_dashboard_js_has_week_digest_card() -> None:
    """#14: a "This week" digest card tops the Timeline tab. The builder snaps a
    week-ago date to the real H.trend.dates entry nearest 7 days before the latest
    snapshot, runs diffCounts(master, weekAgo, today) for the big signed net % +
    advanced/regressed micro-stats, and a single trend arrow comparing this week's
    net to the prior 7-day window's net (a second diffCounts). Falls back to "since
    you started" on <7 days of history; rolls up across all masters when none is
    selected."""
    js = assets.DASHBOARD_JS
    # the named digest builder, wired into the timeline view above the chart
    assert "function weekDigest(" in js
    timeline = js.split("function timelineView(")[1].split("function ")[0]
    assert "weekDigest()" in timeline
    # the digest container class
    assert "tl-digest" in js
    # the honest "This week" headline + the <7-day fallback label
    assert "This week" in js
    assert "since you started" in js
    # snaps a real date ~7 days before the latest; reuses the diff engine, not a reinvention
    assert "diffCounts(" in js
    assert "H.trend.dates" in js or "H.trend && H.trend.dates" in js
    # big signed net % + advanced/regressed micro-stats
    assert "advanced" in js and "regressed" in js
    # all-masters roll-up when no master is selected
    assert "state.master" in js


def test_dashboard_js_week_digest_compares_prior_week() -> None:
    """#14: the trend arrow compares this week's net delta against the prior 7-day
    window's net (a second diffCounts call over the window before weekAgo)."""
    js = assets.DASHBOARD_JS
    digest = js.split("function weekDigest(")[1].split("\n  function ")[0]
    # two diffCounts windows: this week + the prior window before it
    assert digest.count("diffCounts(") >= 2 or digest.count("rollupDiff(") >= 2 \
        or (digest.count("diffCounts(") + digest.count("rollupDiff(")) >= 2
    # an explicit prior-window anchor date
    assert "prior" in digest.lower()
    # the comparison drives a single up/down/flat arrow token
    assert "deltaPct" in digest


def test_dashboard_css_styles_week_digest_class() -> None:
    """#14: the digest card carries a theme-safe rule and the big net number is
    sized/coloured via the design tokens (no hard-coded colours)."""
    css = assets.DASHBOARD_CSS
    assert ".tl-digest" in css
    digest_block = css.split(".tl-digest")[1].split("}")[0]
    assert "var(--" in digest_block


def test_dashboard_js_has_full_history_regression_log() -> None:
    """#15: a full-history regression log walks consecutive H.trend.dates for the
    active master, compares stateAt(prev) vs stateAt(curr) and collects glyphs whose
    rank dropped (rankOf(now) < rankOf(was); -> uncoloured counts as backward). It
    renders a newest-first was->now swatch table (top 8 + a "show all" expander) whose
    rows open the journey modal, and stays distinct from the last-save regressionCard
    (which keys off H.changes)."""
    js = assets.DASHBOARD_JS
    # the named full-history builder, wired into the timeline view (D1: last item)
    assert "function regressionLog(" in js
    timeline = js.split("function timelineView(")[1].split("function ")[0]
    assert "regressionLog()" in timeline
    # walks the real snapshot dates and reconstructs colour state at each
    assert "H.trend.dates" in js or "H.trend && H.trend.dates" in js
    assert "function regressionWalk(" in js               # the full-history walk
    walk = js.split("function regressionWalk(")[1].split("\n  function ")[0]
    assert "stateAt(" in walk                              # reconstruct each snapshot
    assert "rankOf(" in walk                               # rank comparison
    # the backward test: now ranks below was (-> uncoloured / null counts as backward)
    assert "rankOf(nw) < rankOf(was)" in walk
    # newest-first, top 8 with a "show all" expander, rows open the journey modal
    log = js.split("function regressionLog(")[1].split("\n  function ")[0]
    assert "regressionWalk()" in log                       # the log renders the walk
    assert "data-jglyph" in log
    assert "swatchFor(" in log                             # canonical varFor-backed swatch
    assert "slice(0, 8)" in log                            # top 8 + show-all expander
    assert "tl-reglog" in js
    # distinct from the last-save regressionCard (H.changes), still present
    assert "function regressionCard(" in js


def test_dashboard_js_regression_log_renders_nothing_when_clean() -> None:
    """#15: a clean history (no rank drops) renders nothing (or a quiet note), never
    inventing data."""
    js = assets.DASHBOARD_JS
    log = js.split("function regressionLog(")[1].split("\n  function ")[0]
    # the builder bails out when no glyph moved backwards
    assert 'return ""' in log or "nothing moved backwards" in log.lower()


def test_dashboard_js_regression_log_flags_chart_dates() -> None:
    """#15: every snapshot date with >=1 regression gets a small red tick (.tl-flag)
    on the line chart, drawn at that date's X via the shared calendar axis."""
    js = assets.DASHBOARD_JS
    # a shared set of regression dates the chart can flag
    assert "function regressionDates(" in js
    # the line chart draws a tl-flag tick at each flagged date's X
    trend = js.split("function trendParts(")[1].split("\n  function ")[0]
    assert "tl-flag" in trend
    assert "regressionDates(" in trend


def test_dashboard_css_styles_regression_log_and_flag() -> None:
    """#15: the regression-log table and the chart tick are theme-safe (no hard-coded
    colours leaking past the design tokens) and the tick reads as a red flag."""
    css = assets.DASHBOARD_CSS
    assert ".tl-reglog" in css
    assert ".tl-flag" in css
    flag_block = css.split(".tl-flag")[1].split("}")[0]
    assert "var(--" in flag_block


def test_dashboard_js_has_category_progress_lanes() -> None:
    """#17: per-category progress lanes over time. A categoryLanes builder maps each
    glyph to its category from the parallel H.glyphNames / H.categories arrays, then —
    per category, per snapshot date — sums graded step weights over that category's
    glyphs via stateAt to draw a tiny completion sparkline. Each row carries the
    category name, its sparkline, the current %, and a delta arrow vs ~a week ago;
    rows sort laggard-first (lowest current % on top). It degrades to a current-%
    bar when there are only 1-2 snapshots, and is wired into the timeline view."""
    js = assets.DASHBOARD_JS
    # the named builder, wired into the timeline view (D1: lanes section)
    assert "function categoryLanes(" in js
    timeline = js.split("function timelineView(")[1].split("function ")[0]
    assert "categoryLanes()" in timeline
    lanes = js.split("function categoryLanes(")[1].split("\n  function ")[0]
    # builds the glyphName -> category map from the two parallel arrays
    assert "H.categories" in lanes
    assert "H.glyphNames" in lanes
    # graded completion per date via stateAt + the shared step weights (not reinvented)
    assert "stateAt(" in lanes
    assert "stepWeights(" in lanes
    # walks the real snapshot dates for the over-time sparkline
    assert "H.trend.dates" in lanes or "H.trend && H.trend.dates" in lanes
    # one .tl-lane row per category, with a delta arrow vs ~a week ago
    assert "tl-lane" in lanes
    # laggard-first ordering (lowest current % on top)
    assert "sort(" in lanes
    # degrades to a current-% bar at 1-2 snapshots (no sparkline to draw)
    assert "tl-lane-bar" in lanes


def test_dashboard_css_styles_category_lane_class() -> None:
    """#17: the category lane row and its mini chart carry theme-safe rules built
    from the design tokens (no hard-coded colours)."""
    css = assets.DASHBOARD_CSS
    assert ".tl-lane" in css
    lane_block = css.split(".tl-lane{")[1].split("}")[0]
    assert "var(--" in lane_block


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


def test_dashboard_js_escape_closes_help_modal() -> None:
    js = assets.DASHBOARD_JS
    # The single Escape keydown branch must dismiss every modal, including help.
    start = js.index('if (e.key==="Escape"){')
    branch = js[start:js.index("}", start) + 1]
    assert "closeExport()" in branch
    assert "closeJourney()" in branch
    assert "closeHelp()" in branch


def test_dashboard_css_styles_help_panel() -> None:
    css = assets.DASHBOARD_CSS
    # The legend rows the help panel emits must carry layout/alignment rules.
    for selector in (".hp-list", ".hp-row", ".hp-n", ".hp-pos", ".hp-gloss", ".rg-sw"):
        assert selector in css, selector


def test_dashboard_css_styles_cross_master_card() -> None:
    css = assets.DASHBOARD_CSS
    # Every class crossMasterCard emits needs a layout rule.
    for selector in (".cm-headline", ".cm-bar", ".cm-line", ".cm-note",
                     ".cm-differ-list", ".cm-differ-row", ".cm-steps",
                     ".cm-steps-l", ".cm-step", ".cm-step-n"):
        assert selector in css, selector


def test_build_html_wires_all_report_insight_features() -> None:
    """End-to-end smoke: every new render unit + its wiring marker is present in
    the generated document, and the self-contained/no-network invariant holds."""
    html = assets.build_html(_model())
    # render units
    for marker in ("function crossMasterCard(", "function regressionCard(",
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


def test_dashboard_css_styles_report_insight_classes() -> None:
    """Every class the six report-insight features emit must carry a CSS rule, so
    swatches render at a real size and the new panels/rows/modal get layout."""
    css = assets.DASHBOARD_CSS
    # regression + recent-activity cards
    for selector in (".rg-sw", ".rg-row", ".rg-n", ".rg-ar", ".rg-when"):
        assert selector in css, selector
    # date A/B diff panel + its result chips
    for selector in (".tl-diff", ".tl-diff-h", ".tl-diff-pick", ".tl-diff-out",
                     ".dz", ".dz-up", ".dz-down", ".dz-flat", ".dz-net"):
        assert selector in css, selector
    # journey modal rows + help/legend panel
    for selector in (".jm-list", ".jm-row", ".jm-date", ".jm-lab",
                     ".hp-row", ".hp-gloss"):
        assert selector in css, selector
    # the swatch must declare an explicit size: guards the zero-size regression
    # that made every swatch invisible.
    swatch_rule = css.split(".rg-sw")[1].split("}")[0]
    assert "width:" in swatch_rule and "height:" in swatch_rule
