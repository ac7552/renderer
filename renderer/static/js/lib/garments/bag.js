// A bag, at its real size, on the mannequin: a backpack on the back, a belt bag or a sling across the chest, a
// crossbody at the hip, anything else (a tote, a duffle, a clutch) carried in the hand.
//
// The bag's body is a soft shape as wide and tall as its listing says (or its kind's usual, when it doesn't),
// with the outline its shop photo shows once its handles and straps are taken away (print.js's bagShape), as
// deep as the listing says, rounded at its edges. The photo is laid on its front, and turned round on its back
// (a bag's two faces are made alike), its outline's edge round its sides. Its straps aren't the photo's: they're built where they'd lie on this body, over whatever it wears:
// a strap is taut, so its line is the tight outline (the convex hull) of the body and the cloth along its way.
// (A hobo's loop, which is one with its body, is the photo's: its horns a card cut from the photo, its strap
// where the photo's stands and as wide: bagSurface's card, loopStrap.)
//
// Metres, in the scene: y up, the body facing +z, its left at +x. Pure but for the geometries at the end.
import * as THREE from "three"
import { convexHull } from "lib/garments/body"

// A kind's usual size when its listing gives none: width, height, depth (cm).
export const BAG_USUAL = { backpack: [30, 44, 15], sling: [28, 15, 8], crossbody: [23, 17, 7], duffle: [52, 28, 26], tote: [38, 34, 13], clutch: [26, 16, 4] }
// The ways each can be carried, its usual first: "back", "chest" (lying along a strap across the chest), "hip"
// (hanging at the hip from a strap across the body), "shoulder" (hung from one shoulder, under the arm) or
// "hand". The wearer picks among them (the page's "Bag" switch).
export const BAG_WAYS = { backpack: ["back", "hand"], sling: ["chest"], crossbody: ["hip", "shoulder", "hand"], duffle: ["hand", "shoulder"], tote: ["hand", "shoulder"], clutch: ["hand"] }
// How each is worn when nothing's picked.
export const BAG_WORN = Object.fromEntries(Object.entries(BAG_WAYS).map(([style, ways]) => [style, ways[0]]))
// The way a bag of this kind is carried: the one asked for, when it's one of its ways; else its usual. shape:
// the photo's (print.js's bagShape): a bag whose handle is one long loop (a hobo) goes on the shoulder.
export function bagWay(style, asked = null, shape = null) {
  const ways = BAG_WAYS[style] ?? BAG_WAYS.tote
  if (ways.includes(asked)) return asked
  return shape?.loop && (shape.loop.high ?? 0) > 0.6 && ways.includes("shoulder") ? "shoulder" : ways[0]
}
// How far under the shoulder's top a bag hung from it has its own top (m): the listing's drop, or the photo's
// handles, within what goes over a shoulder and round an arm; a crossbody's long strap, or a hobo's long loop,
// lets it down to the hip. s: the body's height against 1.76 m.
export function shoulderFall(style, size, shape, drop = null, s = 1) {
  const long = style === "crossbody", loop = Boolean(shape?.loop)
  // (A hobo's horns are stiff: it hangs by all its loop's height.)
  const fall = drop ? drop / 100 : long ? 0.48 * s : (shape?.handle ?? 0.6) * size.height * (shape?.loop?.horns ? 1 : 0.85)
  return Math.min((long || loop ? 0.56 : 0.36) * s, Math.max((long ? 0.4 : 0.2) * s, fall))
}
// A loop handle's strap (a hobo's): where its two ends stand (at: m from the bag's middle, the photo's left
// first; up: m over the bag's top: on it, or at the tips of its horns) and how wide the strap is from one to
// the other, point by point: as wide as the photo shows at each end, narrowing to its strap's width a third of
// the way along. top: the loop's own top in the photo, as its ends are (where it hangs from).
function loopStrap(shape, size, count, s) {
  const { feet, wide, thin, apex } = shape.loop
  const narrow = Math.max(0.018 * s, Math.min(0.06 * s, thin * size.width))
  const ends = wide.map(v => Math.max(narrow, Math.min(0.42, v) * size.width))
  const width = []
  for (let k = 0; k < count; k++) {
    const t = k / (count - 1), near = Math.min(t, 1 - t), end = t < 0.5 ? ends[0] : ends[1]
    width.push(narrow + (end - narrow) * Math.pow(Math.max(0, 1 - near / 0.3), 1.6))
  }
  const across = x => (Math.min(0.98, Math.max(0.02, x)) - 0.5) * size.width
  return { at: feet.map(q => across(q[0])), up: feet.map(q => q[1] * size.height), width, top: [across(apex[0]), apex[1] * size.height] }
}
// A point of the bag's own frame (x across, y up from its bottom, z through it) where the bag is: in the scene.
export function placed(place, size, [lx, ly, lz]) {
  const cy = Math.cos(place.yaw), sy = Math.sin(place.yaw), cr = Math.cos(place.roll ?? 0), sr = Math.sin(place.roll ?? 0)
  // (Lying along a strap, it turns about its own middle; hanging, about its bottom's.)
  const y0 = ly - (place.centred ? size.height / 2 : 0)
  const x = lx * cr - y0 * sr, y = lx * sr + y0 * cr
  let out = [place.position[0] + x * cy + lz * sy, place.position[1] + y, place.position[2] - x * sy + lz * cy]
  // What stands over its top leans to where it hangs from (a hobo's horns, to the shoulder): by more the higher.
  const lean = place.lean
  if (lean && ly > size.height) {
    const by = Math.min(1.15, (ly - size.height) / lean.rise)
    out = out.map((v, d) => v + lean.shift[d] * by)
  }
  return out
}
// A hobo's loop hung from a point (the shoulder's top, the hand): its top, as the photo has it over the bag,
// brought there. What stands over the bag's top leans with it (placed).
function hung(place, size, loop, to) {
  if (!(loop.top[1] > 0.02)) return place
  const from = placed(place, size, [loop.top[0], size.height + loop.top[1], 0])
  return { ...place, lean: { rise: loop.top[1], shift: to.map((v, d) => v - from[d]) } }
}
// On a shoulder, a bag hangs between the arm and the body, pressed flatter than it stands on a table: no
// deeper than this (m, on the 1.76 m body).
export const SHOULDER_DEPTH = 0.09
const ROWS = 40, ACROSS = 20

