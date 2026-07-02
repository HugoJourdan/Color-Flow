"""Tests for the compact userData history codec (delta + xz/gzip + base64)."""

from __future__ import annotations

import base64
import gzip
import json

import azcolorflow_history_store as store
import pytest

SAMPLE = {
    "2026-06-01": {"m1": {"A": 0, "B": -1}, "m2": {"A": 1, "B": 0}},
    "2026-06-02": {"m1": {"A": 2, "B": 0}, "m2": {"A": 1, "B": 1}},
}


def test_round_trips_exactly() -> None:
    assert store.decode_history(store.encode_history(SAMPLE)) == SAMPLE


def test_empty_history_round_trips() -> None:
    assert store.decode_history(store.encode_history({})) == {}


def test_encoding_is_deterministic() -> None:
    # identical history -> identical bytes (mtime pinned), so saving twice with no
    # change doesn't keep re-dirtying the font.
    assert store.encode_history(SAMPLE) == store.encode_history(SAMPLE)


def test_decode_empty_or_missing_input_is_empty() -> None:
    # "no data" stays a plain empty dict — callers may freely start a fresh log.
    assert store.decode_history(None) == {}
    assert store.decode_history("") == {}


def _wrap(payload: object) -> str:
    """base64(gzip(json(payload))) — a structurally valid container for any payload."""
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii")


def test_decode_raises_on_undecodable_payload() -> None:
    # "data present but unreadable" must be distinguishable from "no data": the
    # caller has to preserve the raw value instead of overwriting it with a fresh
    # log, so every corrupt shape raises HistoryDecodeError.
    with pytest.raises(store.HistoryDecodeError):
        store.decode_history("not-base64-!!")                      # bad base64
    with pytest.raises(store.HistoryDecodeError):
        store.decode_history(base64.b64encode(b"plain").decode())  # not gzip/xz
    with pytest.raises(store.HistoryDecodeError):
        store.decode_history(_wrap([1, 2, 3]))                     # JSON but not a mapping
    with pytest.raises(store.HistoryDecodeError):
        store.decode_history(_wrap({"v": 99, "h": {}}))            # unknown schema version
    with pytest.raises(store.HistoryDecodeError):
        store.decode_history(_wrap(                                # malformed delta model
            {"v": 2, "dates": ["2026-06-01"], "base": {"m1": {"A": "xx"}}, "steps": {}}))


def test_decode_error_is_a_value_error() -> None:
    # callers that only knew the old contract catch ValueError and keep working
    assert issubclass(store.HistoryDecodeError, ValueError)


def test_decode_coerces_values_to_str_and_int() -> None:
    decoded = store.decode_history(store.encode_history(SAMPLE))
    for masters in decoded.values():
        for glyphs in masters.values():
            for name, key in glyphs.items():
                assert isinstance(name, str)
                assert isinstance(key, int)


def test_encoded_payload_is_far_smaller_than_raw() -> None:
    # a redundant, sizeable history should compress to a small fraction of raw json
    big = {
        f"2026-06-{day:02d}": {"m1": {f"glyph{n}": (n + day) % 6 for n in range(400)}}
        for day in range(1, 29)
    }
    encoded = store.encode_history(big)
    raw = json.dumps(big).encode("utf-8")
    assert len(encoded) < len(raw) // 5          # at least 5x smaller
    assert store.decode_history(encoded) == big


# --------------------------------------------------------------------------- #
# Delta encoding: only changed glyphs are stored per save (forward-fill on read).
# Must stay lossless across glyph/master additions AND removals.
# --------------------------------------------------------------------------- #

def _round_trip(history: dict) -> dict:
    return store.decode_history(store.encode_history(history))


def test_round_trips_when_glyph_added_between_saves() -> None:
    history = {
        "2026-06-01T10:00:00": {"m1": {"A": 0, "B": 1}},
        "2026-06-02T10:00:00": {"m1": {"A": 0, "B": 1, "C": 2}},  # C added
    }
    assert _round_trip(history) == history


def test_round_trips_when_glyph_removed_between_saves() -> None:
    history = {
        "2026-06-01T10:00:00": {"m1": {"A": 0, "B": 1, "C": 2}},
        "2026-06-02T10:00:00": {"m1": {"A": 0, "B": 1}},          # C deleted
    }
    assert _round_trip(history) == history


def test_round_trips_when_master_added_between_saves() -> None:
    history = {
        "2026-06-01T10:00:00": {"m1": {"A": 0}},
        "2026-06-02T10:00:00": {"m1": {"A": 1}, "m2": {"A": 3, "B": 4}},  # m2 added
    }
    assert _round_trip(history) == history


def test_round_trips_when_master_removed_between_saves() -> None:
    history = {
        "2026-06-01T10:00:00": {"m1": {"A": 0}, "m2": {"A": 3}},
        "2026-06-02T10:00:00": {"m1": {"A": 1}},                  # m2 deleted
    }
    assert _round_trip(history) == history


def test_round_trips_single_snapshot() -> None:
    history = {"2026-06-01T10:00:00": {"m1": {"A": 0, "B": -1}}}
    assert _round_trip(history) == history


def test_round_trips_unsorted_input_dates() -> None:
    # encode must order saves chronologically regardless of dict insertion order
    history = {
        "2026-06-03T10:00:00": {"m1": {"A": 2}},
        "2026-06-01T10:00:00": {"m1": {"A": 0}},
        "2026-06-02T10:00:00": {"m1": {"A": 1}},
    }
    assert _round_trip(history) == history


def test_decodes_legacy_v1_gzip_dense_blob() -> None:
    # fonts saved by older builds carry base64(gzip(json({"v":1,"h":history}))).
    # The new decoder must still read them so upgrading never drops history.
    history = {
        "2026-06-01": {"m1": {"A": 0, "B": -1}},
        "2026-06-02": {"m1": {"A": 2, "B": 0}},
    }
    raw = json.dumps({"v": 1, "h": history}, separators=(",", ":")).encode("utf-8")
    legacy_blob = base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii")
    assert store.decode_history(legacy_blob) == history


def test_new_encoding_prefers_xz_when_available() -> None:
    # the compressed payload should be xz (magic FD 37 7A 58 5A 00) where lzma is
    # importable, since xz is markedly smaller than gzip on this data.
    import importlib.util

    if importlib.util.find_spec("lzma") is None:  # pragma: no cover - platform dep
        return
    blob = base64.b64decode(store.encode_history(SAMPLE))
    assert blob[:6] == b"\xfd7zXZ\x00"


def test_delta_beats_dense_gzip_on_redundant_history() -> None:
    # the whole point: delta+xz must be much smaller than the old dense+gzip blob.
    big = {
        f"2026-06-{day:02d}T10:00:00": {
            "m1": {f"glyph{n}": (1 if n < day else 0) for n in range(800)}
        }
        for day in range(1, 41)
    }
    new_blob = store.encode_history(big)
    raw = json.dumps({"v": 1, "h": big}, separators=(",", ":")).encode("utf-8")
    dense_gzip = base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii")
    assert len(new_blob) < len(dense_gzip) // 2   # at least 2x smaller than the old codec
    assert store.decode_history(new_blob) == big
