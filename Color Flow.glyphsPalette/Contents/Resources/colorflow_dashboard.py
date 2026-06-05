# encoding: utf-8
"""Color Font Dashboard — an HTML progress report for Color Flow.

Summarises, per master, how the font's glyphs are distributed across the Color
Flow colour labels, and which glyphs changed colour since the last run. Opens in
the default browser.

The numbers match the palette sidebar exactly: the same glyph set (ALL glyphs,
the layer's own ``layer.color`` only), the same shared ``colornames`` counting
(cumulative ``counts_from_colors`` in step mode, exact ``single_counts_from_colors``
in free mode), and the same active mode — read from the one global pref both
sides share, ``Glyphs.defaults["com.hugojourdan.ColorFlow-FreeMode"]``. The
uncoloured "None" row is a dashboard-only extra, tallied separately.

Design notes:
  * colours, order, labels and visibility come from the shared ``colornames``
    module / ``colorNames.txt`` — identical to the palette, no hardcoded copy;
  * the "what changed since last run" snapshot lives in ``Glyphs.defaults`` keyed
    by file path — NOT in the .glyphs file and NOT in a sidecar — so the source
    stays clean while the diff still survives across sessions;
  * the report is themeable (dark default, light via ``prefers-color-scheme``)
    and accessible (``role="progressbar"``, ``<th scope>``, escaped titles);
  * all user-supplied text is HTML-escaped — body text with ``xesc``,
    attribute-embedded text (titles / aria-labels) with ``xattr`` (quotes too);
  * the data + HTML layer is pure and unit-tested.

Imported lazily from plugin.py (GlyphsApp only exists inside Glyphs); the pure
helpers and HTML builders import nothing from Glyphs so they stay unit-testable.
"""

from __future__ import annotations

import tempfile
import webbrowser
from datetime import datetime
from pathlib import Path
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

# The single global pref the palette uses to decide step vs free mode
# (settings_panel.py writes it, plugin.py:_free_mode reads it). Reading the same
# key here guarantees the dashboard and palette can never disagree on the model.
FREE_KEY = "com.hugojourdan.ColorFlow-FreeMode"

# Glyphs colour index -> CSS background, kept in sync with the ``--cN`` CSS
# variables below. ``colornames.NO_COLOR`` (-1) is the uncoloured bucket.
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


def var_for(key: int) -> str:
    """CSS custom-property name for a colour key, so theming applies centrally.
    ``--c-none`` is the hatch; ``--c0``..``--c11`` are the label hues."""
    return "--c-none" if key == colornames.NO_COLOR else f"--c{int(key)}"


def xattr(text: str) -> str:
    """Escape text destined for an HTML *attribute* value — like ``xesc`` but
    also escaping double quotes (``xml.sax.saxutils.escape`` leaves them as-is)."""
    return xesc(text, {'"': "&quot;"})


# --------------------------------------------------------------------------- #
# Pure data layer (no GlyphsApp) — unit-tested in tests/test_colorflow_dashboard
# --------------------------------------------------------------------------- #

def color_to_key(color) -> int:
    """Native ``layer.color`` (int 0-11 or ``None``) -> a plist-safe storage/
    display key: ``None`` becomes ``colornames.NO_COLOR`` (-1)."""
    return colornames.NO_COLOR if color is None else int(color)


def snapshot_to_colors(per_glyph: dict[str, int]) -> list[int | None]:
    """Inverse of :func:`color_to_key` over a master's ``{glyph_name: key}`` map:
    a list of native colours (``int`` or ``None``) ready for the ``colornames``
    counting functions. ``NO_COLOR`` (-1) becomes ``None``."""
    return [None if key == colornames.NO_COLOR else int(key) for key in per_glyph.values()]


def master_counts(colors: list[int | None], order: list[str], is_free: bool) -> dict[str, int]:
    """Per-step counts for one master, matching the palette exactly. ``order`` is
    the str-keyed workflow order from ``load_meaning`` (file order, INCLUDING
    hidden/empty-label slots — required so cumulative crediting matches). Free
    mode is exact per-colour, step mode is cumulative."""
    if is_free:
        return colornames.single_counts_from_colors(colors, order)
    return colornames.counts_from_colors(colors, order)