// The bag's size in metres: { width, height, depth, guessed }. listed: the listing's { width, height, depth,
// sure } in cm (any of them); shape: the photo's body ({ aspect }: how tall it stands against its width), which
// settles which way up a listing's two numbers go when it doesn't say, and gives the one it leaves out.
// guessed: nothing of its face was given (the size is its kind's usual, in the photo's proportions).
export function bagSize(style, listed, shape) {
  const usual = BAG_USUAL[style] ?? BAG_USUAL.tote
  const aspect = shape?.aspect > 0.15 && shape.aspect < 6 ? shape.aspect : usual[1] / usual[0]
  let width = listed?.width ?? null, height = listed?.height ?? null
  if (width && height && listed.sure === false && shape) {
    // Which is which was a guess: the photo says whether it stands taller than it's wide.
    if ((aspect > 1.12 && width > height) || (aspect < 0.89 && height > width)) [width, height] = [height, width]
  }
  const guessed = !width && !height
  if (guessed) {
    // The kind's usual area, in the photo's proportions.
    width = Math.sqrt((usual[0] * usual[1]) / aspect)
    height = width * aspect
  } else if (!height) height = width * aspect
  else if (!width) width = height / aspect
  else if (shape && Math.abs(Math.log((height / width) / aspect)) > Math.log(1.3)) {
    // Both given, but not in the photo's proportions (a soft bag measured flat, a height that counts its handles):
    // the greater is kept, the other read off the photo.
    if (width >= height) height = width * aspect
    else width = height / aspect
  }
  const grown = Math.sqrt((width * height) / (usual[0] * usual[1]))
  const depth = Math.min(listed?.depth ?? usual[2] * grown, Math.max(width, height))
  return { width: width / 100, height: height / 100, depth: Math.max(1.5, depth) / 100, guessed }
}

