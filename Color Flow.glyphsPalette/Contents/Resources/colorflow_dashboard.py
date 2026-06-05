# encoding: utf-8
"""Color Font Dashboard — an HTML progress report for Color Flow.

Summarises, per master, how the font's glyphs are distributed across the Color
Flow colour labels (derived from each layer's native colour, with the glyph
colour as a fallback), and which glyphs changed colour since the last run.
Opens in the default browser.

Improvements over the original standalone "Color Font Dashboard" script:
  * colours, order, labels and visibility come from the shared ``colornames``
    module / ``colorNames.txt`` — identical to the palette, no hardcoded copy,
    so the two never drift;
  * the "what changed since last run" snapshot lives in ``Glyphs.defaults``
    keyed by file path — NOT in the .glyphs file and NOT in a sidecar file — so
    the source stays clean while the diff still survives across sessions;
  * all user-supplied text (labels, glyph names, family) is HTML-escaped;
  * the data layer is pure and unit-tested; the dead inline-SVG helper and the
    main-thread ``time.sleep`` (which froze Glyphs) are gone.

Imported lazily from plugin.py (GlyphsApp only exists inside Glyphs); the pure
helpers and HTML builders import nothing from Glyphs so they stay unit-testable.
"""

from __future__ import annotations

import os
import tempfile
import webbrowser
from datetime import datetime
from xml.sax.saxutils import escape as xesc

import colornames

try:
    from GlyphsApp import Glyphs, Message  # type: ignore[import]
except Exception:  # pragma: no cover - only importable inside Glyphs
    Glyphs = None

    def Message(*args, **kwargs) -> None:
        pass


# Where the cross-session diff snapshot is stored (app prefs, not the font file).
DEFAULTS_KEY = "com.hugojourdan.ColorFlow-DashboardSnapshot"

# Glyphs colour index -> CSS background. ``colornames.NO_COLOR`` (-1) is the
# uncoloured bucket, drawn as a hatch so it reads as "not yet labelled".
HATCH = "repeating-linear-gradient(135deg,#0e1116 0px,#0e1116 5px,#686d74 5px,#686d74 6px)"
COLOR_HEX = {
    colornames.NO_COLOR: HATCH,
    0: "#f97e55", 1: "#ffbe68", 2: "#ba9d6d", 3: "#fff157",
    4: "#c1ec8a", 5: "#6bab59", 6: "#64a5ef", 7: "#576ef1",
    8: "#a962e7", 9: "#e77eb4", 10: "#c5c5c5", 11: "#5f5f5f",
}


def hex_for(key: int) -> str:
    """CSS background for a colour key, falling back to the hatch."""
    return COLOR_HEX.get(key, HATCH)


# --------------------------------------------------------------------------- #
# Pure data layer (no GlyphsApp) — unit-tested in tests/test_colorflow_dashboard
# --------------------------------------------------------------------------- #

def color_to_key(color) -> int:
    """Native ``layer.color`` (int 0-11 or ``None``) -> a plist-safe storage/
    display key: ``None`` becomes ``colornames.NO_COLOR`` (-1)."""
    return colornames.NO_COLOR if color is None else int(color)


def pct(count: int, total: int) -> int:
    """Integer percentage, guarding division by zero."""
    return round(count / total * 100) if total else 0


def counts_for_master(glyph_colors: dict, display_keys: list) -> dict:
    """``{display_key: number of glyphs with that colour}`` for one master.

    ``glyph_colors`` is ``{glyph_name: key}``. Every key in ``display_keys`` is
    present in the result (0 when unused) so empty rows still render. Colours
    used on layers but hidden from the display set are intentionally ignored."""
    counts = {key: 0 for key in display_keys}
    for key in glyph_colors.values():
        if key in counts:
            counts[key] = counts[key] + 1
    return counts