def uncolored_count(colors: list[int | None], order: list[str]) -> int:
    """How many layers fall outside the counted steps — the exact complement of
    "credited to a step": ``None`` or a colour whose ``str`` is not in ``order``
    (hidden / unknown). One predicate serves both modes (the ``colornames``
    counters never emit a None bucket, so the dashboard tallies it itself)."""
    order_set = set(order)
    return sum(1 for color in colors if color is None or str(color) not in order_set)


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


def display_from_meaning(meaning: dict[str, str], none_label: str) -> list[tuple[int, str]]:
    """Ordered ``[(int_key, label)]`` of the rows to show: the visible colours in
    the user's configured order, then the None bucket last. Int keys (so the
    swatch CSS variables / ``hex_for`` line up); counting stays in str space."""
    display = [(int(index), label) for index, label in colornames.visible_labels(meaning).items()]
    none_text = none_label or colornames.DEFAULT_LABELS[colornames.NO_COLOR]
    display.append((colornames.NO_COLOR, none_text))
    return display


def label_map_from_display(display: list[tuple[int, str]]) -> dict[int, str]:
    """``{int_key: label}`` for swatch tooltips / change-log names."""
    return {key: label for key, label in display}


def is_finished(key: int, order: list[str], is_free: bool) -> bool:
    """Whether a glyph at colour ``key`` counts as done (and so is hidden from the
    unfinished heatmap). Step mode: reached the final step. Free mode: carries any
    visible colour (only None / unknown are "unfinished")."""
    if not order:
        return False
    if is_free:
        return str(key) in set(order)
    return str(key) == order[-1]


# --------------------------------------------------------------------------- #
# GlyphsApp-touching helpers
# --------------------------------------------------------------------------- #

def free_mode() -> bool:
    """Active mode, read from the SAME global pref the palette reads, so the two
    always agree. ``False`` (step mode) when Glyphs is absent or the pref unset."""
    if Glyphs is None:
        return False
    return bool(Glyphs.defaults[FREE_KEY])


def _meaning_and_none(font) -> tuple[dict[str, str], str]:
    """``(meaning, none_label)`` from this font's ``colorNames.txt``, mirroring
    ``colornames.load_meaning``'s resolution + blank-file fallback so ``meaning``
    (and therefore the counting ``order``) is identical to the palette's."""
    font_dir = str(Path(font.filepath).parent) if font.filepath else None
    path = colornames.resolve_key_file(font_dir)
    content = colornames.read_color_names(path)
    text = content if content.strip() else colornames.DEFAULT_COLOR_NAMES
    meaning = colornames.parse_color_names(text)
    none_label = colornames.parse_settings(text)[1]
    return meaning, none_label


def display_colors(font) -> list[tuple[int, str]]:
    """Visible colours + None bucket for this font (see :func:`display_from_meaning`)."""
    meaning, none_label = _meaning_and_none(font)
    return display_from_meaning(meaning, none_label)


def build_master_glyph_colors(font) -> dict[str, dict[str, int]]:
    """``{master_id: {glyph_name: key}}`` over ALL glyphs, taking the layer's own
    ``layer.color`` only (a missing layer is uncoloured) — exactly the set and
    source the palette counts (plugin.py ``_derive_counts``)."""
    data: dict[str, dict[str, int]] = {}
    for master in font.masters:
        per_glyph: dict[str, int] = {}
        for glyph in font.glyphs:
            layer = glyph.layers[master.id]
            color = layer.color if layer is not None else None
            per_glyph[glyph.name] = color_to_key(color)
        data[master.id] = per_glyph
    return data


def _coerce_snapshot(raw) -> dict[str, dict[str, int]]:
    """Coerce a possibly NSDictionary-backed snapshot into plain
    ``{master_id: {glyph_name: int}}`` so iteration/indexing behave normally."""
    snapshot: dict[str, dict[str, int]] = {}
    if not raw:
        return snapshot
    for master_id in raw:
        inner = raw[master_id]
        snapshot[str(master_id)] = {str(name): int(inner[name]) for name in inner}
    return snapshot


def load_snapshot(font) -> dict[str, dict[str, int]]:
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


