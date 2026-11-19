// Run with: node --test tests/javascript/*.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import "./support/lib.mjs"

const { deltaE, linearOf } = await import("lib/colour")

test("sRGB to linear light", () => {
  assert.deepEqual(linearOf("#000000"), [0, 0, 0])
  assert.deepEqual(linearOf([255, 255, 255]), [1, 1, 1])
  // Middle grey: sRGB 118 is about 18% in linear light.
  assert.ok(Math.abs(linearOf("#767676")[0] - 0.18) < 0.005)
})

test("deltaE: none for the same colour, small for a shade apart, large across a hue", () => {
  assert.equal(deltaE([212, 203, 185], [212, 203, 185]), 0)
  // Kith's Armani crewneck: its photo's cloth against the stage's rendering of it before metering.
  const before = deltaE([212, 203, 185], [162, 150, 134])
  assert.ok(before > 15, `${before}`)
  assert.ok(deltaE([200, 200, 200], [204, 204, 204]) < 2.5)
  assert.ok(deltaE([200, 50, 50], [50, 200, 50]) > 80)
})

test("blockNear: a garment in two colours far apart is metered on the block nearer its photo's cloth", async () => {
  const { blockNear } = await import("lib/colour")
  // A varsity drawn: 300 navy pixels (the body), 200 white (the sleeves), a little noise on each.
  const s = [[], [], []]
  for (let k = 0; k < 500; k++) {
    const c = k < 300 ? [20, 45, 85] : [225, 225, 222], e = (k % 7) - 3
    for (let ch = 0; ch < 3; ch++) s[ch].push(c[ch] + e)
  }
  const kept = blockNear(s, [10, 37, 69])
  assert.equal(kept[0].length, 300)
  assert.ok(kept[2].every(v => v < 100))
  // Nearer white: the sleeves' block.
  assert.equal(blockNear(s, [240, 240, 240])[0].length, 200)
  // One colour lit and shaded (a mustard's fold, about 110 apart): all of it.
  const one = [[], [], []]
  for (let k = 0; k < 400; k++) { const c = k % 2 ? [200, 160, 60] : [140, 105, 30]; for (let ch = 0; ch < 3; ch++) one[ch].push(c[ch]) }
  assert.equal(blockNear(one, [180, 140, 50])[0].length, 400)
  // A few white pixels (a logo, under the share): all of it.
  const logo = [[], [], []]
  for (let k = 0; k < 400; k++) { const c = k < 30 ? [240, 240, 240] : [20, 45, 85]; for (let ch = 0; ch < 3; ch++) logo[ch].push(c[ch]) }
  assert.equal(blockNear(logo, [10, 37, 69])[0].length, 400)
})

test("middleColour: a little embroidery in another colour doesn't tint the cloth's middle colour", async () => {
  const { middleColour } = await import("lib/colour")
  // A grey cloth lit and shaded (88 to 168), a seventh of it red embroidery: red's red is above all the grey's,
  // its green and blue below, so each channel's median lands at a different place in the grey.
  const s = [[], [], []]
  for (let k = 0; k < 1000; k++) {
    const v = 88 + (k % 80), c = k % 7 === 0 ? [230, 40, 40] : [v, v, v]
    for (let ch = 0; ch < 3; ch++) s[ch].push(c[ch])
  }
  const plain = s.map(v => [...v].sort((a, b) => a - b)[500])
  assert.ok(plain[0] - plain[1] > 8, `the plain medians are tinted: ${plain}`)
  const m = middleColour(s)
  assert.ok(Math.abs(m[0] - m[1]) <= 2 && Math.abs(m[1] - m[2]) <= 2, `${m}`)
  // All one colour: its median.
  assert.deepEqual(middleColour([[10, 20, 30], [10, 20, 30], [10, 20, 30]]), [20, 20, 20])
})

test("the lit colour is the cloth's where the light falls, not its shaded middle, and not a print's", async () => {
  const { litColour, middleColour } = await import("lib/colour")
  // Grey cloth: 40% of what's seen lit (176), half in shade (130), and a tenth a black print.
  const s = [[], [], []]
  for (let k = 0; k < 1000; k++) {
    const v = k % 20 < 8 ? 176 + (k % 3) : k % 20 < 18 ? 130 + (k % 5) : 12
    for (let c = 0; c < 3; c++) s[c].push(v)
  }
  const lit = litColour(s), middle = middleColour(s)
  assert.ok(lit[0] >= 174 && lit[0] <= 179, `lit ${lit}`)
  assert.ok(middle[0] < 172, `middle ${middle}`)
  // Evenly lit cloth: the two agree.
  const even = [[], [], []]
  for (let k = 0; k < 1000; k++) { even[0].push(60 + (k % 4)); even[1].push(120 + (k % 4)); even[2].push(70 + (k % 4)) }
  const a = litColour(even), b = middleColour(even)
  assert.ok(Math.abs(a[1] - b[1]) <= 2 && Math.abs(a[0] - b[0]) <= 2)
})
