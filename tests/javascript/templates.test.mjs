// Run with: node --test tests/javascript/*.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import "./support/lib.mjs"

const { readTemplate, openTemplate, templateGeometry, templateFor } = await import("lib/garments/templates")
const { lastFrame } = await import("lib/garments/last_shape")

const bin = name => { const b = readFileSync(new URL(`../../renderer/static/shoes/${name}.bin`, import.meta.url)); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) }

function leg() {
  const positions = [], part = []
  for (let k = 0; k < 14; k++) {
    const y = k * 0.02
    for (let j = 0; j < 24; j++) { const a = (j / 24) * 2 * Math.PI, rz = y < 0.05 ? 0.12 : 0.045; positions.push(0.1 + 0.045 * Math.sin(a), y, (y < 0.05 ? 0.04 : 0) + rz * Math.cos(a)); part.push(4) }
  }
  return { body: { positions: Float32Array.from(positions) }, frame: { floor: 0, top: 1.76, part } }
}
// A boot's side: tall at the heel, low over the toe.
function side() {
  const n = 64, top = [], bottom = [], sole = []
  for (let b = 0; b < n; b++) { const u = b / (n - 1); bottom.push(0.8); sole.push(0.74); top.push(u < 0.45 ? 0.35 : 0.35 + 0.3 * ((u - 0.45) / 0.55) ** 0.7) }
  return { left: 0.1, right: 0.9, aspect: 1, top, bottom, sole }
}

test("a template's file is read: its points inside its box, its triangles over them, its parts grouped", async () => {
  for (const name of ["runner", "chunky"]) assert.equal((await openTemplate(bin(name))).name, name)
  const t = (await openTemplate(bin("workboot")))
  assert.equal(t.name, "workboot")
  assert.equal(t.positions.length, 3 * t.count)
  const [lo, hi] = t.box
  for (let i = 0; i < t.count; i++) for (let d = 0; d < 3; d++) assert.ok(t.positions[3 * i + d] >= lo[d] - 1e-6 && t.positions[3 * i + d] <= hi[d] + 1e-6)
  for (const v of t.index) assert.ok(v < t.count)
  assert.deepEqual(t.groups.map(g => g[2]), [0, 1, 2, 3, 4])
  assert.equal(t.profile.top.length, 64)
})

test("a template is stretched to the side photo: its upper's top along the shoe on the photo's topline, its sole on the floor", async () => {
  const { body, frame } = leg()
  const style = { family: "combat", square: 2.2, thick: 0.007, toe: 0.014 }
  const t = (await openTemplate(bin("workboot")))
  const g = templateGeometry(body, frame, "L", side(), [], style, t)
  const f = lastFrame(body, frame, "L", side(), [], style)
  const p = g.attributes.position.array, n = p.length / 3
  // The upper's points (group 1) binned along the shoe: the highest in each bin at the photo's topline there.
  const upper = new Set()
  const index = g.index.array
  for (const { start, count, materialIndex } of g.groups) if (materialIndex === 1) for (let k = start; k < start + count; k++) upper.add(index[k])
  const bins = 20, high = new Array(bins).fill(-Infinity)
  let low = Infinity
  for (let i = 0; i < n; i++) {
    low = Math.min(low, p[3 * i + 1])
    if (!upper.has(i)) continue
    const u = (p[3 * i + 2] - f.back) / f.span
    const b = Math.min(bins - 1, Math.max(0, Math.floor(u * bins)))
    high[b] = Math.max(high[b], p[3 * i + 1])
  }
  for (let b = 2; b < bins - 2; b++) {
    const u = (b + 0.5) / bins
    assert.ok(Math.abs(high[b] - f.yTop(u)) < 0.02, `bin ${b}: ${high[b].toFixed(3)} against ${f.yTop(u).toFixed(3)}`)
  }
  assert.ok(Math.abs(low - f.floor) < 0.004, `the sole's bottom at ${low}`)
  assert.equal(g.userData.photo.hull.template, "workboot")
})

test("a template is chosen by the family, unless the photo's side is much more like another's", () => {
  assert.equal(templateFor({ family: "loafer" }, null).name, "loafer")
  assert.equal(templateFor({ family: "sandal" }, null), null)
  // A runner and a chunky sneaker have their own (a rockered midsole; a platform), not the court's.
  assert.equal(templateFor({ family: "runner" }, null).name, "runner")
  assert.equal(templateFor({ family: "chunky" }, null).name, "chunky")
})

