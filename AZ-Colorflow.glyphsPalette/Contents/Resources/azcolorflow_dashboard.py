"""Color Font Dashboard — data model + entry point for Color Flow's report.

Summarises, per master, how the font's glyphs are distributed across the Color
Flow colour labels, and which glyphs changed colour since the last run. This
module builds the data model and writes the report; the interactive HTML/CSS/JS
that renders it lives in ``azcolorflow_assets`` (one self-contained, offline file).

The numbers come from the same shared ``colornames`` counting as the palette
sidebar (same glyph set: ALL glyphs, the layer's own ``layer.color`` only).
The per-group ``dist`` data is the exact census (``single_counts_from_colors``)
— the same semantics as the palette's count badges; ``masters[].counts`` is the
report-only cumulative "reached step k or beyond" view (``counts_from_colors``).
The uncoloured "None" row is a dashboard-only extra, tallied separately.

Design notes:
  * colours, order, labels and visibility come from the shared ``colornames``
    module / ``colorNames.txt`` — identical to the palette, no hardcoded copy;
  * the "what changed since last run" snapshot lives in ``Glyphs.defaults`` keyed
    by file path — NOT in the .glyphs file and NOT in a sidecar — so the source
    stays clean while the diff still survives across sessions;
  * ``build_model`` returns a plain dict; ``azcolorflow_assets.build_html`` embeds it
    as JSON and the inline JS app renders it (search/filter/sort, tabs + compare,
    per-glyph heatmap, light/dark) with no network and no dependencies.

The data layer imports nothing from Glyphs so it stays unit-testable; only the
snapshot helpers and ``main`` touch the running app.
"""

from __future__ import annotations

import base64
import json
import re
import tempfile
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

import azcolorflow_assets
import azcolorflow_git
import azcolorflow_history_store
import azcolorflow_outline_diff
import colornames
import glyphsvg
import labelcolors

try:
    from GlyphsApp import Glyphs, Message  # type: ignore[import]
except Exception:  # pragma: no cover - only importable inside Glyphs
    Glyphs = None

    def Message(*args, **kwargs) -> None:
        pass


# Where the cross-session diff snapshot is stored (app prefs, not the font file).
DEFAULTS_KEY = "com.hugojourdan.AZColorflow-DashboardSnapshot"

# Hidden power-user pref: when truthy, the per-glyph outline SVGs are omitted from
# the report. The embedded glyph paths are by far the heaviest part of the file, so
# skipping them makes the report dramatically lighter (cells render as plain colour
# swatches). Set from the Macro panel:
#   Glyphs.defaults["com.hugojourdan.AZColorflow-NoGlyphSVG"] = True
NO_GLYPH_SVG_KEY = "com.hugojourdan.AZColorflow-NoGlyphSVG"

# Outline-changes view (#D): how many recent git-committed days to diff for glyph
# shape changes. Re-opening each historical commit is expensive, so this is a small
# recent window by default. Set to 0 to disable the feature entirely. Tunable via:
#   Glyphs.defaults["com.hugojourdan.AZColorflow-OutlineChangeDays"] = 10
OUTLINE_CHANGE_DAYS_KEY = "com.hugojourdan.AZColorflow-OutlineChangeDays"
OUTLINE_CHANGE_DAYS_DEFAULT = 10   # diff the last ~10 committed days
OUTLINE_CHANGE_LIMIT = 60          # cap changed glyphs kept per day (avoid huge days)


# --------------------------------------------------------------------------- #
# Pure data layer (no GlyphsApp) — unit-tested in tests/test_azcolorflow_dashboard
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


def master_counts(colors: list[int | None], order: list[str]) -> dict[str, int]:
    """Cumulative per-step counts for one master ("reached step k or beyond").

    Report-only semantics: the palette's count badges show the exact census
    (``single_counts_from_colors``), like the report's ``dist``. ``order`` is the
    str-keyed workflow order from ``load_meaning`` (file order, INCLUDING
    hidden/empty-label slots — required so cumulative crediting matches)."""
    return colornames.counts_from_colors(colors, order)


def uncolored_count(colors: list[int | None], order: list[str]) -> int:
    """How many layers fall outside the counted steps — the exact complement of
    "credited to a step": ``None`` or a colour whose ``str`` is not in ``order``
    (hidden / unknown). The ``colornames`` counters never emit a None bucket, so
    the dashboard tallies it itself."""
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

def no_glyph_svg() -> bool:
    """Hidden pref: skip embedding per-glyph outline SVGs to make the report much
    lighter. ``False`` (embed the outlines) when Glyphs is absent or the key unset."""
    if Glyphs is None:
        return False
    return bool(Glyphs.defaults[NO_GLYPH_SVG_KEY])


def non_exporting_names(font) -> list[str]:
    """Sorted names of this font's non-exporting glyphs (``glyph.export`` is
    falsy). Cheap (one ``font.glyphs`` pass) and shipped in the model so the
    report can ALWAYS exclude these glyphs from every displayed percentage —
    empty list when every glyph exports (nothing to exclude)."""
    return sorted(colornames.non_exporting_names(font.glyphs))


def glyph_meta(font) -> dict:
    """``{glyph_name: {category, script}}`` feeding the per-glyph ``categories`` /
    ``scripts`` model lists (heatmap lanes + coverage grouping)."""
    return {glyph.name: {"category": str(getattr(glyph, "category", None) or ""),
                         "script": str(getattr(glyph, "script", None) or "")}
            for glyph in font.glyphs}


def _meaning_and_none(font) -> tuple[dict[str, str], str]:
    """``(meaning, none_label)`` from this font's ``colorNames.txt``, mirroring
    ``colornames.load_meaning``'s resolution + blank-file fallback so ``meaning``
    (and therefore the counting ``order``) is identical to the palette's."""
    font_dir = str(Path(font.filepath).parent) if font.filepath else None
    path = colornames.resolve_key_file(font_dir)
    # in-font labels (userData) win over the sidecar key file, so a shared .glyphs file
    # reports the same labels its author saved; the key file is the offline fallback.
    text = colornames.pick_settings_text(
        colornames.font_labels_text(font), colornames.read_color_names(path))
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


