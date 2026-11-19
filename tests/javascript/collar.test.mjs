// Run with: node --test tests/javascript/*.test.mjs
// A collar's leaf (lib/garments/collar.js): how long it is round the neck, and the line it takes from its fold
// at the stand's top to where its edge rests on the shirt.
import { test } from "node:test"
import assert from "node:assert/strict"
import "./support/lib.mjs"

const { COLLAR_LEAF, leafLength, leafFront, leafLine, alongLine, surfaceUnder } = await import("lib/garments/collar")

const far = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1])

test("a collar's leaf is a collar's size: a finger over its stand at the back, longer at its points", () => {
  const shirt = COLLAR_LEAF.shirt, polo = COLLAR_LEAF.polo
  // At the back of the neck, and round the sides: about 4 cm (the stand is 3.2).
  assert.ok(Math.abs(leafLength(shirt, Math.PI) - 0.041) < 1e-9)
  assert.ok(Math.abs(leafLength(shirt, 1.5) - 0.041) < 1e-9)
  // At its points, either side of the neck's opening: about 7 cm (it was 9 cm down and 7 cm out).
  const point = leafLength(shirt, shirt.open)
  assert.ok(point > 0.066 && point < 0.076, `point ${point}`)
  assert.ok(Math.abs(leafLength(shirt, -shirt.open) - point) < 1e-12)
  // Longer the nearer the front, and with the body.
  assert.ok(leafLength(shirt, 0.5) > leafLength(shirt, 0.9) && leafLength(shirt, 0.9) > leafLength(shirt, 1.2))
  assert.ok(Math.abs(leafLength(shirt, 0.5, 1.1) - leafLength(shirt, 0.5) * 1.1) < 1e-12)
  assert.equal(leafFront(0), 1)
  assert.equal(leafFront(2), 0)
  // A polo's knit collar: longer over its lower stand, its points a little longer, meeting nearer the front.
  assert.ok(leafLength(polo, Math.PI) > leafLength(shirt, Math.PI) && leafLength(polo, polo.open) < 0.07)
  assert.ok(polo.open < shirt.open)
})

test("the leaf's edge rests on the shirt, its length from the fold; it's taut from the fold to there", () => {
  // A stand 3.2 cm high, 7 cm out from the neck's middle; the yoke from its foot, falling 1 in 3 going out.
  const fold = [0.074, 0.004]
  const under = Array.from({ length: 14 }, (_, k) => [0.078 + k * 0.006, -0.032 - k * 0.002])
  const line = leafLine(fold, under, 0.044)
  // Straight from the fold to the yoke (it doesn't go down the stand and along the yoke: it stands off the
  // stand's foot), 4.4 cm long, its end on the yoke's line.
  assert.equal(line.length, 2)
  const end = line[1]
  // (To a fifth of a millimetre: between two looks at the shirt the place is found along a straight line.)
  assert.ok(Math.abs(far(fold, end) - 0.044) < 2e-4, `long ${far(fold, end)}`)
  assert.ok(Math.abs(end[1] - (-0.032 - ((end[0] - 0.078) / 0.006) * 0.002)) < 1e-9, "on the yoke")
  assert.ok(end[0] - fold[0] > 0.01 && end[0] - fold[0] < 0.03, `out ${end[0] - fold[0]}`)
  // Down a chest (steep under the stand's foot), the same leaf hangs nearly straight down.
  const chest = Array.from({ length: 14 }, (_, k) => [0.078 + k * 0.006, -0.032 - k * 0.03])
  const hung = leafLine(fold, chest, 0.074)
  const tip = hung[hung.length - 1]
  assert.ok(Math.abs(far(fold, tip) - 0.074) < 2e-4 && tip[0] - fold[0] < 0.02 && fold[1] - tip[1] > 0.068, `tip ${tip}`)
  // Over a rise that stands above the straight line (a shoulder seam's ridge), it goes over it, not through.
  const ridge = under.map((q, k) => (k === 1 ? [q[0], -0.002] : q))
  const over = leafLine(fold, ridge, 0.06)
  assert.equal(over.length, 3)
  assert.deepEqual(over[1], [0.084, -0.002])
  for (const q of ridge) {
    if (q[0] > over[over.length - 1][0]) continue
    // (The line's height at q's place is never under q.)
    let k = 1
    while (k < over.length - 1 && over[k][0] < q[0]) k++
    const a = over[k - 1], b = over[k], y = a[1] + ((q[0] - a[0]) / (b[0] - a[0])) * (b[1] - a[1])
    assert.ok(y >= q[1] - 1e-9, `over the shirt at ${q[0]}`)
  }
  // Where the shirt runs out before the leaf does, it ends at the last of it.
  assert.deepEqual(leafLine(fold, under.slice(0, 2), 0.2).at(-1), under[1])
})

