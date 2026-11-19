// An open shoe (a sandal, a slide, a thong, a strappy heel) built as it's made, fitted to its side photo: a footbed
// slab as thick as the photo's sole (on a heel only its top, the stem below carved from the photo as hull.js
// carves it), and the straps as a thin band hugging the foot, a few millimetres off the skin, wherever the side
// photo shows the shoe above the footbed, cut along a smooth line where the photo's strap ends.
//
// hull.js carved these out of a block on a 2.7 mm grid and rounded it: straps came out torn at the edges, holes
// went through where a strap should be, and a strap standing off the foot was a lump. The foot's own surface
// (accessories.js's legSlices) gives the band its shape; the photo gives only where it is.
//
// Metres, in the scene, on hull.js's and last_shape.js's frame, with userData.photo as they set it, so the photos
// are laid on the same way (accessories.js's wrapShoePhoto) and the skin under the straps is hidden (stage.js's
// coverFeet: shoeAt).
import * as THREE from "three"
import { legSlices } from "lib/garments/accessories"
import { lastFrame } from "lib/garments/last_shape"

// The families built this way (lasts.js's), when the side photo shows openings (shoeSide's open mask).
// (Not a pump, tried 8 November: built this way a stiletto's stem came out as wide as the shoe, a wall behind
// the heel seen from the front, and closed pumps and heeled boots passed the toe test (a heel's own stem is its
// tallest part, so its toe looks low beside it) and lost their toes' cover. Heels stay carved.)
export const OPEN_SHAPED = new Set(["sandal", "slide"])
// Points round the footbed's outline, and its profile's layers.
const AROUND = 96
// The band's outside and inside off the skin, and how far the photo's mask is blurred for its edge (pixels).
const OUTSIDE = 0.0036, INSIDE = 0.0012, BLUR = 3
// How tall over its toes, against its tallest, a closed toe stands at least.
const CLOSED = 0.42
// A thong's strap: half its width over the foot (metres on the 1.76 m body).
const THONG = 0.007

// The last open shoe's reading (for the validation runner): its forefoot's closed share.
export const openReading = {}

