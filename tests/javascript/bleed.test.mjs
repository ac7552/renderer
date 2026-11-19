// Run with: node --test tests/javascript/*.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import "./support/lib.mjs"

const { bleed } = await import("lib/garments/redrape")

// A white square of cloth with a grey rim (the backdrop blended into its outline) on a grey backdrop.
function photo(n = 60, from = 10, to = 40) {
  const data = new Uint8ClampedArray(4 * n * n), mask = new Uint8Array(n * n)
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
    const i = y * n + x, inside = x >= from && x < to && y >= from && y < to
    const rim = inside && (x === from || y === from || x === to - 1 || y === to - 1)
    const v = inside ? (rim ? 120 : 250) : 200
    data.set([v, v, v, 255], 4 * i)
    mask[i] = inside ? 1 : 0
  }
  return { data, mask, n }
}

test("the cloth's colour is spread out from inside its outline, its grey rim spread over", () => {
  const { data, mask, n } = photo()
  bleed(data, mask, n, n, 5)
  for (const [x, y] of [[10, 20], [8, 20], [20, 6], [39, 39], [42, 30]]) assert.equal(data[4 * (y * n + x)], 250, `${x},${y}`)
  // Further out than the spread: the backdrop as it was.
  assert.equal(data[4 * (20 * n + 1)], 200)
})

test("a sliver thinner than the inset spreads from its outline as before", () => {
  const { data, mask, n } = photo(60, 28, 31)
  bleed(data, mask, n, n, 3)
  assert.equal(data[4 * (29 * n + 26)], 120)
})
