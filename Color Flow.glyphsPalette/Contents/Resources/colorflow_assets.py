"""Inline assets + HTML shell for the Color Font Dashboard.

Turns the data model (see colorflow_dashboard.build_model) into one
self-contained, offline .html with inline CSS + inline vanilla JS. No network,
no dependencies. The model is the single source of truth the JS app renders.
"""

from __future__ import annotations

import base64
import gzip
import json
import re
from xml.sax.saxutils import escape as xesc

# A self-contained ``data:image/...`` URI, restricted to characters that are safe
# to drop into a double-quoted ``href`` attribute. The payload allowlist covers
# base64 (``A-Za-z0-9+/=``) and percent-encoded SVG markup, but deliberately
# excludes ``"`` ``'`` ``<`` ``>`` ``&`` ``\`` and every whitespace/control char,
# so a hostile favicon value cannot close the attribute or inject new ones.
_DATA_IMAGE_URI = re.compile(
    r"data:image/[a-zA-Z0-9.+-]+"      # image/<subtype>, e.g. png, svg+xml, x-icon
    r"(?:;[a-zA-Z0-9.+=-]+)*"          # optional parameters (e.g. ;charset=utf-8;base64)
    r",[A-Za-z0-9+/=%_.!~*()-]+\Z"     # required comma + non-empty payload
)


def embed_model(model: dict) -> str:
    """Serialise the model, gzip it, and embed as base64 in a non-executed
    ``<script>`` block. The client decompresses it with ``DecompressionStream``.
    base64's alphabet (``A-Za-z0-9+/=``) contains no ``<`` ``>`` ``&`` ``"``, so
    it can't terminate the script element or break any attribute — no escaping
    needed — and it shrinks the (outline-heavy) model ~4-5x on disk."""
    raw = json.dumps(model, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    payload = base64.b64encode(gzip.compress(raw, compresslevel=9)).decode("ascii")
    return f'<script type="application/octet-stream" id="cfd-model-gz">{payload}</script>'


def _color_overrides(model: dict) -> str:
    """A ``:root`` ``--cN`` override built from the model's per-colour hexes, so the
    report follows the user's Glyphs label colours. Placed after the base stylesheet
    so it wins; the ``--cN`` swatch vars are shared by both themes, so this covers
    light and dark. Empty when the model carries no colours."""
    colors = model.get("colors") or {}
    if not colors:
        return ""
    rules = "".join(f"--c{key}:{value};" for key, value in sorted(colors.items()))
    return f"<style>:root{{{rules}}}</style>"


def _favicon_link(model: dict) -> str:
    """A ``<link rel="icon">`` carrying the bundled brand favicon as a self-contained
    ``data:`` URI (built by the model). Empty when the model has none, or when the
    value isn't a well-formed ``data:image/...`` URI — the favicon is interpolated
    raw into the ``href`` attribute, so anything that could close the attribute or
    add new ones (a ``"``, ``<``, ``>`` or whitespace) is rejected outright rather
    than escaped, to keep an attacker-supplied value from breaking the markup."""
    favicon = model.get("favicon")
    if not favicon or not isinstance(favicon, str):
        return ""
    if not _DATA_IMAGE_URI.fullmatch(favicon):
        return ""
    return f'<link rel="icon" href="{favicon}">'


def build_html(model: dict) -> str:
    """Assemble the complete, self-contained dashboard page from a model."""
    title = xesc(f'CF - {model.get("family") or "Untitled"}')
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title>{_favicon_link(model)}"
        f"<style>{DASHBOARD_CSS}</style>{_color_overrides(model)}</head>"
        '<body><div id="cfd-app"></div>'
        '<noscript>This report needs JavaScript — please open it in a modern browser.</noscript>'
        f"{embed_model(model)}"
        f"<script>{DASHBOARD_JS}</script>"
        "</body></html>"
    )


DASHBOARD_CSS = """
:root{
  --bg:#0a0b0e;--surface:#0e1014;--surface-2:#101217;--border:#1c1f26;--border-2:#23262e;
  --text:#e6e8ec;--muted:#9aa0ab;--muted-2:#6b7280;--accent:#6e7bff;--ok:#3fb950;
  --track:#15171c;--swatch-outline:rgba(255,255,255,.10);--glyph-ink:var(--text);
  --c-none-a:#0e1116;--c-none-b:#3a3f4a;
  --c0:#f97e55;--c1:#ffbe68;--c2:#ba9d6d;--c3:#fff157;--c4:#c1ec8a;--c5:#6bab59;
  --c6:#64a5ef;--c7:#576ef1;--c8:#a962e7;--c9:#e77eb4;--c10:#c5c5c5;--c11:#5f5f5f;
  --c-none:repeating-linear-gradient(135deg,var(--c-none-a) 0,var(--c-none-a) 5px,var(--c-none-b) 5px,var(--c-none-b) 6px);
  --r:10px;--r-sm:7px;
  --fs-base:15px;--fs-row:14px;--fs-sm:13px;--fs-xs:12px;--fs-2xs:11.5px;--fs-big:46px;--fs-big-sm:24px;
  color-scheme:dark;
}
html[data-theme=light]{
  --bg:#f6f7f9;--surface:#ffffff;--surface-2:#f1f3f6;--border:#e3e6ea;--border-2:#d6dae0;
  --text:#15171c;--muted:#5b6270;--muted-2:#8b919c;--accent:#5b62ff;--ok:#1a7f37;
  --track:#eceef2;--swatch-outline:rgba(20,24,33,.18);
  --c-none-a:#dfe3e9;--c-none-b:#aab2bf;color-scheme:light;
}
*{box-sizing:border-box}
html,body{margin:0}
*{font-family:"JetBrains Mono",monospace}
body{background:var(--bg);color:var(--text);font:var(--fs-base)/1.5 "JetBrains Mono",monospace;
  font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased;opacity:0}
body.ready{opacity:1;transition:opacity .35s ease}
@media (prefers-reduced-motion:reduce){body,body.ready{opacity:1;transition:none}.cell{transition:none}.seg.intro{animation:none}.heat,.heat.fading{transition:none;opacity:1}.tl-ring{animation:none!important}.tl-seed-shimmer .tl-seed-ghost{animation:none}}
#cfd-app{max-width:1180px;margin:0 auto;padding:0 20px}
#cfd-main{display:flex;gap:24px;align-items:flex-start}
#cfd-tower{position:sticky;top:0;flex:0 0 240px;width:240px}
#cfd-tower canvas{display:block;width:240px;height:560px;cursor:pointer}
#cfd-body{flex:1 1 auto;min-width:0;min-height:0;overflow-y:auto;padding-right:6px}
/* wide screens: lock the window, scroll the body internally (page never grows) */
@media screen and (min-width:781px){html,body{height:100%;overflow:hidden}#cfd-app{height:100vh;display:flex;flex-direction:column}#cfd-main{flex:1 1 auto;min-height:0;overflow:hidden}#cfd-body{height:100%}}
@media (max-width:780px){#cfd-main{flex-direction:column}#cfd-tower{position:static;width:100%;flex:0 0 auto}#cfd-tower canvas{margin:0 auto}#cfd-body{overflow:visible;padding-right:0}}
.hd{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:10px;padding:14px 0;background:var(--bg);border-bottom:1px solid var(--border)}
.hd .fam-logo{height:22px;width:auto;color:var(--text);display:block}
.hd .fam{font-weight:600}
.hd .meta{font-size:var(--fs-sm);color:var(--muted-2)}
.hd .sp{flex:1}
.hd .mode{font-size:var(--fs-xs);color:var(--muted);border:1px solid var(--border-2);border-radius:var(--r-sm);padding:4px 9px}
.hd .streak{font-size:var(--fs-xs);color:var(--text);border:1px solid var(--border-2);border-radius:var(--r-sm);padding:4px 9px}
.icon{width:30px;height:28px;border:1px solid var(--border-2);border-radius:var(--r-sm);background:transparent;color:var(--muted);cursor:pointer}
.icon:hover{color:var(--text)}
.tb{position:sticky;top:57px;z-index:4;display:flex;align-items:center;gap:8px;padding:12px 0;background:var(--bg);border-bottom:1px solid var(--border);flex-wrap:wrap}
.search{flex:1;min-width:180px;display:flex;align-items:center;gap:8px;background:var(--surface-2);border:1px solid var(--border-2);border-radius:var(--r-sm);padding:6px 10px;color:var(--muted-2)}
.search input{flex:1;background:transparent;border:0;outline:0;color:var(--text);font:inherit}
.search input::placeholder{color:var(--muted-2)}
.search kbd{border:1px solid var(--border-2);border-radius:4px;padding:0 5px;font:var(--fs-xs)/1.4 inherit;color:var(--muted-2)}
.chip{font-size:var(--fs-xs);border:1px solid var(--border-2);border-radius:var(--r-sm);padding:6px 10px;background:var(--surface-2);color:var(--muted);cursor:pointer}
.chip:hover{color:var(--text)}
.chip[aria-pressed=true]{border-color:var(--accent);color:var(--text);background:color-mix(in srgb,var(--accent) 16%,transparent)}
.overall{display:flex;align-items:center;gap:22px;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 18px;margin:16px 0}
.master-overall{margin-top:8px}
.ov-num{display:flex;align-items:center;justify-content:center}
.ov-num .big{font-size:var(--fs-big);font-weight:650;letter-spacing:-.02em;line-height:1}
.ov-num .big small{font-size:var(--fs-big-sm);color:var(--muted-2)}
.ov-sub{font-size:var(--fs-xs);color:var(--muted-2);text-transform:uppercase;letter-spacing:.06em}
.ov-main{flex:1}
.ov-head{font-size:var(--fs-sm);color:var(--muted);margin-bottom:8px}
.ov-head b{color:var(--text)}
.ov-name{color:var(--text);font-weight:600;margin-right:9px}
.ov-name::after{content:"·";color:var(--muted-2);margin-left:9px}
.seg{display:flex;height:10px;border-radius:5px;overflow:hidden;background:var(--track)}
.seg>span{display:block;height:100%;transform-origin:left center;transition:opacity .2s ease;box-shadow:inset -6px 0 9px -3px rgba(0,0,0,.2)}
.seg .seg-none{background:var(--c-none)}
.segc{cursor:pointer}
.seg>span.off{opacity:.28}
.seg>span.on{filter:saturate(1.18)}
@keyframes segGrow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
.seg.intro{transform-origin:left center;animation:segGrow .5s ease backwards}
.ov-recipe{margin-top:10px;font-size:var(--fs-xs);color:var(--muted)}
.ov-recipe b{color:var(--text)}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;font-size:var(--fs-xs);color:var(--muted)}
.legend .lg{display:inline-flex;align-items:center;gap:5px}
.ov-extra{display:grid;grid-template-columns:repeat(auto-fit,minmax(238px,1fr));gap:14px;margin-top:16px}
.ov-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.ov-card.open{grid-column:1/-1}
.ov-card-h{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;margin:0 0 10px;padding:0;background:none;border:0;font:inherit;font-size:var(--fs-2xs);font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;text-align:left}
button.ov-card-h{cursor:pointer}
.ov-exp{font-size:var(--fs-2xs);font-weight:600;color:var(--accent);text-transform:none;letter-spacing:0}
button.ov-card-h:hover .ov-exp{filter:brightness(1.2)}
.ov-card-body.scroll{max-height:300px;overflow-y:auto;padding-right:4px}
.tl-legend-card{margin-top:10px;max-height:120px;overflow-y:auto}
.lb-row{display:flex;align-items:center;gap:9px;width:100%;background:none;border:0;padding:5px 0;cursor:pointer;color:var(--text);font:inherit;text-align:left}
.lb-row+.lb-row{border-top:1px solid var(--track)}
.lb-n{flex:0 0 96px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:var(--fs-xs)}
.lb-bar{flex:1;height:7px;border-radius:4px;background:var(--track);overflow:hidden}
.lb-bar>span{display:block;height:100%;background:var(--accent);border-radius:4px}
.lb-p{flex:0 0 36px;text-align:right;font-size:var(--fs-xs);color:var(--muted)}
.lb-row:hover .lb-bar>span{filter:brightness(1.18)}
.ov-foot{margin-top:9px;font-size:var(--fs-2xs);color:var(--muted-2)}
.hg-row{display:flex;align-items:center;gap:9px;padding:4px 0}
.hg-l{flex:0 0 56px;font-size:var(--fs-2xs);color:var(--muted)}
.hg-bar{flex:1;height:9px;border-radius:4px;background:var(--track);overflow:hidden}
.hg-bar>span{display:block;height:100%;background:var(--accent);border-radius:4px}
.hg-n{flex:0 0 26px;text-align:right;font-size:var(--fs-2xs);color:var(--muted)}
.legend i{width:8px;height:8px;border-radius:50%;display:inline-block;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.tabs{display:flex;gap:18px;border-bottom:1px solid var(--border);margin-bottom:6px;overflow-x:auto}
.tab{font:var(--fs-sm) inherit;background:transparent;border:0;border-bottom:2px solid transparent;color:var(--muted-2);padding:8px 0;cursor:pointer;white-space:nowrap}
.tab:hover{color:var(--text)}
.tab.on{color:var(--text);border-bottom-color:var(--accent)}
.tab .tabsvg{display:block;height:26px;width:auto;color:inherit}
.rows{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:2px 22px;margin:6px 0 4px}
.row{display:flex;align-items:center;gap:9px;font-size:var(--fs-sm);padding:7px 0;border-top:1px solid var(--track);min-width:0}
.row .dot{width:9px;height:9px;border-radius:50%;flex:none;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.row .rl{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row .chk{color:var(--ok)}
.row.done .rl{color:var(--muted)}
.bar{flex:1;min-width:20px;height:5px;background:var(--track);border-radius:3px;overflow:hidden}
.bar>span{display:block;height:100%;border-radius:3px}
.row .num{display:none}
.row .pc{width:38px;text-align:right;flex:none}
@media (max-width:720px){.rows{grid-template-columns:1fr}}
.heat{margin-top:14px;border-top:1px solid var(--border);padding-top:12px;transition:opacity .2s ease}
.heat.fading{opacity:0}
.heat-h{font-size:var(--fs-xs);color:var(--muted);margin-bottom:8px;display:flex;align-items:center;gap:8px}
.heat-h .ba-toggle{flex:none}
.heat-h .hint{color:var(--muted-2)}
.heat-h .hsort{margin-left:auto;display:flex;gap:6px}
.heat-h .chip{padding:4px 8px;font-size:var(--fs-2xs)}
.focus-clear{border-color:var(--accent);color:var(--text)}
.cat:first-child{margin-top:0}
.cat-h{font-size:var(--fs-xs);color:var(--muted);margin:14px 0 6px;display:flex;align-items:center;gap:6px}
.cat-n{color:var(--muted-2)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(40px,1fr));gap:3px}
.cell{aspect-ratio:1;border:0;padding:0;border-radius:5px;cursor:pointer;display:block;text-decoration:none;overflow:hidden;transition:background .45s ease,opacity .2s ease}
.cell:hover{outline:2px solid var(--accent);outline-offset:1px}
.cell.copied{outline:2px solid var(--ok);outline-offset:1px}
.cell svg{width:100%;height:100%;display:block;padding:3px;transform:scale(.9)}
.cell svg path{fill:var(--glyph-ink)}
.more{display:inline-block;margin-top:8px;font-size:var(--fs-xs);color:var(--muted-2)}
.empty{font-size:var(--fs-sm);color:var(--muted-2)}
.changes{margin-top:14px}
.changes>summary{cursor:pointer;font-size:var(--fs-sm);color:var(--muted)}
.chgwrap{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.chg{display:flex;align-items:center;gap:6px;background:var(--surface-2);border:1px solid var(--border);border-radius:var(--r-sm);padding:5px 9px;font-size:var(--fs-xs)}
.chg .cn{max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chg .sw{width:11px;height:11px;border-radius:3px;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.chg .arr{color:var(--muted-2)}
.cmp-wrap{overflow-x:auto;margin-top:8px}
.cmp{border-collapse:collapse;width:100%;font-size:var(--fs-xs)}
.cmprow{transition:opacity .2s ease;cursor:pointer}
.cmp tr.cmp-dim{opacity:.3}
.cmp tr.cmp-sel{opacity:1}
.cmp tr.cmp-sel .cmp-m{color:var(--text);font-weight:600}
.cmp tr.cmp-sel td{background:color-mix(in srgb,var(--accent) 9%,transparent)}
.cmp caption{text-align:left;color:var(--muted-2);font-size:var(--fs-xs);padding-bottom:8px}
.cmp th,.cmp td{border:1px solid var(--border);padding:4px 10px;text-align:left}
.cmp thead th:first-child,.cmp tbody th[scope="row"]{width:1%;white-space:nowrap}
.cmp thead th{color:var(--muted);font-weight:600;text-align:center;background:color-mix(in srgb,var(--text) 7%,transparent)}
.cmp thead th:first-child{text-align:left}
.cmp tbody tr:nth-child(even):not(.cmp-sel) td,.cmp tbody tr:nth-child(even):not(.cmp-sel) th{background:color-mix(in srgb,var(--text) 4%,transparent)}
.cmp thead th .dot{margin:0}
.cmp tbody th{font-weight:500}
.cmp th .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.cmp td{position:relative}
.cmp .cmpbar{position:absolute;left:0;top:0;bottom:0;border-radius:0;opacity:.28}
.cmp .cmpn{position:relative}
.cov{margin-top:6px}
.cov-h{display:flex;align-items:center;gap:12px;margin:10px 0 4px}
.cov-title{font-size:var(--fs-sm);color:var(--muted)}
.cov-switch{margin-left:auto;display:flex;gap:6px}
.cov-switch .chip.on{border-color:var(--accent);color:var(--text);background:color-mix(in srgb,var(--accent) 16%,transparent)}
.cov-rows{margin:6px 0 4px}
.cov-row{display:flex;align-items:center;gap:12px;font-size:var(--fs-row);padding:9px 0;border-top:1px solid var(--track)}
.cov-name{width:120px;flex:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cov-bar{flex:1;display:flex;height:18px;border-radius:5px;overflow:hidden;background:var(--track);min-width:0}
.cov-bar>span{display:flex;align-items:center;justify-content:center;height:100%;min-width:0;overflow:hidden}
.cov-bar .cov-pct{font-size:var(--fs-2xs);line-height:1;color:#fff;mix-blend-mode:difference;white-space:nowrap;padding:0 2px}
.cov-bar .cov-none{background:var(--c-none)}
.cov-row .num{width:auto;min-width:48px;text-align:right;color:var(--muted)}
.sgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:12px;margin:12px 0 4px}
.scard{position:relative;aspect-ratio:1;border-radius:16px;overflow:hidden;background:var(--track)}
.scard-fill{position:absolute;inset:0;width:100%;height:100%;display:block}
.scard-in{position:absolute;inset:0;z-index:1;display:flex;flex-direction:column;align-items:center;justify-content:space-between;padding:13px 11px;text-align:center}
.scard-name{font-size:13px;font-weight:600;color:#fff;line-height:1.15;text-shadow:0 1px 3px rgba(0,0,0,.6)}
.scard-gl{width:46%;height:auto;max-height:50%;fill:rgba(255,255,255,.96);filter:drop-shadow(0 1px 4px rgba(0,0,0,.5))}
.scard-ct{font-size:11px;color:rgba(255,255,255,.82);text-shadow:0 1px 2px rgba(0,0,0,.55)}
.timeline{margin-top:14px}
.tl-empty{margin-top:20px}
.tl-legend{display:flex;flex-wrap:wrap;gap:14px;font-size:var(--fs-xs);color:var(--muted);margin-bottom:8px}
.tl-lg{display:inline-flex;align-items:center;gap:5px}
.tl-lg i{width:9px;height:9px;border-radius:50%;display:inline-block;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.tl-chart{width:100%;height:auto;display:block;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:4px}
.tl-line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round;transition:opacity .2s ease}
.tl-line.tl-dim{opacity:.16}
.tl-line.tl-sel{stroke-width:3}
.tl-area{stroke:none}
.tl-dot{transition:opacity .2s ease}
.tl-dot.tl-dim{opacity:.16}
.tl-lg{transition:opacity .2s ease}
.tl-lg.tl-dim{opacity:.4}
.tl-lg.tl-sel{font-weight:600}
.tl-grid{stroke:var(--track);stroke-width:1}
.tl-axis{fill:var(--muted-2);font-size:10px}
.tl-weekband{fill:var(--text);opacity:.035}
.tl-xtick{fill:var(--muted-2);font-size:9px}
.tl-today{stroke:var(--accent);stroke-width:1.5;stroke-dasharray:3 3;opacity:.7}
.tl-today-pill{fill:var(--accent)}
.tl-today-pill-t{fill:#fff;font-size:8.5px;font-weight:600}
.tl-cross{stroke:var(--muted-2);stroke-width:1;opacity:.85;pointer-events:none;display:none}
.tl-cross-mark{fill:var(--muted-2);pointer-events:none;display:none}
.tl-crossarea{fill:transparent;cursor:crosshair}
.tl-brush{fill:var(--accent);opacity:.16;pointer-events:none;display:none}
.tl-brush-h{fill:var(--accent);opacity:.9;cursor:ew-resize;display:none}
.tl-brush-h:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.tl-chart:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tl-foot{display:flex;justify-content:space-between;font-size:var(--fs-2xs);color:var(--muted-2);margin-top:6px}
.tl-chartbar{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:8px}
.tl-chartbar .tl-legend{margin-bottom:0;flex:1 1 auto}
.tl-mode{display:inline-flex;gap:4px;flex:0 0 auto}
.tl-mode .tl-mode-btn[aria-pressed=true]{border-color:var(--accent);color:var(--text);background:color-mix(in srgb,var(--accent) 16%,transparent)}
.tl-band{stroke:var(--surface);stroke-width:.5;fill-opacity:.92}
.tl-stream-none{fill-opacity:.85}
.tl-lg-hatch{width:9px;height:9px;border-radius:50%;display:inline-block;box-shadow:inset 0 0 0 1px var(--swatch-outline);background:var(--c-none)}
.ov-ring{display:block}
.ov-ring .ov-ring-track{stroke:var(--track)}
.ov-ring .ov-ring-arc{stroke:var(--accent)}
.ov-ring-t{fill:var(--text);font-size:17px;font-weight:600}
.cmp tbody th[scope="row"]{white-space:nowrap;font-weight:600;color:var(--text)}
.cfd-modal{position:fixed;inset:0;z-index:30;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.5)}
.cfd-modal-box{background:var(--surface);border:1px solid var(--border-2);border-radius:14px;padding:18px 20px;box-shadow:0 18px 60px rgba(0,0,0,.45);max-width:440px;width:calc(100% - 40px)}
.cfd-modal-h{font-size:var(--fs-base);font-weight:600;margin-bottom:14px}
.cfd-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.cfd-card{display:flex;flex-direction:column;align-items:center;gap:4px;text-align:center;background:var(--surface-2);border:1px solid var(--border-2);border-radius:10px;padding:16px 8px;color:var(--text);cursor:pointer;font:inherit}
.cfd-card:hover{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 12%,var(--surface-2))}
.cfd-card-ic{font-size:22px;line-height:1.1}
.cfd-card b{font-size:var(--fs-sm)}
.cfd-card small{font-size:var(--fs-2xs);color:var(--muted-2)}
.cfd-cards.hp-list{display:flex;flex-direction:column;gap:8px;text-align:left}
.rg-sw{display:inline-block;width:12px;height:12px;border-radius:3px;flex:none;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.hp-row{display:flex;align-items:center;gap:9px;font-size:var(--fs-sm)}
.hp-n{flex:1;color:var(--text)}
.hp-pos{font-size:var(--fs-xs);color:var(--muted-2)}
.hp-gloss{margin-top:6px;border-top:1px solid var(--border);padding-top:10px;font-size:var(--fs-xs);color:var(--muted)}
.hp-gloss p{margin:0 0 6px}
.hp-gloss b{color:var(--text)}
.rg-row{display:flex;align-items:center;gap:7px;font-size:var(--fs-xs);padding:4px 0}
.rg-row+.rg-row{border-top:1px solid var(--track)}
.rg-n{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text)}
.rg-ar{color:var(--muted-2)}
.rg-when{margin-left:auto;color:var(--muted-2)}
.cm-headline{margin:0 0 8px;font-size:var(--fs-sm);color:var(--text)}
.cm-headline b{font-size:var(--fs-big-sm)}
.cm-bar{display:block;width:100%;flex:none;height:7px;margin:0 0 12px}
.cm-line{margin:0 0 6px;font-size:var(--fs-xs);color:var(--muted)}
.cm-line b{color:var(--text)}
.cm-note{color:var(--muted-2)}
.cm-differ-list{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 10px}
.cm-differ-row{font-size:var(--fs-xs);background:var(--surface-2);border:1px solid var(--border-2);border-radius:var(--r-sm);color:var(--text);padding:3px 8px;cursor:pointer}
.cm-differ-row:hover{border-color:var(--accent)}
.cm-steps{display:flex;align-items:center;flex-wrap:wrap;gap:10px;margin-top:4px;font-size:var(--fs-xs);color:var(--muted)}
.cm-steps-l{color:var(--muted-2)}
.cm-step{display:inline-flex;align-items:center;gap:5px}
.cm-step-n{color:var(--text)}
.tl-digest{margin-bottom:14px;border:1px solid var(--border-2);border-radius:var(--r);background:var(--surface-2);padding:12px 14px}
.tl-digest-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.tl-digest-title{font-weight:600;color:var(--text)}
.tl-digest-sub{font-size:var(--fs-xs);color:var(--muted)}
.tl-digest-body{display:flex;align-items:center;gap:10px;margin-top:6px}
.tl-digest-net{font-size:var(--fs-big-sm);font-weight:700;letter-spacing:-.01em;line-height:1}
.tl-digest-arrow{font-size:1.1em}
.tl-digest-stats{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px}
.tl-d-up{color:var(--ok)}
.tl-d-down{color:var(--c0)}
.tl-d-flat{color:var(--muted-2)}
.tl-seed{border:1px solid var(--border-2);border-radius:var(--r);background:var(--surface-2);padding:16px}
.tl-seed-head{font-weight:600;color:var(--text);margin-bottom:10px}
.tl-seed-sub{font-size:var(--fs-xs);color:var(--muted);margin:10px 0}
.tl-seed-line2{font-size:var(--fs-sm);color:var(--text);margin:6px 0}
.tl-seed-line2 b{font-size:var(--fs-big-sm);font-weight:700;letter-spacing:-.01em}
.tl-seed-svg{display:block;width:100%;max-width:360px;height:auto}
.tl-seed-ghost{stroke:var(--muted-2);fill:var(--muted-2);opacity:.4}
.tl-seed-line{fill:none;stroke-width:2;stroke-dasharray:4 4;stroke-linecap:round;stroke-linejoin:round}
.tl-seed-dot{stroke:none}
.tl-seed-today{fill:var(--accent);stroke:var(--bg);stroke-width:1.5}
@keyframes tlSeedShimmer{0%{opacity:.25}50%{opacity:.55}100%{opacity:.25}}
.tl-seed-shimmer .tl-seed-ghost{animation:tlSeedShimmer 1.8s ease-in-out infinite}
.tl-seed-locks{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
.tl-lock{display:inline-flex;flex-direction:column;gap:2px;border:1px dashed var(--border-2);border-radius:var(--r-sm);padding:6px 10px;background:var(--surface);color:var(--muted-2)}
.tl-lock-n{font-size:var(--fs-xs);font-weight:600;color:var(--muted)}
.tl-lock-h{font-size:var(--fs-2xs);color:var(--muted-2)}
.tl-histmeter{display:flex;align-items:center;gap:10px;margin-top:12px;font-size:var(--fs-xs);color:var(--muted)}
.tl-histmeter-l{flex:0 0 auto;white-space:nowrap}
.tl-histmeter-bar{flex:1;height:6px;border-radius:3px;background:var(--track);overflow:hidden}
.tl-histmeter-bar i{display:block;height:100%;background:var(--accent);border-radius:3px}
.tl-diff{margin-top:14px;border-top:1px solid var(--border);padding-top:12px}
.tl-diff-h{font-size:var(--fs-xs);color:var(--muted);margin-bottom:8px}
.tl-diff-pick{display:flex;gap:14px;flex-wrap:wrap;font-size:var(--fs-xs);color:var(--muted)}
.tl-diff-pick select{background:var(--surface-2);border:1px solid var(--border-2);border-radius:var(--r-sm);color:var(--text);font:inherit;font-size:var(--fs-xs);padding:3px 6px}
.tl-diff-out{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
.tl-reglog{margin-top:14px;border-top:1px solid var(--border);padding-top:12px}
.tl-reglog-h{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:var(--fs-xs);color:var(--muted);margin-bottom:8px}
.tl-reglog-all{flex:0 0 auto}
.tl-reglog-rows .rg-row{cursor:pointer}
.tl-reglog-rows .rg-row:hover{color:var(--text)}
.tl-flag{stroke:var(--c0);stroke-width:2;stroke-linecap:round}
.tl-lanes{margin-top:14px;border-top:1px solid var(--border);padding-top:12px}
.tl-lanes-h{font-size:var(--fs-xs);color:var(--muted);margin-bottom:8px}
.tl-lane{display:flex;align-items:center;gap:10px;font-size:var(--fs-xs);color:var(--text);padding:4px 0}
.tl-lane+.tl-lane{border-top:1px solid var(--track)}
.tl-lane-n{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tl-lane-n small{color:var(--muted-2)}
.tl-lane-mid{flex:0 0 64px;display:flex;align-items:center;justify-content:center;height:16px}
.tl-lane-spark polyline{stroke:var(--accent);stroke-width:1.5;stroke-linejoin:round;stroke-linecap:round;vector-effect:non-scaling-stroke}
.tl-lane-bar{display:block;width:100%;height:6px;background:var(--track);border-radius:3px;overflow:hidden}
.tl-lane-bar>span{display:block;height:100%;background:var(--accent);border-radius:3px}
.tl-lane-pct{flex:0 0 auto;color:var(--text);font-variant-numeric:tabular-nums;text-align:right;min-width:34px}
.tl-lane-d{flex:0 0 auto}
.tl-deadline-rule{stroke:var(--c0);stroke-width:1.5;stroke-dasharray:4 3}
.tl-deadline-pill{fill:var(--c0);opacity:.92}
.tl-deadline-t{fill:#fff;font-size:9px;font-weight:600}
.tl-verdicts{margin-top:14px;border-top:1px solid var(--border);padding-top:12px}
.tl-deadline-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.tl-deadline-l{font-size:var(--fs-xs);color:var(--muted)}
.tl-deadline-bar input{background:var(--surface-2);border:1px solid var(--border-2);border-radius:var(--r-sm);color:var(--text);font:inherit;font-size:var(--fs-xs);padding:3px 6px;color-scheme:dark light}
.tl-deadline-runway{display:inline-block;margin-top:8px;font-size:var(--fs-xs);color:var(--muted-2)}
.tl-verdict-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.tl-verdict{display:inline-flex;flex-direction:column;gap:2px;font-size:var(--fs-xs);border:1px solid var(--border-2);border-radius:var(--r-sm);padding:5px 9px;background:var(--surface-2)}
.tl-v-name{color:var(--text);font-weight:600}
.tl-v-note{color:var(--muted)}
.tl-v-pace{color:var(--muted-2);font-variant-numeric:tabular-nums}
.tl-v-ok{border-color:var(--ok)}.tl-v-ok .tl-v-name{color:var(--ok)}
.tl-v-amber{border-color:var(--c1)}.tl-v-amber .tl-v-name{color:var(--c1)}
.tl-v-late{border-color:var(--c0)}.tl-v-late .tl-v-name{color:var(--c0)}
.tl-machine{margin-top:14px;border-top:1px solid var(--border);padding-top:12px}
.tl-machine-h{font-size:var(--fs-xs);color:var(--muted);margin-bottom:8px}
.tl-scrub-bar{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.tl-scrub-play{flex:0 0 auto}
.tl-scrub-play[disabled]{opacity:.5;cursor:not-allowed}
.tl-scrub{flex:1 1 auto;min-width:0;accent-color:var(--accent);color-scheme:dark light}
.tl-scrub-date{flex:0 0 auto;font-size:var(--fs-xs);color:var(--text);font-variant-numeric:tabular-nums;min-width:54px;text-align:right}
.tl-scrub-diff{flex:0 0 auto;font-size:var(--fs-xs);font-variant-numeric:tabular-nums;color:var(--muted);white-space:nowrap}
.tl-scrub-diff .du{color:var(--ok)}
.tl-scrub-diff .dd{color:var(--c0)}
.tl-machine-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(20px,1fr));gap:3px}
.tl-machine-grid .cell{aspect-ratio:1;border-radius:4px;cursor:default;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.tl-machine-grid .cell svg{padding:2px}
.tl-ring{position:relative;z-index:1}
.tl-ring-up{box-shadow:inset 0 0 0 1px var(--swatch-outline),0 0 0 2px var(--ok);animation:tlRingUp .6s ease-out}
.tl-ring-down{box-shadow:inset 0 0 0 1px var(--swatch-outline),0 0 0 2px var(--c1);animation:tlRingDown .6s ease-out}
@keyframes tlRingUp{0%{box-shadow:inset 0 0 0 1px var(--swatch-outline),0 0 0 0 var(--ok)}40%{box-shadow:inset 0 0 0 1px var(--swatch-outline),0 0 0 3px var(--ok)}100%{box-shadow:inset 0 0 0 1px var(--swatch-outline),0 0 0 0 var(--ok)}}
@keyframes tlRingDown{0%{box-shadow:inset 0 0 0 1px var(--swatch-outline),0 0 0 0 var(--c1)}40%{box-shadow:inset 0 0 0 1px var(--swatch-outline),0 0 0 3px var(--c1)}100%{box-shadow:inset 0 0 0 1px var(--swatch-outline),0 0 0 0 var(--c1)}}
.dz{font-size:var(--fs-xs);border:1px solid var(--border-2);border-radius:var(--r-sm);padding:4px 9px;color:var(--muted)}
.dz-up{border-color:var(--ok);color:var(--ok)}
.dz-down{border-color:var(--c0);color:var(--c0)}
.dz-flat{color:var(--muted-2)}
.dz-net{color:var(--text);font-weight:600}
.cfd-cards.jm-list{display:flex;flex-direction:column;gap:7px;text-align:left}
.jm-row{display:flex;align-items:center;gap:9px;font-size:var(--fs-sm)}
.jm-date{flex:0 0 92px;color:var(--muted-2);font-size:var(--fs-xs)}
.jm-lab{flex:1;min-width:0;color:var(--text)}
#cfd-print{display:none}
.pcover{display:flex;flex-direction:column;gap:8px}
.pcover-ttl{font-size:34px;font-weight:700;letter-spacing:-.01em}
.pcover-sub{color:var(--muted);font-size:var(--fs-sm)}
.ptabs{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}
.ptab{border:1px solid var(--border-2);border-radius:var(--r-sm);padding:6px 12px;color:var(--text);text-decoration:none;font-size:var(--fs-sm)}
.psec .ph{font-size:18px;margin:0 0 12px;border-bottom:1px solid var(--border);padding-bottom:7px}
@media print{
  *{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .tb,.hd .icon,.cfd-modal,.cfd-tip,.toast{display:none!important}
  body{opacity:1!important}
  #cfd-app{display:none!important}
  #cfd-print{display:block!important;max-width:none}
  .pcover{min-height:88vh;justify-content:center;page-break-after:always}
  .psec{page-break-before:always}
  .ptab{page-break-inside:avoid}
}
.ft{margin-top:24px;padding:12px 0 18px;border-top:1px solid var(--border);font-size:10px;color:var(--muted-2);line-height:1.4;display:flex;justify-content:space-between;gap:12px}
.ft-r{text-align:right}
.cfd-tip{position:fixed;z-index:20;display:none;background:var(--surface);border:1px solid var(--border-2);border-radius:8px;padding:8px 10px;box-shadow:0 6px 24px rgba(0,0,0,.32);pointer-events:none}
.cfd-tip .tip-h{font-size:var(--fs-2xs);color:var(--muted);margin-bottom:5px;white-space:nowrap}
.cfd-tip .spark{display:block}
.cfd-tip .spark rect{box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.tl-cross-row{display:flex;align-items:center;gap:6px;font-size:var(--fs-2xs);color:var(--muted);white-space:nowrap;line-height:1.7}
.tl-cross-row i{width:8px;height:8px;border-radius:50%;flex:0 0 auto;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.tl-cross-row b{margin-left:auto;color:var(--text)}
.tl-cross-row.tl-sel{color:var(--text);font-weight:600}
.toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%) translateY(10px);background:var(--surface);border:1px solid var(--border-2);color:var(--text);border-radius:var(--r-sm);padding:8px 14px;font-size:var(--fs-sm);opacity:0;pointer-events:none;transition:opacity .15s,transform .15s}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
button:focus-visible,input:focus-visible,summary:focus-visible,.cell:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
"""