export function openGeometry(body, frame, side, outline, views, style, { said = false } = {}) {
  for (const k of Object.keys(openReading)) delete openReading[k]
  if (!outline?.open || !outline.w || !outline.h) return null
  const f = lastFrame(body, frame, side, outline, views, style)
  if (!f) return null
  const { s, floor, back, span, centreX, metres, floorLine, yBottom, yTop, halfAt } = f
  // The photo's shoe at a point (u along the shoe, y its height): its mask blurred over a few pixels, so the
  // band's edge runs smoothly between them rather than along the pixels' steps.
  const { open, w, h } = outline
  const pixel = (x, y) => (x >= 0 && y >= 0 && x < w && y < h && open[y * w + x] === 1 ? 1 : 0)
  const maskAt = (u, y) => {
    if (u < 0 || u > 1) return 0
    const xs = outline.toeRight ? outline.left + u * (outline.right - outline.left) : outline.right - u * (outline.right - outline.left)
    const ys = floorLine - (y - floor) / metres
    const px = xs * w - 0.5, py = ys * h - 0.5
    // (Each sample read between its four pixels, so the value runs on smoothly from point to point.)
    let sum = 0, n = 0
    for (let dy = -BLUR; dy <= BLUR; dy++) for (let dx = -BLUR; dx <= BLUR; dx++) {
      const x = px + dx, yy = py + dy, x0 = Math.floor(x), y0 = Math.floor(yy), tx = x - x0, ty = yy - y0
      sum += (pixel(x0, y0) * (1 - tx) + pixel(x0 + 1, y0) * tx) * (1 - ty) + (pixel(x0, y0 + 1) * (1 - tx) + pixel(x0 + 1, y0 + 1) * tx) * ty
      n++
    }
    return sum / n
  }
  // A shoe closed over the toes (a clog, a sneaker mule, a fisherman sandal), however open its back or its sides
  // behind them, isn't a footbed and straps: its toe box stands off the toes, and the hull carves it.
  const closed = closedFore(yTop, yBottom)
  openReading.closed = +closed.toFixed(3)
  // (Unless the listing's own words say it's a sandal, a slide or a mule: a sandal's toe strap can stand as tall
  // as a toe box. Only one closed nearly as tall as the whole shoe is left to the carver then.)
  if (closed > (said ? 0.8 : CLOSED)) return null
  // The sole's top: the photo's sole line, unless its colour couldn't be read apart from the strap's (a rubber
  // flip-flop all one colour), when it falls to its floor (last_shape.js keeps it 6 mm up): then the shoe's
  // thinnest, where only its sole shows (the heel of a flip-flop, the toes of a slide), if it's no thicker than a
  // platform's 3 cm (a shoe covered heel to toe shows no sole on its own).
  let thinnest = Infinity
  for (let u = 0.05; u <= 0.95; u += 0.01) thinnest = Math.min(thinnest, yTop(u) - yBottom(u))
  const misread = u => thinnest < 0.03 * s && f.ySole(u) - yBottom(u) < 0.0065 * s
  const ySole = u => (misread(u) ? yBottom(u) + thinnest : f.ySole(u))
  // --- The footbed: as thick as the photo's sole, but on a heel only the forepart's thickness (the stem is
  // carved below it).
  let fore = 0, foreN = 0
  for (let u = 0.6; u <= 0.9; u += 0.02) { fore += ySole(u) - yBottom(u); foreN++ }
  const thickest = Math.max(0.01 * s, (fore / foreN) * 1.3)
  // (At its very ends the slab keeps the thickness it has just in from them: the photo's sole rounds up to its
  // toe's tip and its heel's back, and a slab following it there curls into a thin flap.)
  const inEnds = u => Math.min(0.93, Math.max(0.05, u))
  const heeled = (style.heel ?? 0) > 0.02
  // A heel's footbed: the photo's underside from the arch forward; behind the arch's highest point (where the
  // stem begins and the photo's underside drops to the floor) the arch's line carried on up to the heel's back,
  // no higher than the photo's shoe there less the bed's thickness. Its top is the bed's thickness over that.
  // The underside: the photo's, bridged over the stem. The bridge is the tightest line over the photo's underside
  // from the heel's back to the ball (its upper hull); where the photo's underside falls well below that (the
  // stem, standing on the floor) the footbed keeps to the bridge.
  const hull = []
  if (heeled) {
    for (let u = 0.03; u <= 0.62; u += 0.01) {
      const pt = [u, yBottom(u)]
      while (hull.length >= 2) {
        const [a, c] = [hull[hull.length - 2], hull[hull.length - 1]]
        if ((c[0] - a[0]) * (pt[1] - a[1]) - (c[1] - a[1]) * (pt[0] - a[0]) >= 0) hull.pop(); else break
      }
      hull.push(pt)
    }
  }
  const bridge = u => {
    const v = Math.min(0.62, Math.max(0.03, u))
    for (let k = 0; k + 1 < hull.length; k++) if (v <= hull[k + 1][0]) { const [a, c] = [hull[k], hull[k + 1]]; return a[1] + (c[1] - a[1]) * (v - a[0]) / (c[0] - a[0] || 1) }
    return hull.length ? hull[hull.length - 1][1] : yBottom(u)
  }
  const seat = Math.min(thickest, 0.012 * s)
  const under = u => {
    if (u > 0.62) return yBottom(u)
    const line = bridge(u), own = yBottom(Math.max(0.03, u))
    // (Eased from the photo's own underside to the bridge as it falls 5 to 15 mm below it.)
    const w = Math.min(1, Math.max(0, (line - own - 0.005 * s) / (0.01 * s)))
    return own + (line - own) * w
  }
  // The photo's own footbed (where its straps are read from): its sole's top; on a heel the seat's thickness over
  // its underside, eased to the sole's top at the ball.
  const photoBed = u => {
    if (!heeled) return ySole(inEnds(u))
    const v = inEnds(u), w = Math.min(1, Math.max(0, (v - 0.5) / 0.15))
    return (under(v) + seat) * (1 - w) + Math.max(ySole(v), under(v) + 0.004 * s) * w
  }
  // A heel's footbed is built under the mannequin's foot as it stands pitched, not where the photo's stands: the
  // foot's own underside along the shoe (the lowest of the skin at each point along), no lower than the forepart's
  // sole. The photo's heel can be higher than the foot is pitched, and a footbed at the photo's height stood
  // clear of the foot, behind and above its heel.
  const BINS = 100, lowest = new Float32Array(BINS).fill(Infinity)
  if (heeled) {
    for (let i = 0; i < body.positions.length / 3; i++) {
      const x = body.positions[3 * i], y = body.positions[3 * i + 1], u = (body.positions[3 * i + 2] - back) / span
      if ((side === "L") !== x > 0 || y > floor + 0.2 * s || u < 0 || u >= 1 || Math.abs(x - centreX) > 0.07 * s) continue
      const k = Math.floor(u * BINS)
      lowest[k] = Math.min(lowest[k], y)
    }
    for (let k = 1; k < BINS; k++) if (!Number.isFinite(lowest[k])) lowest[k] = lowest[k - 1]
    for (let k = BINS - 2; k >= 0; k--) if (!Number.isFinite(lowest[k])) lowest[k] = lowest[k + 1]
    // (The lowest over a few points along: a point with few of the skin's corners in it reads high.)
    const raw = Float32Array.from(lowest)
    for (let k = 0; k < BINS; k++) for (let d = -3; d <= 3; d++) if (k + d >= 4 && k + d < BINS) lowest[k] = Math.min(lowest[k], raw[k + d])
  }
  const footUnder = u => {
    let sum = 0, n = 0
    for (let k = Math.floor(u * BINS) - 7; k <= Math.floor(u * BINS) + 7; k++) if (k >= 5 && k < BINS && Number.isFinite(lowest[k])) { sum += lowest[k]; n++ }
    return n ? sum / n : floor
  }
  const foreSole = Math.min(0.03 * s, Math.max(0.006 * s, fore / foreN))
  const bedTop = u => (heeled ? Math.max(floor + foreSole, footUnder(inEnds(u))) : ySole(inEnds(u)))
  // (Only a heel has a stem under its footbed: where the photo's underside stands on the floor, well under the
  // bridge. A wedge or a platform has none: its footbed is solid to the floor.)
  let stemFrom = null, stemTo = null
  if (heeled) for (let u = 0.03; u <= 0.5; u += 0.01) if (bridge(u) - yBottom(u) > 0.015 * s) { stemFrom ??= u; stemTo = u }
  const stemmed = stemFrom != null
  const bedBottom = u => (heeled ? (stemmed ? Math.max(floor, bedTop(u) - Math.max(seat, foreSole)) : floor) : yBottom(inEnds(u)))
  const positions = [], soleIndex = [], strapIndex = [], painted = []
  slab(positions, soleIndex, { back, span, centreX, halfAt: u => halfAt(u) * 1.04 + 0.002 * s, bottom: bedBottom, top: bedTop, bevel: 0.0025 * s })
  // (Wound outward: a closed slab wound the other way has a negative volume.)
  if (volume(positions, soleIndex) < 0) for (let t = 0; t < soleIndex.length; t += 3) { const b = soleIndex[t + 1]; soleIndex[t + 1] = soleIndex[t + 2]; soleIndex[t + 2] = b }
  // --- The stem (a heel's, a wedge's): the photo's shoe below the footbed, carved as hull.js carves it.
  if (stemmed) {
    // Where it stands: the photo's first stretch on the floor from the heel (its tip), when that ends well before
    // the ball's; else the middle of where the underside drops under the bridge (on a steep sandal that runs on
    // under the arch, and the stem stood under the arch, not the heel).
    let tipFrom = null, tipTo = null
    for (let u = 0.02; u <= 0.45; u += 0.005) {
      if (yBottom(u) - floor < 0.012 * s) { tipFrom ??= u; tipTo = u } else if (tipFrom != null) break
    }
    const mid = tipFrom != null && tipTo < 0.4 ? (tipFrom + tipTo) / 2 : (stemFrom + stemTo) / 2
    stemRings(positions, soleIndex, { maskAt, under, floor, back, span, centreX, halfAt, s, mid, reach: bedBottom(mid) + 0.004 * s })
  }
  // --- The straps: the skin's slices, offset out along the surface's normal, kept where the photo shows shoe.
  const top = floor + Math.min(0.32 * s, Math.max(...Array.from({ length: 21 }, (_, k) => yTop(k / 20))) - floor + 0.02 * s)
  // (A finer grid than a sock's: 2.5 mm up and 192 round, about 4 mm apart along a foot's side; at the sock's
  // 64 round the band's cut edges stepped a centimetre at a time down the foot's long sides.)
  const slices = legSlices(body, frame, side, top, { step: 0.0025, around: 192 })
  const rows = slices.rows, around = slices.reach[0].length
  const skin = new Float32Array(rows * around * 3)
  for (let k = 0; k < rows; k++) for (let j = 0; j < around; j++) {
    const a = (j / around) * 2 * Math.PI, c = slices.centres[k], r = slices.reach[k][j]
    const o = 3 * (k * around + j)
    skin[o] = c[0] + r * Math.sin(a); skin[o + 1] = floor + k * slices.step; skin[o + 2] = c[1] + r * Math.cos(a)
  }
  const normal = gridNormals(skin, rows, around)
  // Each point's share of shoe: the photo's, from just inside the footbed's top (the band meets the bed with no
  // gap). What faces up (over the instep, the toes) also takes the photo's strap a little below it: the
  // mannequin's instep stands higher than a foot in the photographed shoe, and the strap's top would otherwise
  // be cut through, the skin showing in it.
  // A thong's strap (a flip-flop's): from the photo's side only a band rising from the sole to the toe post, but
  // over the foot a V, from the post between the toes back and out to the sole's edges. The band's front (the
  // post) and back (where it meets the sole) read from the photo; a point is strap only near the V there.
  const thong = style.thong ? thongPlan(maskAt, photoBed, s) : null
  openReading.thong = thong
  const onThong = (x, u) => {
    if (!thong) return 1
    const along = Math.min(1, Math.max(0, (thong.front - u) / (thong.front - thong.back)))
    const off = Math.abs(Math.abs(x - centreX) - along * halfAt(Math.min(1, Math.max(0, u))))
    return 1 - Math.min(1, Math.max(0, (off - THONG * s) / (THONG * s)))
  }
  // Where the photo's shoe is, for a point on the skin. The photo shows the shoe empty and from the side: a strap
  // seen standing over the footbed there goes over the foot, and the mannequin's foot isn't the height the strap
  // stands in the photo. So ahead of the leg each point is read at its share of the way up the foot (the footbed
  // to the foot's top, there) against the photo's shoe (the footbed to its top, there): a slide's band covers the
  // foot from its front edge to its back, whatever the instep's height. Round the leg a point is read at its own
  // height, and a strap the photo shows at the ankle's height anywhere behind the instep goes all the way round.
  const skinTop = new Float32Array(BINS).fill(-Infinity), ceiling = floor + (rows - 1) * slices.step
  for (let i = 0; i < rows * around; i++) {
    const u = (skin[3 * i + 2] - back) / span
    if (u < 0 || u >= 1) continue
    const b = Math.floor(u * BINS)
    skinTop[b] = Math.max(skinTop[b], skin[3 * i + 1])
  }
  let leg = 0
  for (let b = 0; b < BINS; b++) if (skinTop[b] >= ceiling - 0.006 * s) leg = (b + 1) / BINS
  const squeeze = new Float32Array(BINS).fill(1)
  for (let b = 0; b < BINS; b++) {
    const u = (b + 0.5) / BINS, shown = yTop(u) - photoBed(u), foot = skinTop[b] - bedTop(u)
    // (Not where the photo's shoe stands far over the foot: an ankle strap, in the air ahead of the leg.)
    if (shown > 0.02 * s && foot > 0.01 * s && shown < foot * 1.6 && u > leg) squeeze[b] = Math.max(0.35, shown / foot)
  }
  const squeezeAt = u => {
    let sum = 0, n = 0
    for (let b = Math.floor(u * BINS) - 3; b <= Math.floor(u * BINS) + 3; b++) if (b >= 0 && b < BINS) { sum += squeeze[b]; n++ }
    const w = Math.min(1, Math.max(0, (u - leg) / 0.1))
    return 1 + ((n ? sum / n : 1) - 1) * w * w * (3 - 2 * w)
  }
  // (The photo's strap at each height behind the instep: how much, and where along.)
  // (Read on the photo as far over its footbed as the row is over the built one, at the heel.)
  const lift = photoBed(0.15) - bedTop(0.15)
  const ring = new Float32Array(rows), ringAt = new Float32Array(rows)
  for (let k = 0; k < rows; k++) {
    const y = floor + k * slices.step + lift
    // (A strap running along, an eighth of the shoe's length or more in one piece: one standing up from the heel,
    // or two crossing, is no ring.)
    let best = 0, bestAt = 0, run = 0, longest = 0
    for (let u = 0; u <= 0.5; u += 0.01) {
      const m = y - photoBed(u) > 0.08 * s ? maskAt(u, y) : 0
      run = m > 0.5 ? run + 1 : 0
      if (run > longest) { longest = run; best = m; bestAt = u - 0.01 * Math.floor(run / 2) }
    }
    if (longest >= 13) { ring[k] = Math.max(0.6, best); ringAt[k] = bestAt }
  }
  // The strap in the photo's column nearest a height (a thong's arm, whose V over the foot the side doesn't show).
  const strapNear = (u, y) => {
    for (let d = 0; d <= 0.04 * s; d += 0.0015 * s) for (const q of [y + d, y - d]) if (q > photoBed(u) && maskAt(u, q) > 0.5) return q
    return y
  }
  const value = new Float32Array(rows * around), seen = new Float32Array(rows * around * 3)
  for (let k = 0; k < rows; k++) for (let j = 0; j < around; j++) {
    const i = k * around + j, o = 3 * i, y = skin[o + 1], u = (skin[o + 2] - back) / span
    seen[o] = u; seen[o + 1] = y
    if (u < 0 || u > 1) continue
    const bed = bedTop(u), seen0 = photoBed(u), above = (y - bed + 0.002 * s) / (0.004 * s)
    // (The photo's shoe a little over the footbed's top is its insole and seat, not a strap.)
    if (above <= 0 || yTop(u) - seen0 < 0.012 * s) continue
    let read = seen0 + (y - bed) * squeezeAt(u), along = u
    // (A thin strap keeps a few millimetres' width: read a little up and down too.)
    let m = Math.max(maskAt(u, read), 0.85 * maskAt(u, read + 0.002 * s), 0.85 * maskAt(u, read - 0.002 * s))
    if (u < leg + 0.05 && ring[k] > m) { m = ring[k]; along = ringAt[k]; read = y + lift }
    const on = onThong(skin[o], u)
    // (A thong's V is painted from the middle of the photo's arm.)
    if (thong && on > 0) {
      along = (thong.front + thong.back) / 2
      // (The arm's own middle there: down from the photo's top through its topmost run of shoe.)
      let from = yTop(along) - 0.001 * s
      while (from > photoBed(along) && maskAt(along, from) <= 0.5) from -= 0.001 * s
      let to = from
      while (to > photoBed(along) && maskAt(along, to) > 0.5) to -= 0.001 * s
      read = (from + to) / 2
    }
    seen[o] = along; seen[o + 1] = read
    value[i] = m * Math.min(1, above) * on
  }
  const outer = [], inner = []
  for (let i = 0; i < rows * around; i++) for (const [list, off] of [[outer, OUTSIDE], [inner, INSIDE]]) list.push(skin[3 * i] + normal[3 * i] * off * s, skin[3 * i + 1] + normal[3 * i + 1] * off * s, skin[3 * i + 2] + normal[3 * i + 2] * off * s)
  const band = clipBand(rows, around, value)
  if (band.triangles.length) {
    // The band's points (the grid's and those cut on its edges), outside then inside.
    const at = (layer, pt) => {
      if (pt.length === 1) return layer.slice(3 * pt[0], 3 * pt[0] + 3)
      const [a, b, t] = pt
      return [0, 1, 2].map(d => layer[3 * a + d] * (1 - t) + layer[3 * b + d] * t)
    }
    const base = positions.length / 3, count = band.points.length
    for (const pt of band.points) positions.push(...at(outer, pt))
    for (const pt of band.points) positions.push(...at(inner, pt))
    // (Each of the band's points, where it's read on the photo: accessories.js's wrapShoePhoto paints it from there.)
    for (let layer = 0; layer < 2; layer++) band.points.forEach((pt, q) => { const [u, y] = at(seen, pt); painted.push(base + layer * count + q, u, y) })
    // Each triangle wound to face out (along the skin's normal there), its twin on the inside facing in.
    const P = i => positions.slice(3 * (base + i), 3 * (base + i) + 3)
    const N = i => at(normal, band.points[i])
    for (let [a, b, c] of band.triangles) {
      const A = P(a), B = P(b), C = P(c), n0 = N(a)
      const e1 = [B[0] - A[0], B[1] - A[1], B[2] - A[2]], e2 = [C[0] - A[0], C[1] - A[1], C[2] - A[2]]
      const face = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]]
      if (face[0] * n0[0] + face[1] * n0[1] + face[2] * n0[2] < 0) [b, c] = [c, b]
      strapIndex.push(base + a, base + b, base + c, base + count + a, base + count + c, base + count + b)
    }
    // Its edges closed: a strip from outside to inside along every edge the band has on one side only (both
    // ways round: the strip is a millimetre or two wide, seen edge on).
    for (const [a, b] of band.edges) strapIndex.push(base + a, base + count + a, base + count + b, base + a, base + count + b, base + b, base + a, base + count + b, base + count + a, base + a, base + b, base + count + b)
  }
  if (!strapIndex.length && !soleIndex.length) return null
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3))
  geometry.setIndex([...soleIndex, ...strapIndex])
  geometry.addGroup(0, soleIndex.length, 0)
  geometry.addGroup(soleIndex.length, strapIndex.length, 1)
  geometry.computeVertexNormals()
  // Where each of the straps' points is on the photo (its x and y as shares of it), NaN for the rest.
  const photoUV = new Float32Array((positions.length / 3) * 2).fill(NaN)
  for (let q = 0; q < painted.length; q += 3) {
    const u = Math.min(0.99, Math.max(0.01, painted[q + 1]))
    photoUV[2 * painted[q]] = outline.toeRight ? outline.left + u * (outline.right - outline.left) : outline.right - u * (outline.right - outline.left)
    photoUV[2 * painted[q] + 1] = floorLine - (painted[q + 2] - floor) / metres
  }
  geometry.userData.photoUV = photoUV
  const shoeAt = () => false
  // The skin under a strap, well inside its edges, isn't drawn (stage.js's coverFeet): the mannequin's toes and
  // ankle bone stand proud of the smooth slices the band is built on.
  const covers = (x, y, z) => {
    const k = Math.round((y - floor) / slices.step)
    if (k < 0 || k >= rows) return false
    const c = slices.centres[k], j = ((Math.round((Math.atan2(x - c[0], z - c[1]) / (2 * Math.PI)) * around) % around) + around) % around
    for (const dj of [-2, 0, 2]) for (const dk of [-1, 0, 1]) {
      const kk = k + dk
      if (kk < 0 || kk >= rows || value[kk * around + ((j + dj + around) % around)] < 0.9) return false
    }
    return true
  }
  let widest = 0
  for (let u = 0; u <= 1; u += 0.02) widest = Math.max(widest, halfAt(u) * 1.04 + 0.002 * s)
  const within = (x, y, z) => {
    const u = (z - back) / span
    if (u < 0 || u > 1 || Math.abs(x - centreX) > widest + 0.01 * s) return false
    return (y >= bedBottom(u) - 0.002 * s && y <= bedTop(u) && Math.abs(x - centreX) <= halfAt(u) * 1.04) || (y > bedTop(u) && shoeAt(u, y))
  }
  geometry.userData.photo = {
    floor, back, length: span, metres, top: u => yTop(Math.min(1, Math.max(0, u))), within, centreX, widest, open: true, shoeAt, covers,
    hull: { open: style.family, stem: stemmed, heeled, straps: strapIndex.length / 3, span: +span.toFixed(3), profile: Array.from({ length: 20 }, (_, k) => { const u = 0.02 + k * 0.05; return [+u.toFixed(2), ...[yBottom(u), heeled ? bridge(u) : 0, bedBottom(u), bedTop(u), photoBed(u), yTop(u)].map(v => Math.round((v - floor) * 1000))] }) }
  }
  return geometry
}

