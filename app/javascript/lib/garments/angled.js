// The shop's photo of a pair at an angle, laid on the 3D shoe. Kith (and most shops) never photograph a shoe
// square from the front; their second photo is nearly always the pair at three-quarters, which shows what the
// side photo can't: the toe box, the laces and eyelets, the tongue, the welt round the toe. The camera it was
// taken from, and where the nearer shoe of the two stands in it, are found by drawing the 3D shoe's outline
// (and its mirror image's beside it, the other shoe of the pair) from every direction and keeping the one that
// matches what stands out of the photo; and each point of the shoe that camera saw takes the photo's colour
// there (stage.js blends it over the side photo where the side photo is weakest: what faces forward and up).
//
// The photo is taken as orthographic (product photos are shot from far off with a long lens): an outline
// depends only on the direction it's seen from (a turn round the shoe and a look down at it) and on which shoe
// of the pair it is (the outline mirrored). Everything runs on the page; nothing is sent anywhere.
import { angledReading } from "lib/garments/print"

// The grid the outlines are compared on, and the one the shoe's depth is drawn on for what the camera saw.
const GRID = 64, DEPTH_GRID = 192
// The most the camera looks down in the first search (degrees; the finer searches round the best go further).
const PITCH_MOST = 45
// The turns tried (degrees): from a little behind square to the outer side, round the toe, to a little behind
// square to the inner side. A shop photographs a pair toes towards the camera; from behind, a shoe's outline is
// much the same as from in front (the heel taken for the toe), and the heel's photo would be laid on the toe.
const TURN_LEAST = -15, TURN_MOST = 195
// The least overlap (intersection over union) of the two outlines for the fit to be used.
const FIT_LEAST = 0.78
// How squarely the camera must face the toe (the sine of its turn from the side) for the photo to be laid on.
const FRONT_LEAST = 0.3
// Height over the floor (metres) under which the angled photo isn't laid (the sole), and over which it is fully.
const SOLE_LOW = 0.02, SOLE_HIGH = 0.035

// The photo, its backdrop filled in, and what stands out of the backdrop on the reading copy (the pair, or the
// one shoe): { canvas, mask, w, h, photo, pair }, or null (nothing stands out, or the photo can't be had). pair:
// the shop's photo is of the pair (read so by the photo examples), so one shoe alone isn't tried for it.
export async function readAngled(src, pair = false) {
  const reading = await angledReading(src).catch(() => null)
  if (!reading || !reading.all.some(Boolean)) return null
  return { canvas: reading.canvas, mask: reading.all, w: reading.w, h: reading.h, photo: src, pair }
}

// The grid the shoe's outlines are drawn on at one scale (the pair's two shoes placed on it side by side), its
// width in shoe lengths, and the grid the pair's outline and the photo's are compared on.
const PLACE_GRID = 80, PLACE_SPAN = 2.6
// Where the other shoe of the pair stands from the first, on the screen (in shoe lengths): across, and up or down.
const APART_X = 0.9, APART_Y = 0.45, APART_STEP = 0.15

