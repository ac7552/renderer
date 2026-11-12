"""Shoes from Google's Scanned Objects (CC-BY 4.0; Downs et al., 2022) as templates the page fits (templates.js):
real shoes, scanned, in place of the nine modelled ones. Each scan is turned to the templates' frame (x across,
y up, z heel to toe, metres, on the floor), made a left shoe (the page mirrors it for the right foot), and
written as public/shoes/scan_<name>.bin in the templates' packed format, with a shade a point (its scan's
texture there, as detail: lighter or darker than the cloth round it), and listed in public/shoes/index.json
with the families it stands for.

    python3 script/shoes/scan_templates.py <dir of scans> [sheet.png]

<dir of scans>/<Name>/model.obj and texture.png, as in github.com/kevinzakka/mujoco_scanned_objects/models (the
dataset's meshes as OBJ). SCANS below says which are used, and as what. Credits: public/shoes/CREDITS.md.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from pack_templates import pack, read  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "public" / "shoes"
BINS = 64
SOLE, UPPER = 0, 1

# name in the dataset: (short name, the page's families it stands for (lasts.js), laced, turn it round)
# turn: True when the heel-or-toe guess below is wrong for it (checked on the sheet).
SCANS = {
    "ASICS_GEL1140V_WhiteBlackSilver": ("runner_gel", ["runner", "chunky"], True),
    "Reebok_ZIGLITE_RUSH": ("runner_zig", ["runner", "chunky"], True),
    "Reebok_CLASSIC_JOGGER": ("runner_jogger", ["runner", "court"], True),
    "Reebok_GL_6000": ("runner_gl", ["runner"], True),
    "TZX_Runner": ("runner_tzx", ["runner"], True),
    "Reebok_TURBO_RC": ("runner_turbo", ["runner", "chunky"], True),
    "Reebok_SH_PRIME_COURT_LOW": ("court_prime", ["court"], True),
    "Reebok_CL_LTHR_R12": ("court_leather", ["court", "runner"], True),
    "Reebok_BREAKPOINT_LO_2V": ("court_strap", ["court"], False),
    "Mens_Striper_Sneaker_in_White_rnp8HUli59Y": ("court_canvas", ["court"], True),
    "Womens_Canvas_Bahama_in_White_4UyOhP6rYGO": ("court_plimsoll", ["court", "flat"], True),
    "Reebok_FS_HI_INT_R12": ("hightop_fs", ["hightop"], True),
    "Reebok_SH_PRIME_COURT_MID": ("hightop_mid", ["hightop"], True),
    "Reebok_KAMIKAZE_II_MID": ("hightop_kamikaze", ["hightop"], True),
    "Reebok_PUMP_OMNI_LITE_HLS": ("hightop_pump", ["hightop"], True),
    "Timberland_Mens_Earthkeepers_Newmarket_6Inch_Cupsole_Boot": ("boot_6inch", ["combat", "hightop"], True),
    "Timberland_Mens_Earthkeepers_Stormbuck_Chukka": ("boot_chukka", ["combat", "derby", "chelsea"], True),
    "Womens_Hikerfish_Boot_in_Black_Leopard_bVSNY1Le1sm": ("boot_hiker", ["combat"], True),
    "MARTIN_WEDGE_LACE_BOOT": ("boot_wedge", ["combat"], True),
    "UGG_Classic_Tall_Womens_Boots_Chestnut_7": ("boot_tall_soft", ["tall", "chelsea"], False),
    "UGG_Bailey_Button_Womens_Boots_Black_7": ("boot_short_soft", ["chelsea", "tall"], False),
    "Tory_Burch_Kiernan_Riding_Boot": ("boot_riding", ["tall"], False),
    "Tory_Burch_Sabe_65mm_Bootie_Split_Suede_in_Caramel": ("bootie_heel", ["chelsea", "pump"], False),
    "Rayna_BootieWP": ("bootie", ["chelsea"], False),
    "Womens_Teva_Capistrano_Bootie": ("bootie_flat", ["chelsea", "combat"], False),
    "Timberland_Mens_Earthkeepers_Stormbuck_Plain_Toe_Oxford": ("derby_plain", ["derby", "combat"], True),
    "Timberland_Mens_Earthkeepers_Casco_Bay_Canvas_Oxford": ("derby_canvas", ["derby", "court"], True),
    "Mens_Gold_Cup_ASV_Capetown_Penny_Loafer_in_Black_EjPnk3E8fCs": ("loafer_penny", ["loafer"], False),
    "Mens_Tremont_Kiltie_Tassel_Loafer_in_Black_Amaretto": ("loafer_tassel", ["loafer"], False),
    "Mens_Gold_Cup_ASV_Dress_Casual_Venetian_in_Dark_Brown_Leather": ("loafer_venetian", ["loafer", "derby"], False),
    "Mens_Authentic_Original_Boat_Shoe_in_Navy_Leather_NHHQddDLQys": ("loafer_boat", ["loafer"], True),
    "Mens_Billfish_Slip_On_in_Coffee_e8bPKE9Lfgo": ("loafer_slipon", ["loafer", "court"], False),
    "Cream_Tieks_Italian_Leather_Ballet_Flats": ("flat_ballet", ["flat"], False),
    "Chelsea_BlkHeelPMP_DwxLtZNxLZZ": ("pump_high", ["pump"], False),
    "Chelsea_lo_fl_rdheel_nQ0LPNF1oMw": ("pump_low", ["pump", "flat"], False),
    "Santa_Cruz_Mens": ("loafer_moc", ["loafer"], False),
    "UGG_Bailey_Bow_Womens_Clogs_Black_7": ("boot_bow", ["tall", "chelsea"], False),
}
# (No sandals or slides: an open shoe's straps have to lie on the foot itself, and the page builds those from the
# photo, open_shape.js. The dataset has a few: NAPA_VALLEY_NAVAJO_SANDAL, adiZero_Slide_2_SC, the Santa Cruz thongs.)
# Scans whose heel and toe the guess below gets the wrong way round (seen on the sheet).
TURN = set()


def load_obj(path):
    V, VT, F, FT = [], [], [], []
    for line in open(path):
        if line.startswith("v "):
            V.append([float(a) for a in line.split()[1:4]])
        elif line.startswith("vt "):
            VT.append([float(a) for a in line.split()[1:3]])
        elif line.startswith("f "):
            ps = [p.split("/") for p in line.split()[1:]]
            for k in range(1, len(ps) - 1):
                F.append([int(ps[0][0]) - 1, int(ps[k][0]) - 1, int(ps[k + 1][0]) - 1])
                FT.append([int(ps[0][1]) - 1, int(ps[k][1]) - 1, int(ps[k + 1][1]) - 1] if len(ps[0]) > 1 and ps[0][1] else [0, 0, 0])
    return np.array(V), np.array(VT) if VT else np.zeros((1, 2)), np.array(F), np.array(FT)


def framed(V, F, name):
    """The scan's points in the templates' frame, a left shoe, and its triangles (rewound when mirrored)."""
    ext = V.max(0) - V.min(0)
    along = 0 if ext[0] > ext[1] else 1
    across = 1 - along
    # x across, y up (the scan's z), z along: a turn about the scan's z, or that and a mirror (fixed below).
    P = np.stack([V[:, across], V[:, 2], V[:, along]], 1)
    P[:, 1] -= P[:, 1].min()
    mirrored = along == 0   # (across, up, along) from (y, z, x) is a turn; from (x, z, y) a mirror
    u = (P[:, 2] - P[:, 2].min()) / (P[:, 2].max() - P[:, 2].min())
    # Heel to toe: the heel's end stands taller (the collar, a boot's shaft; a pump's heel lifts it), the toe lower.
    back, front = P[u < 0.3, 1].max(), P[u > 0.7, 1].max()
    turn = front > back
    if name in TURN:
        turn = not turn
    if turn:
        P[:, 2] = -P[:, 2]
        mirrored = not mirrored
    P[:, 2] -= P[:, 2].min()
    P[:, 0] -= (P[:, 0].min() + P[:, 0].max()) / 2
    u = P[:, 2] / P[:, 2].max()
    # A left shoe: its toe turns towards the other foot (the left foot stands at +x, so towards -x). By where
    # the widest part of the forefoot's outline sits against the heel's middle.
    heel = P[u < 0.15, 0].mean()
    tip = P[u > 0.93, 0].mean()
    if tip - heel > 0:
        P[:, 0] = -P[:, 0]
        mirrored = not mirrored
    if mirrored:
        F = F[:, ::-1].copy()
    return P, F, mirrored


def outward(P, F):
    """The triangles wound so their normals point out (by the mesh's signed volume)."""
    a, b, c = P[F[:, 0]], P[F[:, 1]], P[F[:, 2]]
    volume = np.einsum("ij,ij->i", a, np.cross(b, c)).sum()
    return F if volume > 0 else F[:, ::-1].copy()


def shade_of(VT, FT, F, n, texture):
    """A shade a point: its scan's texture there against the texture round it (a wide blur), 128 for the same:
    seams, laces, eyelets, mesh and stitching stay as lighter and darker; the scan's own colours don't."""
    img = np.asarray(Image.open(texture).convert("L"), dtype=np.float32)
    small = Image.fromarray(img.astype(np.uint8)).resize((256, 256), Image.BILINEAR)
    from PIL import ImageFilter
    wide = np.asarray(small.filter(ImageFilter.GaussianBlur(10)).resize(img.shape[::-1], Image.BILINEAR), dtype=np.float32)
    h, w = img.shape
    uv = np.zeros((n, 2))
    uv[F.reshape(-1)] = VT[FT.reshape(-1)]
    x = np.clip((uv[:, 0] % 1.0) * (w - 1), 0, w - 1).astype(int)
    y = np.clip((1 - uv[:, 1] % 1.0) * (h - 1), 0, h - 1).astype(int)
    ratio = (img[y, x] + 12) / (wide[y, x] + 12)
    return np.clip(np.round(128 * ratio), 30, 255).astype(np.uint8), img[y, x]


def profile_of(P):
    u = P[:, 2] / P[:, 2].max()
    b = np.minimum(BINS - 1, (u * BINS).astype(int))
    prof = {"top": [], "soleTop": [], "bottom": [], "half": []}
    for k in range(BINS):
        m = b == k
        if not m.any():
            for key in prof:
                prof[key].append(None)
            continue
        top, bottom = float(P[m, 1].max()), float(P[m, 1].min())
        prof["top"].append(top)
        prof["bottom"].append(bottom)
        # (The scan has no parts: its sole's top as the lasts take it without a sole line, a seventh up.)
        prof["soleTop"].append(bottom + (top - bottom) / 7)
        prof["half"].append(float(np.abs(P[m, 0]).max()))
    for key in prof:
        vals = prof[key]
        known = [i for i, v in enumerate(vals) if v is not None]
        prof[key] = [round(float(np.interp(i, known, [vals[j] for j in known])), 5) for i in range(BINS)]
    return prof


def convert(src, name):
    short, families, laced = SCANS[name]
    V, VT, F, FT = load_obj(src / name / "model.obj")
    used = np.unique(F)
    P, F2, mirrored = framed(V, F, name)
    FT2 = FT[:, ::-1].copy() if mirrored else FT
    F2o = outward(P, F2)
    if F2o is not F2:
        FT2 = FT2[:, ::-1].copy()
    F2 = F2o
    shade, grey = shade_of(VT, FT2, F2, len(P), src / name / "texture.png")
    lo, hi = P.min(0), P.max(0)
    q = np.round((P - lo) / (hi - lo) * 65535).astype(np.uint16)
    prof = profile_of(P)
    head = {
        "name": f"scan_{short}", "box": [lo.round(6).tolist(), hi.round(6).tolist()], "count": int(len(P)), "triangles": int(len(F2)),
        "groups": [[0, int(len(F2)) * 3, UPPER]], "profile": prof, "throat": 0.4, "laced": bool(laced), "scan": True,
        "families": families, "shade": True,
    }
    parts = np.full(len(F2), UPPER, dtype=np.uint8)
    packed = pack(head, q, F2.reshape(-1), parts)
    # The shades after the parts (gzip'd with the rest): read the packed file back, append, pack again.
    import gzip
    raw = gzip.decompress(packed) + shade.tobytes()
    data = gzip.compress(raw, 9, mtime=0)
    (OUT / f"scan_{short}.bin").write_bytes(data)
    return short, P, F2, grey, len(data), len(used)


def sheet(items, path):
    """Each scan from its outer side and from above, its points in its texture's grey: to check heel, toe and foot."""
    cell = (360, 200)
    cols = 4
    rows = (len(items) + cols - 1) // cols
    out = Image.new("L", (cols * cell[0], rows * cell[1] * 2), 255)
    from PIL import ImageDraw
    draw = ImageDraw.Draw(out)
    for k, (short, P, F, grey) in enumerate(items):
        ox, oy = (k % cols) * cell[0], (k // cols) * cell[1] * 2
        scale = 320 / 0.34
        # From the outer side (+x looks at it): z to the right, y up. Nearest points last.
        order = np.argsort(P[:, 0])
        px = (ox + 20 + P[order, 2] * scale).astype(int)
        py = (oy + cell[1] - 12 - P[order, 1] * scale).astype(int)
        for x, y, g in zip(px, py, grey[order]):
            if 0 <= x < out.width and 0 <= y < out.height:
                out.putpixel((x, y), int(g))
        # From above: z to the right, x down the picture (so -x, the other foot's side, is up).
        order = np.argsort(P[:, 1])
        px = (ox + 20 + P[order, 2] * scale).astype(int)
        py = (oy + cell[1] * 1.5 + P[order, 0] * scale).astype(int)
        for x, y, g in zip(px, py, grey[order]):
            if 0 <= x < out.width and 0 <= y < out.height:
                out.putpixel((x, y), int(g))
        draw.text((ox + 4, oy + 2), short, fill=0)
    out.save(path)


def write_index():
    index = json.loads((OUT / "index.json").read_text()) if (OUT / "index.json").exists() else {}
    index = {k: v for k, v in index.items() if not v.get("scan")}
    import gzip
    for path in sorted(OUT.glob("scan_*.bin")):
        data = gzip.decompress(path.read_bytes())
        h = struct.unpack("<I", data[:4])[0]
        head = json.loads(data[4:4 + h])
        index[head["name"]] = {k: head[k] for k in ("box", "profile", "throat", "laced", "scan", "families")}
        index[head["name"]]["v"] = hashlib.md5(path.read_bytes()).hexdigest()[:10]
    (OUT / "index.json").write_text(json.dumps(index, separators=(",", ":")))


def credits():
    lines = [
        "# Shoe models", "",
        "The files `scan_*.bin` are made from scans in **Google Scanned Objects** (Downs, Francis, Koenig, Kinman,",
        "Hickman, Reymann, McHugh, Vanhoucke: \"Google Scanned Objects: A High-Quality Dataset of 3D Scanned Household",
        "Items\", 2022), licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), taken as OBJ meshes from",
        "github.com/kevinzakka/mujoco_scanned_objects. Changes: turned to one frame, mirrored to a left shoe, their",
        "textures reduced to a shade a point (`script/shoes/scan_templates.py`).", "",
        "| File | Scan |", "|---|---|",
    ]
    for name, (short, _, _) in SCANS.items():
        lines.append(f"| scan_{short}.bin | {name} |")
    (OUT / "CREDITS.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    src = Path(sys.argv[1])
    items = []
    for name in SCANS:
        if not (src / name / "model.obj").exists():
            print("missing", name)
            continue
        short, P, F, grey, size, used = convert(src, name)
        items.append((short, P, F, grey))
        print(f"scan_{short}: {len(P)} points, {len(F)} triangles, {size / 1024:.0f} KB, {P[:, 2].max() * 100:.1f} cm long, {P[:, 1].max() * 100:.1f} tall")
    if len(sys.argv) > 2:
        sheet(items, sys.argv[2])
    write_index()
    credits()
