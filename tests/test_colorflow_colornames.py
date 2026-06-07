"""Tests for the shared, GlyphsApp-free colorNames logic.

This module is the single source of truth for how Color Flow turns a
``colorNames.txt`` file into the ``{"0".."11": label}`` mapping used by both the
palette plugin and the keyboard-shortcut scripts.
"""

import os

import colornames as cc

# --------------------------------------------------------------------------- #
# Constants / canonical mapping
# --------------------------------------------------------------------------- #

def test_color_order_has_the_twelve_glyphs_labels_in_index_order() -> None:
    assert cc.COLOR_ORDER == [
        "red", "orange", "brown", "yellow", "lightGreen", "darkGreen",
        "lightBlue", "darkBlue", "purple", "magenta", "lightGray", "charcoal",
    ]


def test_name_to_index_maps_each_color_to_its_string_index() -> None:
    assert cc.NAME_TO_INDEX["red"] == "0"
    assert cc.NAME_TO_INDEX["charcoal"] == "11"
    assert len(cc.NAME_TO_INDEX) == 12


def test_default_content_parses_to_the_twelve_emoji_default_labels() -> None:
    # parse_color_names drops the leading None= line, leaving the 12 colours.
    parsed = cc.parse_color_names(cc.DEFAULT_COLOR_NAMES)
    assert parsed == {
        "0": "🚨 Red", "1": "🦊 Orange", "2": "🪵 Brown", "3": "🌼 Yellow",
        "4": "🍀 Light green", "5": "🫑 Dark green", "6": "💎 Light blue",
        "7": "🌀 Dark blue", "8": "🔮 Purple", "9": "🌺 Magenta",
        "10": "🏐 Light Gray", "11": "🎱 Charcoal",
    }


# --------------------------------------------------------------------------- #
# parse_color_names
# --------------------------------------------------------------------------- #

def test_parse_preserves_file_line_order() -> None:
    text = "purple=Outline\nlightGreen=Anchors\nyellow=Export"
    parsed = cc.parse_color_names(text)
    assert list(parsed.keys()) == ["8", "4", "3"]  # purple, lightGreen, yellow


def test_parse_keeps_present_colors_with_empty_labels() -> None:
    # An empty label hides the color in the UI but the key must still be present.
    parsed = cc.parse_color_names("red=\norange=Step 2")
    assert parsed == {"0": "", "1": "Step 2"}


def test_parse_skips_blank_and_malformed_lines_without_crashing() -> None:
    # H7: a blank line, a comment, or any '='-less line must not raise.
    text = "red=Red\n\n# a comment\njust noise\norange=Orange\n"
    parsed = cc.parse_color_names(text)
    assert parsed == {"0": "Red", "1": "Orange"}


def test_parse_skips_none_color() -> None:
    parsed = cc.parse_color_names("None=whatever\nred=Red")
    assert parsed == {"0": "Red"}


def test_parse_skips_unknown_color_names() -> None:
    # A typo'd / unsupported color name is dropped instead of raising KeyError.
    parsed = cc.parse_color_names("pink=Nope\nred=Red")
    assert parsed == {"0": "Red"}


def test_parse_strips_surrounding_whitespace_on_name_and_label() -> None:
    parsed = cc.parse_color_names("  red = Outline corrected  ")
    assert parsed == {"0": "Outline corrected"}


def test_parse_handles_trailing_newline_on_last_line() -> None:
    parsed = cc.parse_color_names("charcoal=Charcoal\n")
    assert parsed == {"11": "Charcoal"}


def test_parse_keeps_everything_after_the_first_equals_in_the_label() -> None:
    parsed = cc.parse_color_names("red=a=b=c")
    assert parsed == {"0": "a=b=c"}


def test_parse_empty_text_returns_empty_mapping() -> None:
    assert cc.parse_color_names("") == {}


# --------------------------------------------------------------------------- #
# visible_labels
# --------------------------------------------------------------------------- #

