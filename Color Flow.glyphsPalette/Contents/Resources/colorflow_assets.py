# encoding: utf-8
"""Inline assets + HTML shell for the Color Font Dashboard.

Turns the data model (see colorflow_dashboard.build_model) into one
self-contained, offline .html with inline CSS + inline vanilla JS. No network,
no dependencies. The model is the single source of truth the JS app renders.
"""

from __future__ import annotations

import json
from xml.sax.saxutils import escape as xesc


def embed_model(model: dict) -> str:
    """Serialise the model into a ``<script type="application/json">`` block.
    ``<`` / ``>`` / ``&`` are escaped to their JSON ``\\uXXXX`` forms so no glyph
    name or label can terminate the script element (e.g. ``</script>``)."""
    payload = (json.dumps(model, ensure_ascii=False)
               .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))
    return f'<script type="application/json" id="cfd-model">{payload}</script>'


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
    ``data:`` URI (built by the model). Empty when the model has none. The URI is
    safe to embed unquoted: base64 PNG and URL-encoded SVG contain no ``"``."""
    favicon = model.get("favicon")
    if not favicon:
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
@media (prefers-reduced-motion:reduce){body,body.ready{opacity:1;transition:none}.cell{transition:none}.seg.intro>span{animation:none}.heat,.heat.fading{transition:none;opacity:1}}
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
.seg.intro>span{animation:segGrow .4s ease backwards;animation-delay:calc(var(--i,0)*45ms)}
.ov-recipe{margin-top:10px;font-size:var(--fs-xs);color:var(--muted)}
.ov-recipe b{color:var(--text)}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;font-size:var(--fs-xs);color:var(--muted)}
.legend .lg{display:inline-flex;align-items:center;gap:5px}
.ov-extra{display:grid;grid-template-columns:repeat(auto-fit,minmax(238px,1fr));gap:14px;margin-top:16px}
.ov-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.ov-card h4{margin:0 0 10px;font-size:var(--fs-2xs);font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
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
.dp-bar{display:flex;height:14px;border-radius:5px;overflow:hidden;background:var(--track);margin-bottom:10px}
.dp-seg{display:block;height:100%}
.dp-seg.dp-all,.dp-leg i.dp-all{background:var(--accent)}
.dp-seg.dp-some,.dp-leg i.dp-some{background:color-mix(in srgb,var(--accent) 42%,var(--track))}
.dp-seg.dp-none,.dp-leg i.dp-none{background:color-mix(in srgb,var(--text) 7%,var(--track))}
.dp-leg{display:flex;flex-wrap:wrap;gap:12px;font-size:var(--fs-2xs);color:var(--muted)}
.dp-leg i{display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.dp-leg b{color:var(--text)}
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
.tl-dot{transition:opacity .2s ease}
.tl-dot.tl-dim{opacity:.16}
.tl-lg{transition:opacity .2s ease}
.tl-lg.tl-dim{opacity:.4}
.tl-lg.tl-sel{font-weight:600}
.tl-grid{stroke:var(--track);stroke-width:1}
.tl-axis{fill:var(--muted-2);font-size:10px}
.tl-foot{display:flex;justify-content:space-between;font-size:var(--fs-2xs);color:var(--muted-2);margin-top:6px}
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
.toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%) translateY(10px);background:var(--surface);border:1px solid var(--border-2);color:var(--text);border-radius:var(--r-sm);padding:8px 14px;font-size:var(--fs-sm);opacity:0;pointer-events:none;transition:opacity .15s,transform .15s}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
button:focus-visible,input:focus-visible,summary:focus-visible,.cell:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
"""


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
    master: null,                          // no master selected -> global overview
    view: "tabs", before: false, sort: "workflow",
    coverGroup: "byCategory", glyphSort: "category", focus: null,
    theme: savedTheme || (prefersLight ? "light" : "dark")
  };
  // One-shot: the colour bars animate-fill only on the first render, not on
  // every re-render (tab switch, focus, before/after). Flipped true after init.
  var introDone = false;

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
  function finished(k){
    if (!H.order.length) return false;
    if (H.mode==="free") return H.order.indexOf(String(k))!==-1;
    return String(k)===lastOrder;
  }
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
    var head = '<b>'+compP+'% complete</b> · '+a.started+'/'+a.grand+' started ('+pct(a.started,a.grand)+'%)';
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
      + '<div class="ov-main"><div class="ov-head">'+head+'</div>'
      + '<div class="seg'+(introDone?"":" intro")+'" role="img" aria-label="Colour distribution across the font">'+segParts+'</div>'
      + '<div class="legend">'+legend+'</div>'+recipeLine+'</div></section>';
  }

  // The selected master rendered like the overall card (ring + stacked bar +
  // legend), but scoped to this one master instead of the whole font.
  function masterOverall(m){
    var total = H.glyphTotal;
    var started = total - m.uncolored;
    var completion = (H.mode==="free" || !lastOrder) ? started : (countFor(m,lastOrder)||0);
    var compP = pct(completion,total), startP = pct(started,total);
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
      + '<div class="seg'+(introDone?"":" intro")+'" role="img" aria-label="'+esc(m.name+" colour distribution")+'">'+segParts+'</div>'
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
  // Ranked masters by graded step progress; click a row to focus that master.
  function leaderboard(){
    var rows = H.masters.map(function(m){ return {id:m.id, name:m.name, p:masterPct(m), any:masterStarted(m)}; });
    rows.sort(function(a,b){ return b.p-a.p || (a.name<b.name?-1:1); });
    var started = rows.filter(function(r){ return r.any; });
    var top = (started.length?started:rows).slice(0,6);
    var bars = top.map(function(r){
      return '<button type="button" class="lb-row" data-m="'+esc(r.id)+'" title="Focus '+esc(r.name)+'">'
        + '<span class="lb-n">'+esc(r.name)+'</span>'
        + '<span class="lb-bar"><span style="width:'+r.p+'%"></span></span>'
        + '<span class="lb-p">'+r.p+'%</span></button>';
    }).join("");
    var zero = rows.length - started.length;
    var foot = zero>0 ? '<div class="ov-foot">'+zero+' master'+(zero===1?"":"s")+' not started</div>' : '';
    return '<div class="ov-card"><h4>Furthest along</h4>'+bars+foot+'</div>';
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
    return '<div class="ov-card"><h4>Masters by completion</h4>'+rows+'</div>';
  }
  // For every glyph, in how many masters it is coloured: all / some / none.
  function crossDepth(){
    var oset={}, i, j; for(i=0;i<H.order.length;i++) oset[H.order[i]]=1;
    var nM=H.masters.length, total=H.glyphTotal, all=0, some=0, none=0;
    for (i=0;i<total;i++){
      var c=0;
      for (j=0;j<nM;j++){ var k=H.masters[j].keys[i]; if (k!==-1 && oset[k]) c++; }
      if (c===0) none++; else if (c===nM) all++; else some++;
    }
    function seg(n,cls,lab){ var w=total?n/total*100:0; return '<span class="dp-seg '+cls+'" style="width:'+w.toFixed(2)+'%" title="'+esc(lab+": "+n)+'"></span>'; }
    var bar='<div class="dp-bar" role="img" aria-label="Glyph colour depth across masters">'+seg(all,"dp-all","In all "+nM)+seg(some,"dp-some","In some")+seg(none,"dp-none","In none")+'</div>';
    var leg='<div class="dp-leg"><span><i class="dp-all"></i>All '+nM+': <b>'+all+'</b></span>'
      +'<span><i class="dp-some"></i>Some: <b>'+some+'</b></span>'
      +'<span><i class="dp-none"></i>None: <b>'+none+'</b></span></div>';
    return '<div class="ov-card"><h4>Glyph depth across masters</h4>'+bar+leg+'</div>';
  }
  function overviewExtras(){
    if (!H.masters.length) return "";
    return '<div class="ov-extra">'+leaderboard()+histogram()+crossDepth()+'</div>';
  }
  function tabsView(){
    if (state.master==null) return overall()+overviewExtras();   // no master selected -> global view + extras
    var m = masterById(state.master);
    return '<div class="panel" role="tabpanel">'+masterOverall(m)+heatmap(m)+'</div>';
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
  function timelineView(){
    var series = (H.trend && H.trend.series) || [];
    if (series.length < 2){
      return '<section class="tl-empty"><p class="empty">Not enough history yet. Color Flow saves a snapshot each time you save the font; this timeline fills in as days of history accumulate.</p></section>';
    }
    var W=680, Ht=200, pl=30, pr=12, ptop=12, pb=8, iw=W-pl-pr, ih=Ht-ptop-pb;
    var t0 = new Date(series[0].date).getTime();
    function dayOff(d){ return (new Date(d).getTime()-t0)/86400000; }
    var lastOff = Math.max(1, dayOff(series[series.length-1].date));
    function X(o){ return pl + o/lastOff*iw; }
    function Y(p){ return ptop + ih - p/100*ih; }
    var grid = [0,25,50,75,100].map(function(g){
      var y = Y(g).toFixed(1);
      return '<line class="tl-grid" x1="'+pl+'" y1="'+y+'" x2="'+(W-pr)+'" y2="'+y+'"/>'
        + '<text class="tl-axis" x="'+(pl-5)+'" y="'+(parseFloat(y)+3).toFixed(1)+'" text-anchor="end">'+g+'</text>';
    }).join("");
    var lines = "", selLine = "", legend = "";
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
      var seg = '<polyline class="tl-line'+(dim?" tl-dim":"")+(sel?" tl-sel":"")+'" points="'+poly+'" stroke="'+col+'"/>'+dots;
      if (sel) selLine += seg; else lines += seg;            // keep the selected master's line on top
      legend += '<span class="tl-lg'+(dim?" tl-dim":"")+(sel?" tl-sel":"")+'"><i style="background:'+col+'"></i>'+esc(m.name)+' '+Math.round(pts[pts.length-1].pc)+'%</span>';
    });
    lines += selLine;
    var chart = '<svg class="tl-chart" viewBox="0 0 '+W+' '+Ht+'" role="img" aria-label="Completion over time per master">'+grid+lines+'</svg>';
    var foot = '<div class="tl-foot"><span>'+esc(series[0].date)+'</span><span>'+esc(series[series.length-1].date)+'</span></div>';
    return '<section class="timeline"><div class="tl-legend">'+legend+'</div>'+chart+foot+'</section>';
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
    document.getElementById("cfd-overview").addEventListener("click", function(){ state.view = "tabs"; state.master = null; update(); });
    document.getElementById("cfd-compare").addEventListener("click", function(){ state.view = state.view==="compare" ? "tabs" : "compare"; update(); });
    document.getElementById("cfd-coverage").addEventListener("click", function(){ state.view = state.view==="coverage" ? "tabs" : "coverage"; update(); });
    document.getElementById("cfd-timeline").addEventListener("click", function(){ state.view = state.view==="timeline" ? "tabs" : "timeline"; update(); });
    document.getElementById("cfd-export").addEventListener("click", openExport);
    document.addEventListener("keydown", function(e){
      if (e.key==="Escape"){ closeExport(); if (state.focus!==null){ setFocus(null); } }
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
      var cr = e.target.closest(".cmprow[data-m],.lb-row[data-m]"); if (cr){ var cid=cr.getAttribute("data-m"); state.master=(state.master===cid)?null:cid; update(); return; }
      var cg = e.target.closest("[data-cg]"); if (cg){ state.coverGroup = cg.getAttribute("data-cg"); update(); return; }
      var gs = e.target.closest("[data-gsort]"); if (gs){ state.glyphSort = gs.getAttribute("data-gsort"); update(); return; }
      var fc = e.target.closest("[data-fclear]"); if (fc){ setFocus(null); return; }
      var ba = e.target.closest(".ba-toggle");
      if (ba){ e.preventDefault(); state.before = !state.before; ba.setAttribute("aria-pressed", state.before); ba.textContent = state.before ? "Before" : "After"; applyBeforeAfter(); return; }
    });
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
      var off=document.createElement("canvas"); off.width=off.height=FS;
      var g=off.getContext("2d"), cx=FS/2, cy=FS/2, R=FS*0.46, sum=0, i;
      for (i=0;i<12;i++) sum+=counts[i];
      var total=sum+uncolored;
      if (total){
        // one wedge per present colour (hue) + the uncoloured share (grey), all
        // proportional to the master's glyph total so uncoloured glyphs show too
        var segs=[];
        for (i=0;i<12;i++){ if(counts[i]>0) segs.push([counts[i]/total, slotColor(i)]); }
        if (uncolored>0) segs.push([uncolored/total, UNCOL]);
        var acc=0, stops=[];
        for (i=0;i<segs.length;i++){ stops.push([acc+segs[i][0]/2, segs[i][1]]); acc+=segs[i][0]; }
        var filled=false;
        try {
          var base=g.createConicGradient(-Math.PI/2,cx,cy);
          for (i=0;i<stops.length;i++) base.addColorStop(stops[i][0],stops[i][1]);
          base.addColorStop(1,stops[0][1]);
          g.fillStyle=base; g.fillRect(0,0,FS,FS); filled=true;
        } catch(e){ filled=false; }
        if (!filled){ var a=-Math.PI/2;
          for (i=0;i<segs.length;i++){ var a1=a+segs[i][0]*Math.PI*2;
            g.fillStyle=segs[i][1]; g.beginPath(); g.moveTo(cx,cy); g.arc(cx,cy,R*1.25,a,a1); g.closePath(); g.fill(); a=a1; } }
        var dk=g.createRadialGradient(cx,cy,0,cx,cy,R*0.72);
        dk.addColorStop(0,"rgba(0,0,0,0.58)"); dk.addColorStop(0.5,"rgba(0,0,0,0.26)"); dk.addColorStop(1,"rgba(0,0,0,0)");
        g.fillStyle=dk; g.beginPath(); g.arc(cx,cy,R*0.72,0,7); g.fill();
      }
      var bl=document.createElement("canvas"); bl.width=bl.height=FS; var bg=bl.getContext("2d");
      bg.filter="blur(13px) saturate(1.6) brightness(0.92)"; bg.drawImage(off,0,0);
      bg.filter="none"; bg.globalCompositeOperation="destination-in";
      bg.fillStyle="#000"; bg.beginPath(); bg.arc(FS/2,FS/2,FS*0.5,0,7); bg.fill();
      bg.globalCompositeOperation="source-over";
      return bl;
    }
    var FIELDS = H.masters.map(function(m){ return buildField(countsOf(m), m.uncolored||0); });
    var EMPTY = H.masters.map(function(m){ var c=countsOf(m),s=0,i; for(i=0;i<12;i++)s+=c[i]; return (s+(m.uncolored||0))===0; });
    var FROST = (function(){
      var c=document.createElement("canvas"); c.width=c.height=FS; var g=c.getContext("2d");
      for (var k=0;k<1600;k++){ var x=Math.random()*FS,y=Math.random()*FS,r=Math.random()*1.6+0.3;
        g.fillStyle="rgba(255,255,255,"+(Math.random()*0.07)+")"; g.beginPath(); g.arc(x,y,r,0,7); g.fill(); }
      var o=document.createElement("canvas"); o.width=o.height=FS; var og=o.getContext("2d");
      og.filter="blur(0.6px)"; og.drawImage(c,0,0); return o;
    })();
    var buf=document.createElement("canvas"); buf.width=W; buf.height=Hc; var bctx=buf.getContext("2d");

    function paintDisc(g,fA,cx,cy,rx,ry,holeFrac,glow,empty){
      if (glow===undefined) glow=1;
      if (empty){   // no colours: a near-background tone at lower opacity (mixes with the bg)
        g.save(); g.translate(cx,cy); g.scale(1,ry/rx);
        g.globalAlpha=0.6; g.fillStyle=EMPTYFILL; g.beginPath(); g.arc(0,0,rx,0,7); g.fill(); g.globalAlpha=1;
        g.restore();
        return;
      }
      var o=rx*1.14;
      g.save(); g.translate(cx,cy); g.scale(1,ry/rx); g.rotate(rot);
      var halo=[[1.006,3,0.22],[1.025,6,0.14],[1.06,12,0.08]];
      for (var h=0;h<halo.length;h++){ g.globalAlpha=halo[h][2]*glow; g.filter="blur("+halo[h][1]+"px)"; var hh=rx*halo[h][0]; g.drawImage(fA,-hh,-hh,hh*2,hh*2); }
      g.filter="none"; g.globalAlpha=1; g.restore();
      g.save(); g.translate(cx,cy); g.scale(1,ry/rx); g.rotate(rot);
      g.beginPath(); g.arc(0,0,rx,0,7); g.clip();
      if (glow>1) g.filter="brightness("+(1+(glow-1)*0.7)+")";
      g.globalAlpha=DISC_ALPHA; g.drawImage(fA,-o,-o,o*2,o*2);
      g.filter="none"; g.globalAlpha=1; g.restore();
      g.save(); g.translate(cx,cy); g.scale(1,ry/rx); g.beginPath(); g.arc(0,0,rx,0,7); g.clip();
      g.fillStyle="rgba(255,255,255,0.10)"; g.beginPath(); g.arc(0,0,rx,0,7); g.fill();
      g.globalAlpha=0.9; g.drawImage(FROST,-rx,-rx,rx*2,rx*2); g.globalAlpha=1;
      var sheen=g.createLinearGradient(0,-rx,0,rx);
      sheen.addColorStop(0,"rgba(0,0,0,0.22)"); sheen.addColorStop(0.34,"rgba(255,255,255,0.02)");
      sheen.addColorStop(0.66,"rgba(255,255,255,0.04)"); sheen.addColorStop(1,"rgba(255,255,255,0.18)");
      g.fillStyle=sheen; g.beginPath(); g.arc(0,0,rx,0,7); g.fill();
      var hot=g.createRadialGradient(0,rx*0.42,0,0,rx*0.42,rx*0.8);
      hot.addColorStop(0,"rgba(255,255,255,0.15)"); hot.addColorStop(1,"rgba(255,255,255,0)");
      g.fillStyle=hot; g.beginPath(); g.arc(0,0,rx,0,7); g.fill();
      if (holeFrac>0){ var hr=rx*0.26; g.globalCompositeOperation="destination-out";
        var pg=g.createRadialGradient(0,0,0,0,0,hr); pg.addColorStop(0,"rgba(0,0,0,1)"); pg.addColorStop(0.94,"rgba(0,0,0,1)"); pg.addColorStop(1,"rgba(0,0,0,0)");
        g.fillStyle=pg; g.beginPath(); g.arc(0,0,hr,0,7); g.fill(); g.globalCompositeOperation="source-over"; }
      g.restore();
      g.save(); g.translate(cx,cy); g.scale(1,ry/rx);
      var rim=g.createLinearGradient(0,-rx,0,rx); rim.addColorStop(0,"rgba(0,0,0,0.24)"); rim.addColorStop(0.5,"rgba(255,255,255,0.05)"); rim.addColorStop(1,"rgba(255,255,255,0.32)");
      g.strokeStyle=rim; g.lineWidth=2; g.beginPath(); g.arc(0,0,rx*0.992,0,7); g.stroke(); g.restore();
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
        ctx.save(); ctx.globalAlpha=opacityVal; ctx.drawImage(buf,0,0); ctx.restore();
      }
      function focusDisc(ii){ var amt=focusAmt[ii], cyy=cyOf(ii);
        bctx.clearRect(0,0,W,Hc); if(!EMPTY[ii]) shadowInto(bctx,cx,cyy,rx,ry); paintDisc(bctx,FIELDS[ii],cx,cyy,rx,ry,1,1-amt,EMPTY[ii]);
        var trim=amt*trimVal; if (trim>0){ bctx.save(); bctx.globalCompositeOperation="source-atop"; bctx.fillStyle="rgba(0,0,0,"+trim+")"; bctx.fillRect(0,0,W,Hc); bctx.restore(); }
        edgeFade(bctx);
        ctx.save(); ctx.globalAlpha=1-amt*(1-opacityVal); ctx.drawImage(buf,0,0); ctx.restore();
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
      cv.style.width=availW+"px"; cv.style.height=availH+"px";
      cv.width=availW; cv.height=availH; W=cv.width; Hc=cv.height;
      buf.width=W; buf.height=Hc;
      var rx=Math.min(92,W*0.42), ry=rx*tilt, topY=ry+16, botPad=ry+12;   // mirror render() geometry
      VISIBLE=Math.max(4, Math.min(H.masters.length, Math.floor((Hc-topY-botPad)/34)+1));
      vt=Math.max(0, Math.min(Math.max(0,H.masters.length-VISIBLE), vt));
    }
    fit();
    window.addEventListener("resize", fit);
    function loop(){ rot+=0.008; render(); requestAnimationFrame(loop); }
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
    requestAnimationFrame(function(){ document.body.classList.add("ready"); introDone = true; });
  }
  if (document.readyState!=="loading") init();
  else document.addEventListener("DOMContentLoaded", init);
})();
"""
