// Run with: node --test tests/javascript/*.test.mjs
// The skeleton fitted to the body's shape (lib/bone_fit.js): how far each shape key moves each joint.
import { test } from "node:test"
import assert from "node:assert/strict"
import "./support/lib.mjs"

const { jointShifts, jointMove, FITTED_BONES } = await import("lib/bone_fit")

// An arm of three bones along x: 0 the upper arm (to x = 1), 1 the forearm (1 to 2), 2 the hand (2 on). Rings
// of four vertices every 0.125; at a joint the two bones share the rings' weight.
function arm() {
  const index = [], weight = [], at = []
  for (let k = 0; k <= 20; k++) {
    const x = k * 0.125
    for (let c = 0; c < 4; c++) {
      at.push(x)
      const bone = x < 1 ? 0 : x < 2 ? 1 : 2
      const joint = Math.abs(x - 1) < 0.3 ? [0, 1] : Math.abs(x - 2) < 0.3 ? [1, 2] : null
      if (joint) {
        const far = (x - (joint[1] === 1 ? 1 : 2)) / 0.5 + 0.5
        index.push(joint[0], joint[1], 0, 0); weight.push(1 - far, far, 0, 0)
      } else { index.push(bone, 0, 0, 0); weight.push(1, 0, 0, 0) }
    }
  }
  return { index: Float32Array.from(index), weight: Float32Array.from(weight), at }
}

test("a shape key that lengthens the forearm moves the wrist with it, and leaves the elbow where it was", () => {
  const { index, weight, at } = arm()
  // The key: everything past the elbow drawn out along x, by up to 0.2 at the wrist and all of it beyond.
  const longer = Float32Array.from(at.flatMap(x => [Math.min(0.2, Math.max(0, x - 1) * 0.2), 0, 0]))
  const drop = Float32Array.from(at.flatMap(() => [0, -0.1, 0]))
  const shifts = jointShifts(index, weight, [longer, drop], [-1, 0, 1], bone => bone > 0)
  assert.equal(shifts[0], null)
  // The elbow (where the forearm meets the upper arm) hardly moves; the wrist moves by the 0.2.
  assert.ok(Math.abs(shifts[1][0]) < 0.03, `elbow ${shifts[1][0]}`)
  assert.ok(Math.abs(shifts[2][0] - 0.2) < 0.01, `wrist ${shifts[2][0]}`)
  // (A key that moves everything moves every joint by as much.)
  assert.ok(Math.abs(shifts[1][4] + 0.1) < 1e-6 && Math.abs(shifts[2][4] + 0.1) < 1e-6)
  // With half the first key on and all of the second.
  const move = jointMove(shifts[2], [0.5, 1])
  assert.ok(Math.abs(move[0] - 0.1) < 0.01 && Math.abs(move[1] + 0.1) < 1e-6 && move[2] === 0)
  assert.deepEqual(jointMove(null, [1, 1]), [0, 0, 0])
})

test("a bone that shares no skin with its parent takes its own skin's move; the arms and hands are the bones fitted", () => {
  // Two bones, no vertex held by both.
  const index = Float32Array.from([0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]), weight = Float32Array.from([1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0])
  const key = Float32Array.from([0, 0, 0, 0.1, 0, 0, 0.3, 0, 0])
  const shifts = jointShifts(index, weight, [key], [-1, 0], bone => bone === 1)
  assert.ok(Math.abs(shifts[1][0] - 0.2) < 1e-6)
  for (const name of ["upperarm_l", "lowerarm_r", "hand_l", "index_02_r", "thumb_01_l"]) assert.ok(FITTED_BONES.test(name), name)
  for (const name of ["clavicle_l", "spine_03", "thigh_l", "foot_r", "head"]) assert.ok(!FITTED_BONES.test(name), name)
})
