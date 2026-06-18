"""Tests for the pure outline-diff logic (Glyphs-free)."""

import azcolorflow_outline_diff as od


def _p(d: str, vb: str = "0 0 10 10") -> dict:
    return {"d": d, "vb": vb}


# --------------------------------------------------------------------------- #
# diff_path_maps
# --------------------------------------------------------------------------- #

def test_diff_reports_only_changed_d() -> None:
    prev = {"m1": {"A": _p("M0 0"), "B": _p("M1 1")}}
    cur = {"m1": {"A": _p("M0 0"), "B": _p("M2 2")}}
    changes = od.diff_path_maps(prev, cur)
    assert len(changes) == 1
    assert changes[0]["glyph"] == "B"
    assert changes[0]["master"] == "m1"
    assert changes[0]["old"]["d"] == "M1 1"
    assert changes[0]["new"]["d"] == "M2 2"


def test_diff_keeps_viewboxes() -> None:
    prev = {"m1": {"A": _p("M0 0", "0 0 5 5")}}
    cur = {"m1": {"A": _p("M9 9", "1 1 6 6")}}
    change = od.diff_path_maps(prev, cur)[0]
    assert change["old"]["vb"] == "0 0 5 5"
    assert change["new"]["vb"] == "1 1 6 6"


def test_diff_ignores_added_and_removed_glyphs() -> None:
    # B only in cur (added), C only in prev (removed) -> neither reported
    prev = {"m1": {"A": _p("M0 0"), "C": _p("M3 3")}}
    cur = {"m1": {"A": _p("M0 0"), "B": _p("M2 2")}}
    assert od.diff_path_maps(prev, cur) == []


def test_diff_skips_empty_outlines() -> None:
    prev = {"m1": {"A": _p("")}}            # was inkless
    cur = {"m1": {"A": _p("M0 0")}}          # now has ink
    assert od.diff_path_maps(prev, cur) == []


def test_diff_is_per_master() -> None:
    prev = {"m1": {"A": _p("M0 0")}, "m2": {"A": _p("M0 0")}}
    cur = {"m1": {"A": _p("M0 0")}, "m2": {"A": _p("M9 9")}}
    changes = od.diff_path_maps(prev, cur)
    assert [(c["master"], c["glyph"]) for c in changes] == [("m2", "A")]


def test_diff_sorted_by_master_then_glyph() -> None:
    prev = {"m2": {"B": _p("a"), "A": _p("a")}, "m1": {"Z": _p("a")}}
    cur = {"m2": {"B": _p("b"), "A": _p("b")}, "m1": {"Z": _p("b")}}
    changes = od.diff_path_maps(prev, cur)
    assert [(c["master"], c["glyph"]) for c in changes] == [("m1", "Z"), ("m2", "A"), ("m2", "B")]


# --------------------------------------------------------------------------- #
# outline_changes (chronological adjacent-day diff)
# --------------------------------------------------------------------------- #

def test_outline_changes_diffs_adjacent_days() -> None:
    day_maps = {
        "2026-06-01": {"m1": {"A": _p("M0 0")}},
        "2026-06-02": {"m1": {"A": _p("M1 1")}},     # changed vs 06-01
        "2026-06-03": {"m1": {"A": _p("M1 1")}},     # same as 06-02 -> no change
    }
    result = od.outline_changes(day_maps)
    assert set(result) == {"2026-06-02"}            # earliest has no predecessor; 06-03 unchanged
    assert result["2026-06-02"][0]["glyph"] == "A"


def test_outline_changes_earliest_day_never_appears() -> None:
    day_maps = {"2026-06-01": {"m1": {"A": _p("M0 0")}}}
    assert od.outline_changes(day_maps) == {}


def test_outline_changes_orders_by_date_not_insertion() -> None:
    # insertion order scrambled; diff must still be chronological
    day_maps = {
        "2026-06-03": {"m1": {"A": _p("M2 2")}},
        "2026-06-01": {"m1": {"A": _p("M0 0")}},
        "2026-06-02": {"m1": {"A": _p("M1 1")}},
    }
    result = od.outline_changes(day_maps)
    assert set(result) == {"2026-06-02", "2026-06-03"}


def test_outline_changes_respects_limit_per_day() -> None:
    prev = {"m1": {g: _p("x") for g in ("A", "B", "C", "D")}}
    cur = {"m1": {g: _p("y") for g in ("A", "B", "C", "D")}}
    day_maps = {"2026-06-01": prev, "2026-06-02": cur}
    result = od.outline_changes(day_maps, limit_per_day=2)
    assert len(result["2026-06-02"]) == 2
    # kept in the stable (master, glyph) order -> A, B
    assert [c["glyph"] for c in result["2026-06-02"]] == ["A", "B"]
