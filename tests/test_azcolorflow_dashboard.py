"""Tests for the Color Font Dashboard.

The pure data + HTML layer is exercised directly. The GlyphsApp-touching
helpers (mode pref, colorNames.txt resolution, per-glyph map, snapshot
persistence) are covered with lightweight fakes + a temp colorNames.txt, so the
only thing left to manual testing is the real ``from GlyphsApp import ...`` line.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, SupportsIndex, overload

import azcolorflow_dashboard as db
import colornames as cc
import pytest

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
        self.unicode: str | None = None
        self.export: bool = True            # GSGlyph default: glyphs export


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
    # Bare annotation: type-check dynamic `font.customParameters = [...]` assignments
    # without creating a runtime attribute (so getattr(..., None) reads None when unset).
    customParameters: list

    def __init__(self, masters: list, glyphs: list | None = None,
                 filepath: str | None = "/fonts/Acme.glyphs", family: str = "Acme Sans") -> None:
        self.masters = masters
        self.glyphs = _FakeGlyphs(glyphs if glyphs is not None else [])
        self.filepath = filepath
        self.familyName = family
        # The per-session outline cache lives here (a JSON string per key); tests
        # that exercise the cache assign a plain dict.
        self.tempData: dict[str, object] = {}
        # The dated timeline history is now stored here (gzip+base64 string),
        # mirroring GSFont.userData — a dict-like that travels with the file.
        self.userData: dict[str, object] = {}


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


def test_master_counts_is_the_shared_cumulative_counting() -> None:
    # Report-only semantics: masters[].counts stay cumulative ("reached step k
    # or beyond"); the palette's count badges show the exact census, matching
    # the report's per-group dist (single_counts_from_colors).
    order = _order_from(_HIDDEN_REORDERED)  # ["8", "4", "0", "3"]
    colors = [8, 4, None, 3, 0, 8]
    assert db.master_counts(colors, order) == cc.counts_from_colors(colors, order)


def test_step_counts_are_cumulative_over_file_order() -> None:
    order = _order_from(_HIDDEN_REORDERED)  # ["8", "4", "0", "3"]
    # one glyph at yellow (the final step) credits every earlier step in order
    counts = db.master_counts([3], order)
    assert counts == {"8": 1, "4": 1, "0": 1, "3": 1}
    # ...unlike the palette's census, which credits ONLY the exact step
    assert cc.single_counts_from_colors([3], order) == {
        "8": 0, "4": 0, "0": 0, "3": 1
    }


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

class _FakeGlyphOrderParam:
    """A ``glyphOrder`` custom parameter whose ``active`` flag, when flipped,
    re-sorts the owning fake font's ``glyphs`` between a custom and a default order
    — mirroring how Glyphs re-sorts ``font.glyphs`` when the parameter is toggled."""

    name = "glyphOrder"

    def __init__(self, font: _FakeFontWithGlyphOrder, default_order: list[str],
                 custom_order: list[str], active: bool = True) -> None:
        self._font = font
        self._default = default_order
        self._custom = custom_order
        self._active = active
        self.set_calls = 0                   # how many times `active` was written

    @property
    def active(self) -> bool:
        return self._active

    @active.setter
    def active(self, value: object) -> None:
        self.set_calls += 1
        self._active = bool(value)
        self._font._apply_order(self._custom if self._active else self._default)


class _FakeFontWithGlyphOrder(_FakeFont):
    """A font whose ``glyphs`` follow an active ``glyphOrder`` parameter: while it is
    active the glyphs iterate in ``custom_order``; deactivating the parameter falls
    back to ``default_order`` (what Glyphs' default sort would give)."""

    def __init__(self, masters: list, glyphs_by_name: dict,
                 default_order: list[str], custom_order: list[str]) -> None:
        super().__init__(masters, [glyphs_by_name[name] for name in custom_order])
        self._by_name = glyphs_by_name
        self.customParameters = [
            _FakeGlyphOrderParam(self, default_order, custom_order, active=True)
        ]

    def _apply_order(self, order: list[str]) -> None:
        self.glyphs = _FakeGlyphs(self._by_name[name] for name in order)


def _glyph_order_font(default_order: list[str],
                      custom_order: list[str]) -> _FakeFontWithGlyphOrder:
    by_name = {name: _FakeGlyph(name, {}) for name in default_order}
    return _FakeFontWithGlyphOrder([_FakeMaster("m1", "R")], by_name,
                                   default_order, custom_order)


def test_default_glyph_order_ignores_active_glyphorder_param() -> None:
    # font.glyphs iterates in the custom glyphOrder C, A, B; default is A, B, C.
    font = _glyph_order_font(["A", "B", "C"], ["C", "A", "B"])
    assert db.default_glyph_order(font, ["C", "A", "B"]) == ["A", "B", "C"]


def test_default_glyph_order_restores_param_active_state() -> None:
    font = _glyph_order_font(["A", "B", "C"], ["C", "A", "B"])
    db.default_glyph_order(font, ["C", "A", "B"])
    # the parameter is switched back on and glyphs return to the custom order
    assert font.customParameters[0].active is True
    assert [glyph.name for glyph in font.glyphs] == ["C", "A", "B"]


def test_default_glyph_order_appends_names_absent_from_font() -> None:
    font = _glyph_order_font(["A", "B"], ["B", "A"])
    # "ghost" isn't in font.glyphs -> kept at the end in its given order
    assert db.default_glyph_order(font, ["B", "A", "ghost"]) == ["A", "B", "ghost"]


def test_default_glyph_order_passthrough_without_custom_parameters() -> None:
    glyphs = [_FakeGlyph("B", {}), _FakeGlyph("A", {})]
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs)  # no customParameters API
    assert db.default_glyph_order(font, ["B", "A"]) == ["B", "A"]


def test_default_glyph_order_passthrough_without_glyphorder_param() -> None:
    glyphs = [_FakeGlyph("B", {}), _FakeGlyph("A", {})]
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs)
    font.customParameters = []  # has the API, but no glyphOrder parameter
    assert db.default_glyph_order(font, ["B", "A"]) == ["B", "A"]


def test_default_glyph_order_does_not_touch_inactive_param() -> None:
    # The parameter is already inactive -> font.glyphs is already in the default
    # order, so the document must not be mutated at all (no `active` writes).
    font = _glyph_order_font(["A", "B", "C"], ["C", "A", "B"])
    param = font.customParameters[0]
    param.active = False                     # user had it off; glyphs now default order
    param.set_calls = 0
    assert db.default_glyph_order(font, ["C", "A", "B"]) == ["A", "B", "C"]
    assert param.set_calls == 0              # read-only path: zero document mutation
    assert param.active is False             # and the prior state is untouched


def test_default_glyph_order_restore_failure_is_loud(monkeypatch) -> None:
    # If restoring the parameter fails, the failure must PROPAGATE — the old code
    # swallowed it and silently left the user's glyphOrder disabled.
    font = _glyph_order_font(["A", "B", "C"], ["C", "A", "B"])

    def exploding_restore(self: _FakeGlyphOrderParam, value: object) -> None:
        if bool(value):
            raise RuntimeError("cannot restore")
        self._active = False
        self._font._apply_order(self._default)

    monkeypatch.setattr(
        _FakeGlyphOrderParam, "active",
        property(_FakeGlyphOrderParam.active.fget, exploding_restore))
    with pytest.raises(RuntimeError):
        db.default_glyph_order(font, ["C", "A", "B"])


