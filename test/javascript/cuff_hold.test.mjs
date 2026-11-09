// Run with: node --test test/javascript/*.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import "./support/lib.mjs"

const { Drape } = await import("lib/garments/drape")

// A straight arm hanging down from the origin: shoulder, elbow 30 cm down, wrist 60 cm down. A point's place
// along it is how far below the shoulder it is, its distance from it how far from the vertical line.
const arm = {
  lengths: [0, 0.3, 0.6],
  locate: q => ({ t: -q[1], distance: Math.hypot(q[0], q[2]) }),
  along: () => ({ point: [0, 0, 0], direction: [0, -1, 0] })
}
// A left sleeve: rings of 8 points round the arm (4 cm out) at the heights given (m below the shoulder),
// a ring tilted by `tilt` (its far side lower, as a cuff over a bent hand).
function sleeve(rings, tilt = 0) {
  const p = []
  for (const t of rings) for (let k = 0; k < 8; k++) {
    const a = (k / 8) * 2 * Math.PI
    p.push(0.04 * Math.cos(a), -(t + tilt * Math.cos(a)), 0.04 * Math.sin(a))
  }
  const n = p.length / 3
  return { p: Float32Array.from(p), x: Float32Array.from(p), arms: { L: arm, R: arm }, sleeveSides: () => new Int8Array(n).fill(1) }
}
const tOf = (cloth, i) => -cloth.p[3 * i + 1]

test("a cuff past the wrist comes back up the arm as a ring, the sleeve above eased back, not folded", () => {
  // The cuff's edge 66 cm down on one side and 62 cm on the other (the hand tilts it), past the 63 cm limit.
  const cloth = sleeve([0.40, 0.55, 0.62, 0.64], 0.02)
  const before = Array.from({ length: 32 }, (_, i) => tOf(cloth, i))
  Drape.prototype.stayOnArms.call(cloth)
  const ring = r => Array.from({ length: 8 }, (_, k) => tOf(cloth, 8 * r + k))
  // Nothing past the limit any more.
  for (let i = 0; i < 32; i++) assert.ok(tOf(cloth, i) <= 0.63 + 1e-6, `point ${i} at ${tOf(cloth, i)}`)
  // The edge is still a ring tilted the same way: its far side lower than its near side, by about as much.
  const edge = ring(3)
  assert.ok(edge[0] - edge[4] > 0.025, `edge ${edge.map(v => v.toFixed(3))}`)
  // The ring above it stays above it all the way round (no point of the cuff folded up past the sleeve).
  const above = ring(2)
  for (let k = 0; k < 8; k++) assert.ok(above[k] < edge[k], `side ${k}: ${above[k]} over ${edge[k]}`)
  // The sleeve well above the wrist isn't moved.
  for (let k = 0; k < 8; k++) assert.equal(tOf(cloth, k), before[k])
})

test("a sleeve that ends above the wrist is left as it is", () => {
  const cloth = sleeve([0.40, 0.50, 0.58])
  const before = Float32Array.from(cloth.p)
  Drape.prototype.stayOnArms.call(cloth)
  assert.deepEqual(Array.from(cloth.p), Array.from(before))
})