def pct(count: int, total: int) -> int:
    """Integer percentage, guarding division by zero."""
    return round(count / total * 100) if total else 0


# --------------------------------------------------------------------------- #
# Page styling — CSS custom properties: dark ``:root`` (the original look) with a
# ``prefers-color-scheme: light`` override. Swatch hues are identical in both
# themes (a glyph's "red" must read red); a per-theme inset ring keeps pale hues
# legible and the hatch base flips so it never punches a hole.
# --------------------------------------------------------------------------- #

CSS = """
<style>
:root{
  --bg:#0e1116;--surface:#0d1117;--surface-2:#161b22;--surface-3:#121821;--surface-4:#11161d;
  --text:#c9d1d9;--text-strong:#fff;--muted:#5b6984;--muted-2:#8b949e;
  --border:#30363d;--border-soft:#21262d;--code-bg:rgba(110,118,129,.4);
  --track:rgba(255,255,255,.3);--accent:#539bf5;--swatch-outline:rgba(255,255,255,.14);
  --c-none-a:#0e1116;--c-none-b:#686d74;
  --c0:#f97e55;--c1:#ffbe68;--c2:#ba9d6d;--c3:#fff157;--c4:#c1ec8a;--c5:#6bab59;
  --c6:#64a5ef;--c7:#576ef1;--c8:#a962e7;--c9:#e77eb4;--c10:#c5c5c5;--c11:#5f5f5f;
  --c-none:repeating-linear-gradient(135deg,var(--c-none-a) 0,var(--c-none-a) 5px,var(--c-none-b) 5px,var(--c-none-b) 6px);
  color-scheme:dark;
}
@media (prefers-color-scheme:light){:root{
  --bg:#f6f8fa;--surface:#fff;--surface-2:#f0f3f6;--surface-3:#eaeef2;--surface-4:#eef1f5;
  --text:#1f2328;--text-strong:#0a0c10;--muted:#6e7781;--muted-2:#57606a;
  --border:#d0d7de;--border-soft:#e6e9ee;--code-bg:rgba(175,184,193,.3);
  --track:rgba(31,35,40,.25);--accent:#0969da;--swatch-outline:rgba(31,35,40,.30);
  --c-none-a:#c8ced6;--c-none-b:#8a929c;color-scheme:light;
}}
.markdown-body{margin:0 auto;color:var(--text);background:var(--surface);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif,"Apple Color Emoji";font-size:16px;line-height:1.55;word-wrap:break-word;box-sizing:border-box;min-width:200px;max-width:100%;padding:45px 30px 45px 300px;width:100%}
body{background:var(--bg);animation:fade 1s ease-out forwards;animation-delay:100ms;opacity:0}
@keyframes fade{from{opacity:0}to{opacity:1}}
@media (prefers-reduced-motion:reduce){body{animation:none;opacity:1}}
table{border-collapse:collapse;display:block;width:max-content;max-width:100%;overflow:auto;padding:30px 0}
caption{text-align:left;font-size:11pt;color:var(--muted-2);padding-bottom:10px}
th{font-weight:600;text-align:left}
th,td{padding:6px 13px;border:1px solid var(--border);overflow:hidden}
tr{background:var(--surface);border-top:1px solid var(--border-soft)}
tbody tr:nth-child(2n){background:var(--surface-2)}
code{padding:.2em .4em;font-size:85%;background:var(--code-bg);border-radius:6px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
hr{height:2px;border:0;background:var(--border);margin:30px 0}
a{color:var(--accent)}
summary{cursor:pointer;margin:-15px 0}
summary>div{display:inline-block}
details{margin:-14px 0}
.summaryDiv{display:inline-flex;width:calc(100% - 18px);white-space:nowrap}
.mname{width:120px}
.container{width:50%;margin-left:auto;padding-top:8px}
.progress{border:solid var(--track) 1px;border-radius:10px;height:8px;overflow:hidden;display:flex;background:var(--surface)}
.progress_bar{color:transparent;margin:0;overflow:hidden}
.colorLabel,.swatch,.cell{box-shadow:inset 0 0 0 1px var(--swatch-outline)}
.colorLabel{padding:0 6px!important}
.title{font-size:22pt;line-height:120%}
.subtle{color:var(--muted);font-size:10pt}
.infos{position:fixed;bottom:30px;left:30px;font-size:10pt;color:var(--muted)}
.credit{font-size:7pt;line-height:140%;margin-bottom:0}
.headline{font-size:11pt;color:var(--muted-2);margin:0 0 18px 0}
.headline b{color:var(--text-strong)}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
.sidebar{width:210px;background:var(--surface-3);position:fixed;left:0;top:0;height:100%;padding:20px 30px 0 30px;box-sizing:border-box}
.totals{background:var(--surface-2);border:1px solid var(--border);border-radius:8px;padding:30px;margin:0 0 30px 0}
.totals h2{margin:0 0 18px 0;font-size:13pt}
.totals table{padding:18px 0 0 0}
.chglog{background:var(--surface-4);padding:20px;margin-top:10px;border-radius:8px}
.chglog>summary{padding-bottom:14px}
.chgwrap{display:flex;flex-wrap:wrap;justify-content:space-between}
.chg{width:30%;display:inline-table;line-height:80%;font-size:9pt;border-collapse:separate;border-spacing:0 .7em}
.chg th,.chg td{border:none}
.heat>summary{padding:8px 0}
.heatmap{display:grid;grid-template-columns:repeat(auto-fill,minmax(16px,1fr));gap:3px;margin:12px 0;list-style:none;padding:0}
.heatmap .cell{aspect-ratio:1;border-radius:3px}
.heatmap .more{grid-column:1/-1;font-size:9pt;color:var(--muted-2)}
</style>
"""


