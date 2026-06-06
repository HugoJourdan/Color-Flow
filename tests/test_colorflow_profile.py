"""Tests for the portable .colorflow profile (export / import / diff)."""

from __future__ import annotations

import pytest

import colorflow_profile as profile


def _profile(color_names: str = "red=Outline\norange=Spacing\n", free_mode: bool = False,
             rainbow_source: str = "Layer", label_colors: list | None = None) -> dict:
    return profile.build_profile(
        color_names=color_names, free_mode=free_mode, rainbow_source=rainbow_source,
        label_colors=label_colors if label_colors is not None else [[1, 0, 0, 1], [0, 1, 0, 1]],
        name="House style")


def test_build_profile_normalises_unknown_source() -> None:
    built = profile.build_profile("red=A\n", False, "Nonsense", [])
    assert built["rainbowSource"] == "Layer"      # unknown source -> default
    assert built["version"] == profile.PROFILE_VERSION


def test_serialize_parse_round_trips() -> None:
    original = _profile(free_mode=True, rainbow_source="Glyph")
    assert profile.parse(profile.serialize(original)) == original


def test_parse_rejects_bad_json_and_wrong_version() -> None:
    with pytest.raises(ValueError):
        profile.parse("{not json")
    with pytest.raises(ValueError):
        profile.parse("[]")                       # not an object
    with pytest.raises(ValueError):
        profile.parse('{"version": 999}')         # unsupported version


def test_diff_identical_profiles_is_empty() -> None:
    assert profile.diff_profile(_profile(), _profile()) == []


def test_diff_reports_mode_and_source() -> None:
    diffs = profile.diff_profile(_profile(free_mode=False, rainbow_source="Layer"),
                                 _profile(free_mode=True, rainbow_source="Glyph"))
    fields = {d["field"]: d["detail"] for d in diffs}
    assert fields["Mode"] == "step -> free"
    assert fields["Rainbow source"] == "Layer -> Glyph"


def test_diff_reports_label_colour_count() -> None:
    diffs = profile.diff_profile(_profile(label_colors=[[1, 0, 0, 1]]),
                                 _profile(label_colors=[[0, 0, 1, 1]]))
    assert any(d["field"] == "Label colours" and "1 of 12" in d["detail"] for d in diffs)


def test_diff_reports_colour_label_visibility_and_order() -> None:
    label_change = profile.diff_profile(_profile("red=Outline\norange=Spacing\n"),
                                        _profile("red=Outline\norange=Kerning\n"))
    assert any(d["field"] == "Label" and "Kerning" in d["detail"] for d in label_change)

    hide = profile.diff_profile(_profile("lightBlue=Spacing\n"),
                                _profile("#lightBlue=Spacing\n"))
    assert any(d["field"] == "Visibility" and "hidden" in d["detail"] for d in hide)

    reorder = profile.diff_profile(_profile("red=A\norange=B\n"),
                                   _profile("orange=B\nred=A\n"))
    assert any(d["field"] == "Order" for d in reorder)


def test_diff_reports_none_label() -> None:
    diffs = profile.diff_profile(_profile("red=A\nNone=Nothing\n"),
                                 _profile("red=A\nNone=Uncoloured\n"))
    assert any(d["field"] == "None label" for d in diffs)