// The camera the photo was taken from and where it shows the nearer shoe: { turn, pitch, mirror (the nearer
// shoe's), iou, pair (whether two shoes were found), map: { k, ox, oy } (a point of the nearer shoe on the
// screen, X and Y in metres from its middle, lies at photo pixel ox + X k, oy - Y k) }, or null when nothing
// overlaps the photo's outline by FIT_LEAST or the camera found doesn't face the toe (FRONT_LEAST). geometry:
// the shoe as built (positions in metres, toe along +z).
//
// A pair stands as a left shoe and a right (each the other mirrored), side by side and turned the same way: for
// each direction, the shoe's outline and its mirror image's are drawn at one scale, and the second moved about
// beside the first; the two together (or the one alone, for a photo of one shoe) are compared with what stands
// out of the photo. The nearer shoe of the two is the one standing lower in the frame.
export function fitPose(geometry, angled) {
  const shoe = shoeOf(geometry)
  const target = photoGrid(angled.mask, angled.w, angled.h, GRID)
  if (!target) return null
  const length = extent(shoe), cell = (length * PLACE_SPAN) / PLACE_GRID
  const outlines = new Map()
  const drawn = (turn, pitch, mirror) => {
    const key = `${turn}|${pitch}|${mirror}`
    if (!outlines.has(key)) outlines.set(key, placed(shoe, turn, pitch, mirror, cell))
    return outlines.get(key)
  }
  const steps = (most, step) => { const out = []; for (let v = -most; v <= most + 1e-9; v += step) out.push(Math.round((v * length) / cell)); return out }
  let best = null
  const tryPose = (turn, pitch, mirror, offsets) => {
    const a = drawn(turn, pitch, mirror), b = drawn(turn, pitch, !mirror)
    for (const off of offsets) {
      const iou = overlap(together(a, off && b, off), target)
      if (!best || iou > best.iou) best = { turn, pitch, mirror, off, iou }
    }
  }
  const coarse = angled.pair ? [] : [null]
  for (const dy of steps(APART_Y, APART_STEP)) for (const dx of steps(APART_X, APART_STEP)) if (Math.abs(dx) * cell > 0.25 * length) coarse.push([dx, dy])
  for (const mirror of [false, true]) for (let turn = TURN_LEAST; turn <= TURN_MOST; turn += 15) for (let pitch = 0; pitch <= PITCH_MOST; pitch += 15) tryPose(turn, pitch, mirror, coarse)
  for (let round = 0; round < 2; round++) {
    const at = best, near = [at.off]
    if (at.off) for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) if (dx || dy) near.push([at.off[0] + dx, at.off[1] + dy])
    const reach = round ? 3 : 9, step = round ? 1 : 3
    for (let turn = Math.max(TURN_LEAST, at.turn - reach); turn <= Math.min(TURN_MOST, at.turn + reach); turn += step) for (let pitch = Math.max(0, at.pitch - reach); pitch <= Math.min(60, at.pitch + reach); pitch += step) tryPose(turn, pitch, at.mirror, near)
  }
  if (best.iou < FIT_LEAST) return null
  // Seen from near enough square to its side (or from above it), the photo shows little the side photo doesn't,
  // and what it shows of the front lies at a slant, laid on badly (the UGG's tan heel tab drawn on its toe).
  if (Math.sin((best.turn * Math.PI) / 180) < FRONT_LEAST) return null
  // The nearer shoe: the one whose lowest point stands lower in the frame.
  const a = drawn(best.turn, best.pitch, best.mirror), b = best.off && drawn(best.turn, best.pitch, !best.mirror)
  const second = b && b.y1 + best.off[1] > a.y1 + 0.5
  const fx = second ? best.off[0] : 0, fy = second ? best.off[1] : 0
  // The pair's box on the grid, laid on the photo's as the comparison laid them (centres, longer sides).
  const box = unionBox(a, b, best.off), span = Math.max(box.w, box.h) * 1.02
  const pbox = maskBox(angled.mask, angled.w, angled.h), pspan = Math.max(pbox.w, pbox.h) * 1.02
  const k = pspan / (span * cell)
  const C = PLACE_GRID / 2
  const map = { k, ox: pbox.cx + ((C + fx - box.cx) * pspan) / span, oy: pbox.cy + ((C + fy - box.cy) * pspan) / span }
  return { turn: best.turn, pitch: best.pitch, mirror: second ? !best.mirror : best.mirror, iou: best.iou, pair: !!best.off, map }
}

