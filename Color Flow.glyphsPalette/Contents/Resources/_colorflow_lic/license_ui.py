"""Shared license-entry window + session prompt. Glyphs-only; lazy imports."""
from __future__ import annotations

from typing import Any

_window: Any = None  # keep a reference so the window isn't GC'd


def show_window(config) -> None:
    global _window
    import vanilla
    from . import bootstrap

    w = vanilla.FloatingWindow((360, 150), f"{config.product} — License")
    w.info = vanilla.TextBox((15, 12, -15, 20), f"Activate {config.product}")
    w.key = vanilla.EditText((15, 42, -15, 22), placeholder="License key")
    def _activate(sender):
        code = bootstrap.activate(config, w.key.get())
        import vanilla as v
        msg = "Activated. Thank you!" if code == 0 else f"Activation failed (code {code})."
        v.dialogs.message(messageText=config.product, informativeText=msg)
        if code == 0:
            w.close()
    def _buy(sender):
        import webbrowser
        webbrowser.open(config.buy_url)
    w.activate = vanilla.Button((15, 78, 110, 22), "Activate", callback=_activate)
    w.buy = vanilla.Button((135, 78, 90, 22), "Buy…", callback=_buy)
    w.close_ = vanilla.Button((-95, 78, 80, 22), "Close", callback=lambda s: w.close())
    _window = w
    w.open()


def show_session_prompt(config) -> None:
    """One-shot 'trial expired' nudge that routes to the license window."""
    import vanilla
    result = vanilla.dialogs.askYesNo(
        messageText=f"{config.product} trial has ended",
        informativeText="Enter a license key to keep using it.",
    )
    if result == 1:
        show_window(config)
