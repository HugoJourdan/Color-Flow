"""Tests for the Color Font Dashboard.

The pure data + HTML layer is exercised directly. The GlyphsApp-touching
helpers (mode pref, colorNames.txt resolution, per-glyph map, snapshot
persistence) are covered with lightweight fakes + a temp colorNames.txt, so the
only thing left to manual testing is the real ``from GlyphsApp import ...`` line.
"""

from __future__ import annotations

from datetime import datetime
from typing import SupportsIndex, overload

import colorflow_dashboard as db
import colornames as cc

# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #

class _FakeLayers(dict[str, "_FakeLayerColor | None"]):
    """Glyphs returns ``None`` for a master with no layer, not KeyError."""

    def __getitem__(self, key: str) -> _FakeLayerColor | None:
        return self.get(key)


class _FakeGlyph:
    def __init__(self, name: str, layers: dict) -> None:
        self.name = name
        self.layers = _FakeLayers(layers)
        # Dynamic GSGlyph fields the dashboard reads; tests set them as needed.
        self.lastChange: object | None = None
        self.script: str | None = None
        self.category: str | None = None
        self.subCategory: str | None = None
        self.case: str | None = None
        self.unicode: str | None = None


class _FakeMaster:
    def __init__(self, id_: str, name: str) -> None:
        self.id = id_
        self.name = name


class _FakeGlyphs(list["_FakeGlyph"]):
    """Mirrors ``GSFont.glyphs``: int indexing + iteration like a list, plus
    name indexing (``font.glyphs["A"]``) that returns ``None`` when absent."""

    @overload
    def __getitem__(self, key: SupportsIndex) -> _FakeGlyph: ...
    @overload
    def __getitem__(self, key: slice) -> list[_FakeGlyph]: ...
    @overload
    def __getitem__(self, key: str) -> _FakeGlyph | None: ...

    def __getitem__(self, key: SupportsIndex | slice | str) -> _FakeGlyph | list[_FakeGlyph] | None:
        if isinstance(key, str):
            return next((glyph for glyph in self if glyph.name == key), None)
        return super().__getitem__(key)


class _FakeFont:
    versionMajor = 2
    versionMinor = 5

    def __init__(self, masters: list, glyphs: list | None = None,
                 filepath: str = "/fonts/Acme.glyphs", family: str = "Acme Sans") -> None:
        self.masters = masters
        self.glyphs = _FakeGlyphs(glyphs if glyphs is not None else [])
        self.filepath = filepath
        self.familyName = family
        # The per-session outline cache lives here (a JSON string per key); tests
        # that exercise the cache assign a plain dict.
        self.tempData: dict[str, object] = {}


class _Defaults(dict):
    """Mimics ``Glyphs.defaults``: a missing key reads back as ``None``."""

    def __getitem__(self, key) -> object:
        return self.get(key)


class _FakeGlyphsApp:
    def __init__(self) -> None:
        self.defaults = _Defaults()


# --------------------------------------------------------------------------- #
# color_to_key
# --------------------------------------------------------------------------- #

def test_color_to_key_maps_none_to_no_color_sentinel() -> None:
    assert db.color_to_key(None) == cc.NO_COLOR


def test_color_to_key_passes_real_colours_through_as_int() -> None:
    assert db.color_to_key(3) == 3
    assert db.color_to_key(0) == 0
    assert db.color_to_key(11) == 11


# --------------------------------------------------------------------------- #
# snapshot_to_colors / master_counts parity / uncolored_count
# --------------------------------------------------------------------------- #

def test_snapshot_to_colors_inverts_color_to_key() -> None:
    per_glyph = {"A": 0, "B": cc.NO_COLOR, "C": 3}
    assert db.snapshot_to_colors(per_glyph) == [0, None, 3]


# A non-numeric file order with a hidden (empty-label) colour — the exact shape
# that breaks if the counting order is taken from visible_labels instead of
# load_meaning. Locks the load-bearing parity invariant.
_HIDDEN_REORDERED = (
    "purple=Outline\n"
    "lightGreen=Anchors\n"
    "red=\n"            # known but hidden -> still a slot in the counting order
    "yellow=Ready\n"
)


def _order_from(text: str) -> list[str]:
    return list(cc.parse_color_names(text).keys())


def test_master_counts_matches_palette_step_mode() -> None:
    order = _order_from(_HIDDEN_REORDERED)  # ["8", "4", "0", "3"]
    colors = [8, 4, None, 3, 0, 8]
    assert db.master_counts(colors, order, is_free=False) == cc.counts_from_colors(colors, order)


def test_master_counts_matches_palette_free_mode() -> None:
    order = _order_from(_HIDDEN_REORDERED)
    colors = [8, 4, None, 3, 0, 8]
    assert db.master_counts(colors, order, is_free=True) == cc.single_counts_from_colors(colors, order)


def test_step_counts_are_cumulative_over_file_order() -> None:
    order = _order_from(_HIDDEN_REORDERED)  # ["8", "4", "0", "3"]
    # one glyph at yellow (the final step) credits every earlier step in order
    counts = db.master_counts([3], order, is_free=False)
    assert counts == {"8": 1, "4": 1, "0": 1, "3": 1}


def test_uncolored_count_counts_none_and_out_of_order_colours() -> None:
    order = _order_from(_HIDDEN_REORDERED)  # {"8","4","0","3"}
    # None -> uncoloured; 5 (darkGreen) is not in the order -> uncoloured; 8 is.
    assert db.uncolored_count([8, None, 5, 4], order) == 2


