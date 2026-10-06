"""Lector mínimo de FBX binario y chequeo de re-exportación de los personajes del equipo.

Corre con el Python del sistema (sin Blender). Compara el FBX original con el re-exportado en
lo que Unity usa para no romper prefabs, clips ni controllers:
  - nombres de todos los nodos Model (huesos, mallas, Armature): ninguno puede faltar
  - transform local de cada nodo (la pose por defecto del prefab que arma Unity) y bind pose de cada
    nodo (rotación <= 0.01°, traslación <= 0.005 u del archivo)
  - tomas de animación: mismos nombres y mismo rango de tiempo (los .meta usan firstFrame/lastFrame)
  - fps del archivo (Unity mide los frames del .meta con él)
  - qué curvas de cada toma se mueven de verdad, leídas del archivo sin Blender: una toma horneada
    congelada conserva nombre y rango pero pierde todas sus curvas móviles
y avisa si quedaron texturas embebidas (el sumo pesaba 100 MB por dos PNG/JPG 4K empaquetados).

python fbxcheck.py <original.fbx> <nuevo.fbx> [--rot-tol 0.01] [--sin-tomas]   -> exit 1 si algo no cumple
python fbxcheck.py --info <archivo.fbx>
Las tomas de objetos sueltos ('Isan|Atack1', 'Katana|Block': armas pegadas a huesos, 1 frame, nada las usa)
se aceptan como descartadas: el importador de Blender no las lee (ver charlib.weapon_takes).
"""
import struct, sys, zlib, math

KTIME = 46186158000  # unidades de tiempo FBX por segundo
TIME_MODES = {1: 120, 2: 100, 3: 60, 4: 50, 5: 48, 6: 30, 7: 30, 8: 29.97, 9: 29.97, 10: 25, 11: 24,
              12: 1000, 13: 23.976, 15: 96, 16: 72, 17: 59.94, 18: 119.88}


class Node:
    __slots__ = ("id", "props", "elems")

    def __init__(self, id_, props, elems):
        self.id, self.props, self.elems = id_, props, elems

    def find(self, name):
        return [e for e in self.elems if e.id == name]


def parse(path):
    data = open(path, "rb").read()
    if not data.startswith(b"Kaydara FBX Binary"):
        raise ValueError(f"{path}: no es FBX binario")
    ver = struct.unpack_from("<I", data, 23)[0]
    wide = ver >= 7500
    hdr = 25 if wide else 13

    def read_props(off, n):
        out = []
        for _ in range(n):
            t = data[off:off + 1]; off += 1
            if t == b"Y": out.append(struct.unpack_from("<h", data, off)[0]); off += 2
            elif t == b"C": out.append(data[off] != 0); off += 1
            elif t == b"I": out.append(struct.unpack_from("<i", data, off)[0]); off += 4
            elif t == b"F": out.append(struct.unpack_from("<f", data, off)[0]); off += 4
            elif t == b"D": out.append(struct.unpack_from("<d", data, off)[0]); off += 8
            elif t == b"L": out.append(struct.unpack_from("<q", data, off)[0]); off += 8
            elif t in (b"S", b"R"):
                ln = struct.unpack_from("<I", data, off)[0]; off += 4
                out.append(bytes(data[off:off + ln])); off += ln
            elif t in (b"f", b"d", b"l", b"i", b"b"):
                cnt, enc, clen = struct.unpack_from("<III", data, off); off += 12
                raw = data[off:off + clen]; off += clen
                if enc == 1: raw = zlib.decompress(raw)
                fmt = {b"f": "f", b"d": "d", b"l": "q", b"i": "i", b"b": "?"}[t]
                out.append(struct.unpack("<%d%s" % (cnt, fmt), raw))
            else:
                raise ValueError(f"tipo de propiedad FBX desconocido {t!r} en {off}")
        return out

    def read_node(off):
        if wide: end, nprops, plen = struct.unpack_from("<QQQ", data, off); off += 24
        else: end, nprops, plen = struct.unpack_from("<III", data, off); off += 12
        nlen = data[off]; off += 1
        if end == 0: return None, off
        name = bytes(data[off:off + nlen]); off += nlen
        props = read_props(off, nprops); off += plen
        elems = []
        # los hijos terminan en un registro nulo (hdr bytes en cero) justo antes de 'end'
        while off < end and not (end - off == hdr and not any(data[off:end])):
            child, off = read_node(off)
            if child is None: break
            elems.append(child)
        return Node(name, props, elems), end

    off = 27; top = []
    while off < len(data) - hdr:
        n, off2 = read_node(off)
        if n is None: break
        top.append(n); off = off2
    return Node(b"", [], top), ver


def props70(node):
    d = {}
    for s in node.find(b"Properties70"):
        for p in s.elems:
            d[p.props[0].decode("utf-8", "replace")] = p.props[4:]
    return d


def obj_name(n):
    return n.props[1].split(b"\x00\x01")[0].decode("utf-8", "replace")


