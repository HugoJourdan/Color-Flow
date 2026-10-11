"""Hugo Jourdan plugin-suite capability registry (shared, vendored).

Vendored byte-identical into each Python-running Glyphs plugin's Resources/.
Glyphs runs every plugin in ONE interpreter with ONE sys.path, so the first
plugin to `import _hj_suite` defines the module and every later import shares
that SAME object -> one process-wide REGISTRY (first-import-wins).

DEGRADATION GUARANTEE (load-bearing): best-effort enhancement ONLY.
  * No plugin may hard-require another via the registry.
  * Every lookup() that returns None MUST have a working standalone fallback.
  * The API is additive-only; consumers gate new capabilities with
    available(name, min_version=N). Under version skew the worst case is a new
    synergy staying dark until all plugins update -- never a downgrade.

Owned by the glyphs-licensing repo; do not hand-edit vendored copies. Edit
glyphs_licensing/runtime/_hj_suite.py and re-run `python setup.py vendor-suite all`.
"""

from __future__ import annotations

import contextlib

__version__ = 2

try:
    import objc
except Exception:  # pragma: no cover - objc only exists inside Glyphs
    objc = None

# Capability name -> ObjC class name, for COMPILED providers (e.g. Caliper)
# that cannot run Python to self-register. Resolved lazily via objc.lookUpClass.
_BUILTIN_OBJC = {
    "measurement.pipeline": "AZMeasurementPipeline",
    "measurement.drawing": "AZDrawing",
}

# Shared advisory-lock key. Identical to the sentinel shipped in the 2026-06-14
# fixes so a not-yet-migrated Argus/DA still interoperates.
_ANCHOR_LOCK_KEY = "com.hugojourdan.suite.proportionFixInProgress"
# One-shot "a fix just completed -> recompute linked anchors against the new
# geometry" signal, raised by end() and consumed exactly once by the reverter.
_ANCHOR_RECOMPUTE_KEY = "com.hugojourdan.suite.proportionFixRecomputePending"


class _AnchorLock:
    """Per-font advisory lock backed by font.tempData (in-memory, not saved).

    A writer (Argus, mid anchor-fix) calls begin()/end(); a reverter (DA) skips
    its auto-revert while active(). On end() a one-shot "recompute pending"
    signal is raised: the next consume_recompute(font) returns True exactly once,
    telling the reverter (DA) to re-derive the linked anchors from the now-fixed
    geometry this pass, instead of preserving the fix's anchor write as a manual
    edit. Robust to a fast begin->end that straddles no interface tick. Best-
    effort and null-safe.
    """

    def begin(self, font: object) -> None:
        self._set(_ANCHOR_LOCK_KEY, font, True)

    def end(self, font: object) -> None:
        self._set(_ANCHOR_LOCK_KEY, font, False)
        self._set(_ANCHOR_RECOMPUTE_KEY, font, True)

    def active(self, font: object) -> bool:
        return self._get(_ANCHOR_LOCK_KEY, font)

    def consume_recompute(self, font: object) -> bool:
        """True exactly once after each end(): a fix just finished, so the
        reverter should recompute linked anchors from geometry this pass."""
        if not self._get(_ANCHOR_RECOMPUTE_KEY, font):
            return False
        self._set(_ANCHOR_RECOMPUTE_KEY, font, False)
        return True

    def _get(self, key: str, font: object) -> bool:
        if font is None:
            return False
        try:
            return bool(font.tempData[key])  # type: ignore[union-attr]
        except Exception:
            return False

    def _set(self, key: str, font: object, value: bool) -> None:
        if font is None:
            return
        with contextlib.suppress(Exception):
            font.tempData[key] = bool(value)  # type: ignore[union-attr]


class _Registry:
    """Process-wide capability registry. See module docstring."""

    def __init__(self) -> None:
        self._explicit: dict[str, tuple[int, str | None, object]] = {}
        self._resolved: dict[str, tuple[int, object]] = {}
        self._anchor_lock = _AnchorLock()

    def register(
        self,
        name: str,
        thunk: object,
        *,
        version: int = 1,
        plugin_id: str | None = None,
    ) -> None:
        """Publish a capability. `thunk` is a zero-arg callable returning the
        capability object (use `lambda: obj` for a plain object). Higher version
        wins; lower/equal is ignored."""
        prev = self._explicit.get(name)
        if prev is not None and prev[0] >= version:
            return
        self._explicit[name] = (version, plugin_id, thunk)
        self._resolved.pop(name, None)

    def lookup(self, name: str, *, min_version: int = 1) -> object:
        """Return the capability object, or None if absent / version too low.
        Late-bound: re-resolves until it succeeds, then caches."""
        cached = self._resolved.get(name)
        if cached is not None and cached[0] >= min_version:
            return cached[1]
        reg = self._explicit.get(name)
        if reg is not None:
            version, _pid, thunk = reg
            if version < min_version:
                return None
            try:
                obj = thunk()  # type: ignore[operator]
            except Exception:
                obj = None
            if obj is not None:
                self._resolved[name] = (version, obj)
            return obj
        if name == "anchor.lock":
            return self._anchor_lock if __version__ >= min_version else None
        classname = _BUILTIN_OBJC.get(name)
        if classname is not None and __version__ >= min_version and objc is not None:
            try:
                cls = objc.lookUpClass(classname)
            except Exception:
                cls = None
            if cls is not None:
                self._resolved[name] = (__version__, cls)
            return cls
        return None

    def available(self, name: str, *, min_version: int = 1) -> bool:
        return self.lookup(name, min_version=min_version) is not None

    def capabilities(self) -> list[tuple[str, int, str | None]]:
        """[(name, version, plugin_id)] for introspection / a debug menu."""
        out: list[tuple[str, int, str | None]] = [
            (n, v, pid) for n, (v, pid, _t) in self._explicit.items()
        ]
        out.append(("anchor.lock", __version__, "_hj_suite"))
        for n in _BUILTIN_OBJC:
            out.append((n, __version__, "_hj_suite:objc"))
        return out


REGISTRY = _Registry()