// Where each point of the shoe falls on the photo, and how much of the photo it takes: { uv (2 per point),
// weight (1 per point) }. flip: the other foot (the shoe mirrored across its middle). A point takes the photo
// where the camera saw it (facing it, not hidden behind the rest of the shoe) and it falls on what stands out.
export function projectAngled(geometry, angled, pose, flip = false) {
  const shoe = shoeOf(geometry)
  const mirror = pose.mirror !== flip
  const { X, Y, Z } = view(shoe, pose.turn, pose.pitch, mirror)
  const n = shoe.count
  const { k, ox, oy } = pose.map
  const toPhoto = i => [ox + X[i] * k, oy - Y[i] * k]
  // What the camera saw: the nearest depth on a grid over the outline.
  const sbox = boxOf(X, Y, n)
  const D = DEPTH_GRID, depth = new Float32Array(D * D).fill(-Infinity)
  const span = Math.max(sbox.w, sbox.h) * 1.02, gx = i => ((X[i] - sbox.cx) / span + 0.5) * (D - 1), gy = i => (0.5 - (Y[i] - sbox.cy) / span) * (D - 1)
  const index = shoe.index
  for (let t = 0; t < index.length; t += 3) rasterTriangle(D, [gx(index[t]), gy(index[t])], [gx(index[t + 1]), gy(index[t + 1])], [gx(index[t + 2]), gy(index[t + 2])], [Z[index[t]], Z[index[t + 1]], Z[index[t + 2]]], depth)
  const eps = Math.max(sbox.w, sbox.h) * 0.015
  // The camera's direction in the shoe's frame (towards the camera), for how squarely each point faces it.
  const dir = cameraDir(pose.turn, pose.pitch)
  const uv = new Float32Array(2 * n), weight = new Float32Array(n)
  const normals = shoe.normals
  for (let i = 0; i < n; i++) {
    const [px, py] = toPhoto(i)
    uv[2 * i] = px / angled.w
    uv[2 * i + 1] = 1 - py / angled.h
    const cx = Math.round(gx(i)), cy = Math.round(gy(i))
    const seen = cx >= 0 && cy >= 0 && cx < D && cy < D && Z[i] >= depth[cy * D + cx] - eps
    const mx = Math.round(px), my = Math.round(py)
    const onShoe = mx >= 0 && my >= 0 && mx < angled.w && my < angled.h && near(angled.mask, angled.w, angled.h, mx, my, 1)
    const nx = mirror ? -normals[3 * i] : normals[3 * i]
    const facing = nx * dir[0] + normals[3 * i + 1] * dir[1] + normals[3 * i + 2] * dir[2]
    // Only what faces forward or up (the toe, the laces, the tongue): the side photo has the sides square on.
    // And of the sole only its toe, square ahead (along its sides the other shoe, and the shadow between them,
    // crowd round it in the photo); the side photo can't see that end at all.
    const ahead = Math.max(normals[3 * i + 2], normals[3 * i + 1])
    const above = shoe.positions[3 * i + 1] - shoe.floor
    const upper = Math.max(smoothstep(SOLE_LOW, SOLE_HIGH, above), smoothstep(0.6, 0.85, normals[3 * i + 2]))
    weight[i] = seen && onShoe ? smoothstep(0.15, 0.6, facing) * smoothstep(0.2, 0.55, ahead) * upper : 0
  }
  return { uv, weight }
}

// The shoe's longest reach across its middle, times two (its length, near enough).
function extent(shoe) {
  let most = 0
  for (let i = 0; i < shoe.count; i++) most = Math.max(most, Math.hypot(shoe.positions[3 * i], shoe.positions[3 * i + 1], shoe.positions[3 * i + 2]))
  return 2 * most
}

// The shoe's outline from a direction at a set scale (cell: metres a square), its middle at the grid's:
// { grid, x0, x1, y0, y1 } (the squares it covers).
function placed(shoe, turn, pitch, mirror, cell) {
  const { X, Y } = view(shoe, turn, pitch, mirror)
  const N = PLACE_GRID, C = N / 2, grid = new Uint8Array(N * N), index = shoe.index
  const gx = i => X[i] / cell + C, gy = i => C - Y[i] / cell
  for (let t = 0; t < index.length; t += 3) rasterTriangle(N, [gx(index[t]), gy(index[t])], [gx(index[t + 1]), gy(index[t + 1])], [gx(index[t + 2]), gy(index[t + 2])], null, grid)
  let x0 = N, x1 = -1, y0 = N, y1 = -1
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) if (grid[y * N + x]) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y) }
  return { grid, x0, x1, y0, y1 }
}

function unionBox(a, b, off) {
  let x0 = a.x0, x1 = a.x1, y0 = a.y0, y1 = a.y1
  if (b) { x0 = Math.min(x0, b.x0 + off[0]); x1 = Math.max(x1, b.x1 + off[0]); y0 = Math.min(y0, b.y0 + off[1]); y1 = Math.max(y1, b.y1 + off[1]) }
  return { cx: (x0 + x1 + 1) / 2, cy: (y0 + y1 + 1) / 2, w: x1 - x0 + 1, h: y1 - y0 + 1 }
}

