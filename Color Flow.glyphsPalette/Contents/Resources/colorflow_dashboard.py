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
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast
import colornames
import colorflow_assets
import glyphsvg
import labelcolors
import colorflow_recipes

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

# Opt-in workflow recipes (#5) live here as JSON; absent/empty = recipes off,
# in which case the recipe-adjusted completion equals standard completion.
RECIPES_KEY = "com.hugojourdan.ColorFlow-Recipes"


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


def load_recipes() -> list:
    """Opt-in workflow recipes from ``Glyphs.defaults`` (JSON). ``[]`` when Glyphs
    is absent or no recipes are set — the recipe-adjusted metric then equals the
    standard one."""
    if Glyphs is None:
        return []
    return colorflow_recipes.parse_recipes(Glyphs.defaults[RECIPES_KEY])


def glyph_meta(font) -> dict:
    """``{glyph_name: {category, script, subCategory, case}}`` for recipe matching."""
    return {glyph.name: {"category": str(getattr(glyph, "category", None) or ""),
                         "script": str(getattr(glyph, "script", None) or ""),
                         "subCategory": str(getattr(glyph, "subCategory", None) or ""),
                         "case": str(getattr(glyph, "case", None) or "")}
            for glyph in font.glyphs}


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
# Dated history — a capped series of per-glyph snapshots, the substrate for the
# dashboard's burndown / velocity / finish-date forecast and the per-glyph
# step-journey sparkline. Stored in Glyphs.defaults (not the .glyphs file),
# keyed by file path then ISO date; same-day captures overwrite.
# --------------------------------------------------------------------------- #

HISTORY_KEY = "com.hugojourdan.ColorFlow-DashboardHistory"
HISTORY_CAP = 60


def _coerce_history(raw) -> dict[str, dict[str, dict[str, int]]]:
    """Coerce a possibly NSDictionary-backed history into plain
    ``{iso_date: {master_id: {glyph_name: int}}}`` so it behaves normally."""
    history: dict[str, dict[str, dict[str, int]]] = {}
    if not raw:
        return history
    for date in raw:
        history[str(date)] = _coerce_snapshot(raw[date])
    return history


def load_history(font) -> dict[str, dict[str, dict[str, int]]]:
    """This font's dated per-glyph snapshots from ``Glyphs.defaults`` (keyed by
    file path), ordered oldest-first. Empty when none / unsaved / unavailable."""
    if Glyphs is None or not font.filepath:
        return {}
    store = Glyphs.defaults[HISTORY_KEY]
    if not store or not hasattr(store, "get"):
        return {}
    history = _coerce_history(store.get(font.filepath))
    return {date: history[date] for date in sorted(history)}


def record_history(font, snapshot: dict, now: datetime, cap: int = HISTORY_CAP) -> None:
    """Append today's per-glyph ``snapshot`` to this font's dated history under
    ``Glyphs.defaults`` (same-day capture overwrites), keeping at most ``cap`` most
    recent dates. No-op without Glyphs or an unsaved font."""
    if Glyphs is None or not font.filepath:
        return
    store = Glyphs.defaults[HISTORY_KEY]
    store = dict(store) if hasattr(store, "keys") else {}
    series = store.get(font.filepath) or {}
    series = {str(date): series[date] for date in series}
    series[now.strftime("%Y-%m-%d")] = snapshot
    if cap and len(series) > cap:
        for old_date in sorted(series)[:len(series) - cap]:
            del series[old_date]
    store[font.filepath] = series
    Glyphs.defaults[HISTORY_KEY] = store


# --------------------------------------------------------------------------- #
# Burndown / velocity / forecast — pure functions over the dated history.
# "final" is the completion metric: in step mode the cumulative count at the
# last workflow step; in free mode (no cumulative final) it equals "started".
# --------------------------------------------------------------------------- #

def _parse_iso(date: str) -> datetime:
    """ISO ``YYYY-MM-DD`` -> ``datetime`` (history keys are always this shape)."""
    return datetime.strptime(date, "%Y-%m-%d")


