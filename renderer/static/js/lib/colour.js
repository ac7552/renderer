// Colour arithmetic for metering the drawn cloth to its shop photo (stage.js#meter) and the accuracy checks.
// An sRGB colour (hex, or [r, g, b] 0 to 255) in linear light, 0 to 1.
export function linearOf(color) {
  const rgb = typeof color === "string" ? [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16)) : color
  return rgb.map(v => { const c = v / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 })
}

// CIE76 colour difference between two sRGB colours ([r, g, b], 0 to 255): about 2.3 is a just-noticeable step.
export function deltaE(a, b) {
  const lab = rgb => {
    const [r, g, bl] = linearOf(rgb)
    const xyz = [(0.4124 * r + 0.3576 * g + 0.1805 * bl) / 0.95047, 0.2126 * r + 0.7152 * g + 0.0722 * bl, (0.0193 * r + 0.1192 * g + 0.9505 * bl) / 1.08883]
    const f = t => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116)
    const [fx, fy, fz] = xyz.map(f)
    return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)]
  }
  const p = lab(a), q = lab(b)
  return Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2])
}

// A garment in two colours far apart (a varsity's navy body and white sleeves), drawn: metered on its whole
// cloth, the white pulled its middle colour up and the meter darkened everything to bring it down to the navy
// the photo's cloth was read as. samples: [[r...], [g...], [b...]] (sRGB, 0 to 255); target: the photo's cloth
// ([r, g, b]). Split two ways (two means, a few rounds from the darkest and lightest tenth); when the two
// colours are BLOCKS_APART or more apart and the lesser is BLOCKS_SHARE or more of them, only the block nearer
// the target is kept. Otherwise the samples as they are.
const BLOCKS_APART = 140, BLOCKS_SHARE = 0.12
export function blockNear(samples, target) {
  const n = samples[0].length
  if (!target || n < 40) return samples
  const px = k => [samples[0][k], samples[1][k], samples[2][k]]
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])
  const order = Array.from({ length: n }, (_, k) => k).sort((a, b) => samples[0][a] + samples[1][a] + samples[2][a] - samples[0][b] - samples[1][b] - samples[2][b])
  let c = [px(order[Math.floor(n * 0.1)]), px(order[Math.floor(n * 0.9)])]
  const side = new Uint8Array(n)
  let count = [0, 0]
  for (let round = 0; round < 6; round++) {
    const sum = [[0, 0, 0], [0, 0, 0]]
    count = [0, 0]
    for (let k = 0; k < n; k++) {
      const p = px(k), s = dist(p, c[0]) <= dist(p, c[1]) ? 0 : 1
      side[k] = s; count[s]++
      for (let ch = 0; ch < 3; ch++) sum[s][ch] += p[ch]
    }
    c = c.map((old, s) => (count[s] ? sum[s].map(v => v / count[s]) : old))
  }
  if (dist(c[0], c[1]) < BLOCKS_APART || Math.min(...count) < BLOCKS_SHARE * n) return samples
  const keep = dist(c[0], target) <= dist(c[1], target) ? 0 : 1
  return samples.map(channel => channel.filter((_, k) => side[k] === keep))
}

// The middle colour of samples ([[r...], [g...], [b...]]): each channel's median, then again over the samples
// within TRIM of it (when half or more are). A cream shirt's red embroidery, a tenth of it, pulled its green
// and blue medians down more than its red, and the meter's white balance, making up, drew the cream mint.
const TRIM = 80
export function middleColour(samples) {
  const median = v => { const s = [...v].sort((a, b) => a - b); return s[s.length >> 1] }
  const m = samples.map(median)
  const n = samples[0].length
  const near = []
  for (let k = 0; k < n; k++) if (Math.hypot(samples[0][k] - m[0], samples[1][k] - m[1], samples[2][k] - m[2]) <= TRIM) near.push(k)
  if (near.length < n / 2 || near.length === n) return m
  return samples.map(channel => median(near.map(k => channel[k])))
}

// The colour of samples ([[r...], [g...], [b...]]) where the light falls on them: of those within TRIM of their
// middle colour (so a print or another colour's stripe doesn't count), the mean of the ones between the 60th
// and the 85th in a hundred by brightness. A shop photographs a garment evenly lit, so its cloth's colour there
// is its lit colour; the page's figure stands in a key light with its sides and the insides of its legs in
// shade, a third or more of what's seen, and the middle colour of that is a shaded one. Metered by its
// middle, grey sweatpants were drawn 40 levels too light where the light fell (washed out) to bring their
// shaded sides up to the photo's grey. (Not the very brightest: a sheen's highlights aren't the cloth's colour.)
const LIT = [0.6, 0.85]
export function litColour(samples) {
  const m = middleColour(samples)
  const n = samples[0].length
  const near = []
  for (let k = 0; k < n; k++) if (Math.hypot(samples[0][k] - m[0], samples[1][k] - m[1], samples[2][k] - m[2]) <= TRIM) near.push(k)
  const use = near.length >= n / 2 ? near : Array.from({ length: n }, (_, k) => k)
  const light = k => 0.2126 * samples[0][k] + 0.7152 * samples[1][k] + 0.0722 * samples[2][k]
  use.sort((a, b) => light(a) - light(b))
  const from = Math.floor(use.length * LIT[0]), to = Math.max(from + 1, Math.ceil(use.length * LIT[1]))
  const sum = [0, 0, 0]
  for (let k = from; k < to; k++) for (let c = 0; c < 3; c++) sum[c] += samples[c][use[k]]
  return sum.map(v => Math.round(v / (to - from)))
}
