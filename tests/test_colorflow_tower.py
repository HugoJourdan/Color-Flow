"""Tests for the Color Tower model + HTML injection (colorflow_tower)."""

from __future__ import annotations

import json

import colorflow_tower as tower


def test_master_color_array_tallies_slots_and_uncolored() -> None:
    colors = [0, 0, 3, None, 11, None, 7, 99, -1]
    counts, uncolored = tower.master_color_array(colors)
    assert counts[0] == 2
    assert counts[3] == 1
    assert counts[11] == 1
    assert counts[7] == 1
    assert sum(counts) == 5            # 99 and -1 are out of range -> ignored
    assert uncolored == 2              # only the two None entries
    assert len(counts) == 12


def test_master_color_array_empty() -> None:
    counts, uncolored = tower.master_color_array([])
    assert counts == [0] * 12
    assert uncolored == 0


def test_build_html_injects_model_before_head_close() -> None:
    model = {
        "total": 3,
        "masters": [{"name": "Regular",
                     "counts": [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                     "uncolored": 2}],
    }
    template = "<head><title>t</title></head><body></body>"
    html = tower.build_html(model, template)
    assert "window.TOWER_MODEL = " in html
    assert html.index("window.TOWER_MODEL") < html.index("</head>")   # injected in <head>
    start = html.index("window.TOWER_MODEL = ") + len("window.TOWER_MODEL = ")
    end = html.index(";</script>", start)
    assert json.loads(html[start:end]) == model                       # payload round-trips


def test_build_html_neutralises_script_breakout() -> None:
    model = {"total": 1,
             "masters": [{"name": "</script><b>x", "counts": [0] * 12, "uncolored": 1}]}
    html = tower.build_html(model, "<head></head>")
    assert "</script><b>" not in html        # the raw breakout never appears
    assert "<\\/script><b>" in html           # it is escaped instead


def test_build_html_default_template_is_self_contained() -> None:
    html = tower.build_html({"total": 1, "masters": []})   # reads the bundled tower.html
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "window.TOWER_MODEL = " in html
    assert "<canvas" in html
    assert "http://" not in html and "https://" not in html   # no network dependency
