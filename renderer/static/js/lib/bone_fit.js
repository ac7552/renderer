// Where a body's joints go when its shape changes. The mannequin's shape is shape keys on one mesh (the women's
// body, longer arms, wider shoulders): they move the skin, and the bones stay where the base shape had them. A
// longer forearm puts the wrist 3 or 4 cm past the bone that turns the hand; the women's body has its arm
// joints 4 to 12 cm from theirs. A limb turned about a joint that isn't in it shears: a notch at the elbow, a
// closed hand a claw. stage.js's fitBones moves each arm bone by its joint's shift here. Pure.

// The bones fitted: the arms and the hands.
export const FITTED_BONES = /^(upperarm|lowerarm|hand|thumb|index|middle|ring|pinky)_/

// How far each shape key moves each joint. A joint is where a bone's skin meets its parent's: the mean of the
// shape key there, weighted by how much both bones hold each vertex (a bone that shares too little skin with
// its parent takes the mean over its own).
//   skinIndex, skinWeight: 4 per vertex; keys: each shape key's offsets (x, y, z per vertex);
//   above: each bone's parent's index (-1 for none); fitted: which bones (by index) to work out.
// Returns, per bone, x, y, z per shape key (Float32Array), or null for a bone that isn't fitted.
export function jointShifts(skinIndex, skinWeight, keys, above, fitted) {
  const count = skinIndex.length / 4, K = keys.length
  const sums = above.map((_, bone) => (fitted(bone) ? { shared: new Float64Array(3 * K), sharedWeight: 0, sharedCount: 0, own: new Float64Array(3 * K), ownWeight: 0 } : null))
  const add = (sum, v, w) => {
    for (let k = 0; k < K; k++) {
      const key = keys[k]
      sum[3 * k] += w * key[3 * v]; sum[3 * k + 1] += w * key[3 * v + 1]; sum[3 * k + 2] += w * key[3 * v + 2]
    }
  }
  for (let v = 0; v < count; v++) {
    for (let a = 0; a < 4; a++) {
      const bone = skinIndex[4 * v + a], wa = skinWeight[4 * v + a], s = sums[bone]
      if (!s || !(wa > 0)) continue
      if (wa > 0.5) { add(s.own, v, wa); s.ownWeight += wa }
      for (let b = 0; b < 4; b++) {
        if (b === a || skinIndex[4 * v + b] !== above[bone]) continue
        const w = wa * skinWeight[4 * v + b]
        if (!(w > 0)) continue
        add(s.shared, v, w)
        s.sharedWeight += w
        if (w > 0.02) s.sharedCount++
      }
    }
  }
  return sums.map(s => {
    if (!s) return null
    const [sum, weight] = s.sharedCount >= 6 ? [s.shared, s.sharedWeight] : [s.own, s.ownWeight]
    return weight > 0 ? Float32Array.from(sum, value => value / weight) : null
  })
}

// A joint's move with the shape as it is: its shifts (jointShifts's, for one bone) by how much of each key is on.
export function jointMove(shifts, influences) {
  const move = [0, 0, 0]
  if (!shifts) return move
  for (let k = 0; k < influences.length; k++) {
    const by = influences[k]
    if (by) { move[0] += by * shifts[3 * k]; move[1] += by * shifts[3 * k + 1]; move[2] += by * shifts[3 * k + 2] }
  }
  return move
}