// The body's surface, in its own frame: x across (its middle at 0), y up from its bottom, z through it, its
// front toward +z. `flat`: how much of its depth is in front of its seam (0.5: the same both ways; a backpack's
// back panel is nearly flat, 0.8). Returns { positions, uvs, index, frontCount, front, back } (front, back: how
// far it stands either side of its seam; solid(x, y): how far it stands either side of it at a point of its face,
// x across, y up from its bottom, or null off its outline): the front's triangles first (frontCount indices),
// mapped to the photo; its back's mapped to the photo too, turned round (seen from behind it reads as it does
// from the front: its pattern, its print, its plate).
export function bagSurface(shape, size, { flat = 0.5 } = {}) {
  const { width, height, depth } = size
  const rows = shape?.rows?.length ? shape.rows : null
  // A row's edges (metres from the middle) at a share of the way down; a plain rounded box with no photo.
  const span = rows ? shape.right - shape.left : 1, mid = rows ? (shape.left + shape.right) / 2 : 0.5
  const edges = v => {
    if (!rows) return [-width / 2, width / 2]
    const f = Math.min(rows.length - 1, Math.max(0, v * rows.length - 0.5)), k = Math.min(rows.length - 2, Math.floor(f)), t = f - k
    const a = rows[k], b = rows[Math.min(rows.length - 1, k + 1)]
    return [((a[0] * (1 - t) + b[0] * t - mid) / span) * width, ((a[1] * (1 - t) + b[1] * t - mid) / span) * width]
  }
  // How thick it is at a point: full in its middle, rounded off over its edges (more squarely along its bottom,
  // which a bag stands on).
  const round = Math.min(depth * 0.6, Math.min(width, height) * 0.3)
  const thick = (fromSide, fromTop, fromBottom) => {
    const d = Math.min(fromSide / round, fromTop / round, fromBottom / (round * 0.55))
    const t = Math.min(1, Math.max(0, d))
    return (depth / 2) * Math.sqrt(1 - (1 - t) * (1 - t))
  }
  const positions = [], uvs = []
  for (const face of [1, -1]) {
    for (let r = 0; r <= ROWS; r++) {
      const v = r / ROWS, [l, right] = edges(v), y = height * (1 - v)
      for (let c = 0; c <= ACROSS; c++) {
        const u = c / ACROSS, x = l + (right - l) * u
        const t = thick(Math.min(x - l, right - x), v * height, (1 - v) * height)
        positions.push(x, y, face > 0 ? t * 2 * flat : -t * 2 * (1 - flat))
        // The photo: across the body's own row, down from its top, drawn in a little from its outline (whose
        // pixels are part backdrop, part shadow: stretched round the bag's side they streak).
        if (rows) {
          const cx = (l + right) / 2, inX = cx + ((face > 0 ? x : l + right - x) - cx) * 0.93, inV = 0.5 + (v - 0.5) * 0.95
          uvs.push(shape.left + (inX / width + 0.5) * span, 1 - (shape.top + inV * (shape.bottom - shape.top)))
        }
        else uvs.push(face > 0 ? u : 1 - u, 1 - v)
      }
    }
  }
  const index = []
  const at = (face, r, c) => face * (ROWS + 1) * (ACROSS + 1) + r * (ACROSS + 1) + c
  for (const face of [0, 1]) for (let r = 0; r < ROWS; r++) for (let c = 0; c < ACROSS; c++) {
    const a = at(face, r, c), b = at(face, r + 1, c), d = at(face, r, c + 1), e = at(face, r + 1, c + 1)
    if (face === 0) index.push(a, b, d, d, b, e)
    else index.push(a, d, b, d, e, b)
  }
  // A hobo's horns (where its loop's legs are still the bag: print.js's bagHorns): a card standing on the body's
  // top, cut to their outline and wearing the photo there (stage.js gives it both). Thin leather, so it has no
  // depth of its own; in rows, so that it can lean (placed).
  let card = null
  const horns = shape?.loop?.horns
  if (rows && horns && shape.bottom > shape.top) {
    const across = x => ((x - mid) / span) * width
    const up = y => height + ((shape.top - y) / (shape.bottom - shape.top)) * height
    const x0 = across(horns.left), x1 = across(horns.right), y0 = up(horns.bottom), y1 = up(horns.top)
    const at = [], uv = [], faces = [], STEPS = 8
    for (let r = 0; r <= STEPS; r++) {
      const t = r / STEPS
      at.push(x0, y0 + (y1 - y0) * t, 0, x1, y0 + (y1 - y0) * t, 0)
      uv.push(0, t, 1, t)
      if (r < STEPS) faces.push(2 * r, 2 * r + 1, 2 * r + 2, 2 * r + 1, 2 * r + 3, 2 * r + 2)
    }
    card = { positions: Float32Array.from(at), uvs: Float32Array.from(uv), index: faces }
  }
  const solid = (x, y) => {
    if (!(y > 0 && y < height)) return null
    const v = 1 - y / height, [l, right] = edges(v)
    if (!(x > l && x < right)) return null
    const t = thick(Math.min(x - l, right - x), v * height, (1 - v) * height)
    return { front: t * 2 * flat, back: t * 2 * (1 - flat) }
  }
  return { positions: Float32Array.from(positions), uvs: Float32Array.from(uvs), index, frontCount: index.length / 2, front: depth * flat, back: depth * (1 - flat), card, solid }
}

// A strap along a line of points, lying flat on what it crosses: at each point `out`, the way off the body.
// Returns { positions, index }: a band `width` wide (a number, or one for each point) and `thick` deep, closed
// at its ends.
export function strapBand(points, outs, width, thick) {
  const n = points.length
  if (n < 2) return null
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
  const unit = v => { const l = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / l, v[1] / l, v[2] / l] }
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
  const positions = [], index = []
  let before = null
  for (let i = 0; i < n; i++) {
    const along = unit(sub(points[Math.min(n - 1, i + 1)], points[Math.max(0, i - 1)]))
    let side = unit(cross(along, outs[i]))
    // (Kept the same way round from point to point: a strap doesn't flip over.)
    if (before && side[0] * before[0] + side[1] * before[1] + side[2] * before[2] < 0) side = side.map(v => -v)
    before = side
    const out = unit(cross(side, along)), up = out[0] * outs[i][0] + out[1] * outs[i][1] + out[2] * outs[i][2] < 0 ? out.map(v => -v) : out
    const p = points[i], wide = (Array.isArray(width) ? width[i] : width) / 2
    for (const [a, b] of [[-1, 1], [1, 1], [1, 0], [-1, 0]]) positions.push(p[0] + side[0] * a * wide + up[0] * b * thick, p[1] + side[1] * a * wide + up[1] * b * thick, p[2] + side[2] * a * wide + up[2] * b * thick)
  }
  for (let i = 0; i + 1 < n; i++) for (let k = 0; k < 4; k++) {
    const a = 4 * i + k, b = 4 * i + ((k + 1) % 4), c = a + 4, d = b + 4
    index.push(a, c, b, b, c, d)
  }
  index.push(0, 1, 2, 0, 2, 3, 4 * n - 4, 4 * n - 2, 4 * n - 3, 4 * n - 4, 4 * n - 1, 4 * n - 2)
  return { positions: Float32Array.from(positions), index }
}

