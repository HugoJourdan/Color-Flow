"""Tests for the inline-asset / HTML-shell layer of the Color Font Dashboard."""

from __future__ import annotations

import base64
import gzip
import json

import azcolorflow_assets as assets


def _model() -> dict:
    return {
        "family": "Acme", "fileName": "Acme.glyphs", "version": "1.0",
        "generated": "2026-06-05", "glyphTotal": 2,
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
    assert "<title>a&lt;b&gt; - Colorflow</title>" in html


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
    # the colour bar grows as one block — its own rule carries no per-segment stagger
    seg_rule = css.split(".seg.intro{", 1)[1].split("}", 1)[0]
    assert "animation-delay:calc(var(--i" not in seg_rule        # NOT per-segment staggered
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
    assert "function scriptRows(" in html              # per-master rows


def test_script_names_capitalised_and_other_skipped() -> None:
    js = assets.DASHBOARD_JS
    # the "By script" lanes skip the catch-all "Other" bucket and capitalise names
    lanes = js.split("function scriptLanes(", 1)[1].split("\n  function ", 1)[0]
    assert 'return s !== "Other"' in lanes                 # Other bucket dropped
    assert "esc(prettyScript(ln.script))" in lanes          # display name capitalised
    # the script grid cards capitalise their name too
    grid = js.split("function scriptGrid(", 1)[1].split("\n  function ", 1)[0]
    assert "charAt(0).toUpperCase()" in grid
    assert 'r.key !== "Other"' in grid                      # grid already skips Other


def test_overview_ring_has_colour_label_legend() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    ov = js.split("function overall(", 1)[1].split("\n  function ", 1)[0]
    assert "ov-legend" in ov and "ov-leg-item" in ov          # colour labels beside the ring
    assert 'data-fkey="' in ov                                # legend items focus a colour like the arcs
    assert "ov-leg-sw" in ov and "ov-leg-pct" in ov
    assert "legItem(-1, H.noneLabel" not in ov                # None is intentionally omitted here
    # Laid out as a 3-column grid (not a single vertical list).
    assert ".ov-legend{" in css and ".ov-leg-item" in css
    assert "grid-template-columns:repeat(3" in css


def test_lanes_no_headers_green_at_100_and_shown_in_focus() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    cat = js.split("function categoryLanes(", 1)[1].split("\n  function ", 1)[0]
    scr = js.split("function scriptLanes(", 1)[1].split("\n  function ", 1)[0]
    # the "By category/script · over time" headers are gone
    assert "tl-lanes-h" not in cat and "tl-lanes-h" not in scr
    assert "By category" not in cat and "By script" not in scr
    # category lanes render in focus mode too (Global-only guard removed)
    assert 'if (state.master != null) return ""' not in cat
    # a lane at 100% gets .done -> green line/bar
    assert '(ln.cur>=100?" done":"")' in cat and '(ln.cur>=100?" done":"")' in scr
    assert ".tl-lane.done .tl-lane-spark polyline{stroke:var(--ok)}" in css


def test_line_chart_draw_in_animation_and_nav_aligned() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    # lines carry pathLength=1; the chart svg gets .tl-anim only when entering the Timeline
    assert 'pathLength="1"' in js
    assert 'if (v==="timeline"){ tlChartShouldAnim = true; }' in js
    assert "tlChartShouldAnim = false;" in js                  # consumed after one render (no re-anim on scrub)
    assert '(tlChartShouldAnim?" tl-anim":"")' in js
    assert "@keyframes tlDraw" in css and "@keyframes tlFade" in css
    assert ".tl-anim .tl-line{stroke-dasharray:1;stroke-dashoffset:1;animation:tlDraw" in css
    rm = css.split("@media (prefers-reduced-motion:reduce){", 1)[1]
    assert ".tl-anim .tl-line{animation:none" in rm           # reduced-motion neutralises the draw-in
    # navigator now carries the SAME box as the chart (border+padding+radius) so its
    # outer width equals the chart's full-width bordered box (and plots stay aligned).
    assert ".tl-nav-wrap{position:relative;margin:6px 0 2px;padding:0}" in css
    assert ".tl-nav{display:block;width:100%;height:auto;cursor:crosshair;touch-action:none;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:4px}" in css


def test_lane_sparklines_draw_in_on_focus_switch() -> None:
    """The per-category/script lane sparklines draw in (left-to-right) when the
    focused master switches — a flag set at each master-switch site, consumed once
    the lanes render, reusing the chart's tlDraw keyframe; reduced-motion neutralises."""
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    # the polyline carries pathLength + the svg gets .tl-spark-anim when the flag is set
    assert 'var animCls = laneSparkShouldAnim ? " tl-spark-anim" : "";' in js
    assert 'pathLength="1" fill="none"' in js
    # flag set at every focus-master switch (leaderboard row, tab, tower click, arrows)
    assert js.count("laneSparkShouldAnim = true;") >= 4
    # consumed after the lanes render so scrub/zoom don't re-animate
    assert "laneSparkShouldAnim = false;" in js
    assert ".tl-spark-anim polyline{stroke-dasharray:1;stroke-dashoffset:1;animation:tlDraw" in css
    rm = css.split("@media (prefers-reduced-motion:reduce){", 1)[1]
    assert ".tl-spark-anim polyline{animation:none" in rm


def test_chart_has_savepoint_vertical_bars() -> None:
    """A faint light-gray vertical rule sits at every savepoint/day snapshot, behind
    the line, in both the per-master and the focus-mode (flow) chart."""
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    assert 'class="tl-vgrid"' in js                       # built in calendarAxis
    assert "var colBars = snaps.map(" in js
    assert js.count("+weekBands+ax.colBars+grid+") + js.count("+ax.weekBands+ax.colBars+grid+") >= 2
    assert ".tl-vgrid{stroke:var(--tl-vgrid);stroke-width:1" in css
    # theme-aware faint gray token in both themes
    assert "--tl-vgrid:rgba(255,255,255,.10)" in css and "--tl-vgrid:rgba(20,24,33,.10)" in css


def test_chart_dots_are_white() -> None:
    """Snapshot dots in both chart builders use the white --tl-dot token (dark theme),
    overridden to --text in light theme so they stay visible."""
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    assert 'fill="var(--tl-dot)"' in js
    assert js.count('fill="var(--tl-dot)"') >= 2          # per-master line dots + flow dots
    assert "--tl-dot:#ffffff" in css                      # white in dark theme
    light = css.split("html[data-theme=light]{", 1)[1].split("}", 1)[0]
    assert "--tl-dot:var(--text)" in light


def test_chart_curve_not_clickable() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    # the click-a-curve-to-focus-a-master feature was removed
    assert "data-focusm" not in js and "focusHits" not in js
    assert "tl-focushit" not in js and ".tl-focushit" not in css


def test_coverage_cards_folded_into_overview() -> None:
    html = assets.build_html(_model())
    assert "coverGroup" not in html                    # Script/Category toggle removed
    assert "Colours set by category" in html           # category card (now in the focused Overview)
    assert "Colours set by script" in html             # script card (now in the focused Overview)
    assert "scripts.length <= 1" in html and "scriptGrid()" in html  # script grid, only if >1 script
    # coverage scopes to the focused master, or AGGREGATES across the whole family in
    # Global view (covRows) — no silent first-master fallback.
    assert "function covRows(" in html
    assert "if (state.master != null) return by[state.master]" in html
    assert 'return covRows("byScript")' in html and 'covRows("byCategory")' in html


def test_coverage_bar_has_no_inline_percent_uses_hover_tooltip() -> None:
    html = assets.build_html(_model())
    assert 'class="cov-pct"' not in html               # inline % text removed from the bars
    assert 'labelFor(parseInt(k,10))+" — "+Math.round(w)+"%"' in html  # % + label now on hover
    assert ".cov-bar{flex:1;display:flex;height:10px;border-radius:5px" in html  # smaller, pill like Overview
    assert ".cov-row{display:flex;align-items:center;gap:12px;font-size:var(--fs-xs)" in html  # Compare font size


def test_dashboard_has_activity_calendar() -> None:
    js = assets.DASHBOARD_JS
    assert "function activityCalendar(" in js
    assert "function calActivity(" in js
    assert "data-calday" in js                           # day cells carry their snapshot index
    assert 'parseInt(cd.getAttribute("data-calday")' in js  # click reads the snapshot index
    assert "scrubSet(ci)" in js                          # ...and scrubs the Time Machine to it
    css = assets.DASHBOARD_CSS
    assert ".tl-cal-card" in css and ".tl-mcal-grid{" in css


def test_dashboard_calendar_lives_on_timeline() -> None:
    js = assets.DASHBOARD_JS
    assert "function calendarCard(" in js
    # the calendar moved OFF the Overview and onto the Timeline tab (full width)
    overview_extras = js.split("function overviewExtras(")[1].split("\n  function ")[0]
    assert "calendarCard()" not in overview_extras
    assert "histogram()" not in overview_extras           # "Masters by completion" card removed
    timeline_view = js.split("function timelineView(")[1].split("\n  function ")[0]
    # the calendar is MERGED into the graph card; a Graph/Calendar switch flips between them
    assert "activityCalendar()" in timeline_view and "tlPaneSwitch()" in timeline_view
    assert 'data-tlpane="calendar"' in js and 'data-tlpane="graph"' in js


def test_dashboard_calendar_is_month_grid_only() -> None:
    js = assets.DASHBOARD_JS
    assert "function standardCalendar(" in js            # macOS-style month grid
    assert "function calMonthRef(" in js                 # displayed-month state
    assert "data-calnav" in js                           # prev/next month nav
    # the heatmap variant + its Heatmap/Standard toggle are gone
    assert "function heatmapCalendar(" not in js
    assert "function calModeToggle(" not in js
    assert "data-calmode" not in js
    assert "calMode" not in js
    css = assets.DASHBOARD_CSS
    assert ".tl-mcal-grid{display:grid;grid-template-columns:repeat(7,28px)" in css
    assert ".tl-cal-mode-btn" not in css                 # toggle styles removed
    assert ".tl-cal-wk" not in css and ".tl-cal-key" not in css  # heatmap styles removed


def test_dashboard_has_colour_spread_radar_in_master_view() -> None:
    js = assets.DASHBOARD_JS
    # only the radar survives; treemap + day-rings (and their helpers) are gone
    assert "function radarCard(" in js
    assert "function treemapCard(" not in js
    assert "function dayRingsCard(" not in js
    assert "function squarify(" not in js
    assert "function ringTally(" not in js
    # radar draws ONLY the selected master's spread (one polygon), not all masters
    radar = js.split("function radarCard(", 1)[1].split("\n  function ", 1)[0]
    assert "H.masters[x].id===state.master" in radar      # picks the selected master
    assert "exm[String(steps[j].key)]" in radar           # a spread = exclusive current tally
    assert "masterHue(mi)" in radar                        # its own master hue
    assert "rdr-dim" not in radar and "rdr-foc" not in radar   # no dimmed other masters
    assert "H.masters.map(" not in radar                  # not iterating every master
    # NOT on the global Overview anymore...
    overview_extras = js.split("function overviewExtras(", 1)[1].split("\n  function ", 1)[0]
    assert "radarCard(" not in overview_extras
    # ...shown in the focused-master panel instead, build-animated once
    master_extras = js.split("function masterExtras(", 1)[1].split("\n  function ", 1)[0]
    assert "radarCard()" in master_extras
    assert 'ov-viz\'+(vizIntro?" intro":"")' in master_extras
    css = assets.DASHBOARD_CSS
    assert ".ov-viz{display:grid" in css
    assert ".rdr-poly{" in css
    assert ".rdr-foc{" not in css and ".rdr-dim{" not in css  # comparison styles removed
    assert ".tm-cell{" not in css and ".dr-arc{" not in css   # treemap/day-ring styles removed
    assert "@keyframes ovzScaleIn" in css and "@keyframes ovzRingIn" not in css
    rm = css.split("@media (prefers-reduced-motion:reduce){", 1)[1].split("}}", 1)[0]
    assert ".ov-viz.intro .rdr-poly" in rm


def test_cumulative_progress_shown_as_workflow_funnel() -> None:
    js = assets.DASHBOARD_JS
    # countFor is the cumulative metric (reached step k or beyond) — the model's counts
    # (raw passthrough; with non-exporting glyphs present it reroutes through countedStats).
    countfor = js.split("function countFor(", 1)[1].split("\n  function ", 1)[0]
    assert "m.counts[String(k)]" in countfor
    # the flat text legend is gone; a workflow funnel renders the cumulative reach as
    # descending click-to-focus bars so a near-full makeup bar can't read as near-done.
    assert '<div class="legend">' not in js
    assert "function funnelHTML(" in js
    funnel = js.split("function funnelHTML(", 1)[1].split("\n  function ", 1)[0]
    assert "reached this step or beyond" in funnel        # cumulative semantics
    assert 'class="fnl-fill"' in funnel                    # the descending bars
    assert "if (p === 0) return" in funnel                 # skip steps no glyph reached
    # read-only: focusing means glyphs sitting AT a colour (exclusive), which differs
    # from the funnel's reached-or-beyond, so the funnel must NOT be a focus selector.
    assert "data-fkey" not in funnel
    # collapsed by default; expanded by clicking the % ring (global) / % number (master)
    # — there is NO caption and NO chevron toggle button.
    assert "Reached each step" not in js
    assert "fnl-chev" not in js
    assert "if (state.funnelOpen === false) return" in funnel   # collapsed renders nothing
    assert "funnelOpen: false" in js                            # default collapsed
    assert 'closest("[data-funnel]")' in js                     # toggle wired in click handler
    # the funnel now lives ONLY on the focused-master card (the global Overview card is a
    # bare ring): the master card feeds countFor and toggles via its % number.
    master_overall = js.split("function masterOverall(", 1)[1].split("\n  function ", 1)[0]
    # funnel is fed a per-step count provider (cumFor); live path reuses countFor(m,k).
    assert "funnelHTML(cumFor, total)" in master_overall
    assert "countFor(m,kk)||0" in master_overall
    assert 'class="ov-pct" data-funnel="1"' in master_overall
    # the global card dropped the funnel + its ring-button toggle entirely
    overall = js.split("function overall(", 1)[1].split("\n  function ", 1)[0]
    assert "funnelHTML(" not in overall
    assert "data-funnel" not in overall
    # the funnel + its bars carry CSS
    css = assets.DASHBOARD_CSS
    assert ".funnel{" in css and ".fnl-fill{" in css


def test_tower_disc_desaturates_others_when_one_is_focused() -> None:
    js = assets.DASHBOARD_JS
    paint = js.split("function paintDisc(", 1)[1].split("\n    function ", 1)[0]
    # non-focused discs (glow<1) fully desaturate -> greyscale; gated on the WebKit probe
    assert "var desat = 1 - Math.max(0, Math.min(1, glow))" in paint
    assert 'saturate("+(1-desat)' in paint            # greyscale
    assert 'brightness("+(1-desat' in paint           # + darkened to matte charcoal
    assert "if (CTX_FILTER_OK)" in paint
    # non-focused disc opacity bumped to 0.37
    assert "opacityVal = 0.37" in js
    # every lit disc is 20% lighter globally; the selected disc adds +40% halo glow.
    assert "DISC_BRIGHT = 1.2" in js
    assert 'brightness("+DISC_BRIGHT.toFixed(3)+")' in paint   # all lit discs lightened
    assert "FOCUS_GLOW = 1.4" in js
    assert "(sel>=0 && ii===sel) ? FOCUS_GLOW" in js          # only the selected disc gets the glow
    assert "halo[h][2]*glow" in paint                         # halo alpha scales with glow (+20%)


def test_overview_card_is_big_colour_selectable_ring_only() -> None:
    """The global Overview card is just one big donut ring, tiled with the palette
    colours (each arc = a colour's exclusive share of the font) and each arc is a colour
    selector (data-fkey) that focuses that colour's glyphs and dims the other arcs. No
    stacked bar, no step funnel. The centre reads completion %."""
    js = assets.DASHBOARD_JS
    assert "function ring(p, segs, opts)" in js
    ring_fn = js.split("function ring(p, segs, opts)", 1)[1].split("\n  function ", 1)[0]
    # tiled coloured arcs, each a clickable colour selector with focus dimming
    assert "ov-ring-seg" in ring_fn
    assert "varFor(sg.key)" in ring_fn                 # each arc stroked in its palette colour
    assert "stroke-dasharray=" in ring_fn              # arcs placed by dash length/offset
    assert 'data-fkey="\'+sg.key+\'"' in ring_fn       # arc selects that colour
    assert "state.focus === sg.key" in ring_fn         # the focused arc is highlighted
    assert "sz = big ? 78" in ring_fn                  # the big Overview hero ring (5% up from 74)
    # overall() is ring-only: shares fed in, selectable + big, no bar / no funnel
    overall = js.split("function overall(", 1)[1].split("\n  function ", 1)[0]
    assert "ring(compP, ringSegs, {big:true, select:true, anim:barsAnim||scrubAnim})" in overall
    assert "ov-ringonly" in overall
    assert 'class="seg' not in overall                 # the stacked makeup bar is gone
    assert "funnelHTML(" not in overall                # the step funnel is gone
    css = assets.DASHBOARD_CSS
    assert ".ov-ring-big .ov-ring-t{font-size:18px" in css   # % text (ring 30% smaller)
    assert ".ov-ring-seg.off{" in css                        # non-focused arcs dim


def test_overview_focused_master_name_is_larger() -> None:
    """#4: when a master is focused, its name in the Overview card is rendered a bit
    larger so it reads as the card heading."""
    css = assets.DASHBOARD_CSS
    name_rule = css.split(".ov-name{", 1)[1].split("}", 1)[0]
    assert "font-size:17px" in name_rule


def test_tower_discs_have_frozen_dust_texture() -> None:
    """#3: the procedural FROST texture gets fine dark dust grains interleaved with the
    white frost sparkle, so each disc reads as a subtle frozen/dusty surface. Kept faint
    (low alpha) and drawn into the same offscreen FROST canvas the discs sample."""
    js = assets.DASHBOARD_JS
    frost = js.split("var FROST = (function(){", 1)[1].split("})();", 1)[0]
    # a second grain pass in black (the dust) on top of the white frost sparkle
    assert 'fillStyle="rgba(0,0,0,"' in frost
    assert "dust" in frost.lower() or "grain" in frost.lower()


def test_tower_spin_eases_in_with_smoothstep_ramp() -> None:
    """Motion etiquette #1: on load the tower spin ramps 0 -> full speed over ~1.5s
    (smoothstep on the rot increment) instead of starting at full speed. The old
    unconditional `rot+=0.00768` is gone; full speed itself is unchanged."""
    tower = assets.DASHBOARD_JS.split("function initTower(", 1)[1]
    assert "var SPIN_SPEED = 0.00768" in tower             # full speed unchanged
    assert "var SPIN_RAMP = 1/90, spinT = 0" in tower      # ~1.5s at 60fps
    assert "spinT*spinT*(3-2*spinT)" in tower              # smoothstep ease-in
    assert "rot += SPIN_SPEED*ramp" in tower               # increment scaled by the ramp
    assert "rot+=0.00768" not in tower                     # old hardcoded spin removed


def test_tower_spin_pauses_when_tab_hidden() -> None:
    """Motion etiquette #2: the rAF loop stops scheduling while the document is hidden
    (no CPU burn in hidden tabs) and resumes on visibilitychange — frame counters just
    continue, so there is no time-jump. A pending-frame guard prevents double loops."""
    tower = assets.DASHBOARD_JS.split("function initTower(", 1)[1]
    assert 'document.addEventListener("visibilitychange"' in tower
    assert "if (rafId!=null || document.hidden) return" in tower   # hidden: never schedule
    assert "cancelAnimationFrame(rafId)" in tower                  # hide: drop the pending frame
    assert "else schedule();" in tower                             # visible: resume
    assert "rafId = requestAnimationFrame(loop)" in tower          # single tracked handle


def test_tower_reduced_motion_never_spins_but_still_repaints() -> None:
    """Motion etiquette #3: under reduced motion / __cfdNoAnim (the shared TOWER_ANIM
    flag) the tower never spins — it renders once and repaints only when focus, scrub,
    master, scroll, or size change. The crossfade morph stays instant in that mode."""
    tower = assets.DASHBOARD_JS.split("function initTower(", 1)[1]
    # the spin branch is gated by the SAME flag the crossfade already uses
    assert "var TOWER_ANIM = !window.__cfdNoAnim" in tower
    assert "if (TOWER_ANIM){" in tower
    assert "} else if (changed){" in tower                 # reduced motion: repaint on change only
    # focus/scrub still rebuild the disc fields; master/scroll/resize tracked as dirty
    assert "sc!==curScrub" in tower
    assert "vt!==lastVt || sel!==lastSel || W!==lastW || Hc!==lastHc" in tower
    # the morph/crossfade path stays instant when TOWER_ANIM is off
    assert "{ PREV_FIELDS=null; morph=1; }" in tower


def test_dashboard_js_shape_changes_view() -> None:
    """#D: a "Shape changes" Timeline block reads H.outlineChanges (git outline diffs).
    Each day is a collapsible block (closed by default); expanding shows changed glyphs
    as onion-skin overlays — old outline ghosted under the new in a shared viewBox."""
    js = assets.DASHBOARD_JS
    assert "function outlineChangesView(" in js
    view = js.split("function outlineChangesView(")[1].split("\n  function ")[0]
    assert "H.outlineChanges" in view
    assert "Shape changes" in view
    assert "data-oc=" in view                              # per-day collapse toggle
    assert "state.ocOpen[d]" in view                       # closed unless toggled open
    assert "state.master===c.master" in view or "c.master===state.master" in view  # focus filter
    # onion-skin rendering lives in ONE shared helper (also used by the
    # "Touched after done" watch list): old ghost + new outline in a union viewBox
    onion = js.split("function ocOnionSVG(")[1].split("\n  function ")[0]
    assert "oc-old" in onion and "oc-new" in onion
    assert "ocUnionVB(" in onion
    cell = js.split("function ocCell(")[1].split("\n  function ")[0]
    assert "ocOnionSVG(" in cell
    # wired into the timeline view + the click toggle + default-collapsed state
    tv = js.split("function timelineView(")[1].split("\n  function ")[0]
    assert "outlineChangesView()" in tv
    assert 'closest("[data-oc]")' in js
    assert "ocOpen: {}" in js
    css = assets.DASHBOARD_CSS
    assert ".oc-grid{" in css and ".oc-old{" in css and ".oc-new{" in css


def test_dashboard_js_touched_after_done_watch_list() -> None:
    """Touched-after-done watch list: a Timeline card joining H.outlineChanges with
    H.journeyIndex — glyphs whose outline changed AFTER they reached the final
    workflow step (last key in H.order) and were still on it. Rows reuse the shared
    onion-skin SVG, open the glyph's journey on click, and sort by gap descending.
    Hidden when the join is empty or outlineChanges is absent (non-git reports)."""
    js = assets.DASHBOARD_JS
    # join half 1: the done-entry timestamp scan over journeyIndex events
    done = js.split("function tadDoneTs(")[1].split("\n  function ")[0]
    assert "ts.slice(0,10) >= changeDate" in done   # only events strictly before the change day
    assert "doneTs = null" in done                  # a later off-step event clears "done"
    # join half 2: outlineChanges x journeyIndex -> offence rows
    join = js.split("function touchedAfterDone(")[1].split("\n  function ")[0]
    assert "H.outlineChanges" in join and "H.journeyIndex" in join
    assert "H.order[H.order.length-1]" in join      # final workflow step = last ordered key
    assert "change.master !== state.master" in join  # focused master scopes the list
    assert "tadDoneTs(" in join
    assert "b.gapDays - a.gapDays" in join          # gap-descending sort
    # the card: one row per offence, shared onion-skin, journey on click
    view = js.split("function touchedAfterDoneView(")[1].split("\n  function ")[0]
    assert 'if (!rows.length) return ""' in view    # empty join / no data -> card hidden
    assert "Touched after done" in view
    assert "ocOnionSVG(" in view                    # reuses the oc-old/oc-new machinery
    assert "data-jglyph=" in view                   # delegated click -> openJourney(name)
    assert "tadMasterName(" in view                 # master name shown on global rows
    assert "state.master == null" in view           # ...and only there (focus omits it)
    assert "done " in view and "outline changed " in view and " later)" in view
    # rendered right after the Shape-changes block in the Timeline tab
    tv = js.split("function timelineView(")[1].split("\n  function ")[0]
    assert "outlineChangesView()+touchedAfterDoneView()" in tv
    css = assets.DASHBOARD_CSS
    assert ".tad{" in css and ".tad-row{" in css and ".tad-row svg{" in css


def test_timeline_chart_auto_colours_on_master_focus() -> None:
    js = assets.DASHBOARD_JS
    tv = js.split("function timelineView(", 1)[1].split("\n  function ", 1)[0]
    # one graph, always shown. Focusing a master AUTO-shows its colour breakdown
    # (streamParts); Global (no master) is the plain per-master line (trendParts). No
    # Colours button, no deadline panel, no moment-disc row below the chart.
    assert "var graphPane" in tv
    # focused master -> colour Flow; global -> the median+spread band
    assert "(state.master != null) ? streamParts(680, 200) : trendBandParts(680, 200)" in tv
    assert "tlColorsToggle()" not in tv and "function tlColorsToggle(" not in js
    assert "momentDiscs()" not in tv and "deadlinePanel()" not in tv
    # the category + script lanes sit in a two-column grid; Time Machine row gone
    assert "timeMachine()" not in tv
    assert 'tl-lanes-grid' in tv and "categoryLanes()" in tv and "scriptLanes()" in tv


def test_timeline_lanes_have_rank_arrows() -> None:
    js = assets.DASHBOARD_JS
    # shared rank-arrow helper, reused by the category + script lanes (DRY)
    assert "function rankArrow(" in js
    assert "rankArrow(ln.delta)" in js                   # category + script lanes


def test_dashboard_canvas_blur_has_webkit_fallback() -> None:
    js = assets.DASHBOARD_JS
    assert "CTX_FILTER_OK" in js                          # one-time canvas ctx.filter probe
    assert "function cssSafeBlur(" in js                  # downscale->upscale fallback blur
    assert "if (CTX_FILTER_OK)" in js                     # the disc field blur is gated
    assert "cssSafeBlur(off, bg, FS" in js                # ...fallback on the else path (WebKit)


def test_progress_bar_and_dots_glow_softened() -> None:
    js = assets.DASHBOARD_JS
    html = assets.build_html(_model())
    # bar glow reduced (42% -> 22%) and no longer at the old strength
    assert "0 0 9px color-mix(in srgb,var('+glow+') 22%,transparent)" in js
    assert "42%,transparent)" not in js
    # coverage bars now carry the same per-segment colour glow
    assert "box-shadow:0 0 9px color-mix(in srgb,'+bg+' 22%,transparent)" in js
    assert ".cov-bar{flex:1;display:flex;height:10px;border-radius:5px;overflow:visible" in html
    # legend colour dots glow in their own colour
    assert "function legendDot(" in js
    assert "0 0 7px color-mix(in srgb,var('+v+') 26%,transparent)" in js


def test_dashboard_js_has_expandable_overview_cards_no_duplicate_chart() -> None:
    js = assets.DASHBOARD_JS
    assert "function ovCard(" in js                       # shared expandable card
    # the completion chart lives only on the Timeline tab now; the Overview no longer
    # embeds a duplicate copy of it.
    assert "function timelineCard(" not in js
    overview_extras = js.split("function overviewExtras(")[1].split("\n  function ")[0]
    assert "timelineCard()" not in overview_extras
    assert "function trendParts(" in js                   # chart builder (Timeline tab)
    assert "data-ovexpand" in js                          # header toggles expansion
    assert "ovExpand" in js                               # per-card expanded state
    assert "leaderboard\", \"Furthest along\"" in js or 'ovCard("leaderboard"' in js


def test_dashboard_timeline_chart_has_no_static_legend() -> None:
    js = assets.DASHBOARD_JS
    tv = js.split("function timelineView(")[1].split("\n  function ")[0]
    assert "tl-legend" not in tv                          # static colour/name legend removed
    assert "parts.chart+tlGraphInfo()" in tv              # chart wrapped with the (i) info button
    assert "rangeNav(680)+parts.foot" in tv               # + (short, full-width) navigator + (empty) foot
    assert "tl-legend-card" not in assets.DASHBOARD_CSS    # its style dropped too


def test_dashboard_chart_click_scrubs_sidebar_discs() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    # clicking the chart scrubs to that snapshot; the windowed index maps to the full series
    assert "function scrubSet(" in js
    assert "function chartClick(" in js
    assert "scrubSet(viewBounds()[0] + idx)" in js
    # a persistent marker on the chart for the picked moment
    assert "scrubRule" in js and "tl-scrubline" in js
    assert ".tl-scrubline" in css and ".tl-scrubdot" in css
    # the picked moment drives the LEFT-SIDEBAR rotating discs: the tower's per-master
    # colour counts reconstruct that snapshot's state via stateAt when tlScrub is set.
    tower = js.split("function initTower(", 1)[1]
    assert "function countsOf(" in tower
    assert "if (state.tlScrub != null)" in tower and "stateAt(m.id, date)" in tower
    assert "sc!==curScrub" in tower                  # the spin loop rebuilds discs on a scrub change
    # the moment-disc row below the chart was removed
    assert "function momentDiscs(" not in js and ".tl-moments-row" not in css
    # the brush-to-compare drag + Time Machine scrubber are gone
    assert "function brushMove(" not in js and "tl-brush" not in css
    assert "function timeMachine(" not in js and "function scrubKey(" not in js


def test_dashboard_heatmap_time_travels_with_the_picked_moment() -> None:
    js = assets.DASHBOARD_JS
    heat = js.split("function heatmap(", 1)[1].split("\n  function masterPct(", 1)[0]
    # scrubbed -> the cells reconstruct the HISTORICAL colour state via stateAt,
    # at the same snapshot index the discs/lanes read (scrubIndex over trend dates)
    assert "state.tlScrub != null" in heat
    assert "stateAt(m.id, sdate)" in heat and "scrubIndex()" in heat
    # the historical key feeds the SAME items[] the cell colour, the focus filter
    # and the by-colour grouping all read, so they stay consistent while scrubbed;
    # glyphs without an event by that date fall back to uncoloured (-1).
    assert "scrubSnap[H.glyphNames[i]] != null ? scrubSnap[H.glyphNames[i]] : -1" in heat
    assert "items.push([H.glyphNames[i], key0, i])" in heat
    # the before/after toggle works at ANY picked moment: scrubbed -> it diffs the picked day
    # vs the PREVIOUS snapshot date; not scrubbed -> vs the last run
    assert "scrubPrevSnap = stateAt(m.id, sdates[si-1])" in heat
    assert "var wasKey = (ch[name] != null) ? ch[name][0] : key" in heat
    assert "var toggle = (Object.keys(ch).length)" in heat


def test_dashboard_heatmap_scrub_pill_removed() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    heat = js.split("function heatmap(", 1)[1].split("\n  function masterPct(", 1)[0]
    # the "Viewing … — back to today" pill was removed per request
    assert 'class="heat-pill"' not in heat
    assert "back to today" not in heat
    assert ".heat-pill" not in css                            # dead style removed too
    # scrub still drives the cells' historical colours (time-travel intact)
    assert "scrubSnap" in heat and "stateAt(m.id, sdate)" in heat


def test_dashboard_heatmap_cell_links_require_a_file_path() -> None:
    """An UNSAVED font has no path, and a glyphsapp:// link with an empty path
    would target the wrong (frontmost) document — those cells render as plain
    <span>s with the same classes/data attributes (hover/tooltip intact)."""
    js = assets.DASHBOARD_JS
    cell = js.split("function cellHTML(")[1].split("\n    var sections")[0]
    assert "if (!H.filePath)" in cell                     # the non-link guard
    assert "'<span class=\"' + cls" in cell               # span fallback, same classes
    assert 'encodeURIComponent(H.filePath)' in cell       # link path never empty
    assert 'encodeURIComponent(H.filePath || "")' not in js


def test_dashboard_navigator_has_date_ticks_no_side_dates() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    nav = js.split("function rangeNav(", 1)[1].split("\n  function ", 1)[0]
    # tick labels below the navigator (bucket-aware via tickLabel), replacing the old
    # start/end date row (.tl-foot) which is gone.
    assert "navTicks" in nav and "tickLabel(p.date)" in nav
    assert "tl-xtick" in nav
    assert ".tl-foot" not in css
    # both chart builders now return an empty foot (the side dates moved to the nav)
    assert 'foot:""' in js


def test_dashboard_time_save_modes_and_buckets() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    # Save is the default; a single Time toggle switches modes (no separate Save button).
    # Time mode reveals the Hours/Days/Months range buttons.
    gran = js.split("function tlGranToggle(", 1)[1].split("\n  function ", 1)[0]
    assert "data-tlgrantoggle=" in gran                  # one Time toggle, flips Save <-> Time
    assert ">Time<" in gran
    assert ">Save<" not in gran and 'data-tlgran="save"' not in gran   # Save button removed
    assert "if (time)" in gran                           # range buttons only render in Time mode
    assert "data-tlbucket=" in gran                      # bucket buttons are templated from units
    for unit in ('["day","Days"]', '["month","Months"]'):
        assert unit in gran, unit
    assert '["hour","Hours"]' not in gran                # Hours bucket removed (no intra-day history on past days)
    # bind toggles Save <-> Time on the single button
    assert 'setGranularity(state.tlGran==="time" ? "save" : "time")' in js
    # the engine: Save (the default) plots the raw fine set, Time buckets it (last per hour/day/month)
    assert 'tlGran: "save"' in js                         # Save is the default mode
    assert "function bucketedTrend(" in js and "function bucketKey(" in js
    assert 'state.tlGran === "save"' in js                  # Save mode picks the fine set
    assert "function setBucket(" in js and "tlBucket:" in js
    assert ".tl-bucket" in css


def test_dashboard_uses_even_spacing_in_both_modes() -> None:
    js = assets.DASHBOARD_JS
    # both Time and Save modes space snapshots ordinally (one equal slot each) so bunched-
    # in-time saves don't cluster at the left — the axis is index-based, never proportional.
    assert "var even = true" in js
    assert "idxByDate" in js                              # index lookup drives even spacing


def test_dashboard_has_duration_presets() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    # duration presets (1D/1W/1M/1Y/All) drive the zoom window, rendered as the SAME sliding-
    # pill segmented switch (.segsw) as the Graph/Calendar toggle.
    span = js.split("function tlSpanToggle(", 1)[1].split("\n  function ", 1)[0]
    assert 'class="segsw tl-spanbar"' in span and "--segn:" in span
    assert 'segHL("tlspan"' in span                         # sliding pill, keyed per switch
    assert ".tl-spanbar" in css
    assert "function tlSpanToggle(" in js and "function setTlSpan(" in js
    assert "data-tlspan" in js                              # engine + markup retained
    assert 'segswAnimKey = "tlspan"' in js                  # clicking a preset arms the slide
    tv = js.split("function timelineView(", 1)[1].split("\n  function ", 1)[0]
    assert "tlSpanToggle()" in tv                           # range presets next to the graph
    assert "tlGranToggle" not in tv                         # the granularity bar stays removed
    for label in ('"1D"', '"1W"', '"1M"', '"1Y"', '"All"'):
        assert label in js, label


def test_dashboard_has_range_navigator() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    assert "function rangeNav(" in js                     # the mini-chart range selector
    assert "function trendSeries(" in js and "function viewBounds(" in js   # zoom-window slicing
    assert "function navDrag(" in js and "function navReset(" in js         # drag + reset handlers
    assert 'data-navedge="mid"' in js and 'data-navedge="lo"' not in js     # mid literal; lo/hi via handle()
    # reset affordance: double-clicking the navigator restores the full history
    # (the dead data-navreset button/handler pair was removed)
    assert 'e.target.closest(".tl-nav")' in js and "navReset()" in js
    assert "data-navreset" not in js
    assert ".tl-nav-win" in css and ".tl-nav-h-bar" in css and ".tl-nav-scrim" in css


def test_dashboard_js_uses_graded_step_progress() -> None:
    js = assets.DASHBOARD_JS
    assert "function stepWeights(" in js                 # palette-order step ranking
    assert "function gradedMasterPct(" in js
    assert "function gradedOverallPct(" in js
    assert "(i+1)/N" in js                                # first step = 1/N, final = 100%
    assert "% complete" in js                             # graded % shown in the headline
    assert "function masterPct(m){ return gradedMasterPct(m); }" in js  # leaderboard uses it


def test_dashboard_js_routes_focus_through_setfocus() -> None:
    js = assets.DASHBOARD_JS
    assert "function setFocus(" in js
    assert "__cfdNoAnim" in js
    assert "items.filter(matchesFocus)" in js                   # recompose to selected colour
    assert "barsAnim = !introPlayed" in js                       # fill animation only on first paint
    assert "barMaster" not in js                                 # no re-fill on master switch


def test_dashboard_js_keeps_focus_across_overview_timeline() -> None:
    js = assets.DASHBOARD_JS
    assert "function toggleView(" in js
    tv = js.split("function toggleView(", 1)[1].split("state.view = v; update();", 1)[0]
    # switching Overview <-> Timeline KEEPS the colour focus (no reset on entering Timeline)
    assert "state.focus = null" not in tv
    assert 'if (v==="timeline"){ tlChartShouldAnim = true; }' in tv
    # only Timeline routes through the helper now: the Coverage tab was removed (its
    # category + script cards folded into the focused-master Overview), Compare earlier.
    assert 'toggleView("coverage")' not in js
    assert 'toggleView("timeline")' in js


def test_coverage_tab_removed_cards_in_focused_overview() -> None:
    js = assets.DASHBOARD_JS
    # Coverage tab is gone: no view, no route, no chip, no handler
    assert "function coverageView(" not in js
    assert 'state.view==="coverage"' not in js
    assert 'id="cfd-coverage"' not in js
    # the focused-master Overview now carries BOTH the category card and the script grid,
    # right after the master's progress bar
    tabs = js.split("function tabsView(", 1)[1].split("\n  function ", 1)[0]
    assert "masterOverall(m)+categoryCoverageCard()+scriptCoverageCard()+heatmap(m)" in tabs
    assert "function categoryCoverageCard(" in js and "function scriptCoverageCard(" in js
    # the script card reuses the existing script-grid card builder, gated to >1 script
    scov = js.split("function scriptCoverageCard(", 1)[1].split("\n  function ", 1)[0]
    assert "scriptGrid()" in scov and "scripts.length <= 1" in scov


def test_dashboard_js_has_journey_helpers() -> None:
    js = assets.DASHBOARD_JS
    assert "function journeyOf(" in js
    assert "function stateAt(" in js
    # journeyOf reads the sparse index; stateAt carries the last event forward.
    assert "H.journeyIndex" in js
    assert "<=" in js  # stateAt: last event at or before the date


def test_dashboard_js_has_x_axis_with_bucket_labels() -> None:
    """#7: the chart draws bucket-aware date ticks on an even (index) axis. The
    always-on 'today' dashed rule + date bubble and the calendar week bands were
    removed; tick labels honour the active Time bucket (day/month) via tickLabel."""
    js = assets.DASHBOARD_JS
    # short "D Mon" date->label helper + the bucket-aware tick label that wraps it
    assert "function dateLabel(" in js
    assert "function tickLabel(" in js
    assert "esc(tickLabel(p.date))" in js                 # x ticks route through tickLabel
    assert "tl-xtick" in js
    # the grid/polyline/dots layers stay
    assert "tl-grid" in js
    assert "tl-dot" in js
    # the removed always-on markers are gone
    assert "tl-today" not in js and "tl-weekband" not in js


def test_dashboard_css_styles_x_axis_classes() -> None:
    """#7: the x-axis tick labels carry a theme-safe CSS rule built from --muted vars.
    The 'today' rule + bubble styles were removed with the marker."""
    css = assets.DASHBOARD_CSS
    assert ".tl-xtick" in css
    # the removed markers carry no leftover CSS
    assert ".tl-today" not in css and ".tl-weekband" not in css


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


def test_dashboard_chart_click_only_no_hover_popover() -> None:
    # the hover crosshair + floating read-out popover were removed; the chart's only
    # pointer interaction is click-to-pick-a-moment (chartClick). The transparent capture
    # rect stays so clicks register on empty plot space. cfd-tip survives for the heatmap.
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    assert "function crosshairMove(" not in js and "function crossReadout(" not in js
    assert ".tl-cross{" not in css and ".tl-cross-mark" not in css and ".tl-cross-row" not in css
    assert "tl-crossarea" in js and ".tl-crossarea" in css   # click hit-area kept
    assert "function chartClick(" in js
    assert "function showTip(" in js and ".cfd-tip" in css   # heatmap tooltip untouched


def test_dashboard_js_has_colour_decomposition_builder() -> None:
    """The chart is the graded completion Line; turning Colours ON overlays the weighted
    per-colour breakdown under it (streamParts). Bands stack bottom->top by H.order; each
    band's height is its step-weight x count / total, so the stack TOP traces the same
    graded % as the line (drawn on top). Scope = the focused master, else the aggregate
    over all masters. No uncoloured band (it's the empty space above). Reuses the #7 axis."""
    js = assets.DASHBOARD_JS
    assert "function streamParts(" in js
    # weighted decomposition driving the stack top to the graded line
    assert "function bandPct(" in js and "stepWeights()" in js
    assert "stateAt(" in js                                  # per-snapshot state reconstruction
    assert "scopeIds" in js                                  # focused master OR aggregate over all masters
    assert "H.order" in js and "varFor(" in js               # bands by palette order, per-step var
    assert "smoothPath(up)" in js                            # band edges use the SAME smoothing as the lines
    assert "tl-flow-soft" not in js                          # no dreamy blur filter
    assert "tl-stream-none" not in js                        # no uncoloured band (empty space instead)
    assert "dayOff(" in js                                   # shares the calendar X axis math
    # focus mode draws NO accent top-line — the coloured band stack already traces the
    # completion curve; only small per-snapshot dots remain as clickable markers.
    assert "var topLine" not in js
    assert "var topDots" in js and "bandGroup += topDots;" in js


def test_dashboard_all_lines_use_smooth_path() -> None:
    js = assets.DASHBOARD_JS
    # smoothPath is shared (hoisted above trendParts) and used by every progress line
    assert "function smoothPath(" in js
    assert js.index("function smoothPath(") < js.index("function trendParts(")   # hoisted, reusable
    assert 'polyline class="tl-line' not in js             # no straight master line left
    assert "var smooth = smoothPath(pts);" in js           # per-master trend lines are smooth
    assert "smoothPath(up)" in js                          # focus-mode colour-band edges are smooth
    assert "var line = smoothPath(pts);" in js             # the range navigator line


def test_dashboard_colours_auto_on_master_focus() -> None:
    """No Colours button: the colour breakdown (streamParts) auto-shows when a master is
    focused; Global (no master) is the plain per-master line (trendParts)."""
    js = assets.DASHBOARD_JS
    assert "tlColors" not in js                              # the toggle + its state are gone
    assert "function tlColorsToggle(" not in js and "data-tlcolors" not in js
    assert "(state.master != null) ? streamParts(680, 200) : trendBandParts(680, 200)" in js
    assert "tlModeToggle(" not in js and "state.tlMode" not in js   # old mode toggle removed


def test_dashboard_css_styles_chart_classes() -> None:
    """The colour bands + the granularity chips carry theme-safe rules; the active chip
    is highlighted with the accent var."""
    css = assets.DASHBOARD_CSS
    assert ".tl-band" in css
    assert ".tl-mode" in css                                # the granularity (Per day/Per save) chips
    active_rule = css.split(".tl-mode-btn[aria-pressed=true]")[1].split("}")[0]
    assert "var(--accent)" in active_rule


def test_dashboard_js_single_backward_feed() -> None:
    js = assets.DASHBOARD_JS
    # The three overlapping backward feeds collapsed to one: the last-save regressionCard
    # (and its mergedChanges helper) are gone; "Moved backward over time" (regressionLog,
    # full history) is the single backward feed.
    assert "function regressionCard(" not in js
    assert "function mergedChanges(" not in js
    assert "function regressionLog(" not in js            # the backward-moves panel was removed too


def test_dashboard_js_recent_is_per_master_only() -> None:
    js = assets.DASHBOARD_JS
    # The Recent-activity card was removed from the report UI; a "recently modified" grid
    # filter replaces it. It is rendered NOWHERE now.
    extras = js.split("function overviewExtras(")[1].split("}")[0]
    assert "recentCard(" not in extras                   # not on the global Overview
    tabs = js.split("function tabsView(")[1].split("}")[0]
    assert "masterExtras()" not in tabs                  # focused-master panel no longer renders it
    # the replacement: a recently-modified toggle on the glyph grid
    assert 'data-heatrecent' in js and "state.heatRecent" in js


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


def test_dashboard_js_recent_progress_panel_removed() -> None:
    """The "Recent progress" From/To compare panel (dateDiffPanel) and its A/B date
    state were removed; clicking the chart to pick a moment replaces it. The standalone
    "This week" digest is also gone. The underlying diff engine stays (seed states + lanes)."""
    js = assets.DASHBOARD_JS
    assert "function dateDiffPanel(" not in js
    assert "Recent progress" not in js
    assert "dateA:" not in js and "dateB:" not in js
    assert 'id="cfd-date-a"' not in js and 'id="cfd-date-b"' not in js
    assert "function weekDigest(" not in js and "tl-digest" not in js
    assert ".tl-diff" not in assets.DASHBOARD_CSS
    # the diff engine that backed it survives (the seed states + lanes still use it)
    assert "function diffCounts(" in js


def test_dashboard_js_regression_panel_removed() -> None:
    # The "Moved backward over time" panel (regressionLog) was removed, and so were the
    # red regression ticks (.tl-flag) on the chart.
    js = assets.DASHBOARD_JS
    assert "function regressionLog(" not in js
    assert "Moved backward over time" not in js
    assert "tl-reglog" not in js
    timeline = js.split("function timelineView(")[1].split("function ")[0]
    assert "regressionLog()" not in timeline


def test_dashboard_no_regression_flags_on_chart() -> None:
    # the red regression ticks were removed from the chart entirely
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    assert "tl-flag" not in js and ".tl-flag" not in css
    trend = js.split("function trendParts(")[1].split("\n  function ")[0]
    assert "regressionDates(" not in trend


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
    # graded completion per date via the shared lane helper (averaged across the family
    # in Global view); stateAt + step weights live in laneGradedPctOne, not reinvented here
    assert "laneGradedPct(names" in lanes
    assert "function laneGradedPct(" in js and "function laneGradedPctOne(" in js
    one = js.split("function laneGradedPctOne(")[1].split("\n  function ")[0]
    assert "stateAt(" in one and "stepWeights(" in one
    # walks the real snapshot dates for the over-time sparkline
    assert "H.trend.dates" in lanes or "H.trend && H.trend.dates" in lanes
    # one .tl-lane row per category, with a delta arrow vs ~a week ago
    assert "tl-lane" in lanes
    # laggard-first ordering (lowest current % on top)
    assert "sort(" in lanes
    # always a sparkline line, even at the first snapshot (single point -> flat line); never a bar
    assert "laneSparkSVG(ln.values" in lanes and "tl-lane-bar" not in lanes


def test_dashboard_css_styles_category_lane_class() -> None:
    """#17: the category lane row and its mini chart carry theme-safe rules built
    from the design tokens (no hard-coded colours)."""
    css = assets.DASHBOARD_CSS
    assert ".tl-lane" in css
    lane_block = css.split(".tl-lane{")[1].split("}")[0]
    assert "var(--" in lane_block


def test_dashboard_js_has_script_progress_lanes() -> None:
    """#18: per-script progress lanes over time mirror the per-category lanes (#17),
    but group by the per-glyph H.scripts array (writing systems) instead of
    H.categories. A scriptLanes builder maps each glyph to its script from the
    parallel H.glyphNames / H.scripts arrays, then — per script, per snapshot date —
    sums graded step weights over that script's glyphs via stateAt to draw a tiny
    completion sparkline. Each row carries the script name, its sparkline, the
    current %, and a delta arrow vs ~a week ago; rows sort laggard-first. It reuses
    the .tl-lane styling and is wired into the timeline view."""
    js = assets.DASHBOARD_JS
    # the named builder, wired into the timeline view (D1: lanes section)
    assert "function scriptLanes(" in js
    timeline = js.split("function timelineView(")[1].split("function ")[0]
    assert "scriptLanes()" in timeline
    lanes = js.split("function scriptLanes(")[1].split("\n  function ")[0]
    # builds the glyphName -> script map from the two parallel arrays (the new field)
    assert "H.scripts" in lanes
    assert "H.glyphNames" in lanes
    # graded completion per date via the shared lane helper (averaged across the family
    # in Global view); stateAt + step weights live in laneGradedPctOne, not reinvented here
    assert "laneGradedPct(names" in lanes
    assert "function laneGradedPct(" in js and "function laneGradedPctOne(" in js
    # walks the real snapshot dates for the over-time sparkline
    assert "H.trend.dates" in lanes or "H.trend && H.trend.dates" in lanes
    # one .tl-lane row per script, with a delta arrow vs ~a week ago
    assert "tl-lane" in lanes
    # laggard-first ordering (lowest current % on top)
    assert "sort(" in lanes
    # always a sparkline line, even at the first snapshot (single point -> flat line); never a bar
    assert "laneSparkSVG(ln.values" in lanes and "tl-lane-bar" not in lanes


def test_dashboard_deadline_feature_removed() -> None:
    """The #19 deadline / Target-date feature was removed entirely: no date input, no
    builder, no on-chart deadline rule, no verdict chips/CSS."""
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    assert 'id="cfd-deadline"' not in js
    assert "function deadlinePanel(" not in js and "function deadlineRule(" not in js
    assert "function deadlineKey(" not in js and "function daysUntil(" not in js
    timeline = js.split("function timelineView(")[1].split("\n  function ")[0]
    assert "deadlinePanel()" not in timeline
    for gone in (".tl-deadline", ".tl-verdict", ".tl-v-name", ".tl-v-trend"):
        assert gone not in css, gone


def test_hidden_colours_treated_as_none_everywhere() -> None:
    """A glyph painted with a colour hidden in the plugin (a key not in H.order) is
    treated as uncoloured everywhere: m.keys is normalised to -1 once at load (so the
    disc, heatmap and breakdown agree), and stateAt does the same for the Time Machine."""
    js = assets.DASHBOARD_JS
    assert "function normalizeHiddenKeys(" in js
    norm = js.split("function normalizeHiddenKeys(")[1].split("\n  function ")[0]
    assert "inOrder" in norm
    assert "ks[i] = -1" in norm
    # called once, right after the model is assigned at load
    assert "normalizeHiddenKeys();" in js
    # stateAt drops hidden keys to -1 too (timeline consistency)
    stateat = js.split("function stateAt(")[1].split("\n  function ")[0]
    assert "H.order.indexOf(String(key))===-1" in stateat


def test_heatmap_focus_mode_sort_by_colour() -> None:
    """G: the Overview focus-mode glyph grid offers a Category | By colour sort.
    By-colour groups cells by their current colour in workflow order (uncoloured last);
    Category stays the default."""
    js = assets.DASHBOARD_JS
    heat = js.split("function heatmap(")[1].split("\n  function ")[0]
    # the sort control with both options
    assert "hsort" in heat
    assert 'data-hsort="category"' in heat and 'data-hsort="color"' in heat
    # the by-colour grouping branch: workflow order, uncoloured bucket last
    assert 'state.heatSort === "color"' in heat
    assert 'keyOrder.push("none")' in heat
    assert "swatchFor(" in heat                       # colour sections carry a swatch
    # default + wired toggle
    assert 'heatSort: "category"' in js
    assert 'closest("[data-hsort]")' in js


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


def test_dashboard_js_has_no_help_panel_or_button() -> None:
    """The Colour-label "?" help button + its panel were removed; the colour
    legend lives beside the Overview ring (.ov-legend) instead."""
    js = assets.DASHBOARD_JS
    assert "function helpPanel(" not in js
    assert "function openHelp(" not in js
    assert 'id="cfd-help"' not in js
    assert "state.helpOpen" not in js
    # the Escape branch no longer calls closeHelp
    start = js.index('if (e.key==="Escape"){')
    branch = js[start:js.index("}", start) + 1]
    assert "closeHelp()" not in branch
    assert "closeExport()" in branch and "closeJourney()" in branch


def test_build_html_has_no_help_button() -> None:
    html = assets.build_html(_model())
    assert 'id="cfd-help"' not in html
    assert "http://" not in html and "https://" not in html   # invariant preserved


def test_build_html_wires_all_report_insight_features() -> None:
    """End-to-end smoke: every new render unit + its wiring marker is present in
    the generated document, and the self-contained/no-network invariant holds."""
    html = assets.build_html(_model())
    # render units
    for marker in ("function recentCard(", "function categoryLanes(",
                   "function openJourney(",
                   "function journeyOf(", "function stateAt("):
        assert marker in html, marker
    # wiring: cell + row triggers, journey index
    assert "data-jglyph" in html
    assert "H.journeyIndex" in html
    # spec #4 net graded-% delta engine reaches the document; swatches reuse varFor
    assert "function gradedStateSum(" in html
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
    # the progress lanes + their two-column grid (replaces the removed moment-disc row)
    for selector in (".tl-lanes", ".tl-lane", ".tl-lanes-grid"):
        assert selector in css, selector
    # journey modal rows (the help/legend panel was removed)
    for selector in (".jm-list", ".jm-row", ".jm-date", ".jm-lab"):
        assert selector in css, selector
    # the swatch must declare an explicit size: guards the zero-size regression
    # that made every swatch invisible.
    swatch_rule = css.split(".rg-sw")[1].split("}")[0]
    assert "width:" in swatch_rule and "height:" in swatch_rule
def test_dashboard_time_machine_play_button_removed() -> None:
    js = assets.DASHBOARD_JS
    assert "scrubPlay" not in js                         # Play/autoplay machinery gone
    assert "tl-scrub-play" not in js
    assert ".tl-scrub-play" not in assets.DASHBOARD_CSS


def test_dashboard_js_has_seed_state_builder() -> None:
    """#20: the bland "not enough history" line is replaced by a seed-state builder.
    timelineView routes to it whenever hasTrend() is false (<2 snapshots) AND for the
    ==2 day case, so the full timelineView only renders at >=3 snapshots. The builder is
    a single named fn (seedState) gating internally on H.trend.dates.length."""
    js = assets.DASHBOARD_JS
    assert "function seedState(" in js
    timeline = js.split("function timelineView(")[1].split("\n  function ")[0]
    # timelineView no longer hard-codes the old bland sentence; it routes to seedState
    assert "Not enough history yet" not in timeline
    assert "seedState()" in timeline
    # the gate now keeps the FULL view for >=3 snapshots only
    assert ">= 3" in timeline or ">=3" in timeline or "< 3" in timeline or "<3" in timeline


def test_dashboard_js_seed_state_skeleton_and_locked_chips_under_two() -> None:
    """#20 (<2 snapshots): a skeleton preview (dashed placeholder line + ghost dots +
    one real solid "today" dot from the single snapshot) plus a row of locked preview
    chips (Streak / Moment discs / Shape changes, each muted "unlocks at 2 days")."""
    js = assets.DASHBOARD_JS
    seed = js.split("function seedState(")[1].split("\n  function ")[0]
    # skeleton container + ghost/placeholder line + ghost dots + the one real today dot
    assert "tl-seed" in seed
    assert "tl-seed-ghost" in seed or "tl-seed-line" in seed
    assert "tl-seed-dot" in seed
    assert "tl-seed-today" in seed
    # locked preview chips (the removed Compare / Time Machine chips are gone)
    assert "tl-lock" in seed
    assert "unlocks at 2 days" in seed
    for label in ("Streak", "Moment discs", "Shape changes"):
        assert label in seed, label
    assert "Time Machine" not in seed
    assert "Forecast" not in seed              # forecast feature removed


def test_dashboard_js_seed_state_history_meter() -> None:
    """#20: a "History: N of 3 days" meter (3 = snapshots needed to unlock the full
    timeline; history itself is uncapped). Renders in both the <2 and ==2 branches."""
    js = assets.DASHBOARD_JS
    seed = js.split("function seedState(")[1].split("\n  function ")[0]
    assert "tl-histmeter" in seed
    assert "History" in seed
    assert "of 3 " in seed
    assert "of 60" not in seed                  # the old 60-day cap framing is gone
    # N is the snapshot count, capped at the unlock target
    assert "H.trend.dates" in seed or "dates.length" in seed
    assert "Math.min(" in seed


def test_dashboard_js_seed_state_day_two_compact_diff() -> None:
    """#20 (==2 snapshots): a compact "in 1 day you advanced N (+X%)" line built via
    diffCounts, with the A/B picker hidden (dateDiffPanel not invoked in this branch)."""
    js = assets.DASHBOARD_JS
    seed = js.split("function seedState(")[1].split("\n  function ")[0]
    # the two-snapshot branch keys off the snapshot count == 2
    assert "=== 2" in seed or "== 2" in seed or "length===2" in seed or "length === 2" in seed
    # reuses the diff engine, not a reinvention
    assert "diffCounts(" in seed
    # the compact advanced phrasing
    assert "advanced" in seed
    assert "in 1 day" in seed or "1 day" in seed
    # A/B picker stays hidden in this branch: no dateDiffPanel call inside seedState
    assert "dateDiffPanel()" not in seed


def test_dashboard_js_seed_state_respects_reduced_motion() -> None:
    """#20 / D6: the skeleton shimmer is suppressed under reduced-motion via the shared
    __cfdNoAnim / matchMedia gate (a no-shimmer class variant)."""
    js = assets.DASHBOARD_JS
    seed = js.split("function seedState(")[1].split("\n  function ")[0]
    assert "__cfdNoAnim" in seed or "prefers-reduced-motion" in seed


def test_dashboard_css_styles_seed_state_classes() -> None:
    """#20: the seed-state classes are theme-safe (built from tokens). The skeleton
    shimmer keyframe is neutralised under prefers-reduced-motion."""
    css = assets.DASHBOARD_CSS
    for selector in (".tl-seed", ".tl-lock", ".tl-histmeter"):
        assert selector in css, selector
    seed_block = css.split(".tl-seed{")[1].split("}")[0]
    assert "var(--" in seed_block
    lock_block = css.split(".tl-lock{")[1].split("}")[0]
    assert "var(--" in lock_block
    meter_block = css.split(".tl-histmeter{")[1].split("}")[0]
    assert "var(--" in meter_block
    # the shimmer is animated and reduced-motion neutralises it
    rm_block = css.split("@media (prefers-reduced-motion:reduce){")[1].split("}}")[0]
    assert "tl-seed" in rm_block


def test_dashboard_js_has_timeline_mode_toggle() -> None:
    # the single Time toggle (Save = default/off) + its Hours/Days/Months bucket sub-toggle
    # + the bucketing engine + the datetime-safe date parser are inlined into the report.
    html = assets.build_html(_model())
    assert "data-tlgrantoggle" in html and "data-tlbucket" in html
    assert "tlGranToggle" in html
    assert "setGranularity" in html and "applyGranularity" in html and "setBucket" in html
    assert ">Time<" in html and ">Save<" not in html      # single Time toggle, no Save button
    for unit in ('["day","Days"]', '["month","Months"]'):
        assert unit in html, unit
    assert '["hour","Hours"]' not in html               # Hours bucket removed
    assert "function bucketedTrend(" in html and "function bucketKey(" in html
    assert "fineKind" in html and "fineUnits" in html   # commit/save wording switch
    assert ".tl-granbar" in html and ".tl-bucket" in html   # toggle styling
    assert "function cfdDate" in html            # datetime-safe key parser (no T+T crash)


def test_boot_error_page_is_visible_and_designed() -> None:
    """B1: start()'s catch must lift the body{opacity:0} first-paint gate (add "ready")
    and render the designed error card — otherwise a broken model leaves a blank page."""
    js = assets.DASHBOARD_JS
    catch_block = js.split(".catch(function(err){", 1)[1].split("});", 1)[0]
    assert 'document.body.classList.add("ready")' in catch_block
    assert 'setAttribute("data-theme", state.theme)' in catch_block   # saved/OS theme honoured
    assert 'class="err-card"' in catch_block and "err-mark" in catch_block
    assert "This report couldn’t load its data." in catch_block       # plain-language line
    assert 'role="alert"' in catch_block
    assert "err-msg" in catch_block and "esc(err && err.message" in catch_block  # technical detail, escaped
    assert "system-ui,sans-serif" not in catch_block   # old bare inline-styled <p> is gone


def test_boot_error_card_css_is_theme_safe_pure_css() -> None:
    """B1: the error card is styled from theme tokens (works in dark AND light) and the
    rainbow brand mark is a hard-coded gradient — no dependency on the (failed) model."""
    css = assets.DASHBOARD_CSS
    wrap = css.split(".err-wrap{", 1)[1].split("}", 1)[0]
    assert "center" in wrap                                    # centred card
    card = css.split(".err-card{", 1)[1].split("}", 1)[0]
    assert "var(--surface)" in card and "var(--border)" in card
    title = css.split(".err-title{", 1)[1].split("}", 1)[0]
    assert "var(--text)" in title
    msg = css.split(".err-msg{", 1)[1].split("}", 1)[0]
    assert "var(--muted)" in msg and "monospace" in msg        # small monospace detail line
    mark = css.split(".err-mark{", 1)[1].split("}", 1)[0]
    assert "linear-gradient" in mark and "var(--c" not in mark  # pure-CSS rainbow, no --cN data


def test_print_coverage_uses_active_scope_not_focused_master_only() -> None:
    """B2: the printed "Coverage by category" section goes through covRows(), so printing
    from the global (no master focused) view gets the font-wide merge instead of nothing."""
    js = assets.DASHBOARD_JS
    rows_fn = js.split("function printCoverageRows(", 1)[1].split("\n  function ", 1)[0]
    assert 'covRows("byCategory")' in rows_fn                  # shared scope-aware rows
    assert "cov[state.master]" not in rows_fn                  # no focused-master-only lookup
    assert "H.coverage.byCategory" not in rows_fn
    assert "r.glyphs != null ? r.glyphs : r.total" in rows_fn  # same count rule as on-screen
    # still wired into the print report
    assert 'add("psec-coverage", "Coverage by category", printCoverageRows())' in js


def test_leaderboard_has_no_aa_chip() -> None:
    """The "Aa" letterform chip was removed from each "Furthest along" row — no builder,
    no markup, no CSS."""
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    assert "function lbChip(" not in js and "lbChip(" not in js
    row_fn = js.split("function lbRow(", 1)[1].split("\n  function ", 1)[0]
    assert "lb-chip" not in row_fn
    assert ".lb-chip{" not in css and ".lb-chip svg{" not in css
    assert "pv:m.preview" not in js.split("function leaderboard(", 1)[1].split("\n  function ", 1)[0]


# --------------------------------------------------------------------------- #
# Non-exporting glyphs: ALWAYS excluded from every count and percentage
# --------------------------------------------------------------------------- #

def test_dashboard_js_has_centralised_counted_set_helper() -> None:
    """One countedSet() helper centralises the always-on exclusion: null when
    everything counts (no non-exporting glyphs), else a {name:1} lookup of
    counted glyphs. isCounted/countedTotal wrap it."""
    js = assets.DASHBOARD_JS
    assert "function countedSet(" in js
    assert "function isCounted(" in js
    assert "function countedTotal(" in js
    counted = js.split("function countedSet(")[1].split("\n  function ")[0]
    # nothing-to-exclude -> null (everything counts, zero overhead); otherwise
    # the exclusion applies UNCONDITIONALLY — no state/toggle gate.
    assert "if (!(H.nonExporting||[]).length) return null;" in counted
    assert "state." not in counted


def test_dashboard_js_has_no_exporting_only_toggle() -> None:
    """The exclusion is always on: no toolbar toggle, no setter, no state field,
    no pref seeding — the toolbar keeps only Overview / Timeline (Export moved to
    the header, next to the theme toggle)."""
    js = assets.DASHBOARD_JS
    assert "cfd-exo" not in js                               # old toggle id (cfd-export survives)
    assert "setExporting" not in js
    assert "state.exporting" not in js
    assert "H.exporting" not in js
    assert "Exporting only" not in js
    toolbar = js.split("function toolbar(")[1].split("\n  function ")[0]
    assert toolbar.count("<button") == 2                     # Overview + Timeline only
    assert "cfd-export" not in toolbar                       # export left the toolbar
    header = js.split("function header(")[1].split("\n  function ")[0]
    assert 'id="cfd-export"' in header and 'class="icon"' in header   # now a header icon button
    assert "􀈂" in header                                     # SF Symbol square.and.arrow.up


def test_dashboard_js_percentage_helpers_use_counted_denominators() -> None:
    """Every completion percentage always excludes non-exporting glyphs: the
    ring/donut (gradedOverallPct/aggExclusive), the leaderboard
    (gradedMasterPct), the graded line (gradedPctAt), the stream + navigator
    denominators, and the lanes (laneGradedPctOne)."""
    js = assets.DASHBOARD_JS
    assert "function gradedMasterPct(m){ var n=countedTotal()" in js
    graded_at = js.split("function gradedPctAt(")[1].split("\n  function ")[0]
    assert "countedTotal()" in graded_at and "isCounted(name)" in graded_at
    overall_pct = js.split("function gradedOverallPct(")[1].split("\n  function ")[0]
    assert "countedTotal()" in overall_pct
    agg_excl = js.split("function aggExclusive(")[1].split("\n  function ")[0]
    assert "countedSet()" in agg_excl
    lane_one = js.split("function laneGradedPctOne(")[1].split("\n  function ")[0]
    assert "isCounted(names[i])" in lane_one
    stream = js.split("function streamParts(")[1].split("\n  function tlSpanToggle(")[0]
    assert "countedTotal()" in stream and "isCounted(name)" in stream
    nav = js.split("function navOverallSeries(")[1].split("\n  function ")[0]
    assert "countedTotal()" in nav and "isCounted(name)" in nav


def test_dashboard_js_coverage_rows_recomputed_under_exclusion() -> None:
    """Coverage rows (category card + script grid + print) recompute client-side
    from the raw m.keys when the exclusion is active — the shipped H.coverage
    stays the all-glyphs truth (parity invariant)."""
    js = assets.DASHBOARD_JS
    assert "function covRowsCounted(" in js
    cov = js.split("\n  function covRows(")[1].split("\n  function ")[0]
    assert "covRowsCounted(which)" in cov
    assert "countedSet()" in cov


def test_dashboard_js_heatmap_dims_excluded_cells_instead_of_hiding() -> None:
    """Excluded glyphs stay visible in the heatmap but DIM (.ncnt, opacity ~0.35)
    with a '— not counted' tooltip suffix — they never vanish from the grid."""
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    cell = js.split("function cellHTML(")[1].split("\n    var sections")[0]
    assert "isCounted(name)" in cell
    assert '" — not counted"' in cell
    assert "' ncnt'" in cell
    assert ".cell.ncnt{opacity:.35}" in css


def test_dashboard_js_counted_stats_mirror_raw_counts_shape() -> None:
    """countedStats(m) recomputes the m.counts / m.uncolored equivalents from the
    raw keys as the suffix-sum cumulative ('reached k or beyond') of the exclusive
    distribution; countFor/uncoloredFor route through it whenever the font has
    non-exporting glyphs (raw passthrough otherwise)."""
    js = assets.DASHBOARD_JS
    stats = js.split("function countedStats(")[1].split("\n  function ")[0]
    assert "run += dist[key]||0; counts[key] = run;" in stats   # suffix-sum cumulative
    assert "H.mode" not in js                                   # no mode switch anywhere
    count_for = js.split("function countFor(")[1].split("\n  function ")[0]
    assert "countedSet()" in count_for and "countedStats(m)" in count_for
    assert "m.counts[String(k)]" in count_for                # raw truth when nothing to exclude
    assert "function uncoloredFor(" in js


def test_flow_bands_softened_with_top_stroke_and_smaller_dots() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    # Lower band fill opacity + a per-band top-edge stroke (same colour, higher opacity).
    assert ".tl-band{stroke:none;fill-opacity:.4}" in css
    assert ".tl-band-top{" in css and "opacity:.92" in css
    assert 'class="tl-band-top"' in js
    assert 'stroke="var('+"'"+"+varFor(k)+" in js or 'class="tl-band-top"' in js
    # White snapshot dots shrunk (flow view 2.5 -> 1.8).
    assert 'r="1.8"' in js


def test_disc_intro_blooms_via_crossfade_not_a_conic_wipe() -> None:
    js = assets.DASHBOARD_JS
    # Opening intro cross-fades the grey base into the colour field (alpha * eased reveal),
    # instead of the old hard pie-wedge clip.
    assert "g.globalAlpha=DISC_ALPHA*reveal" in js
    assert "-Math.PI/2+reveal*Math.PI*2" not in js          # the conic-wipe clip is gone


def test_before_after_is_a_switch_with_play_autoswitch() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    assert "ba-toggle" not in js                             # old single chip replaced
    assert 'class="ba-seg' in js and 'data-ba="before"' in js and 'data-ba="after"' in js
    assert 'class="ba-play' in js and "data-baplay" in js
    # Play mode flips before/after every second and self-stops when the control unmounts.
    assert "setInterval(" in js and "}, 1000)" in js
    assert "state.before = !state.before" in js
    assert ".ba-seg" in css and ".ba-play" in css


def test_overview_has_no_across_masters_card() -> None:
    # The "Across masters" (cross-master) card was removed from the Overview.
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    assert "crossMasterCard" not in js
    assert "Across masters" not in js
    assert "data-cmdiffer" not in js and "cmDifferOpen" not in js
    extras = js.split("function overviewExtras(")[1].split("}")[0]
    assert "crossMasterCard()" not in extras
    assert ".cm-headline" not in css and ".cm-differ-panel" not in css


def test_master_card_has_version_navigator() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    # A dot-per-snapshot timeline above the master's distribution bar, hidden under 2 versions.
    assert "function versionNav(" in js
    assert "dates.length < 2" in js
    assert 'data-vnav="' in js
    # the timeline lives in its OWN card (versionCard), rendered ABOVE the master progress card
    assert "function versionCard(" in js
    vc = js.split("function versionCard(", 1)[1].split("\n  function ", 1)[0]
    assert "versionNav()" in vc and "vnav-card" in vc
    tabs = js.split("function tabsView(", 1)[1].split("\n  function ", 1)[0]
    assert "versionCard()" in tabs and tabs.index("versionCard()") < tabs.index("masterOverall(m)")
    mo = js.split("function masterOverall(", 1)[1].split("\n  function ", 1)[0]
    assert "versionNav()" not in mo                                 # lifted out of the progress card
    # Clicking a dot scrubs that master to the picked snapshot (reuses scrubSet).
    assert 'closest("[data-vnav]")' in js and "scrubSet(parseInt(vn.getAttribute" in js
    # The bar/% become scrub-aware: reconstructed from stateAt + gradedPctAt at the version.
    assert "stateAt(m.id, date)" in mo and "gradedPctAt(m.id, date)" in mo
    assert ".vnav-dot" in css and ".vnav-line" in css and ".vnav-card{" in css


def test_version_nav_skips_unchanged_versions_for_selected_master() -> None:
    """In the per-master card, the version timeline only shows a dot where THAT
    master's colours changed vs the previous snapshot (a static master collapses to
    its baseline). data-vnav keeps the absolute series index so scrubbing still
    lands on the right date; global view (no master) still shows every version."""
    js = assets.DASHBOARD_JS
    vn = js.split("function versionNav(", 1)[1].split("\n  function ", 1)[0]
    assert "var mid = state.master" in vn
    # builds the changed-index list by diffing this master's stateAt across dates
    assert "stateAt(mid, dates[0])" in vn and "stateAt(mid, dates[k])" in vn
    assert "vidx.push(k)" in vn
    # global fallback shows every version
    assert "dates.map(function(_d, i){ return i; })" in vn
    # the dot still carries the ABSOLUTE index (di) for scrubSet
    assert 'data-vnav="\'+di+\'"' in vn
    # current/fill track the filtered position, not the absolute index
    assert "activePos" in vn and "activePos/(vidx.length-1)" in vn


# --------------------------------------------------------------------------- #
# Global Timeline: median + min-max spread band (scales to many masters)
# --------------------------------------------------------------------------- #


def test_timeline_global_is_band_only() -> None:
    js = assets.DASHBOARD_JS
    assert "function trendBandParts(" in js and "function pctMatrix(" in js
    # the grid + heatmap views and their toggle were trashed -- only the band remains
    assert "function masterGridParts(" not in js
    assert "function masterHeatParts(" not in js
    assert "function tlViewToggle(" not in js and "function setTlView(" not in js
    assert "state.tlView" not in js and "data-tlview" not in js


def test_timeline_band_is_the_global_view() -> None:
    js = assets.DASHBOARD_JS
    tv = js.split("function timelineView(", 1)[1].split("\n  function ", 1)[0]
    # focused master -> colour Flow; global -> the band, no view toggle
    assert "(state.master != null) ? streamParts(680, 200) : trendBandParts(680, 200)" in tv
    assert "rangeNav(680)" in tv and "tlViewToggle" not in tv


def test_timeline_pct_matrix_cached_excludes_scrub() -> None:
    js = assets.DASHBOARD_JS
    assert "function pctMatrix(" in js and "PMCACHE" in js and "PMCACHE_KEY" in js
    pm = js.split("function pctMatrix(", 1)[1].split("\n  function ", 1)[0]
    assert "gradedPctAt(" in pm
    assert "state.viewLo" in pm and "state.viewHi" in pm     # window busts the cache
    assert "state.tlScrub" not in pm                         # scrubbing must NOT bust it


def test_timeline_band_median_minmax() -> None:
    js = assets.DASHBOARD_JS
    band = js.split("function trendBandParts(", 1)[1].split("\n  function ", 1)[0]
    assert "smoothPath(" in band
    assert "tl-spread-fill" in band and "tl-spread-med" in band and "tl-spread-dot" in band
    assert 'class="tl-chart' in band and "data-snaps" in band   # click-to-scrub for free
    assert 'class="tl-band"' not in band                        # no collision with Flow streamgraph
    assert "col.sort(" in band                                  # median/min/max from sorted column


def test_timeline_band_css_and_reduced_motion() -> None:
    css = assets.DASHBOARD_CSS
    for cls in (".tl-spread-fill", ".tl-spread-med", ".tl-spread-dot", ".tl-cap"):
        assert cls in css, cls
    assert ".tl-mgrid" not in css and ".tl-heatcell" not in css and ".tl-viewbar" not in css
    rm = css.split("prefers-reduced-motion", 1)[1].split("}}", 1)[0]
    assert ".tl-anim .tl-spread-med{animation:none" in rm


# --------------------------------------------------------------------------- #
# Brand colour (#9f75ff) replaces the old blue accent in both themes
# --------------------------------------------------------------------------- #


def test_accent_is_brand_purple_both_themes() -> None:
    css = assets.DASHBOARD_CSS
    # both theme blocks now use the Color Flow purple, not the old blues
    assert css.count("--accent:#9f75ff") == 2
    assert "#6e7bff" not in css and "#5b62ff" not in css
    # everything still consumes it through the var, so one swap repaints buttons/bars/etc.
    assert ".lb-bar>span{display:block;height:100%;background:var(--accent)" in css


# --------------------------------------------------------------------------- #
# Overview ring: left-aligned, wider legend columns, draw-in + count-up
# --------------------------------------------------------------------------- #


def test_overview_ring_left_aligned_and_wider_legend() -> None:
    css = assets.DASHBOARD_CSS
    assert ".ov-ringonly{flex-direction:column;align-items:flex-start" in css   # ring sits left
    assert "justify-content:flex-start" in css.split(".ov-ringrow{", 1)[1].split("}", 1)[0]
    legend = css.split(".ov-legend{", 1)[1].split("}", 1)[0]
    assert "gap:4px 44px" in legend                                             # wide column gap + roomy rows
    # zebra striping: alternate visual rows (3-col grid) get a faint tint so lines read as a table
    assert ".ov-leg-item:nth-child(6n+4)" in css
    # extra breathing room between the colour label and its %
    assert "padding-left:44px" in css.split(".ov-leg-pct{", 1)[1].split("}", 1)[0]


def test_overview_ring_draw_in_and_count_up() -> None:
    js = assets.DASHBOARD_JS
    css = assets.DASHBOARD_CSS
    # CSS: ONE global progression sweep (a single mask arc), not per-segment; reduced-motion off
    assert "@keyframes ovRingSweep" in css
    assert ".ov-ring.ov-anim .ov-ring-reveal{animation:ovRingSweep" in css
    assert "animation-delay:var(--d" not in css                  # no per-segment stagger
    rm = css.split("prefers-reduced-motion", 1)[1].split("}}", 1)[0]
    assert ".ov-ring.ov-anim .ov-ring-reveal{animation:none" in rm
    # JS: ring() takes an anim flag -> wraps the arcs in one sweep mask + data-to for the count-up
    ring_fn = js.split("function ring(p, segs, opts)", 1)[1].split("\n  function ", 1)[0]
    assert "anim = !!opts.anim" in ring_fn
    assert '" ov-anim"' in ring_fn and "--d:" not in ring_fn      # global, no per-segment vars
    assert "ov-ring-reveal" in ring_fn and 'mask="url(#ovRingReveal)"' in ring_fn
    assert 'data-to="\'+p+\'"' in ring_fn
    overall = js.split("function overall(", 1)[1].split("\n  function ", 1)[0]
    assert "anim:barsAnim" in overall
    # the % count-up reuses tweenNumber and is gated to the intro on first paint
    assert "function animateRingNumber(" in js
    upd = js.split("function update(", 1)[1].split("\n  function ", 1)[0]
    assert "animateRingNumber(barsAnim)" in upd


# --------------------------------------------------------------------------- #
# Furthest along: two columns, progress bar always visible
# --------------------------------------------------------------------------- #


def test_leaderboard_two_columns_wide_bar_all_rows() -> None:
    css = assets.DASHBOARD_CSS
    js = assets.DASHBOARD_JS
    body = css.split(".ovc-leaderboard .ov-card-body{", 1)[1].split("}", 1)[0]
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in body              # two columns
    bar = css.split(".lb-bar{", 1)[1].split("}", 1)[0]
    assert "flex:0 0 104px" in bar                                              # fixed narrow bar -> every bar equal, more room for names
    name = css.split(".lb-n{", 1)[1].split("}", 1)[0]
    assert "flex:1 1 auto" in name                                             # name grows into the freed space
    # zebra striping: alternate rows (2-col grid) get a faint tint so rows read as a table
    assert ".ovc-leaderboard .lb-row:nth-child(4n+3)" in css
    lb = js.split("function leaderboard(", 1)[1].split("\n  function ", 1)[0]
    # every master shown, fully (no scroll, no "Show all"): non-expandable card, no top-N slice
    assert ".slice(0,10)" not in lb and "rows.length>10" not in lb
    assert 'ovCard("leaderboard", "Furthest along", bars, false)' in lb
    assert "lbRow(r, barsAnim, i)" in lb                                        # bars animate on first paint
    lbrow = js.split("function lbRow(", 1)[1].split("\n  function ", 1)[0]
    assert 'class="lb-bar"' in lbrow                                            # every row draws the bar
    assert "lb-fill" in lbrow and "intro" in lbrow                             # grow-in fill markup
    assert ".lb-fill.intro{animation:segGrow" in css                           # the load animation
    # focusing a master from the leaderboard clears the colour filter
    click = js.split('closest(".lb-row[data-m]")', 1)[1].split("return;", 1)[0]
    assert "state.focus = null" in click


# --------------------------------------------------------------------------- #
# Sliding segmented switches + grid "recently modified" filter + Timeline merge
# --------------------------------------------------------------------------- #


def test_segmented_switches_and_grid_filter() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    # a sliding-highlight segmented switch, shared by the grid sort + the Timeline toggle
    assert ".segsw{position:relative;display:grid" in css
    seg = css.split(".segsw-hl{position:absolute", 1)[1].split("}", 1)[0]
    assert "transform:translateX(calc(var(--seg,0)*100%))" in seg and "transition:transform" in seg
    rm = css.split("prefers-reduced-motion", 1)[1].split("}}", 1)[0]
    assert ".segsw-hl{transition:none" in rm
    heat = js.split("function heatmap(", 1)[1].split("\n  function ", 1)[0]
    assert 'class="segsw hsort"' in heat and "--seg:'+(state.heatSort" in heat   # grid sort is a segsw
    assert "function tlPaneSwitch(" in js and 'class="segsw tl-paneswitch"' in js
    # recently-modified grid filter (opt-in) keeps only glyphs in the changeset since last run
    assert "if (state.heatRecent && Object.keys(ch).length){" in heat
    assert "ch[it[0]] != null" in heat
    assert 'data-heatrecent="1"' in heat


def test_segmented_switch_purple_morph_and_graph_info() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    # the active pill is purple (brand accent); the active label is white
    seg = css.split(".segsw-hl{position:absolute", 1)[1].split("}", 1)[0]
    assert "background:color-mix(in srgb,var(--accent)" in seg   # purple, dimmed (less bright)
    assert ".segsw>button[aria-pressed=true]{color:#fff" in css
    # the pill MORPHS old->new on click via a keyframe (innerHTML rebuild kills CSS transitions)
    assert ".segsw-hl.anim{animation:segswSlide" in css
    assert "@keyframes segswSlide" in css and "var(--seg-from" in css and "var(--seg-to" in css
    rm = css.split("prefers-reduced-motion", 1)[1].split("}}", 1)[0]
    assert ".segsw-hl.anim{animation:none" in rm
    # shared helper remembers the previous segment per switch key + arms the slide on click
    assert "function segHL(" in js and "segswPrev" in js and "segswAnimKey" in js
    assert 'segswAnimKey = "tlpane"' in js and 'segswAnimKey = "hsort"' in js
    assert 'segHL("tlpane"' in js and 'segHL("hsort"' in js
    # the Graph/Calendar switch sits on the LEFT; an (i) info button (top-right OVER the chart)
    # carries the band caption as a CSS hover/focus tooltip (native title is unreliable in WebKit)
    assert ".tl-graphcard-h{display:flex;justify-content:space-between" in css
    assert ".tl-info{" in css and ".tl-info-tip{" in css
    info = js.split("function tlGraphInfo(", 1)[1].split("\n  function ", 1)[0]
    assert "Median completion over time" in info and 'class="tl-info"' in info
    assert 'class="tl-info-tip"' in info and 'role="tooltip"' in info


def test_scrub_and_master_switch_animations() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    # scrub sets a one-shot flag, consumed after the render
    scrubset = js.split("function scrubSet(", 1)[1].split("\n  function ", 1)[0]
    assert "scrubAnim = true" in scrubset
    upd = js.split("function update(){", 1)[1].split("\n  function ", 1)[0]
    assert "scrubAnim = false" in upd                       # consumed once per picked moment
    # #5: the category bars + glyph cells get a scrub class; the global ring re-sweeps
    assert '(scrubAnim?" scrub":"")' in js
    assert "anim:barsAnim||scrubAnim" in js                 # global ring sweeps on scrub
    assert ".cov-bar.scrub{" in css and "@keyframes covGrow" in css
    assert ".heat.scrub .cell{" in css and "@keyframes cellPop" in css
    # #2: lane sparklines carry a key and morph between moments via a JS point-tween
    assert 'data-spark="' in js and "function morphSparks(" in js
    assert "morphSparks(scrubAnim)" in upd
    assert "requestAnimationFrame" in js and "sparkPrev" in js
    # #9: Global<->Focus master switch fades ONLY the data panels (not the chrome, and NOT the
    # whole disc tower — the tower runs its own per-disc focus crossfade)
    assert "lastRenderMaster" in upd and "fadeData()" in upd
    fd = js.split("function fadeData(", 1)[1].split("\n  function ", 1)[0]
    # only inner data graphics fade, never the card frames (no .overall/.sgrid card containers)
    # only the headline ring + its legend fade on a focus switch; categories, cells and lanes
    # just update in place (no flash)
    assert ".ov-ring" in fd and ".ov-legend" in fd and 'classList.add("cfd-fade")' in fd
    assert ".overall" not in fd and ".sgrid" not in fd and ".cov-bar" not in fd
    assert ".heat .grid" not in fd and ".tl-lanes" not in fd
    assert "cfd-tower-cv" not in upd                        # tower no longer whole-canvas fades
    assert ".cfd-fade{animation:cfdFade" in css and "@keyframes cfdFade" in css
    # all of these are silenced under reduced motion
    rm = css.split("prefers-reduced-motion", 1)[1].split("}}", 1)[0]
    assert ".cfd-fade{animation:none" in rm and ".cov-bar.scrub{animation:none" in rm
    assert ".heat.scrub .cell{animation:none" in rm


def test_glyph_cell_size_slider() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    heat = js.split("function heatmap(", 1)[1].split("\n  function masterPct(", 1)[0]
    # a range slider in the grid header drives the cell size; the section carries the var
    assert "data-cellsize" in heat and 'type="range"' in heat and 'class="cell-size"' in heat
    assert "--cell-min:" in heat
    assert "state.cellSize" in js                                   # default + live update
    # the grid columns honour the var (falling back to 40px)
    assert "minmax(var(--cell-min,40px),1fr)" in css and ".cell-size{" in css
    # live resize without a full re-render: an input listener sets the CSS var directly
    inp = js.split('addEventListener("input"', 1)[1].split("});", 1)[0]
    assert 'setProperty("--cell-min"' in inp and "state.cellSize = v" in inp


def test_timeline_graph_and_calendar_share_one_card() -> None:
    js = assets.DASHBOARD_JS
    tv = js.split("function timelineView(", 1)[1].split("\n  function ", 1)[0]
    # one card, switched between the graph pane and the calendar pane (never both)
    assert "tl-graphcard" in tv
    assert "var graphPane" in tv and "var calPane" in tv
    assert 'state.tlPane === "calendar"' in tv
    assert "tlSpanToggle()" in tv                 # range presets live next to the graph
    # the click handler flips the pane AND resets the picked moment back to latest
    assert 'closest("[data-tlpane]")' in js and "state.tlPane = tp.getAttribute" in js
    pane_click = js.split('closest("[data-tlpane]")', 1)[1].split("return;", 1)[0]
    assert "state.tlScrub = null" in pane_click


def test_lane_sparkline_draws_flat_line_for_single_snapshot() -> None:
    """Category/script lanes show the sparkline LINE at every moment, including the
    first snapshot: a single data point degrades to a flat line across the box (never
    a progress bar)."""
    js = assets.DASHBOARD_JS
    spark = js.split("function laneSparkSVG(", 1)[1].split("\n  function ", 1)[0]
    assert "n === 1" in spark and "n < 1" in spark      # flat line for one point; empty only at zero
    assert "tl-lane-spark" in spark


def test_version_nav_line_draw_animation() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    vn = js.split("function versionNav(", 1)[1].split("\n  function ", 1)[0]
    assert "vnav-fill" in vn and "vnavShouldAnim" in vn          # a progress line + animate-once flag
    # full-width fill clipped to the current node via scaleX, with the previous fraction
    # remembered so the line grows/shrinks from the old node end (not redrawn from the start)
    assert "transform:scaleX(" in vn and "--vnav-from:" in vn and "--vnav-to:" in vn
    assert "vnavPrevFrac" in vn
    # clicking a node arms the draw animation before scrubbing
    click = js.split('closest("[data-vnav]")', 1)[1].split("return;", 1)[0]
    assert "vnavShouldAnim = true" in click
    assert "@keyframes vnavGrow" in css and ".vnav-fill.anim{animation:vnavGrow" in css
    assert "scaleX(var(--vnav-from" in css and "scaleX(var(--vnav-to" in css   # interpolate prev->new
    assert ".vnav-fill{" in css and "width:calc(100% - 10px)" in css           # spans the whole track
    rm = css.split("prefers-reduced-motion", 1)[1].split("}}", 1)[0]
    assert ".vnav-fill.anim{animation:none" in rm


def test_before_after_falls_back_to_journey_history() -> None:
    js = assets.DASHBOARD_JS
    heat = js.split("function heatmap(", 1)[1].split("\n  function ", 1)[0]
    # with no last-run diff, derive each glyph's previous colour from saved history so the
    # Before/After switch still appears + works
    assert "if (!Object.keys(ch).length){" in heat
    assert "jev[jev.length-2][1]" in heat and "ch[gn] = [pk]" in heat


def test_overview_this_week_card() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    assert "function weekProgressCard(" in js
    assert "function gradedOverallPctAt(" in js
    extras = js.split("function overviewExtras(", 1)[1].split("\n  function ", 1)[0]
    assert "weekProgressCard()" in extras                        # on the global Overview
    wk = js.split("function weekProgressCard(", 1)[1].split("\n  function ", 1)[0]
    assert "isoMinusDays(latest, 7)" in wk and "snapDate(dates" in wk
    # past-7-days AND past-30-days deltas, built by the shared wkStat helper
    assert "isoMinusDays(latest, 30)" in wk and "monthDelta" in wk
    assert 'wkStat(delta, "past 7 days")' in wk and '"past 30 days"' in wk
    assert 'ovCard("week"' in wk
    assert ".wk-delta{" in css and ".wk-stat{" in css
    # full-width card; the verbose "complete now · was X% on …" meta line is gone
    assert ".ov-extra .ovc-week{grid-column:1/-1}" in css
    assert "wk-meta" not in wk
    # top 3 most-improved masters (by %) AND the top 3 colours that gained the most glyphs
    assert "Most improved masters" in wk and "Focus of the week" in wk
    assert "colorMoves" in wk and ".slice(0, 3)" in wk
    assert ".wk-extra{" in css and ".wk-sw{" in css and ".wk-list{" in css


def test_timeline_calendar_uses_full_width() -> None:
    css = assets.DASHBOARD_CSS
    # in the Timeline calendar pane the month grid stretches to the full width (1fr columns),
    # overriding the compact centred 28px default used by the Overview mini-calendar
    assert ".tl-calpane .tl-mcal-grid{grid-template-columns:repeat(7,minmax(0,1fr))" in css
    assert "justify-content:stretch" in css


def test_script_lanes_hidden_when_latin_is_the_only_script() -> None:
    js = assets.DASHBOARD_JS
    lanes = js.split("function scriptLanes(", 1)[1].split("\n  function ", 1)[0]
    # a lone-Latin font: the per-script breakdown just mirrors the overall progress, so the
    # whole section is suppressed
    assert "/^latin$/i.test(scripts[0])" in lanes
    assert 'scripts.length === 1' in lanes


def test_category_lanes_use_fixed_canonical_order() -> None:
    js = assets.DASHBOARD_JS
    lanes = js.split("function categoryLanes(", 1)[1].split("\n  function ", 1)[0]
    # lanes keep a stable Glyphs Font-View order (Letter, Number, ...), never reshuffling on
    # scrub/data change; the old laggard-first %-sort is gone
    assert 'CAT_ORDER = ["Letter","Number","Punctuation","Mark","Separator","Symbol","Other"]' in lanes
    assert "CAT_ORDER.indexOf(a.cat)" in lanes
    assert "(a.cur - b.cur)" not in lanes


def test_tower_focus_change_fades_per_disc_not_whole_tower() -> None:
    js = assets.DASHBOARD_JS
    # the previously-selected disc dims out and the new one lights in by EASING each disc's
    # trim toward its target — no instant snap, and no whole-canvas fade
    assert "var FOCUS_STEP = 0.08" in js
    assert "instant switch, no fade" not in js
    # transitioning discs render individually (focusDisc) so their fade is visible; the settled
    # dimmed mass still composites as one layer (group) to avoid overlap seams
    assert "var flushPend = function()" in js
    assert "focusAmt[n2] > 0.005 && focusAmt[n2] < 0.995" in js


def test_glyph_cell_size_slider_allows_smaller_cells() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    heat = js.split("function heatmap(", 1)[1].split("\n  function masterPct(", 1)[0]
    # the cell-size slider runs 20..80
    assert 'class="cell-size" min="20" max="80"' in heat
    # below 26px the category SECTIONS lay out two-up (CSS columns), each block kept whole
    assert "var twoCol = cz < 26" in heat and "heat-2col" in heat and 'class="heat-cats"' in heat
    assert ".heat.heat-2col .heat-cats{column-count:2" in css and "break-inside:avoid" in css
    # the switch happens live while dragging the slider (no full re-render needed)
    inp = js.split('addEventListener("input"', 1)[1].split("});", 1)[0]
    assert 'classList.toggle("heat-2col"' in inp
