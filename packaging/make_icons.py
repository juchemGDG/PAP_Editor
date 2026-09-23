"""Erzeugt alle Icon-Dateien aus assets/icon.svg.

    python3 packaging/make_icons.py

Benötigt cairosvg und Pillow (pip install cairosvg pillow), für die .icns
zusätzlich macOS (iconutil). Die Ergebnisse liegen im Repository, der
CI-Build braucht dieses Skript also nicht.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

import cairosvg
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
STATIC = os.path.join(ROOT, "web", "static")
SVG = os.path.join(ASSETS, "icon.svg")


def render(svg: bytes, size: int) -> Image.Image:
    png = cairosvg.svg2png(bytestring=svg, output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def main() -> None:
    svg = open(SVG, "rb").read()
    # Browser-Tab: ohne den App-Icon-Rand, damit das Symbol bei 16 px groß bleibt
    tab_svg = re.sub(rb'viewBox="[^"]*"', b'viewBox="96 96 832 832"', svg, count=1)

    # Desktop: Fenster-/Taskleisten-Icon (Tk) und Windows-.ico
    render(svg, 512).save(os.path.join(ASSETS, "icon.png"))
    render(svg, 256).save(os.path.join(ASSETS, "icon.ico"),
                          sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    # macOS-.icns über iconutil
    if sys.platform == "darwin" and shutil.which("iconutil"):
        with tempfile.TemporaryDirectory() as tmp:
            iconset = os.path.join(tmp, "icon.iconset")
            os.mkdir(iconset)
            for size in (16, 32, 128, 256, 512):
                render(svg, size).save(os.path.join(iconset, f"icon_{size}x{size}.png"))
                render(svg, size * 2).save(os.path.join(iconset, f"icon_{size}x{size}@2x.png"))
            subprocess.run(["iconutil", "-c", "icns", iconset, "-o", os.path.join(ASSETS, "icon.icns")], check=True)
    else:
        print("Hinweis: icon.icns nur unter macOS erzeugbar – übersprungen")

    # Web: SVG-Favicon, PNG-Fallback und Icon für den iOS-Homescreen
    with open(os.path.join(STATIC, "favicon.svg"), "wb") as f:
        f.write(tab_svg)
    render(tab_svg, 32).save(os.path.join(STATIC, "favicon-32.png"))
    touch = Image.new("RGBA", (180, 180), "#F07A2B")     # iOS mag keine Transparenz
    touch.alpha_composite(render(tab_svg, 180))
    touch.convert("RGB").save(os.path.join(STATIC, "apple-touch-icon.png"))
    print("Icons erzeugt.")


if __name__ == "__main__":
    main()
