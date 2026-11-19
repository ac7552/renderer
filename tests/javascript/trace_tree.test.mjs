// Run with: node --test tests/javascript/*.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import "./support/lib.mjs"

const THREE = await import("three")
const { treeClass, treeRequest, buildTree, treeFrom, handle } = await import("lib/trace_tree")

test("the tracer's tree built elsewhere from a mesh's points and triangles is the tree built on the mesh", () => {
  const geometry = new THREE.TorusKnotGeometry(1, 0.3, 120, 24)
  const options = { strategy: 2, maxLeafTris: 1, indirect: true, onProgress: () => {} }
  const { message, transfer } = treeRequest(geometry, options)
  // What's sent is a copy (handed over, the page keeps its own) and nothing a worker can't be sent.
  assert.notEqual(message.position.buffer, geometry.attributes.position.array.buffer)
  assert.deepEqual(Object.keys(message.options).sort(), ["indirect", "maxLeafTris", "strategy"])
  assert.equal(transfer.length, 2)
  structuredClone(message)
  const built = buildTree(message)
  assert.ok(built.roots.every(root => root instanceof ArrayBuffer) && built.indirect.length === geometry.index.count / 3)
  const index = Array.from(geometry.index.array)
  const tree = treeFrom({ roots: built.roots, indirect: built.indirect }, geometry)
  // The page's triangles are as they were (the tree keeps its own order of them), and rays find what a tree
  // built on the page finds.
  assert.deepEqual(Array.from(geometry.index.array), index)
  const here = new (treeClass())(geometry.clone(), { strategy: 2, maxLeafTris: 1, indirect: true })
  for (let k = 0; k < 40; k++) {
    const a = k * 2.399, origin = new THREE.Vector3(4 * Math.cos(a), (k % 7 - 3) * 0.3, 4 * Math.sin(a))
    const ray = new THREE.Ray(origin, origin.clone().multiplyScalar(-1).add(new THREE.Vector3(0.1 * (k % 3), 0.05 * (k % 5), 0)).normalize())
    const one = tree.raycastFirst(ray, THREE.DoubleSide), other = here.raycastFirst(ray, THREE.DoubleSide)
    assert.equal(Boolean(one), Boolean(other))
    if (one) assert.ok(Math.abs(one.distance - other.distance) < 1e-6 && one.faceIndex === other.faceIndex)
  }
})

test("the worker answers a tree's request with its buffers, or says what went wrong", () => {
  const geometry = new THREE.BoxGeometry(1, 1, 1, 4, 4, 4)
  const sent = []
  handle({ id: "tree:1", ...treeRequest(geometry, { strategy: 2, maxLeafTris: 1, indirect: true }).message }, (message, transfer) => sent.push([message, transfer]))
  assert.equal(sent[0][0].type, "answer")
  assert.equal(sent[0][0].id, "tree:1")
  assert.ok(sent[0][1].includes(sent[0][0].roots[0]) && sent[0][1].includes(sent[0][0].indirect.buffer))
  handle({ type: "tree", id: "tree:2", position: null, index: null, options: {} }, (message, transfer) => sent.push([message, transfer]))
  assert.equal(sent[1][0].type, "error")
  assert.equal(sent[1][0].id, "tree:2")
  // (Anything else isn't its to answer.)
  handle({ type: "sew", id: 3 }, () => assert.fail("answered"))
})