# --------------------------------------------------------------------------- #
# display_from_meaning / label_map / is_finished
# --------------------------------------------------------------------------- #

def test_display_from_meaning_keeps_visible_then_none_last() -> None:
    meaning = cc.parse_color_names(_HIDDEN_REORDERED)
    display = db.display_from_meaning(meaning, none_label="Nothing")
    assert display == [(8, "Outline"), (4, "Anchors"), (3, "Ready"), (cc.NO_COLOR, "Nothing")]


def test_display_from_meaning_falls_back_to_default_none_label() -> None:
    display = db.display_from_meaning({"0": "Red"}, none_label="")
    assert display[-1] == (cc.NO_COLOR, cc.DEFAULT_LABELS[cc.NO_COLOR])


# --------------------------------------------------------------------------- #
# compute_changes
# --------------------------------------------------------------------------- #

def test_compute_changes_reports_only_changed_glyphs() -> None:
    current = {"m1": {"A": 0, "B": 3, "C": cc.NO_COLOR}}
    previous = {"m1": {"A": 0, "B": 2, "C": cc.NO_COLOR}}
    assert db.compute_changes(current, previous) == {"m1": {"B": (2, 3)}}


def test_compute_changes_ignores_newly_added_glyphs() -> None:
    current = {"m1": {"A": 0, "NEW": 5}}
    previous = {"m1": {"A": 0}}
    assert db.compute_changes(current, previous) == {"m1": {}}


def test_compute_changes_handles_missing_master_in_previous() -> None:
    current = {"m1": {"A": 0}, "m2": {"A": 3}}
    previous = {"m1": {"A": 1}}
    assert db.compute_changes(current, previous) == {"m1": {"A": (1, 0)}, "m2": {}}


# --------------------------------------------------------------------------- #
# GlyphsApp-touching helpers (fakes)
# --------------------------------------------------------------------------- #

def test_build_master_glyph_colors_all_glyphs_layer_color_only() -> None:
    master = _FakeMaster("m1", "Regular")
    glyphs = [
        _FakeGlyph("A", {"m1": _FakeLayerColor(0)}),
        _FakeGlyph("B", {}),                       # no layer for m1 -> uncoloured
        _FakeGlyph("C", {"m1": _FakeLayerColor(3)}),
    ]
    font = _FakeFont([master], glyphs)
    assert db.build_master_glyph_colors(font) == {"m1": {"A": 0, "B": cc.NO_COLOR, "C": 3}}


# --------------------------------------------------------------------------- #
# default_glyph_order — bypass the glyphOrder custom parameter
# --------------------------------------------------------------------------- #

class _FakeGlyphsInfo:
    """Stand-in for ``GSGlyphsInfo``: maps a glyph to its GlyphData index, with
    ``NS_NOT_FOUND`` for glyphs the database doesn't know."""

    def __init__(self, index_by_name: dict) -> None:
        self._index = index_by_name

    def glyphIndex_(self, glyph) -> int:
        return self._index.get(glyph.name, db.NS_NOT_FOUND)


class _FakeFontWithInfo(_FakeFont):
    def __init__(self, masters: list, glyphs: list, index_by_name: dict) -> None:
        super().__init__(masters, glyphs)
        self._info = _FakeGlyphsInfo(index_by_name)

    def glyphsInfo(self) -> _FakeGlyphsInfo:
        return self._info


def test_default_glyph_order_sorts_by_glyphdata_index_ignoring_custom_order() -> None:
    # font.glyphs is in a custom (glyphOrder) order: C, A, B
    glyphs = [_FakeGlyph("C", {}), _FakeGlyph("A", {}), _FakeGlyph("B", {})]
    font = _FakeFontWithInfo([_FakeMaster("m1", "R")], glyphs, {"A": 0, "B": 1, "C": 2})
    assert db.default_glyph_order(font, ["C", "A", "B"]) == ["A", "B", "C"]


def test_default_glyph_order_unknown_glyphs_sort_last_keeping_relative_order() -> None:
    glyphs = [_FakeGlyph("zz", {}), _FakeGlyph("A", {}), _FakeGlyph("yy", {})]
    font = _FakeFontWithInfo([_FakeMaster("m1", "R")], glyphs, {"A": 0})  # zz, yy unknown
    assert db.default_glyph_order(font, ["zz", "A", "yy"]) == ["A", "zz", "yy"]


def test_default_glyph_order_passthrough_without_glyphs_info() -> None:
    glyphs = [_FakeGlyph("B", {}), _FakeGlyph("A", {})]
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs)  # no glyphsInfo()
    assert db.default_glyph_order(font, ["B", "A"]) == ["B", "A"]


def test_build_model_uses_default_order_over_glyph_iteration_order(tmp_path) -> None:
    glyphs = [_FakeGlyph("C", {"m1": _FakeLayerColor(0)}),
              _FakeGlyph("A", {"m1": _FakeLayerColor(0)}),
              _FakeGlyph("B", {"m1": _FakeLayerColor(0)})]
    font = _FakeFontWithInfo([_FakeMaster("m1", "R")], glyphs, {"A": 0, "B": 1, "C": 2})
    font.filepath = str(tmp_path / "Font.glyphs")
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["glyphNames"] == ["A", "B", "C"]