test("points along a leaf's line are by length, no further than the leaf is long", () => {
  const line = [[0, 0], [0.03, -0.04], [0.06, -0.04]]
  assert.deepEqual(alongLine(line, 0, 0.08), [0, 0])
  const half = alongLine(line, 0.5, 0.08)
  assert.ok(Math.abs(half[0] - 0.024) < 1e-9 && Math.abs(half[1] + 0.032) < 1e-9)
  assert.deepEqual(alongLine(line, 1, 0.08), [0.06, -0.04])
  // (A line longer than the leaf is cut at the leaf's length.)
  const cut = alongLine(line, 1, 0.05)
  assert.ok(Math.abs(cut[0] - 0.03) < 1e-9 && Math.abs(cut[1] + 0.04) < 1e-9)
})

test("the surface under a point, looked straight down on: the highest one below a height, from the triangles over it", () => {
  // A sloping sheet (y = 0.5 + x) over a level one (y = 0.2), each two triangles over the unit square about the origin.
  const sheet = (y, n) => [[-1, -1], [1, -1], [1, 1], [-1, 1]].flatMap(([x, z]) => [x, y(x), z])
  const positions = Float32Array.from([...sheet(x => 0.5 + x), ...sheet(() => 0.2)])
  const index = [0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7]
  const under = surfaceUnder(positions, index, [0, 0], 1.2, { cell: 0.1 })
  assert.ok(Math.abs(under(0.3, -0.4) - 0.8) < 1e-6)
  // Below a height: the sheet under it, as a collar's edge looks past the stand it hangs from.
  assert.ok(Math.abs(under(0.3, -0.4, 0.7) - 0.2) < 1e-6)
  assert.equal(under(0.3, -0.4, 0.1), null)
  // Where the sloping sheet dips under the level one, the level one is on top.
  assert.ok(Math.abs(under(-0.6, 0.2) - 0.2) < 1e-6)
  // Past the cloth's edge, and past the reach, there's nothing.
  assert.equal(under(1.1, 0), null)
  assert.equal(under(5, 5), null)
  // Without an index every three points are a triangle; only the part that's drawn counts.
  const loose = Float32Array.from(index.flatMap(i => [...positions.slice(3 * i, 3 * i + 3)]))
  assert.ok(Math.abs(surfaceUnder(loose, null, [0, 0], 1.2)(0.3, -0.4) - 0.8) < 1e-6)
  assert.ok(Math.abs(surfaceUnder(positions, index, [0, 0], 1.2, { from: 6 })(0.3, -0.4) - 0.2) < 1e-6)
})

test("the surface under many points of a big mesh agrees with trying every triangle", () => {
  // A wavy cloth of 20,000 triangles; 400 points looked at.
  const n = 100, positions = new Float32Array(3 * (n + 1) * (n + 1)), index = []
  const wave = (x, z) => 1 + 0.05 * Math.sin(9 * x) * Math.cos(7 * z)
  for (let i = 0; i <= n; i++) for (let j = 0; j <= n; j++) { const k = i * (n + 1) + j, x = -0.5 + i / n, z = -0.5 + j / n; positions.set([x, wave(x, z), z], 3 * k) }
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) { const a = i * (n + 1) + j, b = a + 1, c = a + n + 1, d = c + 1; index.push(a, c, b, b, c, d) }
  const under = surfaceUnder(positions, index, [0.1, -0.05], 0.2)
  let seen = 0
  for (let k = 0; k < 400; k++) {
    const angle = k * 2.399, far = 0.19 * Math.sqrt((k + 0.5) / 400), x = 0.1 + far * Math.cos(angle), z = -0.05 + far * Math.sin(angle)
    const y = under(x, z)
    assert.ok(y !== null && Math.abs(y - wave(x, z)) < 2e-4, `at ${x.toFixed(3)}, ${z.toFixed(3)}: ${y} against ${wave(x, z)}`)
    seen++
  }
  assert.equal(seen, 400)
})
