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
    assert "legItem(-1, H.noneLabel" in ov                    # includes the None bucket
    assert ".ov-legend{" in css and ".ov-leg-item" in css


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
    # navigator inset to match the chart's inner width (1px border + 4px padding = 5px)
    assert ".tl-nav-wrap{position:relative;margin:6px 0 2px;padding:0 5px}" in css


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


def test_dashboard_calendar_lives_on_overview() -> None:
    js = assets.DASHBOARD_JS
    # the calendar is an Overview card, not part of the Timeline section anymore
    assert "function calendarCard(" in js
    overview_extras = js.split("function overviewExtras(")[1].split("\n  function ")[0]
    assert "calendarCard()" in overview_extras
    # the duplicate Overview chart is gone, so the calendar gets its own full-width slot
    assert '"ov-cal-solo">\'+cal+\'' in overview_extras
    assert "timelineCard()" not in overview_extras
    timeline_view = js.split("function timelineView(")[1].split("\n  function ")[0]
    assert "activityCalendar()" not in timeline_view     # moved off the Timeline tab
    # clicking a day when the Time Machine isn't on screen hops to the Timeline tab
    assert 'state.view = "timeline"' in js
    css = assets.DASHBOARD_CSS
    assert ".ov-cal-solo{" in css


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
    # (raw passthrough; the exporting-only branch reroutes through countedStats).
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
    assert "funnelHTML(function(k){ return countFor(m,k)||0; }, total)" in master_overall
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
    assert "sz = big ? 132" in ring_fn                 # the big Overview hero ring
    # overall() is ring-only: shares fed in, selectable + big, no bar / no funnel
    overall = js.split("function overall(", 1)[1].split("\n  function ", 1)[0]
    assert "ring(compP, ringSegs, {big:true, select:true})" in overall
    assert "ov-ringonly" in overall
    assert 'class="seg' not in overall                 # the stacked makeup bar is gone
    assert "funnelHTML(" not in overall                # the step funnel is gone
    css = assets.DASHBOARD_CSS
    assert ".ov-ring-big .ov-ring-t{font-size:26px" in css   # bigger % text
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
    assert "var chartBlock" in tv
    assert "(state.master != null) ? streamParts(680, 200) : trendParts(680, 200)" in tv
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
    assert "parts.chart+rangeNav(680)+parts.foot" in tv   # chart + (short, full-width) navigator + (empty) foot
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
    heat = js.split("function heatmap(", 1)[1].split("\n  function changes(", 1)[0]
    # scrubbed -> the cells reconstruct the HISTORICAL colour state via stateAt,
    # at the same snapshot index the discs/lanes read (scrubIndex over trend dates)
    assert "state.tlScrub != null" in heat
    assert "stateAt(m.id, sdate)" in heat and "scrubIndex()" in heat
    # the historical key feeds the SAME items[] the cell colour, the focus filter
    # and the by-colour grouping all read, so they stay consistent while scrubbed;
    # glyphs without an event by that date fall back to uncoloured (-1).
    assert "scrubSnap[H.glyphNames[i]] != null ? scrubSnap[H.glyphNames[i]] : -1" in heat
    assert "items.push([H.glyphNames[i], key0, i])" in heat
    # the before/after toggle hides while time-travelling (it compares live runs),
    # and the cell's was/now pair collapses to the historical colour
    assert "(!scrubSnap && Object.keys(ch).length)" in heat
    assert "(!scrubSnap && ch[name] != null)" in heat