test("a scanned shoe is fitted in its own shape: the foot's length, the photo's height, mirrored for the right foot, with its shades", async () => {
  const t = await openTemplate(bin("scan_boot_chukka"))
  assert.equal(t.scan, true)
  assert.equal(t.shade.length, t.count)
  const { body, frame } = leg()
  const style = { family: "combat", thick: 0.007, toe: 0.014 }
  const f = lastFrame(body, frame, "L", side(), [], style)
  const g = templateGeometry(body, frame, "L", side(), [], style, t)
  const p = g.attributes.position.array
  let zmin = Infinity, zmax = -Infinity, ymin = Infinity, ymax = -Infinity
  for (let i = 0; i < p.length; i += 3) { zmin = Math.min(zmin, p[i + 2]); zmax = Math.max(zmax, p[i + 2]); ymin = Math.min(ymin, p[i + 1]); ymax = Math.max(ymax, p[i + 1]) }
  assert.ok(Math.abs(zmin - f.back) < 1e-3 && Math.abs(zmax - (f.back + f.span)) < 1e-3, "heel to toe on the foot's reach")
  assert.ok(Math.abs(ymin - frame.floor) < 1e-3, "on the floor")
  // Its own proportions, within a quarter: not pulled to the photo's taller shaft.
  const own = (t.box[1][1] - t.box[0][1]) / (t.box[1][2] - t.box[0][2]), shown = (ymax - ymin) / (zmax - zmin)
  assert.ok(shown >= own * 0.79 && shown <= own * 1.26, `height over length ${shown.toFixed(3)}, the scan's ${own.toFixed(3)}`)
  assert.equal(g.attributes.aShade.count, t.count)
  assert.equal(g.userData.photo.hull.scan, true)
  // The right foot's: the same shoe mirrored across the foot, its triangles rewound.
  const r = templateGeometry(body, frame, "R", side(), [], style, t)
  const fr = lastFrame(body, frame, "R", side(), [], style)
  if (fr) {
    const q = r.attributes.position.array
    assert.ok(Math.abs((q[0] - fr.centreX) + (p[0] - f.centreX)) < 1e-6)
    assert.equal(r.index.array[1], g.index.array[2])
  }
})

// Which way a shoe's inside faces (x across, z heel to toe): its sole, each stretch's points within 12 mm of its
// lowest, comes in at the waist on the inside, under the arch, against the line from the heel's middle to the
// ball's (as scan_templates.py's right_shoe). -1: the inside at -x, a left shoe (the left foot stands at +x).
function insideOf(P) {
  const n = 40, count = P.length / 3
  let zmin = Infinity, zmax = -Infinity
  for (let i = 0; i < count; i++) { zmin = Math.min(zmin, P[3 * i + 2]); zmax = Math.max(zmax, P[3 * i + 2]) }
  const length = zmax - zmin, bin = i => Math.min(n - 1, Math.floor(((P[3 * i + 2] - zmin) / length) * n))
  const lowest = new Array(n).fill(Infinity), lo = new Array(n).fill(Infinity), hi = new Array(n).fill(-Infinity)
  for (let i = 0; i < count; i++) lowest[bin(i)] = Math.min(lowest[bin(i)], P[3 * i + 1])
  for (let i = 0; i < count; i++) {
    const b = bin(i)
    if (P[3 * i + 1] < lowest[b] + (0.012 * length) / 0.27) { lo[b] = Math.min(lo[b], P[3 * i]); hi[b] = Math.max(hi[b], P[3 * i]) }
  }
  const mean = (from, to) => { let s = 0, c = 0; for (let b = 0; b < n; b++) { const u = (b + 0.5) / n; if (u > from && u < to) { s += (lo[b] + hi[b]) / 2; c++ } } return s / c }
  const heel = mean(0.1, 0.2), ball = mean(0.65, 0.75)
  let out = 0
  for (let b = 0; b < n; b++) {
    const u = (b + 0.5) / n
    if (u <= 0.36 || u >= 0.52) continue
    const line = heel + ((ball - heel) * (u - 0.15)) / 0.55
    out += (line - lo[b]) - (hi[b] - line)
  }
  return out > 0 ? 1 : -1
}

test("every scanned shoe is a left one, and on the page each foot wears its own: the arch towards the other foot", async () => {
  const index = JSON.parse(readFileSync(new URL("../../renderer/static/shoes/index.json", import.meta.url)))
  const scans = Object.keys(index).filter(name => index[name].scan)
  assert.ok(scans.length > 30)
  // Both legs: the left one at +x, the right one its mirror at -x.
  const one = leg(), p = one.body.positions, n = p.length / 3
  const positions = new Float32Array(2 * p.length)
  positions.set(p)
  for (let i = 0; i < n; i++) { positions[3 * (n + i)] = -p[3 * i]; positions[3 * (n + i) + 1] = p[3 * i + 1]; positions[3 * (n + i) + 2] = p[3 * i + 2] }
  const body = { positions }, frame = { ...one.frame, part: [...one.frame.part, ...one.frame.part] }
  const style = { family: "court", thick: 0.007, toe: 0.014 }
  for (const name of scans) {
    const t = await openTemplate(bin(name))
    assert.equal(insideOf(t.positions), -1, `${name}: a left shoe, its inside at -x`)
    // The left foot's (at +x) inside towards -x, the right foot's towards +x: the other foot, both.
    const left = templateGeometry(body, frame, "L", side(), [], style, t), right = templateGeometry(body, frame, "R", side(), [], style, t)
    assert.equal(insideOf(left.attributes.position.array), -1, `${name}: the left foot's`)
    assert.equal(insideOf(right.attributes.position.array), 1, `${name}: the right foot's`)
  }
})

