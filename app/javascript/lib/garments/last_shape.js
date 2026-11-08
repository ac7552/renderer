// A closed shoe built on a last, fitted to its side photo: a sole slab as thick as the photo's sole, flat
// underneath and square-edged; an upper whose walls rise straight from the sole and round over into the
// toe box and the vamp at the photo's topline; and, from the heel to the throat, the opening the foot goes
// into (the collar's rim at the topline, the inside falling away to the insole). Seen from above it has a
// last's plan, not the foot's: a round heel cup, a narrower waist, the ball at its widest and the toe
// tapering round, pointed or square by the family (lasts.js's `square`); from above, a shop photo's own
// outline when there is one.
//
// hull.js carves a shoe out of a block by its photos and rounds it in from the outline's edges every way,
// which gave sneakers and boots a pillow's shape: a rounded sole, a domed toe, the mannequin's foot standing
// through the walls. A shoe on a heel, a sandal, a slide or a pump stays carved (its stem, its straps and its
// openings are the photo's own shapes).
//
// Metres, in the scene, on the same scale as hull.js (the side photo's length is the foot's with the toe
// room), with userData.photo as it sets it, so wrapShoePhoto lays the photos on the same way.
import * as THREE from "three"

// Stations along the shoe (closer together at its ends) and points round each one.
const STATIONS = 72, AROUND = 44, SOLE_AROUND = 16
// Where the throat is (the opening ends and the vamp closes over the foot), as a share of the length from the
// heel, by family; and how far down inside the opening the insole is, as a share of the upper's height.
const THROAT = { runner: 0.42, court: 0.42, chunky: 0.42, hightop: 0.44, chelsea: 0.46, combat: 0.46, tall: 0.46, derby: 0.46, loafer: 0.52, flat: 0.7 }
const INSOLE = 0.18
// How square the upper's cross-section is (a superellipse's exponent): a boot's squarer, a runner's rounder.
const ROUND = { runner: 2.6, court: 2.8, chunky: 2.8, hightop: 3, chelsea: 3.2, combat: 3.2, tall: 3.2, derby: 2.8, loafer: 2.6, flat: 2.4 }
// The families built this way.
export const LAST_FAMILIES = new Set(Object.keys(THROAT))

