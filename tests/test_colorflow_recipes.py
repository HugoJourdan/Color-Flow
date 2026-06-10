"""Tests for workflow recipes (#5) — including the no-recipe parity invariant."""

from __future__ import annotations

from pathlib import Path

import colorflow_recipes as recipes

ORDER = ["8", "4", "6", "3"]   # workflow order; "3" is the global final step

PLUGIN_SOURCE = (
    Path(__file__).resolve().parent.parent
    / "Color Flow.glyphsPalette"
    / "Contents"
    / "Resources"
    / "plugin.py"
).read_text(encoding="utf-8")


def _plugin_method_body(name: str) -> str:
    """Source of plugin method ``name`` (up to the next method def) — the same
    source-assert idiom as test_plugin_source.py (plugin.py only imports inside
    Glyphs)."""
    start = PLUGIN_SOURCE.index(f"def {name}(")
    end = PLUGIN_SOURCE.index("\n\tdef ", start)
    return PLUGIN_SOURCE[start:end]


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


# ---------------------------------------------------------------------- editor helpers


def test_parse_recipes_keeps_optional_name() -> None:
    parsed = recipes.parse_recipes(
        '[{"name": "Marks", "match": {"category": "Mark"}, "steps": ["8"]}]')
    assert parsed == [{"name": "Marks", "match": {"category": "Mark"}, "steps": ["8"]}]
    # a blank/whitespace name is dropped, so name-less configs stay name-less
    assert recipes.parse_recipes([{"name": "  ", "match": {"category": "Mark"}, "steps": []}]) \
        == [{"match": {"category": "Mark"}, "steps": []}]


def test_serialize_recipes_round_trips() -> None:
    config = [
        {"name": "Marks", "match": {"category": "Mark", "script": "latin"}, "steps": ["8", "4"]},
        {"match": {"case": "1"}, "steps": []},
    ]
    text = recipes.serialize_recipes(config)
    assert isinstance(text, str)
    assert recipes.parse_recipes(text) == recipes.parse_recipes(config) == config


def test_serialize_recipes_normalises_like_parse() -> None:
    # serialize == "parse then dump": junk entries dropped, ints stringified,
    # unknown match keys removed — exactly what parse_recipes would read back.
    raw = [{"match": {"category": "Mark", "bogus": "x"}, "steps": [8, 4]}, "junk", {"x": 1}]
    assert recipes.parse_recipes(recipes.serialize_recipes(raw)) \
        == [{"match": {"category": "Mark"}, "steps": ["8", "4"]}]


def test_serialize_recipes_empty_and_invalid_input() -> None:
    assert recipes.serialize_recipes([]) == "[]"
    # non-list input means "recipes off", same as parse_recipes
    assert recipes.serialize_recipes("garbage") == "[]"   # type: ignore[arg-type]


def test_match_fields_cover_engine_keys() -> None:
    # The editor's field list must stay in lockstep with the engine's match keys.
    assert tuple(field for field, _label in recipes.MATCH_FIELDS) \
        == ("category", "script", "subCategory", "case")


def test_match_options_font_values_win_over_defaults() -> None:
    options = recipes.match_options("category", ["Mark", "Letter", "Mark", " "])
    assert options == [("Letter", "Letter"), ("Mark", "Mark")]   # sorted, deduped, blank dropped


def test_match_options_falls_back_to_static_vocabulary() -> None:
    assert ("latin", "latin") in recipes.match_options("script")
    assert ("Letter", "Letter") in recipes.match_options("category", [])
    assert ("Ligature", "Ligature") in recipes.match_options("subCategory")


def test_match_options_always_includes_selected() -> None:
    options = recipes.match_options("category", ["Letter"], selected="Mark")
    assert ("Mark", "Mark") in options
    # already-present selected is not duplicated
    assert recipes.match_options("category", ["Mark"], selected="Mark") == [("Mark", "Mark")]


def test_match_options_case_pairs_enum_with_labels() -> None:
    options = recipes.match_options("case")
    assert ("1", "Uppercase") in options and ("3", "Smallcaps") in options
    # an unknown stored case value survives as a raw pair
    assert ("9", "9") in recipes.match_options("case", selected="9")


# ---------------------------------------------------------------------- plugin source asserts
# plugin.py only imports inside Glyphs (vanilla/AppKit), so the editor UI is
# locked by source assertions, mirroring test_plugin_source.py.


def test_plugin_popover_has_recipes_button() -> None:
    body = _plugin_method_body("Open_Action_Popover")
    assert "Workflow recipes…" in body
    assert "_open_recipes_editor" in body


def test_plugin_recipes_editor_methods_exist() -> None:
    for name in ("_open_recipes_editor", "_build_recipes_window", "_build_recipe_row",
                 "_recipes_draft_from_ui", "_recipes_add", "_recipes_remove",
                 "_recipes_save", "_recipes_cancel", "_close_recipes_editor"):
        assert f"def {name}(" in PLUGIN_SOURCE, name


def test_plugin_recipes_editor_persists_through_pure_helpers() -> None:
    save = _plugin_method_body("_recipes_save")
    assert "serialize_recipes" in save
    assert "RECIPES_KEY" in save
    load = _plugin_method_body("_open_recipes_editor")
    assert "parse_recipes" in load
    assert "RECIPES_KEY" in load


def test_plugin_recipes_popups_use_match_options() -> None:
    row = _plugin_method_body("_build_recipe_row")
    assert "match_options" in row          # font values + static fallback live in the helper
    assert "MATCH_FIELDS" in row           # one popup per engine match key
    assert "PopUpButton" in row
    assert "CheckBox" in row               # step checkboxes


def test_plugin_recipes_editor_has_buttons() -> None:
    build = _plugin_method_body("_build_recipes_window")
    assert "FloatingWindow" in build
    for attr in ("addRecipe", "removeRecipe", "cancel", "save"):
        assert f"window.{attr} = Button(" in build, attr
