"""Single source of truth for Color Flow's colorNames mapping.

This module is deliberately free of any GlyphsApp / AppKit imports so it can be
unit-tested with plain CPython and embedded verbatim into the keyboard-shortcut
scripts by ``tools/generate_shortcuts.py``. It is also imported directly by the
palette ``plugin.py`` (Glyphs adds the bundle's ``Resources/`` dir to sys.path).

Both halves of the product (palette + shortcuts) must agree on:
  * the file name (``colorNames.txt``),
  * the color-name -> index map,
  * how a ``colorNames.txt`` file is parsed into ``{"0".."11": label}``.

Keeping that here means the two can never drift again.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from typing import Any

# Canonical color order — index 0..11 matches Glyphs' native layer color labels.
COLOR_ORDER = [
    "red", "orange", "brown", "yellow", "lightGreen", "darkGreen",
    "lightBlue", "darkBlue", "purple", "magenta", "lightGray", "charcoal",
]

# colorName -> index string ("0".."11").
NAME_TO_INDEX = {name: str(index) for index, name in enumerate(COLOR_ORDER)}

# Int-keyed views, used by the Font-View grouping (Glyphs' native .color is int).
NAME_TO_COLOR = {name: index for index, name in enumerate(COLOR_ORDER)}
COLOR_NAMES = {index: name for index, name in enumerate(COLOR_ORDER)}

# The "no color label" bucket for Font-View grouping. Glyphs' .color is 0-11 or
# None, so the sentinel sits outside that range; the parser maps the literal
# "None" name to it and grouping always places it last.
NO_COLOR = -1
NONE_TOKEN = "None"

# File the plugin and shortcuts both read. (The README documents this name too.)
KEY_FILE_NAME = "colorNames.txt"

# Optional in-font storage for the colour labels (the same text as colorNames.txt).
# When present in ``font.userData`` it travels inside the .glyphs file, so a shared
# font shows the same labels without the sidecar file. Takes precedence over the
# external key file (see :func:`pick_settings_text`).
FONT_LABELS_KEY = "com.hugojourdan.ColorFlow.colorNames"


def _user_home() -> str:
    """Best-effort home directory.

    Glyphs' embedded Python has been seen to return ``~`` unexpanded from
    ``os.path.expanduser`` at plugin-load time; fall back to ``$HOME`` /
    ``$USERPROFILE`` so we never build a literal ``~/...`` path (which then
    crashes on open()).
    """
    home = os.path.expanduser("~")
    if not home or home.startswith("~"):
        home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or ""
    return home


def _glyphs_support_dir() -> str:
    """Glyphs 3 application-support directory.

    Uses GlyphsApp's own ``GSGlyphsInfo.applicationSupportPath()`` when running
    inside Glyphs (robust, sandbox-aware); falls back to a plain ``$HOME`` path
    outside Glyphs so this module stays importable and unit-testable.
    """
    try:
        from GlyphsApp import GSGlyphsInfo  # type: ignore[import]  # Glyphs-only
        path = os.path.expanduser(str(GSGlyphsInfo.applicationSupportPath()))
        if path and not path.startswith("~"):
            return path
    except Exception:
        pass
    return os.path.join(_user_home(), "Library", "Application Support", "Glyphs 3")


def default_info_dir() -> str:
    """Shared Glyphs info dir, resolved at call time (not import time)."""
    return os.path.join(_glyphs_support_dir(), "info")

# Content written when no colorNames.txt exists yet. Emoji labels + a None bucket
# (matches what Rainbow FontView writes, so the two halves agree out of the box).
DEFAULT_COLOR_NAMES = (
    "None=🫥 None\n"
    "red=🚨 Red\n"
    "orange=🦊 Orange\n"
    "brown=🪵 Brown\n"
    "yellow=🌼 Yellow\n"
    "lightGreen=🍀 Light green\n"
    "darkGreen=🫑 Dark green\n"
    "lightBlue=💎 Light blue\n"
    "darkBlue=🌀 Dark blue\n"
    "purple=🔮 Purple\n"
    "magenta=🌺 Magenta\n"
    "lightGray=🏐 Light Gray\n"
    "charcoal=🎱 Charcoal\n"
)

# Default display labels by int index (for Font-View section headers when the key
# file omits an entry).
DEFAULT_LABELS = {
    0: "🚨 Red", 1: "🦊 Orange", 2: "🪵 Brown", 3: "🌼 Yellow",
    4: "🍀 Light green", 5: "🫑 Dark green", 6: "💎 Light blue", 7: "🌀 Dark blue",
    8: "🔮 Purple", 9: "🌺 Magenta", 10: "🏐 Light Gray", 11: "🎱 Charcoal",
    NO_COLOR: "🫥 None",
}


def parse_color_names(text: str) -> dict[str, str]:
    """Parse ``colorNames.txt`` content into ``{indexStr: label}`` in file order.

    Robust against the edits real users make:
      * lines without ``=`` (blank lines, comments, stray text) are skipped,
      * ``None=...`` lines are skipped,
      * unknown / mistyped color names are skipped (no KeyError),
      * surrounding whitespace on the name and label is trimmed,
      * everything after the first ``=`` is kept as the label.

    Empty labels are preserved (the color stays known but is hidden in the UI).
    Dict insertion order follows the file's line order, which is what defines the
    workflow step order.
    """
    meaning: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        name, _, label = line.partition("=")
        name = name.strip()
        if name == "None" or name not in NAME_TO_INDEX:
            continue
        meaning[NAME_TO_INDEX[name]] = label.strip()
    return meaning


def visible_labels(meaning: dict[str, str]) -> dict[str, str]:
    """Return only the entries with a non-empty label (the rows the UI shows)."""
    return {index: label for index, label in meaning.items() if label}


def final_visible_step(meaning: dict[str, str]) -> str | None:
    """The index string of the last visible workflow step, or ``None``.

    "Final" is the highest-ranked visible step in workflow order — the last
    non-empty-labelled line of ``colorNames.txt``. Shared by the palette and the
    jump shortcut so "finished" means the same thing in both halves.
    """
    visible = visible_labels(meaning)
    if not visible:
        return None
    return list(visible.keys())[-1]


def default_state(order: list[str]) -> dict[str, bool]:
    """A fresh per-layer Color Flow state: every step unchecked, in order."""
    return {index: False for index in order}


def count_states(states: list, order: list[str]) -> dict[str, int]:
    """Aggregate per-step checked counts across many layer states.

    Returns ``{index: number_of_states_where_that_step_is_checked}`` for every
    index in ``order``. Used to (re)derive a master's progress counts from the
    real layer data, which self-heals corrupt/missing persisted counters.
    A missing key counts as unchecked; both ``True`` and ``1`` count as checked.
    """
    counts = {index: 0 for index in order}
    for state in states:
        for index in order:
            if index in state and state[index]:
                counts[index] += 1
    return counts


def selection_signature(master_id, layer_states: list) -> tuple:
    """Cheap, hashable fingerprint of what the palette renders.

    ``layer_states`` is a list of ``(glyph_name, state_dict)``. Comparing the
    returned tuple against the last one lets the high-frequency update() handler
    early-return when nothing the UI depends on (master, selection, or any
    selected layer's checkbox state) has changed. Order-independent within a
    state; tolerates a ``None`` state.
    """
    items = tuple(
        (name, tuple(sorted((str(key), bool(value)) for key, value in (state or {}).items())))
        for name, state in layer_states
    )
    return (master_id, items)


def checked_state_for_color(color, order: list[str]) -> dict[str, bool]:
    """Inverse of :func:`layer_color_for_state`.

    Given a native ``layer.color`` (int or ``None``), return the checkbox state
    that would derive it: every step up to and including ``color`` checked, the
    rest unchecked. A ``None`` or hidden/unknown color yields all-unchecked.
    """
    state = {index: False for index in order}
    if color is None:
        return state
    target = str(color)
    if target not in state:
        return state
    for index in order:
        state[index] = True
        if index == target:
            break
    return state


def single_counts_from_colors(colors: list, order: list[str]) -> dict[str, int]:
    """Exact per-step census: how many layers have *exactly* each colour.

    Unlike :func:`counts_from_colors` (cumulative), this is the exclusive
    distribution — used for the palette's count badges, row bars and
    title-bar colour segments, and the report's per-group ``dist`` data."""
    counts = {index: 0 for index in order}
    for color in colors:
        if color is None:
            continue
        key = str(color)
        if key in counts:
            counts[key] += 1
    return counts


def non_exporting_names(glyphs: Iterable[Any]) -> set[str]:
    """Names of the glyphs marked non-exporting (``GSGlyph.export == False``).

    Pure: ``glyphs`` is any iterable of objects with a ``name`` and an optional
    ``export`` flag — a missing flag counts as exporting, matching Glyphs'
    default. This is the exclusion set ALWAYS threaded through the palette's
    and the report's counting: non-exporting glyphs never count."""
    return {str(glyph.name) for glyph in glyphs if not getattr(glyph, "export", True)}


def exclude_named_colors(named_colors: Iterable[tuple[str, Any]],
                         excluded: set[str]) -> list:
    """Drop the colours of excluded glyphs from ``(glyph_name, color)`` pairs,
    returning the plain colour list the counting functions consume. An empty
    exclusion set keeps every colour (nothing to exclude — everything counts)."""
    if not excluded:
        return [color for _name, color in named_colors]
    return [color for name, color in named_colors if name not in excluded]


def counts_from_colors(colors: list, order: list[str]) -> dict[str, int]:
    """Cumulative per-step counts: layers that reached each step OR BEYOND.

    Each colour is expanded to its checkbox state via :func:`checked_state_for_color`
    (the contiguous "steps up to this colour" model), then summed. Used by the
    report's ``masters[].counts`` ("reached step k or beyond" views); the palette's
    displayed counts are the exact census (:func:`single_counts_from_colors`)."""
    states = [checked_state_for_color(color, order) for color in colors]
    return count_states(states, order)


def layer_color_for_state(state: dict[str, bool], order: list[str]) -> int | None:
    """Native Glyphs ``layer.color`` for a checkbox state.

    Implements the documented rule: the color is the step that *precedes the
    first unchecked checkbox* — i.e. the last step of the contiguous checked run
    starting from the top. ``None`` if the very first step is unchecked.

    ``order`` is the workflow order (``meaning.keys()``); a step missing from
    ``state`` counts as unchecked. This is the single derivation shared by the
    palette and the keyboard-shortcut scripts so they can never disagree.
    """
    color: int | None = None
    for index in order:
        # Avoid dict.get(): at Glyphs runtime `state` is a bridged userData
        # dict whose .get() is not guaranteed; `in` / `[]` always work.
        if index in state and state[index]:
            color = int(index)
        else:
            break
    return color


def font_labels_text(font: Any) -> str | None:
    """Colour-label text stored inside ``font.userData[FONT_LABELS_KEY]``, or ``None``.

    Reads the optional in-font label storage. Returns ``None`` when the font is
    ``None``, the key is unset, or the value is blank/not a string — so callers can
    treat ``None`` as "fall back to the external key file". Never raises."""
    if font is None:
        return None
    try:
        value = font.userData[FONT_LABELS_KEY]
    except Exception:
        return None
    if isinstance(value, str) and value.strip():
        return value
    return None


def pick_settings_text(userdata_text: str | None, file_text: str | None) -> str:
    """Resolve the colour-label settings text by precedence: the in-font value wins,
    then the external key file, then the built-in default. Blank entries are skipped
    so an empty file/userData never shadows a real source."""
    for candidate in (userdata_text, file_text):
        if candidate is not None and candidate.strip():
            return candidate
    return DEFAULT_COLOR_NAMES


def resolve_key_file(
    font_dir: str | None,
    info_dir: str | None = None,
    exists: Callable[[str], bool] = os.path.exists,
) -> str:
    """Return the path to the colorNames.txt to use.

    Prefers ``<font_dir>/colorNames.txt`` (so the mapping can travel with the
    source file and be shared between collaborators); otherwise falls back to
    ``<info_dir>/colorNames.txt``. ``font_dir`` may be ``None`` (unsaved font).
    """
    if info_dir is None:
        info_dir = default_info_dir()
    if font_dir:
        local = os.path.join(font_dir, KEY_FILE_NAME)
        if exists(local):
            return local
    return os.path.join(info_dir, KEY_FILE_NAME)


def ensure_key_file(
    path: str,
    content: str = DEFAULT_COLOR_NAMES,
    exists: Callable[[str], bool] = os.path.exists,
) -> str:
    """Create ``path`` (and any missing parent dirs) with the default content
    when it does not yet exist. Best-effort: a key-file problem must never crash
    plugin load, so filesystem errors are swallowed and the path is returned.

    Never writes through a broken symlink — that would create/clobber the
    (possibly shared) target the user pointed it at."""
    if not exists(path):
        if os.path.islink(path):
            return path
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as key_file:
                key_file.write(content)
        except OSError:
            pass
    return path


def get_key_file(font_dir: str | None, info_dir: str | None = None) -> str:
    """Resolve the colorNames.txt path and make sure it exists, returning it."""
    path = resolve_key_file(font_dir, info_dir)
    ensure_key_file(path)
    return path


def write_color_names(path: str, text: str) -> bool:
    """Write ``text`` to ``path``, best-effort. Returns True on success.

    If ``path`` is a *broken* symlink (its target is gone, e.g. an unmounted
    shared file), the dangling link is replaced with a real file so the edit can
    be saved locally. A valid symlink is written through to its target."""
    try:
        if os.path.islink(path) and not os.path.exists(path):
            os.unlink(path)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as key_file:
            key_file.write(text)
        return True
    except OSError:
        return False


def read_color_names(path: str) -> str:
    """Read a colorNames.txt file as UTF-8 text (empty string if unreadable)."""
    try:
        with open(path, encoding="utf-8") as key_file:
            return key_file.read()
    except OSError:
        return ""


def load_meaning(font_dir: str | None, info_dir: str | None = None) -> dict[str, str]:
    """Resolve + read + parse, with a defaults fallback.

    If there is no usable colorNames.txt (missing, a broken symlink, unreadable,
    or blank) the palette must still work, so we fall back to the 12 defaults in
    memory and best-effort create the file for next time. A file that exists and
    has real content is respected as-is (including an intentional all-hidden
    config, which parses to keys with empty labels)."""
    path = resolve_key_file(font_dir, info_dir)
    content = read_color_names(path)
    if content.strip():
        return parse_color_names(content)
    ensure_key_file(path)  # best-effort; a no-op if the path is a broken symlink
    return parse_color_names(DEFAULT_COLOR_NAMES)


# --------------------------------------------------------------------------- #
# Font-View grouping — int-keyed views ported from Rainbow FontView's core, so
# the merged plugin groups the Font View into colour sections from the same file.
# --------------------------------------------------------------------------- #


def color_index_for_name(name: str) -> int | None:
    """Resolve a key-file colour name to its int index, ``None`` if unknown.
    The literal ``None`` token maps to :data:`NO_COLOR`."""
    if name == NONE_TOKEN:
        return NO_COLOR
    return NAME_TO_COLOR.get(name)


def parse_key_file(text: str) -> tuple[dict[int, str], list[int], list[str]]:
    """Parse colorNames.txt into ``(meaning, order, rejected)``, int-keyed.

    ``meaning`` maps an int index (0-11 or :data:`NO_COLOR`) to its label;
    ``order`` lists indices in file order (section order); ``rejected`` collects
    unrecognised colour names. Same tolerant rules as :func:`parse_color_names`,
    but the ``None`` bucket is kept."""
    meaning: dict[int, str] = {}
    order: list[int] = []
    rejected: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name_part, label_part = line.split("=", 1)
        name = name_part.strip()
        label = label_part.strip()
        if not name or not label:
            continue
        index = color_index_for_name(name)
        if index is None:
            rejected.append(name)
            continue
        if index not in meaning:
            meaning[index] = label
            order.append(index)
    return meaning, order, rejected


def label_for(index: int, meaning: dict[int, str]) -> str:
    """Display label for an int colour index, falling back to the built-in default."""
    if index in meaning:
        return meaning[index]
    if index in DEFAULT_LABELS:
        return DEFAULT_LABELS[index]
    return f"Color {index}"


def section_order(present: set[int], order: list[int]) -> list[int]:
    """Section sequence for the colours present in the font. Key-file order first,
    then remaining present colours numerically; :data:`NO_COLOR` last unless the
    key file positioned it explicitly."""
    listed = [index for index in order if index in present]
    listed_set = set(listed)
    remaining = sorted(
        index for index in present if index not in listed_set and index != NO_COLOR
    )
    result = listed + remaining
    if NO_COLOR in present and NO_COLOR not in listed_set:
        result.append(NO_COLOR)
    return result


def build_glyph_order(
    glyph_colors: list[tuple[str, int | None]],
    meaning: dict[int, str],
    order: list[int],
    header: str = "#Color Flow",
) -> list[str]:
    """Build the ``glyphOrder`` custom-parameter value grouping glyphs by colour.
    ``glyph_colors`` is ``(glyph_name, color_index_or_None)`` in font order."""
    buckets: dict[int, list[str]] = {}
    for name, color in glyph_colors:
        index = NO_COLOR if color is None else color
        buckets.setdefault(index, []).append(name)
    code: list[str] = [header]
    for index in section_order(set(buckets), order):
        code.append(f"**{label_for(index, meaning)}**")
        code.extend(buckets[index])
    return code


def parse_settings(text: str) -> tuple[list[tuple[int, str, bool]], str]:
    """Parse colorNames.txt for the Settings panel.

    Returns ``(rows, none_label)`` where ``rows`` is an ordered list of
    ``(index, label, visible)`` covering all 12 colours (file order first, then
    any missing colours appended hidden), and ``none_label`` is the label of the
    Rainbow "None" bucket (``""`` if absent). A ``#``-commented line is a HIDDEN
    colour whose label is remembered.
    """
    rows: list[tuple[int, str, bool]] = []
    seen: set[int] = set()
    none_label = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        visible = True
        if line.startswith("#"):
            visible = False
            line = line[1:].strip()
        if "=" not in line:
            continue
        name, _, label = line.partition("=")
        name = name.strip()
        label = label.strip()
        if name == NONE_TOKEN:
            none_label = label
            continue
        index = NAME_TO_COLOR.get(name)
        if index is None or index in seen:
            continue
        seen.add(index)
        rows.append((index, label, visible))
    for index in range(12):
        if index not in seen:
            rows.append((index, DEFAULT_LABELS.get(index, ""), False))
    return rows, none_label


def render_settings(rows: list[tuple[int, str, bool]], none_label: str = "") -> str:
    """Serialise the Settings panel state back to colorNames.txt text.

    Visible colours are written ``name=label``; hidden colours are written
    ``#name=label`` so their label survives. The ``None`` bucket is preserved at
    the top when present."""
    lines: list[str] = []
    if none_label:
        lines.append(f"{NONE_TOKEN}={none_label}")
    for index, label, visible in rows:
        name = COLOR_NAMES.get(index)
        if name is None:
            continue
        prefix = "" if visible else "#"
        lines.append(f"{prefix}{name}={label}")
    return "\n".join(lines) + "\n"


def reorder_visible_rows(
    rows: list[tuple[int, str, bool]], new_visible_order: list[int]
) -> list[tuple[int, str, bool]]:
    """Return ``rows`` with the VISIBLE entries reordered to ``new_visible_order``.

    ``new_visible_order`` is the desired sequence of colour indices for the visible
    rows. Hidden rows keep their relative order and trail the visible block (matching
    how the colorNames.txt order was always persisted). Indices that aren't present,
    or are duplicated, are ignored; any visible row omitted from ``new_visible_order``
    is appended in its original order so nothing is lost."""
    by_index = {index: (index, label, visible) for index, label, visible in rows}
    visible_indices = [index for index, _label, visible in rows if visible]
    hidden_rows = [(index, label, visible) for index, label, visible in rows if not visible]
    visible_set = set(visible_indices)
    ordered: list[tuple[int, str, bool]] = []
    placed: set[int] = set()
    for index in new_visible_order:
        if index in visible_set and index not in placed:
            ordered.append(by_index[index])
            placed.add(index)
    for index in visible_indices:           # any visible row not named in new order
        if index not in placed:
            ordered.append(by_index[index])
            placed.add(index)
    return ordered + hidden_rows


def set_label_visibility(
    rows: list[tuple[int, str, bool]], index: int, visible: bool
) -> list[tuple[int, str, bool]]:
    """Return a NEW rows list with the slot ``index``'s ``visible`` flag set.

    Pure: the slot's label (and the colour-order of every row) is left untouched —
    only its visibility changes. A colour can therefore stay NAMED yet HIDDEN. If
    ``index`` is not present the rows are returned unchanged (copied)."""
    return [
        (row_index, label, visible if row_index == index else row_visible)
        for row_index, label, row_visible in rows
    ]


def render_key_file(meaning: dict[int, str], order: list[int]) -> str:
    """Serialise an int-keyed meaning/order mapping back to colorNames.txt text,
    preserving order (used to persist inline label edits)."""
    seen: set[int] = set()
    sequence: list[int] = []
    for index in order:
        if index not in seen:
            sequence.append(index)
            seen.add(index)
    for index in sorted(meaning):
        if index not in seen:
            sequence.append(index)
            seen.add(index)
    lines: list[str] = []
    for index in sequence:
        name = NONE_TOKEN if index == NO_COLOR else COLOR_NAMES.get(index)
        if name is None:
            continue
        lines.append(f"{name}={label_for(index, meaning)}")
    return "\n".join(lines) + "\n"