// How tall the photo's shoe stands over its toes (from just behind the tip back toward the ball) against its
// tallest: a closed toe stands about half as tall as the shoe, an open one (the toes out, only the sole under
// them) a third or less.
export function closedFore(yTop, yBottom) {
  const tall = u => yTop(u) - yBottom(u)
  let toe = 0, n = 0, most = 0
  for (let u = 0.84; u <= 0.93; u += 0.01) { toe += tall(u); n++ }
  for (let u = 0.1; u <= 0.9; u += 0.01) most = Math.max(most, tall(u))
  return most > 0 ? toe / n / most : 0
}

// Where a thong's strap runs along the shoe, from the photo: seen from the side the strap's near arm stands as
// an arch over the footbed, from where it meets the sole (back) to near the post between the toes (front). Each
// point along is the strap's height there over the footbed; the arch is where that's near its highest (its low
// ends merge with the sole's own unevenness). The post is the arch's front, kept between the toes' roots (70 to
// 80 % along). null when the photo shows no arch.
export function thongPlan(maskAt, bedTop, s) {
  const heights = []
  for (let u = 0.08; u <= 0.92; u += 0.01) {
    let high = 0
    for (let d = 0.004; d <= 0.08; d += 0.002) if (maskAt(u, bedTop(u) + d * s) > 0.5) high = d
    heights.push([u, high])
  }
  const most = Math.max(...heights.map(([, d]) => d))
  if (most < 0.012) return null
  const arch = heights.filter(([, d]) => d > 0.45 * most).map(([u]) => u)
  const back = arch[0], front = Math.min(0.8, Math.max(0.7, arch[arch.length - 1]))
  return front - back > 0.08 ? { front, back } : null
}