def test_default_glyph_order_deactivation_failure_leaves_param_active(monkeypatch) -> None:
    # If the deactivation itself fails, nothing was toggled: fall back to the input
    # order and leave the parameter exactly as it was (active).
    font = _glyph_order_font(["A", "B", "C"], ["C", "A", "B"])

    def exploding_deactivate(self: _FakeGlyphOrderParam, value: object) -> None:
        if not bool(value):
            raise RuntimeError("cannot deactivate")
        self._active = True
        self._font._apply_order(self._custom)

    monkeypatch.setattr(
        _FakeGlyphOrderParam, "active",
        property(_FakeGlyphOrderParam.active.fget, exploding_deactivate))
    assert db.default_glyph_order(font, ["C", "A", "B"]) == ["C", "A", "B"]
    assert font.customParameters[0].active is True


def test_build_model_uses_default_order_over_glyph_iteration_order(tmp_path) -> None:
    by_name = {name: _FakeGlyph(name, {"m1": _FakeLayerColor(0)})
               for name in ("A", "B", "C")}
    # font.glyphs iterates in the custom glyphOrder C, A, B; default is A, B, C.
    font = _FakeFontWithGlyphOrder([_FakeMaster("m1", "R")], by_name,
                                   default_order=["A", "B", "C"],
                                   custom_order=["C", "A", "B"])
    font.filepath = str(tmp_path / "Font.glyphs")
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["glyphNames"] == ["A", "B", "C"]


def test_build_model_omits_paths_when_no_glyph_svg(tmp_path, monkeypatch) -> None:
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(0)}),
              _FakeGlyph("B", {"m1": _FakeLayerColor(0)})]
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs)
    font.filepath = str(tmp_path / "Font.glyphs")
    current = db.build_master_glyph_colors(font)
    # default (pref off): the per-master outline dict is embedded
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["paths"]
    # hidden pref on: outlines omitted entirely -> a much lighter report
    fake = _FakeGlyphsApp()
    fake.defaults[db.NO_GLYPH_SVG_KEY] = True
    monkeypatch.setattr(db, "Glyphs", fake)
    lighter = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert lighter["paths"] == {}


def test_outline_paths_reports_monotonic_progress(tmp_path) -> None:
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(0)}),
              _FakeGlyph("B", {"m1": _FakeLayerColor(0)})]
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs)
    font.filepath = str(tmp_path / "Font.glyphs")
    seen: list[float] = []
    db._outline_paths(font, ["A", "B"], progress=seen.append)
    assert seen, "progress callback should fire"
    assert seen == sorted(seen)                              # monotonic non-decreasing
    assert all(0.0 <= value <= 1.0 for value in seen)
    assert seen[-1] == 1.0                                   # always finishes at 100%


def test_build_model_reports_monotonic_progress(tmp_path) -> None:
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(0)}),
              _FakeGlyph("B", {"m1": _FakeLayerColor(0)})]
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs)
    font.filepath = str(tmp_path / "Font.glyphs")
    current = db.build_master_glyph_colors(font)
    seen: list[float] = []
    db.build_model(font, datetime(2026, 6, 5), current, current, progress=seen.append)
    assert seen, "progress callback should fire"
    assert seen == sorted(seen)
    assert all(0.0 <= value <= 1.0 for value in seen)
    assert seen[-1] == 1.0


def test_main_reports_progress_and_opens_report(tmp_path, monkeypatch) -> None:
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(0)}),
              _FakeGlyph("B", {"m1": _FakeLayerColor(1)})]
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs)
    font.filepath = str(tmp_path / "Font.glyphs")
    opened: list[str] = []
    monkeypatch.setattr(db.webbrowser, "open", lambda uri: opened.append(uri))
    seen: list[float] = []
    db.main(font, progress=seen.append)
    assert opened, "the finished report should open in a browser"
    assert seen == sorted(seen)
    assert all(0.0 <= value <= 1.0 for value in seen)
    assert seen[-1] == 1.0                                   # reaches 100% before opening


def test_main_open_when_done_false_returns_path_without_opening(tmp_path, monkeypatch) -> None:
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(0)}),
              _FakeGlyph("B", {"m1": _FakeLayerColor(1)})]
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs)
    font.filepath = str(tmp_path / "Font.glyphs")
    opened: list[str] = []
    monkeypatch.setattr(db.webbrowser, "open", lambda uri: opened.append(uri))
    result = db.main(font, open_when_done=False)
    assert not opened                                        # NOT auto-opened
    assert result is not None and result.exists()            # path returned for Open/Save
    assert result.suffix == ".html"


def test_no_glyph_svg_reads_hidden_pref(monkeypatch) -> None:
    fake = _FakeGlyphsApp()
    fake.defaults[db.NO_GLYPH_SVG_KEY] = True
    monkeypatch.setattr(db, "Glyphs", fake)
    assert db.no_glyph_svg() is True
    fake.defaults[db.NO_GLYPH_SVG_KEY] = False
    assert db.no_glyph_svg() is False


def test_no_glyph_svg_defaults_off_without_glyphs(monkeypatch) -> None:
    monkeypatch.setattr(db, "Glyphs", None)
    assert db.no_glyph_svg() is False


def test_outline_change_days_reads_pref(monkeypatch) -> None:
    monkeypatch.setattr(db, "Glyphs", None)
    assert db.outline_change_days() == 0                      # dormant without Glyphs
    fake = _FakeGlyphsApp()
    monkeypatch.setattr(db, "Glyphs", fake)
    assert db.outline_change_days() == db.OUTLINE_CHANGE_DAYS_DEFAULT  # key unset -> default
    fake.defaults[db.OUTLINE_CHANGE_DAYS_KEY] = 5
    assert db.outline_change_days() == 5
    fake.defaults[db.OUTLINE_CHANGE_DAYS_KEY] = 0
    assert db.outline_change_days() == 0                      # 0 disables


def test_collect_outline_changes_empty_when_not_git_tracked(tmp_path, monkeypatch) -> None:
    fake = _FakeGlyphsApp()
    monkeypatch.setattr(db, "Glyphs", fake)
    font = _FakeFont([_FakeMaster("m1", "R")], filepath=str(tmp_path / "Font.glyphs"))
    # tmp_path is not a git repo -> the feature stays dormant (no changes, no crash)
    assert db.collect_outline_changes(font) == {}


def test_build_model_includes_outline_changes_key(tmp_path) -> None:
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(0)})]
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs)
    font.filepath = str(tmp_path / "Font.glyphs")
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert "outlineChanges" in model
    assert model["outlineChanges"] == {}


def test_meaning_and_none_prefers_in_font_userdata(tmp_path) -> None:
    """C: labels stored in font.userData win over the sidecar key file, so a shared
    .glyphs file reports the labels its author saved."""
    font = _FakeFont([_FakeMaster("m1", "R")], filepath=str(tmp_path / "Font.glyphs"))
    font.userData = {cc.FONT_LABELS_KEY:
                     cc.DEFAULT_COLOR_NAMES.replace("red=🚨 Red", "red=Shared Red")}
    meaning, _none = db._meaning_and_none(font)
    assert meaning["0"] == "Shared Red"


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