// The first outline and (moved by off) the second, together, on a GRID square as photoGrid draws the photo's.
function together(a, b, off) {
  const N = PLACE_GRID, box = unionBox(a, b, off), span = Math.max(box.w, box.h) * 1.02, out = new Uint8Array(GRID * GRID)
  for (let gy = 0; gy < GRID; gy++) for (let gx = 0; gx < GRID; gx++) {
    const x = Math.round(box.cx + (gx / (GRID - 1) - 0.5) * span), y = Math.round(box.cy + (gy / (GRID - 1) - 0.5) * span)
    let v = x >= 0 && y >= 0 && x < N && y < N && a.grid[y * N + x]
    if (!v && b) { const bx = x - off[0], by = y - off[1]; v = bx >= 0 && by >= 0 && bx < N && by < N && b.grid[by * N + bx] }
    out[gy * GRID + gx] = v ? 1 : 0
  }
  return out
}

// The shoe's points centred on its box, its triangles, and its normals facing out.
function shoeOf(geometry) {
  const p = geometry.attributes.position.array, count = p.length / 3
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity, z0 = Infinity, z1 = -Infinity
  for (let i = 0; i < count; i++) { x0 = Math.min(x0, p[3 * i]); x1 = Math.max(x1, p[3 * i]); y0 = Math.min(y0, p[3 * i + 1]); y1 = Math.max(y1, p[3 * i + 1]); z0 = Math.min(z0, p[3 * i + 2]); z1 = Math.max(z1, p[3 * i + 2]) }
  const c = [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2]
  const positions = new Float32Array(3 * count)
  for (let i = 0; i < count; i++) for (let d = 0; d < 3; d++) positions[3 * i + d] = p[3 * i + d] - c[d]
  if (!geometry.attributes.normal) geometry.computeVertexNormals()
  const normals = Float32Array.from(geometry.attributes.normal.array)
  let out = 0
  for (let i = 0; i < count; i++) for (let d = 0; d < 3; d++) out += normals[3 * i + d] * positions[3 * i + d]
  if (out < 0) for (let k = 0; k < normals.length; k++) normals[k] = -normals[k]
  return { positions, normals, count, floor: y0 - c[1], index: geometry.index ? geometry.index.array : Uint32Array.from({ length: count }, (_, i) => i) }
}

// The camera's direction from the shoe (unit), turned round it by `turn` degrees from its side (+x: turn 0 sees
// the shoe's outer side, 90 its toe) and looking down by `pitch`.
function cameraDir(turn, pitch) {
  const t = (turn * Math.PI) / 180, q = (pitch * Math.PI) / 180
  return [Math.cos(t) * Math.cos(q), Math.sin(q), Math.sin(t) * Math.cos(q)]
}

// The shoe seen from a direction: each point's screen x and y (y up) and depth (larger: nearer the camera).
function view(shoe, turn, pitch, mirror) {
  const d = cameraDir(turn, pitch)
  // Screen right: across the direction, level; screen up: square to both.
  let r = [d[2], 0, -d[0]]
  const rl = Math.hypot(r[0], r[2]) || 1
  r = [r[0] / rl, 0, r[2] / rl]
  const u = [d[1] * r[2] - d[2] * r[1], d[2] * r[0] - d[0] * r[2], d[0] * r[1] - d[1] * r[0]]
  const n = shoe.count, X = new Float32Array(n), Y = new Float32Array(n), Z = new Float32Array(n), p = shoe.positions
  for (let i = 0; i < n; i++) {
    const x = mirror ? -p[3 * i] : p[3 * i], y = p[3 * i + 1], z = p[3 * i + 2]
    X[i] = x * r[0] + y * r[1] + z * r[2]
    Y[i] = x * u[0] + y * u[1] + z * u[2]
    Z[i] = x * d[0] + y * d[1] + z * d[2]
  }
  return { X, Y, Z }
}