def test_visible_labels_excludes_empty_labels() -> None:
    parsed = {"0": "", "1": "Step 2", "2": ""}
    assert cc.visible_labels(parsed) == {"1": "Step 2"}


# --------------------------------------------------------------------------- #
# final_visible_step
# --------------------------------------------------------------------------- #

def test_final_visible_step_returns_last_visible_key() -> None:
    meaning = cc.parse_color_names("red=Rough\nyellow=Refine\norange=Done\n")
    assert cc.final_visible_step(meaning) == "1"   # orange = index 1


def test_final_visible_step_ignores_trailing_hidden_steps() -> None:
    # purple has an empty label -> hidden; the final step is the last *labelled* one
    meaning = cc.parse_color_names("red=Start\ndarkGreen=Done\npurple=\n")
    assert cc.final_visible_step(meaning) == "5"   # darkGreen = index 5


def test_final_visible_step_returns_none_when_no_visible_steps() -> None:
    assert cc.final_visible_step({}) is None
    assert cc.final_visible_step(cc.parse_color_names("red=\norange=\n")) is None


# --------------------------------------------------------------------------- #
# key-file resolution
# --------------------------------------------------------------------------- #

def test_resolve_prefers_local_file_when_it_exists(tmp_path) -> None:
    font_dir = tmp_path / "font"
    info_dir = tmp_path / "info"
    font_dir.mkdir()
    local = font_dir / cc.KEY_FILE_NAME
    local.write_text("red=Red")
    resolved = cc.resolve_key_file(str(font_dir), str(info_dir))
    assert resolved == str(local)


def test_resolve_falls_back_to_info_dir_when_no_local_file(tmp_path) -> None:
    font_dir = tmp_path / "font"
    info_dir = tmp_path / "info"
    font_dir.mkdir()
    resolved = cc.resolve_key_file(str(font_dir), str(info_dir))
    assert resolved == str(info_dir / cc.KEY_FILE_NAME)


def test_resolve_uses_info_dir_when_font_dir_is_none(tmp_path) -> None:
    info_dir = tmp_path / "info"
    resolved = cc.resolve_key_file(None, str(info_dir))
    assert resolved == str(info_dir / cc.KEY_FILE_NAME)


# --------------------------------------------------------------------------- #
# ensure_key_file  (real filesystem, fixes the handle leak + mkdir gaps)
# --------------------------------------------------------------------------- #

def test_ensure_creates_default_file_and_parent_dir_when_missing(tmp_path) -> None:
    target = tmp_path / "nested" / "info" / cc.KEY_FILE_NAME
    cc.ensure_key_file(str(target))
    assert target.exists()
    # The created file must parse back to the 12 defaults (proves it was flushed
    # and closed — no leaked, unflushed handle).
    assert cc.parse_color_names(target.read_text()) == cc.parse_color_names(
        cc.DEFAULT_COLOR_NAMES
    )


def test_ensure_does_not_write_through_a_broken_symlink(tmp_path) -> None:
    # A dangling colorNames.txt symlink (target moved) must never be written
    # through — that would create/clobber the (possibly shared) target.
    target = tmp_path / "missing_target.txt"
    link = tmp_path / cc.KEY_FILE_NAME
    os.symlink(str(target), str(link))
    cc.ensure_key_file(str(link))
    assert not target.exists()
    assert not link.exists()  # exists() follows the link → still broken


def test_ensure_does_not_overwrite_an_existing_file(tmp_path) -> None:
    target = tmp_path / cc.KEY_FILE_NAME
    target.write_text("red=Custom")
    cc.ensure_key_file(str(target))
    assert target.read_text() == "red=Custom"


def test_default_info_dir_is_expanded_and_absolute() -> None:
    info_dir = cc.default_info_dir()
    assert "~" not in info_dir
    assert info_dir.endswith(os.path.join("Glyphs 3", "info"))