# --------------------------------------------------------------------------- #
# HTML building (pure: take plain data, return strings)
# --------------------------------------------------------------------------- #

def build_sidebar(family: str, file_name: str, master_count: int, total: int,
                  version: str, mode_label: str, now: datetime) -> str:
    """Fixed sidebar inner content (the ``<nav>`` wrapper is added by build_html)."""
    family = xesc(family or "")
    return f'''
        <div class="title" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{family}</div>
        <span class="subtle">{xesc(file_name)}</span>
        <span class="infos">{now.strftime("%m.%d.%Y")}<br>{family} (v{xesc(version)})<br>⎯⎯⎯⎯⎯⎯⎯<br>Masters : {master_count}<br>Glyphs : {total}<br>Mode : {xesc(mode_label)}<br><br>
        <p class="credit">Color Font Dashboard<br>Color Flow — Hugo Jourdan</p></span>
    '''


def _summary_bar(master_name: str, counts: dict, uncolored: int, total: int,
                 order: list[str], is_free: bool) -> str:
    """The ``<summary>`` line: master name + a single progress bar. Step mode
    shows completion (reached the final step); free mode shows labelled share."""
    progress = (total - uncolored) if (is_free or not order) else counts.get(order[-1], 0)
    width = pct(progress, total)
    check = " ✅" if total > 0 and progress >= total else ""
    aria = xattr(f"{master_name}: {progress} of {total} ({width}%)")
    return (
        '<summary><div class="summaryDiv">'
        f'<div class="mname">{xesc(master_name)}{check}</div>'
        '<div class="container">'
        f'<div class="progress" role="progressbar" aria-valuenow="{progress}" aria-valuemin="0" '
        f'aria-valuemax="{total}" aria-label="{aria}">'
        f'<div class="progress_bar" style="background:var(--accent);width:{width}%"></div>'
        '</div></div></div></summary>'
    )


def _count_row(key: int, label: str, count: int, total: int, prev_count: int | None) -> str:
    """One colour row shared by the per-master and overall tables."""
    percent = pct(count, total)
    aria = xattr(f"{label}: {count} of {total} ({percent}%)")
    row = (
        "<tr>"
        f'<td class="colorLabel" aria-hidden="true" style="background:var({var_for(key)})"></td>'
        f'<th scope="row">{xesc(label)}</th>'
        f'<td><div class="progress" role="progressbar" aria-valuenow="{count}" aria-valuemin="0" '
        f'aria-valuemax="{total}" aria-label="{aria}">'
        f'<div class="progress_bar" style="background:var({var_for(key)});width:{percent}%"></div></div></td>'
    )
    if prev_count is not None:
        diff = count - prev_count
        row += f'<td style="white-space:nowrap"><code>{"+" if diff >= 0 else ""}{diff}</code></td>'
    mark = " ✅" if total > 0 and count >= total else ""
    row += f"<td><code>{count}/{total}</code>{mark}</td><td><code>{percent}%</code></td></tr>"
    return row


