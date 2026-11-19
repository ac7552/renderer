// Run with: node --test tests/javascript/*.test.mjs
// Bags (bag.js, print.js's bagShape): the size a bag is built at, its body told from its handles in the photo,
// its surface, and where it's worn.
import { test } from "node:test"
import assert from "node:assert/strict"
import "./support/lib.mjs"

const { bagSize, bagSurface, strapBand, smoothLine, bagWay, shoulderFall, BAG_WAYS, BAG_WORN } = await import("lib/garments/bag")
const { bagShape, bagBody, bagLoop } = await import("lib/garments/print")

test("a bag is built at its listing's size, the photo settling what the listing leaves open", () => {
  // As listed.
  assert.deepEqual(bagSize("tote", { width: 46, height: 41, depth: 12 }, { aspect: 41 / 46 }), { width: 0.46, height: 0.41, depth: 0.12, guessed: false })
  // "L 17.3 x W 9.8": which is its height is a guess, and the photo stands tall.
  const pack = bagSize("backpack", { width: 44, height: 25, depth: 21, sure: false }, { aspect: 1.6 })
  assert.ok(pack.height > pack.width && Math.abs(pack.height - 0.44) < 1e-9)
  // One number given: the other from the photo's proportions.
  const wide = bagSize("duffle", { width: 55 }, { aspect: 0.5 })
  assert.ok(Math.abs(wide.height - 0.275) < 1e-9 && !wide.guessed)
  // Both given but far from the photo's proportions: the greater kept.
  const soft = bagSize("tote", { width: 30, height: 60 }, { aspect: 1.1 })
  assert.ok(Math.abs(soft.height - 0.6) < 1e-9 && Math.abs(soft.width - 0.6 / 1.1) < 1e-9)
  // None: its kind's usual area, in the photo's proportions, and marked as a guess.
  const guess = bagSize("backpack", null, { aspect: 1.5 })
  assert.ok(guess.guessed && Math.abs(guess.width * guess.height - 0.30 * 0.44) < 1e-6 && Math.abs(guess.height / guess.width - 1.5) < 1e-6)
  assert.equal(bagSize("clutch", null, null).guessed, true)
})

test("each kind of bag has its usual way of being worn, and the ways the wearer can pick", () => {
  assert.deepEqual([BAG_WORN.backpack, BAG_WORN.sling, BAG_WORN.crossbody, BAG_WORN.tote, BAG_WORN.duffle], ["back", "chest", "hip", "hand", "hand"])
  // A tote or a duffle: in the hand or on the shoulder. Asked for a way that isn't one of its own, its usual.
  assert.deepEqual(BAG_WAYS.tote, ["hand", "shoulder"])
  assert.equal(bagWay("tote", "shoulder"), "shoulder")
  assert.equal(bagWay("tote", null), "hand")
  assert.equal(bagWay("sling", "shoulder"), "chest")
  assert.equal(bagWay("something else", "shoulder"), "shoulder")
})

// A photo: a light backdrop, a dark body (a rounded box), and two thin handles standing over it.
function photo(w = 120, h = 120) {
  const data = new Uint8ClampedArray(4 * w * h)
  for (let i = 0; i < w * h; i++) data.set([236, 236, 236, 255], 4 * i)
  const paint = (x0, x1, y0, y1, c) => { for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) data.set([...c, 255], 4 * (y * w + x)) }
  paint(30, 89, 50, 104, [60, 40, 30])             // the body: 60 wide, 55 tall
  for (const x of [44, 74]) paint(x, x + 2, 22, 49, [20, 20, 20])   // two handles, 3 wide
  paint(44, 76, 22, 24, [20, 20, 20])              // joined over the top
  return { data, w, h }
}

test("a bag's body is told from its handles", () => {
  const { data, w, h } = photo()
  const read = bagShape(data, w, h)
  assert.ok(read, "the photo reads")
  const { shape } = read
  assert.ok(Math.abs(shape.top - 50 / 120) < 0.02 && Math.abs(shape.bottom - 105 / 120) < 0.02, `top ${shape.top}, bottom ${shape.bottom}`)
  assert.ok(Math.abs(shape.aspect - 55 / 60) < 0.06, `aspect ${shape.aspect}`)
  assert.ok(shape.handle > 0.4 && shape.handle < 0.6, `handles stand ${shape.handle} of its height over it`)
  assert.equal(read.color, "#3c281e")
  assert.equal(read.strap, "#141414")
  // (Worn away and grown back: the thin parts go, the body stays its size.)
  const mask = new Uint8Array(w * h)
  for (let i = 0; i < w * h; i++) mask[i] = data[4 * i] < 200 ? 1 : 0
  const body = bagBody(mask, w, h, 4)
  assert.equal(body[30 * w + 45], 0)
  assert.equal(body[80 * w + 60], 1)
  assert.equal(body[51 * w + 31], 1)
})