def test_default_info_dir_falls_back_to_home_env_when_expanduser_fails(monkeypatch) -> None:
    # Reproduces the crash: in Glyphs' embedded Python expanduser('~') can come
    # back unexpanded; we must still resolve a real home from $HOME.
    monkeypatch.setattr(os.path, "expanduser", lambda path: path)
    monkeypatch.setenv("HOME", "/tmp/fakehome")
    assert cc.default_info_dir() == os.path.join(
        "/tmp/fakehome", "Library", "Application Support", "Glyphs 3", "info"
    )


def test_ensure_key_file_is_best_effort_and_never_raises(tmp_path) -> None:
    # If the directory cannot be created (here the parent path runs through a
    # regular file), ensure_key_file must NOT raise — a key-file problem must
    # never crash plugin load.
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    target = blocker / "info" / cc.KEY_FILE_NAME
    result = cc.ensure_key_file(str(target))
    assert result == str(target)
    assert not os.path.exists(str(target))


def test_load_meaning_falls_back_to_defaults_when_file_unwritable_and_absent(tmp_path) -> None:
    # Broken symlink / unwritable / absent key file must NOT yield an empty
    # palette — fall back to the 12 defaults in memory.
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    info_dir = blocker / "info"  # cannot be created (parent is a file)
    assert cc.load_meaning(None, info_dir=str(info_dir)) == cc.parse_color_names(
        cc.DEFAULT_COLOR_NAMES
    )


def test_load_meaning_respects_an_existing_custom_file(tmp_path) -> None:
    info_dir = tmp_path / "info"
    info_dir.mkdir()
    (info_dir / cc.KEY_FILE_NAME).write_text("purple=Outline\nyellow=Export")
    assert cc.load_meaning(None, info_dir=str(info_dir)) == {"8": "Outline", "3": "Export"}


def test_load_meaning_falls_back_to_defaults_for_a_blank_file(tmp_path) -> None:
    info_dir = tmp_path / "info"
    info_dir.mkdir()
    (info_dir / cc.KEY_FILE_NAME).write_text("   \n")
    assert cc.load_meaning(None, info_dir=str(info_dir)) == cc.parse_color_names(
        cc.DEFAULT_COLOR_NAMES
    )


def test_get_key_file_creates_and_returns_path(tmp_path) -> None:
    info_dir = tmp_path / "info"
    path = cc.get_key_file(None, info_dir=str(info_dir))
    assert path == str(info_dir / cc.KEY_FILE_NAME)
    assert os.path.exists(path)


def test_load_meaning_round_trips_default(tmp_path) -> None:
    info_dir = tmp_path / "info"
    meaning = cc.load_meaning(None, info_dir=str(info_dir))
    assert meaning == cc.parse_color_names(cc.DEFAULT_COLOR_NAMES)


# --------------------------------------------------------------------------- #
# default_state
# --------------------------------------------------------------------------- #

def test_default_state_is_all_false_in_order() -> None:
    assert cc.default_state(["0", "1", "2"]) == {"0": False, "1": False, "2": False}


# --------------------------------------------------------------------------- #
# layer_color_for_state — the documented "precedent color of the first
# unchecked checkbox" rule, the single derivation used by palette + shortcuts.
# --------------------------------------------------------------------------- #

def test_color_is_none_when_first_step_unchecked() -> None:
    state = {"0": False, "1": True, "2": True}
    assert cc.layer_color_for_state(state, ["0", "1", "2"]) is None


def test_color_is_last_of_a_contiguous_checked_prefix() -> None:
    # README example: 0,1 checked, 2 unchecked -> color is 1 (precedes 2).
    state = {"0": True, "1": True, "2": False, "3": True}
    assert cc.layer_color_for_state(state, ["0", "1", "2", "3"]) == 1


def test_color_stops_at_first_gap_ignoring_later_checks() -> None:
    state = {"0": True, "1": False, "2": True}
    assert cc.layer_color_for_state(state, ["0", "1", "2"]) == 0


def test_color_is_last_index_when_all_checked() -> None:
    state = {"0": True, "1": True, "2": True}
    assert cc.layer_color_for_state(state, ["0", "1", "2"]) == 2