// The shoe's outline from a direction on a GRID square, its longer side across the grid, centred.
function outline(shoe, turn, pitch, mirror, N) {
  const { X, Y } = view(shoe, turn, pitch, mirror)
  const box = boxOf(X, Y, shoe.count), span = Math.max(box.w, box.h) * 1.02
  const gx = i => ((X[i] - box.cx) / span + 0.5) * (N - 1), gy = i => (0.5 - (Y[i] - box.cy) / span) * (N - 1)
  const grid = new Uint8Array(N * N), index = shoe.index
  for (let t = 0; t < index.length; t += 3) rasterTriangle(N, [gx(index[t]), gy(index[t])], [gx(index[t + 1]), gy(index[t + 1])], [gx(index[t + 2]), gy(index[t + 2])], null, grid)
  return grid
}

// The photo's mask on a GRID square the same way.
function photoGrid(mask, w, h, N) {
  const box = maskBox(mask, w, h)
  if (!box.w) return null
  const span = Math.max(box.w, box.h) * 1.02, grid = new Uint8Array(N * N)
  for (let gy = 0; gy < N; gy++) for (let gx = 0; gx < N; gx++) {
    const x = Math.round(box.cx + (gx / (N - 1) - 0.5) * span), y = Math.round(box.cy + (gy / (N - 1) - 0.5) * span)
    grid[gy * N + gx] = x >= 0 && y >= 0 && x < w && y < h && mask[y * w + x] ? 1 : 0
  }
  return grid
}

function overlap(a, b) {
  let both = 0, either = 0
  for (let i = 0; i < a.length; i++) { if (a[i] && b[i]) both++; if (a[i] || b[i]) either++ }
  return either ? both / either : 0
}

function boxOf(X, Y, n) {
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity
  for (let i = 0; i < n; i++) { x0 = Math.min(x0, X[i]); x1 = Math.max(x1, X[i]); y0 = Math.min(y0, Y[i]); y1 = Math.max(y1, Y[i]) }
  return { cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, w: x1 - x0, h: y1 - y0 }
}

function maskBox(mask, w, h) {
  let x0 = w, x1 = -1, y0 = h, y1 = -1
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (mask[y * w + x]) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y) }
  return x1 < 0 ? { w: 0, h: 0, cx: 0, cy: 0 } : { cx: (x0 + x1 + 1) / 2, cy: (y0 + y1 + 1) / 2, w: x1 - x0 + 1, h: y1 - y0 + 1 }
}

function near(mask, w, h, x, y, r) {
  for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) {
    const xx = x + dx, yy = y + dy
    if (xx >= 0 && yy >= 0 && xx < w && yy < h && mask[yy * w + xx]) return true
  }
  return false
}

// A triangle drawn on an N by N grid: filled (out: a mask) or, with depths, the nearest depth kept (out: depths).
function rasterTriangle(N, a, b, c, z, out) {
  const xmin = Math.max(0, Math.floor(Math.min(a[0], b[0], c[0]))), xmax = Math.min(N - 1, Math.ceil(Math.max(a[0], b[0], c[0])))
  const ymin = Math.max(0, Math.floor(Math.min(a[1], b[1], c[1]))), ymax = Math.min(N - 1, Math.ceil(Math.max(a[1], b[1], c[1])))
  const area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
  if (Math.abs(area) < 1e-9) return
  for (let y = ymin; y <= ymax; y++) for (let x = xmin; x <= xmax; x++) {
    const w0 = ((b[0] - x) * (c[1] - y) - (b[1] - y) * (c[0] - x)) / area
    const w1 = ((c[0] - x) * (a[1] - y) - (c[1] - y) * (a[0] - x)) / area
    const w2 = 1 - w0 - w1
    if (w0 < -0.02 || w1 < -0.02 || w2 < -0.02) continue
    if (!z) out[y * N + x] = 1
    else {
      const d = w0 * z[0] + w1 * z[1] + w2 * z[2]
      if (d > out[y * N + x]) out[y * N + x] = d
    }
  }
}

function smoothstep(a, b, x) {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}

export const testing = { cameraDir, view, outline, overlap, photoGrid, shoeOf, placed, together, extent }
