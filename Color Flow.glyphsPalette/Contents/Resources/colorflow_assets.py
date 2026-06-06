# encoding: utf-8
"""Inline assets + HTML shell for the Color Font Dashboard.

Turns the data model (see colorflow_dashboard.build_model) into one
self-contained, offline .html with inline CSS + inline vanilla JS. No network,
no dependencies. The model is the single source of truth the JS app renders.
"""

from __future__ import annotations

import json
from urllib.parse import quote
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
    """A ``<link rel="icon">`` carrying the bundled brand favicon (the Color Flow
    colour wheel SVG) as an inline SVG data URI. Empty when the model has none."""
    favicon = model.get("favicon")
    if not favicon:
        return ""
    return f'<link rel="icon" href="data:image/svg+xml,{quote(favicon)}">'


def build_html(model: dict) -> str:
    """Assemble the complete, self-contained dashboard page from a model."""
    title = xesc(f'Colorflow Dashboard - {model.get("family") or "Untitled"}')
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
@media (prefers-reduced-motion:reduce){body,body.ready{opacity:1;transition:none}.cell{transition:none}}
#cfd-app{max-width:1180px;margin:0 auto;padding:0 20px 60px}
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
.seg{display:flex;height:10px;border-radius:5px;overflow:hidden;background:var(--track)}
.seg>span{display:block;height:100%}
.seg .seg-none{background:var(--c-none)}
.ov-recipe{margin-top:10px;font-size:var(--fs-xs);color:var(--muted)}
.ov-recipe b{color:var(--text)}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;font-size:var(--fs-xs);color:var(--muted)}
.legend .lg{display:inline-flex;align-items:center;gap:5px}
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
.heat{margin-top:14px;border-top:1px solid var(--border);padding-top:12px}
.heat-h{font-size:var(--fs-xs);color:var(--muted);margin-bottom:8px;display:flex;align-items:center;gap:10px}
.heat-h .ba-toggle{margin-left:auto;flex:none}
.heat-h .hint{color:var(--muted-2)}
.cat:first-child{margin-top:0}
.cat-h{font-size:var(--fs-xs);color:var(--muted);margin:14px 0 6px;display:flex;align-items:center;gap:6px}
.cat-n{color:var(--muted-2)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(34px,1fr));gap:3px}
.cell{aspect-ratio:1;border:0;padding:0;border-radius:5px;cursor:pointer;display:block;text-decoration:none;overflow:hidden;transition:background .45s ease;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
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
.cmp{border-collapse:collapse;width:100%;font-size:var(--fs-row)}
.cmp caption{text-align:left;color:var(--muted-2);font-size:var(--fs-xs);padding-bottom:8px}
.cmp th,.cmp td{border:1px solid var(--border);padding:7px 10px;text-align:left}
.cmp thead th{color:var(--muted);font-weight:600;text-align:center}
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
.timeline{margin-top:14px}
.tl-empty{margin-top:20px}
.tl-legend{display:flex;flex-wrap:wrap;gap:14px;font-size:var(--fs-xs);color:var(--muted);margin-bottom:8px}
.tl-lg{display:inline-flex;align-items:center;gap:5px}
.tl-lg i{width:9px;height:9px;border-radius:50%;display:inline-block;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.tl-chart{width:100%;height:auto;display:block;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:4px}
.tl-line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.tl-grid{stroke:var(--track);stroke-width:1}
.tl-axis{fill:var(--muted-2);font-size:10px}
.tl-foot{display:flex;justify-content:space-between;font-size:var(--fs-2xs);color:var(--muted-2);margin-top:6px}
.ov-ring{display:block}
.ov-ring .ov-ring-track{stroke:var(--track)}
.ov-ring .ov-ring-arc{stroke:var(--accent)}
.ov-ring-t{fill:var(--text);font-size:17px;font-weight:600}
.cmp-aa{display:block;height:20px;width:auto;margin:0 auto;color:var(--text)}
.cmp-mname{display:block;font-size:var(--fs-2xs);color:var(--muted);font-weight:400;margin-top:3px;white-space:nowrap}
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
.ft{margin-top:30px;padding-top:16px;border-top:1px solid var(--border);font-size:var(--fs-2xs);color:var(--muted-2);line-height:1.6}
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
    master: H.masters.length ? H.masters[0].id : null,
    view: "tabs", before: false, sort: "workflow",
    coverGroup: "byCategory",
    theme: savedTheme || (prefersLight ? "light" : "dark")
  };

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
      + '<span class="meta">'+esc(H.fileName)+' · v'+esc(H.version)+'</span>'
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
      + '<button type="button" id="cfd-export" class="chip" title="Export the report as PDF, CSV or JSON">⤓ Export Report</button></div>';
  }
  function ring(p){
    var r=26, c=2*Math.PI*r, off=c*(1-Math.max(0,Math.min(100,p))/100);
    return '<svg class="ov-ring" width="66" height="66" viewBox="0 0 66 66" role="progressbar" aria-valuenow="'+p+'" aria-valuemin="0" aria-valuemax="100" aria-label="'+p+'% complete">'
      + '<circle class="ov-ring-track" cx="33" cy="33" r="'+r+'" fill="none" stroke-width="6"/>'
      + '<circle class="ov-ring-arc" cx="33" cy="33" r="'+r+'" fill="none" stroke-width="6" stroke-linecap="round" stroke-dasharray="'+c.toFixed(1)+'" stroke-dashoffset="'+off.toFixed(1)+'" transform="rotate(-90 33 33)"/>'
      + '<text class="ov-ring-t" x="33" y="34" text-anchor="middle" dominant-baseline="central">'+p+'%</text></svg>';
  }
  function overall(){
    var a = aggregate(), compP = pct(a.completion,a.grand), startP = pct(a.started,a.grand);
    var legend = H.steps.map(function(s){
      return '<span class="lg" title="'+esc(s.label)+'"><i style="background:var('+varFor(s.key)+')"></i>'+pct(a.agg[String(s.key)]||0,a.grand)+'%</span>';
    }).join("");
    var head = (H.mode==="free" || !lastOrder)
      ? '<b>'+a.started+'/'+a.grand+'</b>'
      : '<b>'+a.completion+'/'+a.grand+'</b> complete · '+a.started+'/'+a.grand+' started ('+startP+'%)';
    var recipeLine = "";
    if (H.recipes && H.recipes.length){
      var recipeComplete = 0;
      H.masters.forEach(function(m){ recipeComplete += (((H.recipeCompletion||{})[m.id])||{}).complete||0; });
      recipeLine = '<div class="ov-recipe">Recipe-adjusted: <b>'+recipeComplete+'/'+a.grand+'</b> complete ('
        + pct(recipeComplete,a.grand)+'%) · '+H.recipes.length+' recipe'+(H.recipes.length===1?"":"s")+'</div>';
    }
    var ex = aggExclusive();
    var segParts = H.steps.map(function(s){
      var w = pct(ex.dist[String(s.key)]||0, a.grand);
      return w ? '<span style="width:'+w+'%;background:var('+varFor(s.key)+')" title="'+esc(s.label)+'"></span>' : "";
    }).join("");
    var noneW = pct(ex.none, a.grand);
    if (noneW) segParts += '<span class="seg-none" style="width:'+noneW+'%" title="'+esc(H.noneLabel)+'"></span>';
    return '<section class="overall" aria-label="Overall totals">'
      + '<div class="ov-num">'+ring(compP)+'</div>'
      + '<div class="ov-main"><div class="ov-head">'+head+'</div>'
      + '<div class="seg" role="img" aria-label="Colour distribution across the font">'+segParts+'</div>'
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
    var head = (H.mode==="free" || !lastOrder)
      ? '<b>'+started+'/'+total+'</b>'
      : '<b>'+completion+'/'+total+'</b> complete · '+started+'/'+total+' started ('+startP+'%)';
    var recipeLine = "";
    if (H.recipes && H.recipes.length){
      var rc = ((H.recipeCompletion||{})[m.id])||{};
      if (rc.complete != null) recipeLine = '<div class="ov-recipe">Recipe-adjusted: <b>'+rc.complete+'/'+total+'</b> complete ('+pct(rc.complete,total)+'%)</div>';
    }
    var dist={}, none=0;
    (m.keys||[]).forEach(function(k){ var sk=String(k); if (k===-1 || H.order.indexOf(sk)===-1) none++; else dist[sk]=(dist[sk]||0)+1; });
    var segParts = H.steps.map(function(s){
      var w = pct(dist[String(s.key)]||0, total);
      return w ? '<span style="width:'+w+'%;background:var('+varFor(s.key)+')" title="'+esc(s.label)+'"></span>' : "";
    }).join("");
    var noneW = pct(none, total);
    if (noneW) segParts += '<span class="seg-none" style="width:'+noneW+'%" title="'+esc(H.noneLabel)+'"></span>';
    return '<section class="overall master-overall" aria-label="'+esc(m.name+" totals")+'">'
      + '<div class="ov-main"><div class="ov-head">'+head+'</div>'
      + '<div class="seg" role="img" aria-label="'+esc(m.name+" colour distribution")+'">'+segParts+'</div>'
      + '<div class="legend">'+legend+'</div>'+recipeLine+'</div></section>';
  }
  function heatmap(m){
    var cats = H.categories || [];
    var items = [];
    for (var i=0;i<H.glyphNames.length;i++){
      items.push([H.glyphNames[i], m.keys[i], i]);
    }
    var shown = items;   // every glyph (no cap); letterforms come from H.paths
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
      return '<a class="cell' + (p ? ' glyph' : '') + '" href="' + href + '" data-glyph="' + esc(name) + '" data-now="' + nowVar + '" data-was="' + wasVar + '" style="background:color-mix(in srgb,var(' + showVar + ') 25%,transparent)" title="' + esc(name + " — " + lab + " (open in Glyphs)") + '" aria-label="' + esc(name + ", " + lab + ", open in Glyphs") + '">' + inner + '</a>';
    }
    // group cells by glyph category, Font-View style
    var groups = {}, seen = [];
    shown.forEach(function(it){ var c = cats[it[2]] || "Other"; if (!groups[c]){ groups[c]=[]; seen.push(c); } groups[c].push(it); });
    // order categories like the Glyphs Font View (Letter first); glyphs within a
    // category keep font order. Unknown categories fall after, in first-appearance order.
    var pref = ["Letter","Number","Punctuation","Mark","Separator","Symbol","Other"];
    seen.sort(function(a,b){ var ia=pref.indexOf(a); ia=ia<0?pref.length:ia; var ib=pref.indexOf(b); ib=ib<0?pref.length:ib; return ia-ib; });
    var sections = seen.map(function(c){
      return '<div class="cat"><div class="cat-h">'+esc(c)+' <span class="cat-n">'+groups[c].length+'</span></div>'
        + '<div class="grid" aria-label="'+esc(c)+'">'+groups[c].map(cellHTML).join("")+'</div></div>';
    }).join("");
    var more = "";
    var empty = items.length===0 ? '<p class="empty">No glyphs.</p>' : "";
    var toggle = Object.keys(ch).length ? '<button type="button" class="ba-toggle chip" aria-pressed="'+state.before+'" title="Toggle the cell colours between before and after the last run">'+(state.before?"Before":"After")+'</button>' : '';
    return '<section class="heat"><div class="heat-h"><span>Per-glyph · '+items.length
      + ' <span class="hint">hover for name · click to open</span></span>'+toggle+'</div>'
      + (sections||empty)+more+'</section>';
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
  function tabsView(){
    var m = masterById(state.master);
    return masterTabs()+'<div class="panel" role="tabpanel">'+masterOverall(m)+heatmap(m)+'</div>';
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
  function coverageView(){
    var cov = (H.coverage && H.coverage[state.coverGroup]) || {};
    var rows2 = cov[state.master] || [];
    var head = '<div class="cov-h"><span class="cov-title">Colours set by '+(state.coverGroup==="byScript"?"script":"category")+'</span>'
      + '<span class="cov-switch">'
      + '<button type="button" class="chip'+(state.coverGroup==="byScript"?" on":"")+'" data-cg="byScript" aria-pressed="'+(state.coverGroup==="byScript")+'">Script</button>'
      + '<button type="button" class="chip'+(state.coverGroup==="byCategory"?" on":"")+'" data-cg="byCategory" aria-pressed="'+(state.coverGroup==="byCategory")+'">Category</button></span></div>';
    var body = rows2.length ? rows2.map(function(r){
      return '<div class="cov-row"><span class="cov-name" title="'+esc(r.key)+'">'+esc(r.key)+'</span>'
        + covStacked(r) + '<span class="num">'+r.total+'</span></div>';
    }).join("") : '<p class="empty">No glyphs.</p>';
    return masterTabs()+'<section class="cov"><div class="panel">'+head+'<div class="cov-rows">'+body+'</div></div></section>';
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
    var lines = "", legend = "";
    H.masters.forEach(function(m, i){
      var col = "hsl("+masterHue(i)+",70%,55%)";
      var pts = series.map(function(p){
        var mp = p.masters[m.id]; if (!mp) return null;
        var c = mp.total ? mp.final/mp.total*100 : 0;
        return { x:X(dayOff(p.date)), y:Y(c), pc:c, date:p.date };
      }).filter(Boolean);
      if (!pts.length) return;
      var poly = pts.map(function(o){ return o.x.toFixed(1)+","+o.y.toFixed(1); }).join(" ");
      var dots = pts.map(function(o){ return '<circle cx="'+o.x.toFixed(1)+'" cy="'+o.y.toFixed(1)+'" r="2.5" fill="'+col+'"><title>'+esc(m.name+" · "+o.date+" · "+Math.round(o.pc)+"%")+'</title></circle>'; }).join("");
      lines += '<polyline class="tl-line" points="'+poly+'" stroke="'+col+'"/>'+dots;
      legend += '<span class="tl-lg"><i style="background:'+col+'"></i>'+esc(m.name)+' '+Math.round(pts[pts.length-1].pc)+'%</span>';
    });
    var chart = '<svg class="tl-chart" viewBox="0 0 '+W+' '+Ht+'" role="img" aria-label="Completion over time per master">'+grid+lines+'</svg>';
    var foot = '<div class="tl-foot"><span>'+esc(series[0].date)+'</span><span>'+esc(series[series.length-1].date)+'</span></div>';
    return '<section class="timeline"><div class="tl-legend">'+legend+'</div>'+chart+foot+'</section>';
  }
  function compareView(){
    // columns = steps (+None); rows = masters. The master name shows only on
    // hovering its Aa preview (title), not as visible text.
    var head = '<th scope="col">Master</th>'+H.steps.map(function(s){
      return '<th scope="col" title="'+esc(s.label)+'" aria-label="'+esc(s.label)+'"><span class="dot" style="background:var('+varFor(s.key)+')"></span></th>';
    }).join("")+'<th scope="col" title="'+esc(H.noneLabel)+'" aria-label="'+esc(H.noneLabel)+'"><span class="dot" style="background:var(--c-none)"></span></th>';
    var body = H.masters.map(function(m){
      var pv = m.preview;
      var aa = (pv && pv.d) ? '<svg class="cmp-aa" viewBox="'+esc(pv.vb)+'" preserveAspectRatio="xMidYMid meet"><path d="'+esc(pv.d)+'" fill="currentColor"/></svg>' : esc(m.name);
      var cells = H.steps.map(function(s){
        var p = pct(countFor(m,s.key),H.glyphTotal);
        return '<td><span class="cmpbar" style="width:'+p+'%;background:var('+varFor(s.key)+')"></span><span class="cmpn">'+p+'%</span></td>';
      }).join("");
      var np = pct(m.uncolored,H.glyphTotal);
      cells += '<td><span class="cmpbar" style="width:'+np+'%;background:var(--c-none)"></span><span class="cmpn">'+np+'%</span></td>';
      return '<tr><th scope="row" class="cmp-m" title="'+esc(m.name)+'" aria-label="'+esc(m.name)+'">'+aa+'</th>'+cells+'</tr>';
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
      cell.style.background = "color-mix(in srgb,var("+v+") 25%,transparent)";
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
    document.getElementById("cfd-overview").addEventListener("click", function(){ state.view = "tabs"; update(); });
    document.getElementById("cfd-compare").addEventListener("click", function(){ state.view = state.view==="compare" ? "tabs" : "compare"; update(); });
    document.getElementById("cfd-coverage").addEventListener("click", function(){ state.view = state.view==="coverage" ? "tabs" : "coverage"; update(); });
    document.getElementById("cfd-timeline").addEventListener("click", function(){ state.view = state.view==="timeline" ? "tabs" : "timeline"; update(); });
    document.getElementById("cfd-export").addEventListener("click", openExport);
    document.addEventListener("keydown", function(e){
      if (e.key==="Escape"){ closeExport(); }
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
      var cg = e.target.closest("[data-cg]"); if (cg){ state.coverGroup = cg.getAttribute("data-cg"); update(); return; }
      var ba = e.target.closest(".ba-toggle");
      if (ba){ e.preventDefault(); state.before = !state.before; ba.setAttribute("aria-pressed", state.before); ba.textContent = state.before ? "Before" : "After"; applyBeforeAfter(); return; }
    });
  }
  function init(){
    document.getElementById("cfd-app").innerHTML =
      header() + overall() + toolbar() + '<div id="cfd-body"></div>'
      + '<footer class="ft">Color Font Dashboard · Color Flow — Hugo Jourdan<br>'+esc(H.generated)+'</footer>';
    bind(); update();
    window.__cfdExport = { csv: exportCSV, json: exportJSON, rows: exportRows, printHTML: buildPrintReport };
    requestAnimationFrame(function(){ document.body.classList.add("ready"); });
  }
  if (document.readyState!=="loading") init();
  else document.addEventListener("DOMContentLoaded", init);
})();
"""
