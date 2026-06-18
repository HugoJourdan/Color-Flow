"""Tests for the Color Flow smart-filter group builder."""

from __future__ import annotations

import azcolorflow_filters as filters


def test_step_filter_is_exact_color_index_predicate() -> None:
    assert filters.step_filter("Spacing", 6) == {"name": "Spacing", "predicate": "colorIndex == 6"}


def test_build_group_one_filter_per_step_plus_none() -> None:
    group = filters.build_filter_group([(8, "Outline"), (4, "Anchors")], none_label="Untouched")
    assert group["name"] == "AZ Colorflow"
    items = group["subGroup"]
    assert [item["predicate"] for item in items] == [
        "colorIndex == 8", "colorIndex == 4", f"colorIndex == {filters.NO_COLOR_INDEX}"]
    assert items[0]["name"] == "Outline" and items[-1]["name"] == "Untouched"


def test_build_group_preserves_workflow_order_not_numeric() -> None:
    # order is purple(8) before lightGreen(4): the predicates must follow that
    # order, never be re-sorted into a (wrong) ascending colorIndex run.
    group = filters.build_filter_group([(8, "First"), (4, "Second"), (3, "Third")])
    assert [item["predicate"] for item in group["subGroup"][:3]] == [
        "colorIndex == 8", "colorIndex == 4", "colorIndex == 3"]


def test_build_group_blank_label_falls_back_to_index() -> None:
    group = filters.build_filter_group([(5, "")])
    assert group["subGroup"][0]["name"] == "Colour 5"


def test_merge_replaces_previous_group_and_keeps_others() -> None:
    existing = [{"name": "My filter", "predicate": "name LIKE 'a*'"},
                {"name": "AZ Colorflow", "subGroup": [{"name": "old"}]}]
    group = filters.build_filter_group([(0, "Step")])
    merged = filters.merge_into_filters(existing, group)
    assert [entry["name"] for entry in merged] == ["My filter", "AZ Colorflow"]   # one AZ Colorflow only
    assert merged[-1]["subGroup"][0]["predicate"] == "colorIndex == 0"          # the new one


def test_merge_into_empty_filters() -> None:
    group = filters.build_filter_group([(0, "Step")])
    assert filters.merge_into_filters(None, group) == [group]