// A slab round a plan (half width along the shoe), from a bottom to a top along it, its edges bevelled: rings of
// points round its outline, from the underside's middle out, round the edge, up the side and in over the top to
// its middle, each side's middle zipped to the other's.
function slab(positions, index, { back, span, centreX, halfAt, bottom, top, bevel }) {
  // The outline: from the heel's middle round the outer side to the toe and back, at even steps along it.
  const dense = []
  for (let k = 0; k <= 400; k++) { const u = (1 - Math.cos((k / 400) * Math.PI)) / 2; dense.push([halfAt(u), u]) }
  const loop = [...dense, ...dense.slice(1, -1).reverse().map(([x, u]) => [-x, u])]
  const arc = [0]
  for (let i = 1; i <= loop.length; i++) { const a = loop[i - 1], b = loop[i % loop.length]; arc.push(arc[i - 1] + Math.hypot((a[0] - b[0]) / span, a[1] - b[1])) }
  const ring = []
  for (let k = 0; k < AROUND; k++) {
    const want = (k / AROUND) * arc[arc.length - 1]
    let i = 1
    while (arc[i] < want) i++
    const t = (want - arc[i - 1]) / (arc[i] - arc[i - 1] || 1), a = loop[i - 1], b = loop[i % loop.length]
    ring.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t])
  }
  // The profile, from the underside's middle out: in over the bottom, round the bottom edge (a quarter round),
  // up the side, round the top edge and in over the top to its middle.
  const layers = []
  for (const inward of [1, 0.6, 0.25]) layers.push({ inward, at: "bottom" })
  for (const angle of [0, 45, 90]) layers.push({ angle, at: "bottom" })
  layers.push({ at: "middle" })
  for (const angle of [90, 45, 0]) layers.push({ angle, at: "top" })
  for (const inward of [0.25, 0.6, 1]) layers.push({ inward, at: "top" })
  const base = positions.length / 3
  for (const { inward = 0, angle, at } of layers) for (const [x, u] of ring) {
    const uc = Math.min(0.94, Math.max(0.06, u)), um = u + (uc - u) * inward
    const b = bottom(um), t = top(um), r = Math.min(bevel, (t - b) / 2.5)
    const a = ((angle ?? 0) * Math.PI) / 180
    const inset = at === "middle" ? 0 : angle === undefined ? r : r * (1 - Math.sin(a))
    const lift = angle === undefined ? 0 : r * (1 - Math.cos(a))
    const y = at === "middle" ? (b + t) / 2 : at === "bottom" ? b + lift : t - lift
    positions.push(centreX + Math.sign(x) * Math.max(0, Math.abs(x) - inset) * (1 - inward), y, back + um * span)
  }
  const L = layers.length
  const id = (l, k) => base + l * AROUND + ((k + AROUND) % AROUND)
  for (let l = 0; l + 1 < L; l++) for (let k = 0; k < AROUND; k++) index.push(id(l, k), id(l + 1, k), id(l + 1, k + 1), id(l, k), id(l + 1, k + 1), id(l, k + 1))
  // The middles zipped: the bottom's (layer 0) and the top's (the last), each point to its mirror.
  const half = AROUND / 2
  for (const [l, flip] of [[0, false], [L - 1, true]]) {
    for (let k = 1; k < half - 1; k++) {
      const q = [id(l, k), id(l, k + 1), id(l, AROUND - k - 1), id(l, AROUND - k)]
      if (flip) index.push(q[0], q[1], q[2], q[0], q[2], q[3])
      else index.push(q[0], q[2], q[1], q[0], q[3], q[2])
    }
    const ends = [[id(l, 0), id(l, 1), id(l, AROUND - 1)], [id(l, half), id(l, half - 1), id(l, half + 1)]]
    for (const [a, b, c] of ends) flip ? index.push(a, b, c) : index.push(a, c, b)
  }
}

