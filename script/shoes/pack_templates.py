"""Packs the shoe templates (public/shoes/<name>.bin) for the wire: a template as build_templates.py writes it is
600 KB or so, most of it its triangles' indices; packed it's about a quarter. The points' quantised coordinates
are stored as the change from the point before (each axis on its own), the triangles' indices as the change from
the index before (zigzag, as varints: neighbouring triangles share points, so most changes are small), and the
whole file gzipped. The page reads it back with the browser's own gzip (templates.js, readTemplate).

    python3 script/shoes/pack_templates.py [names]     # packs the raw files in place (a packed one is left as it is)
"""
import gzip
import json
import struct
import sys
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[2] / "public" / "shoes"


def read(data):
    """A template file's head and arrays, packed or not: (head, q uint16 (n, 3), tris (t*3), parts (t))."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    h = struct.unpack("<I", data[:4])[0]
    head = json.loads(data[4:4 + h])
    at = 4 + h
    n, t = head["count"], head["triangles"]
    if head.get("packed") == 2:
        d = np.frombuffer(data[at:at + 6 * n], dtype="<u2").reshape(3, n)
        at += 6 * n + ((6 * n) % 4 and 2)
        q = np.cumsum(d.astype(np.uint64), axis=1).astype(np.uint16).T.copy()
        vi = data[at:at + head["indexBytes"]]
        at += head["indexBytes"]
        tris = unvarint(vi, 3 * t)
        parts = np.frombuffer(data[at:at + t], dtype=np.uint8)
        return head, q, tris, parts
    q = np.frombuffer(data[at:at + 6 * n], dtype="<u2").reshape(n, 3)
    at += 6 * n + ((6 * n) % 4 and 2)
    big = n > 65535
    tb = (4 if big else 2) * 3 * t
    tris = np.frombuffer(data[at:at + tb], dtype="<u4" if big else "<u2").astype(np.int64)
    at += tb
    at += (4 - at % 4) % 4   # (the head is padded to 4 bytes, so the body's padding is the file's)
    parts = np.frombuffer(data[at:at + t], dtype=np.uint8)
    return head, q, tris, parts


def varint(values):
    out = bytearray()
    for v in values:
        v = int(v)
        while v >= 128:
            out.append((v & 127) | 128)
            v >>= 7
        out.append(v)
    return bytes(out)


def unvarint(data, count):
    out = np.zeros(count, dtype=np.int64)
    k = shift = acc = 0
    for b in data:
        acc |= (b & 127) << shift
        if b & 128:
            shift += 7
            continue
        out[k] = acc
        k += 1
        acc = shift = 0
    zz = out
    d = (zz >> 1) ^ -(zz & 1)
    return np.cumsum(d)


def pack(head, q, tris, parts):
    n, t = head["count"], head["triangles"]
    d = np.diff(q.astype(np.int64), axis=0, prepend=0) % 65536
    planes = d.T.astype("<u2").tobytes()
    planes += b"\0\0" if len(planes) % 4 else b""
    dt = np.diff(tris.astype(np.int64), prepend=0)
    vi = varint((dt << 1) ^ (dt >> 63))
    head = {**head, "packed": 2, "indexBytes": len(vi)}
    hb = json.dumps(head, separators=(",", ":")).encode()
    hb += b" " * ((4 - len(hb) % 4) % 4)
    raw = struct.pack("<I", len(hb)) + hb + planes + vi + parts.astype(np.uint8).tobytes()
    return gzip.compress(raw, 9, mtime=0)


def pack_file(path):
    data = path.read_bytes()
    head, q, tris, parts = read(data)
    if data[:2] == b"\x1f\x8b":
        return len(data), len(data)
    packed = pack(head, q, tris, parts)
    # (Checked: read back, the same points, triangles and parts.)
    h2, q2, t2, p2 = read(packed)
    assert np.array_equal(q, q2) and np.array_equal(tris, t2) and np.array_equal(parts, p2), path
    path.write_bytes(packed)
    return len(data), len(packed)


if __name__ == "__main__":
    names = sys.argv[1:]
    paths = [OUT / f"{n}.bin" for n in names] if names else sorted(OUT.glob("*.bin"))
    for p in paths:
        a, b = pack_file(p)
        print(f"{p.name}: {a / 1024:.0f} KB -> {b / 1024:.0f} KB")
