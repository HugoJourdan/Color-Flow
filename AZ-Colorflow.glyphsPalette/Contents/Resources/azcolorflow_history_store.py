"""Compact, file-embeddable encoding of Color Flow's dated colour history.

The dated history — ``{iso_date: {master_id: {glyph_name: int}}}`` — is the
substrate for the report's timeline (burndown, journeys, Time Machine). To make it
travel *with* the font (so a shared file shows the same timeline on any machine,
with no git repo or sidecar) it is stored in the font's ``userData``.

Stored raw, that nested dict is large and very redundant: each save is a *dense*
snapshot of every glyph in every master, and most glyphs keep the same colour from
one save to the next. So this codec:

1. **Delta-encodes** the series — the first save is a full snapshot, each later save
   stores only the glyphs whose colour changed (plus explicit add/remove markers so
   it stays lossless when glyphs or masters are added/deleted between saves). On read
   the dense series is reconstructed by forward-filling.
2. **Compresses** the JSON with LZMA/xz (much smaller than gzip on this data),
   falling back to gzip where ``lzma`` is unavailable.
3. **base64**-wraps the result into a single ASCII string for ``userData``.

The delta step also shrinks the compressor's *input* ~25x on a big family, so saving
is faster, not just smaller. Decoding is backward-compatible: it reads both the new
delta payload (schema v2) and the legacy dense gzip payload (schema v1) written by
older builds, so upgrading never drops a font's history.

This module is pure (no Glyphs) so the codec is unit-tested in isolation.
"""

from __future__ import annotations

import base64
import gzip
import io
import json

try:  # liblzma ships on macOS; the Glyphs-bundled Python normally has _lzma.
    import lzma
except ImportError:  # pragma: no cover - platform without _lzma; fall back to gzip
    lzma = None  # type: ignore[assignment]

History = dict[str, dict[str, dict[str, int]]]

SCHEMA_VERSION = 1   # legacy dense payload {"v":1,"h":history} (still decoded)
DELTA_VERSION = 2    # current delta payload (see _to_delta)


class HistoryDecodeError(ValueError):
    """A history payload was *present* but could not be decoded.

    Deliberately distinct from empty/missing input (which decodes to ``{}``): a
    caller that gets ``{}`` back may safely write a fresh log, but on this error it
    must preserve the raw payload (e.g. stash it under a backup key) before any
    overwrite — otherwise one bad read silently destroys the font's timeline."""

_GZIP_MAGIC = b"\x1f\x8b"
_XZ_MAGIC = b"\xfd7zXZ\x00"


# --------------------------------------------------------------------------- #
# Compression (deterministic so re-encoding identical history yields identical
# bytes — avoids spuriously re-dirtying the font when nothing changed).
# --------------------------------------------------------------------------- #

def _gzip(data: bytes) -> bytes:
    """Deterministic gzip (mtime pinned to 0)."""
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as handle:
        handle.write(data)
    return buffer.getvalue()


def _compress(data: bytes) -> bytes:
    """xz (deterministic, no timestamp) when ``lzma`` is available, else gzip."""
    if lzma is not None:
        return lzma.compress(data, preset=6)
    return _gzip(data)


def _decompress(blob: bytes) -> bytes:
    """Inflate a payload produced by :func:`_compress` (or a legacy gzip blob),
    sniffing the magic bytes so old and new files both read."""
    if blob[:2] == _GZIP_MAGIC:
        return gzip.decompress(blob)
    if blob[:6] == _XZ_MAGIC:
        if lzma is None:  # pragma: no cover - xz blob on a python without _lzma
            raise ValueError("xz payload but lzma is unavailable")
        return lzma.decompress(blob)
    raise ValueError("unrecognised compression header")


# --------------------------------------------------------------------------- #
# Delta model: {"v":2, "dates":[iso...], "base":snapshot, "steps":{iso:step}}.
# ``base`` is the full snapshot at dates[0]. Each later date carries a ``step``:
#   "s":  {master: {glyph: key}}  changed-or-added glyphs (and whole new masters)
#   "d":  {master: [glyph, ...]}  glyphs removed from a surviving master
#   "dm": [master, ...]           masters removed entirely
# Empty members are omitted. Reconstruct by forward-filling base through the steps.
# --------------------------------------------------------------------------- #