def default_glyph_order(font, glyph_names: list[str]) -> list[str]:
    """Return ``glyph_names`` in the font's *default* glyph order, ignoring any
    ``glyphOrder`` custom parameter.

    ``font.glyphs`` (the source of ``glyph_names``) iterates in the order imposed
    by a ``glyphOrder`` custom parameter whenever one is active — a user's
    hand-tuned order, or our own Rainbow grouping order — so that would otherwise
    drive the report. We temporarily deactivate that parameter, which makes Glyphs
    re-sort ``font.glyphs`` to its default order, read that order, then restore the
    parameter's previous active state. The result is filtered to the glyphs present
    in ``glyph_names``; any names not found in ``font.glyphs`` keep their original
    relative order at the end. Falls back to the input order unchanged outside
    Glyphs (tests) or when the ``customParameters`` / ``glyphs`` API is missing."""
    params = getattr(font, "customParameters", None)
    if params is None:
        return glyph_names
    try:
        order_param = next(
            (param for param in params if getattr(param, "name", None) == "glyphOrder"),
            None,
        )
    except Exception:  # pragma: no cover - defensive, app-only call path
        return glyph_names
    previous_active: bool | None = None
    try:
        if order_param is not None:
            previous_active = bool(order_param.active)
            order_param.active = False               # Glyphs re-sorts to default
        default_order = [glyph.name for glyph in font.glyphs]
    except Exception:  # pragma: no cover - defensive, app-only call path
        return glyph_names
    finally:
        if order_param is not None and previous_active is not None:
            try:
                order_param.active = previous_active  # restore the user's setting
            except Exception:  # pragma: no cover - defensive, app-only call path
                pass
    wanted = set(glyph_names)
    ordered = [name for name in default_order if name in wanted]
    seen = set(ordered)
    ordered.extend(name for name in glyph_names if name not in seen)
    return ordered


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
# dashboard's burndown / velocity and the per-glyph step-journey sparkline.
#
# Stored IN THE FONT (userData), gzip+base64-compacted, so the timeline travels
# WITH the file: a shared .glyphs/.glyphspackage shows the same history on any
# machine, with no git repo or sidecar needed. (Older builds kept this in
# Glyphs.defaults keyed by file path; that store is still read once as a fallback
# so existing users don't lose their history on upgrade.)
# --------------------------------------------------------------------------- #

HISTORY_KEY = "com.hugojourdan.AZColorflow-DashboardHistory"           # legacy (Glyphs.defaults)
TIMELINE_USERDATA_KEY = "com.hugojourdan.ColorFlow.timelineHistory"  # primary (font userData)


def _coerce_history(raw) -> dict[str, dict[str, dict[str, int]]]:
    """Coerce a possibly NSDictionary-backed history into plain
    ``{iso_date: {master_id: {glyph_name: int}}}`` so it behaves normally."""
    history: dict[str, dict[str, dict[str, int]]] = {}
    if not raw:
        return history
    for date in raw:
        history[str(date)] = _coerce_snapshot(raw[date])
    return history


def _read_user_data(font, key: str) -> object:
    """Safely read ``font.userData[key]`` (``None`` when absent / unavailable)."""
    try:
        user_data = getattr(font, "userData", None)
        if user_data is None:
            return None
        try:
            return user_data[key]
        except (KeyError, TypeError):
            return None
    except Exception:  # pragma: no cover - defensive, app-only call path
        return None


def _write_user_data(font, key: str, value: str) -> None:
    """Safely set ``font.userData[key] = value`` (no-op when unavailable)."""
    try:
        user_data = getattr(font, "userData", None)
        if user_data is None:
            return
        user_data[key] = value
    except Exception:  # pragma: no cover - defensive, app-only call path
        pass


def _legacy_history(font) -> dict[str, dict[str, dict[str, int]]]:
    """One-time migration read of the old machine-local history from
    ``Glyphs.defaults`` (keyed by file path). Empty when none / unavailable."""
    if Glyphs is None or not getattr(font, "filepath", None):
        return {}
    store = Glyphs.defaults[HISTORY_KEY]
    if not store or not hasattr(store, "get"):
        return {}
    return _coerce_history(store.get(font.filepath))


def load_history(font) -> dict[str, dict[str, dict[str, int]]]:
    """This font's per-*save* snapshot log, ordered oldest-first — one entry per save,
    keyed by ISO datetime (``%Y-%m-%dT%H:%M:%S``). The report groups these by date for
    the per-day timeline (:func:`group_saves_by_date`) and uses the raw log for the
    per-save view. Read from the font's ``userData`` (so the timeline travels with the
    file); falls back to the legacy ``Glyphs.defaults`` store for fonts saved by older
    builds (those entries are date-keyed and pass through fine). Empty when none /
    unavailable. Datetime keys sort lexicographically = chronologically."""
    if Glyphs is None or font is None:
        return {}
    history = azcolorflow_history_store.decode_history(
        _read_user_data(font, TIMELINE_USERDATA_KEY))
    if not history:
        history = _legacy_history(font)
    return {key: history[key] for key in sorted(history)}


def group_saves_by_date(log: dict) -> dict[str, dict[str, dict[str, int]]]:
    """Collapse a per-save log (``{iso_datetime: snapshot}``) to a per-day history
    (``{iso_date: snapshot}``), keeping the LAST save of each day (the latest state
    that day). Legacy date-keyed entries (10-char keys) pass through unchanged."""
    grouped: dict[str, dict[str, dict[str, int]]] = {}
    for key in sorted(log):                  # chronological; later same-day wins
        grouped[str(key)[:10]] = log[key]
    return grouped


def _keep_last_save_of_past_days(series: dict) -> dict:
    """Collapse every *past* day to its final save (end-of-day state), keeping every
    save of the most-recent day. Once work moves to a new day the old day's intra-day
    saves stop mattering, so only its closing state is kept — this is what bounds the
    log's growth (one entry per past day, forever; no day-window cap)."""
    if not series:
        return {}
    keys = sorted(series)
    latest_day = str(keys[-1])[:10]
    last_of_day: dict[str, str] = {}
    for key in keys:                          # chronological; later same-day wins
        last_of_day[str(key)[:10]] = key
    return {
        key: series[key]
        for key in keys
        if str(key)[:10] == latest_day or last_of_day[str(key)[:10]] == key
    }


