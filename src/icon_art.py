"""
Original icon artwork for ED MQTT Telemetry, drawn with Pillow so there are no
binary assets to keep in sync: the system-tray icon is rendered from this code
at runtime, and `make_icon.py` renders the same artwork into assets/icon.ico
for the .exe file icon.

Design: a HUD-style ring with a ship chevron on a dark rounded tile. The tray
variant adds a small status dot (grey / amber / green / red) in the corner.
"""

from PIL import Image, ImageDraw

BG = (11, 18, 32, 255)          # deep navy tile
RING = (255, 140, 26, 255)      # HUD orange
CHEVRON = (255, 190, 80, 255)   # lighter amber

_SUPERSAMPLE = 4                # draw large, then downscale for smooth edges


def _draw(size, status_color):
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.22), fill=BG)

    c = s / 2
    r = s * 0.36
    d.ellipse((c - r, c - r, c + r, c + r), outline=RING, width=int(s * 0.08))

    d.polygon(
        [
            (c, c - s * 0.24),
            (c + s * 0.18, c + s * 0.17),
            (c, c + s * 0.07),
            (c - s * 0.18, c + s * 0.17),
        ],
        fill=CHEVRON,
    )

    if status_color is not None:
        dot_c = s * 0.80
        dot_r = s * 0.15
        outline = s * 0.035
        d.ellipse(
            (dot_c - dot_r - outline, dot_c - dot_r - outline,
             dot_c + dot_r + outline, dot_c + dot_r + outline),
            fill=BG,
        )
        d.ellipse(
            (dot_c - dot_r, dot_c - dot_r, dot_c + dot_r, dot_c + dot_r),
            fill=status_color,
        )
    return img


def make_icon(size=64, status_color=None):
    """Return an RGBA PIL image of the icon at `size` px. Pass an (r, g, b, a)
    tuple as status_color to add the tray status dot; omit it for the plain
    application icon."""
    big = _draw(size * _SUPERSAMPLE, status_color)
    return big.resize((size, size), Image.LANCZOS)
