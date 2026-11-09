// Run with: node --test test/javascript/*.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import "./support/lib.mjs"

const { readTemplate, openTemplate } = await import("lib/garments/templates")

// A packed file built here (as pack_templates.py packs): the same points and triangles as the raw one.
async function gzip(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream("gzip"))
  return new Response(stream).arrayBuffer()
}
function varint(values) {
  const out = []
  for (let v of values) { while (v >= 128) { out.push((v & 127) | 128); v = Math.floor(v / 128) } out.push(v) }
  return Uint8Array.from(out)
}
function file(head, body) {
  let h = new TextEncoder().encode(JSON.stringify(head))
  const padded = new Uint8Array(h.length + ((4 - (h.length % 4)) % 4)).fill(32); padded.set(h)
  const out = new Uint8Array(4 + padded.length + body.length)
  new DataView(out.buffer).setUint32(0, padded.length, true); out.set(padded, 4); out.set(body, 4 + padded.length)
  return out
}

test("a packed template reads back as the raw one: points from their changes, triangles from zigzag varints", async () => {
  const q = [[0, 0, 0], [65535, 100, 7], [3, 65535, 40000], [500, 600, 700]]
  const tris = [0, 1, 2, 2, 1, 3, 3, 0, 2]
  const box = [[-1, 0, 2], [1, 3, 4]]
  const head = { name: "t", box, count: 4, triangles: 3, groups: [[0, 9, 0]], profile: {}, laced: false }
  const raw = new Uint8Array(24 + 18)
  const rv = new DataView(raw.buffer)
  q.flat().forEach((v, i) => rv.setUint16(2 * i, v, true))
  tris.forEach((v, i) => rv.setUint16(24 + 2 * i, v, true))
  const plain = readTemplate(file(head, raw).buffer)
  const planes = new Uint8Array(24)
  const pv = new DataView(planes.buffer)
  for (let a = 0; a < 3; a++) for (let i = 0; i < 4; i++) pv.setUint16(2 * (a * 4 + i), (q[i][a] - (i ? q[i - 1][a] : 0) + 65536) % 65536, true)
  const vi = varint(tris.map((t, i) => { const d = t - (i ? tris[i - 1] : 0); return d < 0 ? -2 * d - 1 : 2 * d }))
  const body = new Uint8Array(planes.length + vi.length + 3); body.set(planes); body.set(vi, planes.length)
  const packed = await openTemplate(await gzip(file({ ...head, packed: 2, indexBytes: vi.length }, body)))
  assert.deepEqual(Array.from(packed.index), tris)
  assert.deepEqual(Array.from(packed.positions).map(v => +v.toFixed(5)), Array.from(plain.positions).map(v => +v.toFixed(5)))
})
