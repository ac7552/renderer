// Shoe templates: a shoe of each family modelled once (script/shoes/build_templates.py: its sole with its edge and
// tread, the upper's walls, toe box and vamp, the collar and lining, the tongue, eyelets and laces, the seams),
// stretched here to the shop's side photo and painted with its photos as the last-built shoe is (stage.js).
//
// A template's file (public/shoes/<name>.bin, a few hundred kilobytes, fetched once and kept) holds its points over
// a box (Uint16), its triangles, each triangle's part (0 the sole, 1 the upper, 2 the laces, 3 the collar and lining,
// 4 metal) and its profile along its length: the upper's top, the sole's top and bottom, the upper's half width.
// Fitting it is a stretch, height by height along the shoe: the template's sole onto the photo's sole, its upper
// from the sole's top to its topline onto the photo's, its length onto the foot's with the toe room, its width
// onto the last's at the ball (the photo from above when the shop has one).
import * as THREE from "three"
import { lastFrame } from "lib/garments/last_shape"
import { closedFore } from "lib/garments/open_shape"

// The template each family is fitted from.
const TEMPLATE_OF = { combat: "workboot", tall: "workboot", court: "court", chunky: "chunky", runner: "runner", hightop: "hightop", chelsea: "chelsea", derby: "derby", loafer: "loafer", flat: "flat" }
const loaded = new Map()
// The templates' profiles (public/shoes/index.json, a few kilobytes), fetched as the page loads.
let index = null
const indexed = typeof fetch === "function" ? fetch("/shoes/index.json", { cache: "no-cache" }).then(r => (r.ok ? r.json() : null)).then(i => (index = i)).catch(() => null) : Promise.resolve(null)

// The template's name for a last (lasts.js's), or null when its family has none. The family's own, unless the
// side photo's outline is much more like another template's (the listing's words can call a canvas high-top a
// "flat"; a ballet flat's wide opening stretched up to a high-top's collar is a sheet of lining in front of the
// ankle): { name, own } (own: the family's template, so its words' lacing holds). words: the listing's; a shoe
// whose words lace it is only ever switched to a laced template.
export function templateFor(style, outline, words = "") {
  const scan = SCANS_ON ? scanFor(style, outline, words) : null
  if (scan) return { name: scan, own: false, scan: true }
  const own = TEMPLATE_OF[style?.family]
  if (!own) return null
  if (!index?.[own] || !outline?.top?.length) return { name: own, own: true }
  const height = photoHeight(outline)
  const off = name => {
    const { profile, box } = index[name], length = box[1][2] - box[0][2]
    let d = 0, k = 0
    for (let u = 0.04; u <= 0.96; u += 0.02, k++) d += Math.abs(height(u) - (lerp(profile.top, u) - lerp(profile.soleTop, u)) / length)
    return d / k
  }
  const mine = off(own)
  let best = own, least = mine
  const laced = /\blac(?:e|es|ed|ing)\b|eyelets?/i.test(words) && !/laceless|slip[- ]on/i.test(words)
  // A lace-up whose family's template has no laces (a "ballet" sneaker): the nearest laced one, whatever the
  // distance (the flat's wide opening under its laces stands up as flaps of lining).
  if (laced && !index[own].laced) {
    let pick = null, near = Infinity
    for (const name of Object.keys(index)) if (index[name].laced) { const d = off(name); if (d < near) { pick = name; near = d } }
    if (pick) return { name: pick, own: false }
  }
  for (const name of Object.keys(index)) {
    if (laced && !index[name].laced) continue
    const d = off(name)
    if (d < least) { best = name; least = d }
  }
  // (Only when the family's is clearly wrong: well off the photo's side, and another twice as close.)
  return mine > 0.08 && least < mine * 0.5 ? { name: best, own: false } : { name: own, own: true }
}