def test_color_follows_custom_order_not_numeric_order() -> None:
    # Reordered colorNames: purple(8) first, then lightGreen(4), then yellow(3).
    order = ["8", "4", "3"]
    state = {"8": True, "4": True, "3": False}
    assert cc.layer_color_for_state(state, order) == 4


def test_color_handles_order_not_starting_at_zero() -> None:
    assert cc.layer_color_for_state({"4": True, "5": True}, ["4", "5"]) == 5


def test_color_is_none_for_empty_order() -> None:
    assert cc.layer_color_for_state({}, []) is None


def test_color_treats_missing_key_as_unchecked() -> None:
    # A step present in `order` but absent from the layer state counts as off.
    assert cc.layer_color_for_state({"0": True}, ["0", "1"]) == 0


# --------------------------------------------------------------------------- #
# count_states — aggregate per-master progress counts derived from layer state.
# Used to self-heal corrupt/missing persisted counts.
# --------------------------------------------------------------------------- #

def test_count_states_counts_truthy_per_index() -> None:
    states = [{"0": True, "1": False}, {"0": True, "1": True}]
    assert cc.count_states(states, ["0", "1"]) == {"0": 2, "1": 1}


def test_count_states_treats_missing_key_as_unchecked() -> None:
    assert cc.count_states([{"0": True}], ["0", "1"]) == {"0": 1, "1": 0}


def test_count_states_with_no_states_is_all_zero() -> None:
    assert cc.count_states([], ["0", "1", "2"]) == {"0": 0, "1": 0, "2": 0}


def test_count_states_accepts_one_and_zero_ints() -> None:
    states = [{"0": 1}, {"0": 0}, {"0": 1}]
    assert cc.count_states(states, ["0"]) == {"0": 2}


def test_count_states_follows_order_keys_only() -> None:
    # Keys outside `order` are ignored.
    states = [{"0": True, "99": True}]
    assert cc.count_states(states, ["0"]) == {"0": 1}


# --------------------------------------------------------------------------- #
# selection_signature — cheap fingerprint of what the palette renders, so
# update() can early-return when nothing relevant changed.
# --------------------------------------------------------------------------- #

def test_selection_signature_changes_with_master_layer_or_state() -> None:
    base = cc.selection_signature("m1", [("a", {"0": True})])
    assert cc.selection_signature("m1", [("a", {"0": True})]) == base       # stable
    assert cc.selection_signature("m2", [("a", {"0": True})]) != base       # master change
    assert cc.selection_signature("m1", [("a", {"0": False})]) != base      # state change
    assert cc.selection_signature("m1", [("b", {"0": True})]) != base       # selection change
    assert cc.selection_signature("m1", []) != base                        # empty selection


def test_selection_signature_is_order_independent_within_a_state() -> None:
    a = cc.selection_signature("m1", [("g", {"0": True, "1": False})])
    b = cc.selection_signature("m1", [("g", {"1": False, "0": True})])
    assert a == b


def test_selection_signature_tolerates_none_state() -> None:
    assert cc.selection_signature("m1", [("g", None)]) == cc.selection_signature(
        "m1", [("g", {})]
    )


# --------------------------------------------------------------------------- #
# checked_state_for_color — inverse of layer_color_for_state, used by Setup to
# derive checkbox state from an existing native layer color.
# --------------------------------------------------------------------------- #

def test_checked_state_marks_contiguous_prefix_up_to_color() -> None:
    assert cc.checked_state_for_color(1, ["0", "1", "2"]) == {
        "0": True, "1": True, "2": False
    }


def test_checked_state_all_true_when_color_is_last() -> None:
    assert cc.checked_state_for_color(2, ["0", "1", "2"]) == {
        "0": True, "1": True, "2": True
    }


def test_checked_state_first_only_when_color_is_first() -> None:
    assert cc.checked_state_for_color(0, ["0", "1", "2"]) == {
        "0": True, "1": False, "2": False
    }


