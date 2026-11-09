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
    return { ...head, positions, index }
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

function lerp(list, u) {
  const f = Math.min(1, Math.max(0, u)) * (list.length - 1), k = Math.min(list.length - 2, Math.floor(f)), t = f - k
  return list[k] * (1 - t) + list[k + 1] * t
}
