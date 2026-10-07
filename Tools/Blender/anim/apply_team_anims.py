#!/usr/bin/env python3
"""Lleva los FBX de animación del equipo (build_team_anims.py --export) a Unity SIN correr el generador entero
(que reescribe assets de otras áreas): los .meta de TeamAnims/, los AnimatorControllers de ninja, sumo, Gorō y el
abuelo (Tools/Unity/generate_assets.py controllers(), mismos GUIDs) y, en NindoContent.asset, la tabla de
duraciones por estado de esos personajes (stateNames/stateLengths), que CharacterAnimator.Length usa para el reloj
de los golpes. Idempotente.

uso: python Tools/Blender/anim/apply_team_anims.py
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "Tools", "Unity"))
import generate_assets as GA   # noqa: E402

# los personajes de los que se ocupa este paso y el controller que usa cada fila de NindoContent
ROWS = {"ninja": "ninja", "sumo": "sumo", "goro": "goro", "grandpa": "grandpa", "kidnap": "grandpa"}


def main():
    GA.team_anim_metas()
    ctrls = GA.controllers()
    path = os.path.join(GA.P_RES, "NindoContent.asset")
    txt = open(path, encoding="utf-8").read()
    for cid, cc in ROWS.items():
        if cc not in ctrls:
            continue
        _, lens = ctrls[cc]
        names = "".join(f"\n    - {n}" for n in lens) or " []"
        secs = "".join(f"\n    - {lens[n]}" for n in lens) or " []"
        pat = re.compile(r"(  - id: " + cid + r"\n(?:    .*\n)*?    stateNames:)((?:\n    - .*)*| \[\])(\n    stateLengths:)((?:\n    - .*)*| \[\])")
        txt, k = pat.subn(lambda m: m.group(1) + names + m.group(3) + secs, txt, count=1)
        assert k == 1, f"no encontré la fila '{cid}' en NindoContent.asset"
    open(path, "w", encoding="utf-8", newline="\n").write(txt)
    print("NindoContent: duraciones de", ", ".join(ROWS))


if __name__ == "__main__":
    main()
