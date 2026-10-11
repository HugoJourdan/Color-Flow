"""Inline assets + HTML shell for the Color Font Dashboard.

Turns the data model (see azcolorflow_dashboard.build_model) into one
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
    r"data:image/[a-zA-Z0-9.+-]+"  # image/<subtype>, e.g. png, svg+xml, x-icon
    r"(?:;[a-zA-Z0-9.+=-]+)*"  # optional parameters (e.g. ;charset=utf-8;base64)
    r",[A-Za-z0-9+/=%_.!~*()-]+\Z"  # required comma + non-empty payload
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
    title = xesc(f"{model.get('family') or 'Untitled'} - Colorflow")
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title>{_favicon_link(model)}"
        f"<style>{DASHBOARD_CSS}</style>{_color_overrides(model)}</head>"
        '<body><div id="cfd-app"></div>'
        "<noscript>This report needs JavaScript — please open it in a modern browser.</noscript>"
        f"{embed_model(model)}"
        f"<script>{DASHBOARD_JS}</script>"
        "</body></html>"
    )


DASHBOARD_CSS = """
:root{
  --bg:#0a0b0e;--surface:#0e1014;--surface-2:#101217;--border:#1c1f26;--border-2:#23262e;
  --text:#e6e8ec;--muted:#9aa0ab;--muted-2:#6b7280;--accent:#9f75ff;--ok:#3fb950;
  --track:#15171c;--swatch-outline:rgba(255,255,255,.10);--glyph-ink:var(--text);
  --tl-dot:#ffffff;--tl-vgrid:rgba(255,255,255,.10);
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
  --text:#15171c;--muted:#5b6270;--muted-2:#8b919c;--accent:#9f75ff;--ok:#1a7f37;
  --track:#eceef2;--swatch-outline:rgba(20,24,33,.18);
  --tl-dot:var(--text);--tl-vgrid:rgba(20,24,33,.10);
  --c-none-a:#dfe3e9;--c-none-b:#aab2bf;color-scheme:light;
}
*{box-sizing:border-box}
html,body{margin:0}
*{font-family:"JetBrains Mono",monospace}
body{background:var(--bg);color:var(--text);font:var(--fs-base)/1.5 "JetBrains Mono",monospace;
  font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased;opacity:0}