def _coefficient_of_variation(values: list[float]) -> float:
    """Std/mean of ``values`` (population). ``1.0`` for empty or non-positive mean
    — used as a worst-case spread when the rate signal is weak."""
    if not values:
        return 1.0
    mean = sum(values) / len(values)
    if mean <= 0:
        return 1.0
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return (variance ** 0.5) / mean


def _master_point(per_glyph: dict, order: list[str], is_free: bool) -> dict[str, int]:
    """One master's ``{final, started, total}`` for a single dated snapshot."""
    colors = snapshot_to_colors(per_glyph)
    counts = master_counts(colors, order, is_free)
    total = len(per_glyph)
    started = total - uncolored_count(colors, order)
    last = order[-1] if order else None
    final = started if (is_free or last is None) else counts.get(last, 0)
    return {"final": final, "started": started, "total": total}


def history_series(history: dict, order: list[str], is_free: bool) -> list[dict]:
    """The dated history reduced to a per-master count time series, oldest-first:
    ``[{"date": iso, "masters": {master_id: {final, started, total}}}]``."""
    series = []
    for date in sorted(history):
        masters = {master_id: _master_point(per_glyph, order, is_free)
                   for master_id, per_glyph in history[date].items()}
        series.append({"date": date, "masters": masters})
    return series


def forecast_master(series: list[dict], master_id: str, total: int, now: datetime,
                    is_free: bool, window_days: int = 28) -> dict:
    """Velocity + a hedged finish-date for one master from its ``final`` history.

    Rate is the completion gained per day over a trailing ``window_days`` window
    (falling back to the last two points). Returns a never-a-hard-date estimate:
    an ETA with a ``±`` band derived from how variable the recent pace was, plus a
    confidence label. No ETA when there is too little data, no recent progress, or
    the master is already done."""
    points = [(point["date"], point["masters"][master_id]["final"])
              for point in series if master_id in point["masters"]]
    final_now = points[-1][1] if points else 0
    remaining = max(0, total - final_now)
    result = {"velocityPerWeek": 0.0, "remaining": remaining, "final": final_now,
              "total": total, "etaIso": None, "bandDays": None,
              "confidence": "none", "points": len(points)}
    if len(points) < 2:
        return result

    cutoff = now - timedelta(days=window_days)
    windowed = [(date, final) for (date, final) in points if _parse_iso(date) >= cutoff]
    if len(windowed) < 2:
        windowed = points[-2:]

    span_days = max(1, (_parse_iso(windowed[-1][0]) - _parse_iso(windowed[0][0])).days)
    rate = (windowed[-1][1] - windowed[0][1]) / span_days
    result["velocityPerWeek"] = round(rate * 7, 1)
    if remaining <= 0:
        result["confidence"] = "done"
        return result
    if rate <= 0:
        return result  # flat or regressing — no honest ETA

    eta_days = remaining / rate
    interval_rates = [
        (later_final - earlier_final) / max(1, (_parse_iso(later) - _parse_iso(earlier)).days)
        for (earlier, earlier_final), (later, later_final) in zip(windowed, windowed[1:])
    ]
    band_fraction = min(1.0, max(0.15, _coefficient_of_variation(interval_rates)))
    result["etaIso"] = (now + timedelta(days=eta_days)).strftime("%Y-%m-%d")
    result["bandDays"] = int(round(eta_days * band_fraction))
    result["confidence"] = ("high" if len(windowed) >= 4 and band_fraction < 0.5
                            else "med" if len(windowed) >= 3 else "low")
    return result


def progress_streak(history: dict, order: list[str], is_free: bool) -> dict:
    """A motivation streak (#17): how many consecutive *recorded days* ended with
    more labelled glyphs than the day before. Same-day captures already collapse
    to one entry per date, so each history entry is one work-day; calendar gaps
    (days you never opened the font) don't break the streak, regressions do.
    Returns ``{current, best, days}``."""
    dates = sorted(history)
    totals = [sum(_master_point(per_glyph, order, is_free)["started"]
                  for per_glyph in history[date].values()) for date in dates]
    progressed = [False] + [totals[i] > totals[i - 1] for i in range(1, len(totals))]
    current = 0
    for flag in reversed(progressed):
        if not flag:
            break
        current += 1
    best = run = 0
    for flag in progressed:
        run = run + 1 if flag else 0
        best = max(best, run)
    return {"current": current, "best": best, "days": len(dates)}


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


