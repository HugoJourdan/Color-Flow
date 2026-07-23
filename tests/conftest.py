"""Put the plugin's ``Resources/`` directory on ``sys.path`` so the pure-logic
modules shipped inside the ``.glyphsPlugin`` bundle can be imported by tests.

The bundle directory name contains spaces; ``pathlib`` handles that fine.
"""

import sys
from pathlib import Path

RESOURCES = (
    Path(__file__).resolve().parent.parent
    / "AZ-Colorflow.glyphsPlugin"
    / "Contents"
    / "Resources"
)

sys.path.insert(0, str(RESOURCES))
