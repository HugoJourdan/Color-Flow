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

# Fill for the favicon "a" — the brand accent, so it reads on any browser tab.
FAVICON_FILL = "#6e7bff"


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
    """A ``<link rel="icon">`` carrying the model's favicon outline (the Regular
    master's "a") as an inline SVG data URI. Empty when the model has no favicon."""
    favicon = model.get("favicon") or {}
    if not favicon.get("d"):
        return ""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="'
           f'{favicon["vb"]}"><path d="{favicon["d"]}" fill="{FAVICON_FILL}"/></svg>')
    return f'<link rel="icon" href="data:image/svg+xml,{quote(svg)}">'


def build_html(model: dict) -> str:
    """Assemble the complete, self-contained dashboard page from a model."""
    title = xesc(f'{model["generated"]}_{model.get("family") or ""}_Color-Flow-Dashboard')
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
  --track:#15171c;--swatch-outline:rgba(255,255,255,.10);--glyph-ink:rgba(0,0,0,.74);
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
body{background:var(--bg);color:var(--text);font:var(--fs-base)/1.5 "JetBrains Mono","JetBrainsMono Nerd Font",ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace,"Apple Color Emoji";
  font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased;opacity:0}
body.ready{opacity:1;transition:opacity .35s ease}
@media (prefers-reduced-motion:reduce){body,body.ready{opacity:1;transition:none}.cell{transition:none}}
#cfd-app{max-width:980px;margin:0 auto;padding:0 20px 60px}
.hd{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:10px;padding:14px 0;background:var(--bg);border-bottom:1px solid var(--border)}
.hd .brand{width:10px;height:10px;border-radius:3px;background:var(--accent)}
.hd .fam{font-weight:600}
.hd .meta{font-size:var(--fs-sm);color:var(--muted-2)}
.hd .sp{flex:1}
.hd .mode{font-size:var(--fs-xs);color:var(--muted);border:1px solid var(--border-2);border-radius:var(--r-sm);padding:4px 9px}
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
.ov-num{display:flex;flex-direction:column}
.ov-num .big{font-size:var(--fs-big);font-weight:650;letter-spacing:-.02em;line-height:1}
.ov-num .big small{font-size:var(--fs-big-sm);color:var(--muted-2)}
.ov-sub{font-size:var(--fs-xs);color:var(--muted-2);text-transform:uppercase;letter-spacing:.06em}
.ov-main{flex:1}
.ov-head{font-size:var(--fs-sm);color:var(--muted);margin-bottom:8px}
.ov-head b{color:var(--text)}
.seg{display:flex;height:8px;border-radius:5px;overflow:hidden;background:var(--track)}
.seg>span{background:var(--accent)}
.seg .soft{background:color-mix(in srgb,var(--accent) 35%,transparent)}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;font-size:var(--fs-xs);color:var(--muted)}
.legend .lg{display:inline-flex;align-items:center;gap:5px}
.legend i{width:8px;height:8px;border-radius:50%;display:inline-block;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.tabs{display:flex;gap:18px;border-bottom:1px solid var(--border);margin-bottom:6px;overflow-x:auto}
.tab{font:var(--fs-sm) inherit;background:transparent;border:0;border-bottom:2px solid transparent;color:var(--muted-2);padding:8px 0;cursor:pointer;white-space:nowrap}
.tab:hover{color:var(--text)}
.tab.on{color:var(--text);border-bottom-color:var(--accent)}
.tab .tabsvg{display:block;height:26px;width:auto;color:inherit}
.rows{margin:6px 0 4px}
.row{display:flex;align-items:center;gap:12px;font-size:var(--fs-row);padding:9px 0;border-top:1px solid var(--track)}
.row .dot{width:9px;height:9px;border-radius:50%;flex:none;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.row .rl{flex:1}
.row .chk{color:var(--ok)}
.row.done .rl{color:var(--muted)}
.bar{width:200px;height:5px;background:var(--track);border-radius:3px;overflow:hidden;flex:none}
.bar>span{display:block;height:100%;border-radius:3px}
.row .num{width:54px;text-align:right;color:var(--muted)}
.row .pc{width:40px;text-align:right}
.heat{margin-top:14px;border-top:1px solid var(--border);padding-top:12px}
.heat-h{font-size:var(--fs-xs);color:var(--muted);margin-bottom:8px;display:flex;align-items:center;gap:10px}
.heat-h .ba-toggle{margin-left:auto;flex:none}
.heat-h .hint{color:var(--muted-2)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(34px,1fr));gap:6px}
.cell{aspect-ratio:1;border:0;padding:0;border-radius:5px;cursor:pointer;display:block;text-decoration:none;overflow:hidden;transition:background .45s ease;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.cell:hover{outline:2px solid var(--accent);outline-offset:1px}
.cell.copied{outline:2px solid var(--ok);outline-offset:1px}
.cell svg{width:100%;height:100%;display:block;padding:3px}
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
.cmp thead th{color:var(--muted);font-weight:600}
.cmp tbody th{font-weight:500}
.cmp tbody th .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
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
.cov-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.trend{display:flex;flex-direction:column;gap:16px;margin-top:14px}
.trend-empty{margin-top:20px}
.tcard{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.tcard-h{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:10px}
.tname{font-weight:600}
.tstats{display:flex;gap:18px;flex-wrap:wrap;margin-left:auto;font-size:var(--fs-sm)}
.tstat{display:flex;flex-direction:column;line-height:1.25}
.tstat i{font-style:normal;font-size:var(--fs-2xs);color:var(--muted-2);text-transform:uppercase;letter-spacing:.05em}
.tstat.teta{min-width:150px}
.tconf{font-size:var(--fs-2xs);padding:1px 5px;border-radius:4px;border:1px solid var(--border-2);color:var(--muted)}
.tconf.high{color:var(--ok);border-color:color-mix(in srgb,var(--ok) 60%,var(--border-2))}
.tconf.low,.tconf.none{color:var(--muted-2)}
.tchart{width:100%;height:auto;display:block;margin-top:2px}
.tchart .tline{fill:none;stroke:var(--accent);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.tchart circle{fill:var(--accent)}
.tchart .tgoal{stroke:var(--border-2);stroke-width:1;stroke-dasharray:3 3}
.tchart .tproj{stroke:var(--ok);stroke-width:1.5;stroke-dasharray:4 3;fill:none}
.tchart .teta{fill:var(--ok)}
.tchart .tband{fill:color-mix(in srgb,var(--ok) 14%,transparent)}
.tfoot{display:flex;justify-content:space-between;font-size:var(--fs-2xs);color:var(--muted-2);margin-top:6px}
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
    view: "tabs", before: false, q: "", unfinishedOnly: true, sort: "workflow",
    coverGroup: "byScript",
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
  function matchQ(name){ return !state.q || name.toLowerCase().indexOf(state.q.toLowerCase())!==-1; }
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

  function header(){
    return '<header class="hd"><span class="brand"></span>'
      + '<span class="fam">'+esc(H.family)+'</span>'
      + '<span class="meta">'+esc(H.fileName)+' · v'+esc(H.version)+'</span>'
      + '<span class="sp"></span>'
      + '<span class="mode">Mode · '+(H.mode==="free"?"Free":"Step")+'</span>'
      + '<button type="button" id="cfd-theme" class="icon" aria-label="Toggle light or dark theme">◐</button></header>';
  }
  function toolbar(){
    return '<div class="tb">'
      + '<label class="search"><span aria-hidden="true">⌕</span>'
      + '<input id="cfd-search" type="search" placeholder="Search glyphs…" aria-label="Search glyphs" autocomplete="off"><kbd>/</kbd></label>'
      + '<button type="button" id="cfd-unfinished" class="chip" aria-pressed="'+state.unfinishedOnly+'">◦ Unfinished only</button>'
      + '<button type="button" id="cfd-sort" class="chip">↕ Sort: workflow</button>'
      + '<button type="button" id="cfd-trend" class="chip" aria-pressed="false">📈 Trend</button>'
      + '<button type="button" id="cfd-coverage" class="chip" aria-pressed="false">🗂 Coverage</button>'
      + '<button type="button" id="cfd-compare" class="chip" aria-pressed="false">▤ Compare</button>'
      + '<button type="button" id="cfd-csv" class="chip" title="Download per-step counts as CSV">⇩ CSV</button>'
      + '<button type="button" id="cfd-json" class="chip" title="Download the summary as JSON">⇩ JSON</button></div>';
  }
  function overall(){
    var a = aggregate(), compP = pct(a.completion,a.grand), startP = pct(a.started,a.grand);
    var legend = H.steps.map(function(s){
      return '<span class="lg"><i style="background:var('+varFor(s.key)+')"></i>'+esc(s.label)+' '+pct(a.agg[String(s.key)]||0,a.grand)+'%</span>';
    }).join("");
    var head = (H.mode==="free" || !lastOrder)
      ? '<b>'+a.started+'/'+a.grand+'</b> labelled ('+startP+'%)'
      : '<b>'+a.completion+'/'+a.grand+'</b> complete ('+compP+'%) · '+a.started+'/'+a.grand+' started ('+startP+'%)';
    return '<section class="overall" aria-label="Overall totals">'
      + '<div class="ov-num"><span class="big">'+compP+'<small>%</small></span><span class="ov-sub">'+(H.mode==="free"?"labelled":"complete")+'</span></div>'
      + '<div class="ov-main"><div class="ov-head">'+head+'</div>'
      + '<div class="seg" role="img" aria-label="Overall '+compP+'% complete, '+startP+'% started">'
      + '<span style="width:'+compP+'%"></span><span class="soft" style="width:'+Math.max(0,startP-compP)+'%"></span></div>'
      + '<div class="legend">'+legend+'</div></div></section>';
  }

  function rows(m){
    var html = stepsSorted(m).map(function(s){
      var c = countFor(m,s.key), p = pct(c,H.glyphTotal), done = H.glyphTotal>0 && c>=H.glyphTotal;
      return '<div class="row'+(done?' done':'')+'"><span class="dot" style="background:var('+varFor(s.key)+')"></span>'
        + '<span class="rl">'+esc(s.label)+(done?' <span class="chk" aria-label="complete">✓</span>':'')+'</span>'
        + bar(c,H.glyphTotal,varFor(s.key),s.label+': '+c+' of '+H.glyphTotal+' ('+p+'%)')
        + '<span class="num">'+c+'/'+H.glyphTotal+'</span><span class="pc">'+p+'%</span></div>';
    }).join("");
    var un = m.uncolored, up = pct(un,H.glyphTotal);
    html += '<div class="row none"><span class="dot" style="background:var(--c-none)"></span>'
      + '<span class="rl">'+esc(H.noneLabel)+'</span>'
      + bar(un,H.glyphTotal,"--c-none",H.noneLabel+': '+un+' of '+H.glyphTotal+' ('+up+'%)')
      + '<span class="num">'+un+'/'+H.glyphTotal+'</span><span class="pc">'+up+'%</span></div>';
    return '<div class="rows">'+html+'</div>';
  }
  function heatmap(m){
    var items = [];
    for (var i=0;i<H.glyphNames.length;i++){
      var name = H.glyphNames[i], k = m.keys[i];
      if (state.unfinishedOnly && finished(k)) continue;
      if (!matchQ(name)) continue;
      items.push([name,k]);
    }
    var cap = 500, shown = items.slice(0,cap);
    var paths = (H.paths && H.paths[m.id]) || {};
    var ch = (H.changes && H.changes[m.id]) || {};
    var cells = shown.map(function(it){
      var name = it[0], key = it[1], lab = labelFor(key);
      var wasKey = (ch[name] != null) ? ch[name][0] : key;
      var nowVar = varFor(key), wasVar = varFor(wasKey);
      var showVar = state.before ? wasVar : nowVar;
      var href = "glyphsapp://show/?path=" + encodeURIComponent(H.filePath || "")
        + "&glyph=" + encodeURIComponent(name) + "&layer=" + encodeURIComponent(m.id);
      var p = paths[name];
      var inner = p ? '<svg viewBox="' + esc(p.vb) + '" preserveAspectRatio="xMidYMid meet"><path d="' + esc(p.d) + '"/></svg>' : '';
      return '<a class="cell' + (p ? ' glyph' : '') + '" href="' + href + '" data-glyph="' + esc(name) + '" data-now="' + nowVar + '" data-was="' + wasVar + '" style="background:var(' + showVar + ')" title="' + esc(name + " — " + lab + " (open in Glyphs)") + '" aria-label="' + esc(name + ", " + lab + ", open in Glyphs") + '">' + inner + '</a>';
    }).join("");
    var more = items.length>cap ? '<span class="more">… +'+(items.length-cap)+' more</span>' : "";
    var empty = items.length===0 ? '<p class="empty">No glyphs match.</p>' : "";
    var toggle = Object.keys(ch).length ? '<button type="button" class="ba-toggle chip" aria-pressed="'+state.before+'" title="Toggle the cell colours between before and after the last run">'+(state.before?"Before":"After")+'</button>' : '';
    return '<section class="heat"><div class="heat-h"><span>Per-glyph · '+items.length+(state.unfinishedOnly?" unfinished":"")
      + ' <span class="hint">hover for name · click to open</span></span>'+toggle+'</div>'
      + '<div class="grid" aria-label="Per-glyph colours">'+cells+'</div>'+more+empty+'</section>';
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
    return masterTabs()+'<div class="panel" role="tabpanel">'+rows(m)+heatmap(m)+'</div>';
  }
  function coverageView(){
    var cov = (H.coverage && H.coverage[state.coverGroup]) || {};
    var rows2 = cov[state.master] || [];
    var goalVar = "--c"+(lastOrder!=null?lastOrder:0);
    var head = '<div class="cov-h"><span class="cov-title">Coverage by '+(state.coverGroup==="byScript"?"script":"category")+'</span>'
      + '<span class="cov-switch">'
      + '<button type="button" class="chip'+(state.coverGroup==="byScript"?" on":"")+'" data-cg="byScript" aria-pressed="'+(state.coverGroup==="byScript")+'">Script</button>'
      + '<button type="button" class="chip'+(state.coverGroup==="byCategory"?" on":"")+'" data-cg="byCategory" aria-pressed="'+(state.coverGroup==="byCategory")+'">Category</button></span></div>';
    var body = rows2.length ? rows2.map(function(r){
      var p = pct(r.final, r.total);
      return '<div class="cov-row"><span class="cov-name">'+esc(r.key)+'</span>'
        + bar(r.final, r.total, goalVar, r.key+": "+r.final+" of "+r.total+" complete ("+p+"%)")
        + '<span class="num">'+r.final+'/'+r.total+'</span><span class="pc">'+p+'%</span></div>';
    }).join("") : '<p class="empty">No glyphs.</p>';
    return masterTabs()+'<section class="cov"><div class="panel">'+head+'<div class="cov-rows">'+body+'</div></div></section>';
  }
  function compareView(){
    var head = '<th scope="col">Step</th>'+H.masters.map(function(m){ return '<th scope="col">'+esc(m.name)+'</th>'; }).join("");
    var body = H.steps.map(function(s){
      var tds = H.masters.map(function(m){
        var p = pct(countFor(m,s.key),H.glyphTotal);
        return '<td><span class="cmpbar" style="width:'+p+'%;background:var('+varFor(s.key)+')"></span><span class="cmpn">'+p+'%</span></td>';
      }).join("");
      return '<tr><th scope="row"><span class="dot" style="background:var('+varFor(s.key)+')"></span>'+esc(s.label)+'</th>'+tds+'</tr>';
    }).join("");
    var noneTds = H.masters.map(function(m){ return '<td><span class="cmpn">'+pct(m.uncolored,H.glyphTotal)+'%</span></td>'; }).join("");
    body += '<tr class="none"><th scope="row"><span class="dot" style="background:var(--c-none)"></span>'+esc(H.noneLabel)+'</th>'+noneTds+'</tr>';
    return '<div class="cmp-wrap"><table class="cmp"><caption>Step completion by master</caption><thead><tr>'+head+'</tr></thead><tbody>'+body+'</tbody></table></div>';
  }
  // ----- Trend: burndown + velocity + hedged finish-date forecast (#1) -----
  function trendStats(fc){
    var eta;
    if (fc.confidence==="done") eta = '<b>done</b>';
    else if (fc.etaIso) eta = '≈ <b>'+esc(fc.etaIso)+'</b> ±'+fc.bandDays+'d <span class="tconf '+esc(fc.confidence)+'">'+esc(fc.confidence)+'</span>';
    else eta = '<span class="muted">no estimate yet</span>';
    return '<span class="tstats">'
      + '<span class="tstat"><i>Velocity</i>'+(fc.velocityPerWeek||0)+'/wk</span>'
      + '<span class="tstat"><i>Remaining</i>'+(fc.remaining!=null?fc.remaining:"—")+'</span>'
      + '<span class="tstat"><i>Complete</i>'+(fc.final!=null?fc.final:0)+'/'+(fc.total!=null?fc.total:0)+'</span>'
      + '<span class="tstat teta"><i>Forecast</i>'+eta+'</span></span>';
  }
  function trendChart(pts, fc){
    var W=640, H=150, pl=8, pr=8, ptop=10, pb=14, iw=W-pl-pr, ih=H-ptop-pb;
    var total = (fc && fc.total) || pts.reduce(function(mx,o){ return Math.max(mx,o.mp.total); },1) || 1;
    var t0 = new Date(pts[0].date).getTime();
    function dayOff(d){ return (new Date(d).getTime()-t0)/86400000; }
    var lastOff = Math.max(1, dayOff(pts[pts.length-1].date));
    var etaOff = (fc && fc.etaIso) ? dayOff(fc.etaIso) : null;
    var xmax = Math.max(lastOff, etaOff||0) || 1;
    function X(off){ return pl + off/xmax*iw; }
    function Y(v){ return ptop + ih - (v/total*ih); }
    var poly = pts.map(function(o){ return X(dayOff(o.date)).toFixed(1)+","+Y(o.mp.final).toFixed(1); }).join(" ");
    var dots = pts.map(function(o){ return '<circle cx="'+X(dayOff(o.date)).toFixed(1)+'" cy="'+Y(o.mp.final).toFixed(1)+'" r="2.5"/>'; }).join("");
    var goalY = Y(total).toFixed(1);
    var proj = "";
    if (etaOff!=null && fc.confidence!=="done" && fc.confidence!=="none"){
      var lx=X(lastOff).toFixed(1), ly=Y(pts[pts.length-1].mp.final).toFixed(1), ex=X(etaOff).toFixed(1);
      var band = fc.bandDays ? Math.abs(X(etaOff+fc.bandDays)-X(etaOff)) : 0;
      proj = (band ? '<rect class="tband" x="'+(ex-band).toFixed(1)+'" y="'+ptop+'" width="'+(2*band).toFixed(1)+'" height="'+ih+'"/>' : "")
        + '<line class="tproj" x1="'+lx+'" y1="'+ly+'" x2="'+ex+'" y2="'+goalY+'"/>'
        + '<circle class="teta" cx="'+ex+'" cy="'+goalY+'" r="3"/>';
    }
    return '<svg class="tchart" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Completion over time toward the goal">'
      + '<line class="tgoal" x1="'+pl+'" y1="'+goalY+'" x2="'+(W-pr)+'" y2="'+goalY+'"/>'
      + proj + '<polyline class="tline" points="'+poly+'"/>' + dots + '</svg>';
  }
  function masterTrendCard(m, pts, fc){
    var total = (fc && fc.total) || 0;
    var foot = '<div class="tfoot"><span>'+esc(pts[0].date)+'</span><span>'+total+' goal</span><span>'+esc(pts[pts.length-1].date)+'</span></div>';
    return '<section class="tcard"><div class="tcard-h"><span class="tname">'+esc(m.name)+'</span>'+trendStats(fc)+'</div>'
      + trendChart(pts, fc) + foot + '</section>';
  }
  function trendView(){
    var series = (H.trend && H.trend.series) || [];
    if (series.length < 2){
      return '<section class="trend-empty"><p class="empty">Not enough history yet. Color Flow records a snapshot every time you save the font; the burndown and finish-date forecast appear once there are at least two days of history.</p></section>';
    }
    var fcs = (H.trend && H.trend.forecast) || {};
    var cards = H.masters.map(function(m){
      var pts = series.map(function(p){ return { date:p.date, mp:p.masters[m.id] }; })
                      .filter(function(o){ return o.mp; });
      return pts.length ? masterTrendCard(m, pts, fcs[m.id] || {}) : "";
    }).join("");
    return '<div class="trend">'+cards+'</div>';
  }

  function renderBody(){
    return state.view==="compare" ? compareView()
      : state.view==="trend" ? trendView()
      : state.view==="coverage" ? coverageView()
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
    if (!journey){ hideTip(); return; }
    var tip = document.getElementById("cfd-tip");
    if (!tip){ tip = document.createElement("div"); tip.id = "cfd-tip"; tip.className = "cfd-tip"; document.body.appendChild(tip); }
    tip.innerHTML = '<div class="tip-h">'+esc(name)+' · step journey</div>'+sparkline(journey);
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
      cell.style.background = "var("+v+")";
    }
  }

  function update(){
    hideTip();
    document.getElementById("cfd-body").innerHTML = renderBody();
    document.documentElement.setAttribute("data-theme", state.theme);
    var cmp = document.getElementById("cfd-compare"); if (cmp) cmp.setAttribute("aria-pressed", state.view==="compare");
    var trd = document.getElementById("cfd-trend"); if (trd) trd.setAttribute("aria-pressed", state.view==="trend");
    var cov = document.getElementById("cfd-coverage"); if (cov) cov.setAttribute("aria-pressed", state.view==="coverage");
    var uf = document.getElementById("cfd-unfinished"); if (uf) uf.setAttribute("aria-pressed", state.unfinishedOnly);
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

  function bind(){
    document.getElementById("cfd-theme").addEventListener("click", function(){
      state.theme = state.theme==="dark" ? "light" : "dark";
      try { localStorage.setItem("cfd-theme", state.theme); } catch(e){}
      document.documentElement.setAttribute("data-theme", state.theme);
    });
    document.getElementById("cfd-unfinished").addEventListener("click", function(){ state.unfinishedOnly = !state.unfinishedOnly; update(); });
    document.getElementById("cfd-sort").addEventListener("click", function(){ state.sort = state.sort==="workflow" ? "progress" : "workflow"; update(); });
    document.getElementById("cfd-compare").addEventListener("click", function(){ state.view = state.view==="compare" ? "tabs" : "compare"; update(); });
    document.getElementById("cfd-trend").addEventListener("click", function(){ state.view = state.view==="trend" ? "tabs" : "trend"; update(); });
    document.getElementById("cfd-coverage").addEventListener("click", function(){ state.view = state.view==="coverage" ? "tabs" : "coverage"; update(); });
    document.getElementById("cfd-csv").addEventListener("click", function(){ download(exportName("csv"), exportCSV(), "text/csv"); });
    document.getElementById("cfd-json").addEventListener("click", function(){ download(exportName("json"), exportJSON(), "application/json"); });
    var s = document.getElementById("cfd-search");
    s.addEventListener("input", function(){ state.q = s.value; update(); });
    document.addEventListener("keydown", function(e){
      if (e.key==="/" && document.activeElement!==s){ e.preventDefault(); s.focus(); }
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
      header() + toolbar() + overall() + '<div id="cfd-body"></div>'
      + '<footer class="ft">Color Font Dashboard · Color Flow — Hugo Jourdan<br>'+esc(H.generated)+'</footer>';
    bind(); update();
    window.__cfdExport = { csv: exportCSV, json: exportJSON, rows: exportRows };
    requestAnimationFrame(function(){ document.body.classList.add("ready"); });
  }
  if (document.readyState!=="loading") init();
  else document.addEventListener("DOMContentLoaded", init);
})();
"""
