// Depth from a shop photo. The full app read it with a depth model (Depth Anything); the renderer runs no models, so
// there's never a reading (null), and shoes and garments are built without relief, as they were whenever the model
// couldn't load.

export const DEPTH_SIZE = 518

export async function readDepth() { return null }

export async function depthForSide() { return null }

// Depth sampled at a share of the picture's width and height (u, v in 0..1), bilinear.
export function depthAt(depth, u, v) {
  const x = Math.min(depth.w - 1, Math.max(0, u * (depth.w - 1))), y = Math.min(depth.h - 1, Math.max(0, v * (depth.h - 1)))
  const x0 = Math.floor(x), y0 = Math.floor(y), x1 = Math.min(depth.w - 1, x0 + 1), y1 = Math.min(depth.h - 1, y0 + 1)
  const fx = x - x0, fy = y - y0
  const d = depth.data
  return (d[y0 * depth.w + x0] * (1 - fx) + d[y0 * depth.w + x1] * fx) * (1 - fy) + (d[y1 * depth.w + x0] * (1 - fx) + d[y1 * depth.w + x1] * fx) * fy
}
