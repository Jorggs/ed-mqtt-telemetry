"""Render assets/icon.ico (the .exe file icon) from src/icon_art.py.

Run from the project root:  python make_icon.py
The committed assets/icon.ico is what PyInstaller embeds; re-run this only if
you change the artwork in src/icon_art.py.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from icon_art import make_icon  # noqa: E402

SIZES = [16, 24, 32, 48, 64, 128, 256]

os.makedirs("assets", exist_ok=True)
base = make_icon(256)
base.save("assets/icon.ico", format="ICO", sizes=[(s, s) for s in SIZES])
base.save("assets/icon.png")
print("wrote assets/icon.ico and assets/icon.png")
