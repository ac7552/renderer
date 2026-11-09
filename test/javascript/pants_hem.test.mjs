// Run with: node --test test/javascript/*.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import "./support/lib.mjs"

const { hemSlant } = await import("lib/garments/pants")

test("a leg longer than the wearer's has its back hem cut higher, up to 4 cm", () => {
  assert.equal(hemSlant({ inseam: 81 }, { inseam: 81 }), 1.5)
  assert.equal(hemSlant({ inseam: 78 }, { inseam: 81 }), 1.5)
  assert.equal(hemSlant({ inseam: 84 }, { inseam: 81 }), 3)
  assert.equal(hemSlant({ inseam: 95 }, { inseam: 81 }), 4)
  assert.equal(hemSlant({ inseam: 84 }, {}), 1.5)
})