test("a shoe its words call a dress shoe isn't fitted from a sneaker's scan, however near its side", async () => {
  const { scanFor } = await import("lib/garments/templates")
  // (The page fetches the list; here it's read from the file.)
  const index = JSON.parse(readFileSync(new URL("../../renderer/static/shoes/index.json", import.meta.url)))
  const scans = Object.keys(index).filter(name => index[name].scan)
  // A side like a leather court sneaker's (the Reebok's own profile): a Gibson by its words still gets a derby's.
  const entry = index.scan_court_leather, length = entry.box[1][2] - entry.box[0][2]
  const n = 64, top = [], bottom = []
  for (let b = 0; b < n; b++) { const u = b / (n - 1), at = list => list[Math.round(u * (list.length - 1))]; bottom.push(0.8); top.push(0.8 - ((at(entry.profile.top) - entry.box[0][1]) / length) * 0.8) }
  const outline = { left: 0.1, right: 0.9, aspect: 1, top, bottom }
  const sneaker = name => index[name].families.every(f => ["court", "runner", "chunky", "hightop"].includes(f))
  // An "oxford" alone can be a sneaker's low cut: it may still take the sneaker's scan nearest its side.
  assert.ok(sneaker(scanFor({ family: "derby" }, outline, "Converse Chuck 70 Oxford", index)))
  const pick = scanFor({ family: "derby" }, outline, "Solovair 3-Eye Gibson Shoe", index)
  assert.ok(scans.includes(pick))
  assert.ok(!sneaker(pick), `a Gibson from ${pick}`)
  // Nor, when no scan stands near (a photo read as heeled), from the nearest of all the templates and scans.
  const lifted = { ...outline, bottom: bottom.map((b, k) => (k / (n - 1) > 0.2 && k / (n - 1) < 0.45 ? b - 0.12 : b)) }
  const chosen = templateFor({ family: "derby" }, lifted, "Solovair 3-Eye Gibson Shoe", index)
  assert.ok(chosen && !(index[chosen.name].scan ? sneaker(chosen.name) : ["court", "runner", "chunky", "hightop"].includes(chosen.name)), `a Gibson from ${chosen?.name}`)
})

test("a scanned shoe gives to the photo at its toe: a sprung toe lies on the photo's flat sole, its toe box as tall as the photo's", async () => {
  // (The 6-inch boot's scan: its toe 1 cm off the floor, a low toe box.)
  const t = await openTemplate(bin("scan_boot_6inch"))
  const { body, frame } = leg()
  const style = { family: "combat", thick: 0.007, toe: 0.014 }
  const f = lastFrame(body, frame, "L", side(), [], style)
  const p = templateGeometry(body, frame, "L", side(), [], style, t).attributes.position.array
  const own = t.positions, scale = f.span / (t.box[1][2] - t.box[0][2])
  let under = Infinity, top = -Infinity, ownUnder = Infinity
  for (let i = 0; i < p.length; i += 3) {
    const u = (p[i + 2] - f.back) / f.span
    if (u < 0.86 || u > 0.94) continue
    under = Math.min(under, p[i + 1]); top = Math.max(top, p[i + 1]); ownUnder = Math.min(ownUnder, own[i + 1] * scale)
  }
  assert.ok(ownUnder > 0.008, `the scan's own toe stands ${ownUnder.toFixed(4)} off the floor`)
  assert.ok(under - frame.floor < 0.003, `the fitted toe's underside at ${under.toFixed(4)}`)
  assert.ok(Math.abs(top - f.yTop(0.9)) < 0.01, `the toe box's top at ${top.toFixed(3)}, the photo's ${f.yTop(0.9).toFixed(3)}`)
  // Its laces and tongue over the instep stay the scan's own (the one scale's), not pulled to the photo's line.
  let instep = -Infinity, ownInstep = -Infinity
  for (let i = 0; i < p.length; i += 3) {
    const u = (p[i + 2] - f.back) / f.span
    if (u > 0.5 && u < 0.56) { instep = Math.max(instep, p[i + 1]); ownInstep = Math.max(ownInstep, own[i + 1] * scale) }
  }
  assert.ok(instep / ownInstep > 1.1 && instep / ownInstep < 1.3, `the instep at ${(instep / ownInstep).toFixed(3)} of the scan's`)
})