def test_save_snapshot_prunes_paths_missing_on_disk(monkeypatch, tmp_path) -> None:
    # The defaults store is keyed by file path and used to accumulate an entry for
    # every font ever reported; saving now prunes entries whose file is gone.
    fake = _FakeGlyphsApp()
    monkeypatch.setattr(db, "Glyphs", fake)
    alive = tmp_path / "Alive.glyphs"
    alive.write_text("x", encoding="utf-8")
    fake.defaults[db.DEFAULTS_KEY] = {
        str(alive): {"m1": {"A": 0}},
        str(tmp_path / "Ghost.glyphs"): {"m1": {"A": 1}},   # deleted long ago
    }
    font = _FakeFont([_FakeMaster("m1", "R")], filepath=str(tmp_path / "Current.glyphs"))
    db.save_snapshot(font, {"m1": {"A": 2}})
    store = fake.defaults[db.DEFAULTS_KEY]
    assert isinstance(store, dict)
    # ghost pruned; the on-disk sibling survives; the current font is always kept
    # (even though its path isn't on disk yet).
    assert set(store) == {str(alive), font.filepath}
    assert store[font.filepath] == {"m1": {"A": 2}}


# --------------------------------------------------------------------------- #
# Corrupt embedded history — never silently overwritten
# --------------------------------------------------------------------------- #

def test_load_history_stashes_corrupt_payload(monkeypatch, capsys) -> None:
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    font.userData[db.TIMELINE_USERDATA_KEY] = "definitely-not-a-payload-!!"
    assert db.load_history(font) == {}                       # unreadable -> empty view
    backup_key = db.TIMELINE_USERDATA_KEY + db.CORRUPT_HISTORY_SUFFIX
    assert font.userData[backup_key] == "definitely-not-a-payload-!!"
    assert "could not be decoded" in capsys.readouterr().out  # loud, not silent


def test_record_history_preserves_corrupt_payload_before_overwrite(monkeypatch) -> None:
    # The exact data-loss scenario: a corrupt embedded timeline used to be replaced
    # by a fresh 1-entry log. The fresh log is still written (the plugin must keep
    # working) but the original payload survives under the backup key.
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    font.userData[db.TIMELINE_USERDATA_KEY] = "corrupt!!"
    db.record_history(font, {"m1": {"A": 0}}, datetime(2026, 6, 6))
    assert db.load_history(font) == {"2026-06-06T00:00:00": {"m1": {"A": 0}}}
    backup_key = db.TIMELINE_USERDATA_KEY + db.CORRUPT_HISTORY_SUFFIX
    assert font.userData[backup_key] == "corrupt!!"


def test_corrupt_stash_keeps_the_first_copy(monkeypatch) -> None:
    # A second corruption never overwrites the stashed original (the first corrupt
    # payload is the one closest to the user's real history).
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    backup_key = db.TIMELINE_USERDATA_KEY + db.CORRUPT_HISTORY_SUFFIX
    font.userData[backup_key] = "the-original-corrupt-copy"
    font.userData[db.TIMELINE_USERDATA_KEY] = "newer-corruption!!"
    assert db.load_history(font) == {}
    assert font.userData[backup_key] == "the-original-corrupt-copy"


def test_load_history_corrupt_primary_still_reads_legacy_store(monkeypatch) -> None:
    # A corrupt userData payload must not block the legacy Glyphs.defaults fallback.
    fake = _FakeGlyphsApp()
    monkeypatch.setattr(db, "Glyphs", fake)
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    font.userData[db.TIMELINE_USERDATA_KEY] = "corrupt!!"
    fake.defaults[db.HISTORY_KEY] = {font.filepath: {"2026-06-01": {"m1": {"A": 4}}}}
    assert db.load_history(font) == {"2026-06-01": {"m1": {"A": 4}}}


def test_record_history_round_trips_and_sorts(monkeypatch) -> None:
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    assert db.load_history(font) == {}                       # nothing yet
    db.record_history(font, {"m1": {"A": 0}}, datetime(2026, 6, 4))
    db.record_history(font, {"m1": {"A": 3}}, datetime(2026, 6, 6))
    db.record_history(font, {"m1": {"A": 4}}, datetime(2026, 6, 5))
    history = db.load_history(font)
    assert list(history.keys()) == [                          # datetime keys, oldest-first
        "2026-06-04T00:00:00", "2026-06-05T00:00:00", "2026-06-06T00:00:00"]
    assert history["2026-06-06T00:00:00"] == {"m1": {"A": 3}}


def test_record_history_logs_each_save_not_per_day(monkeypatch) -> None:
    # One entry per SAVE (datetime key), not one per day: two saves the same day with
    # different colours keep BOTH; the report groups them by date later.
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    db.record_history(font, {"m1": {"A": 0}}, datetime(2026, 6, 6, 9))
    db.record_history(font, {"m1": {"A": 8}}, datetime(2026, 6, 6, 17))
    history = db.load_history(font)
    assert list(history.keys()) == ["2026-06-06T09:00:00", "2026-06-06T17:00:00"]
    # grouping by date collapses to the last save of the day
    assert db.group_saves_by_date(history) == {"2026-06-06": {"m1": {"A": 8}}}


def test_record_history_skips_unchanged_save(monkeypatch) -> None:
    # A save that changes no colour (e.g. an outline-only edit, or a double save) adds
    # no entry — the log only grows on colour-changing saves.
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    db.record_history(font, {"m1": {"A": 5}}, datetime(2026, 6, 6, 9))
    db.record_history(font, {"m1": {"A": 5}}, datetime(2026, 6, 6, 10))   # identical -> skipped
    db.record_history(font, {"m1": {"A": 6}}, datetime(2026, 6, 6, 11))   # changed  -> kept
    assert list(db.load_history(font).keys()) == [
        "2026-06-06T09:00:00", "2026-06-06T11:00:00"]


def test_record_history_is_uncapped_keeps_all_days(monkeypatch) -> None:
    # No day-window pruning: a long-running project keeps its entire dated history
    # (each past day collapsed to its closing save, so growth stays small).
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    days = [datetime(2026, 1, 1) + timedelta(days=offset) for offset in range(70)]
    for index, day in enumerate(days):
        db.record_history(font, {"m1": {"A": index % 12}}, day)
    history = db.load_history(font)
    assert len(history) == 70                                  # nothing dropped
    assert min(history) == "2026-01-01T00:00:00"               # the very first day survives


def test_record_history_keeps_only_last_save_of_past_days(monkeypatch) -> None:
    # Once work moves to a new day, the old day's intra-day saves collapse to its
    # final save (end-of-day state); the current day keeps every save.
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    db.record_history(font, {"m1": {"A": 0}}, datetime(2026, 6, 1, 9))
    db.record_history(font, {"m1": {"A": 1}}, datetime(2026, 6, 1, 17))   # day 1 closing state
    db.record_history(font, {"m1": {"A": 2}}, datetime(2026, 6, 2, 9))    # new day -> day 1 coalesces
    db.record_history(font, {"m1": {"A": 3}}, datetime(2026, 6, 2, 17))   # current day: all saves kept
    assert list(db.load_history(font).keys()) == [
        "2026-06-01T17:00:00", "2026-06-02T09:00:00", "2026-06-02T17:00:00"]


def test_history_no_op_without_glyphs(monkeypatch) -> None:
    monkeypatch.setattr(db, "Glyphs", None)
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    db.record_history(font, {"m1": {"A": 0}}, datetime(2026, 6, 6))   # silently no-op
    assert db.load_history(font) == {}