def record_history(font, snapshot: dict, now: datetime) -> None:
    """Append a per-glyph ``snapshot`` to this font's per-*save* log in ``userData``,
    keyed by save datetime (one entry per save, not per day). Skips a no-op save: if
    the snapshot equals the most-recent stored one (e.g. an outline-only edit or a
    double save with no colour change), nothing is written, so the log only grows on
    colour-changing saves. The log is never day-capped; instead each *past* day keeps
    only its final save (see :func:`_keep_last_save_of_past_days`). The value is
    written into the font object; Glyphs persists it on the next save, so call this
    from a *will-save* hook to have it land in that save. No-op without Glyphs/font."""
    if Glyphs is None or font is None:
        return
    series = load_history(font)
    series = {str(key): series[key] for key in series}
    if series and series[max(series)] == snapshot:
        return                                          # nothing changed -> no junk entry
    series[now.strftime("%Y-%m-%dT%H:%M:%S")] = snapshot
    series = _keep_last_save_of_past_days(series)
    _write_user_data(
        font, TIMELINE_USERDATA_KEY, azcolorflow_history_store.encode_history(series))


def write_history(font, history: dict) -> None:
    """Replace this font's entire save log in ``userData`` with ``history``
    (``{iso_datetime: snapshot}``), each past day collapsed to its final save (the
    same end-of-day policy as :func:`record_history`; never day-capped). Used by the
    git backfill to install reconstructed history wholesale. No-op without Glyphs or
    a font."""
    if Glyphs is None or font is None:
        return
    series = _keep_last_save_of_past_days({str(key): history[key] for key in history})
    _write_user_data(
        font, TIMELINE_USERDATA_KEY, azcolorflow_history_store.encode_history(series))


def _git_open_colors(path) -> dict | None:
    """Open a historical font (a ``.glyphs`` file or ``.glyphspackage`` extracted by
    the git backfill) headlessly and return its ``{master_id: {glyph_name: key}}``
    colour snapshot. Glyphs-only; ``None`` outside Glyphs or on any open failure."""
    if Glyphs is None:
        return None
    font = None
    try:
        font = Glyphs.open(str(path), showInterface=False)
        if font is None:
            return None
        return build_master_glyph_colors(font)
    except Exception:  # pragma: no cover - app-only path
        return None
    finally:  # close the document we opened so it doesn't linger in the app
        if font is not None:
            try:  # pragma: no cover - app-only path
                document = getattr(font, "parent", None)
                if document is not None:
                    document.close()
            except Exception:  # pragma: no cover - app-only path
                pass


def _history_paths(font) -> dict:
    """``{master_id: {glyph_name: {"d","vb"}}}`` of every glyph's outline in a
    historical font, sharing each master's em box (the same shape ``_outline_paths``
    emits, minus the live-font cache). Used to diff shape changes across commits."""
    ems = _em_boxes(font)
    out: dict = {master_id: {} for master_id in ems}
    budget = 100000
    produced = 0
    for glyph in font.glyphs:
        if produced >= budget:
            break
        name = glyph.name
        for master_id in ems:
            try:
                layer = glyph.layers[master_id]
            except Exception:
                layer = None
            _asc, _desc = ems[master_id]
            outline = glyphsvg.layer_outline_em(layer, _asc, _desc) if layer is not None else {}
            if outline:
                out[master_id][name] = outline
                produced += 1
    return out


def _git_open_paths(path) -> dict | None:
    """Open a historical font headlessly and return its per-master outline path map
    (see :func:`_history_paths`). Glyphs-only; ``None`` outside Glyphs or on failure."""
    if Glyphs is None:
        return None
    font = None
    try:
        font = Glyphs.open(str(path), showInterface=False)
        if font is None:
            return None
        return _history_paths(font)
    except Exception:  # pragma: no cover - app-only path
        return None
    finally:
        if font is not None:
            try:  # pragma: no cover - app-only path
                document = getattr(font, "parent", None)
                if document is not None:
                    document.close()
            except Exception:  # pragma: no cover - app-only path
                pass


def outline_change_days() -> int:
    """Recent committed-day window to diff for the outline-changes view. Reads the
    tunable pref, defaulting to ``OUTLINE_CHANGE_DAYS_DEFAULT``; 0 disables the view.
    ``0`` when Glyphs is absent (the feature only makes sense in the app)."""
    if Glyphs is None:
        return 0
    raw = Glyphs.defaults[OUTLINE_CHANGE_DAYS_KEY]
    if raw is None:
        return OUTLINE_CHANGE_DAYS_DEFAULT
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return OUTLINE_CHANGE_DAYS_DEFAULT


def collect_outline_changes(font) -> dict:
    """``{iso_date: [change, ...]}`` of glyph outline changes across this font's recent
    git commits (see ``azcolorflow_outline_diff``). Empty when the font isn't git-tracked,
    the light-report pref is on, or the day window is 0 — so the view stays dormant."""
    if Glyphs is None or not font.filepath or no_glyph_svg():
        return {}
    cap_days = outline_change_days()
    if cap_days <= 0:
        return {}
    # collect_git_history is generic over the per-day payload; here _git_open_paths
    # returns outline path maps rather than colour snapshots, so cast for the type.
    day_maps = cast(dict, azcolorflow_git.collect_git_history(
        font.filepath, _git_open_paths, cap=cap_days))
    return azcolorflow_outline_diff.outline_changes(day_maps, limit_per_day=OUTLINE_CHANGE_LIMIT)


