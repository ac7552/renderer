// The body mesh as the page loads it (positions, skin weights, bone names and heads), for slim_women.py and slim_arms.py:
//   node script/mannequin/dump_body.mjs tmp/body.json [http://127.0.0.1:8787]
import { createRequire } from "node:module"
import fs from "node:fs"
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE ?? "playwright")
const browser = await chromium.launch({ args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] })
const page = await browser.newPage({ viewport: { width: 400, height: 600 } })
await page.goto(`${process.argv[3] ?? "http://127.0.0.1:8787"}/stage.html`)
await page.waitForFunction(() => window.stageReady, null, { timeout: 120000 })
const data = await page.evaluate(() => {
  const m = window.stage.meshes.body, g = m.geometry
  m.updateMatrixWorld(true)
  return {
    pos: Array.from(g.attributes.position.array), si: Array.from(g.attributes.skinIndex.array), sw: Array.from(g.attributes.skinWeight.array),
    bones: m.skeleton.bones.map(b => b.name),
    // Each bone's head as bound, in the mesh's own space (for slim_arms.py: the arms' axes).
    heads: m.skeleton.boneInverses.map(inv => { const e = inv.clone().invert().premultiply(m.bindMatrixInverse).elements; return [e[12], e[13], e[14]] }), index: Array.from(g.index.array), matrixWorld: m.matrixWorld.elements, bindMatrix: m.bindMatrix.elements,
    attrs: Object.keys(g.attributes)
  }
})
fs.writeFileSync(process.argv[2], JSON.stringify(data))
console.log(data.attrs, data.bones.length, data.pos.length / 3, data.matrixWorld)
await browser.close()