def _master_layers(font, master_id: str, names: tuple) -> list:
    """``[(layer, dx)]`` for the named glyphs on one master, each offset by the
    running advance width so they sit side by side. Missing glyphs/layers are
    skipped. Used to preview a master's design (e.g. "Aa") on its tab."""
    layers: list = []
    advance = 0.0
    for name in names:
        glyph = font.glyphs[name]
        if glyph is None:
            continue
        layer = glyph.layers[master_id]
        if layer is None:
            continue
        layers.append((layer, advance))
        advance += layer.width
    return layers


def _master_previews(font) -> dict:
    """Per-master ``{"d", "vb"}`` outline of "Aa" for the master-tab preview, so
    each tab shows that master's actual letterforms (weight/width) instead of a
    plain name. ``{}`` for any master whose A/a have no outline."""
    return {master.id: glyphsvg.layers_outline(_master_layers(font, master.id, ("A", "a")))
            for master in font.masters}


def _favicon(font) -> dict:
    """The lowercase ``a`` of the Regular master (or the first master) as a tight
    ``{"d", "vb"}`` outline, used for the page favicon. ``{}`` when unavailable."""
    if not font.masters:
        return {}
    glyph = font.glyphs["a"]
    if glyph is None:
        return {}
    master = next((m for m in font.masters if (m.name or "").lower() == "regular"),
                  font.masters[0])
    layer = glyph.layers[master.id]
    return glyphsvg.layer_outline(layer) if layer is not None else {}


def _glyph_groups(font, attr: str) -> dict[str, list[str]]:
    """``{group_value: [glyph_name]}`` grouping all glyphs by a per-glyph
    attribute (``script`` or ``category``); a missing/blank value -> ``"Other"``."""
    groups: dict[str, list[str]] = {}
    for glyph in font.glyphs:
        value = getattr(glyph, attr, None) or "Other"
        groups.setdefault(str(value), []).append(glyph.name)
    return groups


def _coverage_for(current: dict, groups: dict[str, list[str]], order: list[str],
                  is_free: bool) -> dict[str, list[dict]]:
    """Per-master coverage rows for one grouping: each row is a group's
    ``{key, total, final, started, uncolored, counts}`` using the SAME mode-aware
    counting as the palette/dashboard, restricted to that group's glyphs. Rows are
    sorted largest group first."""
    last = order[-1] if order else None
    result: dict[str, list[dict]] = {}
    for master_id, per_glyph in current.items():
        rows = []
        for group, names in groups.items():
            colors = snapshot_to_colors({name: per_glyph.get(name, colornames.NO_COLOR)
                                         for name in names})
            counts = master_counts(colors, order, is_free)
            total = len(names)
            started = total - uncolored_count(colors, order)
            final = started if (is_free or last is None) else counts.get(last, 0)
            rows.append({"key": group, "total": total, "final": final, "started": started,
                         "uncolored": total - started, "counts": counts})
        rows.sort(key=lambda row: (-row["total"], row["key"]))
        result[master_id] = rows
    return result


def build_coverage(font, current: dict, order: list[str], is_free: bool) -> dict:
    """Completion broken down by Unicode script and by glyph category, per master
    — the data behind the dashboard's Coverage view (#13)."""
    return {
        "byScript": _coverage_for(current, _glyph_groups(font, "script"), order, is_free),
        "byCategory": _coverage_for(current, _glyph_groups(font, "category"), order, is_free),
    }