def test_dashboard_heatmap_scrub_pill_present_and_dismissible() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    heat = js.split("function heatmap(", 1)[1].split("\n  function changes(", 1)[0]
    # a dismissible pill above the grid names the viewed moment (friendly date)
    assert 'class="heat-pill" role="status"' in heat
    assert "Viewing '+esc(dateLabel(scrubISO))" in heat
    assert "back to today" in heat and 'data-scrubclear="1"' in heat
    # the button clears the picked moment (scrubSet's latest==live reset) and
    # re-renders through the normal update() path so the .cell transition fades
    assert '[data-scrubclear]' in js
    assert "state.tlScrub = null; update();" in js
    # pill styled with theme tokens only, so dark and light both work
    pill_rules = [line for line in css.splitlines() if line.startswith(".heat-pill")]
    assert pill_rules
    assert all("var(--" in rule for rule in pill_rules)
    assert all("#" not in rule for rule in pill_rules)


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
    # duration presets (1D/1W/1M/1Y/All) that drive the zoom window (segmented switch)
    assert "tl-switch" in js and "tl-sw-btn" in js
    assert ".tl-switch" in css and ".tl-spanbar" in css
    assert "function tlSpanToggle(" in js and "function setTlSpan(" in js
    assert "data-tlspan" in js and "tlSpanToggle()" in js   # rendered + injected in the toolbar
    for label in ('"1D"', '"1W"', '"1M"', '"1Y"', '"All"'):
        assert label in js, label


def test_dashboard_has_range_navigator() -> None:
    js, css = assets.DASHBOARD_JS, assets.DASHBOARD_CSS
    assert "function rangeNav(" in js                     # the mini-chart range selector
    assert "function trendSeries(" in js and "function viewBounds(" in js   # zoom-window slicing
    assert "function navDrag(" in js and "function navReset(" in js         # drag + reset handlers
    assert 'data-navedge="mid"' in js and 'data-navedge="lo"' not in js     # mid literal; lo/hi via handle()
    assert "data-navreset" in js                          # reset affordance
    assert ".tl-nav-win" in css and ".tl-nav-h-bar" in css and ".tl-nav-scrim" in css


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
    assert "barsAnim = !introPlayed" in js                       # fill animation only on first paint
    assert "barMaster" not in js                                 # no re-fill on master switch


def test_dashboard_js_clears_focus_when_leaving_overview() -> None:
    js = assets.DASHBOARD_JS
    assert "function toggleView(" in js
    # leaving Overview (any non-"tabs" view) clears the colour focus
    assert 'if (v!=="tabs"){ state.focus = null; }' in js
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
    assert "(state.master != null) ? streamParts(680, 200) : trendParts(680, 200)" in js
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
    # The global Overview extras must NOT call the per-master change feed.
    extras = js.split("function overviewExtras(")[1].split("}")[0]
    assert "recentCard(" not in extras
    # Recent activity lives in the per-master panel instead, scoped to state.master.
    assert "function masterExtras(" in js
    master_extras = js.split("function masterExtras(")[1].split("}")[0]
    assert "recentCard()" in master_extras
    assert "regressionCard()" not in master_extras       # the last-save card was removed
    assert "masterExtras()" in js.split("function tabsView(")[1].split("}")[0]


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
    # headline + done-everywhere bar + identical/differ counts + by-step chips
    assert "done everywhere" in js
    assert "identical in all masters" in js
    assert "differ between masters" in js
    assert "by step:" in js
    assert "(single master)" in js
    assert "cm-differ-list" not in js        # the old flat list stays gone (see disclosure)
    # byStep swatches reuse the shared swatchFor helper (parseInt -> int key)
    assert "swatchFor(key)" in js
    # wired into the global Overview extras
    extras = js.split("function overviewExtras(")[1].split("}")[0]
    assert "crossMasterCard()" in extras


def test_dashboard_js_cross_master_differ_disclosure() -> None:
    """Drill-down: the differ count line becomes a chevron disclosure button
    (aria-expanded + aria-controls) over a max-height panel of glyph-name chips;
    each chip opens the journey modal via the shared data-jglyph delegate."""
    js = assets.DASHBOARD_JS
    card = js.split("function crossMasterCard(")[1].split("\n  function ")[0]
    assert "cm.differGlyphs" in card
    assert 'data-cmdiffer="1"' in card
    assert "aria-expanded" in card
    assert 'aria-controls="cm-differ-panel"' in card
    assert "cm-chev" in card
    # the glyph chips carry data-jglyph so the existing delegate calls openJourney
    assert 'class="cm-dg" data-jglyph=' in card
    assert "openJourney(jr.getAttribute" in js
    # when nothing differs the plain count line stays (no empty disclosure)
    assert "differ between masters" in card
    # open state survives full re-renders
    assert "state.cmDifferOpen" in card
    assert "cmDifferOpen: false" in js


