// The path tracer's tree over what it draws (three-mesh-bvh's, which three-gpu-pathtracer builds its scene
// into), built in a Web Worker. Over a shirt, jeans and the mannequin (300,000 triangles) it takes about a
// second, and the tracer by itself builds it on the page: a second the page stood still each time the clothes
// settled. trace.js sends the mesh's points and triangles (remote_drape.js's loader starts this module in a
// worker); the tree is built here and its buffers sent back, which the page makes a tree of again.
//
// handle(message, post): one message from the page; post(message, transfer) sends one back.
//   { type: "tree", id, position, index, groups, options } → { type: "answer", id, roots, indirect }
import * as THREE from "three"
import { PathTracingSceneGenerator } from "three-gpu-pathtracer"

// The tree's class. The library is bundled inside the tracer, which doesn't export it: it's taken from a tree
// the tracer's own scene generator builds over one triangle (so the page's and the worker's are the tracer's own).
let Tree = null
export function treeClass() {
  if (Tree) return Tree
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]), 3))
  Tree = new PathTracingSceneGenerator(new THREE.Mesh(geometry, new THREE.MeshStandardMaterial())).generate().bvh.constructor
  return Tree
}

// What the page sends for a geometry's tree: its points and triangles (copies, to hand over), its groups, and
// the tree's options less what can't be sent (a progress callback).
export function treeRequest(geometry, options = {}) {
  const position = geometry.attributes.position.array.slice(), index = geometry.index ? geometry.index.array.slice() : null
  const plain = Object.fromEntries(Object.entries(options).filter(([, value]) => typeof value !== "function"))
  return { message: { type: "tree", position, index, groups: geometry.groups.map(g => ({ ...g })), options: plain }, transfer: [position.buffer, ...(index ? [index.buffer] : [])] }
}

// The tree the worker built, on the page's geometry (its triangles as they are: the tree keeps its own order
// of them, options.indirect, as the tracer asks).
export function treeFrom(answer, geometry) {
  return treeClass().deserialize({ roots: answer.roots, indirectBuffer: answer.indirect ?? null, index: null }, geometry, { setIndex: false })
}

// The tree's buffers for a request: { roots, indirect } and what to hand over with them.
export function buildTree({ position, index, groups, options }) {
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute("position", new THREE.BufferAttribute(position, 3))
  if (index) geometry.setIndex(new THREE.BufferAttribute(index, 1))
  for (const g of groups ?? []) geometry.addGroup(g.start, g.count, g.materialIndex)
  const tree = new (treeClass())(geometry, options)
  const { roots, indirectBuffer } = treeClass().serialize(tree, { cloneBuffers: false })
  return { roots, indirect: indirectBuffer ?? null, transfer: [...roots, ...(indirectBuffer ? [indirectBuffer.buffer] : [])] }
}

export function handle(message, post) {
  if (message.type !== "tree") return
  try {
    const { roots, indirect, transfer } = buildTree(message)
    post({ type: "answer", id: message.id, roots, indirect }, transfer)
  } catch (error) {
    post({ type: "error", id: message.id, error: String(error?.stack ?? error) })
  }
}