DASHBOARD_JS = r"""
(function(){
  "use strict";
  var H, lastOrder;   // assigned once the gzipped model is decompressed (see start())

  var savedTheme = null;
  try { savedTheme = localStorage.getItem("cfd-theme"); } catch(e){}
  var prefersLight = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
  var state = {
    master: null,                          // no master selected -> global overview
    view: "tabs", before: false, sort: "workflow",
    coverGroup: "byCategory", glyphSort: "category", focus: null,
    ovExpand: {},                          // which Overview cards are expanded
    tlMode: "line",                        // Timeline chart mode: "line" | "flow" (streamgraph)
    tlScrub: null,                         // Time Machine scrubber index (null -> latest snapshot)
    dateA: null, dateB: null,              // Timeline date A-vs-B diff selection
    journeyGlyph: null, helpOpen: false,   // journey modal + help panel
    theme: savedTheme || (prefersLight ? "light" : "dark")
  };
  // The colour bar re-runs its fill animation on first paint AND whenever the
  // selected master changes (switching discs) — not on unrelated re-renders.
  var barsAnim = false, barMaster = "\uffff";

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
  // A clickable segment of a stacked colour bar. Clicking it focuses every glyph
  // with that colour in the heatmap and dims the rest (state.focus). key -1 = None.
  function segSpan(key,w,lab,idx){
    if (!w) return "";
    var on = state.focus===key;
    var off = state.focus!==null && !on;   // a colour is focused and it isn't this one
    return '<span class="segc'+(on?" on":"")+(off?" off":"")+'" data-fkey="'+key+'" style="width:'+w
      + '%;background:var('+varFor(key)+');--i:'+(idx||0)+'" title="'+esc(lab)+' — click to focus these glyphs"></span>';
  }
  function countFor(m,k){ return k===-1 ? m.uncolored : (m.counts[String(k)]||0); }
  function startedOf(m){ return H.glyphTotal - m.uncolored; }
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
    H.masters.forEach(function(m){ H.order.forEach(function(o){ agg[o]+=(m.counts[o]||0); }); });
    return { grand:grand, agg:agg };
  }

  function aggExclusive(){
    var dist = {}; H.order.forEach(function(o){ dist[o]=0; }); var none = 0;
    H.masters.forEach(function(m){
      (m.keys||[]).forEach(function(k){
        var sk = String(k);
        if (k===-1 || H.order.indexOf(sk)===-1) none++; else dist[sk]++;
      });
    });
    return { dist:dist, none:none };
  }
  function streakBadge(){
    var s = (H.trend && H.trend.streak) || {};
    if (!s.current) return "";
    var title = "Progress streak: "+s.current+" day"+(s.current===1?"":"s")+" in a row"
      + (s.best>s.current ? " · best "+s.best : "");
    return '<span class="streak" title="'+esc(title)+'">🔥 '+s.current+'</span>';
  }
  function header(){
    var fam = (H.logo && H.logo.d)
      ? '<svg class="fam-logo" viewBox="'+esc(H.logo.vb)+'" preserveAspectRatio="xMidYMid meet" role="img" aria-label="'+esc(H.family)+'"><path d="'+esc(H.logo.d)+'" fill="currentColor"/></svg>'
      : '<span class="fam">'+esc(H.family)+'</span>';
    return '<header class="hd">'+fam
      + '<span class="sp"></span>'
      + streakBadge()
      + '<button type="button" id="cfd-help" class="icon" aria-label="Help and legend">?</button>'
      + '<button type="button" id="cfd-theme" class="icon" aria-label="Toggle light or dark theme">◐</button></header>';
  }
  function toolbar(){
    return '<div class="tb">'
      + '<button type="button" id="cfd-overview" class="chip" aria-pressed="true" title="Back to the overview">⌂ Overview</button>'
      + '<button type="button" id="cfd-coverage" class="chip" aria-pressed="false">🗂 Coverage</button>'
      + '<button type="button" id="cfd-timeline" class="chip" aria-pressed="false">📈 Timeline</button>'
      + '<button type="button" id="cfd-compare" class="chip" aria-pressed="false">▤ Compare</button>'
      + '<button type="button" id="cfd-export" class="chip" style="margin-left:auto" title="Export the report as PDF, CSV or JSON">⤓ Export Report</button></div>';
  }
  // ----- Graded step progress -----------------------------------------------
  // Each colour is a workflow step ranked by the Palette order; a glyph sitting
  // at step i of N counts as i/N (first step = 1/N, final = 100%). N = the
  // distinct colours actually used across the whole font, kept in Palette order.
  // Uncoloured / off-palette glyphs count as 0.
  var STEPW = null;
  function stepWeights(){
    if (STEPW) return STEPW;
    var used = {};
    H.masters.forEach(function(m){ var ks=m.keys||[]; for (var i=0;i<ks.length;i++){ if (ks[i]!==-1) used[ks[i]]=1; } });
    var steps = (H.order||[]).filter(function(k){ return used[k]; });
    var weight = {}, N = steps.length;
    steps.forEach(function(k,i){ weight[k] = (i+1)/N; });
    STEPW = { weight:weight, N:N, steps:steps };
    return STEPW;
  }
  function gradedSum(m){ var W=stepWeights().weight, ks=m.keys||[], s=0; for (var i=0;i<ks.length;i++){ var w=W[ks[i]]; if (w) s+=w; } return s; }
  function gradedMasterPct(m){ var n=H.glyphTotal||((m.keys||[]).length)||1; return Math.round(gradedSum(m)/n*100); }
  function gradedOverallPct(){ var s=0, tot=0; H.masters.forEach(function(m){ s+=gradedSum(m); tot+=H.glyphTotal; }); return tot? Math.round(s/tot*100):0; }
  function masterStarted(m){ return (m.uncolored||0) < H.glyphTotal; }   // any colour set at all
  function ring(p){
    var r=26, c=2*Math.PI*r, off=c*(1-Math.max(0,Math.min(100,p))/100);
    return '<svg class="ov-ring" width="66" height="66" viewBox="0 0 66 66" role="progressbar" aria-valuenow="'+p+'" aria-valuemin="0" aria-valuemax="100" aria-label="'+p+'% complete">'
      + '<circle class="ov-ring-track" cx="33" cy="33" r="'+r+'" fill="none" stroke-width="6"/>'
      + '<circle class="ov-ring-arc" cx="33" cy="33" r="'+r+'" fill="none" stroke-width="6" stroke-linecap="round" stroke-dasharray="'+c.toFixed(1)+'" stroke-dashoffset="'+off.toFixed(1)+'" transform="rotate(-90 33 33)"/>'
      + '<text class="ov-ring-t" x="33" y="34" text-anchor="middle" dominant-baseline="central">'+p+'%</text></svg>';
  }
  function overall(){
    var a = aggregate(), compP = gradedOverallPct();
    var legend = H.steps.map(function(s){
      return '<span class="lg" title="'+esc(s.label)+'"><i style="background:var('+varFor(s.key)+')"></i>'+pct(a.agg[String(s.key)]||0,a.grand)+'%</span>';
    }).join("");
    var recipeLine = "";
    if (H.recipes && H.recipes.length){
      var recipeComplete = 0;
      H.masters.forEach(function(m){ recipeComplete += (((H.recipeCompletion||{})[m.id])||{}).complete||0; });
      recipeLine = '<div class="ov-recipe">Recipe-adjusted: <b>'+recipeComplete+'/'+a.grand+'</b> complete ('
        + pct(recipeComplete,a.grand)+'%) · '+H.recipes.length+' recipe'+(H.recipes.length===1?"":"s")+'</div>';
    }
    var ex = aggExclusive();
    var segParts = H.steps.map(function(s,i){
      return segSpan(s.key, pct(ex.dist[String(s.key)]||0, a.grand), s.label, i);
    }).join("") + segSpan(-1, pct(ex.none, a.grand), H.noneLabel, H.steps.length);
    return '<section class="overall" aria-label="Overall totals">'
      + '<div class="ov-num">'+ring(compP)+'</div>'
      + '<div class="ov-main">'
      + '<div class="seg'+(barsAnim?" intro":"")+'" role="img" aria-label="Colour distribution across the font">'+segParts+'</div>'
      + '<div class="legend">'+legend+'</div>'+recipeLine+'</div></section>';
  }

  // The selected master rendered like the overall card (ring + stacked bar +
  // legend), but scoped to this one master instead of the whole font.
  function masterOverall(m){
    var total = H.glyphTotal;
    var started = total - m.uncolored;
    var startP = pct(started,total);
    var legend = stepsSorted(m).map(function(s){
      return '<span class="lg" title="'+esc(s.label)+'"><i style="background:var('+varFor(s.key)+')"></i>'+pct(countFor(m,s.key)||0,total)+'%</span>';
    }).join("");
    var head = '<span class="ov-name">'+esc(m.name)+'</span>'
      + '<b>'+gradedMasterPct(m)+'% complete</b> · '+started+'/'+total+' started ('+startP+'%)';
    var recipeLine = "";
    if (H.recipes && H.recipes.length){
      var rc = ((H.recipeCompletion||{})[m.id])||{};
      if (rc.complete != null) recipeLine = '<div class="ov-recipe">Recipe-adjusted: <b>'+rc.complete+'/'+total+'</b> complete ('+pct(rc.complete,total)+'%)</div>';
    }
    var dist={}, none=0;
    (m.keys||[]).forEach(function(k){ var sk=String(k); if (k===-1 || H.order.indexOf(sk)===-1) none++; else dist[sk]=(dist[sk]||0)+1; });
    var segParts = H.steps.map(function(s,i){
      return segSpan(s.key, pct(dist[String(s.key)]||0, total), s.label, i);
    }).join("") + segSpan(-1, pct(none, total), H.noneLabel, H.steps.length);
    return '<section class="overall master-overall" aria-label="'+esc(m.name+" totals")+'">'
      + '<div class="ov-main"><div class="ov-head">'+head+'</div>'
      + '<div class="seg'+(barsAnim?" intro":"")+'" role="img" aria-label="'+esc(m.name+" colour distribution")+'">'+segParts+'</div>'
      + '<div class="legend">'+legend+'</div>'+recipeLine+'</div></section>';
  }
  function heatmap(m){
    var cats = H.categories || [];
    var items = [];
    for (var i=0;i<H.glyphNames.length;i++){
      items.push([H.glyphNames[i], m.keys[i], i]);
    }
    function matchesFocus(it){
      var k = it[1];
      var fk = (k===-1 || H.order.indexOf(String(k))===-1) ? -1 : k;
      return fk === state.focus;
    }
    // When a colour is focused, show ONLY its glyphs; the grid recomposes (packed).
    // Otherwise every glyph (no cap); letterforms come from H.paths.
    var shown = (state.focus===null) ? items : items.filter(matchesFocus);
    var paths = (H.paths && H.paths[m.id]) || {};
    var ch = (H.changes && H.changes[m.id]) || {};
    function cellHTML(it){
      var name = it[0], key = it[1], lab = labelFor(key);
      var wasKey = (ch[name] != null) ? ch[name][0] : key;
      var nowVar = varFor(key), wasVar = varFor(wasKey);
      var showVar = state.before ? wasVar : nowVar;
      // Fully percent-encode the path (encodeURIComponent → slashes become %2F),
      // exactly as the handbook example does. With literal slashes Glyphs misparses
      // the path and falls back to the frontmost font + active master, ignoring the
      // layer (master) we asked for. layer == master id selects the master layer.
      var href = "glyphsapp://show/?path=" + encodeURIComponent(H.filePath || "")
        + "&glyph=" + encodeURIComponent(name) + "&layer=" + encodeURIComponent(m.id);
      var p = paths[name];
      var inner = p ? '<svg viewBox="' + esc(p.vb) + '" preserveAspectRatio="xMidYMid meet"><path d="' + esc(p.d) + '"/></svg>' : '';
      return '<a class="cell' + (p ? ' glyph' : '') + '" href="' + href + '" data-glyph="' + esc(name) + '" data-now="' + nowVar + '" data-was="' + wasVar + '" style="background:color-mix(in srgb,var(' + showVar + ') 35%,transparent)" title="' + esc(name + " — " + lab + " (open in Glyphs)") + '" aria-label="' + esc(name + ", " + lab + ", open in Glyphs") + '">' + inner + '</a>';
    }
    var sections;
    if (state.glyphSort === "font"){
      // pure font glyph order — one flat grid, no category headers
      sections = '<div class="grid" aria-label="All glyphs in font order">'+shown.map(cellHTML).join("")+'</div>';
    } else {
      // group cells by glyph category, Font-View style
      var groups = {}, seen = [];
      shown.forEach(function(it){ var c = cats[it[2]] || "Other"; if (!groups[c]){ groups[c]=[]; seen.push(c); } groups[c].push(it); });
      // order categories like the Glyphs Font View (Letter first); glyphs within a
      // category keep font order. Unknown categories fall after, in first-appearance order.
      var pref = ["Letter","Number","Punctuation","Mark","Separator","Symbol","Other"];
      seen.sort(function(a,b){ var ia=pref.indexOf(a); ia=ia<0?pref.length:ia; var ib=pref.indexOf(b); ib=ib<0?pref.length:ib; return ia-ib; });
      sections = seen.map(function(c){
        return '<div class="cat"><div class="cat-h">'+esc(c)+' <span class="cat-n">'+groups[c].length+'</span></div>'
          + '<div class="grid" aria-label="'+esc(c)+'">'+groups[c].map(cellHTML).join("")+'</div></div>';
      }).join("");
    }
    var empty = items.length===0 ? '<p class="empty">No glyphs.</p>' : "";
    var toggle = Object.keys(ch).length ? '<button type="button" class="ba-toggle chip" aria-pressed="'+state.before+'" title="Toggle the cell colours between before and after the last run">'+(state.before?"Before":"After")+'</button>' : '';
    var sortCtl = '<span class="hsort">'
      + '<button type="button" class="chip" data-gsort="category" aria-pressed="'+(state.glyphSort==="category")+'" title="Group glyphs by category (Font View order)">Category</button>'
      + '<button type="button" class="chip" data-gsort="font" aria-pressed="'+(state.glyphSort==="font")+'" title="Keep the plain font glyph order">Font order</button></span>';
    var focusInfo = state.focus!==null
      ? '<button type="button" class="chip focus-clear" data-fclear="1" title="Clear colour focus">Focus: '+esc(labelFor(state.focus))+' ✕</button>'
      : '';
    return '<section class="heat"><div class="heat-h">'+sortCtl+focusInfo+toggle+'</div>'
      + (sections||empty)+'</section>';
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
  function masterTabs(){
    var tabs = H.masters.map(function(m){
      var on = m.id===state.master, pv = m.preview;
      var label = (pv && pv.d)
        ? '<svg class="tabsvg" viewBox="'+esc(pv.vb)+'" preserveAspectRatio="xMidYMid meet"><path d="'+esc(pv.d)+'" fill="currentColor"/></svg>'
        : esc(m.name);
      return '<button type="button" role="tab" aria-selected="'+on+'" class="tab'+(on?" on":"")
        +'" data-m="'+esc(m.id)+'" title="'+esc(m.name)+'" aria-label="'+esc(m.name)+'">'+label+'</button>';
    }).join("");
    return '<div class="tabs" role="tablist">'+tabs+'</div>';
  }
  // ----- Overview extras (only when no master is selected) ------------------
  function masterPct(m){ return gradedMasterPct(m); }   // graded step progress
  // A dashboard card; when expandable, the header toggles state.ovExpand[key]
  // and the body scrolls so the full content is reachable.
  function ovCard(key, title, bodyHtml, expandable){
    var open = !!state.ovExpand[key];
    var head = expandable
      ? '<button type="button" class="ov-card-h" data-ovexpand="'+esc(key)+'" aria-expanded="'+open+'"><span>'+esc(title)+'</span><span class="ov-exp">'+(open?"Show less":"Show all")+'</span></button>'
      : '<div class="ov-card-h"><span>'+esc(title)+'</span></div>';
    return '<div class="ov-card'+(open?" open":"")+'">'+head
      + '<div class="ov-card-body'+(open?" scroll":"")+'">'+bodyHtml+'</div></div>';
  }
  function lbRow(r){
    return '<button type="button" class="lb-row" data-m="'+esc(r.id)+'" title="Focus '+esc(r.name)+'">'
      + '<span class="lb-n">'+esc(r.name)+'</span>'
      + '<span class="lb-bar"><span style="width:'+r.p+'%"></span></span>'
      + '<span class="lb-p">'+r.p+'%</span></button>';
  }
  // Ranked masters by graded step progress; click a row to focus that master.
  // Collapsed shows the top 6; expanded scrolls through every master.
  function leaderboard(){
    var rows = H.masters.map(function(m){ return {id:m.id, name:m.name, p:masterPct(m), any:masterStarted(m)}; });
    rows.sort(function(a,b){ return b.p-a.p || (a.name<b.name?-1:1); });
    var started = rows.filter(function(r){ return r.any; });
    var open = !!state.ovExpand.leaderboard;
    var list = open ? rows : (started.length?started:rows).slice(0,6);
    var bars = list.map(lbRow).join("");
    var zero = rows.length - started.length;
    var foot = (!open && zero>0) ? '<div class="ov-foot">'+zero+' master'+(zero===1?"":"s")+' not started</div>' : '';
    return ovCard("leaderboard", "Furthest along", bars+foot, rows.length>6);
  }
  // How many masters fall in each completion band.
  function histogram(){
    var buckets=[{l:"0%",n:0},{l:"1–25%",n:0},{l:"26–50%",n:0},{l:"51–75%",n:0},{l:"76–99%",n:0},{l:"100%",n:0}];
    H.masters.forEach(function(m){ var p=masterPct(m);
      var b = !masterStarted(m)?0 : p>=100?5 : p<=25?1 : p<=50?2 : p<=75?3 : 4; buckets[b].n++; });
    var max=buckets.reduce(function(a,c){return Math.max(a,c.n);},1);
    var rows=buckets.map(function(b){
      return '<div class="hg-row"><span class="hg-l">'+b.l+'</span>'
        + '<span class="hg-bar"><span style="width:'+(b.n/max*100).toFixed(1)+'%"></span></span>'
        + '<span class="hg-n">'+b.n+'</span></div>';
    }).join("");
    return ovCard("histogram", "Masters by completion", rows, false);
  }
  // Completion-over-time, compact; expanded grows the chart and adds the legend.
  function timelineCard(){
    if (!hasTrend()) return "";
    var open = !!state.ovExpand.timeline;
    var parts = trendParts(680, open?190:120);
    var body = parts.chart + (open ? '<div class="tl-legend tl-legend-card">'+parts.legend+'</div>'+parts.foot : '');
    return ovCard("timeline", "Completion over time", body, true);
  }
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
    var open = !!state.ovExpand.recent;
    var list = open ? feed : feed.slice(0, 12);
    var rows = list.map(function(it){
      return '<div class="rg-row" data-jglyph="'+esc(it.name)+'"><span class="rg-n">'+esc(it.name)+'</span>'
        + swatchFor(it.was)+'<span class="rg-ar">→</span>'+swatchFor(it.nw)
        + '<span class="rg-when">'+esc(whenLabel(it.name) || it.date)+'</span></div>';
    }).join("");
    return ovCard("recent", "Recent activity", rows, feed.length > 12);
  }
  // Cross-master agreement (global Overview lead card). H.crossMaster is computed
  // in Python; this only renders it. byStep keys arrive as JSON strings, so we
  // parseInt before handing them to the int-keyed swatchFor/labelFor helpers
  // (swatchFor("-1") would otherwise miss varFor's `k===-1` guard).
  function crossMasterCard(){
    var cm = H.crossMaster;
    if (!cm) return "";
    var open = !!state.ovExpand.crossMaster;
    var donePct = pct(cm.doneEverywhere, cm.total);
    var head = '<p class="cm-headline"><b>'+cm.doneEverywhere+'</b> / '+cm.total+' done everywhere</p>'
      + '<div class="bar cm-bar"><span style="width:'+donePct+'%;background:var(--accent)"></span></div>';
    var ident = '<p class="cm-line">identical in all masters: <b>'+cm.identical+'</b></p>';
    var single = (cm.masterCount < 2) ? ' <span class="cm-note">(single master)</span>' : '';
    var differLine = '<p class="cm-line">differ between masters: <b>'+cm.differ+'</b>'+single+'</p>';
    var differList = "";
    if (open){
      var names = cm.differGlyphs || [];
      differList = names.length
        ? '<div class="cm-differ-list">'+names.map(function(name){
            return '<button type="button" class="cm-differ-row" data-jglyph="'+esc(name)+'">'+esc(name)+'</button>';
          }).join("")+'</div>'
        : '<p class="ov-empty">No glyphs differ.</p>';
    }
    var byStep = cm.byStep || {};
    var chips = Object.keys(byStep).map(function(k){
      var key = parseInt(k, 10);
      return '<span class="cm-step" title="'+esc(labelFor(key))+'">'+swatchFor(key)
        + '<span class="cm-step-n">'+byStep[k]+'</span></span>';
    }).join("");
    var steps = chips
      ? '<div class="cm-steps"><span class="cm-steps-l">by step:</span>'+chips+'</div>'
      : "";
    var body = head + ident + differLine + differList + steps;
    return ovCard("crossMaster", "Across masters", body, (cm.differGlyphs||[]).length > 0);
  }
  function overviewExtras(){
    if (!H.masters.length) return "";
    return '<div class="ov-extra">'+crossMasterCard()+leaderboard()+histogram()+timelineCard()+'</div>';
  }
  // Regression + Recent are per-master change feeds, so they belong with the
  // selected master, not the global Overview. Both already key off state.master
  // (set here), so they render that master's regressions/recent activity.
  function masterExtras(){
    var cards = regressionCard()+recentCard();
    return cards ? '<div class="ov-extra">'+cards+'</div>' : "";
  }
  function tabsView(){
    if (state.master==null) return overall()+overviewExtras();   // no master selected -> global view + extras
    var m = masterById(state.master);
    return '<div class="panel" role="tabpanel">'+masterOverall(m)+heatmap(m)+masterExtras()+'</div>';
  }
  function covStacked(r){
    // a left-aligned stacked bar of the colours actually set in this group, each
    // segment labelled with its share (shown only when the segment is wide enough)
    var dist = r.dist || {};
    function seg(w, bg, cls, title){
      var label = w >= 7 ? '<span class="cov-pct">'+Math.round(w)+'%</span>' : '';
      return '<span'+(cls?' class="'+cls+'"':'')+' style="width:'+w+'%;background:'+bg+'" title="'+title+'">'+label+'</span>';
    }
    var segs = H.order.map(function(k){
      var c = dist[k] || 0;
      if (!c) return "";
      var w = r.total ? (c/r.total*100) : 0;
      return seg(w, 'var(--c'+k+')', '', esc(labelFor(parseInt(k,10))+": "+c));
    }).join("");
    var uncolored = r.uncolored || 0;
    if (uncolored) segs += seg(r.total?uncolored/r.total*100:0, 'var(--c-none)', 'cov-none', esc(H.noneLabel+": "+uncolored));
    return '<div class="cov-bar" role="img" aria-label="'+esc(r.key+": colour distribution")+'">'+segs+'</div>';
  }
  // ----- Script grid: one rounded card per script, filled with that script's
  //       label-colour blend, a sample glyph and its glyph count (#13) ---------
  function stepColor(key){
    var v = (H.colors && H.colors[String(key)]) || "";
    if (!v) v = getComputedStyle(document.documentElement).getPropertyValue("--c"+key) || "";
    v = (""+v).trim();
    return v || ("hsl("+Math.round((key*31)%360)+",65%,55%)");
  }
  function prettyScript(key){ return key==="Other" ? "Other" : key.charAt(0).toUpperCase()+key.slice(1); }
  // Rows for the grid: the selected master's per-script coverage, or — when no
  // master is selected — the same scripts aggregated across every master (the
  // glyph count is constant per master, so it stays; the colour distribution
  // sums so the blend reflects the whole family).
  function scriptRows(){
    var cov = (H.coverage && H.coverage.byScript) || {};
    if (state.master != null) return cov[state.master] || [];
    var acc = {}, masters = H.masters || [], key;
    for (var mi=0; mi<masters.length; mi++){
      var rows = cov[masters[mi].id] || [];
      for (var ri=0; ri<rows.length; ri++){
        var r = rows[ri], a = acc[r.key] || (acc[r.key] = {key:r.key, total:0, uncolored:0, dist:{}});
        a.total = Math.max(a.total, r.total||0);
        a.uncolored += (r.uncolored || 0);
        var d = r.dist || {};
        for (key in d){ if (d[key]) a.dist[key] = (a.dist[key]||0) + d[key]; }
      }
    }
    var out = []; for (key in acc) out.push(acc[key]);
    out.sort(function(p,q){ return q.total - p.total || (p.key<q.key?-1:1); });
    return out;
  }
  function scriptGlyphSVG(meta){
    if (!meta || !meta.glyph) return "";
    var first = (H.masters[0]||{}).id, paths = H.paths || {};
    var mid = state.master != null ? state.master : first;
    var o = (paths[mid] && paths[mid][meta.glyph]) || (paths[first] && paths[first][meta.glyph]);
    if (!o){ for (var k in paths){ if (paths[k][meta.glyph]){ o = paths[k][meta.glyph]; break; } } }
    if (!o) return "";
    return '<svg class="scard-gl" viewBox="'+esc(o.vb)+'" aria-hidden="true"><path d="'+esc(o.d)+'"/></svg>';
  }
  function scriptGrid(){
    var rows = scriptRows().filter(function(r){ return r.key !== "Other"; });
    if (!rows.length) return '<p class="empty">No glyphs.</p>';
    var meta = (H.coverage && H.coverage.scriptMeta) || {};
    var cards = rows.map(function(r){
      var m = meta[r.key] || {}, name = m.name || prettyScript(r.key), dist = r.dist || {}, parts = [], k;
      for (k in dist){ if (dist[k]) parts.push(k+":"+dist[k]); }
      return '<div class="scard" data-dist="'+esc(parts.join(","))+'" data-total="'+r.total
        + '" data-uncol="'+(r.uncolored||0)+'" title="'+esc(name+" — "+r.total+" glyphs")+'">'
        + '<canvas class="scard-fill" width="320" height="320" aria-hidden="true"></canvas>'
        + '<div class="scard-in"><span class="scard-name">'+esc(name)+'</span>'
        + scriptGlyphSVG(m) + '<span class="scard-ct">'+r.total+'</span></div></div>';
    }).join("");
    return '<div class="sgrid">'+cards+'</div>';
  }
  // Soft proportional colour blend (a flat 2D echo of the tower disc): a blurred
  // conic of the present labels over a solid base, darkened in the centre so the
  // white sample glyph stays legible.
  function paintBlend(ctx, W, Ht, segs, sum, grey){
    var cx=W/2, cy=Ht/2, R=Math.max(W,Ht)*0.72, i;
    var base = segs.length ? segs[0][1] : grey;
    ctx.clearRect(0,0,W,Ht); ctx.fillStyle=base; ctx.fillRect(0,0,W,Ht);
    if (segs.length && sum>0){
      var off=document.createElement("canvas"); off.width=W; off.height=Ht; var g=off.getContext("2d");
      var acc=0, stops=[];
      for (i=0;i<segs.length;i++){ stops.push([acc+segs[i][0]/sum/2, segs[i][1]]); acc+=segs[i][0]/sum; }
      var filled=false;
      try {
        var grad=g.createConicGradient(-Math.PI/2, cx, cy);
        for (i=0;i<stops.length;i++) grad.addColorStop(Math.min(1,stops[i][0]), stops[i][1]);
        grad.addColorStop(1, stops[0][1]);
        g.fillStyle=grad; g.fillRect(0,0,W,Ht); filled=true;
      } catch(e){ filled=false; }
      if (!filled){ var a=-Math.PI/2;
        for (i=0;i<segs.length;i++){ var a1=a+segs[i][0]/sum*Math.PI*2;
          g.fillStyle=segs[i][1]; g.beginPath(); g.moveTo(cx,cy); g.arc(cx,cy,R,a,a1); g.closePath(); g.fill(); a=a1; } }
      ctx.filter="blur("+Math.round(Math.max(W,Ht)*0.085)+"px) saturate(1.2)"; ctx.drawImage(off,0,0); ctx.filter="none";
    }
  }
  function paintScriptCards(){
    var cards = document.querySelectorAll(".scard");
    var grey = (getComputedStyle(document.documentElement).getPropertyValue("--track")||"").trim() || "hsl(225,8%,15%)";
    for (var i=0;i<cards.length;i++){
      var cv = cards[i].querySelector("canvas.scard-fill"); if (!cv) continue;
      var ctx = cv.getContext("2d"); if (!ctx) continue;
      var uncol = parseFloat(cards[i].getAttribute("data-uncol")) || 0;
      var raw = (cards[i].getAttribute("data-dist")||"").split(","), segs=[], sum=0, j, pair, c;
      for (j=0;j<raw.length;j++){ if (!raw[j]) continue; pair=raw[j].split(":"); c=parseFloat(pair[1])||0;
        if (c>0){ segs.push([c, stepColor(pair[0])]); sum+=c; } }
      if (uncol>0){ segs.push([uncol, grey]); sum+=uncol; }
      paintBlend(ctx, cv.width, cv.height, segs, sum, grey);
    }
  }
  function coverageView(){
    var cov = (H.coverage && H.coverage[state.coverGroup]) || {};
    var covMaster = state.master==null ? ((H.masters[0]||{}).id) : state.master;
    var rows2 = cov[covMaster] || [];
    var head = '<div class="cov-h"><span class="cov-title">Colours set by '+(state.coverGroup==="byScript"?"script":"category")+'</span>'
      + '<span class="cov-switch">'
      + '<button type="button" class="chip'+(state.coverGroup==="byScript"?" on":"")+'" data-cg="byScript" aria-pressed="'+(state.coverGroup==="byScript")+'">Script</button>'
      + '<button type="button" class="chip'+(state.coverGroup==="byCategory"?" on":"")+'" data-cg="byCategory" aria-pressed="'+(state.coverGroup==="byCategory")+'">Category</button></span></div>';
    if (state.coverGroup==="byScript")
      return '<section class="cov"><div class="panel">'+head+scriptGrid()+'</div></section>';
    var body = rows2.length ? rows2.map(function(r){
      return '<div class="cov-row"><span class="cov-name" title="'+esc(r.key)+'">'+esc(r.key)+'</span>'
        + covStacked(r) + '<span class="num">'+r.total+'</span></div>';
    }).join("") : '<p class="empty">No glyphs.</p>';
    return '<section class="cov"><div class="panel">'+head+'<div class="cov-rows">'+body+'</div></div></section>';
  }
  // ----- Timeline: completion over time, one line per master -----
  function masterHue(i){ return Math.round((i*137.508) % 360); }
  // ISO date "YYYY-MM-DD" -> short "D Mon" axis label (e.g. "7 Jun"). UTC-parsed
  // so the day never drifts across the local timezone boundary.
  var CFD_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  function dateLabel(iso){
    var d = new Date(iso + "T00:00:00Z");
    if (isNaN(d.getTime())) return iso;
    return d.getUTCDate() + " " + CFD_MONTHS[d.getUTCMonth()];
  }
  // ----- #7 shared calendar X axis -------------------------------------------
  // Builds the plot geometry + X scale and the calendar layers (zebra ISO-week
  // bands, thinned date tick labels, dashed "today" rule) that both the line chart
  // (trendParts) and the streamgraph (streamParts) draw, so the X axis stays
  // identical between the Line and Flow modes. Y(pct) maps a 0-100 % onto the plot.
  function calendarAxis(W, Ht){
    var series = (H.trend && H.trend.series) || [];
    var pl=30, pr=12, ptop=12, pb=16, iw=W-pl-pr, ih=Ht-ptop-pb;
    var t0 = new Date(series[0].date).getTime();
    function dayOff(d){ return (new Date(d).getTime()-t0)/86400000; }
    var lastOff = Math.max(1, dayOff(series[series.length-1].date));
    function X(o){ return pl + o/lastOff*iw; }
    function Y(p){ return ptop + ih - p/100*ih; }
    // zebra ISO-week bands: align to the Monday opening the first snapshot's week.
    var firstDate = new Date(series[0].date + "T00:00:00Z");
    var firstDow = (firstDate.getUTCDay() + 6) % 7;          // 0 = Monday
    var weekStart = -firstDow;                                // offset of that Monday
    var weekBands = "";
    for (var wOff = weekStart, band = 0; wOff < lastOff; wOff += 7, band++){
      if (band % 2 === 0){ continue; }                       // tint every other week only
      var bx0 = Math.max(pl, X(Math.max(0, wOff)));
      var bx1 = Math.min(W - pr, X(Math.min(lastOff, wOff + 7)));
      if (bx1 <= bx0){ continue; }
      weekBands += '<rect class="tl-weekband" x="'+bx0.toFixed(1)+'" y="'+ptop+'" width="'+(bx1-bx0).toFixed(1)+'" height="'+ih+'"/>';
    }
    // thin the tick labels so they never collide on long spans: aim for ~6 ticks,
    // stepping whole snapshots so every label sits on a real data X.
    var tickStep = Math.max(1, Math.ceil(series.length / 6));
    var xticks = "";
    series.forEach(function(p, idx){
      if (idx % tickStep !== 0 && idx !== series.length - 1){ return; }
      var tx = X(dayOff(p.date));
      var anchor = idx === 0 ? "start" : (idx === series.length - 1 ? "end" : "middle");
      xticks += '<text class="tl-xtick" x="'+tx.toFixed(1)+'" y="'+(ptop+ih+pb).toFixed(1)+'" text-anchor="'+anchor+'">'+esc(dateLabel(p.date))+'</text>';
    });
    // dashed "today" rule + pill, only when today falls inside the plotted span.
    var todayRule = "";
    var today = H.trend && H.trend.today;
    if (today){
      var tOff = dayOff(today);
      if (tOff >= 0 && tOff <= lastOff){
        var trx = X(tOff);
        var lab = dateLabel(today);
        var pillW = lab.length * 5.5 + 12;
        var pillX = Math.min(W - pr - pillW, Math.max(pl, trx - pillW/2));
        todayRule = '<line class="tl-today" x1="'+trx.toFixed(1)+'" y1="'+ptop+'" x2="'+trx.toFixed(1)+'" y2="'+(ptop+ih).toFixed(1)+'"/>'
          + '<rect class="tl-today-pill" x="'+pillX.toFixed(1)+'" y="'+(ptop-1)+'" width="'+pillW.toFixed(1)+'" height="13" rx="6"/>'
          + '<text class="tl-today-pill-t" x="'+(pillX+pillW/2).toFixed(1)+'" y="'+(ptop+8.5)+'" text-anchor="middle">'+esc(lab)+'</text>';
      }
    }
    // snapshot X anchors in SVG user-space — crosshair + brush snap to these.
    var snaps = series.map(function(p){ return { x:+X(dayOff(p.date)).toFixed(1), d:p.date }; });
    return { series:series, pl:pl, pr:pr, ptop:ptop, pb:pb, iw:iw, ih:ih,
             dayOff:dayOff, lastOff:lastOff, X:X, Y:Y,
             weekBands:weekBands, xticks:xticks, todayRule:todayRule, snaps:snaps };
  }
  // Shared trend builder: returns the chart SVG, the per-master legend and the
  // date foot, so both the Timeline view and the Overview card draw the same.
  function trendParts(W, Ht){
    var ax = calendarAxis(W, Ht);
    var series = ax.series, pl = ax.pl, pr = ax.pr, ptop = ax.ptop, ih = ax.ih, iw = ax.iw;
    var dayOff = ax.dayOff, X = ax.X, Y = ax.Y;
    var grid = [0,25,50,75,100].map(function(g){
      var y = Y(g).toFixed(1);
      return '<line class="tl-grid" x1="'+pl+'" y1="'+y+'" x2="'+(W-pr)+'" y2="'+y+'"/>'
        + '<text class="tl-axis" x="'+(pl-5)+'" y="'+(parseFloat(y)+3).toFixed(1)+'" text-anchor="end">'+g+'</text>';
    }).join("");
    // ----- #7 real calendar X axis: zebra ISO-week bands + date tick labels -----
    var weekBands = ax.weekBands, xticks = ax.xticks, todayRule = ax.todayRule;
    // ----- #10 gentle monotone smoothing for the selected master's line/area.
    // Cubic path whose control-point tangents are clamped so the curve stays
    // monotone between real data points and never overshoots a tl-dot value.
    function smoothPath(ps){
      if (ps.length < 2){ return ps.length ? "M"+ps[0].x.toFixed(1)+" "+ps[0].y.toFixed(1) : ""; }
      var slopes = [];                                       // secant slope of each segment
      for (var s = 0; s < ps.length - 1; s++){
        var dx = ps[s+1].x - ps[s].x;
        slopes.push(dx ? (ps[s+1].y - ps[s].y) / dx : 0);
      }
      var tang = [slopes[0]];                                // tangent (dy/dx) at each point
      for (var k = 1; k < ps.length - 1; k++){
        var a = slopes[k-1], b = slopes[k];
        tang.push(a*b <= 0 ? 0 : (a + b) / 2);               // zero tangent at local extrema -> no overshoot
      }
      tang.push(slopes[slopes.length-1]);
      var d = "M"+ps[0].x.toFixed(1)+" "+ps[0].y.toFixed(1);
      for (var j = 0; j < ps.length - 1; j++){
        var hx = (ps[j+1].x - ps[j].x) / 3;                  // 1/3-span control handles
        var c1x = ps[j].x + hx,   c1y = ps[j].y + tang[j]*hx;
        var c2x = ps[j+1].x - hx, c2y = ps[j+1].y - tang[j+1]*hx;
        d += " C"+c1x.toFixed(1)+" "+c1y.toFixed(1)+" "+c2x.toFixed(1)+" "+c2y.toFixed(1)+" "+ps[j+1].x.toFixed(1)+" "+ps[j+1].y.toFixed(1);
      }
      return d;
    }
    var defs = "", lines = "", selLine = "", legend = "";
    H.masters.forEach(function(m, i){
      var col = "hsl("+masterHue(i)+",70%,55%)";
      var pts = series.map(function(p){
        var mp = p.masters[m.id]; if (!mp) return null;
        var c = mp.total ? mp.final/mp.total*100 : 0;
        return { x:X(dayOff(p.date)), y:Y(c), pc:c, date:p.date };
      }).filter(Boolean);
      if (!pts.length) return;
      var dim = state.master!=null && m.id!==state.master;   // a master is selected, not this one
      var sel = state.master!=null && m.id===state.master;
      var poly = pts.map(function(o){ return o.x.toFixed(1)+","+o.y.toFixed(1); }).join(" ");
      var dots = pts.map(function(o){ return '<circle class="tl-dot'+(dim?" tl-dim":"")+'" cx="'+o.x.toFixed(1)+'" cy="'+o.y.toFixed(1)+'" r="'+(sel?3:2.5)+'" fill="'+col+'"><title>'+esc(m.name+" · "+o.date+" · "+Math.round(o.pc)+"%")+'</title></circle>'; }).join("");
      if (sel){
        // #10 hero area: gentle smoothed line + a soft gradient fill that closes
        // down to the baseline Y(0). Dots above stay at exact values (honest).
        var gradId = "tl-area-grad-"+i;
        var topY = ptop, botY = Y(0);
        defs += '<linearGradient id="'+gradId+'" x1="0" y1="'+topY+'" x2="0" y2="'+botY.toFixed(1)+'" gradientUnits="userSpaceOnUse">'
          + '<stop offset="0" stop-color="hsl('+masterHue(i)+',70%,55%)" stop-opacity="0.22"/>'
          + '<stop offset="1" stop-color="hsl('+masterHue(i)+',70%,55%)" stop-opacity="0"/>'
          + '</linearGradient>';
        var top = smoothPath(pts);
        var area = top + " L"+pts[pts.length-1].x.toFixed(1)+" "+botY.toFixed(1)
          + " L"+pts[0].x.toFixed(1)+" "+botY.toFixed(1) + " Z";
        var line = '<path class="tl-line tl-sel" d="'+top+'" stroke="'+col+'"/>';
        selLine += '<path class="tl-area" d="'+area+'" fill="url(#'+gradId+')"/>' + line + dots;
      } else {
        lines += '<polyline class="tl-line'+(dim?" tl-dim":"")+'" points="'+poly+'" stroke="'+col+'"/>'+dots;
      }
      legend += '<span class="tl-lg'+(dim?" tl-dim":"")+(sel?" tl-sel":"")+'"><i style="background:'+col+'"></i>'+esc(m.name)+' '+Math.round(pts[pts.length-1].pc)+'%</span>';
    });
    lines += selLine;                                        // keep the selected master (area+line) on top
    // ----- #6 snapping crosshair: a transparent overlay rect captures pointer X,
    // a 1px vertical guide + nearest-snapshot marker draw on top, and the snapshot
    // X positions (in SVG user-space) ride along as data so crosshairMove() can snap
    // to the nearest discrete date without re-deriving the X scale. baseY/topY let
    // it place the marker on the chart even when no master line is selected.
    var snaps = ax.snaps;
    var crossData = ' data-snaps="'+esc(JSON.stringify(snaps))+'" data-topy="'+ptop+'" data-boty="'+Y(0).toFixed(1)+'"';
    var crossLayer = '<line class="tl-cross" y1="'+ptop+'" y2="'+(ptop+ih).toFixed(1)+'"/>'
      + '<circle class="tl-cross-mark" r="3.5"/>'
      + '<rect class="tl-crossarea" x="'+pl+'" y="'+ptop+'" width="'+iw.toFixed(1)+'" height="'+ih.toFixed(1)+'"/>';
    // ----- #8 brush-to-compare: a translucent band + two draggable handles drawn
    // over the same plot. brushMove() snaps each edge to the nearest snapshot X
    // (reusing data-snaps), inverts the forward X scale to recover dates, and on
    // release writes them into state.dateA/dateB. The handles are focusable so the
    // arrow keys nudge a focused edge. The <select> a11y fallback stays the source
    // markup (dateDiffPanel below). All hidden until a drag begins.
    var brushLayer = '<rect class="tl-brush" y="'+ptop+'" height="'+ih.toFixed(1)+'"/>'
      + '<rect class="tl-brush-h" data-edge="a" tabindex="0" role="slider" aria-label="Compare range start" y="'+ptop+'" width="6" height="'+ih.toFixed(1)+'"/>'
      + '<rect class="tl-brush-h" data-edge="b" tabindex="0" role="slider" aria-label="Compare range end" y="'+ptop+'" width="6" height="'+ih.toFixed(1)+'"/>';
    // ----- #15 regression flags: a small red tick at the baseline on every snapshot
    // X that carried >=1 backward move (regressionDates over the full history). Reuses
    // ax.snaps so the tick sits exactly on the discrete date, like the crosshair.
    var regDates = regressionDates();
    var baseY = Y(0);
    var flags = ax.snaps.filter(function(s){ return regDates[s.d]; }).map(function(s){
      return '<line class="tl-flag" x1="'+s.x+'" y1="'+(baseY-6).toFixed(1)+'" x2="'+s.x+'" y2="'+baseY.toFixed(1)+'"><title>'+esc(dateLabel(s.d)+" · moved backward")+'</title></line>';
    }).join("");
    // #19 dashed deadline rule (reuses the calendar axis date->X math); dormant
    // until a target date is stored, so this is "" by default.
    var deadline = deadlineRule(ax);
    var chart = '<svg class="tl-chart" viewBox="0 0 '+W+' '+Ht+'" role="img" tabindex="0"'+crossData+' aria-label="Completion over time per master. Hover or use the left and right arrow keys to read each snapshot.">'+(defs?'<defs>'+defs+'</defs>':'')+weekBands+grid+xticks+lines+flags+todayRule+deadline+brushLayer+crossLayer+'</svg>';
    var foot = '<div class="tl-foot"><span>'+esc(series[0].date)+'</span><span>'+esc(series[series.length-1].date)+'</span></div>';
    return { chart:chart, legend:legend, foot:foot };
  }
  // ----- #5 colour streamgraph (Flow mode) -----------------------------------
  // Tally per-step counts for every date in H.trend.dates by calling stateAt over
  // the chosen master (state.master, else the first master), bucketing each glyph's
  // key into H.order (+ a "none" bucket for uncoloured/unknown keys). Render a
  // stacked area: bands stack bottom->top by H.order with each step's own var, and
  // the none bucket is hatched on top. Shares the #7 calendar X axis with the line
  // chart and the same data-snaps so the crosshair read-out works in both modes.
  // The crosshair card shows the per-step COUNTS at the snapped date.
  function streamTally(masterId){
    var dates = (H.trend && H.trend.dates) || [];
    var order = H.order || [];
    // per date: { byKey:{ stepKey: count }, none: count }
    return dates.map(function(d){
      var snap = stateAt(masterId, d);
      var byKey = {}; order.forEach(function(k){ byKey[k] = 0; });
      var none = 0;
      for (var name in snap){
        var sk = String(snap[name]);
        if (snap[name] === -1 || order.indexOf(sk) === -1){ none++; } else { byKey[sk]++; }
      }
      return { date:d, byKey:byKey, none:none };
    });
  }
  function streamParts(W, Ht){
    var ax = calendarAxis(W, Ht);
    var pl = ax.pl, ptop = ax.ptop, ih = ax.ih, iw = ax.iw;
    var dayOff = ax.dayOff, X = ax.X, Y = ax.Y;
    var order = H.order || [];
    var mid = state.master != null ? state.master : (H.masters[0] && H.masters[0].id);
    var tally = streamTally(mid);
    // denominator: whole-font total keeps band heights honest + comparable to the
    // % grid; degrade to the max stacked count when glyphTotal is missing.
    var denom = H.glyphTotal || tally.reduce(function(mx, t){
      var s = t.none; for (var k in t.byKey){ s += t.byKey[k]; } return Math.max(mx, s);
    }, 0) || 1;
    var grid = [0,25,50,75,100].map(function(g){
      var y = Y(g).toFixed(1);
      return '<line class="tl-grid" x1="'+pl+'" y1="'+y+'" x2="'+(W-ax.pr)+'" y2="'+y+'"/>'
        + '<text class="tl-axis" x="'+(pl-5)+'" y="'+(parseFloat(y)+3).toFixed(1)+'" text-anchor="end">'+g+'</text>';
    }).join("");
    // an SVG diagonal hatch pattern for the uncoloured band (mirrors the --c-none
    // repeating-gradient look; theme-safe via the muted-2 stroke).
    var defs = '<pattern id="tl-stream-hatch" class="stream-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
      + '<rect width="6" height="6" fill="var(--track)"/>'
      + '<line x1="0" y1="0" x2="0" y2="6" stroke="var(--muted-2)" stroke-width="2"/></pattern>';
    // build a stacked Y for every date: running cumulative % from the baseline up.
    // bands stack bottom->top by H.order; the none band sits on top, hatched.
    var nPts = tally.length;
    function pctOf(c){ return c / denom * 100; }
    var bandKeys = order.slice();                          // bottom -> top by palette order
    var bands = "";
    // cumulative top of the stack at each date, seeded at 0 (baseline = Y(0)).
    var cum = tally.map(function(){ return 0; });
    bandKeys.forEach(function(k){
      var lower = cum.slice();
      var upper = tally.map(function(t, i){ return cum[i] + pctOf(t.byKey[k] || 0); });
      for (var i = 0; i < nPts; i++){ cum[i] = upper[i]; }
      // skip an all-zero band so empty steps add no markup on sparse history.
      var any = upper.some(function(v, i){ return v - lower[i] > 0.0001; });
      if (!any){ return; }
      var topPts = tally.map(function(t, i){ return X(dayOff(t.date)).toFixed(1)+","+Y(upper[i]).toFixed(1); });
      var botPts = tally.map(function(t, i){ return X(dayOff(t.date)).toFixed(1)+","+Y(lower[i]).toFixed(1); }).reverse();
      var poly = topPts.concat(botPts).join(" ");
      bands += '<polygon class="tl-band" points="'+poly+'" fill="var('+varFor(k)+')"><title>'+esc(labelFor(k))+'</title></polygon>';
    });
    // the uncoloured bucket, hatched, stacked last (on top of the coloured bands).
    var noneLower = cum.slice();
    var noneUpper = tally.map(function(t, i){ return cum[i] + pctOf(t.none); });
    if (noneUpper.some(function(v, i){ return v - noneLower[i] > 0.0001; })){
      var nTop = tally.map(function(t, i){ return X(dayOff(t.date)).toFixed(1)+","+Y(noneUpper[i]).toFixed(1); });
      var nBot = tally.map(function(t, i){ return X(dayOff(t.date)).toFixed(1)+","+Y(noneLower[i]).toFixed(1); }).reverse();
      bands += '<polygon class="tl-band tl-stream-none" points="'+nTop.concat(nBot).join(" ")+'" fill="url(#tl-stream-hatch)"><title>'+esc(H.noneLabel)+'</title></polygon>';
    }
    // crosshair overlay shares the #7 data-snaps + the per-date counts so the
    // read-out (streamReadout) can show each step's count at the snapped date.
    var snaps = ax.snaps;
    var crossData = ' data-snaps="'+esc(JSON.stringify(snaps))+'" data-topy="'+ptop+'" data-boty="'+Y(0).toFixed(1)+'"'
      + ' data-stream="'+esc(JSON.stringify(tally))+'"';
    var crossLayer = '<line class="tl-cross" y1="'+ptop+'" y2="'+(ptop+ih).toFixed(1)+'"/>'
      + '<rect class="tl-crossarea" x="'+pl+'" y="'+ptop+'" width="'+iw.toFixed(1)+'" height="'+ih.toFixed(1)+'"/>';
    var deadline = deadlineRule(ax);                         // #19: shared rule, Flow mode too
    var chart = '<svg class="tl-chart tl-flow" viewBox="0 0 '+W+' '+Ht+'" role="img" tabindex="0"'+crossData
      + ' aria-label="Stacked colour completion over time. Hover or use the left and right arrow keys to read each snapshot.">'
      + '<defs>'+defs+'</defs>'+ax.weekBands+grid+bands+ax.xticks+ax.todayRule+deadline+crossLayer+'</svg>';
    // legend: one swatch per step (+ uncoloured), mirroring the band fills.
    var legend = order.map(function(k){
      return '<span class="tl-lg"><i style="background:var('+varFor(k)+')"></i>'+esc(labelFor(k))+'</span>';
    }).join("") + '<span class="tl-lg"><i class="tl-lg-hatch"></i>'+esc(H.noneLabel)+'</span>';
    var series = ax.series;
    var foot = '<div class="tl-foot"><span>'+esc(series[0].date)+'</span><span>'+esc(series[series.length-1].date)+'</span></div>';
    return { chart:chart, legend:legend, foot:foot };
  }
  // The Line/Flow toggle: a two-button segmented control that sets state.tlMode and
  // marks the active mode with aria-pressed. Default mode is Line (D2).
  function tlModeToggle(){
    var line = state.tlMode !== "flow";
    return '<div class="tl-mode" role="group" aria-label="Timeline chart mode">'
      + '<button type="button" class="chip tl-mode-btn" data-tlmode="line" aria-pressed="'+line+'" title="Per-master completion lines">Line</button>'
      + '<button type="button" class="chip tl-mode-btn" data-tlmode="flow" aria-pressed="'+(!line)+'" title="Stacked colour streamgraph over time">Flow</button>'
      + '</div>';
  }
  function hasTrend(){ return ((H.trend && H.trend.series) || []).length >= 2; }
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
  // ----- #14 This-week digest card ------------------------------------------
  // Snap an ISO target to the real H.trend.dates entry nearest (but not after) it,
  // falling back to the earliest date when the target predates all history. Lets the
  // digest "label honestly": it always reports a date a snapshot actually exists for.
  function snapDate(dates, targetIso){
    var pick = dates[0];
    for (var i = 0; i < dates.length; i++){
      if (dates[i] <= targetIso) pick = dates[i]; else break;
    }
    return pick;
  }
  // ISO date N days before another ISO date (UTC midnight, timezone-stable).
  function isoMinusDays(iso, days){
    var d = new Date(iso + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() - days);
    return d.toISOString().slice(0, 10);
  }
  // Diff over [isoA, isoB] for the focused master, or rolled up across every master
  // when none is selected: advanced/regressed are summed, the net % is the mean of the
  // per-master nets so it stays on the same 0-100 scale as diffCounts' deltaPct.
  function rollupDiff(isoA, isoB){
    if (state.master != null) return diffCounts(state.master, isoA, isoB);
    var advanced = 0, regressed = 0, unchanged = 0, netSum = 0, n = 0;
    H.masters.forEach(function(m){
      var c = diffCounts(m.id, isoA, isoB);
      advanced += c.advanced; regressed += c.regressed; unchanged += c.unchanged;
      netSum += c.deltaPct; n++;
    });
    return { advanced:advanced, regressed:regressed, unchanged:unchanged,
             deltaPct: n ? Math.round(netSum / n) : 0 };
  }
  function weekDigest(){
    var dates = (H.trend && H.trend.dates) || [];
    if (dates.length < 2) return "";
    var today = (H.trend && H.trend.today) || dates[dates.length-1];
    // snap a ~7-days-before-today target onto a real snapshot; fall back to "since you
    // started" when there is under a week of history (weekAgo lands on the first date).
    var weekAgo = snapDate(dates, isoMinusDays(today, 7));
    var started = weekAgo === dates[0]
      && new Date(today+"T00:00:00Z").getTime() - new Date(dates[0]+"T00:00:00Z").getTime() < 7*86400000;
    var label = started ? "since you started" : "vs " + esc(dateLabel(weekAgo));
    var cur = rollupDiff(weekAgo, today);
    // prior 7-day window: from a snapped ~7-days-before-weekAgo date up to weekAgo. Only
    // meaningful when a real earlier snapshot exists, otherwise the arrow is suppressed.
    var priorAnchor = snapDate(dates, isoMinusDays(weekAgo, 7));
    var hasPrior = priorAnchor !== weekAgo;
    var prior = hasPrior ? rollupDiff(priorAnchor, weekAgo) : null;
    var arrow = "", arrowCls = "tl-d-flat", arrowTitle = "No earlier week to compare";
    if (prior){
      var diff = cur.deltaPct - prior.deltaPct;
      arrow = diff > 0 ? "▲" : (diff < 0 ? "▼" : "▬");
      arrowCls = diff > 0 ? "tl-d-up" : (diff < 0 ? "tl-d-down" : "tl-d-flat");
      arrowTitle = "This week's net " + (cur.deltaPct>=0?"+":"") + cur.deltaPct
        + "% vs prior week " + (prior.deltaPct>=0?"+":"") + prior.deltaPct + "%";
    }
    var net = (cur.deltaPct>=0?"+":"") + cur.deltaPct + "%";
    // honest scope label: rolled up across every master, or the focused master's name.
    var scope = "all masters";
    if (state.master != null){ var mm = masterById(state.master); scope = mm ? esc(mm.name) : ""; }
    return '<div class="tl-digest" role="group" aria-label="This week digest">'
      + '<div class="tl-digest-head"><span class="tl-digest-title">This week</span>'
      + '<span class="tl-digest-sub">'+label+(scope?' · '+scope:'')+'</span></div>'
      + '<div class="tl-digest-body">'
      + '<span class="tl-digest-net '+(cur.deltaPct>=0?"tl-d-up":"tl-d-down")+'">'+net+' net</span>'
      + '<span class="tl-digest-arrow '+arrowCls+'" title="'+arrowTitle+'" aria-label="'+arrowTitle+'">'+arrow+'</span>'
      + '</div>'
      + '<div class="tl-digest-stats"><span class="dz dz-up">↑ '+cur.advanced+' advanced</span>'
      + '<span class="dz dz-down">↓ '+cur.regressed+' regressed</span></div></div>';
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
  // ----- #15 full-history regression log + chart flags -----------------------
  // The active master for the full-history walk: the selected one, else the first.
  // Distinct from regressionCard()/H.changes (last-save delta only) — this walks the
  // entire snapshot history.
  function reglogMaster(){ return state.master || (H.masters[0] && H.masters[0].id); }
  // Walk consecutive H.trend.dates for one master: for each adjacent pair compare
  // stateAt(prev) vs stateAt(curr) and collect every glyph whose rank dropped
  // (rankOf(now) < rankOf(was); a missing/uncoloured key reads as -1, so "-> none"
  // counts as backward via rankOf's -1). Newest-first, one row per backward move.
  function regressionWalk(){
    var mid = reglogMaster();
    var dates = (H.trend && H.trend.dates) || [];
    if (!mid || dates.length < 2) return [];
    var hits = [];
    for (var i = 1; i < dates.length; i++){
      var before = stateAt(mid, dates[i-1]), after = stateAt(mid, dates[i]);
      var names = {};
      for (var n1 in before){ names[n1] = true; }
      for (var n2 in after){ names[n2] = true; }
      for (var name in names){
        var was = before[name]; if (was == null) was = -1;
        var nw = after[name]; if (nw == null) nw = -1;
        if (rankOf(nw) < rankOf(was)){                     // backward; -> uncoloured ranks -1
          hits.push({ name:name, was:was, nw:nw, date:dates[i] });
        }
      }
    }
    hits.reverse();                                        // newest-first
    return hits;
  }
  // The set of snapshot dates carrying >=1 regression, for the chart tick flags.
  function regressionDates(){
    var out = {};
    regressionWalk().forEach(function(h){ out[h.date] = true; });
    return out;
  }
  // Newest-first was->now swatch table: top 8 + a "show all" expander (reuses the
  // ovCard data-ovexpand idiom via state.ovExpand.reglog), rows open the journey
  // modal. Renders nothing when the whole history is clean.
  function regressionLog(){
    var hits = regressionWalk();
    if (!hits.length) return "";
    var open = !!state.ovExpand.reglog;
    var list = open ? hits : hits.slice(0, 8);
    var rows = list.map(function(it){
      return '<div class="rg-row" data-jglyph="'+esc(it.name)+'"><span class="rg-n">'+esc(it.name)+'</span>'
        + swatchFor(it.was)+'<span class="rg-ar">→</span>'+swatchFor(it.nw)
        + '<span class="rg-when">'+esc(dateLabel(it.date))+'</span></div>';
    }).join("");
    var head = '<div class="tl-reglog-h"><span>Moved backward over time ('+hits.length+')</span>'
      + (hits.length > 8 ? '<button type="button" class="chip tl-reglog-all" data-ovexpand="reglog">'
          + (open ? "Show top 8" : "Show all "+hits.length)+'</button>' : '')+'</div>';
    return '<div class="tl-reglog">'+head+'<div class="tl-reglog-rows">'+rows+'</div></div>';
  }
  // ----- #17 per-category progress lanes over time ---------------------------
  function categoryLanes(){
    var dates = (H.trend && H.trend.dates) || [];
    if (dates.length < 1) return "";
    // Map each glyph to its category from the parallel H.glyphNames / H.categories
    // arrays, grouping the glyph names by category (empty categories never appear).
    var allNames = H.glyphNames || [], allCats = H.categories || [], groups = {};
    for (var gi = 0; gi < allNames.length; gi++){
      var gcat = allCats[gi] || "Other";
      (groups[gcat] || (groups[gcat] = [])).push(allNames[gi]);
    }
    var cats = Object.keys(groups);
    if (!cats.length) return "";
    var mid = reglogMaster();
    if (!mid) return "";
    var sparse = dates.length < 3;                 // 1-2 snapshots: bar, no over-time line
    var weight = stepWeights().weight;             // shared palette-order step weights
    // Graded completion % for one category at one snapshot date: sum the step weights
    // over that category's glyphs (reconstructed via stateAt) over the category's glyph
    // count, on the same 0-100 graded scale as the master/overall cards.
    var laneStatePct = function(names, iso){
      var st = stateAt(mid, iso), sum = 0;
      for (var i = 0; i < names.length; i++){
        var w = weight[st[names[i]]]; if (w) sum += w;
      }
      return names.length ? Math.round(sum / names.length * 100) : 0;
    };
    // Tiny completion-over-time polyline (reuses the chart's Y-flip idiom, scaled to a
    // mini box); only drawn when there are >=2 snapshots to connect.
    var laneSpark = function(values){
      var n = values.length, w = 64, h = 16, pad = 1.5, iw = w - pad*2, ih = h - pad*2;
      if (n < 2) return "";
      var pts = values.map(function(v, i){
        var x = pad + i/(n-1)*iw;
        var y = pad + ih - Math.max(0, Math.min(100, v))/100*ih;
        return x.toFixed(1)+","+y.toFixed(1);
      }).join(" ");
      return '<svg class="tl-lane-spark" width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'" aria-hidden="true">'
        + '<polyline points="'+pts+'" fill="none"/></svg>';
    };
    // ~a week before the latest snapshot, snapped onto a real snapshot date.
    var today = (H.trend && H.trend.today) || dates[dates.length-1];
    var weekAgo = snapDate(dates, isoMinusDays(today, 7));
    var lanes = cats.map(function(cat){
      var names = groups[cat];
      var values = dates.map(function(d){ return laneStatePct(names, d); });
      var cur = values[values.length-1];
      var prevPct = laneStatePct(names, weekAgo);
      var delta = cur - prevPct;
      return { cat:cat, count:names.length, values:values, cur:cur, delta:delta };
    });
    // laggard-first: lowest current % on top (name as a stable tie-breaker).
    lanes.sort(function(a, b){ return (a.cur - b.cur) || (a.cat < b.cat ? -1 : 1); });
    var rows = lanes.map(function(ln){
      var arrow = ln.delta > 0 ? "▲" : (ln.delta < 0 ? "▼" : "▬");
      var arrowCls = ln.delta > 0 ? "tl-d-up" : (ln.delta < 0 ? "tl-d-down" : "tl-d-flat");
      var deltaTxt = (ln.delta>0?"+":"")+ln.delta+"% vs "+esc(dateLabel(weekAgo));
      var mid2 = sparse
        ? '<span class="tl-lane-bar"><span style="width:'+ln.cur+'%"></span></span>'
        : laneSpark(ln.values);
      return '<div class="tl-lane">'
        + '<span class="tl-lane-n" title="'+esc(ln.cat)+'">'+esc(ln.cat)+' <small>('+ln.count+')</small></span>'
        + '<span class="tl-lane-mid">'+mid2+'</span>'
        + '<span class="tl-lane-pct">'+ln.cur+'%</span>'
        + '<span class="tl-lane-d '+arrowCls+'" title="'+deltaTxt+'" aria-label="'+deltaTxt+'">'+arrow+'</span>'
        + '</div>';
    }).join("");
    return '<div class="tl-lanes"><div class="tl-lanes-h">By category'
      + (sparse ? ' · current %' : ' · over time')+'</div>'+rows+'</div>';
  }
  // ----- #18 per-script progress lanes over time -----------------------------
  // Mirror of categoryLanes (#17) but grouped by the per-glyph H.scripts array
  // (writing systems: Latin, Cyrillic, Greek, ...) instead of H.categories.
  function scriptLanes(){
    var dates = (H.trend && H.trend.dates) || [];
    if (dates.length < 1) return "";
    // Map each glyph to its script from the parallel H.glyphNames / H.scripts
    // arrays, grouping the glyph names by script (empty scripts never appear).
    var allNames = H.glyphNames || [], allScripts = H.scripts || [], groups = {};
    for (var gi = 0; gi < allNames.length; gi++){
      var gscript = allScripts[gi] || "Other";
      (groups[gscript] || (groups[gscript] = [])).push(allNames[gi]);
    }
    var scripts = Object.keys(groups);
    if (!scripts.length) return "";
    var mid = reglogMaster();
    if (!mid) return "";
    var sparse = dates.length < 3;                 // 1-2 snapshots: bar, no over-time line
    var weight = stepWeights().weight;             // shared palette-order step weights
    // Graded completion % for one script at one snapshot date: sum the step weights
    // over that script's glyphs (reconstructed via stateAt) over the script's glyph
    // count, on the same 0-100 graded scale as the master/overall cards.
    var laneStatePct = function(names, iso){
      var st = stateAt(mid, iso), sum = 0;
      for (var i = 0; i < names.length; i++){
        var w = weight[st[names[i]]]; if (w) sum += w;
      }
      return names.length ? Math.round(sum / names.length * 100) : 0;
    };
    // Tiny completion-over-time polyline (reuses the chart's Y-flip idiom, scaled to a
    // mini box); only drawn when there are >=2 snapshots to connect.
    var laneSpark = function(values){
      var n = values.length, w = 64, h = 16, pad = 1.5, iw = w - pad*2, ih = h - pad*2;
      if (n < 2) return "";
      var pts = values.map(function(v, i){
        var x = pad + i/(n-1)*iw;
        var y = pad + ih - Math.max(0, Math.min(100, v))/100*ih;
        return x.toFixed(1)+","+y.toFixed(1);
      }).join(" ");
      return '<svg class="tl-lane-spark" width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'" aria-hidden="true">'
        + '<polyline points="'+pts+'" fill="none"/></svg>';
    };
    // ~a week before the latest snapshot, snapped onto a real snapshot date.
    var today = (H.trend && H.trend.today) || dates[dates.length-1];
    var weekAgo = snapDate(dates, isoMinusDays(today, 7));
    var lanes = scripts.map(function(script){
      var names = groups[script];
      var values = dates.map(function(d){ return laneStatePct(names, d); });
      var cur = values[values.length-1];
      var prevPct = laneStatePct(names, weekAgo);
      var delta = cur - prevPct;
      return { script:script, count:names.length, values:values, cur:cur, delta:delta };
    });
    // laggard-first: lowest current % on top (name as a stable tie-breaker).
    lanes.sort(function(a, b){ return (a.cur - b.cur) || (a.script < b.script ? -1 : 1); });
    var rows = lanes.map(function(ln){
      var arrow = ln.delta > 0 ? "▲" : (ln.delta < 0 ? "▼" : "▬");
      var arrowCls = ln.delta > 0 ? "tl-d-up" : (ln.delta < 0 ? "tl-d-down" : "tl-d-flat");
      var deltaTxt = (ln.delta>0?"+":"")+ln.delta+"% vs "+esc(dateLabel(weekAgo));
      var mid2 = sparse
        ? '<span class="tl-lane-bar"><span style="width:'+ln.cur+'%"></span></span>'
        : laneSpark(ln.values);
      return '<div class="tl-lane">'
        + '<span class="tl-lane-n" title="'+esc(ln.script)+'">'+esc(ln.script)+' <small>('+ln.count+')</small></span>'
        + '<span class="tl-lane-mid">'+mid2+'</span>'
        + '<span class="tl-lane-pct">'+ln.cur+'%</span>'
        + '<span class="tl-lane-d '+arrowCls+'" title="'+deltaTxt+'" aria-label="'+deltaTxt+'">'+arrow+'</span>'
        + '</div>';
    }).join("");
    return '<div class="tl-lanes"><div class="tl-lanes-h">By script'
      + (sparse ? ' · current %' : ' · over time')+'</div>'+rows+'</div>';
  }
  // ----- #19 deadline marker + on-track verdict -----------------------------
  // The target date persists in localStorage, keyed by the family name (D4) so it
  // stays offline-safe and per-font. Empty by default → the feature is dormant
  // (no rule on the chart, no verdict chips) until a date is entered.
  function deadlineKey(){ return "cfd-deadline:" + (H.family || ""); }
  function getDeadline(){
    try { return localStorage.getItem(deadlineKey()) || ""; } catch(e){ return ""; }
  }
  function setDeadline(iso){
    try {
      if (iso){ localStorage.setItem(deadlineKey(), iso); }
      else { localStorage.removeItem(deadlineKey()); }
    } catch(e){}
  }
  // Dashed-red vertical rule + flag at the target date's X, reusing #7's calendar
  // axis date->X math (ax.dayOff + ax.X). A target beyond the plotted span clamps
  // to the right edge and carries an offset label so it never draws off-chart.
  function deadlineRule(ax){
    var iso = getDeadline();
    if (!iso) return "";
    var off = ax.dayOff(iso);
    if (isNaN(off)) return "";
    var beyond = off > ax.lastOff;
    var x = beyond ? ax.X(ax.lastOff) : ax.X(Math.max(0, off));
    var topY = ax.ptop, botY = ax.ptop + ax.ih;
    var lab = dateLabel(iso) + (beyond ? " →" : "");
    var pillW = lab.length * 5.5 + 12;
    var pillX = Math.min(ax.X(ax.lastOff) + ax.pr - pillW, Math.max(ax.pl, x - pillW/2));
    return '<g class="tl-deadline" aria-hidden="true">'
      + '<line class="tl-deadline-rule" x1="'+x.toFixed(1)+'" y1="'+topY+'" x2="'+x.toFixed(1)+'" y2="'+botY.toFixed(1)+'"/>'
      + '<rect class="tl-deadline-pill" x="'+pillX.toFixed(1)+'" y="'+(topY-1)+'" width="'+pillW.toFixed(1)+'" height="13" rx="6"/>'
      + '<text class="tl-deadline-t" x="'+(pillX+pillW/2).toFixed(1)+'" y="'+(topY+8.5)+'" text-anchor="middle">'+esc(lab)+'</text>'
      + '</g>';
  }
  // Whole UTC days from today (H.trend.today, else the last snapshot) up to the
  // target. Negative when the target is already in the past; timezone-stable.
  function daysUntil(iso){
    var dates = (H.trend && H.trend.dates) || [];
    var today = (H.trend && H.trend.today) || dates[dates.length-1];
    if (!today || !iso) return null;
    var ms = new Date(iso+"T00:00:00Z").getTime() - new Date(today+"T00:00:00Z").getTime();
    if (isNaN(ms)) return null;
    return Math.round(ms / 86400000);
  }
  // The date control + per-master verdict chips. Each chip compares the master's
  // forecast.etaIso (estimated finish at the recent pace) against the target:
  //   green  — ETA on or before the target (on track)
  //   amber  — ETA slightly past (within a grace window of the days remaining)
  //   red    — ETA well past, or no honest ETA at all (flat/regressing pace)
  // and shows the required catch-up pace = remaining / daysUntilTarget (glyphs/day)
  // so a behind master gets an actionable number, not just a colour.
  function deadlinePanel(){
    var iso = getDeadline();
    var input = '<div class="tl-deadline-bar"><label class="tl-deadline-l" for="cfd-deadline">Target date</label>'
      + '<input type="date" id="cfd-deadline" value="'+esc(iso)+'"'+(H.trend && H.trend.today ? ' max="9999-12-31"' : '')+' aria-label="Project deadline target date"/></div>';
    if (!iso) return '<div class="tl-verdicts" role="group" aria-label="Deadline">'+input+'</div>';
    var forecast = (H.trend && H.trend.forecast) || {};
    var days = daysUntil(iso);
    var chips = H.masters.map(function(m){
      var fc = forecast[m.id] || {};
      var eta = fc.etaIso || null;
      var remaining = fc.remaining != null ? fc.remaining : null;
      // verdict: a master already finished is on track; otherwise classify by ETA.
      var cls, note;
      if (remaining === 0){ cls = "tl-v-ok"; note = "done"; }
      else if (!eta){ cls = "tl-v-late"; note = "no ETA at current pace"; }
      else {
        // grace window scales with the runway: a forecast within ~15% of the days
        // remaining counts as amber rather than a hard red.
        var grace = days != null && days > 0 ? Math.max(2, Math.round(days * 0.15)) : 2;
        var etaMs = new Date(eta+"T00:00:00Z").getTime();
        var tgtMs = new Date(iso+"T00:00:00Z").getTime();
        var overDays = Math.round((etaMs - tgtMs) / 86400000);
        if (overDays <= 0){ cls = "tl-v-ok"; note = "ETA " + esc(dateLabel(eta)); }
        else if (overDays <= grace){ cls = "tl-v-amber"; note = esc(dateLabel(eta)) + " · " + overDays + "d late"; }
        else { cls = "tl-v-late"; note = esc(dateLabel(eta)) + " · " + overDays + "d late"; }
      }
      // required catch-up pace to land on the target = remaining / daysUntilTarget.
      // Only meaningful with a positive runway and work left to do.
      var pace = "";
      if (remaining != null && remaining > 0 && days != null && days > 0){
        var perDay = remaining / days;
        pace = '<span class="tl-v-pace">'+(perDay >= 10 ? Math.round(perDay) : perDay.toFixed(1))+'/day to hit it</span>';
      } else if (remaining != null && remaining > 0 && days != null && days <= 0){
        pace = '<span class="tl-v-pace">target passed</span>';
      }
      return '<span class="tl-verdict '+cls+'" title="'+esc(m.name+" — "+note)+'">'
        + '<b class="tl-v-name">'+esc(m.name)+'</b>'
        + '<span class="tl-v-note">'+note+'</span>'+pace+'</span>';
    }).join("");
    var runway = days != null
      ? (days > 0 ? days + " day" + (days===1?"":"s") + " to go" : (days===0 ? "due today" : (-days) + " day" + (days===-1?"":"s") + " overdue"))
      : "";
    return '<div class="tl-verdicts" role="group" aria-label="Deadline and on-track verdict">'
      + input
      + (runway ? '<span class="tl-deadline-runway">'+runway+'</span>' : "")
      + '<div class="tl-verdict-row">'+chips+'</div></div>';
  }
  // ----- #11 Time Machine scrubber -------------------------------------------
  // D3: the main heatmap lives in the Overview tab, so the Timeline tab renders its
  // OWN compact heatmap and replays it day by day. The master scrubbed is the focused
  // one, else the first (same anchor the lanes use). The scrub index is clamped onto
  // a real H.trend.dates entry; null means "latest snapshot".
  function scrubMaster(){ return reglogMaster(); }
  // The snapshot index currently scrubbed: state.tlScrub clamped to the dates range,
  // defaulting to the latest snapshot when unset.
  function scrubIndex(){
    var dates = (H.trend && H.trend.dates) || [];
    if (!dates.length) return -1;
    var idx = state.tlScrub == null ? dates.length-1 : state.tlScrub;
    return Math.max(0, Math.min(dates.length-1, idx));
  }
  // Recolour the compact Time-Machine grid in place to the master's colour state at
  // the scrubbed date. Reconstructs each cell's key via stateAt (no interpolation) and
  // writes it back with the SAME color-mix idiom applyBeforeAfter uses, so dark/light
  // themes and the swatch tokens stay consistent. Throttled to rAF by scrubSet.
  function scrubRecolour(){
    var grid = document.querySelector(".tl-machine .tl-machine-grid");
    if (!grid) return;
    var dates = (H.trend && H.trend.dates) || [];
    var idx = scrubIndex();
    if (idx < 0 || !dates[idx]) return;
    var mid = scrubMaster();
    var st = stateAt(mid, dates[idx]);
    // #12: diff against the previous snapshot's state so each scrub step can flag the
    // glyphs that moved THIS day. The first snapshot has no predecessor -> no diff.
    var prev = idx > 0 ? stateAt(mid, dates[idx-1]) : null;
    // Reduced-motion (or the test hook): swap the pulsing ring for a static border via
    // the CSS variant, but the chip count below is still computed + shown either way.
    var noAnim = window.__cfdNoAnim ||
      (window.matchMedia && window.matchMedia("(prefers-reduced-motion:reduce)").matches);
    var advanced = 0, regressed = 0;
    var cells = grid.querySelectorAll(".cell");
    for (var i=0;i<cells.length;i++){
      var cell = cells[i], name = cell.getAttribute("data-glyph");
      var key = (name != null && st[name] != null) ? st[name] : -1;
      var v = varFor(key);
      cell.style.background = "color-mix(in srgb,var("+v+") 35%,transparent)";
      cell.classList.remove("tl-ring", "tl-ring-up", "tl-ring-down");
      if (prev){
        var was = (name != null && prev[name] != null) ? prev[name] : -1;
        var dir = rankOf(key) - rankOf(was);
        if (dir !== 0){
          var ringCell = cell;
          ringCell.classList.add("tl-ring", dir > 0 ? "tl-ring-up" : "tl-ring-down");
          if (dir > 0) advanced++; else regressed++;
          if (!noAnim){
            // transient pulse: drop the class after the keyframe so the next identical
            // step can re-trigger it (reduced-motion keeps the static border in place).
            setTimeout((function(el){ return function(){
              el.classList.remove("tl-ring", "tl-ring-up", "tl-ring-down");
            }; })(ringCell), 650);
          }
        }
      }
    }
    var lab = document.querySelector(".tl-machine .tl-scrub-date");
    if (lab) lab.textContent = dateLabel(dates[idx]);
    // live "+A, -R today" chip: the per-step net of glyphs that moved this day.
    var chip = document.querySelector(".tl-machine .tl-scrub-diff");
    if (chip){
      chip.innerHTML = prev
        ? '<span class="du">+'+advanced+'</span>, <span class="dd">−'+regressed+'</span> today'
        : "";
    }
  }
  // Set the scrub index (clamped), keep the range input + state in sync, and recolour
  // the grid throttled to a single rAF per frame so a fast drag stays smooth.
  var scrubRaf = 0;
  function scrubSet(idx){
    var dates = (H.trend && H.trend.dates) || [];
    if (!dates.length) return;
    state.tlScrub = Math.max(0, Math.min(dates.length-1, idx));
    var input = document.querySelector(".tl-machine .tl-scrub");
    if (input && String(input.value) !== String(state.tlScrub)){ input.value = state.tlScrub; }
    if (scrubRaf) return;                       // coalesce bursts of input events
    scrubRaf = requestAnimationFrame(function(){ scrubRaf = 0; scrubRecolour(); });
  }
  // Keyboard on the scrubber: Left/Right step +-1 day, Home/End jump to the ends.
  function scrubKey(evt){
    var input = evt.target.closest && evt.target.closest(".tl-scrub");
    if (!input) return;
    var dates = (H.trend && H.trend.dates) || [];
    if (!dates.length) return;
    var cur = scrubIndex(), next = cur;
    if (evt.key === "ArrowLeft"){ next = cur-1; }
    else if (evt.key === "ArrowRight"){ next = cur+1; }
    else if (evt.key === "Home"){ next = 0; }
    else if (evt.key === "End"){ next = dates.length-1; }
    else return;
    evt.preventDefault();
    scrubSet(next);
  }
  // Play auto-advances through the snapshots (one step per ~700ms) then stops at the
  // end. Disabled under 3 snapshots; reduced-motion (or the test hook) refuses to
  // start so the page never auto-animates against the user's preference — dragging
  // still snaps instantly. A second click stops an in-flight playback.
  var scrubTimer = 0;
  function scrubStopPlay(){
    if (scrubTimer){ clearInterval(scrubTimer); scrubTimer = 0; }
    var btn = document.querySelector(".tl-machine .tl-scrub-play");
    if (btn){ btn.setAttribute("aria-pressed", "false"); btn.textContent = "▶ Play"; }
  }
  function scrubPlay(){
    var dates = (H.trend && H.trend.dates) || [];
    if (dates.length < 3) return;
    if (scrubTimer){ scrubStopPlay(); return; }
    var noAnim = window.__cfdNoAnim ||
      (window.matchMedia && window.matchMedia("(prefers-reduced-motion:reduce)").matches);
    if (noAnim) return;                         // reduced motion: no autoplay
    if (scrubIndex() >= dates.length-1){ scrubSet(0); }   // replay from the start
    var btn = document.querySelector(".tl-machine .tl-scrub-play");
    if (btn){ btn.setAttribute("aria-pressed", "true"); btn.textContent = "❚❚ Pause"; }
    scrubTimer = setInterval(function(){
      var i = scrubIndex();
      if (i >= dates.length-1){ scrubStopPlay(); return; }
      scrubSet(i+1);
    }, 700);
  }
  // Build one compact cell for the scrub grid: a div carrying data-glyph + the
  // letterform (if the model embedded a path for this master), recoloured on render
  // to the master's colour at the scrubbed date via the shared color-mix idiom.
  function timeMachine(){
    var dates = (H.trend && H.trend.dates) || [];
    if (dates.length < 2) return "";            // <2 snapshots: nothing to replay
    var mid = scrubMaster();
    if (!mid) return "";
    var idx = scrubIndex();
    var st = stateAt(mid, dates[idx]);
    var names = H.glyphNames || [];
    var paths = (H.paths && H.paths[mid]) || {};
    var cells = names.map(function(name){
      var key = (st[name] != null) ? st[name] : -1;
      var v = varFor(key);
      var p = paths[name];
      var inner = p ? '<svg viewBox="'+esc(p.vb)+'" preserveAspectRatio="xMidYMid meet"><path d="'+esc(p.d)+'"/></svg>' : '';
      return '<span class="cell'+(p ? ' glyph' : '')+'" data-glyph="'+esc(name)+'"'
        + ' style="background:color-mix(in srgb,var('+v+') 35%,transparent)"'
        + ' title="'+esc(name)+'" aria-hidden="true">'+inner+'</span>';
    }).join("");
    var canPlay = dates.length >= 3;            // autoplay needs >=3 snapshots
    var controls = '<div class="tl-scrub-bar">'
      + '<button type="button" class="chip tl-scrub-play" aria-pressed="false"'
      + (canPlay ? "" : ' disabled aria-disabled="true" title="Needs at least 3 snapshots"')
      + '>▶ Play</button>'
      + '<input type="range" class="tl-scrub" min="0" max="'+(dates.length-1)+'" step="1" value="'+idx+'"'
      + ' aria-label="Scrub through snapshot history" aria-valuetext="'+esc(dateLabel(dates[idx]))+'"/>'
      + '<span class="tl-scrub-date" aria-live="polite">'+esc(dateLabel(dates[idx]))+'</span>'
      // #12: live "+A, -R today" chip near the slider; filled by scrubRecolour.
      + '<span class="tl-scrub-diff" aria-live="polite"></span>'
      + '</div>';
    return '<div class="tl-machine" role="group" aria-label="Time Machine: replay the heatmap by date">'
      + '<div class="tl-machine-h">Time Machine</div>'
      + controls
      + '<div class="tl-machine-grid heat" aria-label="Glyph colours at the scrubbed date">'+cells+'</div>'
      + '</div>';
  }
  // ----- #20 rich onboarding seed states for sparse history -------------------
  // One builder for both early states. <2 snapshots: a skeleton preview (dashed
  // placeholder line + ghost dots + ONE real solid "today" dot from the single
  // snapshot) + locked preview chips + a "History: N of 60 days" meter. ==2: a
  // compact one-day diff (A/B picker hidden) + the same meter. >=3 never reaches
  // here (timelineView gates it). All theme-safe + a11y-labelled; reduced-motion
  // drops the skeleton shimmer via the shared __cfdNoAnim / matchMedia gate.
  function seedState(){
    var dates = (H.trend && H.trend.dates) || [];
    var noAnim = window.__cfdNoAnim ||
      (window.matchMedia && window.matchMedia("(prefers-reduced-motion:reduce)").matches);
    // shared "History: N of 60 days" meter; N is the real snapshot count, capped at 60.
    var n = Math.min(60, dates.length);
    var meterWidth = Math.round(n / 60 * 100);
    var meterLabel = "History: " + n + " of 60 days";
    var histMeter = '<div class="tl-histmeter" role="img" aria-label="'+esc(meterLabel)+'">'
      + '<span class="tl-histmeter-l">'+esc(meterLabel)+'</span>'
      + '<span class="tl-histmeter-bar"><i style="width:'+meterWidth+'%"></i></span></div>';
    if (dates.length === 2){
      // ==2 snapshots: a compact one-day diff (A/B picker stays hidden). Reuse the
      // existing diff engine over the only two dates we have.
      var midTwo = state.master || (H.masters[0] && H.masters[0].id);
      var c = diffCounts(midTwo, dates[0], dates[1]);
      var net = (c.deltaPct>=0?"+":"") + c.deltaPct + "%";
      return '<section class="tl-seed tl-seed-2" role="group" aria-label="Day-two progress">'
        + '<div class="tl-seed-head">First two days in</div>'
        + '<p class="tl-seed-line2">In 1 day you advanced <b>'+c.advanced+'</b> '
        + '<span class="tl-seed-net '+(c.deltaPct>=0?"tl-d-up":"tl-d-down")+'">('+net+')</span>.</p>'
        + '<p class="tl-seed-sub">Save again tomorrow to unlock the full timeline (forecast, streak, brush-compare).</p>'
        + histMeter
        + '</section>';
    }
    // <2 snapshots: skeleton preview. A dashed placeholder line + a couple of ghost
    // dots hint at the coming chart; ONE real solid "today" dot sits at the single
    // snapshot's completion % — the ghosts are decorative, the solid dot is the one
    // honest reading. No data invented.
    var single = (H.trend && H.trend.series && H.trend.series[0]) || null;
    var midOne = state.master || (H.masters[0] && H.masters[0].id);
    var pc = 0;
    if (single && midOne && single.masters[midOne] && single.masters[midOne].total){
      pc = single.masters[midOne].final / single.masters[midOne].total * 100;
    }
    var W = 320, Ht = 120, pad = 14, iw = W - pad*2, ih = Ht - pad*2;
    var gx = function(t){ return pad + t*iw; };                // t in [0,1]
    var gy = function(p){ return pad + ih - p/100*ih; };       // p in [0,100]
    var ghostLine = '<polyline class="tl-seed-ghost tl-seed-line" points="'
      + gx(0).toFixed(1)+','+gy(8).toFixed(1)+' '
      + gx(0.5).toFixed(1)+','+gy(22).toFixed(1)+' '
      + gx(1).toFixed(1)+','+gy(38).toFixed(1)+'"/>';
    var ghostDots = [0, 0.5].map(function(t, i){
      var gp = i === 0 ? 8 : 22;
      return '<circle class="tl-seed-ghost tl-seed-dot" cx="'+gx(t).toFixed(1)+'" cy="'+gy(gp).toFixed(1)+'" r="3"/>';
    }).join("");
    var todayDot = '<circle class="tl-seed-today" cx="'+gx(1).toFixed(1)+'" cy="'+gy(pc).toFixed(1)+'" r="4"><title>'
      + esc("Today · " + Math.round(pc) + "%") + '</title></circle>';
    var shimmer = noAnim ? "" : " tl-seed-shimmer";
    var skeleton = '<svg class="tl-seed-svg'+shimmer+'" viewBox="0 0 '+W+' '+Ht+'" role="img" aria-label="'
      + esc("One snapshot so far at " + Math.round(pc) + "%. The chart unlocks once a second day of history is saved.")+'">'
      + ghostLine + ghostDots + todayDot + '</svg>';
    // locked preview chips: Forecast / Streak / Compare, each muted "unlocks at 2 days".
    var locks = ["Forecast", "Streak", "Compare"].map(function(name){
      return '<span class="tl-lock" aria-disabled="true">'
        + '<span class="tl-lock-n">'+esc(name)+'</span>'
        + '<span class="tl-lock-h">unlocks at 2 days</span></span>';
    }).join("");
    return '<section class="tl-seed tl-seed-1" role="group" aria-label="Getting started">'
      + '<div class="tl-seed-head">Building your timeline</div>'
      + skeleton
      + '<p class="tl-seed-sub">Color Flow saves a snapshot each time you save the font. '
      + 'The chart unlocks at 2 days of history.</p>'
      + '<div class="tl-seed-locks">'+locks+'</div>'
      + histMeter
      + '</section>';
  }
  function timelineView(){
    // #20: <3 snapshots routes to the rich seed states (a skeleton + locked chips at
    // <2, a compact one-day diff at ==2). The full view needs >=3 to be meaningful.
    var dates = (H.trend && H.trend.dates) || [];
    if (dates.length < 3){
      return '<section class="tl-empty">'+seedState()+'</section>';
    }
    // D2: Line is the default; Flow renders the stacked colour streamgraph (#5).
    var parts = state.tlMode === "flow" ? streamParts(680, 200) : trendParts(680, 200);
    // #14: This-week digest tops the tab (above the chart), per D1.
    return '<section class="timeline">'+weekDigest()+'<div class="tl-chartbar">'+tlModeToggle()
      + '<div class="tl-legend">'+parts.legend+'</div></div>'
      + parts.chart+parts.foot+dateDiffPanel()+deadlinePanel()+timeMachine()+categoryLanes()+scriptLanes()+regressionLog()+'</section>';
  }
  function compareView(){
    // columns = steps (+None); rows = masters, labelled by the master name.
    var head = '<th scope="col">Master</th>'+H.steps.map(function(s){
      return '<th scope="col" title="'+esc(s.label)+'" aria-label="'+esc(s.label)+'"><span class="dot" style="background:var('+varFor(s.key)+')"></span></th>';
    }).join("");
    var body = H.masters.map(function(m){
      var aa = esc(m.name);
      var cells = H.steps.map(function(s){
        var p = pct(countFor(m,s.key),H.glyphTotal);
        return '<td><span class="cmpbar" style="width:'+p+'%;background:var('+varFor(s.key)+')"></span><span class="cmpn">'+p+'%</span></td>';
      }).join("");
      var cls = state.master==null ? "" : (m.id===state.master ? " cmp-sel" : " cmp-dim");
      return '<tr class="cmprow'+cls+'" data-m="'+esc(m.id)+'" title="Click to focus this master"><th scope="row" class="cmp-m" aria-label="'+esc(m.name)+'">'+aa+'</th>'+cells+'</tr>';
    }).join("");
    return '<div class="cmp-wrap"><table class="cmp"><caption>Step completion by master</caption><thead><tr>'+head+'</tr></thead><tbody>'+body+'</tbody></table></div>';
  }
  function renderBody(){
    return state.view==="compare" ? compareView()
      : state.view==="coverage" ? coverageView()
      : state.view==="timeline" ? timelineView()
      : tabsView();
  }

  // ----- Per-glyph step-journey sparkline on heatmap hover (#12) -----
  function sparkline(journey){
    var n = journey.length, gap = 2, bw = 9, h = 18, w = n*bw + (n-1)*gap;
    var rects = journey.map(function(k,i){
      var v = k===-1 ? "--c-none" : "--c"+k;
      return '<rect x="'+(i*(bw+gap))+'" y="0" width="'+bw+'" height="'+h+'" rx="2" fill="var('+v+')"/>';
    }).join("");
    return '<svg class="spark" width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'" aria-hidden="true">'+rects+'</svg>';
  }
  function journeyFor(name){
    return H.journeys && H.journeys[state.master] && H.journeys[state.master][name];
  }
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
  function showTip(name, x, y){
    var journey = journeyFor(name);
    var edited = (H.lastEdit && H.lastEdit[name] != null) ? H.lastEdit[name] : null;
    if (!journey && edited == null){ hideTip(); return; }
    var tip = document.getElementById("cfd-tip");
    if (!tip){ tip = document.createElement("div"); tip.id = "cfd-tip"; tip.className = "cfd-tip"; document.body.appendChild(tip); }
    var head = esc(name) + (edited != null ? ' · edited '+edited+'d ago' : ' · step journey');
    tip.innerHTML = '<div class="tip-h">'+head+'</div>' + (journey ? sparkline(journey) : "");
    tip.style.display = "block";
    var left = Math.min(x+14, window.innerWidth - tip.offsetWidth - 8);
    tip.style.left = Math.max(8, left)+"px";
    tip.style.top = Math.max(8, y - tip.offsetHeight - 12)+"px";
  }
  function hideTip(){ var tip = document.getElementById("cfd-tip"); if (tip) tip.style.display = "none"; }

  // ----- #6 snapping crosshair read-out -------------------------------------
  // Index of the snapshot the crosshair currently rests on (-1 = hidden). Kept on
  // the module so Left/Right keyboard stepping shares the same anchor as the pointer.
  var crossIdx = -1;
  // The exact completion % of master m.id at snapshot p (same maths trendParts uses
  // for the dots). Honest: reads the stored finals, never interpolates between dates.
  function crossPctAt(p, masterId){
    var mp = p.masters && p.masters[masterId];
    return mp && mp.total ? mp.final/mp.total*100 : 0;
  }
  // Float the cfd-tip read-out: the snapshot date + every master's exact % there.
  // In Flow mode the chart carries data-stream (per-date per-step tallies) instead
  // of per-master %, so the read-out lists each step's count at the snapped date.
  function crossReadout(svg, idx, clientX){
    var series = (H.trend && H.trend.series) || [];
    var p = series[idx]; if (!p){ hideTip(); return; }
    var tip = document.getElementById("cfd-tip");
    if (!tip){ tip = document.createElement("div"); tip.id = "cfd-tip"; tip.className = "cfd-tip"; document.body.appendChild(tip); }
    var streamData = svg.getAttribute("data-stream");
    var rows;
    if (streamData){
      var tally; try { tally = JSON.parse(streamData); } catch(e){ tally = []; }
      var t = tally[idx] || { byKey:{}, none:0 };
      rows = (H.order||[]).map(function(k){
        return '<div class="tl-cross-row"><i style="background:var('+varFor(k)+')"></i>'
          + esc(labelFor(k))+' <b>'+(t.byKey[k]||0)+'</b></div>';
      }).join("")
        + '<div class="tl-cross-row"><i class="tl-lg-hatch"></i>'+esc(H.noneLabel)+' <b>'+(t.none||0)+'</b></div>';
    } else {
      rows = H.masters.map(function(m, i){
        if (!(p.masters && p.masters[m.id])) return "";
        var col = "hsl("+masterHue(i)+",70%,55%)";
        var bold = state.master!=null && m.id===state.master;
        return '<div class="tl-cross-row'+(bold?" tl-sel":"")+'"><i style="background:'+col+'"></i>'
          + esc(m.name)+' <b>'+Math.round(crossPctAt(p, m.id))+'%</b></div>';
      }).join("");
    }
    tip.innerHTML = '<div class="tip-h">'+esc(dateLabel(p.date))+' · '+esc(p.date)+'</div>'+rows;
    tip.style.display = "block";
    var box = svg.getBoundingClientRect();
    var anchorX = clientX != null ? clientX : box.left + box.width/2;
    var left = Math.min(anchorX+14, window.innerWidth - tip.offsetWidth - 8);
    tip.style.left = Math.max(8, left)+"px";
    tip.style.top = Math.max(8, box.top - tip.offsetHeight - 4)+"px";
  }
  // Snap the guide + marker to snapshot `idx` and float the read-out. Reduced motion
  // (or the test hook) means the guide jumps instantly — it never animates anyway,
  // but we honour the shared gate by skipping any future transition opt-in.
  function crossSnapTo(svg, idx, clientX){
    var snaps; try { snaps = JSON.parse(svg.getAttribute("data-snaps")||"[]"); } catch(e){ snaps = []; }
    if (!snaps.length || idx < 0 || idx >= snaps.length){ crossHide(svg); return; }
    crossIdx = idx;
    var snap = snaps[idx];
    var topY = parseFloat(svg.getAttribute("data-topy")) || 0;
    var botY = parseFloat(svg.getAttribute("data-boty")) || 0;
    var guide = svg.querySelector(".tl-cross");
    var mark = svg.querySelector(".tl-cross-mark");
    if (guide){ guide.setAttribute("x1", snap.x); guide.setAttribute("x2", snap.x); guide.style.display = "block"; }
    if (mark){
      // marker sits on the selected master's value (honest dot) when one is focused,
      // else parks at the top of the plot so it stays a pure x-locator.
      var my = topY;
      var series = (H.trend && H.trend.series) || [];
      if (state.master!=null && series[idx]){ my = botY - crossPctAt(series[idx], state.master)/100*(botY-topY); }
      mark.setAttribute("cx", snap.x); mark.setAttribute("cy", my.toFixed(1)); mark.style.display = "block";
    }
    crossReadout(svg, idx, clientX);
  }
  function crossHide(svg){
    crossIdx = -1;
    var guide = svg && svg.querySelector(".tl-cross"); if (guide) guide.style.display = "none";
    var mark = svg && svg.querySelector(".tl-cross-mark"); if (mark) mark.style.display = "none";
    hideTip();
  }
  // Pointer handler: map the client X into SVG user-space (viewBox width / box width),
  // then pick the NEAREST snapshot X — discrete series, so no interpolation. Resolves
  // the chart from the event target so it works as a delegated #cfd-body listener.
  function crosshairMove(evt){
    var svg = evt.target.closest && evt.target.closest(".tl-chart");
    if (!svg){ return; }
    var snaps; try { snaps = JSON.parse(svg.getAttribute("data-snaps")||"[]"); } catch(e){ snaps = []; }
    if (!snaps.length){ return; }
    var box = svg.getBoundingClientRect();
    if (!box.width){ return; }
    var vb = svg.viewBox && svg.viewBox.baseVal;
    var vbw = (vb && vb.width) || box.width;
    var ux = (evt.clientX - box.left) / box.width * vbw;   // pointer X in SVG user-space
    var nearest = 0, best = Infinity;
    for (var i=0;i<snaps.length;i++){
      var d = Math.abs(snaps[i].x - ux);
      if (d < best){ best = d; nearest = i; }
    }
    crossSnapTo(svg, nearest, evt.clientX);
  }
  // Pointer left the chart: drop the guide + read-out.
  function crosshairLeave(evt){
    var svg = evt.target.closest && evt.target.closest(".tl-chart");
    if (svg){ crossHide(svg); }
  }
  // Keyboard: Left/Right step the snapped snapshot and refresh the same read-out.
  function crosshairKey(evt){
    if (evt.key!=="ArrowLeft" && evt.key!=="ArrowRight"){ return; }
    // a focused brush handle owns the arrow keys (brushKey) — don't also step the crosshair.
    if (evt.target.closest && evt.target.closest(".tl-brush-h")){ return; }
    var svg = evt.target.closest && evt.target.closest(".tl-chart");
    if (!svg){ return; }
    var snaps; try { snaps = JSON.parse(svg.getAttribute("data-snaps")||"[]"); } catch(e){ snaps = []; }
    if (!snaps.length){ return; }
    evt.preventDefault();
    var idx = crossIdx < 0 ? (evt.key==="ArrowLeft" ? snaps.length-1 : 0)
      : Math.max(0, Math.min(snaps.length-1, crossIdx + (evt.key==="ArrowRight" ? 1 : -1)));
    crossSnapTo(svg, idx, null);
  }

  // ----- #8 brush-to-compare ------------------------------------------------
  // The two snapshot indices the brush currently spans (low..high). Live during a
  // drag/nudge so the band + handles stay coherent before the diff settles.
  var brushA = -1, brushB = -1;
  // Read the snapshot X anchors off the SVG (same data-snaps the crosshair uses).
  function brushSnaps(svg){
    var snaps; try { snaps = JSON.parse(svg.getAttribute("data-snaps")||"[]"); } catch(e){ snaps = []; }
    return snaps;
  }
  // Invert the forward X scale: map a client X to the NEAREST snapshot index. The
  // forward map is X(off)=pl+off/lastOff*iw drawn into the viewBox, so we only need
  // the snapshot X anchors and the box->viewBox ratio to recover the date under the
  // pointer — no interpolation, the series is discrete.
  function brushIndexFromClient(svg, clientX){
    var snaps = brushSnaps(svg); if (!snaps.length){ return -1; }
    var box = svg.getBoundingClientRect(); if (!box.width){ return -1; }
    var vb = svg.viewBox && svg.viewBox.baseVal;
    var vbw = (vb && vb.width) || box.width;
    var ux = (clientX - box.left) / box.width * vbw;       // pointer X in SVG user-space
    var nearest = 0, best = Infinity;
    for (var i=0;i<snaps.length;i++){
      var d = Math.abs(snaps[i].x - ux);
      if (d < best){ best = d; nearest = i; }
    }
    return nearest;
  }
  // Position the translucent band + the two handles for the current brush span.
  function brushPaint(svg){
    var snaps = brushSnaps(svg);
    var band = svg.querySelector(".tl-brush");
    var handles = svg.querySelectorAll(".tl-brush-h");
    if (brushA < 0 || brushB < 0 || !snaps.length){
      if (band){ band.style.display = "none"; }
      return;
    }
    var lo = Math.min(brushA, brushB), hi = Math.max(brushA, brushB);
    var xLo = snaps[lo].x, xHi = snaps[hi].x;
    if (band){
      band.setAttribute("x", xLo);
      band.setAttribute("width", Math.max(0, xHi - xLo).toFixed(1));
      band.style.display = "block";
    }
    for (var i=0;i<handles.length;i++){
      var edge = handles[i].getAttribute("data-edge");
      var hx = (edge === "a") ? xLo : xHi;
      handles[i].setAttribute("x", (hx - 3).toFixed(1));   // centre the 6px-wide handle
      handles[i].style.display = "block";
    }
  }
  // Settle the compare: write the two snapped dates into state.dateA/dateB and the
  // <select> a11y fallback, then re-render so dateDiffPanel recomputes advanced/
  // regressed/unchanged/net for the range. Reduced-motion is honoured implicitly —
  // dateDiffPanel just renders numbers, no live animation runs while dragging.
  function brushApply(svg){
    var snaps = brushSnaps(svg);
    if (brushA < 0 || brushB < 0 || !snaps.length){ return; }
    var lo = Math.min(brushA, brushB), hi = Math.max(brushA, brushB);
    state.dateA = snaps[lo].d;
    state.dateB = snaps[hi].d;
    update();
  }
  // Named brush handler: pointerdown on the chart starts a drag; pointermove paints
  // the live band; pointerup snaps both endpoints into the compare. A drag that
  // starts on a handle drags that single edge; otherwise both edges track the drag.
  function brushMove(evt){
    var svg = evt.target.closest && evt.target.closest(".tl-chart");
    if (!svg){ return; }
    var snaps = brushSnaps(svg); if (snaps.length < 2){ return; }
    var start = brushIndexFromClient(svg, evt.clientX); if (start < 0){ return; }
    var onHandle = evt.target.closest && evt.target.closest(".tl-brush-h");
    var dragEdge = onHandle ? onHandle.getAttribute("data-edge") : null;
    if (dragEdge){
      // dragging a single existing handle; keep the other edge anchored.
      if (dragEdge === "a"){ brushA = start; } else { brushB = start; }
    } else {
      brushA = start; brushB = start;     // fresh drag: collapse, then expand on move
    }
    brushPaint(svg);
    evt.preventDefault();
    function onPointerMove(moveEvt){
      var idx = brushIndexFromClient(svg, moveEvt.clientX); if (idx < 0){ return; }
      if (dragEdge === "a"){ brushA = idx; }
      else if (dragEdge === "b"){ brushB = idx; }
      else { brushB = idx; }
      brushPaint(svg);
    }
    function onPointerUp(){
      document.removeEventListener("pointermove", onPointerMove);
      document.removeEventListener("pointerup", onPointerUp);
      brushApply(svg);
    }
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
  }
  // Keyboard: Left/Right nudge the focused handle by one snapshot, then settle.
  function brushKey(evt){
    if (evt.key!=="ArrowLeft" && evt.key!=="ArrowRight"){ return; }
    var handle = evt.target.closest && evt.target.closest(".tl-brush-h");
    if (!handle){ return; }
    var svg = handle.closest(".tl-chart"); if (!svg){ return; }
    var snaps = brushSnaps(svg); if (snaps.length < 2){ return; }
    evt.preventDefault();
    var edge = handle.getAttribute("data-edge");
    // seed from the current compare endpoints if the brush has not been dragged yet,
    // so a keyboard-only user still gets a coherent range to nudge.
    if (brushA < 0 || brushB < 0){
      brushA = 0; brushB = snaps.length-1;
      for (var i=0;i<snaps.length;i++){
        if (state.dateA && snaps[i].d===state.dateA){ brushA = i; }
        if (state.dateB && snaps[i].d===state.dateB){ brushB = i; }
      }
    }
    var step = evt.key==="ArrowRight" ? 1 : -1;
    if (edge === "a"){ brushA = Math.max(0, Math.min(snaps.length-1, brushA + step)); }
    else { brushB = Math.max(0, Math.min(snaps.length-1, brushB + step)); }
    brushPaint(svg);
    brushApply(svg);
  }

  // Animate the heatmap cells between their last-run ("before") and current
  // ("after") colours by updating the cell background in place so the CSS
  // transition runs. The glyph drawn on top keeps its fixed ink colour.
  function applyBeforeAfter(){
    var cells = document.querySelectorAll(".heat .cell");
    for (var i=0;i<cells.length;i++){
      var cell = cells[i];
      var v = state.before ? cell.getAttribute("data-was") : cell.getAttribute("data-now");
      if (!v) continue;
      cell.style.background = "color-mix(in srgb,var("+v+") 35%,transparent)";
    }
  }

  function update(){
    hideTip();
    scrubStopPlay();                            // a full re-render replaces the scrub grid; drop any in-flight playback
    barsAnim = (state.master !== barMaster);   // re-fill the colour bar only when the master changed
    barMaster = state.master;
    document.getElementById("cfd-body").innerHTML = renderBody();
    document.documentElement.setAttribute("data-theme", state.theme);
    var cmp = document.getElementById("cfd-compare"); if (cmp) cmp.setAttribute("aria-pressed", state.view==="compare");
    var cov = document.getElementById("cfd-coverage"); if (cov) cov.setAttribute("aria-pressed", state.view==="coverage");
    var tl = document.getElementById("cfd-timeline"); if (tl) tl.setAttribute("aria-pressed", state.view==="timeline");
    var ov = document.getElementById("cfd-overview"); if (ov) ov.setAttribute("aria-pressed", state.view==="tabs");
    var sb = document.getElementById("cfd-sort"); if (sb) sb.textContent = "↕ Sort: "+(state.sort==="progress"?"progress":"workflow");
    paintScriptCards();
  }

  // Re-organise the heatmap when the focused colour changes (a FLIP animation):
  // snapshot every cell's box, swap the DOM to the recomposed grid, then play each
  // surviving cell from its old box to its new one — so the focused colour's cells
  // slide up and pack to the top while the rest slide out. Skips when there's no
  // heatmap, for reduced-motion users, or under the test hook. Only cells near the
  // viewport animate (off-screen ones just snap) to keep big grids smooth.
  function setFocus(fk){
    var heat = document.querySelector(".heat");
    var instant = !heat || window.__cfdNoAnim ||
      (window.matchMedia && window.matchMedia("(prefers-reduced-motion:reduce)").matches);
    if (instant){ state.focus = fk; update(); return; }
    var vh = window.innerHeight || 800, margin = 40;
    function near(r){ return r && r.bottom > -margin && r.top < vh + margin; }
    var first = {}, prevList = Array.prototype.slice.call(heat.querySelectorAll(".cell"));
    prevList.forEach(function(c){ first[c.getAttribute("data-glyph")] = c.getBoundingClientRect(); });

    state.focus = fk; update();

    var nh = document.querySelector(".heat");
    if (!nh) return;
    var seen = {}, play = [];
    Array.prototype.forEach.call(nh.querySelectorAll(".cell"), function(c){
      var key = c.getAttribute("data-glyph"); seen[key] = 1;
      var fr = first[key], lr = c.getBoundingClientRect();
      if (fr){                                              // survivor: slide old box -> new box
        var dx = fr.left - lr.left, dy = fr.top - lr.top;
        if ((dx || dy) && (near(fr) || near(lr))){ c.style.transition = "none"; c.style.transform = "translate("+dx+"px,"+dy+"px)"; play.push(c); }
      } else if (near(lr)){                                 // newly shown (e.g. on clear): scale in
        c.style.transition = "none"; c.style.opacity = "0"; c.style.transform = "scale(.55)"; play.push(c);
      }
    });

    var layer = null;                                       // removed cells -> clones that slide out
    var exiting = prevList.filter(function(c){ var k = c.getAttribute("data-glyph"); return !seen[k] && near(first[k]); });
    if (exiting.length){
      layer = document.createElement("div");
      layer.style.cssText = "position:fixed;inset:0;z-index:30;pointer-events:none";
      exiting.forEach(function(c){
        var r = first[c.getAttribute("data-glyph")], cl = c.cloneNode(true);
        cl.style.position = "fixed"; cl.style.margin = "0"; cl.style.pointerEvents = "none";
        cl.style.left = r.left+"px"; cl.style.top = r.top+"px"; cl.style.width = r.width+"px"; cl.style.height = r.height+"px";
        layer.appendChild(cl);
      });
      document.body.appendChild(layer);
    }

    requestAnimationFrame(function(){ requestAnimationFrame(function(){
      for (var i=0;i<play.length;i++){ var c = play[i];
        c.style.transition = "transform .44s cubic-bezier(.2,.7,.2,1),opacity .34s ease"; c.style.transform = ""; c.style.opacity = ""; }
      if (layer) Array.prototype.forEach.call(layer.children, function(cl){
        cl.style.transition = "transform .42s ease,opacity .42s ease"; cl.style.transform = "translateY(16px) scale(.5)"; cl.style.opacity = "0"; });
    }); });
    if (layer) setTimeout(function(){ if (layer.parentNode) layer.parentNode.removeChild(layer); }, 480);
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

  // ----- Status export: CSV / JSON for stakeholders + trackers (#22) -----
  function exportRows(){
    var rows = [];
    H.masters.forEach(function(m){
      H.steps.forEach(function(s){
        var c = countFor(m, s.key);
        rows.push({master:m.name, step:s.key, label:s.label, count:c, total:H.glyphTotal, pct:pct(c,H.glyphTotal)});
      });
      rows.push({master:m.name, step:"None", label:H.noneLabel, count:m.uncolored, total:H.glyphTotal, pct:pct(m.uncolored,H.glyphTotal)});
    });
    return rows;
  }
  function csvCell(value){
    var s = String(value==null ? "" : value);
    return /[",\n]/.test(s) ? '"'+s.replace(/"/g,'""')+'"' : s;
  }
  function exportCSV(){
    var lines = [["Family",H.family],["File",H.fileName],["Version",H.version],["Mode",H.mode],
                 ["Generated",H.generated],["Glyphs",H.glyphTotal]]
      .map(function(r){ return csvCell(r[0])+","+csvCell(r[1]); });
    lines.push("", ["Master","Step","Label","Count","Total","Percent"].join(","));
    exportRows().forEach(function(r){
      lines.push([r.master,r.step,r.label,r.count,r.total,r.pct].map(csvCell).join(","));
    });
    return lines.join("\n");
  }
  function exportJSON(){
    return JSON.stringify({
      family:H.family, fileName:H.fileName, version:H.version, mode:H.mode,
      generated:H.generated, glyphTotal:H.glyphTotal, steps:H.steps,
      masters:H.masters.map(function(m){
        return { id:m.id, name:m.name, counts:m.counts, uncolored:m.uncolored,
                 started:startedOf(m), total:H.glyphTotal };
      })
    }, null, 2);
  }
  function exportName(ext){
    return H.generated+"_"+String(H.family||"font").replace(/[^\w.-]+/g,"-")+"_Color-Flow."+ext;
  }
  function download(name, text, type){
    try {
      var url = URL.createObjectURL(new Blob([text], {type:type}));
      var a = document.createElement("a"); a.href = url; a.download = name;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setTimeout(function(){ URL.revokeObjectURL(url); }, 0);
      toast("Exported "+name);
    } catch(e){ toast("Export not supported here"); }
  }
  // ----- Full PDF report: a contents page with clickable jump links, then every
  //       section (overview, each master, compare, coverage, timeline) -----
  function printCoverageRows(){
    var cov = (H.coverage && H.coverage.byCategory) || {};
    var rows = cov[state.master] || [];
    if (!rows.length) return '<p class="empty">No coverage data.</p>';
    return '<div class="cov-rows">'+rows.map(function(r){
      return '<div class="cov-row"><span class="cov-name" title="'+esc(r.key)+'">'+esc(r.key)+'</span>'
        + covStacked(r) + '<span class="num">'+r.total+'</span></div>';
    }).join("")+'</div>';
  }
  function buildPrintReport(){
    var toc = [], secs = "";
    function add(id, title, inner){
      toc.push('<a class="ptab" href="#'+id+'">'+esc(title)+'</a>');
      secs += '<section class="psec" id="'+id+'"><h2 class="ph">'+esc(title)+'</h2>'+inner+'</section>';
    }
    add("psec-overview", "Overview", overall());
    H.masters.forEach(function(m){ add("psec-m-"+m.id, m.name, masterOverall(m)+heatmap(m)); });
    add("psec-compare", "Compare by master", compareView());
    add("psec-coverage", "Coverage by category", printCoverageRows());
    add("psec-timeline", "Progress over time", timelineView());
    return '<section class="pcover"><div class="pcover-ttl">'+esc(H.family)+'</div>'
      + '<div class="pcover-sub">Color Flow report · '+esc(H.fileName)+' · v'+esc(H.version)+' · '+esc(H.generated)+'</div>'
      + '<nav class="ptabs" aria-label="Contents">'+toc.join("")+'</nav></section>' + secs;
  }
  function printReport(){
    var host = document.getElementById("cfd-print");
    if (!host){ host = document.createElement("div"); host.id = "cfd-print"; document.body.appendChild(host); }
    host.innerHTML = buildPrintReport();
    try { window.print(); } catch(e){ toast("Print not supported here"); }
  }
  function runExport(fmt){
    if (fmt==="pdf"){ printReport(); }
    else if (fmt==="csv"){ download(exportName("csv"), exportCSV(), "text/csv"); }
    else if (fmt==="json"){ download(exportName("json"), exportJSON(), "application/json"); }
  }
  function closeExport(){ var m = document.getElementById("cfd-export-modal"); if (m) m.style.display = "none"; }
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
  function openExport(){
    var modal = document.getElementById("cfd-export-modal");
    if (!modal){
      modal = document.createElement("div"); modal.id = "cfd-export-modal"; modal.className = "cfd-modal";
      modal.innerHTML = '<div class="cfd-modal-box" role="dialog" aria-label="Export report" aria-modal="true">'
        + '<div class="cfd-modal-h">Export report</div><div class="cfd-cards">'
        + '<button type="button" class="cfd-card" data-fmt="pdf"><span class="cfd-card-ic">🖨</span><b>PDF</b><small>Full report · contents + all sections</small></button>'
        + '<button type="button" class="cfd-card" data-fmt="csv"><span class="cfd-card-ic">⤓</span><b>CSV</b><small>Per-step counts</small></button>'
        + '<button type="button" class="cfd-card" data-fmt="json"><span class="cfd-card-ic">{ }</span><b>JSON</b><small>Full summary</small></button>'
        + '</div></div>';
      document.body.appendChild(modal);
      modal.addEventListener("click", function(e){
        if (e.target===modal){ closeExport(); return; }
        var card = e.target.closest(".cfd-card"); if (!card) return;
        closeExport(); runExport(card.getAttribute("data-fmt"));
      });
    }
    modal.style.display = "flex";
  }

  function bind(){
    document.getElementById("cfd-theme").addEventListener("click", function(){
      state.theme = state.theme==="dark" ? "light" : "dark";
      try { localStorage.setItem("cfd-theme", state.theme); } catch(e){}
      document.documentElement.setAttribute("data-theme", state.theme);
    });
    // Switch view by chip. Leaving the Overview tab clears any colour focus, so the
    // tower discs + heatmap return to the full distribution (focus only lives in
    // Overview); the tower's render loop picks up the cleared state.focus next frame.
    function toggleView(name){
      var v = state.view===name ? "tabs" : name;
      if (v!=="tabs"){ state.focus = null; }
      state.view = v; update();
    }
    document.getElementById("cfd-overview").addEventListener("click", function(){ state.view = "tabs"; state.master = null; update(); });
    document.getElementById("cfd-compare").addEventListener("click", function(){ toggleView("compare"); });
    document.getElementById("cfd-coverage").addEventListener("click", function(){ toggleView("coverage"); });
    document.getElementById("cfd-timeline").addEventListener("click", function(){ toggleView("timeline"); });
    document.getElementById("cfd-export").addEventListener("click", openExport);
    document.getElementById("cfd-help").addEventListener("click", openHelp);
    document.addEventListener("keydown", function(e){
      if (e.key==="Escape"){ closeExport(); closeJourney(); closeHelp(); if (state.focus!==null){ setFocus(null); } }
    });
    var bodyEl = document.getElementById("cfd-body");
    bodyEl.addEventListener("mouseover", function(e){
      var cell = e.target.closest(".heat .cell"); if (cell) showTip(cell.getAttribute("data-glyph"), e.clientX, e.clientY);
    });
    bodyEl.addEventListener("mouseout", function(e){
      if (e.target.closest(".heat .cell")) hideTip();
    });
    bodyEl.addEventListener("click", function(e){
      var tab = e.target.closest(".tab"); if (tab){ state.master = tab.getAttribute("data-m"); update(); return; }
      var ox = e.target.closest("[data-ovexpand]"); if (ox){ var ok=ox.getAttribute("data-ovexpand"); state.ovExpand[ok]=!state.ovExpand[ok]; update(); return; }
      var cr = e.target.closest(".cmprow[data-m],.lb-row[data-m]"); if (cr){ var cid=cr.getAttribute("data-m"); state.master=(state.master===cid)?null:cid; update(); return; }
      var cg = e.target.closest("[data-cg]"); if (cg){ state.coverGroup = cg.getAttribute("data-cg"); update(); return; }
      var tm = e.target.closest("[data-tlmode]"); if (tm){ state.tlMode = tm.getAttribute("data-tlmode"); update(); return; }
      var gs = e.target.closest("[data-gsort]"); if (gs){ state.glyphSort = gs.getAttribute("data-gsort"); update(); return; }
      var fc = e.target.closest("[data-fclear]"); if (fc){ setFocus(null); return; }
      var jr = e.target.closest("[data-jglyph]"); if (jr){ openJourney(jr.getAttribute("data-jglyph")); return; }
      var jc = e.target.closest(".heat .cell"); if (jc && (e.metaKey || e.ctrlKey)){ e.preventDefault(); openJourney(jc.getAttribute("data-glyph")); return; }
      var ba = e.target.closest(".ba-toggle");
      if (ba){ e.preventDefault(); state.before = !state.before; ba.setAttribute("aria-pressed", state.before); ba.textContent = state.before ? "Before" : "After"; applyBeforeAfter(); return; }
      // #11 Time Machine: Play toggles autoplay (disabled <3 snapshots / reduced motion).
      var pl = e.target.closest(".tl-scrub-play");
      if (pl && !pl.disabled){ e.preventDefault(); scrubPlay(); return; }
    });
    bodyEl.addEventListener("change", function(e){
      if (e.target.id === "cfd-date-a"){ state.dateA = e.target.value; update(); }
      else if (e.target.id === "cfd-date-b"){ state.dateB = e.target.value; update(); }
      // #19: persist the deadline target (family-scoped) and re-render so the rule
      // + verdict chips refresh without a reload.
      else if (e.target.id === "cfd-deadline"){ setDeadline(e.target.value); update(); }
    });
    // #11 Time Machine: dragging the range slider scrubs the date; scrubSet throttles
    // the grid recolour to rAF so a fast drag stays smooth. A manual drag stops autoplay.
    bodyEl.addEventListener("input", function(e){
      var sc = e.target.closest && e.target.closest(".tl-scrub");
      if (sc){ scrubStopPlay(); scrubSet(parseInt(sc.value, 10) || 0); }
    });
    bodyEl.addEventListener("keydown", scrubKey);
    // #6 snapping crosshair: the chart SVG is rebuilt on every update(), so delegate
    // its pointer + keyboard interaction at the #cfd-body level (same idiom as the
    // heatmap tip above). pointermove snaps to the nearest snapshot; leaving the
    // chart hides the guide; Left/Right step snapshots while the chart is focused.
    bodyEl.addEventListener("pointermove", crosshairMove);
    bodyEl.addEventListener("pointerout", function(e){
      var chart = e.target.closest && e.target.closest(".tl-chart");
      if (chart && (!e.relatedTarget || !chart.contains(e.relatedTarget))){ crosshairLeave(e); }
    });
    bodyEl.addEventListener("keydown", crosshairKey);
    // #8 brush-to-compare: pointerdown on the chart starts a drag that paints a
    // band between two snapped snapshots and, on release, drives state.dateA/dateB
    // (dateDiffPanel recomputes the range). Arrow keys nudge a focused handle. The
    // <select> a11y fallback in dateDiffPanel stays synced via update().
    bodyEl.addEventListener("pointerdown", brushMove);
    bodyEl.addEventListener("keydown", brushKey);
    // Colour-bar segments live both in the static global bar and in the per-master
    // card (inside #cfd-body), so delegate their clicks at the document level.
    document.addEventListener("click", function(e){
      var seg = e.target.closest("[data-fkey]");
      if (!seg) return;
      var fk = parseInt(seg.getAttribute("data-fkey"),10);
      setFocus(state.focus===fk ? null : fk);
    });
  }
  // ----- Color Tower: one disc per master, the master navigator -------------
  // A persistent canvas in the left sidebar. Each disc is a blurred wheel of that
  // master's label-colour distribution; the focused (current) master lights up,
  // the rest are trimmed. Clicking a disc selects that master. Auto-spins.
  function initTower(){
    var cv = document.getElementById("cfd-tower-cv");
    if (!cv || !cv.getContext || !H.masters.length) return;
    var ctx = cv.getContext("2d");
    if (!ctx) return;                       // headless / no-canvas env: skip
    var EMPTYFILL = (getComputedStyle(document.documentElement).getPropertyValue("--track")||"").trim() || "#15171c";   // empty disc ~ page bg
    var W = cv.width, Hc = cv.height, FS = 320;
    // HiDPI: supersample every backing store by devicePixelRatio (capped at 3) while
    // keeping all geometry in CSS-pixel units. fit() recomputes dpr on resize; the
    // offscreen builders below read this same closure var. dpr=1 reproduces 1x exactly.
    var dpr = Math.min(window.devicePixelRatio || 1, 3);
    var DISC_ALPHA = 0.95, tilt = 0.5, trimVal = 0.5, opacityVal = 0.32;
    var rot = -0.5, focusAmt = [];
    var VISIBLE = Math.min(16, H.masters.length);   // discs shown at once
    var vt = 0;                                      // scroll: master index at window top
    function hueHsl(i){ return "hsl(" + Math.round((i/12)*360) + ",100%,55%)"; }
    // the ACTUAL Glyphs label colour for slot i (from the model / CSS vars), not a synthetic rainbow
    function slotColor(i){
      if (H.colors && H.colors[String(i)]) return H.colors[String(i)];
      var v=(getComputedStyle(document.documentElement).getPropertyValue("--c"+i)||"").trim();
      return v || hueHsl(i);
    }
    function countsOf(m){
      var c = [0,0,0,0,0,0,0,0,0,0,0,0], keys = m.keys || [];
      for (var i=0;i<keys.length;i++){ var k=keys[i]; if (k>=0 && k<12) c[k]++; }
      return c;
    }
    var UNCOL = "hsl(225,8%,4%)";   // dark neutral grey for the uncoloured share
    function buildField(counts, uncolored){
      var off=document.createElement("canvas"); off.width=off.height=Math.round(FS*dpr);
      var g=off.getContext("2d"); g.setTransform(dpr,0,0,dpr,0,0);
      var cx=FS/2, cy=FS/2, R=FS*0.46, sum=0, i;
      for (i=0;i<12;i++) sum+=counts[i];
      var total=sum+uncolored;
      if (total){
        // one wedge per present colour (hue) + the uncoloured share (grey), all
        // proportional to the master's glyph total so uncoloured glyphs show too
        var segs=[];
        for (i=0;i<12;i++){ if(counts[i]>0) segs.push([counts[i]/total, slotColor(i)]); }
        if (uncolored>0) segs.push([uncolored/total, UNCOL]);
        var filled=false;
        try {
          // true proportional wedges (hard edges): each colour spans exactly its
          // share. Two stops per wedge (start + end, same colour) give a crisp
          // boundary; the later blur softens it without distorting the proportion.
          var base=g.createConicGradient(-Math.PI/2,cx,cy), acc=0;
          for (i=0;i<segs.length;i++){
            base.addColorStop(Math.min(acc,1), segs[i][1]);
            acc+=segs[i][0];
            base.addColorStop(Math.min(acc,1), segs[i][1]);
          }
          g.fillStyle=base; g.fillRect(0,0,FS,FS); filled=true;
        } catch(e){ filled=false; }
        if (!filled){ var a=-Math.PI/2;
          for (i=0;i<segs.length;i++){ var a1=a+segs[i][0]*Math.PI*2;
            g.fillStyle=segs[i][1]; g.beginPath(); g.moveTo(cx,cy); g.arc(cx,cy,R*1.25,a,a1); g.closePath(); g.fill(); a=a1; } }
        var dk=g.createRadialGradient(cx,cy,0,cx,cy,R*0.72);
        dk.addColorStop(0,"rgba(0,0,0,0.58)"); dk.addColorStop(0.5,"rgba(0,0,0,0.26)"); dk.addColorStop(1,"rgba(0,0,0,0)");
        g.fillStyle=dk; g.beginPath(); g.arc(cx,cy,R*0.72,0,7); g.fill();
      }
      var bl=document.createElement("canvas"); bl.width=bl.height=Math.round(FS*dpr); var bg=bl.getContext("2d");
      bg.setTransform(dpr,0,0,dpr,0,0);
      bg.filter="blur("+Math.round(FS*0.125)+"px) saturate(1.6) brightness(0.92)"; bg.drawImage(off,0,0,FS,FS);
      bg.filter="none"; bg.globalCompositeOperation="destination-in";
      bg.fillStyle="#000"; bg.beginPath(); bg.arc(FS/2,FS/2,FS*0.5,0,7); bg.fill();
      bg.globalCompositeOperation="source-over";
      return bl;
    }
    // When a colour is focused (clicked in a progress bar), each disc shows only
    // that colour's share; everything else folds into the uncoloured grey. fk<0
    // or null restores the full label distribution.
    function focusedCounts(m, fk){
      var c = countsOf(m);
      if (fk==null) return { counts:c, uncolored:(m.uncolored||0) };                          // no focus -> full distribution
      if (fk<0 || fk>11) return { counts:[0,0,0,0,0,0,0,0,0,0,0,0], uncolored:(m.uncolored||0) };  // None focused -> grey share only
      var only=[0,0,0,0,0,0,0,0,0,0,0,0]; only[fk]=c[fk];
      return { counts:only, uncolored:(H.glyphTotal||0)-c[fk] };                               // one colour -> its wedge + grey rest
    }
    var FIELDS, EMPTY;
    function buildFields(fk){
      FIELDS = H.masters.map(function(m){ var d=focusedCounts(m,fk); return buildField(d.counts, d.uncolored); });
      EMPTY = H.masters.map(function(m){ var d=focusedCounts(m,fk), s=0, i; for(i=0;i<12;i++) s+=d.counts[i]; return (s+d.uncolored)===0; });
    }
    var curFocus = (state.focus==null?null:state.focus);
    buildFields(curFocus);
    var buf=document.createElement("canvas"); buf.width=Math.round(W*dpr); buf.height=Math.round(Hc*dpr); var bctx=buf.getContext("2d");
    bctx.setTransform(dpr,0,0,dpr,0,0);

    function paintDisc(g,fA,cx,cy,rx,ry,holeFrac,glow,empty){
      if (glow===undefined) glow=1;
      if (empty){   // no colours: a near-background tone at lower opacity (mixes with the bg)
        g.save(); g.translate(cx,cy); g.scale(1,ry/rx);
        g.globalAlpha=0.6; g.fillStyle=EMPTYFILL; g.beginPath(); g.arc(0,0,rx,0,7); g.fill(); g.globalAlpha=1;
        g.restore();
        return;
      }
      var o=rx*1.14;
      // matte colour disc: no outer halo glow, no surface gloss/sheen/frost
      g.save(); g.translate(cx,cy); g.scale(1,ry/rx); g.rotate(rot);
      g.beginPath(); g.arc(0,0,rx,0,7); g.clip();
      if (glow>1) g.filter="brightness("+(1+(glow-1)*0.7)+")";
      g.globalAlpha=DISC_ALPHA; g.drawImage(fA,-o,-o,o*2,o*2);
      g.filter="none"; g.globalAlpha=1; g.restore();
      // proportional-hole cut only (keeps the ring/tower read)
      g.save(); g.translate(cx,cy); g.scale(1,ry/rx); g.beginPath(); g.arc(0,0,rx,0,7); g.clip();
      if (holeFrac>0){ var hr=rx*0.26; g.globalCompositeOperation="destination-out";
        var pg=g.createRadialGradient(0,0,0,0,0,hr); pg.addColorStop(0,"rgba(0,0,0,1)"); pg.addColorStop(0.94,"rgba(0,0,0,1)"); pg.addColorStop(1,"rgba(0,0,0,0)");
        g.fillStyle=pg; g.beginPath(); g.arc(0,0,hr,0,7); g.fill(); g.globalCompositeOperation="source-over"; }
      g.restore();
      // subtle dark edge for definition (no bright highlight = no shine)
      g.save(); g.translate(cx,cy); g.scale(1,ry/rx);
      g.strokeStyle="rgba(0,0,0,0.16)"; g.lineWidth=1.5; g.beginPath(); g.arc(0,0,rx*0.992,0,7); g.stroke(); g.restore();
    }
    function shadowInto(g,cx,cy,rx,ry){
      g.save(); g.translate(cx,cy+ry*0.5); g.scale(1,ry/rx);
      var sh=g.createRadialGradient(0,0,0,0,0,rx); sh.addColorStop(0,"rgba(0,0,0,0.07)"); sh.addColorStop(0.7,"rgba(0,0,0,0.03)"); sh.addColorStop(1,"rgba(0,0,0,0)");
      g.fillStyle=sh; g.beginPath(); g.arc(0,0,rx,0,7); g.fill(); g.restore();
    }
    var geo={rx:0,ry:0,cx:0,topY:0,dz:0,vt:0};
    function selIndex(){ if (state.master==null) return -1; for (var i=0;i<H.masters.length;i++){ if (H.masters[i].id===state.master) return i; } return -1; }
    var prevSel=-1;
    function render(){
      ctx.setTransform(dpr,0,0,dpr,0,0);   // HiDPI: paint in CSS units at physical resolution (re-asserted each frame; save/restore below are balanced)
      ctx.clearRect(0,0,W,Hc);
      var M=H.masters.length; if (!M) return;
      var sel=selIndex(), maxTop=Math.max(0, M-VISIBLE);
      // scroll the focused master into view only when it's outside the window
      if (sel!==prevSel){
        if (sel>=0 && (sel < Math.floor(vt) || sel > Math.floor(vt)+VISIBLE-1)) vt = sel - Math.floor(VISIBLE/2);
        prevSel = sel;
      }
      vt = Math.max(0, Math.min(maxTop, vt));
      if (focusAmt.length!==M){ focusAmt=[]; for (var z=0;z<M;z++) focusAmt[z]=(z===sel?0:1); }
      for (var i=0;i<M;i++){ focusAmt[i] = (sel<0 || i===sel) ? 0 : 1; }   // instant switch, no fade
      var rx=Math.min(92, W*0.42), ry=rx*tilt;
      var topY=ry+16, botPad=ry+12;
      var dz=VISIBLE>1?Math.min(60,(Hc-topY-botPad)/(VISIBLE-1)):0, cx=W/2;
      var winBot=topY+(VISIBLE-1)*dz, fade=dz*1.1;
      geo={rx:rx,ry:ry,cx:cx,topY:topY,dz:dz,vt:vt};
      function cyOf(i){ return topY+(i-vt)*dz; }
      function vis(i){ var c=cyOf(i); return c>=topY-dz*1.6 && c<=winBot+dz*1.6; }
      // soft top/bottom of the scroll window: a vertical alpha mask (purely a
      // function of y) so the no-overlap group composite still works
      function edgeFade(g){
        function cl(v){ return Math.max(0,Math.min(1,v)); }
        var gr=g.createLinearGradient(0,0,0,Hc);
        gr.addColorStop(0,"rgba(0,0,0,1)");                       // top: no fade, fully visible
        gr.addColorStop(cl(winBot/Hc),"rgba(0,0,0,1)");
        gr.addColorStop(cl((winBot+fade)/Hc),"rgba(0,0,0,0)");    // bottom fade only
        g.save(); g.globalCompositeOperation="destination-in"; g.fillStyle=gr; g.fillRect(0,0,W,Hc); g.restore();
      }
      function group(idxs){
        if (!idxs.length) return;
        bctx.clearRect(0,0,W,Hc);
        for (var k=0;k<idxs.length;k++){ var ii=idxs[k], cyy=cyOf(ii); if(!EMPTY[ii]) shadowInto(bctx,cx,cyy,rx,ry); paintDisc(bctx,FIELDS[ii],cx,cyy,rx,ry,1,0,EMPTY[ii]); }
        bctx.save(); bctx.globalCompositeOperation="source-atop"; bctx.fillStyle="rgba(0,0,0,"+trimVal+")"; bctx.fillRect(0,0,W,Hc); bctx.restore();
        edgeFade(bctx);
        ctx.save(); ctx.globalAlpha=opacityVal; ctx.drawImage(buf,0,0,W,Hc); ctx.restore();
      }
      function focusDisc(ii){ var amt=focusAmt[ii], cyy=cyOf(ii);
        bctx.clearRect(0,0,W,Hc); if(!EMPTY[ii]) shadowInto(bctx,cx,cyy,rx,ry); paintDisc(bctx,FIELDS[ii],cx,cyy,rx,ry,1,1-amt,EMPTY[ii]);
        var trim=amt*trimVal; if (trim>0){ bctx.save(); bctx.globalCompositeOperation="source-atop"; bctx.fillStyle="rgba(0,0,0,"+trim+")"; bctx.fillRect(0,0,W,Hc); bctx.restore(); }
        edgeFade(bctx);
        ctx.save(); ctx.globalAlpha=1-amt*(1-opacityVal); ctx.drawImage(buf,0,0,W,Hc); ctx.restore();
      }
      if (sel<0){
        for (var n=M-1;n>=0;n--){ if (vis(n)) focusDisc(n); }   // no selection: every disc full
      } else {
        var below=[], above=[];
        for (var n2=M-1;n2>=0;n2--){ if (!vis(n2)) continue; if (n2>sel) below.push(n2); else if (n2<sel) above.push(n2); }
        group(below); if (vis(sel)) focusDisc(sel); group(above);
      }
    }
    // Size the canvas to fill the main column down to the footer, and show as
    // many discs as fit (the rest stay scrollable via the wheel).
    function fit(){
      var main=document.getElementById("cfd-main"), host=cv.parentNode;
      var availW=(host&&host.clientWidth)||240, availH=(main&&main.clientHeight)||0;
      if (availH<240) availH=560;                      // stacked/mobile or pre-layout -> fallback
      dpr=Math.min(window.devicePixelRatio || 1, 3);   // HiDPI: recompute on resize (display may move screens)
      cv.style.width=availW+"px"; cv.style.height=availH+"px";   // CSS size stays in logical px (hit-test/layout unchanged)
      cv.width=Math.round(availW*dpr); cv.height=Math.round(availH*dpr);   // backing store = physical px
      W=availW; Hc=availH;                                       // logical drawing units (CSS px)
      buf.width=Math.round(W*dpr); buf.height=Math.round(Hc*dpr); bctx.setTransform(dpr,0,0,dpr,0,0);
      var rx=Math.min(92,W*0.42), ry=rx*tilt, topY=ry+16, botPad=ry+12;   // mirror render() geometry
      VISIBLE=Math.max(4, Math.min(H.masters.length, Math.floor((Hc-topY-botPad)/34)+1));
      vt=Math.max(0, Math.min(Math.max(0,H.masters.length-VISIBLE), vt));
    }
    fit();
    window.addEventListener("resize", fit);
    function loop(){
      var fk = (state.focus==null?null:state.focus);
      if (fk!==curFocus){ curFocus=fk; buildFields(curFocus); }   // colour focus changed -> refilter discs
      rot+=0.0096; render(); requestAnimationFrame(loop);
    }
    cv.addEventListener("wheel", function(e){ e.preventDefault();
      vt += e.deltaY*0.02; vt=Math.max(0, Math.min(Math.max(0,H.masters.length-VISIBLE), vt));
    }, {passive:false});
    cv.addEventListener("click", function(e){
      var rect=cv.getBoundingClientRect();
      var px=(e.clientX-rect.left)*(W/rect.width), py=(e.clientY-rect.top)*(Hc/rect.height);
      for (var i=0;i<H.masters.length;i++){ var cy=geo.topY+(i-geo.vt)*geo.dz;
        if (cy<geo.topY-geo.dz*1.6 || cy>geo.topY+(VISIBLE-1)*geo.dz+geo.dz*1.6) continue;
        var ex=(px-geo.cx)/geo.rx, ey=(py-cy)/geo.ry;
        if (ex*ex+ey*ey<=1){ var id=H.masters[i].id;
          state.master = (state.master===id) ? null : id;   // click the selected disc -> clear focus
          update(); return; } }                              // keep the current view (tabs/coverage/...)
    });
    // up/down arrows switch the focused master (up = toward the top disc)
    window.addEventListener("keydown", function(e){
      if (e.key!=="ArrowUp" && e.key!=="ArrowDown") return;
      var t=e.target; if (t && (t.tagName==="INPUT"||t.tagName==="TEXTAREA"||t.isContentEditable)) return;
      var M=H.masters.length; if (!M) return;
      var cur=selIndex(), step=(e.key==="ArrowDown")?1:-1;
      var ni = cur<0 ? (step>0?0:M-1) : Math.max(0, Math.min(M-1, cur+step));
      e.preventDefault();
      state.master=H.masters[ni].id; update();   // keep the current view
    });
    loop();
  }

  function init(){
    document.getElementById("cfd-app").innerHTML =
      header() + toolbar()
      + '<div id="cfd-main"><aside id="cfd-tower" aria-label="Masters"><canvas id="cfd-tower-cv" width="240" height="560"></canvas></aside><div id="cfd-body"></div></div>'
      + '<footer class="ft"><span class="ft-l">'+esc(H.fileName)+' · v'+esc(H.version)+'</span>'
      + '<span class="ft-r">ColorFlow Report — '+esc(H.generated)+'</span></footer>';
    bind(); update(); initTower();
    window.__cfdExport = { csv: exportCSV, json: exportJSON, rows: exportRows, printHTML: buildPrintReport };
    // After the first paint the bars have run their fill animation once; stop
    // tagging them ".intro" so later re-renders don't re-animate.
    requestAnimationFrame(function(){ document.body.classList.add("ready"); });
  }
  // Decompress the gzipped model (base64 -> bytes -> gunzip stream -> JSON),
  // then boot. embed_model only ever emits the gzipped block; if it's missing the
  // page is corrupt, so fail loudly rather than silently null-deref a plain block.
  function b64bytes(b64){ var bin=atob(b64), n=bin.length, a=new Uint8Array(n); for (var i=0;i<n;i++) a[i]=bin.charCodeAt(i); return a; }
  function loadModel(){
    var gz = document.getElementById("cfd-model-gz");
    if (!gz)
      return Promise.reject(new Error("Report data block is missing — this file looks incomplete."));
    if (typeof DecompressionStream==="undefined" || typeof Response==="undefined" || typeof Blob==="undefined")
      return Promise.reject(new Error("This report needs a modern browser (gzip decompression)."));
    var stream = new Blob([b64bytes(gz.textContent.trim())]).stream().pipeThrough(new DecompressionStream("gzip"));
    return new Response(stream).text().then(function(t){ return JSON.parse(t); });
  }
  function start(){
    loadModel().then(function(model){
      H = model; lastOrder = H.order.length ? H.order[H.order.length-1] : null;
      init();
    }).catch(function(err){
      var app = document.getElementById("cfd-app");
      if (app) app.innerHTML = '<p style="padding:48px 24px;color:#888;font:14px/1.5 system-ui,sans-serif">'+esc(err && err.message || "Could not load the report data.")+'</p>';
    });
  }
  if (document.readyState!=="loading") start();
  else document.addEventListener("DOMContentLoaded", start);
})();
"""
