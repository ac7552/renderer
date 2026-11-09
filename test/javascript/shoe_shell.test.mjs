// Run with: node --test test/javascript/*.test.mjs
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