// A line of points made even and smooth: cut at its corners (Chaikin, twice), then `count` points at equal
// steps along it.
export function smoothLine(points, count = 48) {
  let line = points
  for (let pass = 0; pass < 2; pass++) {
    const next = [line[0]]
    for (let i = 0; i + 1 < line.length; i++) {
      const a = line[i], b = line[i + 1]
      next.push(a.map((v, d) => v * 0.75 + b[d] * 0.25), a.map((v, d) => v * 0.25 + b[d] * 0.75))
    }
    next.push(line[line.length - 1])
    line = next
  }
  const lengths = [0]
  for (let i = 1; i < line.length; i++) lengths.push(lengths[i - 1] + Math.hypot(line[i][0] - line[i - 1][0], line[i][1] - line[i - 1][1], line[i][2] - line[i - 1][2]))
  const total = lengths[lengths.length - 1] || 1, out = []
  let k = 1
  for (let j = 0; j < count; j++) {
    const want = (j / (count - 1)) * total
    while (k < line.length - 1 && lengths[k] < want) k++
    const t = (want - lengths[k - 1]) / (lengths[k] - lengths[k - 1] || 1)
    out.push(line[k - 1].map((v, d) => v + (line[k][d] - v) * Math.min(1, Math.max(0, t))))
  }
  return out
}

// What a strap lies on: the torso's skin (no arms, head or legs) and the cloth worn over it (its points between
// the shoulders: a sleeve hanging beside the body isn't in a strap's way), as [x, y, z] points.
export function strapGround(body, frame, cloth = []) {
  const points = []
  const p = body.positions
  for (let i = 0; i < frame.count; i++) if (frame.part[i] === 0) points.push([p[3 * i], p[3 * i + 1], p[3 * i + 2]])
  const reach = Math.abs(frame.joints.shoulder_L?.[0] ?? 0.2) + 0.015
  for (const x of cloth) for (let i = 0; i + 2 < x.length; i += 3) if (Math.abs(x[i]) <= reach && Number.isFinite(x[i + 1])) points.push([x[i], x[i + 1], x[i + 2]])
  return points
}

// Where the bag goes and where its straps run: { place, straps, worn } for stage.js.
//   place: { position: [x, y, z], yaw, roll } of the body's own frame (its bottom's middle at the origin);
//   straps: [{ points, outs, width, thick }];
//   worn: "back", "chest", "hip" or "hand".
// ground: strapGround's points. size: bagSize's. surface: bagSurface's (how far it stands off its seam).
// how: the way it's carried (bagWay); drop: the listing's handle drop (cm); grip: where the carrying hand holds
// (stage.js's gripOf).
export function wearBag(style, size, surface, shape, body, frame, ground, { how = null, drop = null, grip = null } = {}) {
  const worn = bagWay(style, how, shape)
  const s = (frame.top - frame.floor) / 1.76
  const J = frame.joints
  if (worn === "back" && J.shoulder_L && J.neck) return { worn, ...onBack(size, surface, frame, ground, s) }
  if (worn === "shoulder" && J.shoulder_L && J.neck) {
    // (The arm it hangs under, as it's held out round it: its skin.)
    const arm = []
    for (let i = 0; i < frame.count; i++) if (frame.part[i] === 1 && body.positions[3 * i] > 0) arm.push([body.positions[3 * i], body.positions[3 * i + 1], body.positions[3 * i + 2]])
    return { worn, ...onShoulder(style, size, surface, shape, frame, ground, s, drop, arm) }
  }
  if ((worn === "chest" || worn === "hip") && J.shoulder_R && J.neck) {
    const across = acrossBody(worn, size, surface, frame, ground, s)
    if (across) return { worn, ...across }
  }
  return { worn: "hand", ...inHand(style, size, surface, shape, body, frame, s, drop, grip) }
}

const CLEAR = 0.004
// The armpits' height on the body as it stands. (The frame's is where the arm parts from the body's side, read
// for clothes on a body with its arms held out; with the arms hanging close it finds that well down the ribs,
// and a strap sent under the arm there went down over the chest first.) Never more than 12 cm under the
// shoulder's joint.
const armpitOf = (frame, s) => Math.max(frame.armpitY ?? -Infinity, frame.joints.shoulder_L[1] - 0.12 * s)