def test_checked_state_all_false_for_none_color() -> None:
    assert cc.checked_state_for_color(None, ["0", "1", "2"]) == {
        "0": False, "1": False, "2": False
    }


def test_checked_state_all_false_for_hidden_color() -> None:
    # color not present in the visible order (hidden) -> nothing checked.
    assert cc.checked_state_for_color(5, ["0", "1"]) == {"0": False, "1": False}


def test_checked_state_round_trips_with_layer_color_for_state() -> None:
    order = ["0", "1", "2", "3"]
    for color in (None, 0, 2, 3):
        state = cc.checked_state_for_color(color, order)
        assert cc.layer_color_for_state(state, order) == color


# --------------------------------------------------------------------------- #
# Font-View grouping (int-keyed parser + builders)
# --------------------------------------------------------------------------- #

def test_parse_key_file_is_int_keyed_with_none_bucket_and_order() -> None:
    meaning, order, rejected = cc.parse_key_file("None=Z\npurple=P\nlightGreen=G")
    assert meaning == {cc.NO_COLOR: "Z", 8: "P", 4: "G"}
    assert order == [cc.NO_COLOR, 8, 4]
    assert rejected == []


def test_parse_key_file_collects_rejected_names() -> None:
    meaning, order, rejected = cc.parse_key_file("pink=Nope\nred=R")
    assert meaning == {0: "R"}
    assert rejected == ["pink"]


def test_label_for_falls_back_to_default() -> None:
    assert cc.label_for(0, {}) == "🚨 Red"
    assert cc.label_for(0, {0: "Custom"}) == "Custom"


def test_section_order_lists_then_remaining_then_none_last() -> None:
    assert cc.section_order({0, 4, 8, cc.NO_COLOR}, [8, 0]) == [8, 0, 4, cc.NO_COLOR]


def test_build_glyph_order_groups_with_headers_in_font_order() -> None:
    glyph_colors = [("a", 0), ("b", None), ("c", 0)]
    meaning = {0: "Red", cc.NO_COLOR: "None"}
    code = cc.build_glyph_order(glyph_colors, meaning, [0], header="#CF")
    assert code == ["#CF", "**Red**", "a", "c", "**None**", "b"]


def test_render_key_file_round_trips_through_parse() -> None:
    meaning = {8: "Outline", 4: "Anchors", cc.NO_COLOR: "None"}
    order = [8, 4, cc.NO_COLOR]
    text = cc.render_key_file(meaning, order)
    assert text == "purple=Outline\nlightGreen=Anchors\nNone=None\n"
    m2, o2, _ = cc.parse_key_file(text)
    assert m2 == meaning
    assert o2 == order


# --------------------------------------------------------------------------- #
# write_color_names (label-edit persistence)
# --------------------------------------------------------------------------- #

def test_write_color_names_creates_file(tmp_path) -> None:
    target = tmp_path / "info" / cc.KEY_FILE_NAME
    assert cc.write_color_names(str(target), "red=R\n") is True
    assert target.read_text() == "red=R\n"


def test_write_color_names_replaces_a_broken_symlink(tmp_path) -> None:
    missing = tmp_path / "gone.txt"
    link = tmp_path / cc.KEY_FILE_NAME
    os.symlink(str(missing), str(link))
    assert cc.write_color_names(str(link), "red=R\n") is True
    assert not os.path.islink(str(link))  # dangling link replaced by a real file
    assert link.read_text() == "red=R\n"


def test_write_color_names_round_trips_a_label_edit(tmp_path) -> None:
    info = tmp_path / "info"
    info.mkdir()
    path = info / cc.KEY_FILE_NAME
    path.write_text(cc.DEFAULT_COLOR_NAMES)
    meaning, order, _ = cc.parse_key_file(path.read_text())
    meaning[1] = "🦊 Spacing"  # rename Orange
    assert cc.write_color_names(str(path), cc.render_key_file(meaning, order)) is True
    reparsed, _, _ = cc.parse_key_file(path.read_text())
    assert reparsed[1] == "🦊 Spacing"


