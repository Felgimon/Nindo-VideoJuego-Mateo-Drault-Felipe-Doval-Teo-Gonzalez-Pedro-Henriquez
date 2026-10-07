"""Escribe SOLO lo de Kaito en Unity, sin correr el generador completo (que re-escribe assets de otros):
el .meta de kaitooo.fbx con los clips, Animation/Kaito.controller y las filas 'kaito' y 'kage' de
NindoContent.asset (los nombres y duraciones de los estados). Usa las mismas funciones que
Tools/Unity/generate_assets.py, así que el resultado es idéntico al del generador.

    python Tools/Blender/anim/kaito/unity_kaito.py
"""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "Tools", "Unity"))
import generate_assets as G  # noqa: E402

G.kaito_assets()
info = G.kaito_info()
assert info, "falta kaitooo.fbx.json (correr build_kaito.py --export)"
g = G.ensure_guid(G.KAITO_FBX)
st = {n: (G.ref(g, G.stable_id("kaito", n), 3), round(r["seconds"], 4), r.get("time_scale", 1)) for n, r in info["clips"].items()}
st.update({a: st[t] for a, t in G.KAITO_ALIASES.items() if t in st})
ths = [0] + [round(info["clips"][n]["timing"]["ground_speed_mps"] / G.KAITO_RUN_SPEED, 4) for n in G.KAITO_LOCO[1:]]
cg, lens = G.controller(os.path.join(G.P_ANIM, "Kaito.controller"), "Kaito", st, [st[n] for n in G.KAITO_LOCO], ths)

# filas de NindoContent: mismos bloques que content_asset().chars() para 'kaito' y 'kage' (el mismo controller)
path = os.path.join(G.P_RES, "NindoContent.asset")
text = open(path, encoding="utf-8").read()
names = "".join(f"\n    - {n}" for n in lens)
secs = "".join(f"\n    - {lens[n]}" for n in lens)
for cid in ("kaito", "kage"):
    pat = re.compile(r"(  - id: " + cid + r"\n(?:    .*\n)*?    stateNames:)(?:\n    - .*)*(\n    stateLengths:)(?:\n    - .*)*")
    text, n = pat.subn(lambda m: m.group(1) + names + m.group(2) + secs, text, count=1)
    assert n == 1, cid
with open(path, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(text)
print("Kaito.controller", cg, "estados", len(lens), "umbrales", ths)
