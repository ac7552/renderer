// Run with: node --test test/javascript/*.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import "./support/lib.mjs"

const { draftTop, measures, roundAtHem, STYLES } = await import("lib/garments/pattern")

// A big man (a 40.5 in waist, the rest guessed from it as the page does) and a size M hoodie from a usual
// chart: the chart's chest 20 cm under his, its shoulders 6 cm narrower.
const big = { chest: 121, waist: 103, hips: 120, shoulders: 49.5, arm: 65.5, height: 178, neck: 42, armpit: 21, bicep: 36, wrist: 18, head: 58 }
const M = { name: "M (2)", chest: 112, waist: 104, shoulders: 50, sleeve: 64, length: 70 }
const small = { ...M, chest: 101, shoulders: 43.5, waist: 94 }

test("a size too small for the body is cut no smaller round than it: drawn tight, never with the body outside it", () => {
  const m = measures(STYLES.hoodie, small, big)
  assert.ok(m.chest >= big.chest + 2, `chest ${m.chest}`)
  assert.ok(m.shoulders >= big.shoulders - 0.01, `shoulders ${m.shoulders}`)
  // Its rib hem band, stretched as rib stretches, goes round the body where it falls.
  const band = m.hem * 0.86
  assert.ok(band * 1.15 >= roundAtHem(big, m.length) - 0.01, `band ${band} round the body's ${roundAtHem(big, m.length)}`)
  // The pattern itself: front and back together as wide as the chest needs.
  const pattern = draftTop("hoodie", small, big, { closure: "zip" })
  const across = name => { const xs = pattern.panels[name].edges.flatMap(e => e.points.map(p => p[0])); return Math.max(...xs) - Math.min(...xs) }
  assert.ok(across("front") + across("back") >= big.chest + 2 - 0.5)
})

test("a size that fits is cut to its chart, as before", () => {
  const body = { chest: 101.6, waist: 86.4, hips: 101, shoulders: 45.5, arm: 65.5, height: 178, neck: 40, armpit: 19, bicep: 32, wrist: 17 }
  const m = measures(STYLES.hoodie, M, body)
  assert.equal(m.chest, 112)
  assert.equal(m.shoulders, 50)
  assert.equal(m.hem, Math.min(M.waist, M.chest))
})

test("a knit that stretches may be cut a little under the body, not far under it", () => {
  const body = { chest: 91, waist: 74, hips: 96, shoulders: 39.5, arm: 58, height: 165, armpit: 18, bicep: 28, wrist: 15, neck: 36 }
  assert.equal(measures(STYLES.tee, { chest: 87 }, body, { fit: "fitted", stretch: true }).chest, 87)
  assert.ok(Math.abs(measures(STYLES.tee, { chest: 70 }, body, { stretch: true }).chest - 91 * 0.94) < 0.01)
})

test("roundAtHem: the waist above it, the hips from them down, between the two between", () => {
  const body = { waist: 90, hips: 110, height: 180 }
  assert.equal(roundAtHem(body, 30), 90)
  assert.equal(roundAtHem(body, 70), 110)
  assert.ok(Math.abs(roundAtHem(body, 180 * 0.285) - 100) < 0.01)
  assert.equal(roundAtHem({}, 50), 0)
})

test("pants too small for the body are cut round it: the seat round the hips, the waist round the waist", async () => {
  const { bottomMeasures } = await import("lib/garments/pants")
  const body = { waist: 116.8, hips: 128, inseam: 88, height: 193, rise: 27 }
  const XS = { waist: 72, seat: 96, thigh: 60, inseam: 81, leg_opening: 44 }
  const m = bottomMeasures("trousers", XS, body)
  assert.ok(m.seat >= 128 + 2, `seat ${m.seat}`)
  assert.ok(m.waist >= 116.8, `waist ${m.waist}`)
  assert.ok(m.thigh >= m.seat * 0.5)
  // Leggings stretch: a little under the body, not far under.
  const tights = bottomMeasures("leggings", { waist: 60, seat: 80 }, body)
  assert.ok(Math.abs(tights.seat - 128 * 0.94) < 0.01, `seat ${tights.seat}`)
  // A pair that fits is cut to its chart.
  const man = { waist: 86.4, hips: 101, inseam: 81, height: 178, rise: 24 }
  const fits = bottomMeasures("trousers", { waist: 91, seat: 118, thigh: 72, inseam: 81, leg_opening: 50 }, man)
  assert.equal(fits.seat, 118); assert.equal(fits.waist, 91); assert.equal(fits.thigh, 72)
})

test("a sleeve much longer than the arm is drawn to the hand's base and bunched a little, not hung over the hand", () => {
  // The example woman's 58 cm arm in a men's M hoodie with a 74 cm sleeve (its cuff included).
  const woman = { chest: 127, waist: 103, hips: 120, shoulders: 46.5, arm: 58, height: 165, neck: 33, armpit: 21, bicep: 30, wrist: 15 }
  const m = measures(STYLES.hoodie, { chest: 129, sleeve: 74, length: 66 }, woman)
  const end = m.sleeve + 7 - 0.5   // the rib cuff's 7 cm, less the seam
  assert.ok(end <= 58 + 2 + 4 + 0.01 && end > 58 + 2, `the sleeve ends ${end} cm down`)
  // One about the arm's length is drawn as it is.
  const fits = measures(STYLES.hoodie, { chest: 129, sleeve: 59, length: 66 }, woman)
  assert.equal(fits.sleeve, 59 - 6.5)
})

test("a coat over a top is cut round the top as it's cut, its sleeves round the top's sleeves", async () => {
  const { overLayer } = await import("lib/garments/pattern")
  const big = { chest: 127, waist: 117, hips: 119, shoulders: 53, arm: 71, height: 193, neck: 43, armpit: 22.7, bicep: 35.3, upperArm: 34.4, wrist: 16.3 }
  const shirt = measures(STYLES.shortshirt, { chest: 88, shoulders: 36.1, sleeve: 24.7, length: 66 }, big)
  const coat = measures(STYLES.coat, { chest: 88, shoulders: 36, sleeve: 60, length: 80 }, overLayer(big, shirt))
  assert.ok(coat.chest >= shirt.chest + 4 + 2 - 0.01, `coat ${coat.chest} over the shirt's ${shirt.chest}`)
  assert.ok(coat.shoulders >= shirt.shoulders)
  assert.ok(coat.bicep >= shirt.bicep + 4, `coat sleeve ${coat.bicep} over the shirt's ${shirt.bicep}`)
  // Nothing under it: the body as it is.
  assert.equal(overLayer(big, null), big)
})

test("an open tee hem goes round a belly bigger than its chart's waist, so it hangs down over it", () => {
  // A 51 in chest (the waist guessed 110 cm, the hips 115), in a Parra tee: the M's and the XXXL's hems were
  // both cut to 92% of the body there and rode up over the belly, a crop top.
  const body = { chest: 129.5, waist: 110, hips: 115, shoulders: 51.5, arm: 65.5, height: 178, neck: 43, armpit: 21, bicep: 36, wrist: 17 }
  for (const size of [{ chest: 112.6, waist: 88.4, shoulders: 46, sleeve: 20, length: 57.6 }, { chest: 132.9, waist: 104.4, shoulders: 54, sleeve: 22, length: 64 }]) {
    const m = measures(STYLES.tee, size, body)
    assert.ok(m.hem >= roundAtHem(body, m.length) + 2 - 0.01, `hem ${m.hem} round ${roundAtHem(body, m.length)}`)
  }
})
