"""Makes a labelled contact sheet of prop previews (run with system python3 + Pillow).
usage: python3 contact_sheet.py out.png id1 id2 ...   (or 'all')"""
import sys, os, glob
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__))
prev = os.path.join(HERE, "out", "previews")
out = sys.argv[1]; ids = sys.argv[2:]
if ids == ["all"] or not ids:
    ids = sorted({os.path.basename(p).rsplit("_", 1)[0] for p in glob.glob(os.path.join(prev, "*_game.png"))})
tiles = []
for i in ids:
    row = []
    for v in ("game", "front34"):
        p = os.path.join(prev, f"{i}_{v}.png")
        if os.path.exists(p):
            im = Image.open(p).convert("RGB").resize((400, 300))
            ImageDraw.Draw(im).text((6, 6), f"{i} [{v}]", fill=(255, 255, 255))
            row.append(im)
    if row:
        tiles.append(row)
if not tiles:
    sys.exit("no previews")
cols = 2
W = 400 * cols * 2; per_row = 2
H = 300 * ((len(tiles) + per_row - 1) // per_row)
sheet = Image.new("RGB", (W, H), (15, 15, 18))
for k, row in enumerate(tiles):
    x0 = (k % per_row) * 800; y0 = (k // per_row) * 300
    for j, im in enumerate(row):
        sheet.paste(im, (x0 + j * 400, y0))
sheet.save(out)
print(out, sheet.size)