// body, frame, side: the foot to stand on; outline: shoeSide's reading of the side photo; views: shoeView
// readings (a view from above sets the plan); style: the last (lasts.js's: family, square, thick, toe).
export function lastGeometry(body, frame, side, outline, views, style) {
  if (!outline?.top?.length || !outline?.bottom?.length) return null
  const s = (frame.top - frame.floor) / 1.76
  const floor = frame.floor, thick = (style.thick ?? 0.007) * s
  // The foot's reach, as hull.js reads it: heel to toes and its width, from the skin's points below the ankle.
  const sign = side === "L" ? 1 : -1
  let zmin = Infinity, zmax = -Infinity, xmin = Infinity, xmax = -Infinity
  for (let i = 0; i < body.positions.length / 3; i++) {
    const x = body.positions[3 * i], y = body.positions[3 * i + 1], z = body.positions[3 * i + 2]
    if (frame.part[i] !== 4 || x * sign <= 0 || y >= floor + 0.1 * s) continue
    zmin = Math.min(zmin, z); zmax = Math.max(zmax, z); xmin = Math.min(xmin, x); xmax = Math.max(xmax, x)
  }
  if (!Number.isFinite(zmin)) return null
  const back = zmin - thick - 0.003 * s, front = zmax + thick + (style.toe ?? 0.014) * s
  const span = front - back, centreX = (xmin + xmax) / 2
  const floorLine = Math.max(...outline.bottom)
  const metres = span * outline.aspect / (outline.right - outline.left)
  const at = (list, u) => lerp(list, u)
  // The topline smoothed over a few bins: a pull tab, a lace's loop or a ragged collar in the photo would
  // otherwise stand up as teeth round the opening.
  const topline = smoothList(outline.top, 2)
  const yTop = u => floor + (floorLine - at(topline, u)) * metres
  const yBottom = u => floor + Math.max(0, floorLine - at(outline.bottom, u)) * metres
  // The sole's top: the photo's sole line, else a seventh of the shoe's height there; never thinner than 6 mm.
  const ySole = u => {
    const b = yBottom(u), t = yTop(u)
    const line = outline.sole ? floor + (floorLine - at(outline.sole, u)) * metres : b + (t - b) / 7
    return Math.min(t - 0.01 * s, Math.max(b + 0.006 * s, line))
  }
  // The plan: the half-width at the ball (the foot's and the upper's thickness, a little room), and its
  // share at each point along the last.
  const footHalf = (xmax - xmin) / 2
  const ball = footHalf + thick + 0.004 * s
  const q = Math.min(3.2, Math.max(1.3, style.square ?? 2.2))
  const plan = u => {
    let k
    if (u < 0.12) k = 0.7 * Math.sqrt(Math.max(0, 1 - ((0.12 - u) / 0.12) ** 2))
    else if (u < 0.4) k = 0.7 + 0.08 * ((u - 0.12) / 0.28)
    else if (u < 0.68) k = 0.78 + 0.22 * Math.sin(((u - 0.4) / 0.28) * Math.PI / 2)
    else if (u < 0.8) k = 1
    else k = Math.max(0, 1 - ((u - 0.8) / 0.2) ** q) ** (1 / q)
    return k
  }
  // From above, when the shop shows it: the view's own width along the shoe (its toe and heel ends as
  // photographed), held to between the foot's and twice the plan's.
  const topView = (views ?? []).find(v => v.kind === "top"), topShoe = topView?.shoes?.[0]
  const fromAbove = topShoe?.silhouette ? (() => {
    const rows = topShoe.silhouette, n = rows.length
    const k = span / (topShoe.bottom - topShoe.top)
    return u => {
      const r = Math.min(n - 1, Math.max(0, Math.round((topShoe.toeUp ? 1 - u : u) * (n - 1))))
      const row = rows[r]
      return row ? ((row[1] - row[0]) * k / topView.aspect) / 2 : null
    }
  })() : null
  const halfAt = u => {
    const planned = ball * plan(u)
    const seen = fromAbove?.(u)
    return seen != null && u > 0.04 && u < 0.96 ? Math.min(planned * 1.3, Math.max(planned * 0.8, seen)) : planned
  }
  const family = style.family ?? "court"
  const throat = THROAT[family] ?? 0.44, n = ROUND[family] ?? 2.8
  // How open each station is: 1 back from the throat, closing over a short run past it.
  // (And closed at the very heel: the counter's back wall stands to the topline all across, not notched.)
  const openAt = u => (1 - smoothstep(throat - 0.05, throat + 0.03, u)) * smoothstep(0.035, 0.09, u)
  const stations = Array.from({ length: STATIONS }, (_, i) => 0.003 + 0.994 * (1 - Math.cos((Math.PI * i) / (STATIONS - 1))) / 2)
  const positions = [], soleIndex = [], upperIndex = []
  const put = (x, y, z) => { positions.push(centreX + x, y, z); return positions.length / 3 - 1 }
  // The upper, station by station: up the outer wall from the sole, over the top (the vamp, or the collar's
  // rim and the opening inside it), down the inner wall.
  const wall = 0.3   // the share of the upper's height that rises straight before it rounds over
  const rings = stations.map(u => {
    const z = back + u * span, ys = ySole(u), yt = Math.max(ys + 0.004 * s, yTop(u))
    const W = Math.max(0.002 * s, halfAt(u)), H = yt - ys, yw = ys + wall * H, open = openAt(u)
    const ring = []
    for (let k = 0; k < AROUND; k++) {
      const t = k / (AROUND - 1)
      let x, y
      if (t < 0.15) { x = W; y = ys + (yw - ys) * (t / 0.15) }
      else if (t > 0.85) { x = -W; y = ys + (yw - ys) * ((1 - t) / 0.15) }
      else {
        const phi = ((t - 0.15) / 0.7) * Math.PI
        const c = Math.cos(phi), sn = Math.sin(phi)
        x = W * Math.sign(c) * Math.abs(c) ** (2 / n)
        y = yw + (yt - yw) * Math.abs(sn) ** (2 / n)
        // The opening: inside the collar's rim the top falls to the insole (a rim a thickness wide).
        if (open > 0) {
          const inner = Math.min(1, Math.max(0, (W - thick * 1.6 - Math.abs(x)) / Math.max(1e-6, W * 0.25)))
          y -= open * inner * (y - (ys + INSOLE * H))
        }
      }
      ring.push(put(x, y, z))
    }
    return ring
  })
  for (let i = 0; i + 1 < rings.length; i++) for (let k = 0; k + 1 < AROUND; k++) {
    const a = rings[i][k], b = rings[i][k + 1], c = rings[i + 1][k + 1], d = rings[i + 1][k]
    upperIndex.push(a, b, c, a, c, d)
  }
  // The sole: a slab under it, its edge a little proud of the upper's (the welt), flat underneath, its corners
  // rounded a few millimetres.
  const r = 0.003 * s, flare = 0.0025 * s
  const soleRings = stations.map(u => {
    const z = back + u * span, yb = yBottom(u), ys = ySole(u), W = Math.max(0.002 * s, halfAt(u) * 1.03 + flare * plan(u))
    const ring = []
    for (let k = 0; k < SOLE_AROUND; k++) {
      const a = (k / SOLE_AROUND) * 2 * Math.PI
      // A rounded rectangle, W across and (ys - yb) tall, by a superellipse of high power.
      const c = Math.cos(a), sn = Math.sin(a), p = 2 / 8
      const x = W * Math.sign(c) * Math.abs(c) ** p
      const y = (yb + ys) / 2 + ((ys - yb) / 2) * Math.sign(sn) * Math.abs(sn) ** p
      ring.push(put(x, y, z))
    }
    void r
    return ring
  })
  for (let i = 0; i + 1 < soleRings.length; i++) for (let k = 0; k < SOLE_AROUND; k++) {
    const k2 = (k + 1) % SOLE_AROUND
    const a = soleRings[i][k], b = soleRings[i][k2], c = soleRings[i + 1][k2], d = soleRings[i + 1][k]
    soleIndex.push(a, d, c, a, c, b)
  }
  // The ends closed: the sole's and the upper's last rings to a point in their middle.
  for (const [rings2, list, closed, flip] of [[soleRings, soleIndex, true, false], [rings, upperIndex, false, true]]) {
    for (const [ring, end] of [[rings2[0], 0], [rings2[rings2.length - 1], 1]]) {
      let cx = 0, cy = 0
      for (const v of ring) { cx += positions[3 * v]; cy += positions[3 * v + 1] }
      const mid = put(cx / ring.length - centreX, cy / ring.length, positions[3 * ring[0] + 2])
      const count = closed ? ring.length : ring.length - 1
      for (let k = 0; k < count; k++) {
        const a = ring[k], b = ring[(k + 1) % ring.length]
        if ((end === 0) !== flip) list.push(mid, b, a)
        else list.push(mid, a, b)
      }
    }
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3))
  geometry.setIndex([...soleIndex, ...upperIndex])
  geometry.addGroup(0, soleIndex.length, 0)
  geometry.addGroup(soleIndex.length, upperIndex.length, 1)
  geometry.computeVertexNormals()
  const within = (x, y, z) => {
    const u = (z - back) / span
    if (u < 0 || u > 1) return false
    return y >= yBottom(u) - 0.002 * s && y <= yTop(u) && Math.abs(x - centreX) <= halfAt(u) * 1.05 + flare
  }
  let widest = 0
  for (const u of stations) widest = Math.max(widest, halfAt(u))
  geometry.userData.photo = {
    floor, back, length: span, metres, top: u => yTop(Math.min(1, Math.max(0, u))), within, centreX, widest, open: false,
    hull: { last: family, throat, views: (views ?? []).map(v => v.kind), fromAbove: Boolean(fromAbove), span: +span.toFixed(3) }
  }
  return geometry
}