def test_free_mode_reads_global_pref(monkeypatch) -> None:
    fake = _FakeGlyphsApp()
    fake.defaults[db.FREE_KEY] = True
    monkeypatch.setattr(db, "Glyphs", fake)
    assert db.free_mode() is True
    fake.defaults[db.FREE_KEY] = False
    assert db.free_mode() is False


def test_free_mode_defaults_to_step_without_glyphs(monkeypatch) -> None:
    monkeypatch.setattr(db, "Glyphs", None)
    assert db.free_mode() is False


def test_meaning_and_none_reads_font_dir_color_names(tmp_path) -> None:
    (tmp_path / "colorNames.txt").write_text(_HIDDEN_REORDERED + "None=Nothing\n",
                                             encoding="utf-8")
    font = _FakeFont([_FakeMaster("m1", "R")], filepath=str(tmp_path / "Font.glyphs"))
    meaning, none_label = db._meaning_and_none(font)
    assert list(meaning.keys()) == ["8", "4", "0", "3"]
    assert none_label == "Nothing"
    assert db.display_from_meaning(meaning, none_label)[-1] == (cc.NO_COLOR, "Nothing")


def test_snapshot_round_trip_through_defaults(monkeypatch) -> None:
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    assert db.load_snapshot(font) == {}            # nothing stored yet
    db.save_snapshot(font, {"m1": {"A": 0, "B": cc.NO_COLOR}})
    assert db.load_snapshot(font) == {"m1": {"A": 0, "B": cc.NO_COLOR}}


def test_coerce_snapshot_stringifies_and_ints() -> None:
    raw = {"m1": {"A": "0", "B": 3}}  # NSDictionary-ish: mixed value types
    assert db._coerce_snapshot(raw) == {"m1": {"A": 0, "B": 3}}
    assert db._coerce_snapshot(None) == {}


def test_record_history_round_trips_and_sorts(monkeypatch) -> None:
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    assert db.load_history(font) == {}                       # nothing yet
    db.record_history(font, {"m1": {"A": 0}}, datetime(2026, 6, 4))
    db.record_history(font, {"m1": {"A": 3}}, datetime(2026, 6, 6))
    db.record_history(font, {"m1": {"A": 4}}, datetime(2026, 6, 5))
    history = db.load_history(font)
    assert list(history.keys()) == ["2026-06-04", "2026-06-05", "2026-06-06"]   # oldest-first
    assert history["2026-06-06"] == {"m1": {"A": 3}}


def test_record_history_same_day_overwrites(monkeypatch) -> None:
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    db.record_history(font, {"m1": {"A": 0}}, datetime(2026, 6, 6, 9))
    db.record_history(font, {"m1": {"A": 8}}, datetime(2026, 6, 6, 17))
    history = db.load_history(font)
    assert list(history.keys()) == ["2026-06-06"]
    assert history["2026-06-06"] == {"m1": {"A": 8}}         # latest capture of the day wins


def test_record_history_caps_to_most_recent(monkeypatch) -> None:
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    for day in range(1, 6):
        db.record_history(font, {"m1": {"A": day}}, datetime(2026, 6, day), cap=3)
    history = db.load_history(font)
    assert list(history.keys()) == ["2026-06-03", "2026-06-04", "2026-06-05"]  # oldest dropped


def test_history_no_op_without_glyphs_or_filepath(monkeypatch) -> None:
    monkeypatch.setattr(db, "Glyphs", None)
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    db.record_history(font, {"m1": {"A": 0}}, datetime(2026, 6, 6))   # silently no-op
    assert db.load_history(font) == {}
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    unsaved = _FakeFont([_FakeMaster("m1", "R")], filepath="")
    db.record_history(unsaved, {"m1": {"A": 0}}, datetime(2026, 6, 6))
    assert db.load_history(unsaved) == {}


def test_coerce_history_stringifies_dates_and_ints() -> None:
    raw = {"2026-06-06": {"m1": {"A": "3"}}}   # NSDictionary-ish
    assert db._coerce_history(raw) == {"2026-06-06": {"m1": {"A": 3}}}
    assert db._coerce_history(None) == {}


# --------------------------------------------------------------------------- #
# Burndown / velocity / forecast
# --------------------------------------------------------------------------- #

_FC_ORDER = ["0", "1", "2"]   # 3 workflow steps; "2" is the final step


def _snap(n_final: int, total: int = 10) -> dict:
    """One master's per-glyph snapshot: ``n_final`` glyphs at the final step (key
    2), the rest uncoloured."""
    return {"m1": {f"g{i}": 2 if i < n_final else cc.NO_COLOR for i in range(total)}}


def _history(pairs: list) -> dict:
    """``[(iso, n_final)]`` -> a dated history of single-master snapshots."""
    return {date: _snap(n_final) for date, n_final in pairs}


def test_history_series_reduces_to_per_master_counts() -> None:
    history = _history([("2026-06-01", 2), ("2026-06-08", 4)])
    series = db.history_series(history, _FC_ORDER, is_free=False)
    assert [point["date"] for point in series] == ["2026-06-01", "2026-06-08"]
    assert series[1]["masters"]["m1"] == {"final": 4, "started": 4, "total": 10}


