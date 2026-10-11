"""The native report's data layer must agree with the JS maths on the sample model."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "AZ-Colorflow.glyphsPlugin/Contents/Resources"))
sys.path.insert(0, str(ROOT / "tools"))

import dashboard_sample  # noqa: E402
from azcolorflow_native_model import NO_COLOR, ReportModel, smooth_segments  # noqa: E402


def _model() -> ReportModel:
    return ReportModel(dashboard_sample._model())


def test_graded_percentages_are_consistent_between_live_and_history() -> None:
    model = _model()
    assert 0 <= model.graded_overall_pct() <= 100
    last = model.dates[-1]
    for master in model.masters:
        # the sample journey index ends at each glyph's live key, so reconstructing
        # the last snapshot must reproduce the live graded % (JS gradedPctAt == gradedMasterPct)
        assert round(model.graded_pct_at(master["id"], last)) == model.graded_master_pct(master)
        live = {
            name: key
            for name, key in zip(model.glyph_names, master["keys"], strict=False)
            if key != NO_COLOR
        }
        assert {
            k: v for k, v in model.state_at(master["id"], last).items() if v != NO_COLOR
        } == live


def test_change_counts_and_calendar() -> None:
    model = _model()
    for master in model.masters:
        chg = model.change_counts(master["id"])
        assert len(chg) == len(model.dates) and chg[0] == 0 and sum(chg) > 0
    activity = model.cal_activity_scoped(None)
    assert set(activity) == set(model.dates)


def test_coverage_rows_merge_every_master() -> None:
    model = _model()
    rows = model.cov_rows("byCategory")
    assert rows and rows[0]["key"] == "Letter"
    assert sum(row["total"] for row in rows) == model.glyph_total * len(model.masters)
    single = model.cov_rows("byCategory", model.masters[0]["id"])
    assert sum(row["total"] for row in single) == model.glyph_total


def test_lanes_and_leaderboard_order() -> None:
    model = _model()
    lanes = model.lanes("category", None, None)
    assert [lane["key"] for lane in lanes][:2] == ["Letter", "Number"]
    assert all(len(lane["values"]) == len(model.dates) for lane in lanes)
    board = model.leaderboard_rows()
    assert board == sorted(board, key=lambda row: (-row["p"], row["name"]))
    digest = model.week_digest()  # week-ago snaps to the EARLIEST date (JS snapDate fallback)
    assert digest is not None and digest[
        "delta"
    ] == model.graded_overall_pct() - model.graded_overall_pct_at(model.dates[0])


def test_smooth_segments_never_overshoot() -> None:
    segments = smooth_segments([(0, 0), (10, 10), (20, 10), (30, 0)])
    assert len(segments) == 3
    # a local maximum gets a zero tangent: both handles around (10,10)-(20,10) stay at y=10
    assert segments[1][0][1] == 10 and segments[1][1][1] == 10


def test_timeline_lock_below_three_snapshots() -> None:
    assert _model().timeline_lock() == ""
    raw = dashboard_sample._model()
    last = raw["trend"]["dates"][0]
    raw["trend"]["dates"], raw["trend"]["series"] = [last], raw["trend"]["series"][:1]
    for per_master in raw["journeyIndex"].values():
        for name, events in list(per_master.items()):
            per_master[name] = [event for event in events if event[0] <= last]
    lock = ReportModel(raw).timeline_lock()
    assert lock.startswith("Timeline unlocks at 3 ") and "1 so far" in lock
