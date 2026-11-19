// The full app could send store photos to a vision service on its server for its AI models' readings. The renderer
// has no such service and runs no models: every question here answers that there is none, as the app's did when no
// service was configured, and the callers read photos by their colours alone.

export function visionUrl() { return null }
export function visionDown() { return true }
export async function remoteMasks() { return null }
export async function remoteEmbedding() { return null }
export function visionFeatures() { return Promise.resolve({}) }
export async function remoteParse() { return null }

// What a clothes-parsing model's labels say isn't the garment: a person's skin, hair and face, the
// backdrop, and what's worn with it. (SegFormer's clothes labels, as the model names them.)
const NOT_CLOTH = /^(background|hair|face|hat|sunglasses|left[- ]?(arm|leg|shoe)|right[- ]?(arm|leg|shoe)|bag)$/i

// The cloth mask (Uint8Array, 1 for cloth) with what the parse says isn't cloth taken off it, in place.
// Only taken off, never added; and not at all when it would take off more than `most` of it (a model
// trained on people can misread a garment laid flat). Returns how much was taken off (a share).
export function trimByParse(mask, parse, most = 0.35) {
  const foreign = parse.labels.map(label => NOT_CLOTH.test(label.trim()))
  let on = 0, off = 0
  for (let i = 0; i < mask.length; i++) {
    if (!mask[i]) continue
    on++
    const k = parse.map[i]
    if (k !== 255 && foreign[k]) off++
  }
  if (!on || off / on > most) return 0
  for (let i = 0; i < mask.length; i++) {
    const k = parse.map[i]
    if (mask[i] && k !== 255 && foreign[k]) mask[i] = 0
  }
  return off / on
}
