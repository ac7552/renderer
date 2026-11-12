// Run with: node --test test/javascript/*.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import "./support/lib.mjs"

const { Drape, tetherPairs, TETHER } = await import("lib/garments/drape")
const { SkinField } = await import("lib/garments/body")
const { buildCloth } = await import("lib/garments/cloth")

function farSkin() {
  const positions = [], normals = [], index = []
  for (let j = 0; j <= 2; j++) for (let i = 0; i <= 2; i++) { positions.push(i * 0.1, j * 0.1, -5); normals.push(0, 0, 1) }
  for (let j = 0; j < 2; j++) for (let i = 0; i < 2; i++) { const a = j * 3 + i; index.push(a, a + 1, a + 4, a, a + 4, a + 3) }
  return new SkinField(Float32Array.from(positions), Float32Array.from(normals), Uint32Array.from(index))
}
const line = (a, b, n = 11) => Array.from({ length: n }, (_, k) => [a[0] + ((b[0] - a[0]) * k) / (n - 1), a[1] + ((b[1] - a[1]) * k) / (n - 1)])
const sheet = (w, h) => ({ panels: { sheet: { edges: [
  { name: "bottom", points: line([-w / 2, -h], [w / 2, -h]) }, { name: "right", points: line([w / 2, -h], [w / 2, 0]) },
  { name: "top", points: line([w / 2, 0], [-w / 2, 0]) }, { name: "left", points: line([-w / 2, 0], [-w / 2, -h]) }
], place: { at: "body" } } }, seams: [] })

// A sheet hung by its top row, settled; returns how far below its own length its bottom row hangs (m).
function hung(tethered) {
  const cloth = buildCloth(sheet(30, 80), 1.6)
  const start = cloth.points.flatMap(([x, y]) => [x / 100, y / 100, 0])
  const drape = new Drape(cloth, start, { field: farSkin() }, { fabric: "twill", kernel: false })
  drape.sewn = true
  if (!tethered) { drape.tethers = new Int32Array(0); drape.tetherRest = new Float32Array(0) }
  // (Its top row held where it is, every small step.)
  const top = cloth.points.flatMap(([, y], i) => (y > -0.01 ? [i] : []))
  drape.collide = () => { for (const i of top) for (let c = 0; c < 3; c++) drape.p[3 * i + c] = start[3 * i + c] }
  for (let k = 0; k < 240; k++) drape.step({ gravity: true, sew: false })
  let low = 0
  for (let i = 1; i < drape.x.length; i += 3) low = Math.min(low, drape.x[i])
  return { sag: -low - 0.8, drape }
}

test("a hanging sheet keeps its length: without tethers it hangs centimetres long", () => {
  assert.ok(TETHER > 0)
  const loose = hung(false), held = hung(true)
  assert.ok(loose.sag > 0.03, `without tethers it sags ${(loose.sag * 100).toFixed(1)} cm`)
  assert.ok(held.sag < 0.012, `with them ${(held.sag * 100).toFixed(1)} cm`)
  assert.ok(held.sag < loose.sag / 3)
})

test("tethers only pull: on a sheet pushed together into waves every one is slack", () => {
  const cloth = buildCloth(sheet(40, 40), 1.6)
  const start = cloth.points.flatMap(([x, y]) => [(x / 100) * 0.8, y / 100, 0.008 * Math.sin(x / 4)])
  const drape = new Drape(cloth, start, { field: farSkin() }, { fabric: "twill", kernel: false })
  assert.ok(drape.tetherRest.length > cloth.points.length)
  for (let k = 0; k < drape.tetherRest.length; k++) {
    const a = 3 * drape.tethers[2 * k], b = 3 * drape.tethers[2 * k + 1]
    const d = Math.hypot(start[a] - start[b], start[a + 1] - start[b + 1], start[a + 2] - start[b + 2])
    assert.ok(d < drape.tetherRest[k] + 1e-6, `a tether ${d} m long, ${drape.tetherRest[k]} m on the pattern`)
  }
  // And a knit's give a little more than their length on the pattern.
  const knit = new Drape(cloth, start, { field: farSkin() }, { fabric: "stretch", kernel: false })
  assert.ok(Math.abs(knit.tetherRest[0] / drape.tetherRest[0] - 1.2) < 1e-3)
})

test("a tether never runs across a gap in its piece (a neckline, an armhole)", () => {
  // A U: two legs joined along the bottom, a notch 12 cm wide between them from the top.
  const u = { panels: { u: { edges: [
    { name: "bottom", points: line([-20, -40], [20, -40]) }, { name: "right", points: line([20, -40], [20, 0]) },
    { name: "topR", points: line([20, 0], [6, 0], 5) }, { name: "inR", points: line([6, 0], [6, -25]) },
    { name: "notch", points: line([6, -25], [-6, -25], 5) }, { name: "inL", points: line([-6, -25], [-6, 0]) },
    { name: "topL", points: line([-6, 0], [-20, 0], 5) }, { name: "left", points: line([-20, 0], [-20, -40]) }
  ], place: { at: "body" } } }, seams: [] }
  const cloth = buildCloth(u, 1.6)
  const pairs = tetherPairs(cloth, null, 4, 1.6)
  assert.ok(pairs.length > cloth.points.length, `${pairs.length} tethers for ${cloth.points.length} points`)
  for (const [a, b, rest] of pairs) {
    const [ax, ay] = cloth.points[a], [bx, by] = cloth.points[b]
    assert.ok(Math.abs(rest * 100 - Math.hypot(ax - bx, ay - by)) < 1e-3)
    assert.ok(Math.abs(rest * 100 - 6.4) < 1.2, `a tether ${(rest * 100).toFixed(1)} cm long`)
    // Above the notch's floor, both ends on the same side of it.
    if (Math.max(ay, by) > -23 && Math.min(ay, by) > -23) assert.ok(ax * bx > 0 || Math.abs(ax - bx) < 1e-6, `across the notch: ${ax},${ay} to ${bx},${by}`)
  }
})