// A backpack: its top a little under the shoulders' line, its back panel against the furthest-out of the back
// over its height, a strap over each shoulder and round under the arm to its lower corner.
function onBack(size, surface, frame, ground, s) {
  const J = frame.joints
  const shoulder = Math.abs(J.shoulder_L[0]), neck = frame.neckSide ?? 0.05
  const top = (frame.hps?.[1] ?? J.neck[1]) - 0.035 * s, bottom = top - size.height
  const half = Math.min(size.width / 2, shoulder)
  let back = Infinity, centre = 0, n = 0
  for (const q of ground) {
    if (q[1] < bottom || q[1] > top || Math.abs(q[0]) > half) continue
    back = Math.min(back, q[2]); centre += q[2]; n++
  }
  if (!Number.isFinite(back)) back = J.neck[2] - 0.12 * s
  const seam = back - CLEAR - surface.back
  // (Turned to face behind: its photo reads the right way round from there.)
  const place = { position: [0, bottom, seam], yaw: Math.PI, roll: 0 }
  const straps = []
  // Where it turns under the arm: it comes down the front as far as the armpit, no lower (below that is the
  // chest: pulled down over it the strap stood off the body from the collarbone to the bust).
  const turnAt = armpitOf(frame, s) + 0.045 * s
  // Its place across the body: over the middle of the shoulder at the top and behind; down the front it swings
  // out to the front of the armpit, outside the chest.
  const crest = J.shoulder_L[1] + 0.02 * s, mid = neck + (shoulder - neck) * 0.55, outer = Math.max(mid, shoulder - 0.022 * s)
  const across = (y, z) => (z <= J.shoulder_L[2] || y >= crest ? mid : mid + (outer - mid) * Math.min(1, (crest - y) / Math.max(0.01, crest - turnAt)))
  for (const side of [1, -1]) {
    const x = side * mid
    // Over the shoulder: the tight line over what's there, in the slice of the body along the strap's place,
    // from the bag's top to the front of the armpit.
    const from = [back - CLEAR, top - 0.03 * s]
    const slice = [from]
    for (const q of ground) if (q[1] > turnAt - 0.012 * s && Math.abs(q[0] * side - across(q[1], q[2])) < 0.022 * s) slice.push([q[2], q[1]])
    const hull = convexHull(slice)
    // (The hull runs anticlockwise from its backmost point: under, to the front, then back over the top. Its
    // upper side, turned round, runs from the back over the shoulder to the front.)
    const start = hull.reduce((best, q, k) => (Math.hypot(q[0] - from[0], q[1] - from[1]) < Math.hypot(hull[best][0] - from[0], hull[best][1] - from[1]) ? k : best), 0)
    const over = []
    for (let k = 0; k < hull.length; k++) {
      const q = hull[(start - k + hull.length) % hull.length]
      over.push(q)
      if (k > 0 && q[0] > J.neck[2] && q[1] <= turnAt) break
    }
    const inside = [x * 0.6, turnAt, J.neck[2] - 0.02 * s]
    const points = over.map(q => [side * across(q[1], q[0]), q[1], q[0]])
    const front = points[points.length - 1]
    // Round under the arm: about the body's middle at each height, from the front of the shoulder out to the
    // side and back to the bag's lower corner, falling evenly as it goes (a taut strap's line round a body),
    // on the body's side all the way.
    const end = [side * Math.min(size.width / 2, shoulder) * 0.92, bottom + size.height * 0.16, back - CLEAR]
    // (The body's middle, front to back, at the bag's height.)
    const mz = (centre / (n || 1) + J.neck[2]) / 2
    const a0 = Math.atan2(front[0], front[2] - mz), a1 = Math.atan2(end[0], end[2] - mz)
    const turn = side > 0 ? (a1 < a0 ? a1 + 2 * Math.PI - a0 : a1 - a0) : (a1 > a0 ? a1 - 2 * Math.PI - a0 : a1 - a0)
    const under = []
    const STEPS = 16
    for (let k = 1; k < STEPS; k++) {
      const t = k / STEPS, a = a0 + turn * t, y = front[1] + (end[1] - front[1]) * t
      const dir = [Math.sin(a), Math.cos(a)]
      let far = 0
      for (const q of ground) {
        if (Math.abs(q[1] - y) > 0.02 * s) continue
        const along = q[0] * dir[0] + (q[2] - mz) * dir[1], off = Math.abs(q[0] * dir[1] - (q[2] - mz) * dir[0])
        if (along > far && off < 0.03 * s) far = along
      }
      if (far > 0) under.push([dir[0] * (far + CLEAR), y, mz + dir[1] * (far + CLEAR)])
    }
    const whole = smoothLine([...points, ...under, end], 72)
    const outs = whole.map(q => {
      const c = q[1] > turnAt ? inside : [0, q[1], mz]
      return [q[0] - c[0], q[1] - c[1], q[2] - c[2]]
    })
    // (Padded over the shoulder and down its front; webbing from there round to the bag.)
    const PAD = 0.042 * s, WEB = 0.024 * s
    const width = whole.map(q => (q[1] > turnAt ? PAD : q[1] > turnAt - 0.06 * s ? WEB + (PAD - WEB) * ((q[1] - (turnAt - 0.06 * s)) / (0.06 * s)) : WEB))
    straps.push({ points: whole, outs, width, thick: 0.007 })
  }
  return { place, straps }
}