// The skin grid's normals (rows of points round the leg), pointing out.
function gridNormals(p, rows, around) {
  const n = new Float32Array(p.length)
  const P = (k, j) => { const o = 3 * (Math.min(rows - 1, Math.max(0, k)) * around + ((j + around) % around)); return [p[o], p[o + 1], p[o + 2]] }
  for (let k = 0; k < rows; k++) for (let j = 0; j < around; j++) {
    const a = P(k, j + 1), b = P(k, j - 1), c = P(k + 1, j), d = P(k - 1, j)
    const t = [a[0] - b[0], a[1] - b[1], a[2] - b[2]], v = [c[0] - d[0], c[1] - d[1], c[2] - d[2]]
    let x = t[1] * v[2] - t[2] * v[1], y = t[2] * v[0] - t[0] * v[2], z = t[0] * v[1] - t[1] * v[0]
    // (Out: away from the slice's middle, or up on the top row.)
    const here = P(k, j), mid = [0, 0, 0]
    for (let jj = 0; jj < around; jj++) { const q = P(k, jj); mid[0] += q[0] / around; mid[2] += q[2] / around }
    if (x * (here[0] - mid[0]) + z * (here[2] - mid[2]) < 0) { x = -x; y = -y; z = -z }
    const l = Math.hypot(x, y, z) || 1
    const o = 3 * (k * around + j)
    n[o] = x / l; n[o + 1] = y / l; n[o + 2] = z / l
  }
  return n
}