def _to_delta(history: History) -> dict:
    dates = sorted(history)
    if not dates:
        return {"v": DELTA_VERSION, "dates": [], "base": {}, "steps": {}}
    base = {master: dict(glyphs) for master, glyphs in history[dates[0]].items()}
    steps: dict[str, dict] = {}
    previous = base
    for date in dates[1:]:
        current = history[date]
        changed: dict[str, dict[str, int]] = {}
        removed: dict[str, list[str]] = {}
        for master, glyphs in current.items():
            prev_glyphs = previous.get(master)
            if prev_glyphs is None:                      # whole new master
                changed[master] = dict(glyphs)
                continue
            master_changed = {
                name: key for name, key in glyphs.items() if prev_glyphs.get(name) != key
            }
            if master_changed:
                changed[master] = master_changed
            gone = [name for name in prev_glyphs if name not in glyphs]
            if gone:
                removed[master] = sorted(gone)
        dropped_masters = sorted(m for m in previous if m not in current)
        step: dict = {}
        if changed:
            step["s"] = changed
        if removed:
            step["d"] = removed
        if dropped_masters:
            step["dm"] = dropped_masters
        steps[date] = step
        previous = {master: dict(glyphs) for master, glyphs in current.items()}
    return {"v": DELTA_VERSION, "dates": dates, "base": base, "steps": steps}


def _from_delta(model: dict) -> History:
    dates = model.get("dates")
    if not isinstance(dates, list) or not dates:
        return {}
    state: dict[str, dict[str, int]] = {}
    base = model.get("base")
    if isinstance(base, dict):
        for master, glyphs in base.items():
            if isinstance(glyphs, dict):
                state[str(master)] = {str(n): int(k) for n, k in glyphs.items()}
    out: History = {str(dates[0]): {m: dict(g) for m, g in state.items()}}
    steps = model.get("steps")
    steps = steps if isinstance(steps, dict) else {}
    for date in dates[1:]:
        step = steps.get(date)
        step = step if isinstance(step, dict) else {}
        for master in step.get("dm", []) or []:
            state.pop(str(master), None)
        for master, glyphs in (step.get("s") or {}).items():
            if isinstance(glyphs, dict):
                target = state.setdefault(str(master), {})
                for name, key in glyphs.items():
                    target[str(name)] = int(key)
        for master, names in (step.get("d") or {}).items():
            target = state.get(str(master))
            if target is not None:
                for name in names:
                    target.pop(str(name), None)
        out[str(date)] = {m: dict(g) for m, g in state.items()}
    return out


# --------------------------------------------------------------------------- #
# Public codec
# --------------------------------------------------------------------------- #

def encode_history(history: History) -> str:
    """Encode ``history`` to a compact base64(xz(json(delta))) string for ``userData``."""
    raw = json.dumps(
        _to_delta(history), separators=(",", ":"), ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    return base64.b64encode(_compress(raw)).decode("ascii")


def decode_history(text: object) -> History:
    """Decode a string produced by :func:`encode_history` back to the history dict.

    Reads both the current delta payload (schema v2) and the legacy dense gzip payload
    (schema v1) written by older builds. Returns ``{}`` for empty/missing input, and
    coerces every value to plain ``str``/``int`` so a value read back from ``userData``
    (which may be an ``NSString``/``NSDictionary``) behaves like a normal Python dict.

    Raises :class:`HistoryDecodeError` when a payload is present but undecodable
    (garbage base64, wrong compression, malformed JSON, unknown schema) — so callers
    can tell "no data" from "data I must not clobber"."""
    if not text:
        return {}
    try:
        blob = base64.b64decode(str(text))
        decoded = json.loads(_decompress(blob).decode("utf-8"))
    except Exception as error:
        raise HistoryDecodeError(f"undecodable history payload: {error}") from error
    if not isinstance(decoded, dict):
        raise HistoryDecodeError("history payload is not a mapping")
    version = decoded.get("v")
    if version == DELTA_VERSION:
        try:
            return _from_delta(decoded)
        except Exception as error:
            raise HistoryDecodeError(f"malformed delta payload: {error}") from error
    if version == SCHEMA_VERSION:
        return _coerce_dense(decoded.get("h"))
    raise HistoryDecodeError(f"unknown history schema version: {version!r}")


def _coerce_dense(history: object) -> History:
    """Coerce a legacy (v1) dense ``{date:{master:{glyph:int}}}`` to plain types."""
    if not isinstance(history, dict):
        return {}
    out: History = {}
    for date, masters in history.items():
        if not isinstance(masters, dict):
            continue
        per_master: dict[str, dict[str, int]] = {}
        for master_id, glyphs in masters.items():
            if not isinstance(glyphs, dict):
                continue
            try:
                per_master[str(master_id)] = {str(name): int(key) for name, key in glyphs.items()}
            except (TypeError, ValueError):
                continue
        out[str(date)] = per_master
    return out