// A strap across the body, over the right shoulder and under the left arm: the tight line round the torso in
// the plane through both. A crossbody hangs from it at the left hip, turned out; a belt bag or a sling lies
// along it on the chest.
function acrossBody(worn, size, surface, frame, ground, s) {
  const J = frame.joints
  const shoulder = Math.abs(J.shoulder_R[0]), neck = frame.neckSide ?? 0.05
  const high = [-((neck + shoulder) / 2), frame.shoulderTop?.at((neck + shoulder) / 2) ?? J.shoulder_R[1], J.neck[2]]
  const lowY = worn === "hip" ? (frame.crotch ?? frame.floor + 0.8 * s) + 0.13 * s : armpitOf(frame, s) - 0.13 * s
  // (The low end at the body's left side, at that height.)
  let side = 0
  for (const q of ground) if (Math.abs(q[1] - lowY) < 0.02 * s && q[0] > side) side = q[0]
  if (!side) return null
  const low = [side, lowY, J.neck[2]]
  // The plane: through both ends, and running front to back. e2 runs down it from the shoulder to the hip.
  const down = [low[0] - high[0], low[1] - high[1]], length = Math.hypot(down[0], down[1])
  const e2 = [down[0] / length, down[1] / length], normal = [-e2[1], e2[0]]
  const flat = []
  for (const q of ground) {
    const dx = q[0] - high[0], dy = q[1] - high[1]
    if (Math.abs(dx * normal[0] + dy * normal[1]) > 0.014 * s) continue
    const along = dx * e2[0] + dy * e2[1]
    if (along < -0.03 * s || along > length + 0.01 * s) continue
    flat.push([q[2], along])
  }
  if (flat.length < 12) return null
  const hull = convexHull(flat)
  let mz = 0, ma = 0
  for (const q of hull) { mz += q[0] / hull.length; ma += q[1] / hull.length }
  const loop = hull.map(q => {
    const d = Math.hypot(q[0] - mz, q[1] - ma) || 1, z = q[0] + ((q[0] - mz) / d) * CLEAR, a = q[1] + ((q[1] - ma) / d) * CLEAR
    return [high[0] + e2[0] * a, high[1] + e2[1] * a, z]
  })
  loop.push(loop[0])
  const points = smoothLine(loop, 96)
  const middle = [high[0] + e2[0] * ma, high[1] + e2[1] * ma, mz]
  const outs = points.map(q => [q[0] - middle[0], q[1] - middle[1], q[2] - middle[2]])
  const straps = [{ points, outs, width: (worn === "hip" ? 0.028 : 0.038) * s, thick: 0.004 }]
  if (worn === "hip") {
    // At the hip, a little to the front: of the strap's low stretch, its foremost point.
    let at = points[0], most = -Infinity
    for (const q of points) {
      const along = (q[0] - high[0]) * e2[0] + (q[1] - high[1]) * e2[1]
      if (along > length * 0.8 && q[2] > most) { most = q[2]; at = q }
    }
    const out = [at[0], 0, at[2] - mz], l = Math.hypot(out[0], out[2]) || 1
    const yaw = Math.atan2(out[0] / l, out[2] / l)
    const off = surface.back + CLEAR
    return { place: { position: [at[0] + (out[0] / l) * off, at[1] - size.height * 0.92, at[2] + (out[2] / l) * off], yaw, roll: 0 }, straps }
  }
  // On the chest: the strap's foremost point, the bag lying along the strap there.
  let k = 0
  for (let i = 0; i < points.length; i++) if (points[i][2] > points[k][2]) k = i
  const at = points[k], a = points[Math.max(0, k - 3)], b = points[Math.min(points.length - 1, k + 3)]
  let roll = Math.atan2(b[1] - a[1], b[0] - a[0])
  // (The right way up: within a quarter turn of level.)
  if (roll > Math.PI / 2) roll -= Math.PI
  if (roll < -Math.PI / 2) roll += Math.PI
  return { place: { position: [at[0], at[1], at[2] + surface.back + CLEAR], yaw: 0, roll, centred: true }, straps }
}

