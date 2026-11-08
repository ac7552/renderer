// Run with: node --test test/javascript/*.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import "./support/lib.mjs"

const { lastGeometry, onLast } = await import("lib/garments/last_shape")

// A foot on a shin, as hull.test.mjs's.
function leg() {
  const positions = [], part = []
  for (let k = 0; k < 14; k++) {
    const y = k * 0.02
    for (let j = 0; j < 24; j++) {
      const a = (j / 24) * 2 * Math.PI, rz = y < 0.05 ? 0.12 : 0.045
      positions.push(0.1 + 0.045 * Math.sin(a), y, (y < 0.05 ? 0.04 : 0) + rz * Math.cos(a))
      part.push(4)
    }
  }
  return { body: { positions: Float32Array.from(positions) }, frame: { floor: 0, top: 1.76, part } }
}
// A low shoe's side: 0.3 as tall as long, its sole a sixth of that, on the floor; the topline high at the
// collar (the heel's end), low over the toe.
function side(lift = 0) {
  const n = 64, top = [], bottom = [], sole = []
  for (let b = 0; b < n; b++) {
    const u = b / (n - 1)
    const arch = lift && u > 0.25 && u < 0.65 ? lift : 0
    bottom.push(0.8 - arch); sole.push(0.75 - arch); top.push(0.5 + 0.15 * u * u)
  }
  return { left: 0.1, right: 0.9, aspect: 1, top, bottom, sole }
}

test("a shoe on a last stands flat on the floor, as long as the foot and its toe room, and no wider than a shoe", () => {
  const { body, frame } = leg()
  const g = lastGeometry(body, frame, "L", side(), [], { family: "court", square: 2.2, thick: 0.007, toe: 0.014 })
  assert.ok(g)
  const p = g.attributes.position
  let ymin = Infinity, ymax = -Infinity, xmin = Infinity, xmax = -Infinity, zmin = Infinity, zmax = -Infinity
  for (let i = 0; i < p.count; i++) { ymin = Math.min(ymin, p.getY(i)); ymax = Math.max(ymax, p.getY(i)); xmin = Math.min(xmin, p.getX(i)); xmax = Math.max(xmax, p.getX(i)); zmin = Math.min(zmin, p.getZ(i)); zmax = Math.max(zmax, p.getZ(i)) }
  assert.ok(Math.abs(ymin) < 0.003, `floor ${ymin}`)
  assert.ok(zmax - zmin > 0.25 && zmax - zmin < 0.3, `length ${zmax - zmin}`)
  assert.ok(xmax - xmin > 0.09 && xmax - xmin < 0.13, `width ${xmax - xmin}`)
  // Its sole is flat: every point of the sole's underside is on the floor.
  const index = g.index.array, sole = g.groups[0]
  let under = 0, flat = 0
  for (let k = sole.start; k < sole.start + sole.count; k++) { const y = p.getY(index[k]); if (y < 0.004) { under++; if (y < 0.002) flat++ } }
  assert.ok(under > 0 && flat === under)
  // The foot is inside it.
  const photo = g.userData.photo
  assert.ok(photo.within(0.1, 0.02, 0.06))
  assert.ok(!photo.within(0.1, 0.2, 0.06))
})

test("a heeled or open shoe isn't built on a last", () => {
  assert.equal(onLast({ family: "court" }, side()), true)
  assert.equal(onLast({ family: "pump", heel: 0.06 }, side()), false)
  assert.equal(onLast({ family: "sandal" }, side()), false)
  assert.equal(onLast({ family: "court", heel: 0.02 }, side()), true, "a sneaker's heel-to-toe drop")
  assert.equal(onLast({ family: "court", heel: 0.05 }, side()), false)
  assert.equal(onLast({ family: "chelsea" }, side(0.2)), false)
})