// The part of a grid (rows by points round, closed round) where the value is at least a half, cut along the
// line where it crosses a half (between two points, where it would be read there): { points (each [i] a grid
// point, or [i, j, t] a point t of the way from i to j), triangles, edges (on the band's edge, each once) }.
export function clipBand(rows, around, value) {
  const points = [], ids = new Map()
  const grid = i => { const key = `g${i}`; if (!ids.has(key)) { ids.set(key, points.length); points.push([i]) } return ids.get(key) }
  const cut = (i, j) => {
    const [a, b] = i < j ? [i, j] : [j, i], key = `c${a}_${b}`
    if (!ids.has(key)) { const t = (0.5 - value[a]) / (value[b] - value[a]); ids.set(key, points.length); points.push([a, b, t]) }
    return ids.get(key)
  }
  const triangles = []
  const tri = (a, b, c) => {
    const ins = [a, b, c].map(i => value[i] >= 0.5)
    const kept = ins.filter(Boolean).length
    if (kept === 0) return
    if (kept === 3) { triangles.push([grid(a), grid(b), grid(c)]); return }
    // Rotated so the odd one out is first.
    const order = [a, b, c], k = kept === 1 ? ins.indexOf(true) : ins.indexOf(false)
    const [p, q, r] = [order[k], order[(k + 1) % 3], order[(k + 2) % 3]]
    if (kept === 1) triangles.push([grid(p), cut(p, q), cut(p, r)])
    else { const pq = cut(p, q), pr = cut(p, r); triangles.push([pq, grid(q), grid(r)], [pq, grid(r), pr]) }
  }
  for (let k = 0; k + 1 < rows; k++) for (let j = 0; j < around; j++) {
    const a = k * around + j, b = k * around + ((j + 1) % around), c = (k + 1) * around + ((j + 1) % around), d = (k + 1) * around + j
    tri(a, b, c); tri(a, c, d)
  }
  // The edges used by one triangle only, as wound.
  const used = new Map()
  for (const [a, b, c] of triangles) for (const [x, y] of [[a, b], [b, c], [c, a]]) { const key = x < y ? `${x}_${y}` : `${y}_${x}`; used.set(key, (used.get(key) ?? 0) + 1) }
  const edges = []
  for (const [a, b, c] of triangles) for (const [x, y] of [[a, b], [b, c], [c, a]]) if (used.get(x < y ? `${x}_${y}` : `${y}_${x}`) === 1) edges.push([x, y])
  return { points, triangles, edges }
}