// Hung from the left shoulder: its handles (or its strap) over the shoulder's top, the bag under the arm against
// the body's side, its face out. The arm is held out round it (stage.js's holdOut); where a handle passes
// between the arm and the body it's out of sight, as it is on a person.
function onShoulder(style, size, surface, shape, frame, ground, s, drop, arm = []) {
  const J = frame.joints
  const shoulder = Math.abs(J.shoulder_L[0]), neck = frame.neckSide ?? 0.05
  const line = (neck + shoulder) / 2 + 0.012 * s
  // The top of the shoulder there (the skin's or the cloth's).
  let over = [line, J.shoulder_L[1], J.shoulder_L[2]]
  for (const q of ground) if (Math.abs(q[0] - line) < 0.02 * s && q[1] > over[1]) over = [line, q[1], q[2]]
  over[1] += CLEAR
  // How far it hangs (shoulderFall), and never onto the floor.
  const long = style === "crossbody"
  const fall = Math.max(0.12 * s, Math.min(shoulderFall(style, size, shape, drop, s), over[1] - frame.floor - size.height - 0.03))
  // (A little behind the shoulder's middle: the arm hangs past its front half. On a crossbody's long strap it
  // hangs at the hip, where the hand is: behind the arm, which hangs in front of it as it would.)
  const middle0 = long ? (J.wrist_L?.[2] ?? J.shoulder_L[2]) - size.width / 2 - 0.03 * s : J.shoulder_L[2] - 0.025 * s
  // Against the body's side there: the furthest out the body (and what it wears) stands beside the bag.
  const sideOf = (bottom, top, middle) => {
    let side = 0
    for (const q of ground) if (q[1] >= bottom && q[1] <= top && Math.abs(q[2] - middle) < size.width / 2 && q[0] > side) side = q[0]
    return side || shoulder
  }
  // Clear of the arm. It's held out round the bag (stage.js's holdOut), but only as far as an arm goes: a deep
  // bag hung high, close under it, still stood in it, the sleeve through its middle. Where it would, the bag
  // hangs further back (on the shoulder a bag swings behind the arm, which comes down in front of it), and if
  // that's not enough, lower: as little of either as clears the arm and its sleeve.
  const pad = 0.014 * s
  const strikes = (seam, bottom, middle) => {
    let n = 0
    for (const q of arm) {
      const ly = q[1] - bottom
      if (ly < -pad || ly > size.height + pad) continue
      const lx = middle - q[2], lz = q[0] - seam
      const at = surface.solid?.(lx - Math.sign(lx) * Math.min(Math.abs(lx), pad), Math.min(size.height * 0.999, Math.max(size.height * 0.001, ly)))
      if (at && lz < at.front + pad && lz > -at.back - pad) n++
    }
    return n
  }
  const step = 0.01 * s, deepest = Math.max(0, Math.min(0.16 * s, over[1] - fall - size.height - frame.floor - 0.03))
  let best = null
  for (let h = 0; h <= deepest + 1e-9; h += step) {
    for (let d = 0; d <= size.width * 0.6 + 1e-9; d += step) {
      const top = over[1] - fall - h, bottom = top - size.height, middle = middle0 - d
      const seam = sideOf(bottom, top, middle) + CLEAR + surface.back
      const n = arm.length ? strikes(seam, bottom, middle) : 0
      const cost = n * 10 + d / s + 3 * h / s
      if (!best || cost < best.cost) best = { cost, n, top, bottom, middle, seam }
      if (n === 0) break
    }
    if (best.n === 0 && best.cost <= (h + step) * 3 / s) break
  }
  const { top, bottom, middle, seam } = best
  let place = { position: [seam, bottom, middle], yaw: Math.PI / 2, roll: 0 }
  const straps = []
  const reach = size.width * (long ? 0.42 : style === "duffle" ? 0.2 : 0.24)
  const mid = (surface.front - surface.back) / 2, half = (surface.front + surface.back) / 2
  // A hobo's loop: one strap, from where its ends stand in the photo, as wide as they are there; its horns lean
  // to the shoulder's top.
  const loop = shape?.loop ? loopStrap(shape, size, 40, s) : null
  if (loop) place = hung(place, size, loop, over)
  // (Across the bag is front to back here: local x runs to -z.)
  for (const x of long || loop ? [mid] : [mid + half * 0.5, mid - half * 0.5]) {
    const foot = z => [seam + x, top - size.height * 0.03, middle + z]
    const a = loop ? placed(place, size, [loop.at[1], size.height + loop.up[1], x]) : foot(-reach), b = loop ? placed(place, size, [loop.at[0], size.height + loop.up[0], x]) : foot(reach)
    const arch = []
    for (let k = 0; k <= 16; k++) {
      const t = k / 16, u = 1 - t
      arch.push([0, 1, 2].map(d => u * u * a[d] + 2 * u * t * (2 * over[d] - (a[d] + b[d]) / 2) + t * t * b[d]))
    }
    const points = smoothLine(arch, loop ? 40 : 32)
    // (Flat against the body's side as it rises, turned to lie on the shoulder at its top.)
    const low = Math.min(a[1], b[1])
    const outs = points.map(q => {
      const up = Math.pow(Math.min(1, Math.max(0, (q[1] - low) / Math.max(0.01, over[1] - low))), 3)
      return [1 - 0.8 * up, 0.35 + 0.65 * up, 0]
    })
    straps.push({ points, outs, width: loop ? loop.width.slice().reverse() : (long ? 0.02 : 0.026) * s, thick: 0.005 })
  }
  return { place, straps }
}

