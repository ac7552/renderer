// Run with: node --test tests/javascript/*.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import { FAMILIES, familyFromWords, lastFor, measureSide } from "../../renderer/static/js/lib/garments/lasts.js"

test("a shoe's family from its listing's words, else from its drawing style", () => {
  assert.equal(familyFromWords("New Balance 990v6 Made in USA"), "runner")
  assert.equal(familyFromWords("Nike Air Force 1 '07"), "court")
  assert.equal(familyFromWords("New Balance 9060"), "runner")
  assert.equal(familyFromWords("Timberland 6 Inch Premium Boot"), "combat")
  assert.equal(familyFromWords("Common Projects Chelsea Boot Suede"), "chelsea")
  assert.equal(familyFromWords("Manolo Blahnik BB 90 Pump"), "pump")
  assert.equal(familyFromWords("Repetto Cendrillon Ballet Flat"), "flat")
  assert.equal(familyFromWords("Birkenstock Arizona"), "sandal")
  assert.equal(familyFromWords("Gucci Horsebit Loafer"), "loafer")
  assert.equal(familyFromWords("", "boot"), "combat")
  assert.equal(familyFromWords("", "hightop"), "hightop")
  for (const family of Object.values(FAMILIES)) assert.ok(["sneaker", "hightop", "boot", "loafer", "sandal"].includes(family.style))
})

test("a loafer by its name isn't a pump for the heel in its description", () => {
  const margiela = "Maison Margiela Decortique Loafers - Black Loafers Decortique Loafers silhouette Calfskin and suede upper Penny strap Slip-on style Block heel Rubber outsole"
  // (Without its name the words' heel reads as a pump's, as before.)
  assert.equal(familyFromWords(margiela), "pump")
  assert.equal(familyFromWords(margiela, "sneaker", "Maison Margiela Decortique Loafers - Black"), "loafer")
  assert.equal(lastFor(margiela, "sneaker", null, "Maison Margiela Decortique Loafers - Black").family, "loafer")
  assert.equal(familyFromWords("Dr. Martens 1461 Oxford Stacked heel", "loafer", "Dr. Martens 1461 Oxford"), "derby")
  // A Gibson (the English derby) and a shoe by its count of eyelets are derbies; a boot by its count is a lace-up boot.
  assert.equal(familyFromWords("Solovair 3-Eye Gibson Shoe Made in England 100% leather upper Goodyear welt", "sneaker", "Solovair 3-Eye Gibson Shoe"), "derby")
  assert.equal(familyFromWords("Dr. Martens 1461 Smooth Leather 3 Eyelet Shoes"), "derby")
  assert.equal(familyFromWords("Dr. Martens 1460 8-Eye Boot Smooth Leather"), "combat")
  // A heel its own name says so is still one, and so is one whose name says nothing about what it is.
  assert.equal(familyFromWords("Prada Heeled Loafer 75mm heel height", "loafer", "Prada Heeled Loafer"), "pump")
  assert.equal(familyFromWords("Gianvito Rossi Loafer Pump Block heel", "loafer", "Gianvito Rossi Loafer Pump"), "pump")
  assert.equal(familyFromWords("Jimmy Choo Romy 85 Heel height: 3.3in", "loafer", "Jimmy Choo Romy 85"), "pump")
  // A colourway isn't the shoe's name: an "Oxford Blue" or a "Penny" pump stays a pump.
  assert.equal(familyFromWords("Manolo Blahnik BB 90 - Oxford Blue Heels Stiletto heel", "loafer", "Manolo Blahnik BB 90 - Oxford Blue"), "pump")
  // A heeled boot or a heeled slipper stays with its heel.
  assert.equal(familyFromWords("Femme LA Vienna Boot - Chocolate Boots Heel height: 3.93in", "boot", "Femme LA Vienna Boot - Chocolate"), "pump")
  assert.equal(familyFromWords("Femme LA Maeve Slipper - Plum Heels Kitten heel", "loafer", "Femme LA Maeve Slipper - Plum"), "pump")
})

