"""Lee las tomas (takes) de un FBX binario sin Blender ni Unity: nombre y rango de tiempo en cuadros.

Sirve para comprobar lo que Unity va a ver (firstFrame/lastFrame del .meta se miden en el tiempo de la
toma del archivo, no en el de la acción de Blender) y que ninguna toma quedó corrida un cuadro.

python fbx_takes.py <archivo.fbx> [fps]
"""
import struct, sys, zlib

FBX_TICKS = 46186158000  # ticks de tiempo FBX por segundo


def _read_props(data, pos, n):
    props = []
    for _ in range(n):
        t = data[pos:pos + 1]
        pos += 1
        if t == b"Y":
            props.append(struct.unpack_from("<h", data, pos)[0]); pos += 2
        elif t == b"C":
            props.append(data[pos] != 0); pos += 1
        elif t == b"I":
            props.append(struct.unpack_from("<i", data, pos)[0]); pos += 4
        elif t == b"F":
            props.append(struct.unpack_from("<f", data, pos)[0]); pos += 4
        elif t == b"D":
            props.append(struct.unpack_from("<d", data, pos)[0]); pos += 8
        elif t == b"L":
            props.append(struct.unpack_from("<q", data, pos)[0]); pos += 8
        elif t in (b"S", b"R"):
            ln = struct.unpack_from("<I", data, pos)[0]; pos += 4
            raw = data[pos:pos + ln]; pos += ln
            props.append(raw.decode("utf-8", "replace") if t == b"S" else raw)
        elif t in (b"f", b"d", b"l", b"i", b"b"):
            cnt, enc, ln = struct.unpack_from("<III", data, pos); pos += 12
            raw = data[pos:pos + ln]; pos += ln
            if enc == 1:
                raw = zlib.decompress(raw)
            fmt = {b"f": "f", b"d": "d", b"l": "q", b"i": "i", b"b": "B"}[t]
            props.append(list(struct.unpack("<%d%s" % (cnt, fmt), raw)))
        else:
            raise ValueError("tipo de propiedad FBX desconocido %r en %d" % (t, pos))
    return props, pos


def read_nodes(data, pos, end, wide):
    nodes = []
    hdr = 25 if wide else 13
    while pos < end:
        if wide:
            end_off, nprops, plen = struct.unpack_from("<QQQ", data, pos)
        else:
            end_off, nprops, plen = struct.unpack_from("<III", data, pos)
        if end_off == 0:
            break
        nlen = data[pos + hdr - 1]
        name = data[pos + hdr:pos + hdr + nlen].decode("ascii", "replace")
        p = pos + hdr + nlen
        props, p2 = _read_props(data, p, nprops)
        children = read_nodes(data, p + plen, end_off, wide) if end_off > p + plen else []
        nodes.append((name, props, children))
        pos = end_off
    return nodes


def takes(path, fps=30.0):
    data = open(path, "rb").read()
    assert data.startswith(b"Kaydara FBX Binary"), "solo FBX binario"
    version = struct.unpack_from("<I", data, 23)[0]
    nodes = read_nodes(data, 27, len(data), version >= 7500)
    out = []
    for name, props, children in nodes:
        if name != "Takes":
            continue
        for cname, cprops, cch in children:
            if cname != "Take":
                continue
            info = {c[0]: c[1] for c in cch}
            lt = info.get("LocalTime", [0, 0])
            out.append((cprops[0], lt[0] / FBX_TICKS * fps, lt[1] / FBX_TICKS * fps))
    return out


if __name__ == "__main__":
    fps = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
    for n, a, b in takes(sys.argv[1], fps):
        print(f"{n}\t{a:.2f}\t{b:.2f}")
