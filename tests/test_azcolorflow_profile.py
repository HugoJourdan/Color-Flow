"""Tests for the portable .azcolorflow profile (export / import / diff)."""

from __future__ import annotations

import azcolorflow_profile as profile
import pytest


def _profile(color_names: str = "red=Outline\norange=Spacing\n",
             rainbow_source: str = "Layer", label_colors: list | None = None) -> dict:
    return profile.build_profile(
        color_names=color_names, rainbow_source=rainbow_source,
        label_colors=label_colors if label_colors is not None else [[1, 0, 0, 1], [0, 1, 0, 1]],
        name="House style")


def test_build_profile_normalises_unknown_source() -> None:
    built = profile.build_profile("red=A\n", "Nonsense", [])
    assert built["rainbowSource"] == "Layer"      # unknown source -> default
    assert built["version"] == profile.PROFILE_VERSION


def test_serialize_parse_round_trips() -> None:
    original = _profile(rainbow_source="Glyph")
    assert profile.parse(profile.serialize(original)) == original


def test_parse_ignores_unknown_keys_from_older_profiles() -> None:
    # Tolerant import: keys written by older plugin versions (e.g. the retired
    # mode flag) are dropped, and never re-exported.
    parsed = profile.parse(
        '{"version": 1, "colorNames": "red=A\\n", "freeMode": true,'
        ' "rainbowSource": "Layer", "labelColors": []}')
    assert "freeMode" not in parsed
    assert "freeMode" not in profile.serialize(parsed)


def test_parse_rejects_bad_json_and_wrong_version() -> None:
    with pytest.raises(ValueError):
        profile.parse("{not json")
    with pytest.raises(ValueError):
        profile.parse("[]")                       # not an object
    with pytest.raises(ValueError):
        profile.parse('{"version": 999}')         # unsupported version


def test_parse_rejects_non_iterable_label_colors() -> None:
    # null / number / string entries are not RGBA lists: must raise ValueError
    # (the documented contract), not a bare TypeError the importer ignores.
    with pytest.raises(ValueError):
        profile.parse('{"version": 1, "labelColors": [null, 5, "x"]}')
    with pytest.raises(ValueError):
        profile.parse('{"version": 1, "labelColors": 7}')   # field itself not a list


def test_diff_identical_profiles_is_empty() -> None:
    assert profile.diff_profile(_profile(), _profile()) == []


def test_diff_reports_source() -> None:
    diffs = profile.diff_profile(_profile(rainbow_source="Layer"),
                                 _profile(rainbow_source="Glyph"))
    fields = {d["field"]: d["detail"] for d in diffs}
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