def test_forecast_steady_progress_gives_eta_and_high_confidence() -> None:
    series = db.history_series(
        _history([("2026-06-01", 2), ("2026-06-08", 4), ("2026-06-15", 6), ("2026-06-22", 8)]),
        _FC_ORDER, is_free=False)
    out = db.forecast_master(series, "m1", total=10, now=datetime(2026, 6, 22), is_free=False)
    assert out["velocityPerWeek"] == 2.0      # +6 over 21 days = 2/week
    assert out["remaining"] == 2 and out["final"] == 8
    assert out["etaIso"] == "2026-06-29"      # 2 remaining / (2/7 per day) = 7 days
    assert out["bandDays"] == 1               # perfectly steady -> tight band
    assert out["confidence"] == "high"


def test_forecast_two_points_is_low_confidence_but_still_estimates() -> None:
    series = db.history_series(_history([("2026-06-01", 3), ("2026-06-08", 6)]),
                              _FC_ORDER, is_free=False)
    out = db.forecast_master(series, "m1", total=10, now=datetime(2026, 6, 8), is_free=False)
    assert out["velocityPerWeek"] == 3.0
    assert out["etaIso"] is not None and out["confidence"] == "low"


def test_forecast_flat_history_has_no_eta() -> None:
    series = db.history_series(_history([("2026-06-01", 5), ("2026-06-08", 5)]),
                              _FC_ORDER, is_free=False)
    out = db.forecast_master(series, "m1", total=10, now=datetime(2026, 6, 8), is_free=False)
    assert out["velocityPerWeek"] == 0.0
    assert out["etaIso"] is None and out["confidence"] == "none"


def test_forecast_single_point_has_no_eta() -> None:
    series = db.history_series(_history([("2026-06-08", 4)]), _FC_ORDER, is_free=False)
    out = db.forecast_master(series, "m1", total=10, now=datetime(2026, 6, 8), is_free=False)
    assert out["etaIso"] is None and out["confidence"] == "none" and out["points"] == 1


def test_forecast_done_master_reports_done() -> None:
    series = db.history_series(_history([("2026-06-01", 6), ("2026-06-08", 10)]),
                              _FC_ORDER, is_free=False)
    out = db.forecast_master(series, "m1", total=10, now=datetime(2026, 6, 8), is_free=False)
    assert out["remaining"] == 0 and out["confidence"] == "done" and out["etaIso"] is None


def test_master_point_free_mode_final_equals_started() -> None:
    per_glyph = {"A": 0, "B": 1, "C": cc.NO_COLOR}    # free: exact labelled, no cumulative final
    point = db._master_point(per_glyph, _FC_ORDER, is_free=True)
    assert point["final"] == point["started"] == 2 and point["total"] == 3


def test_glyph_journeys_only_changed_unfinished_aligned_to_dates() -> None:
    dates = ["2026-06-01", "2026-06-02"]
    history = {
        "2026-06-01": {"m1": {"A": cc.NO_COLOR, "B": 1, "C": 0}},
        "2026-06-02": {"m1": {"A": 1, "B": 1, "C": 2}},
    }
    current = {"m1": {"A": 1, "B": 1, "C": 2}}   # C is at the final step (2) -> finished
    journeys = db._glyph_journeys(history, dates, current, ["A", "B", "C"], _FC_ORDER, is_free=False)
    assert journeys["m1"]["A"] == [cc.NO_COLOR, 1]   # changed + unfinished -> included, date-aligned
    assert "B" not in journeys["m1"]                 # flat journey -> nothing to show
    assert "C" not in journeys["m1"]                 # finished -> excluded
    assert db._glyph_journeys(history, [], current, ["A"], _FC_ORDER, is_free=False) == {}


class _FakeNSDate:
    def __init__(self, timestamp: float) -> None:
        self._timestamp = timestamp

    def timeIntervalSince1970(self) -> float:
        return self._timestamp


def test_days_ago_from_datetime_and_nsdate() -> None:
    now = datetime(2026, 6, 10)
    assert db._days_ago(datetime(2026, 6, 4), now) == 6                 # plain datetime
    nsdate = _FakeNSDate(datetime(2026, 6, 8).timestamp())
    assert db._days_ago(nsdate, now) == 2                               # NSDate-like
    assert db._days_ago(None, now) is None                             # absent -> None
    assert db._days_ago(datetime(2026, 6, 20), now) == 0               # future clamps to 0


def test_glyph_last_edit_is_sparse() -> None:
    edited = _FakeGlyph("A", {"m1": _FakeLayerColor(0)})
    edited.lastChange = _FakeNSDate(datetime(2026, 6, 7).timestamp())
    never = _FakeGlyph("B", {"m1": _FakeLayerColor(0)})   # no lastChange attr
    font = _FakeFont([_FakeMaster("m1", "R")], [edited, never])
    result = db.glyph_last_edit(font, datetime(2026, 6, 10))
    assert result == {"A": 3}                              # B omitted (no timestamp)


def test_progress_streak_counts_trailing_improving_days() -> None:
    # started rises 2->4->5 (3 improving days), dips, then rises again for 2
    history = _history([("2026-06-01", 2), ("2026-06-02", 4), ("2026-06-03", 5),
                        ("2026-06-04", 3), ("2026-06-05", 6), ("2026-06-06", 7)])
    streak = db.progress_streak(history, _FC_ORDER, is_free=False)
    assert streak["current"] == 2     # last two days both improved (3->6->7)
    assert streak["best"] == 2        # two runs of length 2 (06-02..03 and 06-05..06)
    assert streak["days"] == 6


def test_progress_streak_zero_when_last_day_regresses() -> None:
    history = _history([("2026-06-01", 5), ("2026-06-02", 8), ("2026-06-03", 6)])
    assert db.progress_streak(history, _FC_ORDER, is_free=False)["current"] == 0