def compute_changes(current: dict, previous: dict) -> dict:
    """Per master id, ``{glyph_name: (old_key, new_key)}`` for glyphs whose
    colour changed since the previous snapshot.

    Both arguments are ``{master_id: {glyph_name: key}}``. Glyphs absent from the
    previous snapshot (newly added) are not reported as changes."""
    changes: dict = {}
    for master_id, colors in current.items():
        previous_master = previous.get(master_id, {})
        master_changes = {}
        for name, key in colors.items():
            if name in previous_master and previous_master[name] != key:
                master_changes[name] = (previous_master[name], key)
        changes[master_id] = master_changes
    return changes


# --------------------------------------------------------------------------- #
# GlyphsApp-touching helpers
# --------------------------------------------------------------------------- #

def build_master_glyph_colors(font) -> dict:
    """``{master_id: {glyph_name: key}}`` over the exporting glyphs.

    The layer's own colour wins; otherwise the glyph colour; otherwise the
    uncoloured bucket. Only exporting glyphs are counted so the totals match the
    "Glyphs" figure shown in the sidebar."""
    data: dict = {}
    for master in font.masters:
        per_glyph = {}
        for glyph in font.glyphs:
            if not glyph.export:
                continue
            layer = glyph.layers[master.id]
            color = layer.color if layer is not None else None
            if color is None and glyph.color is not None:
                color = glyph.color
            per_glyph[glyph.name] = color_to_key(color)
        data[master.id] = per_glyph
    return data


def display_colors(font) -> list:
    """Ordered ``[(key, label)]`` to show: the visible colours from
    colorNames.txt in the user's configured order, then the None bucket last —
    exactly the colours and order the palette uses."""
    font_dir = os.path.dirname(font.filepath) if font.filepath else None
    path = colornames.resolve_key_file(font_dir)
    text = colornames.read_color_names(path) or colornames.DEFAULT_COLOR_NAMES
    rows, none_label = colornames.parse_settings(text)
    display = [
        (index, label or colornames.DEFAULT_LABELS.get(index, str(index)))
        for index, label, visible in rows
        if visible
    ]
    none_text = none_label or colornames.DEFAULT_LABELS[colornames.NO_COLOR]
    display.append((colornames.NO_COLOR, none_text))
    return display


def _coerce_snapshot(raw) -> dict:
    """Coerce a possibly NSDictionary-backed snapshot into plain
    ``{master_id: {glyph_name: int}}`` so iteration/indexing behave normally."""
    snapshot: dict = {}
    if not raw:
        return snapshot
    for master_id in raw:
        inner = raw[master_id]
        snapshot[str(master_id)] = {str(name): int(inner[name]) for name in inner}
    return snapshot


def load_snapshot(font) -> dict:
    """Previous per-glyph colour snapshot for this font from ``Glyphs.defaults``
    (keyed by file path). Empty dict if none / unsaved / unavailable."""
    if Glyphs is None or not font.filepath:
        return {}
    store = Glyphs.defaults[DEFAULTS_KEY]
    if not store or not hasattr(store, "get"):
        return {}
    return _coerce_snapshot(store.get(font.filepath))


def save_snapshot(font, snapshot: dict) -> None:
    """Persist this run's snapshot in ``Glyphs.defaults`` (not the .glyphs file)."""
    if Glyphs is None or not font.filepath:
        return
    store = Glyphs.defaults[DEFAULTS_KEY]
    store = dict(store) if hasattr(store, "keys") else {}
    store[font.filepath] = snapshot
    Glyphs.defaults[DEFAULTS_KEY] = store


# --------------------------------------------------------------------------- #
# Page styling (GitHub dark theme + dashboard tweaks)
# --------------------------------------------------------------------------- #

