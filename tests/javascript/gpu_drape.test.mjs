// Run with: node --test tests/javascript/*.test.mjs
// How Drape#step hands its frames to the graphics card (gpu_drape.js) and takes them back. The card itself
// isn't here (Node has no WebGPU): a stand-in takes its place.
import { test } from "node:test"
import assert from "node:assert/strict"
import "./support/lib.mjs"

const { Drape } = await import("lib/garments/drape")
const { SkinField } = await import("lib/garments/body")
const { buildCloth } = await import("lib/garments/cloth")

function sheet() {
  const line = (a, b) => Array.from({ length: 6 }, (_, k) => [a[0] + ((b[0] - a[0]) * k) / 5, a[1] + ((b[1] - a[1]) * k) / 5])
  const pattern = { panels: { sheet: { edges: [
    { name: "bottom", points: line([-10, -10], [10, -10]) }, { name: "right", points: line([10, -10], [10, 10]) },
    { name: "top", points: line([10, 10], [-10, 10]) }, { name: "left", points: line([-10, 10], [-10, -10]) }
  ], place: { at: "body" } } }, seams: [] }
  const cloth = buildCloth(pattern, 4)
  const far = new SkinField(Float32Array.of(0, 0, -5, 1, 0, -5, 0, 1, -5), Float32Array.of(0, 0, 1, 0, 0, 1, 0, 0, 1), Uint32Array.of(0, 1, 2))
  return new Drape(cloth, cloth.points.flatMap(([x, y]) => [x / 100, y / 100 + 1, 0]), { field: far })
}

test("a frame the card takes isn't also stepped on the CPU, and one it turns down is, timed for its trial", () => {
  const taken = [], timed = []
  let take = true
  Drape.gpu = { step: (drape, options) => { taken.push(options); return take }, cpuTime: (drape, ms) => timed.push(ms) }
  try {
    const drape = sheet()
    const before = Float32Array.from(drape.x)
    drape.step({ gravity: true, sew: false })
    assert.equal(drape.frame, 1)
    assert.deepEqual(Array.from(drape.x), Array.from(before), "the card's frame leaves the CPU's points for it to fill in")
    assert.deepEqual(taken[0], { gravity: true, sew: false, still: false })
    take = false
    drape.step({ gravity: true, sew: false })
    assert.equal(drape.frame, 2)
    assert.ok(drape.x[1] < before[1], "turned down, the CPU drapes the frame")
    assert.equal(timed.length, 1)
  } finally {
    Drape.gpu = null
  }
})

test("a drape kept off the card, or with no card, steps as before", () => {
  Drape.gpu = { step: () => { throw new Error("shouldn't be asked") }, cpuTime: () => {} }
  try {
    const off = sheet()
    off.noGpu = true
    off.step()
    assert.equal(off.frame, 1)
  } finally {
    Drape.gpu = null
  }
  const plain = sheet(), copy = sheet()
  plain.step(); copy.stepCpu()
  assert.deepEqual(Array.from(plain.x), Array.from(copy.x))
})