def test_dashboard_js_cross_master_differ_toggle_handler() -> None:
    """The disclosure toggles the DOM in place (classList + aria-expanded, NO full
    update()) so the CSS max-height slide can animate; the window.__cfdNoAnim test
    escape hatch snaps the transition off, mirroring the reduced-motion CSS gate."""
    js = assets.DASHBOARD_JS
    branch = js.split('closest("[data-cmdiffer]")')[1].split("return;")[0]
    assert "state.cmDifferOpen = !state.cmDifferOpen" in branch
    assert 'classList.toggle("open", state.cmDifferOpen)' in branch
    assert 'setAttribute("aria-expanded", state.cmDifferOpen)' in branch
    assert "window.__cfdNoAnim" in branch and '"none"' in branch
    assert "update()" not in branch


def test_dashboard_js_cross_master_step_chips_toggle_focus() -> None:
    """The by-step chips are buttons carrying data-fkey with on/off focus classes,
    so the shared document-level [data-fkey] delegate toggles colour focus on them
    exactly like the Overview ring legend (state.focus + update via setFocus)."""
    js = assets.DASHBOARD_JS
    card = js.split("function crossMasterCard(")[1].split("\n  function ")[0]
    assert "data-fkey=\"'+key+'\"" in card
    assert '<button type="button" class="cm-step' in card
    assert "state.focus === key" in card           # .on / .off mirror the legend
    # the one shared delegate serves both the ring legend and these chips
    assert 'closest("[data-fkey]")' in js
    assert "setFocus(state.focus===fk ? null : fk)" in js


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
    # degrades to a current-% bar at 1-2 snapshots (no sparkline to draw)
    assert "tl-lane-bar" in lanes


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
    # degrades to a current-% bar at 1-2 snapshots (no sparkline to draw)
    assert "tl-lane-bar" in lanes


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


def test_dashboard_js_has_help_panel_and_button() -> None:
    js = assets.DASHBOARD_JS
    assert "function helpPanel(" in js
    assert "function openHelp(" in js
    assert "function closeHelp(" in js
    assert 'id="cfd-help"' in js               # the ? header button
    assert "state.helpOpen" in js
    # the help panel is labels-only: the colour-label legend (+ uncoloured row), titled
    # "Colour labels". The metric glossary (% complete / forecast / regression) is removed.
    help_panel = js.split("function helpPanel(", 1)[1].split("\n  function ", 1)[0]
    assert "H.steps" in help_panel               # legend rows from steps
    assert "Colour labels" in help_panel
    assert "hp-gloss" not in help_panel          # glossary block gone
    assert "forecast" not in help_panel and "regression" not in help_panel


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
    for selector in (".hp-list", ".hp-row", ".hp-n", ".hp-pos", ".rg-sw"):
        assert selector in css, selector


def test_dashboard_css_styles_cross_master_card() -> None:
    css = assets.DASHBOARD_CSS
    # Every class crossMasterCard emits needs a layout rule.
    for selector in (".cm-headline", ".cm-bar", ".cm-line", ".cm-note",
                     ".cm-steps", ".cm-steps-l", ".cm-step", ".cm-step-n"):
        assert selector in css, selector


def test_dashboard_css_styles_cross_master_disclosure() -> None:
    """Drill-down CSS: disclosure header + chevron + sliding panel + glyph chips,
    all on theme variables; the reduced-motion gate kills the max-height slide."""
    css = assets.DASHBOARD_CSS
    for selector in (".cm-differ-h", ".cm-chev", ".cm-differ-panel",
                     ".cm-differ-panel.open", ".cm-dg"):
        assert selector in css, selector
    # NB: split on the line-start rule — the reduced-motion block also mentions
    # .cm-differ-panel (mid-line) and sits earlier in the stylesheet.
    panel = css.split("\n.cm-differ-panel{")[1].split("}")[0]
    assert "max-height:0" in panel and "transition:max-height" in panel
    reduce_block = css.split("@media (prefers-reduced-motion:reduce){")[1].split("\n")[0]
    assert ".cm-differ-panel{transition:none}" in reduce_block
    # the step chips highlight like the ring legend items (.ov-leg-item family)
    assert ".cm-step:hover,.cm-step.on{" in css
    assert ".cm-step.off{opacity:.4}" in css