// A hobo: a body 70 wide and 30 tall, its two ends drawn up into one wide loop (each leg 16 wide where it leaves
// the body, 6 wide higher up), the backdrop showing through the loop.
function hobo(w = 120, h = 120) {
  const data = new Uint8ClampedArray(4 * w * h)
  for (let i = 0; i < w * h; i++) data.set([236, 236, 236, 255], 4 * i)
  const paint = (x0, x1, y0, y1, c = [150, 130, 100]) => { for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) data.set([...c, 255], 4 * (y * w + x)) }
  paint(25, 94, 75, 104)                       // the body
  for (let y = 20; y < 75; y++) {
    const wide = y > 55 ? 6 + Math.round(((y - 55) / 20) * 10) : 6
    paint(25, 25 + wide - 1, y, y)             // the left leg, wider toward the body
    paint(95 - wide, 94, y, y)                 // the right
  }
  paint(25, 94, 14, 19)                        // joined over the top
  return { data, w, h }
}

test("a loop handle that's one with the bag is told from its body: the body is what's under the loop", () => {
  const { data, w, h } = hobo()
  const read = bagShape(data, w, h)
  assert.ok(read, "the photo reads")
  const { shape } = read
  // The body starts under the loop (not at the top of its legs, the backdrop between them taken for bag).
  assert.ok(Math.abs(shape.top - 75 / 120) < 0.02 && Math.abs(shape.bottom - 105 / 120) < 0.02, `top ${shape.top}, bottom ${shape.bottom}`)
  assert.ok(Math.abs(shape.aspect - 30 / 70) < 0.05, `aspect ${shape.aspect}`)
  assert.ok(shape.fill > 0.9, `fill ${shape.fill}`)
  // Its loop: as tall again as twice the body, its top over the bag's middle.
  assert.ok(shape.handle > 1.8 && shape.handle < 2.2, `handle ${shape.handle}`)
  const loop = shape.loop
  assert.ok(loop, "a loop")
  assert.ok(Math.abs(loop.apex[0] - 0.5) < 0.03 && Math.abs(loop.apex[1] - shape.handle) < 1e-9, `apex ${loop.apex}`)
  assert.ok(Math.abs(loop.high - 61 / 70) < 0.03, `high ${loop.high}`)
  // Its horns: the legs where they're still wide (over 1.8 times the strap's 6: from row 65 down), kept as a
  // mask over their box of the photo; the strap's ends stand at their tips, a third of the body's height up.
  const horns = loop.horns
  assert.ok(horns, "horns")
  assert.ok(Math.abs(horns.top - 65 / 120) < 0.01 && Math.abs(horns.bottom - 75 / 120) < 0.01 && Math.abs(horns.left - 25 / 120) < 0.01 && Math.abs(horns.right - 95 / 120) < 0.01, JSON.stringify({ ...horns, bits: 0 }))
  assert.equal(horns.bits.length, horns.w * horns.h)
  const cell = (x, y) => horns.bits[Math.floor(((y - 65) / 10) * horns.h) * horns.w + Math.floor(((x - 25) / 70) * horns.w)]
  assert.equal(cell(28, 72), "1")
  assert.equal(cell(91, 72), "1")
  assert.equal(cell(60, 70), "0")
  assert.ok(loop.feet[0][0] < 0.12 && loop.feet[1][0] > 0.88 && loop.feet.every(q => Math.abs(q[1] - 10 / 30) < 0.04), `feet ${JSON.stringify(loop.feet)}`)
  assert.ok(loop.wide.every(v => v > 0.14 && v < 0.2) && Math.abs(loop.thin - 6 / 70) < 0.01, `wide ${loop.wide}, thin ${loop.thin}`)
  // It goes on the shoulder unless asked otherwise, and hangs by all its loop's height, as low as that lets it.
  assert.equal(bagWay("tote", null, shape), "shoulder")
  assert.equal(bagWay("tote", "hand", shape), "hand")
  assert.equal(bagWay("clutch", null, shape), "hand")
  const size = { width: 0.46, height: 0.2, depth: 0.12 }
  assert.ok(Math.abs(shoulderFall("tote", size, shape) - shape.handle * 0.2) < 1e-9)
  assert.equal(shoulderFall("tote", { ...size, height: 0.5 }, shape), 0.56)
  // The horns stand on the surface's top as a card, as wide and tall as their box against the body's.
  const card = bagSurface(shape, size).card
  assert.ok(card, "a card")
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity
  for (let i = 0; i < card.positions.length; i += 3) { x0 = Math.min(x0, card.positions[i]); x1 = Math.max(x1, card.positions[i]); y0 = Math.min(y0, card.positions[i + 1]); y1 = Math.max(y1, card.positions[i + 1]) }
  assert.ok(Math.abs(x0 + 0.23) < 0.01 && Math.abs(x1 - 0.23) < 0.01, `card across ${x0} to ${x1}`)
  assert.ok(Math.abs(y0 - 0.2) < 0.01 && Math.abs(y1 - (0.2 + 0.2 * (10 / 30))) < 0.012, `card up ${y0} to ${y1}`)
  assert.equal(bagSurface(bagShape(...Object.values(photo())).shape, size).card, null)
  // (A tote's thin handles aren't one: its body is as it was, and it's carried in the hand.)
  const tote = bagShape(...Object.values(photo())).shape
  assert.equal(tote.loop, undefined)
  assert.equal(bagWay("tote", null, tote), "hand")
  assert.ok(Math.abs(shoulderFall("tote", size, tote) - 0.2) < 1e-9)
  // (bagLoop: nothing for a bag in one piece, or a ring low down, a cord lying at its foot.)
  const mask = new Uint8Array(w * h)
  for (let y = 30; y < 100; y++) for (let x = 30; x < 90; x++) mask[y * w + x] = 1
  const box = { left: 30, right: 89, top: 30, bottom: 99 }
  assert.equal(bagLoop(mask, w, h, box), null)
  for (let y = 80; y < 95; y++) for (let x = 45; x < 75; x++) mask[y * w + x] = 0
  assert.equal(bagLoop(mask, w, h, box), null)
  for (let y = 36; y < 60; y++) for (let x = 45; x < 75; x++) mask[y * w + x] = 0
  assert.equal(bagLoop(mask, w, h, box)?.dip, 59)
  // (Nor two tabs standing up from its top with the backdrop open between them: a loop is closed over its gap.)
  for (let y = 30; y < 36; y++) for (let x = 45; x < 75; x++) mask[y * w + x] = 0
  assert.equal(bagLoop(mask, w, h, box), null)
})

