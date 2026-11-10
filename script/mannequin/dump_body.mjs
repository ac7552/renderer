// The body mesh as the page loads it (positions, skin weights, bone names), for slim_women.py:
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
    bones: m.skeleton.bones.map(b => b.name), index: Array.from(g.index.array), matrixWorld: m.matrixWorld.elements, bindMatrix: m.bindMatrix.elements,
    attrs: Object.keys(g.attributes)
  }
})
fs.writeFileSync(process.argv[2], JSON.stringify(data))
console.log(data.attrs, data.bones.length, data.pos.length / 3, data.matrixWorld)
await browser.close()