def test_history_records_into_unsaved_font_userdata(monkeypatch) -> None:
    # userData travels with the file, so we can accrue history before the first save
    # (an unsaved font with no filepath). It persists once the file is first written.
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    unsaved = _FakeFont([_FakeMaster("m1", "R")], filepath="")
    db.record_history(unsaved, {"m1": {"A": 0}}, datetime(2026, 6, 6))
    assert db.load_history(unsaved) == {"2026-06-06T00:00:00": {"m1": {"A": 0}}}


def test_history_stored_in_userdata_not_defaults(monkeypatch) -> None:
    # the snapshot lives in the font's userData (travels with the file), not in the
    # machine-local Glyphs.defaults store.
    fake = _FakeGlyphsApp()
    monkeypatch.setattr(db, "Glyphs", fake)
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    db.record_history(font, {"m1": {"A": 2}}, datetime(2026, 6, 6))
    assert db.TIMELINE_USERDATA_KEY in font.userData
    assert fake.defaults[db.HISTORY_KEY] is None                 # nothing written to defaults


def test_load_history_migrates_from_legacy_defaults(monkeypatch) -> None:
    # a font saved by an older build has history in Glyphs.defaults but nothing in
    # userData yet -> load_history falls back to the legacy store.
    fake = _FakeGlyphsApp()
    monkeypatch.setattr(db, "Glyphs", fake)
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    fake.defaults[db.HISTORY_KEY] = {font.filepath: {"2026-06-01": {"m1": {"A": 4}}}}
    assert db.load_history(font) == {"2026-06-01": {"m1": {"A": 4}}}


def test_write_history_replaces_uncapped_and_coalesces_past_days(monkeypatch) -> None:
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    db.record_history(font, {"m1": {"A": 0}}, datetime(2026, 6, 9))   # a pre-existing day
    db.write_history(font, {
        "2026-06-01T09:00:00": {"m1": {"A": 1}},
        "2026-06-01T17:00:00": {"m1": {"A": 2}},   # past day -> only this closing save kept
        "2026-06-02T09:00:00": {"m1": {"A": 3}},
        "2026-06-02T17:00:00": {"m1": {"A": 4}},   # latest day -> every save kept
    })
    history = db.load_history(font)
    assert list(history) == [                       # replaced wholesale, nothing day-capped
        "2026-06-01T17:00:00", "2026-06-02T09:00:00", "2026-06-02T17:00:00"]


def test_backfill_from_git_imports_commits_under_live_saves(monkeypatch) -> None:
    # Backfill imports git COMMIT datetimes into the per-save log; a live save wins on a
    # shared key, and only non-colliding commits count as newly imported. The collector
    # receives the already-recorded keys as `skip`, so the backfill is truly incremental.
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    db.record_history(font, {"m1": {"A": 5}}, datetime(2026, 6, 2, 12))   # a live save
    seen: dict = {}

    def fake_commits(path, load, cap=0, progress=None, skip=None) -> dict:
        seen["skip"] = skip
        return {
            "2026-06-01T09:00:00": {"m1": {"A": 0}},
            "2026-06-02T12:00:00": {"m1": {"A": 9}},   # collides with the live save's key
        }

    monkeypatch.setattr(db.azcolorflow_git, "collect_commit_history", fake_commits)
    imported = db.backfill_from_git(font)
    assert imported == 1                          # only the non-colliding commit is new
    assert seen["skip"] == {"2026-06-02T12:00:00"}  # recorded keys are never re-opened
    history = db.load_history(font)
    assert history == {
        "2026-06-01T09:00:00": {"m1": {"A": 0}},
        "2026-06-02T12:00:00": {"m1": {"A": 5}},   # live save wins the shared key
    }


def test_backfill_from_git_no_op_when_not_in_repo(monkeypatch) -> None:
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    monkeypatch.setattr(
        db.azcolorflow_git, "collect_commit_history",
        lambda path, load, cap=0, progress=None, skip=None: {},  # not a repo / untracked
    )
    assert db.backfill_from_git(font) == 0
    assert db.load_history(font) == {}


def test_backfill_from_git_uses_precollected_pass_without_recollecting(monkeypatch) -> None:
    # When main() hands over the single per-run git pass, backfill must not walk the
    # repo again — the collector is not called at all.
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")

    def exploding_collect(*args, **kwargs) -> dict:
        raise AssertionError("collect_commit_history must not be called")

    monkeypatch.setattr(db.azcolorflow_git, "collect_commit_history", exploding_collect)
    imported = db.backfill_from_git(
        font, git_history={"2026-06-01T09:00:00": {"m1": {"A": 0}}})
    assert imported == 1
    assert db.load_history(font) == {"2026-06-01T09:00:00": {"m1": {"A": 0}}}


def test_backfill_from_git_nothing_new_does_not_rewrite(monkeypatch) -> None:
    # A precollected pass where every key is already recorded must not re-dirty the
    # font (no userData write at all).
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    db.record_history(font, {"m1": {"A": 5}}, datetime(2026, 6, 2, 12))
    before = font.userData[db.TIMELINE_USERDATA_KEY]
    assert db.backfill_from_git(
        font, git_history={"2026-06-02T12:00:00": {"m1": {"A": 9}}}) == 0
    assert font.userData[db.TIMELINE_USERDATA_KEY] == before


def test_coerce_history_stringifies_dates_and_ints() -> None:
    raw = {"2026-06-06": {"m1": {"A": "3"}}}   # NSDictionary-ish
    assert db._coerce_history(raw) == {"2026-06-06": {"m1": {"A": 3}}}
    assert db._coerce_history(None) == {}


# --------------------------------------------------------------------------- #
# Burndown / velocity
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
    series = db.history_series(history, _FC_ORDER)
    assert [point["date"] for point in series] == ["2026-06-01", "2026-06-08"]
    assert series[1]["masters"]["m1"] == {"final": 4, "started": 4, "total": 10}


def test_master_point_counts_final_started_total() -> None:
    # "final" is the cumulative count at the last step; "started" excludes the
    # uncoloured glyphs; with no order at all, "final" falls back to "started".
    per_glyph = {"A": 0, "B": 2, "C": cc.NO_COLOR}
    point = db._master_point(per_glyph, _FC_ORDER)
    assert point == {"final": 1, "started": 2, "total": 3}
    empty = db._master_point(per_glyph, [])
    assert empty["final"] == empty["started"]


# --------------------------------------------------------------------------- #
# cross_master_summary
# --------------------------------------------------------------------------- #

def test_cross_master_summary_single_master_all_identical() -> None:
    # One master -> every glyph is trivially "identical"; doneEverywhere counts
    # only the glyphs sitting on the final step (2). Differ is always 0.
    current = {"m1": {"A": 2, "B": 1, "C": cc.NO_COLOR}}
    out = db.cross_master_summary(current, ["m1"], ["A", "B", "C"], _FC_ORDER)
    assert out["total"] == 3 and out["masterCount"] == 1
    assert out["identical"] == 3 and out["differ"] == 0
    assert out["doneEverywhere"] == 1           # only A is at final step 2
    assert out["byStep"] == {"-1": 1, "1": 1, "2": 1}
    assert out["differGlyphs"] == []


def test_cross_master_summary_two_masters_agree_but_not_final() -> None:
    # Both masters share each glyph's key, but none is the final step -> identical
    # everywhere, done nowhere.
    current = {"m1": {"A": 1, "B": 0}, "m2": {"A": 1, "B": 0}}
    out = db.cross_master_summary(current, ["m1", "m2"], ["A", "B"], _FC_ORDER)
    assert out["identical"] == 2 and out["differ"] == 0
    assert out["doneEverywhere"] == 0
    assert out["byStep"] == {"0": 1, "1": 1}
    assert out["differGlyphs"] == []