def test_build_html_wires_all_report_insight_features() -> None:
    """End-to-end smoke: every new render unit + its wiring marker is present in
    the generated document, and the self-contained/no-network invariant holds."""
    html = assets.build_html(_model())
    # render units
    for marker in ("function crossMasterCard(",
                   "function recentCard(", "function categoryLanes(",
                   "function openJourney(", "function helpPanel(",
                   "function journeyOf(", "function stateAt("):
        assert marker in html, marker
    # wiring: header button, cell + row triggers, journey index
    assert 'id="cfd-help"' in html
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
    # journey modal rows + help/legend panel
    for selector in (".jm-list", ".jm-row", ".jm-date", ".jm-lab", ".hp-row"):
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


def test_leaderboard_rows_lead_with_master_letterform_chip() -> None:
    """Each "Furthest along" row starts with the master's own "Aa" outline
    (H.masters[].preview {d, vb}), so a Thin master visibly looks thin and a Black
    looks black. Rows whose master has no preview render exactly as before."""
    js = assets.DASHBOARD_JS
    assert "function lbChip(" in js
    chip_fn = js.split("function lbChip(", 1)[1].split("\n  function ", 1)[0]
    assert 'if (!pv || !pv.d) return "";' in chip_fn            # guard: no preview -> no chip markup
    assert 'class="lb-chip"' in chip_fn
    assert 'aria-hidden="true"' in chip_fn                      # decorative; row title/name carry the label
    assert 'preserveAspectRatio="xMidYMid meet"' in chip_fn     # fit any master's proportions
    assert 'fill="currentColor"' in chip_fn                     # inherits theme text colour
    # the chip leads the row, before the name; rows feed the preview through as r.pv
    row_fn = js.split("function lbRow(", 1)[1].split("\n  function ", 1)[0]
    assert "lbChip(r.pv)" in row_fn
    assert row_fn.index("lbChip(r.pv)") < row_fn.index('class="lb-n"')
    assert "pv:m.preview" in js.split("function leaderboard(", 1)[1].split("\n  function ", 1)[0]


def test_leaderboard_chip_css_is_compact_and_theme_safe() -> None:
    """The chip is a fixed ~28px-tall box styled from theme tokens (dark AND light),
    and the .lb-n name column keeps its flex-basis so names don't get cropped."""
    css = assets.DASHBOARD_CSS
    chip = css.split(".lb-chip{", 1)[1].split("}", 1)[0]
    assert "flex:0 0 40px" in chip and "height:28px" in chip    # compact fixed box keeps rows aligned
    assert "color:var(--text)" in chip and "opacity:.85" in chip
    chip_svg = css.split(".lb-chip svg{", 1)[1].split("}", 1)[0]
    assert "display:block" in chip_svg
    # name column untouched: same basis collapsed and expanded as before the chip
    assert ".lb-n{flex:0 0 96px" in css
    assert ".ov-card.open .lb-n{flex-basis:170px}" in css
    # no new animation machinery rode in with the chip
    assert "lb-chip" not in css.split("@media (prefers-reduced-motion:reduce)", 1)[1].split("\n", 1)[0]


