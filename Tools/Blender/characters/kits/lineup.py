"""Hojas de comparación de los kits (Python 3 + PIL, sin Blender).

    python Tools/Blender/characters/kits/lineup.py DIR

DIR es la carpeta de --preview de build_kits.py (usa DIR/_tmp/<kit>_cell.png y <kit>_p0.png). Escribe:
  lineup_ninjas.png  base, jardín, montaña, lago, bambú y abajo los élites de cada zona (x2)
  lineup_sumos.png   base, jardín, montaña, lago, bambú y abajo el Ōzeki al lado del sumo base (x1: la densidad
                     del juego tal cual; el sumo ya ocupa el doble que un ninja)
  close_ninjas.png / close_sumos.png  los mismos en Idle de cerca
Las celdas "game" son la cámara del juego a la densidad de 1080p (x2 sin filtrar para mirarlas): si una zona
no se distingue acá, no se distingue jugando.
"""
import os, sys
from PIL import Image, ImageDraw

NINJAS = [["ninja_base", "ninja_default", "ninja_mountain", "ninja_lake", "ninja_bamboo"],
          [None, "ninja_elite", "ninja_mountain_elite", "ninja_lake_elite", "ninja_bamboo_elite"]]
SUMOS = [["sumo_base", "sumo_default", "sumo_mountain", "sumo_lake", "sumo_bamboo"],
         ["sumo_base", "ozeki"]]
BG = (12, 16, 26)


def grid(rows, tmp, suffix, scale, cell=None):
    imgs = [[Image.open(os.path.join(tmp, f"{n}_{suffix}.png")).convert("RGB") if n else None for n in r] for r in rows]
    w0, h0 = cell or next(i.size for r in imgs for i in r if i)
    w, h = int(w0 * scale), int(h0 * scale)
    cols = max(len(r) for r in rows)
    out = Image.new("RGB", (w * cols, h * len(rows)), BG)
    for y, r in enumerate(imgs):
        for x, im in enumerate(r):
            if im is None:
                continue
            im = im.resize((w, h), Image.NEAREST if scale >= 1 else Image.LANCZOS)
            out.paste(im, (x * w, y * h))
    d = ImageDraw.Draw(out)
    for x in range(1, cols):
        d.line([(x * w, 0), (x * w, out.height)], fill=(40, 46, 60))
    return out


def main():
    root = sys.argv[1]
    tmp = os.path.join(root, "_tmp")
    for name, rows, scale in (("ninjas", NINJAS, 2), ("sumos", SUMOS, 1)):
        grid(rows, tmp, "cell", scale).save(os.path.join(root, f"lineup_{name}.png"))
        grid(rows, tmp, "p0", 0.6).save(os.path.join(root, f"close_{name}.png"))
        print("ok", name)


if __name__ == "__main__":
    main()
