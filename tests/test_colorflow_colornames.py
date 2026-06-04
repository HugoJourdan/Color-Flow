"""Tests for the shared, GlyphsApp-free colorNames logic.

This module is the single source of truth for how Color Flow turns a
``colorNames.txt`` file into the ``{"0".."11": label}`` mapping used by both the
palette plugin and the keyboard-shortcut scripts.
"""

import os

import colorflow_colornames as cc


# --------------------------------------------------------------------------- #
# Constants / canonical mapping
# --------------------------------------------------------------------------- #

def test_color_order_has_the_twelve_glyphs_labels_in_index_order():
    assert cc.COLOR_ORDER == [
        "red", "orange", "brown", "yellow", "lightGreen", "darkGreen",
        "lightBlue", "darkBlue", "purple", "magenta", "lightGray", "charcoal",
    ]


def test_name_to_index_maps_each_color_to_its_string_index():
    assert cc.NAME_TO_INDEX["red"] == "0"
    assert cc.NAME_TO_INDEX["charcoal"] == "11"
    assert len(cc.NAME_TO_INDEX) == 12


def test_default_content_parses_to_the_twelve_default_labels():
    parsed = cc.parse_color_names(cc.DEFAULT_COLOR_NAMES)
    assert parsed == {
        "0": "Red", "1": "Orange", "2": "Brown", "3": "Yellow",
        "4": "Light green", "5": "Dark green", "6": "Light blue",
        "7": "Dark blue", "8": "Purple", "9": "Magenta",
        "10": "Light Gray", "11": "Charcoal",
    }


# --------------------------------------------------------------------------- #
# parse_color_names
# --------------------------------------------------------------------------- #

def test_parse_preserves_file_line_order():
    text = "purple=Outline\nlightGreen=Anchors\nyellow=Export"
    parsed = cc.parse_color_names(text)
    assert list(parsed.keys()) == ["8", "4", "3"]  # purple, lightGreen, yellow


def test_parse_keeps_present_colors_with_empty_labels():
    # An empty label hides the color in the UI but the key must still be present.
    parsed = cc.parse_color_names("red=\norange=Step 2")
    assert parsed == {"0": "", "1": "Step 2"}


def test_parse_skips_blank_and_malformed_lines_without_crashing():
    # H7: a blank line, a comment, or any '='-less line must not raise.
    text = "red=Red\n\n# a comment\njust noise\norange=Orange\n"
    parsed = cc.parse_color_names(text)
    assert parsed == {"0": "Red", "1": "Orange"}


def test_parse_skips_none_color():
    parsed = cc.parse_color_names("None=whatever\nred=Red")
    assert parsed == {"0": "Red"}


def test_parse_skips_unknown_color_names():
    # A typo'd / unsupported color name is dropped instead of raising KeyError.
    parsed = cc.parse_color_names("pink=Nope\nred=Red")
    assert parsed == {"0": "Red"}


def test_parse_strips_surrounding_whitespace_on_name_and_label():
    parsed = cc.parse_color_names("  red = Outline corrected  ")
    assert parsed == {"0": "Outline corrected"}


def test_parse_handles_trailing_newline_on_last_line():
    parsed = cc.parse_color_names("charcoal=Charcoal\n")
    assert parsed == {"11": "Charcoal"}


def test_parse_keeps_everything_after_the_first_equals_in_the_label():
    parsed = cc.parse_color_names("red=a=b=c")
    assert parsed == {"0": "a=b=c"}


def test_parse_empty_text_returns_empty_mapping():
    assert cc.parse_color_names("") == {}


# --------------------------------------------------------------------------- #
# visible_labels
# --------------------------------------------------------------------------- #

def test_visible_labels_excludes_empty_labels():
    parsed = {"0": "", "1": "Step 2", "2": ""}
    assert cc.visible_labels(parsed) == {"1": "Step 2"}


# --------------------------------------------------------------------------- #
# key-file resolution
# --------------------------------------------------------------------------- #

def test_resolve_prefers_local_file_when_it_exists(tmp_path):
    font_dir = tmp_path / "font"
    info_dir = tmp_path / "info"
    font_dir.mkdir()
    local = font_dir / cc.KEY_FILE_NAME
    local.write_text("red=Red")
    resolved = cc.resolve_key_file(str(font_dir), str(info_dir))
    assert resolved == str(local)


def test_resolve_falls_back_to_info_dir_when_no_local_file(tmp_path):
    font_dir = tmp_path / "font"
    info_dir = tmp_path / "info"
    font_dir.mkdir()
    resolved = cc.resolve_key_file(str(font_dir), str(info_dir))
    assert resolved == str(info_dir / cc.KEY_FILE_NAME)