def _master_table(counts: dict, uncolored: int, prev_counts: dict, prev_uncolored: int,
                  display: list[tuple[int, str]], total: int, has_changes: bool,
                  caption: str) -> str:
    cols = '<col width="1%"><col width="250px"><col width="auto">'
    head = ('<thead><tr><th scope="col"><span class="sr-only">Swatch</span></th>'
            '<th scope="col">Colour</th><th scope="col">Share</th>')
    if has_changes:
        cols += '<col width="10px">'
        head += '<th scope="col">Δ</th>'
    cols += '<col width="10px"><col width="10px">'
    head += '<th scope="col">Count</th><th scope="col">Percent</th></tr></thead>'
    rows = ""
    for key, label in display:
        count = uncolored if key == colornames.NO_COLOR else counts.get(str(key), 0)
        prev = None
        if has_changes:
            prev = prev_uncolored if key == colornames.NO_COLOR else prev_counts.get(str(key), 0)
        rows += _count_row(key, label, count, total, prev)
    return f'<table><caption>{xesc(caption)}</caption>{cols}{head}<tbody>{rows}</tbody></table>'


def _change_log(changes_for_master: dict, label_map: dict[int, str]) -> str:
    """Collapsible "changed since last run" block — one mini table per glyph."""
    if not changes_for_master:
        return ""
    blocks = ""
    for glyph_name, (old_key, new_key) in changes_for_master.items():
        old_label = label_map.get(old_key, colornames.DEFAULT_LABELS.get(old_key, f"Color {old_key}"))
        new_label = label_map.get(new_key, colornames.DEFAULT_LABELS.get(new_key, f"Color {new_key}"))
        was = xattr(f"was {old_label}")
        now_label = xattr(f"now {new_label}")
        blocks += (
            '<table class="chg"><col width="90%"><col width="4%"><col width="1%"><col width="4%">'
            "<tbody><tr>"
            f'<th scope="row">{xesc(glyph_name)}</th>'
            f'<td class="swatch" style="background:var({var_for(old_key)})" title="{was}" aria-label="{was}"></td>'
            '<td aria-hidden="true">▶</td>'
            f'<td class="swatch" style="background:var({var_for(new_key)})" title="{now_label}" aria-label="{now_label}"></td>'
            "</tr></tbody></table>"
        )
    return (
        f'<details class="chglog"><summary>Changed since last run ({len(changes_for_master)})</summary>'
        f'<div class="chgwrap">{blocks}</div></details>'
    )


def build_heatmap_section(master_name: str, per_glyph: dict[str, int],
                          label_map: dict[int, str], order: list[str], is_free: bool,
                          cap: int = 500) -> str:
    """Collapsed per-glyph grid of the *unfinished* glyphs (in font/glyph order),
    each cell a swatch with an accessible ``glyph — colour`` tooltip. Capped so a
    several-thousand-glyph font stays light. Empty (no markup) when all done."""
    unfinished = [(name, key) for name, key in per_glyph.items()
                  if not is_finished(key, order, is_free)]
    if not unfinished:
        return ""
    cells = ""
    for name, key in unfinished[:cap]:
        label = label_map.get(key, colornames.DEFAULT_LABELS.get(key, f"Color {key}"))
        tip = xattr(f"{name} — {label}")
        cells += (f'<li class="cell" role="listitem" style="background:var({var_for(key)})" '
                  f'title="{tip}" aria-label="{tip}"></li>')
    extra = len(unfinished) - min(len(unfinished), cap)
    more = f'<li class="more">… +{extra} more</li>' if extra > 0 else ""
    grid_aria = xattr(f"Unfinished glyphs, {master_name}")
    return (
        f'<details class="heat"><summary>Per-glyph heatmap — {len(unfinished)} unfinished</summary>'
        f'<ul class="heatmap" role="list" aria-label="{grid_aria}">{cells}{more}</ul></details>'
    )


