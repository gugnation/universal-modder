"""Draws assets/icon.ico: a cel-shaded yellow loot cog with a hazard-stripe core.
Run: uv run --with pillow python assets/make_icon.py"""
import math
from pathlib import Path
from PIL import Image, ImageDraw

S = 1024
YELLOW, ORANGE, BLACK, DARK = (255, 196, 14), (255, 138, 0), (0, 0, 0), (34, 39, 49)


def cog(cx, cy, r_out, r_in, teeth, tooth_frac=0.42, rot=0.0):
    pts = []
    step = 2 * math.pi / teeth
    for i in range(teeth):
        a = rot + i * step
        half = step * tooth_frac / 2
        for ang, rad in ((a - step / 2 + 0.06, r_in), (a - half, r_in), (a - half * 0.8, r_out), (a + half * 0.8, r_out), (a + half, r_in)):
            pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    return pts


img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
c = S / 2
# drop shadow, black outline, then yellow face (cel-shaded look)
d.polygon(cog(c + 30, c + 34, 470, 380, 10, rot=0.1), fill=BLACK)
d.polygon(cog(c, c, 480, 390, 10, rot=0.1), fill=BLACK)
d.polygon(cog(c, c, 440, 352, 10, rot=0.1), fill=YELLOW)
# lower half shade
shade = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(shade).polygon(cog(c, c, 440, 352, 10, rot=0.1), fill=ORANGE)
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).polygon([(0, c + 120), (S, c - 40), (S, S), (0, S)], fill=255)
img.paste(shade, (0, 0), Image.composite(mask, Image.new("L", (S, S), 0), shade.getchannel("A")))
d = ImageDraw.Draw(img)
# hub: black ring, dark core with hazard stripes, black ring again
d.ellipse([c - 250, c - 250, c + 250, c + 250], fill=BLACK)
core = Image.new("RGBA", (S, S), DARK + (255,))
cd = ImageDraw.Draw(core)
for x in range(-S, 2 * S, 120):
    cd.polygon([(x, 0), (x + 60, 0), (x + 60 - S, S), (x - S, S)], fill=YELLOW)
cmask = Image.new("L", (S, S), 0)
ImageDraw.Draw(cmask).ellipse([c - 205, c - 205, c + 205, c + 205], fill=255)
img.paste(core, (0, 0), cmask)
d = ImageDraw.Draw(img)
# center bolt
d.ellipse([c - 95, c - 95, c + 95, c + 95], fill=BLACK)
d.ellipse([c - 62, c - 62, c + 62, c + 62], fill=ORANGE)
d.ellipse([c - 62, c - 62, c + 30, c + 30], fill=YELLOW)
d.ellipse([c - 62, c - 62, c + 62, c + 62], outline=BLACK, width=10)

out = Path(__file__).with_name("icon.ico")
big = img.resize((256, 256), Image.LANCZOS)
big.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
big.save(Path(__file__).with_name("icon-preview.png"))
print("wrote", out)