def test_dashboard_js_recipe_card_replaces_overall_text_line() -> None:
    """Recipes no longer render as a muted one-line footnote inside the global
    overall() section — they get a proper Overview card (ovCard pattern) gated on
    H.recipes, wired into the overviewExtras grid AND appended to the printed
    Overview section so the PDF keeps the recipe data. The focused-master view
    keeps its own per-master recipe-adjusted footnote."""
    js = assets.DASHBOARD_JS
    overall = js.split("function overall(", 1)[1].split("\n  function ", 1)[0]
    assert "Recipe-adjusted" not in overall          # old inline line removed
    assert "recipeLine" not in overall
    assert "function recipeCard(" in js
    card = js.split("function recipeCard(", 1)[1].split("\n  function ", 1)[0]
    assert "H.recipes && H.recipes.length" in card   # gate: no recipes -> no card
    assert 'return ""' in card
    assert 'ovCard("recipes"' in card
    extras = js.split("function overviewExtras(", 1)[1].split("}", 1)[0]
    assert "recipeCard()" in extras
    # print: the Overview section keeps the recipe data (card appended to overall())
    assert 'add("psec-overview", "Overview", overall()+recipeCard());' in js
    master = js.split("function masterOverall(", 1)[1].split("\n  function ", 1)[0]
    assert "Recipe-adjusted" in master               # focused-master footnote stays


def test_dashboard_js_recipe_card_lists_recipes_and_master_bars() -> None:
    """Card body: a one-line global summary on top (X/Y + % + recipe count), then
    one row per recipe (display name with a fallback for nameless configs, the
    human match-rule summary, kept-step count) and a compact recipe-adjusted
    progress bar per master reusing the existing .lb-bar track/fill styles with
    X/Y counts; a single-master file gets one anonymous bar (no master name)."""
    js = assets.DASHBOARD_JS
    card = js.split("function recipeCard(", 1)[1].split("\n  function ", 1)[0]
    assert 'class="rcp-sum"' in card and "Recipe-adjusted" in card
    assert "H.recipes.length===1" in card            # "recipe" vs "recipes" plural
    assert "H.recipeCompletion" in card              # render-only: Python computes it
    assert 'class="rcp-name"' in card and "recipeMatchLabel(r.match)" in card
    assert '"Recipe "+(i+1)' in card                 # nameless recipes get a fallback
    assert 'class="rcp-rule"' in card and 'class="rcp-steps"' in card
    assert 'class="lb-bar"' in card                  # existing progress-bar styles
    assert 'class="rcp-m-c"' in card                 # the X/Y count per master bar
    assert "H.masters.length === 1" in card          # single master -> one bare bar
    assert 'class="rcp-m-n"' in card                 # master name on multi-master rows


def test_dashboard_js_recipe_match_label_humanises_rules() -> None:
    """recipeMatchLabel turns a recipe's match dict into editor-vocabulary prose
    (Category/Script/Subcategory/Case, joined with a middle dot); the stringified
    GS case enum maps back to its human name; empty/absent criteria are skipped."""
    js = assets.DASHBOARD_JS
    assert "function recipeMatchLabel(" in js
    helper = js.split("function recipeMatchLabel(", 1)[1].split("\n  function ", 1)[0]
    assert "RECIPE_FIELDS" in helper and "RECIPE_CASES" in helper
    for label in ('"category","Category"', '"script","Script"',
                  '"subCategory","Subcategory"', '"case","Case"'):
        assert label in js
    for case_pair in ('"1":"Uppercase"', '"2":"Lowercase"',
                      '"3":"Smallcaps"', '"4":"Minor"'):
        assert case_pair in js
    assert 'parts.join(" · ")' in helper
    assert 'value == null || value === ""' in helper  # absent criteria skipped