function volume(p, index) {
  let v = 0
  for (let t = 0; t < index.length; t += 3) {
    const a = 3 * index[t], b = 3 * index[t + 1], c = 3 * index[t + 2]
    v += p[a] * (p[b + 1] * p[c + 2] - p[b + 2] * p[c + 1]) - p[a + 1] * (p[b] * p[c + 2] - p[b + 2] * p[c]) + p[a + 2] * (p[b] * p[c + 1] - p[b + 1] * p[c])
  }
  return v / 6
}

// A heel's stem, turned from the photo's profile: at each height under the photo's footbed, the photo's shoe from
// its back edge to its front, a rounded section as deep as that and about as wide (a stiletto's is round, a
// block's nearly as wide as the heel's seat), capped underneath. Its heights are scaled so its top meets the
// footbed as built (reach), which follows the foot. When the photo shows no clear stem (a shadow, a stem a pixel
// wide), a plain tapered one.
function stemRings(positions, index, { maskAt, under, floor, back, span, centreX, halfAt, s, mid, reach }) {
  const ROUND = 20
  let rings = []
  const height = under(mid) - floor
  for (let y = floor + 0.0005 * s; y < floor + 0.16 * s; y += 0.003 * s) {
    let from = null, to = null
    // (Only round the stem's own place along the shoe (mid): low down, the photo's mask from the heel forward
    // also takes in the sole at the ball, on the floor, and a stem read from there stood as thick as the forepart,
    // a block under a stiletto.)
    for (let u = Math.max(0, mid - 0.1); u <= Math.min(0.6, mid + 0.1); u += 0.004) {
      const on = y < under(u) - 0.003 * s && maskAt(u, y) > 0.5
      if (on) { from ??= u; to = u } else if (from != null) break
    }
    if (from == null) { if (rings.length) break; continue }
    if (to - from > 0.4) { rings = rings.length < 3 ? [] : rings; break }
    rings.push({ y, from, to })
  }
  // (Down to the floor: a stiletto's tip is lost for its last few rows in the photo's shadow on the floor.)
  if (rings.length >= 3 && rings[0].y > floor + 0.0005 * s) rings.unshift({ ...rings[0], y: floor + 0.0005 * s })
  if (rings.length < 3 || height < 0.01 * s) {
    rings = []
    for (let k = 0; k <= 10; k++) { const t = k / 10, half = (0.012 + 0.03 * t * t * t) / 2; rings.push({ y: floor + t * Math.max(0.01 * s, height), from: mid - half, to: mid + half }) }
  }
  const scale = (reach - floor) / Math.max(0.005 * s, rings[rings.length - 1].y - floor)
  const base = positions.length / 3
  // (Each ring's ends eased over its neighbours': the photo's edge steps a pixel at a time.)
  const eased = rings.map((r, k) => {
    const near = rings.slice(Math.max(0, k - 1), k + 2)
    return { y: floor + (r.y - floor) * scale, from: near.reduce((a, q) => a + q.from, 0) / near.length, to: near.reduce((a, q) => a + q.to, 0) / near.length }
  })
  // Its middle on one straight line from its tip to its top (no more than 3% of the shoe's length off the tip's),
  // and no thinner going up: read row by row from a small photo the stem zigzagged.
  {
    const mids = eased.map(r => (r.from + r.to) / 2), n = eased.length
    const tip = mids.slice(0, Math.max(1, Math.round(n / 4))).reduce((a, b) => a + b, 0) / Math.max(1, Math.round(n / 4))
    const upper = mids.slice(Math.floor(n * 0.6)), head = Math.min(tip + 0.03, Math.max(tip - 0.03, upper.reduce((a, b) => a + b, 0) / upper.length))
    let deep = 0
    eased.forEach((r, k) => {
      deep = Math.max(deep, Math.min(0.09, r.to - r.from))
      const at = tip + (head - tip) * (k / Math.max(1, n - 1))
      r.from = at - deep / 2; r.to = at + deep / 2
    })
  }
  // (Carried up into the footbed, so no gap shows under it.)
  const last = eased[eased.length - 1]
  eased.push({ y: last.y + 0.006 * s, from: last.from, to: last.to })
  for (const r of eased) {
    const at = (r.from + r.to) / 2, deep = Math.max(0.003 * s, ((r.to - r.from) / 2) * span)
    const wide = Math.min(halfAt(Math.max(0.05, at)) * 0.92, Math.max(0.0035 * s, deep * 1.1))
    // (A block's corners squarer than a stiletto's round.)
    const power = deep > 0.012 * s ? 3.5 : 2
    for (let j = 0; j < ROUND; j++) {
      const a = (j / ROUND) * 2 * Math.PI, c = Math.cos(a), d = Math.sin(a)
      const r2 = 1 / Math.pow(Math.pow(Math.abs(c), power) + Math.pow(Math.abs(d), power), 1 / power)
      positions.push(centreX + wide * r2 * d, r.y, back + at * span + deep * r2 * c)
    }
  }
  const id = (k, j) => base + k * ROUND + ((j + ROUND) % ROUND)
  const part = []
  for (let k = 0; k + 1 < eased.length; k++) for (let j = 0; j < ROUND; j++) part.push(id(k, j), id(k + 1, j), id(k + 1, j + 1), id(k, j), id(k + 1, j + 1), id(k, j + 1))
  for (let j = 1; j + 1 < ROUND; j++) part.push(id(0, 0), id(0, j + 1), id(0, j))
  // (Wound outward, as the slab is.)
  if (volumeOpen(positions, part, eased.length - 1, id, ROUND) < 0) for (let t = 0; t < part.length; t += 3) { const b = part[t + 1]; part[t + 1] = part[t + 2]; part[t + 2] = b }
  for (const i of part) index.push(i)
  return true
}

// A capped tube's volume, its open top closed for the count.
function volumeOpen(p, part, topRing, id, round) {
  const closed = part.slice()
  for (let j = 1; j + 1 < round; j++) closed.push(id(topRing, 0), id(topRing, j), id(topRing, j + 1))
  return volume(p, closed)
}
