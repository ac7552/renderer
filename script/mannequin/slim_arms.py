# The women's mannequin's arms slimmer: its shape key (public/models/women.bin) changed so the upper arm (with the
# cap of the shoulder, as far as the arm's bone carries it) and the forearm are drawn in toward the arm's own axis
# (the line through its joints), easing to nothing at the wrist; the hands don't change. The torso and legs don't
# move, so what the body measures (mannequin.json's women.body) stays as it is. It prints the arm's girth at the
# middle of the upper arm and of the forearm, before and after.
#
#   python3 script/headless/serve.py 8787 &
#   node script/mannequin/dump_body.mjs tmp/body.json
#   python3 script/mannequin/slim_arms.py tmp/body.json public/models/women.bin public/models/women.bin 0.86 0.9
#
# The numbers: how much the upper arm and the forearm are drawn in. Each run slims what's there, so run it once
# from the version you want to start from (12 November 2026: from dceeb3c's women.bin).
import json, math, sys
import numpy as np

d = json.load(open(sys.argv[1]))
P = np.array(d["pos"]).reshape(-1, 3)
OFF = np.fromfile(sys.argv[2], dtype="<f4").reshape(-1, 3).astype(np.float64)
si = np.array(d["si"]).reshape(-1, 4); sw = np.array(d["sw"]).reshape(-1, 4); bones = d["bones"]; heads = np.array(d["heads"])
K_UPPER, K_LOWER = float(sys.argv[4]), float(sys.argv[5])
weight = lambda name: (sw * (si == bones.index(name))).sum(1)
head = lambda name: heads[bones.index(name)]

W = P + OFF
N = W.copy()
report = {}
for side in "lr":
    for part, a, b, k_from, k_to in (("upperarm", "upperarm", "lowerarm", K_UPPER, K_UPPER), ("lowerarm", "lowerarm", "hand", K_LOWER, 1.0)):
        A, B = head(f"{a}_{side}"), head(f"{b}_{side}")
        axis = (B - A) / np.linalg.norm(B - A)
        t = (W - A) @ axis / np.linalg.norm(B - A)
        on = A + np.clip(t, -0.3, 1.0)[:, None] * (B - A)
        # (Radially only: nothing along the arm, so its length and its joints stay.)
        radial = (W - on) - ((W - on) @ axis)[:, None] * axis
        # The forearm eases to its own girth over its last third, to meet the hand.
        k = np.where(t < 0.66, k_from, k_from + (k_to - k_from) * np.clip((t - 0.66) / 0.34, 0, 1))
        w = weight(f"{part}_{side}")
        N += (w * (k - 1))[:, None] * radial
        if side == "l":
            ring = lambda V: V[(w > 0.6) & (np.abs(t - 0.5) < 0.04)]
            def girth(V):
                q = ring(V); u = np.cross(axis, [0, 0, 1.0]); u /= np.linalg.norm(u); v = np.cross(axis, u)
                r = np.hypot((q - A) @ u - ((q - A) @ u).mean(), (q - A) @ v - ((q - A) @ v).mean())
                return float(2 * math.pi * r.mean() * 100)
            report[part] = {"before_cm": round(girth(W), 1), "after_cm": round(girth(N), 1)}
(N - P).astype("<f4").tofile(sys.argv[3])
report["moved_max_cm"] = round(float(np.abs(N - W).max() * 100), 2)
print(json.dumps(report, indent=1))