def build_master_section(master_name: str, counts: dict, prev_counts: dict, uncolored: int,
                         prev_uncolored: int, display: list[tuple[int, str]], total: int,
                         order: list[str], is_free: bool, changes_for_master: dict,
                         has_changes: bool, label_map: dict[int, str], heatmap: str) -> str:
    """One collapsible ``<details>`` block for a single master."""
    started = total - uncolored
    if is_free or not order:
        headline = f'Labelled : <b>{started}/{total}</b> ({pct(started, total)}%)'
    else:
        completion = counts.get(order[-1], 0)
        headline = (f'Complete : <b>{completion}/{total}</b> ({pct(completion, total)}%)'
                    f' · Started : {started}/{total} ({pct(started, total)}%)')
    parts = [
        "<details open>",
        _summary_bar(master_name, counts, uncolored, total, order, is_free),
        f'<p class="headline">{headline}</p>',
        _master_table(counts, uncolored, prev_counts, prev_uncolored, display, total,
                      has_changes, f"{master_name} — colour distribution"),
    ]
    if has_changes:
        parts.append(_change_log(changes_for_master, label_map))
    parts.append(heatmap)
    parts.append("</details><hr>")
    return "".join(parts)


def build_overall_totals(order: list[str], is_free: bool, display: list[tuple[int, str]],
                         total: int, master_count: int, per_master: dict) -> str:
    """Font-wide summary across all masters. Step mode headlines completion
    (reached the final step) with started as secondary; free mode headlines the
    labelled share. Per-step counts are aggregated, never summed cumulatively."""
    grand_total = total * master_count
    agg = {step: 0 for step in order}
    agg_uncolored = 0
    for counts, uncolored in per_master.values():
        for step in order:
            agg[step] += counts.get(step, 0)
        agg_uncolored += uncolored
    started = grand_total - agg_uncolored
    masters_word = "master" if master_count == 1 else "masters"
    if is_free or not order:
        progress = started
        headline = (f'Labelled across {master_count} {masters_word} : '
                    f'<b>{started}/{grand_total}</b> ({pct(started, grand_total)}%)')
    else:
        progress = agg.get(order[-1], 0)
        headline = (f'Complete : <b>{progress}/{grand_total}</b> ({pct(progress, grand_total)}%)'
                    f' · Started : {started}/{grand_total} ({pct(started, grand_total)}%)')
    width = pct(progress, grand_total)
    aria = xattr(f"Overall progress: {progress} of {grand_total} ({width}%)")
    rows = ""
    for key, label in display:
        count = agg_uncolored if key == colornames.NO_COLOR else agg.get(str(key), 0)
        rows += _count_row(key, label, count, grand_total, None)
    return (
        '<section class="totals" aria-labelledby="totals-h">'
        '<h2 id="totals-h">Overall totals</h2>'
        f'<p class="headline">{headline}</p>'
        f'<div class="progress" role="progressbar" aria-valuenow="{progress}" aria-valuemin="0" '
        f'aria-valuemax="{grand_total}" aria-label="{aria}">'
        f'<div class="progress_bar" style="background:var(--accent);width:{width}%"></div></div>'
        '<table><caption>Per-colour totals (all masters)</caption>'
        '<col width="1%"><col width="250px"><col width="auto"><col width="10px"><col width="10px">'
        '<thead><tr><th scope="col"><span class="sr-only">Swatch</span></th>'
        '<th scope="col">Colour</th><th scope="col">Share</th>'
        '<th scope="col">Count</th><th scope="col">Percent</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></section>'
    )