// Carried in the left hand, as the hand holds it (grip, stage.js's gripOf: the crook of its closed fingers, and
// the way its knuckles run): hanging straight down from there on its handles, its face along the knuckles'
// line and turned out, and no nearer the leg than its own depth lets it be (a bag that would stand in the thigh
// hangs out from it, its handles slanting to the hand). A clutch is held at its top edge.
function inHand(style, size, surface, shape, body, frame, s, drop, grip) {
  const J = frame.joints
  const wrist = J.wrist_L ?? [0.3 * s, frame.floor + 0.85 * s, 0], tip = J.hand_L ?? [wrist[0], wrist[1] - 0.18 * s, wrist[2]]
  const hold = grip?.point ?? wrist.map((v, d) => v + (tip[d] - v) * 0.7)
  // Its width runs the way the knuckles do (front to back, when the palm faces the leg); its face is out.
  const run = grip?.along ?? [0, 1]
  let yaw = Math.atan2(-run[1], run[0])
  if (Math.sin(yaw) < 0) yaw += Math.PI
  const face = [Math.sin(yaw), Math.cos(yaw)], across = [Math.cos(yaw), -Math.sin(yaw)]
  const clutch = style === "clutch"
  // The handles' drop: the listing's, or as far as the photo's handles stand over the bag; never so long that
  // the bag would stand on the floor.
  let fall = clutch ? -0.02 * s : drop ? drop / 100 : (shape?.handle ?? 0.5) * size.height * 0.85
  if (!clutch) {
    fall = Math.min(0.32 * s, Math.max(0.07 * s, fall))
    fall = Math.max(0.04, Math.min(fall, hold[1] - frame.floor - size.height - 0.03))
  }
  const bottom = hold[1] - fall - size.height
  // Clear of the leg: the furthest out the leg stands, the bag's way, beside where the bag hangs.
  const mid = (surface.front - surface.back) / 2, half = (surface.front + surface.back) / 2
  let leg = -Infinity
  const p = body.positions
  for (let i = 0; i < frame.count; i++) {
    if (frame.part[i] !== 4 || p[3 * i] <= 0 || p[3 * i + 1] < bottom || p[3 * i + 1] > bottom + size.height) continue
    const dx = p[3 * i] - hold[0], dz = p[3 * i + 2] - hold[2]
    if (Math.abs(dx * across[0] + dz * across[1]) > size.width / 2) continue
    leg = Math.max(leg, dx * face[0] + dz * face[1])
  }
  // (The bag's middle, front to back, from the hand: under it, or out past the leg.)
  const out = Math.max(0, Number.isFinite(leg) ? leg + 0.008 + half : 0)
  const centre = [hold[0] + face[0] * out, bottom, hold[2] + face[1] * out]
  let place = { position: [centre[0] - face[0] * mid, centre[1], centre[2] - face[1] * mid], yaw, roll: 0 }
  if (clutch) return { place, straps: [] }
  const straps = []
  const reach = size.width * (style === "duffle" ? 0.2 : 0.24)
  // A hobo's loop: one strap, from where its ends stand in the photo, as wide as they are there; its horns lean
  // to the hand.
  const loop = shape?.loop ? loopStrap(shape, size, 28, s) : null
  if (loop) place = hung(place, size, loop, hold)
  // Two handles (one from each face) for a tote or a duffle, gathered in the hand; one for the rest.
  for (const z of !loop && (style === "tote" || style === "duffle") ? [half * 0.5, -half * 0.5] : [0]) {
    const foot = x => [centre[0] + across[0] * x + face[0] * z, bottom + size.height * 0.97, centre[2] + across[1] * x + face[1] * z]
    const a = loop ? placed(place, size, [loop.at[0], size.height + loop.up[0], mid]) : foot(-reach), b = loop ? placed(place, size, [loop.at[1], size.height + loop.up[1], mid]) : foot(reach)
    const top = [hold[0] + face[0] * Math.sign(z) * 0.003, hold[1], hold[2] + face[1] * Math.sign(z) * 0.003]
    // An arch from one side of the bag's top up through the hand and down to the other.
    const arch = []
    for (let k = 0; k <= 16; k++) {
      const t = k / 16, u = 1 - t
      arch.push([0, 1, 2].map(d => u * u * a[d] + 2 * u * t * (2 * top[d] - (a[d] + b[d]) / 2) + t * t * b[d]))
    }
    const points = smoothLine(arch, 28)
    straps.push({ points, outs: points.map(() => [face[0], 0, face[1]]), width: loop ? loop.width : 0.024 * s, thick: 0.005 })
  }
  return { place, straps }
}

// The body's geometry (two groups: its front, which takes the photo, and the rest), placed as wearBag says.
export function bagGeometry(surface, place, size) {
  const geometry = new THREE.BufferGeometry()
  const positions = Float32Array.from(surface.positions)
  for (let i = 0; i < positions.length; i += 3) positions.set(placed(place, size, [positions[i], positions[i + 1], positions[i + 2]]), i)
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3))
  geometry.setAttribute("uv", new THREE.BufferAttribute(Float32Array.from(surface.uvs), 2))
  geometry.setIndex(surface.index)
  geometry.addGroup(0, surface.frontCount, 0)
  geometry.addGroup(surface.frontCount, surface.index.length - surface.frontCount, 1)
  geometry.computeVertexNormals()
  return geometry
}

// A hobo's horns (the surface's card: bagSurface), placed with the bag and leaning to where it hangs from.
export function bagCardGeometry(surface, place, size) {
  if (!surface.card) return null
  const geometry = new THREE.BufferGeometry()
  const positions = Float32Array.from(surface.card.positions)
  for (let i = 0; i < positions.length; i += 3) positions.set(placed(place, size, [positions[i], positions[i + 1], positions[i + 2]]), i)
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3))
  geometry.setAttribute("uv", new THREE.BufferAttribute(Float32Array.from(surface.card.uvs), 2))
  geometry.setIndex(surface.card.index)
  geometry.computeVertexNormals()
  return geometry
}

export function bagStrapGeometry(strap) {
  const band = strapBand(strap.points, strap.outs, strap.width, strap.thick)
  if (!band) return null
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute("position", new THREE.BufferAttribute(band.positions, 3))
  geometry.setIndex(band.index)
  geometry.computeVertexNormals()
  return geometry
}