// A scanned shoe for the last (script/shoes/scan_templates.py: real shoes, each listed with the families it
// stands for): of its family's, the one whose side is nearest the photo's (in shoe lengths; a scan has no sole
// line to measure an upper from). Null for an open shoe (see below), or before the list is in.
const SCANS_ON = typeof location === "undefined" || new URLSearchParams(location.search).get("scans") !== "off"
const SCAN_FAMILIES = new Set(["runner", "chunky", "court", "hightop", "combat", "tall", "chelsea", "derby", "loafer", "flat", "pump", "sandal", "slide"])
// (A listing's words put a low hiker under "boots" and a leather sneaker under "court": a family also takes its
// neighbours' scans, a little further off, so the photo's own height along the shoe picks between them.)
const NEIGHBOURS = {
  combat: ["tall", "chelsea", "derby", "hightop"], tall: ["combat", "chelsea"], chelsea: ["combat", "tall"], hightop: ["combat"],
  runner: ["chunky", "court"], chunky: ["runner"], court: ["runner", "derby"], derby: ["court", "loafer", "combat"],
  loafer: ["derby", "flat"], flat: ["loafer", "pump"], pump: ["flat", "chelsea"], sandal: ["slide"], slide: ["sandal"]
}
// A sandal's or a slide's family closed over the toes in its photo (a sneaker mule, a clog, a fisherman sandal):
// the closed shoes it's nearest, not a footbed and a strap.
const CLOSED_TOE = ["runner", "court", "loafer", "flat", "derby"]
// A heel: the sole under the arch this far off the floor (of the shoe's length); and how near a heeled scan's
// side must be to the photo's (the mean difference along the shoe, of its length) to stand for it.
// (A scan's own: the heeled ones stand 0.14 and up, a lug sole's step under the arch 0.06 at most.)
const HEEL_ARCH = 0.045, SCAN_HEEL = 0.1, HEEL_NEAR = 0.16
const UNLACED = new Set(["loafer", "chelsea", "flat", "tall"])
export function scanFor(style, outline, words = "") {
  const family = style?.family
  if (!SCANS_ON) return null
  if (!index || !SCAN_FAMILIES.has(family) || !outline?.top?.length || !outline?.bottom?.length) return null
  const across = (outline.right - outline.left) || 1
  const seen = u => Math.max(0, lerp(outline.bottom, u) - lerp(outline.top, u)) * outline.aspect / across
  const floorLine = Math.max(...outline.bottom)
  const lifted = u => Math.max(0, floorLine - lerp(outline.bottom, u)) * outline.aspect / across
  // (Closed over the toes: the photo's shoe stands at least 0.42 of its tallest there, open_shape.js's test.)
  const openFamily = family === "sandal" || family === "slide"
  const closedToe = openFamily && closedFore(u => -lerp(outline.top, u), u => -lerp(outline.bottom, u)) >= 0.42
  // An open one (a sandal's straps, a slide's band, a strappy or a thong heel) is built on the foot from its
  // photo as before (open_shape.js): a scan's straps lie as they did on the scanner, not on this foot.
  // (A mule or a slingback too, open behind: the scans are closed round the heel.)
  if (openFamily ? !closedToe : family === "pump" && ((outline.openShare ?? 0) > 0.1 || /\bmules?\b|sling[- ]?back|\bthong|sandal|slipper/i.test(words))) return null
  // A heel in the photo (its sole well off the floor under the arch) is only ever fitted from a heeled scan, and
  // only one about as tall: a stiletto boot to the knee on a flat sheepskin boot lost its heel and its toe.
  // (Its highest between the heel's breast and the ball: a pump's sole comes down to the floor by the middle.)
  const archOf = at => { let most = 0; for (let u = 0.2; u <= 0.45; u += 0.01) most = Math.max(most, at(u)); return most }
  const heeled = archOf(lifted) > HEEL_ARCH
  const near = closedToe ? CLOSED_TOE : NEIGHBOURS[family] ?? []
  const worded = /\blac(?:e|es|ed|ing)\b|eyelets?/i.test(words) && !/laceless|slip[- ]on/i.test(words)
  const laced = worded || (!UNLACED.has(family) && !openFamily && family !== "pump" && style.laces !== false)
  let best = null, least = Infinity
  for (const [name, entry] of Object.entries(index)) {
    if (!entry.scan) continue
    const own = !closedToe && entry.families.includes(family)
    if (!own && !entry.families.some(f => near.includes(f))) continue
    const length = entry.box[1][2] - entry.box[0][2]
    if (heeled !== archOf(u => (lerp(entry.profile.bottom, u) - entry.box[0][1]) / length) > SCAN_HEEL) continue
    let d = 0, k = 0
    // (How high its top stands off the floor along the shoe, and how far its sole does under the arch: a
    // heel's. Not its height from its own sole at the heel: a stiletto's stem is too thin for the photo's
    // outline, which ends above it, and the pump read as a low-heeled one.)
    for (let u = 0.04; u <= 0.96; u += 0.02, k++) {
      d += Math.abs(seen(u) + lifted(u) - (lerp(entry.profile.top, u) - entry.box[0][1]) / length)
      if (u >= 0.25 && u <= 0.6) d += Math.abs(lifted(u) - (lerp(entry.profile.bottom, u) - entry.box[0][1]) / length)
    }
    // (What it is before what it stands in for, its own family before a neighbour's, laced as the shoe is.)
    // (Never a laced one for a shoe with no laces: a knit sock shoe on a chukka wore its laces.)
    if (entry.laced && !laced) continue
    const off = d / k + (entry.families[0] === family ? 0 : own ? 0.008 : 0.02) + (entry.laced === laced ? 0 : 0.03)
    if (off < least) { best = name; least = off }
  }
  return heeled && least > HEEL_NEAR ? null : best
}

