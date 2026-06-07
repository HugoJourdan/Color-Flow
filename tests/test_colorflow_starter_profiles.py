"""Every bundled starter .colorflow must validate and round-trip."""

from __future__ import annotations

from pathlib import Path

import colorflow_profile as profile
import pytest

STARTER_DIR = (
    Path(__file__).resolve().parent.parent
    / "Color Flow.glyphsPalette"
    / "Contents"
    / "Resources"
    / "StarterProfiles"
)
STARTERS = sorted(STARTER_DIR.glob("*.colorflow"))


def test_three_starter_profiles_are_shipped() -> None:
    assert len(STARTERS) == 3


@pytest.mark.parametrize("path", STARTERS, ids=lambda path: path.name)
def test_starter_profile_parses_and_round_trips(path: Path) -> None:
    parsed = profile.parse(path.read_text(encoding="utf-8"))
    assert parsed["version"] == profile.PROFILE_VERSION
    assert parsed["name"]                                   # non-empty name
    assert parsed["colorNames"].strip()                    # has at least one step
    assert len(parsed["labelColors"]) == 12                # full Glyphs palette
    assert parsed["rainbowSource"] in profile.RAINBOW_SOURCES
    # Re-serialising a parsed profile and parsing again must be a fixed point.
    assert profile.parse(profile.serialize(parsed)) == parsed
