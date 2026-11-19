// Run with: node --test tests/javascript/*.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import "./support/lib.mjs"

const { outerShell } = await import("lib/garments/accessories")

// A box's faces, wound to face out (sign 1) or in (sign -1), its points added to `positions`.
function box(positions, index, [x0, y0, z0], [x1, y1, z1], sign) {
  const base = positions.length / 3
  for (const [x, y, z] of [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]]) positions.push(x, y, z)
  const faces = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [2, 3, 7, 6], [1, 2, 6, 5], [0, 4, 7, 3]]
  for (const [a, b, c, d] of faces) {
    const quad = sign > 0 ? [a, b, c, a, c, d] : [a, c, b, a, d, c]
    for (const k of quad) index.push(base + k)
  }
}

test("a shoe's outside is kept for the cloth to lie on; its lining, facing in towards the leg, isn't", () => {
  const positions = [], index = []
  box(positions, index, [-0.05, 0, -0.13], [0.05, 0.1, 0.13], 1)       // the upper's outside
  box(positions, index, [-0.04, 0.01, -0.12], [0.04, 0.1, 0.12], -1)   // its lining, facing in
  const kept = outerShell(Float32Array.from(positions), Uint32Array.from(index))
  // The outside's four walls and its top (up) stay; of the lining only its floor (the insole, facing up).
  const outside = new Set([...kept].filter(i => i < 8))
  assert.equal(outside.size, 8)
  const liningTriangles = []
  for (let t = 0; t < kept.length; t += 3) if (kept[t] >= 8) liningTriangles.push([kept[t], kept[t + 1], kept[t + 2]])
  assert.equal(liningTriangles.length, 2)
  for (const tri of liningTriangles) for (const i of tri) assert.ok(Math.abs(positions[3 * i + 1] - 0.01) < 1e-9)
})

test("the frame stands in its shoes: each shoe's outline, its ankle and the way its toe points, worked out from its points", async () => {
  const { standInShoes } = await import("lib/garments/accessories")
  // A block of a shoe each side: 10 cm wide, 28 cm long (its heel 6 cm behind the ankle), 8 cm tall.
  const shoe = cx => { const p = []; for (const x of [cx - 0.05, cx + 0.05]) for (const y of [0.005, 0.045, 0.075]) for (const z of [-0.06, 0.08, 0.22]) p.push(x, y, z); return Float32Array.from(p) }
  const frame = { floor: 0, top: 1.76, feet: { bare: true }, joints: { ankle_L: [0.1, 0.09, 0], ankle_R: [-0.1, 0.09, 0] } }
  assert.equal(standInShoes(frame, { L: shoe(0.1), R: shoe(-0.1) }), frame)
  for (const [side, cx] of [["L", 0.1], ["R", -0.1]]) {
    const foot = frame.feet[side]
    assert.ok(foot.hulls.some(Boolean) && typeof foot.at === "function")
    assert.deepEqual(foot.ankle, frame.joints[`ankle_${side}`])
    // Its toe points forward (+z), a little out toward the far corner of its sole.
    assert.ok(foot.forward[1] > 0.9 && Math.abs(Math.hypot(...foot.forward) - 1) < 1e-9, `forward ${foot.forward}`)
    assert.ok(Math.abs(foot.reach - 0.035) < 1e-9)
    assert.ok(Math.abs(foot.top - 0.075) < 1e-6)
  }
  // Bare feet (no shoes, or only one) and a frame with no feet are left as they are.
  const bare = { floor: 0, top: 1.76, feet: { bare: true }, joints: {} }
  assert.equal(standInShoes(bare, null).feet.bare, true)
  assert.equal(standInShoes(bare, { L: shoe(0.1) }).feet.bare, true)
  assert.equal(standInShoes({ floor: 0, top: 1.76, feet: null }, { L: shoe(0.1), R: shoe(-0.1) }).feet, null)
})