def test_resolve_uses_info_dir_when_font_dir_is_none(tmp_path):
    info_dir = tmp_path / "info"
    resolved = cc.resolve_key_file(None, str(info_dir))
    assert resolved == str(info_dir / cc.KEY_FILE_NAME)


# --------------------------------------------------------------------------- #
# ensure_key_file  (real filesystem, fixes the handle leak + mkdir gaps)
# --------------------------------------------------------------------------- #

def test_ensure_creates_default_file_and_parent_dir_when_missing(tmp_path):
    target = tmp_path / "nested" / "info" / cc.KEY_FILE_NAME
    cc.ensure_key_file(str(target))
    assert target.exists()
    # The created file must parse back to the 12 defaults (proves it was flushed
    # and closed — no leaked, unflushed handle).
    assert cc.parse_color_names(target.read_text()) == cc.parse_color_names(
        cc.DEFAULT_COLOR_NAMES
    )


def test_ensure_does_not_write_through_a_broken_symlink(tmp_path):
    # A dangling colorNames.txt symlink (target moved) must never be written
    # through — that would create/clobber the (possibly shared) target.
    target = tmp_path / "missing_target.txt"
    link = tmp_path / cc.KEY_FILE_NAME
    os.symlink(str(target), str(link))
    cc.ensure_key_file(str(link))
    assert not target.exists()
    assert not link.exists()  # exists() follows the link → still broken


def test_ensure_does_not_overwrite_an_existing_file(tmp_path):
    target = tmp_path / cc.KEY_FILE_NAME
    target.write_text("red=Custom")
    cc.ensure_key_file(str(target))
    assert target.read_text() == "red=Custom"


def test_default_info_dir_is_expanded_and_absolute():
    info_dir = cc.default_info_dir()
    assert "~" not in info_dir
    assert info_dir.endswith(os.path.join("Glyphs 3", "info"))


def test_default_info_dir_falls_back_to_home_env_when_expanduser_fails(monkeypatch):
    # Reproduces the crash: in Glyphs' embedded Python expanduser('~') can come
    # back unexpanded; we must still resolve a real home from $HOME.
    monkeypatch.setattr(os.path, "expanduser", lambda path: path)
    monkeypatch.setenv("HOME", "/tmp/fakehome")
    assert cc.default_info_dir() == os.path.join(
        "/tmp/fakehome", "Library", "Application Support", "Glyphs 3", "info"
    )


def test_ensure_key_file_is_best_effort_and_never_raises(tmp_path):
    # If the directory cannot be created (here the parent path runs through a
    # regular file), ensure_key_file must NOT raise — a key-file problem must
    # never crash plugin load.
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    target = blocker / "info" / cc.KEY_FILE_NAME
    result = cc.ensure_key_file(str(target))
    assert result == str(target)
    assert not os.path.exists(str(target))


def test_load_meaning_falls_back_to_defaults_when_file_unwritable_and_absent(tmp_path):
    # Broken symlink / unwritable / absent key file must NOT yield an empty
    # palette — fall back to the 12 defaults in memory.
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    info_dir = blocker / "info"  # cannot be created (parent is a file)
    assert cc.load_meaning(None, info_dir=str(info_dir)) == cc.parse_color_names(
        cc.DEFAULT_COLOR_NAMES
    )


def test_load_meaning_respects_an_existing_custom_file(tmp_path):
    info_dir = tmp_path / "info"
    info_dir.mkdir()
    (info_dir / cc.KEY_FILE_NAME).write_text("purple=Outline\nyellow=Export")
    assert cc.load_meaning(None, info_dir=str(info_dir)) == {"8": "Outline", "3": "Export"}


def test_load_meaning_falls_back_to_defaults_for_a_blank_file(tmp_path):
    info_dir = tmp_path / "info"
    info_dir.mkdir()
    (info_dir / cc.KEY_FILE_NAME).write_text("   \n")
    assert cc.load_meaning(None, info_dir=str(info_dir)) == cc.parse_color_names(
        cc.DEFAULT_COLOR_NAMES
    )


def test_get_key_file_creates_and_returns_path(tmp_path):
    info_dir = tmp_path / "info"
    path = cc.get_key_file(None, info_dir=str(info_dir))
    assert path == str(info_dir / cc.KEY_FILE_NAME)
    assert os.path.exists(path)


