"""Backend dispatcher for the license gate.

Loads `license.dylib` if available (branch H), otherwise falls back to
the pure-Python `licensing.py` module (branch F). The plugin imports
this module and calls `entitlement()` etc. — branch is transparent.
"""

from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Literal

BackendName = Literal["dylib", "python", "uninitialised"]

_BACKEND: BackendName = "uninitialised"
_DYLIB: ctypes.CDLL | None = None
_PY_LICENSING = None  # reference to the imported licensing module on branch F

# Plugin sets these before first call (branch F only).
read_trial_payload = None
write_trial_payload = None
read_license_payload = None
write_license_payload = None
http_transport = None


def _dylib_path() -> Path:
    return Path(__file__).resolve().parent / "license.dylib"


def _reset_for_testing() -> None:
    global _BACKEND, _DYLIB, _PY_LICENSING
    _BACKEND = "uninitialised"
    _DYLIB = None
    _PY_LICENSING = None


def _load() -> BackendName:
    global _BACKEND, _DYLIB, _PY_LICENSING
    if _BACKEND != "uninitialised":
        return _BACKEND

    path = _dylib_path()
    try:
        lib = ctypes.CDLL(str(path))
    except OSError:
        lib = None
    if lib is not None:  # pragma: no cover - requires the compiled license.dylib
        lib.da_entitlement.restype = ctypes.c_int32
        lib.da_trial_days_remaining.restype = ctypes.c_int32
        lib.da_activate.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        lib.da_activate.restype = ctypes.c_int32
        lib.da_validate.restype = ctypes.c_int32
        lib.da_deactivate.restype = ctypes.c_int32
        _DYLIB = lib
        _BACKEND = "dylib"
        return _BACKEND

    from . import licensing

    _PY_LICENSING = licensing
    _BACKEND = "python"
    return _BACKEND


_ENTITLEMENT_INT = {
    "licensed": 0,
    "trial": 1,
    "trial_expired": 2,
    "unlicensed": 3,
}


def entitlement() -> int:
    backend = _load()
    if backend == "dylib":
        assert _DYLIB is not None
        return int(_DYLIB.da_entitlement())
    return _py_entitlement_int()


def trial_days_remaining() -> int:
    backend = _load()
    if backend == "dylib":
        assert _DYLIB is not None
        return int(_DYLIB.da_trial_days_remaining())
    return _py_trial_days_remaining()


def activate(license_key: str, instance_name: str) -> int:
    backend = _load()
    if backend == "dylib":
        assert _DYLIB is not None
        return int(
            _DYLIB.da_activate(
                license_key.encode("utf-8"),
                instance_name.encode("utf-8"),
            )
        )
    return _py_activate(license_key, instance_name)


def validate() -> int:
    backend = _load()
    if backend == "dylib":
        assert _DYLIB is not None
        return int(_DYLIB.da_validate())
    return _py_validate()


def deactivate() -> int:
    backend = _load()
    if backend == "dylib":
        assert _DYLIB is not None
        return int(_DYLIB.da_deactivate())
    return _py_deactivate()


def start_trial_if_needed() -> None:
    """Stamp the trial start-date if no trial / no license exists yet.

    Branch H: a single da_entitlement() call makes the dylib lazy-stamp
    its Keychain + HMAC mirror via startTrialIfNeeded. Branch F: stamp
    the Glyphs.defaults trial payload through the wired callbacks.
    """
    backend = _load()
    if backend == "dylib":
        assert _DYLIB is not None
        _DYLIB.da_entitlement()
        return

    # _load() above already set _PY_LICENSING on the "python" branch; guard
    # gracefully (matching the _py_* helpers) rather than asserting, so an
    # unwired callback can't raise inside a license check.
    if _PY_LICENSING is None or read_trial_payload is None or write_trial_payload is None:
        return
    if _PY_LICENSING.deserialize_trial(read_trial_payload()) is not None:
        return
    fresh = _PY_LICENSING.start_trial()
    write_trial_payload(_PY_LICENSING.serialize_trial(fresh))


# ---------- branch F (pure-Python) implementations ----------


def _py_entitlement_int() -> int:
    if _PY_LICENSING is None or read_trial_payload is None or read_license_payload is None:
        return 3
    trial = _PY_LICENSING.deserialize_trial(read_trial_payload())
    lic = _PY_LICENSING.deserialize_license(read_license_payload())
    ent = _PY_LICENSING.resolve_entitlement(lic, trial)
    return _ENTITLEMENT_INT[ent.kind]


def _py_trial_days_remaining() -> int:
    if _PY_LICENSING is None or read_trial_payload is None:
        return 0
    trial = _PY_LICENSING.deserialize_trial(read_trial_payload())
    if trial is None:
        return 0
    from datetime import UTC, datetime

    remaining = _PY_LICENSING.trial_remaining(trial, now=datetime.now(UTC))
    return -(-int(remaining.total_seconds()) // 86_400)


def _py_activate(license_key: str, instance_name: str) -> int:
    if _PY_LICENSING is None or http_transport is None or write_license_payload is None:
        return 100
    outcome = _PY_LICENSING.activate(license_key, instance_name, http=http_transport)
    if isinstance(outcome, _PY_LICENSING.ActivationSuccess):
        write_license_payload(_PY_LICENSING.serialize_license(outcome.state))
        return 0
    return max(outcome.http_status, 100)


def _py_validate() -> int:
    if _PY_LICENSING is None or http_transport is None or read_license_payload is None or write_license_payload is None:
        return 100
    state = _PY_LICENSING.deserialize_license(read_license_payload())
    if state is None:
        return 100
    outcome = _PY_LICENSING.validate(state, http=http_transport)
    if isinstance(outcome, _PY_LICENSING.ValidationSuccess):
        write_license_payload(_PY_LICENSING.serialize_license(outcome.state))
        return 0
    return max(outcome.http_status, 100)


def _py_deactivate() -> int:
    if _PY_LICENSING is None or http_transport is None or read_license_payload is None or write_license_payload is None:
        return 100
    state = _PY_LICENSING.deserialize_license(read_license_payload())
    if state is None:
        return 100
    outcome = _PY_LICENSING.deactivate(state, http=http_transport)
    if isinstance(outcome, _PY_LICENSING.DeactivationSuccess):
        write_license_payload(None)
        return 0
    return max(outcome.http_status, 100)