# --------------------------------------------------------------------------- #
# counts_from_colors (derive aggregate progress from native layer colors)
# --------------------------------------------------------------------------- #

def test_counts_from_colors_counts_contiguous_prefixes() -> None:
    # color 1 -> steps 0,1 done; color 0 -> step 0; None -> nothing.
    order = ["0", "1", "2"]
    counts = cc.counts_from_colors([1, 0, None], order)
    assert counts == {"0": 2, "1": 1, "2": 0}


def test_counts_from_colors_all_none_is_zero() -> None:
    assert cc.counts_from_colors([None, None], ["0", "1"]) == {"0": 0, "1": 0}


def test_counts_from_colors_ignores_hidden_colors() -> None:
    # color 5 not in the visible order -> contributes nothing.
    assert cc.counts_from_colors([5, 0], ["0", "1"]) == {"0": 1, "1": 0}


# --------------------------------------------------------------------------- #
# parse_settings / render_settings (the Settings panel: order + visibility)
# --------------------------------------------------------------------------- #

def test_parse_settings_captures_order_visibility_and_hidden_labels() -> None:
    text = "None=Z\nmagenta=Mag\n#red=Red\nblue isnt a color\n"
    rows, none_label = cc.parse_settings(text)
    assert none_label == "Z"
    # magenta(9) visible first, red(0) hidden second, then the rest appended hidden
    assert rows[0] == (9, "Mag", True)
    assert rows[1] == (0, "Red", False)
    assert len(rows) == 12  # all 12 colours represented
    assert {r[0] for r in rows} == set(range(12))


def test_parse_settings_appends_missing_colours_hidden() -> None:
    rows, _ = cc.parse_settings("red=R")
    assert rows[0] == (0, "R", True)
    # everything else appended, hidden, with default labels
    assert all(not visible for _, _, visible in rows[1:])
    assert rows[1][1] == cc.DEFAULT_LABELS[1]  # default Orange label


def test_render_settings_writes_hidden_as_commented_and_preserves_none() -> None:
    rows = [(9, "Mag", True), (0, "Red", False)]
    text = cc.render_settings(rows, none_label="🫥 None")
    assert text == "None=🫥 None\nmagenta=Mag\n#red=Red\n"


def test_settings_round_trip() -> None:
    rows = [(8, "Outline", True), (4, "Anchors", False), (3, "Export", True)]
    text = cc.render_settings(rows, none_label="None")
    rows2, none2 = cc.parse_settings(text)
    assert none2 == "None"
    assert rows2[:3] == rows  # order + visibility + labels preserved


# --------------------------------------------------------------------------- #
# highest_checked (free mode -> native layer colour)
# --------------------------------------------------------------------------- #

def test_highest_checked_returns_top_checked_index() -> None:
    assert cc.highest_checked({"0": True, "1": False, "3": True}, ["0", "1", "2", "3"]) == 3


def test_highest_checked_none_when_empty() -> None:
    assert cc.highest_checked({"0": False, "1": False}, ["0", "1"]) is None


def test_highest_checked_ignores_keys_outside_order() -> None:
    assert cc.highest_checked({"0": True, "9": True}, ["0", "1"]) == 0


# --------------------------------------------------------------------------- #
# Free mode = single-select (derived from layer.color, no userData)
# --------------------------------------------------------------------------- #

def test_exclusive_state_checks_only_the_matching_colour() -> None:
    assert cc.exclusive_state_for_color(2, ["0", "1", "2", "3"]) == {
        "0": False, "1": False, "2": True, "3": False
    }


def test_exclusive_state_all_false_for_none() -> None:
    assert cc.exclusive_state_for_color(None, ["0", "1"]) == {"0": False, "1": False}


def test_single_counts_count_exact_colour_matches() -> None:
    assert cc.single_counts_from_colors([0, 0, 2, None], ["0", "1", "2"]) == {
        "0": 2, "1": 0, "2": 1
    }