# cuánto tiene que variar una curva para contar como movimiento: 0.01° de giro, 0.001 u de traslación y
# 0.5 % de escala (los targets de IK del abuelo traen ruido de escala de 0.1-0.3 % que nada usa)
MOVES = {"Lcl Rotation": 0.01, "Lcl Translation": 1e-3, "Lcl Scaling": 5e-3}


def motion(root):
    """{toma: {(nodo, propiedad, eje)}} de las curvas que cambian de valor en esa toma.
    Toma -> capas -> nodos de curva (OP a un Model: 'Lcl Rotation'...) -> curvas (OP 'd|X')."""
    objs = {}; up = {}; down = {}
    for e in root.elems:
        if e.id == b"Objects":
            objs = {o.props[0]: o for o in e.elems if o.props}
        elif e.id == b"Connections":
            for c in e.elems:
                kid, par = c.props[1], c.props[2]
                prop = c.props[3].decode("utf-8", "replace") if len(c.props) > 3 else None
                down.setdefault(par, []).append((kid, prop)); up.setdefault(kid, []).append((par, prop))
    kind = lambda i, k: i in objs and objs[i].id == k
    out = {}
    for sid, st in objs.items():
        if st.id != b"AnimationStack": continue
        moving = set()
        for lid, _ in down.get(sid, ()):
            if not kind(lid, b"AnimationLayer"): continue
            for cn, _ in down.get(lid, ()):
                if not kind(cn, b"AnimationCurveNode"): continue
                tgt = [(obj_name(objs[m]), prop) for m, prop in up.get(cn, ()) if kind(m, b"Model")]
                for cid, axis in down.get(cn, ()):
                    if not kind(cid, b"AnimationCurve"): continue
                    kv = next((x.props[0] for x in objs[cid].elems if x.id == b"KeyValueFloat"), ())
                    if not kv: continue
                    moving.update((n, prop, axis) for n, prop in tgt if max(kv) - min(kv) > MOVES.get(prop, 1e-3))
        out[obj_name(st)] = moving
    return out


def summary(path):
    root, ver = parse(path)
    out = {"version": ver, "models": {}, "local": {}, "bind": {}, "stacks": {}, "videos": 0, "video_bytes": 0, "fps": None,
           "motion": motion(root)}
    for e in root.elems:
        if e.id == b"GlobalSettings":
            g = props70(e)
            mode = g.get("TimeMode", [None])[0]
            out["fps"] = TIME_MODES.get(mode) or (g.get("CustomFrameRate", [30.0])[0])
            out["unit"] = g.get("UnitScaleFactor", [1.0])[0]
        if e.id != b"Objects": continue
        ids = {}
        for o in e.elems:
            if o.id == b"Model":
                ids[o.props[0]] = obj_name(o)
                out["models"][obj_name(o)] = o.props[2].decode()
                out["local"][obj_name(o)] = _local(props70(o))
            elif o.id == b"AnimationStack":
                p = props70(o)
                out["stacks"][obj_name(o)] = tuple(p.get(k, [0])[0] / KTIME for k in ("LocalStart", "LocalStop"))
            elif o.id == b"Video":
                out["videos"] += 1
                for c in o.find(b"Content"):
                    if c.props and isinstance(c.props[0], bytes): out["video_bytes"] += len(c.props[0])
        for o in e.elems:
            if o.id != b"Pose": continue
            for pn in o.find(b"PoseNode"):
                nid = next((x.props[0] for x in pn.elems if x.id == b"Node"), None)
                mat = next((x.props[0] for x in pn.elems if x.id == b"Matrix"), None)
                if nid in ids and mat: out["bind"][ids[nid]] = mat
    return out


def _mul3(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _euler(x, y, z):
    """Matriz 3x3 de una rotación FBX en grados (orden XYZ: primero X)."""
    cx, sx = math.cos(math.radians(x)), math.sin(math.radians(x))
    cy, sy = math.cos(math.radians(y)), math.sin(math.radians(y))
    cz, sz = math.cos(math.radians(z)), math.sin(math.radians(z))
    rx = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
    ry = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
    rz = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]
    return _mul3(rz, _mul3(ry, rx))


def _local(p):
    """Rotación local (Pre * Lcl * Post^-1, como la arma Unity) y traslación de un nodo Model."""
    pre = _euler(*p.get("PreRotation", (0, 0, 0)))
    lcl = _euler(*p.get("Lcl Rotation", (0, 0, 0)))
    post = _euler(*p.get("PostRotation", (0, 0, 0)))
    post_t = [[post[j][i] for j in range(3)] for i in range(3)]
    r = _mul3(pre, _mul3(lcl, post_t))
    return r, tuple(p.get("Lcl Translation", (0, 0, 0))), tuple(p.get("Lcl Scaling", (1, 1, 1)))


def _rot3_angle(a, b):
    tr = sum(a[i][k] * b[i][k] for i in range(3) for k in range(3))
    return math.degrees(math.acos(max(-1.0, min(1.0, (tr - 1) / 2))))