def is_git_tracked(font) -> bool:
    """Whether this font's source file lives in a git repo and is tracked there.

    The timeline is no longer gated on this (history now lives in the font's userData
    and travels with the file); git is only an *optional* extra history source via the
    backfill. Cheap (two quick git calls); ``False`` when the font is unsaved or git is
    unavailable."""
    path = getattr(font, "filepath", None)
    if not path:
        return False
    try:
        target = Path(path)
        repo = azcolorflow_git.git_root(target)
        return repo is not None and azcolorflow_git.is_tracked(repo, target)
    except Exception:
        return False


def backfill_from_git(font, progress=None) -> int:
    """Bake this font's git commit history into its userData save log (each commit is
    a per-save-equivalent datetime entry), merged under any existing live saves — so
    the timeline travels with the file even without the .git folder. Live saves win on
    a shared key. Returns the number of newly-imported commits (0 when the font isn't
    in a git repo, isn't saved, or Glyphs is unavailable)."""
    if Glyphs is None or not font.filepath:
        return 0
    existing = load_history(font)
    git_history = azcolorflow_git.collect_commit_history(
        font.filepath, _git_open_colors, progress=progress)
    if not git_history:
        return 0
    new_keys = [key for key in git_history if key not in existing]
    merged = {**git_history, **existing}            # existing (live saves) win on collision
    write_history(font, merged)
    return len(new_keys)


def commit_timeline_history(font) -> dict[str, dict[str, dict[str, int]]]:
    """Per-commit colour history (``{commit_datetime: snapshot}``) reconstructed from
    the font's git commits — the substrate for the timeline's per-commit view. Empty
    when the font is unsaved, not in a git repo, or Glyphs is unavailable. Computed
    fresh on each report (not persisted to userData)."""
    if Glyphs is None or not getattr(font, "filepath", None):
        return {}
    try:
        return azcolorflow_git.collect_commit_history(font.filepath, _git_open_colors)
    except Exception:
        return {}


def git_day_history(font) -> dict[str, dict[str, dict[str, int]]]:
    """Per-*day* colour history (``{iso_date: snapshot}``) reconstructed from the font's
    git commits (newest commit of each day wins). This is the day-timeline's substrate
    when the font is git-tracked: git is the store, so we read history straight from it
    rather than from userData. Empty when the font is unsaved, not in a git repo, or
    Glyphs is unavailable. Computed fresh per report (not persisted)."""
    if Glyphs is None or not getattr(font, "filepath", None):
        return {}
    try:
        return cast(dict, azcolorflow_git.collect_git_history(
            font.filepath, _git_open_colors))
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
# Burndown / velocity — pure functions over the dated history.
# "final" is the completion metric: the cumulative count at the last workflow
# step.
# --------------------------------------------------------------------------- #

def _parse_iso(date: str) -> datetime:
    """ISO ``YYYY-MM-DD`` -> ``datetime`` (history keys are always this shape)."""
    return datetime.strptime(date, "%Y-%m-%d")


def _master_point(per_glyph: dict, order: list[str]) -> dict[str, int]:
    """One master's ``{final, started, total}`` for a single dated snapshot."""
    colors = snapshot_to_colors(per_glyph)
    counts = master_counts(colors, order)
    total = len(per_glyph)
    started = total - uncolored_count(colors, order)
    last = order[-1] if order else None
    final = started if last is None else counts.get(last, 0)
    return {"final": final, "started": started, "total": total}


def history_series(history: dict, order: list[str]) -> list[dict]:
    """The dated history reduced to a per-master count time series, oldest-first:
    ``[{"date": iso, "masters": {master_id: {final, started, total}}}]``."""
    series = []
    for date in sorted(history):
        masters = {master_id: _master_point(per_glyph, order)
                   for master_id, per_glyph in history[date].items()}
        series.append({"date": date, "masters": masters})
    return series