def test_cross_master_summary_two_masters_done_everywhere() -> None:
    # Every glyph is the final step (2) in every master.
    current = {"m1": {"A": 2, "B": 2}, "m2": {"A": 2, "B": 2}}
    out = db.cross_master_summary(current, ["m1", "m2"], ["A", "B"], _FC_ORDER)
    assert out["identical"] == 2 and out["differ"] == 0
    assert out["doneEverywhere"] == 2
    assert out["byStep"] == {"2": 2}


def test_cross_master_summary_two_masters_partial_differ() -> None:
    # A agrees (1/1), B differs (2 vs 0), C differs (final vs absent), D done both.
    current = {
        "m1": {"A": 1, "B": 2, "C": 2, "D": 2},
        "m2": {"A": 1, "B": 0, "C": cc.NO_COLOR, "D": 2},
    }
    out = db.cross_master_summary(current, ["m1", "m2"], ["A", "B", "C", "D"], _FC_ORDER)
    assert out["total"] == 4 and out["masterCount"] == 2
    assert out["identical"] == 2 and out["differ"] == 2
    assert out["doneEverywhere"] == 1           # only D is final-step in both
    # byStep counts only the identical glyphs (A at 1, D at 2).
    assert out["byStep"] == {"1": 1, "2": 1}
    # differGlyphs follow glyph order, not the order they were discovered.
    assert out["differGlyphs"] == ["B", "C"]


def test_cross_master_summary_absent_master_key_is_uncolored() -> None:
    # A glyph missing from one master's map reads as -1 there, so it differs.
    current = {"m1": {"A": 1}, "m2": {}}
    out = db.cross_master_summary(current, ["m1", "m2"], ["A"], _FC_ORDER)
    assert out["differ"] == 1 and out["differGlyphs"] == ["A"]
    assert out["byStep"] == {}


def test_cross_master_summary_no_masters_is_all_zero() -> None:
    out = db.cross_master_summary({}, [], [], _FC_ORDER)
    assert out["total"] == 0 and out["masterCount"] == 0
    assert out["identical"] == 0 and out["differ"] == 0 and out["doneEverywhere"] == 0
    assert out["byStep"] == {} and out["differGlyphs"] == []


def test_cross_master_summary_no_order_means_no_done() -> None:
    # Without a workflow order there is no final step, so doneEverywhere is 0 even
    # when masters agree.
    current = {"m1": {"A": 2}, "m2": {"A": 2}}
    out = db.cross_master_summary(current, ["m1", "m2"], ["A"], [])
    assert out["finalStep"] is None
    assert out["identical"] == 1 and out["doneEverywhere"] == 0


def test_glyph_journeys_only_changed_unfinished_aligned_to_dates() -> None:
    dates = ["2026-06-01", "2026-06-02"]
    history = {
        "2026-06-01": {"m1": {"A": cc.NO_COLOR, "B": 1, "C": 0}},
        "2026-06-02": {"m1": {"A": 1, "B": 1, "C": 2}},
    }
    current = {"m1": {"A": 1, "B": 1, "C": 2}}   # C is at the final step (2) -> finished
    journeys = db._glyph_journeys(history, dates, current, ["A", "B", "C"], _FC_ORDER)
    assert journeys["m1"]["A"] == [cc.NO_COLOR, 1]   # changed + unfinished -> included, date-aligned
    assert "B" not in journeys["m1"]                 # flat journey -> nothing to show
    assert "C" not in journeys["m1"]                 # finished -> excluded
    assert db._glyph_journeys(history, [], current, ["A"], _FC_ORDER) == {}


def test_build_journey_index_emits_sparse_change_events_only() -> None:
    # history: 3 dates, one master, glyph A changes twice, glyph B never changes.
    history = {
        "2026-06-01": {"m1": {"A": cc.NO_COLOR, "B": 2}},
        "2026-06-02": {"m1": {"A": 1, "B": 2}},
        "2026-06-03": {"m1": {"A": 5, "B": 2}},
    }
    dates = ["2026-06-01", "2026-06-02", "2026-06-03"]
    index = db.build_journey_index(history, dates)
    # Only the first observation + each actual change is recorded (sparse).
    assert index["m1"]["A"] == [["2026-06-01", cc.NO_COLOR], ["2026-06-02", 1], ["2026-06-03", 5]]
    # A glyph that never changed records a single initial event, not one per date.
    assert index["m1"]["B"] == [["2026-06-01", 2]]


def test_build_journey_index_handles_missing_dates_as_uncoloured() -> None:
    # m1 has no entry on the middle date -> that date reads as NO_COLOR, a change.
    history = {
        "2026-06-01": {"m1": {"A": 3}},
        "2026-06-02": {},
        "2026-06-03": {"m1": {"A": 3}},
    }
    dates = ["2026-06-01", "2026-06-02", "2026-06-03"]
    index = db.build_journey_index(history, dates)
    assert index["m1"]["A"] == [["2026-06-01", 3], ["2026-06-02", cc.NO_COLOR], ["2026-06-03", 3]]


def test_build_journey_index_empty_when_no_dates() -> None:
    assert db.build_journey_index({}, []) == {}


def _dense_journey_index_reference(history: dict, dates: list) -> dict:
    """The original dense O(masters x glyphs x dates) implementation, kept verbatim
    as the oracle for the rewritten single-pass diff version."""
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
                key = history.get(date, {}).get(master_id, {}).get(name, cc.NO_COLOR)
                if key != previous:
                    events.append([date, key])
                    previous = key
            per_glyph[name] = events
        index[master_id] = per_glyph
    return index


def test_build_journey_index_matches_dense_reference() -> None:
    # The rewrite must be behaviour-identical on every awkward shape at once: a
    # master missing a date, a glyph appearing mid-history, a glyph disappearing
    # and coming back, a glyph starting uncoloured, a second master appearing
    # late, and a history entry whose date is outside the `dates` window (its
    # master still shows up, with no events — exactly like the dense version).
    history = {
        "2026-06-01": {"m1": {"A": cc.NO_COLOR, "B": 2}},
        "2026-06-02": {},                                        # m1 absent that day
        "2026-06-03": {"m1": {"A": 1, "C": 4}, "m2": {"A": 0}},  # B gone; C + m2 appear
        "2026-06-04": {"m1": {"A": 1, "B": 2, "C": 4}},          # B returns unchanged
        "2026-09-09": {"m9": {"Z": 3}},                          # outside the window
    }
    dates = ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"]
    assert db.build_journey_index(history, dates) == _dense_journey_index_reference(
        history, dates)


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
    streak = db.progress_streak(history, _FC_ORDER)
    assert streak["current"] == 2     # last two days both improved (3->6->7)
    assert streak["best"] == 2        # two runs of length 2 (06-02..03 and 06-05..06)
    assert streak["days"] == 6


def test_progress_streak_zero_when_last_day_regresses() -> None:
    history = _history([("2026-06-01", 5), ("2026-06-02", 8), ("2026-06-03", 6)])
    assert db.progress_streak(history, _FC_ORDER)["current"] == 0


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
    cov = db.build_coverage(font, current, _FC_ORDER)
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

    meta = db.build_coverage(font, current, _FC_ORDER)["scriptMeta"]
    assert meta["latin"] == {"name": "Latin", "glyph": "A"}     # Letter, lowest codepoint wins
    assert meta["Other"] == {"name": "Other", "glyph": "comma"}  # non-letter group falls to min cp