def test_dashboard_css_styles_recipe_card() -> None:
    """Recipe-card CSS: every class is token-driven (--text/--muted/--track…) so
    both themes and print stay right; the rule summary ellipsises instead of
    wrapping; no animation rides in (nothing for the reduced-motion gate). The
    old .ov-recipe footnote class survives for the focused-master view."""
    css = assets.DASHBOARD_CSS
    for selector in (".rcp-sum{", ".rcp-row{", ".rcp-name{", ".rcp-rule{",
                     ".rcp-steps{", ".rcp-masters{", ".rcp-m{", ".rcp-m-n{",
                     ".rcp-m-c{"):
        assert selector in css
        block = css.split(selector, 1)[1].split("}", 1)[0]
        assert "animation" not in block and "transition" not in block
    rule = css.split(".rcp-rule{", 1)[1].split("}", 1)[0]
    assert "ellipsis" in rule and "var(--muted)" in rule
    assert "var(--muted)" in css.split(".rcp-sum{", 1)[1].split("}", 1)[0]
    assert ".rcp-sum b{color:var(--text)}" in css
    assert ".rcp-m-c b{color:var(--text)}" in css
    assert "var(--track)" in css.split(".rcp-masters{", 1)[1].split("}", 1)[0]
    # nothing new behind the reduced-motion gate
    gate = css.split("@media (prefers-reduced-motion:reduce)", 1)[1].split("\n", 1)[0]
    assert "rcp-" not in gate
    assert ".ov-recipe{" in css                       # master footnote still styled


# --------------------------------------------------------------------------- #
# Exporting-only mode: count exporting glyphs only (opt-in, default OFF)
# --------------------------------------------------------------------------- #

def test_dashboard_js_has_centralised_counted_set_helper() -> None:
    """One countedSet() helper centralises the exclusion: null when everything
    counts (toggle off / nothing to exclude), else a {name:1} lookup of counted
    glyphs. isCounted/countedTotal wrap it; memos drop when the toggle flips."""
    js = assets.DASHBOARD_JS
    assert "function countedSet(" in js
    assert "function isCounted(" in js
    assert "function countedTotal(" in js
    counted = js.split("function countedSet(")[1].split("\n  function ")[0]
    # off / nothing-to-exclude -> null (everything counts, zero overhead)
    assert "if (!state.exportingOnly || !(H.nonExporting||[]).length) return null;" in counted
    # the toggle flip clears every exclusion-dependent memo before re-rendering
    toggle = js.split("function setExportingOnly(")[1].split("\n  function ")[0]
    assert "COUNTED = null" in toggle
    assert "CSTATS = {}" in toggle and "EXCL = {}" in toggle
    assert "NAVCACHE = null" in toggle
    assert "update();" in toggle


def test_dashboard_js_exporting_only_toggle_in_toolbar() -> None:
    """The toolbar offers the toggle only when the font has non-exporting glyphs;
    its initial state is seeded from the palette pref (H.exportingOnly)."""
    js = assets.DASHBOARD_JS
    toolbar = js.split("function toolbar(")[1].split("\n  function ")[0]
    assert 'id="cfd-exonly"' in toolbar
    assert "(H.nonExporting||[]).length" in toolbar          # gated on having anything to exclude
    assert "state.exportingOnly" in toolbar                  # aria-pressed reflects the state
    # seeded from the embedded pref once the model is decompressed
    assert "state.exportingOnly = !!H.exportingOnly;" in js
    # wired: clicking flips the centralised toggle; update() keeps aria-pressed in sync
    bind = js.split("function bind(")[1].split("\n  function init(")[0]
    assert 'getElementById("cfd-exonly")' in bind
    assert "setExportingOnly(!state.exportingOnly)" in bind
    update = js.split("function update(")[1].split("\n  function ")[0]
    assert 'getElementById("cfd-exonly")' in update


def test_dashboard_js_percentage_helpers_use_counted_denominators() -> None:
    """Every completion percentage excludes non-exporting glyphs when the toggle is
    ON: the ring/donut (gradedOverallPct/aggExclusive), the leaderboard
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
    assert "state.exportingOnly" in nav                      # cache key includes the toggle


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
    raw keys: free mode = exclusive distribution, step mode = suffix-sum
    cumulative ('reached k or beyond'); countFor/uncoloredFor route through it
    only while the exclusion is active (raw passthrough when OFF)."""
    js = assets.DASHBOARD_JS
    stats = js.split("function countedStats(")[1].split("\n  function ")[0]
    assert 'H.mode === "free"' in stats
    count_for = js.split("function countFor(")[1].split("\n  function ")[0]
    assert "countedSet()" in count_for and "countedStats(m)" in count_for
    assert "m.counts[String(k)]" in count_for                # raw truth when OFF
    assert "function uncoloredFor(" in js
