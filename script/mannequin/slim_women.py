# The women's mannequin slimmer below the waist: its shape key (public/models/women.bin) changed so the hips,
# seat and thighs are drawn in toward each leg's (and the pelvis's) own centre, most at the seat and the top of
# the thigh, more behind than in front, nothing at the waist or below the knee. The arms (which hang beside the
# hips) don't move. It prints what the body measures before and after, taken as fitroom_model.py's BodyGauge
# takes them: put the new hips in mannequin.json's women.body (the waist, chest and inseam don't change).
#
#   python3 script/headless/serve.py 8787 &
#   node script/mannequin/dump_body.mjs tmp/body.json
#   python3 script/mannequin/slim_women.py tmp/body.json public/models/women.bin public/models/women.bin 0.94 0.90 0.93
#
# The numbers: how much the hips, the upper thighs and (behind) the seat are drawn in. Each run slims what's
# there, so run it once from the version you want to start from (November 2026: from c47ea5d's women.bin).
import json, math, sys
import numpy as np

d = json.load(open(sys.argv[1]))
P = np.array(d["pos"]).reshape(-1, 3)
OFF = np.fromfile(sys.argv[2], dtype="<f4").reshape(-1, 3).astype(np.float64)
si = np.array(d["si"]).reshape(-1, 4); sw = np.array(d["sw"]).reshape(-1, 4); bones = d["bones"]
K_HIP, K_THIGH, K_SEAT = (float(x) for x in sys.argv[4:7])

def bw(*names):
    out = np.zeros(len(P))
    for n in names:
        out += (sw * (si == bones.index(n))).sum(1)
    return out
arm = np.zeros(len(P))
for i, n in enumerate(bones):
    if n.startswith(("upperarm_", "lowerarm_", "hand_", "thumb_", "index_", "middle_", "ring_", "pinky_")):
        arm += (sw * (si == i)).sum(1)
torso = arm < 0.3

def hull_perimeter(pts):
    pts = sorted(map(tuple, pts))
    if len(pts) < 3: return 0
    cross = lambda o, a, b: (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0: lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0: up.pop()
        up.append(p)
    h = lo[:-1] + up[:-1]
    return sum(math.dist(h[i], h[(i+1) % len(h)]) for i in range(len(h)))

def measure(V):
    floor, top = V[:, 1].min(), V[:, 1].max(); H = top - floor
    z = lambda s: floor + s * H
    slab = lambda y: V[torso & (np.abs(V[:, 1] - y) < 0.006)][:, [0, 2]]
    chest = max(hull_perimeter(slab(h)) for h in np.linspace(z(0.68), z(0.76), 17))
    waist = hull_perimeter(slab(z(0.6)))
    hips_at = [(hull_perimeter(slab(h)), h) for h in np.linspace(z(0.46), z(0.56), 21)]
    hips, hy = max(hips_at)
    mid = (np.abs(V[:, 0]) < 0.01) & (V[:, 1] > z(0.3))
    inseam = V[mid][:, 1].min() - floor
    thigh = hull_perimeter(V[(bw("thigh_l") > 0.5) & (np.abs(V[:, 1] - (floor + inseam - 0.05)) < 0.006)][:, [0, 2]])
    return {"height": H*100, "chest": chest*100, "waist": waist*100, "hips": hips*100, "hips_y": hy, "inseam": inseam*100, "thigh": thigh*100}

W = P + OFF
before = measure(W)

# Each region's centre (the middle of its extent across and front to back) at each height, smoothed.
T = bw("pelvis", "spine_01", "spine_02", "spine_03"); L = bw("thigh_l", "calf_l"); R = bw("thigh_r", "calf_r")
bins = np.arange(0.0, 1.2, 0.01)
def centres(mask):
    c = np.full((len(bins), 2), np.nan)
    for i, y in enumerate(bins):
        s = W[mask & (np.abs(W[:, 1] - y) < 0.01)]
        if len(s) > 4: c[i] = [(s[:, 0].min() + s[:, 0].max()) / 2, (s[:, 2].min() + s[:, 2].max()) / 2]
    for k in range(2):  # fill gaps, then smooth
        good = ~np.isnan(c[:, k]); c[:, k] = np.interp(bins, bins[good], c[good, k])
        c[:, k] = np.convolve(np.pad(c[:, k], 3, mode="edge"), np.ones(7) / 7, mode="valid")
    return c
cT, cL, cR = centres(torso & (T > 0.5)), centres(L > 0.5), centres(R > 0.5)
at = lambda c, y: np.stack([np.interp(y, bins, c[:, 0]), np.interp(y, bins, c[:, 1])], 1)

y = W[:, 1]
# How much each height is drawn in: nothing at the waist and the knee, most at the seat and upper thigh.
ys = [0.48, 0.60, 0.74, 0.86, 0.95, 1.03]
ks = [1.0, (1 + K_THIGH) / 2, K_THIGH, K_HIP, (1 + K_HIP) / 2 + 0.0, 1.0]
k = np.interp(y, ys, ks)
# The seat: extra, behind only, from the top of the thigh to below the waist.
seat = np.interp(y, [0.74, 0.84, 0.92, 1.0], [1.0, K_SEAT, K_SEAT, 1.0])

cover = np.clip(T + L + R, 0, 1) * (arm < 0.05)
total = np.maximum(T + L + R, 1e-9)
C = (T[:, None] * at(cT, y) + L[:, None] * at(cL, y) + R[:, None] * at(cR, y)) / total[:, None]
dx = W[:, 0] - C[:, 0]; dz = W[:, 2] - C[:, 1]
back = np.clip((-dz) / 0.03, 0, 1); back = back * back * (3 - 2 * back)  # smoothstep behind the centre
kz = k * (1 - back * (1 - seat))
nx = C[:, 0] + dx * k; nz = C[:, 1] + dz * kz
N = W.copy()
N[:, 0] = W[:, 0] + cover * (nx - W[:, 0]); N[:, 2] = W[:, 2] + cover * (nz - W[:, 2])
after = measure(N)
(N - P).astype("<f4").tofile(sys.argv[3])
print(json.dumps({"before": before, "after": after, "moved_max_cm": float(np.abs(N - W).max() * 100)}, indent=1))
