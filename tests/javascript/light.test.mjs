// Run with: node --test tests/javascript/*.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import { nightAt, MODES } from "../../renderer/static/js/lib/light.js"

test("by the clock it's daylight from 7 to 6, and night otherwise", () => {
  assert.equal(nightAt("auto", 6), true)
  assert.equal(nightAt("auto", 7), false)
  assert.equal(nightAt("auto", 17), false)
  assert.equal(nightAt("auto", 18), true)
  assert.equal(nightAt("auto", 3), true)
})

test("a held light ignores the clock", () => {
  for (const hour of [0, 9, 13, 22]) {
    assert.equal(nightAt("day", hour), false)
    assert.equal(nightAt("night", hour), true)
  }
  assert.deepEqual(MODES, ["auto", "day", "night"])
})