def test_coverage_rows_for_master_follows_the_selected_master() -> None:
    # The native sidebar's data source: one master's category + script bars, with
    # prettified script labels — and a DIFFERENT master gives different bars.
    letter_a = _FakeGlyph("A", {"m1": _FakeLayerColor(2), "m2": _FakeLayerColor(0)})
    letter_b = _FakeGlyph("B", {"m1": _FakeLayerColor(0), "m2": _FakeLayerColor(None)})
    comma = _FakeGlyph("comma", {"m1": _FakeLayerColor(2), "m2": _FakeLayerColor(2)})
    for glyph, script, category in ((letter_a, "latin", "Letter"), (letter_b, "latin", "Letter"),
                                    (comma, None, "Punctuation")):
        glyph.script, glyph.category = script, category
    letter_a.subCategory, letter_b.subCategory, comma.subCategory = "Uppercase", "Lowercase", None
    font = _FakeFont([_FakeMaster("m1", "R"), _FakeMaster("m2", "B")], [letter_a, letter_b, comma])

    data = db.coverage_rows_for_master(font, "m1")
    assert data["master_id"] == "m1"
    by_cat = {row["key"]: row for row in data["byCategory"]}
    assert by_cat["Letter"]["total"] == 2
    assert by_cat["Letter"]["dist"]["2"] == 1 and by_cat["Letter"]["dist"]["0"] == 1
    assert by_cat["Letter"]["label"] == "Letter"            # categories pass through
    by_script = {row["key"]: row for row in data["byScript"]}
    assert by_script["latin"]["label"] == "Latin"           # scripts prettified

    # Letter breaks down into its sub-categories (Uppercase/Lowercase); a
    # single-sub category (Punctuation) has no expandable breakdown.
    subs = {row["key"]: row for row in by_cat["Letter"]["subRows"]}
    assert set(subs) == {"Uppercase", "Lowercase"}
    assert subs["Uppercase"]["total"] == 1 and subs["Uppercase"]["dist"]["2"] == 1  # A at step 2
    assert subs["Lowercase"]["dist"]["0"] == 1                                       # B at step 0
    assert by_cat["Punctuation"]["subRows"] == []

    # Global row = the whole master's distribution (all 3 glyphs on m1).
    assert data["global"]["total"] == 3
    assert data["global"]["dist"]["2"] == 2 and data["global"]["dist"]["0"] == 1  # A,comma=2; B=0

    other = db.coverage_rows_for_master(font, "m2")
    other_letter = {row["key"]: row for row in other["byCategory"]}["Letter"]
    assert other_letter["dist"]["0"] == 1 and other_letter["dist"]["2"] == 0  # A=0, B uncoloured
    assert other_letter["uncolored"] == 1


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
    assert model["glyphTotal"] == 3
    assert model["order"] == ["8", "4", "3"]
    assert model["steps"] == [{"key": 8, "label": "Outline"},
                              {"key": 4, "label": "Anchors"},
                              {"key": 3, "label": "Ready"}]
    assert model["noneLabel"] == "Nothing"
    assert model["glyphNames"] == ["A", "B", "C"]          # stored once
    assert model["masters"][0]["keys"] == [8, 4, -1]        # parallel to glyphNames
    assert model["changes"] == {"m1": {}}


def test_build_model_emits_scripts_parallel_to_glyph_names(tmp_path) -> None:
    # #18: a per-glyph `scripts` list, parallel to glyphNames, drives the
    # per-script progress lanes. A blank/missing script falls back to "Other".
    (tmp_path / "colorNames.txt").write_text("red=R\nNone=Nothing\n", encoding="utf-8")
    master = _FakeMaster("m1", "Regular")
    letter_a = _FakeGlyph("A", {"m1": _FakeLayerColor(0)})
    alef = _FakeGlyph("alef-ar", {"m1": _FakeLayerColor(0)})
    comma = _FakeGlyph("comma", {"m1": _FakeLayerColor(0)})   # no script -> "Other"
    letter_a.script, alef.script = "latin", "arabic"
    font = _FakeFont([master], [letter_a, alef, comma], filepath=str(tmp_path / "Font.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)

    assert "scripts" in model
    assert len(model["scripts"]) == len(model["glyphNames"])   # parallel to glyphNames
    by_name = dict(zip(model["glyphNames"], model["scripts"], strict=True))
    assert by_name == {"A": "latin", "alef-ar": "arabic", "comma": "Other"}


def test_build_model_empty_font_has_empty_scripts(monkeypatch, tmp_path) -> None:
    # #18: the empty-font invariant — no glyphs means scripts is [].
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    (tmp_path / "colorNames.txt").write_text("red=R\n", encoding="utf-8")
    font = _FakeFont([], [], filepath=str(tmp_path / "Empty.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["scripts"] == [] and model["glyphNames"] == []


def test_build_model_emits_journey_index_field(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "is_git_tracked", lambda font: True)   # timeline needs git
    (tmp_path / "colorNames.txt").write_text(
        "purple=Outline\nyellow=Ready\nNone=Nothing\n", encoding="utf-8")
    master = _FakeMaster("m1", "Regular")
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(8)})]
    font = _FakeFont([master], glyphs, filepath=str(tmp_path / "Font.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert "journeyIndex" in model
    # One master, today's snapshot only -> one initial event for A.
    assert model["journeyIndex"]["m1"]["A"] == [["2026-06-05", 8]]


def test_build_model_timeline_present_without_git(tmp_path) -> None:
    """The timeline no longer requires git: history lives in the font's userData and
    travels with the file, so even a non-git font folds today's snapshot in and gets a
    populated trend/journey. Git-only extras (outline changes) stay empty with no repo."""
    (tmp_path / "colorNames.txt").write_text("purple=Outline\nNone=Nothing\n", encoding="utf-8")
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(8)})]
    font = _FakeFont([_FakeMaster("m1", "Regular")], glyphs, filepath=str(tmp_path / "Font.glyphs"))
    current = db.build_master_glyph_colors(font)
    # tmp_path is not a git repo, yet the timeline still populates from the folded snapshot
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["trend"]["dates"] == ["2026-06-05"]           # today folded in (no git needed)
    assert model["journeyIndex"]["m1"]["A"] == [["2026-06-05", 8]]
    assert model["outlineChanges"] == {}                       # git-only feature, no repo here
    # current-state fields still populated
    assert model["glyphNames"] == ["A"]
    assert model["masters"][0]["keys"] == [8]


