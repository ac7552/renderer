// Run with: node --test tests/javascript/*.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import "./support/lib.mjs"

const { FittingStage } = await import("lib/stage")

// A stage with one top on, sewn, in its pose and shown, its shop photos still being laid on (hung up, in the
// worker): only what the drape's own step reads, with what it says to the page kept.
function stage() {
  const s = Object.create(FittingStage.prototype)
  const top = { slot: "top", top: { done: true, photos: { front: "front.jpg" }, item: { photoCloth: null }, mesh: {} }, posedAs: "standing", posing: null, shown: true, final: true,
    restX: new Float32Array(3), redrapeState: "hanging", hanger: { advance: () => true } }
  Object.assign(s, { slots: { bottom: null, top, outer: null }, leaving: {}, waiting: {}, order: ["bottom", "top", "outer"], pose: "standing", feet: {}, holds: 0, pendingSince: null,
    busy: true, revealed: true, said: [], turns: 0 })
  s.onDrape = phase => s.said.push(phase)
  s.redraw = () => {}
  s.reveal = () => { s.turns++ }
  return s
}

test("clothes that have settled stay covered until their photos are laid on, then are shown once", () => {
  const s = stage()
  assert.equal(s.settled, true)
  assert.equal(s.pending(), "photos")
  assert.equal(s.finished, false)
  s.advanceDrape()
  s.advanceDrape()
  // Still covered: the page is told so (its words stay as they were), and the figure hasn't made its turn.
  assert.deepEqual(s.said, ["finishing", "finishing"])
  assert.equal(s.turns, 0)
  assert.equal(s.busy, true)
  s.slots.top.redrapeState = "done"
  assert.equal(s.finished, true)
  s.advanceDrape()
  s.advanceDrape()
  assert.deepEqual(s.said, ["finishing", "finishing", "done"])
  assert.equal(s.turns, 1)
  assert.equal(s.busy, false)
})

test("what the page is still reading keeps them covered too, and covers them when it starts", () => {
  const s = stage()
  s.slots.top.redrapeState = "done"
  s.advanceDrape()
  assert.deepEqual(s.said, ["done"])
  // A reading begun with the clothes on and shown: covered now, not at the next frame.
  const read = s.hold(), other = s.hold()
  assert.deepEqual(s.said, ["done", "finishing"])
  assert.equal(s.pending(), "reading")
  s.advanceDrape()
  read()
  read()   // (said twice, counted once)
  s.advanceDrape()
  assert.equal(s.finished, false)
  other()
  assert.equal(s.pending(), null)
  s.advanceDrape()
  assert.deepEqual(s.said, ["done", "finishing", "finishing", "finishing", "done"])
})

test("shoes being built, a garment not yet shown and a colour not yet metered are waited for", () => {
  const s = stage()
  s.slots.top.redrapeState = "done"
  s.feet.dressing = "boots"
  assert.equal(s.pending(), "shoes")
  s.feet.dressing = null
  s.slots.top.shown = false
  assert.equal(s.pending(), "showing")
  s.slots.top.shown = true
  s.slots.top.top.item.photoCloth = "#8a8f7d"
  assert.equal(s.pending(), "colour")
  s.slots.top.metered = s.meterKey(s.slots.top)
  assert.equal(s.pending(), null)
  // (Its photos taken off: nothing to lay on, and its colour metered again without them.)
  s.slots.top.redrapeState = "off"
  assert.equal(s.pending(), "colour")
  s.slots.top.metered = s.meterKey(s.slots.top)
  assert.equal(s.pending(), null)
  // Not settled, it isn't finished whatever else is done.
  s.slots.top.posing = {}
  assert.equal(s.finished, false)
})

test("nothing is waited for for ever, and a change with the clothes on and no veil up raises none", () => {
  const s = stage()
  s.advanceDrape()
  assert.equal(s.finished, false)
  assert.ok(s.pendingSince !== null)
  // (Twenty seconds on: a photo that never came.)
  s.pendingSince = performance.now() - 21000
  assert.equal(s.finished, true)
  s.advanceDrape()
  assert.deepEqual(s.said, ["finishing", "done"])
  // Still pending, and no longer busy: nothing more is said (the veil doesn't come back for it).
  s.advanceDrape()
  assert.deepEqual(s.said, ["finishing", "done"])
  // A new drape starts the wait again.
  s.slots.top.posing = { next: () => ({ done: false, value: null }) }
  s.slots.top.final = false
  s.advanceDrape()
  assert.equal(s.pendingSince, null)
})