def _glyph_journeys(history: dict, dates: list, current: dict, glyph_names: list,
                    order: list, is_free: bool, cap: int = 400) -> dict:
    """Per-master ``{glyph_name: [key_per_date]}`` for the heatmap drill-down
    sparkline — only *unfinished* glyphs whose step actually *changed* over the
    recorded dates (a flat journey has nothing to show), capped for big fonts.
    Each list is aligned to ``dates`` (oldest-first); missing dates read as
    uncoloured."""
    if not dates:
        return {}
    order_set = set(order)
    last = order[-1] if order else None
    journeys: dict = {}
    for master_id, per_glyph in current.items():
        shown: dict = {}
        produced = 0
        for name in glyph_names:
            if produced >= cap:
                break
            key = per_glyph.get(name)
            finished = (str(key) in order_set) if is_free else (str(key) == last)
            if finished:
                continue
            journey = [history.get(date, {}).get(master_id, {}).get(name, colornames.NO_COLOR)
                       for date in dates]
            if len(set(journey)) > 1:   # changed at least once -> worth a sparkline
                shown[name] = journey
                produced += 1
        journeys[master_id] = shown
    return journeys


def _days_ago(value, now: datetime) -> int | None:
    """Whole days between ``value`` (a Glyphs ``lastChange`` NSDate or a
    ``datetime``) and ``now``; ``None`` when absent/unreadable. Glyphs' per-glyph
    ``lastChange`` is often disabled in foundry setups, hence the tolerant None."""
    if value is None:
        return None
    edited = None
    timestamp = getattr(value, "timeIntervalSince1970", None)
    if callable(timestamp):
        try:
            edited = datetime.fromtimestamp(cast(float, timestamp()))
        except Exception:
            edited = None
    if edited is None and isinstance(value, datetime):
        edited = value
    if edited is None:
        return None
    return max(0, (now - edited).days)


def glyph_last_edit(font, now: datetime) -> dict:
    """``{glyph_name: days_since_edit}`` for glyphs that carry a ``lastChange``.
    Per-GLYPH only (Glyphs has no per-layer timestamp), and sparse — glyphs whose
    timestamp is missing/disabled are simply absent."""
    result = {}
    for glyph in font.glyphs:
        days = _days_ago(getattr(glyph, "lastChange", None), now)
        if days is not None:
            result[glyph.name] = days
    return result


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

    previews = _master_previews(font)
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
            "preview": previews.get(master.id, {}),
        })

    paths = _outline_paths(font, current, glyph_names, order, is_free)

    history = load_history(font)
    series = history_series(history, order, is_free)
    dates = [point["date"] for point in series]
    trend = {
        "series": series,
        "forecast": {master.id: forecast_master(series, master.id, glyph_total, now, is_free)
                     for master in font.masters},
        "dates": dates,
        "today": now.strftime("%Y-%m-%d"),
        "streak": progress_streak(history, order, is_free),
    }
    journeys = _glyph_journeys(history, dates, current, glyph_names, order, is_free)

    recipes = load_recipes()
    meta = glyph_meta(font)
    metas = [meta.get(name, {}) for name in glyph_names]
    recipe_completion = {}
    for master in font.masters:
        per_glyph = current.get(master.id, {})
        colors = [None if per_glyph.get(name, colornames.NO_COLOR) == colornames.NO_COLOR
                  else int(per_glyph.get(name)) for name in glyph_names]
        recipe_completion[master.id] = colorflow_recipes.recipe_completion(
            metas, colors, recipes, order, is_free)

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
        "favicon": _favicon(font),
        "trend": trend,
        "journeys": journeys,
        "lastEdit": glyph_last_edit(font, now),
        "recipes": recipes,
        "recipeCompletion": recipe_completion,
        "coverage": build_coverage(font, current, order, is_free),
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
    record_history(font, current, now)

    base = Path(font.filepath).stem if font.filepath else (font.familyName or "font")
    out_path = Path(tempfile.gettempdir()) / f"{now.strftime('%Y%m%d')} {base} — Color Flow.html"
    try:
        out_path.write_text(html, encoding="utf-8")
    except OSError as error:
        Message(f"Could not write the dashboard:\n{error}", "Color Font Dashboard")
        return
    webbrowser.open(out_path.as_uri())