def progress_streak(history: dict, order: list[str]) -> dict:
    """A motivation streak (#17): how many consecutive *recorded days* ended with
    more labelled glyphs than the day before. Same-day captures already collapse
    to one entry per date, so each history entry is one work-day; calendar gaps
    (days you never opened the font) don't break the streak, regressions do.
    Returns ``{current, best, days}``."""
    dates = sorted(history)
    totals = [sum(_master_point(per_glyph, order)["started"]
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


def cross_master_summary(current: dict, master_ids: list[str],
                         glyph_names: list[str], order: list[str]) -> dict:
    """Cross-master agreement over the reported glyphs. For each glyph, gather its
    colour key in *every* master (absent/uncoloured == ``NO_COLOR``); a glyph is
    ``identical`` when all masters share one key, and ``doneEverywhere`` when that
    shared key is the workflow's final step (``order[-1]`` — the same "done" step
    the report grades 100%). Returns counts plus ``byStep`` (how identical glyphs
    split across the shared keys, including the uncoloured ``-1`` bucket) and
    ``differGlyphs`` (the names that disagree, in glyph order) for the expandable
    list. A single-master font has every glyph identical; an empty/no-master font
    returns all-zero with empty lists."""
    final_step = int(order[-1]) if order else None
    identical = differ = done_everywhere = 0
    by_step: dict[int, int] = {}
    differ_glyphs: list[str] = []
    for name in glyph_names:
        keys = [int(current.get(master_id, {}).get(name, colornames.NO_COLOR))
                for master_id in master_ids]
        if not keys:
            continue
        shared = keys[0] if len(set(keys)) == 1 else None
        if shared is not None:
            identical += 1
            by_step[shared] = by_step.get(shared, 0) + 1
            if final_step is not None and shared == final_step:
                done_everywhere += 1
        else:
            differ += 1
            differ_glyphs.append(name)
    return {
        "total": identical + differ,
        "masterCount": len(master_ids),
        "finalStep": final_step,
        "identical": identical,
        "differ": differ,
        "doneEverywhere": done_everywhere,
        "byStep": {str(key): count for key, count in sorted(by_step.items())},
        "differGlyphs": differ_glyphs,
    }


# --------------------------------------------------------------------------- #
# Full JSON model
# --------------------------------------------------------------------------- #

_OUTLINE_CACHE_KEY = "com.dinamo.azcolorflow.outlineCache"


def _change_stamp(glyph) -> float | None:
    """Epoch seconds of a glyph's ``lastChange`` (NSDate or datetime), or ``None``
    when it has none — foundry setups often disable lastChange, so a missing
    stamp must force re-extraction rather than silently reuse a stale outline."""
    value: Any = getattr(glyph, "lastChange", None)
    if value is None:
        return None
    interval = cast(Any, getattr(value, "timeIntervalSince1970", None))
    if callable(interval):
        try:
            return float(cast(Any, interval()))
        except Exception:
            return None
    try:
        return float(value.timestamp())          # datetime
    except Exception:
        try:
            return float(value)                   # already epoch
        except (TypeError, ValueError):
            return None


def _component_deps(font, glyph, master_ids: list, seen: set) -> set:
    """Names of every glyph referenced (recursively) as a component by any of
    ``glyph``'s master layers — so a composite is invalidated when a base it
    draws changes, even though the composite's own lastChange did not."""
    deps: set = set()
    for master_id in master_ids:
        try:
            layer = glyph.layers[master_id]
        except Exception:
            layer = None
        for component in (getattr(layer, "components", None) or []):
            base_name = getattr(component, "componentName", None) or getattr(component, "name", None)
            if not base_name or base_name in seen:
                continue
            seen.add(base_name)
            deps.add(base_name)
            base = font.glyphs[base_name]
            if base is not None:
                deps |= _component_deps(font, base, master_ids, seen)
    return deps


def _effective_stamp(font, glyph, master_ids: list) -> float | None:
    """Newest lastChange among a glyph and everything it draws via components.
    ``None`` if any of them lacks a stamp (forces re-extraction)."""
    newest = _change_stamp(glyph)
    if newest is None:
        return None
    for base_name in _component_deps(font, glyph, master_ids, set()):
        base = font.glyphs[base_name]
        if base is None:
            continue
        stamp = _change_stamp(base)
        if stamp is None:
            return None
        newest = max(newest, stamp)
    return newest


def _em_boxes(font) -> dict[str, tuple[float, float]]:
    """``{master_id: (ascender, descender)}`` — the master's vertical metrics, so the
    cell glyphs share one baseline-aligned square scale (a/A keep relative sizes)."""
    upm = float(getattr(font, "upm", None) or 1000.0)
    boxes: dict[str, tuple[float, float]] = {}
    for master in font.masters:
        ascender = getattr(master, "ascender", None)
        descender = getattr(master, "descender", None)
        ascender = float(ascender) if ascender is not None else upm * 0.75
        descender = float(descender) if descender is not None else -upm * 0.25
        if ascender - descender <= 0:  # degenerate metrics → fall back to a sane em
            ascender, descender = upm * 0.75, -upm * 0.25
        boxes[master.id] = (ascender, descender)
    return boxes


def _outline_signature(font) -> list:
    """A signature of the masters' geometry; if it changes (master added/removed,
    metrics or upm edited) the whole outline cache is dropped."""
    upm = round(float(getattr(font, "upm", None) or 1000.0), 3)
    return [upm] + [[mid, round(asc, 3), round(desc, 3)]
                    for mid, (asc, desc) in _em_boxes(font).items()]


def _outline_cache_load(font, signature: list) -> dict:
    """The per-session outline cache from ``font.tempData`` (stored as a JSON
    string so it round-trips cleanly), or a fresh cache when absent, unreadable,
    or built for a different master signature."""
    store = getattr(font, "tempData", None)
    if store is not None:
        try:
            raw = store[_OUTLINE_CACHE_KEY]
        except Exception:
            raw = None
        if raw:
            try:
                cache = json.loads(raw if isinstance(raw, str) else str(raw))
                if isinstance(cache, dict) and cache.get("sig") == signature:
                    return cache
            except Exception:
                pass
    return {"sig": signature, "glyphs": {}}


def _outline_cache_store(font, cache: dict) -> None:
    store = getattr(font, "tempData", None)
    if store is None:
        return
    try:
        store[_OUTLINE_CACHE_KEY] = json.dumps(cache, separators=(",", ":"))
    except Exception:
        pass


def _outline_paths(font, glyph_names: list, progress=None) -> dict:
    """Per-master ``{glyph_name: {"d", "vb"}}`` of glyph outlines for the heatmap
    cells (every glyph in font order, so any shown cell can draw its letter), each
    entry sharing the master's em box.

    Outlines are cached for the session in ``font.tempData``: only glyphs whose
    ``lastChange`` — their own or a component they draw — is newer than the cache
    are re-extracted, so regenerating the report after a few edits is near-instant
    instead of re-walking every layer. Bounded by a TOTAL outline budget so very
    large fonts keep the report a sane size."""
    budget = 100000   # global ceiling on emitted outlines, generous so every glyph draws
    ems = _em_boxes(font)
    master_ids = list(ems.keys())
    signature = _outline_signature(font)
    cache = _outline_cache_load(font, signature)
    entries = cache.get("glyphs")
    if not isinstance(entries, dict):
        entries = {}
        cache["glyphs"] = entries
    dirty = False

    paths: dict = {mid: {} for mid in master_ids}
    produced = 0
    total_names = len(glyph_names) or 1
    for position, name in enumerate(glyph_names):
        # Outline extraction is the report's heaviest phase; report the fraction
        # walked (every 16 glyphs) so the loader bar tracks real progress.
        if progress is not None and position % 16 == 0:
            try:
                progress(position / total_names)
            except Exception:
                pass
        if produced >= budget:
            break
        glyph = font.glyphs[name]
        if glyph is None:
            continue
        stamp = _effective_stamp(font, glyph, master_ids)
        cached = entries.get(name)
        by_master: dict | None = None
        # A cache hit is: same stamp AND the same master set was EXAMINED last time.
        # The master set is already pinned by the signature, so an empty ``m`` (an
        # inkless or partial-master glyph that produced no outline anywhere) is a
        # valid hit — otherwise such glyphs would be re-extracted every run.
        if (isinstance(cached, dict) and stamp is not None and cached.get("t") == stamp
                and isinstance(cached.get("m"), dict)
                and cached.get("masters") == master_ids):
            by_master = cached["m"]
        if by_master is None:
            by_master = {}
            for master_id in master_ids:
                try:
                    layer = glyph.layers[master_id]
                except Exception:
                    layer = None
                _asc, _desc = ems[master_id]
                outline = glyphsvg.layer_outline_em(layer, _asc, _desc) if layer is not None else {}
                if outline:
                    by_master[master_id] = outline
            entries[name] = {"t": stamp, "masters": master_ids, "m": by_master}
            dirty = True
        for master_id, outline in by_master.items():
            if produced >= budget:
                break
            if outline:
                paths[master_id][name] = outline
                produced += 1

    present = set(glyph_names)
    for stale in [key for key in entries if key not in present]:
        del entries[stale]
        dirty = True
    if dirty:
        _outline_cache_store(font, cache)
    if progress is not None:
        try:
            progress(1.0)
        except Exception:
            pass
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


def _logo_master(font):
    """The master to draw the header logo with: Regular, else Bold, else the first."""
    if not font.masters:
        return None
    for target in ("regular", "bold"):
        for master in font.masters:
            if (master.name or "").lower() == target:
                return master
    return font.masters[0]


def _family_logo(font) -> dict:
    """The family name set in the font's own glyphs (via :func:`_logo_master`) as a
    single ``{"d", "vb"}`` outline, so the report header shows the typeface in
    itself. ``{}`` when it can't be drawn (no master / name / matching glyphs)."""
    if font is None:
        return {}
    master = _logo_master(font)
    name = font.familyName or ""
    if master is None or not name:
        return {}
    upm = float(getattr(font, "upm", None) or 1000.0)
    space = upm * 0.28
    layers: list = []
    advance = 0.0
    for char in name:
        glyph = None if char == " " else font.glyphs[char]
        layer = glyph.layers[master.id] if glyph is not None else None
        if layer is None:
            advance += space
            continue
        layers.append((layer, advance))
        advance += (getattr(layer, "width", 0) or 0)
    return glyphsvg.layers_outline(layers)


def _favicon_data_uri() -> str:
    """The bundled brand favicon as a self-contained ``data:`` URI. Prefers
    ``favicon.gif`` (base64), then ``favicon.png`` (base64), and falls back to
    ``favicon.svg`` (URL-encoded) beside this module. ``""`` when none present."""
    here = Path(__file__).parent
    for name, mime in (("favicon.gif", "image/gif"), ("favicon.png", "image/png")):
        try:
            data = (here / name).read_bytes()
        except OSError:
            continue
        return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")
    try:
        text = (here / "favicon.svg").read_text(encoding="utf-8")
    except OSError:
        return ""
    return "data:image/svg+xml," + quote(re.sub(r">\s+<", "><", text).strip())


def _glyph_groups(font, attr: str) -> dict[str, list[str]]:
    """``{group_value: [glyph_name]}`` grouping all glyphs by a per-glyph
    attribute (``script`` or ``category``); a missing/blank value -> ``"Other"``."""
    groups: dict[str, list[str]] = {}
    for glyph in font.glyphs:
        value = getattr(glyph, attr, None) or "Other"
        groups.setdefault(str(value), []).append(glyph.name)
    return groups


def _coverage_for(current: dict, groups: dict[str, list[str]],
                  order: list[str]) -> dict[str, list[dict]]:
    """Per-master coverage rows for one grouping: each row is a group's
    ``{key, total, final, started, uncolored, counts}`` using the SAME counting
    as the palette/dashboard, restricted to that group's glyphs. Rows are sorted
    largest group first."""
    last = order[-1] if order else None
    result: dict[str, list[dict]] = {}
    for master_id, per_glyph in current.items():
        rows = []
        for group, names in groups.items():
            colors = snapshot_to_colors({name: per_glyph.get(name, colornames.NO_COLOR)
                                         for name in names})
            counts = master_counts(colors, order)
            total = len(names)
            started = total - uncolored_count(colors, order)
            final = started if last is None else counts.get(last, 0)
            rows.append({"key": group, "total": total, "final": final, "started": started,
                         "uncolored": total - started, "counts": counts,
                         "dist": colornames.single_counts_from_colors(colors, order)})
        rows.sort(key=lambda row: (-row["total"], row["key"]))
        result[master_id] = rows
    return result


_SCRIPT_DISPLAY = {
    "latin": "Latin", "greek": "Greek", "cyrillic": "Cyrillic", "arabic": "Arabic",
    "hebrew": "Hebrew", "devanagari": "Devanagari", "bengali": "Bangla",
    "gujarati": "Gujarati", "gurmukhi": "Gurmukhi", "tamil": "Tamil",
    "telugu": "Telugu", "kannada": "Kannada", "malayalam": "Malayalam",
    "oriya": "Odia", "sinhala": "Sinhala", "thai": "Thai", "lao": "Lao",
    "tibetan": "Tibetan", "myanmar": "Myanmar", "khmer": "Khmer",
    "georgian": "Georgian", "armenian": "Armenian", "hangul": "Hangul",
    "han": "Han", "hiragana": "Hiragana", "katakana": "Katakana", "kana": "Kana",
    "cherokee": "Cherokee", "Other": "Other",
}


def _script_display(key: str) -> str:
    """Human label for a Glyphs script id (``latin`` -> ``Latin``)."""
    if key in _SCRIPT_DISPLAY:
        return _SCRIPT_DISPLAY[key]
    return key if key == "Other" else key[:1].upper() + key[1:]


def _representative_glyph(font, names: list[str]) -> str:
    """Pick one canonical glyph to stand for a script: prefer a ``Letter``, then
    the lowest Unicode codepoint (so Latin -> ``A``, Greek -> ``Alpha``). Falls
    back to the first name when nothing is encoded."""
    best_rank: tuple | None = None
    best_name = names[0] if names else ""
    for name in names:
        glyph = font.glyphs[name]
        if glyph is None:
            continue
        category = str(getattr(glyph, "category", None) or "")
        unicode_hex = getattr(glyph, "unicode", None)
        try:
            codepoint = int(unicode_hex, 16) if unicode_hex else 0x110000
        except (TypeError, ValueError):
            codepoint = 0x110000
        rank = (0 if category == "Letter" else 1, codepoint, name)
        if best_rank is None or rank < best_rank:
            best_rank, best_name = rank, name
    return best_name


def _script_meta(font) -> dict[str, dict]:
    """``{scriptKey: {"name": display, "glyph": representativeName}}`` so the
    dashboard's script grid can label each square and draw a sample letter; the
    outline itself is pulled client-side from the per-master ``paths``."""
    return {key: {"name": _script_display(key), "glyph": _representative_glyph(font, names)}
            for key, names in _glyph_groups(font, "script").items()}


def build_coverage(font, current: dict, order: list[str]) -> dict:
    """Completion broken down by Unicode script and by glyph category, per master
    — the data behind the dashboard's Coverage view (#13). ``scriptMeta`` adds a
    display name + representative glyph per script for the script grid."""
    return {
        "byScript": _coverage_for(current, _glyph_groups(font, "script"), order),
        "byCategory": _coverage_for(current, _glyph_groups(font, "category"), order),
        "scriptMeta": _script_meta(font),
    }


def _glyph_journeys(history: dict, dates: list, current: dict, glyph_names: list,
                    order: list, cap: int = 400) -> dict:
    """Per-master ``{glyph_name: [key_per_date]}`` for the heatmap drill-down
    sparkline — only *unfinished* glyphs whose step actually *changed* over the
    recorded dates (a flat journey has nothing to show), capped for big fonts.
    Each list is aligned to ``dates`` (oldest-first); missing dates read as
    uncoloured."""
    if not dates:
        return {}
    last = order[-1] if order else None
    journeys: dict = {}
    for master_id, per_glyph in current.items():
        shown: dict = {}
        produced = 0
        for name in glyph_names:
            if produced >= cap:
                break
            key = per_glyph.get(name)
            finished = str(key) == last
            if finished:
                continue
            journey = [history.get(date, {}).get(master_id, {}).get(name, colornames.NO_COLOR)
                       for date in dates]
            if len(set(journey)) > 1:   # changed at least once -> worth a sparkline
                shown[name] = journey
                produced += 1
        journeys[master_id] = shown
    return journeys


def build_journey_index(history: dict, dates: list) -> dict:
    """Sparse per-master ``{glyph_name: [[iso_date, step_key], ...]}`` of colour
    *change-events* — the first observation of each glyph plus every date its key
    actually changed. Reconstructs full state at any date by carrying the last
    event forward, so it stays small for big fonts (vs the dense ``journeys``
    array). Missing dates read as uncoloured. Covers every glyph seen in history,
    aligned to ``dates`` (oldest-first)."""
    if not dates:
        return {}
    index: dict = {}
    master_ids: set = set()
    for per_master in history.values():
        master_ids.update(per_master.keys())
    for master_id in master_ids:
        names: set = set()
        for date in dates:
            names.update(history.get(date, {}).get(master_id, {}).keys())
        per_glyph: dict = {}
        for name in names:
            events: list = []
            previous = None
            for date in dates:
                key = history.get(date, {}).get(master_id, {}).get(name, colornames.NO_COLOR)
                if key != previous:
                    events.append([date, key])
                    previous = key
            per_glyph[name] = events
        index[master_id] = per_glyph
    return index


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


def build_model(font, now: datetime, current: dict, previous: dict, progress=None) -> dict:
    """The full data model the JS app renders. Pure aside from reading the
    font's colorNames.txt (via _meaning_and_none) — the same source the palette
    uses, so counts stay in lockstep.

    ``progress`` (optional ``Callable[[float], None]``) receives a 0->1 fraction
    so a caller can drive a determinate loader; the outline phase dominates the
    cost, so it gets most of the band."""
    meaning, none_label = _meaning_and_none(font)
    order = list(meaning.keys())
    display = display_from_meaning(meaning, none_label)
    steps = [{"key": key, "label": label} for key, label in display
             if key != colornames.NO_COLOR]
    none_text = next((label for key, label in display
                      if key == colornames.NO_COLOR), "")
    glyph_total = len(font.glyphs)
    glyph_names = list(current[font.masters[0].id].keys()) if font.masters else []
    # Use Glyphs' default GlyphData order, not the font's glyphOrder custom param.
    glyph_names = default_glyph_order(font, glyph_names)

    previews = _master_previews(font)
    masters = []
    for master in font.masters:
        per_glyph = current.get(master.id, {})
        colors = snapshot_to_colors(per_glyph)
        masters.append({
            "id": master.id,
            "name": master.name,
            "keys": [per_glyph.get(name, colornames.NO_COLOR) for name in glyph_names],
            "counts": master_counts(colors, order),
            "uncolored": uncolored_count(colors, order),
            "preview": previews.get(master.id, {}),
        })

    def _outline_progress(frac: float) -> None:
        if progress is not None:
            try:
                progress(0.05 + 0.90 * frac)
            except Exception:
                pass

    # Hidden pref: skip the (heavy) per-glyph outline SVGs for a much lighter report.
    # The report JS already falls back to plain colour swatches when paths are absent.
    paths = {} if no_glyph_svg() else _outline_paths(font, glyph_names, progress=_outline_progress)

    # Day-timeline substrate. Storage rule mirrors how history is recorded:
    #   * No git  -> the userData per-save log, grouped by date (last save of each day).
    #   * Git     -> git commits are the store; read the per-day history from them and
    #                merge it under any *frozen* pre-git userData past (live userData
    #                saves win on a shared day, being the actual save state).
    # When there's no repo, ``git_day_history`` is empty and this reduces to userData.
    # Either way, fold today's live snapshot in under today's date so the newest point
    # reflects current work (same-day overwrite keeps re-running idempotent).
    today = now.strftime("%Y-%m-%d")
    day_history = group_saves_by_date(load_history(font))
    git_days = git_day_history(font)
    if git_days:
        day_history = azcolorflow_git.merge_history(day_history, git_days)
    history = {**day_history, today: current}
    series = history_series(history, order)
    dates = [point["date"] for point in series]
    trend = {
        "series": series,
        "dates": dates,
        "today": today,
        "streak": progress_streak(history, order),
    }
    journeys = _glyph_journeys(history, dates, current, glyph_names, order)
    journey_index = build_journey_index(history, dates)

    # Fine-grain timeline: every checkpoint is its own point, finer than the per-day
    # view. Source depends on the storage mode — git per-commit when the font is in a
    # repo, else the no-git per-save log from userData (both are {datetime: snapshot}).
    # Computed fresh (commits) / read from userData (saves); the report ships this as the
    # "commit" dataset plus a ``fineKind`` tag so the granularity toggle can label itself
    # ("With commits" vs "Per save"), and swaps which dataset drives the whole timeline.
    commit_trend = commit_journeys = commit_journey_index = None
    fine_kind = None
    fine_history = commit_timeline_history(font)
    if fine_history:
        fine_kind = "commit"
    else:
        fine_history = load_history(font)            # no-git: the per-save log
        if fine_history:
            fine_kind = "save"
    if fine_history:
        fine_history = {**fine_history, now.strftime("%Y-%m-%dT%H:%M:%S"): current}
        commit_series = history_series(fine_history, order)
        commit_dates = [point["date"] for point in commit_series]
        commit_trend = {
            "series": commit_series,
            "dates": commit_dates,
            "today": commit_dates[-1] if commit_dates else None,
            "streak": progress_streak(fine_history, order),
        }
        commit_journeys = _glyph_journeys(
            fine_history, commit_dates, current, glyph_names, order)
        commit_journey_index = build_journey_index(fine_history, commit_dates)

    meta = glyph_meta(font)
    metas = [meta.get(name, {}) for name in glyph_names]
    categories = [(entry.get("category") or "Other") for entry in metas]
    scripts = [(entry.get("script") or "Other") for entry in metas]

    if progress is not None:
        try:
            progress(1.0)
        except Exception:
            pass

    return {
        "family": font.familyName or "",
        "fileName": Path(font.filepath).name if font.filepath else (font.familyName or "Untitled"),
        "version": f"{font.versionMajor}.{font.versionMinor:03d}",
        "generated": now.strftime("%Y-%m-%d"),
        "glyphTotal": glyph_total,
        "order": order,
        "steps": steps,
        "noneLabel": none_text,
        "glyphNames": glyph_names,
        "categories": categories,
        "scripts": scripts,
        # Parity invariant: masters[].counts/keys above ship ALL glyphs (raw
        # truth — the heatmap needs them to render the dimmed cells); the report
        # ALWAYS applies this exclusion client-side to every percentage.
        "nonExporting": non_exporting_names(font),
        "masters": masters,
        "colors": {str(index): labelcolors.hex_for(rgba)
                   for index, rgba in enumerate(labelcolors.read_label_colors())},
        "filePath": font.filepath or "",
        "paths": paths,
        "outlineChanges": collect_outline_changes(font),
        "favicon": _favicon_data_uri(),
        "logo": _family_logo(font),
        "trend": trend,
        "journeys": journeys,
        "journeyIndex": journey_index,
        "trendCommits": commit_trend,                # fine-grain set (git commits OR no-git saves)
        "journeysCommits": commit_journeys,
        "journeyIndexCommits": commit_journey_index,
        "hasCommits": bool(commit_trend and len(commit_trend["series"]) >= 2),
        "fineKind": fine_kind,                        # "commit" | "save" | None (labels the toggle)
        "lastEdit": glyph_last_edit(font, now),
        "coverage": build_coverage(font, current, order),
        "changes": compute_changes(current, previous),
        "crossMaster": cross_master_summary(
            current, [master.id for master in font.masters], glyph_names, order),
    }


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main(font=None, progress=None, open_when_done: bool = True) -> Path | None:
    """Build the report, write it to a temp file, and (when ``open_when_done``)
    open it in the browser. ``progress`` (optional ``Callable[[float], None]``)
    receives a monotonic 0->1 fraction at each phase boundary so a caller can drive
    a determinate loading bar. Returns the written ``Path`` (so a caller can offer
    Open/Save itself), or ``None`` if nothing was produced."""
    def _emit(frac: float) -> None:
        if progress is not None:
            try:
                progress(frac)
            except Exception:
                pass

    if font is None and Glyphs is not None:
        font = Glyphs.font
    if font is None:
        Message("Open a font first.", "Color Font Dashboard")
        return
    total = len(font.glyphs)
    if total == 0:
        Message("No glyphs to report on.", "Color Font Dashboard")
        return

    _emit(0.02)
    now = datetime.now()
    current = build_master_glyph_colors(font)
    _emit(0.05)
    # Backfill the dated history from the font's git commits (incremental — only days
    # not already recorded). No-op when the font isn't in a git repo. This is what lets
    # the timeline populate immediately instead of accruing one snapshot per day.
    try:
        backfill_from_git(font, progress=lambda frac: _emit(0.05 + 0.10 * frac))
    except Exception:
        pass
    _emit(0.15)
    previous = load_snapshot(font) or current
    model = build_model(font, now, current, previous, progress=lambda frac: _emit(0.15 + 0.65 * frac))
    _emit(0.80)
    html = azcolorflow_assets.build_html(model)
    _emit(0.94)
    save_snapshot(font, current)
    # Note: today's snapshot is NOT persisted here — generating a report must not modify
    # the font. The plugin records it into userData on save (a will-save hook); the
    # report still shows today via the in-memory fold above.
    _emit(0.96)

    base = Path(font.filepath).stem if font.filepath else (font.familyName or "font")
    out_path = Path(tempfile.gettempdir()) / f"{now.strftime('%Y%m%d')} {base} — Color Flow.html"
    try:
        out_path.write_text(html, encoding="utf-8")
    except OSError as error:
        Message(f"Could not write the dashboard:\n{error}", "Color Font Dashboard")
        return None
    _emit(0.98)
    if open_when_done:
        webbrowser.open(out_path.as_uri())
    _emit(1.0)
    return out_path
