// Run with: node --test test/javascript/*.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import "./support/lib.mjs"

const { clipBand, closedFore, thongPlan } = await import("lib/garments/open_shape")
const { lastFor } = await import("lib/garments/lasts")

test("a band is cut from the grid where its value crosses a half, and its edge closed once round", () => {
  // A grid 6 rows by 8 round, its value 1 in a block of rows and columns, falling to 0 outside it.
  const rows = 6, around = 8, value = new Float32Array(rows * around)
  for (let k = 0; k < rows; k++) for (let j = 0; j < around; j++) value[k * around + j] = k >= 2 && k <= 3 && j >= 2 && j <= 4 ? 1 : 0
  const { points, triangles, edges } = clipBand(rows, around, value)
  assert.ok(triangles.length > 0)
  // Every cut point halfway between an inside and an outside point.
  for (const p of points) if (p.length === 3) { assert.ok(Math.abs(p[2] - 0.5) < 1e-6); assert.notEqual(value[p[0]] >= 0.5, value[p[1]] >= 0.5) }
  // The edge is closed: each of its points starts one edge and ends one.
  const starts = new Map(), ends = new Map()
  for (const [a, b] of edges) { starts.set(a, (starts.get(a) ?? 0) + 1); ends.set(b, (ends.get(b) ?? 0) + 1) }
  for (const [a, n] of starts) assert.equal(n, ends.get(a))
  // Nothing outside the block is kept.
  for (const t of triangles) for (const i of t) { const p = points[i]; if (p.length === 1) assert.ok(value[p[0]] >= 0.5) }
})

// A side photo as a mask over (u along the shoe, y in metres): a sole 0..0.02 m, and over it whatever's given.
const sole = () => 0.02, top = () => 0.08
test("a shoe closed over the toes (a clog, a sneaker mule) is told from one open over them (a slide, a sandal)", () => {
  const floor = () => 0
  // A clog: tall at the instep, its toe box half as tall. A slide: its strap over the instep, only the sole under the toes.
  const clog = u => (u < 0.3 ? 0.05 : 0.09 - 0.05 * Math.max(0, u - 0.5) / 0.5)
  const slide = u => (u > 0.4 && u < 0.78 ? 0.08 : 0.02)
  assert.ok(closedFore(clog, floor) > 0.42)
  assert.ok(closedFore(slide, floor) < 0.42)
})

test("a thong's strap runs from where the photo's arch meets the sole to its post; a flip-flop's words make it one", () => {
  // The arch: from the sole at 30 % along, up to 4 cm at 55 %, down to the post at 76 %; the sole uneven by 3 mm.
  const arch = u => (u < 0.3 || u > 0.76 ? 0 : 0.04 * Math.sin(Math.PI * (u - 0.3) / 0.46))
  const flipflop = (u, y) => (y <= 0.02 + 0.003 * Math.sin(u * 20) + Math.max(0, arch(u)) ? 1 : 0)
  const plan = thongPlan(flipflop, sole, 1)
  assert.ok(plan.front >= 0.7 && plan.front <= 0.8, `front ${plan.front}`)
  assert.ok(plan.back > 0.3 && plan.back < 0.42, `back ${plan.back}`)
  assert.equal(thongPlan((u, y) => (y <= 0.02 + 0.003 * Math.sin(u * 20) ? 1 : 0), sole, 1), null)
  assert.equal(lastFor("Havaianas Top - Blue", "sandal", null).params.thong, true)
  assert.equal(lastFor("Pennon Phat Flipflops - Taupe", "sandal", null).params.thong, true)
  assert.equal(lastFor("Birkenstock Arizona Sandal", "sandal", null).params.thong, undefined)
})
