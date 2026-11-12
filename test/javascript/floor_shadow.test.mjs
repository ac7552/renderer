// The line of shadow under a heel's arch (print.js's floorShadow): taken out of the shoe's mask, so the sole reads
// up in the air there; a flip-flop's own dark sole under its strap stays.
import test from "node:test"
import assert from "node:assert/strict"
import { floorShadow } from "../../app/javascript/lib/garments/print.js"

const W = 120, H = 80, BG = [93, 0, 0], FAR = [3, 2]
// A scene: rows from the top; paint(x0, x1, y0, y1, lab) sets the mask and the colour.
function scene() {
  const mask = new Uint8Array(W * H), lab = new Float32Array(W * H * 3)
  for (let i = 0; i < W * H; i++) lab.set(BG, 3 * i)
  const paint = (x0, x1, y0, y1, colour) => { for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) { mask[y * W + x] = 1; lab.set(colour, 3 * (y * W + x)) } }
  return { mask, lab, paint }
}
const lowest = (mask, x) => { for (let y = H - 1; y >= 0; y--) if (mask[y * W + x]) return y; return -1 }

test("a heel's floor shadow is taken out from under its arch", () => {
  const { mask, lab, paint } = scene()
  const shoe = [40, 20, 10]
  paint(10, 14, 20, 70, shoe)            // the stem
  paint(10, 60, 20, 26, shoe)            // the seat and the arch, up in the air
  paint(60, 110, 62, 70, shoe)           // the forepart on the floor
  for (let x = 15; x <= 59; x++) paint(x, x, 20 + Math.round((x - 15) * 0.9), 26 + Math.round((x - 15) * 0.9), shoe)
  paint(15, 59, 68, 70, [85, 0.5, 0.5])  // the shadow: the backdrop's colour, a little darker
  const cleared = floorShadow(mask, lab, BG, FAR, W, H)
  assert.ok(cleared > 20, `cleared ${cleared} columns`)
  assert.ok(lowest(mask, 25) < 60, "the arch's underside is the lowest of the shoe there")
  assert.equal(lowest(mask, 12), 70, "the stem still stands on the floor")
  assert.equal(lowest(mask, 90), 70, "and the forepart")
})

test("a flip-flop's dark sole under its strap stays", () => {
  const { mask, lab, paint } = scene()
  paint(10, 110, 66, 70, [30, 10, 15])                                                   // the sole
  for (let x = 50; x <= 90; x++) paint(x, x, 50 - Math.round(8 * Math.sin(((x - 50) / 40) * Math.PI)), 54 - Math.round(8 * Math.sin(((x - 50) / 40) * Math.PI)), [60, 5, 20])
  assert.equal(floorShadow(mask, lab, BG, FAR, W, H), 0)
  assert.equal(lowest(mask, 70), 70)
})
