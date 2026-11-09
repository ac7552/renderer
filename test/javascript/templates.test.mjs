// Run with: node --test test/javascript/*.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import "./support/lib.mjs"

const { readTemplate, templateGeometry, templateFor } = await import("lib/garments/templates")
const { lastFrame } = await import("lib/garments/last_shape")

const bin = name => { const b = readFileSync(new URL(`../../public/shoes/${name}.bin`, import.meta.url)); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) }

function leg() {
  const positions = [], part = []
  for (let k = 0; k < 14; k++) {
    const y = k * 0.02
    for (let j = 0; j < 24; j++) { const a = (j / 24) * 2 * Math.PI, rz = y < 0.05 ? 0.12 : 0.045; positions.push(0.1 + 0.045 * Math.sin(a), y, (y < 0.05 ? 0.04 : 0) + rz * Math.cos(a)); part.push(4) }
  }
  return { body: { positions: Float32Array.from(positions) }, frame: { floor: 0, top: 1.76, part } }
}
// A boot's side: tall at the heel, low over the toe.
function side() {
  const n = 64, top = [], bottom = [], sole = []
  for (let b = 0; b < n; b++) { const u = b / (n - 1); bottom.push(0.8); sole.push(0.74); top.push(u < 0.45 ? 0.35 : 0.35 + 0.3 * ((u - 0.45) / 0.55) ** 0.7) }
  return { left: 0.1, right: 0.9, aspect: 1, top, bottom, sole }
}

test("a template's file is read: its points inside its box, its triangles over them, its parts grouped", () => {
  for (const name of ["runner", "chunky"]) assert.equal(readTemplate(bin(name)).name, name)
  const t = readTemplate(bin("workboot"))
  assert.equal(t.name, "workboot")
  assert.equal(t.positions.length, 3 * t.count)
  const [lo, hi] = t.box
  for (let i = 0; i < t.count; i++) for (let d = 0; d < 3; d++) assert.ok(t.positions[3 * i + d] >= lo[d] - 1e-6 && t.positions[3 * i + d] <= hi[d] + 1e-6)
  for (const v of t.index) assert.ok(v < t.count)
  assert.deepEqual(t.groups.map(g => g[2]), [0, 1, 2, 3, 4])
  assert.equal(t.profile.top.length, 64)
})

test("a template is stretched to the side photo: its upper's top along the shoe on the photo's topline, its sole on the floor", () => {
  const { body, frame } = leg()
  const style = { family: "combat", square: 2.2, thick: 0.007, toe: 0.014 }
  const t = readTemplate(bin("workboot"))
  const g = templateGeometry(body, frame, "L", side(), [], style, t)
  const f = lastFrame(body, frame, "L", side(), [], style)
  const p = g.attributes.position.array, n = p.length / 3
  // The upper's points (group 1) binned along the shoe: the highest in each bin at the photo's topline there.
  const upper = new Set()
  const index = g.index.array
  for (const { start, count, materialIndex } of g.groups) if (materialIndex === 1) for (let k = start; k < start + count; k++) upper.add(index[k])
  const bins = 20, high = new Array(bins).fill(-Infinity)
  let low = Infinity
  for (let i = 0; i < n; i++) {
    low = Math.min(low, p[3 * i + 1])
    if (!upper.has(i)) continue
    const u = (p[3 * i + 2] - f.back) / f.span
    const b = Math.min(bins - 1, Math.max(0, Math.floor(u * bins)))
    high[b] = Math.max(high[b], p[3 * i + 1])
  }
  for (let b = 2; b < bins - 2; b++) {
    const u = (b + 0.5) / bins
    assert.ok(Math.abs(high[b] - f.yTop(u)) < 0.02, `bin ${b}: ${high[b].toFixed(3)} against ${f.yTop(u).toFixed(3)}`)
  }
  assert.ok(Math.abs(low - f.floor) < 0.004, `the sole's bottom at ${low}`)
  assert.equal(g.userData.photo.hull.template, "workboot")
})

test("a template is chosen by the family, unless the photo's side is much more like another's", () => {
  assert.equal(templateFor({ family: "loafer" }, null).name, "loafer")
  assert.equal(templateFor({ family: "sandal" }, null), null)
  // A runner and a chunky sneaker have their own (a rockered midsole; a platform), not the court's.
  assert.equal(templateFor({ family: "runner" }, null).name, "runner")
  assert.equal(templateFor({ family: "chunky" }, null).name, "chunky")
})