CSS = """
<style>
.markdown-body{color-scheme:dark;margin:0;color:#c9d1d9;background:#0d1117;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif,"Apple Color Emoji";font-size:16px;line-height:1.5;word-wrap:break-word;box-sizing:border-box;min-width:200px;max-width:100%;margin:0 auto;padding:45px 30px 45px 300px;width:100%}
body{background:#0e1116;animation:fade 1s ease-out forwards;animation-delay:100ms;opacity:0}
@keyframes fade{from{opacity:0}to{opacity:1}}
table{border-collapse:collapse;display:block;width:max-content;max-width:100%;overflow:auto;padding:30px 0}
th,td{padding:6px 13px;border:1px solid #30363d;overflow:hidden}
tr{background:#0d1117;border-top:1px solid #21262d}
tr:nth-child(2n){background:#161b22}
code{padding:.2em .4em;font-size:85%;background:rgba(110,118,129,.4);border-radius:6px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
hr{height:2px;border:0;background:#30363d;margin:30px 0}
summary{cursor:pointer;margin:-15px 0}
summary>div{display:inline-block}
details{margin:-14px 0}
.summaryDiv{display:inline-flex;width:calc(100% - 18px);white-space:nowrap}
.container{width:50%;margin-left:auto;padding-top:8px}
.progress{border:solid rgba(255,255,255,.3) 1px;border-radius:10px;height:8px;overflow:hidden;display:flex}
.progress_bar{color:transparent;margin:0;overflow:hidden}
.colorLabel{padding:0 6px!important}
.title{font-size:22pt;line-height:120%}
.infos{position:fixed;bottom:30px;left:30px;font-size:10pt;color:#5b6984}
.headline{font-size:11pt;color:#8b949e;margin:0 0 18px 0}
.headline b{color:#c9d1d9}
</style></head>
"""


# --------------------------------------------------------------------------- #
# HTML building (pure: take plain data, return strings)
# --------------------------------------------------------------------------- #

def build_sidebar(family: str, file_name: str, master_count: int, total: int,
                  version: str, now: datetime) -> str:
    family = xesc(family or "")
    return f'''
        <div style="width:210px;background:#121821;position:fixed;left:0;top:0;height:100%;padding:20px 30px 0 30px">
            <div class="title" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{family}</div>
            <span style="color:#5b6984;font-size:10pt">{xesc(file_name)}</span>
            <span class="infos">{now.strftime("%m.%d.%Y")}<br>{family} (v{xesc(version)})<br>⎯⎯⎯⎯⎯⎯⎯<br>Masters : {master_count}<br>Glyphs : {total}<br><br>
            <p style="font-size:7pt;line-height:140%;margin-bottom:0">Color Font Dashboard<br>Color Flow — Hugo Jourdan</p></span>
        </div>
    '''


