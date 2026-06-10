"""Workflow recipes: per-script / per-category step routing (#5).

A *recipe* declares that glyphs matching some criteria (category / script /
subCategory / case) only need a *subset* of the workflow steps — so a mark that
never gets spaced can read "complete" at its last *relevant* step instead of
stalling on an irrelevant one.

This module is pure and ADDITIVE: it computes a parallel "recipe-adjusted
completion" metric. It does NOT touch the shared ``colornames`` counting, so
every existing palette/dashboard number is unchanged. With no recipes defined,
:func:`recipe_completion` equals the standard completion count by construction
(a glyph's relevant order is the full order) — this is locked by a parity test.
"""

from __future__ import annotations

import json

_MATCH_KEYS = ("category", "script", "subCategory", "case")

# ---------------------------------------------------------------------- editor
# The pure surface the recipes-editor UI (plugin.py) builds its popups from.

# Match criteria a recipe may use, with the labels the editor shows.
MATCH_FIELDS = (
    ("category", "Category"),
    ("script", "Script"),
    ("subCategory", "Subcategory"),
    ("case", "Case"),
)

# Static popup fallbacks for when no font is open (values found in the actual
# font win — see :func:`match_options`). Categories/subcategories mirror Glyphs'
# own GlyphData vocabulary; scripts list the common ones.
DEFAULT_CATEGORIES = ("Letter", "Mark", "Number", "Punctuation", "Separator", "Symbol")
DEFAULT_SCRIPTS = ("arabic", "cyrillic", "devanagari", "greek", "han", "hangul",
                   "hebrew", "kana", "latin", "thai")
DEFAULT_SUBCATEGORIES = ("Currency", "Decimal Digit", "Fraction", "Letter", "Ligature",
                         "Math", "Modifier", "Nonspacing", "Quote", "Small", "Space",
                         "Spacing", "Spacing Combining", "Superscript")

# ``glyph.case`` is a GS enum int (GSUppercase=1 … GSMinor=4); the report's
# glyph_meta stringifies it, so recipes match on the stringified value while the
# editor shows the human name.
CASE_OPTIONS = (("1", "Uppercase"), ("2", "Lowercase"), ("3", "Smallcaps"), ("4", "Minor"))

_DEFAULT_FIELD_VALUES = {
    "category": DEFAULT_CATEGORIES,
    "script": DEFAULT_SCRIPTS,
    "subCategory": DEFAULT_SUBCATEGORIES,
}


def parse_recipes(raw) -> list[dict]:
    """Normalise a recipes config into ``[{match, steps}]``. ``raw`` may be a JSON
    string or an already-decoded list. Each recipe carries a ``match`` dict (any
    of category/script/subCategory/case), ``steps`` (str colour-index keys) and an
    optional display ``name`` (kept only when non-blank, so name-less configs are
    untouched). Anything malformed is dropped; a non-list yields ``[]``
    (= recipes off)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    if not isinstance(raw, list):
        return []
    recipes: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        match = entry.get("match")
        if not isinstance(match, dict):
            continue
        cleaned = {key: str(value) for key, value in match.items() if key in _MATCH_KEYS}
        steps = [str(step) for step in (entry.get("steps") or [])]
        recipe = {"match": cleaned, "steps": steps}
        name = str(entry.get("name") or "").strip()
        if name:
            recipe["name"] = name
        recipes.append(recipe)
    return recipes


def serialize_recipes(recipes: list) -> str:
    """Inverse of :func:`parse_recipes`: normalise ``recipes`` through the same
    cleaning rules and dump the JSON string stored under the defaults key. The
    result is validated to round-trip (``parse_recipes`` reads back exactly what
    was written) so the editor can never persist something the engine would
    interpret differently."""
    cleaned = parse_recipes(recipes)
    text = json.dumps(cleaned, ensure_ascii=False)
    if parse_recipes(text) != cleaned:  # pragma: no cover - impossible by construction
        raise ValueError("Color Flow recipes failed to round-trip through JSON.")
    return text


def match_options(field: str, font_values: list | None = None,
                  selected: str | None = None) -> list[tuple[str, str]]:
    """``(value, label)`` pairs for one match-field popup in the recipes editor.
    Values actually present in the font win (sorted, deduped, blanks dropped);
    with no font (or none found) the static vocabulary above is the fallback.
    ``case`` always uses its fixed enum/label pairs (font values are bare ints
    with no labels of their own). ``selected`` is appended when missing so
    editing an existing recipe never silently loses a value the open font
    happens to lack."""
    if field == "case":
        pairs = list(CASE_OPTIONS)
    else:
        values = sorted({str(value).strip() for value in (font_values or [])
                         if str(value).strip()})
        if not values:
            values = list(_DEFAULT_FIELD_VALUES.get(field, ()))
        pairs = [(value, value) for value in values]
    if selected and selected not in {value for value, _label in pairs}:
        pairs.append((selected, selected))
    return pairs


def _matches(match: dict, meta: dict) -> bool:
    """Whether a glyph's ``meta`` satisfies a recipe ``match``. An empty match
    never matches — recipes must name at least one criterion (no accidental
    catch-all that would silently reshape every glyph)."""
    if not match:
        return False
    return all(str(meta.get(key) or "") == value for key, value in match.items())


def relevant_order(meta: dict, recipes: list, full_order: list) -> list:
    """The steps relevant to a glyph: the first matching recipe's steps, kept in
    ``full_order`` order and intersected with it; no match (or empty result) ->
    ``full_order`` unchanged. This default is what makes the no-recipe path
    identical to today."""
    for recipe in recipes:
        if _matches(recipe["match"], meta):
            wanted = set(recipe["steps"])
            subset = [step for step in full_order if step in wanted]
            return subset or list(full_order)
    return list(full_order)


def is_glyph_complete(color, relevant: list, full_order: list, is_free: bool) -> bool:
    """Whether a glyph has reached the last step of ITS relevant order. Step mode:
    at-or-past that step (by position in the full order, so a colour beyond the
    relevant subset still counts). Free mode: exactly that step."""
    if not relevant or color is None:
        return False
    key = str(color)
    last = relevant[-1]
    if is_free:
        return key == last
    if key not in full_order or last not in full_order:
        return key == last
    return full_order.index(key) >= full_order.index(last)


def recipe_completion(metas: list, colors: list, recipes: list, full_order: list,
                      is_free: bool) -> dict:
    """``{complete, total}`` over a master: ``complete`` counts glyphs that reached
    the last step of their own relevant order. ``metas`` and ``colors`` are
    parallel per-glyph lists. With ``recipes == []`` this equals the count of
    glyphs at the global final step (standard completion)."""
    complete = sum(
        1 for meta, color in zip(metas, colors)
        if is_glyph_complete(color, relevant_order(meta, recipes, full_order), full_order, is_free)
    )
    return {"complete": complete, "total": len(colors)}