def test_coverage_groups_by_attribute_and_counts_per_group() -> None:
    letter_a = _FakeGlyph("A", {"m1": _FakeLayerColor(2)})       # at final step 2
    letter_b = _FakeGlyph("B", {"m1": _FakeLayerColor(0)})
    comma = _FakeGlyph("comma", {"m1": _FakeLayerColor(2)})
    for glyph, script, category in ((letter_a, "latin", "Letter"), (letter_b, "latin", "Letter"),
                                    (comma, None, "Punctuation")):
        glyph.script, glyph.category = script, category
    font = _FakeFont([_FakeMaster("m1", "R")], [letter_a, letter_b, comma])
    current = db.build_master_glyph_colors(font)

    assert db._glyph_groups(font, "script") == {"latin": ["A", "B"], "Other": ["comma"]}
    cov = db.build_coverage(font, current, _FC_ORDER, is_free=False)
    by_script = {row["key"]: row for row in cov["byScript"]["m1"]}
    assert cov["byScript"]["m1"][0]["key"] == "latin"          # largest group first
    assert by_script["latin"]["total"] == 2 and by_script["latin"]["final"] == 1  # only A reached step 2
    by_cat = {row["key"]: row for row in cov["byCategory"]["m1"]}
    assert by_cat["Letter"]["total"] == 2 and by_cat["Punctuation"]["total"] == 1


def test_build_coverage_emits_script_meta_with_representative_glyph() -> None:
    letter_a = _FakeGlyph("A", {"m1": _FakeLayerColor(2)})
    letter_b = _FakeGlyph("B", {"m1": _FakeLayerColor(0)})
    comma = _FakeGlyph("comma", {"m1": _FakeLayerColor(2)})
    for glyph, script, category, unicode_hex in ((letter_a, "latin", "Letter", "0041"),
                                                 (letter_b, "latin", "Letter", "0042"),
                                                 (comma, None, "Punctuation", "002C")):
        glyph.script, glyph.category, glyph.unicode = script, category, unicode_hex
    font = _FakeFont([_FakeMaster("m1", "R")], [letter_a, letter_b, comma])
    current = db.build_master_glyph_colors(font)

    meta = db.build_coverage(font, current, _FC_ORDER, is_free=False)["scriptMeta"]
    assert meta["latin"] == {"name": "Latin", "glyph": "A"}     # Letter, lowest codepoint wins
    assert meta["Other"] == {"name": "Other", "glyph": "comma"}  # non-letter group falls to min cp


class _FakeLayerColor:
    def __init__(self, color: int | None, width: float = 500.0) -> None:
        self.color = color
        self.width = width
        # Dynamic GSLayer fields the outline/cache paths read; set by tests.
        self.drawBezierPath: object | None = None
        self.components: list[_FakeComponent] = []


# --------------------------------------------------------------------------- #
# build_model
# --------------------------------------------------------------------------- #

def test_build_model_shape_and_compact_glyph_names(tmp_path) -> None:
    (tmp_path / "colorNames.txt").write_text(
        "purple=Outline\nlightGreen=Anchors\nyellow=Ready\nNone=Nothing\n", encoding="utf-8")
    master = _FakeMaster("m1", "Regular")
    glyphs = [
        _FakeGlyph("A", {"m1": _FakeLayerColor(8)}),
        _FakeGlyph("B", {"m1": _FakeLayerColor(4)}),
        _FakeGlyph("C", {}),  # no layer -> none
    ]
    font = _FakeFont([master], glyphs, filepath=str(tmp_path / "Font.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)

    assert model["family"] == "Acme Sans"
    assert model["fileName"] == "Font.glyphs"
    assert model["version"] == "2.005"   # Glyphs-style zero-padded minor (versionMinor=5)
    assert model["generated"] == "2026-06-05"
    assert model["mode"] == "step"
    assert model["glyphTotal"] == 3
    assert model["order"] == ["8", "4", "3"]
    assert model["steps"] == [{"key": 8, "label": "Outline"},
                              {"key": 4, "label": "Anchors"},
                              {"key": 3, "label": "Ready"}]
    assert model["noneLabel"] == "Nothing"
    assert model["glyphNames"] == ["A", "B", "C"]          # stored once
    assert model["masters"][0]["keys"] == [8, 4, -1]        # parallel to glyphNames
    assert model["changes"] == {"m1": {}}


def test_build_model_counts_match_palette_step_and_free(tmp_path) -> None:
    (tmp_path / "colorNames.txt").write_text(_HIDDEN_REORDERED, encoding="utf-8")
    glyphs = [
        _FakeGlyph("A", {"m1": _FakeLayerColor(8)}),
        _FakeGlyph("B", {"m1": _FakeLayerColor(4)}),
        _FakeGlyph("C", {"m1": _FakeLayerColor(3)}),
        _FakeGlyph("D", {}),  # none
    ]
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs, filepath=str(tmp_path / "F.glyphs"))
    current = db.build_master_glyph_colors(font)
    order = list(cc.parse_color_names(_HIDDEN_REORDERED).keys())
    colors = [8, 4, 3, None]

    step = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert step["mode"] == "step"
    assert step["masters"][0]["counts"] == cc.counts_from_colors(colors, order)
    assert step["masters"][0]["uncolored"] == db.uncolored_count(colors, order)


def test_build_model_free_mode(monkeypatch, tmp_path) -> None:
    fake = _FakeGlyphsApp()
    fake.defaults[db.FREE_KEY] = True
    monkeypatch.setattr(db, "Glyphs", fake)
    (tmp_path / "colorNames.txt").write_text(_HIDDEN_REORDERED, encoding="utf-8")
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(8)}), _FakeGlyph("B", {"m1": _FakeLayerColor(4)})]
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs, filepath=str(tmp_path / "F.glyphs"))
    current = db.build_master_glyph_colors(font)
    order = list(cc.parse_color_names(_HIDDEN_REORDERED).keys())
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["mode"] == "free"
    assert model["masters"][0]["counts"] == cc.single_counts_from_colors([8, 4], order)