def test_build_model_has_no_commit_timeline_without_git(tmp_path) -> None:
    # per-commit view is git-only: no repo -> trendCommits is None and hasCommits False.
    (tmp_path / "colorNames.txt").write_text("purple=Outline\nNone=Nothing\n", encoding="utf-8")
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(8)})]
    font = _FakeFont([_FakeMaster("m1", "Regular")], glyphs, filepath=str(tmp_path / "F.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["hasCommits"] is False
    assert model["trendCommits"] is None
    assert model["journeyIndexCommits"] is None
    assert model["fineKind"] is None                            # no commits and no saves logged


def test_build_model_builds_per_commit_timeline_when_available(monkeypatch, tmp_path) -> None:
    # with git commit history available, the model ships a parallel per-commit dataset
    # (datetime-keyed) plus today's live work folded in as the newest point.
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    (tmp_path / "colorNames.txt").write_text("purple=Outline\nNone=Nothing\n", encoding="utf-8")
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(8)})]
    font = _FakeFont([_FakeMaster("m1", "Regular")], glyphs, filepath=str(tmp_path / "F.glyphs"))
    monkeypatch.setattr(db, "commit_timeline_history", lambda font, git_commits=None: {
        "2026-06-01T09:00:00": {"m1": {"A": cc.NO_COLOR}},
        "2026-06-01T15:00:00": {"m1": {"A": 8}},
    })
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5, 11, 30), current, current)
    assert model["hasCommits"] is True
    commit_dates = model["trendCommits"]["dates"]
    assert commit_dates[0] == "2026-06-01T09:00:00"
    assert commit_dates[1] == "2026-06-01T15:00:00"
    assert commit_dates[-1] == "2026-06-05T11:30:00"          # current work folded in
    assert "m1" in model["journeyIndexCommits"]


def test_git_day_history_empty_without_filepath_or_glyphs(monkeypatch, tmp_path) -> None:
    # git_day_history needs a saved font and a live Glyphs; otherwise it stays dormant.
    font_unsaved = _FakeFont([_FakeMaster("m1", "Regular")], filepath=None)
    assert db.git_day_history(font_unsaved) == {}
    font = _FakeFont([_FakeMaster("m1", "Regular")], filepath=str(tmp_path / "F.glyphs"))
    monkeypatch.setattr(db, "Glyphs", None)
    assert db.git_day_history(font) == {}


def test_git_day_history_derives_days_from_precollected_commits(monkeypatch, tmp_path) -> None:
    # With this run's git pass in hand, the day view is derived (last checkpoint of
    # each day wins) — git is not walked a second time.
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath=str(tmp_path / "F.glyphs"))

    def exploding_collect(*args, **kwargs) -> dict:
        raise AssertionError("collect_git_history must not be called")

    monkeypatch.setattr(db.azcolorflow_git, "collect_git_history", exploding_collect)
    days = db.git_day_history(font, git_commits={
        "2026-06-01T09:00:00": {"m1": {"A": 0}},
        "2026-06-01T17:00:00": {"m1": {"A": 1}},   # same day, later -> wins
        "2026-06-02T10:00:00": {"m1": {"A": 2}},
    })
    assert days == {"2026-06-01": {"m1": {"A": 1}}, "2026-06-02": {"m1": {"A": 2}}}


def test_commit_timeline_history_merges_precollected_with_saved_log(monkeypatch) -> None:
    # Precollected commits (already-recorded keys skipped) are merged under the
    # recorded save log — the skipped checkpoints live there — so the fine timeline
    # is complete without re-opening a single commit.
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    font = _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Acme.glyphs")
    db.record_history(font, {"m1": {"A": 5}}, datetime(2026, 6, 2, 12))

    def exploding_collect(*args, **kwargs) -> dict:
        raise AssertionError("collect_commit_history must not be called")

    monkeypatch.setattr(db.azcolorflow_git, "collect_commit_history", exploding_collect)
    fine = db.commit_timeline_history(
        font, git_commits={"2026-06-01T09:00:00": {"m1": {"A": 0}}})
    assert fine == {
        "2026-06-01T09:00:00": {"m1": {"A": 0}},
        "2026-06-02T12:00:00": {"m1": {"A": 5}},   # the recorded save folds in
    }
    # tracked repo but nothing new and nothing recorded elsewhere -> stays empty
    assert db.commit_timeline_history(
        _FakeFont([_FakeMaster("m1", "R")], filepath="/fonts/Other.glyphs"),
        git_commits={}) == {}


def test_main_collects_git_commits_once_and_shares_the_pass(monkeypatch, tmp_path) -> None:
    # THE single-pass invariant: one report run performs exactly one per-commit git
    # collection (with the recorded keys skipped) — the backfill, the fine timeline
    # and the day timeline all reuse it instead of re-opening every commit.
    fake = _FakeGlyphsApp()
    fake.defaults[db.OUTLINE_CHANGE_DAYS_KEY] = 0            # keep the outline view dormant
    monkeypatch.setattr(db, "Glyphs", fake)
    monkeypatch.setattr(db.webbrowser, "open", lambda uri: None)
    monkeypatch.setattr(db, "is_git_tracked", lambda font: True)
    calls = {"commits": 0, "days": 0}
    seen: dict = {}

    def fake_commits(path, load, cap=0, progress=None, skip=None) -> dict:
        calls["commits"] += 1
        seen["skip"] = skip
        return {"2026-06-01T09:00:00": {"m1": {"A": 8}}}

    def fake_days(path, load, cap=0, progress=None, skip=None) -> dict:
        calls["days"] += 1
        return {}

    monkeypatch.setattr(db.azcolorflow_git, "collect_commit_history", fake_commits)
    monkeypatch.setattr(db.azcolorflow_git, "collect_git_history", fake_days)
    (tmp_path / "colorNames.txt").write_text("purple=Outline\nNone=Nothing\n", encoding="utf-8")
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(8)})]
    font = _FakeFont([_FakeMaster("m1", "Regular")], glyphs, filepath=str(tmp_path / "F.glyphs"))
    db.record_history(font, {"m1": {"A": cc.NO_COLOR}}, datetime(2026, 6, 1, 8))  # a prior save

    result = db.main(font, open_when_done=False)
    assert result is not None
    assert calls["commits"] == 1                             # ONE pass, not one per view
    assert calls["days"] == 0                                # day view derived, not re-collected
    assert seen["skip"] == {"2026-06-01T08:00:00"}           # recorded keys were skipped
    assert "2026-06-01T09:00:00" in db.load_history(font)    # ...and the pass fed the backfill


def test_build_model_merges_git_day_history_userdata_wins(monkeypatch, tmp_path) -> None:
    # When the font is git-tracked, the day-timeline reads from git and merges it under
    # any frozen pre-git userData past. On a shared day the live userData snapshot wins
    # (it's the actual save state, not a commit reconstruction).
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    (tmp_path / "colorNames.txt").write_text("purple=Outline\nNone=Nothing\n", encoding="utf-8")
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(8)})]
    font = _FakeFont([_FakeMaster("m1", "Regular")], glyphs, filepath=str(tmp_path / "F.glyphs"))
    db.record_history(font, {"m1": {"A": 8}}, datetime(2026, 6, 2))   # frozen pre-git userData day
    monkeypatch.setattr(db, "git_day_history", lambda font, git_commits=None: {
        "2026-06-01": {"m1": {"A": cc.NO_COLOR}},                     # git fills an earlier gap
        "2026-06-02": {"m1": {"A": 3}},                              # collides with userData's 8
    })
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["trend"]["dates"] == ["2026-06-01", "2026-06-02", "2026-06-05"]  # union of all
    # A: first seen uncoloured (git, 06-01), then 8 on 06-02 (userData wins over git's 3),
    # unchanged through 06-05 -> exactly two change-events.
    assert model["journeyIndex"]["m1"]["A"] == [["2026-06-01", cc.NO_COLOR], ["2026-06-02", 8]]


