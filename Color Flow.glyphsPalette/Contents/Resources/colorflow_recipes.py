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


def parse_recipes(raw) -> list[dict]:
    """Normalise a recipes config into ``[{match, steps}]``. ``raw`` may be a JSON
    string or an already-decoded list. Each recipe carries a ``match`` dict (any
    of category/script/subCategory/case) and ``steps`` (str colour-index keys).
    Anything malformed is dropped; a non-list yields ``[]`` (= recipes off)."""
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
        recipes.append({"match": cleaned, "steps": steps})
    return recipes


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