// The upper's height over the sole along the photo's shoe, in shoe lengths (as lastFrame reads it).
function photoHeight(outline) {
  const across = (outline.right - outline.left) || 1
  return u => {
    const top = lerp(outline.top, u), bottom = lerp(outline.bottom, u)
    const sole = outline.sole ? lerp(outline.sole, u) : bottom - (bottom - top) / 7
    return Math.max(0, sole - top) * outline.aspect / across
  }
}

// Resolves once the profiles are in (or couldn't be had).
export function templatesIndexed() {
  return indexed
}

// The template if it's here (null if it couldn't be had), undefined while it's still on its way.
export function templateNow(name) {
  const got = loaded.get(name)
  return got && !(got instanceof Promise) ? got.template : undefined
}

// Fetches a template (once); resolves to it, or null.
export function loadTemplate(name) {
  const got = loaded.get(name)
  if (got) return got instanceof Promise ? got : Promise.resolve(got.template)
  const promise = fetch(`/shoes/${name}.bin${index?.[name]?.v ? `?v=${index[name].v}` : ""}`)
    .then(r => (r.ok ? r.arrayBuffer() : null))
    .then(buffer => (buffer ? openTemplate(buffer) : null))
    .catch(() => null)
    .then(template => { loaded.set(name, { template }); return template })
  loaded.set(name, promise)
  return promise
}

// A template's file as fetched: gzipped as packed (script/shoes/pack_templates.py), opened with the browser's own
// gzip, then read. Resolves to readTemplate's.
export async function openTemplate(buffer) {
  const bytes = new Uint8Array(buffer)
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"))
    buffer = await new Response(stream).arrayBuffer()
  }
  return readTemplate(buffer)
}

// A template's file read (once opened): { name, positions (Float32, the template's frame), index, groups, profile,
// laced }. Packed (head.packed 2): each axis's quantised coordinates as changes from the point before, the
// triangles' indices as zigzag varints of the change from the index before.
export function readTemplate(buffer) {
  const view = new DataView(buffer)
  const headLength = view.getUint32(0, true)
  const head = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, 4, headLength)))
  let at = 4 + headLength
  const n = head.count, [lo, hi] = head.box, triangles = head.triangles
  const positions = new Float32Array(3 * n)
  if (head.packed === 2) {
    const d = new Uint16Array(buffer.slice(at, at + 6 * n))
    at += 6 * n + ((6 * n) % 4 ? 2 : 0)
    for (let a = 0; a < 3; a++) {
      let q = 0
      for (let i = 0; i < n; i++) { q = (q + d[a * n + i]) & 0xffff; positions[3 * i + a] = lo[a] + (q / 65535) * (hi[a] - lo[a]) }
    }
    const bytes = new Uint8Array(buffer, at, head.indexBytes)
    const index = n > 65535 ? new Uint32Array(3 * triangles) : new Uint16Array(3 * triangles)
    let k = 0, last = 0, acc = 0, shift = 0
    for (let i = 0; i < bytes.length; i++) {
      const b = bytes[i]
      acc += (b & 127) * 2 ** shift
      if (b & 128) { shift += 7; continue }
      last += acc % 2 ? -(acc + 1) / 2 : acc / 2
      index[k++] = last
      acc = shift = 0
    }
    // (A scanned shoe's shade a point, after its triangles' parts: see script/shoes/scan_templates.py.)
    const shadeAt = at + head.indexBytes + triangles
    const shade = head.shade && buffer.byteLength >= shadeAt + n ? new Uint8Array(buffer.slice(shadeAt, shadeAt + n)) : null
    return { ...head, positions, index, shade }
  }
  const q = new Uint16Array(buffer.slice(at, at + 6 * n))
  at += 6 * n + ((6 * n) % 4 ? 2 : 0)
  for (let i = 0; i < 3 * n; i++) positions[i] = lo[i % 3] + (q[i] / 65535) * (hi[i % 3] - lo[i % 3])
  const big = n > 65535
  const index = big ? new Uint32Array(buffer.slice(at, at + 12 * triangles)) : new Uint16Array(buffer.slice(at, at + 6 * triangles))
  return { ...head, positions, index }
}

