// Run with: node --test tests/javascript/*.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import "./support/lib.mjs"

const { lastGeometry } = await import("lib/garments/last_shape")
const { fitPose, projectAngled, testing } = await import("lib/garments/angled")

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

test("the camera a shoe was photographed from is found from its outline, and the photo laid on what it saw", () => {
  const { body, frame } = leg()
  const g = lastGeometry(body, frame, "L", side(), [], { family: "combat", square: 2.2, thick: 0.007, toe: 0.014 })
  // A "photo": the shoe's outline from three-quarters in front, looking down a little, on a 200 pixel square.
  const N = 200, shoe = testing.shoeOf(g)
  const mask = testing.outline(shoe, 50, 18, false, N)
  const pose = fitPose(g, { mask, w: N, h: N })
  assert.ok(pose, "a pose")
  assert.ok(!pose.pair, "one shoe")
  assert.ok(Math.abs(pose.turn - 50) <= 6 && Math.abs(pose.pitch - 18) <= 6 && !pose.mirror, JSON.stringify(pose))
  const { uv, weight } = projectAngled(g, { mask, w: N, h: N }, pose)
  // What faces the camera (forward or up, above the sole) takes the photo; what faces away doesn't.
  const dir = testing.cameraDir(pose.turn, pose.pitch), nrm = shoe.normals
  let toward = 0, towardSeen = 0, away = 0, awaySeen = 0
  for (let i = 0; i < shoe.count; i++) {
    const f = nrm[3 * i] * dir[0] + nrm[3 * i + 1] * dir[1] + nrm[3 * i + 2] * dir[2]
    const ahead = Math.max(nrm[3 * i + 2], nrm[3 * i + 1]), above = shoe.positions[3 * i + 1] - shoe.floor
    if (f > 0.7 && ahead > 0.6 && above > 0.04) { toward++; if (weight[i] > 0.5) towardSeen++ }
    if (f < -0.3) { away++; if (weight[i] > 0) awaySeen++ }
  }
  assert.ok(towardSeen / toward > 0.6, `${towardSeen} of ${toward} facing the camera`)
  assert.equal(awaySeen, 0)
  for (let i = 0; i < shoe.count; i++) if (weight[i] > 0) assert.ok(uv[2 * i] >= 0 && uv[2 * i] <= 1 && uv[2 * i + 1] >= 0 && uv[2 * i + 1] <= 1)
})

test("in a photo of the pair, the nearer shoe is found beside its mirror image", () => {
  const { body, frame } = leg()
  const g = lastGeometry(body, frame, "L", side(), [], { family: "combat", square: 2.2, thick: 0.007, toe: 0.014 })
  const shoe = testing.shoeOf(g), length = testing.extent(shoe), cell = (length * 2.6) / 80
  // The left shoe in front, lower and to the right; the right shoe behind it, up and to the left.
  const a = testing.placed(shoe, 40, 20, false, cell), b = testing.placed(shoe, 40, 20, true, cell)
  const N = 200, off = [Math.round((-0.55 * length) / cell), Math.round((-0.2 * length) / cell)]
  const small = testing.together(b, a, [-off[0], -off[1]])
  // Drawn bigger as the photo.
  const mask = new Uint8Array(N * N)
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) mask[y * N + x] = small[Math.floor((y * 64) / N) * 64 + Math.floor((x * 64) / N)]
  const pose = fitPose(g, { mask, w: N, h: N })
  assert.ok(pose && pose.pair, JSON.stringify(pose))
  assert.ok(Math.abs(pose.turn - 40) <= 8 && Math.abs(pose.pitch - 20) <= 8 && !pose.mirror, JSON.stringify(pose))
  // The nearer shoe's middle lands right of and below the pair's.
  assert.ok(pose.map.ox > N / 2 && pose.map.oy > N / 2, JSON.stringify(pose.map))
})
