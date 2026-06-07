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
    assert ".seg.intro>span" in css
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


def test_build_html_wires_all_report_insight_features() -> None:
    """End-to-end smoke: every new render unit + its wiring marker is present in
    the generated document, and the self-contained/no-network invariant holds."""
    html = assets.build_html(_model())
    # render units
    for marker in ("function regressionCard(",
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