// The template stretched to the shoe in the side photo, on this foot: a BufferGeometry with the last-built shoe's
// groups and userData.photo (so the photos are laid on it the same way), or null without a side photo.
export function templateGeometry(body, frame, side, outline, views, style, template) {
  const f = lastFrame(body, frame, side, outline, views, style)
  if (!f || !template) return null
  const { s, floor, back, span, centreX, metres, yBottom, ySole, ball, fromAbove } = f
  // The topline smoothed further than the last's (a running mean over a twentieth of the length after its
  // median): the template's collar is a smooth roll, and the photo's teeth (a pull tab, a lace's loop, a ragged
  // cut-out) would pull its walls up and down in steps.
  const TOPS = 96, raw = Array.from({ length: TOPS }, (_, k) => f.yTop(k / (TOPS - 1)))
  const tops = raw.map((_, k) => { let sum = 0, c = 0; for (let j = Math.max(0, k - 3); j <= Math.min(TOPS - 1, k + 3); j++) { sum += raw[j]; c++ } return sum / c })
  const yTop = u => lerp(tops, u)
  const { positions: P, profile, box } = template
  const [lo, hi] = box
  const along = z => (z - lo[2]) / (hi[2] - lo[2])
  const prof = key => u => lerp(profile[key], u)
  const topT = prof("top"), soleT = prof("soleTop"), bottomT = prof("bottom"), halfT = prof("half")
  // Across: the template's ball onto the last's (and, from above, its width along the shoe where the shop shows
  // it, held near the ball's scale).
  let templateBall = 0
  for (let u = 0.55; u <= 0.85; u += 0.01) templateBall = Math.max(templateBall, halfT(u))
  let across = ball / templateBall
  if (fromAbove) {
    const ratios = []
    for (let u = 0.2; u <= 0.85; u += 0.05) { const seen = fromAbove(u); if (seen) ratios.push(seen / halfT(u)) }
    if (ratios.length > 4) {
      ratios.sort((a, b) => a - b)
      across = Math.min(across * 1.2, Math.max(across * 0.85, ratios[ratios.length >> 1]))
    }
  }
  const n = P.length / 3, out = new Float32Array(3 * n)
  if (template.scan) return scanGeometry(f, template, side, style, views, { across, halfT, topT, bottomT, yTop })
  for (let i = 0; i < n; i++) {
    const x = P[3 * i], y = P[3 * i + 1], z = P[3 * i + 2]
    const u = Math.min(1, Math.max(0, along(z)))
    const tb = bottomT(u), ts = soleT(u), tt = Math.max(ts + 1e-4, topT(u))
    const yb = yBottom(u), ys = ySole(u), yt = Math.max(ys + 0.004 * s, yTop(u))
    // The sole onto the photo's sole, the upper (and what's on it) from the sole's top to its topline.
    const Y = y <= ts ? yb + ((y - tb) / Math.max(1e-4, ts - tb)) * (ys - yb) : ys + ((y - ts) / (tt - ts)) * (yt - ys)
    out[3 * i] = centreX + x * across
    out[3 * i + 1] = Y
    out[3 * i + 2] = back + u * span
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute("position", new THREE.BufferAttribute(out, 3))
  geometry.setIndex(new THREE.BufferAttribute(template.index, 1))
  // A lace-up the listing's words call a slip-on (lasts.js's `laces`): its laces and eyelets left off.
  const bare = template.laced && style.laces === false
  for (const [start, count, part] of template.groups) if (!(bare && (part === 2 || part === 4))) geometry.addGroup(start, count, part)
  geometry.computeVertexNormals()
  const half = u => halfT(u) * across
  let widest = 0
  for (let u = 0; u <= 1; u += 0.02) widest = Math.max(widest, half(u))
  const within = (x, y, z) => {
    const u = (z - back) / span
    if (u < 0 || u > 1) return false
    return y >= yBottom(u) - 0.002 * s && y <= yTop(u) && Math.abs(x - centreX) <= half(u) * 1.05
  }
  geometry.userData.photo = {
    floor, back, length: span, metres, top: u => yTop(Math.min(1, Math.max(0, u))), within, centreX, widest, open: false,
    hull: { last: style.family, template: template.name, views: (views ?? []).map(v => v.kind), fromAbove: Boolean(fromAbove), span: +span.toFixed(3) }
  }
  return geometry
}

// A scanned shoe on this foot: kept in its own shape (a real shoe's), its length the foot's with its toe room, its
// width the last's at the ball, its height the photo's (one scale for the whole shoe: the middle of the photo's
// height over the scan's along it, held within a quarter of the scale its length gives). A left shoe as scanned,
// mirrored for the right foot. The photos are laid on it as on any template (userData.photo); aShade is its
// own detail (seams, laces, eyelets, mesh), for the plain colour where the photos don't reach.
function scanGeometry(f, template, side, style, views, { across, halfT, topT, bottomT, yTop }) {
  const { s, floor, back, span, centreX, metres, yBottom, fromAbove } = f
  const { positions: P, box } = template
  const [lo, hi] = box
  const lengthScale = span / (hi[2] - lo[2])
  const ratios = []
  for (let u = 0.06; u <= 0.94; u += 0.02) ratios.push((yTop(u) - yBottom(u)) / Math.max(1e-4, topT(u) - bottomT(u)))
  ratios.sort((a, b) => a - b)
  const up = Math.min(lengthScale * 1.25, Math.max(lengthScale * 0.8, ratios[ratios.length >> 1]))
  const sign = side === "R" ? -1 : 1
  const n = P.length / 3, out = new Float32Array(3 * n)
  for (let i = 0; i < n; i++) {
    out[3 * i] = centreX + sign * P[3 * i] * across
    out[3 * i + 1] = floor + (P[3 * i + 1] - lo[1]) * up
    out[3 * i + 2] = back + ((P[3 * i + 2] - lo[2]) / (hi[2] - lo[2])) * span
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute("position", new THREE.BufferAttribute(out, 3))
  let index = template.index
  if (sign < 0) {
    // (Mirrored: its triangles wound the other way, so they still face out.)
    index = new template.index.constructor(template.index.length)
    for (let k = 0; k < index.length; k += 3) { index[k] = template.index[k]; index[k + 1] = template.index[k + 2]; index[k + 2] = template.index[k + 1] }
  }
  geometry.setIndex(new THREE.BufferAttribute(index, 1))
  for (const [start, count, part] of template.groups) geometry.addGroup(start, count, part)
  if (template.shade) geometry.setAttribute("aShade", new THREE.BufferAttribute(Float32Array.from(template.shade, v => Math.min(1.6, Math.max(0.35, v / 128))), 1))
  geometry.computeVertexNormals()
  const top = u => floor + (topT(Math.min(1, Math.max(0, u))) - lo[1]) * up
  const half = u => halfT(u) * across
  let widest = 0
  for (let u = 0; u <= 1; u += 0.02) widest = Math.max(widest, half(u))
  const within = (x, y, z) => {
    const u = (z - back) / span
    return u >= 0 && u <= 1 && y >= floor - 0.002 * s && y <= top(u) && Math.abs(x - centreX) <= half(u) * 1.05
  }
  geometry.userData.photo = {
    floor, back, length: span, metres, top, within, centreX, widest, open: false,
    hull: { last: style.family, template: template.name, scan: true, views: (views ?? []).map(v => v.kind), fromAbove: Boolean(fromAbove), span: +span.toFixed(3) }
  }
  return geometry
}

function lerp(list, u) {
  const f = Math.min(1, Math.max(0, u)) * (list.length - 1), k = Math.min(list.length - 2, Math.floor(f)), t = f - k
  return list[k] * (1 - t) + list[k + 1] * t
}