def _rot_angle(a, b):
    """Ángulo (°) entre las partes de rotación de dos matrices 4x4 FBX (fila mayor, escala quitada)."""
    def rot3(m):
        r = [[m[i * 4 + j] for j in range(3)] for i in range(3)]
        for i in range(3):
            s = math.sqrt(sum(x * x for x in r[i])) or 1.0
            r[i] = [x / s for x in r[i]]
        return r
    ra, rb = rot3(a), rot3(b)
    # traza de Ra * Rb^T
    tr = sum(ra[i][k] * rb[i][k] for i in range(3) for k in range(3))
    return math.degrees(math.acos(max(-1.0, min(1.0, (tr - 1) / 2))))


def compare(src, dst, rot_tol=0.01, pos_tol=0.005, dropped_takes=()):
    """dropped_takes: tomas que el script descartó a propósito (acciones sueltas de armas que nada usa)."""
    A, B = summary(src), summary(dst)
    ok = True
    missing = [n for n in A["models"] if n not in B["models"]]
    extra = [n for n in B["models"] if n not in A["models"]]
    print(f"nodos: original {len(A['models'])}, nuevo {len(B['models'])}")
    if missing: ok = False; print("  FALTAN:", missing)
    if extra: print("  nuevos:", extra)
    worst = (0.0, 0.0, "")
    for n, ma in A["bind"].items():
        mb = B["bind"].get(n)
        if mb is None:
            if n in B["models"]: ok = False; print("  sin bind pose en el nuevo:", n)
            continue
        ang = _rot_angle(ma, mb)
        dt = math.dist(ma[12:15], mb[12:15])
        if (ang, dt) > worst[:2]: worst = (ang, dt, n)
        if ang > rot_tol or dt > pos_tol:
            ok = False; print(f"  bind distinto {n}: {ang:.4f}° {dt:.5f}")
    print(f"bind pose: {len(A['bind'])} nodos, peor {worst[0]:.5f}° / {worst[1]:.6f} ({worst[2]})")
    worst = (0.0, 0.0, "")
    for n, (ra, ta, sa) in A["local"].items():
        if n not in B["local"]: continue
        rb, tb, sb = B["local"][n]
        ang, dt = _rot3_angle(ra, rb), math.dist(ta, tb)
        ds = max(abs(x - y) for x, y in zip(sa, sb))
        if (ang, dt) > worst[:2]: worst = (ang, dt, n)
        if ang > rot_tol or dt > pos_tol or ds > 5e-3:
            ok = False; print(f"  transform local distinto {n}: {ang:.4f}° {dt:.5f} escala {sa} -> {sb}")
    print(f"transform local: {len(A['local'])} nodos, peor {worst[0]:.5f}° / {worst[1]:.6f} ({worst[2]})")
    if A["fps"] != B["fps"]: ok = False; print("  FPS distinto:", A["fps"], B["fps"])
    for s, (a0, a1) in A["stacks"].items():
        if s not in B["stacks"]:
            if s in dropped_takes: print("  toma descartada a propósito:", s)
            else: ok = False; print("  falta la toma", s)
            continue
        b0, b1 = B["stacks"][s]
        fa, fb = (round(a0 * A["fps"], 2), round(a1 * A["fps"], 2)), (round(b0 * B["fps"], 2), round(b1 * B["fps"], 2))
        if fa != fb: ok = False; print(f"  toma {s}: frames {fa} -> {fb}")
        # mismas curvas móviles en los mismos nodos: lo que no se movía puede quedar horneado constante
        ma, mb = A["motion"].get(s, set()), B["motion"].get(s, set())
        if ma != mb:
            ok = False
            print(f"  toma {s}: curvas que se mueven {len(ma)} -> {len(mb)}; quietas en el nuevo "
                  f"{sorted(ma - mb)[:4]}, nuevas {sorted(mb - ma)[:4]}")
    print(f"tomas: {len(A['stacks'])} -> {len(B['stacks'])}; fps {A['fps']} -> {B['fps']}; curvas móviles por toma "
          + ", ".join(f"{s.split('|')[-1]} {len(B['motion'].get(s, ()))}" for s in A["stacks"] if s in B["stacks"]))
    print(f"texturas embebidas: {A['videos']} ({A['video_bytes'] / 1e6:.1f} MB) -> {B['videos']} ({B['video_bytes'] / 1e6:.1f} MB)")
    if B["video_bytes"]: ok = False; print("  el nuevo FBX trae texturas embebidas")
    print("OK" if ok else "FALLA")
    return ok


if __name__ == "__main__":
    if sys.argv[1] == "--info":
        s = summary(sys.argv[2])
        print({k: v for k, v in s.items() if k not in ("bind", "models")})
        print(len(s["models"]), "nodos")
    else:
        a, b = sys.argv[1], sys.argv[2]
        tol = float(sys.argv[sys.argv.index("--rot-tol") + 1]) if "--rot-tol" in sys.argv else 0.01
        stacks = summary(a)["stacks"]
        # --sin-tomas: el nuevo se exportó sin animación a propósito (el sumo: anima con .anim de Unity)
        weapons = set(stacks) if "--sin-tomas" in sys.argv else {t for t in stacks if "|" in t and not t.startswith("Armature|")}
        sys.exit(0 if compare(a, b, rot_tol=tol, dropped_takes=weapons) else 1)