// Whether a shoe is built on a last (lastGeometry) rather than carved (hull.js): a closed shoe of a family
// above, flat underfoot (no heel a centimetre and more off the floor under its arch).
export function onLast(style, outline) {
  if (!LAST_FAMILIES.has(style?.family)) return false
  // (A sneaker's sole rises a centimetre or two to its heel and still stands flat: only a real heel, its arch
  // off the floor, below, or a tall one, is carved.)
  if ((style.heel ?? 0) > 0.035) return false
  if (outline?.bottom?.length) {
    const floorLine = Math.max(...outline.bottom), tall = floorLine - Math.min(...outline.top)
    // (Under the arch, the photo's outline lifted off its floor by more than a tenth of the shoe's height.)
    if (floorLine - lerp(outline.bottom, 0.45) > tall * 0.12) return false
  }
  return true
}

function lerp(list, u) {
  const f = Math.min(1, Math.max(0, u)) * (list.length - 1), k = Math.min(list.length - 2, Math.floor(f)), t = f - k
  return list[k] * (1 - t) + list[k + 1] * t
}

// A running median over 2r + 1 neighbours (a median, not a mean: a tab's spike goes, the collar's step stays).
function smoothList(list, r) {
  return list.map((_, i) => {
    const near = []
    for (let k = Math.max(0, i - r); k <= Math.min(list.length - 1, i + r); k++) near.push(list[k])
    near.sort((a, b) => a - b)
    return near[near.length >> 1]
  })
}

function smoothstep(a, b, x) {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}