test("a full grain boot isn't a rain boot, flat-woven laces aren't a flat, and derbies are a derby", () => {
  assert.equal(familyFromWords("Clarks Suede Wallabee - Maple Boots Wallabee silhouette Suede upper Flat-woven laces Crepe outsole", "boot"), "combat")
  assert.equal(familyFromWords("Dr. Martens Lowell - Black / Aniline Derbies Leather upper Brass eyelets", "loafer"), "derby")
  assert.equal(familyFromWords("Timberland Textured Premium 6-Inch Boots - Beige Full Grain Boots Leather upper Rubber lug outsole", "boot"), "combat")
  assert.equal(familyFromWords("Hunter Original Tall Rain Boots", "boot"), "tall")
})

// A side reading like print.js's shoeSide: n columns heel (0) to toe (1), the shoe `height` pixels tall.
function side({ n = 40, height = 100, sole = 0.1, heel = 0, back = 0.5, front = 0.35, blunt = 0 } = {}) {
  const bottom = Array.from({ length: n }, () => height)
  const top = Array.from({ length: n }, (_, i) => height - height * (back + (front - back) * Math.min(1, i / (n * 0.45))))
  const soleProfile = Array.from({ length: n }, (_, i) => sole + heel * Math.max(0, 1 - i / (n * 0.3)))
  // (The front edge per height row: a tapered toe reaches less far higher up.)
  const frontEdge = Array.from({ length: 10 }, (_, k) => 1 - (k < 2 ? 0 : blunt))
  return { top, bottom, sole: bottom.map((b, i) => b - soleProfile[i] * height), soleProfile, front: frontEdge, height, aspect: 1, left: 0, right: 200 }
}

test("the side photo measures the sole, a heel's rise and the collar", () => {
  const m = measureSide(side({ sole: 0.1, heel: 0.3, back: 0.5, front: 0.3 }))
  assert.ok(Math.abs(m.sole.ball - 0.1) < 0.02)
  assert.ok(m.sole.heel > 0.3, `heel sole ${m.sole.heel}`)
  assert.ok(m.heelRise > 0.2 && m.heelRise < 0.32, `rise ${m.heelRise}`)
  assert.ok(Math.abs(m.collar.back - 0.5) < 0.06, `back ${m.collar.back}`)
  assert.ok(Math.abs(m.collar.front - 0.3) < 0.06, `front ${m.collar.front}`)
  assert.equal(measureSide(null), null)
})

test("the last: the family's numbers, then the photo's over them, in metres", () => {
  const plain = lastFor("Nike Air Force 1", "sneaker", null)
  assert.equal(plain.family, "court")
  assert.equal(plain.params.measured, undefined)
  assert.equal(plain.params.sole, FAMILIES.court.sole)

  // A pump photo 100 px tall over 200 px long: 0.135 m tall for a 0.27 m foot; a heel a third of that.
  const pump = lastFor("Leather pump", "loafer", side({ sole: 0.06, heel: 0.33, back: 0.45, front: 0.25 }))
  assert.equal(pump.family, "pump")
  assert.ok(pump.params.measured)
  assert.ok(pump.params.heel > 0.03 && pump.params.heel < 0.05, `heel ${pump.params.heel}`)
  assert.ok(pump.params.back > pump.params.front)
  assert.ok(pump.params.toeSole <= pump.params.sole)
  // A boot with a tall shaft and a blunt toe.
  const boot = lastFor("Lace-up boot", "boot", side({ height: 180, sole: 0.1, back: 0.9, front: 0.8, blunt: 0 }))
  assert.equal(boot.family, "combat")
  assert.ok(boot.params.back > 0.15, `shaft ${boot.params.back}`)
  assert.ok(boot.params.square > 1.9, `square ${boot.params.square}`)
  assert.equal(boot.params.heel, 0)
  // A pointed toe tapers: rounder in cross-section than the boot's.
  const pointed = lastFor("Leather pump", "loafer", side({ sole: 0.06, heel: 0.33, blunt: 0.08 }))
  assert.ok(pointed.params.square < boot.params.square - 0.4)
})