body.ready{opacity:1;transition:opacity .35s ease}
@media (prefers-reduced-motion:reduce){body,body.ready{opacity:1;transition:none}.cell{transition:none}.seg.intro{animation:none}.heat,.heat.fading{transition:none;opacity:1}.tl-seed-shimmer .tl-seed-ghost{animation:none}.ov-viz.intro .rdr-poly{animation:none}.funnel.intro .fnl-fill{animation:none}.tl-anim .tl-line{animation:none;stroke-dasharray:none;stroke-dashoffset:0}.tl-anim .tl-band,.tl-anim .tl-area,.tl-anim .tl-dot{animation:none;opacity:1}.tl-spark-anim polyline{animation:none;stroke-dasharray:none;stroke-dashoffset:0}.tl-anim .tl-spread-med{animation:none;stroke-dasharray:none;stroke-dashoffset:0}.tl-anim .tl-spread-fill,.tl-anim .tl-spread-dot{animation:none;opacity:1}.ov-ring.ov-anim .ov-ring-reveal{animation:none}.lb-fill.intro{animation:none}.segsw-hl{transition:none}.segsw-hl.anim{animation:none}.vnav-fill.anim{animation:none}.cfd-fade{animation:none}.cov-bar.scrub{animation:none}.heat.scrub .cell{animation:none}}
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
.hd .streak{font-size:var(--fs-xs);color:var(--text);border:1px solid var(--border-2);border-radius:var(--r-sm);padding:4px 9px}
.icon{width:30px;height:28px;border:1px solid var(--border-2);border-radius:var(--r-sm);background:transparent;color:var(--muted);cursor:pointer}
.icon:hover{color:var(--text)}
.tb{position:sticky;top:57px;z-index:4;display:flex;align-items:center;gap:8px;padding:12px 0;background:var(--bg);border-bottom:1px solid var(--border);flex-wrap:wrap}
.chip{font-size:var(--fs-xs);border:1px solid var(--border-2);border-radius:var(--r-sm);padding:6px 10px;background:var(--surface-2);color:var(--muted);cursor:pointer}
.ba-switch{display:inline-flex;align-items:center;gap:6px}
.ba-seg{font:inherit;font-size:var(--fs-xs);background:var(--surface-2);border:1px solid var(--border-2);color:var(--muted);padding:5px 10px;cursor:pointer}
.ba-seg:first-of-type{border-radius:var(--r-sm) 0 0 var(--r-sm)}
.ba-seg:nth-of-type(2){border-radius:0 var(--r-sm) var(--r-sm) 0;border-left:0}
.ba-seg.on{background:color-mix(in srgb,var(--accent) 58%,#15131c);border-color:color-mix(in srgb,var(--accent) 58%,#15131c);color:#fff}
.ba-play{font:inherit;font-size:13px;line-height:1;background:var(--surface-2);border:1px solid var(--border-2);color:var(--text);width:26px;height:24px;border-radius:var(--r-sm);cursor:pointer;display:inline-flex;align-items:center;justify-content:center}
.ba-play.on{background:var(--accent);border-color:var(--accent);color:#fff}
.vnav{position:relative;display:flex;align-items:center;justify-content:space-between;margin:0 2px 10px;padding:5px 3px}
.vnav-line{position:absolute;left:5px;right:5px;top:50%;height:2px;margin-top:-1px;background:var(--track);border-radius:2px}
.vnav-dot{position:relative;width:10px;height:10px;padding:0;border-radius:50%;border:1.5px solid var(--muted-2);background:var(--surface-2);cursor:pointer;transition:transform .12s ease,box-shadow .12s ease}
.vnav-dot.past{background:var(--accent);border-color:var(--accent)}
.vnav-dot:hover{transform:scale(1.25)}
.vnav-dot.on{transform:scale(1.4);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 28%,transparent)}
.vnav-fill{position:absolute;left:5px;top:50%;width:calc(100% - 10px);height:2px;margin-top:-1px;background:var(--accent);border-radius:2px;transform-origin:left center}
.vnav-fill.anim{animation:vnavGrow .45s cubic-bezier(.4,0,.2,1)}
@keyframes vnavGrow{from{transform:scaleX(var(--vnav-from,0))}to{transform:scaleX(var(--vnav-to,1))}}
.chip:hover{color:var(--text)}
.chip[aria-disabled=true]{opacity:.45;cursor:not-allowed}
.chip[aria-disabled=true]:hover{color:var(--muted)}
.chip[aria-pressed=true]{border-color:var(--accent);color:var(--text);background:color-mix(in srgb,var(--accent) 16%,transparent)}
.overall{display:flex;align-items:center;gap:16px;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:12px 16px;margin:16px 0}
.master-overall{margin-top:8px}
.vnav-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:12px 16px;margin:16px 0 8px}
.vnav-card-h{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.vnav-card-ttl{font-size:var(--fs-xs);color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.vnav-card-when{font-size:var(--fs-xs);color:var(--muted-2)}
.vnav-card .vnav{margin-bottom:2px}
.ov-num{display:flex;align-items:center;justify-content:center;border:0;background:none;padding:0;cursor:pointer}
.ov-num:hover{filter:brightness(1.1)}
.ov-num .big{font-size:var(--fs-big);font-weight:650;letter-spacing:-.02em;line-height:1}
.ov-num .big small{font-size:var(--fs-big-sm);color:var(--muted-2)}
.ov-sub{font-size:var(--fs-xs);color:var(--muted-2);text-transform:uppercase;letter-spacing:.06em}
.ov-main{flex:1}
.ov-head{font-size:var(--fs-sm);color:var(--muted);margin-bottom:8px}
.ov-head b{color:var(--text)}
.ov-name{color:var(--text);font-weight:650;font-size:17px;letter-spacing:-.01em;margin-right:9px}
.ov-name::after{content:"·";color:var(--muted-2);margin-left:9px}
.seg{display:flex;height:10px;border-radius:5px;overflow:visible;background:var(--track)}
.seg>span{display:block;height:100%;transform-origin:left center;transition:opacity .2s ease;filter:saturate(1.2) brightness(1.08)}
.seg>span:first-child{border-radius:5px 0 0 5px}
.seg>span:last-child{border-radius:0 5px 5px 0}
.seg .seg-none{background:var(--c-none)}
.segc{cursor:pointer}
.seg>span.off{opacity:.28}
.seg>span.on{filter:saturate(1.18)}
@keyframes segGrow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
.seg.intro{transform-origin:left center;animation:segGrow .5s ease backwards}
.funnel{margin-top:12px;display:flex;flex-direction:column;gap:5px}
.fnl-row{display:flex;align-items:center;gap:9px;width:100%;padding:1px 4px}
.fnl-row>i{flex:0 0 auto}
.fnl-lab{flex:0 0 auto;min-width:84px;max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:var(--fs-xs);color:var(--muted)}
.fnl-track{flex:1;height:9px;border-radius:5px;background:var(--track);overflow:hidden}
.fnl-fill{display:block;height:100%;border-radius:5px;transform-origin:left center;filter:saturate(1.2) brightness(1.08)}
.fnl-pct{flex:0 0 auto;min-width:38px;text-align:right;font-size:var(--fs-xs);font-variant-numeric:tabular-nums;color:var(--text)}
.fnl-empty{font-size:var(--fs-xs);color:var(--muted-2);padding:4px 5px}
.funnel.intro .fnl-fill{animation:segGrow .5s ease backwards}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;font-size:var(--fs-xs);color:var(--muted)}
.legend .lg{display:inline-flex;align-items:center;gap:5px}
.ov-extra{display:grid;grid-template-columns:repeat(auto-fit,minmax(238px,1fr));gap:14px;margin-top:16px}
.ov-extra .ovc-timeline{grid-column:1/-1}
.ov-extra .ovc-leaderboard{grid-column:1/-1}
.ovc-leaderboard .ov-card-body{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:30px;align-content:start}
.ovc-leaderboard .lb-row+.lb-row{border-top:0}
.ovc-week .wk-head{display:flex;align-items:baseline;gap:6px 24px;flex-wrap:wrap}
.wk-stat{display:flex;align-items:baseline;gap:7px}
.wk-delta{font-size:22px;font-weight:680;font-variant-numeric:tabular-nums}
.wk-sub{font-size:var(--fs-2xs);color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.wk-meta{margin-top:6px;font-size:var(--fs-xs);color:var(--muted)}
.ov-extra .ovc-week{grid-column:1/-1}
.wk-extra{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px 28px;margin-top:10px;padding-top:10px;border-top:1px solid var(--track)}
.wk-row{display:flex;flex-direction:column;gap:3px;min-width:0}
.wk-k{font-size:var(--fs-2xs);color:var(--muted-2);text-transform:uppercase;letter-spacing:.04em}
.wk-v{font-size:var(--fs-sm);color:var(--text);display:flex;align-items:center;gap:7px;min-width:0}
.wk-v b{color:var(--accent);font-weight:650}
.wk-list{list-style:none;margin:5px 0 0;padding:0;display:flex;flex-direction:column;gap:5px;font-size:var(--fs-sm)}
.wk-list li{display:flex;align-items:center;gap:7px;color:var(--text);min-width:0}
.wk-list li>span,.wk-list li{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wk-list li b{margin-left:auto;color:var(--accent);font-weight:650;font-variant-numeric:tabular-nums;flex:none}
.wk-pct{color:var(--muted);font-weight:500;margin-left:5px;opacity:.6}
.wk-sw{width:11px;height:11px;border-radius:3px;flex:none;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.ov-cal-tl{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,2fr);gap:14px;margin-top:14px}
.ov-cal-solo{margin-top:14px}
.ovc-calendar .tl-cal-card{margin-top:0;border-top:0;padding-top:0}
@media (max-width:720px){.ov-cal-tl{grid-template-columns:1fr}}
.ov-viz{display:grid;grid-template-columns:repeat(auto-fit,minmax(238px,1fr));gap:14px;margin-top:14px}
.ovz-wrap{display:flex;flex-direction:column;align-items:center;gap:8px}
.ovz{display:block;width:100%;height:auto;max-width:320px}
.rdr-grid{stroke:var(--track);fill:none}
.rdr-spoke{stroke:var(--track)}
.rdr-axt{fill:var(--muted-2);font-size:9px}
.rdr-poly{fill-opacity:.2;stroke-width:2;stroke-linejoin:round;transform-box:fill-box;transform-origin:center}
@keyframes ovzScaleIn{from{transform:scale(.55);opacity:0}to{transform:scale(1);opacity:1}}
.ov-viz.intro .rdr-poly{animation:ovzScaleIn .5s ease backwards;animation-delay:calc(var(--i,0)*90ms)}
.ov-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.ov-card.open{grid-column:1/-1}
.ov-card-h{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;margin:0 0 10px;padding:0;background:none;border:0;font:inherit;font-size:var(--fs-2xs);font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;text-align:left}
button.ov-card-h{cursor:pointer}
.ov-exp{font-size:var(--fs-2xs);font-weight:600;color:var(--accent);text-transform:none;letter-spacing:0}
button.ov-card-h:hover .ov-exp{filter:brightness(1.2)}
.ov-card-body.scroll{max-height:300px;overflow-y:auto;padding-right:4px}
.lb-row{display:flex;align-items:center;gap:9px;width:100%;background:none;border:0;padding:3px 6px;border-radius:5px;cursor:pointer;color:var(--text);font:inherit;text-align:left}
.lb-row+.lb-row{border-top:1px solid var(--track)}
.ovc-leaderboard .lb-row:nth-child(4n+3),.ovc-leaderboard .lb-row:nth-child(4n+4){background:color-mix(in srgb,var(--text) 5%,transparent)}
.lb-n{flex:1 1 auto;min-width:60px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:var(--fs-xs)}
.lb-bar{flex:0 0 104px;height:7px;border-radius:4px;background:var(--track);overflow:hidden}
.lb-bar>span{display:block;height:100%;background:var(--accent);border-radius:4px;transform-origin:left center}
.lb-fill.intro{animation:segGrow .55s ease backwards;animation-delay:calc(var(--i,0)*45ms)}
.lb-p{flex:0 0 36px;text-align:right;font-size:var(--fs-xs);color:var(--muted)}
.lb-row:hover .lb-bar>span{filter:brightness(1.18)}
.ov-foot{margin-top:9px;font-size:var(--fs-2xs);color:var(--muted-2)}
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
.heat-h .heat-recent{margin-left:auto}
.heat-h .chip{padding:4px 8px;font-size:var(--fs-2xs)}
.segsw{position:relative;display:grid;grid-template-columns:repeat(var(--segn,2),1fr);background:var(--track);border-radius:7px;padding:2px}
.segsw-hl{position:absolute;top:2px;bottom:2px;left:2px;width:calc((100% - 4px)/var(--segn,2));border-radius:5px;background:color-mix(in srgb,var(--accent) 52%,#15131c);box-shadow:0 1px 3px color-mix(in srgb,var(--accent) 16%,transparent);transform:translateX(calc(var(--seg,0)*100%));transition:transform .28s cubic-bezier(.4,0,.2,1)}
.segsw-hl.anim{animation:segswSlide .28s cubic-bezier(.4,0,.2,1)}
@keyframes segswSlide{from{transform:translateX(calc(var(--seg-from,0)*100%))}to{transform:translateX(calc(var(--seg-to,0)*100%))}}
.segsw>button{position:relative;z-index:1;border:0;background:none;color:var(--muted);font:inherit;font-size:var(--fs-2xs);padding:3px 12px;cursor:pointer;white-space:nowrap;transition:color .2s ease}
.segsw>button[aria-pressed=true]{color:#fff;font-weight:600}
.focus-clear{border-color:var(--accent);color:var(--text)}
/* Global<->Focus master switch: fade ONLY the data panels that change (not the chrome);
   the disc tower runs its own per-disc focus crossfade. */
.cfd-fade{animation:cfdFade .3s ease}
@keyframes cfdFade{from{opacity:0}to{opacity:1}}
/* Scrub (pick another moment): the category-coverage bars grow + the glyph cells fade in. */
.cov-bar.scrub{transform-origin:left center;animation:covGrow .42s cubic-bezier(.4,0,.2,1)}
@keyframes covGrow{from{transform:scaleX(.2);opacity:.35}to{transform:scaleX(1);opacity:1}}
.heat.scrub .cell{animation:cellPop .42s ease}
@keyframes cellPop{from{opacity:.18}to{opacity:1}}
.cat:first-child{margin-top:0}
.cat-h{font-size:var(--fs-xs);color:var(--muted);margin:14px 0 6px;display:flex;align-items:center;gap:6px}
.cat-n{color:var(--muted-2)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(var(--cell-min,40px),1fr));gap:3px}
/* Tiny cells (<26px): lay the category SECTIONS two-up so the grid fills the width and
   scrolls less. CSS columns flow blocks down col 1 then col 2; break-inside keeps each
   .cat block whole (never split across the column gap). */
.heat .heat-cats{column-count:2;column-gap:24px}
.heat .cat{margin:0 0 16px;break-inside:avoid;-webkit-column-break-inside:avoid}
.heat .cat-h{margin-top:0}            /* zero top margins so both column tops align */
.cell-size{flex:0 0 92px;accent-color:var(--accent);cursor:pointer;height:14px}
.heat-h .cell-size{margin-left:8px}
.cell{aspect-ratio:1;border:0;padding:0;border-radius:5px;cursor:pointer;display:block;text-decoration:none;overflow:hidden;transition:background .45s ease,opacity .2s ease}
.cell.ncnt{opacity:.35}
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
.cov{margin-top:6px}
.cov-h{display:flex;align-items:center;gap:12px;margin:10px 0 4px}
.cov-title{font-size:var(--fs-sm);color:var(--muted)}
.cov-rows{margin:6px 0 4px}
.cov-row{display:flex;align-items:center;gap:12px;font-size:var(--fs-xs);padding:5px 0;border-top:1px solid var(--track)}
.cov-name{width:120px;flex:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cov-bar{flex:1;display:flex;height:10px;border-radius:5px;overflow:visible;background:var(--track);min-width:0}
.cov-bar>span{display:flex;align-items:center;justify-content:center;height:100%;min-width:0}
.cov-bar>span:first-child{border-radius:5px 0 0 5px}
.cov-bar>span:last-child{border-radius:0 5px 5px 0}
.cov-bar>span:first-child:last-child{border-radius:5px}
.cov-bar .cov-none{background:var(--c-none)}
.cov-row .num{width:auto;min-width:48px;text-align:right;color:var(--muted)}
.ov-catcov{margin:16px 0}
.cov-grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 28px}
.cov-grid2 .cov-row:nth-child(1),.cov-grid2 .cov-row:nth-child(2){border-top:0}
@media (max-width:680px){.cov-grid2{grid-template-columns:1fr}.cov-grid2 .cov-row:nth-child(2){border-top:1px solid var(--track)}}
.sgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:12px;margin:12px 0 4px}
.scard{position:relative;aspect-ratio:1;border-radius:16px;overflow:hidden;background:var(--track)}
.scard-fill{position:absolute;inset:0;width:100%;height:100%;display:block}
.scard-in{position:absolute;inset:0;z-index:1;display:flex;flex-direction:column;align-items:center;justify-content:space-between;padding:13px 11px;text-align:center}
.scard-name{font-size:13px;font-weight:600;color:#fff;line-height:1.15;text-shadow:0 1px 3px rgba(0,0,0,.6)}
.scard-gl{width:46%;height:auto;max-height:50%;fill:rgba(255,255,255,.96);filter:drop-shadow(0 1px 4px rgba(0,0,0,.5))}
.scard-ct{font-size:11px;color:rgba(255,255,255,.82);text-shadow:0 1px 2px rgba(0,0,0,.55)}
.timeline{margin-top:2px}
.tl-empty{margin-top:20px}
.tl-legend{display:flex;flex-wrap:wrap;gap:14px;font-size:var(--fs-xs);color:var(--muted);margin-bottom:8px}
.tl-lg{display:inline-flex;align-items:center;gap:5px}
.tl-lg i{width:9px;height:9px;border-radius:50%;display:inline-block;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.tl-chart{width:100%;height:auto;display:block;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:4px}
.tl-line{fill:none;stroke-width:1.4;stroke-linejoin:round;stroke-linecap:round;transition:opacity .2s ease}
.tl-line.tl-dim{opacity:.16}
.tl-line.tl-sel{stroke-width:3}
@keyframes tlDraw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
@keyframes tlFade{from{opacity:0}to{opacity:1}}
.tl-anim .tl-line{stroke-dasharray:1;stroke-dashoffset:1;animation:tlDraw 1s cubic-bezier(.4,0,.2,1) forwards}
.tl-anim .tl-area,.tl-anim .tl-band{animation:tlFade .8s ease both}
.tl-anim .tl-dot{animation:tlFade .5s ease both;animation-delay:.55s}
.tl-spark-anim polyline{stroke-dasharray:1;stroke-dashoffset:1;animation:tlDraw .6s cubic-bezier(.4,0,.2,1) forwards}
.tl-area{stroke:none}
.tl-dot{transition:opacity .2s ease}
.tl-dot.tl-dim{opacity:.16}
.tl-lg{transition:opacity .2s ease}
.tl-lg.tl-dim{opacity:.4}
.tl-lg.tl-sel{font-weight:600}
.tl-grid{stroke:var(--track);stroke-width:1}
.tl-vgrid{stroke:var(--tl-vgrid);stroke-width:1;shape-rendering:crispEdges}
.tl-axis{fill:var(--muted-2);font-size:10px}
.tl-xtick{fill:var(--muted-2);font-size:9px}
.tl-crossarea{fill:transparent;cursor:pointer}
.tl-chart{cursor:pointer}
.tl-chart:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tl-nav-wrap{position:relative;margin:6px 0 2px;padding:0}
.tl-nav{display:block;width:100%;height:auto;cursor:crosshair;touch-action:none;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:4px}
.tl-nav-area{fill:var(--accent);opacity:.13}
.tl-nav-line{fill:none;stroke:var(--accent);stroke-width:1.2;opacity:.6}
.tl-nav-scrim{fill:var(--bg);opacity:.58}
.tl-nav-win{fill:var(--accent);opacity:.1;cursor:grab}
.tl-nav-win:active{cursor:grabbing}
.tl-nav-h{cursor:ew-resize}
.tl-nav-h-hit{fill:transparent}
.tl-nav-h-bar{fill:var(--accent);opacity:.95}
.tl-nav-grip{stroke:var(--bg);stroke-width:1;opacity:.85}
.tl-nav-h:focus-visible{outline:none}
.tl-nav-h:focus-visible .tl-nav-h-bar{outline:2px solid var(--text);outline-offset:1px}
.tl-nav-reset{position:absolute;top:-1px;right:0;font:inherit;font-size:var(--fs-xs);color:var(--muted);background:var(--surface-2);border:1px solid var(--border);border-radius:var(--r-sm);padding:1px 7px;cursor:pointer}
.tl-nav-reset:hover{color:var(--text)}
.tl-lanes-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 28px}
.tl-lanes-cat2{grid-template-columns:1fr}
.tl-lanes-cat2 .tl-lanes{column-count:2;column-gap:28px}
.tl-lanes-cat2 .tl-lanes>div{break-inside:avoid;-webkit-column-break-inside:avoid}
@media (max-width:680px){.tl-lanes-grid{grid-template-columns:1fr}}
.tl-graphcard{margin-bottom:14px}
.tl-graphcard-h{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:8px}
.tl-chartwrap{position:relative}
.tl-info-wrap{position:absolute;top:9px;right:9px;z-index:4}
.tl-info{display:block;width:18px;height:18px;border-radius:50%;border:1px solid var(--border-2);background:var(--surface);color:var(--muted);font:italic 600 11px/1 Georgia,'Times New Roman',serif;cursor:help;padding:0;transition:color .15s ease,border-color .15s ease}
.tl-info:hover{color:var(--accent);border-color:var(--accent)}
.tl-info-tip{position:absolute;top:24px;right:0;width:210px;background:var(--surface-2);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:var(--fs-2xs);line-height:1.45;box-shadow:0 8px 24px rgba(0,0,0,.22);opacity:0;visibility:hidden;transform:translateY(-3px);transition:opacity .14s ease,transform .14s ease,visibility .14s;pointer-events:none;z-index:5}
.tl-info-wrap:hover .tl-info-tip,.tl-info:focus-visible~.tl-info-tip{opacity:1;visibility:visible;transform:translateY(0)}
.tl-calpane{margin-top:2px}
.tl-granbar{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.tl-granlabel{font-size:var(--fs-xs);color:var(--muted-2);text-transform:uppercase;letter-spacing:.04em}
.tl-mode{display:inline-flex;gap:4px;flex:0 0 auto}
.tl-bucket{margin-left:2px;padding-left:8px;border-left:1px solid var(--border)}
.tl-mode .tl-mode-btn[aria-pressed=true]{border-color:var(--accent);color:var(--text);background:color-mix(in srgb,var(--accent) 16%,transparent)}
.tl-ico{width:14px;height:14px;display:block;fill:currentColor}
.tl-spanbar{margin-left:auto}
.segsw.tl-spanbar>button{padding:3px 9px}
.tl-band{stroke:none;fill-opacity:.4}
.tl-band-top{fill:none;stroke-width:1.4;stroke-linejoin:round;stroke-linecap:round;opacity:.92}
.tl-anim .tl-band-top{animation:tlFade .8s ease both}
.tl-cap{font-size:var(--fs-xs);color:var(--muted);margin:0 0 6px}
.tl-spread-fill{fill:var(--accent);fill-opacity:.16;stroke:none}
.tl-spread-med{fill:none;stroke:var(--accent);stroke-width:1.8;stroke-linejoin:round;stroke-linecap:round}
.tl-spread-dot{fill:var(--tl-dot)}
.tl-anim .tl-spread-med{stroke-dasharray:1;stroke-dashoffset:1;animation:tlDraw 1s cubic-bezier(.4,0,.2,1) forwards}
.tl-anim .tl-spread-fill,.tl-anim .tl-spread-dot{animation:tlFade .8s ease both}
.tl-lg-hatch{width:9px;height:9px;border-radius:50%;display:inline-block;box-shadow:inset 0 0 0 1px var(--swatch-outline);background:var(--c-none-b)}
.ov-ring{display:block}
.ov-ring .ov-ring-track{stroke:var(--track)}
.ov-ring .ov-ring-arc{stroke:var(--accent)}
.ov-ring .ov-ring-seg{stroke-linecap:butt;transition:opacity .15s ease}
.ov-ring-big .ov-ring-seg{cursor:pointer}
.ov-ring-seg.off{opacity:.28}
.ov-ring-seg.on,.ov-ring-big .ov-ring-seg:hover{opacity:1}
.ov-ring-t{fill:var(--text);font-size:12.5px;font-weight:600}
.ov-ring-big .ov-ring-t{font-size:18px;font-weight:500}
@keyframes ovRingSweep{from{stroke-dashoffset:var(--c,1)}to{stroke-dashoffset:0}}
.ov-ring.ov-anim .ov-ring-reveal{animation:ovRingSweep .85s cubic-bezier(.4,0,.2,1) backwards}
.ov-ringonly{flex-direction:column;align-items:flex-start;justify-content:center;gap:12px}
.ov-ringbox{display:flex}
.ov-ringrow{display:flex;align-items:center;gap:40px;flex-wrap:wrap;justify-content:flex-start}
.ov-legend{display:grid;grid-template-columns:repeat(3,minmax(0,auto));gap:4px 44px}
.ov-leg-item{display:flex;align-items:center;gap:8px;background:none;border:0;color:var(--text);cursor:pointer;font:inherit;font-size:var(--fs-xs);padding:2px 7px;border-radius:6px;text-align:left;transition:opacity .15s ease,background .15s ease}
.ov-leg-item:nth-child(6n+4),.ov-leg-item:nth-child(6n+5),.ov-leg-item:nth-child(6n+6){background:color-mix(in srgb,var(--text) 5%,transparent)}
.ov-leg-item:hover,.ov-leg-item.on{background:var(--surface-2)}
.ov-leg-item.off{opacity:.4}
.ov-leg-sw{width:11px;height:11px;border-radius:3px;flex:none;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.ov-leg-lab{flex:1;white-space:nowrap}
.ov-leg-pct{margin-left:auto;padding-left:44px;color:var(--muted);font-variant-numeric:tabular-nums}
.cfd-modal{position:fixed;inset:0;z-index:30;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.5)}
.cfd-modal-box{background:var(--surface);border:1px solid var(--border-2);border-radius:14px;padding:18px 20px;box-shadow:0 18px 60px rgba(0,0,0,.45);max-width:440px;width:calc(100% - 40px)}
.cfd-modal-h{font-size:var(--fs-base);font-weight:600;margin-bottom:14px}
.cfd-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.cfd-card{display:flex;flex-direction:column;align-items:center;gap:4px;text-align:center;background:var(--surface-2);border:1px solid var(--border-2);border-radius:10px;padding:16px 8px;color:var(--text);cursor:pointer;font:inherit}
.cfd-card:hover{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 12%,var(--surface-2))}
.cfd-card-ic{font-size:22px;line-height:1.1}
.cfd-card b{font-size:var(--fs-sm)}
.cfd-card small{font-size:var(--fs-2xs);color:var(--muted-2)}
.rg-sw{display:inline-block;width:12px;height:12px;border-radius:3px;flex:none;box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.rg-row{display:flex;align-items:center;gap:7px;font-size:var(--fs-xs);padding:4px 0}
.rg-row+.rg-row{border-top:1px solid var(--track)}
.rg-n{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text)}
.rg-ar{color:var(--muted-2)}
.rg-when{margin-left:auto;color:var(--muted-2)}
.rg-m{margin-left:8px;font-size:var(--fs-xs);color:var(--muted-2)}
.ov-pct{border:0;background:none;font:inherit;font-weight:700;color:var(--text);cursor:pointer;padding:0;vertical-align:baseline}
.ov-pct:hover{text-decoration:underline;text-decoration-style:dotted;text-underline-offset:2px}
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
/* #D Shape changes (git outline diffs) */
.oc{margin-top:14px;border-top:1px solid var(--border);padding-top:12px}
.oc-h{font-size:var(--fs-xs);color:var(--muted);margin-bottom:8px}
.oc-day{margin-top:4px}
.oc-day-h{display:flex;align-items:center;gap:8px;width:100%;padding:5px 6px;border:0;border-radius:7px;background:none;color:var(--text);font:inherit;cursor:pointer;text-align:left}
.oc-day-h:hover{background:var(--surface-2)}
.oc-chev{flex:0 0 auto;width:10px;color:var(--muted-2)}
.oc-date{flex:1;font-weight:600}
.oc-count{flex:0 0 auto;font-size:var(--fs-xs);color:var(--muted-2);font-variant-numeric:tabular-nums}
.oc-grid{display:flex;flex-wrap:wrap;gap:10px;padding:8px 6px 2px}
.oc-cell{display:flex;flex-direction:column;align-items:center;gap:3px;width:60px}
.oc-cell svg{width:48px;height:48px;background:var(--track);border-radius:6px;border:1px solid var(--border)}
.oc-old{fill:var(--muted-2);opacity:.32}
.oc-new{fill:var(--text)}
.tad{margin-top:14px;border-top:1px solid var(--border);padding-top:12px}
.tad-h{font-size:var(--fs-xs);color:var(--muted);margin-bottom:8px}
.tad-sub{color:var(--muted-2);font-weight:400}
.tad-row{display:flex;align-items:center;gap:10px;width:100%;padding:5px 6px;border:0;border-radius:7px;background:none;color:var(--text);font:inherit;cursor:pointer;text-align:left}
.tad-row:hover{background:var(--surface-2)}
.tad-row svg{width:34px;height:34px;flex:none;background:var(--track);border-radius:6px;border:1px solid var(--border)}
.tad-glyph{font-weight:600}
.tad-master{color:var(--muted);font-size:var(--fs-xs)}
.tad-when{margin-left:auto;color:var(--muted);font-size:var(--fs-xs);text-align:right}
.tad-when b{color:var(--text);font-weight:600}
.oc-glyph{font-size:var(--fs-2xs);color:var(--muted);max-width:60px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
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
.tl-lane.done .tl-lane-spark polyline{stroke:var(--ok)}
.tl-lane.done .tl-lane-bar>span{background:var(--ok)}
.tl-lane-pct{flex:0 0 auto;color:var(--text);font-variant-numeric:tabular-nums;text-align:right;min-width:34px}
.tl-lane-d{flex:0 0 auto}
.tl-scrubline{stroke:var(--accent);stroke-width:1.5;stroke-dasharray:3 3;opacity:.85;pointer-events:none}
.tl-scrubdot{fill:var(--accent);pointer-events:none}
.tl-cal-card{margin-top:14px;border-top:1px solid var(--border);padding-top:12px}
.tl-cal-h{display:flex;align-items:center;gap:10px;font-size:var(--fs-xs);color:var(--muted);margin-bottom:8px}
.tl-cal-ttl{flex:none}
.tl-mcal{margin-top:2px}
.tl-mcal-nav{display:flex;align-items:center;justify-content:center;gap:14px;margin-bottom:10px}
.tl-mcal-title{font-size:var(--fs-sm);font-weight:600;color:var(--text);min-width:150px;text-align:center}
.tl-mcal-prev,.tl-mcal-next{padding:1px 10px;line-height:1.2;font-size:var(--fs-sm)}
.tl-mcal-grid{display:grid;grid-template-columns:repeat(7,28px);gap:5px;justify-content:center}
/* In the Timeline calendar pane, stretch the month grid to the full available width
   (square cells grow with it); the compact Overview mini-calendar keeps its 28px cells. */
.tl-calpane .tl-mcal-grid{grid-template-columns:repeat(7,minmax(0,1fr));justify-content:stretch}
.tl-calpane .tl-mcal-d{aspect-ratio:2/1}            /* half-height day cells (calendar 2x shorter) */
.tl-mcal-dow{text-align:center;font-size:var(--fs-2xs);color:var(--muted-2);padding-bottom:2px}
.tl-mcal-d{aspect-ratio:1;display:flex;align-items:flex-start;justify-content:flex-end;border-radius:5px;padding:2px 4px;font-size:var(--fs-2xs);color:var(--muted-2);background:transparent}
.tl-mcal-inrange{background:color-mix(in srgb,var(--text) 5%,transparent)}
.tl-mcal-snap{color:var(--text);cursor:pointer}
.tl-mcal-snap.lv1{background:color-mix(in srgb,var(--accent) 12%,var(--track))}
.tl-mcal-snap.lv2{background:color-mix(in srgb,var(--accent) 40%,var(--track))}
.tl-mcal-snap.lv3{background:color-mix(in srgb,var(--accent) 70%,var(--track))}
.tl-mcal-snap.lv4{background:var(--accent);color:#fff}
.tl-mcal-snap:hover{outline:1px solid var(--text);outline-offset:1px}
.tl-mcal-n{pointer-events:none}
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
.toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%) translateY(10px);background:var(--surface);border:1px solid var(--border-2);color:var(--text);border-radius:var(--r-sm);padding:8px 14px;font-size:var(--fs-sm);opacity:0;pointer-events:none;transition:opacity .15s,transform .15s}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
/* Boot-failure card (start()'s catch). Pure CSS — it must render when the embedded
   model is broken, so the rainbow brand mark is a hard-coded gradient, not --cN data.
   Theme tokens (--surface/--border/--text/--muted) keep both themes right. */
.err-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
.err-card{max-width:460px;text-align:center;background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:34px 32px}
.err-mark{display:block;width:52px;height:10px;border-radius:5px;margin:0 auto 18px;background:linear-gradient(90deg,#f97e55,#ffbe68,#fff157,#6bab59,#64a5ef,#a962e7)}
.err-title{margin:0 0 10px;font-size:var(--fs-base);font-weight:600;color:var(--text)}
.err-msg{margin:0;font-size:var(--fs-xs);line-height:1.5;color:var(--muted);font-family:"JetBrains Mono",monospace;word-break:break-word}
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
    view: "tabs", before: false, baPlaying: false,
    focus: null,
    ovExpand: {},                          // which Overview cards are expanded
    heatSort: "category",                  // focus-mode glyph grid: "category" | "color"
    heatRecent: false,                     // focus-mode glyph grid: show only glyphs modified in the last 7 days
    cellSize: 40,                          // glyph-grid cell min size in px (slider-controlled, 20..40)
    tlPane: "graph",                       // Timeline card: "graph" (chart) | "calendar" (activity calendar)
    funnelOpen: false,                     // per-step funnel: collapsed by default, toggled by the % ring/number
    ocOpen: {},                            // Timeline "Shape changes" day blocks expanded? (closed by default)
    tlGran: "save",                        // Timeline mode: "save" (one point per save, the base graph) | "time"
    tlBucket: "day",                       // Time-mode grouping: "hour" | "day" | "month"
    calY: null, calM: null,                // Activity-calendar displayed month (lazy: last snapshot)
    tlScrub: null,                         // picked-moment scrubber index (null -> latest snapshot)
    viewLo: null, viewHi: null,            // Range-navigator zoom window (snapshot indices; null = full)
    tlSpan: null,                          // active duration preset ("1d".."1y"/"all"; null = custom/full)
    journeyGlyph: null,                    // journey modal
    theme: savedTheme || (prefersLight ? "light" : "dark")
  };
  // Timeline datasets: the per-day set (always) and the fine-grain per-save/per-commit set
  // (may be null). "Save" mode plots the raw fine set; "Time" mode buckets that fine set by
  // hour/day/month (last save per bucket). applyGranularity() swaps which trend/journeys/
  // journeyIndex H points at. H.fineKind ("commit"|"save") picks the user-facing wording.
  var tlDay = null, tlCommit = null;
  function fineUnits(){ return H.fineKind === "save" ? "saves" : "commits"; }
  function fineNoun(){ return H.fineKind === "save" ? "save" : "commit"; }
  // Bucket key for a datetime ISO string per the active Time unit (truncate the ISO).
  function bucketKey(iso, unit){
    var s = String(iso);
    if (unit === "hour") return s.slice(0,13);     // YYYY-MM-DDTHH
    if (unit === "month") return s.slice(0,7);      // YYYY-MM
    return s.slice(0,10);                            // day: YYYY-MM-DD
  }
  // Group a fine (per-save) dataset into one snapshot per time bucket — the LAST save in
  // each bucket wins (series is oldest-first). journeyIndex stays the full fine history so
  // stateAt() still reconstructs colours at any bucket-end date.
  function bucketedTrend(fine, unit){
    var ser = (fine.trend && fine.trend.series) || [];
    var lastByBucket = {};
    ser.forEach(function(p){ lastByBucket[bucketKey(p.date, unit)] = p; });
    var keys = Object.keys(lastByBucket).sort();
    var series = keys.map(function(k){ return lastByBucket[k]; });
    var dates = series.map(function(p){ return p.date; });
    return { trend: { series: series, dates: dates,
                      today: dates.length ? dates[dates.length-1] : null,
                      streak: fine.trend && fine.trend.streak },
             journeys: fine.journeys, journeyIndex: fine.journeyIndex };
  }
  function applyGranularity(){
    var fine = tlCommit || tlDay;          // prefer the per-save fine set; fall back to per-day
    if (!fine) return;
    var src = (state.tlGran === "save") ? fine : bucketedTrend(fine, state.tlBucket);
    H.trend = src.trend; H.journeys = src.journeys; H.journeyIndex = src.journeyIndex;
  }
  function resetTimelineWindow(){
    state.tlScrub = null;                  // reset the picked moment to latest on switch
    state.viewLo = null; state.viewHi = null;   // window indices are dataset-specific
    state.tlSpan = null;
  }
  function setGranularity(gran){
    if (gran === "save" && !tlCommit) return;
    if (gran === state.tlGran) return;
    state.tlGran = gran;
    resetTimelineWindow();
    applyGranularity();
    update();
  }
  function setBucket(unit){
    if (unit === state.tlBucket) return;
    state.tlBucket = unit;
    if (state.tlGran !== "time"){ state.tlGran = "time"; }   // picking a bucket implies Time mode
    resetTimelineWindow();
    applyGranularity();
    update();
  }
  // The colour bar runs its fill animation once, on the first paint only — not on
  // master switches or any later re-render.
  var barsAnim = false, introPlayed = false;
  var scrubAnim = false;                        // a moment was just picked (scrub): animate the bars/cells/lines that follow it
  var lastRenderMaster = "__cfd_init__";              // last-rendered state.master, to fade cards+discs on a Global<->Focus switch
  var sparkPrev = {};                           // last-rendered lane sparkline points per key, so the line can morph on scrub
  var tlChartShouldAnim = false;                // draw-in the timeline chart once when entering the Timeline
  var laneSparkShouldAnim = false;              // draw-in the lane sparklines when the focused master switches
  var vnavShouldAnim = false;                   // draw the version-nav progress line once when a node is clicked
  var vnavPrevFrac = 0;                          // fill fraction shown BEFORE the click, so the line grows/shrinks from the old node end (not from the start)
  var segswPrev = {};                            // last --seg index per .segsw switch key, so a click can morph the pill from old->new
  var segswAnimKey = null;                       // which switch to slide-animate on the next render (set on click, guarded by prev!==seg)
  var laneNumCache = {};                        // last-shown lane % per lane key, for count-up tweening
  var vizIntroPlayed = false;                   // colour-spread radar build-animates once

  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]; }); }
  function pct(n,t){ return t ? Math.round(n/t*100) : 0; }
  // WebKit (and therefore the plugin's embedded WKWebView) does not support canvas 2D
  // ctx.filter, so the disc/script-card blur silently no-ops there (hard wedges). Probe
  // once; the browser path (filter works) is untouched, and the canvas blurs below fall
  // back to a downscale->upscale approximation when it's missing.
  var CTX_FILTER_OK = (function(){
    try {
      var c = document.createElement("canvas"); c.width = c.height = 9;
      var g = c.getContext("2d");
      g.fillStyle = "#fff"; g.fillRect(0, 0, 9, 9);
      g.filter = "blur(2px)"; g.fillStyle = "#000"; g.fillRect(0, 0, 4, 9); g.filter = "none";
      var p = g.getImageData(4, 4, 1, 1).data;
      return p[0] > 20 && p[0] < 235;            // boundary pixel is mid-grey only if blurred
    } catch(e){ return false; }
  })();
  // Cheap, WebKit-safe blur: shrink the source then draw it back up with smoothing.
  function cssSafeBlur(src, dst, side, radius){
    var step = Math.max(2, Math.round(radius));
    var small = Math.max(1, Math.round(side / step));
    var t = document.createElement("canvas"); t.width = t.height = small;
    var tg = t.getContext("2d");
    tg.imageSmoothingEnabled = true; tg.imageSmoothingQuality = "high";
    tg.drawImage(src, 0, 0, small, small);
    dst.imageSmoothingEnabled = true; dst.imageSmoothingQuality = "high";
    dst.drawImage(t, 0, 0, side, side);
  }
  function varFor(k){ return k===-1 ? "--c-none" : "--c"+k; }
  // A legend swatch dot that glows in its own colour (matches the progress-bar glow).
  function legendDot(key){
    var v = varFor(key);
    return '<i style="background:var('+v+');box-shadow:inset 0 0 0 1px var(--swatch-outline),'
      + '0 0 7px color-mix(in srgb,var('+v+') 26%,transparent)"></i>';
  }
  function labelFor(k){
    if (k===-1 || String(k)==="-1") return H.noneLabel;
    // steps keys are ints, but callers pass H.order keys (strings) too — compare as
    // strings so the real label is returned (not the "Color N" fallback).
    for (var i=0;i<H.steps.length;i++){ if (String(H.steps[i].key)===String(k)) return H.steps[i].label; }
    return "Color "+k;
  }
  // A glyph painted with a HIDDEN colour (a label hidden in the plugin) is not a
  // workflow step, so it must read as uncoloured EVERYWHERE — otherwise it shows as a
  // phantom colour the ring/breakdown deny, paints a stray wedge on the disc, and lands
  // in "None" while still tinted its real colour. Rewrite any per-master key that isn't
  // in the visible order to -1, once, at load. (stateAt does the same for the timeline.)
  function normalizeHiddenKeys(){
    var inOrder = {}; (H.order||[]).forEach(function(k){ inOrder[String(k)] = 1; });
    (H.masters||[]).forEach(function(m){
      var ks = m.keys; if (!ks) return;
      for (var i=0;i<ks.length;i++){ if (ks[i] !== -1 && !inOrder[String(ks[i])]) ks[i] = -1; }
    });
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
    // glow in the segment's own colour (None uses the solid grey, not its gradient)
    var glow = key===-1 ? "--c-none-b" : varFor(key);
    return '<span class="segc'+(on?" on":"")+(off?" off":"")+'" data-fkey="'+key+'" style="width:'+w
      + '%;background:var('+varFor(key)+');--i:'+(idx||0)
      + ';box-shadow:0 0 9px color-mix(in srgb,var('+glow+') 22%,transparent),inset -6px 0 9px -3px rgba(0,0,0,.2)" title="'+esc(lab)+' — click to focus these glyphs"></span>';
  }
  // ----- Non-exporting exclusion ---------------------------------------------
  // Glyphs marked non-exporting in Glyphs (H.nonExporting) are ALWAYS dropped
  // from every completion percentage, matching the palette. PARITY: the
  // embedded masters[].counts/keys always ship ALL glyphs (raw truth); the
  // exclusion is applied HERE, client-side, so the displayed numbers match
  // the palette's. countedSet() centralises the exclusion: null when nothing
  // to exclude (every glyph exports), else a {name:1} lookup of the glyphs
  // that DO count. Heatmap cells of excluded glyphs dim (.ncnt) instead of
  // vanishing.
  var COUNTED = null, COUNTEDN = 0;            // memo; the exclusion never changes after load
  function countedSet(){
    if (!(H.nonExporting||[]).length) return null;
    if (COUNTED) return COUNTED;
    var off = {}; (H.nonExporting||[]).forEach(function(n){ off[n]=1; });
    var set = {}, n = 0;
    (H.glyphNames||[]).forEach(function(nm){ if (!off[nm]){ set[nm]=1; n++; } });
    COUNTEDN = n;
    return (COUNTED = set);
  }
  function isCounted(name){ var set = countedSet(); return !set || !!set[name]; }
  function countedTotal(){ return countedSet() ? COUNTEDN : (H.glyphTotal||0); }
  // Per-master tallies with the exclusion applied (memoised; consulted whenever
  // the font has non-exporting glyphs): the m.counts / m.uncolored equivalents,
  // recomputed from the raw m.keys. The cumulative "reached k or beyond" count
  // is the suffix sum of the exclusive distribution in workflow order.
  var CSTATS = {};
  function countedStats(m){
    if (CSTATS[m.id]) return CSTATS[m.id];
    var set = countedSet(), ks = m.keys||[], names = H.glyphNames||[];
    var dist = {}, none = 0;
    for (var i=0;i<ks.length;i++){
      if (set && !set[names[i]]) continue;
      var k = ks[i], sk = String(k);
      if (k===-1 || H.order.indexOf(sk)===-1) none++; else dist[sk]=(dist[sk]||0)+1;
    }
    var counts = {}, run = 0, order = H.order||[];
    for (var j=order.length-1;j>=0;j--){
      var key = order[j];
      run += dist[key]||0; counts[key] = run;
    }
    return (CSTATS[m.id] = { dist:dist, counts:counts, uncolored:none });
  }
  // Exclusive current-colour tally for a master: how many glyphs sit at EACH colour
  // right now (memoised per master). m.counts is cumulative ("reached step k or
  // beyond"), which made every earlier step inherit the most-advanced count — so the
  // legend/compare/export must use this, not m.counts, to match the stacked bar.
  var EXCL = {};
  function exclusiveOf(m){
    if (EXCL[m.id]) return EXCL[m.id];
    var set = countedSet(), names = H.glyphNames||[];
    var dist = {}, ks = m.keys || [];
    for (var i=0;i<ks.length;i++){ if (set && !set[names[i]]) continue; var k=ks[i], sk=String(k); if (k!==-1 && H.order.indexOf(sk)!==-1) dist[sk]=(dist[sk]||0)+1; }
    return (EXCL[m.id] = dist);
  }
  // cumulative: glyphs that reached step k OR BEYOND (the model's m.counts). This is
  // the workflow-completion metric used by the legends, Compare grid and exports.
  // With non-exporting glyphs present the counted recompute stands in for m.counts.
  function countFor(m,k){
    if (countedSet()){ var cs = countedStats(m); return k===-1 ? cs.uncolored : (cs.counts[String(k)]||0); }
    return k===-1 ? m.uncolored : (m.counts[String(k)]||0);
  }
  function uncoloredFor(m){ return countedSet() ? countedStats(m).uncolored : m.uncolored; }
  function startedOf(m){ return countedTotal() - uncoloredFor(m); }

  function aggregate(){
    var grand = countedTotal() * H.masters.length;
    var agg = {}; H.order.forEach(function(o){ agg[o]=0; });
    H.masters.forEach(function(m){ H.order.forEach(function(o){ agg[o]+=countFor(m,o); }); });
    return { grand:grand, agg:agg };
  }

  function aggExclusive(){
    var dist = {}; H.order.forEach(function(o){ dist[o]=0; }); var none = 0;
    var set = countedSet(), names = H.glyphNames||[];
    H.masters.forEach(function(m){
      (m.keys||[]).forEach(function(k, i){
        if (set && !set[names[i]]) return;
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
      + '<button type="button" id="cfd-export" class="icon" aria-label="Export report" title="Export the report as PDF, CSV or JSON">􀈂</button>'
      + '<button type="button" id="cfd-theme" class="icon" aria-label="Toggle light or dark theme">◐</button></header>';
  }
  function toolbar(){
    return '<div class="tb">'
      + '<button type="button" id="cfd-overview" class="chip" aria-pressed="true" title="Back to the overview">⌂ Overview</button>'
      + '<button type="button" id="cfd-timeline" class="chip" aria-pressed="false"'+(timelineLock()?' aria-disabled="true" title="'+esc(timelineLock())+'"':'')+'>📈 Timeline</button></div>';
  }
  // The Timeline tab needs 3 snapshots (timelineView's gate); below that the chip is
  // disabled and its title says what unlocks it. "" once ready.
  function timelineLock(){
    var n = ((H.trend && H.trend.dates) || []).length;
    if (n >= 3) return "";
    var byCommit = state.tlGran === "save";
    return "Timeline unlocks at 3 "+(byCommit ? fineUnits() : "days")+" of history — "+n+" so far. "
      + (byCommit ? "Make another "+fineNoun()+"." : "Save again tomorrow.");
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
  function gradedSum(m){ var W=stepWeights().weight, ks=m.keys||[], names=H.glyphNames||[], set=countedSet(), s=0; for (var i=0;i<ks.length;i++){ if (set && !set[names[i]]) continue; var w=W[ks[i]]; if (w) s+=w; } return s; }
  function gradedMasterPct(m){ var n=countedTotal()||((m.keys||[]).length)||1; return Math.round(gradedSum(m)/n*100); }
  // Graded completion % of one master AT a past snapshot date — partial credit per
  // step (final step weight 1), the SAME metric the Overview ring / Compare / exports
  // use. Reconstructs the state at the date (stateAt) and sums step weights, so the
  // Line chart, the ring and Flow all tell one consistent story. (Was final-step-only,
  // which sat at 0 until glyphs reached the last colour, then cliffed to 100.)
  // Memoised per master|date: the matrix/week/nav surfaces ask for the same pairs on
  // every re-render, and each answer is a full stateAt reconstruction. Same keying +
  // reset discipline as NAVCACHE/PMCACHE — the key is the active timeline dataset
  // (tlDatasetKey), so switching granularity/bucket drops the memo; scrubbing keeps it.
  var GPCACHE = {}, GPCACHE_KEY = "";
  function gradedPctAt(masterId, date){
    var key = tlDatasetKey();
    if (GPCACHE_KEY !== key){ GPCACHE = {}; GPCACHE_KEY = key; }
    var ck = masterId + "|" + date;
    if (GPCACHE[ck] != null){ return GPCACHE[ck]; }
    var W = stepWeights().weight, total = countedTotal() || 1, snap = stateAt(masterId, date), s = 0;
    for (var name in snap){ if (!isCounted(name)) continue; var w = W[String(snap[name])]; if (w){ s += w; } }
    return (GPCACHE[ck] = s / total * 100);
  }
  function gradedOverallPct(){ var s=0, tot=0; H.masters.forEach(function(m){ s+=gradedSum(m); tot+=countedTotal(); }); return tot? Math.round(s/tot*100):0; }
  // Overall graded % AT a past snapshot date (avg of per-master gradedPctAt — countedTotal
  // is master-independent, so this matches gradedOverallPct's weighting).
  function gradedOverallPctAt(date){
    if (!H.masters.length) return 0;
    var s = 0; H.masters.forEach(function(m){ s += gradedPctAt(m.id, date); }); return Math.round(s / H.masters.length);
  }
  function masterStarted(m){ return (uncoloredFor(m)||0) < countedTotal(); }   // any counted colour set at all
  // A donut. With `segs` ({key,frac,label} colour shares) it tiles the ring with the
  // palette colours — each arc proportional to its share of the font, the uncoloured
  // remainder showing as the faint track. opts.select makes each arc a colour selector
  // (data-fkey; dims the others when one is focused). opts.big draws the large Overview
  // hero ring. The centre always reads the completion %. No segs -> a single progress arc.
  function ring(p, segs, opts){
    opts = opts || {};
    var big = !!opts.big, select = !!opts.select, anim = !!opts.anim;
    // big ring sized 78 (5% up from 74) with a proportionally thin stroke; the % text keeps a
    // fixed 18px (the viewBox tracks sz, so 1 user-unit = 1px regardless of size).
    var sz = big ? 78 : 52, cc = sz/2, sw = big ? 10 : 5, r = cc - sw/2 - 2, c = 2*Math.PI*r;
    var arcs = "";
    if (segs && segs.length){
      var acc = 0;
      segs.forEach(function(sg){
        var len = Math.max(0, Math.min(1, sg.frac||0)) * c;
        if (len <= 0.01) return;
        var on = select && state.focus === sg.key;
        var off = select && state.focus !== null && !on;
        var cls = "ov-ring-seg" + (on ? " on" : (off ? " off" : ""));
        var sel = select ? ' data-fkey="'+sg.key+'" title="'+esc((sg.label||"")+" — click to focus these glyphs")+'"' : '';
        arcs += '<circle class="'+cls+'"'+sel+' cx="'+cc+'" cy="'+cc+'" r="'+r+'" fill="none" stroke="var('+varFor(sg.key)+')" stroke-width="'+sw+'"'
          + ' stroke-dasharray="'+len.toFixed(2)+' '+(c-len).toFixed(2)+'" stroke-dashoffset="'+(-acc).toFixed(2)+'" transform="rotate(-90 '+cc+' '+cc+')"/>';
        acc += len;
      });
    } else {
      var offp = c*(1-Math.max(0,Math.min(100,p))/100);
      arcs = '<circle class="ov-ring-arc" cx="'+cc+'" cy="'+cc+'" r="'+r+'" fill="none" stroke-width="'+sw+'" stroke-linecap="round" stroke-dasharray="'+c.toFixed(1)+'" stroke-dashoffset="'+offp.toFixed(1)+'" transform="rotate(-90 '+cc+' '+cc+')"/>';
    }
    // anim: one global progression sweep — a single full-ring mask arc whose dashoffset
    // animates C->0, revealing the whole (multi-colour) ring as ONE motion, not per segment.
    var defs = "", body = arcs;
    if (anim){
      defs = '<defs><mask id="ovRingReveal" maskUnits="userSpaceOnUse" x="0" y="0" width="'+sz+'" height="'+sz+'">'
        + '<circle class="ov-ring-reveal" style="--c:'+c.toFixed(1)+'" cx="'+cc+'" cy="'+cc+'" r="'+r+'" fill="none" stroke="#fff" stroke-width="'+(sw+2)+'" stroke-dasharray="'+c.toFixed(1)+'" stroke-dashoffset="0" transform="rotate(-90 '+cc+' '+cc+')"/></mask></defs>';
      body = '<g mask="url(#ovRingReveal)">'+arcs+'</g>';
    }
    return '<svg class="ov-ring'+(big?" ov-ring-big":"")+(anim?" ov-anim":"")+'" width="'+sz+'" height="'+sz+'" viewBox="0 0 '+sz+' '+sz+'" role="progressbar" aria-valuenow="'+p+'" aria-valuemin="0" aria-valuemax="100" aria-label="'+p+'% complete">'
      + defs
      + '<circle class="ov-ring-track" cx="'+cc+'" cy="'+cc+'" r="'+r+'" fill="none" stroke-width="'+sw+'"/>'
      + body
      + '<text class="ov-ring-t" data-to="'+p+'" x="'+cc+'" y="'+(cc+0.5)+'" text-anchor="middle" dominant-baseline="central">'+p+'%</text></svg>';
  }
  // ----- Workflow funnel: cumulative "reached step k or beyond" as descending bars.
  // Replaces the flat text legend with the SAME cumulative metric drawn so a nearly
  // full makeup bar can't be misread as nearly complete — the funnel visibly narrows
  // toward "done". Read-only on purpose: it counts reached-or-beyond, while focusing a
  // colour means the glyphs sitting AT it (exclusive) — different sets, so the click-to-
  // focus selector stays on the makeup bar above; the funnel is the progress reference.
  function funnelHTML(cumFor, total){
    // Collapsed by default; expanded by clicking the % ring (global) / % number (master).
    // No caption or chevron — the percentage itself is the toggle (data-funnel on it).
    if (state.funnelOpen === false) return "";
    var rows = H.steps.map(function(s){
      var p = pct(cumFor(s.key)||0, total);
      if (p === 0) return "";                       // a step no glyph has reached yet
      return '<div class="fnl-row" title="'+esc(s.label+" — "+p+"% reached this step or beyond")+'">'
        + legendDot(s.key)
        + '<span class="fnl-lab">'+esc(s.label)+'</span>'
        + '<span class="fnl-track"><span class="fnl-fill" style="width:'+p+'%;background:var('+varFor(s.key)+')"></span></span>'
        + '<span class="fnl-pct">'+p+'%</span></div>';
    }).join("");
    if (!rows) rows = '<div class="fnl-empty">Not started yet</div>';
    return '<div class="funnel'+(barsAnim?" intro":"")+'" role="group" aria-label="Cumulative progress by step, reached or beyond">'+rows+'</div>';
  }
  function overall(){
    var a = aggregate(), compP = gradedOverallPct();
    // exclusive current-colour totals (one colour per glyph) so the ring tiles read the
    // same as the makeup bar did — not aggregate()'s cumulative "reached-or-beyond" sums.
    var ex = aggExclusive();
    var grand = a.grand || 1;
    // The Overview card is just the big donut ring: tiled with the exclusive colour shares,
    // each arc clickable to focus that colour's glyphs. No stacked bar, no step funnel.
    var ringSegs = H.steps.map(function(s){ return { key:s.key, label:s.label, frac:(ex.dist[String(s.key)]||0)/grand }; });
    // Colour labels beside the ring: one clickable swatch+label+% per step (+ None),
    // matching the ring arcs (same data-fkey focus + on/off highlight).
    function legItem(key, label, cnt){
      var on = state.focus === key, off = state.focus !== null && !on, p = Math.round(cnt/grand*100);
      return '<button type="button" class="ov-leg-item'+(on?" on":"")+(off?" off":"")+'" data-fkey="'+key+'" title="'+esc(label+" — "+cnt+" glyphs ("+p+"%)")+'">'
        + '<i class="ov-leg-sw" style="background:var('+varFor(key)+')"></i>'
        + '<span class="ov-leg-lab">'+esc(label)+'</span><span class="ov-leg-pct">'+p+'%</span></button>';
    }
    // 3-column grid of the 12 colour labels; "None" is intentionally omitted here.
    var legend = H.steps.map(function(s){ return legItem(s.key, s.label, ex.dist[String(s.key)]||0); }).join("");
    return '<section class="overall ov-ringonly" aria-label="Overall completion — click a colour to focus its glyphs">'
      + '<div class="ov-ringrow"><div class="ov-ringbox">'+ring(compP, ringSegs, {big:true, select:true, anim:barsAnim||scrubAnim})+'</div>'
      + '<div class="ov-legend" role="group" aria-label="Colour labels">'+legend+'</div></div>'
      + '</section>';
  }

  // Version navigator: a line of clickable dots (one per saved snapshot) above the master's
  // colour-distribution bar, so you can scrub THIS master back through its saved versions.
  // Reuses the Time-Machine scrub (scrubSet/state.tlScrub); the bar, %, heatmap, discs and
  // lanes all follow the picked moment. Hidden when there are <2 versions to move between.
  function versionNav(){
    var dates = (H.trend && H.trend.dates) || [];
    if (dates.length < 2) return "";
    // In the per-master card, only show a version where THIS master's colours actually
    // changed (vs the previous snapshot) — a static master collapses to its single
    // baseline. Global view (no master) still shows every version. data-vnav keeps the
    // ABSOLUTE series index so scrubSet still lands on the right date. The change flags
    // come from changeCounts() (cached, walked off the sparse journeyIndex) — same
    // nodes as diffing full stateAt snapshots, without paying that on every render.
    var mid = state.master, vidx;
    if (mid){
      vidx = [0];
      var chg = changeCounts(mid);
      for (var k=1;k<dates.length;k++){
        if (chg[k]){ vidx.push(k); }
      }
    } else {
      vidx = dates.map(function(_d, i){ return i; });
    }
    var cur = scrubIndex();
    // the version in effect at the scrubbed moment = latest change index <= cur
    var activePos = 0;
    for (var pi=0;pi<vidx.length;pi++){ if (vidx[pi] <= cur) activePos = pi; else break; }
    var dots = vidx.map(function(di, p){
      var d = dates[di];
      var cls = "vnav-dot" + (p<=activePos?" past":"") + (p===activePos?" on":"");
      return '<button type="button" class="'+cls+'" data-vnav="'+di+'" title="'+esc(d+(p===activePos?" · showing":""))
        + '" aria-label="'+esc("Version "+(p+1)+" of "+vidx.length+", "+d)+'"'+(p===activePos?' aria-current="true"':'')+'></button>';
    }).join("");
    // A coloured progress line drawn from the first node to the current one. The fill spans
    // the whole track and is clipped with transform:scaleX(frac); when a node is clicked it
    // animates from the PREVIOUS fraction to the new one, so the line grows/shrinks from the
    // old node end (not redrawing from the start). transform-origin:left keeps node 0 fixed.
    var frac = vidx.length > 1 ? activePos/(vidx.length-1) : 0;
    var animCls = vnavShouldAnim ? " anim" : ""; vnavShouldAnim = false;
    var fromFrac = vnavPrevFrac; vnavPrevFrac = frac;
    return '<div class="vnav" role="group" aria-label="Navigate saved versions">'
      + '<span class="vnav-line"></span>'
      + '<span class="vnav-fill'+animCls+'" style="--vnav-from:'+fromFrac.toFixed(4)+';--vnav-to:'+frac.toFixed(4)+';transform:scaleX('+frac.toFixed(4)+')" aria-hidden="true"></span>'
      + dots+'</div>';
  }

  // The version timeline lifted into its OWN card, shown ABOVE the master's progress card.
  // Returns "" when there are <2 versions (versionNav self-gates), so no empty card appears.
  function versionCard(){
    var nav = versionNav();
    if (!nav) return "";
    var dates = (H.trend && H.trend.dates) || [];
    var cur = scrubIndex();
    var when = (cur >= 0 && dates[cur]) ? dateLabel(dates[cur]) : "";
    return '<section class="vnav-card" aria-label="Saved versions">'
      + '<div class="vnav-card-h"><span class="vnav-card-ttl">Versions</span>'
      + (when ? '<span class="vnav-card-when">'+esc(when)+'</span>' : '')
      + '</div>' + nav + '</section>';
  }
  // The selected master rendered like the overall card (ring + stacked bar +
  // legend), but scoped to this one master instead of the whole font.
  function masterOverall(m){
    var total = countedTotal();
    var dates = (H.trend && H.trend.dates) || [];
    var scrubbing = (state.tlScrub != null) && dates.length > 1;
    var dist = {}, none = 0, started, headPct, cumFor;
    if (scrubbing){
      // Reconstruct this master's colour distribution AT the navigated version (stateAt),
      // so the bar + % + funnel reflect the picked snapshot, not today.
      var date = dates[scrubIndex()], snap = stateAt(m.id, date), nm, sk;
      for (nm in snap){ if (!isCounted(nm)) continue; var k = snap[nm]; sk = String(k);
        if (k!==-1 && H.order.indexOf(sk)!==-1) dist[sk] = (dist[sk]||0) + 1; }
      var colored = 0; for (sk in dist){ colored += dist[sk]; }
      none = Math.max(0, total - colored); started = colored;
      headPct = Math.round(gradedPctAt(m.id, date));
      var cum = {}, order = H.order || [], run = 0;
      for (var j = order.length-1; j >= 0; j--){ run += dist[order[j]] || 0; cum[order[j]] = run; }
      cumFor = function(kk){ return kk===-1 ? none : (cum[kk] || 0); };
    } else {
      // exclusive current-colour tally drives the makeup bar (exclusion-aware).
      var set = countedSet(), names = H.glyphNames || [];
      (m.keys||[]).forEach(function(k, i){ if (set && !set[names[i]]) return; var s2=String(k);
        if (k===-1 || H.order.indexOf(s2)===-1) none++; else dist[s2]=(dist[s2]||0)+1; });
      started = total - uncoloredFor(m); headPct = gradedMasterPct(m);
      cumFor = function(kk){ return countFor(m,kk)||0; };
    }
    var startP = pct(started,total);
    // one clear progress number; the started count is in the tooltip. The number is also
    // the funnel toggle (click to show/hide progress by step).
    var head = '<span class="ov-name">'+esc(m.name)+'</span>'
      + '<button type="button" class="ov-pct" data-funnel="1" aria-expanded="'+(state.funnelOpen!==false)+'" title="'+started+'/'+total+' glyphs started ('+startP+'%) · click for progress by step">'+headPct+'% complete</button>';
    var segParts = H.steps.map(function(s,i){
      return segSpan(s.key, pct(dist[String(s.key)]||0, total), s.label, i);
    }).join("") + segSpan(-1, pct(none, total), H.noneLabel, H.steps.length);
    return '<section class="overall master-overall" aria-label="'+esc(m.name+" totals")+'">'
      + '<div class="ov-main"><div class="ov-head">'+head+'</div>'
      + '<div class="seg'+(barsAnim?" intro":"")+'" role="img" aria-label="'+esc(m.name+" colour distribution")+'">'+segParts+'</div>'
      + funnelHTML(cumFor, total)+'</div></section>';
  }
  function heatmap(m){
    var cats = H.categories || [];
    // Time travel: when a moment is picked on the Timeline chart (state.tlScrub),
    // every cell renders the HISTORICAL colour at that snapshot, reconstructed via
    // stateAt() — the same source the tower discs and the category/script lanes
    // read, so all the scrub-aware surfaces agree. stateAt already normalises
    // hidden keys to -1; a glyph with no event by that date reads as uncoloured
    // (exactly like the discs' countsOf).
    var scrubISO = null, scrubSnap = null, scrubPrevSnap = null;
    if (state.tlScrub != null){
      var sdates = (H.trend && H.trend.dates) || [], si = scrubIndex(), sdate = sdates[si];
      if (sdate != null){ scrubISO = sdate; scrubSnap = stateAt(m.id, sdate);
        // the snapshot BEFORE the picked day, so Before/After can diff ANY picked moment vs
        // the day before it (not only the latest run).
        if (si > 0){ scrubPrevSnap = stateAt(m.id, sdates[si-1]); } }
    }
    var items = [];
    for (var i=0;i<H.glyphNames.length;i++){
      // the historical key feeds the SAME items the cell colour, the focus filter
      // and the by-colour grouping read, so they stay consistent while scrubbed.
      var key0 = scrubSnap ? (scrubSnap[H.glyphNames[i]] != null ? scrubSnap[H.glyphNames[i]] : -1) : m.keys[i];
      items.push([H.glyphNames[i], key0, i]);
    }
    function matchesFocus(it){
      var k = it[1];
      var fk = (k===-1 || H.order.indexOf(String(k))===-1) ? -1 : k;
      return fk === state.focus;
    }
    // When a colour is focused, show ONLY its glyphs; the grid recomposes (packed).
    // Otherwise every glyph (no cap); letterforms come from H.paths.
    var shown = (state.focus===null) ? items : items.filter(matchesFocus);
    var jidx = (H.journeyIndex && H.journeyIndex[m.id]) || {};
    var paths = (H.paths && H.paths[m.id]) || {};
    // The changeset that drives Before/After + the "Recently modified" filter: glyphName ->
    // [previousKey]. Scrubbed to a past day -> the diff vs the PREVIOUS snapshot date, so any
    // picked moment compares with the day before it. Not scrubbed -> "since the last run"
    // (H.changes, with a history-derived fallback).
    var ch = {};
    if (scrubSnap){
      if (scrubPrevSnap){
        var seenG = {};
        for (var gp in scrubPrevSnap){ seenG[gp] = 1; }
        for (var gc in scrubSnap){ seenG[gc] = 1; }
        for (var gname in seenG){
          var bKey = (scrubPrevSnap[gname] != null) ? scrubPrevSnap[gname] : -1;
          var aKey = (scrubSnap[gname] != null) ? scrubSnap[gname] : -1;
          if (String(bKey) !== String(aKey)){ ch[gname] = [bKey]; }
        }
      }
    } else {
      ch = (H.changes && H.changes[m.id]) || {};
      // Before/After fallback (#B): with no last-run diff recorded, derive each glyph's
      // previous colour from its saved history so the switch still appears + works.
      if (!Object.keys(ch).length){
        for (var gn in jidx){ var jev = jidx[gn]; if (jev && jev.length >= 2){ var pk = jev[jev.length-2][1], nk = jev[jev.length-1][1]; if (pk !== nk){ ch[gn] = [pk]; } } }
      }
    }
    // "Recently modified" filter (opt-in): keep ONLY the glyphs that actually changed since
    // the last run — i.e. the ones in the changeset. (The old 7-days-ago baseline matched
    // every coloured glyph on a freshly-coloured font, so the toggle read as a no-op.)
    if (state.heatRecent && Object.keys(ch).length){
      shown = shown.filter(function(it){ return ch[it[0]] != null; });
    }
    function cellHTML(it){
      var name = it[0], key = it[1], lab = labelFor(key);
      // non-exporting: excluded glyphs stay visible but DIM (.ncnt) with a
      // "not counted" affordance — they never vanish from the grid.
      var dim = !isCounted(name);
      if (dim) lab += " — not counted";
      // "before" = the glyph's previous colour from the active changeset (the last run, or
      // the PREVIOUS snapshot day while scrubbed); falls back to the current key (no change).
      var wasKey = (ch[name] != null) ? ch[name][0] : key;
      var nowVar = varFor(key), wasVar = varFor(wasKey);
      var showVar = state.before ? wasVar : nowVar;
      var p = paths[name];
      var inner = p ? '<svg viewBox="' + esc(p.vb) + '" preserveAspectRatio="xMidYMid meet"><path d="' + esc(p.d) + '"/></svg>' : '';
      var cls = 'cell' + (p ? ' glyph' : '') + (dim ? ' ncnt' : '');
      var attrs = ' data-glyph="' + esc(name) + '" data-now="' + nowVar + '" data-was="' + wasVar + '" style="background:color-mix(in srgb,var(' + showVar + ') 35%,transparent)"';
      // An UNSAVED font has no file path, so a glyphsapp:// link would target the
      // wrong document — render a non-link cell instead (same classes and data
      // attributes, so the hover tooltip and animations still work).
      if (!H.filePath){
        return '<span class="' + cls + '"' + attrs + ' title="' + esc(name + " — " + lab) + '" aria-label="' + esc(name + ", " + lab) + '">' + inner + '</span>';
      }
      // Fully percent-encode the path (encodeURIComponent → slashes become %2F),
      // exactly as the handbook example does. With literal slashes Glyphs misparses
      // the path and falls back to the frontmost font + active master, ignoring the
      // layer (master) we asked for. layer == master id selects the master layer.
      var href = "glyphsapp://show/?path=" + encodeURIComponent(H.filePath)
        + "&glyph=" + encodeURIComponent(name) + "&layer=" + encodeURIComponent(m.id);
      return '<a class="' + cls + '" href="' + href + '"' + attrs + ' title="' + esc(name + " — " + lab + " (open in Glyphs)") + '" aria-label="' + esc(name + ", " + lab + ", open in Glyphs") + '">' + inner + '</a>';
    }
    var sections;
    if (state.heatSort === "color"){
      // group cells by their current colour, ordered by the workflow (order[]), the
      // uncoloured bucket last; glyphs within a colour keep font order.
      var byKey = {};
      shown.forEach(function(it){
        var k = it[1];
        var kk = (k===-1 || H.order.indexOf(String(k))===-1) ? "none" : String(k);
        if (!byKey[kk]){ byKey[kk] = []; }
        byKey[kk].push(it);
      });
      var keyOrder = H.order.slice();
      keyOrder.push("none");
      sections = keyOrder.filter(function(kk){ return byKey[kk] && byKey[kk].length; }).map(function(kk){
        var key = kk==="none" ? -1 : parseInt(kk,10);
        var lab = labelFor(key);
        return '<div class="cat"><div class="cat-h">'+swatchFor(kk==="none"?null:key)+' '+esc(lab)+' <span class="cat-n">'+byKey[kk].length+'</span></div>'
          + '<div class="grid" aria-label="'+esc(lab)+'">'+byKey[kk].map(cellHTML).join("")+'</div></div>';
      }).join("");
    } else {
      // group cells by glyph category, Font-View style (the default layout).
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
    // Empty when the font has no glyphs, OR when "Recently modified" is on but nothing
    // changed since the last run (the filter emptied the grid).
    var empty = (!sections)
      ? '<p class="empty">'+(state.heatRecent ? "No glyphs changed since the last run." : "No glyphs.")+'</p>'
      : "";
    var toggle = (Object.keys(ch).length)
      ? '<span class="ba-switch" role="group" aria-label="Show cell colours before or after the picked moment">'
        + '<button type="button" class="ba-seg'+(state.before?" on":"")+'" data-ba="before" aria-pressed="'+state.before+'">Before</button>'
        + '<button type="button" class="ba-seg'+(!state.before?" on":"")+'" data-ba="after" aria-pressed="'+(!state.before)+'">After</button>'
        + '<button type="button" class="ba-play'+(state.baPlaying?" on":"")+'" data-baplay="1" aria-pressed="'+(!!state.baPlaying)+'" aria-label="Auto-switch before and after every second" title="Auto-switch before/after every second">'+(state.baPlaying?'􀊗':'􀊕')+'</button>'
        + '</span>'
      : '';
    var focusInfo = state.focus!==null
      ? '<button type="button" class="chip focus-clear" data-fclear="1" title="Clear colour focus">Focus: '+esc(labelFor(state.focus))+' ✕</button>'
      : '';
    // sort control: a segmented switch with a sliding highlight — group the grid by
    // glyph category (default) or by colour.
    var sortCtl = '<span class="segsw hsort" role="group" aria-label="Sort glyphs" style="--seg:'+(state.heatSort==="color"?1:0)+'">'
      + segHL("hsort", state.heatSort==="color"?1:0)
      + '<button type="button" data-hsort="category" aria-pressed="'+(state.heatSort!=="color")+'" title="Group glyphs by category">Category</button>'
      + '<button type="button" data-hsort="color" aria-pressed="'+(state.heatSort==="color")+'" title="Group glyphs by colour">By colour</button></span>';
    // recently-modified filter: show only glyphs touched in the last 7 days.
    // Hidden when there is nothing changed to filter to (no changeset).
    var recentCtl = Object.keys(ch).length
      ? '<button type="button" class="chip heat-recent'+(state.heatRecent?" on":"")+'" data-heatrecent="1" aria-pressed="'+(!!state.heatRecent)+'" title="Show only glyphs changed since the last run">Recently modified</button>'
      : '';
    // glyph-cell size slider: live-resizes the grid cells (drives --cell-min on the section).
    var cz = state.cellSize || 40;
    var sizeCtl = '<input type="range" class="cell-size" min="20" max="40" step="2" value="'+cz+'" data-cellsize title="Glyph cell size" aria-label="Glyph cell size">';
    // (The time-travel scrub pill above the grid was removed; the latest version node /
    // timeline already returns to the live moment, and scrubSnap still drives the cells.)
    // The category SECTIONS always lay two-up (CSS columns on .heat-cats; each .cat stays
    // whole). The wrapper lets the column rule target the sections without catching the
    // .heat-h controls.
    var body = sections ? '<div class="heat-cats">'+sections+'</div>' : empty;
    return '<section class="heat'+(scrubAnim?" scrub":"")+'" style="--cell-min:'+cz+'px"><div class="heat-h">'+focusInfo+toggle+recentCtl+sortCtl+sizeCtl+'</div>'
      + body+'</section>';
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
    return '<div class="ov-card ovc-'+esc(key)+(open?" open":"")+'">'+head
      + '<div class="ov-card-body'+(open?" scroll":"")+'">'+bodyHtml+'</div></div>';
  }
  function lbRow(r, anim, i){
    // anim (first paint only) grows each bar 0->width with a small per-row cascade.
    var fillCls = "lb-fill" + (anim ? " intro" : "");
    var fillStyle = "width:" + r.p + "%" + (anim ? ";--i:" + i : "");
    return '<button type="button" class="lb-row" data-m="'+esc(r.id)+'" title="Focus '+esc(r.name)+'">'
      + '<span class="lb-n">'+esc(r.name)+'</span>'
      + '<span class="lb-bar"><span class="'+fillCls+'" style="'+fillStyle+'"></span></span>'
      + '<span class="lb-p">'+r.p+'%</span></button>';
  }
  // Ranked masters by graded step progress; click a row to focus that master.
  // Collapsed shows the top 10; expanded scrolls through every master.
  function leaderboard(){
    var rows = H.masters.map(function(m){ return {id:m.id, name:m.name, p:masterPct(m), any:masterStarted(m)}; });
    rows.sort(function(a,b){ return b.p-a.p || (a.name<b.name?-1:1); });
    // Always show every master, fully expanded — no scroll, no "Show all" toggle.
    var bars = rows.map(function(r, i){ return lbRow(r, barsAnim, i); }).join("");
    return ovCard("leaderboard", "Furthest along", bars, false);
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
  // The activity calendar (heatmap / standard month grid) lives on the Overview, as a
  // full-width card. Clicking a day still scrubs the Time Machine (jumping to the
  // Timeline tab if it isn't on screen — see the data-calday handler).
  function calendarCard(){
    if (!hasTrend()) return "";
    return '<div class="ov-card ovc-calendar">'+activityCalendar()+'</div>';
  }
  // ----- Colour-spread radar (shown in the focused-master panel) -------------
  // The selected master's glyph spread across the colour-step axes, scaled to that
  // master's busiest step so the shape fills the chart. Only the selected master.
  var CFD_TAU = Math.PI * 2, CFD_TOP = -Math.PI / 2;
  function polarXY(cx, cy, r, ang){ return [cx + r*Math.cos(ang), cy + r*Math.sin(ang)]; }
  function shortLab(s){ s = ""+s; return s.length > 9 ? s.slice(0,8)+"…" : s; }
  function radarCard(){
    var steps = H.steps || [];
    if (steps.length < 3 || H.masters.length < 1) return "";
    // only the selected master (this card lives in its panel); fall back to the first.
    var mi = 0; for (var x=0;x<H.masters.length;x++){ if (H.masters[x].id===state.master){ mi=x; break; } }
    var m = H.masters[mi];
    var cx=100, cy=100, R=64, N=steps.length, maxVal=1, g, k, a, p;
    var exm = exclusiveOf(m);   // a spread = where glyphs ACTUALLY sit now (exclusive), not cumulative
    steps.forEach(function(s){ var v=exm[String(s.key)]||0; if (v>maxVal) maxVal=v; });   // scale to this master
    var grid="", spokes="", axt="";
    for (g=1; g<=3; g++){
      var pts=[]; for (k=0;k<N;k++){ a=CFD_TOP+k/N*CFD_TAU; p=polarXY(cx,cy,R*g/3,a); pts.push(p[0].toFixed(1)+","+p[1].toFixed(1)); }
      grid += '<polygon class="rdr-grid" points="'+pts.join(" ")+'"/>';
    }
    for (k=0;k<N;k++){
      a=CFD_TOP+k/N*CFD_TAU; var pe=polarXY(cx,cy,R,a), pa=polarXY(cx,cy,R+12,a);
      spokes += '<line class="rdr-spoke" x1="'+cx+'" y1="'+cy+'" x2="'+pe[0].toFixed(1)+'" y2="'+pe[1].toFixed(1)+'"/>';
      var anchor = Math.abs(pa[0]-cx)<4 ? "middle" : (pa[0]<cx ? "end" : "start");
      axt += '<text class="rdr-axt" x="'+pa[0].toFixed(1)+'" y="'+(pa[1]+3).toFixed(1)+'" text-anchor="'+anchor+'">'+esc(shortLab(steps[k].label))+'</text>';
    }
    var pp=[]; for (var j=0;j<N;j++){ var an=CFD_TOP+j/N*CFD_TAU; var r=R*(exm[String(steps[j].key)]||0)/maxVal; var xy=polarXY(cx,cy,r,an); pp.push(xy[0].toFixed(1)+","+xy[1].toFixed(1)); }
    var col="hsl("+masterHue(mi)+",70%,58%)";
    var poly='<polygon class="rdr-poly" points="'+pp.join(" ")+'" style="fill:'+col+';stroke:'+col+'"><title>'+esc(m.name)+'</title></polygon>';
    // viewBox padded horizontally so the axis labels at the left/right tips aren't clipped.
    var svg = '<svg class="ovz" viewBox="-26 0 252 200" role="img" aria-label="'+esc(m.name+" colour spread")+'">'+grid+spokes+poly+axt+'</svg>';
    return ovCard("radar", "Colour spread by master", '<div class="ovz-wrap">'+svg+'</div>', false);
  }
  // "Focus of the week" tally: how many glyphs moved TO each visible colour since the
  // week-ago snapshot, across all masters. Needs a stateAt reconstruction per master,
  // so it's cached like NAVCACHE/PMCACHE (key = the active timeline dataset, entries
  // per compared snapshot date) — the Overview re-renders on every click and must not
  // pay the full-history walk again.
  var WKCACHE = {}, WKCACHE_KEY = "";
  function weekColorMoves(weekAgo){
    var key = tlDatasetKey();
    if (WKCACHE_KEY !== key){ WKCACHE = {}; WKCACHE_KEY = key; }
    if (WKCACHE[weekAgo]) return WKCACHE[weekAgo];
    var colorMoves = {}, names = H.glyphNames || [];
    H.masters.forEach(function(m){
      var snap = stateAt(m.id, weekAgo), ks = m.keys || [];
      for (var i=0;i<names.length;i++){
        if (!isCounted(names[i])) continue;
        var nowK = (ks[i] != null) ? ks[i] : -1, thenK = (snap[names[i]] != null) ? snap[names[i]] : -1;
        // a glyph moved TO a visible colour this week -> tally it for "focus of the week"
        if (String(nowK) !== String(thenK) && nowK !== -1 && H.order.indexOf(String(nowK)) !== -1){
          colorMoves[String(nowK)] = (colorMoves[String(nowK)] || 0) + 1;
        }
      }
    });
    return (WKCACHE[weekAgo] = colorMoves);
  }
  // Overview "This week" card: graded completion change over the last 7 days + how many
  // glyph layers advanced a step. Hidden until there's a snapshot >=7 days back.
  function weekProgressCard(){
    var dates = (H.trend && H.trend.dates) || [];
    if (dates.length < 2) return "";
    var latest = dates[dates.length-1], weekAgo = snapDate(dates, isoMinusDays(latest, 7));
    if (weekAgo === latest) return "";
    var nowPct = gradedOverallPct(), thenPct = gradedOverallPctAt(weekAgo), delta = nowPct - thenPct;
    var monthAgo = snapDate(dates, isoMinusDays(latest, 30)), monthDelta = nowPct - gradedOverallPctAt(monthAgo);
    function wkStat(d, lab){ var a = rankArrow(d); return '<span class="wk-stat"><span class="wk-delta '+a.c+'">'+a.g+' '+(d>0?"+":"")+d+'%</span><span class="wk-sub">'+lab+'</span></span>'; }
    var gains = [], colorMoves = weekColorMoves(weekAgo);
    H.masters.forEach(function(m){
      gains.push({ m:m, d:Math.round(gradedMasterPct(m) - gradedPctAt(m.id, weekAgo)) });   // weekly gain
    });
    // top 3 most-improved masters (positive weekly gain), and the top 3 colours that gained
    // the most glyphs this week.
    var topMasters = gains.filter(function(x){ return x.d > 0; })
      .sort(function(a,b){ return b.d - a.d || (a.m.name < b.m.name ? -1 : 1); }).slice(0, 3);
    var moveTotal = Object.keys(colorMoves).reduce(function(s,k){ return s + colorMoves[k]; }, 0);
    var topColors = Object.keys(colorMoves).map(function(k){ return { k:parseInt(k,10), n:colorMoves[k] }; })
      .sort(function(a,b){ return b.n - a.n || a.k - b.k; }).slice(0, 3);
    var mList = topMasters.map(function(g){ return '<li>'+esc(g.m.name)+'<b>+'+g.d+'%</b></li>'; }).join("");
    var cList = topColors.map(function(f){ var pc = moveTotal ? Math.round(f.n / moveTotal * 100) : 0; return '<li><i class="wk-sw" style="background:var('+varFor(f.k)+')"></i>'+esc(labelFor(f.k))+'<b>+'+f.n+'<span class="wk-pct">(+'+pc+'%)</span></b></li>'; }).join("");
    var bestBlock = mList ? '<div class="wk-row"><span class="wk-k">Most improved masters</span><ol class="wk-list">'+mList+'</ol></div>' : '';
    var focusBlock = cList ? '<div class="wk-row"><span class="wk-k">Focus of the week</span><ol class="wk-list">'+cList+'</ol></div>' : '';
    var extra = (bestBlock || focusBlock) ? '<div class="wk-extra">'+bestBlock+focusBlock+'</div>' : '';
    var monthStat = (monthAgo !== latest) ? wkStat(monthDelta, "past 30 days") : "";
    var body = '<div class="wk-head">'+wkStat(delta, "past 7 days")+monthStat+'</div>'
      + extra;
    return ovCard("week", "This week", body, false);
  }
  function overviewExtras(){
    if (!H.masters.length) return "";
    // This-week progress + the "Furthest along" leaderboard. (Histogram removed; the
    // activity calendar moved to the Timeline tab.)
    return '<div class="ov-extra">'+weekProgressCard()+leaderboard()+'</div>';
  }
  // Recent activity is the per-master change feed (all moves, history-aware), so it
  // belongs with the selected master, not the global Overview. The old last-save
  // regression card is gone; backward moves are no longer surfaced on the chart.
  // The colour-spread radar joins Recent — it reads against the focused master.
  function masterExtras(){
    var cards = recentCard();
    var body = cards ? '<div class="ov-extra">'+cards+'</div>' : "";
    var radar = radarCard();
    if (radar){
      var vizIntro = !vizIntroPlayed; vizIntroPlayed = true;   // animate once, not on every master switch
      body += '<div class="ov-viz'+(vizIntro?" intro":"")+'">'+radar+'</div>';
    }
    return body;
  }
  function tabsView(){
    if (state.master==null) return overall()+overviewExtras();   // no master selected -> global view + extras
    var m = masterById(state.master);
    return '<div class="panel" role="tabpanel">'+versionCard()+masterOverall(m)+categoryCoverageCard()+scriptCoverageCard()+heatmap(m)+'</div>';
  }
  function covStacked(r){
    // a left-aligned stacked bar of the colours actually set in this group; no inline
    // text — each segment's colour label + share show in a hover tooltip instead.
    var dist = r.dist || {};
    function seg(w, bg, cls, title){
      return '<span'+(cls?' class="'+cls+'"':'')+' style="width:'+w+'%;background:'+bg
        +';box-shadow:0 0 9px color-mix(in srgb,'+bg+' 22%,transparent)" title="'+title+'"></span>';
    }
    var segs = H.order.map(function(k){
      var c = dist[k] || 0;
      if (!c) return "";
      var w = r.total ? (c/r.total*100) : 0;
      return seg(w, 'var(--c'+k+')', '', esc(labelFor(parseInt(k,10))+" — "+Math.round(w)+"%"));
    }).join("");
    var uncolored = r.uncolored || 0;
    if (uncolored){ var wu = r.total ? uncolored/r.total*100 : 0;
      segs += seg(wu, 'var(--c-none)', 'cov-none', esc(H.noneLabel+" — "+Math.round(wu)+"%")); }
    return '<div class="cov-bar'+(scrubAnim?" scrub":"")+'" role="img" aria-label="'+esc(r.key+": colour distribution")+'">'+segs+'</div>';
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
  // Coverage rows for the active scope. Focused master -> that master's rows. Global
  // (no master) -> every master MERGED into font-wide rows: per-colour dist / total /
  // uncoloured summed across the family, so the bar reads across all master-glyph slots
  // instead of silently showing only the first master. `glyphs` keeps the real per-group
  // glyph count (same for every master) so the displayed count isn't multiplied.
  // Coverage rows with the non-exporting exclusion applied: rebuilt client-side
  // from the raw m.keys + the parallel H.categories / H.scripts arrays (the
  // shipped H.coverage rows are the all-glyphs truth). Mirrors _coverage_for's
  // row shape ({key,total,uncolored,dist,glyphs}) and largest-group-first order.
  function covRowsCounted(which){
    var attrs = which === "byScript" ? (H.scripts||[]) : (H.categories||[]);
    var names = H.glyphNames||[], set = countedSet();
    var masters = state.master != null ? [masterById(state.master)] : H.masters;
    var groupIdx = {}, gkeys = [];
    for (var i=0;i<names.length;i++){
      if (set && !set[names[i]]) continue;
      var g = attrs[i] || "Other";
      if (!groupIdx[g]){ groupIdx[g] = []; gkeys.push(g); }
      groupIdx[g].push(i);
    }
    var out = gkeys.map(function(gk){
      var idxs = groupIdx[gk], total = 0, uncolored = 0, dist = {};
      masters.forEach(function(m){
        var ks = m.keys||[];
        for (var j=0;j<idxs.length;j++){
          var k = ks[idxs[j]], sk = String(k);
          total++;
          if (k===-1 || H.order.indexOf(sk)===-1) uncolored++; else dist[sk]=(dist[sk]||0)+1;
        }
      });
      return { key:gk, total:total, uncolored:uncolored, glyphs:idxs.length, dist:dist };
    });
    out.sort(function(a,b){ return (b.glyphs - a.glyphs) || (a.key < b.key ? -1 : 1); });
    return out;
  }
  function covRows(which){
    if (countedSet()) return covRowsCounted(which);   // non-exporting glyphs present: recompute without them
    var by = (H.coverage && H.coverage[which]) || {};
    if (state.master != null) return by[state.master] || [];
    var merged = {}, orderKeys = [];
    H.masters.forEach(function(m){
      (by[m.id] || []).forEach(function(r){
        var agg = merged[r.key];
        if (!agg){ agg = merged[r.key] = {key:r.key, total:0, uncolored:0, glyphs:r.total||0, dist:{}}; orderKeys.push(r.key); }
        agg.total += r.total||0; agg.uncolored += r.uncolored||0;
        var dd = r.dist || {}; for (var k in dd){ agg.dist[k] = (agg.dist[k]||0) + dd[k]; }
      });
    });
    return orderKeys.map(function(k){ return merged[k]; });
  }
  // Rows for the script grid: the active scope's per-script coverage (covRows).
  function scriptRows(){ return covRows("byScript"); }
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
      var m = meta[r.key] || {}, rawName = m.name || prettyScript(r.key), dist = r.dist || {}, parts = [], k;
      var name = rawName ? rawName.charAt(0).toUpperCase() + rawName.slice(1) : rawName;   // always capitalise
      var count = (r.glyphs != null ? r.glyphs : r.total);
      for (k in dist){ if (dist[k]) parts.push(k+":"+dist[k]); }
      return '<div class="scard" data-dist="'+esc(parts.join(","))+'" data-total="'+r.total
        + '" data-uncol="'+(r.uncolored||0)+'" title="'+esc(name+" — "+count+" glyphs")+'">'
        + '<canvas class="scard-fill" width="320" height="320" aria-hidden="true"></canvas>'
        + '<div class="scard-in"><span class="scard-name">'+esc(name)+'</span>'
        + scriptGlyphSVG(m) + '<span class="scard-ct">'+count+'</span></div></div>';
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
      if (CTX_FILTER_OK){
        ctx.filter="blur("+Math.round(Math.max(W,Ht)*0.085)+"px) saturate(1.2)"; ctx.drawImage(off,0,0); ctx.filter="none";
      } else { cssSafeBlur(off, ctx, Math.max(W,Ht), Math.round(Math.max(W,Ht)*0.085)); }
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
  // The "Colours set by category" rows for the active scope (shared by the Coverage tab
  // and, when a master is focused, the Overview under its progress bar).
  function categoryCoverageBody(){
    var catRows = covRows("byCategory");
    if (!catRows.length) return '<p class="empty">No glyphs.</p>';
    return catRows.map(function(r){
      var count = (r.glyphs != null ? r.glyphs : r.total);
      return '<div class="cov-row"><span class="cov-name" title="'+esc(r.key)+'">'+esc(r.key)+'</span>'
        + covStacked(r) + '<span class="num">'+count+'</span></div>';
    }).join("");
  }
  // Two-column version surfaced in the focused-master Overview, just under the bar.
  function categoryCoverageCard(){
    // Heading removed — the category rows are self-evident under the bar.
    return '<div class="ov-catcov">'
      + '<div class="cov-rows cov-grid2">'+categoryCoverageBody()+'</div></div>';
  }
  // The "Colours set by script" grid for the focused master, surfaced in the Overview
  // under the category card (only when the family has more than one script).
  function scriptCoverageCard(){
    var scripts = scriptRows().filter(function(r){ return r.key !== "Other"; });
    if (scripts.length <= 1) return "";
    return '<div class="ov-catcov"><div class="cov-h"><span class="cov-title">Colours set by script</span></div>'+scriptGrid()+'</div>';
  }
  // ----- Timeline: completion over time, one line per master -----
  function masterHue(i){ return Math.round((i*137.508) % 360); }
  // ISO date "YYYY-MM-DD" -> short "D Mon" axis label (e.g. "7 Jun"). UTC-parsed
  // so the day never drifts across the local timezone boundary.
  var CFD_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  function dateLabel(iso){
    // commit-granularity keys carry a time (YYYY-MM-DDTHH:MM:SS[.n]) -> "5 Jun 14:30";
    // per-day keys are date-only -> "5 Jun".
    if (typeof iso === "string" && iso.indexOf("T") > 0){
      var dt = new Date(iso.slice(0, 19) + "Z");
      if (isNaN(dt.getTime())) return iso.slice(0, 16);
      var hh = ("0" + dt.getUTCHours()).slice(-2), mm = ("0" + dt.getUTCMinutes()).slice(-2);
      return dt.getUTCDate() + " " + CFD_MONTHS[dt.getUTCMonth()] + " " + hh + ":" + mm;
    }
    var d = new Date(iso + "T00:00:00Z");
    if (isNaN(d.getTime())) return iso;
    return d.getUTCDate() + " " + CFD_MONTHS[d.getUTCMonth()];
  }
  // Axis tick label honouring the active Time bucket: Days -> "5 Jun", Months -> "Jun 26",
  // Hours/Save -> the full "5 Jun 14:30". Keeps the axis legible per grouping.
  function tickLabel(iso){
    if (state.tlGran === "time"){
      if (state.tlBucket === "month"){
        var s = String(iso), year = +s.slice(0,4), mo = +s.slice(5,7) - 1;
        if (mo >= 0 && mo < 12){ return CFD_MONTHS[mo] + (isNaN(year) ? "" : " " + String(year).slice(2)); }
        return s.slice(0,7);
      }
      if (state.tlBucket === "day"){ return dateLabel(String(iso).slice(0,10)); }
    }
    return dateLabel(iso);
  }
  // ----- #7 shared calendar X axis -------------------------------------------
  // Builds the plot geometry + X scale and the calendar layers (zebra ISO-week
  // bands, thinned date tick labels, dashed "today" rule) that both the line chart
  // (trendParts) and the streamgraph (streamParts) draw, so the X axis stays
  // identical between the Line and Flow modes. Y(pct) maps a 0-100 % onto the plot.
  // ----- Range navigator (CMC-style) -----------------------------------------
  // A full-history mini-chart with a draggable window that ZOOMS the main trend chart
  // to a focus date range. The window is two snapshot indices (state.viewLo/viewHi;
  // null = full range). Only the Timeline tab's chart is windowed (the Overview card
  // stays full-range), so trendSeries() gates on the active view.
  function fullSeries(){ return (H.trend && H.trend.series) || []; }
  function isZoomed(){ return state.viewLo != null || state.viewHi != null; }
  function viewBounds(){
    var n = fullSeries().length;
    if (n === 0){ return [0, -1]; }
    var lo = state.viewLo == null ? 0 : state.viewLo;
    var hi = state.viewHi == null ? n - 1 : state.viewHi;
    lo = Math.max(0, Math.min(lo, n - 1));
    hi = Math.max(0, Math.min(hi, n - 1));
    if (lo > hi){ var t = lo; lo = hi; hi = t; }
    if (hi - lo < 1){                          // keep >=2 points so a line can draw
      if (hi < n - 1){ hi = lo + 1; } else { lo = hi - 1; }
    }
    return [lo, hi];
  }
  function trendSeries(){
    var s = fullSeries();
    if (state.view !== "timeline" || !isZoomed()){ return s; }
    var b = viewBounds(); return s.slice(b[0], b[1] + 1);
  }
  function calendarAxis(W, Ht){
    var series = trendSeries();
    var pl=30, pr=12, ptop=12, pb=16, iw=W-pl-pr, ih=Ht-ptop-pb;
    // Both Time and Save modes space snapshots EVENLY (one equal slot each) so bunched-
    // in-time saves don't cluster at the left. dayOff() returns the snapshot index.
    var even = true;
    var t0 = new Date(series[0].date).getTime();
    var idxByDate = {}; series.forEach(function(p, i){ idxByDate[p.date] = i; });
    function dayOff(d){ return even ? (idxByDate[d] != null ? idxByDate[d] : 0)
                                    : (new Date(d).getTime() - t0)/86400000; }
    var lastOff = even ? Math.max(1, series.length - 1) : dayOff(series[series.length-1].date);
    if (!(lastOff > 0)){ lastOff = 1; }
    function X(o){ return pl + o/lastOff*iw; }
    function Y(p){ return ptop + ih - p/100*ih; }
    var weekBands = "";   // even spacing has no real time axis -> no calendar week bands
    // thin the tick labels so they never collide on long spans: aim for ~6 ticks,
    // stepping whole snapshots so every label sits on a real data X.
    var tickStep = Math.max(1, Math.ceil(series.length / 6));
    var xticks = "";
    series.forEach(function(p, idx){
      if (idx % tickStep !== 0 && idx !== series.length - 1){ return; }
      var tx = X(dayOff(p.date));
      var anchor = idx === 0 ? "start" : (idx === series.length - 1 ? "end" : "middle");
      xticks += '<text class="tl-xtick" x="'+tx.toFixed(1)+'" y="'+(ptop+ih+pb).toFixed(1)+'" text-anchor="'+anchor+'">'+esc(tickLabel(p.date))+'</text>';
    });
    var todayRule = "";   // the always-on "today" line + date bubble were removed
    // snapshot X anchors in SVG user-space — crosshair + brush snap to these.
    var snaps = series.map(function(p){ return { x:+X(dayOff(p.date)).toFixed(1), d:p.date }; });
    // Faint light-gray vertical rule at every savepoint/save-or-day snapshot, so each
    // data point reads as its own column behind the line.
    var colBars = snaps.map(function(s){
      return '<line class="tl-vgrid" x1="'+s.x+'" y1="'+ptop+'" x2="'+s.x+'" y2="'+(ptop+ih).toFixed(1)+'"/>';
    }).join("");
    // Persistent marker at the clicked/scrubbed snapshot (state.tlScrub is a FULL-series
    // index; map it into the possibly-windowed series). Lets a click on the chart show
    // which moment is selected (the colour disc reads the same index).
    var scrubRule = "";
    if (state.tlScrub != null){
      var swi = state.tlScrub - viewBounds()[0];
      if (swi >= 0 && swi < series.length && series[swi]){
        var srx = X(dayOff(series[swi].date));
        scrubRule = '<line class="tl-scrubline" x1="'+srx.toFixed(1)+'" y1="'+ptop+'" x2="'+srx.toFixed(1)+'" y2="'+(ptop+ih).toFixed(1)+'"/>'
          + '<circle class="tl-scrubdot" cx="'+srx.toFixed(1)+'" cy="'+(ptop+ih).toFixed(1)+'" r="3.5"/>';
      }
    }
    return { series:series, pl:pl, pr:pr, ptop:ptop, pb:pb, iw:iw, ih:ih,
             dayOff:dayOff, lastOff:lastOff, X:X, Y:Y,
             weekBands:weekBands, xticks:xticks, todayRule:todayRule, snaps:snaps, scrubRule:scrubRule };
  }
  // Shared trend builder: returns the chart SVG, the per-master legend and the
  // date foot, so both the Timeline view and the Overview card draw the same.
  // Gentle MONOTONE smoothing through pts ([{x,y},...]): a cubic path whose control-point
  // tangents are clamped (zero at local extrema) so the curve never overshoots a real data
  // value. Shared by every progress line (each master, the colour-mode top line, the
  // navigator) so all graphs are smooth, not just the focused one.
  function smoothPath(ps){
    if (ps.length < 2){ return ps.length ? "M"+ps[0].x.toFixed(1)+" "+ps[0].y.toFixed(1) : ""; }
    var slopes = [];
    for (var s = 0; s < ps.length - 1; s++){
      var dx = ps[s+1].x - ps[s].x;
      slopes.push(dx ? (ps[s+1].y - ps[s].y) / dx : 0);
    }
    var tang = [slopes[0]];
    for (var k = 1; k < ps.length - 1; k++){
      var a = slopes[k-1], b = slopes[k];
      tang.push(a*b <= 0 ? 0 : (a + b) / 2);                 // zero tangent at extrema -> no overshoot
    }
    tang.push(slopes[slopes.length-1]);
    var d = "M"+ps[0].x.toFixed(1)+" "+ps[0].y.toFixed(1);
    for (var j = 0; j < ps.length - 1; j++){
      var hx = (ps[j+1].x - ps[j].x) / 3;                    // 1/3-span control handles
      var c1x = ps[j].x + hx,   c1y = ps[j].y + tang[j]*hx;
      var c2x = ps[j+1].x - hx, c2y = ps[j+1].y - tang[j+1]*hx;
      d += " C"+c1x.toFixed(1)+" "+c1y.toFixed(1)+" "+c2x.toFixed(1)+" "+c2y.toFixed(1)+" "+ps[j+1].x.toFixed(1)+" "+ps[j+1].y.toFixed(1);
    }
    return d;
  }
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
    var defs = "", lines = "", selLine = "", legend = "";
    H.masters.forEach(function(m, i){
      // Colours OFF -> the line is neutral gray (turn Colours on for the per-colour
      // breakdown). The focused master reads brighter; the rest sit at muted gray.
      var col = (state.master != null && m.id === state.master) ? "var(--text)" : "var(--muted)";
      var pts = series.map(function(p){
        var mp = p.masters[m.id]; if (!mp) return null;
        var c = gradedPctAt(m.id, p.date);          // graded completion (matches the ring), not final-step-only
        return { x:X(dayOff(p.date)), y:Y(c), pc:c, date:p.date };
      }).filter(Boolean);
      if (!pts.length) return;
      var dim = state.master!=null && m.id!==state.master;   // a master is selected, not this one
      var sel = state.master!=null && m.id===state.master;
      var smooth = smoothPath(pts);                          // every line is smooth, not just the focused one
      var dots = pts.map(function(o){ return '<circle class="tl-dot'+(dim?" tl-dim":"")+'" cx="'+o.x.toFixed(1)+'" cy="'+o.y.toFixed(1)+'" r="'+(sel?2.2:1.8)+'" fill="var(--tl-dot)"><title>'+esc(m.name+" · "+o.date+" · "+Math.round(o.pc)+"%")+'</title></circle>'; }).join("");
      if (sel){
        // #10 hero area: gentle smoothed line + a soft gradient fill that closes
        // down to the baseline Y(0). Dots above stay at exact values (honest).
        var gradId = "tl-area-grad-"+i;
        var topY = ptop, botY = Y(0);
        defs += '<linearGradient id="'+gradId+'" x1="0" y1="'+topY+'" x2="0" y2="'+botY.toFixed(1)+'" gradientUnits="userSpaceOnUse">'
          + '<stop offset="0" stop-color="var(--text)" stop-opacity="0.16"/>'
          + '<stop offset="1" stop-color="var(--text)" stop-opacity="0"/>'
          + '</linearGradient>';
        var area = smooth + " L"+pts[pts.length-1].x.toFixed(1)+" "+botY.toFixed(1)
          + " L"+pts[0].x.toFixed(1)+" "+botY.toFixed(1) + " Z";
        var line = '<path class="tl-line tl-sel" pathLength="1" d="'+smooth+'" stroke="'+col+'"/>';
        selLine += '<path class="tl-area" d="'+area+'" fill="url(#'+gradId+')"/>' + line + dots;
      } else {
        lines += '<path class="tl-line'+(dim?" tl-dim":"")+'" pathLength="1" d="'+smooth+'" stroke="'+col+'"/>'+dots;
      }
      legend += '<span class="tl-lg'+(dim?" tl-dim":"")+(sel?" tl-sel":"")+'"><i style="background:'+col+'"></i>'+esc(m.name)+' '+Math.round(pts[pts.length-1].pc)+'%</span>';
    });
    lines += selLine;                                        // keep the selected master (area+line) on top
    // data-snaps carries each snapshot's X anchor so chartClick maps a click to the
    // nearest moment; a transparent rect over the plot guarantees clicks register on
    // empty space between lines too. No hover crosshair / read-out popover.
    var snaps = ax.snaps;
    var crossData = ' data-snaps="'+esc(JSON.stringify(snaps))+'" data-topy="'+ptop+'" data-boty="'+Y(0).toFixed(1)+'"';
    var hitLayer = '<rect class="tl-crossarea" x="'+pl+'" y="'+ptop+'" width="'+iw.toFixed(1)+'" height="'+ih.toFixed(1)+'"/>';
    var chart = '<svg class="tl-chart'+(tlChartShouldAnim?" tl-anim":"")+'" viewBox="0 0 '+W+' '+Ht+'" role="img" tabindex="0"'+crossData+' aria-label="Completion over time per master. Click a point to pick that moment; left and right arrow keys step the picked moment.">'+(defs?'<defs>'+defs+'</defs>':'')+weekBands+ax.colBars+grid+xticks+lines+ax.scrubRule+hitLayer+'</svg>';
    return { chart:chart, legend:legend, foot:"" };   // the start/end date row moved to the navigator's ticks
  }
  // ----- Global Timeline: median completion + min-max spread band -----------------
  // One bold median line + a soft band spanning the slowest-to-fastest master at each date.
  // Stays readable at ANY master count (replaces the per-master line spaghetti). Same SVG
  // scaffold + data-snaps as trendParts, so click-to-scrub works for free.
  function trendBandParts(W, Ht){
    var ax = calendarAxis(W, Ht);
    var pl = ax.pl, pr = ax.pr, ptop = ax.ptop, ih = ax.ih, iw = ax.iw;
    var dayOff = ax.dayOff, X = ax.X, Y = ax.Y;
    var grid = [0,25,50,75,100].map(function(g){
      var y = Y(g).toFixed(1);
      return '<line class="tl-grid" x1="'+pl+'" y1="'+y+'" x2="'+(W-pr)+'" y2="'+y+'"/>'
        + '<text class="tl-axis" x="'+(pl-5)+'" y="'+(parseFloat(y)+3).toFixed(1)+'" text-anchor="end">'+g+'</text>';
    }).join("");
    var pm = pctMatrix();
    var up = [], lo = [], md = [];
    for (var j = 0; j < pm.dates.length; j++){
      var col = []; for (var i = 0; i < pm.M.length; i++){ col.push(pm.M[i][j]); }
      col.sort(function(a, b){ return a - b; });
      var mn = col.length ? col[0] : 0, mx = col.length ? col[col.length-1] : 0;
      var mid = !col.length ? 0 : (col.length % 2 ? col[(col.length-1)/2] : (col[col.length/2-1] + col[col.length/2]) / 2);
      var x = X(dayOff(pm.dates[j]));
      up.push({ x:x, y:Y(mx) }); lo.push({ x:x, y:Y(mn) });
      md.push({ x:x, y:Y(mid), pc:mid, mn:mn, mx:mx, date:pm.dates[j] });
    }
    var fill = smoothPath(up) + smoothPath(lo.slice().reverse()).replace(/^M/, "L") + "Z";
    var medLine = '<path class="tl-spread-med" pathLength="1" d="'+smoothPath(md)+'"/>';
    var dots = md.map(function(o){
      return '<circle class="tl-spread-dot" cx="'+o.x.toFixed(1)+'" cy="'+o.y.toFixed(1)+'" r="2"><title>'
        + esc("Median "+Math.round(o.pc)+"% \u00b7 range "+Math.round(o.mn)+"\u2013"+Math.round(o.mx)+"% \u00b7 "+o.date)+'</title></circle>';
    }).join("");
    var snaps = ax.snaps;
    var crossData = ' data-snaps="'+esc(JSON.stringify(snaps))+'" data-topy="'+ptop+'" data-boty="'+Y(0).toFixed(1)+'"';
    var hitLayer = '<rect class="tl-crossarea" x="'+pl+'" y="'+ptop+'" width="'+iw.toFixed(1)+'" height="'+ih.toFixed(1)+'"/>';
    // Caption moved into the (i) tooltip at the card's top-right (tlGraphInfo).
    var chart = '<svg class="tl-chart'+(tlChartShouldAnim?" tl-anim":"")+'" viewBox="0 0 '+W+' '+Ht+'" role="img" tabindex="0"'+crossData
      + ' aria-label="Family completion over time: median line with the min to max spread across all masters. Click a point to pick that moment.">'
      + ax.weekBands + ax.colBars + grid + ax.xticks
      + '<path class="tl-spread-fill" d="'+fill+'"/>' + medLine + dots + ax.scrubRule + hitLayer + '</svg>';
    return { chart:chart, legend:"", foot:"" };
  }
  function streamParts(W, Ht){
    var ax = calendarAxis(W, Ht);
    var pl = ax.pl, ptop = ax.ptop, ih = ax.ih, iw = ax.iw;
    var dayOff = ax.dayOff, X = ax.X, Y = ax.Y;
    var order = H.order || [];
    // Scope: the focused master, else the AGGREGATE across all masters (the overall view).
    // Tally over the (possibly zoom-windowed) axis dates so the bands line up with the X.
    var scopeIds = state.master != null ? [state.master] : H.masters.map(function(m){ return m.id; });
    var tally = ax.series.map(function(p){
      var byKey = {}; order.forEach(function(k){ byKey[k] = 0; }); var none = 0;
      scopeIds.forEach(function(mid){
        var t = colTally(mid, p.date);             // memoised per master|date
        order.forEach(function(k){ byKey[k] += t.byKey[k]; });
        none += t.none;
      });
      return { date:p.date, byKey:byKey, none:none };
    });
    // Weighted decomposition of the graded completion %: each band's height is that
    // colour's WEIGHTED contribution (step weight x count / total). So the stack TOP
    // traces the same graded % as the Line, and the empty space above (up to 100%) is
    // the work remaining. denom = the scope's whole total (the graded-% denominator,
    // exclusion-aware via countedTotal).
    var WT = stepWeights().weight;
    var denom = scopeIds.length * (countedTotal() || 1) || 1;
    var grid = [0,25,50,75,100].map(function(g){
      var y = Y(g).toFixed(1);
      return '<line class="tl-grid" x1="'+pl+'" y1="'+y+'" x2="'+(W-ax.pr)+'" y2="'+y+'"/>'
        + '<text class="tl-axis" x="'+(pl-5)+'" y="'+(parseFloat(y)+3).toFixed(1)+'" text-anchor="end">'+g+'</text>';
    }).join("");
    // Flowing (smooth-curved) bands at lower opacity — no blur/saturate filter.
    var defs = "";
    // build a stacked Y for every date: running cumulative weighted-% from the baseline
    // up. bands stack bottom->top by H.order; no uncoloured band (it has zero weight, so
    // it lives in the empty space above the stack).
    var nPts = tally.length;
    function bandPct(k, c){ return (WT[k] || 0) * c / denom * 100; }
    // Band edges use the SAME smoothing as the lines (smoothPath), so the top band's
    // upper edge exactly coincides with the graded top line drawn over it.
    function bandPath(lowerVals, upperVals){
      var up = tally.map(function(t, i){ return { x:X(dayOff(t.date)), y:Y(upperVals[i]) }; });
      var lo = tally.map(function(t, i){ return { x:X(dayOff(t.date)), y:Y(lowerVals[i]) }; }).reverse();
      return smoothPath(up) + smoothPath(lo).replace(/^M/, "L") + "Z";
    }
    var bandKeys = order.slice();                          // bottom -> top by palette order
    var bands = "";
    var bandTops = "";                                     // top-edge strokes, drawn over every fill
    // cumulative top of the stack at each date, seeded at 0 (baseline = Y(0)).
    var cum = tally.map(function(){ return 0; });
    bandKeys.forEach(function(k){
      var lower = cum.slice();
      var upper = tally.map(function(t, i){ return cum[i] + bandPct(k, t.byKey[k] || 0); });
      for (var i = 0; i < nPts; i++){ cum[i] = upper[i]; }
      // skip an all-zero band so empty steps add no markup on sparse history.
      var any = upper.some(function(v, i){ return v - lower[i] > 0.0001; });
      if (!any){ return; }
      bands += '<path class="tl-band" d="'+bandPath(lower, upper)+'" fill="var('+varFor(k)+')"><title>'+esc(labelFor(k))+'</title></path>';
      // Trace the band's TOP edge in its own colour at higher opacity so each softened layer
      // still reads as a defined curve. Same smoothing as the fill's upper edge.
      var upPts = tally.map(function(t, i){ return { x:X(dayOff(t.date)), y:Y(upper[i]) }; });
      bandTops += '<path class="tl-band-top" d="'+smoothPath(upPts)+'" stroke="var('+varFor(k)+')"/>';
    });
    var bandGroup = bands + bandTops;                      // strokes layer above all fills
    // The graded line traced along the stack TOP (the same curve as the colour-less Line
    // view) + dots, labelled by scope ("Overall" when aggregating, else the master name).
    var scopeName = "Overall";
    if (state.master != null){
      var sm = H.masters.filter(function(x){ return x.id === state.master; })[0];
      scopeName = sm ? sm.name : "";
    }
    var topPts = tally.map(function(t, i){ return { x:X(dayOff(t.date)), y:Y(cum[i]) }; });
    // No accent top-line in focus mode: the coloured band stack already traces the
    // completion curve. Keep small dots as clickable per-snapshot moment markers.
    var topDots = topPts.map(function(o, i){
      return '<circle class="tl-dot" cx="'+o.x.toFixed(1)+'" cy="'+o.y.toFixed(1)+'" r="1.8" fill="var(--tl-dot)">'
        + '<title>'+esc(scopeName+" · "+tally[i].date+" · "+Math.round(cum[i])+"%")+'</title></circle>';
    }).join("");
    bandGroup += topDots;
    // crosshair overlay shares the #7 data-snaps + the per-date counts so the
    // read-out (streamReadout) can show each step's count at the snapped date.
    var snaps = ax.snaps;
    var crossData = ' data-snaps="'+esc(JSON.stringify(snaps))+'" data-topy="'+ptop+'" data-boty="'+Y(0).toFixed(1)+'"';
    var hitLayer = '<rect class="tl-crossarea" x="'+pl+'" y="'+ptop+'" width="'+iw.toFixed(1)+'" height="'+ih.toFixed(1)+'"/>';
    var chart = '<svg class="tl-chart tl-flow'+(tlChartShouldAnim?" tl-anim":"")+'" viewBox="0 0 '+W+' '+Ht+'" role="img" tabindex="0"'+crossData
      + ' aria-label="Stacked colour completion over time. Click a point to pick that moment.">'
      + (defs?'<defs>'+defs+'</defs>':'')+ax.weekBands+ax.colBars+grid+bandGroup+ax.xticks+ax.scrubRule+hitLayer+'</svg>';
    // legend: one swatch per step (+ uncoloured), mirroring the band fills.
    var legend = order.map(function(k){
      return '<span class="tl-lg"><i style="background:var('+varFor(k)+')"></i>'+esc(labelFor(k))+'</span>';
    }).join("") + '<span class="tl-lg"><i class="tl-lg-hatch"></i>'+esc(H.noneLabel)+'</span>';
    return { chart:chart, legend:legend, foot:"" };   // the start/end date row moved to the navigator's ticks
  }
  // Colour tally of ONE master at ONE snapshot (exclusion-aware) for the Flow bands.
  // Every stacked-band render re-reads the same master|date pairs, and each tally is a
  // full stateAt reconstruction — so it's memoised like NAVCACHE/PMCACHE (key = the
  // active timeline dataset; zoom, scrub and view switches all reuse the entries).
  var COLCACHE = {}, COLCACHE_KEY = "";
  function colTally(mid, iso){
    var key = tlDatasetKey();
    if (COLCACHE_KEY !== key){ COLCACHE = {}; COLCACHE_KEY = key; }
    var ck = mid + "|" + iso;
    if (COLCACHE[ck]) return COLCACHE[ck];
    var order = H.order || [], byKey = {}; order.forEach(function(k){ byKey[k] = 0; }); var none = 0;
    var snap = stateAt(mid, iso);
    for (var name in snap){ if (!isCounted(name)) continue; var sk = String(snap[name]);
      if (snap[name] === -1 || order.indexOf(sk) === -1){ none++; } else { byKey[sk]++; } }
    return (COLCACHE[ck] = { byKey:byKey, none:none });
  }
  // Preset duration windows (1D / 1W / 1M / 1Y / All) that zoom the chart to the last N
  // period. They drive the SAME zoom window as the range navigator (state.viewLo/viewHi),
  // anchored on the latest snapshot (the data may be historical). "All" = full history.
  var TL_SPANS = [["1d","1D",1],["1w","1W",7],["1m","1M",30],["1y","1Y",365],["all","All",0]];
  function tlSpanToggle(){
    if (fullSeries().length < 3){ return ""; }
    var active = state.tlSpan || (isZoomed() ? "" : "all");
    var activeIdx = -1;
    TL_SPANS.forEach(function(sp, i){ if (sp[0] === active){ activeIdx = i; } });
    var btns = TL_SPANS.map(function(sp, i){
      return '<button type="button" data-tlspan="'+sp[0]+'" aria-pressed="'+(i===activeIdx)+'" title="'+(sp[0]==="all"?"Full history":"Last "+sp[1])+'">'+sp[1]+'</button>';
    }).join("");
    // Same sliding-pill segmented switch as the Graph/Calendar toggle (--segn segments).
    // While the range is dragged manually no preset is active (activeIdx<0) -> no pill.
    var hl = activeIdx >= 0 ? segHL("tlspan", activeIdx) : "";
    return '<span class="segsw tl-spanbar" role="group" aria-label="Timeline duration" style="--segn:'+TL_SPANS.length+';--seg:'+(activeIdx<0?0:activeIdx)+'">'+hl+btns+'</span>';
  }
  function setTlSpan(span){
    state.tlSpan = span;
    var s = fullSeries();
    if (span === "all" || !s.length){ state.viewLo = null; state.viewHi = null; update(); return; }
    var days = 0; TL_SPANS.forEach(function(sp){ if (sp[0] === span){ days = sp[2]; } });
    var cutMs = cfdDate(s[s.length-1].date).getTime() - days*86400000;
    var lo = 0;
    for (var i = 0; i < s.length; i++){ if (cfdDate(s[i].date).getTime() >= cutMs){ lo = i; break; } }
    state.viewLo = lo; state.viewHi = s.length - 1;
    update();
  }
  function hasTrend(){ return ((H.trend && H.trend.series) || []).length >= 2; }

  // ----- Range navigator: full-history overall-% area + a draggable zoom window -----
  // The overall graded-% line (one value per snapshot, averaged over all masters) is the
  // same metric the headline ring uses, reconstructed over time. It's expensive (stateAt
  // per master per snapshot) but invariant while zooming, so it's cached and reused across
  // the many re-renders a drag triggers.
  var NAVCACHE = null, NAVCACHE_KEY = "";
  function navOverallSeries(){
    var s = fullSeries();
    var key = state.tlGran + ":" + state.tlBucket
      + ":" + s.length + ":" + (s.length ? s[s.length-1].date : "");
    if (NAVCACHE && NAVCACHE_KEY === key){ return NAVCACHE; }
    var W = stepWeights().weight, denom = (H.masters.length * (countedTotal() || 1)) || 1;
    NAVCACHE = s.map(function(p){
      var sum = 0;
      H.masters.forEach(function(m){
        var snap = stateAt(m.id, p.date);
        for (var name in snap){ if (!isCounted(name)) continue; var w = W[String(snap[name])]; if (w){ sum += w; } }
      });
      return sum / denom * 100;
    });
    NAVCACHE_KEY = key;
    return NAVCACHE;
  }
  // ----- Per-master graded-% matrix over the windowed axis (band/grid/heatmap share it) ---
  // M[i][j] = gradedPctAt(masters[i].id, dates[j]) for the active (zoom-windowed) dates. One
  // stateAt scan per (master,date); cached so switching view or scrubbing never recomputes it.
  var PMCACHE = null, PMCACHE_KEY = "";
  function pctMatrix(){
    var series = calendarAxis(680, 200).series;
    var dates = series.map(function(p){ return p.date; });
    var key = state.tlGran + ":" + state.tlBucket + ":" + state.viewLo + ":" + state.viewHi
      + ":" + dates.length + ":" + (dates.length ? dates[dates.length-1] : "") + ":" + H.masters.length;
    if (PMCACHE && PMCACHE_KEY === key){ return PMCACHE; }
    var M = H.masters.map(function(m){
      return dates.map(function(d){ return gradedPctAt(m.id, d); });
    });
    PMCACHE = { dates:dates, M:M, masters:H.masters };
    PMCACHE_KEY = key;
    return PMCACHE;
  }
  function rangeNav(W){
    var s = fullSeries();
    if (s.length < 5){ return ""; }              // not worth a navigator below ~5 snapshots
    // Short strip (full width, same W as the main chart) — a compact overview, not a 2nd graph.
    // No y-axis labels here (unlike the main chart's pl=30 gutter), so inset only enough to
    // keep the 6px drag handles inside the box: the area/line fills the box edge-to-edge.
    var Ht = 54, pl = 8, pr = 8, ptop = 9, pb = 15, iw = W - pl - pr, ih = Ht - ptop - pb;
    // Match the main chart's spacing: even (ordinal) in both Time and Save modes so the
    // progress line rises across the full width.
    var even = true;
    var t0 = new Date(s[0].date).getTime();
    var span = (new Date(s[s.length-1].date).getTime() - t0) || 1;
    function X(i){ return even ? (pl + (s.length < 2 ? 0 : i/(s.length-1))*iw)
                               : (pl + (new Date(s[i].date).getTime() - t0)/span*iw); }
    function Y(pc){ return ptop + ih - pc/100*ih; }
    var oa = navOverallSeries();
    var pts = s.map(function(p, i){ return { x:X(i), y:Y(oa[i]) }; });
    var line = smoothPath(pts);                   // smooth, like the main chart
    var base = (ptop+ih).toFixed(1);
    var area = line + " L"+pts[pts.length-1].x.toFixed(1)+" "+base+" L"+pts[0].x.toFixed(1)+" "+base+" Z";
    var b = viewBounds(), xLo = X(b[0]), xHi = X(b[1]);
    var scrimL = '<rect class="tl-nav-scrim" x="'+pl+'" y="'+ptop+'" width="'+Math.max(0,xLo-pl).toFixed(1)+'" height="'+ih.toFixed(1)+'"/>';
    var scrimR = '<rect class="tl-nav-scrim" x="'+xHi.toFixed(1)+'" y="'+ptop+'" width="'+Math.max(0,(W-pr)-xHi).toFixed(1)+'" height="'+ih.toFixed(1)+'"/>';
    var win = '<rect class="tl-nav-win" data-navedge="mid" x="'+xLo.toFixed(1)+'" y="'+ptop+'" width="'+Math.max(0,xHi-xLo).toFixed(1)+'" height="'+ih.toFixed(1)+'"/>';
    function handle(edge, x, label){
      var gy = ptop + ih/2;
      return '<g class="tl-nav-h" data-navedge="'+edge+'" tabindex="0" role="slider" aria-label="'+label+'" aria-valuemin="0" aria-valuemax="'+(s.length-1)+'">'
        + '<rect class="tl-nav-h-hit" x="'+(x-7).toFixed(1)+'" y="'+ptop+'" width="14" height="'+ih.toFixed(1)+'"/>'
        + '<rect class="tl-nav-h-bar" x="'+(x-3).toFixed(1)+'" y="'+(gy-9).toFixed(1)+'" width="6" height="18" rx="3"/>'
        + '<line class="tl-nav-grip" x1="'+(x-1.3).toFixed(1)+'" y1="'+(gy-4).toFixed(1)+'" x2="'+(x-1.3).toFixed(1)+'" y2="'+(gy+4).toFixed(1)+'"/>'
        + '<line class="tl-nav-grip" x1="'+(x+1.3).toFixed(1)+'" y1="'+(gy-4).toFixed(1)+'" x2="'+(x+1.3).toFixed(1)+'" y2="'+(gy+4).toFixed(1)+'"/></g>';
    }
    var snaps = s.map(function(p,i){ return { x:+X(i).toFixed(1), i:i }; });
    // Date ticks below the navigator (replaces the old start/end date row): ~5 labels
    // across the full history, bucket-aware via tickLabel, sitting in the bottom gutter.
    var tickStep = Math.max(1, Math.ceil(s.length / 5));
    var navTicks = "";
    s.forEach(function(p, i){
      if (i % tickStep !== 0 && i !== s.length - 1){ return; }
      var anchor = i === 0 ? "start" : (i === s.length - 1 ? "end" : "middle");
      navTicks += '<text class="tl-xtick" x="'+X(i).toFixed(1)+'" y="'+(ptop+ih+11).toFixed(1)+'" text-anchor="'+anchor+'">'+esc(tickLabel(p.date))+'</text>';
    });
    var reset = "";   // Reset-zoom button removed (double-click the navigator to reset).
    return '<div class="tl-nav-wrap">'
      + '<svg class="tl-nav" viewBox="0 0 '+W+' '+Ht+'" data-navsnaps="'+esc(JSON.stringify(snaps))+'" role="group" aria-label="Range navigator — drag the handles to zoom the chart to a date range">'
      + '<path class="tl-nav-area" d="'+area+'"/><path class="tl-nav-line" d="'+line+'"/>'
      + scrimL + scrimR + win
      + handle("lo", xLo, "Range start") + handle("hi", xHi, "Range end")
      + navTicks
      + '</svg>' + reset + '</div>';
  }
  function navSnaps(svg){ try { return JSON.parse(svg.getAttribute("data-navsnaps")||"[]"); } catch(e){ return []; } }
  function navIndexFromClient(svg, clientX){
    var snaps = navSnaps(svg); if (!snaps.length){ return -1; }
    var box = svg.getBoundingClientRect(); if (!box.width){ return -1; }
    var vb = svg.viewBox && svg.viewBox.baseVal, vbw = (vb && vb.width) || box.width;
    var ux = (clientX - box.left) / box.width * vbw;
    var nearest = 0, best = Infinity;
    for (var i=0;i<snaps.length;i++){ var dx = Math.abs(snaps[i].x - ux); if (dx < best){ best = dx; nearest = i; } }
    return nearest;
  }
  // pointerdown on a handle resizes that edge; on the window pans it (keeping width); on
  // the side scrims starts a fresh selection. The main chart re-zooms live (rAF-throttled)
  // by re-reading the navigator off the DOM each frame, since update() rebuilds it.
  function navDrag(evt){
    var svg = evt.target.closest && evt.target.closest(".tl-nav");
    if (!svg){ return; }
    var edgeEl = evt.target.closest("[data-navedge]");
    var edge = edgeEl ? edgeEl.getAttribute("data-navedge") : "new";
    var snaps = navSnaps(svg); var n = snaps.length; if (n < 2){ return; }
    evt.preventDefault();
    var b = viewBounds(), lo0 = b[0], hi0 = b[1], width = hi0 - lo0;
    var startIdx = navIndexFromClient(svg, evt.clientX);
    var grabOff = (edge === "mid") ? startIdx - lo0 : 0;
    state.tlSpan = null;                        // manual zoom -> no preset is "active"
    function setFromIdx(idx){
      if (edge === "hi"){ state.viewLo = lo0; state.viewHi = Math.max(lo0 + 1, idx); }
      else if (edge === "lo"){ state.viewHi = hi0; state.viewLo = Math.min(hi0 - 1, idx); }
      else if (edge === "mid"){ var nlo = Math.max(0, Math.min(idx - grabOff, n - 1 - width)); state.viewLo = nlo; state.viewHi = nlo + width; }
      else { state.viewLo = Math.min(startIdx, idx); state.viewHi = Math.max(startIdx, idx);
             if (state.viewHi - state.viewLo < 1){ state.viewHi = Math.min(n - 1, state.viewLo + 1); } }
    }
    setFromIdx(startIdx); update();
    var raf = 0, pend = startIdx;
    function flush(){ raf = 0; setFromIdx(pend); update(); }
    function onMove(mv){
      var live = document.querySelector(".tl-nav"); if (!live){ return; }
      var idx = navIndexFromClient(live, mv.clientX); if (idx < 0){ return; }
      pend = idx;
      if (!raf){ raf = (window.requestAnimationFrame || function(f){ return setTimeout(f, 16); })(flush); }
    }
    function onUp(){
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      if (raf){ (window.cancelAnimationFrame || clearTimeout)(raf); raf = 0; }
      setFromIdx(pend); update();
    }
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
  }
  // Keyboard: Left/Right nudge the focused handle by one snapshot.
  function navKey(evt){
    if (evt.key !== "ArrowLeft" && evt.key !== "ArrowRight"){ return; }
    var h = evt.target.closest && evt.target.closest(".tl-nav-h"); if (!h){ return; }
    var n = fullSeries().length; if (n < 2){ return; }
    evt.preventDefault();
    var edge = h.getAttribute("data-navedge");
    var b = viewBounds(), lo = b[0], hi = b[1], step = evt.key === "ArrowRight" ? 1 : -1;
    if (edge === "lo"){ state.viewLo = Math.max(0, Math.min(hi - 1, lo + step)); state.viewHi = hi; }
    else { state.viewHi = Math.min(n - 1, Math.max(lo + 1, hi + step)); state.viewLo = lo; }
    update();
  }
  function navReset(){ state.viewLo = null; state.viewHi = null; state.tlSpan = "all"; update(); }
  // graded value of one state map {glyph:key}: sum of the per-step weights used by
  // the existing % helpers (stepWeights().weight maps key -> (i+1)/N).
  function gradedStateSum(stateMap){
    var W = stepWeights().weight, s = 0;
    for (var name in stateMap){ if (!isCounted(name)) continue; var w = W[stateMap[name]]; if (w) s += w; }
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
    // over the whole-font denominator (exclusion-aware), same scale as the % cards.
    var denom = countedTotal() || Object.keys(names).length || 1;
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
  // Parse a timeline key — "YYYY-MM-DD" (per-day) or "YYYY-MM-DDTHH:MM:SS[.n]"
  // (per-commit) — into a stable Date. Avoids the "...T...T00:00:00Z" invalid-date
  // trap when commit-granularity datetime keys flow through the date math below.
  function cfdDate(iso){
    if (typeof iso !== "string") return new Date(NaN);
    return (iso.indexOf("T") > 0) ? new Date(iso.slice(0, 19) + "Z")
                                  : new Date(iso + "T00:00:00Z");
  }
  // ISO date N days before another ISO date (UTC midnight, timezone-stable).
  function isoMinusDays(iso, days){
    var d = cfdDate(iso);
    d.setUTCDate(d.getUTCDate() - days);
    return d.toISOString().slice(0, 10);
  }
  // Shared rank-arrow glyph + colour class for a signed change (used by the week
  // digest, the category/script lanes and the per-master deadline verdict chips).
  function rankArrow(value){
    return { g: value > 0 ? "▲" : (value < 0 ? "▼" : "▬"),
             c: value > 0 ? "tl-d-up" : (value < 0 ? "tl-d-down" : "tl-d-flat") };
  }
  // The active master for the per-category / per-script lanes: the selected one, else
  // the first. (The full-history regression log + red chart flags were removed.)
  function reglogMaster(){ return state.master || (H.masters[0] && H.masters[0].id); }
  // ----- #D Shape changes: glyphs whose OUTLINE changed between git commits ----
  // H.outlineChanges = { iso_date: [{glyph, master, old:{d,vb}, new:{d,vb}}] }, built
  // from the font's recent git history. Each day is a collapsible block (closed by
  // default); expanding it shows the changed glyphs as onion-skin overlays — the old
  // outline ghosted under the new, both drawn in a shared (union) viewBox so a moved
  // shape reads as the real shift. Dormant (renders nothing) when the data is empty.
  function ocUnionVB(a, b){
    function parse(s){
      var t = (s||"").split(/\s+/).map(parseFloat);
      return (t.length===4 && t.every(function(n){ return !isNaN(n); })) ? t : null;
    }
    var pa = parse(a), pb = parse(b);
    if (!pa && !pb) return "0 0 1000 1000";
    if (!pa) return b; if (!pb) return a;
    var x = Math.min(pa[0], pb[0]), y = Math.min(pa[1], pb[1]);
    var right = Math.max(pa[0]+pa[2], pb[0]+pb[2]), bottom = Math.max(pa[1]+pa[3], pb[1]+pb[3]);
    return x+" "+y+" "+(right-x)+" "+(bottom-y);
  }
  // Shared onion-skin SVG for ONE outline change — the old outline ghosted under the
  // new in their union viewBox. Used by both the per-day grid cells (ocCell) and the
  // "Touched after done" watch-list rows, so the rendering never forks.
  function ocOnionSVG(change){
    var oldP = change.old || {}, newP = change.new || {};
    var vb = ocUnionVB(oldP.vb, newP.vb);
    return '<svg viewBox="'+esc(vb)+'" preserveAspectRatio="xMidYMid meet" aria-hidden="true">'
      + (oldP.d ? '<path class="oc-old" d="'+esc(oldP.d)+'"/>' : '')
      + (newP.d ? '<path class="oc-new" d="'+esc(newP.d)+'"/>' : '')
      + '</svg>';
  }
  function ocCell(change){
    var sub = state.master==null && change.master ? (" · "+change.master) : "";
    return '<span class="oc-cell" title="'+esc(change.glyph+sub+" — outline changed")+'">'
      + ocOnionSVG(change)
      + '<span class="oc-glyph">'+esc(change.glyph)+'</span></span>';
  }
  function outlineChangesView(){
    var oc = H.outlineChanges || {};
    var dates = Object.keys(oc).sort().reverse();        // most recent day first
    if (!dates.length) return "";
    var blocks = dates.map(function(d){
      var items = (oc[d]||[]).filter(function(c){ return state.master==null || c.master===state.master; });
      if (!items.length) return "";
      var open = !!state.ocOpen[d];
      var grid = open ? '<div class="oc-grid">'+items.map(ocCell).join("")+'</div>' : "";
      return '<div class="oc-day'+(open?" open":"")+'">'
        + '<button type="button" class="oc-day-h" data-oc="'+esc(d)+'" aria-expanded="'+(!!open)+'" title="Show or hide the glyphs whose outline changed on '+esc(dateLabel(d))+'">'
        + '<span class="oc-chev" aria-hidden="true">'+(open?"▾":"▸")+'</span>'
        + '<span class="oc-date">'+esc(dateLabel(d))+'</span>'
        + '<span class="oc-count">'+items.length+' glyph'+(items.length===1?"":"s")+'</span></button>'
        + grid + '</div>';
    }).join("");
    if (!blocks){ return ""; }                            // nothing for the focused master
    return '<div class="oc" role="group" aria-label="Glyph outline changes by date">'
      + '<div class="oc-h">Shape changes</div>'+blocks+'</div>';
  }
  // ----- "Touched after done" watch list: outline edits to FINISHED glyphs ----
  // Client-side join of H.outlineChanges (per-day outline diffs, per master) with
  // H.journeyIndex (per-glyph step change-events): a change on date D offends when the
  // glyph ENTERED the final workflow step (last key in H.order) strictly before D and
  // no later event moved it off that step before the change. Dormant when either
  // dataset is empty (non-git / NoGlyphSVG reports never show the card).
  function tadDoneTs(events, finalKey, changeDate){
    // Timestamp the glyph entered the final step, scanning only events dated strictly
    // BEFORE the change's day (same-day ordering is unknowable at day granularity);
    // any later off-step event clears it. null = not done by the change.
    var doneTs = null;
    for (var i=0;i<events.length;i++){
      var ts = String(events[i][0]);
      if (ts.slice(0,10) >= changeDate) break;
      if (String(events[i][1]) === finalKey){ if (doneTs === null) doneTs = ts; }
      else { doneTs = null; }                  // moved off the final step -> not done
    }
    return doneTs;
  }
  function touchedAfterDone(){
    // -> [{glyph, master, change, date, doneDate, gapDays}] sorted gap-descending.
    // Scoped to the focused master when focused, else joined across every master.
    var oc = H.outlineChanges || {}, index = H.journeyIndex || {};
    var finalKey = (H.order && H.order.length) ? String(H.order[H.order.length-1]) : null;
    if (!finalKey) return [];
    var rows = [];
    Object.keys(oc).forEach(function(d){
      (oc[d]||[]).forEach(function(change){
        if (state.master != null && change.master !== state.master) return;
        var perGlyph = index[change.master] || {};
        var doneTs = tadDoneTs(perGlyph[change.glyph] || [], finalKey, d);
        if (doneTs === null) return;
        var ms = cfdDate(d).getTime() - cfdDate(doneTs.slice(0,10)).getTime();
        if (isNaN(ms) || ms <= 0) return;      // malformed dates -> not an offence
        rows.push({ glyph: change.glyph, master: change.master, change: change,
                    date: d, doneDate: doneTs.slice(0,10), gapDays: Math.round(ms/86400000) });
      });
    });
    rows.sort(function(a,b){ return (b.gapDays - a.gapDays) || (a.glyph < b.glyph ? -1 : 1); });
    return rows;
  }
  function tadMasterName(mid){
    var m = (H.masters||[]).filter(function(x){ return x.id === mid; })[0];
    return m ? m.name : mid;
  }
  function touchedAfterDoneView(){
    var rows = touchedAfterDone();
    if (!rows.length) return "";               // empty join or no outlineChanges -> hidden
    var body = rows.map(function(row){
      var masterTag = state.master == null
        ? '<span class="tad-master">'+esc(tadMasterName(row.master))+'</span>' : "";
      return '<button type="button" class="tad-row" data-jglyph="'+esc(row.glyph)
        + '" title="Open the journey of '+esc(row.glyph)+'">'
        + ocOnionSVG(row.change)
        + '<span class="tad-glyph">'+esc(row.glyph)+'</span>'+masterTag
        + '<span class="tad-when">done '+esc(dateLabel(row.doneDate))
        + ' → outline changed '+esc(dateLabel(row.date))
        + ' <b>('+row.gapDays+' day'+(row.gapDays===1?"":"s")+' later)</b></span></button>';
    }).join("");
    return '<div class="tad" role="group" aria-label="Touched after done — outline edits to glyphs already on the final step">'
      + '<div class="tad-h">Touched after done <span class="tad-sub">outline edits to glyphs already on the final step</span></div>'
      + body + '</div>';
  }
  // ----- shared lane maths (category + script lanes) -------------------------
  // Graded completion % of a glyph-name set at a snapshot, for ONE master.
  function laneGradedPctOne(mid, names, iso){
    var st = stateAt(mid, iso), weight = stepWeights().weight, sum = 0, n = 0;
    for (var i=0;i<names.length;i++){ if (!isCounted(names[i])) continue; n++; var w = weight[st[names[i]]]; if (w) sum += w; }
    return n ? Math.round(sum/n*100) : 0;
  }
  // ...scoped to the focused master, or AVERAGED across the family in Global view, so a
  // lane reads font-wide instead of silently tracking only the first master.
  function laneGradedPct(names, iso){
    if (state.master != null) return laneGradedPctOne(state.master, names, iso);
    var sum=0, n=0;
    for (var i=0;i<H.masters.length;i++){ sum += laneGradedPctOne(H.masters[i].id, names, iso); n++; }
    return n ? Math.round(sum/n) : 0;
  }
  // The snapshot index the over-time lanes read: the moment picked by clicking the chart
  // (state.tlScrub, via scrubIndex), in both Global and focused views, so the category /
  // script panels follow the click. Defaults to the latest snapshot. Date-consistent.
  function scrubScopeIdx(){
    var dates = (H.trend && H.trend.dates) || [];
    if (!dates.length) return -1;
    return scrubIndex();
  }
  // Tiny completion-over-time polyline for a lane (chart Y-flip idiom, mini box).
  function laneSparkSVG(values, key){
    var n = values.length, w = 64, h = 16, pad = 1.5, iw = w - pad*2, ih = h - pad*2;
    if (n < 1) return "";
    // First snapshot has a single point: draw a flat line across the box at that level
    // (Hugo wants the line look at every moment, never a bar). morphSparks still tweens it.
    var yOf = function(v){ return pad + ih - Math.max(0, Math.min(100, v))/100*ih; };
    var pts = (n === 1)
      ? (pad.toFixed(1)+","+yOf(values[0]).toFixed(1)+" "+(w-pad).toFixed(1)+","+yOf(values[0]).toFixed(1))
      : values.map(function(v, i){
          var x = pad + i/(n-1)*iw;
          return x.toFixed(1)+","+yOf(v).toFixed(1);
        }).join(" ");
    // Draw-in the line when switching focused master (laneSparkShouldAnim), reusing the
    // chart's tlDraw keyframe via pathLength="1". Reduced-motion neutralises it. The
    // data-spark key lets morphSparks() tween this line's shape when the moment changes.
    var animCls = laneSparkShouldAnim ? " tl-spark-anim" : "";
    return '<svg class="tl-lane-spark'+animCls+'" width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'" aria-hidden="true">'
      + '<polyline data-spark="'+esc(key||"")+'" points="'+pts+'" pathLength="1" fill="none"/></svg>';
  }
  // ----- #17 per-category progress lanes over time ---------------------------
  function categoryLanes(){
    // Shown in BOTH Global and focus mode. laneGradedPct scopes to the focused master
    // (or averages the family in Global), so the lanes read for whatever's in focus.
    var dates = (H.trend && H.trend.dates) || [];
    if (dates.length < 1) return "";
    // Map each glyph to its category from the parallel H.glyphNames / H.categories
    // arrays, grouping the glyph names by category (empty categories never appear).
    // Non-exporting glyphs are dropped here so the lane counts read counted sizes.
    var allNames = H.glyphNames || [], allCats = H.categories || [], groups = {};
    for (var gi = 0; gi < allNames.length; gi++){
      if (!isCounted(allNames[gi])) continue;
      var gcat = allCats[gi] || "Other";
      (groups[gcat] || (groups[gcat] = [])).push(allNames[gi]);
    }
    var cats = Object.keys(groups);
    if (!cats.length) return "";
    var mid = reglogMaster();
    if (!mid) return "";
    // Follow the moment picked on the chart (state.tlScrub via scrubScopeIdx), even in
    // Global view: the % is at that snapshot, the sparkline runs up to it, the delta is
    // vs the previous snapshot. Defaults to the latest snapshot when nothing is picked.
    var idx = scrubScopeIdx();
    var scrubISO = (idx>=0 && dates[idx]) ? dates[idx] : dates[dates.length-1];
    var prevISO = idx > 0 ? dates[idx-1] : null;
    var upto = idx >= 0 ? dates.slice(0, idx+1) : dates.slice();
    var lanes = cats.map(function(cat){
      var names = groups[cat];
      var values = upto.map(function(d){ return laneGradedPct(names, d); });
      var cur = laneGradedPct(names, scrubISO);
      var delta = prevISO ? cur - laneGradedPct(names, prevISO) : 0;
      return { cat:cat, count:names.length, values:values, cur:cur, delta:delta };
    });
    // Fixed canonical order (Glyphs Font-View style: Letter, Number, ...), so the lanes
    // never reshuffle when the picked moment / data changes. Unknown categories fall after,
    // alphabetically.
    var CAT_ORDER = ["Letter","Number","Punctuation","Mark","Separator","Symbol","Other"];
    lanes.sort(function(a, b){
      var ia = CAT_ORDER.indexOf(a.cat); ia = ia < 0 ? CAT_ORDER.length : ia;
      var ib = CAT_ORDER.indexOf(b.cat); ib = ib < 0 ? CAT_ORDER.length : ib;
      return (ia - ib) || (a.cat < b.cat ? -1 : 1);
    });
    var rows = lanes.map(function(ln){
      var ra = rankArrow(ln.delta); var arrow = ra.g, arrowCls = ra.c;
      var deltaTxt = prevISO ? ((ln.delta>0?"+":"")+ln.delta+"% vs "+esc(dateLabel(prevISO))) : "first snapshot";
      var mid2 = laneSparkSVG(ln.values, "cat:"+ln.cat);   // line at every moment (incl. first date)
      return '<div class="tl-lane'+(ln.cur>=100?" done":"")+'">'
        + '<span class="tl-lane-n" title="'+esc(ln.cat)+'">'+esc(ln.cat)+' <small>('+ln.count+')</small></span>'
        + '<span class="tl-lane-mid">'+mid2+'</span>'
        + '<span class="tl-lane-pct" data-lanekey="cat:'+esc(ln.cat)+'" data-to="'+ln.cur+'">'+ln.cur+'%</span>'
        + '<span class="tl-lane-d '+arrowCls+'" title="'+deltaTxt+'" aria-label="'+deltaTxt+'">'+arrow+'</span>'
        + '</div>';
    }).join("");
    return '<div class="tl-lanes">'+rows+'</div>';
  }
  // Compact per-category header strip for the Time Machine grid blocks (master view):
  // ----- #18 per-script progress lanes over time -----------------------------
  // Mirror of categoryLanes (#17) but grouped by the per-glyph H.scripts array
  // (writing systems: Latin, Cyrillic, Greek, ...) instead of H.categories.
  function scriptLanes(){
    var dates = (H.trend && H.trend.dates) || [];
    if (dates.length < 1) return "";
    // Map each glyph to its script from the parallel H.glyphNames / H.scripts
    // arrays, grouping the glyph names by script (empty scripts never appear).
    // Non-exporting glyphs are dropped here so the lane counts read counted sizes.
    var allNames = H.glyphNames || [], allScripts = H.scripts || [], groups = {};
    for (var gi = 0; gi < allNames.length; gi++){
      if (!isCounted(allNames[gi])) continue;
      var gscript = allScripts[gi] || "Other";
      (groups[gscript] || (groups[gscript] = [])).push(allNames[gi]);
    }
    var scripts = Object.keys(groups).filter(function(s){ return s !== "Other"; });   // skip the "Other" bucket
    if (!scripts.length) return "";
    // When Latin is the ONLY writing system, the per-script breakdown just mirrors the
    // overall progress -> hide the whole section (no point showing a single "Latin" lane).
    if (scripts.length === 1 && /^latin$/i.test(scripts[0])) return "";
    var mid = reglogMaster();
    if (!mid) return "";
    // read the scrubbed Time-Machine checkpoint (master view) / latest (global): the % at
    // that date, the sparkline up to it, and the delta vs the PREVIOUS snapshot, so the
    // script breakdown follows the slider the same way the category headers do.
    var idx = scrubScopeIdx();
    var scrubISO = (idx>=0 && dates[idx]) ? dates[idx] : dates[dates.length-1];
    var prevISO = idx > 0 ? dates[idx-1] : null;
    var upto = idx >= 0 ? dates.slice(0, idx+1) : dates.slice();
    var lanes = scripts.map(function(script){
      var names = groups[script];
      var values = upto.map(function(d){ return laneGradedPct(names, d); });
      var cur = laneGradedPct(names, scrubISO);
      var delta = prevISO ? cur - laneGradedPct(names, prevISO) : 0;
      return { script:script, count:names.length, values:values, cur:cur, delta:delta };
    });
    // laggard-first: lowest current % on top (name as a stable tie-breaker).
    lanes.sort(function(a, b){ return (a.cur - b.cur) || (a.script < b.script ? -1 : 1); });
    var rows = lanes.map(function(ln){
      var ra = rankArrow(ln.delta); var arrow = ra.g, arrowCls = ra.c;
      var deltaTxt = prevISO ? ((ln.delta>0?"+":"")+ln.delta+"% vs "+esc(dateLabel(prevISO))) : "first snapshot";
      var mid2 = laneSparkSVG(ln.values, "scr:"+ln.script);   // line at every moment (incl. first date)
      return '<div class="tl-lane'+(ln.cur>=100?" done":"")+'">'
        + '<span class="tl-lane-n" title="'+esc(prettyScript(ln.script))+'">'+esc(prettyScript(ln.script))+' <small>('+ln.count+')</small></span>'
        + '<span class="tl-lane-mid">'+mid2+'</span>'
        + '<span class="tl-lane-pct" data-lanekey="scr:'+esc(ln.script)+'" data-to="'+ln.cur+'">'+ln.cur+'%</span>'
        + '<span class="tl-lane-d '+arrowCls+'" title="'+deltaTxt+'" aria-label="'+deltaTxt+'">'+arrow+'</span>'
        + '</div>';
    }).join("");
    return '<div class="tl-lanes">'+rows+'</div>';
  }
  // (The #19 deadline / Target-date feature was removed — no target picker, no on-chart
  //  deadline rule, no verdict chips.)
  // ----- #11 moment scrubber -------------------------------------------------
  // The snapshot index currently scrubbed: state.tlScrub clamped to the dates range,
  // defaulting to the latest snapshot when unset.
  function scrubIndex(){
    var dates = (H.trend && H.trend.dates) || [];
    if (!dates.length) return -1;
    var idx = state.tlScrub == null ? dates.length-1 : state.tlScrub;
    return Math.max(0, Math.min(dates.length-1, idx));
  }
  // Set the scrub index (clamped) and re-render. A full update() makes picking a moment
  // update EVERYTHING tied to it — the colour disc, the category/script lanes and their
  // %/deltas all recompute at the scrubbed index (scrubScopeIdx). Picking the latest
  // snapshot clears the scrub (back to "live").
  function scrubSet(idx){
    var dates = (H.trend && H.trend.dates) || [];
    if (!dates.length) return;
    var clamped = Math.max(0, Math.min(dates.length-1, idx));
    var prev = state.tlScrub;
    state.tlScrub = (clamped === dates.length-1) ? null : clamped;
    if (state.tlScrub !== prev) scrubAnim = true;   // a new moment: animate the bars/cells/lines that follow it
    update();
  }
  // ----- #20 rich onboarding seed states for sparse history -------------------
  // One builder for both early states. <2 snapshots: a skeleton preview (dashed
  // placeholder line + ghost dots + ONE real solid "today" dot from the single
  // snapshot) + locked preview chips + a "History: N of 3 days" meter. ==2: a
  // compact one-day diff (A/B picker hidden) + the same meter. >=3 never reaches
  // here (timelineView gates it). All theme-safe + a11y-labelled; reduced-motion
  // drops the skeleton shimmer via the shared __cfdNoAnim / matchMedia gate.
  function seedState(){
    var dates = (H.trend && H.trend.dates) || [];
    var noAnim = window.__cfdNoAnim ||
      (window.matchMedia && window.matchMedia("(prefers-reduced-motion:reduce)").matches);
    // shared "History: N of 3 days" meter; 3 snapshots unlock the full timeline
    // (history itself is uncapped). In Save mode the unlock is "another commit"/
    // "another save", not a day.
    var byCommit = state.tlGran === "save";
    var units = byCommit ? fineUnits() : "days";
    var n = Math.min(3, dates.length);
    var meterWidth = Math.round(n / 3 * 100);
    var meterLabel = "History: " + n + " of 3 " + units;
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
        + '<div class="tl-seed-head">First two '+units+' in</div>'
        + '<p class="tl-seed-line2">'+(byCommit?"Across those 2 "+fineUnits()+" you advanced ":"In 1 day you advanced ")+'<b>'+c.advanced+'</b> '
        + '<span class="tl-seed-net '+(c.deltaPct>=0?"tl-d-up":"tl-d-down")+'">('+net+')</span>.</p>'
        + '<p class="tl-seed-sub">'+(byCommit?"Make another "+fineNoun():"Save again tomorrow")+' to unlock the full timeline (streak, moment discs, shape changes).</p>'
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
      pc = gradedPctAt(midOne, single.date);        // graded (matches the ring), not final-step-only
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
      + esc("One snapshot so far at " + Math.round(pc) + "%. The chart unlocks once a second " + (byCommit ? fineNoun()+" is recorded" : "day of history is saved") + ".")+'">'
      + ghostLine + ghostDots + todayDot + '</svg>';
    // locked preview chips: Streak / Moment discs / Shape changes, each muted "unlocks at 2 days".
    var locks = ["Streak", "Moment discs", "Shape changes"].map(function(name){
      return '<span class="tl-lock" aria-disabled="true">'
        + '<span class="tl-lock-n">'+esc(name)+'</span>'
        + '<span class="tl-lock-h">unlocks at 2 '+units+'</span></span>';
    }).join("");
    return '<section class="tl-seed tl-seed-1" role="group" aria-label="Getting started">'
      + '<div class="tl-seed-head">Building your timeline</div>'
      + skeleton
      + '<p class="tl-seed-sub">'+(byCommit
          ? "AZ Colorflow reads a snapshot from each git commit. The chart unlocks at 2 commits of history."
          : "AZ Colorflow saves a snapshot each time you save the font. The chart unlocks at 2 days of history.")+'</p>'
      + '<div class="tl-seed-locks">'+locks+'</div>'
      + histMeter
      + '</section>';
  }
  // ----- Activity calendar (GitHub-contribution style) -----------------------
  // Per snapshot date, how many glyphs changed colour vs the previous snapshot —
  // the shared changeCounts() walk (cached; equivalent to diffing full stateAt
  // snapshots) over the chosen master. Non-snapshot calendar days are 0.
  function calActivity(masterId){
    var dates = (H.trend && H.trend.dates) || [];
    var chg = changeCounts(masterId), counts = {};
    for (var d=0; d<dates.length; d++){ counts[dates[d]] = chg[d]; }
    return counts;
  }
  // Shared per-master activity level: 1 (no change) .. 4 (busiest snapshot).
  function calLevelFn(counts){
    var maxC = 1; for (var k in counts){ if (counts[k] > maxC) maxC = counts[k]; }
    return function(c){ if (!c) return 1; var r = c/maxC; return r>0.66?4:r>0.33?3:2; };
  }
  // Activity counts for the calendar's active scope: the focused master, or summed
  // across the whole family in Global view (so the calendar isn't just master #1).
  function calActivityScoped(){
    if (state.master != null) return calActivity(state.master);
    var dates = (H.trend && H.trend.dates) || [], total = {};
    dates.forEach(function(d){ total[d] = 0; });
    H.masters.forEach(function(m){
      var c = calActivity(m.id);
      for (var k in c){ total[k] = (total[k]||0) + (c[k]||0); }
    });
    return total;
  }
  // The displayed month for the Standard calendar; lazily seeded to the last snapshot's
  // month so the first thing the user sees is where their history actually is.
  function calMonthRef(){
    var dates = (H.trend && H.trend.dates) || [];
    if (state.calY == null || state.calM == null){
      var last = dates.length ? dates[dates.length-1] : null;
      state.calY = last ? parseInt(last.slice(0,4),10) : 2000;
      state.calM = last ? parseInt(last.slice(5,7),10)-1 : 0;
    }
    return { y: state.calY, m: state.calM };
  }
  // macOS-Calendar-style month grid: ‹ Month Year › nav, weekday header, day cells.
  // Snapshot days carry the activity level + are clickable (scrub the Time Machine);
  // days inside the history range but without a snapshot get a faint fill.
  function standardCalendar(){
    var MONTHS = ["January","February","March","April","May","June",
                  "July","August","September","October","November","December"];
    var dates = (H.trend && H.trend.dates) || [];
    var counts = calActivityScoped();
    var dateIdx = {}; dates.forEach(function(dt, i){ dateIdx[dt] = i; });
    var level = calLevelFn(counts);
    var ref = calMonthRef(), y = ref.y, m = ref.m;
    function pad2(n){ return (n<10?"0":"")+n; }
    var firstSnap = dates[0], lastSnap = dates[dates.length-1];
    var firstDow = new Date(Date.UTC(y, m, 1)).getUTCDay();            // 0=Sun
    var daysInMonth = new Date(Date.UTC(y, m+1, 0)).getUTCDate();
    var dow = ["S","M","T","W","T","F","S"].map(function(d){
      return '<div class="tl-mcal-dow">'+d+'</div>'; }).join("");
    var cells = "";
    for (var b=0; b<firstDow; b++){ cells += '<div class="tl-mcal-d tl-mcal-pad"></div>'; }
    for (var day=1; day<=daysInMonth; day++){
      var iso = y+"-"+pad2(m+1)+"-"+pad2(day);
      var snapI = dateIdx[iso], inRange = (iso >= firstSnap && iso <= lastSnap);
      var cnt = counts[iso] || 0, cls = "tl-mcal-d", attr = "", title = iso;
      if (snapI != null){
        cls += " tl-mcal-snap lv"+level(cnt);
        attr = ' data-calday="'+snapI+'" role="button" tabindex="0"';
        title = iso + (cnt ? " · "+cnt+" changed" : " · snapshot");
      } else if (inRange){ cls += " tl-mcal-inrange"; }
      cells += '<div class="'+cls+'"'+attr+' title="'+esc(title)+'"><span class="tl-mcal-n">'+day+'</span></div>';
    }
    var nav = '<div class="tl-mcal-nav">'
      + '<button type="button" class="chip tl-mcal-prev" data-calnav="-1" aria-label="Previous month">‹</button>'
      + '<span class="tl-mcal-title">'+MONTHS[m]+' '+y+'</span>'
      + '<button type="button" class="chip tl-mcal-next" data-calnav="1" aria-label="Next month">›</button></div>';
    return '<div class="tl-mcal">'+nav
      + '<div class="tl-mcal-grid" role="img" aria-label="'+esc(MONTHS[m]+" "+y+" snapshot calendar; click a snapshot day to scrub the Time Machine to it.")+'">'
      + dow + cells + '</div></div>';
  }
  function activityCalendar(){
    var dates = (H.trend && H.trend.dates) || [];
    if (dates.length < 2) return "";
    return '<div class="tl-cal-card">' + standardCalendar() + '</div>';
  }
  // Timeline mode toggle: Time (group saves over time) vs Save (one point per save).
  // In Time mode a second toggle picks the grouping bucket (Hours/Days/Months). Hidden
  // without a fine dataset (then there is only one possible view).
  function tlGranToggle(){
    if (!H.hasCommits) return "";
    // Save is the default base graph (every save). A single "Time" toggle switches into
    // the grouped view; clicking it again returns to Save. The time-range buttons
    // (Hours/Days/Months) only appear while Time is active — no separate Save button.
    var time = state.tlGran === "time";
    var timeTitle = H.fineKind === "save" ? "Group saves over time" : "Group commits over time";
    var modes = '<div class="tl-mode" role="group" aria-label="Timeline mode">'
      + '<button type="button" class="chip tl-mode-btn" data-tlgrantoggle="1" aria-pressed="'+time+'" title="'+timeTitle+'">Time</button>'
      + '</div>';
    var buckets = "";
    if (time){
      // Hours dropped: past days collapse to end-of-day (no intra-day history to group),
      // and today's per-save detail already lives in the Save view.
      var units = [["day","Days"],["month","Months"]];
      buckets = '<div class="tl-mode tl-bucket" role="group" aria-label="Time grouping">'
        + units.map(function(u){
            return '<button type="button" class="chip tl-mode-btn" data-tlbucket="'+u[0]+'" aria-pressed="'+(state.tlBucket===u[0])+'" title="Group by '+u[1].toLowerCase()+'">'+u[1]+'</button>';
          }).join("") + '</div>';
    }
    return '<div class="tl-granbar"><span class="tl-granlabel">Timeline</span>'+modes+buckets+'</div>';
  }
  // Shared sliding highlight for any .segsw switch. Remembers the previous --seg index per
  // switch key, so a click can MORPH the pill from the old segment to the new one. The report
  // rebuilds the DOM via innerHTML each render, so a plain CSS transition never fires on the
  // fresh element — we drive the slide with a keyframe gated on a click flag (segswAnimKey).
  function segHL(key, seg){
    var prev = segswPrev.hasOwnProperty(key) ? segswPrev[key] : seg;
    segswPrev[key] = seg;
    var anim = (segswAnimKey === key && prev !== seg) ? " anim" : "";
    return '<span class="segsw-hl'+anim+'" style="--seg-from:'+prev+';--seg-to:'+seg+'" aria-hidden="true"></span>';
  }
  // The little (i) at the top-right of the graph card; its tooltip explains what the band is.
  function tlGraphInfo(){
    var pm = pctMatrix();
    var txt = "Median completion over time · shaded band spans min–max across "+pm.masters.length+" masters";
    // A CSS hover/focus tooltip (the native title attribute does not surface reliably in the
    // Glyphs WebView). Positioned top-right OVER the chart by .tl-info-wrap.
    return '<span class="tl-info-wrap">'
      + '<button type="button" class="tl-info" aria-label="'+esc(txt)+'" aria-describedby="cfd-tl-tip">i</button>'
      + '<span class="tl-info-tip" id="cfd-tl-tip" role="tooltip">'+esc(txt)+'</span></span>';
  }
  // Segmented switch (sliding highlight) that flips the shared Timeline card between the
  // completion Graph and the Activity Calendar — only one is on screen at a time.
  function tlPaneSwitch(){
    var cal = state.tlPane === "calendar";
    return '<span class="segsw tl-paneswitch" role="group" aria-label="Timeline view" style="--seg:'+(cal?1:0)+'">'
      + segHL("tlpane", cal?1:0)
      + '<button type="button" data-tlpane="graph" aria-pressed="'+(!cal)+'" title="Show the completion graph">Graph</button>'
      + '<button type="button" data-tlpane="calendar" aria-pressed="'+cal+'" title="Show the activity calendar">Calendar</button></span>';
  }
  function timelineView(){
    // #20: <3 snapshots routes to the rich seed states (a skeleton + locked chips at
    // <2, a compact one-day diff at ==2). The full view needs >=3 to be meaningful.
    var dates = (H.trend && H.trend.dates) || [];
    if (dates.length < 3){
      return '<section class="timeline"><section class="tl-empty">'+seedState()+'</section></section>';
    }
    // One graph (the graded completion Line). Global (no master) -> a neutral band per
    // master. Focusing a master AUTO-SHOWS that master's weighted per-colour breakdown.
    var parts = (state.master != null) ? streamParts(680, 200) : trendBandParts(680, 200);
    tlChartShouldAnim = false;                   // consumed: animate only on entering Timeline, not on scrub/zoom
    // The graph and the Activity calendar share ONE card; the segmented switch flips
    // between them. The duration (Day/Week/Month/Year/All) presets sit next to the graph.
    var graphPane = '<div class="tl-chartwrap">'+parts.chart+tlGraphInfo()+'</div>'+rangeNav(680)+parts.foot;
    var calPane = '<div class="tl-calpane">'+activityCalendar()+'</div>';
    var pane = (state.tlPane === "calendar") ? calPane : graphPane;
    // Header row: Graph/Calendar switch on the LEFT, the duration presets (1D/1W/1M/1Y/All)
    // on the RIGHT — aligned on one line. The (i) info button moved INTO the chart (top-right).
    var spans = (state.tlPane === "calendar") ? "" : tlSpanToggle();
    var card = '<div class="tl-graphcard"><div class="tl-graphcard-h">'+tlPaneSwitch()+spans+'</div>'+pane+'</div>';
    // Clicking the chart picks a moment (scrub): the left-sidebar discs + the category /
    // script lanes recompute at that moment. The lanes sit in a two-column grid.
    // In the Calendar pane the category/script lanes are hidden entirely (just the calendar).
    var scriptL = (state.tlPane === "calendar") ? "" : scriptLanes();
    // No Script lanes (e.g. a Latin-only font) -> let the category lanes use the freed second
    // column (two-up) instead of leaving an empty half.
    var lanesGrid = (state.tlPane === "calendar") ? ""
      : (scriptL
          ? '<div class="tl-lanes-grid">'+categoryLanes()+scriptL+'</div>'
          : '<div class="tl-lanes-grid tl-lanes-cat2">'+categoryLanes()+'</div>');
    laneSparkShouldAnim = false;                  // consumed: lanes draw-in once per focus switch, not on scrub/zoom
    return '<section class="timeline">'+card+lanesGrid
      + outlineChangesView()+touchedAfterDoneView()+'</section>';
  }
  function renderBody(){
    return state.view==="timeline" ? timelineView()
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
      // a hidden colour (not in the visible order) reads as uncoloured, like m.keys
      if (key !== null) out[name] = (key !== -1 && H.order.indexOf(String(key))===-1) ? -1 : key;
    }
    return out;
  }
  // ----- Shared caches over the journey substrate -----------------------------
  // Everything derived from journeyIndex only changes when applyGranularity() swaps
  // the timeline dataset (Save vs Time / hour-day-month bucketing). tlDatasetKey() is
  // that identity — the SAME keying + reset discipline as NAVCACHE/PMCACHE: a key
  // mismatch drops the cache; scrubbing, zooming and master/view switches keep it.
  function tlDatasetKey(){
    var dates = (H.trend && H.trend.dates) || [];
    return state.tlGran + ":" + state.tlBucket
      + ":" + dates.length + ":" + (dates.length ? dates[dates.length-1] : "");
  }
  // Per-master change counts per snapshot: chg[k] = how many glyphs' EFFECTIVE colour
  // (hidden keys read as -1, same normalisation as stateAt) differs between dates[k-1]
  // and dates[k]; chg[0] = 0 (no predecessor). Walked straight off the sparse
  // journeyIndex events — O(events + dates) per master, ONCE — instead of
  // reconstructing and diffing a full per-glyph snapshot per date per render.
  // versionNav and the activity calendar read it on every re-render. Events that
  // cancel out between two snapshots (away and back inside one gap) count as no
  // change, exactly like diffing the snapshots themselves.
  var CHGCACHE = {}, CHGCACHE_KEY = "";
  function changeCounts(masterId){
    var key = tlDatasetKey();
    if (CHGCACHE_KEY !== key){ CHGCACHE = {}; CHGCACHE_KEY = key; }
    if (CHGCACHE[masterId]) return CHGCACHE[masterId];
    var dates = (H.trend && H.trend.dates) || [];
    var chg = dates.map(function(){ return 0; });
    var perMaster = (H.journeyIndex && H.journeyIndex[masterId]) || {};
    for (var name in perMaster){
      var events = perMaster[name];
      // eff = the glyph's value once this bucket's events are applied; committed = its
      // value at the previous snapshot; undefined = not in the snapshot yet, so a glyph
      // APPEARING (first event, even uncoloured) counts as a change. Explicit undefined
      // inits: vars are function-scoped and must not leak across glyphs.
      var bp = 0, cur = -1, eff = undefined, committed = undefined;
      for (var i=0;i<events.length;i++){
        while (bp < dates.length && dates[bp] < events[i][0]){ bp++; }
        if (bp >= dates.length) break;             // event after the last snapshot: never visible
        if (bp !== cur){                           // close the previous snapshot's event group
          if (cur > 0 && eff !== committed){ chg[cur]++; }
          if (cur !== -1){ committed = eff; }
          cur = bp;
        }
        var k = events[i][1];
        eff = (k !== -1 && H.order.indexOf(String(k)) === -1) ? -1 : k;
      }
      if (cur > 0 && eff !== committed){ chg[cur]++; }
    }
    return (CHGCACHE[masterId] = chg);
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

  // (The #6 hover crosshair + floating read-out popover were removed. The chart's only
  //  pointer interaction is now click-to-pick-a-moment; hover shows nothing.)

  // Map a client X to the NEAREST snapshot index. The forward map is
  // X(off)=pl+off/lastOff*iw drawn into the viewBox, so we only need the snapshot X
  // anchors (data-snaps) and the box->viewBox ratio — no interpolation, series is discrete.
  function chartIndexFromClient(svg, clientX){
    var snaps; try { snaps = JSON.parse(svg.getAttribute("data-snaps")||"[]"); } catch(e){ snaps = []; }
    if (!snaps.length){ return -1; }
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
  // Click anywhere on the chart to PICK that moment (scrub): the per-master colour discs
  // and the category/script lanes recompute at that snapshot. Map the windowed index back
  // to the full series. Clicking the latest point clears the scrub (back to live).
  function chartClick(evt){
    var svg = evt.target.closest && evt.target.closest(".tl-chart");
    if (!svg){ return; }
    var idx = chartIndexFromClient(svg, evt.clientX); if (idx < 0){ return; }
    scrubSet(viewBounds()[0] + idx);
  }
  // Keyboard: Left/Right step the picked moment by one snapshot while the chart is focused.
  function chartKey(evt){
    if (evt.key!=="ArrowLeft" && evt.key!=="ArrowRight"){ return; }
    var svg = evt.target.closest && evt.target.closest(".tl-chart"); if (!svg){ return; }
    var dates = (H.trend && H.trend.dates) || []; if (dates.length < 2){ return; }
    evt.preventDefault();
    var step = evt.key==="ArrowRight" ? 1 : -1;
    scrubSet(Math.max(0, Math.min(dates.length-1, scrubIndex() + step)));
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

  // ----- Before/After switch + "play" auto-toggle ----------------------------
  var baTimer = null;
  function baSyncUI(){
    var segs = document.querySelectorAll(".ba-seg"), i;
    for (i=0;i<segs.length;i++){
      var on = (segs[i].getAttribute("data-ba")==="before") === state.before;
      segs[i].classList.toggle("on", on); segs[i].setAttribute("aria-pressed", on);
    }
    var pb = document.querySelector(".ba-play");
    if (pb){ pb.classList.toggle("on", !!state.baPlaying);
      pb.setAttribute("aria-pressed", !!state.baPlaying);
      pb.textContent = state.baPlaying ? "􀊗" : "􀊕"; }   // pause while playing, else play
  }
  function baStopPlay(){ if (baTimer){ clearInterval(baTimer); baTimer = null; } state.baPlaying = false; baSyncUI(); }
  function baStartPlay(){
    if (baTimer) return;
    state.baPlaying = true; baSyncUI();
    // Flip before<->after every second; self-stops if the control leaves the DOM (view change).
    baTimer = setInterval(function(){
      if (!document.querySelector(".ba-play")){ baStopPlay(); return; }
      state.before = !state.before; baSyncUI(); applyBeforeAfter();
    }, 1000);
  }

  // Count-up a lane's percentage from -> to (uses the rAF timestamp, no clock).
  function tweenNumber(el, from, to, dur){
    requestAnimationFrame(function step(ts){
      if (step.t0 == null){ step.t0 = ts; }
      var p = Math.min(1, (ts - step.t0) / dur), ease = p*p*(3-2*p);
      el.textContent = Math.round(from + (to - from) * ease) + "%";
      if (p < 1){ requestAnimationFrame(step); }
    });
  }
  // Animate the category/script lane numbers whenever they change (picking a different
  // moment on the chart, or focusing a master). Each render carries the new value in
  // data-to; we tween from the last shown value cached per lane key. Reduced-motion /
  // headless snap straight to the value. Zoom drags don't change the numbers, so they
  // never trigger a tween.
  function animateLaneNumbers(){
    var anim = !window.__cfdNoAnim && !(window.matchMedia && window.matchMedia("(prefers-reduced-motion:reduce)").matches);
    var els = document.querySelectorAll(".timeline .tl-lane-pct[data-lanekey]");
    for (var i = 0; i < els.length; i++){
      var el = els[i], key = el.getAttribute("data-lanekey"), to = parseInt(el.getAttribute("data-to"), 10) || 0;
      var from = (key in laneNumCache) ? laneNumCache[key] : to;
      laneNumCache[key] = to;
      if (!anim || from === to){ el.textContent = to + "%"; continue; }
      el.textContent = from + "%";
      tweenNumber(el, from, to, 460);
    }
  }

  // Count-up the big Overview ring's % number. On the first Overview paint (intro) it
  // sweeps 0 -> value in step with the ring's draw-in; afterwards it tweens only when the
  // value actually changes (focus/scrub) and snaps under reduced-motion / headless.
  var ringNumCache = null;
  function animateRingNumber(intro){
    var el = document.querySelector(".overall .ov-ring-t[data-to]");
    if (!el) return;
    var to = parseInt(el.getAttribute("data-to"), 10) || 0;
    var anim = !window.__cfdNoAnim && !(window.matchMedia && window.matchMedia("(prefers-reduced-motion:reduce)").matches);
    var from = intro ? 0 : (ringNumCache == null ? to : ringNumCache);
    ringNumCache = to;
    if (!anim || from === to){ el.textContent = to + "%"; return; }
    el.textContent = from + "%";
    tweenNumber(el, from, to, intro ? 800 : 460);
  }

  // On a Global<->Focus master switch, fade ONLY the headline ring + its legend. Everything
  // else (category-coverage bars, glyph cells, timeline lanes) updates IN PLACE — no flash —
  // with its own count-ups / sparkline morphs handling the value changes. Each faded element
  // is fresh from the innerHTML rebuild, so adding the keyframe class plays it once. Silenced
  // under reduced-motion / headless.
  function fadeData(){
    if (noAnim()) return;
    var body = document.getElementById("cfd-body"); if (!body) return;
    var els = body.querySelectorAll(".ov-ring,.ov-legend");
    for (var i=0;i<els.length;i++){ els[i].classList.add("cfd-fade"); }
  }
  function noAnim(){
    return !!window.__cfdNoAnim ||
      (window.matchMedia && window.matchMedia("(prefers-reduced-motion:reduce)").matches);
  }
  // ----- lane sparkline morph (scrub) ----------------------------------------
  // Tween each lane's polyline from its PREVIOUS shape to the new one when the picked
  // moment changes, so the line reshapes smoothly between two time points instead of
  // snapping. Points are cached per data-spark key. sparkPrev is refreshed every render
  // (even with animate=false) so the next morph starts from what's on screen.
  function _parsePts(s){
    return (s||"").trim().split(/\s+/).map(function(p){ var c=p.split(","); return [parseFloat(c[0]), parseFloat(c[1])]; })
      .filter(function(p){ return !isNaN(p[0]) && !isNaN(p[1]); });
  }
  function _ptsStr(a){ return a.map(function(p){ return p[0].toFixed(1)+","+p[1].toFixed(1); }).join(" "); }
  function _resample(pts, count){
    if (pts.length === count) return pts.slice();
    var out = [], last = pts.length - 1;
    for (var i=0;i<count;i++){
      var t = (count<2?0:i/(count-1))*last, lo = Math.floor(t), hi = Math.min(lo+1, last), f = t-lo;
      out.push([pts[lo][0]+(pts[hi][0]-pts[lo][0])*f, pts[lo][1]+(pts[hi][1]-pts[lo][1])*f]);
    }
    return out;
  }
  function _tweenSpark(poly, a, b, finalPts){
    var dur = 380, start = null;
    poly.setAttribute("points", _ptsStr(a));      // start from the old shape (no flash of the target)
    function frame(ts){
      if (start == null) start = ts;
      var k = Math.min(1, (ts - start)/dur), e = 1 - Math.pow(1-k, 3);   // easeOutCubic
      if (k >= 1){ poly.setAttribute("points", _ptsStr(finalPts)); return; }
      poly.setAttribute("points", _ptsStr(a.map(function(p,i){ return [p[0]+(b[i][0]-p[0])*e, p[1]+(b[i][1]-p[1])*e]; })));
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }
  function morphSparks(animate){
    var polys = document.querySelectorAll(".tl-lane-spark polyline[data-spark]");
    Array.prototype.forEach.call(polys, function(poly){
      var key = poly.getAttribute("data-spark");
      var target = _parsePts(poly.getAttribute("points"));
      var prev = sparkPrev[key];
      sparkPrev[key] = target;                     // always refresh, so the next morph is from what's shown
      if (!animate || noAnim() || !prev || prev.length < 2 || target.length < 2) return;
      if (_ptsStr(prev) === _ptsStr(target)) return;
      var npts = Math.max(prev.length, target.length, 2);
      _tweenSpark(poly, _resample(prev, npts), _resample(target, npts), target);
    });
  }
  function update(){
    hideTip();
    barsAnim = !introPlayed;                    // fill the colour bar once on first paint, never on master switches
    introPlayed = true;
    var masterChanged = (lastRenderMaster !== "__cfd_init__") && (state.master !== lastRenderMaster);
    lastRenderMaster = state.master;
    var bodyEl = document.getElementById("cfd-body");
    bodyEl.innerHTML = renderBody();
    if (masterChanged){                          // Global<->Focus switch: fade ONLY the data panels
      fadeData();                                // the disc tower runs its own per-disc focus crossfade
    }
    morphSparks(scrubAnim);                       // tween lane sparkline shapes on scrub (always refresh the cache)
    document.documentElement.setAttribute("data-theme", state.theme);
    var tl = document.getElementById("cfd-timeline"); if (tl) tl.setAttribute("aria-pressed", state.view==="timeline");
    var ov = document.getElementById("cfd-overview"); if (ov) ov.setAttribute("aria-pressed", state.view==="tabs");
    paintScriptCards();
    animateLaneNumbers();                        // count-up the lane %s when the picked moment / focus changes
    animateRingNumber(barsAnim);                 // count-up the Overview ring %; sweeps 0->value on first paint
    scrubAnim = false;                           // consumed: the scrub animation runs once per picked moment
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
    // countFor / uncoloredFor / countedTotal always exclude non-exporting glyphs,
    // so an export always matches the percentages on screen.
    var rows = [], total = countedTotal();
    H.masters.forEach(function(m){
      H.steps.forEach(function(s){
        var c = countFor(m, s.key);
        rows.push({master:m.name, step:s.key, label:s.label, count:c, total:total, pct:pct(c,total)});
      });
      var un = uncoloredFor(m);
      rows.push({master:m.name, step:"None", label:H.noneLabel, count:un, total:total, pct:pct(un,total)});
    });
    return rows;
  }
  function csvCell(value){
    var s = String(value==null ? "" : value);
    return /[",\n]/.test(s) ? '"'+s.replace(/"/g,'""')+'"' : s;
  }
  function exportCSV(){
    var lines = [["Family",H.family],["File",H.fileName],["Version",H.version],
                 ["Generated",H.generated],["Glyphs",H.glyphTotal]]
      .map(function(r){ return csvCell(r[0])+","+csvCell(r[1]); });
    lines.push("", ["Master","Step","Label","Count","Total","Percent"].join(","));
    exportRows().forEach(function(r){
      lines.push([r.master,r.step,r.label,r.count,r.total,r.pct].map(csvCell).join(","));
    });
    return lines.join("\n");
  }
  function exportJSON(){
    // countFor / uncoloredFor / countedTotal always exclude non-exporting glyphs,
    // so the JSON matches the on-screen numbers (raw m.counts passthrough when
    // the font has nothing to exclude).
    return JSON.stringify({
      family:H.family, fileName:H.fileName, version:H.version,
      generated:H.generated, glyphTotal:H.glyphTotal, steps:H.steps,
      nonExporting:H.nonExporting||[],
      masters:H.masters.map(function(m){
        var counts = {}; (H.order||[]).forEach(function(k){ counts[k] = countFor(m,k); });
        return { id:m.id, name:m.name, counts:counts, uncolored:uncoloredFor(m),
                 started:startedOf(m), total:countedTotal() };
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
    // The active scope via covRows(): focused master -> that master's rows; global
    // (no focus) -> the font-wide merge — same as the on-screen category card, so
    // printing from the unfocused overview no longer yields an empty section.
    var rows = covRows("byCategory");
    if (!rows.length) return '<p class="empty">No coverage data.</p>';
    return '<div class="cov-rows">'+rows.map(function(r){
      var count = (r.glyphs != null ? r.glyphs : r.total);
      return '<div class="cov-row"><span class="cov-name" title="'+esc(r.key)+'">'+esc(r.key)+'</span>'
        + covStacked(r) + '<span class="num">'+count+'</span></div>';
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
    add("psec-coverage", "Coverage by category", printCoverageRows());
    add("psec-timeline", "Progress over time", timelineView());
    return '<section class="pcover"><div class="pcover-ttl">'+esc(H.family)+'</div>'
      + '<div class="pcover-sub">AZ Colorflow report · '+esc(H.fileName)+' · v'+esc(H.version)+' · '+esc(H.generated)+'</div>'
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
    // Switching Overview <-> Timeline KEEPS the colour focus (it's restored when you return
    // to Overview); only the chart draw-in is armed when entering Timeline.
    function toggleView(name){
      var v = state.view===name ? "tabs" : name;
      if (v==="timeline"){ tlChartShouldAnim = true; }   // draw-in the chart on entering Timeline
      state.view = v; update();
    }
    document.getElementById("cfd-overview").addEventListener("click", function(){ state.view = "tabs"; state.master = null; update(); });
    document.getElementById("cfd-timeline").addEventListener("click", function(){ if (!timelineLock()) toggleView("timeline"); });
    document.getElementById("cfd-export").addEventListener("click", openExport);
    document.addEventListener("keydown", function(e){
      if (e.key==="Escape"){ closeExport(); closeJourney(); if (state.focus!==null){ setFocus(null); } }
    });
    var bodyEl = document.getElementById("cfd-body");
    // Glyph-cell size slider: resize the grid LIVE (set the CSS var on the .heat section
    // directly) while dragging, so there's no full re-render per input tick; state.cellSize
    // persists the choice for the next render.
    bodyEl.addEventListener("input", function(e){
      var sz = e.target.closest && e.target.closest("[data-cellsize]");
      if (!sz) return;
      var v = parseInt(sz.value, 10) || 40;
      state.cellSize = v;
      var heat = sz.closest(".heat"); if (heat){ heat.style.setProperty("--cell-min", v+"px"); }
    });
    bodyEl.addEventListener("mouseover", function(e){
      var cell = e.target.closest(".heat .cell"); if (cell) showTip(cell.getAttribute("data-glyph"), e.clientX, e.clientY);
    });
    bodyEl.addEventListener("mouseout", function(e){
      if (e.target.closest(".heat .cell")) hideTip();
    });
    bodyEl.addEventListener("click", function(e){
      var tab = e.target.closest(".tab"); if (tab){ state.master = tab.getAttribute("data-m"); laneSparkShouldAnim = true; update(); return; }
      var ox = e.target.closest("[data-ovexpand]"); if (ox){ var ok=ox.getAttribute("data-ovexpand"); state.ovExpand[ok]=!state.ovExpand[ok]; update(); return; }
      var hs = e.target.closest("[data-hsort]"); if (hs){ segswAnimKey = "hsort"; state.heatSort = hs.getAttribute("data-hsort"); update(); return; }
      var hr = e.target.closest("[data-heatrecent]"); if (hr){ state.heatRecent = !state.heatRecent; update(); return; }
      var tp = e.target.closest("[data-tlpane]"); if (tp){ segswAnimKey = "tlpane"; state.tlPane = tp.getAttribute("data-tlpane"); state.tlScrub = null; update(); return; }
      var fn = e.target.closest("[data-funnel]"); if (fn){ state.funnelOpen = (state.funnelOpen === false); update(); return; }
      var oc = e.target.closest("[data-oc]"); if (oc){ var ok=oc.getAttribute("data-oc"); state.ocOpen[ok]=!state.ocOpen[ok]; update(); return; }
      var cr = e.target.closest(".lb-row[data-m]"); if (cr){ var cid=cr.getAttribute("data-m"); state.master=(state.master===cid)?null:cid; state.focus = null; laneSparkShouldAnim = true; update(); return; }
      var sp = e.target.closest("[data-tlspan]"); if (sp){ segswAnimKey = "tlspan"; setTlSpan(sp.getAttribute("data-tlspan")); return; }
      var tg = e.target.closest("[data-tlgrantoggle]"); if (tg){ setGranularity(state.tlGran==="time" ? "save" : "time"); return; }
      var tb = e.target.closest("[data-tlbucket]"); if (tb){ setBucket(tb.getAttribute("data-tlbucket")); return; }
      var cnv = e.target.closest("[data-calnav]"); if (cnv){
        calMonthRef();                                   // ensure calY/calM seeded
        state.calM += parseInt(cnv.getAttribute("data-calnav"),10);
        while (state.calM < 0){ state.calM += 12; state.calY--; }
        while (state.calM > 11){ state.calM -= 12; state.calY++; }
        update(); return; }
      var cd = e.target.closest("[data-calday]"); if (cd){
        var ci = parseInt(cd.getAttribute("data-calday"),10);
        if (state.view !== "timeline"){ state.view = "timeline"; state.focus = null; }  // hop to the chart
        scrubSet(ci); return; }                                       // pick that moment (disc + lanes follow)
      var fc = e.target.closest("[data-fclear]"); if (fc){ setFocus(null); return; }
      var vn = e.target.closest("[data-vnav]"); if (vn){ e.preventDefault(); vnavShouldAnim = true; scrubSet(parseInt(vn.getAttribute("data-vnav"),10)); return; }
      var jr = e.target.closest("[data-jglyph]"); if (jr){ openJourney(jr.getAttribute("data-jglyph")); return; }
      var jc = e.target.closest(".heat .cell"); if (jc && (e.metaKey || e.ctrlKey)){ e.preventDefault(); openJourney(jc.getAttribute("data-glyph")); return; }
      var bseg = e.target.closest(".ba-seg");
      if (bseg){ e.preventDefault(); baStopPlay(); state.before = (bseg.getAttribute("data-ba")==="before"); baSyncUI(); applyBeforeAfter(); return; }
      var bplay = e.target.closest(".ba-play");
      if (bplay){ e.preventDefault(); if (state.baPlaying){ baStopPlay(); } else { baStartPlay(); } return; }
    });
    // Click the chart to PICK a moment (scrub -> sidebar discs + lanes follow); the
    // left/right arrow keys step the picked moment while the chart is focused.
    bodyEl.addEventListener("pointerdown", chartClick);
    bodyEl.addEventListener("keydown", chartKey);
    // Range navigator: drag a handle/window/scrim to zoom the main chart live; arrow keys
    // nudge a focused handle; double-clicking the navigator resets to the full history.
    bodyEl.addEventListener("pointerdown", navDrag);
    bodyEl.addEventListener("keydown", navKey);
    bodyEl.addEventListener("dblclick", function(e){
      if (e.target.closest && e.target.closest(".tl-nav")){ navReset(); }
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
    // Empty disc ~ page bg (--track). Read per theme, not once: data-theme flips after
    // initTower() runs, and a cached dark value painted black discs in light mode.
    var emptyFillCache = {};
    function emptyFill(){
      var t = document.documentElement.getAttribute("data-theme") || "";
      if (!emptyFillCache[t]) emptyFillCache[t] = (getComputedStyle(document.documentElement).getPropertyValue("--track")||"").trim() || "#15171c";
      return emptyFillCache[t];
    }
    var W = cv.width, Hc = cv.height, FS = 320;
    // HiDPI: supersample every backing store by devicePixelRatio (capped at 3) while
    // keeping all geometry in CSS-pixel units. fit() recomputes dpr on resize; the
    // offscreen builders below read this same closure var. dpr=1 reproduces 1x exactly.
    var dpr = Math.min(window.devicePixelRatio || 1, 3);
    var DISC_ALPHA = 0.95, tilt = 0.5, trimVal = 0.5, opacityVal = 0.37;
    var DISC_BRIGHT = 1.2;  // every lit disc rendered 20% lighter (global)
    var FOCUS_GLOW = 1.4;   // selected disc: +40% halo glow on top
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
    // Per-colour glyph counts for a master. Scrub-aware: when a moment is picked on the
    // Timeline chart (state.tlScrub set), reconstruct that master's colour state at the
    // picked snapshot via stateAt — so clicking the graph spins these discs back in time.
    // Otherwise the live (current) label keys.
    function countsOf(m){
      var c = [0,0,0,0,0,0,0,0,0,0,0,0], i;
      if (state.tlScrub != null){
        var dates = (H.trend && H.trend.dates) || [], date = dates[scrubIndex()];
        if (date != null){
          var snap = stateAt(m.id, date);
          for (var name in snap){ var sk = snap[name]; if (sk>=0 && sk<12) c[sk]++; }
          return c;
        }
      }
      var keys = m.keys || [];
      for (i=0;i<keys.length;i++){ var k=keys[i]; if (k>=0 && k<12) c[k]++; }
      return c;
    }
    // Uncoloured share consistent with countsOf: at a scrubbed moment it's whatever the
    // glyph total minus the coloured count is; live it's the master's stored uncolored.
    function uncoloredOf(m, counts){
      if (state.tlScrub != null){
        var s=0; for (var i=0;i<12;i++){ s+=counts[i]; }
        return Math.max(0, (H.glyphTotal||0) - s);
      }
      return m.uncolored || 0;
    }
    var UNCOL = "hsl(225,8%,4%)";   // dark neutral grey for the uncoloured share
    function buildField(counts, uncolored, grey){
      var off=document.createElement("canvas"); off.width=off.height=Math.round(FS*dpr);
      var g=off.getContext("2d"); g.setTransform(dpr,0,0,dpr,0,0);
      var cx=FS/2, cy=FS/2, R=FS*0.46, sum=0, i;
      for (i=0;i<12;i++) sum+=counts[i];
      var total=sum+uncolored;
      if (total){
        // one wedge per present colour (hue) + the uncoloured share (grey), all
        // proportional to the master's glyph total so uncoloured glyphs show too
        var segs=[];
        for (i=0;i<12;i++){ if(counts[i]>0) segs.push([counts[i]/total, grey?"#3a3f49":slotColor(i)]); }
        if (uncolored>0) segs.push([uncolored/total, grey?"#23262d":UNCOL]);
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
      if (CTX_FILTER_OK){
        bg.filter="blur("+Math.round(FS*0.125)+"px) saturate(1.6) brightness(0.92)"; bg.drawImage(off,0,0,FS,FS); bg.filter="none";
      } else { cssSafeBlur(off, bg, FS, Math.round(FS*0.125)); }
      bg.globalCompositeOperation="destination-in";
      bg.fillStyle="#000"; bg.beginPath(); bg.arc(FS/2,FS/2,FS*0.5,0,7); bg.fill();
      bg.globalCompositeOperation="source-over";
      return bl;
    }
    // When a colour is focused (clicked in a progress bar), each disc shows only
    // that colour's share; everything else folds into the uncoloured grey. fk<0
    // or null restores the full label distribution.
    function focusedCounts(m, fk){
      var c = countsOf(m), unc = uncoloredOf(m, c);
      if (fk==null) return { counts:c, uncolored:unc };                                       // no focus -> full distribution
      if (fk<0 || fk>11) return { counts:[0,0,0,0,0,0,0,0,0,0,0,0], uncolored:unc };          // None focused -> grey share only
      var only=[0,0,0,0,0,0,0,0,0,0,0,0]; only[fk]=c[fk];
      return { counts:only, uncolored:(H.glyphTotal||0)-c[fk] };                               // one colour -> its wedge + grey rest
    }
    var FIELDS, EMPTY;
    function buildFields(fk){
      FIELDS = H.masters.map(function(m){ var d=focusedCounts(m,fk); return buildField(d.counts, d.uncolored); });
      EMPTY = H.masters.map(function(m){ var d=focusedCounts(m,fk), s=0, i; for(i=0;i<12;i++) s+=d.counts[i]; return (s+d.uncolored)===0; });
    }
    var curFocus = (state.focus==null?null:state.focus);
    var curScrub = state.tlScrub;   // rebuild the disc fields when the picked moment changes
    buildFields(curFocus);
    // Smoothly crossfade each disc's colour field old -> new when the focused colour or
    // picked moment changes, instead of snapping. Reduced-motion / headless = instant.
    var TOWER_ANIM = !window.__cfdNoAnim && !(window.matchMedia && window.matchMedia("(prefers-reduced-motion:reduce)").matches);
    // ----- Colour Bloom opening intro (variant 4: smootherstep, ~760ms/disc, ~120ms stagger) -----
    // Each disc starts as a blurry grey blank; its colour BLOOMS in via a soft cross-fade (no
    // hard conic wipe / cut line), staggered top->bottom down the stack. Plays ONCE on open, frame-paced like the spin ramp
    // (~60fps). Reduced-motion / headless: skipped entirely (discs render full colour at once).
    var GREYFIELDS = H.masters.map(function(m){ var d=focusedCounts(m,null); return buildField(d.counts,d.uncolored,true); });
    function smootherstep(t){ t=t<0?0:(t>1?1:t); return t*t*t*(t*(t*6-15)+10); }
    var INTRO_PER = 23, INTRO_STAG = 4;            // 2x faster: ~380ms per disc, ~65ms stagger at 60fps
    var introFrame = 0, introDone = !TOWER_ANIM;   // reduced-motion: no intro, full colour immediately
    function introReveal(i){ if (introDone) return 1; return smootherstep((introFrame - i*INTRO_STAG)/INTRO_PER); }
    var PREV_FIELDS = null, morph = 1, MORPH_STEP = 0.044;   // colour dissolve, 2x faster
    var mtmp = document.createElement("canvas"); mtmp.width = mtmp.height = Math.round(FS*dpr);
    var mctx = mtmp.getContext("2d");
    function fieldFor(i){
      if (morph >= 1 || !PREV_FIELDS || !PREV_FIELDS[i]) return FIELDS[i];
      var nf = FIELDS[i];
      if (mtmp.width !== nf.width || mtmp.height !== nf.height){ mtmp.width = nf.width; mtmp.height = nf.height; }
      var t = morph*morph*(3-2*morph);                       // smoothstep dissolve
      mctx.clearRect(0,0,mtmp.width,mtmp.height);
      mctx.globalAlpha = 1; mctx.drawImage(PREV_FIELDS[i],0,0,mtmp.width,mtmp.height);   // old colours beneath
      mctx.globalAlpha = t; mctx.drawImage(nf,0,0,mtmp.width,mtmp.height);               // new colours fade in
      mctx.globalAlpha = 1;
      return mtmp;
    }
    var FROST = (function(){
      var c=document.createElement("canvas"); c.width=c.height=Math.round(FS*dpr); var g=c.getContext("2d");
      g.setTransform(dpr,0,0,dpr,0,0);
      // white frost sparkle
      for (var k=0;k<1600;k++){ var x=Math.random()*FS,y=Math.random()*FS,r=Math.random()*1.6+0.3;
        g.fillStyle="rgba(255,255,255,"+(Math.random()*0.07)+")"; g.beginPath(); g.arc(x,y,r,0,7); g.fill(); }
      // fine dark dust grains interleaved so the surface reads as frozen/dusty texture
      // rather than only sparkle — finer + fainter than the frost, kept subtle.
      for (var kd=0;kd<1100;kd++){ var dx=Math.random()*FS,dy=Math.random()*FS,dr=Math.random()*0.9+0.2;
        g.fillStyle="rgba(0,0,0,"+(Math.random()*0.05+0.008)+")"; g.beginPath(); g.arc(dx,dy,dr,0,7); g.fill(); }
      var o=document.createElement("canvas"); o.width=o.height=Math.round(FS*dpr); var og=o.getContext("2d");
      og.setTransform(dpr,0,0,dpr,0,0);
      if (CTX_FILTER_OK){ og.filter="blur(0.6px)"; og.drawImage(c,0,0,FS,FS); og.filter="none"; }
      else { og.drawImage(c,0,0,FS,FS); }
      return o;
    })();
    var buf=document.createElement("canvas"); buf.width=Math.round(W*dpr); buf.height=Math.round(Hc*dpr); var bctx=buf.getContext("2d");
    bctx.setTransform(dpr,0,0,dpr,0,0);

    function paintDisc(g,fA,cx,cy,rx,ry,holeFrac,glow,empty,greyA,reveal){
      if (glow===undefined) glow=1;
      if (reveal===undefined) reveal=1;
      if (empty){   // no colours: a near-background tone at lower opacity (mixes with the bg)
        g.save(); g.translate(cx,cy); g.scale(1,ry/rx);
        g.globalAlpha=0.6; g.fillStyle=emptyFill(); g.beginPath(); g.arc(0,0,rx,0,7); g.fill(); g.globalAlpha=1;
        g.restore();
        return;
      }
      var o=rx*1.14;
      // dreamy/shiny finish at HALF the original strength (all highlight alphas
      // halved) layered over the now-blurrier colour field.
      g.save(); g.translate(cx,cy); g.scale(1,ry/rx); g.rotate(rot);
      if (CTX_FILTER_OK){   // the halo is pure blur — skip it (not a sharp ghost) on WebKit
        var halo=[[1.006,3,0.11],[1.025,6,0.07],[1.06,12,0.04]];
        for (var h=0;h<halo.length;h++){ g.globalAlpha=halo[h][2]*glow*reveal; g.filter="blur("+halo[h][1]+"px)"; var hh=rx*halo[h][0]; g.drawImage(fA,-hh,-hh,hh*2,hh*2); }
        g.filter="none"; g.globalAlpha=1;
      }
      g.restore();
      g.save(); g.translate(cx,cy); g.scale(1,ry/rx); g.rotate(rot);
      g.beginPath(); g.arc(0,0,rx,0,7); g.clip();
      // a focused disc renders the OTHERS as dark matte greyscale (glow<1 == not the
      // selected master): fully desaturate + darken to charcoal. Browser path only —
      // WebKit keeps the existing dim.
      if (CTX_FILTER_OK){
        var desat = 1 - Math.max(0, Math.min(1, glow));   // 1 for non-focused -> greyscale
        var filt = "";
        if (desat>0) filt = "saturate("+(1-desat).toFixed(3)+") brightness("+(1-desat*0.5).toFixed(3)+")";
        else filt = "brightness("+DISC_BRIGHT.toFixed(3)+")";   // every lit disc 20% lighter (global)
        if (filt) g.filter=filt;
      }
      g.globalAlpha=DISC_ALPHA;
      if (reveal<1 && greyA){            // Colour Bloom intro: cross-fade the already-blurry grey
        // base INTO the blurry colour field — a soft bloom, NOT a hard conic wedge/cut line.
        // reveal is smootherstep-eased, so the colour blooms in evenly with no edgy sweep.
        g.drawImage(greyA,-o,-o,o*2,o*2);
        if (reveal>0){ g.globalAlpha=DISC_ALPHA*reveal; g.drawImage(fA,-o,-o,o*2,o*2); }
      } else { g.drawImage(fA,-o,-o,o*2,o*2); }
      g.filter="none"; g.globalAlpha=1; g.restore();
      g.save(); g.translate(cx,cy); g.scale(1,ry/rx); g.beginPath(); g.arc(0,0,rx,0,7); g.clip();
      g.fillStyle="rgba(255,255,255,0.05)"; g.beginPath(); g.arc(0,0,rx,0,7); g.fill();
      g.globalAlpha=0.45; g.drawImage(FROST,-rx,-rx,rx*2,rx*2); g.globalAlpha=1;
      var sheen=g.createLinearGradient(0,-rx,0,rx);
      sheen.addColorStop(0,"rgba(0,0,0,0.11)"); sheen.addColorStop(0.34,"rgba(255,255,255,0.01)");
      sheen.addColorStop(0.66,"rgba(255,255,255,0.02)"); sheen.addColorStop(1,"rgba(255,255,255,0.09)");
      g.fillStyle=sheen; g.beginPath(); g.arc(0,0,rx,0,7); g.fill();
      var hot=g.createRadialGradient(0,rx*0.42,0,0,rx*0.42,rx*0.8);
      hot.addColorStop(0,"rgba(255,255,255,0.075)"); hot.addColorStop(1,"rgba(255,255,255,0)");
      g.fillStyle=hot; g.beginPath(); g.arc(0,0,rx,0,7); g.fill();
      if (holeFrac>0){ var hr=rx*0.26; g.globalCompositeOperation="destination-out";
        var pg=g.createRadialGradient(0,0,0,0,0,hr); pg.addColorStop(0,"rgba(0,0,0,1)"); pg.addColorStop(0.94,"rgba(0,0,0,1)"); pg.addColorStop(1,"rgba(0,0,0,0)");
        g.fillStyle=pg; g.beginPath(); g.arc(0,0,hr,0,7); g.fill(); g.globalCompositeOperation="source-over"; }
      g.restore();
      g.save(); g.translate(cx,cy); g.scale(1,ry/rx);
      var rim=g.createLinearGradient(0,-rx,0,rx); rim.addColorStop(0,"rgba(0,0,0,0.12)"); rim.addColorStop(0.5,"rgba(255,255,255,0.025)"); rim.addColorStop(1,"rgba(255,255,255,0.16)");
      g.strokeStyle=rim; g.lineWidth=2; g.beginPath(); g.arc(0,0,rx*0.992,0,7); g.stroke(); g.restore();
    }
    function shadowInto(g,cx,cy,rx,ry){
      // a deeper, wider drop shadow under each disc so the stack reads with clear
      // separation between discs (the disc below catches a stronger shadow)
      g.save(); g.translate(cx,cy+ry*0.62); g.scale(1,ry/rx);
      var sh=g.createRadialGradient(0,0,0,0,0,rx*1.12); sh.addColorStop(0,"rgba(0,0,0,0.28)"); sh.addColorStop(0.6,"rgba(0,0,0,0.14)"); sh.addColorStop(1,"rgba(0,0,0,0)");
      g.fillStyle=sh; g.beginPath(); g.arc(0,0,rx*1.12,0,7); g.fill(); g.restore();
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
      // Ease each disc's trim toward its target (0 = lit, 1 = dimmed) so changing focus FADES:
      // the previously-selected disc dims out and the newly-selected disc lights in, instead of
      // the whole tower flashing. Reduced-motion / headless snaps instantly.
      var FOCUS_STEP = 0.08;   // gentle ease (prev disc dims out / new lights in, slower)
      for (var i=0;i<M;i++){
        var tgt = (sel<0 || i===sel) ? 0 : 1;
        if (!TOWER_ANIM){ focusAmt[i] = tgt; }
        else { var df = tgt - focusAmt[i]; focusAmt[i] = (Math.abs(df) < 0.005) ? tgt : (focusAmt[i] + df*FOCUS_STEP); }
      }
      var rx=Math.min(92, W*0.42), ry=rx*tilt;
      var topY=ry+16, botPad=ry+12;
      var dz=VISIBLE>1?Math.min(51,(Hc-topY-botPad)/(VISIBLE-1)):0, cx=W/2;   // ~15% tighter stack
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
        for (var k=0;k<idxs.length;k++){ var ii=idxs[k], cyy=cyOf(ii); if(!EMPTY[ii]) shadowInto(bctx,cx,cyy,rx,ry); paintDisc(bctx,fieldFor(ii),cx,cyy,rx,ry,1,0,EMPTY[ii],GREYFIELDS[ii],introReveal(ii)); }
        bctx.save(); bctx.globalCompositeOperation="source-atop"; bctx.fillStyle="rgba(0,0,0,"+trimVal+")"; bctx.fillRect(0,0,W,Hc); bctx.restore();
        edgeFade(bctx);
        ctx.save(); ctx.globalAlpha=opacityVal; ctx.drawImage(buf,0,0,W,Hc); ctx.restore();
      }
      function focusDisc(ii){ var amt=focusAmt[ii], cyy=cyOf(ii);
        var glowV = (sel>=0 && ii===sel) ? FOCUS_GLOW : (1-amt);   // selected disc: +40% halo glow (halo alpha *glow)
        bctx.clearRect(0,0,W,Hc); if(!EMPTY[ii]) shadowInto(bctx,cx,cyy,rx,ry); paintDisc(bctx,fieldFor(ii),cx,cyy,rx,ry,1,glowV,EMPTY[ii],GREYFIELDS[ii],introReveal(ii));
        var trim=amt*trimVal; if (trim>0){ bctx.save(); bctx.globalCompositeOperation="source-atop"; bctx.fillStyle="rgba(0,0,0,"+trim+")"; bctx.fillRect(0,0,W,Hc); bctx.restore(); }
        edgeFade(bctx);
        ctx.save(); ctx.globalAlpha=1-amt*(1-opacityVal); ctx.drawImage(buf,0,0,W,Hc); ctx.restore();
      }
      if (sel<0){
        for (var n=M-1;n>=0;n--){ if (vis(n)) focusDisc(n); }   // no selection: every disc full
      } else {
        // Back-to-front: fully-dimmed discs composite together (one layer, no overlap seams);
        // the selected disc AND any still-transitioning disc (focusAmt mid-way — e.g. the one
        // just deselected) render individually via focusDisc so their fade is visible.
        var pend = [];
        var flushPend = function(){ if (pend.length){ group(pend); pend=[]; } };
        for (var n2=M-1;n2>=0;n2--){
          if (!vis(n2)) continue;
          var moving = (n2!==sel) && focusAmt[n2] > 0.005 && focusAmt[n2] < 0.995;
          if (n2===sel || moving){ flushPend(); focusDisc(n2); }
          else { pend.push(n2); }
        }
        flushPend();
      }
      // The TOP disc shows the page background through its hole (not the disc
      // below): find the topmost visible non-empty disc and punch its hole through
      // the canvas with a soft destination-out matching paintDisc's hole gradient.
      var topI = -1;
      for (var ti=0; ti<M; ti++){ if (vis(ti)){ topI = ti; break; } }
      if (topI >= 0 && !EMPTY[topI]){
        ctx.save(); ctx.translate(cx, cyOf(topI)); ctx.scale(1, ry/rx);
        ctx.globalCompositeOperation = "destination-out";
        ctx.globalAlpha = 0.7;                 // clear 70% -> hole is 70% see-through, not a stark void
        var hrT = rx*0.26;
        var pgT = ctx.createRadialGradient(0,0,0,0,0,hrT);
        pgT.addColorStop(0,"rgba(0,0,0,1)"); pgT.addColorStop(0.94,"rgba(0,0,0,1)"); pgT.addColorStop(1,"rgba(0,0,0,0)");
        ctx.fillStyle=pgT; ctx.beginPath(); ctx.arc(0,0,hrT,0,7); ctx.fill();
        ctx.restore();
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
      VISIBLE=Math.max(4, Math.min(H.masters.length, Math.floor((Hc-topY-botPad)/29)+1));   // ~15% tighter disc gap
      vt=Math.max(0, Math.min(Math.max(0,H.masters.length-VISIBLE), vt));
    }
    fit();
    window.addEventListener("resize", fit);
    // Motion etiquette for the spin loop:
    //  - EASE-IN: the spin ramps 0 -> full speed over ~1.5s (smoothstep on the rot
    //    increment), gated by TOWER_ANIM (the shared __cfdNoAnim / reduced-motion flag).
    //  - PAUSE WHEN HIDDEN: visibilitychange stops scheduling rAF in hidden tabs and
    //    resumes on return — frame counters just continue, so no time-jump.
    //  - REDUCED-MOTION: TOWER_ANIM false = no spin at all; the stack renders once and
    //    repaints only when focus/scrub/master/scroll/size change (the crossfade morph
    //    is already instant in that mode: morph snaps to 1, never animates).
    var SPIN_SPEED = 0.00768;                  // full speed (~20% slower auto-spin)
    var SPIN_RAMP = 1/90, spinT = 0;           // ease-in progress: ~1.5s at 60fps
    var rafId = null;
    var lastVt = null, lastSel = null, lastW = 0, lastHc = 0;   // reduced-motion dirty tracking
    function loop(){
      rafId = null;
      var fk = (state.focus==null?null:state.focus);
      var sc = state.tlScrub;
      var changed = false;
      if (fk!==curFocus || sc!==curScrub){
        curFocus=fk; curScrub=sc;
        var old=FIELDS; buildFields(curFocus);               // new disc fields for the picked moment / colour
        if (TOWER_ANIM){ PREV_FIELDS=old; morph=0; } else { PREV_FIELDS=null; morph=1; }   // crossfade old -> new colours
        changed = true;
      }
      if (morph<1){ morph=Math.min(1, morph+MORPH_STEP); if (morph>=1){ PREV_FIELDS=null; } changed = true; }
      var sel = selIndex();
      if (vt!==lastVt || sel!==lastSel || W!==lastW || Hc!==lastHc){
        lastVt=vt; lastSel=sel; lastW=W; lastHc=Hc; changed = true;   // wheel scroll / master pick / resize
      }
      if (TOWER_ANIM){
        if (!introDone){ introFrame++; if (introFrame > (VISIBLE-1)*INTRO_STAG + INTRO_PER + 4) introDone = true; }
        if (spinT<1) spinT = Math.min(1, spinT+SPIN_RAMP);
        var ramp = spinT*spinT*(3-2*spinT);                  // smoothstep ease-in on the increment
        rot += SPIN_SPEED*ramp;
        render();
      } else if (changed){
        render();                                            // reduced motion: no spin, repaint on change only
      }
      schedule();
    }
    var PAUSED = false;
    function schedule(){
      if (rafId!=null || document.hidden || PAUSED) return;  // hidden tab / host pause: stop scheduling rAF
      rafId = requestAnimationFrame(loop);
    }
    document.addEventListener("visibilitychange", function(){
      if (document.hidden){ if (rafId!=null){ cancelAnimationFrame(rafId); rafId=null; } }
      else schedule();                                       // visible again: resume where we left off
    });
    // Native host hook: the Glyphs report window pauses the spin while it is not
    // the key window / is occluded — a continuously-spinning canvas forces a
    // compositor commit through the HOST app's main thread every frame, which is
    // what made the report feel laggy inside Glyphs. Browsers never call this.
    window.__cfdSpinPause = function(paused){
      PAUSED = !!paused;
      if (PAUSED){ if (rafId!=null){ cancelAnimationFrame(rafId); rafId=null; } }
      else schedule();
    };
    cv.addEventListener("wheel", function(e){ e.preventDefault();
      vt += e.deltaY*0.02; vt=Math.max(0, Math.min(Math.max(0,H.masters.length-VISIBLE), vt));
    }, {passive:false});
    // Native host hook: a Glyphs-hosted webview registers azcfMaster and switches
    // the app's selected master on disc picks; in a browser this is a silent no-op.
    function notifyMaster(mid){ try{ window.webkit.messageHandlers.azcfMaster.postMessage(mid==null?"":String(mid)); }catch(e){} }
    cv.addEventListener("click", function(e){
      var rect=cv.getBoundingClientRect();
      var px=(e.clientX-rect.left)*(W/rect.width), py=(e.clientY-rect.top)*(Hc/rect.height);
      for (var i=0;i<H.masters.length;i++){ var cy=geo.topY+(i-geo.vt)*geo.dz;
        if (cy<geo.topY-geo.dz*1.6 || cy>geo.topY+(VISIBLE-1)*geo.dz+geo.dz*1.6) continue;
        var ex=(px-geo.cx)/geo.rx, ey=(py-cy)/geo.ry;
        if (ex*ex+ey*ey<=1){ var id=H.masters[i].id;
          state.master = (state.master===id) ? null : id;   // click the selected disc -> clear focus
          notifyMaster(state.master);
          laneSparkShouldAnim = true; update(); return; } }  // keep the current view (tabs/coverage/...)
    });
    // up/down arrows switch the focused master (up = toward the top disc)
    window.addEventListener("keydown", function(e){
      if (e.key!=="ArrowUp" && e.key!=="ArrowDown") return;
      var t=e.target; if (t && (t.tagName==="INPUT"||t.tagName==="TEXTAREA"||t.isContentEditable)) return;
      var M=H.masters.length; if (!M) return;
      var cur=selIndex(), step=(e.key==="ArrowDown")?1:-1;
      var ni = cur<0 ? (step>0?0:M-1) : Math.max(0, Math.min(M-1, cur+step));
      e.preventDefault();
      state.master=H.masters[ni].id; notifyMaster(state.master); laneSparkShouldAnim = true; update();   // keep the current view
    });
    loop();
  }

  function init(){
    document.getElementById("cfd-app").innerHTML =
      header() + toolbar()
      + '<div id="cfd-main"><aside id="cfd-tower" aria-label="Masters"><canvas id="cfd-tower-cv" width="240" height="560"></canvas></aside><div id="cfd-body"></div></div>'
      + '<footer class="ft"><span class="ft-l">'+esc(H.fileName)+' · v'+esc(H.version)+'</span>'
      + '<span class="ft-r">AZ Colorflow Report — '+esc(H.generated)+'</span></footer>';
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
      H = model; normalizeHiddenKeys(); lastOrder = H.order.length ? H.order[H.order.length-1] : null;
      // Stash both timeline granularities; the toggle swaps which drives H.trend etc.
      tlDay = { trend: H.trend, journeys: H.journeys, journeyIndex: H.journeyIndex };
      tlCommit = H.hasCommits
        ? { trend: H.trendCommits, journeys: H.journeysCommits, journeyIndex: H.journeyIndexCommits }
        : null;
      if (!tlCommit && state.tlGran === "save") state.tlGran = "time";   // no fine set -> Save unavailable
      applyGranularity();
      init();
    }).catch(function(err){
      // Boot failure. The body ships opacity:0 until "ready" (the first-paint gate,
      // normally added by init()), so without it the error page renders invisibly —
      // add it here too. Theme attr likewise normally comes from update(); set it so
      // the card honours the saved/OS theme. The card itself is pure CSS (.err-card,
      // hard-coded rainbow mark) — it must not lean on the model, which just failed.
      document.documentElement.setAttribute("data-theme", state.theme);
      document.body.classList.add("ready");
      var app = document.getElementById("cfd-app");
      if (app) app.innerHTML =
        '<div class="err-wrap"><div class="err-card" role="alert">'
        + '<span class="err-mark" aria-hidden="true"></span>'
        + '<p class="err-title">This report couldn’t load its data.</p>'
        + '<p class="err-msg">'+esc(err && err.message || "Could not load the report data.")+'</p>'
        + '</div></div>';
    });
  }
  if (document.readyState!=="loading") start();
  else document.addEventListener("DOMContentLoaded", start);
})();
"""
