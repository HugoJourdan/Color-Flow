# encoding: utf-8
"""Color Font Dashboard — data model + entry point for Color Flow's report.

Summarises, per master, how the font's glyphs are distributed across the Color
Flow colour labels, and which glyphs changed colour since the last run. This
module builds the data model and writes the report; the interactive HTML/CSS/JS
that renders it lives in ``colorflow_assets`` (one self-contained, offline file).

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
  * ``build_model`` returns a plain dict; ``colorflow_assets.build_html`` embeds it
    as JSON and the inline JS app renders it (search/filter/sort, tabs + compare,
    per-glyph heatmap, light/dark) with no network and no dependencies.

The data layer imports nothing from Glyphs so it stays unit-testable; only
``free_mode``, the snapshot helpers and ``main`` touch the running app.
"""

from __future__ import annotations

import tempfile
import webbrowser
from datetime import datetime
from pathlib import Path
import colornames
import colorflow_assets
import glyphsvg
import labelcolors

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


# --------------------------------------------------------------------------- #
# Full JSON model
# --------------------------------------------------------------------------- #

def _outline_paths(font, current: dict, glyph_names: list, order: list, is_free: bool) -> dict:
    """Per-master ``{glyph_name: {"d", "vb"}}`` for the heatmap's *unfinished*
    glyphs (capped) — only the likely-shown glyphs are rendered so big fonts stay
    light + fast. Each entry carries a tight per-glyph viewBox."""
    order_set = set(order)
    last = order[-1] if order else None
    cap = 300
    paths: dict = {}
    for master in font.masters:
        master_id = master.id
        per_glyph = current.get(master_id, {})
        shown: dict = {}
        produced = 0
        for name in glyph_names:
            if produced >= cap:
                break
            key = per_glyph.get(name)
            finished = (str(key) in order_set) if is_free else (str(key) == last)
            if finished:
                continue
            try:
                layer = font.glyphs[name].layers[master_id]
            except Exception:
                layer = None
            outline = glyphsvg.layer_outline(layer) if layer is not None else {}
            if outline:
                shown[name] = outline
                produced += 1
        paths[master_id] = shown
    return paths


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

    paths = _outline_paths(font, current, glyph_names, order, is_free)

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
        "colors": {str(index): labelcolors.hex_for(rgba)
                   for index, rgba in enumerate(labelcolors.read_label_colors())},
        "filePath": font.filepath or "",
        "paths": paths,
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
    current = build_master_glyph_colors(font)
    previous = load_snapshot(font) or current
    model = build_model(font, now, current, previous)
    html = colorflow_assets.build_html(model)
    save_snapshot(font, current)

    base = Path(font.filepath).stem if font.filepath else (font.familyName or "font")
    out_path = Path(tempfile.gettempdir()) / f"{now.strftime('%Y%m%d')} {base} — Color Flow.html"
    try:
        out_path.write_text(html, encoding="utf-8")
    except OSError as error:
        Message(f"Could not write the dashboard:\n{error}", "Color Font Dashboard")
        return
    webbrowser.open(out_path.as_uri())
