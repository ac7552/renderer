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
import { hullGeometry } from "lib/garments/hull"
import { lastFrame } from "lib/garments/last_shape"

// The families built this way (lasts.js's), when the side photo shows openings (shoeSide's open mask).
export const OPEN_SHAPED = new Set(["sandal", "slide"])
// Points round the footbed's outline, and its profile's layers.
const AROUND = 96
// The band's outside and inside off the skin, and how far the photo's mask is blurred for its edge (pixels).
const OUTSIDE = 0.0028, INSIDE = 0.0006, BLUR = 3
// How tall over its toes, against its tallest, a closed toe stands at least.
const CLOSED = 0.42
// A thong's strap: half its width over the foot (metres on the 1.76 m body).
const THONG = 0.007

// The last open shoe's reading (for the validation runner): its forefoot's closed share.
export const openReading = {}

export function openGeometry(body, frame, side, outline, views, style) {
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
  if (closed > CLOSED) return null
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
  const bedTop = u => ySole(inEnds(u))
  const bedBottom = u => (heeled ? Math.max(yBottom(inEnds(u)), ySole(inEnds(u)) - thickest) : yBottom(inEnds(u)))
  // (Only a heel has a stem under its footbed: a flat sandal's thick heel is its sole.)
  let stemmed = false
  if (heeled) for (let u = 0; u <= 0.4; u += 0.02) if (bedBottom(u) > yBottom(u) + 0.01 * s) stemmed = true
  const positions = [], soleIndex = [], strapIndex = []
  slab(positions, soleIndex, { back, span, centreX, halfAt: u => halfAt(u) * 1.04 + 0.002 * s, bottom: bedBottom, top: bedTop, bevel: 0.0025 * s })
  // (Wound outward: a closed slab wound the other way has a negative volume.)
  if (volume(positions, soleIndex) < 0) for (let t = 0; t < soleIndex.length; t += 3) { const b = soleIndex[t + 1]; soleIndex[t + 1] = soleIndex[t + 2]; soleIndex[t + 2] = b }
  // --- The stem (a heel's, a wedge's): the photo's shoe below the footbed, carved as hull.js carves it.
  if (stemmed) {
    const stem = hullGeometry(body, frame, side, outline, views, style, { only: (u, y) => y < bedBottom(u) + 0.002 * s })
    if (stem) {
      const p = stem.attributes.position.array, base = positions.length / 3
      for (let i = 0; i < p.length; i++) positions.push(p[i])
      for (const i of stem.index.array) soleIndex.push(base + i)
    }
  }
  // --- The straps: the skin's slices, offset out along the surface's normal, kept where the photo shows shoe.
  const top = floor + Math.min(0.32 * s, Math.max(...Array.from({ length: 21 }, (_, k) => yTop(k / 20))) - floor + 0.02 * s)
  const slices = legSlices(body, frame, side, top)
  const rows = slices.rows, around = slices.reach[0].length
  const skin = new Float32Array(rows * around * 3)
  for (let k = 0; k < rows; k++) for (let j = 0; j < around; j++) {
    const a = (j / around) * 2 * Math.PI, c = slices.centres[k], r = slices.reach[k][j]
    const o = 3 * (k * around + j)
    skin[o] = c[0] + r * Math.sin(a); skin[o + 1] = floor + k * 0.005; skin[o + 2] = c[1] + r * Math.cos(a)
  }
  const normal = gridNormals(skin, rows, around)
  // Each point's share of shoe: the photo's, from just inside the footbed's top (the band meets the bed with no
  // gap). What faces up (over the instep, the toes) also takes the photo's strap a little below it: the
  // mannequin's instep stands higher than a foot in the photographed shoe, and the strap's top would otherwise
  // be cut through, the skin showing in it.
  // A thong's strap (a flip-flop's): from the photo's side only a band rising from the sole to the toe post, but
  // over the foot a V, from the post between the toes back and out to the sole's edges. The band's front (the
  // post) and back (where it meets the sole) read from the photo; a point is strap only near the V there.
  const thong = style.thong ? thongPlan(maskAt, bedTop, s) : null
  openReading.thong = thong
  const onThong = (x, u) => {
    if (!thong) return 1
    const along = Math.min(1, Math.max(0, (thong.front - u) / (thong.front - thong.back)))
    const off = Math.abs(Math.abs(x - centreX) - along * halfAt(Math.min(1, Math.max(0, u))))
    return 1 - Math.min(1, Math.max(0, (off - THONG * s) / (THONG * s)))
  }
  const value = new Float32Array(rows * around)
  for (let k = 0; k < rows; k++) for (let j = 0; j < around; j++) {
    const i = k * around + j, o = 3 * i, y = skin[o + 1], u = (skin[o + 2] - back) / span
    if (u < 0 || u > 1) continue
    const above = (y - bedTop(u) + 0.002 * s) / (0.004 * s)
    if (above <= 0) continue
    let m = maskAt(u, y)
    const up = normal[o + 1]
    if (up > 0.4) for (const d of [0.006, 0.012, 0.018]) m = Math.max(m, maskAt(u, y - d * s) * Math.min(1, (up - 0.4) / 0.3))
    value[i] = m * Math.min(1, above) * onThong(skin[o], u)
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
  const shoeAt = (u, y) => maskAt(Math.min(1, Math.max(0, u)), y) > 0.5
  let widest = 0
  for (let u = 0; u <= 1; u += 0.02) widest = Math.max(widest, halfAt(u) * 1.04 + 0.002 * s)
  const within = (x, y, z) => {
    const u = (z - back) / span
    if (u < 0 || u > 1 || Math.abs(x - centreX) > widest + 0.01 * s) return false
    return (y >= bedBottom(u) - 0.002 * s && y <= bedTop(u) && Math.abs(x - centreX) <= halfAt(u) * 1.04) || (y > bedTop(u) && shoeAt(u, y))
  }
  geometry.userData.photo = {
    floor, back, length: span, metres, top: u => yTop(Math.min(1, Math.max(0, u))), within, centreX, widest, open: true, shoeAt,
    hull: { open: style.family, stem: stemmed, straps: strapIndex.length / 3, span: +span.toFixed(3) }
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
