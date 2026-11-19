// Telling the garment from what isn't it in a photo, by its colours alone. (The full app pointed a segmentation
// model at the garment as well; the renderer runs no models, so a photo is read as the colours give it, as the app
// did whenever its model couldn't load.)

import { garmentMask, isSkin } from "lib/garments/print"

// A key for a photo by its address (a data: URL's length and some of its middle and end, not all of it).
export function photoKey(src) {
  if (typeof src !== "string") return null
  return `${src.length}:${src.slice(Math.floor(src.length / 2), Math.floor(src.length / 2) + 48)}:${src.slice(-48)}`
}

// A store photo with what isn't the garment painted out: without a model there's nothing to find, so the photo as
// it is (src: a data: URL).
export async function cleanPhoto(src) {
  return src
}

// The garment alone in a photo of someone wearing it (data: RGBA, w by h; kind "top", "dress" or "trousers"): a
// mask (1 per pixel) of the person less their skin and anything above their chin, or null when they can't be found.
export async function wornGarmentMask(data, w, h, kind = "top") {
  const person = garmentMask(data, w, h)?.mask
  if (!person) return null
  const n = w * h
  const skin = new Uint8Array(n)
  for (let i = 0; i < n; i++) if (person[i] && isSkin(data[4 * i], data[4 * i + 1], data[4 * i + 2])) skin[i] = 1
  let top = -1, bottom = -1
  for (let y = 0; y < h && top < 0; y++) for (let x = 0; x < w; x++) if (person[y * w + x]) { top = y; break }
  for (let y = h - 1; y >= 0 && bottom < 0; y--) for (let x = 0; x < w; x++) if (person[y * w + x]) { bottom = y; break }
  if (top < 0 || bottom - top < 0.3 * h) return null
  const tall = bottom - top
  // The face: the skin in the person's top third, as a box; the cloth starts below its chin.
  let fx0 = w, fx1 = -1, fy0 = h, fy1 = -1, faceN = 0
  for (let y = top; y < top + tall / 3; y++) for (let x = 0; x < w; x++) if (skin[y * w + x]) { faceN++; fx0 = Math.min(fx0, x); fx1 = Math.max(fx1, x); fy0 = Math.min(fy0, y); fy1 = Math.max(fy1, y) }
  const face = faceN > 0.002 * n ? { x: (fx0 + fx1) / 2, y: (fy0 + fy1) / 2, top: fy0, bottom: fy0 + (fy1 - fy0) * 0.75, half: (fx1 - fx0) / 2 } : null
  const from = face ? Math.round(face.bottom) : top
  // The cloth's candidate: the person less skin, below the chin.
  const candidate = new Uint8Array(n)
  for (let y = from; y <= bottom; y++) for (let x = 0; x < w; x++) { const i = y * w + x; if (person[i] && !skin[i]) candidate[i] = 1 }
  // Points down the middle of it: the torso for a top or a dress, the hips and both legs for trousers.
  const runAt = (y, near) => {
    let best = null, start = -1
    for (let x = 0; x <= w; x++) {
      const on = x < w && candidate[y * w + x]
      if (on && start < 0) start = x
      if (!on && start >= 0) { const run = [start, x - 1]; if (!best || (near == null ? run[1] - run[0] > best[1] - best[0] : Math.abs((run[0] + run[1]) / 2 - near) < Math.abs((best[0] + best[1]) / 2 - near))) best = run; start = -1 }
    }
    return best && best[1] - best[0] > 0.03 * w ? [(best[0] + best[1]) / 2, y] : null
  }
  const centre = face ? face.x : w / 2
  const shares = kind === "trousers" ? [0.5, 0.65, 0.85] : [0.28, 0.4, 0.55]
  const positives = shares.map(t => runAt(Math.round(top + t * tall), centre)).filter(Boolean)
  if (!positives.length) return null
  return candidate
}

// How long a worn garment's sleeves are, from a photo of someone wearing it (data: RGBA, w by h): "none"
// (the arms bare from the shoulder), "short" (bare below the upper arm), "long" (covered to the wrist), or
// null when the arms can't be found. The arms are the person's outermost columns either side of the torso,
// from the shoulders to the hips; what share of them is skin, over the upper arm and over the forearm,
// says how far the sleeves reach.
export function wornSleeves(data, w, h) {
  const person = garmentMask(data, w, h)?.mask
  if (!person) return null
  let top = -1, bottom = -1
  for (let y = 0; y < h && top < 0; y++) for (let x = 0; x < w; x++) if (person[y * w + x]) { top = y; break }
  for (let y = h - 1; y >= 0 && bottom < 0; y--) for (let x = 0; x < w; x++) if (person[y * w + x]) { bottom = y; break }
  if (top < 0) return null
  const tall = bottom - top
  // The shoulders are about a fifth of the way down a photo cropped at the knee or above, an eighth on a
  // full figure; the hips about half or a third. Read the arms over 25%–40% (upper arm) and 42%–55% (forearm).
  const band = (from, to) => {
    let skin = 0, all = 0
    for (let y = Math.round(top + from * tall); y < top + to * tall; y += 2) {
      let a = -1, b = -1
      for (let x = 0; x < w; x++) if (person[y * w + x]) { if (a < 0) a = x; b = x }
      if (a < 0) continue
      const reach = Math.max(2, Math.round((b - a) * 0.14))
      for (const [x0, x1] of [[a, a + reach], [b - reach, b]]) for (let x = x0; x <= x1; x++) {
        const i = y * w + x
        if (!person[i]) continue
        all++
        if (isSkin(data[4 * i], data[4 * i + 1], data[4 * i + 2])) skin++
      }
    }
    return all > 40 ? skin / all : null
  }
  const upper = band(0.25, 0.4), fore = band(0.42, 0.55)
  if (upper == null || fore == null) return null
  if (upper > 0.5) return "none"
  if (fore > 0.5) return "short"
  if (fore < 0.2 && upper < 0.2) return "long"
  return null
}

// A shoe's outline from a model: none here.
export async function shoeModelMask() {
  return null
}
