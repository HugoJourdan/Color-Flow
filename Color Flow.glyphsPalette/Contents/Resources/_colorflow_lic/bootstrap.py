"""Reusable glue: turn a LicenseConfig into an entitlement Gate.

Two-call contract for plugins:
    self._ent = bootstrap.start(CONFIG)         # at start()/init
    if self._ent.blocked: return self._ent.nag()# at each feature gate
"""
from __future__ import annotations

import socket
import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional

from . import _licensing, licensing
from .transport import urllib_transport

_KIND_FROM_INT = {0: "licensed", 1: "trial", 2: "trial_expired", 3: "unlicensed"}


@dataclass(frozen=True)
class LicenseConfig:
    product: str
    defaults_prefix: str
    buy_url: str
    trial_days: int = 30
    grace_days: int = 30
    revalidate_days: int = 7
    # Phase 2 (hardening) only — ignored on Branch F:
    keychain_service: str = ""
    mirror_path: str = ""
    hmac_key: bytes = b""
    dylib_name: str = "license.dylib"


class _GlyphsDefaults:
    """Default store adapter; lazy-imports Glyphs so tests can inject a fake."""
    def get(self, key: str) -> Optional[str]:
        from GlyphsApp import Glyphs
        val = Glyphs.defaults[key]
        return str(val) if val is not None else None
    def set(self, key: str, value: Optional[str]) -> None:
        from GlyphsApp import Glyphs
        Glyphs.defaults[key] = value


class Gate:
    def __init__(self, kind: str, trial_days_remaining: int, config: LicenseConfig) -> None:
        self.kind = kind
        self.trial_days_remaining = trial_days_remaining
        self._config = config
        self._nagged = False

    @property
    def blocked(self) -> bool:
        return self.kind not in ("licensed", "trial")

    def nag(self) -> None:
        """Show the license prompt at most once per session; then no-op."""
        if self._nagged or not self.blocked:
            return None
        self._nagged = True
        try:
            from . import license_ui
            license_ui.show_session_prompt(self._config)
        except Exception:
            pass
        return None


def _wire(store: Any, prefix: str, transport: Callable) -> None:
    _licensing.read_trial_payload = lambda: store.get(prefix + ".trial")
    _licensing.write_trial_payload = lambda s: store.set(prefix + ".trial", s)
    _licensing.read_license_payload = lambda: store.get(prefix + ".license")
    _licensing.write_license_payload = lambda s: store.set(prefix + ".license", s)
    _licensing.http_transport = transport


def start(config: LicenseConfig, *, defaults: Any = None,
          transport: Callable = urllib_transport) -> Gate:
    store = defaults if defaults is not None else _GlyphsDefaults()
    prefix = config.defaults_prefix
    try:
        _wire(store, prefix, transport)
        _licensing.start_trial_if_needed()
        kind = _KIND_FROM_INT.get(_licensing.entitlement(), "unlicensed")
        days = _licensing.trial_days_remaining()
        _revalidate_async(store, prefix, config)
        return Gate(kind, days, config)
    except Exception:
        return _recover(store, prefix, config)  # bounded fail-safe, never mints a trial


def _recover(store: Any, prefix: str, config: LicenseConfig) -> Gate:
    try:
        lic = licensing.deserialize_license(store.get(prefix + ".license"))
        if licensing.is_license_active(lic, grace_days=config.grace_days):
            return Gate("licensed", 0, config)
    except Exception:
        pass
    return Gate("trial_expired", 0, config)


def _revalidate_async(store: Any, prefix: str, config: LicenseConfig) -> None:
    def _run() -> None:
        try:
            lic = licensing.deserialize_license(store.get(prefix + ".license"))
            if lic is not None and licensing.should_revalidate(
                lic, interval_days=config.revalidate_days
            ):
                _licensing.validate()
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def hostname() -> str:
    try:
        return socket.gethostname() or "glyphs"
    except Exception:
        return "glyphs"


def activate(config: LicenseConfig, key: str, *, defaults: Any = None,
             transport: Callable = urllib_transport) -> int:
    """Activate a license key. Returns 0 on success, >=100 on failure."""
    store = defaults if defaults is not None else _GlyphsDefaults()
    _wire(store, config.defaults_prefix, transport)
    return _licensing.activate(key.strip(), hostname())


def show_license_ui(config: LicenseConfig) -> None:
    from . import license_ui
    license_ui.show_window(config)