def test_build_model_multi_master_keys_align_to_glyph_names(tmp_path) -> None:
    (tmp_path / "colorNames.txt").write_text("purple=Outline\nyellow=Ready\n", encoding="utf-8")
    glyphs = [
        _FakeGlyph("A", {"m1": _FakeLayerColor(8), "m2": _FakeLayerColor(3)}),
        _FakeGlyph("B", {"m1": _FakeLayerColor(3), "m2": _FakeLayerColor(8)}),
    ]
    font = _FakeFont([_FakeMaster("m1", "Regular"), _FakeMaster("m2", "Bold")],
                     glyphs, filepath=str(tmp_path / "F.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)

    assert model["glyphNames"] == ["A", "B"]
    by_id = {m["id"]: m for m in model["masters"]}
    assert by_id["m1"]["keys"] == [8, 3]   # keys[i] aligns with glyphNames[i]
    assert by_id["m2"]["keys"] == [3, 8]


def test_build_model_includes_label_colors_as_hex(tmp_path) -> None:
    import labelcolors
    (tmp_path / "colorNames.txt").write_text("red=R\n", encoding="utf-8")
    font = _FakeFont([_FakeMaster("m1", "R")], [_FakeGlyph("A", {"m1": _FakeLayerColor(0)})],
                     filepath=str(tmp_path / "F.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert set(model["colors"].keys()) == {str(index) for index in range(12)}
    assert model["colors"]["0"] == labelcolors.hex_for(labelcolors.DEFAULTS[0])


def test_build_model_includes_outline_metrics_and_paths(tmp_path) -> None:
    (tmp_path / "colorNames.txt").write_text("red=R\n", encoding="utf-8")
    font = _FakeFont([_FakeMaster("m1", "R")], [_FakeGlyph("A", {"m1": _FakeLayerColor(0)})],
                     filepath=str(tmp_path / "F.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["filePath"] == str(tmp_path / "F.glyphs")
    assert model["paths"] == {"m1": {}}   # fake font has no real layers -> no outlines


class _BezPoint:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class _BezPath:
    def __init__(self, elements: list) -> None:
        self._elements = elements

    def elementCount(self) -> int:
        return len(self._elements)

    def elementAtIndex_associatedPoints_(self, index: int) -> tuple[int, list[_BezPoint]]:
        element_type, points = self._elements[index]
        return element_type, [_BezPoint(x, y) for x, y in points]


def _outline_layer(color: int) -> _FakeLayerColor:
    layer = _FakeLayerColor(color)
    layer.drawBezierPath = _BezPath([(0, [(0, 0)]), (1, [(400, 0)]), (1, [(400, 700)]), (3, [])])
    return layer


class _FakeComponent:
    def __init__(self, name: str) -> None:
        self.componentName = name


def _outline_with(width: float, height: float) -> _FakeLayerColor:
    layer = _FakeLayerColor(0)
    layer.drawBezierPath = _BezPath([(0, [(0, 0)]), (1, [(width, 0)]), (1, [(width, height)]), (3, [])])
    return layer


def _cache_font(glyph: _FakeGlyph) -> _FakeFont:
    font = _FakeFont([_FakeMaster("m1", "R")], [glyph])
    font.tempData = {}   # the session outline cache lives here (JSON string)
    return font


def test_outline_cache_reuses_unchanged_glyph_and_invalidates_on_lastchange() -> None:
    layer = _outline_with(400, 700)
    glyph = _FakeGlyph("A", {"m1": layer})
    glyph.lastChange = _FakeNSDate(100.0)
    font = _cache_font(glyph)
    first = db._outline_paths(font, ["A"])["m1"]["A"]["d"]
    # change the outline but keep lastChange -> the cache must serve the OLD outline
    layer.drawBezierPath = _BezPath([(0, [(0, 0)]), (1, [(999, 0)]), (1, [(999, 9)]), (3, [])])
    reused = db._outline_paths(font, ["A"])["m1"]["A"]["d"]
    assert reused == first
    # bump lastChange -> re-extract, picking up the new outline
    glyph.lastChange = _FakeNSDate(200.0)
    fresh = db._outline_paths(font, ["A"])["m1"]["A"]["d"]
    assert fresh != first


def test_outline_cache_invalidates_composite_when_a_base_changes() -> None:
    base = _FakeGlyph("A", {"m1": _outline_with(400, 700)})
    base.lastChange = _FakeNSDate(100.0)
    composite_layer = _outline_with(420, 720)
    composite_layer.components = [_FakeComponent("A")]
    acute = _FakeGlyph("Aacute", {"m1": composite_layer})
    acute.lastChange = _FakeNSDate(100.0)
    font = _FakeFont([_FakeMaster("m1", "R")], [base, acute])
    font.tempData = {}
    first = db._outline_paths(font, ["A", "Aacute"])["m1"]["Aacute"]["d"]
    # the composite's OWN lastChange is unchanged, but the base it draws changed
    composite_layer.drawBezierPath = _BezPath([(0, [(0, 0)]), (1, [(800, 0)]), (1, [(800, 8)]), (3, [])])
    base.lastChange = _FakeNSDate(300.0)
    second = db._outline_paths(font, ["A", "Aacute"])["m1"]["Aacute"]["d"]
    assert second != first   # component dependency forced a re-extract


def test_outline_cache_never_reuses_glyph_without_lastchange() -> None:
    layer = _outline_with(400, 700)
    glyph = _FakeGlyph("A", {"m1": layer})   # foundry-disabled lastChange
    font = _cache_font(glyph)
    first = db._outline_paths(font, ["A"])["m1"]["A"]["d"]
    layer.drawBezierPath = _BezPath([(0, [(0, 0)]), (1, [(700, 0)]), (1, [(700, 7)]), (3, [])])
    second = db._outline_paths(font, ["A"])["m1"]["A"]["d"]
    assert second != first   # no stamp -> can't prove unchanged -> always re-extract


def test_logo_master_prefers_regular_then_bold_then_first() -> None:
    thin, bold, reg = _FakeMaster("t", "Thin"), _FakeMaster("b", "Bold"), _FakeMaster("r", "Regular")
    regular = db._logo_master(_FakeFont([thin, bold, reg], []))
    boldest = db._logo_master(_FakeFont([thin, bold], []))
    only = db._logo_master(_FakeFont([thin], []))
    assert regular is not None and regular.id == "r"
    assert boldest is not None and boldest.id == "b"
    assert only is not None and only.id == "t"
    assert db._logo_master(_FakeFont([], [])) is None


def test_family_logo_renders_family_with_chosen_master() -> None:
    glyphs = [_FakeGlyph("A", {"m1": _outline_layer(3)}),
              _FakeGlyph("a", {"m1": _outline_layer(3)})]
    font = _FakeFont([_FakeMaster("m1", "Regular")], glyphs, family="Aa")
    logo = db._family_logo(font)
    assert logo["d"] and logo["vb"]
    assert "M500" in logo["d"]   # the "a" is shifted right by the "A" advance (500)


def test_family_logo_empty_without_matching_glyphs() -> None:
    font = _FakeFont([_FakeMaster("m1", "Regular")], [], family="Zz")
    assert db._family_logo(font) == {}


def test_build_model_recipe_completion_parity_without_recipes(tmp_path) -> None:
    # No recipes (Glyphs absent) -> recipeCompletion.complete must equal the
    # count of glyphs at the global final step, i.e. standard completion.
    (tmp_path / "colorNames.txt").write_text("purple=A\nyellow=Done\n", encoding="utf-8")
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(3)}),   # 3 = yellow = final step
              _FakeGlyph("B", {"m1": _FakeLayerColor(3)}),
              _FakeGlyph("C", {"m1": _FakeLayerColor(8)})]   # 8 = purple = not final
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs, filepath=str(tmp_path / "F.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["recipes"] == []
    last = model["order"][-1]
    standard_final = model["masters"][0]["counts"][last]
    assert model["recipeCompletion"]["m1"]["complete"] == standard_final == 2


def test_build_model_master_preview_and_favicon(tmp_path) -> None:
    (tmp_path / "colorNames.txt").write_text("yellow=Ready\nNone=Nothing\n", encoding="utf-8")
    glyphs = [_FakeGlyph("A", {"m1": _outline_layer(3)}),
              _FakeGlyph("a", {"m1": _outline_layer(3)})]
    font = _FakeFont([_FakeMaster("m1", "Regular")], glyphs, filepath=str(tmp_path / "F.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)

    preview = model["masters"][0]["preview"]
    assert preview["d"] and preview["vb"]
    assert "M500" in preview["d"]            # the "a" is shifted right by the "A" advance (500)
    # the favicon is the bundled brand image as a self-contained data: URI
    # (favicon.gif preferred, then png/svg)
    assert isinstance(model["favicon"], str) and model["favicon"].startswith("data:image/")


def test_build_model_preview_empty_without_outlines(tmp_path) -> None:
    (tmp_path / "colorNames.txt").write_text("red=R\n", encoding="utf-8")
    font = _FakeFont([_FakeMaster("m1", "R")], [_FakeGlyph("A", {"m1": _FakeLayerColor(0)})],
                     filepath=str(tmp_path / "F.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["masters"][0]["preview"] == {}


# --------------------------------------------------------------------------- #
# Outline cache — inkless / partial-master glyphs must be cache HITS (not
# re-extracted forever). Probe: count real outline extractions per run.
# --------------------------------------------------------------------------- #

def _counting_extractor(monkeypatch) -> list[int]:
    """Patch ``glyphsvg.layer_outline_em`` to count calls; returns a 1-elem list
    used as a mutable counter (calls[0])."""
    real = db.glyphsvg.layer_outline_em
    calls = [0]

    def counted(layer: object, em_height: float) -> dict:
        calls[0] += 1
        return real(layer, em_height)

    monkeypatch.setattr(db.glyphsvg, "layer_outline_em", counted)
    return calls


def test_outline_cache_hits_inkless_glyph_on_second_run(monkeypatch) -> None:
    # A glyph whose layer produces NO ink (no drawBezierPath) but carries a stamp:
    # its cached ``m`` is empty, yet the second run with an unchanged stamp must be
    # a HIT, never re-extracting (the old all()-in-cache guard never matched).
    glyph = _FakeGlyph("space", {"m1": _FakeLayerColor(None)})   # layer present, no outline
    glyph.lastChange = _FakeNSDate(100.0)
    font = _cache_font(glyph)
    calls = _counting_extractor(monkeypatch)
    assert db._outline_paths(font, ["space"]) == {"m1": {}}      # no ink anywhere
    assert calls[0] == 1                                         # examined once on run 1
    calls[0] = 0
    assert db._outline_paths(font, ["space"]) == {"m1": {}}
    assert calls[0] == 0                                         # run 2 is a cache hit


def test_outline_cache_hits_partial_master_glyph_on_second_run(monkeypatch) -> None:
    # Ink in m1 only, none in m2 (a partial-master glyph). The cached ``m`` omits
    # m2, but the master set was fully EXAMINED, so the second run is a HIT.
    glyph = _FakeGlyph("A", {"m1": _outline_with(400, 700), "m2": _FakeLayerColor(0)})
    glyph.lastChange = _FakeNSDate(100.0)
    font = _FakeFont([_FakeMaster("m1", "R"), _FakeMaster("m2", "B")], [glyph])
    font.tempData = {}
    calls = _counting_extractor(monkeypatch)
    first = db._outline_paths(font, ["A"])
    assert "A" in first["m1"] and "A" not in first["m2"]         # only m1 has ink
    assert calls[0] == 2                                         # both masters examined run 1
    calls[0] = 0
    second = db._outline_paths(font, ["A"])
    assert second == first
    assert calls[0] == 0                                         # run 2 re-extracts nothing


def test_component_deps_handles_cyclic_reference(monkeypatch) -> None:
    # a -> b -> a: a self-referential component cycle must terminate (the ``seen``
    # set breaks it) rather than recursing forever, and still report both bases.
    layer_a = _outline_with(100, 100)
    layer_a.components = [_FakeComponent("b")]
    layer_b = _outline_with(100, 100)
    layer_b.components = [_FakeComponent("a")]
    glyph_a = _FakeGlyph("a", {"m1": layer_a})
    glyph_b = _FakeGlyph("b", {"m1": layer_b})
    font = _FakeFont([_FakeMaster("m1", "R")], [glyph_a, glyph_b])
    deps = db._component_deps(font, glyph_a, ["m1"], set())
    assert deps == {"a", "b"}                                    # both reached, no infinite loop
    # the cycle must not crash the cache walk either
    font.tempData = {}
    paths = db._outline_paths(font, ["a", "b"])
    assert "a" in paths["m1"] and "b" in paths["m1"]


def test_build_model_folds_today_into_trend_on_first_run(monkeypatch, tmp_path) -> None:
    # First run with EMPTY persisted history must still yield a trend point for
    # today (build_model folds the live snapshot in before deriving the series).
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    (tmp_path / "colorNames.txt").write_text("purple=A\nyellow=Done\n", encoding="utf-8")
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(3)}),   # at final step
              _FakeGlyph("B", {"m1": _FakeLayerColor(8)})]   # started, not final
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs, filepath=str(tmp_path / "F.glyphs"))
    current = db.build_master_glyph_colors(font)
    assert db.load_history(font) == {}                         # nothing persisted yet
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    series = model["trend"]["series"]
    assert [point["date"] for point in series] == ["2026-06-05"]   # today present
    assert series[-1]["masters"]["m1"]["final"] == 1               # A reached the final step


def test_build_model_latest_series_point_is_todays_data_not_prior_capture(
        monkeypatch, tmp_path) -> None:
    # Persisted history already holds an EARLIER capture for today; the run's
    # latest series point must reflect today's live ``current``, not that capture.
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    (tmp_path / "colorNames.txt").write_text("purple=A\nyellow=Done\n", encoding="utf-8")
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(3)}),
              _FakeGlyph("B", {"m1": _FakeLayerColor(3)})]    # both at final step now
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs, filepath=str(tmp_path / "F.glyphs"))
    now = datetime(2026, 6, 5)
    # an earlier capture of the SAME day, with both glyphs still uncoloured
    db.record_history(font, {"m1": {"A": cc.NO_COLOR, "B": cc.NO_COLOR}}, now)
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, now, current, current)
    series = model["trend"]["series"]
    assert series[-1]["date"] == "2026-06-05"
    assert series[-1]["masters"]["m1"]["final"] == 2          # live data (both final), not 0


def test_build_model_empty_font_does_not_crash(monkeypatch, tmp_path) -> None:
    # No glyphs and no masters: build_model must produce a sane, empty-ish model
    # rather than raise (glyphTotal == 0, no masters to index).
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    (tmp_path / "colorNames.txt").write_text("red=R\n", encoding="utf-8")
    font = _FakeFont([], [], filepath=str(tmp_path / "Empty.glyphs"))
    current = db.build_master_glyph_colors(font)            # {} -> no masters
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["glyphTotal"] == 0
    assert model["glyphNames"] == [] and model["masters"] == []
    assert model["paths"] == {} and model["coverage"]["byScript"] == {}
    assert model["trend"]["forecast"] == {}                # no masters -> no forecasts
    assert model["trend"]["series"][-1]["date"] == "2026-06-05"   # today still folded in