test("the surface is as wide, tall and deep as the bag, its front on the photo", () => {
  const shape = bagShape(...Object.values(photo())).shape
  const size = { width: 0.4, height: 0.36, depth: 0.12 }
  const surface = bagSurface(shape, size, { flat: 0.8 })
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity, z0 = Infinity, z1 = -Infinity
  for (let i = 0; i < surface.positions.length; i += 3) {
    x0 = Math.min(x0, surface.positions[i]); x1 = Math.max(x1, surface.positions[i])
    y0 = Math.min(y0, surface.positions[i + 1]); y1 = Math.max(y1, surface.positions[i + 1])
    z0 = Math.min(z0, surface.positions[i + 2]); z1 = Math.max(z1, surface.positions[i + 2])
  }
  assert.ok(Math.abs(x1 - x0 - 0.4) < 0.03 && Math.abs(y1 - y0 - 0.36) < 1e-6, `${x1 - x0} by ${y1 - y0}`)
  assert.ok(Math.abs(z1 - 0.096) < 1e-6 && Math.abs(z0 + 0.024) < 1e-6, `front ${z1}, back ${z0}`)
  assert.equal(surface.frontCount * 2, surface.index.length)
  // Every point of the front reads the photo inside the body's own box.
  for (let i = 0; i < surface.uvs.length / 2; i += 2) {
    assert.ok(surface.uvs[i] >= shape.left - 0.03 && surface.uvs[i] <= shape.right + 0.03)
    assert.ok(1 - surface.uvs[i + 1] >= shape.top - 1e-6 && 1 - surface.uvs[i + 1] <= shape.bottom + 1e-6)
  }
  // With no photo, a plain rounded box of the size.
  const plain = bagSurface(null, size)
  assert.equal(plain.positions.length, surface.positions.length)
})

test("a strap is a band along its line, as wide and thick as asked", () => {
  const line = smoothLine([[0, 0, 0], [0.1, 0, 0], [0.2, 0.05, 0], [0.3, 0.05, 0]], 20)
  assert.equal(line.length, 20)
  assert.deepEqual(line[0], [0, 0, 0])
  const band = strapBand(line, line.map(() => [0, 0, 1]), 0.04, 0.005)
  assert.equal(band.positions.length, 20 * 4 * 3)
  // The first ring: 4 cm across (along y here), and 5 mm off the line (along z).
  const ring = [0, 1, 2, 3].map(k => [band.positions[3 * k], band.positions[3 * k + 1], band.positions[3 * k + 2]])
  const ys = ring.map(q => q[1]), zs = ring.map(q => q[2])
  assert.ok(Math.abs(Math.max(...ys) - Math.min(...ys) - 0.04) < 1e-3 && Math.abs(Math.max(...zs) - Math.min(...zs) - 0.005) < 1e-6)
  assert.ok(Math.min(...zs) >= -1e-9, "it stands off the body, not into it")
})