def build_master_section(master_name: str, counts: dict, prev_counts: dict,
                         display: list, total: int, changes_for_master: dict,
                         has_changes: bool) -> str:
    """One collapsible ``<details>`` block for a single master."""
    labelled = sum(count for key, count in counts.items() if key != colornames.NO_COLOR)
    html = f'''
    <details open>
        <summary>
            <div class="summaryDiv"><div style="width:120px">{xesc(master_name)}</div>
                <div class="container"><div class="progress">'''
    for key, _ in display:
        count = counts.get(key, 0)
        if count and key != colornames.NO_COLOR:
            html += (f'<div class="progress_bar" style="background:{hex_for(key)};'
                     f'width:{pct(count, total)}%"></div>')
    html += '</div></div></div></summary>'

    html += f'<p class="headline">Labelled : <b>{labelled}/{total}</b> ({pct(labelled, total)}%)</p>'

    html += '<table><col width="1%"><col width="250px"><col width="auto">'
    if has_changes:
        html += '<col width="10px">'
    html += '<col width="10px"><col width="10px">'
    for key, label in display:
        count = counts.get(key, 0)
        percent = pct(count, total)
        bar_extra = "" if key != colornames.NO_COLOR else ";border-right:solid rgba(255,255,255,.3) 1px"
        html += f'''
            <tr>
                <td class="colorLabel" style="background:{hex_for(key)}"></td>
                <td>{xesc(label)}</td>
                <td><div class="progress"><div class="progress_bar" style="background:{hex_for(key)};width:{percent}%{bar_extra}"></div></div></td>'''
        if has_changes:
            diff = count - prev_counts.get(key, 0)
            html += f'<td style="white-space:nowrap"><code>{"+" if diff >= 0 else ""}{diff}</code></td>'
        html += f'''
                <td><code>{count}/{total}</code></td>
                <td><code>{percent}%</code></td>
            </tr>'''
    html += '</table>'

    if has_changes and changes_for_master:
        html += '''
        <details style="background:#11161d;padding:20px;margin-top:10px">
            <summary style="padding-bottom:14px">Changed since last run ({n})</summary>
            <div style="display:flex;flex-wrap:wrap;justify-content:space-between">'''.replace(
            "{n}", str(len(changes_for_master)))
        for glyph_name, (old_key, new_key) in changes_for_master.items():
            html += f'''
                <table style="width:30%;display:inline-table;line-height:80%;font-size:9pt;border-collapse:separate;border-spacing:0 .7em">
                    <col width="90%"><col width="4%"><col width="1%"><col width="4%">
                    <tr style="background:#0e1116">
                        <td>{xesc(glyph_name)}</td>
                        <td style="background:{hex_for(old_key)};border:none"> </td>
                        <td style="white-space:nowrap;padding:6px">▶</td>
                        <td style="background:{hex_for(new_key)};border:none"></td>
                    </tr>
                </table>'''
        html += '</div></details>'

    html += '</details><hr>'
    return html


def build_html(font, total: int, display: list, current: dict, previous: dict,
               changes: dict, now: datetime) -> str:
    title = f'{now.strftime("%Y%m%d")}_{xesc(font.familyName or "")}_Color-Flow-Dashboard'
    file_name = os.path.basename(font.filepath) if font.filepath else (font.familyName or "Untitled")
    version = f'{font.versionMajor}.{font.versionMinor}'

    html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{title}</title>{CSS}<body><article class="markdown-body">'
    )
    html += build_sidebar(font.familyName, file_name, len(font.masters), total, version, now)

    display_keys = [key for key, _ in display]
    has_changes = any(changes.values())
    for master in font.masters:
        counts = counts_for_master(current.get(master.id, {}), display_keys)
        prev_counts = counts_for_master(previous.get(master.id, {}), display_keys)
        html += build_master_section(
            master.name, counts, prev_counts, display, total,
            changes.get(master.id, {}), has_changes,
        )
    html += '</article></body></html>'
    return html


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main(font=None) -> None:
    if font is None and Glyphs is not None:
        font = Glyphs.font
    if font is None:
        Message("Open a font first.", "Color Font Dashboard")
        return
    total = len([glyph for glyph in font.glyphs if glyph.export])
    if total == 0:
        Message("No exporting glyphs to report on.", "Color Font Dashboard")
        return

    now = datetime.now()
    display = display_colors(font)
    current = build_master_glyph_colors(font)
    previous = load_snapshot(font) or current
    changes = compute_changes(current, previous)

    html = build_html(font, total, display, current, previous, changes, now)
    save_snapshot(font, current)

    base = os.path.basename(font.filepath).rsplit(".", 1)[0] if font.filepath else (font.familyName or "font")
    out_path = os.path.join(tempfile.gettempdir(), f"{now.strftime('%Y%m%d')} {base} — Color Flow.html")
    try:
        with open(out_path, "w", encoding="utf-8") as page:
            page.write(html)
    except OSError as error:
        Message(f"Could not write the dashboard:\n{error}", "Color Font Dashboard")
        return
    # Leave the file in the temp dir (the OS reclaims it); deleting it here would
    # race the browser load — and the original's blocking sleep froze Glyphs.
    webbrowser.open(f"file://{out_path}")
