// A shirt's or polo's collar leaf: the part folded down over the stand (stage.js's collarLeaf draws it on the
// shirt as draped). How long it is, and the line it takes from its fold to where its edge rests. Pure.

// A leaf's length from its fold at the stand's top to its edge (m, on the 1.76 m body): `back` at the back of
// the neck, `points` more at its points; `open`: how far round from the front's middle it starts (radians: a
// shirt's points stand apart either side of the neck's opening; a polo's meet over its placket); `spread`: how
// far round the neck a point's tip lies from where it leaves the stand (they lie apart).
export const COLLAR_LEAF = {
  // A shirt's: 4.1 cm at the back of the neck (a 3.2 cm stand and a finger more: its edge rests on the yoke
  // some 2 cm out from the stand), 7 cm at its points.
  shirt: { back: 0.041, points: 0.036, open: 0.34, spread: 0.16 },
  // A polo's or a rugby shirt's knit collar: 4.6 cm over a lower stand (its edge 3.5 cm out, on the
  // shoulders), 6.4 cm at its points.
  polo: { back: 0.046, points: 0.018, open: 0.16, spread: 0.1 }
}
// How thick a leaf is drawn (m): its edge shows, as a folded collar's does.
export const COLLAR_THICK = 0.003

// How long the leaf is at an angle round the neck (0 at the front's middle), on a body `scale` times 1.76 m:
// longer toward the front, where the points are.
export function leafLength(leaf, angle, scale = 1) {
  const front = leafFront(angle)
  return (leaf.back + leaf.points * Math.pow(front, 1.2)) * scale
}
// How much of a point there is at an angle: 1 at the front's middle, none from 1.1 radians round.
export function leafFront(angle) {
  return Math.max(0, Math.min(1, (1.1 - Math.abs(angle)) / 0.9))
}

// The leaf's line at one place round the neck, as [out from the neck's middle, height] points: from its fold
// to where its edge rests on the shirt. under: the shirt's surface there, going out from the stand ([out,
// height], nearest first). The edge rests on the shirt where that's `long` from the fold (straight); from the
// fold to there the leaf is taut, over anything that stands above that line (a shoulder's rise): it stands a
// little off the stand's foot, as a collar's roll does, and never off the shirt at its edge. Where the shirt
// is never that far (it ran out), the leaf ends at its last point.
export function leafLine(fold, under, long) {
  const far = q => Math.hypot(q[0] - fold[0], q[1] - fold[1])
  let end = under[under.length - 1] ?? fold, reached = under.length - 1
  for (let k = 0; k < under.length; k++) {
    if (far(under[k]) < long) continue
    const before = k ? under[k - 1] : fold, f = (long - far(before)) / Math.max(1e-9, far(under[k]) - far(before))
    end = [before[0] + (under[k][0] - before[0]) * f, before[1] + (under[k][1] - before[1]) * f]
    reached = k - 1
    break
  }
  const line = [fold]
  for (const q of [...under.slice(0, reached + 1), end]) {
    // (The tight line over them: a point under the line from the one before it to the next is dropped.)
    while (line.length >= 2) {
      const a = line[line.length - 2], b = line[line.length - 1]
      if ((b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0]) < 0) break
      line.pop()
    }
    line.push(q)
  }
  return line
}

// A point `share` of the way along a line of [out, height] points, by length, no further than `long` along it.
export function alongLine(line, share, long) {
  let total = 0
  const lengths = [0]
  for (let k = 1; k < line.length; k++) lengths.push((total += Math.hypot(line[k][0] - line[k - 1][0], line[k][1] - line[k - 1][1])))
  const want = Math.min(share * long, total)
  let k = 1
  while (k < line.length - 1 && lengths[k] < want) k++
  if (line.length < 2) return line[0]
  const f = lengths[k] > lengths[k - 1] ? (want - lengths[k - 1]) / (lengths[k] - lengths[k - 1]) : 0
  return [line[k - 1][0] + (line[k][0] - line[k - 1][0]) * f, line[k - 1][1] + (line[k][1] - line[k - 1][1]) * f]
}

// A garment's surface looked straight down on, for many points at once: its triangles within `reach` of a
// centre (x, z) are put in cells over the floor once, and a point then tries only the few triangles over its
// cell. (A ray cast per point at the whole garment, a hundred thousand triangles a thousand times over, held
// the page for seconds each time a collar was laid.) positions: the garment's points (x, y, z); index: its
// triangles as indices into them, or null where every three points are one; from, to: the part of the index
// that's drawn. Returns (x, z, under) => the height of the highest surface there below `under`, or null where
// there's none.
export function surfaceUnder(positions, index, [cx, cz], reach, { cell = 0.01, from = 0, to = Infinity } = {}) {
  const size = Math.max(1, Math.ceil((2 * reach) / cell)), x0 = cx - reach, z0 = cz - reach
  const cells = new Map()
  const end = Math.min(to, index ? index.length : positions.length / 3)
  for (let t = from; t + 2 < end; t += 3) {
    const a = index ? index[t] : t, b = index ? index[t + 1] : t + 1, c = index ? index[t + 2] : t + 2
    const ax = positions[3 * a], az = positions[3 * a + 2], bx = positions[3 * b], bz = positions[3 * b + 2], qx = positions[3 * c], qz = positions[3 * c + 2]
    const lox = Math.min(ax, bx, qx), hix = Math.max(ax, bx, qx), loz = Math.min(az, bz, qz), hiz = Math.max(az, bz, qz)
    if (!(hix >= x0 && lox <= x0 + 2 * reach && hiz >= z0 && loz <= z0 + 2 * reach)) continue
    const i0 = Math.max(0, Math.floor((lox - x0) / cell)), i1 = Math.min(size - 1, Math.floor((hix - x0) / cell))
    const j0 = Math.max(0, Math.floor((loz - z0) / cell)), j1 = Math.min(size - 1, Math.floor((hiz - z0) / cell))
    for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) {
      let list = cells.get(i * size + j)
      if (!list) cells.set(i * size + j, (list = []))
      list.push(a, b, c)
    }
  }
  return (x, z, under = Infinity) => {
    const i = Math.floor((x - x0) / cell), j = Math.floor((z - z0) / cell)
    if (i < 0 || j < 0 || i >= size || j >= size) return null
    const list = cells.get(i * size + j)
    if (!list) return null
    let best = null
    for (let k = 0; k < list.length; k += 3) {
      const a = 3 * list[k], b = 3 * list[k + 1], c = 3 * list[k + 2]
      const ax = positions[a], az = positions[a + 2], bx = positions[b], bz = positions[b + 2], qx = positions[c], qz = positions[c + 2]
      // Where the point is in the triangle as seen from above (its shares of the three corners).
      const d = (bz - qz) * (ax - qx) + (qx - bx) * (az - qz)
      if (Math.abs(d) < 1e-14) continue
      const u = ((bz - qz) * (x - qx) + (qx - bx) * (z - qz)) / d, v = ((qz - az) * (x - qx) + (ax - qx) * (z - qz)) / d, w = 1 - u - v
      if (u < -1e-9 || v < -1e-9 || w < -1e-9) continue
      const y = u * positions[a + 1] + v * positions[b + 1] + w * positions[c + 1]
      if (y < under && (best === null || y > best)) best = y
    }
    return best
  }
}
