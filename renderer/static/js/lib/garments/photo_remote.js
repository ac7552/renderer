// What the page asks of photos beyond their colours. The full app ran AI models here (in a worker); the renderer runs
// none, so a model's question is answered with an error, as the app's was when its models couldn't load (each caller
// goes on without the answer). One question isn't a model's: the camera an angled shoe photo was taken from
// (angled.js's fitPose), worked out here on the page.
import { fitPose } from "lib/garments/angled"

const NO_MODELS = () => Promise.reject(new Error("The renderer has no photo models."))

export function photoMasks() { return NO_MODELS() }
export function photoSummaryOf() { return NO_MODELS() }
export function photoDepth() { return NO_MODELS() }
export function warmPhotoModel() { return NO_MODELS() }

// The camera a pair's angled photo was taken from, or null. geometry: the shoe as built; angled: readAngled's reading.
export async function photoPose(geometry, angled) {
  if (!geometry.attributes.normal) geometry.computeVertexNormals()
  return fitPose(geometry, angled)
}