def build_html(font, total: int, order: list[str], is_free: bool,
               display: list[tuple[int, str]], current: dict, previous: dict,
               changes: dict, now: datetime) -> str:
    title = xesc(f'{now.strftime("%Y%m%d")}_{font.familyName or ""}_Color-Flow-Dashboard')
    file_name = Path(font.filepath).name if font.filepath else (font.familyName or "Untitled")
    version = f"{font.versionMajor}.{font.versionMinor}"
    mode_label = "Free" if is_free else "Step"
    masters = list(font.masters)
    label_map = label_map_from_display(display)

    per_master = {}
    for master in masters:
        colors = snapshot_to_colors(current.get(master.id, {}))
        per_master[master.id] = (master_counts(colors, order, is_free),
                                 uncolored_count(colors, order))

    html = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title>{CSS}</head>"
        '<body><div class="markdown-body">'
        '<nav class="sidebar" aria-label="Font summary">'
        f'{build_sidebar(font.familyName, file_name, len(masters), total, version, mode_label, now)}'
        '</nav><main aria-label="Color Flow dashboard">'
    )
    html += build_overall_totals(order, is_free, display, total, len(masters), per_master)

    has_changes = any(changes.values())
    for master in masters:
        counts, uncolored = per_master[master.id]
        prev_colors = snapshot_to_colors(previous.get(master.id, {}))
        prev_counts = master_counts(prev_colors, order, is_free)
        prev_uncolored = uncolored_count(prev_colors, order)
        heatmap = build_heatmap_section(master.name, current.get(master.id, {}),
                                        label_map, order, is_free)
        html += build_master_section(
            master.name, counts, prev_counts, uncolored, prev_uncolored, display, total,
            order, is_free, changes.get(master.id, {}), has_changes, label_map, heatmap,
        )
    html += "</main></div></body></html>"
    return html


# --------------------------------------------------------------------------- #
# Full JSON model
# --------------------------------------------------------------------------- #

def build_model(font, now: datetime, current: dict, previous: dict) -> dict:
    """The full data model the JS app renders. Pure aside from reading the
    font's colorNames.txt (via _meaning_and_none) — the same source the palette
    uses, so counts stay in lockstep."""
    is_free = free_mode()
    meaning, none_label = _meaning_and_none(font)
    order = list(meaning.keys())
    display = display_from_meaning(meaning, none_label)
    steps = [{"key": key, "label": label} for key, label in display
             if key != colornames.NO_COLOR]
    none_text = next((label for key, label in display
                      if key == colornames.NO_COLOR), "")
    glyph_total = len(font.glyphs)
    glyph_names = list(current[font.masters[0].id].keys()) if font.masters else []

    masters = []
    for master in font.masters:
        per_glyph = current.get(master.id, {})
        colors = snapshot_to_colors(per_glyph)
        masters.append({
            "id": master.id,
            "name": master.name,
            "keys": [per_glyph.get(name, colornames.NO_COLOR) for name in glyph_names],
            "counts": master_counts(colors, order, is_free),
            "uncolored": uncolored_count(colors, order),
        })

    return {
        "family": font.familyName or "",
        "fileName": Path(font.filepath).name if font.filepath else (font.familyName or "Untitled"),
        "version": f"{font.versionMajor}.{font.versionMinor}",
        "generated": now.strftime("%Y-%m-%d"),
        "mode": "free" if is_free else "step",
        "glyphTotal": glyph_total,
        "order": order,
        "steps": steps,
        "noneLabel": none_text,
        "glyphNames": glyph_names,
        "masters": masters,
        "changes": compute_changes(current, previous),
    }


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main(font=None) -> None:
    if font is None and Glyphs is not None:
        font = Glyphs.font
    if font is None:
        Message("Open a font first.", "Color Font Dashboard")
        return
    total = len(font.glyphs)
    if total == 0:
        Message("No glyphs to report on.", "Color Font Dashboard")
        return

    now = datetime.now()
    is_free = free_mode()
    meaning, none_label = _meaning_and_none(font)
    order = list(meaning.keys())
    display = display_from_meaning(meaning, none_label)
    current = build_master_glyph_colors(font)
    previous = load_snapshot(font) or current
    changes = compute_changes(current, previous)

    html = build_html(font, total, order, is_free, display, current, previous, changes, now)
    save_snapshot(font, current)

    base = Path(font.filepath).stem if font.filepath else (font.familyName or "font")
    out_path = Path(tempfile.gettempdir()) / f"{now.strftime('%Y%m%d')} {base} — Color Flow.html"
    try:
        out_path.write_text(html, encoding="utf-8")
    except OSError as error:
        Message(f"Could not write the dashboard:\n{error}", "Color Font Dashboard")
        return
    # Leave the file in the temp dir (the OS reclaims it); deleting it here would
    # race the browser load — and the original's blocking sleep froze Glyphs.
    webbrowser.open(out_path.as_uri())
