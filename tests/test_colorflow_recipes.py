"""Tests for workflow recipes (#5) — including the no-recipe parity invariant."""

from __future__ import annotations

import colorflow_recipes as recipes

ORDER = ["8", "4", "6", "3"]   # workflow order; "3" is the global final step


def test_parse_recipes_normalises_and_drops_junk() -> None:
    parsed = recipes.parse_recipes(
        '[{"match": {"category": "Mark", "bogus": "x"}, "steps": [8, 4]}, "nope", {"x": 1}]')
    assert parsed == [{"match": {"category": "Mark"}, "steps": ["8", "4"]}]
    assert recipes.parse_recipes("not json") == []
    assert recipes.parse_recipes({}) == []


def test_relevant_order_defaults_to_full_order() -> None:
    assert recipes.relevant_order({"category": "Letter"}, [], ORDER) == ORDER
    # no matching recipe -> full order unchanged
    marks = [{"match": {"category": "Mark"}, "steps": ["8", "4"]}]
    assert recipes.relevant_order({"category": "Letter"}, marks, ORDER) == ORDER


def test_relevant_order_subsets_in_full_order_sequence() -> None:
    marks = [{"match": {"category": "Mark"}, "steps": ["4", "8"]}]   # given out of order
    assert recipes.relevant_order({"category": "Mark"}, marks, ORDER) == ["8", "4"]   # reordered to ORDER


def test_empty_match_never_matches() -> None:
    assert recipes.relevant_order({"category": "Mark"}, [{"match": {}, "steps": ["8"]}], ORDER) == ORDER


def test_is_glyph_complete_step_and_free() -> None:
    marks_order = ["8", "4"]   # a mark is "done" at step 4
    assert recipes.is_glyph_complete(4, marks_order, ORDER, is_free=False)      # exactly its last
    assert recipes.is_glyph_complete(3, marks_order, ORDER, is_free=False)      # beyond it -> still complete
    assert not recipes.is_glyph_complete(8, marks_order, ORDER, is_free=False)  # only at step 8
    assert recipes.is_glyph_complete(4, marks_order, ORDER, is_free=True)       # free: exact last
    assert not recipes.is_glyph_complete(3, marks_order, ORDER, is_free=True)   # free: not its last


def test_recipe_completion_credits_relevant_last_step() -> None:
    metas = [{"category": "Mark"}, {"category": "Letter"}]
    colors = [4, 4]   # both at step 4
    marks = [{"match": {"category": "Mark"}, "steps": ["8", "4"]}]
    # the mark is complete at 4; the letter needs the global final step 3 -> not complete
    assert recipes.recipe_completion(metas, colors, marks, ORDER, is_free=False) == {"complete": 1, "total": 2}


def test_no_recipes_parity_with_standard_completion() -> None:
    # Invariant: with no recipes, recipe_completion == count of glyphs at the
    # global final step (what standard completion measures).
    metas = [{}, {}, {}, {}]
    colors = [3, 3, 4, None]            # two at the final step "3"
    result = recipes.recipe_completion(metas, colors, [], ORDER, is_free=False)
    standard_final = sum(1 for c in colors if str(c) == ORDER[-1])
    assert result["complete"] == standard_final == 2