def test_build_model_fine_dataset_is_per_save_without_git(monkeypatch, tmp_path) -> None:
    # No git repo: the fine-grain Time Machine dataset comes from the userData per-save
    # log (fineKind == "save"), so non-git fonts also get a "Per save" granularity.
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    (tmp_path / "colorNames.txt").write_text("purple=Outline\nNone=Nothing\n", encoding="utf-8")
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(8)})]
    font = _FakeFont([_FakeMaster("m1", "Regular")], glyphs, filepath=str(tmp_path / "F.glyphs"))
    db.record_history(font, {"m1": {"A": cc.NO_COLOR}}, datetime(2026, 6, 4, 9))   # a prior save
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5, 14, 0), current, current)
    assert model["fineKind"] == "save"
    assert model["hasCommits"] is True                              # 2 fine points -> toggle shows
    fine_dates = model["trendCommits"]["dates"]
    assert fine_dates[0] == "2026-06-04T09:00:00"                   # the prior save
    assert fine_dates[-1] == "2026-06-05T14:00:00"                  # today's live work, datetime-keyed


def test_build_model_fine_kind_is_commit_with_git(monkeypatch, tmp_path) -> None:
    # With git commit history, the fine dataset is per-commit (fineKind == "commit"),
    # even if a userData save log also exists (git takes precedence).
    monkeypatch.setattr(db, "Glyphs", _FakeGlyphsApp())
    (tmp_path / "colorNames.txt").write_text("purple=Outline\nNone=Nothing\n", encoding="utf-8")
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(8)})]
    font = _FakeFont([_FakeMaster("m1", "Regular")], glyphs, filepath=str(tmp_path / "F.glyphs"))
    monkeypatch.setattr(db, "commit_timeline_history", lambda font, git_commits=None: {
        "2026-06-01T09:00:00": {"m1": {"A": cc.NO_COLOR}},
        "2026-06-01T15:00:00": {"m1": {"A": 8}},
    })
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5, 11, 30), current, current)
    assert model["fineKind"] == "commit"
    assert model["hasCommits"] is True


def test_build_model_emits_cross_master_summary(tmp_path) -> None:
    # Two masters; A agrees on the final step (3 = yellow "Ready"), B differs.
    (tmp_path / "colorNames.txt").write_text(
        "purple=Outline\nlightGreen=Anchors\nyellow=Ready\nNone=Nothing\n", encoding="utf-8")
    masters = [_FakeMaster("m1", "Regular"), _FakeMaster("m2", "Bold")]
    glyphs = [
        _FakeGlyph("A", {"m1": _FakeLayerColor(3), "m2": _FakeLayerColor(3)}),
        _FakeGlyph("B", {"m1": _FakeLayerColor(8), "m2": _FakeLayerColor(4)}),
    ]
    font = _FakeFont(masters, glyphs, filepath=str(tmp_path / "Font.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    cross = model["crossMaster"]
    assert cross["total"] == 2 and cross["masterCount"] == 2
    assert cross["finalStep"] == 3           # last key in order ["8","4","3"]
    assert cross["identical"] == 1 and cross["differ"] == 1
    assert cross["doneEverywhere"] == 1      # A is final-step in both masters
    assert cross["differGlyphs"] == ["B"]


def test_build_model_counts_are_cumulative_dist_matches_palette(tmp_path) -> None:
    # masters[].counts keep the report-only cumulative semantics; the exact
    # census (dist) is what the palette's count badges now show.
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

    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert "mode" not in model                       # single (sequential) workflow
    assert model["masters"][0]["counts"] == cc.counts_from_colors(colors, order)
    assert model["masters"][0]["uncolored"] == db.uncolored_count(colors, order)


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

    def counted(*args: Any, **kwargs: Any) -> dict:
        calls[0] += 1
        return real(*args, **kwargs)

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
    monkeypatch.setattr(db, "is_git_tracked", lambda font: True)   # timeline needs git
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
    monkeypatch.setattr(db, "is_git_tracked", lambda font: True)   # timeline needs git
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
    monkeypatch.setattr(db, "is_git_tracked", lambda font: True)   # exercise the folded-trend path
    (tmp_path / "colorNames.txt").write_text("red=R\n", encoding="utf-8")
    font = _FakeFont([], [], filepath=str(tmp_path / "Empty.glyphs"))
    current = db.build_master_glyph_colors(font)            # {} -> no masters
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["glyphTotal"] == 0
    assert model["glyphNames"] == [] and model["masters"] == []
    assert model["paths"] == {} and model["coverage"]["byScript"] == {}
    assert "forecast" not in model["trend"]                # forecast feature removed
    assert model["trend"]["series"][-1]["date"] == "2026-06-05"   # today still folded in


# --------------------------------------------------------------------------- #
# Non-exporting glyphs are ALWAYS excluded from every count and percentage
# --------------------------------------------------------------------------- #

def test_non_exporting_names_sorted_from_font() -> None:
    glyphs = [_FakeGlyph("zeta", {}), _FakeGlyph("A", {}), _FakeGlyph("comma", {})]
    glyphs[0].export = False
    glyphs[2].export = False
    font = _FakeFont([_FakeMaster("m1", "R")], glyphs)
    assert db.non_exporting_names(font) == ["comma", "zeta"]    # sorted


def test_build_model_ships_non_exporting_names_only(tmp_path) -> None:
    (tmp_path / "colorNames.txt").write_text("red=R\nNone=Nothing\n", encoding="utf-8")
    master = _FakeMaster("m1", "Regular")
    letter_a = _FakeGlyph("A", {"m1": _FakeLayerColor(0)})
    ornament = _FakeGlyph("ornament", {"m1": _FakeLayerColor(0)})
    ornament.export = False
    font = _FakeFont([master], [letter_a, ornament], filepath=str(tmp_path / "Font.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["nonExporting"] == ["ornament"]
    # the exclusion is always on — no pref/toggle key ships with the model
    assert all(not key.startswith("exporting") for key in model)


def test_build_model_non_exporting_empty_when_all_export(tmp_path) -> None:
    (tmp_path / "colorNames.txt").write_text("red=R\n", encoding="utf-8")
    master = _FakeMaster("m1", "Regular")
    glyphs = [_FakeGlyph("A", {"m1": _FakeLayerColor(0)})]
    font = _FakeFont([master], glyphs, filepath=str(tmp_path / "Font.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["nonExporting"] == []


def test_build_model_counts_stay_raw_with_non_exporting_glyphs(tmp_path) -> None:
    # PARITY INVARIANT: the embedded per-master counts/keys ship ALL glyphs (raw
    # truth — the heatmap needs every key to render the dimmed cells); the report
    # ALWAYS applies the exclusion client-side, so it counts the same glyph set
    # as the palette (its census/dist numbers match the palette's badges; its
    # cumulative views keep the report-only "reached step k or beyond" sums).
    (tmp_path / "colorNames.txt").write_text("red=R\nNone=Nothing\n", encoding="utf-8")
    master = _FakeMaster("m1", "Regular")
    letter_a = _FakeGlyph("A", {"m1": _FakeLayerColor(0)})
    ornament = _FakeGlyph("ornament", {"m1": _FakeLayerColor(0)})
    ornament.export = False
    font = _FakeFont([master], [letter_a, ornament], filepath=str(tmp_path / "Font.glyphs"))
    current = db.build_master_glyph_colors(font)
    model = db.build_model(font, datetime(2026, 6, 5), current, current)
    assert model["nonExporting"] == ["ornament"]
    assert model["glyphTotal"] == 2                             # raw total
    assert model["masters"][0]["counts"] == {"0": 2}            # raw: both glyphs counted
    assert len(model["masters"][0]["keys"]) == 2                # keys ship every glyph