def test_load_meaning_round_trips_default(tmp_path):
    info_dir = tmp_path / "info"
    meaning = cc.load_meaning(None, info_dir=str(info_dir))
    assert meaning == cc.parse_color_names(cc.DEFAULT_COLOR_NAMES)


# --------------------------------------------------------------------------- #
# default_state
# --------------------------------------------------------------------------- #

def test_default_state_is_all_false_in_order():
    assert cc.default_state(["0", "1", "2"]) == {"0": False, "1": False, "2": False}


# --------------------------------------------------------------------------- #
# layer_color_for_state — the documented "precedent color of the first
# unchecked checkbox" rule, the single derivation used by palette + shortcuts.
# --------------------------------------------------------------------------- #

def test_color_is_none_when_first_step_unchecked():
    state = {"0": False, "1": True, "2": True}
    assert cc.layer_color_for_state(state, ["0", "1", "2"]) is None


def test_color_is_last_of_a_contiguous_checked_prefix():
    # README example: 0,1 checked, 2 unchecked -> color is 1 (precedes 2).
    state = {"0": True, "1": True, "2": False, "3": True}
    assert cc.layer_color_for_state(state, ["0", "1", "2", "3"]) == 1


def test_color_stops_at_first_gap_ignoring_later_checks():
    state = {"0": True, "1": False, "2": True}
    assert cc.layer_color_for_state(state, ["0", "1", "2"]) == 0


def test_color_is_last_index_when_all_checked():
    state = {"0": True, "1": True, "2": True}
    assert cc.layer_color_for_state(state, ["0", "1", "2"]) == 2


def test_color_follows_custom_order_not_numeric_order():
    # Reordered colorNames: purple(8) first, then lightGreen(4), then yellow(3).
    order = ["8", "4", "3"]
    state = {"8": True, "4": True, "3": False}
    assert cc.layer_color_for_state(state, order) == 4


def test_color_handles_order_not_starting_at_zero():
    assert cc.layer_color_for_state({"4": True, "5": True}, ["4", "5"]) == 5


def test_color_is_none_for_empty_order():
    assert cc.layer_color_for_state({}, []) is None


def test_color_treats_missing_key_as_unchecked():
    # A step present in `order` but absent from the layer state counts as off.
    assert cc.layer_color_for_state({"0": True}, ["0", "1"]) == 0


# --------------------------------------------------------------------------- #
# count_states — aggregate per-master progress counts derived from layer state.
# Used to self-heal corrupt/missing persisted counts.
# --------------------------------------------------------------------------- #

def test_count_states_counts_truthy_per_index():
    states = [{"0": True, "1": False}, {"0": True, "1": True}]
    assert cc.count_states(states, ["0", "1"]) == {"0": 2, "1": 1}


def test_count_states_treats_missing_key_as_unchecked():
    assert cc.count_states([{"0": True}], ["0", "1"]) == {"0": 1, "1": 0}


def test_count_states_with_no_states_is_all_zero():
    assert cc.count_states([], ["0", "1", "2"]) == {"0": 0, "1": 0, "2": 0}


def test_count_states_accepts_one_and_zero_ints():
    states = [{"0": 1}, {"0": 0}, {"0": 1}]
    assert cc.count_states(states, ["0"]) == {"0": 2}


def test_count_states_follows_order_keys_only():
    # Keys outside `order` are ignored.
    states = [{"0": True, "99": True}]
    assert cc.count_states(states, ["0"]) == {"0": 1}


# --------------------------------------------------------------------------- #
# selection_signature — cheap fingerprint of what the palette renders, so
# update() can early-return when nothing relevant changed.
# --------------------------------------------------------------------------- #

def test_selection_signature_changes_with_master_layer_or_state():
    base = cc.selection_signature("m1", [("a", {"0": True})])
    assert cc.selection_signature("m1", [("a", {"0": True})]) == base       # stable
    assert cc.selection_signature("m2", [("a", {"0": True})]) != base       # master change
    assert cc.selection_signature("m1", [("a", {"0": False})]) != base      # state change
    assert cc.selection_signature("m1", [("b", {"0": True})]) != base       # selection change
    assert cc.selection_signature("m1", []) != base                        # empty selection


def test_selection_signature_is_order_independent_within_a_state():
    a = cc.selection_signature("m1", [("g", {"0": True, "1": False})])
    b = cc.selection_signature("m1", [("g", {"1": False, "0": True})])
    assert a == b


def test_selection_signature_tolerates_none_state():
    assert cc.selection_signature("m1", [("g", None)]) == cc.selection_signature(
        "m1", [("g", {})]
    )
